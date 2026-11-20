"""App Store numbers for Admin from Apple's Analytics Reports API.

The Admin Web visits page shows them under App Store, and the Dashboard App
downloads card adds App Store downloads beside the GitHub counters
(docs/admin-behavior-contract.md). They are Apple's own population: App Store
impressions, product page views and downloads as Apple reports them, never
app, web installer, Umami or Search Console statistics, and they are not
reconciled with any of them (contracts/STATISTICS_CONTRACT.md).

How it works (Apple: Analytics Reports API, "Downloading Analytics Reports"):

* An ``ONGOING`` report request for the app makes Apple generate reports every
  day. Creating it needs an Admin key once (``request --apply`` below, or the
  owner's key setup script); the server keeps only a Sales and Reports key,
  which can list and download the reports.
* The scheduler reads, about once an hour, the daily instances of four
  reports: App Store Discovery and Engagement and App Store Downloads, each
  Standard and Detailed. Every instance is a set of gzip tab-separated
  segments. Standard rows give the totals, sources and the Dashboard numbers;
  Detailed rows (noised, rows under 5 users omitted) give only the campaign
  numbers, because only Detailed reports have the Campaign column.
* Rows become daily aggregates in the catalog database. A newer processing
  date replaces a day (Apple: "Instances from a more recent processingDate
  overwrite instances with an earlier processingDate ... Don't merge records
  for a Date across two report instances"), and processed instance IDs are
  kept, so a second run never doubles a count. Admin reads only that table.

The private key stays on the server: it is read from the environment (the
key itself or the path of a file holding it), a token is signed for at most
ten minutes, and both are sent only to api.appstoreconnect.apple.com, never
logged, never followed through a redirect and never put in a response.
Report files are downloaded from the address Apple gives, without the token.
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterator

LOGGER = logging.getLogger(__name__)

API_HOST = "api.appstoreconnect.apple.com"
API_BASE = "https://" + API_HOST
DEFAULT_APP_ID = "6828556832"
CONSOLE_URL = "https://appstoreconnect.apple.com/analytics"
AUDIENCE = "appstoreconnect-v1"
# Apple accepts at most 20 minutes; the token is renewed a minute early.
TOKEN_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_SEGMENT_BYTES = 32 * 1024 * 1024
MAX_SEGMENT_TEXT_BYTES = 256 * 1024 * 1024
MAX_PAGES = 25
MAX_INSTANCES_PER_RUN = 200
SYNC_INTERVAL_SECONDS = 60 * 60

ISSUER_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
KEY_ID_PATTERN = re.compile(r"[A-Z0-9]{10}")
APP_ID_PATTERN = re.compile(r"[0-9]{1,20}")

# The four reports, matched by category and name (Apple's documentation names
# the report group "App Store Downloads"; the instance list names it with a
# Standard or Detailed suffix).
REPORT_PATTERNS = (
    ("APP_STORE_ENGAGEMENT", re.compile(r"app store discovery and engagement (standard|detailed)"), "engagement"),
    ("COMMERCE", re.compile(r"(?:app store )?(?:app )?downloads? (standard|detailed)"), "downloads"),
)
KIND_METRICS = {
    "engagement": ("impressions", "product_page_views"),
    "downloads": ("first_time_downloads", "redownloads"),
}
METRICS = tuple(metric for metrics in KIND_METRICS.values() for metric in metrics)
LEVELS = ("standard", "detailed")

# Apple's Source Type values (report values are not case sensitive).
SOURCE_TYPES = {
    "app store search": "App Store search",
    "app store browse": "App Store browse",
    "app referrer": "App referrer",
    "web referrer": "Web referrer",
    "app clip": "App Clip",
    "notification": "Notification",
    "institutional purchase": "Institutional purchase",
    "unavailable": "Unavailable",
}
NO_CAMPAIGN = {"", "-", "null", "none", "(none)", "n/a"}


def report_kind(category: str, name: str) -> tuple[str, str] | None:
    """(kind, level) of a report Admin reads, or None."""
    text = " ".join(str(name or "").lower().split())
    for wanted, pattern, kind in REPORT_PATTERNS:
        match = pattern.fullmatch(text)
        if str(category or "").upper() == wanted and match:
            return kind, match.group(1)
    return None


# --- Settings -----------------------------------------------------------------

def load_private_key(raw: str):
    """The EC P-256 private key from a ``.p8`` text, its base64 body on one
    line, or the path of a file holding either. Raises ValueError without the
    key text in the message."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    text = raw.strip()
    if not text:
        raise ValueError("empty")
    # A path (a base64 body may start with "/" too, so only an existing file).
    if not text.startswith("-----BEGIN") and "\n" not in text and os.path.isfile(os.path.expanduser(text)):
        with open(os.path.expanduser(text), encoding="utf-8") as handle:
            text = handle.read().strip()
    text = text.replace("\\n", "\n")
    if not text.startswith("-----BEGIN"):
        body = "".join(text.split())
        if not re.fullmatch(r"[A-Za-z0-9+/=]+", body):
            raise ValueError("not a key")
        text = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(
            body[index:index + 64] for index in range(0, len(body), 64)) + "\n-----END PRIVATE KEY-----"
    try:
        key = load_pem_private_key(text.encode("ascii"), password=None)
    except (ValueError, TypeError, UnicodeEncodeError):
        raise ValueError("not a key") from None
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError("not an ES256 key")
    return key


@dataclass(frozen=True)
class AscSettings:
    issuer_id: str
    key_id: str
    private_key: Any = field(repr=False, compare=False)
    app_id: str = DEFAULT_APP_ID

    def __repr__(self) -> str:  # never show the key in a traceback or log
        return f"AscSettings(key_id={self.key_id!r}, app_id={self.app_id!r})"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "AscSettings | None":
        """The settings, or None (App Store then shows "not set up").

        ``ASC_PRIVATE_KEY`` holds the ``.p8`` key itself (or its base64 body
        on one line) or the path of a file holding it. An invalid set logs
        which setting is wrong, never its value, and does not stop the API.
        """
        environ = os.environ if environ is None else environ
        issuer = environ.get("ASC_ISSUER_ID", "").strip()
        key_id = environ.get("ASC_KEY_ID", "").strip()
        raw = environ.get("ASC_PRIVATE_KEY", "")
        app_id = environ.get("ASC_APP_ID", "").strip() or DEFAULT_APP_ID
        if not (issuer or key_id or raw.strip()):
            return None
        problems = []
        if not ISSUER_PATTERN.fullmatch(issuer):
            problems.append("ASC_ISSUER_ID")
        if not KEY_ID_PATTERN.fullmatch(key_id):
            problems.append("ASC_KEY_ID")
        try:
            key = load_private_key(raw)
        except (OSError, ValueError):
            key = None
            problems.append("ASC_PRIVATE_KEY")
        if not APP_ID_PATTERN.fullmatch(app_id):
            problems.append("ASC_APP_ID")
        if problems:
            LOGGER.warning("App Store statistics disabled: %s missing or invalid", ", ".join(problems))
            return None
        return cls(issuer_id=issuer.lower(), key_id=key_id, private_key=key, app_id=app_id)


# --- Token ----------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_token(issuer_id: str, key_id: str, private_key: Any, now: float, lifetime: int = TOKEN_SECONDS) -> str:
    """An ES256 JWT for App Store Connect (Apple: "Generating Tokens for API
    Requests"): header alg/kid/typ, payload iss/iat/exp/aud."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    if not 0 < lifetime <= 20 * 60:
        raise ValueError("token lifetime must be at most 20 minutes")
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    issued = int(now)
    payload = {"iss": issuer_id, "iat": issued, "exp": issued + lifetime, "aud": AUDIENCE}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." + _b64url(json.dumps(payload, separators=(",", ":")).encode()))
    r, s = decode_dss_signature(private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256())))
    return signing_input + "." + _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


# --- HTTP -----------------------------------------------------------------------

class AscError(Exception):
    """A failed App Store Connect step. ``reason`` is safe to log and store:
    no key, token, URL or response body."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the token to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        raise AscError(f"redirect HTTP {code}", code)


class _HttpsRedirectOnly(urllib.request.HTTPRedirectHandler):
    """Report files carry no token; a redirect may only stay on HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise AscError(f"redirect HTTP {code}", code)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_API_OPENER = urllib.request.build_opener(_NoRedirect)
_FILE_OPENER = urllib.request.build_opener(_HttpsRedirectOnly)

# (method, url, headers, body, limit) -> (status, bytes)
Transport = Callable[[str, str, dict[str, str], bytes | None, int], tuple[int, bytes]]


def http_transport(method: str, url: str, headers: dict[str, str], body: bytes | None, limit: int) -> tuple[int, bytes]:
    """One HTTPS request with the 10 second limit; the answer is cut at
    ``limit`` + 1 bytes. An error answer's body is never read."""
    opener = _API_OPENER if urllib.parse.urlsplit(url).hostname == API_HOST else _FILE_OPENER
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, response.read(limit + 1)
    except AscError:
        raise
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()  # the body is never read: it may echo the request
        return status, b""
    except TimeoutError:
        raise AscError("timeout") from None
    except urllib.error.URLError as error:
        reason = "timeout" if isinstance(error.reason, TimeoutError) else f"connection failed ({type(error.reason).__name__})"
        raise AscError(reason) from None
    except OSError as error:
        raise AscError(f"connection failed ({type(error).__name__})") from None


def _is_api_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and parts.hostname == API_HOST and parts.port in (None, 443) and not parts.username


class AscClient:
    """App Store Connect API calls with one key. The token is renewed before
    it expires and goes only to api.appstoreconnect.apple.com."""

    def __init__(self, issuer_id: str, key_id: str, private_key: Any, *,
                 transport: Transport = http_transport, clock: Callable[[], float] = time.time) -> None:
        self._issuer_id = issuer_id
        self._key_id = key_id
        self._key = private_key
        self._transport = transport
        self._clock = clock
        self._token: tuple[float, str] | None = None
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"AscClient(key_id={self._key_id!r})"

    @classmethod
    def from_settings(cls, settings: AscSettings, **kwargs: Any) -> "AscClient":
        return cls(settings.issuer_id, settings.key_id, settings.private_key, **kwargs)

    def _authorization(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token is None or self._token[0] - 60 <= now:
                try:
                    token = make_token(self._issuer_id, self._key_id, self._key, now)
                except Exception as error:  # noqa: BLE001 - never echo key material
                    raise AscError(f"token failed ({type(error).__name__})") from None
                self._token = (now + TOKEN_SECONDS, token)
            return "Bearer " + self._token[1]

    def _call(self, method: str, url: str, body: Any = None) -> tuple[int, Any]:
        if not _is_api_url(url):
            raise AscError("unexpected address")
        headers = {"Authorization": self._authorization(), "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        status, raw = self._transport(method, url, headers, data, MAX_RESPONSE_BYTES)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AscError("response too large")
        if status >= 400:
            return status, None
        try:
            return status, json.loads(raw) if raw else {}
        except ValueError:
            raise AscError("not JSON") from None

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = path if path.startswith("https://") else API_BASE + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        status, payload = self._call("GET", url)
        if status != 200 or not isinstance(payload, dict):
            raise AscError(f"HTTP {status}", status)
        return payload

    def post(self, path: str, body: Any) -> tuple[int, Any]:
        return self._call("POST", API_BASE + path, body)

    def pages(self, path: str, params: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
        """Every ``data`` item, following ``links.next`` on Apple's host only."""
        url: str | None = path
        for _ in range(MAX_PAGES):
            payload = self.get(url, params)
            params = None
            data = payload.get("data")
            if not isinstance(data, list):
                raise AscError("unexpected shape")
            yield from (item for item in data if isinstance(item, dict))
            following = (payload.get("links") or {}).get("next") if isinstance(payload.get("links"), dict) else None
            if not following:
                return
            if not isinstance(following, str) or not _is_api_url(following):
                raise AscError("unexpected address")
            url = following
        raise AscError("too many pages")

    def download(self, url: str) -> bytes:
        """A report file from the address Apple gave, without the token."""
        if urllib.parse.urlsplit(url).scheme != "https":
            raise AscError("unexpected address")
        status, raw = self._transport("GET", url, {"Accept": "*/*"}, None, MAX_SEGMENT_BYTES)
        if status != 200:
            raise AscError(f"report file HTTP {status}", status)
        if len(raw) > MAX_SEGMENT_BYTES:
            raise AscError("report file too large")
        return raw


# --- Report requests ------------------------------------------------------------------

def report_requests(client: AscClient, app_id: str) -> list[dict[str, Any]]:
    """The app's report requests as {id, accessType, stopped}."""
    found = []
    for item in client.pages(f"/v1/apps/{app_id}/analyticsReportRequests", {"limit": "200"}):
        attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        found.append({"id": str(item.get("id") or ""), "accessType": str(attributes.get("accessType") or ""),
                      "stopped": attributes.get("stoppedDueToInactivity") is True})
    return [item for item in found if item["id"]]


def request_state(requests: list[dict[str, Any]]) -> str:
    """``active``: an ongoing request that Apple still fills; ``stopped``:
    only stopped ones (Apple stops one that nobody reads for a long time);
    ``missing``: none."""
    ongoing = [item for item in requests if item["accessType"] == "ONGOING"]
    if any(not item["stopped"] for item in ongoing):
        return "active"
    return "stopped" if ongoing else "missing"


def create_report_request(client: AscClient, app_id: str, access_type: str) -> str:
    """POST one analyticsReportRequests (needs an Admin key). Returns
    ``created`` or ``already existed`` (409)."""
    status, payload = client.post("/v1/analyticsReportRequests", {"data": {
        "type": "analyticsReportRequests",
        "attributes": {"accessType": access_type},
        "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
    }})
    if status == 409:
        return "already existed"
    if status not in (200, 201) or not isinstance(payload, dict):
        raise AscError(f"HTTP {status}", status)
    return "created"


# --- Report files ---------------------------------------------------------------------

def _gunzip(raw: bytes) -> bytes:
    if raw[:2] != b"\x1f\x8b":
        if len(raw) > MAX_SEGMENT_TEXT_BYTES:
            raise AscError("report file too large")
        return raw
    out = io.BytesIO()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                if out.tell() > MAX_SEGMENT_TEXT_BYTES:
                    raise AscError("report file too large")
    except (OSError, EOFError, zlib.error):
        raise AscError("report file not gzip") from None
    return out.getvalue()


def source_label(value: str) -> str:
    text = " ".join(value.split())
    return SOURCE_TYPES.get(text.lower(), text[:80] or "Unavailable")


def campaign_token(value: str) -> str:
    text = value.strip()
    return "" if text.lower() in NO_CAMPAIGN else text[:200]


Rows = dict[tuple[str, str, str, str, str, str], int]  # (day, metric, source, campaign, territory, device) -> count


def parse_report(raw: bytes, kind: str, level: str, app_id: str) -> Rows:
    """Daily aggregates of one report file. Columns are found by name (Apple
    may move them); an unknown column is ignored, a missing one stops the
    instance. Only the counted rows are kept: Standard has no campaign;
    Detailed rows without a campaign are left out."""
    text = _gunzip(raw).decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    reader = csv.reader(io.StringIO(text), delimiter="\t" if "\t" in first or "," not in first else ",")
    try:
        header = [" ".join(name.lower().split()) for name in next(reader)]
    except StopIteration:
        return {}
    column = {name: index for index, name in enumerate(header)}
    required = ["date", "counts", "source type", "territory"] + (
        ["event", "page type"] if kind == "engagement" else ["download type"])
    if level == "detailed":
        required.append("campaign")
    missing = [name for name in required if name not in column]
    if missing:
        raise AscError("report columns missing: " + ", ".join(missing))
    value = lambda row, name: row[column[name]] if name in column and column[name] < len(row) else ""
    rows: Rows = {}
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        app = value(row, "app apple identifier").strip()
        if app and app != app_id:
            continue
        try:
            day = date.fromisoformat(value(row, "date").strip()[:10]).isoformat()
            count = int(value(row, "counts").strip())
        except ValueError:
            continue
        if count <= 0:
            continue
        if kind == "engagement":
            event = value(row, "event").strip().lower()
            if event == "impression":
                metric = "impressions"
            elif event == "page view" and value(row, "page type").strip().lower() == "product page":
                metric = "product_page_views"
            else:
                continue
        else:
            download = value(row, "download type").strip().lower()
            metric = {"first-time download": "first_time_downloads", "redownload": "redownloads"}.get(download)
            if metric is None:
                continue
        campaign = campaign_token(value(row, "campaign")) if level == "detailed" else ""
        if level == "detailed" and not campaign:
            continue
        key = (day, metric, source_label(value(row, "source type")), campaign,
               value(row, "territory").strip()[:64], value(row, "device").strip()[:64])
        rows[key] = rows.get(key, 0) + count
    return rows


# --- Sync -----------------------------------------------------------------------------

class AscSync:
    """Reads new daily report instances into the database (one scheduler run)."""

    def __init__(self, database: Any, client: AscClient, app_id: str, *, clock: Callable[[], float] = time.time,
                 max_instances: int = MAX_INSTANCES_PER_RUN) -> None:
        self.database = database
        self.client = client
        self.app_id = app_id
        self._clock = clock
        self._max_instances = max_instances

    def _reports(self, request_id: str) -> list[tuple[str, str, str]]:
        found = []
        for item in self.client.pages(f"/v1/analyticsReportRequests/{request_id}/reports",
                                      {"filter[category]": "APP_STORE_ENGAGEMENT,COMMERCE", "limit": "200"}):
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            match = report_kind(str(attributes.get("category") or ""), str(attributes.get("name") or ""))
            if match and item.get("id"):
                found.append((str(item["id"]), *match))
        return found

    def _instances(self, report_id: str) -> list[tuple[str, date]]:
        found = []
        for item in self.client.pages(f"/v1/analyticsReports/{report_id}/instances",
                                      {"filter[granularity]": "DAILY", "limit": "200"}):
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            try:
                processing = date.fromisoformat(str(attributes.get("processingDate") or "")[:10])
            except ValueError:
                continue
            if item.get("id") and str(attributes.get("granularity") or "DAILY").upper() == "DAILY":
                found.append((str(item["id"]), processing))
        return found

    def _rows(self, instance_id: str, kind: str, level: str) -> Rows:
        rows: Rows = {}
        for segment in self.client.pages(f"/v1/analyticsReportInstances/{instance_id}/segments", {"limit": "200"}):
            attributes = segment.get("attributes") if isinstance(segment.get("attributes"), dict) else {}
            url = attributes.get("url")
            if not isinstance(url, str):
                raise AscError("report file address missing")
            size = attributes.get("sizeInBytes")
            if isinstance(size, int) and size > MAX_SEGMENT_BYTES:
                raise AscError("report file too large")
            raw = self.client.download(url)
            checksum = attributes.get("checksum")
            if isinstance(checksum, str) and re.fullmatch(r"[0-9a-fA-F]{32}", checksum) \
                    and hashlib.md5(raw, usedforsecurity=False).hexdigest() != checksum.lower():
                raise AscError("report file checksum mismatch")
            for key, count in parse_report(raw, kind, level, self.app_id).items():
                rows[key] = rows.get(key, 0) + count
        return rows

    def run_once(self) -> dict[str, Any]:
        """Process new instances; records the result for Admin. Never raises."""
        attempted = datetime.fromtimestamp(self._clock(), timezone.utc)
        summary: dict[str, Any] = {"instances": 0, "days": 0, "request": None, "error": None}
        state = None
        try:
            requests = report_requests(self.client, self.app_id)
            state = request_state(requests)
            summary["request"] = state
            usable = [item for item in requests if not item["stopped"] or item["accessType"] == "ONE_TIME_SNAPSHOT"]
            done = self.database.app_store_processed_instance_ids()
            todo: list[tuple[date, str, str, str]] = []
            for request in usable:
                for report_id, kind, level in self._reports(request["id"]):
                    todo.extend((processing, instance_id, kind, level)
                                for instance_id, processing in self._instances(report_id) if instance_id not in done)
            # Oldest first, so a newer processing date replaces an older one.
            todo.sort(key=lambda item: (item[0], item[2], item[3], item[1]))
            for processing, instance_id, kind, level in todo[:self._max_instances]:
                rows = self._rows(instance_id, kind, level)
                stored = self.database.store_app_store_instance(
                    instance_id=instance_id, kind=kind, level=level, processing_date=processing, rows=rows)
                if stored is not None:
                    summary["instances"] += 1
                    summary["days"] += stored
            if state == "missing":
                summary["error"] = "no report request"
            elif state == "stopped":
                summary["error"] = "report request stopped"
        except AscError as error:
            summary["error"] = error.reason
            LOGGER.warning("ASC %s", "403" if error.status == 403 else error.reason)
        except Exception as error:  # never let the scheduler stop
            summary["error"] = f"failed ({type(error).__name__})"
            LOGGER.warning("ASC sync failed (%s)", type(error).__name__)
        try:
            self.database.record_app_store_sync(
                attempted_at=attempted, succeeded=summary["error"] is None, error=summary["error"], request_state=state)
        except Exception:
            LOGGER.exception("App Store sync state update failed")
        return summary


def run_schedule(database: Any, stop: threading.Event, settings: AscSettings, *,
                 sync_factory: Callable[[], AscSync] | None = None) -> None:
    """Read new instances at start, then about once an hour."""
    make = sync_factory or (lambda: AscSync(database, AscClient.from_settings(settings), settings.app_id))
    while not stop.is_set():
        summary = make().run_once()
        LOGGER.info("App Store sync instances=%s days=%s request=%s error=%s",
                    summary["instances"], summary["days"], summary["request"], summary["error"])
        stop.wait(SYNC_INTERVAL_SECONDS)


# --- Admin read model -----------------------------------------------------------------

PERIOD_DAYS = {"7d": 7, "30d": 30, "all": None}
PERIODS = tuple(PERIOD_DAYS)
DEFAULT_PERIOD = "30d"


def _empty_totals() -> dict[str, int]:
    return {metric: 0 for metric in METRICS}


def _conversion(downloads: int, views: int) -> float | None:
    return downloads / views if views else None


def admin_snapshot(database: Any, period: str, *, configured: bool) -> dict[str, Any]:
    """App Store numbers for one period, read from the database only.

    The period ends on the last day Apple has reported (one day before the
    newest processed Standard instance of both reports), so Last 7 days are
    seven reported days; the change compares as many days just before them.
    State: ``not_set_up`` (no settings, or no report request), ``ok``,
    ``waiting`` (set up, nothing reported yet) or ``stale`` (Apple failed
    after the last good read; the stored numbers stay)."""
    period = period if period in PERIOD_DAYS else DEFAULT_PERIOD
    base: dict[str, Any] = {"period": period, "configured": configured, "startDate": None, "endDate": None,
                            "previousStartDate": None, "updatedAt": None, "lastAttemptAt": None, "data": None}
    if not configured:
        return {**base, "state": "not_set_up"}
    sync = database.app_store_sync_state() or {}
    base["updatedAt"] = sync.get("last_success_at")
    base["lastAttemptAt"] = sync.get("last_attempt_at")
    failed = bool(sync.get("last_error")) and (sync.get("last_success_at") is None
                                               or sync["last_attempt_at"] > sync["last_success_at"])
    through = database.app_store_reported_through()
    ends = [day for day in (through.get("engagement"), through.get("downloads")) if day is not None]
    if not ends:
        if sync.get("request_state") == "missing":
            return {**base, "state": "not_set_up"}
        return {**base, "state": "unavailable" if failed else "waiting"}
    end = min(ends)
    days = PERIOD_DAYS[period]
    first_day = database.app_store_first_day()
    if days is None:
        start, previous = (first_day or end), None
    else:
        start = end - timedelta(days=days - 1)
        previous = start - timedelta(days=days)
    standard = database.app_store_daily("standard", previous or start, end)
    detailed = database.app_store_daily("detailed", start, end)
    now_totals, before_totals = _empty_totals(), _empty_totals()
    by_day: dict[str, dict[str, int]] = {}
    sources: dict[str, dict[str, int]] = {}
    for row in standard:
        day, metric, count = row["day"], row["metric"], int(row["count"])
        if day < start:
            before_totals[metric] += count
            continue
        now_totals[metric] += count
        by_day.setdefault(day.isoformat(), _empty_totals())[metric] += count
        sources.setdefault(row["source_type"] or "Unavailable", _empty_totals())[metric] += count
    campaigns: dict[str, dict[str, int]] = {}
    for row in detailed:
        if row["campaign"]:
            campaigns.setdefault(row["campaign"], _empty_totals())[row["metric"]] += int(row["count"])
    data = {
        "totals": {**now_totals, "conversion": _conversion(now_totals["first_time_downloads"], now_totals["product_page_views"])},
        "previousTotals": None if previous is None else {
            **before_totals, "conversion": _conversion(before_totals["first_time_downloads"], before_totals["product_page_views"])},
        "days": [{"date": day, **values} for day, values in sorted(by_day.items())],
        "sources": [{"source": name, **values, "conversion": _conversion(values["first_time_downloads"], values["product_page_views"])}
                    for name, values in sources.items()],
        "campaigns": campaign_groups(campaigns),
        "dayCount": (end - start).days + 1,
    }
    return {**base, "state": "stale" if failed else "ok", "startDate": start.isoformat(), "endDate": end.isoformat(),
            "previousStartDate": previous.isoformat() if previous else None, "data": data}


CAMPAIGN_GROUPS = (("fb-", "Facebook"), ("rd-", "Reddit"), ("site-", "Site"))


def campaign_group(token: str) -> str:
    lowered = token.lower()
    return next((name for prefix, name in CAMPAIGN_GROUPS if lowered.startswith(prefix)), "Other")


def campaign_groups(campaigns: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """Facebook (``fb-*``), Reddit (``rd-*``), Site (``site-*``) and Other,
    each with its total; groups and campaigns most first-time downloads
    first. A token without rows is not listed."""
    groups: dict[str, dict[str, Any]] = {}
    for token, values in campaigns.items():
        group = groups.setdefault(campaign_group(token), {"group": campaign_group(token), "campaigns": [],
                                                          "product_page_views": 0, "first_time_downloads": 0})
        group["campaigns"].append({"campaign": token, "product_page_views": values["product_page_views"],
                                   "first_time_downloads": values["first_time_downloads"],
                                   "conversion": _conversion(values["first_time_downloads"], values["product_page_views"])})
        group["product_page_views"] += values["product_page_views"]
        group["first_time_downloads"] += values["first_time_downloads"]
    order = {name: index for index, (_, name) in enumerate(CAMPAIGN_GROUPS + (("", "Other"),))}
    for group in groups.values():
        group["campaigns"].sort(key=lambda item: (-item["first_time_downloads"], -item["product_page_views"], item["campaign"]))
        group["conversion"] = _conversion(group["first_time_downloads"], group["product_page_views"])
    return sorted(groups.values(), key=lambda item: (-item["first_time_downloads"], -item["product_page_views"], order[item["group"]]))


def dashboard_downloads(database: Any, first: date, last: date) -> dict[str, Any]:
    """App Store downloads (first-time downloads plus redownloads, Standard)
    per reported day first..last, the all-time total and the last update."""
    through = database.app_store_reported_through().get("downloads")
    days = {} if through is None else {
        day.isoformat(): count for day, count in database.app_store_download_days(first, min(last, through)).items()}
    sync = database.app_store_sync_state() or {}
    first_day = database.app_store_first_day() if through else None
    return {"reportedThrough": through.isoformat() if through else None,
            "firstDay": first_day.isoformat() if first_day else None, "days": days,
            "total": database.app_store_download_total() if through else None,
            "updatedAt": sync.get("last_success_at")}


# --- Command line ---------------------------------------------------------------------

def _read_admin_key(args: argparse.Namespace) -> Any | None:
    if args.admin_key_stdin:
        raw = sys.stdin.read()
    elif args.admin_key_file:
        with open(args.admin_key_file, encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = os.environ.get("ASC_ADMIN_PRIVATE_KEY", "")
    if not raw.strip():
        return None
    return load_private_key(raw)


def _request_command(args: argparse.Namespace, environ: dict[str, str], transport: Transport) -> int:
    issuer = environ.get("ASC_ISSUER_ID", "").strip().lower()
    app_id = environ.get("ASC_APP_ID", "").strip() or DEFAULT_APP_ID
    if not ISSUER_PATTERN.fullmatch(issuer):
        print("ASC_ISSUER_ID is missing or not an Issuer ID.", file=sys.stderr)
        return 2
    try:
        admin_key = _read_admin_key(args)
    except (OSError, ValueError):
        print("The Admin key could not be read as an App Store Connect .p8 key.", file=sys.stderr)
        return 2
    admin_key_id = (args.admin_key_id or environ.get("ASC_ADMIN_KEY_ID", "")).strip()
    if admin_key is not None:
        if not KEY_ID_PATTERN.fullmatch(admin_key_id):
            print("--admin-key-id is missing or not a Key ID.", file=sys.stderr)
            return 2
        client = AscClient(issuer, admin_key_id, admin_key, transport=transport)
    elif args.apply:
        print("--apply needs the Admin key (--admin-key-stdin, --admin-key-file or ASC_ADMIN_PRIVATE_KEY).", file=sys.stderr)
        return 2
    else:
        settings = AscSettings.from_env(environ)
        if settings is None:
            print("App Store statistics are not set up and no Admin key was given.", file=sys.stderr)
            return 2
        client = AscClient.from_settings(settings, transport=transport)
    try:
        requests = report_requests(client, app_id)
        wanted = ["ONGOING"] + ([] if args.no_history else ["ONE_TIME_SNAPSHOT"])
        for access_type in wanted:
            matching = [item for item in requests if item["accessType"] == access_type]
            exists = any(not item["stopped"] for item in matching) if access_type == "ONGOING" else bool(matching)
            if exists:
                print(f"{access_type} report request: already existed")
            elif not args.apply:
                print(f"{access_type} report request: missing ({'stopped' if matching else 'none'}); run again with --apply")
            else:
                print(f"{access_type} report request: {create_report_request(client, app_id, access_type)}")
    except AscError as error:
        print(f"App Store Connect refused: {error.reason}", file=sys.stderr)
        return 1
    return 0


def _status_command(environ: dict[str, str]) -> int:
    from .config import Settings
    from .db import Database

    settings = AscSettings.from_env(environ)
    print(f"App Store settings: {'set' if settings else 'not set'}")
    database_settings = Settings.from_env()
    database = Database(database_settings.database_url,
                        connect_timeout_seconds=database_settings.database_connect_timeout_seconds)
    sync = database.app_store_sync_state() or {}
    through = database.app_store_reported_through()
    print(f"Report request: {sync.get('request_state') or 'not read yet'}")
    print(f"Last read: {sync.get('last_attempt_at') or 'never'}; last good read: {sync.get('last_success_at') or 'never'}")
    print(f"Last problem: {sync.get('last_error') or 'none'}")
    print("Reported through: " + ", ".join(f"{kind} {day or 'nothing yet'}" for kind, day in (
        ("engagement", through.get("engagement")), ("downloads", through.get("downloads")))))
    return 0 if settings else 1


def _fetch_command(environ: dict[str, str]) -> int:
    from .config import Settings
    from .db import Database

    settings = AscSettings.from_env(environ)
    if settings is None:
        print("App Store statistics are not set up.", file=sys.stderr)
        return 2
    database_settings = Settings.from_env()
    database = Database(database_settings.database_url,
                        connect_timeout_seconds=database_settings.database_connect_timeout_seconds)
    summary = AscSync(database, AscClient.from_settings(settings), settings.app_id).run_once()
    print(f"Instances {summary['instances']}, days {summary['days']}, request {summary['request']}, "
          f"problem {summary['error'] or 'none'}")
    return 0 if summary["error"] is None else 1


def main(argv: list[str] | None = None, *, environ: dict[str, str] | None = None,
         transport: Transport = http_transport) -> int:
    parser = argparse.ArgumentParser(prog="terento-catalog-app-store", description="App Store statistics for Admin.")
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request", help="Show or create the app's ONGOING report request (Admin key, once).")
    request.add_argument("--apply", action="store_true", help="Create what is missing; without it nothing changes.")
    request.add_argument("--admin-key-id", help="Key ID of the Admin key used for this run.")
    source = request.add_mutually_exclusive_group()
    source.add_argument("--admin-key-stdin", action="store_true", help="Read the Admin .p8 key from standard input.")
    source.add_argument("--admin-key-file", help="Read the Admin .p8 key from this file.")
    request.add_argument("--no-history", action="store_true", help="Do not also ask for the one-time history snapshot.")
    commands.add_parser("status", help="Show the stored App Store sync state.")
    commands.add_parser("fetch", help="Read new report instances once.")
    args = parser.parse_args(argv)
    environ = dict(os.environ if environ is None else environ)
    if args.command == "request":
        return _request_command(args, environ, transport)
    if args.command == "status":
        return _status_command(environ)
    return _fetch_command(environ)


if __name__ == "__main__":
    raise SystemExit(main())

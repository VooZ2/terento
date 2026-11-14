"""Read-only Google Search numbers from Search Console for terento.app.

The Admin Web visits page shows them under Google Search
(docs/admin-behavior-contract.md, "Web visits"). They are Google's own
population: clicks and impressions in Google web search, never app, web
installer or Umami statistics, and they are not reconciled with any of them
(contracts/STATISTICS_CONTRACT.md).

The service account key stays on the server: it is read from the environment
(or a file it names), an access token is obtained with google-auth, and both
are sent only to Google, never logged, never followed through a redirect and
never put in a response. Requests run in parallel with a 10 second limit; each
block is cached for one hour per period, and the last good result stays
available when Search Console fails later.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
REQUEST_TIMEOUT_SECONDS = 10
CACHE_SECONDS = 60 * 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_PROPERTY = "sc-domain:terento.app"
SITE_ORIGIN = "https://terento.app"
# Search Console days are Pacific Time days.
PACIFIC = ZoneInfo("America/Los_Angeles")
# Search Console keeps 16 months; "all" asks for all of it.
ALL_DAYS = 486
PERIOD_DAYS = {"7d": 7, "30d": 30, "all": ALL_DAYS}
# Search Console reports whole days only: no request for these periods.
HOURLY_PERIODS = ("today", "24h")
BLOCKS = ("totals", "previousTotals", "dates", "queries", "pages")
QUERY_ROWS = 100
TOP_QUERIES = 10
TOP_PAGES = 5


def console_url(property_name: str) -> str:
    return ("https://search.google.com/search-console/performance/search-analytics?resource_id="
            + quote(property_name, safe=""))


@dataclass(frozen=True)
class GscSettings:
    property_name: str
    service_account: dict[str, Any] = field(repr=False)

    def __repr__(self) -> str:  # never show the key in a traceback or log
        return f"GscSettings(property_name={self.property_name!r})"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "GscSettings | None":
        """The settings, or None (Google Search then shows Unavailable).

        ``GSC_SERVICE_ACCOUNT_JSON`` holds the key JSON itself or the path of
        a file holding it. An invalid set logs which setting is wrong, never
        its value, and does not stop the API.
        """
        environ = os.environ if environ is None else environ
        raw = environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
        property_name = environ.get("GSC_PROPERTY", "").strip() or DEFAULT_PROPERTY
        if not raw:
            return None
        try:
            if not raw.startswith("{"):
                with open(raw, encoding="utf-8") as handle:
                    raw = handle.read()
            info = json.loads(raw)
        except (OSError, ValueError):
            info = None
        problems = []
        if not (isinstance(info, dict) and info.get("type") == "service_account"
                and info.get("client_email") and info.get("private_key")):
            problems.append("GSC_SERVICE_ACCOUNT_JSON")
        if not (property_name.startswith("sc-domain:") or property_name.startswith("https://")):
            problems.append("GSC_PROPERTY")
        if problems:
            LOGGER.warning("Google Search disabled: %s missing or invalid", ", ".join(problems))
            return None
        return cls(property_name=property_name, service_account=info)


class GscRequestError(Exception):
    """A failed Search Console request. ``reason`` is safe to log: no key,
    token, URL or response body."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the access token to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        raise GscRequestError(f"redirect HTTP {code}", code)


_OPENER = urllib.request.build_opener(_NoRedirect)


class GoogleToken:
    """An access token for the service account, from google-auth; refreshed
    under a lock when it is missing or about to expire."""

    def __init__(self, settings: GscSettings) -> None:
        self._settings = settings
        self._credentials: Any = None
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            try:
                if self._credentials is None:
                    from google.oauth2 import service_account

                    self._credentials = service_account.Credentials.from_service_account_info(
                        self._settings.service_account, scopes=[SCOPE])
                if not self._credentials.valid:
                    import urllib3
                    from google.auth.transport.urllib3 import Request

                    http = urllib3.PoolManager(timeout=urllib3.Timeout(total=REQUEST_TIMEOUT_SECONDS), retries=False)
                    self._credentials.refresh(Request(http))
                return str(self._credentials.token)
            except Exception as error:  # noqa: BLE001 - google-auth messages may quote Google's answer
                raise GscRequestError(f"token failed ({type(error).__name__})") from None


def http_query(settings: GscSettings, token: str, body: dict[str, Any]) -> Any:
    """POST one searchAnalytics/query and return its JSON."""
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
           + quote(settings.property_name, safe="") + "/searchAnalytics/query")
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except GscRequestError:
        raise
    except urllib.error.HTTPError as error:
        error.close()  # the body is never read: it may echo the request
        raise GscRequestError(f"HTTP {error.code}", error.code) from None
    except TimeoutError:
        raise GscRequestError("timeout") from None
    except urllib.error.URLError as error:
        reason = "timeout" if isinstance(error.reason, TimeoutError) else f"connection failed ({type(error.reason).__name__})"
        raise GscRequestError(reason) from None
    except OSError as error:
        raise GscRequestError(f"connection failed ({type(error).__name__})") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise GscRequestError("response too large")
    try:
        return json.loads(raw)
    except ValueError:
        raise GscRequestError("not JSON") from None


def pacific_today(now: datetime) -> date:
    return now.astimezone(PACIFIC).date()


def period_dates(period: str, now: datetime) -> tuple[date, date, date | None]:
    """(start, end, previous start) in Pacific days. The period ends today
    (Pacific) so the newest preliminary days show; "all" has no previous."""
    end = pacific_today(now)
    days = PERIOD_DAYS[period]
    start = end - timedelta(days=days - 1)
    return start, end, None if period == "all" else start - timedelta(days=days)


def _metric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and value >= 0 else None


def _rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        raise GscRequestError("unexpected shape")
    rows = raw.get("rows", [])
    if not isinstance(rows, list):
        raise GscRequestError("unexpected shape")
    return [row for row in rows if isinstance(row, dict)]


def _values(row: dict[str, Any]) -> dict[str, float | None]:
    return {key: _metric(row.get(key)) for key in ("clicks", "impressions", "ctr", "position")}


def parse_totals(raw: Any) -> dict[str, float | None]:
    """Sums of the period; no row means nothing was shown (0 clicks, 0
    impressions, no CTR or position)."""
    rows = _rows(raw)
    if not rows:
        return {"clicks": 0.0, "impressions": 0.0, "ctr": None, "position": None}
    return _values(rows[0])


def _key(row: dict[str, Any]) -> str:
    keys = row.get("keys")
    return str(keys[0])[:500] if isinstance(keys, list) and keys else ""


def parse_dates(raw: Any) -> dict[str, Any]:
    days = []
    for row in _rows(raw):
        day = _key(row)
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        values = _values(row)
        days.append({"date": day, "clicks": values["clicks"] or 0, "impressions": values["impressions"] or 0})
    days.sort(key=lambda item: item["date"])
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    # The API answers camelCase; the documented name is snake_case.
    incomplete = str(metadata.get("firstIncompleteDate") or metadata.get("first_incomplete_date") or "")
    try:
        date.fromisoformat(incomplete)
    except ValueError:
        incomplete = None
    return {"days": days, "firstIncompleteDate": incomplete}


def parse_queries(raw: Any) -> dict[str, Any]:
    """The top 10 by clicks, then impressions, from Google's top 100. A query
    is Near top at position 4–10 with at least 20 % of the most-shown query's
    impressions among those 100."""
    rows = [{"query": _key(row), **_values(row)} for row in _rows(raw)]
    rows = [row for row in rows if row["clicks"] is not None and row["impressions"] is not None]
    most = max((row["impressions"] for row in rows), default=0)
    for row in rows:
        position = row["position"]
        row["nearTop"] = bool(position is not None and 4 <= position <= 10 and most and row["impressions"] >= 0.2 * most)
    ranked = sorted(rows, key=lambda row: (-row["clicks"], -row["impressions"], row["query"]))
    return {"rows": ranked[:TOP_QUERIES], "clicks": sum(row["clicks"] for row in rows)}


def page_path(url: str) -> str:
    """https://terento.app/guides/ -> /guides/; another host keeps its name."""
    if url == SITE_ORIGIN:
        return "/"
    if url.startswith(SITE_ORIGIN + "/"):
        return url[len(SITE_ORIGIN):]
    return url.removeprefix("https://")


def parse_pages(raw: Any) -> list[dict[str, Any]]:
    rows = [{"path": page_path(_key(row)), **_values(row)} for row in _rows(raw)]
    return [row for row in rows if row["clicks"] is not None][:TOP_PAGES]


Query = Callable[[GscSettings, str, dict[str, Any]], Any]


class GscStats:
    """Google Search per Admin period, cached per block."""

    def __init__(self, settings: GscSettings, *, query: Query = http_query, token: Callable[[], str] | None = None,
                 clock: Callable[[], float] = time.time, deadline_seconds: float = REQUEST_TIMEOUT_SECONDS + 1) -> None:
        self.settings = settings
        self._query = query
        self._token = token or GoogleToken(settings)
        self._clock = clock
        self._deadline = deadline_seconds
        # (block, period) -> (fetched at, parsed data)
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @property
    def console_url(self) -> str:
        return console_url(self.settings.property_name)

    def _requests(self, period: str, now: datetime) -> dict[str, tuple[dict[str, Any], Callable[[Any], Any]]]:
        start, end, previous = period_dates(period, now)
        window = lambda first, last: {"startDate": first.isoformat(), "endDate": last.isoformat(),
                                      "type": "web", "dataState": "all"}
        current = window(start, end)
        requests = {
            "totals": (current, parse_totals),
            "dates": ({**current, "dimensions": ["date"], "rowLimit": ALL_DAYS + 14}, parse_dates),
            "queries": ({**current, "dimensions": ["query"], "rowLimit": QUERY_ROWS}, parse_queries),
            "pages": ({**current, "dimensions": ["page"], "rowLimit": TOP_PAGES}, parse_pages),
        }
        if previous is not None:
            requests["previousTotals"] = (window(previous, start - timedelta(days=1)), parse_totals)
        return requests

    def snapshot(self, period: str, now: datetime | None = None) -> dict[str, Any]:
        """Every block as {state, fetchedAt, data}: ``ok``, ``stale`` (Search
        Console failed; the last good result) or ``unavailable`` (failed,
        nothing cached). Today and Last 24 hours ask nothing (``daily``
        False): Search Console has whole days only."""
        now = now or datetime.fromtimestamp(self._clock(), timezone.utc)
        if period in HOURLY_PERIODS:
            return {"period": period, "daily": False, "blocks": {}}
        period = period if period in PERIOD_DAYS else "7d"
        start, end, previous = period_dates(period, now)
        requests = self._requests(period, now)
        moment = self._clock()
        blocks: dict[str, dict[str, Any]] = {}
        missing = []
        with self._lock:
            for name in requests:
                cached = self._cache.get((name, period))
                if cached and moment - cached[0] < CACHE_SECONDS:
                    blocks[name] = {"state": "ok", "fetchedAt": cached[0], "data": cached[1]}
                else:
                    missing.append(name)
        if missing:
            try:
                token = self._token()
            except GscRequestError as error:
                for name in missing:
                    blocks[name] = self._failed(name, period, error.reason, error.status)
            else:
                executor = ThreadPoolExecutor(max_workers=len(missing), thread_name_prefix="gsc")
                futures = {name: executor.submit(self._query, self.settings, token, requests[name][0]) for name in missing}
                wait(futures.values(), timeout=self._deadline)
                executor.shutdown(wait=False, cancel_futures=True)
                for name, future in futures.items():
                    blocks[name] = self._result(name, period, future, requests[name][1])
        return {"period": period, "daily": True, "startDate": start.isoformat(), "endDate": end.isoformat(),
                "previousStartDate": previous.isoformat() if previous else None,
                "blocks": {name: blocks[name] for name in BLOCKS if name in blocks}}

    def _result(self, name: str, period: str, future: Any, parse: Callable[[Any], Any]) -> dict[str, Any]:
        try:
            if not future.done():
                raise GscRequestError("timeout")
            data = parse(future.result())
        except GscRequestError as error:
            return self._failed(name, period, error.reason, error.status)
        except Exception as error:  # never let one block break the page
            return self._failed(name, period, f"failed ({type(error).__name__})", None)
        fetched = self._clock()
        with self._lock:
            self._cache[(name, period)] = (fetched, data)
        return {"state": "ok", "fetchedAt": fetched, "data": data}

    def _failed(self, name: str, period: str, reason: str, status: int | None) -> dict[str, Any]:
        if status == 403:
            LOGGER.warning("GSC 403")
        else:
            LOGGER.warning("GSC %s unavailable: %s", name, reason)
        with self._lock:
            cached = self._cache.get((name, period))
        if cached:
            return {"state": "stale", "fetchedAt": cached[0], "data": cached[1]}
        return {"state": "unavailable", "fetchedAt": None, "data": None}

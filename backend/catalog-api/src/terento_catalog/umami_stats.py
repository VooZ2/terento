"""Read-only Website stats from the Umami instance that measures terento.app.

The Admin Website stats page shows these numbers (docs/admin-behavior-contract.md,
"Website stats"). They are Umami's own population: website visitors and page
views, never app or web installer statistics, and they are not reconciled
with Installs or Downloads (contracts/STATISTICS_CONTRACT.md).

The API key stays on the server: it is read from the environment, sent only in
the ``Authorization`` header to the configured Umami origin, never logged,
never followed through a redirect and never put in a response. Requests run in
parallel with a 10 second limit; each block's result is cached for 15 minutes
per (block, period, time zone), and the last good result stays available when
Umami fails later.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit

from .statistics_periods import ADMIN_PERIODS, local_day_start

LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
CACHE_SECONDS = 15 * 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DOWNLOAD_EVENT = "download-click"
USER_AGENT = "Terento-Admin/1.0 (+https://terento.app)"
# The Web installer funnel: (block, Umami event), in step order. Each step is
# the event's distinct visitors (owner request 2026-11-15).
FUNNEL_STEPS = (
    ("funnelCta", "web-installer-cta-click"),
    ("funnelGate", "web-installer-gate"),
    ("funnelConnected", "web-installer-connected"),
    ("funnelDone", "web-installer-done"),
)
# The Key events chart: only these three events, in this order.
KEY_EVENTS = ("download-click", "web-installer-done", "map-compare")
EVENT_LIMIT = 50
# Block order; each is one Umami request (previousErrors and previousEvents
# feed a change, not a card of their own).
BLOCKS = ("visitors", "downloads", "referrers", "entries", "countries", "vitals", "errors", "previousErrors",
          "events", "previousEvents", "eventSeries", *(name for name, _ in FUNNEL_STEPS))
# Umami has measured terento.app since this day; "all" starts here.
TRACKING_START = datetime(2026, 8, 20, tzinfo=timezone.utc)
# Old Maps hash page views inflate Views before this moment (site #686 live).
CLEAN_VIEWS_SINCE = datetime(2026, 11, 13, 7, 45, tzinfo=timezone.utc)
# Health reads Umami at most this often.
HEALTH_SECONDS = 5 * 60
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ROLLING = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


@dataclass(frozen=True)
class UmamiSettings:
    base_url: str
    website_id: str
    api_key: str = ""

    def __repr__(self) -> str:  # never show the key in a traceback or log
        return f"UmamiSettings(base_url={self.base_url!r}, website_id={self.website_id!r})"

    @property
    def dashboard_url(self) -> str:
        return f"{self.base_url}/websites/{self.website_id}"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "UmamiSettings | None":
        """The three settings, or None (Website stats then show Unavailable).

        An incomplete or invalid set does not stop the API; it logs which
        setting is wrong, never its value.
        """
        environ = os.environ if environ is None else environ
        base_url = environ.get("UMAMI_BASE_URL", "").strip().rstrip("/")
        website_id = environ.get("UMAMI_WEBSITE_ID", "").strip().lower()
        api_key = environ.get("UMAMI_API_KEY", "").strip()
        if not (base_url or website_id or api_key):
            return None
        parts = urlsplit(base_url)
        problems = [name for name, bad in (
            ("UMAMI_BASE_URL", parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment
             or parts.username or parts.password),
            ("UMAMI_WEBSITE_ID", not _UUID.match(website_id)),
            ("UMAMI_API_KEY", not api_key or len(api_key) > 1024 or any(c.isspace() for c in api_key)),
        ) if bad]
        if problems:
            LOGGER.warning("Website stats disabled: %s missing or invalid", ", ".join(problems))
            return None
        return cls(base_url=base_url, website_id=website_id, api_key=api_key)


class UmamiRequestError(Exception):
    """A failed Umami request. ``reason`` is safe to log: no URL, query or key."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the Authorization header to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        raise UmamiRequestError(f"redirect HTTP {code}", code)


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_fetch(settings: UmamiSettings, path: str, params: dict[str, Any]) -> Any:
    """GET one Umami API path and return its JSON."""
    url = f"{settings.base_url}{path}?{urlencode(params)}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {settings.api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except UmamiRequestError:
        raise
    except urllib.error.HTTPError as error:
        error.close()
        raise UmamiRequestError(f"HTTP {error.code}", error.code) from None
    except TimeoutError:
        raise UmamiRequestError("timeout") from None
    except urllib.error.URLError as error:
        reason = "timeout" if isinstance(error.reason, TimeoutError) else f"connection failed ({type(error.reason).__name__})"
        raise UmamiRequestError(reason) from None
    except OSError as error:
        raise UmamiRequestError(f"connection failed ({type(error).__name__})") from None
    if len(body) > MAX_RESPONSE_BYTES:
        raise UmamiRequestError("response too large")
    try:
        return json.loads(body)
    except ValueError:
        # A Cloudflare challenge page answers 200/403 with HTML.
        raise UmamiRequestError("not JSON") from None


def period_window(period: str, now: datetime, time_zone: str) -> tuple[int, int]:
    """Umami startAt/endAt in milliseconds for an Admin period ending now."""
    end = now.astimezone(timezone.utc)
    if period == "all":
        start_ms = int(TRACKING_START.timestamp() * 1000)
    elif period == "today":
        start_ms = int(local_day_start(end, time_zone).timestamp() * 1000)
    else:
        start_ms = int((end - _ROLLING[period]).timestamp() * 1000)
    return start_ms, int(end.timestamp() * 1000)


def series_unit(period: str) -> str:
    """Hours for a period of up to two days, else days."""
    return "hour" if period in ("today", "24h") else "day"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, dict):  # Umami 2 shape {"value": n, "prev": n}
        return _number(value.get("value"))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def _totals(raw: Any) -> dict[str, float | None] | None:
    if not isinstance(raw, dict):
        return None
    return {key: _number(raw.get(key)) for key in ("pageviews", "visitors", "visits", "bounces", "totaltime")}


def parse_stats(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise UmamiRequestError("unexpected shape")
    current = _totals(raw)
    previous = _totals(raw.get("comparison"))
    if previous is None and any(isinstance(raw.get(key), dict) for key in ("pageviews", "visitors")):
        previous = {key: _number((raw.get(key) or {}).get("prev")) for key in ("pageviews", "visitors", "visits", "bounces", "totaltime")}
    return {"current": current, "previous": previous}


def parse_event_stats(raw: Any) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict):
        raise UmamiRequestError("unexpected shape")
    pick = lambda item: None if not isinstance(item, dict) else {
        "events": _number(item.get("events")), "visitors": _number(item.get("visitors"))}
    return {"current": pick(data), "previous": pick(data.get("comparison"))}


def parse_metrics(raw: Any, limit: int) -> list[dict[str, Any]]:
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise UmamiRequestError("unexpected shape")
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, count = row.get("x"), _number(row.get("y"))
        if count is None:
            continue
        parsed.append({"name": "" if name is None else str(name)[:300], "visitors": int(count)})
    parsed.sort(key=lambda row: -row["visitors"])
    return parsed[:limit]


# One platform under one name (owner request 2026-11-14): app ids, short
# links, mobile and country hosts.
_REFERRER_ALIASES = {
    "com.reddit.frontpage": "reddit.com", "redd.it": "reddit.com",
    "com.google.android.googlequicksearchbox": "google.com", "com.google.android.gm": "mail.google.com",
    "com.google.android.youtube": "youtube.com", "youtu.be": "youtube.com",
    "com.facebook.katana": "facebook.com", "fb.com": "facebook.com",
    "t.co": "x.com", "twitter.com": "x.com", "com.twitter.android": "x.com",
    "chat.openai.com": "chatgpt.com", "org.telegram.messenger": "t.me", "telegram.org": "t.me",
}
_REFERRER_FAMILIES = (
    (re.compile(r"^(?:[a-z0-9-]+\.)*reddit\.com$"), "reddit.com"),
    (re.compile(r"^(?:[a-z0-9-]+\.)*youtube\.com$"), "youtube.com"),
    (re.compile(r"^(?:[a-z0-9-]+\.)*facebook\.com$"), "facebook.com"),
    (re.compile(r"^(?:[a-z0-9-]+\.)*instagram\.com$"), "instagram.com"),
    (re.compile(r"^(?:[a-z0-9-]+\.)*(?:x|twitter)\.com$"), "x.com"),
    (re.compile(r"^(?:[a-z0-9-]+\.)*bing\.com$"), "bing.com"),
    (re.compile(r"^(?:[a-z0-9-]+\.)*duckduckgo\.com$"), "duckduckgo.com"),
    (re.compile(r"^(?:www\.)?google\.(?:com?\.)?[a-z]{2,3}$"), "google.com"),
)


def referrer_source(name: str) -> str:
    """The platform a referrer domain belongs to (google.lt -> google.com)."""
    host = name.strip().lower().rstrip(".")
    host = _REFERRER_ALIASES.get(host, host)
    for pattern, source in _REFERRER_FAMILIES:
        if pattern.match(host):
            return source
    for prefix in ("www.", "m."):
        if host.startswith(prefix) and host.count(".") > 1:
            host = host[len(prefix):]
    return _REFERRER_ALIASES.get(host, host)


def parse_referrers(raw: Any, limit: int = 10) -> dict[str, Any]:
    """Every referrer merged per platform: the top ``limit`` and the visitor
    sum of all of them (Umami counts distinct visitors per referrer)."""
    merged: dict[str, int] = {}
    for row in parse_metrics(raw, 10_000):
        if not row["name"]:
            continue
        source = referrer_source(row["name"])
        merged[source] = merged.get(source, 0) + row["visitors"]
    rows = sorted(({"name": name, "visitors": count} for name, count in merged.items()),
                  key=lambda row: (-row["visitors"], row["name"]))
    return {"rows": rows[:limit], "total": sum(merged.values())}


def parse_countries(raw: Any) -> list[dict[str, Any]]:
    """Every country as an ISO 3166-1 alpha-2 code, most visitors first;
    anything else is ``""`` (Unknown)."""
    rows = parse_metrics(raw, 10_000)
    for row in rows:
        code = row["name"].strip().upper()
        row["name"] = code if re.fullmatch(r"[A-Z]{2}", code) and code not in {"XX", "ZZ"} else ""
    return rows


def parse_events(raw: Any) -> list[dict[str, Any]]:
    """Custom events by name with their counts (every event, not visitors)."""
    return [{"name": row["name"], "count": row["visitors"]} for row in parse_metrics(raw, EVENT_LIMIT) if row["name"]]


_BUCKET = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}))?")


def parse_event_series(raw: Any, unit: str) -> dict[str, Any]:
    """Counts of the Key events per local day (``2026-11-15``) or hour
    (``2026-11-15 14``); Umami has no row for a bucket without events."""
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise UmamiRequestError("unexpected shape")
    series: dict[str, dict[str, int]] = {name: {} for name in KEY_EVENTS}
    for row in rows:
        if not isinstance(row, dict) or row.get("x") not in series:
            continue
        found, count = _BUCKET.match(str(row.get("t") or "")), _number(row.get("y"))
        if not found or count is None or (unit == "hour" and not found.group(2)):
            continue
        key = found.group(1) + (f" {found.group(2)}" if unit == "hour" else "")
        series[row["x"]][key] = series[row["x"]].get(key, 0) + int(count)
    return {"unit": unit, "series": series}


def parse_performance(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise UmamiRequestError("unexpected shape")
    p75 = lambda key: _number((raw.get(key) or {}).get("p75")) if isinstance(raw.get(key), dict) else None
    count = _number(raw.get("count"))
    return {**{key: p75(key) for key in ("lcp", "inp", "cls", "fcp", "ttfb")},
            "count": int(count) if count is not None else None}


def parse_errors(raw: Any) -> dict[str, Any]:
    """Issues seen in the period, ignored issues left out; the 3 most frequent."""
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
        raise UmamiRequestError("unexpected shape")
    issues = []
    for item in raw["data"]:
        if not isinstance(item, dict) or item.get("status") == "ignored":
            continue
        count = _number(item.get("occurrences"))
        if count is None:
            continue
        issues.append({"message": str(item.get("title") or item.get("name") or "")[:300], "count": int(count)})
    issues.sort(key=lambda issue: -issue["count"])
    return {"total": sum(issue["count"] for issue in issues), "issues": len(issues), "top": issues[:3]}


Fetch = Callable[[UmamiSettings, str, dict[str, Any]], Any]


class UmamiStats:
    """Website stats per Admin period, cached per block."""

    def __init__(self, settings: UmamiSettings, *, fetch: Fetch = http_fetch,
                 clock: Callable[[], float] = time.time, deadline_seconds: float = REQUEST_TIMEOUT_SECONDS + 1) -> None:
        self.settings = settings
        self._fetch = fetch
        self._clock = clock
        self._deadline = deadline_seconds
        # (block, period, time zone) -> (fetched at, parsed data)
        self._cache: dict[tuple[str, str, str], tuple[float, Any]] = {}
        self._lock = threading.Lock()
        # Health: the latest read of Umami, from a probe or a page block.
        self._last_success: float | None = None
        self._last_failure: tuple[float, str, int | None] | None = None
        self._last_probe: float | None = None

    def _requests(self, start: int, end: int, period: str = "7d",
                  time_zone: str = "UTC") -> dict[str, tuple[str, dict[str, Any], Callable[[Any], Any]]]:
        base = f"/api/websites/{self.settings.website_id}"
        window = {"startAt": start, "endAt": end}
        previous = {"startAt": start - (end - start), "endAt": start}
        unit = series_unit(period)
        return {
            "visitors": (f"{base}/stats", window, parse_stats),
            "downloads": (f"{base}/events/stats", {**window, "event": DOWNLOAD_EVENT}, parse_event_stats),
            # All referrers (Umami's own limit), so platforms merge and
            # Direct / none is visitors minus every referred visitor.
            "referrers": (f"{base}/metrics", {**window, "type": "referrer", "limit": 500}, parse_referrers),
            "entries": (f"{base}/metrics", {**window, "type": "entry", "limit": 5}, lambda raw: parse_metrics(raw, 5)),
            # Every country (Umami's own limit) for the map; the table shows 10.
            "countries": (f"{base}/metrics", {**window, "type": "country", "limit": 500}, parse_countries),
            "vitals": (f"{base}/performance/stats", window, parse_performance),
            "errors": (f"{base}/errors", {**window, "pageSize": 100}, parse_errors),
            # Umami has no error comparison: the same length just before.
            "previousErrors": (f"{base}/errors", {**previous, "pageSize": 100}, parse_errors),
            "events": (f"{base}/metrics", {**window, "type": "event", "limit": EVENT_LIMIT}, parse_events),
            "previousEvents": (f"{base}/metrics", {**previous, "type": "event", "limit": EVENT_LIMIT}, parse_events),
            "eventSeries": (f"{base}/events/series", {**window, "unit": unit, "timezone": time_zone},
                            lambda raw: parse_event_series(raw, unit)),
            **{name: (f"{base}/events/stats", {**window, "event": event}, parse_event_stats)
               for name, event in FUNNEL_STEPS},
        }

    def snapshot(self, period: str, time_zone: str, now: datetime | None = None) -> dict[str, Any]:
        """Every block as {state, fetchedAt, data}: ``ok``, ``stale`` (Umami
        failed; the last good result), ``unavailable`` (failed, nothing
        cached) or ``hidden`` (Umami answered 400 or 404)."""
        period = period if period in ADMIN_PERIODS else "7d"
        now = now or datetime.fromtimestamp(self._clock(), timezone.utc)
        start, end = period_window(period, now, time_zone)
        requests = self._requests(start, end, period, time_zone)
        moment = self._clock()
        blocks: dict[str, dict[str, Any]] = {}
        missing = []
        with self._lock:
            for name in BLOCKS:
                cached = self._cache.get((name, period, time_zone))
                if cached and moment - cached[0] < CACHE_SECONDS:
                    blocks[name] = {"state": "ok", "fetchedAt": cached[0], "data": cached[1]}
                else:
                    missing.append(name)
        if missing:
            executor = ThreadPoolExecutor(max_workers=len(missing), thread_name_prefix="umami")
            futures = {name: executor.submit(self._fetch, self.settings, requests[name][0], requests[name][1]) for name in missing}
            wait(futures.values(), timeout=self._deadline)
            executor.shutdown(wait=False, cancel_futures=True)
            for name, future in futures.items():
                blocks[name] = self._result(name, period, time_zone, future, requests[name][2])
        return {"period": period, "timeZone": time_zone, "startAt": start, "endAt": end,
                # Umami's comparison: the same length just before startAt.
                "previousStartAt": start - (end - start),
                "blocks": {name: blocks[name] for name in BLOCKS}}

    def _result(self, name: str, period: str, time_zone: str, future: Any, parse: Callable[[Any], Any]) -> dict[str, Any]:
        try:
            if not future.done():
                raise UmamiRequestError("timeout")
            data = parse(future.result())
        except UmamiRequestError as error:
            if error.status in (400, 404):
                LOGGER.info("Website stats %s hidden: Umami HTTP %s", name, error.status)
                return {"state": "hidden", "fetchedAt": None, "data": None}
            reason, status = error.reason, error.status
        except Exception as error:  # never let one block break the page
            reason, status = f"failed ({type(error).__name__})", None
        else:
            fetched = self._clock()
            with self._lock:
                self._cache[(name, period, time_zone)] = (fetched, data)
                self._last_success = fetched
            return {"state": "ok", "fetchedAt": fetched, "data": data}
        LOGGER.warning("Website stats %s unavailable: %s", name, reason)
        with self._lock:
            self._last_failure = (self._clock(), reason, status)
            cached = self._cache.get((name, period, time_zone))
        if cached:
            return {"state": "stale", "fetchedAt": cached[0], "data": cached[1]}
        return {"state": "unavailable", "fetchedAt": None, "data": None}

    def health(self, *, probe: bool = True) -> dict[str, Any]:
        """Umami connection state for Admin Health: HEALTHY when the latest read
        answered, FAILED when it did not. With ``probe`` (Health and the
        attention read) one small stats read runs when the latest is older
        than five minutes; without it (the Dashboard) only earlier reads count.
        """
        now = self._clock()
        with self._lock:
            due = self._last_probe is None or now - self._last_probe >= HEALTH_SECONDS
            if probe and due:
                self._last_probe = now
        if probe and due:
            end = int(now * 1000)
            try:
                parse_stats(self._fetch(self.settings, f"/api/websites/{self.settings.website_id}/stats",
                                        {"startAt": end - 3_600_000, "endAt": end}))
            except Exception as error:  # noqa: BLE001 - every failure is a Health state
                reason = error.reason if isinstance(error, UmamiRequestError) else f"failed ({type(error).__name__})"
                LOGGER.warning("Website stats health check failed: %s", reason)
                with self._lock:
                    self._last_failure = (self._clock(), reason, getattr(error, "status", None))
            else:
                with self._lock:
                    self._last_success = self._clock()
        with self._lock:
            success, failure = self._last_success, self._last_failure
        if failure and (success is None or failure[0] > success):
            return {"status": "FAILED", "reason": failure[1], "httpStatus": failure[2],
                    "checkedAt": failure[0], "lastSuccessAt": success}
        if success is not None:
            return {"status": "HEALTHY", "reason": "", "httpStatus": None,
                    "checkedAt": success, "lastSuccessAt": success}
        return {"status": "UNKNOWN", "reason": "", "httpStatus": None, "checkedAt": None, "lastSuccessAt": None}

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
# Block order on the page; each is one Umami request.
BLOCKS = ("visitors", "downloads", "referrers", "entries", "vitals", "errors")
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
        start_ms = 0
    elif period == "today":
        start_ms = int(local_day_start(end, time_zone).timestamp() * 1000)
    else:
        start_ms = int((end - _ROLLING[period]).timestamp() * 1000)
    return start_ms, int(end.timestamp() * 1000)


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


def parse_performance(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise UmamiRequestError("unexpected shape")
    p75 = lambda key: _number((raw.get(key) or {}).get("p75")) if isinstance(raw.get(key), dict) else None
    count = _number(raw.get("count"))
    return {"lcp": p75("lcp"), "inp": p75("inp"), "cls": p75("cls"), "count": int(count) if count is not None else None}


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

    def _requests(self, start: int, end: int) -> dict[str, tuple[str, dict[str, Any], Callable[[Any], Any]]]:
        base = f"/api/websites/{self.settings.website_id}"
        window = {"startAt": start, "endAt": end}
        return {
            "visitors": (f"{base}/stats", window, parse_stats),
            "downloads": (f"{base}/events/stats", {**window, "event": DOWNLOAD_EVENT}, parse_event_stats),
            "referrers": (f"{base}/metrics", {**window, "type": "referrer", "limit": 10}, lambda raw: parse_metrics(raw, 10)),
            "entries": (f"{base}/metrics", {**window, "type": "entry", "limit": 5}, lambda raw: parse_metrics(raw, 5)),
            "vitals": (f"{base}/performance/stats", window, parse_performance),
            "errors": (f"{base}/errors", {**window, "pageSize": 100}, parse_errors),
        }

    def snapshot(self, period: str, time_zone: str, now: datetime | None = None) -> dict[str, Any]:
        """Every block as {state, fetchedAt, data}: ``ok``, ``stale`` (Umami
        failed; the last good result), ``unavailable`` (failed, nothing
        cached) or ``hidden`` (Umami answered 400 or 404)."""
        period = period if period in ADMIN_PERIODS else "7d"
        now = now or datetime.fromtimestamp(self._clock(), timezone.utc)
        start, end = period_window(period, now, time_zone)
        requests = self._requests(start, end)
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
            reason = error.reason
        except Exception as error:  # never let one block break the page
            reason = f"failed ({type(error).__name__})"
        else:
            fetched = self._clock()
            with self._lock:
                self._cache[(name, period, time_zone)] = (fetched, data)
            return {"state": "ok", "fetchedAt": fetched, "data": data}
        LOGGER.warning("Website stats %s unavailable: %s", name, reason)
        with self._lock:
            cached = self._cache.get((name, period, time_zone))
        if cached:
            return {"state": "stale", "fetchedAt": cached[0], "data": cached[1]}
        return {"state": "unavailable", "fetchedAt": None, "data": None}

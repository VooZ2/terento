"""Umami 3.5 API answers in the shapes its source returns (src/app/api/websites/[websiteId]/...)."""

from __future__ import annotations

from typing import Any

WEBSITE_ID = "d8097a98-ffe4-478e-b212-9f06b5bcccbe"
SECRET_KEY = "umami-test-key-7f3c1e0b9a4d4f1aa2c3"

STATS = {
    "pageviews": 410, "visitors": 120, "visits": 150, "bounces": 60, "totaltime": 13500,
    "comparison": {"pageviews": 380, "visitors": 100, "visits": 140, "bounces": 70, "totaltime": 11200},
}
EVENT_STATS = {"data": {"events": 30, "visitors": 18, "visits": 20, "uniqueEvents": 1,
                        "comparison": {"events": 25, "visitors": 20, "visits": 21, "uniqueEvents": 1}}}
REFERRERS = [{"x": "google.com", "y": 40}, {"x": "reddit.com", "y": 12}, {"x": "github.com", "y": 9}]
ENTRIES = [{"x": "/", "y": 80}, {"x": "/download/", "y": 22}, {"x": "/install/", "y": 11}]
PERFORMANCE = {
    "lcp": {"p50": 1500, "p75": 2300, "p95": 5100},
    "inp": {"p50": 90, "p75": 260, "p95": 700},
    "cls": {"p50": 0.01, "p75": 0.31, "p95": 0.6},
    "fcp": {"p50": 900, "p75": 1200, "p95": 2600},
    "ttfb": {"p50": 120, "p75": 210, "p95": 600},
    "count": 64,
}
ERRORS = {
    "data": [
        {"id": "a1", "title": "TypeError: <img src=x onerror=alert(1)>", "status": "unresolved", "occurrences": 4, "visits": 3},
        {"id": "a2", "title": "Error: test from DevTools", "status": "ignored", "occurrences": 9, "visits": 1},
        {"id": "a3", "title": "ReferenceError: map is not defined", "status": "unresolved", "occurrences": 7, "visits": 5},
        {"id": "a4", "title": "NetworkError when attempting to fetch resource.", "status": "resolved", "occurrences": 2, "visits": 2},
        {"id": "a5", "title": "Script error.", "status": "unresolved", "occurrences": 1, "visits": 1},
    ],
    "count": 5, "page": 1, "pageSize": 100,
}


def answer(path: str, params: dict[str, Any]) -> Any:
    """The fixture answer for one request path and query."""
    if path.endswith("/stats") and "/events/" not in path and "/performance/" not in path:
        return STATS
    if path.endswith("/events/stats"):
        return EVENT_STATS
    if path.endswith("/metrics"):
        return REFERRERS if params["type"] == "referrer" else ENTRIES
    if path.endswith("/performance/stats"):
        return PERFORMANCE
    if path.endswith("/errors"):
        return ERRORS
    raise AssertionError(path)

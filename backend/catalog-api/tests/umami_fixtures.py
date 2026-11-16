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
REFERRERS = [{"x": "google.com", "y": 34}, {"x": "reddit.com", "y": 10}, {"x": "github.com", "y": 9},
             {"x": "www.google.lt", "y": 6}, {"x": "com.reddit.frontpage", "y": 2}, {"x": "m.youtube.com", "y": 3},
             {"x": "youtu.be", "y": 1}, {"x": "forums.garmin.com", "y": 5}, {"x": "example.org", "y": 2}]
COUNTRIES = [{"x": "LT", "y": 50}, {"x": "DE", "y": 30}, {"x": "US", "y": 20}, {"x": None, "y": 3}]
ENTRIES = [{"x": "/", "y": 80}, {"x": "/download/", "y": 22}, {"x": "/install/", "y": 11}]
PERFORMANCE = {
    "lcp": {"p50": 1500, "p75": 2300, "p95": 5100},
    "inp": {"p50": 90, "p75": 260, "p95": 700},
    "cls": {"p50": 0.01, "p75": 0.31, "p95": 0.6},
    "fcp": {"p50": 900, "p75": 1200, "p95": 2600},
    "ttfb": {"p50": 120, "p75": 210, "p95": 600},
    "count": 64,
}
# Custom events (metrics type=event: event counts, most first).
EVENTS = [
    {"x": "language-switch-click", "y": 90}, {"x": "guide-link-click", "y": 61}, {"x": "map-style-switch", "y": 219},
    {"x": "download-cta-click", "y": 41}, {"x": "download-click", "y": 30}, {"x": "web-installer-cta-click", "y": 25},
    {"x": "web-installer-link-click", "y": 12}, {"x": "web-installer-gate", "y": 9}, {"x": "web-installer-connected", "y": 2},
    {"x": "web-installer-done", "y": 4}, {"x": "installer-result", "y": 4}, {"x": "install-link-copy", "y": 1},
    {"x": "map-compare", "y": 33}, {"x": "maps-link-click", "y": 20}, {"x": "faq-link-click", "y": 5},
    {"x": "newsletter-link-click", "y": 3}, {"x": "app-store-click", "y": 2}, {"x": "brand-new-event", "y": 7},
    {"x": "<b>odd</b>", "y": 1},
]
# events/series: one row per event and local bucket that had events.
EVENT_SERIES = [
    {"x": "download-click", "t": "2026-11-12 00:00:00", "y": 10}, {"x": "download-click", "t": "2026-11-14 00:00:00", "y": 20},
    {"x": "web-installer-done", "t": "2026-11-13 00:00:00", "y": 4}, {"x": "map-compare", "t": "2026-11-12T00:00:00Z", "y": 33},
    {"x": "guide-link-click", "t": "2026-11-12 00:00:00", "y": 61},
]
# events/stats per event: the funnel's visitors; connected below done shows a tracking gap.
FUNNEL_VISITORS = {"web-installer-cta-click": 20, "web-installer-gate": 8, "web-installer-connected": 2, "web-installer-done": 3}
# The Map styles page (path filter "c./map-styles/"): its visitors, top
# countries and map-compare change and area values (event-data/values).
MAP_PAGE_STATS = {"pageviews": 70, "visitors": 40, "visits": 45, "bounces": 10, "totaltime": 3000,
                  "comparison": {"pageviews": 0, "visitors": 0, "visits": 0, "bounces": 0, "totaltime": 0}}
MAP_COMPARE_VISITORS = 9
MAP_COUNTRIES = [{"x": "FR", "y": 12}, {"x": "US", "y": 8}]
MAP_CHANGES = [{"value": "style", "total": 12}, {"value": "area", "total": 12}, {"value": "swap", "total": 3},
               {"value": "<i>new</i>", "total": 1}]
MAP_AREAS = [{"value": "cinque-terre", "total": 20}, {"value": "zermatt", "total": 9}, {"value": "gone-area", "total": 4}]
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
        return MAP_PAGE_STATS if params.get("path") else STATS
    if path.endswith("/event-data/values"):
        return {"change": MAP_CHANGES, "area": MAP_AREAS}[params["propertyName"]]
    if path.endswith("/events/stats"):
        if params.get("event") == "map-compare":
            return {"data": {"events": 33, "visitors": MAP_COMPARE_VISITORS, "visits": 10}}
        if params.get("event") in FUNNEL_VISITORS:
            visitors = FUNNEL_VISITORS[params["event"]]
            return {"data": {"events": visitors * 2, "visitors": visitors, "visits": visitors,
                             "comparison": {"events": 0, "visitors": 0, "visits": 0}}}
        return EVENT_STATS
    if path.endswith("/events/series"):
        return EVENT_SERIES
    if path.endswith("/metrics"):
        if params.get("path"):
            return {"country": MAP_COUNTRIES}[params["type"]]
        return {"referrer": REFERRERS, "entry": ENTRIES, "country": COUNTRIES, "event": EVENTS}[params["type"]]
    if path.endswith("/performance/stats"):
        return PERFORMANCE
    if path.endswith("/errors"):
        return ERRORS
    raise AssertionError(path)

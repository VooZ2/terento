"""Admin Web visits page (docs/admin-behavior-contract.md, "Web visits").

Umami's terento.app numbers: a separate population from app and web installer
statistics. The page renders at once with every block loading; its script then
reads ``/admin/api/umami`` for the Admin period, which answers with the blocks
rendered here, so the Umami key never reaches the browser. The Google Search
block loads the same way from ``/admin/api/gsc`` (Search Console, gsc_stats).
"""

from __future__ import annotations

import hashlib
import html
import json
import math
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .admin import (
    _ADMIN_NONCE_PLACEHOLDER,
    _admin_header,
    _admin_icon,
    _chart_axis_labels,
    _chart_legend,
    _chart_value_attributes,
    _chart_value_strip,
    _empty_state,
    _nice_tick_step,
    _layout,
    _metric_row,
    _metric_tile,
    _overview_period_script,
    _section_card,
    _status_pill,
    _timestamp_markup,
)
from .admin_referrer_icons import FONT_AWESOME_BRANDS, SIMPLE_ICONS
from .admin_web_installer import _duration
from .gsc_stats import DEFAULT_PERIOD as GSC_DEFAULT_PERIOD, PERIODS as GSC_PERIODS
from .statistics_periods import ADMIN_PERIOD_LABELS, ADMIN_PERIODS
from .admin_visits_map import VISITS_MAP_SVG
from .map_preview.areas import load_areas
from .umami_stats import CLEAN_VIEWS_SINCE, FUNNEL_STEPS, KEY_EVENTS, MAP_STYLES_LIMIT

TITLES = {
    "visitors": "Visitors", "downloads": "Downloads", "referrers": "Referrers",
    "entries": "Entry pages", "countries": "Countries", "vitals": "Web Vitals", "errors": "Errors",
    "events": "Events", "eventSeries": "Key events over time", "funnel": "Web installer funnel",
    "mapPage": "Map styles page", "mapCountries": "Map styles countries", "mapChanges": "Map changes",
    "mapAreas": "Map places",
}
# map-compare change values (site/map-styles/map-styles.js), in this order
# when counts tie; any other value shows under its own name.
MAP_CHANGES = (("area", "Place"), ("style", "Style"), ("compare", "Compared style"), ("swap", "Swap"), ("mode", "View"))
PREVIOUS = {"today": "previous period", "24h": "previous 24 h", "7d": "previous 7 days", "30d": "previous 30 days"}
VITALS_MIN_SAMPLES = 20
# Google's p75 limits (good, needs improvement); above the second is Poor.
VITALS = (
    ("lcp", "LCP · p75", (2500, 4000)),
    ("inp", "INP · p75", (200, 500)),
    ("cls", "CLS · p75", (0.1, 0.25)),
    ("fcp", "FCP · p75", (1800, 3000)),
    ("ttfb", "TTFB · p75", (800, 1800)),
)
UNAVAILABLE = "Statistics unavailable."

# Referrer platform -> logo; FA = Font Awesome brands, SI = Simple Icons.
_SOURCE_ICONS = {
    "google.com": ("FA", "google"), "reddit.com": ("FA", "reddit"), "youtube.com": ("FA", "youtube"),
    "github.com": ("FA", "github"), "x.com": ("FA", "x-twitter"), "facebook.com": ("FA", "facebook"),
    "news.ycombinator.com": ("FA", "hacker-news"), "linkedin.com": ("FA", "linkedin"),
    "mastodon.social": ("FA", "mastodon"), "bsky.app": ("FA", "bluesky"), "t.me": ("FA", "telegram"),
    "discord.com": ("FA", "discord"), "strava.com": ("FA", "strava"), "instagram.com": ("FA", "instagram"),
    "pinterest.com": ("FA", "pinterest"), "threads.net": ("FA", "threads"), "threads.com": ("FA", "threads"),
    "chatgpt.com": ("FA", "openai"), "search.brave.com": ("FA", "brave"), "yandex.ru": ("FA", "yandex"),
    "yandex.com": ("FA", "yandex"), "slack.com": ("FA", "slack"), "medium.com": ("FA", "medium"),
    "stackoverflow.com": ("FA", "stack-overflow"), "tiktok.com": ("FA", "tiktok"), "whatsapp.com": ("FA", "whatsapp"),
    "duckduckgo.com": ("SI", "duckduckgo"), "perplexity.ai": ("SI", "perplexity"),
}
# Hosts ending in one of these share its logo (forums.garmin.com, en.wikipedia.org).
_SOURCE_SUFFIX_ICONS = (
    (".wikipedia.org", ("FA", "wikipedia-w")),
    (".linkedin.com", ("FA", "linkedin")), (".medium.com", ("FA", "medium")),
)
_SOURCE_PREFIX_ICONS = (("lemmy.", ("SI", "lemmy")), ("mastodon.", ("FA", "mastodon")))


def _card_id(name: str) -> str:
    return f"web-visits-{name}"


def _ratio(part: float | None, whole: float | None) -> float | None:
    return None if part is None or not whole else part / whole


def _rate(part: float | None, whole: float | None) -> float | None:
    ratio = _ratio(part, whole)
    return None if ratio is None else round(ratio * 100, 1)


def _delta(current: float | None, previous: float | None, period: str, kind: str = "count", *,
           better: str = "up", plain: bool = False, against: str | None = None) -> str:
    """Change against the previous period of the same length: arrow, sign and
    text, coloured by meaning (green better, red worse, grey same or without a
    base). Rates change in percentage points."""
    if period not in PREVIOUS or current is None or previous is None:
        return ""
    against = against or PREVIOUS[period]
    change = current - previous
    if kind == "rate":
        change = round(change, 1)
        amount = f"{abs(change):.1f}".removesuffix(".0") + " pp"
    elif kind == "duration":
        change = round(change)
        amount = _duration(abs(change))
    elif kind == "decimal":
        change = round(change, 1)
        amount = f"{abs(change):.1f}"
    else:
        change = round(change)
        amount = f"{abs(change):,}"
    if change == 0:
        arrow, text, trend = "=", f"Same as {against}", "same"
    else:
        arrow, sign = ("▲", "+") if change > 0 else ("▼", "−")
        text = f"{sign}{amount} vs {against}"
        trend = "neutral" if plain or not previous else (
            "better" if (change > 0) == (better == "up") else "worse")
    return (f"<span class='funnel-delta' data-trend='{trend}'><span aria-hidden='true'>{arrow}</span> "
            f"{html.escape(text)}</span>")


def _stale(block: dict[str, Any]) -> str:
    """Header marks of a block that shows its last good result."""
    if block.get("state") != "stale":
        return ""
    fetched = datetime.fromtimestamp(block["fetchedAt"], timezone.utc)
    return (_status_pill("unknown", "Statistics unavailable")
            + f"<span class='admin-metric-secondary'>Last result {_timestamp_markup(fetched)}</span>")


def _headline(name: str, body: str, extra_attributes: str = "") -> str:
    """An untitled KPI panel, like the Dashboard and Web installer headline;
    its first tile already names it."""
    return (f"<section class='admin-card {_HEAD}' id='{_card_id(name)}' aria-label='{TITLES[name]}'"
            f"{extra_attributes}>{body}</section>")


def _card(name: str, block: dict[str, Any], body: Any, css: str = "") -> str:
    if block.get("state") == "hidden":
        return ""
    if block.get("state") not in ("ok", "stale") or block.get("data") is None:
        return _section_card(TITLES[name], _empty_state("unavailable", UNAVAILABLE), card_id=_card_id(name), css=css)
    if css == _HEAD and block.get("state") == "ok":
        return _headline(name, body(block["data"]))
    return _section_card(TITLES[name], body(block["data"]), card_id=_card_id(name), css=css, totals=_stale(block))


def _usable(block: dict[str, Any] | None) -> Any:
    return (block or {}).get("data") if (block or {}).get("state") in ("ok", "stale") else None


def _ranking(caption: str, label: str, rows: list[tuple[str, int, str]], empty: str, *,
             count_label: str = "Visitors") -> str:
    """A ranking table; each row is (cell markup, visitors or events, row class)."""
    if not rows:
        return _empty_state("empty", empty)
    body = "".join(
        f"<tr{f' class={chr(39)}{css}{chr(39)}' if css else ''}><td>{cell}</td>"
        f"<td class='column-number'>{count:,}</td></tr>"
        for cell, count, css in rows)
    return (
        "<div class='table-wrap'><table class='admin-table popular-maps-table' data-own-mobile-layout>"
        f"<caption class='sr-only'>{html.escape(caption)}</caption><thead><tr><th scope='col'>{html.escape(label)}</th>"
        f"<th scope='col' class='column-number'>{html.escape(count_label)}</th></tr></thead><tbody>{body}</tbody></table></div>"
    )


def _source_icon(source: str) -> str:
    found = _SOURCE_ICONS.get(source)
    if found is None:
        found = next((icon for suffix, icon in _SOURCE_SUFFIX_ICONS if source.endswith(suffix) or source == suffix[1:]), None)
    if found is None:
        found = next((icon for prefix, icon in _SOURCE_PREFIX_ICONS if source.startswith(prefix)), None)
    if found is None:
        return _admin_icon("source-web")
    view_box, path = (FONT_AWESOME_BRANDS if found[0] == "FA" else SIMPLE_ICONS)[found[1]]
    return (f"<svg class='admin-icon' viewBox='{view_box}' aria-hidden='true' focusable='false'>"
            f"<path fill='currentColor' d='{path}'/></svg>")


def _referrers(data: dict[str, Any], visitors: dict[str, Any] | None) -> str:
    rows = [(f"<span class='web-visits-source'>{_source_icon(row['name'])}<span>{html.escape(row['name'])}</span></span>",
             row["visitors"], "") for row in data.get("rows") or []]
    total_visitors = ((visitors or {}).get("current") or {}).get("visitors")
    if total_visitors is not None:
        direct = int(total_visitors) - int(data.get("total") or 0)
        if direct > 0:
            rows.append((f"<span class='web-visits-source'>{_admin_icon('arrow-right')}<span>Direct / none</span></span>",
                         direct, "web-visits-direct"))
    return _ranking("Top referrers", "Source", rows, "No referrers in this period.")


def _entries(rows: list[dict[str, Any]]) -> str:
    return _ranking("Top entry pages", "Page", [(html.escape(row["name"] or "—"), row["visitors"], "") for row in rows],
                    "No visits in this period.")


def _flag(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)


def _country_cells(rows: list[dict[str, Any]]) -> list[tuple[str, int, str]]:
    """The top 10 countries with flag and code (the browser names each code
    in English); no code is Unknown."""
    cells = []
    for row in rows[:10]:
        code = row["name"]
        cell = (f"<span class='web-visits-source' data-country='{code.lower()}'><span class='web-visits-flag' aria-hidden='true'>"
                f"{_flag(code)}</span><span data-region-name='{code}'>{code}</span></span>") if code else "Unknown"
        cells.append((cell, row["visitors"], ""))
    return cells


def _countries(rows: list[dict[str, Any]]) -> str:
    """The top 10 countries by visitors beside the map of every country."""
    table = _ranking("Top countries", "Country", _country_cells(rows), "No visits in this period.")
    world = _visits_map(rows)
    if not world:
        return table
    return f"<div class='web-visits-countries'>{world}<div class='web-visits-countries-list'>{table}</div></div>"


def _visitors(data: dict[str, Any], period: str, views_mixed: bool) -> str:
    now, before = data.get("current") or {}, data.get("previous") or {}
    bounce = lambda totals: _rate(totals.get("bounces"), totals.get("visits"))
    duration = lambda totals: None if _ratio(totals.get("totaltime"), totals.get("visits")) is None else round(
        totals["totaltime"] / totals["visits"])
    tiles = [
        _metric_tile("Visitors", now.get("visitors"), secondary=_delta(now.get("visitors"), before.get("visitors"), period)),
        _metric_tile("Visits", now.get("visits"), secondary=_delta(now.get("visits"), before.get("visits"), period)),
        _metric_tile("Views", now.get("pageviews"), secondary=_delta(
            now.get("pageviews"), before.get("pageviews"), period, plain=views_mixed)),
        _metric_tile("Bounce rate", bounce(now), fmt="rate",
                     secondary=_delta(bounce(now), bounce(before), period, "rate", better="down")),
    ]
    seconds = duration(now)
    tiles.append(_metric_tile("Visit duration", seconds, value_html=_duration(seconds) if seconds is not None else None,
                              secondary=_delta(seconds, duration(before), period, "duration")))
    return _metric_row(tiles, label="Visitors")


def _downloads(data: dict[str, Any], visitors: dict[str, Any] | None, period: str) -> str:
    now, before = data.get("current") or {}, data.get("previous") or {}
    site = visitors or {}
    site_now, site_before = site.get("current") or {}, site.get("previous") or {}
    conversion = _rate(now.get("visitors"), site_now.get("visitors"))
    return _metric_row([
        _metric_tile("Downloads", now.get("events"), secondary=_delta(now.get("events"), before.get("events"), period)),
        _metric_tile("Visitors who downloaded", now.get("visitors"),
                     secondary=_delta(now.get("visitors"), before.get("visitors"), period)),
        _metric_tile("Conversion", conversion, fmt="rate", secondary=_delta(
            conversion, _rate(before.get("visitors"), site_before.get("visitors")), period, "rate")),
    ], label="Downloads")


def _vital_value(key: str, value: float) -> str:
    if key == "cls":
        return f"{value:.3f}".rstrip("0").rstrip(".") if value else "0"
    if value >= 1000:
        return f"{value / 1000:.2f} s"
    return f"{round(value):,} ms"


def _limit(key: str, good: float) -> str:
    return f"Good ≤ {_vital_value(key, good) if key == 'cls' else (f'{good / 1000:g} s' if good >= 1000 else f'{good:g} ms')}"


def _rating(value: float, limits: tuple[float, float]) -> str:
    if value <= limits[0]:
        return _status_pill("success", "Good")
    if value <= limits[1]:
        return _status_pill("warning", "Needs improvement")
    return _status_pill("danger", "Poor")


def _vitals(data: dict[str, Any]) -> str:
    """p75 per metric with its rating from 20 samples on; below that the value
    stays and a grey Few samples pill replaces the rating."""
    count = data.get("count")
    enough = count is not None and count >= VITALS_MIN_SAMPLES
    tiles = []
    for key, label, limits in VITALS:
        value = data.get(key)
        mark = (_rating(value, limits) if enough and value is not None
                else _status_pill("unknown", f"Few samples ({count or 0:,})"))
        limit = f"<span class='web-visits-limit'>{html.escape(_limit(key, limits[0]))}</span>"
        tiles.append(_metric_tile(label, value, value_html=None if value is None else html.escape(_vital_value(key, value)),
                                  secondary=mark + limit))
    tiles.append(_metric_tile("Samples", count))
    return _metric_row(tiles, label="Web Vitals")


def _errors(data: dict[str, Any], previous: dict[str, Any] | None, period: str) -> str:
    tiles = _metric_row([
        _metric_tile("Errors", data.get("total"), failure=True,
                     secondary=_delta(data.get("total"), (previous or {}).get("total"), period, better="down")),
        _metric_tile("Issues", data.get("issues"),
                     secondary=_delta(data.get("issues"), (previous or {}).get("issues"), period, better="down")),
    ], label="Errors")
    top = data.get("top") or []
    if not top:
        return tiles + _empty_state("empty", "No errors in this period.")
    rows = "".join(
        f"<tr><td>{html.escape(issue['message'] or '—')}</td><td class='column-number'>{issue['count']:,}</td></tr>"
        for issue in top)
    # The ranking list look of Referrers and Entry pages, also on phones.
    return tiles + (
        "<div class='map-statistics-popularity'><div class='table-wrap'><table class='admin-table popular-maps-table' data-own-mobile-layout>"
        "<caption class='sr-only'>Most frequent errors</caption><thead><tr><th scope='col'>Error</th>"
        f"<th scope='col' class='column-number'>Count</th></tr></thead><tbody>{rows}</tbody></table></div></div>"
    )


# Every Umami event the site and the web installer send, by group, with the
# name the Events table shows (owner request 2026-11-15). Another
# ``*-link-click`` joins Navigation & links and any other event joins Other,
# each under its own name, so a new event never disappears.
EVENT_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Download", (("download-cta-click", "Download button"), ("download-click", "Download started"))),
    ("Web installer", (
        ("web-installer-cta-click", "Installer button"), ("web-installer-link-click", "Installer link"),
        ("web-installer-gate", "Browser check"), ("web-installer-connected", "Garmin connected"),
        ("web-installer-done", "Install finished"), ("installer-result", "Installer result"),
        ("install-link-copy", "Installer link copied"))),
    ("Maps", (("map-style-switch", "Map style switch"), ("map-compare", "Map compare"),
              ("maps-link-click", "Maps link"))),
    ("Navigation & links", (
        ("language-switch-click", "Language switch"), ("guide-link-click", "Guide link"),
        ("internal-link-click", "Internal link"), ("compatibility-link-click", "Compatibility link"),
        ("navigation-link-click", "Navigation link"), ("home-link-click", "Home link"),
        ("privacy-link-click", "Privacy link"), ("legal-link-click", "Legal link"), ("faq-link-click", "FAQ link"),
        ("support-link-click", "Support link"), ("social-link-click", "Social link"),
        ("project-link-click", "Project link"), ("licence-link-click", "Licence link"),
        ("outbound-link-click", "Outbound link"))),
    ("Other", (("app-store-click", "App Store button"), ("donate", "Donate"),
               ("guide-command-copy", "Guide command copied"))),
)
_EVENT_NAMES = {event: (group, label) for group, events in EVENT_GROUPS for event, label in events}
NAVIGATION_GROUP, OTHER_GROUP = "Navigation & links", "Other"
# Rows a group shows before Show all; Navigation & links starts closed.
EVENT_GROUP_ROWS = 3
# Groups whose changes have no better direction: grey.
_PLAIN_GROUPS = {NAVIGATION_GROUP, OTHER_GROUP}
# Key events chart: event -> (swatch and line class, legend name), in the
# fixed colour order Interactive Primary, Lichen dark, Stone dark.
KEY_EVENT_SERIES = {"download-click": ("events-download", "Download started"),
                    "web-installer-done": ("events-installed", "Install finished"),
                    "map-compare": ("events-compare", "Map compare")}
TRACKING_GAP = "Tracking gap"
MAP_LEVELS = 5


def event_label(name: str) -> tuple[str, str]:
    """(group, shown name) of one Umami event."""
    if name in _EVENT_NAMES:
        return _EVENT_NAMES[name]
    return (NAVIGATION_GROUP if name.endswith("-link-click") else OTHER_GROUP), name


def _change(current: int, previous: int | None, period: str, *, plain: bool) -> str:
    """The table form of ``_delta``: arrow and signed amount, the compared
    period for screen readers only."""
    if period not in PREVIOUS or previous is None:
        return ""
    change = current - previous
    against = f"<span class='sr-only'> vs {PREVIOUS[period]}</span>"
    if change == 0:
        return f"<span class='funnel-delta' data-trend='same'><span aria-hidden='true'>=</span><span class='sr-only'>Same</span>{against}</span>"
    arrow, sign = ("▲", "+") if change > 0 else ("▼", "−")
    trend = "neutral" if plain or not previous else ("better" if change > 0 else "worse")
    return (f"<span class='funnel-delta' data-trend='{trend}'><span aria-hidden='true'>{arrow}</span> "
            f"{sign}{abs(change):,}{against}</span>")


def _events(data: list[dict[str, Any]], previous: list[dict[str, Any]] | None, period: str) -> str:
    """Every event in its group, most frequent first; a group shows 3 rows
    (Navigation & links none) until Show all."""
    now = {row["name"]: row["count"] for row in data}
    before = None if previous is None or period not in PREVIOUS else {row["name"]: row["count"] for row in previous}
    names = set(now) | set(before or {})
    if not any(now.values()) and not any((before or {}).values()):
        return _empty_state("empty", "No events in this period.")
    grouped: dict[str, list[tuple[str, int, int | None]]] = {}
    for name in names:
        group, label = event_label(name)
        grouped.setdefault(group, []).append((label, now.get(name, 0), None if before is None else before.get(name, 0)))
    columns = 3 if before is not None else 2
    bodies = []
    for index, group in enumerate([group for group, _ in EVENT_GROUPS]):
        rows = sorted(grouped.get(group) or [], key=lambda row: (-row[1], row[0]))
        if not rows:
            continue
        limit = 0 if group == NAVIGATION_GROUP else EVENT_GROUP_ROWS
        body_id = f"web-visits-events-{index}"
        toggle = ""
        if len(rows) > limit:
            closed = "Show" if limit == 0 else "Show all"
            toggle = (f"<button type='button' class='web-visits-events-toggle' data-events-toggle data-limit='{limit}' "
                      f"data-closed='{closed} {len(rows)}' data-open='{'Hide' if limit == 0 else 'Show fewer'}' "
                      f"aria-expanded='false' aria-controls='{body_id}'>{closed} {len(rows)}"
                      f"<span class='sr-only'> {html.escape(group)}</span></button>")
        cells = "".join(
            f"<tr data-events-row{' hidden' if position >= limit else ''}><td>{html.escape(label)}</td>"
            f"<td class='column-number'>{count:,}</td>"
            + (f"<td class='column-number'>{_change(count, old, period, plain=group in _PLAIN_GROUPS)}</td>"
               if columns == 3 else "") + "</tr>"
            for position, (label, count, old) in enumerate(rows))
        bodies.append(
            f"<tbody id='{body_id}'><tr class='web-visits-events-group'><th scope='rowgroup' colspan='{columns}'>"
            f"<span>{html.escape(group)}</span>{toggle}</th></tr>{cells}</tbody>")
    change_head = "<th scope='col' class='column-number'>Change</th>" if columns == 3 else ""
    return ("<div class='table-wrap'><table class='admin-table web-visits-events-table' data-own-mobile-layout"
            f" data-columns='{columns}'><caption class='sr-only'>Events</caption><thead><tr><th scope='col'>Event</th>"
            f"<th scope='col' class='column-number'>Count</th>{change_head}</tr></thead>{''.join(bodies)}</table></div>")


def _series_buckets(snapshot: dict[str, Any], unit: str) -> list[tuple[str, str]]:
    """(key, axis label) per local day or hour from the period's start to now."""
    try:
        zone = ZoneInfo(snapshot.get("timeZone") or "UTC")
    except Exception:  # noqa: BLE001 - an unknown zone is UTC, as for the page
        zone = ZoneInfo("UTC")
    start = datetime.fromtimestamp(snapshot["startAt"] / 1000, timezone.utc).astimezone(zone)
    end = datetime.fromtimestamp(snapshot["endAt"] / 1000, timezone.utc).astimezone(zone)
    buckets = []
    if unit == "hour":
        moment = start.replace(minute=0, second=0, microsecond=0)
        while moment <= end and len(buckets) < 200:
            buckets.append((moment.strftime("%Y-%m-%d %H"), moment.strftime("%H:00")))
            moment = (moment + timedelta(hours=1)).astimezone(zone)
    else:
        day = start.date()
        while day <= end.date() and len(buckets) < 400:
            buckets.append((day.isoformat(), _day_label(day)))
            day += timedelta(days=1)
    return buckets


def _key_events_svg(buckets: list[tuple[str, str]], values: dict[str, list[int]], width: int, variant: str) -> str:
    font = 13 if variant == "mobile" else 11
    height, left, right, top, bottom = 200, 36, 12, 12, 28
    plot, base = width - left - right, height - bottom
    count = len(buckets)
    xs = [left + (plot * index / (count - 1) if count > 1 else plot / 2) for index in range(count)]
    step = _nice_tick_step(max(max(series) for series in values.values()))
    scale = step * 4
    parts = []
    for amount in (0, step * 2, scale):
        y = base - (base - top) * amount / scale
        parts.append(f"<line class='overview-chart-grid' x1='{left}' x2='{width - right}' y1='{y:.1f}' y2='{y:.1f}'/>"
                     f"<text class='overview-chart-axis-label' x='{left - 8}' y='{y + 4:.1f}' text-anchor='end'>"
                     f"{_compact(amount)}</text>")
    points: dict[str, list[tuple[float, float]]] = {}
    for event in KEY_EVENTS:
        css = KEY_EVENT_SERIES[event][0]
        points[event] = [(x, base - (base - top) * value / scale) for x, value in zip(xs, values[event])]
        coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points[event])
        parts.append(f"<g class='web-visits-series-{css}'>"
                     + (f"<polyline class='gsc-chart-line' points='{coords}'/>" if count > 1 else
                        f"<circle class='gsc-chart-dot' cx='{xs[0]:.1f}' cy='{points[event][0][1]:.1f}' r='3'/>")
                     + "</g>")
    slot = plot / max(count - 1, 1) if count > 1 else plot
    for index, (x, (_, label)) in enumerate(zip(xs, buckets)):
        items = [(KEY_EVENT_SERIES[event][0], KEY_EVENT_SERIES[event][1], values[event][index]) for event in KEY_EVENTS]
        text = label + " · " + " · ".join(f"{name} {value:,}" for _, name, value in items)
        dots = "".join(f"<circle class='gsc-chart-focus web-visits-series-{KEY_EVENT_SERIES[event][0]}' cx='{x:.1f}' "
                       f"cy='{points[event][index][1]:.1f}' r='3.5'/>" for event in KEY_EVENTS)
        hit_x = max(x - slot / 2, left)
        parts.append(
            f"<g class='overview-chart-group gsc-chart-day' role='img' tabindex='0'"
            f"{_chart_value_attributes(label, items, None)} aria-label='{html.escape(text, quote=True)}'>"
            f"<title>{html.escape(text)}</title><rect class='gsc-chart-hit' x='{hit_x:.1f}' y='{top}' "
            f"width='{min(slot, width - right - hit_x):.1f}' height='{base - top}'/>{dots}</g>")
    labels = [label for _, label in buckets]
    for index, anchor in _chart_axis_labels(xs, labels, font_size=font, chart_width=width):
        parts.append(f"<text x='{xs[index]:.1f}' y='{height - 8}' text-anchor='{anchor}' aria-hidden='true'>"
                     f"{html.escape(labels[index])}</text>")
    return (f"<svg class='overview-trend-chart overview-trend-{variant} web-visits-events-chart' viewBox='0 0 {width} {height}' "
            f"role='group' aria-label='Key events over time'>{''.join(parts)}</svg>")


def _key_events(data: dict[str, Any], snapshot: dict[str, Any]) -> str:
    """Download started, Install finished and Map compare per day (per hour
    for Today and Last 24 hours); a bucket without events is 0."""
    unit = data.get("unit") or "day"
    buckets = _series_buckets(snapshot, unit)
    series = data.get("series") or {}
    values = {event: [int((series.get(event) or {}).get(key, 0)) for key, _ in buckets] for event in KEY_EVENTS}
    if not buckets or not any(any(row) for row in values.values()):
        return _empty_state("empty", "No key events in this period.")
    legend = _chart_legend([(KEY_EVENT_SERIES[event][0], KEY_EVENT_SERIES[event][1], sum(values[event]))
                            for event in KEY_EVENTS], label="Key events")
    return ("<div class='overview-chart-wrap'>" + "".join(
        _key_events_svg(buckets, values, width, variant) for width, variant in ((720, "desktop"), (360, "mobile")))
        + legend + _chart_value_strip() + "</div>")


def _funnel(steps: list[tuple[str, int | None]], caption: str = "Web installer funnel") -> str:
    """Visitors of each step as a bar against the first step. A step with
    more visitors than the step before has no percentage and a grey Tracking
    gap mark instead (the events count different things), never a negative
    drop-off."""
    first = steps[0][1]
    widest = max((value or 0) for _, value in steps)
    rows = []
    for index, (label, value) in enumerate(steps):
        before = steps[index - 1][1] if index else None
        gap = value is not None and before is not None and value > before
        if value is None:
            share = "—"
        elif gap:
            share = _status_pill("neutral", TRACKING_GAP)
        elif first:
            share = f"{value / first * 100:.0f}%"
        else:
            share = "—"
        width = 0 if not value or not widest else max(value / widest * 100, 1)
        number = "—" if value is None else f"{value:,}"
        rows.append(
            f"<tr{' data-gap' if gap else ''}><td>{html.escape(label)}</td>"
            f"<td class='web-visits-funnel-bar'><span class='web-visits-funnel-track' aria-hidden='true'>"
            f"<span style='width:{width:.1f}%'></span></span><span class='numeric'>{number}</span></td>"
            f"<td class='column-number'>{share}</td></tr>")
    return ("<div class='table-wrap'><table class='admin-table web-visits-funnel' data-own-mobile-layout>"
            f"<caption class='sr-only'>{html.escape(caption)}</caption><thead><tr><th scope='col'>Step</th>"
            "<th scope='col'>Visitors</th><th scope='col' class='column-number'>Of first step</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def _funnel_card(blocks: dict[str, dict[str, Any]]) -> str:
    states = [blocks.get(name) or {} for name, _ in FUNNEL_STEPS]
    if all(state.get("state") == "hidden" for state in states):
        return ""
    data = [_usable(state) for state in states]
    card_id = _card_id("funnel")
    if not any(data):
        return _section_card(TITLES["funnel"], _empty_state("unavailable", UNAVAILABLE), card_id=card_id, css=_LIST)
    steps = [(event_label(event)[1], None if item is None else ((item.get("current") or {}).get("visitors")))
             for (_, event), item in zip(FUNNEL_STEPS, data)]
    steps = [(label, None if value is None else int(value)) for label, value in steps]
    if not any(value for _, value in steps):
        body = _empty_state("empty", "No web installer visits in this period.")
    else:
        body = _funnel(steps)
    stale = [state for state in states if state.get("state") == "stale"]
    marks = _stale(min(stale, key=lambda state: state["fetchedAt"])) if stale else ""
    return _section_card(TITLES["funnel"], body, card_id=card_id, css=_LIST, totals=marks)


@lru_cache(maxsize=1)
def _area_names() -> dict[str, str]:
    """Preview area id -> English name (the packaged copy of
    contracts/map-preview-areas.json)."""
    return {area.id: area.name.get("en") or area.id for area in load_areas()}


def _marks(states: list[dict[str, Any]]) -> str:
    stale = [state for state in states if state.get("state") == "stale"]
    return _stale(min(stale, key=lambda state: state["fetchedAt"])) if stale else ""


def _map_card(name: str, states: list[dict[str, Any]], body: Callable[[list[Any]], str]) -> str:
    """One Map styles card from its Umami blocks: hidden or unavailable with
    its first block, with the oldest stale mark of all."""
    if states[0].get("state") == "hidden":
        return ""
    data = [_usable(state) for state in states]
    if data[0] is None:
        return _section_card(TITLES[name], _empty_state("unavailable", UNAVAILABLE), card_id=_card_id(name), css=_LIST)
    return _section_card(TITLES[name], body(data), card_id=_card_id(name), css=_LIST, totals=_marks(states))


def _map_page(data: list[Any]) -> str:
    """Visitors of /map-styles/ in every language and those who changed the
    map (map-compare visitors), as funnel bars."""
    visitors = lambda item: None if item is None or (item.get("current") or {}).get("visitors") is None else int(
        item["current"]["visitors"])
    steps = [("Page visitors", visitors(data[0])), ("Changed the map", visitors(data[1]))]
    if not any(value for _, value in steps):
        return _empty_state("empty", "No Map styles visits in this period.")
    return _funnel(steps, TITLES["mapPage"])


def _map_changes(data: list[Any]) -> str:
    """map-compare events per change, most first (ties in MAP_CHANGES order),
    and a grey Not recorded row for events without one (before 2026-11-17)."""
    changes, compare = data
    events = int(((compare or {}).get("current") or {}).get("events") or 0)
    order = {value: index for index, (value, _) in enumerate(MAP_CHANGES)}
    labels = dict(MAP_CHANGES)
    rows = [(html.escape(labels.get(row["name"], row["name"])), row["count"], "")
            for row in sorted(changes or [], key=lambda row: (-row["count"], order.get(row["name"], len(order)), row["name"]))]
    missing = events - sum(row["count"] for row in changes or [])
    if missing > 0:
        rows.append(("Not recorded", missing, "web-visits-direct"))
    return _ranking(TITLES["mapChanges"], "Change", rows, "No map changes in this period.", count_label="Events")


def _map_areas(data: list[Any]) -> str:
    names = _area_names()
    rows = [(html.escape(names.get(row["name"], row["name"])), row["count"], "") for row in (data[0] or [])[:MAP_STYLES_LIMIT]]
    return _ranking(TITLES["mapAreas"], "Place", rows, "No map changes in this period.", count_label="Events")


def _map_cards(blocks: dict[str, dict[str, Any]]) -> str:
    state = lambda name: blocks.get(name) or {}
    return "".join(part for part in (
        _map_card("mapPage", [state("mapPage"), state("mapCompare")], _map_page),
        _map_card("mapCountries", [state("mapCountries")],
                  lambda data: _ranking(TITLES["mapCountries"], "Country", _country_cells(data[0]), "No visits in this period.")),
        _map_card("mapChanges", [state("mapChanges"), state("mapCompare")], _map_changes),
        _map_card("mapAreas", [state("mapAreas")], _map_areas),
    ) if part)


def _map_levels(values: list[int]) -> tuple[Callable[[int], int], list[tuple[int, int, int]]]:
    """Five logarithmic classes from 1 to the most visitors, so one large
    country does not wash out the rest: (level of a count, [(level, low,
    high)] for the legend). Empty classes drop out; the rest spread over the
    five colour steps."""
    top = max(values)
    edges = [math.floor(top ** (step / MAP_LEVELS) + 1e-9) for step in range(MAP_LEVELS + 1)]
    edges[0], edges[-1] = 0, top
    classes = [(edges[step] + 1, edges[step + 1]) for step in range(MAP_LEVELS) if edges[step + 1] > edges[step]]
    spread = [1 + round(index * (MAP_LEVELS - 1) / max(len(classes) - 1, 1)) for index in range(len(classes))]
    if len(classes) == 1:
        spread = [MAP_LEVELS]
    legend = [(level, low, high) for level, (low, high) in zip(spread, classes)]

    def level(count: int) -> int:
        return next((step for step, low, high in legend if count <= high), legend[-1][0])

    return level, legend


def _visits_map(rows: list[dict[str, Any]]) -> str:
    """The choropleth beside the Countries list: the same numbers, so it is
    decorative for screen readers (aria-hidden); the shapes load when the
    card comes into view."""
    known = [row for row in rows if row["name"] and row["visitors"] > 0]
    if not known:
        return ""
    total = sum(row["visitors"] for row in rows)
    level, legend = _map_levels([row["visitors"] for row in known])
    payload = {row["name"]: [row["visitors"], level(row["visitors"]),
                             f"{row['visitors'] / total * 100:.1f}".removesuffix(".0") + "%"] for row in known}
    swatches = "".join(
        f"<li><i class='web-visits-map-l{step}'></i><span>{low:,}{'' if low == high else f'–{high:,}'}</span></li>"
        for step, low, high in legend)
    return (f"<div class='web-visits-map' aria-hidden='true' data-visits-map='{html.escape(json.dumps(payload), quote=True)}'"
            f" data-visits-map-src='{VISITS_MAP_PATH}'><div class='web-visits-map-canvas'></div>"
            "<div class='web-visits-map-tooltip' hidden></div>"
            f"<ul class='admin-legend web-visits-map-legend'>{swatches}"
            "<li><i class='web-visits-map-none'></i><span>No visits</span></li></ul></div>")


def _views_mixed(snapshot: dict[str, Any]) -> bool:
    """Whether the compared span reaches before the old map views stopped;
    the Views change is then grey, without a note (owner request 2026-11-14)."""
    since = snapshot.get("previousStartAt") if snapshot["period"] != "all" else snapshot.get("startAt")
    return since is not None and since < CLEAN_VIEWS_SINCE.timestamp() * 1000


_KPI = "admin-kpi-panel web-installer-server"
_HEAD = "admin-kpi-panel web-visits-kpis"
_LIST = "map-statistics-popularity"
# The map's shapes: a content-versioned asset (served by the admin map-assets
# route), read once when a Countries card with data comes into view.
VISITS_MAP_PATH = "/admin/map-assets/visits-map." + hashlib.sha256(VISITS_MAP_SVG.encode("utf-8")).hexdigest()[:16] + ".svg"


def website_stats_blocks(snapshot: dict[str, Any] | None, *, dashboard_url: str | None) -> str:
    """The page's blocks, in order, for one snapshot (None: Umami is not configured)."""
    if not snapshot:
        return _section_card("Web visits", _empty_state("unavailable", UNAVAILABLE), card_id="web-visits-unavailable")
    period, blocks = snapshot["period"], snapshot["blocks"]
    visitors = _usable(blocks["visitors"])
    cards = []
    headline = "".join(part for part in (
        _card("visitors", blocks["visitors"], lambda data: _visitors(data, period, _views_mixed(snapshot)), css=_HEAD),
        _card("downloads", blocks["downloads"], lambda data: _downloads(data, visitors, period), css=_HEAD),
    ) if part)
    if headline:
        cards.append(f"<div class='web-installer-grid web-visits-headline'>{headline}</div>")
    lists = "".join(part for part in (
        _card("referrers", blocks["referrers"], lambda data: _referrers(data, visitors), css=_LIST),
        _card("entries", blocks["entries"], _entries, css=_LIST),
    ) if part)
    if lists:
        cards.append(f"<div class='web-installer-grid web-visits-lists'>{lists}</div>")
    cards.append(_card("countries", blocks["countries"], _countries, css=_LIST + " web-visits-countries-card"))
    events = _card("events", blocks["events"], lambda data: _events(
        data, _usable(blocks.get("previousEvents")), period), css=_LIST)
    side = "".join(part for part in (
        _card("eventSeries", blocks["eventSeries"], lambda data: _key_events(data, snapshot), css="overview-chart-panel"),
        _funnel_card(blocks),
    ) if part)
    if events or side:
        cards.append(f"<div class='web-installer-grid web-visits-events'>{events}"
                     + (f"<div class='web-visits-events-side'>{side}</div>" if side else "") + "</div>")
    maps = _map_cards(blocks)
    if maps:
        cards.append(f"<div class='web-installer-grid web-visits-lists'>{maps}</div>")
    cards.append(_card("vitals", blocks["vitals"], _vitals, css=_KPI))
    cards.append(_card("errors", blocks["errors"],
                       lambda data: _errors(data, _usable(blocks.get("previousErrors")), period), css=_KPI))
    fetched = [block["fetchedAt"] for block in blocks.values() if block.get("fetchedAt")]
    footer = []
    if fetched:
        footer.append(f"Updated {_timestamp_markup(datetime.fromtimestamp(min(fetched), timezone.utc))}")
    if dashboard_url:
        footer.append(f"<a class='section-link' href='{html.escape(dashboard_url, quote=True)}' target='_blank' "
                      f"rel='noopener noreferrer'>Open Umami&nbsp;{_admin_icon('external')}</a>")
    if footer:
        cards.append(f"<p class='web-installer-tests muted-value'>{' · '.join(footer)}</p>")
    return "".join(card for card in cards if card)


def _loading_blocks() -> str:
    """What the page shows until the stats arrive: every block as a skeleton."""
    loading = lambda name, css=_KPI: _section_card(
        TITLES[name], "<div class='web-visits-skeleton' aria-hidden='true'><span></span><span></span><span></span></div>"
        "<span class='sr-only'>Loading…</span>", card_id=_card_id(name), css=css,
        extra_attributes=" data-website-stats-block aria-busy='true'")
    skeleton = ("<div class='web-visits-skeleton' aria-hidden='true'><span></span><span></span><span></span></div>"
                "<span class='sr-only'>Loading…</span>")
    headline = lambda name: _headline(name, skeleton, " aria-busy='true'")
    return ("<div class='web-installer-grid web-visits-headline' data-website-stats-block>" + headline("visitors")
            + headline("downloads") + "</div>"
            + "<div class='web-installer-grid web-visits-lists' data-website-stats-block>" + loading("referrers", _LIST)
            + loading("entries", _LIST) + "</div>" + loading("countries", _LIST + " web-visits-countries-card")
            + "<div class='web-installer-grid web-visits-events' data-website-stats-block>" + loading("events", _LIST)
            + "<div class='web-visits-events-side'>" + loading("eventSeries", "overview-chart-panel") + loading("funnel", _LIST)
            + "</div></div>"
            + "<div class='web-installer-grid web-visits-lists' data-website-stats-block>"
            + "".join(loading(name, _LIST) for name in ("mapPage", "mapCountries", "mapChanges", "mapAreas"))
            + "</div>" + loading("vitals") + loading("errors"))


def _website_stats_script() -> str:
    """Reads the blocks for the shown period and puts them in place of the
    loading ones; a failed read shows Unavailable. Country codes get their
    English names from the browser."""
    return r"""(() => {
      let request = 0;
      const regionNames = (() => {
        try { return new Intl.DisplayNames(['en'], {type: 'region'}); } catch (error) { return null; }
      })();
      const load = async () => {
        const main = document.querySelector('#main-content');
        const form = document.querySelector('#overview-period-form');
        const failed = document.querySelector('#website-stats-failed');
        if (!main || !form || !failed || main.dataset.websiteStatsLoaded === 'true') return;
        main.dataset.websiteStatsLoaded = 'true';
        const number = ++request;
        const url = new URL('/admin/api/umami', window.location.origin);
        url.searchParams.set('period', document.querySelector('#overview-period')?.value || '7d');
        url.searchParams.set('timeZone', form.dataset.timeZone || 'UTC');
        main.setAttribute('aria-busy', 'true');
        let markup = null;
        try {
          const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
          if (response.ok) markup = (await response.json()).html;
        } catch (error) { markup = null; }
        if (number !== request || !main.isConnected) return;
        const next = document.createElement('template');
        next.innerHTML = typeof markup === 'string' ? markup : failed.innerHTML;
        next.content.querySelectorAll('[data-region-name]').forEach((node) => {
          let name = null;
          try { name = regionNames?.of(node.dataset.regionName); } catch (error) { name = null; }
          if (name) node.textContent = name;
        });
        main.querySelectorAll(':scope > [data-website-stats-block]').forEach((node) => node.remove());
        [...next.content.children].forEach((node) => node.setAttribute('data-website-stats-block', ''));
        failed.before(next.content);
        main.removeAttribute('aria-busy');
        window.TerentoAdminTime?.render();
        main.querySelectorAll('[data-visits-map]').forEach((box) => (observer ? observer.observe(box) : drawMap(box)));
      };
      // Events: a group's Show all / Show fewer (Navigation & links: Show / Hide).
      document.addEventListener('click', (event) => {
        const button = event.target instanceof Element ? event.target.closest('[data-events-toggle]') : null;
        const body = button && document.getElementById(button.getAttribute('aria-controls') || '');
        if (!body) return;
        const open = button.getAttribute('aria-expanded') !== 'true';
        const limit = Number(button.dataset.limit || 0);
        body.querySelectorAll('tr[data-events-row]').forEach((row, index) => { row.hidden = !open && index >= limit; });
        button.setAttribute('aria-expanded', String(open));
        button.firstChild.textContent = open ? button.dataset.open : button.dataset.closed;
      });
      // Countries map: the shapes are read once, when a map comes into view.
      let shapes = null;
      const readShapes = (src) => (shapes ??= fetch(src, {credentials: 'same-origin'})
        .then((response) => (response.ok ? response.text() : Promise.reject(new Error('map'))))
        .catch((error) => { shapes = null; throw error; }));
      const countryName = (code) => {
        try { return regionNames?.of(code.toUpperCase()) || code.toUpperCase(); } catch (error) { return code.toUpperCase(); }
      };
      const drawMap = async (box) => {
        let values = {};
        try { values = JSON.parse(box.dataset.visitsMap || '{}'); } catch (error) { values = {}; }
        let svg = null;
        try { svg = await readShapes(box.dataset.visitsMapSrc); } catch (error) { svg = null; }
        const canvas = box.querySelector('.web-visits-map-canvas');
        const tip = box.querySelector('.web-visits-map-tooltip');
        if (!box.isConnected || !canvas || !tip) return;
        if (typeof svg !== 'string' || !svg.startsWith('<svg')) { box.hidden = true; return; }
        canvas.innerHTML = svg;
        Object.entries(values).forEach(([code, entry]) => {
          const shape = canvas.querySelector('#v-' + code.toLowerCase());
          if (shape && Array.isArray(entry)) shape.classList.add('web-visits-map-l' + Number(entry[1]));
        });
        box.classList.add('is-ready');
        let active = null;
        const hide = () => { active?.classList.remove('is-active'); active = null; tip.hidden = true; };
        const show = (shape, x, y) => {
          const code = shape.id.slice(2);
          const entry = values[code.toUpperCase()];
          active?.classList.remove('is-active');
          active = shape;
          shape.classList.add('is-active');
          const title = document.createElement('strong');
          title.textContent = countryName(code);
          const line = document.createElement('span');
          line.textContent = Array.isArray(entry)
            ? `${Number(entry[0]).toLocaleString('en-US')} visitor${Number(entry[0]) === 1 ? '' : 's'} · ${entry[2]} of all`
            : 'No visits';
          tip.replaceChildren(title, line);
          tip.hidden = false;
          const room = box.getBoundingClientRect();
          const left = Math.min(Math.max(x - room.left + 12, 4), room.width - tip.offsetWidth - 4);
          const top = y - room.top - tip.offsetHeight - 12;
          tip.style.left = `${left}px`;
          tip.style.top = `${top < 4 ? y - room.top + 16 : top}px`;
        };
        canvas.addEventListener('pointermove', (event) => {
          const shape = event.target instanceof Element ? event.target.closest('path[id^="v-"]') : null;
          if (shape) show(shape, event.clientX, event.clientY); else hide();
        });
        canvas.addEventListener('pointerleave', hide);
        // A Countries row points at its country on the map.
        const list = box.closest('.web-visits-countries')?.querySelector('.web-visits-countries-list');
        list?.addEventListener('pointerover', (event) => {
          const code = event.target instanceof Element ? event.target.closest('tr')?.querySelector('[data-country]')?.dataset.country : null;
          const shape = code ? canvas.querySelector('#v-' + code) : null;
          if (!shape) { hide(); return; }
          const box2 = shape.getBoundingClientRect();
          show(shape, box2.left + box2.width / 2, box2.top + box2.height / 2);
        });
        list?.addEventListener('pointerleave', hide);
      };
      const observer = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          observer.unobserve(entry.target);
          drawMap(entry.target);
        });
      }, {rootMargin: '200px 0px'}) : null;
      window.addEventListener('terento-admin-content-changed', load);
      load();
    })();"""


def website_stats_page(user: dict[str, Any], csrf_token: str, *, period: str, time_zone: str = "UTC") -> bytes:
    """Web visits: the Admin period filter, then every block loading."""
    if period not in ADMIN_PERIODS:
        period = "7d"
    options = "".join(
        f"<option value='{value}'{' selected' if value == period else ''}>{ADMIN_PERIOD_LABELS[value]}</option>"
        for value in ADMIN_PERIODS
    )
    failed = website_stats_blocks(None, dashboard_url=None)
    content = f"""
      {_admin_header(user, csrf_token, active='web-visits')}
      <main class='dashboard overview-page web-installer-page web-visits-page' id='main-content' data-admin-no-titles>
        <div class='heading-row overview-heading'><div><h1>Web visits</h1></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin/web-visits' data-time-zone='{html.escape(time_zone, quote=True)}'><span class='web-installer-source'>{_admin_icon('source-web')}Umami</span><label><span class='sr-only'>Time period</span><select id='overview-period' data-admin-dropdown name='period'>{options}</select></label></form></div>
        {_loading_blocks()}
        <template id='website-stats-failed'>{failed}</template>
        {_gsc_loading()}
        <template id='gsc-failed'>{search_console_blocks(None, console_url=None)}</template>
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_overview_period_script()}{_website_stats_script()}{_gsc_script()}</script>
    """
    return _layout("Web visits", content, sections={"webVisits": period})


# Google Search (Search Console): its own block under the Umami numbers,
# loaded from /admin/api/gsc with its own period picker (Last 7 days, Last 30
# days, All time; default Last 30 days): the Admin period does not change it
# (owner 2026-11-14).
GSC_UNAVAILABLE = "Search Console unavailable."
GSC_NOTE = "Google Search Console · dates in Pacific Time · data delayed 2–3 days"
NEAR_TOP_TITLE = "Position 4–10 with many impressions: closest to page-one top"


def _gsc_period_picker(period: str) -> str:
    options = "".join(f"<option value='{value}'{' selected' if value == period else ''}>{ADMIN_PERIOD_LABELS[value]}</option>"
                      for value in GSC_PERIODS)
    return ("<div class='filter-bar web-visits-gsc-period'><label><span class='sr-only'>Google Search period</span>"
            f"<select id='gsc-period' data-admin-dropdown>{options}</select></label></div>")


def _gsc_section(body: str, marks: str = "", *, period: str, loading: bool = False) -> str:
    busy = " aria-busy='true'" if loading else ""
    return (f"<section class='web-visits-gsc' id='web-visits-gsc' aria-labelledby='web-visits-gsc-title' data-gsc-period='{period}'{busy}>"
            f"<div class='web-visits-gsc-heading'><h2 id='web-visits-gsc-title'>Google Search</h2>"
            f"<span class='web-installer-source'>{_source_icon('google.com')}Search Console</span>{marks}"
            f"{_gsc_period_picker(period)}</div>"
            f"{body}</section>")


def _gsc_card(name: str, title: str, body: str, css: str = "") -> str:
    return _section_card(title, body, card_id=f"web-visits-gsc-{name}", css=css)


def _compact(value: float) -> str:
    return f"{value / 1000:g}k" if value >= 1000 else f"{value:g}"


def _day_label(day: date) -> str:
    return day.strftime("%d %b")


def _gsc_buckets(data: dict[str, Any], start: str, end: str, weekly: bool) -> list[dict[str, Any]]:
    """One point per day (per week for All time), gaps filled with 0: Search
    Console has no row for a day without impressions. All time starts at the
    first day with data."""
    by_day = {item["date"]: item for item in data.get("days") or []}
    first = date.fromisoformat(min(by_day)) if weekly and by_day else date.fromisoformat(start)
    last = date.fromisoformat(end)
    incomplete = data.get("firstIncompleteDate")
    buckets: list[dict[str, Any]] = []
    day = first
    while day <= last:
        item = by_day.get(day.isoformat()) or {}
        key = day - timedelta(days=day.weekday()) if weekly else day
        if not buckets or buckets[-1]["key"] != key:
            buckets.append({"key": key, "clicks": 0, "impressions": 0, "preliminary": False})
        bucket = buckets[-1]
        bucket["clicks"] += int(item.get("clicks") or 0)
        bucket["impressions"] += int(item.get("impressions") or 0)
        bucket["preliminary"] = bucket["preliminary"] or bool(incomplete and day.isoformat() >= incomplete)
        day += timedelta(days=1)
    for bucket in buckets:
        bucket["label"] = ("Week of " if weekly else "") + _day_label(bucket["key"])
    return buckets


def _gsc_chart_svg(buckets: list[dict[str, Any]], width: int, variant: str) -> str:
    """Clicks over Impressions: two small line charts, each with its own Y
    axis, under one date axis (not one chart with two Y axes)."""
    font = 13 if variant == "mobile" else 11
    # A wide gap and each series in its own colour with a named swatch keep
    # Clicks and Impressions apart (owner 2026-11-14).
    height, left, right, top, gap, bottom = 252, 42, 12, 22, 46, 28
    panel = (height - top - gap - bottom) / 2
    plot_width = width - left - right
    count = len(buckets)
    xs = [left + (plot_width * index / (count - 1) if count > 1 else plot_width / 2) for index in range(count)]
    prelim = next((index for index, bucket in enumerate(buckets) if bucket["preliminary"]), None)
    parts: list[str] = []
    marks: list[list[tuple[float, float]]] = []
    for row, (metric, label) in enumerate((("clicks", "Clicks"), ("impressions", "Impressions"))):
        panel_top = top + row * (panel + gap)
        parts.append(f"<g class='gsc-series-{metric}'>")
        base = panel_top + panel
        step = _nice_tick_step(max(bucket[metric] for bucket in buckets))
        scale = step * 4
        for amount in (0, step * 2, scale):
            y = base - panel * amount / scale
            parts.append(f"<line class='overview-chart-grid' x1='{left}' x2='{width - right}' y1='{y:.1f}' y2='{y:.1f}'/>"
                         f"<text class='overview-chart-axis-label' x='{left - 8}' y='{y + 4:.1f}' text-anchor='end'>"
                         f"{_compact(amount)}</text>")
        parts.append(f"<line class='gsc-chart-swatch' x1='{left}' x2='{left + 14}' y1='{panel_top - 12:.1f}' y2='{panel_top - 12:.1f}'/>"
                     f"<text class='gsc-chart-name' x='{left + 20}' y='{panel_top - 8:.1f}'>{label}</text>")
        points = [(x, base - panel * bucket[metric] / scale) for x, bucket in zip(xs, buckets)]
        marks.append(points)
        coords = [f"{x:.1f},{y:.1f}" for x, y in points]
        solid = coords if prelim is None else coords[:prelim]
        dotted = [] if prelim is None else coords[max(prelim - 1, 0):]
        parts.append(f"<polygon class='gsc-chart-area' points='{xs[0]:.1f},{base:.1f} {' '.join(coords)} {xs[-1]:.1f},{base:.1f}'/>")
        if len(solid) > 1:
            parts.append(f"<polyline class='gsc-chart-line' points='{' '.join(solid)}'/>")
        if len(dotted) > 1:
            parts.append(f"<polyline class='gsc-chart-line is-preliminary' points='{' '.join(dotted)}'/>")
        if count == 1:
            parts.append(f"<circle class='gsc-chart-dot' cx='{points[0][0]:.1f}' cy='{points[0][1]:.1f}' r='3'/>")
        parts.append("</g>")
    if prelim is not None:
        x = xs[prelim]
        anchor = "end" if x > width - right - 80 else "start"
        parts.append(f"<line class='gsc-chart-prelim' x1='{x:.1f}' x2='{x:.1f}' y1='{top - 4}' y2='{height - bottom}'/>"
                     f"<text class='gsc-chart-prelim-label' x='{x + (-4 if anchor == 'end' else 4):.1f}' y='{top - 8}' "
                     f"text-anchor='{anchor}'>Preliminary</text>")
    slot = plot_width / max(count - 1, 1) if count > 1 else plot_width
    for index, (x, bucket) in enumerate(zip(xs, buckets)):
        when = bucket["label"] + (" (preliminary)" if bucket["preliminary"] else "")
        text = f"{when} · Clicks {bucket['clicks']:,} · Impressions {bucket['impressions']:,}"
        strip = _chart_value_attributes(when, [("gsc-clicks", "Clicks", bucket["clicks"]),
                                               ("gsc-impressions", "Impressions", bucket["impressions"])], None)
        dots = "".join(f"<circle class='gsc-chart-focus gsc-series-{metric}' cx='{x:.1f}' cy='{series[index][1]:.1f}' r='3.5'/>"
                       for metric, series in zip(("clicks", "impressions"), marks))
        parts.append(
            f"<g class='overview-chart-group gsc-chart-day' role='img' tabindex='0'{strip} aria-label='{html.escape(text, quote=True)}'>"
            f"<title>{html.escape(text)}</title><rect class='gsc-chart-hit' x='{max(x - slot / 2, left):.1f}' y='{top - 4}' "
            f"width='{min(slot, width - right - max(x - slot / 2, left)):.1f}' height='{height - bottom - top + 4}'/>{dots}</g>")
    texts = [bucket["label"].removeprefix("Week of ") for bucket in buckets]
    for index, anchor in _chart_axis_labels(xs, texts, font_size=font, chart_width=width):
        parts.append(f"<text x='{xs[index]:.1f}' y='{height - 8}' text-anchor='{anchor}' aria-hidden='true'>"
                     f"{html.escape(texts[index])}</text>")
    return (f"<svg class='overview-trend-chart overview-trend-{variant} gsc-chart' viewBox='0 0 {width} {height}' "
            f"role='group' aria-label='Google Search clicks and impressions'>{''.join(parts)}</svg>")


def _gsc_trend(data: dict[str, Any], snapshot: dict[str, Any]) -> str:
    buckets = _gsc_buckets(data, snapshot["startDate"], snapshot["endDate"], snapshot["period"] == "all")
    if not buckets or not any(bucket["impressions"] for bucket in buckets):
        return _empty_state("empty", "No Google Search impressions in this period.")
    return ("<div class='overview-chart-wrap'>" + "".join(
        _gsc_chart_svg(buckets, width, variant) for width, variant in ((720, "desktop"), (1200, "wide"), (360, "mobile")))
        + _chart_value_strip() + f"</div><p class='overview-chart-note'>{html.escape(GSC_NOTE)}</p>")


def _ctr(totals: dict[str, Any] | None) -> float | None:
    value = (totals or {}).get("ctr")
    return None if value is None else round(value * 100, 1)


def _gsc_kpis(now: dict[str, Any], before: dict[str, Any] | None, period: str) -> str:
    """Totals of the final days only; the change is against the same number
    of days just before them."""
    days = int(now.get("days") or 0)
    before = before if before and days else {}
    against = f"previous {days} day{'' if days == 1 else 's'}"
    delta = lambda current, previous, *args, **kwargs: _delta(current, previous, period, *args, against=against, **kwargs)
    position = now.get("position")
    return _metric_row([
        _metric_tile("Clicks", now.get("clicks"), secondary=delta(now.get("clicks"), before.get("clicks"))),
        _metric_tile("Impressions", now.get("impressions"),
                     secondary=delta(now.get("impressions"), before.get("impressions"))),
        _metric_tile("CTR", _ctr(now), fmt="rate", secondary=delta(_ctr(now), _ctr(before), "rate")),
        _metric_tile("Avg position", position, value_html=None if position is None else f"{position:.1f}",
                     secondary=delta(position, before.get("position"), "decimal", better="down")),
    ], label="Google Search")


def _gsc_number(value: Any, kind: str = "count") -> str:
    if value is None:
        return "—"
    if kind == "rate":
        return "<0.1%" if 0 < value < 0.001 else f"{value * 100:.1f}%"
    if kind == "position":
        return f"{value:.1f}"
    return f"{int(value):,}"


def _gsc_table(caption: str, columns: list[tuple[str, str, str]], rows: list[dict[str, Any]], first: Callable[[dict[str, Any]], str]) -> str:
    """columns: (heading, key, kind); the first column is ``first(row)``."""
    short = {"Impressions": "Impr.", "Position": "Pos."}  # phone headers; the full name stays for screen readers
    label = lambda heading: (f"<span class='gsc-full'>{heading}</span><span class='gsc-short' aria-hidden='true'>"
                             f"{short[heading]}</span>" if heading in short else html.escape(heading))
    head = "".join(f"<th scope='col'{'' if index == 0 else ' class=column-number'}>{label(heading)}</th>"
                   for index, (heading, _, _) in enumerate(columns))
    body = "".join(
        f"<tr><td data-label='{html.escape(columns[0][0], quote=True)}'>{first(row)}</td>" + "".join(
            f"<td data-label='{html.escape(heading, quote=True)}' class='column-number numeric'>{_gsc_number(row.get(key), kind)}</td>"
            for heading, key, kind in columns[1:]) + "</tr>"
        for row in rows)
    return (f"<div class='table-wrap'><table class='admin-table gsc-table' data-own-mobile-layout><caption class='sr-only'>{html.escape(caption)}</caption>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _gsc_queries(data: dict[str, Any], totals: dict[str, Any] | None) -> str:
    rows = data.get("rows") or []
    if not rows:
        return _empty_state("empty", "No queries in this period.")
    cell = lambda row: (f"<span class='gsc-query'><span>{html.escape(row['query'] or '—')}</span>"
                        + (_status_pill("info", "Near top", title=NEAR_TOP_TITLE) if row.get("nearTop") else "") + "</span>")
    table = _gsc_table("Top queries", [("Query", "", ""), ("Clicks", "clicks", "count"), ("Impressions", "impressions", "count"),
                                       ("CTR", "ctr", "rate"), ("Position", "position", "position")], rows, cell)
    total_clicks = (totals or {}).get("clicks")
    if total_clicks is not None and (data.get("clicks") or 0) < total_clicks:
        table += "<p class='overview-chart-note'>Rare queries are hidden by Google</p>"
    return table


def _gsc_pages(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return _empty_state("empty", "No pages in this period.")
    return _gsc_table("Top pages", [("Page", "", ""), ("Clicks", "clicks", "count"), ("Impressions", "impressions", "count"),
                                    ("Position", "position", "position")], rows,
                      lambda row: f"<span class='gsc-page'>{html.escape(row['path'] or '/')}</span>")


def search_console_blocks(snapshot: dict[str, Any] | None, *, console_url: str | None,
                          period: str = GSC_DEFAULT_PERIOD) -> str:
    """The Google Search block for one snapshot (None: not configured)."""
    period = (snapshot or {}).get("period") or period
    period = period if period in GSC_PERIODS else GSC_DEFAULT_PERIOD
    section = lambda body, marks="": _gsc_section(body, marks, period=period)
    link = (f"<p class='web-installer-tests muted-value'><a class='section-link' href='{html.escape(console_url, quote=True)}' "
            f"target='_blank' rel='noopener noreferrer'>Open Search Console&nbsp;{_admin_icon('external')}</a></p>"
            if console_url else "")
    if not snapshot:
        return section(_gsc_card("unavailable", "Search Console", _empty_state("unavailable", GSC_UNAVAILABLE)))
    blocks = snapshot["blocks"]
    if not any(block.get("state") in ("ok", "stale") for block in blocks.values()):
        return section(_gsc_card("unavailable", "Search Console", _empty_state("unavailable", GSC_UNAVAILABLE)) + link)
    stale = [block["fetchedAt"] for block in blocks.values() if block.get("state") == "stale"]
    marks = "" if not stale else (_status_pill("unknown", "Search Console unavailable") + "<span class='admin-metric-secondary'>"
                                  f"Last result {_timestamp_markup(datetime.fromtimestamp(min(stale), timezone.utc))}</span>")
    totals = _usable(blocks.get("totals"))
    missing = _empty_state("unavailable", GSC_UNAVAILABLE)
    kpis = (_kpi_panel(_gsc_kpis(totals, _usable(blocks.get("previousTotals")), period)) if totals
            else _gsc_card("kpis", "Totals", missing))
    dates = _usable(blocks.get("dates"))
    trend = _gsc_card("trend", "Trend", _gsc_trend(dates, snapshot) if dates else missing, css="overview-chart-panel")
    queries, pages = _usable(blocks.get("queries")), _usable(blocks.get("pages"))
    lists = ("<div class='web-installer-grid web-visits-gsc-lists'>"
             + _gsc_card("queries", "Top queries", _gsc_queries(queries, totals) if queries else missing)
             + _gsc_card("pages", "Top pages", _gsc_pages(pages) if pages is not None else missing) + "</div>")
    fetched = [block["fetchedAt"] for block in blocks.values() if block.get("fetchedAt")]
    footer = (f"Updated {_timestamp_markup(datetime.fromtimestamp(min(fetched), timezone.utc))}" if fetched else "")
    if link:
        footer += (" · " if footer else "") + link.removeprefix("<p class='web-installer-tests muted-value'>").removesuffix("</p>")
    return section(kpis + trend + lists + (f"<p class='web-installer-tests muted-value'>{footer}</p>" if footer else ""), marks)


def _kpi_panel(body: str) -> str:
    return f"<section class='admin-card {_HEAD}' id='web-visits-gsc-kpis' aria-label='Google Search totals'>{body}</section>"


def _gsc_loading(period: str = GSC_DEFAULT_PERIOD) -> str:
    skeleton = ("<div class='web-visits-skeleton' aria-hidden='true'><span></span><span></span><span></span></div>"
                "<span class='sr-only'>Loading…</span>")
    return _gsc_section(_kpi_panel(skeleton) + _gsc_card("trend", "Trend", skeleton, css="overview-chart-panel")
                        + "<div class='web-installer-grid web-visits-gsc-lists'>" + _gsc_card("queries", "Top queries", skeleton)
                        + _gsc_card("pages", "Top pages", skeleton) + "</div>", period=period, loading=True)


def _gsc_script() -> str:
    """Reads the Google Search block for its own period (default Last 30
    days) and puts it in place of the loading one; a failed read shows
    Unavailable. Its picker reloads only this block. A new Admin period
    replaces the page content: the block is put back as it was, unread."""
    return r"""(() => {
      let request = 0;
      let period = '%(default)s';
      let markup = null;
      const place = (html) => {
        const slot = document.querySelector('#web-visits-gsc');
        if (!slot) return;
        const next = document.createElement('template');
        next.innerHTML = html;
        const select = next.content.querySelector('#gsc-period');
        if (select) select.value = period;
        slot.replaceWith(next.content);
        window.TerentoAdminTime?.render();
      };
      const load = async () => {
        const slot = document.querySelector('#web-visits-gsc');
        const failed = document.querySelector('#gsc-failed');
        if (!slot || !failed) return;
        const number = ++request;
        slot.setAttribute('aria-busy', 'true');
        const url = new URL('/admin/api/gsc', window.location.origin);
        url.searchParams.set('period', period);
        let next = null;
        try {
          const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
          if (response.ok) next = (await response.json()).html;
        } catch (error) { next = null; }
        if (number !== request) return;
        markup = typeof next === 'string' ? next : null;
        place(markup ?? failed.innerHTML);
      };
      document.addEventListener('change', (event) => {
        if (event.target?.id !== 'gsc-period' || event.target.value === period) return;
        period = event.target.value;
        load();
      });
      window.addEventListener('terento-admin-content-changed', () => {
        const slot = document.querySelector('#web-visits-gsc');
        if (!slot || slot.getAttribute('aria-busy') !== 'true') return;
        if (markup !== null) place(markup);
        else load();
      });
      load();
    })();""" % {"default": GSC_DEFAULT_PERIOD}

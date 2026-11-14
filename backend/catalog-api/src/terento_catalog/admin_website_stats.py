"""Admin Website stats page (docs/admin-behavior-contract.md, "Website stats").

Umami's terento.app numbers: a separate population from app and web installer
statistics. The page renders at once with every block loading; its script then
reads ``/admin/api/umami`` for the selected period, which answers with the
blocks rendered here, so the Umami key never reaches the browser.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from .admin import (
    _ADMIN_NONCE_PLACEHOLDER,
    _admin_header,
    _admin_icon,
    _empty_state,
    _layout,
    _metric_row,
    _metric_tile,
    _overview_period_script,
    _section_card,
    _status_pill,
    _timestamp_markup,
)
from .admin_web_installer import _duration
from .statistics_periods import ADMIN_PERIOD_LABELS, ADMIN_PERIODS

TITLES = {
    "visitors": "Visitors", "downloads": "Downloads", "referrers": "Referrers",
    "entries": "Entry pages", "vitals": "Web Vitals", "errors": "Errors",
}
PREVIOUS = {"today": "previous period", "24h": "previous 24 h", "7d": "previous 7 days", "30d": "previous 30 days"}
VITALS_MIN_SAMPLES = 20
# p75 limits (good, needs improvement); above the second is Poor.
VITALS = (
    ("lcp", "LCP · p75", (2500, 4000)),
    ("inp", "INP · p75", (200, 500)),
    ("cls", "CLS · p75", (0.1, 0.25)),
)
UNAVAILABLE = "Statistics unavailable."


def _card_id(name: str) -> str:
    return f"website-stats-{name}"


def _ratio(part: float | None, whole: float | None) -> float | None:
    return None if part is None or not whole else part / whole


def _rate(part: float | None, whole: float | None) -> float | None:
    ratio = _ratio(part, whole)
    return None if ratio is None else round(ratio * 100, 1)


def _delta(current: float | None, previous: float | None, period: str, kind: str = "count") -> str:
    """Change against the previous period of the same length, as text with an
    arrow (never colour alone); rates change in percentage points."""
    if period not in PREVIOUS or current is None or previous is None:
        return ""
    against = PREVIOUS[period]
    change = current - previous
    if kind == "rate":
        change = round(change, 1)
        amount = f"{abs(change):.1f}".removesuffix(".0") + " pp"
    elif kind == "duration":
        change = round(change)
        amount = _duration(abs(change))
    else:
        change = round(change)
        amount = f"{abs(change):,}"
    if change == 0:
        arrow, text = "=", f"Same as {against}"
    else:
        arrow, text = ("▲", "+") if change > 0 else ("▼", "−")
        text = f"{text}{amount} vs {against}"
    return f"<span class='funnel-delta'><span aria-hidden='true'>{arrow}</span> {html.escape(text)}</span>"


def _stale(block: dict[str, Any]) -> str:
    """Header marks of a block that shows its last good result."""
    if block.get("state") != "stale":
        return ""
    fetched = datetime.fromtimestamp(block["fetchedAt"], timezone.utc)
    return (_status_pill("unknown", "Statistics unavailable")
            + f"<span class='admin-metric-secondary'>Last result {_timestamp_markup(fetched)}</span>")


def _card(name: str, block: dict[str, Any], body: Any, css: str = "") -> str:
    if block.get("state") == "hidden":
        return ""
    if block.get("state") not in ("ok", "stale") or block.get("data") is None:
        return _section_card(TITLES[name], _empty_state("unavailable", UNAVAILABLE), card_id=_card_id(name), css=css)
    return _section_card(TITLES[name], body(block["data"]), card_id=_card_id(name), css=css, totals=_stale(block))


def _ranking(caption: str, label: str, rows: list[dict[str, Any]], empty: str) -> str:
    if not rows:
        return _empty_state("empty", empty)
    body = "".join(
        f"<tr><td>{html.escape(row['name'] or '—')}</td><td class='column-number'>{row['visitors']:,}</td></tr>"
        for row in rows)
    return (
        "<div class='table-wrap'><table class='admin-table popular-maps-table' data-own-mobile-layout>"
        f"<caption class='sr-only'>{html.escape(caption)}</caption><thead><tr><th scope='col'>{html.escape(label)}</th>"
        f"<th scope='col' class='column-number'>Visitors</th></tr></thead><tbody>{body}</tbody></table></div>"
    )


def _visitors(data: dict[str, Any], period: str) -> str:
    now, before = data.get("current") or {}, data.get("previous") or {}
    bounce = lambda totals: _rate(totals.get("bounces"), totals.get("visits"))
    duration = lambda totals: None if _ratio(totals.get("totaltime"), totals.get("visits")) is None else round(
        totals["totaltime"] / totals["visits"])
    tiles = [
        _metric_tile(label, now.get(key), secondary=_delta(now.get(key), before.get(key), period))
        for label, key in (("Visitors", "visitors"), ("Visits", "visits"), ("Views", "pageviews"))
    ]
    tiles.append(_metric_tile("Bounce rate", bounce(now), fmt="rate",
                              secondary=_delta(bounce(now), bounce(before), period, "rate")))
    seconds = duration(now)
    tiles.append(_metric_tile("Visit duration", _duration(seconds) if seconds is not None else None, fmt="text",
                              secondary=_delta(seconds, duration(before), period, "duration")))
    return _metric_row(tiles, label="Visitors")


def _downloads(data: dict[str, Any], visitors: dict[str, Any] | None, period: str) -> str:
    now, before = data.get("current") or {}, data.get("previous") or {}
    site = (visitors or {}).get("data") or {} if (visitors or {}).get("state") in ("ok", "stale") else {}
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
    if key == "lcp":
        return f"{value / 1000:.2f} s"
    if key == "inp":
        return f"{round(value):,} ms"
    return f"{value:.3f}".rstrip("0").rstrip(".") if value else "0"


def _rating(value: float, limits: tuple[float, float]) -> str:
    if value <= limits[0]:
        return _status_pill("success", "Good")
    if value <= limits[1]:
        return _status_pill("warning", "Needs improvement")
    return _status_pill("danger", "Poor")


def _vitals(data: dict[str, Any]) -> str:
    count = data.get("count")
    enough = count is not None and count >= VITALS_MIN_SAMPLES
    tiles = []
    for key, label, limits in VITALS:
        value = data.get(key)
        if enough and value is not None:
            tiles.append(_metric_tile(label, _vital_value(key, value), fmt="text", secondary=_rating(value, limits)))
        else:
            tiles.append(_metric_tile(label, None, state="unknown", secondary=_status_pill("unknown", "Too little data")))
    tiles.append(_metric_tile("Samples", count))
    return _metric_row(tiles, label="Web Vitals")


def _errors(data: dict[str, Any]) -> str:
    tiles = _metric_row([
        _metric_tile("Errors", data.get("total"), failure=True),
        _metric_tile("Issues", data.get("issues")),
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


def website_stats_blocks(snapshot: dict[str, Any] | None, *, dashboard_url: str | None) -> str:
    """The page's blocks, in order, for one snapshot (None: Umami is not configured)."""
    if not snapshot:
        return _section_card("Website stats", _empty_state("unavailable", UNAVAILABLE), card_id="website-stats-unavailable")
    period, blocks = snapshot["period"], snapshot["blocks"]
    kpi = "admin-kpi-panel web-installer-server"
    cards = [
        _card("visitors", blocks["visitors"], lambda data: _visitors(data, period), css=kpi),
        _card("downloads", blocks["downloads"], lambda data: _downloads(data, blocks["visitors"], period), css=kpi),
    ]
    lists = "".join(part for part in (
        _card("referrers", blocks["referrers"], lambda rows: _ranking("Top referrers", "Source", rows, "No referrers in this period."),
              css="map-statistics-popularity"),
        _card("entries", blocks["entries"], lambda rows: _ranking("Top entry pages", "Page", rows, "No visits in this period."),
              css="map-statistics-popularity"),
    ) if part)
    if lists:
        cards.append(f"<div class='web-installer-grid'>{lists}</div>")
    cards.append(_card("vitals", blocks["vitals"], _vitals, css=kpi))
    cards.append(_card("errors", blocks["errors"], _errors, css=kpi))
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
    """What the page shows until the stats arrive: every block, loading."""
    loading = lambda name, css="admin-kpi-panel web-installer-server": _section_card(
        TITLES[name], _empty_state("empty", "Loading…"), card_id=_card_id(name), css=css,
        extra_attributes=" data-website-stats-block aria-busy='true'")
    return (loading("visitors") + loading("downloads")
            + "<div class='web-installer-grid' data-website-stats-block>" + loading("referrers", "map-statistics-popularity")
            + loading("entries", "map-statistics-popularity") + "</div>" + loading("vitals") + loading("errors"))


def _website_stats_script() -> str:
    """Reads the blocks for the shown period and puts them in place of the
    loading ones; a failed read shows Unavailable."""
    return r"""(() => {
      let request = 0;
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
        main.querySelectorAll(':scope > [data-website-stats-block]').forEach((node) => node.remove());
        [...next.content.children].forEach((node) => node.setAttribute('data-website-stats-block', ''));
        failed.before(next.content);
        main.removeAttribute('aria-busy');
        window.TerentoAdminTime?.render();
      };
      window.addEventListener('terento-admin-content-changed', load);
      load();
    })();"""


def website_stats_page(user: dict[str, Any], csrf_token: str, *, period: str, time_zone: str = "UTC") -> bytes:
    if period not in ADMIN_PERIODS:
        period = "7d"
    options = "".join(
        f"<option value='{value}'{' selected' if value == period else ''}>{ADMIN_PERIOD_LABELS[value]}</option>"
        for value in ADMIN_PERIODS
    )
    failed = website_stats_blocks(None, dashboard_url=None)
    content = f"""
      {_admin_header(user, csrf_token, active='website-stats')}
      <main class='dashboard overview-page web-installer-page website-stats-page' id='main-content' data-admin-no-titles>
        <div class='heading-row overview-heading'><div><h1>Website stats</h1></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin/website-stats' data-time-zone='{html.escape(time_zone, quote=True)}'><span class='web-installer-source'>{_admin_icon('source-web')}Umami</span><label><span class='sr-only'>Time period</span><select id='overview-period' data-admin-dropdown name='period'>{options}</select></label></form></div>
        {_loading_blocks()}
        <template id='website-stats-failed'>{failed}</template>
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_overview_period_script()}{_website_stats_script()}</script>
    """
    return _layout("Website stats", content, sections={"websiteStats": period})

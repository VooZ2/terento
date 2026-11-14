"""Admin Web visits page (docs/admin-behavior-contract.md, "Web visits").

Umami's terento.app numbers: a separate population from app and web installer
statistics. The page renders at once with every block loading; its script then
reads ``/admin/api/umami`` for the Admin period, which answers with the blocks
rendered here, so the Umami key never reaches the browser.
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
from .admin_referrer_icons import FONT_AWESOME_BRANDS, SIMPLE_ICONS
from .admin_web_installer import _duration
from .statistics_periods import ADMIN_PERIOD_LABELS, ADMIN_PERIODS
from .umami_stats import CLEAN_VIEWS_SINCE

TITLES = {
    "visitors": "Visitors", "downloads": "Downloads", "referrers": "Referrers",
    "entries": "Entry pages", "countries": "Countries", "vitals": "Web Vitals", "errors": "Errors",
}
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
VIEWS_NOTE = "Before 2026-11-13 includes old map views"

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
           better: str = "up", plain: bool = False, note: str = "") -> str:
    """Change against the previous period of the same length: arrow, sign and
    text, coloured by meaning (green better, red worse, grey same or without a
    base). Rates change in percentage points."""
    note_markup = f"<span class='web-visits-note'>{html.escape(note)}</span>" if note else ""
    if period not in PREVIOUS or current is None or previous is None:
        return note_markup
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
        arrow, text, trend = "=", f"Same as {against}", "same"
    else:
        arrow, sign = ("▲", "+") if change > 0 else ("▼", "−")
        text = f"{sign}{amount} vs {against}"
        trend = "neutral" if plain or not previous else (
            "better" if (change > 0) == (better == "up") else "worse")
    return (f"<span class='funnel-delta' data-trend='{trend}'><span aria-hidden='true'>{arrow}</span> "
            f"{html.escape(text)}</span>{note_markup}")


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


def _usable(block: dict[str, Any] | None) -> Any:
    return (block or {}).get("data") if (block or {}).get("state") in ("ok", "stale") else None


def _ranking(caption: str, label: str, rows: list[tuple[str, int, str]], empty: str) -> str:
    """A ranking table; each row is (cell markup, visitors, row class)."""
    if not rows:
        return _empty_state("empty", empty)
    body = "".join(
        f"<tr{f' class={chr(39)}{css}{chr(39)}' if css else ''}><td>{cell}</td>"
        f"<td class='column-number'>{count:,}</td></tr>"
        for cell, count, css in rows)
    return (
        "<div class='table-wrap'><table class='admin-table popular-maps-table' data-own-mobile-layout>"
        f"<caption class='sr-only'>{html.escape(caption)}</caption><thead><tr><th scope='col'>{html.escape(label)}</th>"
        f"<th scope='col' class='column-number'>Visitors</th></tr></thead><tbody>{body}</tbody></table></div>"
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


def _countries(rows: list[dict[str, Any]]) -> str:
    """Countries by visitors; the browser names each code in English."""
    cells = []
    for row in rows:
        code = row["name"]
        cell = (f"<span class='web-visits-source'><span class='web-visits-flag' aria-hidden='true'>{_flag(code)}</span>"
                f"<span data-region-name='{code}'>{code}</span></span>") if code else "Unknown"
        cells.append((cell, row["visitors"], ""))
    return _ranking("Top countries", "Country", cells, "No visits in this period.")


def _visitors(data: dict[str, Any], period: str, views_note: str) -> str:
    now, before = data.get("current") or {}, data.get("previous") or {}
    bounce = lambda totals: _rate(totals.get("bounces"), totals.get("visits"))
    duration = lambda totals: None if _ratio(totals.get("totaltime"), totals.get("visits")) is None else round(
        totals["totaltime"] / totals["visits"])
    tiles = [
        _metric_tile("Visitors", now.get("visitors"), secondary=_delta(now.get("visitors"), before.get("visitors"), period)),
        _metric_tile("Visits", now.get("visits"), secondary=_delta(now.get("visits"), before.get("visits"), period)),
        _metric_tile("Views", now.get("pageviews"), secondary=_delta(
            now.get("pageviews"), before.get("pageviews"), period, plain=bool(views_note), note=views_note)),
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


def _views_note(snapshot: dict[str, Any]) -> str:
    """The Views note while the compared span reaches before the old map
    views stopped (owner request 2026-11-14)."""
    since = snapshot.get("previousStartAt") if snapshot["period"] != "all" else snapshot.get("startAt")
    return VIEWS_NOTE if since is not None and since < CLEAN_VIEWS_SINCE.timestamp() * 1000 else ""


_KPI = "admin-kpi-panel web-installer-server"
_LIST = "map-statistics-popularity"


def website_stats_blocks(snapshot: dict[str, Any] | None, *, dashboard_url: str | None) -> str:
    """The page's blocks, in order, for one snapshot (None: Umami is not configured)."""
    if not snapshot:
        return _section_card("Web visits", _empty_state("unavailable", UNAVAILABLE), card_id="web-visits-unavailable")
    period, blocks = snapshot["period"], snapshot["blocks"]
    visitors = _usable(blocks["visitors"])
    cards = [
        _card("visitors", blocks["visitors"], lambda data: _visitors(data, period, _views_note(snapshot)), css=_KPI),
        _card("downloads", blocks["downloads"], lambda data: _downloads(data, visitors, period), css=_KPI),
    ]
    lists = "".join(part for part in (
        _card("referrers", blocks["referrers"], lambda data: _referrers(data, visitors), css=_LIST),
        _card("entries", blocks["entries"], _entries, css=_LIST),
        _card("countries", blocks["countries"], _countries, css=_LIST),
    ) if part)
    if lists:
        cards.append(f"<div class='web-installer-grid web-visits-lists'>{lists}</div>")
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
    return (loading("visitors") + loading("downloads")
            + "<div class='web-installer-grid web-visits-lists' data-website-stats-block>" + loading("referrers", _LIST)
            + loading("entries", _LIST) + loading("countries", _LIST) + "</div>" + loading("vitals") + loading("errors"))


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
      };
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
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_overview_period_script()}{_website_stats_script()}</script>
    """
    return _layout("Web visits", content, sections={"webVisits": period})

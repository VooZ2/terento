"""Admin Web visits page (docs/admin-behavior-contract.md, "Web visits").

Umami's terento.app numbers: a separate population from app and web installer
statistics. The page renders at once with every block loading; its script then
reads ``/admin/api/umami`` for the Admin period, which answers with the blocks
rendered here, so the Umami key never reaches the browser. The Google Search
block loads the same way from ``/admin/api/gsc`` (Search Console, gsc_stats).
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .admin import (
    _ADMIN_NONCE_PLACEHOLDER,
    _admin_header,
    _admin_icon,
    _chart_axis_labels,
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


def _views_mixed(snapshot: dict[str, Any]) -> bool:
    """Whether the compared span reaches before the old map views stopped;
    the Views change is then grey, without a note (owner request 2026-11-14)."""
    since = snapshot.get("previousStartAt") if snapshot["period"] != "all" else snapshot.get("startAt")
    return since is not None and since < CLEAN_VIEWS_SINCE.timestamp() * 1000


_KPI = "admin-kpi-panel web-installer-server"
_HEAD = "admin-kpi-panel web-visits-kpis"
_LIST = "map-statistics-popularity"


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
    skeleton = ("<div class='web-visits-skeleton' aria-hidden='true'><span></span><span></span><span></span></div>"
                "<span class='sr-only'>Loading…</span>")
    headline = lambda name: _headline(name, skeleton, " aria-busy='true'")
    return ("<div class='web-installer-grid web-visits-headline' data-website-stats-block>" + headline("visitors")
            + headline("downloads") + "</div>"
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
    height, left, right, top, gap, bottom = 236, 42, 12, 22, 30, 28
    panel = (height - top - gap - bottom) / 2
    plot_width = width - left - right
    count = len(buckets)
    xs = [left + (plot_width * index / (count - 1) if count > 1 else plot_width / 2) for index in range(count)]
    prelim = next((index for index, bucket in enumerate(buckets) if bucket["preliminary"]), None)
    parts: list[str] = []
    marks: list[list[tuple[float, float]]] = []
    for row, (metric, label) in enumerate((("clicks", "Clicks"), ("impressions", "Impressions"))):
        panel_top = top + row * (panel + gap)
        base = panel_top + panel
        step = _nice_tick_step(max(bucket[metric] for bucket in buckets))
        scale = step * 4
        for amount in (0, step * 2, scale):
            y = base - panel * amount / scale
            parts.append(f"<line class='overview-chart-grid' x1='{left}' x2='{width - right}' y1='{y:.1f}' y2='{y:.1f}'/>"
                         f"<text class='overview-chart-axis-label' x='{left - 8}' y='{y + 4:.1f}' text-anchor='end'>"
                         f"{_compact(amount)}</text>")
        parts.append(f"<text class='gsc-chart-name' x='{left}' y='{panel_top - 8:.1f}'>{label}</text>")
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
        dots = "".join(f"<circle class='gsc-chart-focus' cx='{x:.1f}' cy='{series[index][1]:.1f}' r='3.5'/>" for series in marks)
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

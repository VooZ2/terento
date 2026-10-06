"""Shared Admin presentation kit: tokens, focus, pills, tiles, cards and charts."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from terento_catalog.admin import (
    ADMIN_GLOSSARY,
    ADMIN_STYLES,
    _FA_ICONS,
    _PILL_ICONS,
    _admin_icon,
    _empty_state,
    _metric_tile,
    _scope_chip,
    _section_card,
    _status_pill,
    glossary_page,
)
from terento_catalog.admin_brand_tokens_generated import ADMIN_BRAND_TOKENS_CSS


ROOT = Path(__file__).resolve().parents[3]
TOKENS = json.loads((ROOT / "brand" / "DESIGN_TOKENS.json").read_text(encoding="utf-8"))


def _luminance(value: str) -> float:
    channels = [int(value[offset:offset + 2], 16) / 255 for offset in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    a, b = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _token_variable(name: str) -> str:
    match = re.search(rf"--{re.escape(name)}:([^;]+);", ADMIN_BRAND_TOKENS_CSS)
    assert match, f"missing generated --{name}"
    return match.group(1)


class AdminTokenAndFocusTests(unittest.TestCase):
    def test_focus_ring_uses_the_canonical_token_and_meets_three_to_one(self):
        focus = TOKENS["color"]["light"]["focusRing"]["$value"]
        self.assertEqual(_token_variable("admin-focus-color"), focus)
        self.assertEqual(_token_variable("admin-focus-ring"), "3px solid var(--admin-focus-color)")
        for surface in (TOKENS["color"]["light"]["surfacePrimary"]["$value"],
                        TOKENS["color"]["brand"]["offWhite"]["$value"]):
            self.assertGreaterEqual(_contrast(focus, surface), 3.0)

    def test_focus_ring_shorthand_is_never_nested_in_another_outline(self):
        # ``outline:3px solid var(--admin-focus-ring)`` is invalid because the
        # variable already holds a full shorthand; it used to drop the ring.
        self.assertNotRegex(ADMIN_STYLES, r"outline:\s*\d+px\s+solid\s+var\(--admin-focus-ring\)")
        self.assertIn(".admin-disclosure>summary:focus-visible{outline:var(--admin-focus-ring)", ADMIN_STYLES)
        self.assertNotIn("color-mix(in srgb,var(--sky) 58%,white)", ADMIN_STYLES)

    def test_admin_css_uses_tokens_instead_of_raw_colours(self):
        self.assertNotRegex(ADMIN_STYLES, r"rgba\(")
        self.assertNotRegex(ADMIN_STYLES, r"hsl\(")
        self.assertNotRegex(ADMIN_STYLES, r"[,(]white\)")
        for name in ("stone-dark", "lichen-dark", "status-warning-text", "radius-card", "radius-control"):
            _token_variable(name)

    def test_chart_mark_tokens_meet_three_to_one_on_white(self):
        white = TOKENS["color"]["light"]["surfacePrimary"]["$value"]
        functional = TOKENS["color"]["functional"]
        for value in (functional["interactivePrimary"]["$value"], functional["lichenDark"]["$value"],
                      functional["stoneDark"]["$value"],
                      TOKENS["semantic"]["admin"]["light"]["destructiveText"]["$value"]):
            self.assertGreaterEqual(_contrast(value, white), 3.0, value)
        # Warm Stone itself is below 3:1, so update marks are filled Stone Dark,
        # solid and without an outline.
        self.assertLess(_contrast(TOKENS["color"]["brand"]["stone"]["$value"], white), 3.0)
        self.assertIn(".overview-chart-update{fill:var(--stone-dark);background:var(--stone-dark)}", ADMIN_STYLES)
        self.assertNotIn("rect.overview-chart-update{stroke", ADMIN_STYLES)



class AdminIconTests(unittest.TestCase):
    """Owner decision 2026-10-06: Admin icons are Font Awesome Free, never hand-drawn."""

    def test_icons_are_filled_font_awesome_paths(self):
        for name in set(_PILL_ICONS.values()) | {"arrow-right", "arrow-left", "external", "close", "download", "message"}:
            icon = _admin_icon(name)
            self.assertIn("<path fill='currentColor' d='M", icon, name)
            self.assertNotIn("stroke", icon)
        self.assertEqual(_admin_icon("not-an-icon"), "")
        for view_box, path in _FA_ICONS.values():
            self.assertRegex(view_box, r"^0 0 \d+ 512$")
            self.assertRegex(path, r"^[MmLlHhVvCcSsQqTtAaZz0-9.,\- ]+$")

    def test_css_draws_no_glyph_or_border_icons(self):
        self.assertNotRegex(ADMIN_STYLES, r"content:\s*['\"][⌄›→↗×✓]")
        self.assertNotIn("border-width:0 2px 2px 0", ADMIN_STYLES)  # old drawn chevron
        self.assertIn("--fa-chevron-right:url(\"data:image/svg+xml,", ADMIN_STYLES)
        self.assertNotIn("stroke-linecap:round", ADMIN_STYLES.split(".admin-icon{", 1)[1].split("}", 1)[0])


class AdminChartGeometryTests(unittest.TestCase):
    """Minimum segment rule and x-axis label density (review 2026-10-06)."""

    def test_tiny_segment_gets_the_minimum_while_the_bar_keeps_its_true_height(self):
        from terento_catalog.admin import _CHART_MIN_SEGMENT, _overview_stacked_segments
        segments = _overview_stacked_segments((100, 0, 1), 50, 20, 220, 200, 101)
        self.assertNotIn(1, segments)  # a zero segment is never drawn
        self.assertAlmostEqual(segments[2][3], _CHART_MIN_SEGMENT)
        self.assertAlmostEqual(sum(item[3] for item in segments.values()), 200 * 101 / 101)
        # Segments stay contiguous from the baseline.
        self.assertAlmostEqual(segments[0][2] + segments[0][3], 220)
        self.assertAlmostEqual(segments[2][2] + segments[2][3], segments[0][2])

    def test_bar_shorter_than_the_floor_grows_only_to_the_floor(self):
        from terento_catalog.admin import _overview_stacked_segments
        segments = _overview_stacked_segments((1, 1), 50, 20, 220, 200, 1000, minimum=4)
        self.assertEqual([round(item[3], 2) for item in segments.values()], [4.0, 4.0])

    def test_proportions_are_untouched_when_every_segment_is_visible(self):
        from terento_catalog.admin import _overview_stacked_segments
        segments = _overview_stacked_segments((30, 10), 50, 20, 220, 200, 40)
        self.assertAlmostEqual(segments[0][3], 150)
        self.assertAlmostEqual(segments[1][3], 50)

    def _labels(self, body: str, chart: str) -> list[tuple[float, str, str]]:
        svg = body.split(f"overview-trend-{chart}'", 1)[1].split("</svg>", 1)[0]
        return [(float(x), anchor, text) for x, anchor, text in re.findall(
            r"<text x='([0-9.]+)' y='\d+' text-anchor='(\w+)'[^>]*>([^<]+)</text>", svg)]

    def _assert_no_overlap(self, labels, font_size, width):
        extents = []
        for x, anchor, text in labels:
            w = len(text) * font_size * 0.6
            start = x - w / 2 if anchor == "middle" else x if anchor == "start" else x - w
            extents.append((start, start + w))
        for (_, end), (start, _) in zip(extents, extents[1:]):
            self.assertLessEqual(end, start)
        self.assertGreaterEqual(extents[0][0], 0)
        self.assertLessEqual(extents[-1][1], width)

    def test_axis_labels_every_bucket_when_they_fit_else_every_second(self):
        from terento_catalog.admin import _overview_trend_chart
        daily = [{"bucket": f"2026-09-{day:02d}T00:00:00Z", "success_count": 1} for day in range(18, 25)]
        body = _overview_trend_chart(daily, "day")
        desktop = self._labels(body, "desktop")
        self.assertEqual([text for _, _, text in desktop], [f"{day} Sep" for day in range(18, 25)])
        self._assert_no_overlap(desktop, 11, 720)
        mobile = self._labels(body, "mobile")
        self.assertEqual([text for _, _, text in mobile], ["18 Sep", "20 Sep", "22 Sep", "24 Sep"])
        self._assert_no_overlap(mobile, 13, 360)
        hourly = [{"bucket": f"2026-09-18T{hour:02d}:00:00Z", "success_count": 1} for hour in range(24)]
        desktop = self._labels(_overview_trend_chart(hourly, "hour"), "desktop")
        self.assertEqual(len(desktop), 12)
        self.assertEqual(desktop[-1][2], "23:00")  # the most recent bucket is labelled
        self._assert_no_overlap(desktop, 11, 720)

    def test_app_download_axis_uses_the_same_rule(self):
        from terento_catalog.admin import _overview_downloads_chart
        trend = [{"bucket": f"2026-09-{day:02d}T00:00:00Z", "observed_at": f"2026-09-{day:02d}T18:00:00Z",
                  "dmg_count": 3, "zip_count": 1} for day in range(18, 25)]
        body = _overview_downloads_chart({"hasData": True, "bucket": "day", "trend": trend}, period="7d")
        desktop = self._labels(body, "desktop")
        self.assertEqual(len(desktop), 7)
        self._assert_no_overlap(desktop, 11, 720)
        self._assert_no_overlap(self._labels(body, "mobile"), 13, 360)


class AdminChartValueStripTests(unittest.TestCase):
    """Tap/keyboard value strip: works without hover and is announced."""

    def test_every_bucket_carries_its_date_series_values_and_total(self):
        from terento_catalog.admin import _overview_trend_chart
        body = _overview_trend_chart([{
            "bucket": "2026-09-18T00:00:00Z", "success_count": 5, "custom_count": 1,
            "failed_count": 0, "map_update_success_count": 2, "map_update_failed_count": 1,
        }], "day")
        strip = body.split("<p class='overview-chart-values admin-legend'", 1)[1].split("</p>", 1)[0]
        self.assertIn("data-chart-values-strip aria-live='polite'", strip)
        self.assertEqual(strip.split(">", 1)[1], "")  # no hint text; hidden until a bucket is chosen
        self.assertIn(".overview-chart-values:empty{display:none}", ADMIN_STYLES)
        self.assertNotIn(".overview-chart-group rect{stroke:var(--surface)", ADMIN_STYLES)  # solid bars
        groups = re.findall(r"<g class='overview-chart-group' role='img' tabindex='0' data-chart-values='([^']+)'", body)
        self.assertEqual(len(groups), 2)  # desktop and compact chart, one strip
        import html as html_module
        payload = json.loads(html_module.unescape(groups[0]))
        self.assertEqual(payload["date"], "18 Sep")
        self.assertEqual(payload["total"], 9)
        self.assertEqual(payload["values"], [
            ["success", "Install successful", 5], ["custom", "Custom .img install", 1],
            ["failed", "Install failed", 0], ["update", "Update successful", 2],
            ["update-failed", "Update failed", 1],
        ])
        self.assertEqual(body.count("data-chart-values-strip"), 1)

    def test_app_download_buckets_keep_unknown_values_unknown(self):
        from terento_catalog.admin import _overview_downloads_chart
        body = _overview_downloads_chart({"hasData": True, "bucket": "day", "trend": [
            {"bucket": "2026-09-18T00:00:00Z", "observed_at": "2026-09-18T18:00:00Z", "dmg_count": 4, "zip_count": None},
        ]}, period="7d")
        import html as html_module
        payload = json.loads(html_module.unescape(re.search(r"data-chart-values='([^']+)'", body).group(1)))
        self.assertEqual(payload["values"], [["download-dmg", ".dmg", 4], ["download-zip", ".zip", None]])
        self.assertIsNone(payload["total"])
        self.assertIn("data-chart-values-strip aria-live='polite'", body)

    def test_value_strip_script_ships_on_every_admin_page_with_the_nonce(self):
        from terento_catalog.admin import _admin_chart_values_script, _layout
        script = _admin_chart_values_script()
        for event in ("'click'", "'focusin'", "'keydown'"):
            self.assertIn(event, script)
        self.assertNotIn("mouseover", script)
        self.assertNotIn("innerHTML", script)  # values are inserted as text
        self.assertIn("replaceChildren", script)
        page = _layout("Test", "<main id='main-content'></main>").decode()
        self.assertIn("data-chart-values-strip", script)
        self.assertRegex(page, r'<script nonce="[^"]+">[^<]*\(\(\) => \{[\s\S]*closest\(\'\.overview-chart-group\[data-chart-values\]\'\)')
        self.assertIn(".overview-trend-chart .overview-chart-group.is-selected rect{stroke:var(--graphite);stroke-width:2}", ADMIN_STYLES)


class AdminMapsMobileTests(unittest.TestCase):
    """Maps at ≤600 px: compact KPI row and collapsible long cards."""

    def test_section_card_can_start_collapsed_on_mobile_only(self):
        card = _section_card("Top maps", "<p>rows</p>", card_id="maps-by-provider", mobile_collapse=True)
        self.assertIn(" data-mobile-collapse>", card)
        self.assertIn("<button type='button' class='secondary-button admin-card-toggle' data-mobile-collapse-toggle "
                      "aria-expanded='true' aria-controls='maps-by-provider' hidden>Hide<span class='sr-only'> Top maps</span></button></header>", card)
        self.assertNotIn("data-mobile-collapse", _section_card("Top maps", "", card_id="plain"))
        self.assertIn("[data-mobile-collapse][data-mobile-collapsed]>:not(.admin-card-head){display:none}", ADMIN_STYLES)
        self.assertIn(".map-statistics-metrics>.admin-metric-row{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}", ADMIN_STYLES)
        mobile = ADMIN_STYLES.split("@media(max-width:600px){\n  .map-statistics-metrics>.admin-metric-row", 1)[1].split("\n}", 1)[0]
        self.assertIn("[data-mobile-collapse][data-mobile-collapsed]", mobile)

    def test_maps_page_marks_its_long_lower_cards_collapsible(self):
        from terento_catalog.admin import _admin_mobile_collapse_script, map_statistics_page
        rows = [{"provider_id": "opentopomap", "map_package_id": "lt", "region": "LT", "region_country": "LT",
                 "component_kind": "main", "event_type": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED",
                 "operation_count": 3, "event_count": 3, "last_occurred_at": "2026-09-18T09:39:00Z"}]
        body = map_statistics_page({"rows": rows}, [{"id": "opentopomap", "name": "OpenTopoMap"}],
                                   {"username": "operator"}, "csrf").decode()
        collapsible = re.findall(r"<section class='admin-card[^']*' id='([^']+)'[^>]* data-mobile-collapse>", body)
        self.assertEqual(collapsible, ["top-countries", "map-statistics-provider-table", "maps-by-provider"])
        self.assertNotIn("id='map-statistics-world-map-card' aria-labelledby='map-statistics-world-map-card-title' data-mobile-collapse", body)
        script = _admin_mobile_collapse_script()
        self.assertIn("matchMedia('(max-width: 600px)')", script)
        self.assertIn("'hashchange'", script)
        self.assertIn(script, body)


class AdminComponentKitTests(unittest.TestCase):
    def test_scope_chip_is_visible_text_for_every_scope(self):
        self.assertEqual(_scope_chip("7d"), "<span class='admin-scope-chip' data-scope='period'>Last 7 days</span>")
        self.assertIn(">All time<", _scope_chip("all"))
        self.assertIn("data-scope='now'", _scope_chip("now"))

    def test_status_pill_pairs_icon_with_text_and_never_hides_the_text(self):
        pill = _status_pill("danger", "Failed", value="FAILED")
        self.assertIn("admin-icon-x-circle", pill)
        self.assertIn("<span>Failed</span>", pill)
        self.assertNotIn("role='img'", pill)
        self.assertNotIn("aria-label", pill)
        for kind in ("success", "warning", "info", "progress", "neutral", "unknown"):
            self.assertIn("admin-icon", _status_pill(kind, "x"))

    def test_metric_tile_states_are_distinct(self):
        measured_zero = _metric_tile("Failed", 0, failure=True, scope="7d")
        self.assertIn("data-state='measured' data-tone='neutral'", measured_zero)
        self.assertIn(">0</strong>", measured_zero)
        self.assertIn(">Last 7 days<", measured_zero)
        positive = _metric_tile("Failed", 3, failure=True)
        self.assertIn("data-tone='danger'", positive)
        self.assertNotIn("admin-icon", positive)
        unknown = _metric_tile("Installs", None)
        self.assertIn("data-state='unknown'", unknown)
        self.assertIn("—<span class='sr-only'>Unknown</span>", unknown)
        unavailable = _metric_tile("Installs", 5, state="unavailable")
        self.assertIn("—<span class='sr-only'>Unavailable</span>", unavailable)
        self.assertIn("<span>Unavailable</span>", unavailable)
        self.assertNotIn(">5<", unavailable)
        partial = _metric_tile("Installs", 5, state="partial", hint="One provider failed.")
        self.assertIn("<span>Partial</span>", partial)
        self.assertIn("title='One provider failed.'", partial)
        rate = _metric_tile("Success rate", 97.94, fmt="rate")
        self.assertIn(">97.9%</strong>", rate)
        self.assertIn(">1,204<", _metric_tile("Downloads", 1204))

    def test_linked_tile_carries_scope_in_its_accessible_name(self):
        tile = _metric_tile("Open problems", 4, failure=True, scope="now", href="/admin/installations?state=open")
        self.assertIn("aria-label='Open problems, now: 4'", tile)
        self.assertIn("href='/admin/installations?state=open'", tile)

    def test_section_card_has_short_title_scope_and_one_action(self):
        card = _section_card("Countries", "<p>x</p>", card_id="countries", scope="30d",
                             action=("/admin/map-statistics", "View all"))
        self.assertIn("<h2 id='countries-title'>Countries</h2>", card)
        self.assertIn("aria-labelledby='countries-title'", card)
        self.assertEqual(card.count("admin-card-action"), 1)
        self.assertIn("Last 30 days", card)

    def test_empty_states_distinguish_measured_nothing_from_unavailable(self):
        self.assertIn("data-state='empty'", _empty_state("empty", "No installs in this period."))
        unavailable = _empty_state("unavailable", "Could not load this section.", action=("", "Retry"))
        self.assertIn("role='status'", unavailable)
        self.assertIn("<span>Unavailable</span>", unavailable)
        self.assertIn(">Retry</a>", unavailable)


class AdminGlossaryTests(unittest.TestCase):
    REQUIRED = (
        "Attempt", "Successful", "Failed", "Blocked before writing", "Open problem",
        "Provider download", "Installation report", "Map update", "Update report",
        "Terento app download", "Task",
    )

    def test_glossary_defines_every_contract_term_once_with_an_anchor(self):
        terms = [term for _, term, _ in ADMIN_GLOSSARY]
        for required in self.REQUIRED:
            self.assertIn(required, terms)
        self.assertTrue(any(term.startswith("Install (fresh install)") for term in terms))
        anchors = [anchor for anchor, _, _ in ADMIN_GLOSSARY]
        self.assertEqual(len(anchors), len(set(anchors)))
        for anchor in anchors:
            self.assertRegex(anchor, r"^[a-z0-9-]+$")

    def test_glossary_page_renders_inside_admin_chrome_and_links_resolve(self):
        body = glossary_page({"username": "operator"}, "csrf").decode()
        self.assertIn("<h1 id=\"glossary-title\">Glossary</h1>", body)
        self.assertIn('href="/admin/glossary"', body)
        for anchor, term, _ in ADMIN_GLOSSARY:
            self.assertIn(f"id='{anchor}'", body)


if __name__ == "__main__":
    unittest.main()

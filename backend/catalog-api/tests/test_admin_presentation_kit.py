"""Shared Admin presentation kit: tokens, focus, pills, tiles, cards and charts."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from terento_catalog.admin import (
    ADMIN_GLOSSARY,
    ADMIN_STYLES,
    _empty_state,
    _glossary_link,
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
        # Warm Stone itself is below 3:1, so update marks carry a stone-dark outline.
        self.assertLess(_contrast(TOKENS["color"]["brand"]["stone"]["$value"], white), 3.0)



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
        self.assertIn("admin-icon-x-circle", positive)
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
        link = _glossary_link("open-problem")
        self.assertIn("href='/admin/glossary#open-problem'", link)
        self.assertIn("aria-label='About Open problem'", link)
        self.assertEqual(_glossary_link("not-a-term"), "")


if __name__ == "__main__":
    unittest.main()

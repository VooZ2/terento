"""Shared Admin presentation kit: tokens, focus, pills, tiles, cards and charts."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from terento_catalog.admin import ADMIN_STYLES
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


if __name__ == "__main__":
    unittest.main()

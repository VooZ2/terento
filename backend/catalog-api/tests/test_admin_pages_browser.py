"""Every Admin page in a real browser (desktop and phone width).

admin_pages_browser.cjs serves the fixture pages from admin_presentation_preview
and checks that each one loads the versioned Admin stylesheet (HTTP 200, rules
applied), runs without script errors and fits the phone width. The screenshots
land in test-results/admin-pages so a CSS change can be compared before/after.

When ``CI=true`` Playwright is mandatory (TERENTO_PLAYWRIGHT_MODULE), like PGlite:
a missing browser fails the test instead of skipping it.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from admin_presentation_preview import create
from pglite_support import node_binary

TESTS = Path(__file__).resolve().parent
REPOSITORY = TESTS.parents[2]


class AdminPagesBrowserTests(unittest.TestCase):
    def test_every_admin_page_renders_with_its_stylesheet(self):
        module = os.environ.get("TERENTO_PLAYWRIGHT_MODULE", "")
        if not module or not Path(module).exists():
            message = "TERENTO_PLAYWRIGHT_MODULE is required for the Admin browser check"
            if os.environ.get("CI", "").strip().lower() == "true":
                self.fail(message + " (CI=true: the browser check must not be skipped)")
            self.skipTest(message)
        output = REPOSITORY / "test-results" / "admin-pages"
        with tempfile.TemporaryDirectory() as directory:
            create(Path(directory))
            result = subprocess.run(
                [node_binary(), str(TESTS / "admin_pages_browser.cjs"), module, directory, str(output)],
                capture_output=True, text=True, timeout=600,
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()

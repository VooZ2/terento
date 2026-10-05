"""Providers, provider detail and Health simplifications keep every capability."""

from __future__ import annotations

import unittest

from admin_test_utils import metric_value
from terento_catalog.admin import provider_detail_page, providers_page


def _package(index: int, *, reason: str = "Download unavailable", broken: bool = True) -> dict:
    return {
        "id": f"bbbike-region-{index}", "name": f"Region {index}", "release": "2026-09-30",
        "availability": "UNAVAILABLE" if broken else "AVAILABLE", "artifact_count": 1,
        "broken_artifact_count": 1 if broken else 0,
        "artifacts": [{
            "kind": "main", "validation_status": "FAILED" if broken else "VALIDATED",
            "source_url": f"https://download.bbbike.org/region-{index}.zip",
            "last_check": {"message": reason, "nextAction": "Recheck later.", "checkedAt": "2026-10-01T10:00:00Z"} if broken else {},
        }],
    }


class ProviderDetailTests(unittest.TestCase):
    def render(self, packages):
        return provider_detail_page(
            {"provider": {"id": "bbbike", "name": "BBBike", "status": "ACTIVE", "healthStatus": "DEGRADED",
                          "maps": packages, "affectedPackageCount": sum(p["broken_artifact_count"] for p in packages)}},
            [], [], {"username": "operator"}, "csrf",
        ).decode()

    def test_problems_are_grouped_by_reason_with_a_preview_of_five(self):
        packages = [_package(index) for index in range(8)] + [_package(8, reason="Source date missing")]
        packages.append(_package(9, broken=False))
        body = self.render(packages)
        problems = body.split("id='provider-problems-title'", 1)[1].split("id='provider-packages'", 1)[0]
        self.assertEqual(problems.count("class='provider-problem-group'"), 2)
        self.assertIn(">8 packages</span>", problems)
        self.assertIn(">Download unavailable</span>", problems)
        # Preview is capped at five rows per group, with a link to the full list.
        self.assertEqual(problems.count("<li class='provider-problem'>"), 6)
        self.assertIn("Show all 8 in Packages", problems)
        self.assertIn("data-show-problems", problems)
        # A single-package group rechecks that package; a larger group says what it does.
        self.assertIn("data-package-id='bbbike-region-8'>Recheck</button>", problems)
        self.assertIn(">Recheck affected</button>", problems)
        self.assertIn(">Recheck affected packages</button>", problems)
        self.assertIn("BBBike · Main map", problems)
        self.assertNotIn("Bbbike", body)
        self.assertNotIn("Installation availability", body)

    def test_packages_is_one_list_with_a_row_menu_and_problems_preselected(self):
        body = self.render([_package(0), _package(1, broken=False)])
        packages = body.split("id='provider-packages'", 1)[1]
        self.assertIn("<option value='broken' selected>Problems</option>", packages)
        self.assertEqual(packages.count("class='provider-row-menu'"), 2)
        self.assertIn("aria-label='Actions for ", packages)
        self.assertIn("data-provider-action='downloads'", packages)
        self.assertIn(">Disable downloads</button>", packages)
        self.assertIn("data-provider-action='rechecks'", packages)

    def test_summary_tiles_and_collapsed_history_sections(self):
        body = self.render([_package(0)])
        for label in ("Health", "Catalog", "Package problems", "Downloads"):
            self.assertIsNotNone(metric_value(body, label), label)
        self.assertEqual(metric_value(body, "Package problems"), "1")
        for summary in ("<summary>History ", "<summary>Releases</summary>", "<summary>Attribution</summary>",
                        "<summary>Original links</summary>", "<summary>View check details</summary>"):
            self.assertIn(summary, body)
        self.assertNotIn("<details class='admin-card admin-disclosure provider-technical-section' open", body)

    def test_no_problems_shows_an_empty_state(self):
        body = self.render([_package(0, broken=False)])
        self.assertIn("No known package problems.", body)
        self.assertNotIn(">Recheck affected packages</button>", body)


class ProvidersListTests(unittest.TestCase):
    def test_problems_column_counts_packages_and_keeps_unknown_distinct(self):
        body = providers_page([
            {"id": "a", "name": "A", "status": "ACTIVE", "health": "HEALTHY", "packageCount": 3,
             "affectedPackageCount": 0, "problematicSourceCount": 0, "latestRelease": "2026-09",
             "lastCollectionStatus": "SUCCEEDED", "lastCollectionSuccess": "2099-01-01T00:00:00Z"},
            {"id": "b", "name": "B", "status": "ACTIVE", "health": "DOWN", "packageCount": 3,
             "affectedPackageCount": 2, "problematicSourceCount": 1, "lastHealthError": "timeout"},
            {"id": "c", "name": "C", "status": "RETIRED", "health": "UNKNOWN", "packageCount": None,
             "affectedPackageCount": None, "problematicSourceCount": None},
        ], {"username": "operator"}, "csrf").decode()
        self.assertIn("2 packages · 1 source", body)
        self.assertIn("—<span class='sr-only'> Unknown</span>", body)
        self.assertEqual(metric_value(body, "Package problems"), "—")
        # Retired providers are not problems; the degraded active one is.
        self.assertEqual(metric_value(body, "Provider problems"), "1")
        self.assertIn("<span>Failed</span>", body)  # DOWN reads as Failed in one vocabulary


if __name__ == "__main__":
    unittest.main()

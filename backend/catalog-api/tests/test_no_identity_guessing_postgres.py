"""Diagnostic-only fresh results never acquire a guessed package or geography (audit M4)."""
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows


def totals(rows):
    result = {}
    for row in rows:
        result[row["event_type"]] = result.get(row["event_type"], 0) + int(row["operation_count"] or 0)
    return result


class NoPackageGuessTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.rows.package("freizeitkarte-deu", region="DEU", country="DE")

    def test_diagnostic_only_success_keeps_unknown_package_and_geography(self):
        self.rows.diagnostic(region="DEU")
        self.rows.diagnostic(region="DEU", phase_outcome="FAILED", failure_stage="write",
                             failure_code="INSTALL_FAILED_WRITE")
        rows = self.db.map_statistics({})
        self.assertEqual(totals(rows), {"INSTALL_SUCCEEDED": 1, "INSTALL_FAILED": 1})
        for row in rows:
            self.assertIsNone(row["map_package_id"])
            self.assertIsNone(row["map_package_name"])
            self.assertIsNone(row["canonical_region_id"])
            self.assertIsNone(row["region_country"])
            self.assertEqual(row["region"], "DEU")

    def test_catalog_changes_do_not_rewrite_history(self):
        self.rows.diagnostic(region="DEU")
        before = self.db.map_statistics({})
        self.rows.package("freizeitkarte-deu-alt", region="DEU", provider_region="deu-alt", country="DE")
        self.assertEqual(self.db.map_statistics({}), before)

    def test_map_event_identity_is_still_used(self):
        operation = self.rows.uuid()
        self.rows.diagnostic(operation_id=operation, region="DEU")
        self.rows.map_event(operation_id=operation, map_package_id="freizeitkarte-deu", region="DEU")
        rows = [row for row in self.db.map_statistics({}) if row["operation_count"]]
        self.assertEqual([(row["map_package_id"], row["region_country"]) for row in rows], [("freizeitkarte-deu", "DE")])


if __name__ == "__main__":
    unittest.main()

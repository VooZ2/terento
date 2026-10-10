"""Migration 076: fēnix 6 map-capable editions (owner decision 2026-10-10).

The shipped macOS resolver is exercised through the Python port in
test_installation_policy.py, against the policy built from the migrated
PostgreSQL catalog.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from pglite_support import PGliteTestCase
from terento_catalog.installation_policy import (
    build_installation_policy,
    installation_base_model,
    serialize_installation_policy,
)
from terento_catalog.migrate import _statements
from test_installation_policy import app_policy_valid, app_resolve, garmin

MIGRATION = (
    Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
    / "076_fenix_6_map_editions.sql"
)

# id -> base model the watch reports (after the shipped normalizer).
NEW_ROWS = {
    "garmin-fenix-6-pro": "fenix 6 pro",
    "garmin-fenix-6s-pro": "fenix 6s pro",
    "garmin-fenix-6x-pro": "fenix 6x pro",
    "garmin-fenix-6-pro-dual-power": "fenix 6 pro dual power",
    "garmin-fenix-6s-pro-dual-power": "fenix 6s pro dual power",
    "garmin-fenix-6x-pro-dual-power": "fenix 6x pro dual power",
    "garmin-fenix-6x-asia": "fenix 6x asia",
}

# Reported name -> the one approved row.
REPORTED_APPROVED = {
    "fēnix 6 Pro": "garmin-fenix-6-pro",
    "fēnix 6 Pro Solar": "garmin-fenix-6-pro",
    "fēnix 6S Pro": "garmin-fenix-6s-pro",
    "fēnix 6S Pro Solar": "garmin-fenix-6s-pro",
    "fēnix 6X Pro": "garmin-fenix-6x-pro",
    "fenix 6X Pro": "garmin-fenix-6x-pro",
    "fēnix 6X Pro Solar": "garmin-fenix-6x-pro",
    "fēnix 6 Pro Dual Power": "garmin-fenix-6-pro-dual-power",
    "fēnix 6S Pro Dual Power": "garmin-fenix-6s-pro-dual-power",
    "fēnix 6X Pro Dual Power": "garmin-fenix-6x-pro-dual-power",
    "fēnix 6X Asia": "garmin-fenix-6x-asia",
}


class MigrationSourceTests(unittest.TestCase):
    def code(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))

    def test_migration_is_additive_and_guarded(self):
        code = self.code()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "UPDATE ", "RENAME", "CREATE INDEX"):
            self.assertNotIn(forbidden, code.upper())
        self.assertIn("ON CONFLICT (id) DO NOTHING", code)
        ids = re.findall(r"^\s+\('(garmin-[a-z0-9-]+)', 'garmin-", code, flags=re.MULTILINE)
        self.assertEqual(sorted(ids), sorted(NEW_ROWS))
        self.assertEqual(len(ids), len(set(ids)))
        # Existing fēnix 6 rows are never touched, and standard editions are not added.
        for kept in ("garmin-fenix-6-47", "garmin-fenix-6s-42", "garmin-fenix-6x-51"):
            self.assertNotIn(kept, code)
        self.assertNotIn("'fenix 6 dual power'", code)
        self.assertNotIn("'fenix 6s dual power'", code)

    def test_model_labels_match_the_reported_base_models(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for device_id, base in NEW_ROWS.items():
            with self.subTest(device_id=device_id):
                match = re.search(r"\('" + re.escape(device_id) + r"', '[a-z0-9-]+', 'Garmin', '([^']+)'", sql)
                self.assertIsNotNone(match)
                self.assertEqual(installation_base_model(match.group(1)), base)

    def test_statements_split_cleanly(self):
        self.assertEqual(len(_statements(MIGRATION.read_text(encoding="utf-8"))), 1)


class MigratedCatalogTests(PGliteTestCase):
    def policy(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        return json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))

    def test_new_rows_are_map_capable_historical_rows_with_official_evidence(self):
        document = self.policy()
        self.assertTrue(app_policy_valid(document, strict=True))
        self.assertTrue(app_policy_valid(document, strict=False))
        by_id = {device["id"]: device for device in document["devices"]}
        for device_id, base in NEW_ROWS.items():
            with self.subTest(device_id=device_id):
                row = by_id[device_id]
                self.assertEqual(row["baseModel"], base)
                self.assertIs(row["active"], True)
                self.assertIs(row["mapCapable"], True)
                self.assertEqual(row["installationAuthorization"], "APPROVED")
        stored = self.sql("SELECT id, record_source, collector_managed, specification_evidence "
                          "FROM device_model WHERE id = ANY(%s)", (list(NEW_ROWS),))
        self.assertEqual(len(stored), len(NEW_ROWS))
        for row in stored:
            self.assertEqual((row["record_source"], row["collector_managed"]), ("HISTORICAL_REVIEWED", False))
            evidence = row["specification_evidence"]["map_capable"]
            self.assertIs(evidence["value"], True)
            self.assertTrue(re.match(r"https://(www\.garmin\.com|www8\.garmin\.com)/", evidence["source"]))
            self.assertTrue(evidence["field"])

    def test_shipped_resolver_approves_each_reported_name(self):
        document = self.policy()
        for reported, device_id in REPORTED_APPROVED.items():
            for strict in (True, False):
                with self.subTest(reported=reported, strict=strict):
                    self.assertEqual(app_resolve(document, garmin(reported), strict=strict),
                                     ("APPROVED", [device_id]))

    def test_existing_rows_and_standard_editions_are_unchanged(self):
        document = self.policy()
        self.assertEqual(app_resolve(document, garmin("fēnix 6X Sapphire")), ("APPROVED", ["garmin-fenix-6x-51"]))
        self.assertEqual(app_resolve(document, garmin("fēnix 6")), ("APPROVED", ["garmin-fenix-6-47"]))
        self.assertEqual(app_resolve(document, garmin("fēnix 6S")), ("APPROVED", ["garmin-fenix-6s-42"]))
        # Garmin publishes no map row for the standard Dual Power editions.
        self.assertEqual(app_resolve(document, garmin("fēnix 6 Dual Power")), ("PENDING", []))
        self.assertEqual(app_resolve(document, garmin("fēnix 6S Dual Power")), ("PENDING", []))


if __name__ == "__main__":
    unittest.main()

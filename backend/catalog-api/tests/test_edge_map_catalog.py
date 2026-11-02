"""Migration 090: Garmin Edge map catalog (owner test decision 2026-11-02).

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
    / "090_edge_map_catalog.sql"
)

# id -> base model the Edge reports (after the shipped normalizer).
NEW_ROWS = {
    "garmin-edge-540": "edge 540",
    "garmin-edge-840": "edge 840",
    "garmin-edge-1040": "edge 1040",
    "garmin-edge-1050": "edge 1050",
    "garmin-edge-550": "edge 550",
    "garmin-edge-850": "edge 850",
    "garmin-edge-1060": "edge 1060",
    "garmin-edge-explore-2": "edge explore 2",
}

# Reported name -> the one approved row. Solar editions share the base model.
REPORTED_APPROVED = {
    "Edge 540": "garmin-edge-540",
    "Edge® 540 Solar": "garmin-edge-540",
    "Edge 840": "garmin-edge-840",
    "Edge 840 Solar": "garmin-edge-840",
    "Edge 1040": "garmin-edge-1040",
    "Edge® 1040 Solar": "garmin-edge-1040",
    "Edge 1050": "garmin-edge-1050",
    "Edge 550": "garmin-edge-550",
    "Edge 850": "garmin-edge-850",
    "Edge 1060": "garmin-edge-1060",
    "Edge Explore 2": "garmin-edge-explore-2",
}

# Mass-storage generations and other Edge names stay absent, therefore PENDING.
REPORTED_PENDING = ("Edge 530", "Edge 830", "Edge 1030", "Edge 1030 Plus", "Edge 130 Plus",
                    "Edge Explore", "Edge", "Edge 10400")


class MigrationSourceTests(unittest.TestCase):
    def code(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))

    def test_migration_is_additive_and_guarded(self):
        code = self.code()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "UPDATE ", "RENAME", "CREATE INDEX"):
            self.assertNotIn(forbidden, code.upper())
        self.assertEqual(code.count("ON CONFLICT (id) DO NOTHING"), 2)
        ids = re.findall(r"^\s+\('(garmin-[a-z0-9-]+)', 'garmin-", code, flags=re.MULTILINE)
        self.assertEqual(sorted(ids), sorted(NEW_ROWS))
        self.assertEqual(len(ids), len(set(ids)))
        # No row names a Solar value: a reported Solar edition must stay a candidate.
        self.assertNotIn("solar", code.lower())
        # Catalog rows only: no public Compatibility review or publication is written.
        for table in ("compatibility_model_review", "public_statistics", "support_status = 'SUPPORTED'"):
            self.assertNotIn(table, code)

    def test_model_labels_match_the_reported_base_models(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for device_id, base in NEW_ROWS.items():
            with self.subTest(device_id=device_id):
                match = re.search(r"\('" + re.escape(device_id) + r"', 'garmin-edge', 'Garmin', '([^']+)'", sql)
                self.assertIsNotNone(match)
                self.assertEqual(installation_base_model(match.group(1)), base)

    def test_statements_split_cleanly(self):
        self.assertEqual(len(_statements(MIGRATION.read_text(encoding="utf-8"))), 2)


class MigratedCatalogTests(PGliteTestCase):
    def policy(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        return json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))

    def test_new_rows_are_map_capable_reviewed_rows_with_official_evidence(self):
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
                self.assertEqual((row["scope"], row["installationAuthorization"]), ("IN_SCOPE", "APPROVED"))
                self.assertIsNone(row["solar"])
        stored = self.sql("SELECT id, family_id, record_source, collector_managed, support_status, "
                          "specification_evidence FROM device_model WHERE id = ANY(%s)", (list(NEW_ROWS),))
        self.assertEqual(len(stored), len(NEW_ROWS))
        for row in stored:
            self.assertEqual((row["family_id"], row["record_source"], row["collector_managed"], row["support_status"]),
                             ("garmin-edge", "HISTORICAL_REVIEWED", False, "NOT_EVALUATED"))
            evidence = row["specification_evidence"]["map_capable"]
            self.assertIs(evidence["value"], True)
            self.assertRegex(evidence["source"], r"^https://www\.garmin\.com/en-US/p/\d+/$")
            self.assertEqual(evidence["field"], "ability to add maps")

    def test_shipped_resolver_approves_each_reported_name(self):
        document = self.policy()
        for reported, device_id in REPORTED_APPROVED.items():
            for strict in (True, False):
                with self.subTest(reported=reported, strict=strict):
                    self.assertEqual(app_resolve(document, garmin(reported), strict=strict),
                                     ("APPROVED", [device_id]))

    def test_other_edge_names_stay_pending(self):
        document = self.policy()
        for reported in REPORTED_PENDING:
            with self.subTest(reported=reported):
                self.assertEqual(app_resolve(document, garmin(reported)), ("PENDING", []))



if __name__ == "__main__":
    unittest.main()

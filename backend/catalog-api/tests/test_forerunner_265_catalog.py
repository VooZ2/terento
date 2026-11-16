"""Migration 092: Forerunner 265 and 265S as reviewed historical rows.

On 2026-11-16 both watches reached the app's permission check and stayed
PENDING ("Waiting models") because Garmin's category no longer lists them, so
the collector never created a row. The shipped macOS resolver is exercised
through the Python port in test_installation_policy.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from pglite_support import PGliteTestCase
from terento_catalog.identity_assessment import assess_identity
from terento_catalog.installation_policy import (
    build_installation_policy,
    installation_base_model,
    serialize_installation_policy,
)
from terento_catalog.map_capability import classify_map_capable
from test_installation_policy import app_policy_valid, app_resolve, garmin

MIGRATION = (
    Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
    / "092_forerunner_265_catalog.sql"
)

NEW_ROWS = {
    "garmin-forerunner-265": "forerunner 265",
    "garmin-forerunner-265s": "forerunner 265s",
}
CODES = {
    ("XML_PART_NUMBER", "006-B4257-00"): "garmin-forerunner-265",
    ("XML_PART_NUMBER", "006-B4258-00"): "garmin-forerunner-265s",
    ("USB", "091e:50a1"): "garmin-forerunner-265",
    ("USB", "091e:50a2"): "garmin-forerunner-265s",
}


class MigrationSourceTests(unittest.TestCase):
    def code(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))

    def test_migration_is_additive_and_guarded(self):
        code = self.code()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "UPDATE ", "RENAME", "CREATE INDEX"):
            self.assertNotIn(forbidden, code.upper())
        self.assertEqual(code.count("ON CONFLICT (id) DO NOTHING"), 1)
        self.assertEqual(code.count("ON CONFLICT DO NOTHING"), 1)
        ids = re.findall(r"^\s+\('(garmin-[a-z0-9-]+)', 'garmin-", code, flags=re.MULTILINE)
        self.assertEqual(sorted(ids), sorted(NEW_ROWS))
        # New code links are never approved by the migration.
        self.assertNotIn("APPROVED", code)

    def test_model_labels_match_the_reported_base_models(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for device_id, base in NEW_ROWS.items():
            with self.subTest(device_id=device_id):
                match = re.search(r"\('" + re.escape(device_id) + r"', '[a-z0-9-]+', 'Garmin', '([^']+)'", sql)
                self.assertIsNotNone(match)
                self.assertEqual(installation_base_model(match.group(1)), base)
                # Same answer as the reviewed Map Manager list the evidence cites.
                self.assertIs(classify_map_capable(match.group(1)), False)


class MigratedCatalogTests(PGliteTestCase):
    def policy(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        return json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))

    def test_rows_are_historical_maps_no_with_evidence(self):
        document = self.policy()
        self.assertTrue(app_policy_valid(document, strict=True))
        self.assertTrue(app_policy_valid(document, strict=False))
        by_id = {device["id"]: device for device in document["devices"]}
        for device_id, base in NEW_ROWS.items():
            with self.subTest(device_id=device_id):
                row = by_id[device_id]
                self.assertEqual(row["baseModel"], base)
                self.assertIs(row["active"], True)
                self.assertIs(row["mapCapable"], False)
                self.assertEqual(row["installationAuthorization"], "BLOCKED")
        stored = self.sql("SELECT id, record_source, collector_managed, specification_evidence "
                          "FROM device_model WHERE id = ANY(%s)", (list(NEW_ROWS),))
        self.assertEqual(len(stored), len(NEW_ROWS))
        for row in stored:
            self.assertEqual((row["record_source"], row["collector_managed"]), ("HISTORICAL_REVIEWED", False))
            evidence = row["specification_evidence"]["map_capable"]
            self.assertIs(evidence["value"], False)
            self.assertTrue(evidence["source"].startswith("https://www.garmin.com/en-US/p/"))
            self.assertTrue(evidence["field"])

    def test_reported_names_move_from_pending_to_not_available(self):
        document = self.policy()
        for reported, device_id in (("Forerunner 265", "garmin-forerunner-265"),
                                    ("Garmin Forerunner® 265", "garmin-forerunner-265"),
                                    ("Forerunner 265S", "garmin-forerunner-265s"),
                                    ("Forerunner 265S ", "garmin-forerunner-265s")):
            for strict in (True, False):
                with self.subTest(reported=reported, strict=strict):
                    self.assertEqual(app_resolve(document, garmin(reported), strict=strict),
                                     ("OUT_OF_SCOPE", [device_id]))
        # Exact names only: neighbours stay as they were.
        self.assertEqual(app_resolve(document, garmin("Forerunner 255"))[0], "PENDING")
        self.assertEqual(app_resolve(document, garmin("Forerunner 26"))[0], "PENDING")
        self.assertEqual(app_resolve(document, garmin("Forerunner 965")), ("APPROVED", ["garmin-forerunner-965"]))

    def test_code_links_are_pending_and_identity_resolves_by_name(self):
        links = self.sql("SELECT kind, value, device_model_id, status FROM device_identity_mapping "
                         "WHERE device_model_id = ANY(%s)", (list(NEW_ROWS),))
        self.assertEqual({(r["kind"], r["value"]): r["device_model_id"] for r in links}, CODES)
        self.assertEqual({r["status"] for r in links}, {"PENDING"})
        devices = self.sql("SELECT * FROM device_model")
        mappings = self.sql("SELECT * FROM device_identity_mapping")
        for reported, part, device_id in (("Forerunner 265", "006-B4257-00", "garmin-forerunner-265"),
                                          ("Forerunner 265S", "006-B4258-00", "garmin-forerunner-265s")):
            with self.subTest(reported=reported):
                assessment = assess_identity({"model": reported, "rawMTPModel": reported,
                                              "garminModelPartNumber": part}, devices, mappings)
                self.assertEqual((assessment["canonicalDeviceId"], assessment["resolution"]),
                                 (device_id, "SINGLE_MATCH"))


if __name__ == "__main__":
    unittest.main()

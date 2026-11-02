"""Migration 091: every Garmin Edge model with its real catalog status.

Owner decision 2026-11-02: Edge rows carry the real retail status, Garmin's
model names and Garmin's product images, and no Edge model is left out. The
shipped macOS resolver is exercised through the Python port in
test_installation_policy.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from pglite_support import PGliteTestCase
from terento_catalog.device_catalog import build_device_catalog
from terento_catalog.installation_policy import (
    build_installation_policy,
    installation_base_model,
    serialize_installation_policy,
)
from terento_catalog.migrate import _statements
from terento_catalog.models import CollectedDevice, RETAIL_RETIREMENT_MISSED_RUNS
from test_installation_policy import app_resolve, garmin

MIGRATION = (
    Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
    / "091_edge_retail_catalog.sql"
)
CYCLING = "https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/"

# In Garmin's cycling category on 2026-11-02.
CURRENT = {
    "garmin-edge-1060": "Edge 1060",
    "garmin-edge-850": "Edge 850",
    "garmin-edge-550": "Edge 550",
    "garmin-edge-mtb": "Edge MTB",
    "garmin-edge-1040-solar-solar": "Edge 1040 Solar",
    "garmin-edge-explore-3": "Edge Explore 3",
    "garmin-edge-explore-3-plus": "Edge Explore 3 Plus",
}
# The generation opened by 090, no longer in the category.
RETIRED = {
    "garmin-edge-540": "Edge 540",
    "garmin-edge-540-solar-solar": "Edge 540 Solar",
    "garmin-edge-840": "Edge 840",
    "garmin-edge-840-solar-solar": "Edge 840 Solar",
    "garmin-edge-1040": "Edge 1040",
    "garmin-edge-1050": "Edge 1050",
    "garmin-edge-explore-2": "Edge Explore 2",
}
HISTORICAL = {
    "garmin-edge-1030-plus": "Edge 1030 Plus",
    "garmin-edge-1030": "Edge 1030",
    "garmin-edge-1030-bontrager": "Edge 1030 Bontrager",
    "garmin-edge-830": "Edge 830",
    "garmin-edge-530": "Edge 530",
    "garmin-edge-520-plus": "Edge 520 Plus",
    "garmin-edge-520": "Edge 520",
    "garmin-edge-820": "Edge 820",
    "garmin-edge-explore-820": "Edge Explore 820",
    "garmin-edge-130-plus": "Edge 130 Plus",
    "garmin-edge-130": "Edge 130",
    "garmin-edge-explore": "Edge Explore",
    "garmin-edge-1000": "Edge 1000",
    "garmin-edge-explore-1000": "Edge Explore 1000",
    "garmin-edge-touring": "Edge Touring",
    "garmin-edge-touring-plus": "Edge Touring Plus",
    "garmin-edge-810": "Edge 810",
    "garmin-edge-510": "Edge 510",
    "garmin-edge-800": "Edge 800",
    "garmin-edge-500": "Edge 500",
    "garmin-edge-200": "Edge 200",
    "garmin-edge-25": "Edge 25",
    "garmin-edge-20": "Edge 20",
    "garmin-edge-705": "Edge 705",
    "garmin-edge-605": "Edge 605",
    "garmin-edge-305": "Edge 305",
    "garmin-edge-205": "Edge 205",
}
# Garmin has no product image left for these models.
NO_IMAGE = {"garmin-edge-explore", "garmin-edge-25", "garmin-edge-20"}


class MigrationSourceTests(unittest.TestCase):
    def code(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))

    def test_migration_only_adds_and_reclassifies_edge_rows(self):
        code = self.code()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "RENAME", "CREATE INDEX", "TRUNCATE"):
            self.assertNotIn(forbidden, code.upper())
        self.assertEqual(code.count("WHERE dm.id = v.id AND dm.collector_managed = FALSE"), 2)
        self.assertEqual(code.count("ON CONFLICT (id) DO NOTHING"), 2)
        for table in ("compatibility_model_review", "public_statistics", "support_status = 'SUPPORTED'"):
            self.assertNotIn(table, code)

    def test_every_listed_model_appears_once_with_garmin_name(self):
        sql = self.code()
        ids = re.findall(r"^\s+\('(garmin-edge-[a-z0-9-]+)', '(?:garmin-edge|https)", sql, flags=re.MULTILINE)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(CURRENT) | set(RETIRED) | set(HISTORICAL))
        for device_id, model in {**CURRENT, **RETIRED, **HISTORICAL}.items():
            if device_id in ("garmin-edge-1060", "garmin-edge-850", "garmin-edge-550", "garmin-edge-540",
                             "garmin-edge-840", "garmin-edge-1040", "garmin-edge-1050", "garmin-edge-explore-2"):
                continue  # 090 rows: names unchanged.
            with self.subTest(device_id=device_id):
                self.assertIn(f"('{device_id}', 'garmin-edge', 'Garmin', '{model}', '{model.lower()}'", sql)

    def test_images_are_garmin_product_media_only(self):
        for url in re.findall(r"'(https://[^']+\.jpg)'", self.code()):
            self.assertRegex(url, r"^https://res\.garmin\.com/")

    def test_statements_split_cleanly(self):
        self.assertEqual(len(_statements(MIGRATION.read_text(encoding="utf-8"))), 5)


class MigratedCatalogTests(PGliteTestCase):
    def policy(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        return json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))

    def edge_rows(self):
        return {row["id"]: row for row in self.sql(
            "SELECT * FROM device_model WHERE family_id = 'garmin-edge'")}

    def test_every_edge_model_has_its_real_status(self):
        rows = self.edge_rows()
        self.assertEqual(set(rows), set(CURRENT) | set(RETIRED) | set(HISTORICAL))
        for device_id, model in {**CURRENT, **RETIRED, **HISTORICAL}.items():
            row = rows[device_id]
            with self.subTest(device_id=device_id):
                self.assertEqual(row["model"], model)
                self.assertEqual(row["canonical_model"], model.lower())
                self.assertIs(row["active"], True)
                self.assertEqual(row["support_status"], "NOT_EVALUATED")
                if device_id in NO_IMAGE:
                    self.assertIsNone(row["source_image_url"])
                else:
                    self.assertRegex(row["source_image_url"], r"^https://res\.garmin\.com/")
                if device_id in HISTORICAL:
                    self.assertEqual((row["record_source"], row["collector_managed"]),
                                     ("HISTORICAL_REVIEWED", False))
                    self.assertIsNone(row["map_capable"])
                    continue
                self.assertEqual((row["record_source"], row["collector_managed"]), ("CURRENT_RETAIL", True))
                self.assertEqual(row["source_url"], CYCLING)
                self.assertIs(row["map_capable"], True)
                self.assertEqual(row["specification_evidence"]["map_capable"]["value"], True)
                self.assertEqual(row["specification_evidence"]["map_capable"]["field"], "ability to add maps")
                expected_missed = 0 if device_id in CURRENT else RETAIL_RETIREMENT_MISSED_RUNS
                self.assertEqual(row["consecutive_missed_collections"], expected_missed)

    def test_policy_approves_the_opened_generation_and_keeps_older_ones_pending(self):
        document = self.policy()
        for model in (*CURRENT.values(), *RETIRED.values(), "Edge® 1040 Solar", "Edge 540 Solar"):
            with self.subTest(model=model):
                self.assertEqual(app_resolve(document, garmin(model))[0], "APPROVED")
        for model in (*HISTORICAL.values(), "Edge", "Edge 10400", "Edge 1030 Plus Solar"):
            with self.subTest(model=model):
                self.assertEqual(app_resolve(document, garmin(model))[0], "PENDING")

    def test_solar_rows_share_their_base_model(self):
        for solar, base in (("Edge 540 Solar", "edge 540"), ("Edge 840 Solar", "edge 840"),
                            ("Edge 1040 Solar", "edge 1040")):
            self.assertEqual(installation_base_model(solar), base)

    def test_public_device_catalog_lists_retail_edge_rows_with_garmin_images(self):
        rows, updated_at = self.db.device_catalog_snapshot()
        devices = {device["id"]: device for device in build_device_catalog(rows, updated_at)["devices"]}
        for device_id in (*CURRENT, *RETIRED):
            with self.subTest(device_id=device_id):
                self.assertIs(devices[device_id]["mapCapable"], True)
                self.assertRegex(devices[device_id]["sourceAsset"]["url"], r"^https://res\.garmin\.com/")
        for device_id in HISTORICAL:
            self.assertNotIn(device_id, devices)

    def collected(self, device_id, model):
        return CollectedDevice(
            id=device_id, family_id="garmin-edge", family_name="Edge", manufacturer="Garmin",
            model=model, canonical_model=model.lower(), variant="", case_size_mm=None,
            display_type="Solar" if "Solar" in model else None, part_number=None,
            product_url="https://www.garmin.com/en-US/p/1/", source_url=CYCLING,
            source_image_url=self.edge_rows()[device_id]["source_image_url"], map_capable=True,
            map_evidence_row="ability to add maps")

    def test_collector_keeps_maps_and_retail_status(self):
        self.db.upsert_collected_devices([self.collected(device_id, model) for device_id, model in CURRENT.items()])
        rows = self.edge_rows()
        for device_id in CURRENT:
            self.assertEqual((rows[device_id]["consecutive_missed_collections"], rows[device_id]["map_capable"]),
                             (0, True))
        for device_id in RETIRED:
            self.assertEqual(rows[device_id]["consecutive_missed_collections"], RETAIL_RETIREMENT_MISSED_RUNS + 1)
            self.assertEqual((rows[device_id]["active"], rows[device_id]["map_capable"]), (True, True))
        for device_id in HISTORICAL:
            self.assertEqual((rows[device_id]["collector_managed"], rows[device_id]["map_capable"]), (False, None))

    def test_withdrawing_a_retail_edge_needs_maps_false(self):
        # The contract's withdrawal rule for Edge rows the collector still sees:
        # NULL Maps or an inactive row is restored by the next collection, a
        # stored false is kept, so a withdrawal migration must write false.
        self.sql("UPDATE device_model SET map_capable = NULL, active = FALSE WHERE id = 'garmin-edge-mtb'")
        self.sql("UPDATE device_model SET map_capable = FALSE WHERE id = 'garmin-edge-explore-3'")
        self.db.upsert_collected_devices([self.collected(device_id, model) for device_id, model in CURRENT.items()])
        rows = self.edge_rows()
        self.assertEqual((rows["garmin-edge-mtb"]["active"], rows["garmin-edge-mtb"]["map_capable"]), (True, True))
        self.assertEqual((rows["garmin-edge-explore-3"]["active"], rows["garmin-edge-explore-3"]["map_capable"]),
                         (True, False))
        document = self.policy()
        self.assertEqual(app_resolve(document, garmin("Edge MTB"))[0], "APPROVED")
        # Maps=false: the shipped client refuses the model (policy BLOCKED).
        self.assertEqual(app_resolve(document, garmin("Edge Explore 3"))[0], "OUT_OF_SCOPE")


if __name__ == "__main__":
    unittest.main()

"""Migration 093: older Edge models get the Maps value Garmin publishes.

Owner decision 2026-11-16: every model that supports maps, watches and Edge,
is not blocked. Migration 091 stored Maps Unknown (PENDING) for every Edge
older than the Edge 1040 generation; 093 replaces that NULL with Garmin's
published value where Garmin publishes one. The shipped macOS resolver is
exercised through the Python port in test_installation_policy.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from pglite_support import PGliteTestCase
from terento_catalog.installation_policy import build_installation_policy, serialize_installation_policy
from terento_catalog.migrate import _statements
from test_installation_policy import app_policy_valid, app_resolve, garmin

MIGRATION = (
    Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
    / "093_edge_historical_maps.sql"
)
COMPATIBILITY = "https://buy.garmin.com/ecommerceServices/productCompatibility/en-GB/GB/p/010-D1761-00/compatibleDevices"

# Garmin specification row "Ability to add maps: yes" on the stored product page.
SPEC_YES = {
    "garmin-edge-1030-plus": "Edge 1030 Plus",
    "garmin-edge-1030": "Edge 1030",
    "garmin-edge-830": "Edge 830",
    "garmin-edge-530": "Edge 530",
    "garmin-edge-520-plus": "Edge 520 Plus",
    "garmin-edge-1000": "Edge 1000",
    "garmin-edge-touring": "Edge Touring",
    "garmin-edge-touring-plus": "Edge Touring Plus",
    "garmin-edge-810": "Edge 810",
    "garmin-edge-800": "Edge 800",
    "garmin-edge-705": "Edge 705",
    "garmin-edge-605": "Edge 605",
}
# No product page left: Garmin's TopoActive cycling maps compatible-device list.
COMPATIBILITY_YES = {
    "garmin-edge-820": "Edge 820",
    "garmin-edge-explore": "Edge Explore",
    "garmin-edge-explore-820": "Edge Explore 820",
    "garmin-edge-explore-1000": "Edge Explore 1000",
}
# Reviewed owner decision: specifications list no map row, not on the map list.
SPEC_NO = {
    "garmin-edge-130-plus": "Edge 130 Plus",
    "garmin-edge-130": "Edge 130",
    "garmin-edge-510": "Edge 510",
    "garmin-edge-200": "Edge 200",
    "garmin-edge-305": "Edge 305",
    "garmin-edge-205": "Edge 205",
}
# Garmin publishes nothing either way: unchanged.
UNCHANGED = {
    "garmin-edge-1030-bontrager": "Edge 1030 Bontrager",
    "garmin-edge-520": "Edge 520",
    "garmin-edge-500": "Edge 500",
    "garmin-edge-25": "Edge 25",
    "garmin-edge-20": "Edge 20",
}
# Stored Maps value of every historical Edge row after 093 (None = PENDING).
HISTORICAL_EDGE_MAPS = {
    **{device_id: True for device_id in (*SPEC_YES, *COMPATIBILITY_YES)},
    **{device_id: False for device_id in SPEC_NO},
    **{device_id: None for device_id in UNCHANGED},
}


class MigrationSourceTests(unittest.TestCase):
    def code(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))

    def test_migration_is_data_only_and_guarded(self):
        code = self.code()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "INSERT INTO DEVICE_MODEL", "RENAME", "CREATE INDEX"):
            self.assertNotIn(forbidden, code.upper())
        self.assertEqual(code.count("UPDATE device_model"), 1)
        for guard in ("d.map_capable IS NULL", "d.record_source = 'HISTORICAL_REVIEWED'",
                      "d.collector_managed = FALSE", "d.family_id = 'garmin-edge'",
                      "(s.source IS NULL OR d.product_url = s.source)"):
            self.assertIn(guard, code)
        seeded = re.findall(r"^\s+\('(garmin-edge-[a-z0-9-]+)',", code, flags=re.MULTILINE)
        self.assertEqual(sorted(seeded), sorted([*SPEC_YES, *COMPATIBILITY_YES, *SPEC_NO]))
        for device_id in UNCHANGED:
            self.assertNotIn(f"'{device_id}'", code)
        self.assertEqual(len(_statements(MIGRATION.read_text(encoding="utf-8"))), 3)


class MigratedCatalogTests(PGliteTestCase):
    def policy(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        return json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))

    def rows(self):
        return {row["id"]: row for row in self.sql(
            "SELECT * FROM device_model WHERE id = ANY(%s)", (list(HISTORICAL_EDGE_MAPS),))}

    def test_rows_store_garmin_value_with_evidence(self):
        rows = self.rows()
        self.assertEqual(set(rows), set(HISTORICAL_EDGE_MAPS))
        for device_id, expected in HISTORICAL_EDGE_MAPS.items():
            row = rows[device_id]
            with self.subTest(device_id=device_id):
                self.assertIs(row["map_capable"], expected)
                self.assertEqual((row["record_source"], row["collector_managed"], row["active"]),
                                 ("HISTORICAL_REVIEWED", False, True))
                evidence = row["specification_evidence"].get("map_capable")
                if expected is None:
                    self.assertIsNone(evidence)
                    continue
                self.assertIs(evidence["value"], expected)
                if device_id in SPEC_YES:
                    self.assertEqual(evidence["source"], row["product_url"])
                    self.assertEqual(evidence["field"], "ability to add maps")
                elif device_id in COMPATIBILITY_YES:
                    self.assertEqual(evidence["source"], COMPATIBILITY)
                    self.assertIn(COMPATIBILITY_YES[device_id].replace("Edge ", "Edge® "), evidence["field"])
                    self.assertTrue(evidence["manual"].startswith("https://www8.garmin.com/manuals/"))
                else:
                    self.assertEqual(evidence["source"], row["product_url"])
                    self.assertEqual(evidence["version"], "reviewed-owner-decision-2026-11-16")

    def test_reported_names_get_the_new_result_in_the_app(self):
        document = self.policy()
        for strict in (True, False):
            self.assertTrue(app_policy_valid(document, strict=strict))
        expected = {**{m: "APPROVED" for m in (*SPEC_YES.values(), *COMPATIBILITY_YES.values())},
                    **{m: "OUT_OF_SCOPE" for m in SPEC_NO.values()},
                    **{m: "PENDING" for m in UNCHANGED.values()}}
        for reported, decision in expected.items():
            for strict in (True, False):
                with self.subTest(reported=reported, strict=strict):
                    self.assertEqual(app_resolve(document, garmin(reported), strict=strict)[0], decision)
        # Whole names only: neighbours keep their own rows.
        self.assertEqual(app_resolve(document, garmin("Edge 1030 Plus"))[1], ["garmin-edge-1030-plus"])
        self.assertEqual(app_resolve(document, garmin("Edge Explore"))[1], ["garmin-edge-explore"])
        self.assertEqual(app_resolve(document, garmin("Edge Explore 2"))[0], "APPROVED")
        # A variant word ends the base model as for every model.
        self.assertEqual(app_resolve(document, garmin("Edge 1030 Plus Solar")),
                         ("APPROVED", ["garmin-edge-1030-plus"]))
        self.assertEqual(app_resolve(document, garmin("Edge 520 Solar"))[0], "PENDING")
        for unknown in ("Edge", "Edge 10400", "Edge 5300"):
            self.assertEqual(app_resolve(document, garmin(unknown))[0], "PENDING")

    def test_rerun_changes_nothing_and_never_overrides_a_reviewed_value(self):
        self.sql("UPDATE device_model SET map_capable = FALSE WHERE id = 'garmin-edge-530'")
        self.sql("UPDATE device_model SET map_capable = NULL WHERE id = 'garmin-edge-830'")
        self.sql("UPDATE device_model SET map_capable = NULL, product_url = 'https://example.invalid/' "
                 "WHERE id = 'garmin-edge-1030'")
        before = self.rows()
        for statement in _statements(MIGRATION.read_text(encoding="utf-8")):
            self.sql(statement)
        after = self.rows()
        self.assertIs(after["garmin-edge-530"]["map_capable"], False)
        self.assertIs(after["garmin-edge-830"]["map_capable"], True)
        # Evidence is tied to the reviewed product page.
        self.assertIsNone(after["garmin-edge-1030"]["map_capable"])
        for device_id in set(HISTORICAL_EDGE_MAPS) - {"garmin-edge-830"}:
            self.assertIs(after[device_id]["map_capable"], before[device_id]["map_capable"])


if __name__ == "__main__":
    unittest.main()

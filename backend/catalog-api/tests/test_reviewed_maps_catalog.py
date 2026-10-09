"""Migration 075 and the retail-retirement rule (owner decisions 2026-10-09).

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
from terento_catalog.admin import _admin_device_payload
from terento_catalog.installation_policy import (
    build_installation_policy,
    installation_base_model,
    serialize_installation_policy,
)
from terento_catalog.migrate import _statements
from terento_catalog.models import RETAIL_RETIREMENT_MISSED_RUNS, CollectedDevice
from test_installation_policy import app_policy_valid, app_resolve, garmin

MIGRATION = (
    Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
    / "075_reviewed_maps_catalog_decisions.sql"
)

# id -> base model the watch reports (after the shipped normalizer).
NEW_ROWS = {
    "garmin-quatix-7-pro": "quatix 7 pro",
    "garmin-d2-mach-1-pro": "d2 mach 1 pro",
    "garmin-forerunner-945-lte": "forerunner 945 lte",
    "garmin-quatix-6x-solar": "quatix 6x",
    "garmin-quatix-7x-solar": "quatix 7x",
    "garmin-descent-mk2s": "descent mk2s",
    "garmin-marq-adventurer": "marq adventurer",
    "garmin-marq-athlete": "marq athlete",
    "garmin-marq-aviator": "marq aviator",
    "garmin-marq-captain": "marq captain",
    "garmin-marq-commander": "marq commander",
    "garmin-marq-driver": "marq driver",
    "garmin-marq-golfer": "marq golfer",
    "garmin-marq-expedition": "marq expedition",
    "garmin-d2-delta": "d2 delta",
    "garmin-d2-delta-s": "d2 delta s",
    "garmin-d2-delta-px": "d2 delta px",
    "garmin-d2-charlie": "d2 charlie",
    "garmin-fenix-5s-plus": "fenix 5s plus",
    "garmin-fenix-5x-plus": "fenix 5x plus",
    "garmin-epix-gen-1": "epix",
    "garmin-tactix-7-pro-edition": "tactix 7 pro edition",
    "garmin-tactix-7-pro-ballistics-edition": "tactix 7 pro ballistics edition",
    "garmin-tactix-7-standard-edition": "tactix 7 standard edition",
    "garmin-descent-mk2i": "descent mk2i",
    "garmin-marq-commander-gen-2-carbon-edition": "marq commander gen 2 carbon edition",
    "garmin-marq-athlete-gen-2-carbon-edition": "marq athlete gen 2 carbon edition",
    "garmin-marq-golfer-gen-2-carbon-edition": "marq golfer gen 2 carbon edition",
    "garmin-marq-adventurer-gen-2-damascus-steel-edition": "marq adventurer gen 2 damascus steel edition",
    "garmin-fenix-8-dual-power-47": "fenix 8 dual power",
    "garmin-fenix-8-dual-power-51": "fenix 8 dual power",
    "garmin-quatix-6x-dual-power": "quatix 6x dual power",
    "garmin-forerunner-955-dual-power": "forerunner 955 dual power",
    "garmin-quatix-8-pro-51-amoled": "quatix 8 pro",
}

# Names as Garmin publishes them (and as the watch reports its model).
REPORTED_APPROVED = [
    "quatix 7 Pro", "D2 Mach 1 Pro", "Forerunner 945 LTE", "quatix 6X Solar", "quatix 6X",
    "quatix 7X - Solar Edition", "quatix 7X Solar", "Descent Mk2S", "MARQ Adventurer", "MARQ Athlete",
    "MARQ Aviator", "MARQ Captain", "MARQ Commander", "MARQ Driver", "MARQ Golfer", "MARQ Expedition",
    "D2 Delta", "D2 Delta S", "D2 Delta PX", "D2 Charlie", "fēnix 5S Plus", "fēnix 5X Plus", "fenix 5X Plus",
    "epix", "tactix 7 – Pro Edition", "tactix 7 - Pro Ballistics Edition", "tactix 7 – Standard Edition",
    "Descent Mk2i", "MARQ Commander (Gen 2) - Carbon Edition", "MARQ Athlete (Gen 2) – Carbon Edition",
    "MARQ Golfer (Gen 2) - Carbon Edition", "MARQ Adventurer (Gen 2) - Damascus Steel Edition",
    "fēnix 8 Dual Power", "fēnix 8 Dual Power 51mm", "quatix 6X Dual Power", "Forerunner 955 Dual Power",
    "quatix 8 Pro 51mm", "quatix 8 Pro – 51 mm, AMOLED",
    "fēnix 7X Pro - Solar Edition (no Wi-Fi)",
]

FENIX_6_ROWS = {"garmin-fenix-6-47", "garmin-fenix-6s-42", "garmin-fenix-6x-51"}


def collector_row(sql, device_id, model, product_url, map_capable, *, family="garmin-approach",
                  family_name="Approach", active=True, missed=0, collector=True):
    sql("INSERT INTO device_family (id, manufacturer, name, canonical_name, source_url) "
        "VALUES (%s, 'Garmin', %s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (family, family_name, family.removeprefix("garmin-"), product_url))
    sql("INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant, product_url, "
        "source_url, active, map_capable, collector_managed, record_source, consecutive_missed_collections) "
        "VALUES (%s, %s, 'Garmin', %s, %s, '', %s, %s, %s, %s, %s, %s, %s)",
        (device_id, family, model, model.lower(), product_url, product_url, active, map_capable, collector,
         "CURRENT_RETAIL" if collector else "HISTORICAL_REVIEWED", missed))


def retail(device_id, model):
    return CollectedDevice(
        id=device_id, family_id="garmin-fenix", family_name="fēnix", manufacturer="Garmin",
        model=model, canonical_model=model.lower(), variant="", case_size_mm=None, display_type=None,
        part_number=None, product_url=f"https://www.garmin.com/en-US/p/{abs(hash(device_id)) % 10**6}/",
        source_url="https://www.garmin.com/en-US/c/wearables-smartwatches/",
        map_capable=True, map_evidence_row="built-in mapping",
    )


class MigrationSourceTests(unittest.TestCase):
    def test_migration_is_additive_and_guarded(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "RENAME", "CREATE INDEX"):
            self.assertNotIn(forbidden, code.upper())
        self.assertIn("ON CONFLICT (id) DO NOTHING", code)
        self.assertIn("d.map_capable IS FALSE", code)
        self.assertIn("d.map_capable IS NULL", code)
        self.assertIn("consecutive_missed_collections >= 3", code)
        # fēnix 6 is end of life: no row of that family is added or changed.
        self.assertNotRegex(code.lower(), r"fenix-6|fenix 6|fēnix 6")
        ids = re.findall(r"^\s+\('(garmin-[a-z0-9-]+)', 'garmin-", code, flags=re.MULTILINE)
        self.assertEqual(sorted(ids), sorted(NEW_ROWS))
        self.assertEqual(len(ids), len(set(ids)))

    def test_model_labels_match_the_reported_base_models(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for device_id, base in NEW_ROWS.items():
            with self.subTest(device_id=device_id):
                match = re.search(r"\('" + re.escape(device_id) + r"', '[a-z0-9-]+', 'Garmin', '([^']+)'", sql)
                self.assertIsNotNone(match)
                self.assertEqual(installation_base_model(match.group(1)), base)

    def test_statements_split_cleanly(self):
        statements = _statements(MIGRATION.read_text(encoding="utf-8"))
        self.assertEqual(len(statements), 9)


class MigratedCatalogTests(PGliteTestCase):
    def policy(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        return json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))

    def test_new_rows_are_map_capable_historical_rows_in_the_policy(self):
        document = self.policy()
        self.assertTrue(app_policy_valid(document, strict=True))
        self.assertTrue(app_policy_valid(document, strict=False))
        by_id = {device["id"]: device for device in document["devices"]}
        self.assertEqual(len(by_id), len(document["devices"]))
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
            self.assertTrue(re.match(r"https://(www\.garmin\.com|www\.garmin\.co\.jp|www8\.garmin\.com)/", evidence["source"]))
            self.assertTrue(evidence["field"])

    def test_shipped_resolver_approves_each_reported_name(self):
        document = self.policy()
        for reported in REPORTED_APPROVED:
            for strict in (True, False):
                with self.subTest(reported=reported, strict=strict):
                    decision, ids = app_resolve(document, garmin(reported), strict=strict)
                    self.assertEqual(decision, "APPROVED")
                    self.assertTrue(ids)
        # Size narrowing still applies to the new sized rows.
        self.assertEqual(app_resolve(document, garmin("fēnix 8 Dual Power 47mm")),
                         ("APPROVED", ["garmin-fenix-8-dual-power-47"]))
        self.assertEqual(app_resolve(document, garmin("quatix 8 Pro 51mm")),
                         ("APPROVED", ["garmin-quatix-8-pro-51-amoled"]))

    def test_fenix_6_edge_and_unknown_models_are_unchanged(self):
        document = self.policy()
        fenix_6 = {d["id"]: d for d in document["devices"] if d["baseModel"].startswith("fenix 6")}
        self.assertEqual(set(fenix_6), FENIX_6_ROWS)
        for row in fenix_6.values():
            self.assertEqual((row["active"], row["mapCapable"], row["variant"]), (True, True, row["variant"]))
        self.assertEqual(app_resolve(document, garmin("fēnix 6X Pro"))[0], "PENDING")
        self.assertEqual(app_resolve(document, garmin("fēnix 6 Dual Power"))[0], "PENDING")
        self.assertEqual(app_resolve(document, garmin("fēnix 6X Sapphire")), ("APPROVED", ["garmin-fenix-6x-51"]))
        for reported in ("Edge 840", "Edge 1050", "GPSMAP 67", "Enduro 4", "Approach S72", "MARQ Captain (Gen 3)"):
            with self.subTest(reported=reported):
                self.assertEqual(app_resolve(document, garmin(reported)), ("PENDING", []))


class ReviewedMapsUpdateTests(PGliteTestCase):
    """Re-runs migration 075 over collector rows shaped like the live catalog."""

    def apply_migration(self):
        for statement in _statements(MIGRATION.read_text(encoding="utf-8")):
            self.server.exec(statement)

    def maps(self):
        return {row["id"]: row for row in self.sql(
            "SELECT id, map_capable, active, specification_evidence FROM device_model")}

    def test_golf_and_unknown_rows_change_only_from_the_exact_prior_value(self):
        p = "https://www.garmin.com/en-US/p/{}/".format
        collector_row(self.sql, "garmin-approach-s44", "Approach S44", p(1604358), False)
        collector_row(self.sql, "garmin-approach-s50", "Approach S50", p(1604377), False)
        collector_row(self.sql, "garmin-approach-s70-42", "Approach S70", p(847697), False)
        collector_row(self.sql, "garmin-approach-s70-47", "Approach S70", p(847706), False)
        collector_row(self.sql, "garmin-approach-j1", "Approach J1", p(1908217), False)
        collector_row(self.sql, "garmin-approach-s12", "Approach S12", p(721216), False)
        nulls = {"garmin-bounce-2": 1815501, "garmin-d2-air-x15": 1957609, "garmin-forerunner-70": 1941179,
                 "garmin-forerunner-170": 1915560, "garmin-forerunner-170-music": 2014513,
                 "garmin-vivofit-jr-3-disney-princess": 711489, "garmin-vivofit-jr-3-marvel": 711488,
                 "garmin-vivosmart-5": 782585}
        for device_id, product in nulls.items():
            collector_row(self.sql, device_id, device_id, p(product), None, family="garmin-other", family_name="Other")
        # A reviewed value set by an administrator is never overwritten.
        self.sql("UPDATE device_model SET map_capable = TRUE WHERE id = 'garmin-vivosmart-5'")
        # Another unknown model is not part of the reviewed decision.
        collector_row(self.sql, "garmin-venu-x9", "Venu X9", p(42), None, family="garmin-other", family_name="Other")

        self.apply_migration()
        rows = self.maps()
        for device_id in ("garmin-approach-s44", "garmin-approach-s50", "garmin-approach-s70-42", "garmin-approach-s70-47"):
            self.assertIs(rows[device_id]["map_capable"], True)
            self.assertEqual(rows[device_id]["specification_evidence"]["map_capable"]["field"], "full vector map")
        self.assertEqual(rows["garmin-approach-s44"]["specification_evidence"]["map_capable"]["officialValue"],
                         "yes (with Garmin Golf membership)")
        self.assertIs(rows["garmin-approach-j1"]["map_capable"], False)
        self.assertIs(rows["garmin-approach-s12"]["map_capable"], False)
        for device_id in nulls:
            if device_id == "garmin-vivosmart-5":
                continue
            self.assertIs(rows[device_id]["map_capable"], False, device_id)
            self.assertIsNone(rows[device_id]["specification_evidence"]["map_capable"]["field"])
        self.assertIs(rows["garmin-vivosmart-5"]["map_capable"], True)
        self.assertIsNone(rows["garmin-venu-x9"]["map_capable"])

        rows_policy, updated_at = self.db.installation_policy_snapshot()
        document = json.loads(serialize_installation_policy(build_installation_policy(rows_policy, updated_at)))
        self.assertEqual(app_resolve(document, garmin("Approach S70 47mm"))[0], "APPROVED")
        self.assertEqual(app_resolve(document, garmin("Approach S44"))[0], "APPROVED")
        self.assertEqual(app_resolve(document, garmin("Approach S12"))[0], "OUT_OF_SCOPE")
        self.assertEqual(app_resolve(document, garmin("Forerunner 70"))[0], "OUT_OF_SCOPE")

    def test_rows_with_a_different_product_page_are_not_changed(self):
        collector_row(self.sql, "garmin-approach-s44", "Approach S44", "https://www.garmin.com/en-US/p/9/", False)
        collector_row(self.sql, "garmin-bounce-2", "Bounce 2", "https://www.garmin.com/en-US/p/9/", None,
                      family="garmin-bounce", family_name="Bounce")
        self.apply_migration()
        rows = self.maps()
        self.assertIs(rows["garmin-approach-s44"]["map_capable"], False)
        self.assertIsNone(rows["garmin-bounce-2"]["map_capable"])

    def test_collector_retired_rows_are_reactivated_and_nothing_else(self):
        url = "https://www.garmin.com/en-US/p/7/"
        collector_row(self.sql, "garmin-fenix-8-retired", "fēnix 8", url, True, family="garmin-fenix",
                      family_name="fēnix", active=False, missed=3)
        collector_row(self.sql, "garmin-fenix-8-other", "fēnix 8", url, True, family="garmin-fenix",
                      family_name="fēnix", active=False, missed=0)
        collector_row(self.sql, "garmin-historical-off", "fēnix 3", url, True, family="garmin-fenix",
                      family_name="fēnix", active=False, missed=5, collector=False)
        self.apply_migration()
        rows = self.maps()
        self.assertIs(rows["garmin-fenix-8-retired"]["active"], True)
        self.assertIs(rows["garmin-fenix-8-other"]["active"], False)
        self.assertIs(rows["garmin-historical-off"]["active"], False)


class RetailRetirementTests(PGliteTestCase):
    def test_model_missing_from_complete_runs_stays_approvable(self):
        current = retail("garmin-fenix-10-47", "fēnix 10")
        leaving = retail("garmin-fenix-9-old", "fēnix 9 Old")
        self.db.upsert_collected_devices([current, leaving])
        runs = [self.db.upsert_collected_devices([current]) for _ in range(RETAIL_RETIREMENT_MISSED_RUNS + 2)]
        # Reported once, on the run that crosses the threshold.
        self.assertEqual([("garmin-fenix-9-old" in run["updated_ids"]) for run in runs],
                         [False, False, True, False, False])
        row = self.sql("SELECT active, map_capable, consecutive_missed_collections, collector_managed "
                       "FROM device_model WHERE id = 'garmin-fenix-9-old'")[0]
        self.assertEqual((row["active"], row["map_capable"], row["collector_managed"]), (True, True, True))
        self.assertEqual(row["consecutive_missed_collections"], RETAIL_RETIREMENT_MISSED_RUNS + 2)

        rows, updated_at = self.db.installation_policy_snapshot()
        document = json.loads(serialize_installation_policy(build_installation_policy(rows, updated_at)))
        self.assertEqual(app_resolve(document, garmin("fēnix 9 Old")), ("APPROVED", ["garmin-fenix-9-old"]))

        admin_rows, sync = self.db.admin_device_snapshot()
        devices = {d["id"]: d for d in _admin_device_payload(admin_rows, sync)["devices"]}
        self.assertIs(devices["garmin-fenix-9-old"]["retailRetired"], True)
        self.assertIs(devices["garmin-fenix-9-old"]["active"], True)
        self.assertIs(devices["garmin-fenix-10-47"]["retailRetired"], False)
        self.assertIs(devices["garmin-quatix-7-pro"]["retailRetired"], False)

        # Seen again: current retail, counter reset, reported as an update.
        result = self.db.upsert_collected_devices([current, leaving])
        self.assertIn("garmin-fenix-9-old", result["updated_ids"])
        row = self.sql("SELECT active, consecutive_missed_collections FROM device_model WHERE id = 'garmin-fenix-9-old'")[0]
        self.assertEqual((row["active"], row["consecutive_missed_collections"]), (True, 0))

    def test_partial_collection_never_counts_toward_retirement(self):
        current = retail("garmin-fenix-10-47", "fēnix 10")
        leaving = retail("garmin-fenix-9-old", "fēnix 9 Old")
        self.db.upsert_collected_devices([current, leaving])
        for _ in range(4):
            self.db.upsert_collected_devices([current], collection_complete=False)
        row = self.sql("SELECT active, consecutive_missed_collections FROM device_model WHERE id = 'garmin-fenix-9-old'")[0]
        self.assertEqual((row["active"], row["consecutive_missed_collections"]), (True, 0))


if __name__ == "__main__":
    unittest.main()

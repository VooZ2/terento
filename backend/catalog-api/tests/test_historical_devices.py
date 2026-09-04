from pathlib import Path
import unittest

from terento_catalog.historical_devices import (
    HISTORICAL_DEVICE_REGISTRY,
    all_historical_device_specs,
    historical_device_for_event,
    historical_device_spec,
)
from terento_catalog.map_capability import classify_map_capable


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "terento_catalog"
    / "migrations"
    / "016_historical_device_registry.sql"
)
EXPANDED_MIGRATION = MIGRATION.parent / "020_historical_map_capable_registry.sql"

EXPECTED_MISSING_MAP_MODELS = {
    "garmin-d2-mach-1", "garmin-descent-mk1", "garmin-descent-mk2",
    "garmin-enduro-2", "garmin-epix-pro-gen-2", "garmin-fenix-5x",
    "garmin-fenix-5-plus", "garmin-forerunner-945", "garmin-forerunner-965",
    "garmin-quatix-6", "garmin-quatix-7", "garmin-tactix-charlie",
    "garmin-tactix-delta", "garmin-tactix-7",
}


class HistoricalDeviceRegistryTests(unittest.TestCase):
    def test_fenix_7_is_resolved_without_requiring_retail_catalog_membership(self):
        spec = historical_device_for_event({
            "model": "fēnix 7",
            "compatibilityIdentity": "fēnix 7 · 47 mm",
            "caseSizeMm": 47,
        })
        self.assertIsNotNone(spec)
        self.assertEqual(spec.id, "garmin-fenix-7-47")
        self.assertEqual(spec.source_image_url, None)

    def test_variant_boundary_does_not_match_fenix_7s_as_fenix_7(self):
        spec = historical_device_for_event({
            "model": "fēnix 7S",
            "caseSizeMm": 42,
        })
        self.assertIsNotNone(spec)
        self.assertEqual(spec.id, "garmin-fenix-7s-42")

    def test_fenix_7_pro_does_not_match_historical_fenix_7_record(self):
        spec = historical_device_for_event({
            "model": "fēnix 7 Pro",
            "compatibilityIdentity": "fēnix 7 Pro",
            "caseSizeMm": 47,
        })
        self.assertIsNone(spec)

    def test_registry_contains_reviewed_source_and_no_write_authorization(self):
        self.assertEqual(len(HISTORICAL_DEVICE_REGISTRY), 22)
        self.assertTrue(all(spec.source_url.startswith("https://") for spec in HISTORICAL_DEVICE_REGISTRY))
        self.assertFalse(hasattr(historical_device_spec("garmin-fenix-7-47"), "write_profile"))

    def test_registry_covers_missing_map_installer_families(self):
        specs = {spec.id: spec for spec in all_historical_device_specs()}
        self.assertTrue(EXPECTED_MISSING_MAP_MODELS <= specs.keys())
        for device_id in EXPECTED_MISSING_MAP_MODELS:
            spec = specs[device_id]
            self.assertTrue(classify_map_capable(spec.canonical_model))
            resolved = historical_device_for_event({"model": spec.model})
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.id, device_id)

    def test_migration_seeds_history_and_keeps_it_out_of_collector_deactivation(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("HISTORICAL_REVIEWED", sql)
        self.assertIn("collector_managed", sql)
        self.assertIn("garmin-fenix-7-47", sql)
        self.assertIn("collector_managed BOOLEAN NOT NULL DEFAULT TRUE", sql)
        db_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "terento_catalog"
            / "db.py"
        ).read_text(encoding="utf-8")
        self.assertIn("AND collector_managed = TRUE", db_source)
        self.assertIn("WHERE collector_managed = TRUE", db_source)

    def test_expanded_migration_seeds_only_reviewed_map_capable_history(self):
        sql = EXPANDED_MIGRATION.read_text(encoding="utf-8")
        for device_id in EXPECTED_MISSING_MAP_MODELS:
            self.assertIn(device_id, sql)
        self.assertIn("map_capable, support_status", sql)
        self.assertIn("'HISTORICAL_REVIEWED', FALSE", sql)
        self.assertIn("never authorize a device write", sql)


if __name__ == "__main__":
    unittest.main()

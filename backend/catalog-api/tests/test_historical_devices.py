from pathlib import Path
import unittest

from terento_catalog.historical_devices import (
    HISTORICAL_DEVICE_REGISTRY,
    historical_device_for_event,
    historical_device_spec,
)


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "terento_catalog"
    / "migrations"
    / "016_historical_device_registry.sql"
)


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

    def test_registry_contains_reviewed_source_and_no_write_authorization(self):
        self.assertGreaterEqual(len(HISTORICAL_DEVICE_REGISTRY), 8)
        self.assertTrue(all(spec.source_url.startswith("https://") for spec in HISTORICAL_DEVICE_REGISTRY))
        self.assertFalse(hasattr(historical_device_spec("garmin-fenix-7-47"), "write_profile"))

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


if __name__ == "__main__":
    unittest.main()

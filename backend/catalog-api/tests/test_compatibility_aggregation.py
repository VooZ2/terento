from pathlib import Path
import unittest


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "terento_catalog"
    / "migrations"
    / "015_canonical_compatibility_aggregation.sql"
)


class CompatibilityAggregationMigrationTests(unittest.TestCase):
    def test_canonical_device_is_primary_aggregate_key(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        canonical_key = (
            "COALESCE(\n"
            "        e.canonical_device_model_id,\n"
            "        'identity:' || e.compatibility_identity\n"
            "    )"
        )
        self.assertIn(canonical_key, sql)
        self.assertIn("GROUP BY COALESCE(", sql)
        self.assertNotIn("GROUP BY e.compatibility_identity", sql)

    def test_counts_and_status_are_calculated_after_canonical_grouping(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        group_position = sql.index("GROUP BY COALESCE(")
        status_position = sql.index("WHEN e.successful_install_count = 0")
        self.assertLess(group_position, status_position)
        self.assertIn("count(*) AS attempted_install_count", sql)
        self.assertIn("WHEN e.successful_install_count < 3 THEN 'TESTED'", sql)
        self.assertIn("WHEN e.successful_install_count < 5 THEN 'SUPPORTED'", sql)
        self.assertIn("WHEN e.successful_install_count = 0 THEN 'TESTING'", sql)
        self.assertIn("ELSE 'VERIFIED'", sql)

    def test_runtime_and_database_status_rules_are_not_support_decisions(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertNotIn("support_status", sql)
        self.assertIn("calculated_status", sql)

    def test_observed_beta6_47mm_identity_is_corrected_without_touching_siblings(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("compatibility_identity = 'fēnix 8 · 47 mm, AMOLED'", sql)
        self.assertIn("canonical_device_model_id = 'garmin-fenix-8-47-amoled'", sql)
        self.assertIn("case_size_mm = 47", sql)
        self.assertIn("usb_product_id = 20920", sql)
        self.assertNotIn("garmin-fenix-8-51-amoled'\nWHERE", sql)

    def test_dashboard_result_count_describes_aggregate_rows_as_models(self) -> None:
        admin_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "terento_catalog"
            / "admin.py"
        ).read_text(encoding="utf-8")
        self.assertIn("visible.length === 1 ? 'model' : 'models'", admin_source)
        self.assertNotIn("visible.length === 1 ? 'report' : 'reports'", admin_source)


if __name__ == "__main__":
    unittest.main()

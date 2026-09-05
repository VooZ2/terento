from pathlib import Path
import unittest


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "terento_catalog"
    / "migrations"
    / "015_canonical_compatibility_aggregation.sql"
)
CURRENT_MIGRATION = MIGRATION.parent / "025_device_card_failure_epoch.sql"
IDENTITY_CORRECTION_MIGRATION = MIGRATION.parent / "013_canonical_four_status_compatibility.sql"


class CompatibilityAggregationMigrationTests(unittest.TestCase):
    def test_identity_correction_allows_fresh_database_but_rejects_partial_history(self) -> None:
        sql = IDENTITY_CORRECTION_MIGRATION.read_text(encoding="utf-8")
        self.assertIn(
            "(corrected_47_count = 0 AND corrected_51_count = 0)",
            sql,
        )
        self.assertIn(
            "OR (corrected_47_count = 3 AND corrected_51_count = 1)",
            sql,
        )
        self.assertNotIn("CHECK (corrected_47_count = 3)", sql)

    def test_canonical_device_is_primary_aggregate_key(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        canonical_key = (
            "COALESCE(\n"
            "            e.canonical_device_model_id,\n"
            "            'identity:' || e.compatibility_identity\n"
            "        ) AS aggregate_key"
        )
        self.assertIn(canonical_key, sql)
        self.assertIn("GROUP BY e.aggregate_key", sql)
        self.assertNotIn("GROUP BY e.compatibility_identity", sql)

    def test_counts_and_status_are_calculated_after_canonical_grouping(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        group_position = sql.index("GROUP BY e.aggregate_key")
        status_position = sql.index("WHEN e.successful_install_count = 0")
        self.assertLess(group_position, status_position)
        self.assertIn("count(*) AS attempted_install_count", sql)
        self.assertIn("WHEN e.successful_install_count < 3 THEN 'TESTED'", sql)
        self.assertIn("WHEN e.successful_install_count < 5 THEN 'SUPPORTED'", sql)

    def test_error_categories_use_the_same_materialized_aggregate_key(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("error_stats AS (", sql)
        self.assertIn("GROUP BY e.aggregate_key, e.error_category", sql)
        self.assertIn("ON errors.aggregate_key = e.aggregate_key", sql)
        self.assertNotIn("subquery uses ungrouped column", sql)
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

    def test_dashboard_result_count_describes_exact_model_variant_rows_as_variants(self) -> None:
        admin_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "terento_catalog"
            / "admin.py"
        ).read_text(encoding="utf-8")
        self.assertIn("visible.length === 1 ? 'variant' : 'variants'", admin_source)
        self.assertNotIn("visible.length === 1 ? 'report' : 'reports'", admin_source)

    def test_legacy_failures_have_a_non_destructive_resolved_lifecycle(self) -> None:
        migration = (
            MIGRATION.parent / "019_resolved_legacy_diagnostics.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("diagnostic_status", migration)
        self.assertIn("'ACTIVE', 'RESOLVED'", migration)
        self.assertIn("resolution_code = 'LEGACY_PRE_BETA6'", migration)
        self.assertIn("phase_outcome = 'FAILED'", migration)
        self.assertIn("release_label IS NULL", migration)
        self.assertNotIn("DELETE FROM compatibility_evidence_event", migration)

    def test_current_aggregate_excludes_resolved_and_prewrite_history(self) -> None:
        migration = CURRENT_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("compatibility_device_card_failure_epoch", migration)
        self.assertIn("WHERE e.diagnostic_status = 'ACTIVE'", migration)
        self.assertIn("count(*) FILTER (WHERE o.write_started) AS attempted_install_count", migration)
        self.assertIn(
            "count(*) FILTER (WHERE o.write_started AND NOT o.operation_succeeded) AS failed_install_count",
            migration,
        )
        self.assertIn("excluded from current compatibility statistics", migration)

    def test_admin_keeps_resolved_failures_in_history(self) -> None:
        from terento_catalog.admin import diagnostics_page

        body = diagnostics_page(
            [], {"username": "operator"}, "csrf", identity="Test model",
            resolved_operations=[{
                "operation_key": "historical-failure",
                "compatibility_identity": "Test model",
                "phase_outcome": "FAILED",
                "diagnostic_status": "RESOLVED",
                "resolution_reason": "FIXED",
            }],
        ).decode()
        self.assertIn("data-diagnostic-state='resolved'", body)
        self.assertIn("data-diagnostic-result='failed'", body)
        self.assertIn("Diagnostic ID: <code>historical-failure</code>", body)
        self.assertIn("action='/admin/diagnostics/reopen'", body)
        self.assertNotIn("action='/admin/diagnostics/resolve'", body)


if __name__ == "__main__":
    unittest.main()

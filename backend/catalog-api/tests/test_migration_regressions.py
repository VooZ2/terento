from pathlib import Path
import unittest


class MigrationRegressionTests(unittest.TestCase):
    def test_maprando_activation_migration_is_metadata_only(self):
        migration = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "migrations"
            / "039_activate_maprando_beta11.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("'maprando'", migration)
        self.assertIn("'ACTIVE'", migration)
        self.assertIn("ON CONFLICT (id) DO UPDATE", migration)
        self.assertIn("INSERT INTO provider_source", migration)
        self.assertNotIn("DELETE FROM", migration)

    def test_provider_api_migration_is_additive_and_has_required_contract(self):
        migration = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "migrations"
            / "026_provider_neutral_map_api.sql"
        ).read_text(encoding="utf-8")
        for table in (
            "provider_source",
            "map_package",
            "map_artifact",
            "provider_health_check",
            "catalog_collection_run",
            "map_download_event",
            "admin_audit_log",
        ):
            self.assertIn(f"CREATE TABLE {table}", migration)
        for column in ("adapter_id", "status", "license", "last_catalog_sync"):
            self.assertIn(column, migration)
        for column in ("kind", "source_url", "size_bytes", "checksum_sha256", "content_type", "required"):
            self.assertIn(column, migration)
        self.assertIn("magic_status", migration)
        for column in ("old_status", "new_status", "reason"):
            self.assertIn(column, migration)
        self.assertNotIn("DROP TABLE", migration)
        self.assertNotIn("BYTEA", migration)

    def test_map_events_are_pruned_after_documented_retention_period(self):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "db.py"
        ).read_text(encoding="utf-8")
        self.assertIn("DELETE FROM map_download_event", source)
        self.assertIn("interval '24 months'", source)

    def test_otm_state_repair_is_conservative_and_audited(self):
        migration = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "migrations"
            / "027_restore_otm_paused_state.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("UPDATE map_provider", migration)
        self.assertIn("p.status = 'ACTIVE'", migration)
        self.assertIn("package.availability = 'AVAILABLE'", migration)
        self.assertIn("audit.action = 'provider.status_changed'", migration)
        self.assertIn("provider.status_repaired", migration)
        self.assertIn("migration-027", migration)
        self.assertNotIn("DELETE FROM map_provider", migration)

    def test_otm_pause_migration_preserves_explicit_activation_gate(self):
        migration = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "migrations"
            / "028_force_otm_beta8_paused.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("p.id = 'opentopomap'", migration)
        self.assertIn("p.status = 'ACTIVE'", migration)
        self.assertIn("SET status = 'PAUSED'", migration)
        self.assertIn("provider.status_repaired", migration)
        self.assertIn("migration-028", migration)
        self.assertIn("explicitActivationRequired", migration)

    def test_provider_compatibility_linkage_migration_is_allowlisted(self):
        migration = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "migrations"
            / "029_provider_neutral_compatibility_evidence.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("DROP CONSTRAINT compatibility_evidence_event_provider_check", migration)
        self.assertIn("provider IN ('freizeitkarte', 'opentopomap')", migration)
        self.assertNotIn("openmtbmap", migration)
        self.assertNotIn("DROP TABLE", migration)

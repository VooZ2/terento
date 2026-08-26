from __future__ import annotations

from contextlib import contextmanager
import inspect
from pathlib import Path
import unittest

from terento_catalog.admin import (
    _admin_device_payload,
    _render_diagnostic_details,
    _identity_comparison_key,
    _normalise_variant,
    _status_badge,
    campaign_links_page,
    dashboard_page,
    devices_page,
)
from terento_catalog.compatibility_status import (
    CANONICAL_STATUS_ORDER,
    CompatibilityStatus,
    calculate_compatibility_status,
)
from terento_catalog.db import Database


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "021_canonical_admin_semantics.sql"


class RecordingResult:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class RecordingDatabase(Database):
    def __init__(self, *, diagnostic_rows=None, identity_rows=None, canonical_row=None):
        super().__init__("unused")
        self.diagnostic_rows = diagnostic_rows or []
        self.identity_rows = identity_rows or []
        self.canonical_row = canonical_row
        self.calls = []

    @contextmanager
    def connection(self):
        database = self

        class Connection:
            def execute(self, query, parameters=None):
                database.calls.append((query, parameters))
                if "SELECT event_id, diagnostic_status" in query:
                    return RecordingResult(rows=database.diagnostic_rows)
                if "SELECT id, model, variant" in query:
                    return RecordingResult(row=database.canonical_row)
                if "SELECT event_id, compatibility_identity, canonical_device_model_id" in query:
                    return RecordingResult(rows=database.identity_rows)
                return RecordingResult()

        yield Connection()


class AdminSemanticsTests(unittest.TestCase):
    def test_variant_formatting_normalizes_sizes_without_dropping_functional_labels(self):
        self.assertEqual(
            _normalise_variant("47mm, Solar, inReach"),
            "47 mm, Solar, inReach",
        )

    def test_canonical_model_display_ignores_diacritic_only_difference(self):
        self.assertEqual(_identity_comparison_key("fēnix 8"), _identity_comparison_key("fenix 8"))
        self.assertNotEqual(_identity_comparison_key("fēnix 8"), _identity_comparison_key("fēnix 8 Pro"))

    def test_one_common_classifier_has_canonical_order_and_unknown_is_unavailable(self):
        self.assertEqual(
            tuple(status.value for status in CANONICAL_STATUS_ORDER),
            ("TESTING", "TESTED", "SUPPORTED", "VERIFIED"),
        )
        self.assertEqual(
            calculate_compatibility_status(
                successful_install_count=0,
                recognized_map_capable_evidence=True,
            ),
            CompatibilityStatus.TESTING,
        )
        self.assertIsNone(
            calculate_compatibility_status(
                successful_install_count=0,
                recognized_map_capable_evidence=False,
            )
        )
        self.assertIn("status-unavailable", _status_badge(""))
        self.assertIsNone(calculate_compatibility_status(successful_install_count=0))

    def test_dashboard_recomputes_status_and_does_not_trust_stale_view_status(self):
        body = dashboard_page(
            [{
                "model": "Future Garmin watch",
                "variant": "47 mm",
                "attempted_install_count": 1,
                "successful_install_count": 0,
                "failed_install_count": 0,
                "success_rate": 0,
                "calculated_status": "TESTING",
                "recognized_map_capable_evidence": False,
            }],
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("Unavailable", body)
        self.assertIn("data-status=''", body)
        self.assertNotIn("data-status='testing'", body)

    def test_installation_authorization_is_separate_from_compatibility_evidence(self):
        source = inspect.getsource(Database.update_device_support_status)
        self.assertIn("installation authorization", source)
        self.assertNotIn("compatibility_evidence_event", source)
        self.assertIn("device_authorization_audit", source)

    def test_resolve_and_reopen_persist_lifecycle_metadata_without_deleting_evidence(self):
        database = RecordingDatabase(
            diagnostic_rows=[{"event_id": "event-1", "diagnostic_status": "ACTIVE"}]
        )
        self.assertEqual(
            database.update_diagnostic_lifecycle(
                "operation-1",
                new_status="RESOLVED",
                admin_user_id=7,
                resolution_reason="FIXED",
                resolution_note="Verified after firmware update",
                linked_github_issue="#32",
            ),
            1,
        )
        resolve_update = next(query for query, _ in database.calls if "SET diagnostic_status = 'RESOLVED'" in query)
        self.assertIn("resolution_reason", resolve_update)
        self.assertIn("resolved_by", resolve_update)
        self.assertTrue(any("compatibility_diagnostic_lifecycle_audit" in query for query, _ in database.calls))
        self.assertFalse(any("DELETE FROM compatibility_evidence_event" in query for query, _ in database.calls))

        database.calls.clear()
        database.diagnostic_rows = [{"event_id": "event-1", "diagnostic_status": "RESOLVED"}]
        self.assertEqual(
            database.update_diagnostic_lifecycle(
                "operation-1",
                new_status="ACTIVE",
                admin_user_id=7,
            ),
            1,
        )
        self.assertTrue(any("SET diagnostic_status = 'ACTIVE'" in query for query, _ in database.calls))
        self.assertTrue(any("compatibility_diagnostic_lifecycle_audit" in query for query, _ in database.calls))

    def test_identity_assignment_is_explicit_and_audited_without_changing_outcome(self):
        database = RecordingDatabase(
            identity_rows=[{
                "event_id": "event-1",
                "compatibility_identity": "Identity pending · fēnix 7",
                "canonical_device_model_id": None,
            }],
            canonical_row={"id": "garmin-fenix-7-47", "model": "fēnix 7", "variant": "47 mm"},
        )
        self.assertEqual(
            database.resolve_compatibility_identity(
                "operation-1",
                action="ASSIGN",
                canonical_device_model_id="garmin-fenix-7-47",
                admin_user_id=7,
                reason="Exact model confirmed",
                note="Exact device confirmed by operator",
            ),
            1,
        )
        identity_update = next(query for query, _ in database.calls if "identity_resolution_state" in query)
        self.assertIn("canonical_device_model_id", identity_update)
        audit_call = next((query, params) for query, params in database.calls if "compatibility_identity_resolution_audit" in query)
        self.assertEqual(audit_call[1][3], "fēnix 7 · 47 mm")
        self.assertEqual(audit_call[1][6], "Exact model confirmed")
        self.assertFalse(any("phase_outcome" in query for query, _ in database.calls if "UPDATE compatibility_evidence_event" in query))

    def test_operation_level_aggregation_is_shared_by_admin_and_current_view(self):
        db_source = (ROOT / "src" / "terento_catalog" / "db.py").read_text(encoding="utf-8")
        migration = MIGRATION.read_text(encoding="utf-8")
        operation_group = "GROUP BY COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text)"
        self.assertIn(operation_group, db_source)
        self.assertIn("count(*) FILTER (WHERE o.write_started)", db_source)
        self.assertIn("operation_stats AS (", migration)
        self.assertIn("count(*) FILTER (WHERE o.write_started)", migration)
        self.assertIn("terento_compatibility_status(e.successful_install_count, dm.map_capable IS TRUE)", migration)
        self.assertIn(
            "terento_compatibility_status(successful_count BIGINT, recognized BOOLEAN)",
            migration,
        )

    def test_admin_vocabulary_and_accessible_sticky_tables_are_canonical(self):
        admin_source = (ROOT / "src" / "terento_catalog" / "admin.py").read_text(encoding="utf-8")
        body = devices_page([], None, {"username": "operator"}, "csrf").decode()
        for label in (
            "Installation authorization", "Compatibility status", "Last evidence",
            "aria-label=\"Map capability\"", "aria-label=\"Installation authorization\"",
            "aria-label=\"Successful installations\"", "position:sticky", "z-index:3",
        ):
            self.assertIn(label, body if "aria-label" in label or "position:" in label or "z-index" in label else admin_source)
        self.assertIn("sticky", admin_source)
        self.assertNotIn("Support decision", body)
        self.assertNotIn("Evidence status", body)
        self.assertNotIn("Last tested", body)

    def test_modal_campaign_and_timezone_details_keep_the_refined_workflows(self):
        devices_body = devices_page([], None, {"username": "operator"}, "csrf").decode()
        campaign_body = campaign_links_page({"username": "operator"}, "csrf").decode()
        dashboard_body = dashboard_page([], {"username": "operator"}, "csrf").decode()
        for label in ("Identity", "Capability &amp; authorization", "Compatibility evidence", "Catalog"):
            self.assertIn(label, devices_body)
        self.assertIn("VID ${value(identity.vendorId)}", devices_body)
        self.assertIn("0x${Number(number).toString(16)", devices_body)
        self.assertIn("Not known", devices_body)
        self.assertIn("No exact USB identity is currently recorded", devices_body)
        self.assertIn("Operator review", devices_body)
        self.assertIn("Current authorization", devices_body)
        self.assertIn("Change to", devices_body)
        self.assertIn(">Save</button>", devices_body)
        self.assertIn("Garmin · exact model", devices_body)
        self.assertIn("Official product media", devices_body)
        self.assertIn("placeholder=\"garmin maps\"", campaign_body)
        self.assertIn("Usually used for paid-search keywords or targeting", campaign_body)
        self.assertIn("syncPresetLabel", campaign_body)
        self.assertNotIn('value="47mm"', campaign_body)
        positions = [dashboard_body.index(f">{status.title()}<") for status in ("TESTING", "TESTED", "SUPPORTED", "VERIFIED")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Time zone", devices_body)
        self.assertIn("Europe/Vilnius", devices_body)

    def test_diagnostics_use_compact_summary_and_secondary_technical_details(self):
        result = {
            "operation_key": "legacy:diagnostic-1",
            "event_id": "diagnostic-1",
            "occurred_at": "2026-08-25T16:04:00+00:00",
            "compatibility_identity": "Identity pending · fēnix 8 Pro · 51 mm",
            "release_label": "beta",
            "app_build": "2244",
            "region": "DEU+",
            "phase_outcome": "FAILED",
            "failure_stage": "write",
            "failure_code": "SEND_OBJECT_FAILED",
            "native_failure_code": "LIBMTP_ERROR_IO",
            "write_started": True,
            "remote_object_created": False,
            "cleanup_attempted": False,
            "cleanup_succeeded": None,
            "transfer_progress_bucket": "25-50%",
            "map_result_index": 0,
            "selected_map_count": 1,
            "raw_mtp_model": "fenix 8 51mm",
            "identity_resolution_code": "GARMIN_UNIT_ID",
            "error_category": "transport",
            "transport": "MTP",
            "diagnostic_status": "ACTIVE",
            "linked_github_issue": "#32",
        }
        body = _render_diagnostic_details(
            [result],
            identities=None,
            heading="Diagnostics",
            summary_prefix="",
            csrf_token="csrf",
        )
        self.assertIn("Region</th><th scope='col'>Result</th><th scope='col'>Stage</th><th scope='col'>Code</th><th scope='col'>Write</th><th scope='col'>Cleanup", body)
        self.assertNotIn("<th scope='col'>Raw MTP model", body)
        self.assertIn("Technical details · map result 1", body)
        self.assertIn("Raw MTP model", body)
        self.assertIn("Diagnostic ID: <code>legacy:diagnostic-1</code>", body)
        self.assertIn("diagnostic-chip", body)
        self.assertIn("Issue #32", body)
        self.assertIn("Failed", body)
        self.assertIn("Yes", body)
        self.assertIn("Not attempted", body)

    def test_historical_diagnostics_keep_the_same_summary_and_separate_group_metadata(self):
        result = {
            "operation_key": "operation-32",
            "event_id": "event-32",
            "compatibility_identity": "Identity pending · fēnix 8 Pro · 51 mm",
            "region": "FRA+",
            "phase_outcome": "SUCCEEDED",
            "write_started": True,
            "cleanup_attempted": True,
            "cleanup_succeeded": True,
            "map_result_index": 0,
            "diagnostic_status": "RESOLVED",
            "resolution_reason": "FIXED",
            "linked_github_issue": "#32",
        }
        body = _render_diagnostic_details(
            [result],
            identities=None,
            heading="Resolved / historical diagnostics",
            summary_prefix="",
            csrf_token="csrf",
        )
        self.assertIn("fēnix 8 Pro · 51 mm", body)
        self.assertIn("Identity pending", body)
        self.assertIn("1 diagnostic", body)
        self.assertNotIn("Resolved / historical · Identity pending", body)
        self.assertIn("<th scope='col'>Region</th>", body)
        self.assertIn("Technical details · map result 1", body)

    def test_migration_is_additive_and_keeps_historical_records_active(self):
        migration = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE compatibility_evidence_event", migration)
        self.assertIn("CREATE TABLE compatibility_diagnostic_lifecycle_audit", migration)
        self.assertIn("CREATE TABLE compatibility_identity_resolution_audit", migration)
        self.assertIn("CREATE TABLE device_authorization_audit", migration)
        self.assertIn("WHERE collector_managed = TRUE", (ROOT / "src" / "terento_catalog" / "db.py").read_text(encoding="utf-8"))
        self.assertNotIn("UPDATE device_model\nSET active = FALSE", migration)
        self.assertIn("WHEN successful_count < 3 THEN ''TESTED''", migration)
        self.assertIn("WHEN successful_count < 5 THEN ''SUPPORTED''", migration)
        self.assertNotIn("WHEN successful_count = 1 THEN ''SUPPORTED''", migration)
        self.assertNotIn("compatibility_evidence_event\nSET phase_outcome", migration)


if __name__ == "__main__":
    unittest.main()

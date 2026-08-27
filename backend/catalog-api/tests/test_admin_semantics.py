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
    diagnostics_page,
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
ALL_EVENTS_MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "024_count_all_installation_events.sql"
IDENTITY_STATE_MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "022_canonical_identity_state_consistency.sql"
PUBLIC_REVIEW_MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "023_public_compatibility_review_audit.sql"


class RecordingResult:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class RecordingDatabase(Database):
    def __init__(self, *, diagnostic_rows=None, identity_rows=None, canonical_row=None,
                 statistics_row=None, public_review_row=None):
        super().__init__("unused")
        self.diagnostic_rows = diagnostic_rows or []
        self.identity_rows = identity_rows or []
        self.canonical_row = canonical_row
        self.statistics_row = statistics_row
        self.public_review_row = public_review_row
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
                if "SELECT compatibility_identity, calculated_status" in query:
                    return RecordingResult(row=database.statistics_row)
                if "FROM compatibility_model_review" in query:
                    return RecordingResult(row=database.public_review_row)
                return RecordingResult()

        yield Connection()


class ReviewSummaryDatabase(Database):
    def __init__(self):
        super().__init__("unused")

    @contextmanager
    def connection(self):
        class Connection:
            def execute(self, query, parameters=None):
                return RecordingResult(row={
                    "installation_issues": 1,
                    "identity_pending": 2,
                    "ready_to_publish": 3,
                })

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

    def test_public_compatibility_review_is_explicit_audited_and_does_not_change_evidence(self):
        database = RecordingDatabase(
            canonical_row={
                "id": "garmin-fenix-8-pro-51-amoled",
                "model": "fēnix 8 Pro",
                "variant": "51 mm, AMOLED",
            },
            statistics_row={
                "compatibility_identity": "fēnix 8 Pro · 51 mm",
                "calculated_status": "TESTED",
            },
        )
        self.assertTrue(database.update_public_compatibility_review(
            "garmin-fenix-8-pro-51-amoled",
            action="PUBLISH",
            admin_user_id=7,
            note="Exact model reviewed",
        ))
        review_insert = next(
            (query, params) for query, params in database.calls
            if "INSERT INTO compatibility_model_review" in query
        )
        self.assertEqual(review_insert[1][0], "fēnix 8 Pro · 51 mm")
        self.assertEqual(review_insert[1][2:5], (
            "APPROVED", True, "fēnix 8 Pro · 51 mm, AMOLED",
        ))
        audit = next(
            (query, params) for query, params in database.calls
            if "INSERT INTO public_compatibility_review_audit" in query
        )
        self.assertEqual(audit[1][0], "garmin-fenix-8-pro-51-amoled")
        self.assertEqual(audit[1][7], "Exact model reviewed")
        mutating_queries = [
            query for query, _ in database.calls
            if query.lstrip().startswith("UPDATE") or query.lstrip().startswith("INSERT")
        ]
        self.assertFalse(any("compatibility_evidence_event" in query for query in mutating_queries))
        self.assertFalse(any("UPDATE device_model" in query for query in mutating_queries))

    def test_public_compatibility_publish_requires_eligible_evidence(self):
        database = RecordingDatabase(
            canonical_row={"id": "garmin-watch", "model": "Watch", "variant": "47 mm"},
            statistics_row=None,
        )
        with self.assertRaisesRegex(ValueError, "evidence is required"):
            database.update_public_compatibility_review(
                "garmin-watch", action="PUBLISH", admin_user_id=7,
            )
        self.assertFalse(any(
            "INSERT INTO compatibility_model_review" in query for query, _ in database.calls
        ))

    def test_public_review_migration_is_additive_and_audited(self):
        migration = PUBLIC_REVIEW_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE public_compatibility_review_audit", migration)
        self.assertIn("REFERENCES device_model(id) ON DELETE RESTRICT", migration)
        self.assertNotIn("DROP TABLE", migration)
        self.assertNotIn("DROP VIEW", migration)

    def test_needs_review_summary_counts_actionable_tasks(self):
        summary = ReviewSummaryDatabase().admin_review_summary()
        self.assertEqual(summary, {
            "installationIssues": 1,
            "identityPending": 2,
            "readyToPublish": 3,
            "total": 6,
        })
        source = inspect.getsource(Database.admin_review_summary)
        self.assertIn("diagnostic_status = 'ACTIVE'", source)
        self.assertIn("GROUP BY COALESCE(operation_id::text", source)
        self.assertIn("canonical_device_model_id IS NOT NULL", source)
        self.assertIn("review_status = 'PENDING'", source)
        self.assertIn("review_status = 'APPROVED' AND public_statistics_enabled = false", source)

    def test_shared_navigation_shows_actionable_review_breakdown(self):
        body = devices_page([], None, {
            "username": "operator",
            "admin_review_summary": {
                "installationIssues": 1,
                "identityPending": 2,
                "readyToPublish": 3,
                "total": 6,
            },
        }, "csrf").decode()
        self.assertIn('aria-label="Needs review: 6"', body)
        self.assertIn('class="needs-review-count">6</span>', body)
        self.assertIn("Installation issues</span><strong>1", body)
        self.assertIn("Identity pending</span><strong>2", body)
        self.assertIn("Ready to publish</span><strong>3", body)
        self.assertIn("needs-review-popover", body)

        zero_body = devices_page([], None, {
            "username": "operator",
            "admin_review_summary": {"total": 0},
        }, "csrf").decode()
        zero_header = zero_body[zero_body.index("<header"):zero_body.index("</header>")]
        self.assertNotIn("needs-review-menu", zero_header)

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
        migration = ALL_EVENTS_MIGRATION.read_text(encoding="utf-8")
        operation_group = "GROUP BY COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text)"
        self.assertIn(operation_group, db_source)
        self.assertIn("count(*) AS attempts", db_source)
        self.assertIn("count(*) FILTER (WHERE NOT o.operation_succeeded) AS failed", db_source)
        self.assertIn("operation_stats AS (", migration)
        self.assertIn("count(*) AS attempted_install_count", migration)
        self.assertIn("count(*) FILTER (WHERE NOT o.operation_succeeded) AS failed_install_count", migration)
        self.assertIn("terento_compatibility_status(e.successful_install_count, dm.map_capable IS TRUE)", migration)
        status_migration = MIGRATION.read_text(encoding="utf-8")
        self.assertIn(
            "terento_compatibility_status(successful_count BIGINT, recognized BOOLEAN)",
            status_migration,
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

    def test_shared_admin_header_keeps_three_zones_and_lightweight_utility_actions(self):
        body = devices_page([], None, {"username": "operator"}, "csrf").decode()

        self.assertIn(
            '<a class="admin-brand" href="/admin" aria-label="Terento admin home">',
            body,
        )
        self.assertNotIn('href="https://terento.app/" aria-label="Terento home"', body)
        self.assertIn('class="admin-header-zone admin-header-left"', body)
        self.assertIn('class="admin-section-nav" aria-label="Admin sections"', body)
        self.assertIn('class="admin-nav" aria-label="Admin navigation"', body)
        self.assertIn(
            'class="admin-website-link" href="https://terento.app/"',
            body,
        )
        self.assertIn('target="_blank" rel="noopener noreferrer"', body)
        self.assertIn('Website <span aria-hidden="true">↗</span>', body)
        self.assertIn('aria-label="Signed in as operator"', body)
        self.assertNotIn('>Account</a>', body)
        self.assertIn("Auto · ${browserTimeZone}", body)
        self.assertIn("Automatic browser time zone: ${browserTimeZone}", body)
        self.assertIn(
            "grid-template-columns:minmax(180px,1fr) max-content minmax(385px,1fr)",
            body,
        )

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
        self.assertIn("Installation authorization", devices_body)
        self.assertIn(">Current<", devices_body)
        self.assertIn("Change to", devices_body)
        self.assertIn('textarea name="note"', devices_body)
        self.assertIn("data-authorization-change", devices_body)
        self.assertIn("data-authorization-cancel", devices_body)
        self.assertIn(">Save</button>", devices_body)
        self.assertIn("disabled>Save</button>", devices_body)
        self.assertIn("Catalog details", devices_body)
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

    def test_dashboard_is_model_summary_only_and_errors_link_to_exact_drilldown(self):
        identity = "fēnix 8 · 51 mm, AMOLED"
        row = {
            "model": "fēnix 8",
            "variant": "51 mm, AMOLED",
            "compatibility_identity": identity,
            "attempted_install_count": 2,
            "successful_install_count": 1,
            "failed_install_count": 1,
            "success_rate": 50,
            "recognized_map_capable_evidence": True,
            "last_success": "2026-08-25T16:04:00+00:00",
            "last_evidence": "2026-08-25T16:05:00+00:00",
        }
        body = dashboard_page(
            [row],
            {"username": "operator"},
            "csrf",
            operations=[{
                "operation_key": "failed-operation",
                "compatibility_identity": identity,
                "phase_outcome": "FAILED",
                "failure_code": "SEND_OBJECT_FAILED",
                "identity_resolution_state": "RESOLVED",
            }],
            resolved_operations=[{
                "operation_key": "resolved-operation",
                "compatibility_identity": identity,
                "phase_outcome": "FAILED",
                "failure_code": "OLD_FAILURE",
                "diagnostic_status": "RESOLVED",
            }],
        ).decode()
        self.assertNotIn("class='metric'", body)
        self.assertIn('class="admin-summary-strip installation-summary-strip"', body)
        self.assertIn("2 attempts · 1 successful · 1 error", body)
        self.assertNotIn('id="evidence-title"', body)
        self.assertNotIn("<h2 id=\"evidence-title\">Installations</h2>", body)
        self.assertIn("1 error", body)
        self.assertIn("/admin/diagnostics?identity=f%C4%93nix+8+%C2%B7+51+mm%2C+AMOLED&amp;state=all", body)
        self.assertIn("data-diagnostics-url='/admin/diagnostics?identity=", body)
        self.assertIn("Most errors", body)
        self.assertIn("Latest activity", body)
        self.assertIn("Model name", body)
        self.assertNotIn("Diagnostic record", body)
        self.assertNotIn("Raw MTP model", body)
        self.assertNotIn("resolve-diagnostic-dialog", body)

    def test_dashboard_groups_raw_identity_variants_by_canonical_device(self):
        canonical_id = "garmin-fenix-8-47-amoled"
        row = {
            "model": "fēnix 8",
            "variant": "47 mm, AMOLED",
            "compatibility_identity": "fēnix 8 · 47 mm AMOLED",
            "canonical_device_model_id": canonical_id,
            "attempted_install_count": 5,
            "successful_install_count": 5,
            "failed_install_count": 0,
            "recognized_map_capable_evidence": True,
        }
        operations = [
            {
                "operation_key": f"operation-{index}",
                "compatibility_identity": identity,
                "canonical_device_model_id": canonical_id,
                "phase_outcome": "SUCCEEDED",
                "automatic_finishing_result": "VERIFIED",
                "identity_resolution_state": state,
            }
            for index, (identity, state) in enumerate((
                ("fēnix 8 · 47 mm AMOLED", "RESOLVED"),
                ("fēnix 8 · 47 mm, AMOLED", "UNRESOLVED"),
            ), start=1)
        ]
        body = dashboard_page(
            [row], {"username": "operator"}, "csrf", operations=operations,
        ).decode()
        self.assertIn("canonical_device_id=garmin-fenix-8-47-amoled", body)
        self.assertNotIn("Identity pending</span>", body)
        self.assertNotIn(" error</a>", body)

    def test_unresolved_identity_is_separate_from_numeric_errors(self):
        identity = "Unknown Garmin · 47 mm"
        body = dashboard_page(
            [{
                "model": "Unknown Garmin",
                "variant": "47 mm",
                "compatibility_identity": identity,
                "attempted_install_count": 1,
                "successful_install_count": 1,
                "recognized_map_capable_evidence": False,
            }],
            {"username": "operator"},
            "csrf",
            operations=[{
                "operation_key": "pending-success",
                "compatibility_identity": identity,
                "phase_outcome": "SUCCEEDED",
                "automatic_finishing_result": "VERIFIED",
                "identity_resolution_state": "UNRESOLVED",
            }],
        ).decode()
        evidence_row = body.split("class='evidence-model-row'", 1)[1].split("</tr>", 1)[0]
        self.assertIn("Identity pending", evidence_row)
        self.assertNotIn("error-count", evidence_row)
        self.assertIn("<td><span class='muted-value'>—</span></td>", evidence_row)

    def test_canonical_diagnostics_include_all_raw_identity_spellings(self):
        canonical_id = "garmin-fenix-8-47-amoled"
        events = [{
            "operation_key": f"operation-{index}",
            "event_id": f"event-{index}",
            "occurred_at": f"2026-08-25T1{index}:00:00+00:00",
            "compatibility_identity": identity,
            "canonical_device_model_id": canonical_id,
            "phase_outcome": "SUCCEEDED",
            "automatic_finishing_result": "VERIFIED",
            "identity_resolution_state": "RESOLVED",
            "write_started": True,
        } for index, identity in enumerate((
            "fēnix 8 · 47 mm AMOLED",
            "fēnix 8 · 47 mm, AMOLED",
        ), start=1)]
        body = diagnostics_page(
            [{
                "model": "fēnix 8",
                "variant": "47 mm, AMOLED",
                "compatibility_identity": "fēnix 8 · 47 mm AMOLED",
                "canonical_device_model_id": canonical_id,
                "attempted_install_count": 2,
                "successful_install_count": 2,
                "recognized_map_capable_evidence": True,
            }],
            {"username": "operator"}, "csrf",
            identity="fēnix 8 · 47 mm AMOLED",
            canonical_device_model_id=canonical_id,
            operations=events,
        ).decode()
        self.assertIn("2 records", body)
        self.assertIn("Diagnostic ID: <code>operation-1</code>", body)
        self.assertIn("Diagnostic ID: <code>operation-2</code>", body)
        self.assertIn("canonical_device_id=garmin-fenix-8-47-amoled", body)

    def test_diagnostics_page_separates_state_columns_and_collapsed_detail_actions(self):
        identity = "fēnix 8 · 51 mm, AMOLED"
        failed = {
            "operation_key": "failed-operation",
            "event_id": "event-failed",
            "occurred_at": "2026-08-25T16:04:00+00:00",
            "compatibility_identity": identity,
            "variant": "51 mm, AMOLED",
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
            "map_result_index": 0,
            "raw_mtp_model": "fenix 8 51mm",
            "identity_resolution_state": "RESOLVED",
            "canonical_device_model_id": "garmin-fenix-8-51-amoled",
            "linked_github_issue": "#32",
        }
        pending = {
            **failed,
            "operation_key": "pending-operation",
            "event_id": "event-pending",
            "phase_outcome": "SUCCEEDED",
            "failure_stage": None,
            "failure_code": None,
            "native_failure_code": None,
            "raw_mtp_model": "fenix 8 51mm",
            "identity_resolution_state": "UNRESOLVED",
            "canonical_device_model_id": None,
            "linked_github_issue": None,
        }
        succeeded = {
            **pending,
            "operation_key": "succeeded-operation",
            "event_id": "event-succeeded",
            "identity_resolution_state": "RESOLVED",
            "canonical_device_model_id": "garmin-fenix-8-51-amoled",
        }
        resolved = {**failed, "operation_key": "resolved-operation", "event_id": "event-resolved", "diagnostic_status": "RESOLVED", "linked_github_issue": None}
        body = diagnostics_page(
            [{
                "model": "fēnix 8",
                "variant": "51 mm, AMOLED",
                "compatibility_identity": identity,
                "attempted_install_count": 2,
                "successful_install_count": 1,
                "recognized_map_capable_evidence": True,
            }],
            {"username": "operator"},
            "csrf",
            identity=identity,
            operations=[failed, pending, succeeded],
            resolved_operations=[resolved],
            identity_devices=[{
                "id": "garmin-fenix-8-51-amoled",
                "model": "fēnix 8",
                "variant": "51 mm, AMOLED",
                "familyName": "fēnix",
            }],
        ).decode()
        table = body.split("class='diagnostic-list-table'", 1)[1].split("</table>", 1)[0]
        for label in ("Date", "Region", "Result", "Stage", "Code", "Issue", "Review", "Action"):
            self.assertIn(f">{label}<", table)
        self.assertNotIn("Raw MTP model", table)
        self.assertIn("Open", body)
        self.assertIn("Identity pending", body)
        self.assertIn("Resolved", body)
        self.assertIn(">Details</button>", body)
        self.assertIn("aria-label='View installation details", body)
        self.assertNotIn("aria-label='Review diagnostic", body)
        self.assertIn("Resolve diagnostic", body)
        self.assertIn("Reopen diagnostic", body)
        self.assertIn("HISTORICAL_SUPERSEDED", body)
        self.assertIn("Search model, family, variant, case size, or canonical ID", body)
        self.assertIn("Canonical ID:", body)
        self.assertIn("Create GitHub issue", body)
        self.assertIn("Link or create issue", body)
        self.assertEqual(body.count("github-review-collapsed"), 1)
        self.assertIn("Change linked issue", body)
        self.assertIn("Remove link", body)
        self.assertIn("#32 · Open", body)
        self.assertIn("Diagnostic ID:", body)
        self.assertIn("Technical details", body)
        self.assertIn("<option value='all' selected>All</option><option value='succeeded'>Succeeded</option><option value='failed'>Failed</option><option value='open'>Open</option><option value='resolved'>Resolved</option><option value='identity-pending'>Identity pending</option><option value='with-issue'>With issue</option>", body)
        self.assertEqual(body.count("action='/admin/diagnostics/resolve'"), 1)
        self.assertEqual(body.count("action='/admin/diagnostics/reopen'"), 1)
        self.assertEqual(body.count("action='/admin/diagnostics/identity'"), 1)
        self.assertIn("data-diagnostic-state='history'", body)
        self.assertIn("data-diagnostic-result='succeeded'", body)
        self.assertIn("new URLSearchParams(window.location.search).get('state')", body)
        self.assertIn("selected === 'succeeded'", body)
        self.assertIn("selected === 'failed'", body)
        self.assertIn("selected === 'open' && row.dataset.reviewOpen === 'true'", body)
        self.assertIn("selected === 'identity-pending' && row.dataset.identityPending === 'true'", body)

    def test_installations_helper_copy_is_concise_and_keeps_identity_out_of_errors(self):
        body = dashboard_page([], {"username": "operator"}, "csrf").decode()
        self.assertIn(
            "Attempts, successes, and errors include all retained installation operations. The Needs review queue contains only unresolved problems.",
            body,
        )
        self.assertNotIn("Errors are unresolved diagnostic operations", body)

    def test_issue_link_update_is_additive_and_does_not_change_evidence_outcome(self):
        source = inspect.getsource(Database.update_diagnostic_issue)
        self.assertIn("SET linked_github_issue = %s", source)
        self.assertNotIn("phase_outcome", source)
        self.assertNotIn("diagnostic_status =", source)

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

    def test_identity_state_backfill_is_scoped_and_audited(self):
        migration = IDENTITY_STATE_MIGRATION.read_text(encoding="utf-8")
        audit_position = migration.index("INSERT INTO compatibility_identity_resolution_audit")
        update_position = migration.index("UPDATE compatibility_evidence_event")
        self.assertLess(audit_position, update_position)
        self.assertIn("canonical_device_model_id IS NOT NULL", migration)
        self.assertIn("identity_resolution_state = 'UNRESOLVED'", migration)
        self.assertIn("NOT EXISTS", migration)
        for protected_field in (
            "phase_outcome =", "automatic_finishing_result =", "occurred_at =",
            "diagnostic_status =", "successful_install_count =",
        ):
            self.assertNotIn(protected_field, migration)


if __name__ == "__main__":
    unittest.main()

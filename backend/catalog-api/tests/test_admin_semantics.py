from __future__ import annotations

from contextlib import contextmanager
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.parse import parse_qs, urlsplit

from terento_catalog.admin import (
    GITHUB_ADMIN_NOTE_MAX_LENGTH,
    GITHUB_ISSUE_URL_MAX_LENGTH,
    _admin_device_payload,
    _admin_event_outcome_label,
    _admin_map_display_name,
    _admin_timezone_script,
    _campaign_links_script,
    _client_issue_note_sanitizer_script,
    _dashboard_script,
    _device_last_success_comparator_script,
    _devices_script,
    _diagnostic_summary_by_identity,
    _diagnostics_script,
    _github_issue_report,
    _github_issue_url,
    _render_diagnostic_details,
    _sanitised_issue_value,
    _identity_comparison_key,
    _map_statistics_summary,
    _normalise_variant,
    _overview_period_script,
    _map_statistics_script,
    _provider_detail_script,
    format_timestamp,
    _providers_list_script,
    _status_badge,
    campaign_links_page,
    dashboard_page,
    device_detail_page,
    diagnostics_page,
    devices_page,
    map_statistics_page,
    overview_page,
    provider_detail_page,
    providers_page,
)
from terento_catalog.compatibility_status import (
    CANONICAL_STATUS_ORDER,
    CompatibilityStatus,
    calculate_compatibility_status,
)
from terento_catalog.db import Database, _fill_overview_trend_buckets


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "021_canonical_admin_semantics.sql"
CURRENT_MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "025_device_card_failure_epoch.sql"
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
    @staticmethod
    def _node() -> str:
        node = shutil.which("node") or shutil.which("nodejs")
        if not node:
            raise AssertionError("Node.js is required for Admin JavaScript regression tests")
        return node

    def _run_node(self, source: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._node(), "-e", source, *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_every_generated_admin_script_passes_node_syntax_check(self):
        scripts = {
            "dashboard": _dashboard_script(),
            "devices": _devices_script(),
            "diagnostics-and-model": _diagnostics_script(),
            "timezone": _admin_timezone_script(),
            "campaign-links": _campaign_links_script(),
            "providers": _providers_list_script(),
            "provider-detail": _provider_detail_script(),
            "map-statistics": _map_statistics_script(),
            "overview-period": _overview_period_script(),
        }
        for name, script in scripts.items():
            with self.subTest(script=name):
                result = subprocess.run(
                    [self._node(), "--check"], input=script,
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_overview_does_not_turn_missing_evidence_into_zero(self):
        body = overview_page(
            {
                "period": "24h",
                "data": {
                    "eventCount": 0,
                    "completedInstallCount": 0,
                    "failedInstallCount": 0,
                    "installSuccessRate": None,
                    "hasData": False,
                    "recentActivity": [],
                    "attention": [],
                    "trend": [],
                    "bucket": "hour",
                },
                "compatibility": {"hasData": False, "openErrorCount": 0, "recentActivity": [], "failureReasons": []},
                "providers": [{"id": "freizeitkarte", "name": "Freizeitkarte", "health": "HEALTHY"}],
            },
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("<h1>Overview</h1>", body)
        self.assertIn("<span>Map install operations</span><strong>—</strong>", body)
        self.assertIn("<span>Failed map operations</span><strong>—</strong>", body)
        self.assertIn("<span>Open errors</span><strong>—</strong>", body)
        self.assertIn("No map activity in this period.", body)

    def test_overview_uses_existing_operation_and_provider_drill_downs(self):
        body = overview_page(
            {
                "period": "7d",
                "data": {
                    "eventCount": 4,
                    "completedInstallCount": 3,
                    "failedInstallCount": 1,
                    "installSuccessRate": 75,
                    "hasData": True,
                    "recentActivity": [{
                        "event_type": "INSTALL_FAILED",
                        "outcome": "FAILED",
                        "display_name": "Germany",
                        "map_package_id": "freizeitkarte-germany",
                        "region": "DE",
                        "provider_id": "freizeitkarte",
                        "provider_name": "Freizeitkarte",
                        "occurred_at": "2026-09-01T07:00:00+00:00",
                    }],
                    "attention": [],
                    "trend": [{"bucket": "2026-09-01T07:00:00+00:00", "success_count": 3, "failed_count": 1}],
                    "bucket": "day",
                },
                "compatibility": {
                    "operationCount": 2,
                    "failedInstallCount": 1,
                    "openErrorCount": 1,
                    "hasData": True,
                    "recentActivity": [{
                        "canonical_device_model_id": None,
                        "compatibility_identity": "fēnix 8 · 47 mm",
                        "model": "fēnix 8",
                        "variant": "47 mm",
                        "provider": "freizeitkarte",
                        "error_category": "transport",
                        "has_failed": True,
                        "has_not_started": False,
                        "operation_succeeded": False,
                        "open_error": True,
                        "last_occurred_at": "2026-09-01T07:00:00+00:00",
                    }],
                    "failureReasons": [{"reason": "transport", "count": 1}],
                    "writeStartedCount": 2,
                    "variantCount": 1,
                    "evidenceSuccessRate": 50,
                },
                "providers": [{"id": "opentopomap", "name": "OpenTopoMap", "health": "DEGRADED"}],
            },
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("Last 7 days", body)
        self.assertIn("Install failed", body)
        self.assertIn("Device transport", body)
        self.assertIn("/admin/diagnostics?identity=f%C4%93nix+8+%C2%B7+47+mm&amp;state=failed", body)
        self.assertIn("/admin/providers/opentopomap", body)
        self.assertIn("OpenTopoMap health Degraded", body)
        self.assertIn("<span>Map install operations</span><strong>4</strong>", body)
        self.assertIn("<span>Map operation success</span><strong>75%</strong>", body)
        self.assertIn("<span>Failed map operations</span><strong>1</strong>", body)
        self.assertIn("<span>Open errors</span><strong>1</strong>", body)
        self.assertIn("<span>Write-started attempts</span><strong>2</strong>", body)
        self.assertIn("<span>Variants</span><strong>1</strong>", body)
        self.assertIn("<span>Evidence success</span><strong>50%</strong>", body)
        self.assertIn("Map install operations over time", body)
        self.assertIn("overview-chart-success", body)
        self.assertIn("viewBox='0 0 720 190'", body)
        self.assertIn("overview-chart-panel", body)
        self.assertIn("Recent map activity", body)
        self.assertIn("Compatibility evidence", body)
        self.assertNotIn("Pending metric definition", body)
        self.assertNotIn("<span>Success rate</span>", body)

    def test_overview_presents_model_activity_and_exact_period_vocabulary(self):
        body = overview_page(
            {
                "period": "24h",
                "data": {"hasData": False, "recentActivity": [], "attention": [], "trend": [], "bucket": "hour"},
                "compatibility": {
                    "hasData": True,
                    "modelActivity": [{
                        "model": "fēnix 8", "variant": "47 mm, AMOLED",
                        "operation_count": 2, "successful_count": 1,
                        "failed_count": 1, "open_error_count": 1,
                        "last_occurred_at": "2026-09-01T07:00:00+00:00",
                    }],
                    "reviewRequired": [{"model": "Forerunner 965", "review_status": "PENDING"}],
                    "recentActivity": [], "failureReasons": [],
                    "writeStartedCount": 2, "variantCount": 1, "evidenceSuccessRate": 50,
                },
                "providers": [],
            },
            {"username": "operator"}, "csrf",
        ).decode()
        self.assertIn("Device/model activity", body)
        self.assertIn("fēnix 8 · 47 mm, AMOLED", body)
        self.assertIn("New / review-required devices", body)
        self.assertIn("Needs attention", body)
        self.assertIn("Review required", body)
        self.assertIn("Last 24 hours", body)
        self.assertNotIn("build", body.lower())

    def test_overview_hides_unlinked_model_activity_panel(self):
        body = overview_page(
            {
                "period": "7d",
                "data": {"hasData": True, "completedInstallCount": 1, "recentActivity": [], "attention": [], "trend": [], "bucket": "day"},
                "compatibility": {"hasData": False, "modelActivity": [], "reviewRequired": [], "recentActivity": [], "failureReasons": []},
                "providers": [],
            },
            {"username": "operator"}, "csrf",
        ).decode()
        self.assertNotIn("overview-model-title", body)
        self.assertIn("overview-primary-grid-single", body)
        self.assertIn("overview-secondary-grid-single", body)

    def test_overview_period_control_updates_without_hard_reload(self):
        body = overview_page(
            {
                "period": "30d",
                "data": {"hasData": False, "recentActivity": [], "attention": [], "trend": [], "bucket": "day"},
                "compatibility": {"hasData": False, "modelActivity": [], "reviewRequired": [], "recentActivity": [], "failureReasons": []},
                "providers": [],
            },
            {"username": "operator"}, "csrf",
        ).decode()
        self.assertIn("class='filter-bar overview-period-form'", body)
        self.assertIn("id='overview-period'", body)
        self.assertIn("window.history.pushState", body)
        self.assertIn("fetch(url", body)
        self.assertNotIn("onchange='this.form.submit()'", body)
        self.assertIn("value='30d' selected", body)
        self.assertIn("overview-attention-empty", body)
        self.assertIn("overview-provider-panel", body)

    def test_overview_trend_fills_selected_range_without_fabricating_events(self):
        event_bucket = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
        row = {"bucket": event_bucket, "success_count": 1, "failed_count": 0}
        hourly = _fill_overview_trend_buckets(
            [row], bucket="hour",
            since=datetime(2026, 9, 1, 6, 30, tzinfo=timezone.utc),
            until=datetime(2026, 9, 1, 10, 10, tzinfo=timezone.utc),
        )
        daily = _fill_overview_trend_buckets(
            [row], bucket="day",
            since=datetime(2026, 8, 26, 12, tzinfo=timezone.utc),
            until=datetime(2026, 9, 1, 10, tzinfo=timezone.utc),
        )
        all_time = _fill_overview_trend_buckets(
            [row], bucket="day",
            since=datetime(1970, 1, 1, tzinfo=timezone.utc),
            until=datetime(2026, 9, 3, tzinfo=timezone.utc),
            all_time=True,
        )
        self.assertEqual(len(hourly), 5)
        self.assertEqual(sum(item["success_count"] for item in hourly), 1)
        self.assertEqual(len(daily), 7)
        self.assertEqual(sum(item["success_count"] for item in daily), 1)
        self.assertEqual(len(all_time), 3)
        self.assertEqual(sum(item["success_count"] for item in all_time), 1)

    def test_admin_map_labels_are_human_and_unknown_outcomes_are_neutral(self):
        self.assertEqual(_admin_map_display_name("PRINCIPALITY_OF_ANDORRA"), "Andorra")
        self.assertEqual(_admin_map_display_name("SWITZERLAND"), "Switzerland")
        self.assertEqual(_admin_map_display_name("Republic of Albania"), "Albania")
        self.assertEqual(_admin_map_display_name("Kingdom of Belgium"), "Belgium")
        self.assertEqual(_admin_map_display_name("Region Belgium - Netherlands - Luxembourg"), "Belgium – Netherlands – Luxembourg")
        self.assertEqual(_admin_event_outcome_label("UNKNOWN"), "—")
        self.assertEqual(_admin_event_outcome_label("SUCCEEDED"), "Succeeded")

        body = map_statistics_page(
            {"rows": []}, [], {"username": "operator"}, "csrf",
            selected_filters={"period": "24h"},
        ).decode()
        self.assertIn("Last 24 hours", body)
        self.assertIn("Activity by provider", body)
        popular_maps = body.split("id='map-statistics-popularity'", 1)[1].split("popularity-regions-disclosure", 1)[0]
        self.assertIn("<th scope='col'>Package installs</th>", popular_maps)
        self.assertNotIn("<h2>Downloads per provider</h2>", body)
        self.assertNotIn("<th scope='col'>Completed map-package installs</th>", popular_maps)
        self.assertNotIn("90 days", body)

    def test_admin_timestamps_repair_legacy_missing_separator(self):
        self.assertEqual(format_timestamp("2026-08-2123:51"), "2026-08-21 23:51")
        self.assertIn(
            "value.trim().replace(/^(\\d{4}-\\d{2}-\\d{2})(\\d{2}:\\d{2}",
            _map_statistics_script(),
        )
        body = provider_detail_page(
            {"provider": {
                "id": "freizeitkarte", "name": "Freizeitkarte",
                "status": "ACTIVE", "healthStatus": "HEALTHY",
                "lastCatalogSync": "2026-08-2123:51",
                "lastHealthCheck": "2026-08-3119:49",
                "maps": [], "sources": [], "healthHistory": [],
                "activationGate": {"canActivate": True, "blockers": []},
            }}, [], [{
                "admin_user_id": 1, "action": "provider.status_changed",
                "occurred_at": "2026-08-3119:49", "target": 3,
            }], {"username": "operator"}, "csrf",
        ).decode()
        self.assertNotRegex(body, r"\d{4}-\d{2}-\d{2}\d{2}:\d{2}")
        self.assertIn("2026-08-21 23:51", body)
        self.assertIn("2026-08-31 19:49", body)

    def test_map_overview_uses_a_server_compatible_bucket_expression(self):
        database = RecordingDatabase()
        since = datetime(2026, 9, 1, tzinfo=timezone.utc)

        snapshot = database.admin_overview_map_snapshot(since, period="7d")

        self.assertEqual(snapshot["bucket"], "day")
        trend_query, trend_parameters = next(
            (query, parameters)
            for query, parameters in database.calls
            if "GROUP BY" in query and "success_count" in query
        )
        self.assertIn("date_trunc('day', e.occurred_at)", trend_query)
        self.assertNotIn("date_trunc(%s", trend_query)
        self.assertEqual(trend_parameters, (since,))

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
        db_source = inspect.getsource(Database.admin_device_snapshot)
        migration = CURRENT_MIGRATION.read_text(encoding="utf-8")
        operation_group = "GROUP BY COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text)"
        self.assertIn(operation_group, db_source)
        self.assertIn("compatibility_device_card_failure_epoch AS epoch", db_source)
        self.assertIn("WHERE o.operation_succeeded OR o.received_at >= epoch.starts_at", db_source)
        self.assertIn(
            "WHERE NOT o.operation_succeeded AND o.received_at >= epoch.starts_at",
            db_source,
        )
        self.assertNotIn("e.diagnostic_status = 'ACTIVE'", db_source)
        self.assertIn("operation_stats AS (", migration)
        self.assertIn("starts_at TIMESTAMPTZ NOT NULL DEFAULT now()", migration)
        self.assertIn("WHERE e.diagnostic_status = 'ACTIVE'", migration)
        self.assertIn("count(*) FILTER (WHERE o.write_started) AS attempted_install_count", migration)
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
            "Installation authorization", "Compatibility status", "Last success",
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
            "grid-template-columns:minmax(300px,1fr) max-content minmax(335px,1fr)",
            body,
        )

    def test_modal_campaign_and_timezone_details_keep_the_refined_workflows(self):
        devices_body = devices_page([], None, {"username": "operator"}, "csrf").decode()
        device = _admin_device_payload([{
            "device_id": "garmin-fenix-8-47-amoled", "model": "fēnix 8",
            "variant": "47 mm, AMOLED", "family_name": "fēnix", "map_capable": True,
            "support_status": "SUPPORTED", "active": True,
            "attempted_install_count": 0, "successful_install_count": 0,
            "failed_install_count": 0, "usb_identities": [],
        }], None)["devices"][0]
        detail_body = device_detail_page(
            device, {"username": "operator"}, "csrf",
        ).decode()
        campaign_body = campaign_links_page({"username": "operator"}, "csrf").decode()
        dashboard_body = dashboard_page([], {"username": "operator"}, "csrf").decode()
        for label in ("Installation history", "Administration", "Device information", "Technical details"):
            self.assertIn(label, detail_body)
        self.assertIn("id='diagnostic-history-pagination'", detail_body)
        self.assertIn("data-history-page='previous'", detail_body)
        self.assertIn("data-history-page='next'", detail_body)
        self.assertIn("id='diagnostic-history-page-size'", detail_body)
        self.assertIn("Installation authorization", detail_body)
        self.assertIn('textarea name=\'note\'', detail_body)
        self.assertIn("Save authorization", detail_body)
        self.assertIn("Garmin device", detail_body)
        self.assertNotIn("Change history", detail_body)
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
            "canonical_device_model_id": "garmin-fenix-8-51-amoled",
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
                "canonical_device_model_id": "garmin-fenix-8-51-amoled",
                "phase_outcome": "FAILED",
                "failure_code": "SEND_OBJECT_FAILED",
                "identity_resolution_state": "RESOLVED",
            }, {
                "operation_key": "successful-operation",
                "compatibility_identity": identity,
                "canonical_device_model_id": "garmin-fenix-8-51-amoled",
                "phase_outcome": "SUCCEEDED",
                "automatic_finishing_result": "VERIFIED",
                "identity_resolution_state": "RESOLVED",
            }],
            resolved_operations=[{
                "operation_key": "resolved-operation",
                "compatibility_identity": identity,
                "canonical_device_model_id": "garmin-fenix-8-51-amoled",
                "phase_outcome": "FAILED",
                "failure_code": "OLD_FAILURE",
                "diagnostic_status": "RESOLVED",
            }],
        ).decode()
        self.assertNotIn("class='metric'", body)
        self.assertIn('class="admin-kpi-grid installation-kpis"', body)
        self.assertIn("<span>Write-started attempts</span><strong>3</strong>", body)
        self.assertIn("<span>Successful</span><strong>1</strong>", body)
        self.assertIn("<span>Evidence success</span><strong>33.3%</strong>", body)
        self.assertIn("Historical failures: 1", body)
        self.assertNotIn('id="evidence-title"', body)
        self.assertNotIn("<h2 id=\"evidence-title\">Installations</h2>", body)
        self.assertIn("1 open error", body)
        self.assertIn("/admin/devices/garmin-fenix-8-51-amoled?from=installations&amp;state=open#installations", body)
        self.assertIn("data-diagnostics-url='/admin/devices/garmin-fenix-8-51-amoled?from=installations#installations'", body)
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
        self.assertIn("/admin/devices/garmin-fenix-8-47-amoled?from=installations#installations", body)
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
        self.assertIn("historical-number'>0</td>", evidence_row)

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
        self.assertIn("Prepare GitHub issue", body)
        self.assertIn("Copy issue report", body)
        self.assertIn("Link issue", body)
        self.assertEqual(body.count("github-review-collapsed"), 1)
        self.assertIn("Change linked issue", body)
        self.assertIn("Unlink issue", body)
        self.assertIn("#32 <span aria-hidden='true'>↗</span>", body)
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
        self.assertIn("if (event.key === 'Escape')", body)
        self.assertIn("close(dialog)", body)

    def test_installations_helper_copy_is_concise_and_keeps_identity_out_of_errors(self):
        body = dashboard_page([], {"username": "operator"}, "csrf").decode()
        self.assertIn("Historical failures: 0", body)
        self.assertNotIn("Errors are unresolved diagnostic operations", body)

    def test_beta8_installations_summary_uses_five_kpis_and_historical_failure_note(self):
        body = dashboard_page(
            [{
                "model": "fēnix 8",
                "variant": "47 mm, AMOLED",
                "attempted_install_count": 3,
                "successful_install_count": 2,
                "failed_install_count": 2,
                "recognized_map_capable_evidence": True,
            }],
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("<p class=\"eyebrow\">Compatibility</p>", body)
        self.assertIn('class="admin-kpi-grid installation-kpis"', body)
        for label in ("Variants", "Write-started attempts", "Successful", "Evidence success", "Open errors"):
            self.assertIn(f"<span>{label}</span>", body)
        self.assertIn("<span>Successful</span><strong>2</strong>", body)
        self.assertIn("<span>Evidence success</span><strong>66.7%</strong>", body)
        self.assertIn("Historical failures: 2", body)
        self.assertIn("<th scope=\"col\">Status</th><th scope=\"col\">Attempts</th><th scope=\"col\">Successful</th>", body)
        self.assertNotIn("installation-summary-strip", body)

    def test_map_statistics_does_not_render_event_derived_zeros_without_data(self):
        self.assertEqual(
            _map_statistics_summary([]),
            {
                "hasEventData": False,
                "eventGroupCount": 0,
                "eventCount": None,
                "completedDownloads": None,
                "failedDownloads": None,
                "downloadAttempts": None,
                "downloadSuccessRate": None,
                "completedInstalls": None,
                "failedInstalls": None,
                "installAttempts": None,
                "installSuccessRate": None,
            },
        )
        body = map_statistics_page(
            {"rows": []},
            [{"id": "freizeitkarte", "name": "Freizeitkarte", "health": "HEALTHY"}],
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("No map operation data yet", body)
        self.assertIn("<strong data-stat='completedDownloads'>—</strong>", body)
        self.assertIn("<strong data-stat='failedDownloads'>—</strong>", body)
        self.assertIn("<strong data-stat='completedInstalls'>—</strong>", body)
        self.assertIn("<strong data-stat='failedInstalls'>—</strong>", body)
        self.assertIn("<section class='provider-card map-events-card' hidden>", body)
        self.assertIn("id='map-statistics-more-filters'", body)
        self.assertNotIn("<strong data-stat='completedDownloads'>0</strong>", body)

    def test_map_statistics_shows_zero_counts_only_when_event_data_exists(self):
        body = map_statistics_page(
            {"rows": [{
                "provider_id": "freizeitkarte",
                "event_type": "DOWNLOAD_STARTED",
                "outcome": "STARTED",
                "operation_count": 1,
            }]},
            [{"id": "freizeitkarte", "name": "Freizeitkarte", "health": "HEALTHY"}],
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("<strong data-stat='completedDownloads'>0</strong>", body)
        self.assertIn("<strong data-stat='failedDownloads'>0</strong>", body)
        self.assertIn("map-statistics-empty' id='map-statistics-empty' hidden", body)
        self.assertNotIn("map-events-card' hidden", body)

    def test_map_statistics_counts_failed_installations_and_scopes_provider_health(self):
        rows = [
            {
                "provider_id": "opentopomap",
                "event_type": "DOWNLOAD_SUCCEEDED",
                "outcome": "SUCCEEDED",
                "event_count": 6,
                "operation_count": 6,
            },
            {
                "provider_id": "opentopomap",
                "event_type": "DOWNLOAD_FAILED",
                "outcome": "FAILED",
                "event_count": 2,
                "operation_count": 2,
            },
            {
                "provider_id": "opentopomap",
                "event_type": "INSTALL_SUCCEEDED",
                "outcome": "SUCCEEDED",
                "event_count": 4,
                "operation_count": 4,
            },
            {
                "provider_id": "opentopomap",
                "event_type": "INSTALL_FAILED",
                "outcome": "FAILED",
                "event_count": 2,
                "operation_count": 2,
            },
            {
                "provider_id": "opentopomap",
                "event_type": "DOWNLOAD_STARTED",
                "outcome": "UNKNOWN",
                "event_count": 6,
                "operation_count": 6,
            },
        ]
        self.assertEqual(
            _map_statistics_summary(rows),
            {
                "hasEventData": True,
                "eventGroupCount": 5,
                "eventCount": 20,
                "completedDownloads": 6,
                "failedDownloads": 2,
                "downloadAttempts": 8,
                "downloadSuccessRate": 75.0,
                "completedInstalls": 4,
                "failedInstalls": 2,
                "installAttempts": 6,
                "installSuccessRate": 4 / 6 * 100,
            },
        )
        body = map_statistics_page(
            {"rows": rows},
            [
                {"id": "freizeitkarte", "name": "Freizeitkarte", "health": "HEALTHY"},
                {"id": "opentopomap", "name": "OpenTopoMap", "health": "HEALTHY"},
            ],
            {"username": "operator"},
            "csrf",
            selected_filters={"provider": "opentopomap"},
        ).decode()
        self.assertIn("5 event groups · 20 event records", body)
        self.assertIn("<strong data-stat='completedDownloads'>6</strong>", body)
        self.assertIn("<strong data-stat='failedInstalls'>2</strong>", body)
        self.assertIn("<strong data-stat='installSuccessRate'>66.7%</strong>", body)
        self.assertIn("<strong data-stat='providerHealth'>1 / 1 healthy</strong>", body)
        self.assertIn("<em data-stat='providerHealthIssues'> · 0 issues</em>", body)

        script = _map_statistics_script()
        self.assertIn("set('failedInstalls', hasEventData ? failedInstalls : '—')", script)
        self.assertIn("const scopedProviders = selectedProvider ? providers.filter", script)

    def test_map_statistics_exposes_operation_id_watch_linkage(self):
        linkage = {
            "mapOperationCount": 6,
            "mapInstallationCount": 4,
            "linkedOperationCount": 4,
            "linkedInstallationCount": 3,
            "mapOnlyInstallationCount": 1,
            "linkedWriteStartedInstallCount": 3,
            "linkedSuccessfulInstallCount": 2,
            "linkedFailedInstallCount": 1,
            "linkedPrewriteFailureCount": 0,
            "linkageRate": 75.0,
        }
        body = map_statistics_page(
            {
                "rows": [{
                    "provider_id": "opentopomap",
                    "event_type": "INSTALL_SUCCEEDED",
                    "outcome": "SUCCEEDED",
                    "event_count": 4,
                    "operation_count": 4,
                }],
                "linkage": linkage,
            },
            [{"id": "opentopomap", "name": "OpenTopoMap", "health": "HEALTHY"}],
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("Watch event linkage", body)
        self.assertIn("DATA QUALITY · Watch event linkage", body)
        self.assertIn("id='map-rows'", body)
        self.assertIn("View all maps", body)
        self.assertIn("<h3>Top maps</h3>", body)
        self.assertIn("Map install operations</span><strong data-stat='mapInstallationCount'>4", body)
        self.assertIn("Linked watch events</span><strong data-stat='linkedInstallationCount'>3", body)
        self.assertIn("Unlinked installs</span><strong data-stat='mapOnlyInstallationCount'>1", body)
        self.assertIn("Linkage coverage</span><strong data-stat='linkageRate'>75%", body)
        self.assertIn("Watch-confirmed failures</span><strong data-stat='linkedFailedInstallCount'>1", body)

        script = _map_statistics_script()
        self.assertIn("const linkage = payload.linkage || {};", script)
        self.assertIn("set('linkedSuccessfulInstallCount', linkageValue('linkedSuccessfulInstallCount'))", script)

    def test_map_statistics_linkage_query_joins_only_shared_operation_ids(self):
        source = inspect.getsource(Database.map_statistics_linkage)
        self.assertIn("FROM map_download_event AS e", source)
        self.assertIn("FROM compatibility_evidence_event AS e", source)
        self.assertIn("ON c.operation_id = m.operation_id", source)
        self.assertIn("AND c.provider_id = m.provider_id", source)
        self.assertIn("GROUP BY e.operation_id", source)
        self.assertIn("map_only_installation_count", source)
        self.assertIn("linked_failed_install_count", source)
        self.assertIn("count(*) FILTER (WHERE has_install_event)", source)

    def test_provider_list_uses_compact_columns_and_summary(self):
        body = providers_page(
            [{
                "id": "opentopomap",
                "name": "OpenTopoMap",
                "adapterId": "opentopomap",
                "status": "PAUSED",
                "health": "HEALTHY",
                "packageCount": 177,
                "lastCatalogSync": "2026-08-31T12:00:00+00:00",
                "lastHealthCheck": "2026-08-31T12:05:00+00:00",
            }],
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("1 providers", body)
        self.assertIn("0 active · 1 healthy · 177 packages · 0 issues", body)
        self.assertIn("<th scope='col'>Provider</th><th scope='col'>Activity</th><th scope='col'>Health</th><th scope='col'>Packages</th>", body)
        self.assertIn("<th scope='col'>Last check</th><th scope='col'>Issues</th>", body)
        self.assertNotIn(">Adapter<", body)
        self.assertNotIn("Open map statistics", body)
        self.assertIn("<small>opentopomap</small>", body)

    def test_provider_detail_uses_progressive_disclosure_and_human_audit_actions(self):
        body = provider_detail_page(
            {
                "provider": {
                    "id": "opentopomap",
                    "name": "OpenTopoMap",
                    "adapterId": "opentopomap",
                    "status": "PAUSED",
                    "healthStatus": "HEALTHY",
                    "packageCount": 1,
                    "lastCatalogSync": "2026-08-31T12:00:00+00:00",
                    "lastHealthCheck": "2026-08-31T12:05:00+00:00",
                    "website": "https://opentopomap.org/",
                    "license": "ODbL",
                    "attribution": "OpenTopoMap",
                    "sources": [
                        {"source_type": "WEBSITE", "source_url": "https://opentopomap.org/", "enabled": True},
                        {"source_type": "DOWNLOAD", "source_url": "https://example.test/map.zip", "enabled": True, "validation_status": "FAILED"},
                    ],
                    "maps": [{
                        "id": "opentopomap-lithuania",
                        "name": "Lithuania",
                        "region": "LT",
                        "release": "2026-08",
                        "artifact_count": 1,
                        "availability": "AVAILABLE",
                        "broken_artifact_count": 0,
                    }],
                    "healthHistory": [{
                        "status": "HEALTHY",
                        "checked_at": "2026-08-31T12:05:00+00:00",
                        "website_status": "HEALTHY",
                        "catalog_status": "HEALTHY",
                        "redirect_status": "HEALTHY",
                        "download_status": "HEALTHY",
                        "mime_status": "HEALTHY",
                        "magic_status": "HEALTHY",
                        "zip_status": "HEALTHY",
                        "img_status": "HEALTHY",
                        "last_update_status": "HEALTHY",
                        "http_status": 200,
                        "artifact_count": 1,
                        "duration_ms": 120,
                    }],
                    "activationGate": {"canActivate": False, "blockers": [{"message": "Collect a catalog first."}]},
                },
            },
            [{"id": "run-1", "status": "SUCCEEDED", "package_count": 1, "artifact_count": 1}],
            [{"admin_user_id": "operator", "action": "provider.status_changed", "old_status": "ACTIVE", "new_status": "PAUSED", "reason": "Testing", "occurred_at": "2026-08-31T12:10:00+00:00", "target": "opentopomap", "details": {"source": "test"}}],
            {"username": "operator"},
            "csrf",
        ).decode()
        for text in ("Packages", "Broken", "Last catalog sync", "Last health check", "Check now", "Collect catalog", "More", "Retire provider", "Provider metadata", "Original links", "Download source URLs", "Regions and packages", "Latest health check", "View check details", "Collection history", "Provider history"):
            self.assertIn(text, body)
        self.assertIn("id='provider-source-pagination'", body)
        self.assertIn("id='provider-package-pagination'", body)
        self.assertIn("id='provider-source-page-size'", body)
        self.assertIn("id='provider-package-page-size'", body)
        self.assertIn("Health check history · 0 previous checks", body)
        self.assertIn("Status changed", body)
        self.assertIn("provider.status_changed", body)
        self.assertIn("audit-technical-details", body)
        history = body.split("id='provider-history'", 1)[1]
        self.assertNotIn("<th scope='col'>Admin user</th>", history)
        self.assertNotIn("<th scope='col'>Target/details</th>", history)
        self.assertIn("<th scope='col'>Details</th>", history)
        self.assertIn('&quot;adminUserId&quot;:&quot;operator&quot;', history)
        self.assertIn('&quot;target&quot;:&quot;opentopomap&quot;', history)
        self.assertNotIn("<span>Activity</span>", body)

    def test_provider_health_history_does_not_repeat_latest_check(self):
        latest = {
            "status": "HEALTHY", "checked_at": "2026-08-31T12:05:00+00:00",
            "website_status": "HEALTHY", "catalog_status": "HEALTHY",
            "redirect_status": "HEALTHY", "download_status": "HEALTHY",
            "mime_status": "HEALTHY", "magic_status": "HEALTHY",
            "zip_status": "HEALTHY", "img_status": "HEALTHY",
            "last_update_status": "HEALTHY", "http_status": 200,
            "artifact_count": 1, "duration_ms": 120,
        }
        previous = dict(latest, checked_at="2026-08-30T12:05:00+00:00", duration_ms=140)
        body = provider_detail_page(
            {"provider": {
                "id": "opentopomap", "name": "OpenTopoMap", "adapterId": "opentopomap",
                "status": "PAUSED", "healthStatus": "HEALTHY", "healthHistory": [latest, previous],
                "maps": [], "sources": [],
                "activationGate": {"canActivate": False, "blockers": []},
            }}, [], [], {"username": "operator"}, "csrf",
        ).decode()
        history = body.split("id='provider-health-history'", 1)[1].split("</details>", 1)[0]
        self.assertIn("Health check history · 1 previous checks", history)
        self.assertIn("2026-08-30", history)
        self.assertNotIn("2026-08-31", history)
        self.assertNotIn("Download source URLs", body)
        self.assertIn("Collection · No runs yet", body)

    def test_shared_model_page_keeps_resolved_failures_historical_and_open_errors_active_only(self):
        device = _admin_device_payload([{
            "device_id": "garmin-fenix-8-51-amoled", "model": "fēnix 8",
            "variant": "51 mm, AMOLED", "family_name": "fēnix", "map_capable": True,
            "support_status": "SUPPORTED", "active": True,
            "attempted_install_count": 1, "successful_install_count": 1,
            "failed_install_count": 0, "last_success": "2026-08-27T07:53:00+00:00",
            "usb_identities": [],
        }], None)["devices"][0]
        active = [{
            "operation_key": "successful-install", "canonical_device_model_id": device["id"],
            "occurred_at": "2026-08-27T07:53:00+00:00", "phase_outcome": "SUCCEEDED",
            "automatic_finishing_result": "VERIFIED", "write_started": True,
        }]
        resolved = [{
            "operation_key": "resolved-failure", "canonical_device_model_id": device["id"],
            "occurred_at": "2026-08-26T07:53:00+00:00", "phase_outcome": "FAILED",
            "failure_stage": "write", "failure_code": "SEND_OBJECT_FAILED",
            "write_started": False, "diagnostic_status": "RESOLVED",
        }, {
            "operation_key": "resolved-success-anomaly", "canonical_device_model_id": device["id"],
            "occurred_at": "2026-08-25T07:53:00+00:00", "phase_outcome": "SUCCEEDED",
            "automatic_finishing_result": "VERIFIED", "write_started": True,
            "diagnostic_status": "RESOLVED",
        }]
        body = device_detail_page(
            device, {"username": "operator"}, "csrf",
            operations=active, resolved_operations=resolved,
        ).decode()
        statistics = body.split("class='diagnostic-model-metrics model-statistics'", 1)[1].split("</section>", 1)[0]
        for label, value in (("Attempts", "2"), ("Successful", "1"), ("Failed", "1"), ("Open errors", "0")):
            self.assertIn(f"<span>{label}</span><strong>{value}</strong>", statistics)
        self.assertIn("<span>Last activity</span><strong>—</strong>", statistics)
        self.assertNotIn("<span>Compatibility status</span>", statistics)
        self.assertIn("diagnostic-state-resolved", body)
        self.assertIn("data-diagnostic-result='failed'", body)
        self.assertIn("data-review-resolved='true'", body)
        self.assertNotIn("USB identity</dt>", body)
        self.assertNotIn("Firmware</dt>", body)
        self.assertIn("Write failed", body)
        self.assertIn("SEND_OBJECT_FAILED", body)
        self.assertIn("Failure reason:", body)
        self.assertIn("data-history-filter='failed'", body)
        self.assertIn("Device snapshot totals information", body)
        self.assertIn("maxlength='500'", body)
        self.assertIn("link.closest('.github-issue-controls, .github-review')", body)
        self.assertNotIn("\x08", body)

    def test_failed_installation_counts_do_not_depend_on_write_started(self):
        identity = "fēnix 8 · 51 mm, AMOLED"
        device_id = "garmin-fenix-8-51-amoled"
        successful = [{
            "operation_key": f"success-{index}", "compatibility_identity": identity,
            "canonical_device_model_id": device_id, "phase_outcome": "SUCCEEDED",
            "automatic_finishing_result": "VERIFIED", "write_started": True,
        } for index in range(7)]
        open_failed = [{
            "operation_key": "open-failed", "compatibility_identity": identity,
            "canonical_device_model_id": device_id, "phase_outcome": "FAILED",
            "failure_stage": "write", "failure_code": "INSTALL_FAILED_WRITE",
            "write_started": True,
        }]
        resolved_failed = [{
            "operation_key": "resolved-failed-write", "compatibility_identity": identity,
            "canonical_device_model_id": device_id, "phase_outcome": "FAILED",
            "failure_stage": "verify", "failure_code": "INSTALL_FAILED_SIZE_MISMATCH",
            "write_started": True, "diagnostic_status": "RESOLVED",
        }, {
            "operation_key": "resolved-failed-prewrite", "compatibility_identity": identity,
            "canonical_device_model_id": device_id, "phase_outcome": "FAILED",
            "failure_stage": "preflight", "failure_code": "INSTALL_BLOCKED_INSUFFICIENT_SPACE",
            "write_started": False, "diagnostic_status": "RESOLVED",
        }]
        summary = _diagnostic_summary_by_identity(successful + open_failed, resolved_failed)[f"canonical:{device_id}"]
        self.assertEqual(summary["attempts"], 10)
        self.assertEqual(summary["successful"], 7)
        self.assertEqual(summary["failed"], 3)
        self.assertEqual(summary["open_errors"], 1)

        device = _admin_device_payload([{
            "device_id": device_id, "model": "fēnix 8", "variant": "51 mm, AMOLED",
            "family_name": "fēnix", "map_capable": True, "support_status": "SUPPORTED",
            "active": True, "attempted_install_count": 8, "successful_install_count": 7,
            "failed_install_count": 1, "usb_identities": [],
        }], None)["devices"][0]
        body = device_detail_page(
            device, {"username": "operator"}, "csrf",
            operations=successful + open_failed, resolved_operations=resolved_failed,
        ).decode()
        statistics = body.split("class='diagnostic-model-metrics model-statistics'", 1)[1].split("</section>", 1)[0]
        for label, value in (("Attempts", "10"), ("Successful", "7"), ("Failed", "3"), ("Open errors", "1")):
            self.assertIn(f"<span>{label}</span><strong>{value}</strong>", statistics)
        self.assertIn("<span>Last activity</span><strong>—</strong>", statistics)
        self.assertNotIn("<span>Compatibility status</span>", statistics)

    def test_github_issue_report_uses_an_allowlist_and_redacts_sensitive_values(self):
        results = [{
            "operation_key": "install-32", "phase_outcome": "FAILED",
            "failure_stage": "write", "failure_code": "SEND_OBJECT_FAILED",
            "raw_mtp_model": "private raw value", "firmware_version": "20.19",
            "authorization": "Bearer secret", "email": "owner@example.com",
            "private_path": "/Users/alice/Documents/private.log",
        }]
        title, body = _github_issue_report("fēnix 8 · 51 mm, AMOLED", results)
        self.assertIn("[Install][Write]", title)
        self.assertIn(r"SEND\_OBJECT\_FAILED", body)
        self.assertIn("install-32", body)
        self.assertIn("private raw value", body)
        self.assertIn("20.19", body)
        for forbidden in ("Bearer secret", "owner@example.com", "/Users/alice"):
            self.assertNotIn(forbidden, title + body)
        sanitised = _sanitised_issue_value(
            "owner@example.com /Users/alice/Documents/log.txt /private/var/log.txt "
            "api_key=secret cookie=session serialNumber=12345678"
        )
        self.assertNotIn("owner@example.com", sanitised)
        self.assertNotIn("/Users/alice", sanitised)
        self.assertNotIn("secret", sanitised)
        self.assertNotIn("session", sanitised)
        self.assertNotIn("/private/var", sanitised)
        self.assertNotIn("12345678", sanitised)

    def test_browser_and_server_admin_note_sanitizers_remove_private_values_before_url_creation(self):
        fake_values = (
            "serialNumber=SERIAL-123", "unitId=UNIT-456", "unit_id=UNIT-ALT-456",
            "deviceId=DEVICE-789", "device_id=DEVICE-ALT-789",
            "/private/tmp/private.log", "/var/folders/aa/private.log",
            "/Volumes/Garmin/private.log", "/Users/alice/private.log",
            r"C:\Users\alice\private.log", "C:/Users/alice/private.log",
            "owner@example.com", "api_key=FAKE-SECRET", "?token=FAKE-QUERY",
            "Authorization: Bearer FAKE-AUTH", "DATABASE_URL=postgres://private",
            "<script>alert('private')</script>", "&title=INJECTED", "?body=INJECTED",
        )
        sanitizer = _client_issue_note_sanitizer_script()
        source = f"""
          const sanitiseNote = {sanitizer};
          const note = JSON.parse(process.argv[1]);
          const body = `Safe report\\n\\n## Admin note\\n\\n${{sanitiseNote(note)}}`;
          const url = `https://github.com/VooZ2/terento/issues/new?${{new URLSearchParams({{title: 'Safe title', body}})}}`;
          process.stdout.write(JSON.stringify({{body, url, decoded: Object.fromEntries(new URL(url).searchParams)}}));
        """
        for private_value in fake_values:
            with self.subTest(private_value=private_value):
                client = json.loads(self._run_node(source, json.dumps(private_value)).stdout)
                server = _sanitised_issue_value(private_value)
                self.assertNotIn(private_value, client["body"])
                self.assertNotIn(private_value, client["url"])
                self.assertNotIn(private_value, str(client["decoded"]))
                self.assertNotIn(private_value, server)
                self.assertEqual(set(client["decoded"]), {"title", "body"})

    def test_last_success_sort_uses_success_timestamp_and_keeps_missing_values_last(self):
        comparator = _device_last_success_comparator_script()
        source = f"""
          const compareLastSuccess = {comparator};
          const textCompare = (a, b) => String(a || '').localeCompare(String(b || ''));
          const devices = JSON.parse(process.argv[1]);
          const order = (direction) => devices.slice()
            .sort((a, b) => compareLastSuccess(a, b, direction, textCompare))
            .map((device) => device.id);
          process.stdout.write(JSON.stringify({{ascending: order('ascending'), descending: order('descending')}}));
        """
        devices = [{
            "id": "older-success",
            "installationStats": {
                "lastSuccessfulAt": "2026-08-20T10:00:00Z",
                "lastEvidenceAt": "2026-08-28T10:00:00Z",
            },
        }, {
            "id": "newer-success",
            "installationStats": {
                "lastSuccessfulAt": "2026-08-25T10:00:00Z",
                "lastEvidenceAt": "2026-08-25T10:00:00Z",
            },
        }, {
            "id": "failed-only",
            "installationStats": {
                "lastSuccessfulAt": None,
                "lastEvidenceAt": "2026-08-27T10:00:00Z",
            },
        }]
        result = json.loads(self._run_node(source, json.dumps(devices)).stdout)
        self.assertEqual(result["ascending"], ["older-success", "newer-success", "failed-only"])
        self.assertEqual(result["descending"], ["newer-success", "older-success", "failed-only"])

    def test_github_issue_report_redacts_hostile_allowlisted_values_and_encodes_one_query(self):
        fake_values = (
            "ghp_FAKE_TOKEN_123", "github_pat_FAKE", "Bearer FAKE_TOKEN",
            "Authorization: Bearer FAKE", "token=FAKEQUERY", "access_token=FAKE",
            "api_key=FAKE", "DATABASE_URL=postgres://fake", "test@example.com",
            "/Users/gediminas/private/file", r"C:\Users\gediminas\private\file",
            "<script>alert(1)</script>", "&title=injected", "?body=injected",
        )
        results = [{
            "operation_key": "&title=injected", "event_id": "?body=injected",
            "phase_outcome": "FAILED", "failure_stage": "write",
            "failure_code": "ghp_FAKE_TOKEN_123", "native_failure_code": "github_pat_FAKE",
            "error_category": "Authorization: Bearer FAKE", "region": "token=FAKEQUERY",
            "map_release": "DATABASE_URL=postgres://fake", "release_label": "test@example.com",
            "firmware_version": "/Users/gediminas/private/file",
            "raw_mtp_model": "<script>alert(1)</script>",
            "transport": r"C:\Users\gediminas\private\file", "write_started": False,
            "remote_object_created": False, "cleanup_attempted": False,
        }]
        title, body = _github_issue_report(
            "Bearer FAKE_TOKEN · access_token=FAKE api_key=FAKE", results,
        )
        url, prefilled = _github_issue_url(
            "Bearer FAKE_TOKEN · access_token=FAKE api_key=FAKE", results,
        )
        decoded = parse_qs(urlsplit(url).query)
        combined = title + body + str(decoded)
        for forbidden in fake_values:
            self.assertNotIn(forbidden, combined)
        self.assertTrue(prefilled)
        self.assertEqual(set(decoded), {"title", "body"})
        self.assertEqual(decoded["title"], [title])
        self.assertEqual(decoded["body"], [body])
        self.assertNotIn("<script", body)

    def test_github_admin_note_is_sanitised_bounded_and_oversized_report_uses_copy_fallback(self):
        results = [{
            "operation_key": "install-32", "event_id": "event-32",
            "phase_outcome": "FAILED", "failure_stage": "write",
            "failure_code": "INSTALL_FAILED_WRITE",
        }]
        note = "Normal note **markdown** <script>alert(1)</script> ghp_FAKE_TOKEN_123 " + "x" * 700
        _, body = _github_issue_report("fēnix 8 · 51 mm", results, admin_note=note)
        rendered_note = body.split("## Admin note\n\n", 1)[1]
        self.assertLessEqual(len(rendered_note), GITHUB_ADMIN_NOTE_MAX_LENGTH + 40)
        self.assertNotIn("<script", rendered_note)
        self.assertNotIn("ghp_FAKE_TOKEN_123", rendered_note)
        normal_url, normal_prefilled = _github_issue_url("fēnix 8 · 51 mm", results, admin_note="Reviewed")
        self.assertTrue(normal_prefilled)
        self.assertLessEqual(len(normal_url), GITHUB_ISSUE_URL_MAX_LENGTH)
        oversized_url, oversized_prefilled = _github_issue_url("x" * 8_000 + " · 51 mm", results)
        self.assertFalse(oversized_prefilled)
        self.assertEqual(oversized_url, "https://github.com/VooZ2/terento/issues/new")

    def test_oversized_github_report_renders_browser_copy_fallback_without_query_data(self):
        device = _admin_device_payload([{
            "device_id": "garmin-oversized-report", "model": "x" * 8_000,
            "variant": "51 mm", "family_name": "fēnix", "map_capable": True,
            "support_status": "SUPPORTED", "active": True,
            "attempted_install_count": 1, "successful_install_count": 0,
            "failed_install_count": 1, "usb_identities": [],
        }], None)["devices"][0]
        operation = {
            "operation_key": "oversized-report", "event_id": "oversized-event",
            "canonical_device_model_id": device["id"],
            "occurred_at": "2026-08-28T00:00:00+00:00",
            "phase_outcome": "FAILED", "failure_stage": "write",
            "failure_code": "INSTALL_FAILED_WRITE", "write_started": True,
        }
        body = device_detail_page(
            device, {"username": "operator"}, "csrf", operations=[operation],
        ).decode()
        self.assertIn(
            "href='https://github.com/VooZ2/terento/issues/new'", body,
        )
        self.assertIn("data-prefilled='false'", body)
        self.assertIn("Report is too large to prefill; copy it instead.", body)
        self.assertIn("data-copy-issue-report", body)
        self.assertIn("data-issue-body=", body)
        self.assertIn("if (link.dataset.prefilled === 'false')", body)
        self.assertIn("event.preventDefault();", body)
        self.assertIn("copyText(`${link.dataset.issueTitle}\\n\\n${body}`, status);", body)
        fallback_start = body.index("data-github-create")
        fallback_markup = body[max(0, fallback_start - 500):fallback_start + 500]
        self.assertNotIn("issues/new?", fallback_markup)

    def test_admin_actions_have_single_submit_loading_and_inline_failure_enhancement(self):
        device = _admin_device_payload([{
            "device_id": "garmin-fenix-8", "model": "fēnix 8", "variant": "47 mm",
            "family_name": "fēnix", "map_capable": True, "support_status": "SUPPORTED",
            "active": True, "attempted_install_count": 0, "successful_install_count": 0,
            "failed_install_count": 0, "usb_identities": [],
        }], None)["devices"][0]
        body = device_detail_page(device, {"username": "operator"}, "csrf").decode()
        self.assertGreaterEqual(body.count("admin-async-action"), 2)
        self.assertIn("form.dataset.submitting === 'true'", body)
        self.assertIn("submit.textContent = 'Saving…'", body)
        self.assertIn("Could not save. Check the values and try again.", body)
        self.assertIn("controls.forEach((control) =>", body)

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

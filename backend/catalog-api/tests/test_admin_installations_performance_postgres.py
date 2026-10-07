"""Installations page cost guards on the real migrated PostgreSQL schema.

``/admin/installations`` (and Devices) read ``admin_device_snapshot``. It used a
per-device LATERAL over ``compatibility_model_statistics``; PostgreSQL cannot
push the device filter below the view's aggregation, so every catalog row
re-aggregated all evidence and re-ran the view's review lookup for every
aggregate row (devices x rows). The view is now evaluated once per request.
"""
import json
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.admin import dashboard_page
from terento_catalog.http_api import CatalogService

EPIX = "garmin-epix-pro-gen-2-47"
ENDURO = "garmin-enduro-2"


def _plan_nodes(node):
    yield node
    for child in node.get("Plans", []):
        yield from _plan_nodes(child)


class InstallationsQueryCostTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.service = CatalogService(self.db)
        batch = self.rows.uuid()
        for index in range(2):
            self.rows.diagnostic(operation_id=batch, map_result_index=index, selected_map_count=2)
        self.rows.diagnostic(phase_outcome="FAILED", failure_stage="write", failure_code="INSTALL_FAILED_WRITE")
        self.rows.diagnostic(canonical_device_model_id=EPIX, compatibility_identity="epix Pro (Gen 2) · 47 mm",
                             model="epix Pro (Gen 2)", occurred_at=self.rows.at(-90))
        self.rows.diagnostic(canonical_device_model_id=EPIX, compatibility_identity="epix Pro (Gen 2) · 47 mm",
                             model="epix Pro (Gen 2)", diagnostic_status="RESOLVED", occurred_at=self.rows.at(30))
        self.rows.diagnostic(canonical_device_model_id=ENDURO, compatibility_identity="Enduro 2", model="Enduro 2",
                             phase_outcome="FAILED", write_started=False, failure_stage="download",
                             failure_code="INSTALL_BLOCKED_DOWNLOAD_FAILED")
        self.rows.diagnostic(canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
                             compatibility_identity="Venu X1", model="Venu X1")
        self.server.query(
            "INSERT INTO compatibility_model_review (model, identity_key, review_status, public_statistics_enabled)"
            " VALUES ('fēnix 8 · 47 mm', 'fēnix 8 · 47 mm', 'APPROVED', true)"
        )

    def snapshot_sql(self):
        captured = []
        original = self.server.query

        def capture(sql, params=None):
            captured.append(sql)
            return original(sql, params)

        self.server.query = capture
        try:
            self.db.admin_device_snapshot()
        finally:
            self.server.query = original
        return next(sql for sql in captured if "FROM device_model AS dm" in sql)

    def test_snapshot_evidence_matches_the_statistics_view_per_device(self):
        rows, _ = self.db.admin_device_snapshot()
        by_device = {row["device_id"]: row for row in rows}
        view = {
            row["canonical_device_model_id"]: row
            for row in self.sql("SELECT * FROM compatibility_model_statistics WHERE canonical_device_model_id IS NOT NULL")
        }
        self.assertEqual(set(view), {FENIX_8, EPIX, ENDURO})
        for device_id, row in by_device.items():
            stats = view.get(device_id)
            self.assertEqual(
                (row["attempted_install_count"], row["successful_install_count"], row["failed_install_count"],
                 row["compatibility_successful_install_count"]),
                (stats["attempted_install_count"], stats["successful_install_count"], stats["failed_install_count"],
                 stats["successful_install_count"]) if stats else (0, 0, 0, 0),
                device_id,
            )
            self.assertEqual(row["last_success"], stats["last_success"] if stats else None, device_id)
            self.assertEqual(row["last_evidence"], stats["last_evidence"] if stats else None, device_id)
            self.assertEqual(row["public_review_status"], stats["review_status"] if stats else None, device_id)
            self.assertEqual(row["public_statistics_enabled"], bool(stats and stats["public_statistics_enabled"]))
        self.assertEqual((by_device[FENIX_8]["attempted_install_count"], by_device[FENIX_8]["failed_install_count"]), (3, 1))
        self.assertEqual(by_device[EPIX]["first_success"], self.rows.at(-90))
        self.assertIsNone(by_device[ENDURO]["first_success"])
        self.assertEqual(by_device[FENIX_8]["public_review_status"], "APPROVED")

    def test_statistics_view_review_lookup_runs_once_per_aggregate_row(self):
        view_rows = len(self.sql("SELECT 1 FROM compatibility_model_statistics"))
        devices = len(self.sql("SELECT 1 FROM device_model"))
        self.assertGreater(devices, view_rows)
        result = self.sql("EXPLAIN (ANALYZE, FORMAT JSON) " + self.snapshot_sql())[0]["QUERY PLAN"]
        plan = json.loads(result) if isinstance(result, str) else result
        review_loops = sum(
            int(node.get("Actual Loops") or 0)
            for node in _plan_nodes(plan[0]["Plan"])
            if node.get("Relation Name") == "compatibility_model_review"
        )
        # One review lookup per aggregate row; the per-device form needed
        # devices x aggregate rows.
        self.assertGreater(review_loops, 0)
        self.assertLessEqual(review_loops, view_rows)

    def test_installations_page_uses_a_fixed_number_of_queries(self):
        statements = []
        original = self.server.query

        def count(sql, params=None):
            statements.append(" ".join(sql.split())[:60])
            return original(sql, params)

        self.server.query = count
        try:
            body = dashboard_page(
                self.service.compatibility_statistics(), {"username": "test"}, "csrf",
                diagnostic_summary=self.service.compatibility_diagnostic_summary(),
                identity_devices=self.service.admin_devices().get("devices", []),
            ).decode()
        finally:
            self.server.query = original
        self.assertIn("data-stat='attempts'", body)
        # statistics view (2), diagnostic population (1), open problems (1),
        # device snapshot (2) and latest catalog sync (1); none per row.
        self.assertEqual(len(statements), 7, statements)
        self.assertEqual(sum(1 for sql in statements if sql == "SET LOCAL jit = off"), 2)

    def test_canonical_device_evidence_index_exists(self):
        indexes = {row["indexname"] for row in self.sql(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'compatibility_evidence_event'"
        )}
        self.assertIn("compatibility_evidence_canonical_device_idx", indexes)


if __name__ == "__main__":
    unittest.main()

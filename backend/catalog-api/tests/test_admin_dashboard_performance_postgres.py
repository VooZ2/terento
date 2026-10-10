"""Dashboard (``/admin``) cost guards on the real migrated PostgreSQL schema.

The Dashboard reads ``compatibility_model_statistics`` twice (Needs attention
publication reviews and the review-required list). The view's per-aggregate
review lookup makes its estimated cost grow with the number of review rows;
past ``jit_optimize_above_cost`` PostgreSQL spends seconds compiling LLVM code
for reads that run in milliseconds, as it did on Installations. Both reads
therefore run with JIT disabled for their transaction, and the request issues
a fixed number of statements however much history exists.
"""
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows
from terento_catalog.admin import overview_page
from terento_catalog.http_api import CatalogService

EPIX = "garmin-epix-pro-gen-2-47"
ENDURO = "garmin-enduro-2"
PERIODS = ("today", "24h", "7d", "30d", "all")


class DashboardQueryCostTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.service = CatalogService(self.db)
        self.seed(0)
        self.server.query(
            "INSERT INTO compatibility_model_review (model, identity_key, review_status, public_statistics_enabled)"
            " VALUES ('fēnix 8 · 47 mm', 'fēnix 8 · 47 mm', 'PENDING', false)"
        )

    def seed(self, offset):
        batch = self.rows.uuid()
        for index in range(2):
            self.rows.diagnostic(operation_id=batch, map_result_index=index, selected_map_count=2,
                                 occurred_at=self.rows.at(offset))
            self.rows.map_event(operation_id=batch, map_result_index=index, occurred_at=self.rows.at(offset),
                                map_package_id=None, region=f"R{offset}{index}")
        self.rows.diagnostic(phase_outcome="FAILED", failure_stage="write", failure_code="INSTALL_FAILED_WRITE",
                             occurred_at=self.rows.at(offset + 1))
        self.rows.diagnostic(canonical_device_model_id=EPIX, compatibility_identity="epix Pro (Gen 2) · 47 mm",
                             model="epix Pro (Gen 2)", occurred_at=self.rows.at(offset - 90))
        self.rows.diagnostic(canonical_device_model_id=ENDURO, compatibility_identity="Enduro 2", model="Enduro 2",
                             phase_outcome="FAILED", write_started=False, failure_stage="download",
                             failure_code="INSTALL_BLOCKED_DOWNLOAD_FAILED", occurred_at=self.rows.at(offset + 2))
        self.rows.diagnostic(canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
                             compatibility_identity="Venu X1", model="Venu X1", occurred_at=self.rows.at(offset + 3))

    def dashboard_transactions(self, period):
        """Render the Dashboard; return the statements grouped per connection."""
        transactions, current = [], None
        original_query, original_exec = self.server.query, self.server.exec

        def query(sql, params=None):
            current.append(" ".join(sql.split()))
            return original_query(sql, params)

        def exec_(sql):
            nonlocal current
            if sql.startswith("SAVEPOINT "):
                current = []
                transactions.append(current)
            return original_exec(sql)

        self.server.query, self.server.exec = query, exec_
        try:
            session = {"username": "test", "admin_review_summary": self.service.admin_review_summary()}
            body = overview_page(self.service.admin_overview(period, "UTC"), session, "csrf").decode()
        finally:
            self.server.query, self.server.exec = original_query, original_exec
        self.assertIn("Needs attention", body)
        self.assertTrue(session["admin_review_summary"]["available"])
        return transactions

    def test_statistics_view_reads_skip_jit_compilation(self):
        for period in PERIODS:
            view_reads = 0
            for statements in self.dashboard_transactions(period):
                for position, sql in enumerate(statements):
                    if "FROM compatibility_model_statistics" in sql:
                        view_reads += 1
                        self.assertIn("SET LOCAL jit = off", statements[:position], (period, sql[:80]))
            # Needs attention summary only: the unrendered compatibility
            # snapshot (review-required list) is no longer read.
            self.assertEqual(view_reads, 1, period)

    def test_statement_count_does_not_grow_with_history(self):
        before = {period: sum(map(len, self.dashboard_transactions(period))) for period in PERIODS}
        for offset in range(-6000, 0, 600):
            self.seed(offset)
        after = {period: sum(map(len, self.dashboard_transactions(period))) for period in PERIODS}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()

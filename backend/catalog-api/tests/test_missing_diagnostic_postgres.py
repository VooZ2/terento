"""Missing-diagnostic review tasks on the migrated PostgreSQL schema (audit M8)."""
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows


class MissingDiagnosticTaskTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)

    def tasks(self):
        count = self.db.admin_review_summary()["missingDiagnostics"]
        items = self.db.missing_diagnostic_failures(limit=200)["rows"]
        self.assertEqual(count, len(items))
        return count

    def failed_install(self, operation):
        return self.rows.map_event(operation_id=operation, event_type="INSTALL_FAILED", outcome="FAILED")

    def test_map_failure_without_diagnostic_is_a_task(self):
        self.failed_install(self.rows.uuid())
        self.assertEqual(self.tasks(), 1)

    def test_out_of_scope_prewrite_diagnostic_suppresses_the_task(self):
        operation = self.rows.uuid()
        self.failed_install(operation)
        self.rows.diagnostic(operation_id=operation, phase_outcome="NOT_STARTED", write_started=False,
                             failure_stage="preflight", failure_code="INSTALL_BLOCKED_TERENTO_DEVICE_SCOPE",
                             statistics_exclusion_code="OUT_OF_SCOPE_PREWRITE")
        self.assertEqual(self.tasks(), 0)
        self.assertEqual(self.db.admin_review_summary()["installationIssues"], 0)

    def test_out_of_scope_for_another_result_does_not_hide_a_gap(self):
        operation = self.rows.uuid()
        self.failed_install(operation)
        self.rows.diagnostic(operation_id=operation, map_result_index=1, selected_map_count=2,
                             phase_outcome="NOT_STARTED", write_started=False, failure_stage="preflight",
                             failure_code="INSTALL_BLOCKED_TERENTO_DEVICE_SCOPE",
                             statistics_exclusion_code="OUT_OF_SCOPE_PREWRITE")
        self.assertEqual(self.tasks(), 1)

    def test_matching_diagnostic_still_removes_the_gap(self):
        operation = self.rows.uuid()
        self.failed_install(operation)
        self.rows.diagnostic(operation_id=operation, phase_outcome="FAILED", failure_stage="write",
                             failure_code="INSTALL_FAILED_WRITE")
        self.assertEqual(self.tasks(), 0)


if __name__ == "__main__":
    unittest.main()

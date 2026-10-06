"""Installations per-identity population on the real migrated PostgreSQL schema."""
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.admin import _diagnostic_summary_by_identity
from terento_catalog.http_api import CatalogService


class DiagnosticPopulationTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.service = CatalogService(self.db)

    def test_out_of_scope_prewrite_is_not_identity_pending_or_attempt(self):
        self.rows.diagnostic(
            canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
            compatibility_identity="Edge 840", model="Edge 840",
            phase_outcome="NOT_STARTED", write_started=False, failure_stage="preflight",
            failure_code="INSTALL_BLOCKED_TERENTO_DEVICE_SCOPE",
            statistics_exclusion_code="OUT_OF_SCOPE_PREWRITE",
        )
        self.assertEqual(self.db.compatibility_diagnostic_population(), [])
        self.assertEqual(self.service.compatibility_diagnostic_summary(), {})

    def test_download_prewrite_is_not_identity_pending(self):
        self.rows.diagnostic(
            canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
            compatibility_identity="Unknown watch", phase_outcome="FAILED", write_started=False,
            failure_stage="download", failure_code="INSTALL_BLOCKED_DOWNLOAD_FAILED",
        )
        summary = self.service.compatibility_diagnostic_summary()["identity:Unknown watch"]
        self.assertEqual(summary["identity_pending"], 0)
        self.assertEqual(summary["attempts"], 0)

    def test_resolving_a_batch_keeps_sibling_success_like_view_067(self):
        operation = self.rows.uuid()
        for index in range(2):
            self.rows.diagnostic(operation_id=operation, map_result_index=index, selected_map_count=3)
        self.rows.diagnostic(operation_id=operation, map_result_index=2, selected_map_count=3,
                             phase_outcome="FAILED", failure_stage="write", failure_code="INSTALL_FAILED_WRITE")
        before = self.service.compatibility_diagnostic_summary()[f"canonical:{FENIX_8}"]
        self.server.query("UPDATE compatibility_evidence_event SET diagnostic_status='RESOLVED'")
        after = self.service.compatibility_diagnostic_summary()[f"canonical:{FENIX_8}"]
        view = self.sql("SELECT attempted_install_count, successful_install_count, failed_install_count"
                        " FROM compatibility_model_statistics WHERE canonical_device_model_id=%s", (FENIX_8,))[0]
        for summary in (before, after):
            self.assertEqual((summary["attempts"], summary["successful"], summary["failed"]), (3, 2, 1))
        self.assertEqual((before["open_errors"], after["open_errors"]), (1, 0))
        self.assertEqual(
            (view["attempted_install_count"], view["successful_install_count"], view["failed_install_count"]),
            (3, 2, 1),
        )


class ResolvedSuccessPythonTwinTests(unittest.TestCase):
    def test_resolved_success_keeps_historical_outcome(self):
        rows = [dict(operation_id="op", map_result_index=index, canonical_device_model_id="watch",
                     phase_outcome=outcome, automatic_finishing_result=finish, write_started=True)
                for index, (outcome, finish) in enumerate((("SUCCEEDED", "VERIFIED"), ("FAILED", "FAILED")))]
        summary = _diagnostic_summary_by_identity([], rows)["canonical:watch"]
        self.assertEqual((summary["attempts"], summary["successful"], summary["failed"], summary["open_errors"]),
                         (2, 1, 1, 0))


if __name__ == "__main__":
    unittest.main()

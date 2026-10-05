"""One definition and one unit for open installation problems (audit H2).

Dashboard "Installation problems", the Installations "Open problems" KPI, the
Installations row counters and model detail all read the operation-level
Needs attention predicate from ``Database.installation_problem_counts``.
"""
import re
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.admin import dashboard_page, device_detail_page, diagnostics_page
from terento_catalog.http_api import CatalogService

KPI = re.compile(r"data-stat='openProblems'>(?:<svg.*?</svg>)?(\d+)</strong>")
ROW = re.compile(r"data-identity='([^']+)'[^>]*data-errors='(\d+)'")


class InstallationProblemParityTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.service = CatalogService(self.db)

    def installations(self):
        body = dashboard_page(
            self.service.compatibility_statistics(), {"username": "test"}, "csrf",
            diagnostic_summary=self.service.compatibility_diagnostic_summary(),
        ).decode()
        kpi = int(KPI.search(body).group(1))
        rows = {identity: int(count) for identity, count in ROW.findall(body)}
        return kpi, rows

    def seed_audit_scenario(self):
        batch = self.rows.uuid()
        for index in range(2):
            self.rows.diagnostic(operation_id=batch, map_result_index=index, selected_map_count=2,
                                 phase_outcome="FAILED", failure_stage="write",
                                 failure_code="INSTALL_FAILED_WRITE")
        self.rows.diagnostic(phase_outcome="FAILED", write_started=False, failure_stage="preflight",
                             failure_code="INSTALL_BLOCKED_INSUFFICIENT_SPACE")
        self.rows.diagnostic(phase_outcome="FAILED", failure_stage="write",
                             failure_code="INSTALL_FAILED_WRITE", linked_github_issue="#41")
        # Pre-install provider download failures are acquisition facts only.
        self.rows.diagnostic(phase_outcome="FAILED", write_started=False, failure_stage="download",
                             failure_code="INSTALL_BLOCKED_DOWNLOAD_FAILED")
        # Out-of-scope policy block and resolved work never enter open work.
        self.rows.diagnostic(phase_outcome="NOT_STARTED", write_started=False, failure_stage="preflight",
                             failure_code="INSTALL_BLOCKED_TERENTO_DEVICE_SCOPE",
                             statistics_exclusion_code="OUT_OF_SCOPE_PREWRITE")
        self.rows.diagnostic(phase_outcome="FAILED", failure_stage="write",
                             failure_code="INSTALL_FAILED_WRITE", diagnostic_status="RESOLVED")

    def test_dashboard_installations_and_model_detail_reconcile(self):
        self.seed_audit_scenario()
        dashboard = self.db.admin_review_summary()["installationIssues"]
        problems = self.db.installation_problem_counts()
        kpi, rows = self.installations()
        self.assertEqual(dashboard, 2)  # one batch + one pre-write storage block
        self.assertEqual(problems["total"], dashboard)
        self.assertEqual(kpi, dashboard)
        self.assertEqual(sum(rows.values()), kpi)
        self.assertEqual(rows[f"canonical:{FENIX_8}"], 2)
        self.assertEqual(self.db.admin_review_summary()["githubIssuesInProgress"], 1)

        device = {"id": FENIX_8, "model": "fēnix 8", "variant": "47 mm, AMOLED", "installationStats": {}}
        detail = device_detail_page(
            device, {"username": "test"}, "csrf",
            operations=self.service.compatibility_identity_details("ACTIVE", device_id=FENIX_8),
            resolved_operations=self.service.compatibility_identity_details("RESOLVED", device_id=FENIX_8),
            open_problem_count=self.service.installation_problem_count(f"canonical:{FENIX_8}"),
        ).decode()
        self.assertEqual(int(KPI.search(detail).group(1)), dashboard)
        self.assertIn("2 installation problems need review.", detail)

    def test_prewrite_only_identity_stays_visible_and_counts(self):
        self.rows.diagnostic(canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
                             compatibility_identity="Venu X1", model="Venu X1", phase_outcome="FAILED",
                             write_started=False, failure_stage="preflight",
                             failure_code="INSTALL_BLOCKED_INSUFFICIENT_SPACE")
        self.rows.diagnostic()
        kpi, rows = self.installations()
        self.assertEqual(rows.get("identity:Venu X1"), 1)
        self.assertEqual(kpi, self.db.admin_review_summary()["installationIssues"])
        self.assertEqual(kpi, 1)
        body = diagnostics_page(
            self.service.compatibility_statistics(), {"username": "test"}, "csrf", identity="Venu X1",
            operations=self.service.compatibility_identity_details("ACTIVE", identity="Venu X1"),
            resolved_operations=[], unresolved_only=True,
            open_problem_count=self.service.installation_problem_count("identity:Venu X1"),
        ).decode()
        self.assertEqual(int(KPI.search(body).group(1)), 1)
        self.assertIn("data-tone='danger'", body.split("data-stat='openProblems'", 1)[0].rsplit("<div class='admin-metric'", 1)[1])

    def test_operation_spanning_identities_counts_once(self):
        operation = self.rows.uuid()
        self.rows.diagnostic(operation_id=operation, map_result_index=0, selected_map_count=2,
                             phase_outcome="FAILED", failure_stage="write", failure_code="INSTALL_FAILED_WRITE")
        self.rows.diagnostic(operation_id=operation, map_result_index=1, selected_map_count=2,
                             canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
                             compatibility_identity="Unknown watch", phase_outcome="FAILED",
                             failure_stage="write", failure_code="INSTALL_FAILED_WRITE")
        problems = self.db.installation_problem_counts()
        kpi, rows = self.installations()
        self.assertEqual(problems["total"], 1)
        self.assertEqual(sum(problems["byIdentity"].values()), 1)
        self.assertEqual((kpi, sum(rows.values())), (1, 1))

    def test_linking_issue_moves_task_and_resolving_clears_it(self):
        operation = self.rows.uuid()
        self.rows.diagnostic(operation_id=operation, phase_outcome="FAILED", failure_stage="write",
                             failure_code="INSTALL_FAILED_WRITE")
        self.assertEqual(self.installations()[0], 1)
        self.server.query("UPDATE compatibility_evidence_event SET linked_github_issue='#7'")
        self.assertEqual(self.installations()[0], 0)
        self.assertEqual(self.db.admin_review_summary()["installationIssues"], 0)
        self.server.query("UPDATE compatibility_evidence_event SET linked_github_issue=NULL, diagnostic_status='RESOLVED'")
        self.assertEqual(self.installations()[0], 0)


if __name__ == "__main__":
    unittest.main()

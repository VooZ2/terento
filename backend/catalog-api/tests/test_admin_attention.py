from __future__ import annotations

import hashlib
import json
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from terento_catalog import admin_attention
from terento_catalog.admin_attention import attention_report
from terento_catalog.config import Settings
from terento_catalog.http_api import ATTENTION_RATE_LIMIT, CatalogService, make_handler

TOKEN = "attention-test-token-" + "x" * 32
NOW = datetime(2026, 10, 25, 22, 49, tzinfo=timezone.utc)


class FakeDatabase:
    def admin_review_summary(self):
        return {
            "available": True, "installationIssues": 1, "githubIssuesInProgress": 0,
            "identityPending": 2, "readyToPublish": 0, "missingDiagnostics": 1,
        }

    def support_report_open_count(self):
        return 1

    def open_installation_problem_details(self):
        return [{
            "operation_key": "result:0f0c7f4e-79a8-4c0b-9a3a-6b8d6e0d1c11:0",
            "operation_id": "0f0c7f4e-79a8-4c0b-9a3a-6b8d6e0d1c11", "event_id": "event-1",
            "map_result_index": 0, "occurred_at": NOW, "model": "fēnix 7X Pro",
            "compatibility_identity": "fēnix 7X Pro", "canonical_device_model_id": "garmin-fenix-7x-pro",
            "phase_outcome": "FAILED", "failure_stage": "postwrite", "failure_code": "INSTALL_FAILED_CLEANUP",
            "write_started": True, "provider": "custom", "region": "CUSTOM",
            "release_label": "1.0.1", "app_build": "45",
            "firmware_version": "serialNumber=SERIAL-123 owner@example.com /Users/alice/private.img",
        }]

    def open_support_report_details(self, limit):
        return [{
            "reference": "TR-4GBKXX", "received_at": NOW, "category": "OTHER",
            "release_label": "1.0.1", "app_build": "45", "operation_id": None,
            "linked_github_issue": None,
            "user_message": "Maps vanish. Write me at owner@example.com, unitId=UNIT-456",
            "report": {"macOSVersion": "15.6", "device": {"model": "fēnix 8"}},
        }]


class FakeService:
    public_base_url = "https://api.terento.app"

    def __init__(self):
        self.database = FakeDatabase()

    def admin_devices(self):
        return {"devices": [{"id": "garmin-fenix-7x-pro", "model": "fēnix 7X Pro", "variant": None}]}

    def operational_health(self):
        return {
            "providers": [], "observations": [], "scheduler": None,
            "weekly": {"status": "FAILED", "summary": "One or more required Terento quality gates failed.",
                       "observed_at": NOW.isoformat()},
        }


UPDATE_ROWS = {"rows": [{
    "event_id": "6c2f3a3e-1d55-4b1c-9d37-7f1e3d1a2b40", "operation_id": "op-2",
    "occurred_at": NOW, "outcome": "FAILED", "diagnostic_status": "ACTIVE",
    "provider": "opentopomap", "region": "ESP", "canonical_device_model_id": None,
    "linked_github_issue": None,
    "payload": {"model": "Forerunner 965", "failureCode": "UPDATE_WRITE_FAILED",
                "terentoVersion": "1.0.1", "appBuild": "45"},
}], "totals": {"open_failed": 1}}


class AttentionReportTests(unittest.TestCase):
    def report(self):
        with patch.object(admin_attention, "load_update_diagnostics", return_value=UPDATE_ROWS):
            return attention_report(FakeService())

    def test_report_lists_needs_attention_populations_with_sanitised_text(self):
        report = self.report()
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["counts"]["installationIssues"], 1)
        self.assertEqual(report["counts"]["supportReports"], 1)

        problem = report["installationProblems"]["items"][0]
        self.assertEqual(report["installationProblems"]["total"], 1)
        self.assertEqual(problem["operationKey"], "0f0c7f4e-79a8-4c0b-9a3a-6b8d6e0d1c11")
        self.assertEqual(problem["model"], "fēnix 7X Pro")
        self.assertEqual(problem["appVersion"], "1.0.1 · build 45")
        self.assertTrue(problem["adminUrl"].startswith("https://api.terento.app/admin/"))
        self.assertIn("INSTALL\\_FAILED\\_CLEANUP", problem["issueBody"])

        update = report["updateProblems"]["items"][0]
        self.assertEqual(update["model"], "Forerunner 965")
        self.assertIn("diagnosticId=6c2f3a3e", update["adminUrl"])

        support = report["supportReports"]["items"][0]
        self.assertEqual(support["reference"], "TR-4GBKXX")
        self.assertEqual(support["adminUrl"], "https://api.terento.app/admin/support-reports/TR-4GBKXX")
        self.assertIn("Maps vanish.", support["userMessage"])

        check = report["systemChecks"]["items"][0]
        self.assertEqual((check["check"], check["status"]), ("Weekly tests", "FAILED"))

        serialized = json.dumps(report, ensure_ascii=False)
        for forbidden in ("SERIAL-123", "UNIT-456", "owner@example.com", "/Users/alice"):
            self.assertNotIn(forbidden, serialized)

    def test_a_failing_section_is_unavailable_not_empty(self):
        service = FakeService()
        service.database.open_installation_problem_details = lambda: 1 / 0
        with patch.object(admin_attention, "load_update_diagnostics", return_value=UPDATE_ROWS), \
                self.assertLogs("terento_catalog.admin_attention", "ERROR"):
            report = attention_report(service)
        self.assertEqual(report["installationProblems"], {"available": False})
        self.assertEqual(report["supportReports"]["total"], 1)


class AttentionRouteTests(unittest.TestCase):
    def start(self, digest):
        service = CatalogService(FakeDatabase(), admin_read_token_sha256=digest)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, token=None, method="GET"):
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, "/internal/attention",
                           headers={"Authorization": f"Bearer {token}"} if token else {})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def test_only_the_configured_token_reads_and_the_response_is_private(self):
        self.start(hashlib.sha256(TOKEN.encode()).hexdigest())
        for token in (None, "wrong-token-" + "y" * 32, hashlib.sha256(TOKEN.encode()).hexdigest()):
            response, body = self.request(token)
            self.assertEqual(response.status, 401)
            self.assertEqual(json.loads(body), {"error": "unauthorized"})
        with patch("terento_catalog.http_api.attention_report", return_value={"schemaVersion": 1}) as report:
            response, body = self.request(TOKEN)
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(body), {"schemaVersion": 1})
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertIn("noindex", response.getheader("X-Robots-Tag") or "")
            response, _ = self.request(TOKEN, method="POST")
            self.assertNotEqual(response.status, 200)
        self.assertEqual(report.call_count, 1)

    def test_route_is_closed_without_a_configured_digest(self):
        self.start(None)
        response, _ = self.request(TOKEN)
        self.assertEqual(response.status, 401)

    def test_reads_are_rate_limited_before_authorization(self):
        self.start(hashlib.sha256(TOKEN.encode()).hexdigest())
        for _ in range(ATTENTION_RATE_LIMIT):
            self.assertEqual(self.request()[0].status, 401)
        self.assertEqual(self.request(TOKEN)[0].status, 429)


class AttentionSettingsTests(unittest.TestCase):
    def test_settings_accept_only_a_sha256_digest(self):
        digest = hashlib.sha256(TOKEN.encode()).hexdigest()
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://x", "ADMIN_READ_TOKEN_SHA256": digest.upper()}):
            self.assertEqual(Settings.from_env().admin_read_token_sha256, digest)
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://x", "ADMIN_READ_TOKEN_SHA256": TOKEN}):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                Settings.from_env()
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://x"}, clear=True):
            self.assertIsNone(Settings.from_env().admin_read_token_sha256)


if __name__ == "__main__":
    unittest.main()

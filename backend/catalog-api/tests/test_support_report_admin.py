"""Support reports in Admin (S1): list, detail, actions with CSRF, Needs attention and Test data."""
import json
import re
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

from pglite_support import PGliteTestCase
from terento_catalog.admin import hash_password, local_test_data_page, overview_page
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.support_report_admin import support_report_detail_page, support_reports_page
from terento_catalog.support_reports import support_reference, validate_support_report

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
USER = {"username": "operator"}


def fixture(name="support-report.valid", **changes):
    body = json.loads((CONTRACTS / "fixtures" / f"{name}.json").read_text())
    body.update(changes)
    return body


def card_titles(body):
    return re.findall(r"<h2 id='[^']+-title'>([^<]+)</h2>", body)


def list_payload(rows, **changes):
    payload = {"rows": rows, "status": "OPEN", "limit": 50, "offset": 0, "openCount": len(rows),
               "handledCount": 4, "totalCount": len(rows) + 4, "filteredTotal": len(rows)}
    payload.update(changes)
    return payload


ROW = {
    "id": "6f1d2c3b-8a4e-4f60-9b7a-2c1d0e9f8a71", "reference": "TR-FYMEFT",
    "received_at": "2026-10-06T09:41:09Z", "created_at": "2026-10-06T09:41:07Z",
    "app_build": "42", "release_label": "1.0.0-beta.19", "is_local_test": False,
    "category": "INSTALL_FAILED", "operation_id": None, "status": "OPEN", "handled_at": None,
    "linked_github_issue": None, "title": "Installation stopped during Finishing — MapRando / Lithuania",
    "device_model": "fēnix 8", "device_variant": "51 mm, AMOLED", "has_user_message": True,
}


def detail(**changes):
    report = validate_support_report(json.dumps(fixture()).encode())
    value = {
        **ROW, "operation_id": report["operationId"], "user_message": report["userMessage"],
        "report": report["report"], "note": None, "handled_by_username": None, "audit": [],
        "installationDiagnostics": [], "updateDiagnostics": [],
    }
    value.update(changes)
    return value


class SupportReportRenderingTests(unittest.TestCase):
    def test_list_uses_the_kit_with_short_titles_pills_and_filters(self):
        body = support_reports_page(list_payload([ROW]), USER, "csrf").decode()
        self.assertIn("<title>Support reports · Terento</title>", body)
        self.assertIn("<h1>Support reports</h1>", body)
        self.assertTrue(all(len(title.split()) <= 2 for title in card_titles(body)), card_titles(body))
        for label in ("Open", "Handled", "Reports"):
            self.assertIn(f"<span class='admin-metric-label'>{label}", body)
        self.assertIn("data-scope='now'>Now</span>", body)
        self.assertIn("href='/admin/support-reports/TR-FYMEFT'", body)
        # Status pill: icon plus text, never colour alone.
        self.assertRegex(body, r"<span class='admin-pill admin-pill-warning' data-status='OPEN'><svg[^>]*>.*?</svg><span>Open</span></span>")
        self.assertIn("class='quick-filter active' href='/admin/support-reports?status=open' aria-current='page'>Open · 1</a>", body)
        self.assertIn("href='/admin/support-reports?status=handled'>Handled · 4</a>", body)
        self.assertIn("fēnix 8 · 51 mm, AMOLED", body)
        self.assertIn("beta.19 · build 42", body)
        nav = body.split('aria-label="Primary"', 1)[1].split("</div>", 1)[0]
        self.assertIn("<a class='active' href=\"/admin\">Dashboard</a>", nav)

    def test_list_empty_unavailable_and_pagination(self):
        empty = support_reports_page(list_payload([]), USER, "csrf").decode()
        self.assertIn("data-state='empty'", empty)
        self.assertIn("No open reports.", empty)
        handled = support_reports_page(list_payload([], status="HANDLED"), USER, "csrf", status="HANDLED").decode()
        self.assertIn("No handled reports.", handled)
        unavailable = support_reports_page(None, USER, "csrf").decode()
        self.assertIn("admin-card-unavailable", unavailable)
        self.assertIn("Could not load this section.", unavailable)
        self.assertIn(">Retry</a>", unavailable)
        paged = support_reports_page(list_payload([ROW], openCount=120, filteredTotal=120, offset=50), USER, "csrf").decode()
        self.assertIn("51–100 of 120", paged)
        self.assertIn("status=open&amp;offset=0'>Previous", paged)
        self.assertIn("status=open&amp;offset=100'>Next", paged)

    def test_detail_shows_facts_description_actions_and_collapsed_technical_details(self):
        body = support_report_detail_page(detail(), USER, "csrf-token").decode()
        self.assertIn("<h1><code>TR-FYMEFT</code></h1>", body)
        self.assertTrue(all(len(title.split()) <= 2 for title in card_titles(body)), card_titles(body))
        self.assertIn("<dt>Model</dt><dd>fēnix 8</dd>", body)
        self.assertIn("<dt>Error code</dt><dd>READBACK_FAILED, verificationRequired</dd>", body)
        self.assertIn("maprando / Lithuania · 2026-09-02", body)
        self.assertIn("The watch disconnected near the end of the transfer.\nIt was on the charging cable.", body)
        self.assertIn("<details class='admin-disclosure support-report-technical'><summary>Technical details</summary>", body)
        self.assertNotIn("<details class='admin-disclosure support-report-technical' open", body)
        self.assertIn("FINISH_TRACE native event=read_failed", body)
        self.assertIn("boundary: readback", body)
        self.assertEqual(body.count("name='csrf_token' value='csrf-token'"), 2)  # handle and issue forms
        self.assertIn("action='/admin/support-reports/handle'", body)
        self.assertIn(">Mark handled</button>", body)
        self.assertIn("No installation or update report with this operation ID was received.", body)
        handled = support_report_detail_page(detail(status="HANDLED", handled_at="2026-10-06T12:00:00Z",
                                                    handled_by_username="operator", linked_github_issue="#41",
                                                    audit=[{"action": "HANDLED", "changed_by_username": "operator",
                                                            "changed_at": "2026-10-06T12:00:00Z", "note": "Replied"}]),
                                             USER, "csrf", action="handled").decode()
        self.assertIn("action='/admin/support-reports/reopen'", handled)
        self.assertIn("Report marked handled.", handled)
        self.assertIn("href='https://github.com/VooZ2/terento/issues/41'", handled)
        self.assertIn("<strong>Marked handled</strong>", handled)

    def test_detail_links_matching_diagnostics_and_marks_local_reports(self):
        linked = support_report_detail_page(detail(
            installationDiagnostics=[{"compatibility_identity": "fēnix 8 · 51 mm", "canonical_device_model_id": "fenix-8-51",
                                      "result_count": 1, "last_occurred_at": "2026-10-06T09:40:00Z"}],
            updateDiagnostics=[{"event_id": "11111111-1111-4111-8111-111111111111", "outcome": "FAILED",
                                "provider": "maprando", "region": "lituanie", "occurred_at": "2026-10-06T09:40:00Z"}],
        ), USER, "csrf").decode()
        self.assertIn("href='/admin/devices/fenix-8-51?from=installations#installations'", linked)
        self.assertIn("href='/admin/update-diagnostics?diagnosticId=11111111-1111-4111-8111-111111111111'", linked)
        local = support_report_detail_page(detail(is_local_test=True), USER, "csrf").decode()
        self.assertIn("<span>Local test</span>", local)
        self.assertIn("href='/admin/test-data'", local)
        self.assertIn("Local test report: diagnostics are not linked.", local)
        no_operation = support_report_detail_page(detail(operation_id=None), USER, "csrf").decode()
        self.assertIn("No operation ID was sent with this report.", no_operation)

    def test_user_text_is_escaped(self):
        body = support_report_detail_page(detail(user_message="<script>alert(1)</script>"), USER, "csrf").decode()
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_needs_attention_row_counts_and_unavailable_state(self):
        def attention(**overview):
            body = overview_page({"period": "24h", "data": {}, "providers": [], **overview},
                                 {"username": "operator", "admin_review_summary": {"available": True}}, "csrf").decode()
            return body.split("id='overview-attention-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("aria-label='Support reports: 3'", attention(supportReports={"openCount": 3}))
        unavailable = attention(supportReports={"available": False})
        self.assertIn("aria-label='Support reports: unavailable'", unavailable)
        self.assertNotIn("aria-label='Support reports: 0'", unavailable)
        self.assertIn("aria-label='Support reports: unavailable'", attention())

    def test_test_data_lists_local_reports_only_there(self):
        summary = {"diagnosticEventCount": 0, "mapEventCount": 0, "operationCount": 0, "releaseLabels": [],
                   "activity": [], "supportReports": list_payload([{**ROW, "is_local_test": True}])}
        body = local_test_data_page(summary, USER, "csrf").decode()
        self.assertIn(">Support reports</h2>", body)
        self.assertIn("href='/admin/support-reports/TR-FYMEFT'", body)
        self.assertIn("local test support reports", body)
        unavailable = local_test_data_page({**summary, "supportReports": {"available": False}}, USER, "csrf").decode()
        self.assertIn("admin-card-unavailable", unavailable)
        without = local_test_data_page({k: v for k, v in summary.items() if k != "supportReports"}, USER, "csrf").decode()
        self.assertNotIn(">Support reports</h2>", without)


class SupportReportAdminHTTPTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.service = CatalogService(self.db)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.db.create_admin_user("operator", hash_password("correct horse battery staple"))
        self.session, self.csrf = self.service.login_admin("operator", "correct horse battery staple")

    def store(self, **changes):
        body = fixture(id=str(uuid4()), **changes)
        self.assertEqual(self.db.insert_support_report(validate_support_report(json.dumps(body).encode())), "stored")
        return support_reference(body["id"])

    def request(self, method, path, form=None, *, cookie=True):
        connection = HTTPConnection(*self.http.server_address)
        headers = {}
        if cookie:
            headers["Cookie"] = f"terento_admin_session={self.session}; terento_admin_csrf={self.csrf}"
        body = None
        if form is not None:
            body = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read().decode()
        connection.close()
        return response, payload

    def test_list_detail_and_error_pages(self):
        public = self.store()
        local = self.store(releaseLabel="1.0.0-beta.19-local")
        response, body = self.request("GET", "/admin/support-reports")
        self.assertEqual(response.status, 200)
        self.assertIn(f"/admin/support-reports/{public}'", body)
        self.assertNotIn(local, body)
        self.assertEqual(self.request("GET", f"/admin/support-reports/{public}")[0].status, 200)
        response, body = self.request("GET", f"/admin/support-reports/{local}")
        self.assertEqual(response.status, 200)
        self.assertIn("<span>Local test</span>", body)
        response, body = self.request("GET", "/admin/support-reports/not-a-reference")
        self.assertEqual((response.status, "text/html" in response.headers["Content-Type"]), (400, True))
        response, body = self.request("GET", "/admin/support-reports/TR-AAAAAA")
        self.assertEqual(response.status, 404)
        self.assertIn("This support report does not exist.", body)
        self.assertEqual(self.request("GET", "/admin/support-reports?status=done")[0].status, 400)
        self.assertIn(self.request("GET", "/admin/support-reports", cookie=False)[0].status, {302, 303})

    def test_list_query_failure_keeps_the_admin_chrome(self):
        with patch.object(self.db, "support_reports", side_effect=RuntimeError("down")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.request("GET", "/admin/support-reports")
        self.assertEqual(response.status, 200)
        self.assertIn("admin-card-unavailable", body)
        self.assertIn("admin-section-nav", body)

    def test_actions_require_csrf_and_are_audited(self):
        reference = self.store()
        response, _ = self.request("POST", "/admin/support-reports/handle", {"reference": reference, "csrf_token": "wrong"})
        self.assertEqual(response.status, 403)
        response, _ = self.request("POST", "/admin/support-reports/handle", {"reference": reference})
        self.assertEqual(response.status, 403)
        self.assertEqual(self.db.support_report_open_count(), 1)
        response, _ = self.request("POST", "/admin/support-reports/handle",
                                   {"reference": reference, "csrf_token": self.csrf, "note": "Replied by email"})
        self.assertEqual(response.status, 303)
        self.assertEqual(response.headers["Location"], f"/admin/support-reports/{reference}?action=handled")
        self.assertEqual(self.db.support_report_open_count(), 0)
        response, _ = self.request("POST", "/admin/support-reports/issue",
                                   {"reference": reference, "csrf_token": self.csrf, "linked_github_issue": "41"})
        self.assertEqual(response.headers["Location"], f"/admin/support-reports/{reference}?action=linked")
        response, _ = self.request("POST", "/admin/support-reports/issue",
                                   {"reference": reference, "csrf_token": self.csrf, "linked_github_issue": "not an issue"})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/admin/support-reports/reopen",
                                   {"reference": reference, "csrf_token": self.csrf, "note": "x" * 2001})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/admin/support-reports/reopen", {"reference": "TR-AAAAAA", "csrf_token": self.csrf})
        self.assertEqual(response.status, 404)
        detail = self.db.support_report_detail(reference)
        self.assertEqual((detail["status"], detail["linked_github_issue"], detail["note"]), ("HANDLED", "#41", "Replied by email"))
        self.assertEqual([item["action"] for item in detail["audit"]], ["ISSUE_LINKED", "HANDLED"])

    def test_dashboard_row_counts_open_public_reports_and_degrades_alone(self):
        self.store()
        self.store(releaseLabel="1.0.0-beta.19-local")
        handled = self.store()
        self.db.review_support_report(handled, action="handle", admin_user_id=None)
        response, body = self.request("GET", "/admin")
        self.assertEqual(response.status, 200)
        self.assertIn("aria-label='Support reports: 1'", body)
        with patch.object(self.db, "support_report_open_count", side_effect=RuntimeError("down")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.request("GET", "/admin")
        self.assertEqual(response.status, 200)
        self.assertIn("aria-label='Support reports: unavailable'", body)

    def test_test_data_shows_and_purges_local_reports(self):
        public = self.store()
        local = self.store(releaseLabel="1.0.0-beta.19-local")
        response, body = self.request("GET", "/admin/test-data")
        self.assertEqual(response.status, 200)
        self.assertIn(f"/admin/support-reports/{local}'", body)
        self.assertNotIn(public, body)
        response, _ = self.request("POST", "/admin/test-data/purge",
                                   {"csrf_token": self.csrf, "confirmation": "DELETE_LOCAL_TEST_DATA"})
        self.assertEqual(response.status, 303)
        self.assertIsNone(self.db.support_report_detail(local))
        self.assertIsNotNone(self.db.support_report_detail(public))


if __name__ == "__main__":
    unittest.main()

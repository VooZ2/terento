"""HTML routes answer with HTML error pages; scripts get nonces only at template sites."""

from __future__ import annotations

import json
import re
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from api_test_fixtures import FakeProviderDatabase
from pglite_support import PGliteTestCase
from terento_catalog import provider_rechecks
from terento_catalog.admin import (
    AdminValidationError,
    _ADMIN_NONCE_PLACEHOLDER,
    _layout,
    _normalise_github_issue_reference,
    github_issue_queue_page,
    hash_password,
    token_hash,
)
from terento_catalog.db import Database
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.map_preview.store import PreviewDatabase
from terento_catalog.provider_catalog import OPENTOPO_MAP

COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"


class NonceTests(unittest.TestCase):
    def test_placeholder_is_unguessable_and_data_scripts_get_no_nonce(self):
        self.assertNotEqual(_ADMIN_NONCE_PLACEHOLDER, "__TERENTO_ADMIN_NONCE__")
        self.assertRegex(_ADMIN_NONCE_PLACEHOLDER, r"^__TERENTO_ADMIN_NONCE_[0-9a-f]{24}__$")
        # Content that already contains a literal <script> (an escaping slip)
        # is never decorated with the nonce placeholder by the layout.
        body = _layout("Test", "<main id='main-content'><script>alert(1)</script></main>").decode()
        self.assertIn("<script>alert(1)</script>", body)
        self.assertEqual(body.count(_ADMIN_NONCE_PLACEHOLDER), 2)  # layout's own two scripts


class AdminHttpResilienceTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeProviderDatabase()
        self.service = CatalogService(self.database)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, method="GET", cookie=COOKIE):
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, path, headers={"Cookie": cookie} if cookie else {})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data.decode()

    def post_form(self, path, form, cookie=COOKIE):
        connection = HTTPConnection(*self.server.server_address)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie:
            headers["Cookie"] = cookie
        connection.request("POST", path, body=urlencode(form), headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data.decode()

    def test_admin_post_database_failure_is_a_503_not_a_dropped_connection(self):
        form = {"csrf_token": "csrf", "device_id": "garmin-x", "support_status": "SUPPORTED"}
        with patch.object(self.service, "update_device_authorization", side_effect=RuntimeError("deadlock")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.post_form("/admin/devices/support", form)
        self.assertEqual((response.status, json.loads(body)), (503, {"error": "admin_unavailable"}))
        with patch.object(self.service, "admin_session", side_effect=RuntimeError("restart")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.post_form("/admin/devices/support", form)
        self.assertEqual(response.status, 503)

    def test_nul_in_an_admin_form_field_is_a_400(self):
        with patch.object(self.service, "update_device_authorization") as update:
            response, body = self.post_form("/admin/devices/support", {
                "csrf_token": "csrf", "device_id": "garmin-x", "support_status": "SUPPORTED", "note": "a\x00b",
            })
        self.assertEqual((response.status, json.loads(body)), (400, {"error": "invalid_form"}))
        update.assert_not_called()

    def test_login_attempt_is_counted_before_the_password_check(self):
        # A check that never returns a verdict (here: storage down) still uses up an attempt.
        with patch.object(self.service, "login_admin", side_effect=RuntimeError("down")) as login:
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                statuses = [self.post_form("/admin/login", {"username": "u", "password": "p"}, cookie=None)[0].status
                            for _ in range(11)]
        self.assertEqual(statuses, [503] * 10 + [429])
        self.assertEqual(login.call_count, 10)

    def test_retired_provider_controls_are_a_409(self):
        headers = {"Content-Type": "application/json", "Cookie": COOKIE, "X-CSRF-Token": "csrf"}
        self.database.set_package_downloads = Mock(side_effect=LookupError("provider_retired"))
        connection = HTTPConnection(*self.server.server_address)
        connection.request("POST", "/admin/providers/freizeitkarte/downloads", body=json.dumps(
            {"packageId": "pkg", "enabled": True, "reason": ""}), headers=headers)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual((response.status, json.loads(body)), (409, {"error": "provider_retired"}))

    def test_unknown_admin_page_is_an_html_404_inside_the_chrome(self):
        response, body = self.request("/admin/does-not-exist")
        self.assertEqual(response.status, 404)
        self.assertIn("text/html", response.headers["Content-Type"])
        self.assertIn("<h1 id='admin-error-title'>Not found</h1>", body)
        self.assertIn("admin-section-nav", body)

    def test_failing_html_route_is_an_html_503_and_json_route_stays_json(self):
        with patch.object(self.service, "admin_devices", side_effect=RuntimeError("down")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.request("/admin/device-identification")
            self.assertEqual(response.status, 503)
            self.assertIn("text/html", response.headers["Content-Type"])
            self.assertIn("Model sources could not be loaded.", body)
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.request("/admin/devices.json")
            self.assertEqual(response.status, 503)
            self.assertIn("application/json", response.headers["Content-Type"])

    def test_recheck_status_failure_returns_json_instead_of_dropping_the_connection(self):
        with patch("terento_catalog.provider_rechecks.jobs", side_effect=RuntimeError("down")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                response, body = self.request("/admin/providers/freizeitkarte/rechecks")
        self.assertEqual(response.status, 503)
        self.assertIn("provider_rechecks_unavailable", body)

    def test_invalid_map_filter_is_an_html_400(self):
        response, body = self.request("/admin/map-statistics?period=year")
        self.assertEqual(response.status, 400)
        self.assertIn("text/html", response.headers["Content-Type"])
        self.assertIn("<h1 id='admin-error-title'>Invalid link</h1>", body)

    def test_response_nonce_replaces_only_the_template_placeholder(self):
        response, body = self.request("/admin/campaign-links")
        self.assertEqual(response.status, 200)
        nonce = re.search(r"script-src 'nonce-([^']+)'", response.headers["Content-Security-Policy"]).group(1)
        self.assertNotIn(_ADMIN_NONCE_PLACEHOLDER, body)
        tags = re.findall(r"<script\b[^>]*>", body, re.IGNORECASE)
        self.assertTrue(tags)
        self.assertTrue(all(tag == f'<script nonce="{nonce}">' for tag in tags))


    def test_removed_glossary_url_redirects_to_dashboard_behind_the_admin_gate(self):
        for path in ("/admin/glossary", "/admin/glossary/"):
            response, body = self.request(path)
            self.assertEqual(response.status, 303)
            self.assertEqual(response.headers["Location"], "/admin")
            self.assertEqual(body, "")
            response, _ = self.request(path, cookie=None)
            self.assertEqual(response.status, 303)
            self.assertEqual(response.headers["Location"], "/admin/login")


class AdminServiceHardeningTests(unittest.TestCase):
    def test_unknown_username_pays_the_same_password_hash_cost(self):
        database = Mock(admin_user_by_username=Mock(return_value=None))
        with patch("terento_catalog.http_api.verify_password", return_value=False) as verify:
            with self.assertRaises(AdminValidationError):
                CatalogService(database).login_admin("nobody", "guess")
        verify.assert_called_once()

    def test_non_ascii_setup_secret_is_a_validation_error(self):
        database = Mock(admin_user_count=Mock(return_value=0))
        service = CatalogService(database, admin_bootstrap_secret="one-time-secret")
        with self.assertRaisesRegex(AdminValidationError, "deployment secret is incorrect"):
            service.setup_admin("operator", "long-test-password", "sécret")

    def test_issue_number_zero_is_rejected_everywhere(self):
        with self.assertRaises(ValueError):
            _normalise_github_issue_reference("#0")
        self.assertEqual(_normalise_github_issue_reference("#32"), "#32")
        database = Database("unused")
        with self.assertRaises(ValueError):
            database.update_diagnostic_issue("op", linked_github_issue="#0")
        with self.assertRaises(ValueError):
            database.update_diagnostic_lifecycle("op", new_status="ACTIVE", admin_user_id=None, linked_github_issue="0")

    def test_activation_gate_and_update_run_under_the_provider_lock(self):
        class BusyDatabase(FakeProviderDatabase):
            def execute(self, sql, args=()):
                if sql.startswith("SELECT pg_try_advisory_lock"):
                    return type("LockResult", (), {"fetchone": lambda _: {"acquired": False}})()
                return super().execute(sql, args)
        database = BusyDatabase()
        database.set_provider_status = Mock(return_value=True)
        with self.assertRaisesRegex(ValueError, "provider_busy"):
            CatalogService(database).set_provider_status("freizeitkarte", "ACTIVE", admin_user_id=7)
        database.set_provider_status.assert_not_called()
        CatalogService(database).set_provider_status("freizeitkarte", "PAUSED", admin_user_id=7)
        database.set_provider_status.assert_called_once()

    def test_busy_collection_is_not_audited_as_a_failed_collection(self):
        database = FakeProviderDatabase()
        with patch.object(provider_rechecks, "ensure_retry_allowed", side_effect=ValueError("provider_busy")):
            with self.assertRaisesRegex(ValueError, "provider_busy"):
                CatalogService(database).collect_provider("freizeitkarte", admin_user_id=7)
        self.assertEqual(database.audits, [])

    def test_manifest_built_across_a_preview_switch_is_not_served(self):
        service = CatalogService(FakeProviderDatabase())

        def switch_during_build():
            service._preview_manifest_generation += 1  # what POST .../previews does after its commit
            return set()

        with patch.object(PreviewDatabase, "enabled_providers", side_effect=switch_during_build) as enabled, \
                patch.object(PreviewDatabase, "layers", return_value={}), \
                patch.object(PreviewDatabase, "scores", return_value={}):
            service.preview_manifest_response()
            service.preview_manifest_response()
        self.assertEqual(enabled.call_count, 2)


class AdminPostgresHardeningTests(PGliteTestCase):
    def test_password_change_signs_out_only_the_other_sessions(self):
        user = self.db.create_admin_user("operator", hash_password("long-test-password"))
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        for token in ("current", "other"):
            self.db.create_admin_session(int(user["id"]), token_hash(token), token_hash(token + "-csrf"), expires)
        service = CatalogService(self.db)
        session = self.db.admin_session(token_hash("current"))
        service.update_admin_account(session, "owner", "long-test-password", "", "", "current")
        self.assertIsNotNone(self.db.admin_session(token_hash("other")))  # username only
        service.update_admin_account(
            self.db.admin_session(token_hash("current")), "owner", "long-test-password",
            "another-long-password", "another-long-password", "current",
        )
        self.assertIsNotNone(self.db.admin_session(token_hash("current")))
        self.assertIsNone(self.db.admin_session(token_hash("other")))

    def test_retired_provider_controls_report_provider_retired(self):
        self.db.ensure_provider_definition(OPENTOPO_MAP)
        self.sql("UPDATE map_provider SET status = 'RETIRED' WHERE id = %s", (OPENTOPO_MAP.id,))
        for action in (
            lambda: self.db.set_package_downloads(OPENTOPO_MAP.id, "pkg", True, "", None, None),
            lambda: PreviewDatabase(self.db).set_preview_enabled(OPENTOPO_MAP.id, True, None, None),
            lambda: provider_rechecks.enqueue(self.db, OPENTOPO_MAP.id, None, None),
        ):
            with self.assertRaisesRegex(LookupError, "provider_retired"):
                action()
        with self.assertRaisesRegex(LookupError, "provider_not_found"):
            PreviewDatabase(self.db).set_preview_enabled("missing", True, None, None)

    def test_manual_health_check_audit_is_written_with_its_observation(self):
        from dataclasses import replace
        from terento_catalog.provider_health import check_provider
        from test_provider_health import Probe
        self.db.ensure_provider_definition(OPENTOPO_MAP)
        health_id = self.db.record_provider_health(
            replace(check_provider(OPENTOPO_MAP, probe=Probe()), provider_id=OPENTOPO_MAP.id),
            audit={"admin_user_id": None, "action": "provider.health_checked", "request_id": "r1",
                   "details": {"status": "HEALTHY"}},
        )
        rows = self.sql("SELECT action, provider_id, target FROM admin_audit_log WHERE request_id = 'r1'")
        self.assertEqual(rows, [{"action": "provider.health_checked", "provider_id": OPENTOPO_MAP.id,
                                 "target": str(health_id)}])


class GithubIssuesPageTests(unittest.TestCase):
    def test_page_is_named_github_issues_and_highlights_the_dashboard(self):
        body = github_issue_queue_page([], [], {"username": "operator"}, "csrf").decode()
        self.assertIn("<title>GitHub issues · Terento</title>", body)
        self.assertIn("<h1>GitHub issues</h1>", body)
        nav = body.split('aria-label="Primary"', 1)[1].split("</div>", 1)[0]
        self.assertIn("<a class='active' href=\"/admin\">Dashboard</a>", nav)


if __name__ == "__main__":
    unittest.main()

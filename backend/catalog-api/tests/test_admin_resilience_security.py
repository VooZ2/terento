"""HTML routes answer with HTML error pages; scripts get nonces only at template sites."""

from __future__ import annotations

import re
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.admin import _ADMIN_NONCE_PLACEHOLDER, _layout, github_issue_queue_page
from terento_catalog.http_api import CatalogService, make_handler

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


class GithubIssuesPageTests(unittest.TestCase):
    def test_page_is_named_github_issues_and_highlights_the_dashboard(self):
        body = github_issue_queue_page([], [], {"username": "operator"}, "csrf").decode()
        self.assertIn("<title>GitHub issues · Terento</title>", body)
        self.assertIn("<h1>GitHub issues</h1>", body)
        nav = body.split('aria-label="Primary"', 1)[1].split("</div>", 1)[0]
        self.assertIn("<a class='active' href=\"/admin\">Dashboard</a>", nav)


if __name__ == "__main__":
    unittest.main()

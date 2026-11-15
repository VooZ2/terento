"""GET /internal/attention?page= gives the read-only agent the Admin page text."""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import quote

from api_test_fixtures import FakeProviderDatabase
from terento_catalog import http_api
from terento_catalog.admin import ADMIN_STYLESHEET_PATH
from terento_catalog.admin_agent_view import agent_page, html_text
from terento_catalog.http_api import ATTENTION_PAGE_RATE_LIMIT, CatalogService, make_handler

TOKEN = "agent-page-test-token-" + "x" * 32
COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"


class AgentPagePathTests(unittest.TestCase):
    def test_only_admin_get_pages_are_readable(self):
        for page in ("/admin", "/admin/", "/admin/installations?period=30d", "/admin/devices/garmin-fenix-8",
                     "/admin/api/umami?period=7d", "/admin/devices.json", "/admin/providers/osmapa-pl.json"):
            self.assertEqual(agent_page(page), page)
        for page in ("", "/", "/health", "/adminx", "https://api.terento.app/admin", "//evil/admin",
                     "/admin/login", "/admin/setup", "/admin/logout", "/admin/account", "/admin/account/",
                     "/admin/web-installer.csv", ADMIN_STYLESHEET_PATH, "/admin/map-assets/leaflet-1.9.4.js",
                     "/admin/../internal/attention", "/admin/x#frag", "/admin/a b", "/admin\\x",
                     "/admin/" + "x" * 600):
            self.assertIsNone(agent_page(page), page)


class HtmlTextTests(unittest.TestCase):
    def test_text_keeps_what_the_owner_reads_and_drops_controls_and_private_values(self):
        view = html_text(
            "<html><head><title>Devices · Terento Admin</title><style>.x{}</style></head><body>"
            "<nav><a href='/admin/installations'>Installations</a></nav>"
            "<main id='main-content'><h1>fēnix 8</h1><p>Installs <strong>3</strong> of &lt;20</p>"
            "<table><tr><th>When</th><th>Result</th></tr><tr><td>11-15</td><td>Failed -5</td></tr></table>"
            "<ul><li>Note: owner@example.com at /Users/alice/x.img serial=ABC123</li></ul>"
            "<form method='post' action='/admin/problems/resolve'><input type='hidden' name='csrf_token' value='csrf'>"
            "<button>Resolve</button></form><script>secret()</script>"
            "<p hidden>Hidden error</p><span aria-hidden='true'>decorative</span>"
            "<svg role='group' aria-label='Installs per day'><text>axis</text></svg>"
            "<g data-chart-values='{\"date\":\"2026-11-15\",\"total\":4,\"values\":[[\"ok\",\"Successful\",3],[\"fail\",\"Failed\",1]]}'></g>"
            "<a href='https://github.com/VooZ2/terento/issues/new?title=x&amp;body=y'>Prepare GitHub issue</a>"
            "<a href='/admin/devices/garmin-fenix-8?period=30d#history'>History</a>"
            "<a href='/admin/login'>Sign in</a></main></body></html>"
        )
        text = view["text"]
        self.assertEqual(view["title"], "Devices · Terento Admin")
        self.assertIn("# fēnix 8", text)
        self.assertIn("Installs 3 of ‹20", text)
        self.assertIn("When | Result", text)
        self.assertIn("11-15 | Failed -5", text)
        self.assertIn("[chart] Installs per day", text)
        self.assertIn("[chart value] 2026-11-15: Successful 3; Failed 1; total 4", text)
        self.assertIn("Resolve", text)  # a label, never a usable form
        for hidden in ("secret()", "csrf", "Hidden error", "decorative", "axis", ".x{}",
                       "owner@example.com", "alice", "ABC123"):
            self.assertNotIn(hidden, text)
        self.assertIn("[redacted email]", text)
        self.assertEqual(view["links"], ["/admin/installations", "/admin/devices/garmin-fenix-8?period=30d"])
        self.assertFalse(view["truncated"])


class AgentPageRouteTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeProviderDatabase()
        self.service = CatalogService(self.database, admin_read_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, *, token=TOKEN, method="GET", cookie=None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if cookie:
            headers["Cookie"] = cookie
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def page(self, page, **kwargs):
        return self.request("/internal/attention?page=" + quote(page, safe=""), **kwargs)

    def test_agent_reads_the_same_page_text_the_owner_sees(self):
        owner, owner_body = self.request("/admin/system-health", token=None, cookie=COOKIE)
        self.assertEqual(owner.status, 200)
        response, body = self.page("/admin/system-health")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertIn("noindex", response.getheader("X-Robots-Tag") or "")
        self.assertTrue(response.getheader("Content-Type").startswith("application/json"))
        document = json.loads(body)
        self.assertEqual(document["schemaVersion"], 1)
        self.assertEqual(document["page"], "/admin/system-health")
        self.assertEqual(document["status"], 200)
        # Same renderer, same data: only the per-request nonce and CSRF value differ,
        # and neither reaches the text.
        self.assertEqual(document["text"], html_text(owner_body.decode())["text"])
        self.assertIn("/admin/installations", document["links"])
        self.assertNotIn("csrf", body.decode())

    def test_token_is_required_and_other_routes_stay_closed(self):
        for token in (None, "wrong-token-" + "y" * 32):
            response, body = self.page("/admin/system-health", token=token)
            self.assertEqual(response.status, 401)
            self.assertEqual(json.loads(body), {"error": "unauthorized"})
        # The token is not an Admin login.
        response, _ = self.request("/admin/system-health")
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/admin/login")
        response, _ = self.page("/admin/system-health", method="POST")
        self.assertNotEqual(response.status, 200)
        for page in ("/admin/login", "/admin/account", "/admin/web-installer.csv", "/health", "https://x/admin"):
            response, body = self.page(page)
            self.assertEqual(response.status, 400, page)
            self.assertEqual(json.loads(body), {"error": "page_not_readable"})

    def test_agent_read_ignores_browser_cookies_and_never_touches_sessions(self):
        with patch.object(self.service, "admin_session", side_effect=AssertionError("session read")), \
                patch.object(self.service, "logout_admin", side_effect=AssertionError("session cleared")):
            response, body = self.page("/admin/system-health", cookie=COOKIE)
        self.assertEqual(response.status, 200)
        self.assertNotIn("Set-Cookie", dict(response.getheaders()))

    def test_admin_redirects_are_followed_inside_admin(self):
        response, body = self.page("/admin/glossary")
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertEqual(document["page"], "/admin")
        self.assertIn(document["status"], {200, 503})

    def test_missing_page_reports_the_admin_status(self):
        response, body = self.page("/admin/no-such-page")
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertEqual(document["status"], 404)
        self.assertIn("This admin page does not exist.", document["text"])

    def test_direct_writes_are_refused_not_sent_half_captured(self):
        with patch.object(http_api, "agent_page", side_effect=lambda page: page), \
                self.assertLogs("terento_catalog.http_api", "ERROR"):
            response, body = self.page(ADMIN_STYLESHEET_PATH)
        self.assertEqual(response.status, 503)
        self.assertEqual(json.loads(body), {"error": "page_unavailable"})

    def test_page_reads_have_their_own_rate_limit(self):
        for _ in range(ATTENTION_PAGE_RATE_LIMIT):
            self.page("/admin/no-such-page", token=None)
        response, _ = self.page("/admin/system-health")
        self.assertEqual(response.status, 429)
        # The Needs attention read keeps its own budget.
        with patch("terento_catalog.http_api.attention_report", return_value={"schemaVersion": 1}):
            response, _ = self.request("/internal/attention")
        self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()

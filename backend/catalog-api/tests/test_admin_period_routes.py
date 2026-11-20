"""Every Admin route that reads a period keeps its own default (one helper)."""
from __future__ import annotations

import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.http_api import CatalogService, make_handler

SESSION = "terento_admin_session=session; terento_admin_csrf=csrf"


class _Database(FakeProviderDatabase):
    def delete_admin_session(self, token_hash):
        pass


class AdminPeriodRouteTests(unittest.TestCase):
    # path, service method, how the period reaches it, default, uses the shared choice
    ROUTES = (
        ("/admin", "admin_overview", lambda args: args[0], "24h", True),
        ("/admin/web-installer", "web_installer", lambda args: args[0]["period"], "7d", True),
        ("/admin/web-installer.json", "web_installer", lambda args: args[0]["period"], "7d", True),
        ("/admin/first-run", "app_funnel", lambda args: args[0]["period"], "24h", True),
        ("/admin/web-installer.csv", "web_installer_export", lambda args: args[0]["period"], "7d", False),
        ("/admin/api/umami", "website_stats", lambda args: args[0], "7d", True),
    )

    def setUp(self):
        self.service = CatalogService(_Database())
        self.seen: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def record(self, name, extract):
        def method(*args, **kwargs):
            self.seen.append(extract(args))
            if name == "website_stats":
                return {}  # this JSON route does not catch service errors
            raise RuntimeError("period recorded")
        return method

    def period_for(self, path, method, extract, query="", cookie=""):
        self.seen.clear()
        setattr(self.service, method, self.record(method, extract))
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path + query, headers={"Cookie": SESSION + cookie})
        connection.getresponse().read()
        connection.close()
        self.assertEqual(len(self.seen), 1, path)
        return self.seen[0]

    def test_defaults_link_and_shared_choice(self):
        for path, method, extract, default, shared in self.ROUTES:
            with self.subTest(path=path):
                read = lambda **kw: self.period_for(path, method, extract, **kw)
                self.assertEqual(read(), default)
                self.assertEqual(read(query="?period=30d"), "30d")
                self.assertEqual(read(query="?period=bogus"), default)
                remembered = read(cookie="; terento_admin_period=all")
                self.assertEqual(remembered, "all" if shared else default)
                # The link's own period wins over the remembered one.
                self.assertEqual(read(query="?period=today", cookie="; terento_admin_period=all"), "today")
                self.assertEqual(read(query="?period=bogus", cookie="; terento_admin_period=all"),
                                 "all" if shared else default)
                self.assertEqual(read(cookie="; terento_admin_period=bogus"), default)


if __name__ == "__main__":
    unittest.main()

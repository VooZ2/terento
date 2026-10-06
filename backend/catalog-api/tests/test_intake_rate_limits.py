"""Anonymous intake limits behind the production reverse proxy (contracts finding #6)."""
import json
import os
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from uuid import uuid4

from api_test_fixtures import FakeProviderDatabase
from terento_catalog import http_api
from terento_catalog.config import DEFAULT_TRUSTED_PROXIES, Settings
from terento_catalog.http_api import CatalogService, make_handler


def map_event():
    return {
        "schemaVersion": 1, "id": str(uuid4()), "operationId": str(uuid4()),
        "timestamp": "2026-10-01T12:00:00Z", "providerId": "freizeitkarte",
        "releaseLabel": "1.0.0-beta.18", "mapId": "freizeitkarte-deu", "region": "DEU",
        "eventType": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED", "appBuild": "40",
    }


class ClientAddressTests(unittest.TestCase):
    def setUp(self):
        self.service = CatalogService(FakeProviderDatabase())

    def test_forwarded_header_is_trusted_only_from_a_trusted_proxy(self):
        self.assertEqual(self.service.client_address_for("203.0.113.9", ["198.51.100.7"]), "203.0.113.9")
        self.assertEqual(self.service.client_address_for("172.18.0.3", ["198.51.100.7"]), "198.51.100.7")
        self.assertEqual(self.service.client_address_for("127.0.0.1", []), "127.0.0.1")

    def test_rightmost_untrusted_hop_wins_and_spoofed_prefixes_are_ignored(self):
        self.assertEqual(
            self.service.client_address_for("172.18.0.3", ["1.1.1.1, 198.51.100.7", "10.0.0.5"]),
            "198.51.100.7",
        )
        self.assertEqual(self.service.client_address_for("172.18.0.3", ["not-an-ip"]), "172.18.0.3")
        self.assertEqual(self.service.client_address_for("172.18.0.3", ["10.0.0.4"]), "172.18.0.3")

    def test_no_trusted_proxies_ignores_forwarded_headers(self):
        service = CatalogService(FakeProviderDatabase(), trusted_proxies=())
        self.assertEqual(service.client_address_for("127.0.0.1", ["198.51.100.7"]), "127.0.0.1")

    def test_configuration(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True):
            self.assertEqual(Settings.from_env().trusted_proxies, DEFAULT_TRUSTED_PROXIES)
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example", "CATALOG_TRUSTED_PROXIES": "none"}, clear=True):
            self.assertEqual(Settings.from_env().trusted_proxies, ())
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example",
                                     "CATALOG_TRUSTED_PROXIES": "172.20.0.2, 10.1.0.0/16"}, clear=True):
            self.assertEqual(Settings.from_env().trusted_proxies, ("172.20.0.2/32", "10.1.0.0/16"))
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example", "CATALOG_TRUSTED_PROXIES": "proxy"}, clear=True):
            with self.assertRaises(RuntimeError):
                Settings.from_env()


class IntakeBurstTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CatalogService(FakeProviderDatabase())))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection(*self.server.server_address)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, forwarded=None):
        headers = {"Content-Type": "application/json"}
        if forwarded:
            headers["X-Forwarded-For"] = forwarded
        self.connection.request("POST", "/map-events", body=json.dumps(map_event()).encode(), headers=headers)
        response = self.connection.getresponse()
        response.read()
        return response.status

    def test_one_multi_map_burst_fits_the_map_event_limit(self):
        # Ten maps with contours emit about seventy events within seconds.
        statuses = [self.post() for _ in range(70)]
        self.assertTrue(all(status < 300 for status in statuses), statuses)
        self.assertGreaterEqual(http_api.MAP_EVENT_RATE_LIMIT, 600)
        self.assertGreaterEqual(http_api.COMPATIBILITY_EVENT_RATE_LIMIT, 300)

    def test_clients_behind_the_proxy_have_separate_buckets(self):
        with patch.object(http_api, "MAP_EVENT_RATE_LIMIT", 3):
            first = [self.post("198.51.100.7") for _ in range(4)]
            second = [self.post("198.51.100.8") for _ in range(3)]
        self.assertEqual(first[-1], 429)
        self.assertTrue(all(status < 300 for status in first[:3] + second), (first, second))


if __name__ == "__main__":
    unittest.main()

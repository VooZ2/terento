"""Unstorable intake values are client errors (400), never retryable 503s (contracts #14)."""
import json
import socket
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from api_test_fixtures import FakeProviderDatabase
from jsonschema import Draft202012Validator
from terento_catalog import http_api
from terento_catalog.compatibility_evidence import EvidenceValidationError, validate_event
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.map_events import MapEventValidationError, validate_map_event
from test_compatibility_evidence import event as legacy_event

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def fixture(name):
    return json.loads((CONTRACTS / "fixtures" / f"{name}.json").read_text())


def schema(name):
    return Draft202012Validator(json.loads((CONTRACTS / f"{name}.schema.json").read_text()))


class ValidationMatrixTests(unittest.TestCase):
    def assert_rejected(self, body, code=None):
        with self.assertRaises(EvidenceValidationError) as raised:
            validate_event(json.dumps(body).encode())
        if code:
            self.assertEqual(str(raised.exception), code)

    def test_non_uuid_identifiers_matching_the_old_regex_are_rejected(self):
        current = fixture("compatibility-event.valid")
        for bad in ("-" * 36, "123e4567e89b12d3a456426614174000----", "g" * 8 + "-1111-1111-1111-111111111111"):
            self.assert_rejected(dict(current, id=bad), "invalid_event_id")
            self.assertFalse(schema("compatibility-event").is_valid(dict(current, id=bad)))
            self.assert_rejected(dict(current, operationId=bad), "invalid_operation_id")
        validate_event(json.dumps(current).encode())

    def test_legacy_versions_reject_values_the_columns_cannot_store(self):
        for changes, code in (
            ({"operationId": "not-a-uuid"}, "invalid_operation_id"),
            ({"mapResultIndex": True}, "invalid_mapResultIndex"),
            ({"mapResultIndex": "0"}, "invalid_mapResultIndex"),
            ({"selectedMapCount": 0}, "invalid_selectedMapCount"),
            ({"writeStarted": "yes"}, "invalid_writeStarted"),
            ({"failureStage": "somewhere"}, "invalid_failureStage"),
            ({"transferProgressBucket": "50"}, "invalid_transfer_progress_bucket"),
            ({"identityResolutionCode": "SERIAL"}, "invalid_identity_resolution_code"),
            ({"appBuild": 40}, "invalid_appBuild"),
        ):
            for version in (1, 2):
                with self.subTest(changes=changes, version=version):
                    self.assert_rejected(legacy_event(schemaVersion=version, **changes), code)
        # Valid legacy optional values remain accepted.
        validate_event(json.dumps(legacy_event(
            schemaVersion=2, operationId="123e4567-e89b-12d3-a456-426614174001", mapResultIndex=0,
            selectedMapCount=1, appBuild="12", releaseLabel="anything", writeStarted=True,
        )).encode())

    def test_boolean_is_not_a_map_event_schema_version(self):
        body = dict(fixture("map-event.valid"), schemaVersion=True)
        self.assertFalse(schema("map-event").is_valid(body))
        with self.assertRaises(MapEventValidationError):
            validate_map_event(json.dumps(body).encode())
        for key in ("mapResultIndex",):
            with self.assertRaises(MapEventValidationError):
                validate_map_event(json.dumps(dict(fixture("map-event.valid"), **{key: True})).encode())


class HTTPStatusTests(unittest.TestCase):
    def setUp(self):
        from test_http_api import FakeDatabase
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CatalogService(FakeDatabase())))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, path, body):
        connection = HTTPConnection(*self.server.server_address)
        connection.request("POST", path, body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        response.read()
        connection.close()
        return response.status

    def test_invalid_identifiers_return_400(self):
        self.assertEqual(self.post("/compatibility/events", dict(fixture("compatibility-event.valid"), id="-" * 36)), 400)
        self.assertEqual(self.post("/map-events", dict(fixture("map-event.valid"), schemaVersion=True)), 400)


class SocketTimeoutTests(unittest.TestCase):
    def test_handler_has_a_bounded_socket_timeout(self):
        handler = make_handler(CatalogService(FakeProviderDatabase()))
        self.assertEqual(handler.timeout, http_api.REQUEST_SOCKET_TIMEOUT_SECONDS)
        self.assertGreaterEqual(handler.timeout, 30)

    def test_stalled_body_releases_the_server_thread(self):
        with patch.object(http_api, "REQUEST_SOCKET_TIMEOUT_SECONDS", 0.5):
            handler = make_handler(CatalogService(FakeProviderDatabase()))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = socket.create_connection(server.server_address, timeout=5)
            client.sendall(b"POST /map-events HTTP/1.1\r\nHost: test\r\nContent-Type: application/json\r\n"
                           b"Content-Length: 4000\r\n\r\n{")
            started = time.monotonic()
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
            self.assertLess(time.monotonic() - started, 4)
            client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

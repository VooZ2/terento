"""Released beta.9 (builds 10/11) map events predate releaseLabel and stay accepted."""
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from jsonschema import Draft202012Validator

from pglite_support import PGliteTestCase
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.map_events import MapEventValidationError, validate_map_event

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
LEGACY = json.loads((CONTRACTS / "fixtures/map-event.valid-beta9-legacy.json").read_text())
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "map-event.schema.json").read_text()))


class LegacyShapeValidationTests(unittest.TestCase):
    def test_exact_beta9_shape_is_accepted_with_unknown_release(self):
        SCHEMA.validate(LEGACY)
        event = validate_map_event(json.dumps(LEGACY).encode())
        self.assertIsNone(event["releaseLabel"])
        self.assertEqual(event["appBuild"], "11")
        for event_type, outcome in (("DOWNLOAD_STARTED", "UNKNOWN"), ("DOWNLOAD_FAILED", "FAILED"),
                                    ("INSTALL_FAILED", "FAILED")):
            body = dict(LEGACY, eventType=event_type, outcome=outcome)
            SCHEMA.validate(body)
            self.assertIsNone(validate_map_event(json.dumps(body).encode())["releaseLabel"])

    def test_current_shapes_still_require_release_label(self):
        for changes in (
            {"mapResultIndex": 0},
            {"acquisitionId": "3F2A1B0C-4D5E-4F60-8A7B-9C0D1E2F3A4C", "componentKind": "main",
             "eventType": "DOWNLOAD_SUCCEEDED"},
            {"eventType": "MAP_UPDATE_SUCCEEDED"},
            {"appBuild": None},
        ):
            body = dict(LEGACY, **changes)
            with self.subTest(changes=changes):
                self.assertFalse(SCHEMA.is_valid(body))
                with self.assertRaises(MapEventValidationError):
                    validate_map_event(json.dumps(body).encode())
        body = dict(LEGACY)
        body.pop("appBuild")
        self.assertFalse(SCHEMA.is_valid(body))
        with self.assertRaises(MapEventValidationError):
            validate_map_event(json.dumps(body).encode())

    def test_explicit_release_label_keeps_normal_validation(self):
        with self.assertRaises(MapEventValidationError):
            validate_map_event(json.dumps(dict(LEGACY, releaseLabel="development")).encode())


class LegacyIntakeStorageTests(PGliteTestCase):
    def post(self, server, document):
        connection = HTTPConnection(*server.server_address)
        connection.request("POST", "/map-events", body=json.dumps(document).encode(),
                           headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, body

    def test_beta9_event_is_stored_once_as_unknown_nonlocal_release(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CatalogService(self.db)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            first, _ = self.post(server, LEGACY)
            replay, _ = self.post(server, LEGACY)
            rejected, _ = self.post(server, dict(LEGACY, mapResultIndex=0, id="8D1C3A52-9E4B-4F0A-B7C1-2D5E6F708193"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertLess(first, 300)
        self.assertLess(replay, 300)
        self.assertEqual(rejected, 400)
        rows = self.sql("SELECT release_label, is_local_test, app_build FROM map_download_event")
        self.assertEqual(rows, [{"release_label": None, "is_local_test": False, "app_build": "11"}])


if __name__ == "__main__":
    unittest.main()

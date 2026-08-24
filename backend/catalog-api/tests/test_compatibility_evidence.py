from __future__ import annotations

import base64
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from terento_catalog.compatibility_evidence import EvidenceValidationError, validate_event
from terento_catalog.http_api import CatalogService, make_handler


def event(**changes):
    value = {
        "schemaVersion": 1,
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "timestamp": "2026-08-24T12:00:00Z",
        "model": "fēnix 8",
        "family": "fēnix",
        "firmwareVersion": "20.19",
        "usbVendorID": 2334,
        "usbProductID": 10345,
        "transport": "MTP",
        "provider": "freizeitkarte",
        "region": "LTU",
        "mapRelease": "2026-08",
        "terentoVersion": "1.0.0",
        "macOSVersion": "macOS 15.6",
        "phaseOutcome": "SUCCEEDED",
        "automaticFinishingResult": "VERIFIED",
        "errorCategory": None,
        "userConfirmed": False,
    }
    value.update(changes)
    return value


class FakeEvidenceDatabase:
    def __init__(self):
        self.events = {}

    def insert_compatibility_event(self, value):
        if value["id"] in self.events:
            return False
        self.events[value["id"]] = value
        return True

    def compatibility_statistics(self):
        return [{
            "model": "fēnix 8", "firmware_versions": "20.19", "attempted_install_count": 1,
            "successful_install_count": 1, "failed_install_count": 0, "success_rate": 100,
            "last_success": "2026-08-24", "last_failure": None, "error_categories": {},
            "calculated_status": "TESTED", "physical_device_evidence_count": 1,
            "review_notes": "Owner evidence",
        }]


class CompatibilityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeEvidenceDatabase()
        service = CatalogService(
            self.database,
            compatibility_admin_username="operator",
            compatibility_admin_password="long-test-password",
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse(); data = response.read(); connection.close()
        return response, data

    def test_event_is_idempotent(self):
        body = json.dumps(event()).encode()
        first, _ = self.request("POST", "/compatibility/events", body, {"Content-Type": "application/json"})
        second, duplicate = self.request("POST", "/compatibility/events", body, {"Content-Type": "application/json"})
        self.assertEqual(first.status, 201)
        self.assertEqual(second.status, 200)
        self.assertEqual(json.loads(duplicate)["status"], "duplicate")

    def test_privacy_fields_and_local_paths_are_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**event(), "serialNumber": "secret"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(event(model="/Users/alice/watch")).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(event(phaseOutcome="SUCCEEDED", automaticFinishingResult="FAILED")).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(event(usbVendorID=70000)).encode())

    def test_operator_page_requires_authentication_and_is_noindex(self):
        denied, _ = self.request("GET", "/internal/compatibility/")
        credentials = base64.b64encode(b"operator:long-test-password").decode()
        allowed, body = self.request("GET", "/internal/compatibility/", headers={"Authorization": f"Basic {credentials}"})
        self.assertEqual(denied.status, 401)
        self.assertEqual(allowed.status, 200)
        self.assertEqual(allowed.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn(b"f\xc4\x93nix 8", body)


if __name__ == "__main__":
    unittest.main()

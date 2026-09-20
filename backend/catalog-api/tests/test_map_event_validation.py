import json
import unittest

from terento_catalog.map_events import MapEventValidationError, validate_map_event, validate_statistics_filters
from terento_catalog.telemetry import is_local_release_label


class MapEventValidationTests(unittest.TestCase):
    def test_map_event_validation_is_private_and_normalizes_identifiers(self):
        event = validate_map_event(json.dumps({
            "schemaVersion": 1,
            "id": "A8098C1A-F86E-11DA-BD1A-00112444BE1E",
            "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
            "timestamp": "2026-08-31T10:00:00Z",
            "providerId": "Freizeitkarte",
            "mapId": "FZK-LTU",
            "region": "lt",
            "eventType": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED",
            "appBuild": "beta.8",
            "releaseLabel": "1.0.0-beta.8",
        }).encode())
        self.assertEqual(event["providerId"], "freizeitkarte")
        self.assertEqual(event["mapId"], "fzk-ltu")
        self.assertEqual(event["region"], "LT")
        self.assertNotIn("deviceId", event)
        self.assertEqual(event["id"], "a8098c1a-f86e-11da-bd1a-00112444be1e")

    def test_map_event_validation_rejects_raw_device_fields_and_bad_filters(self):
        payload = {
            "schemaVersion": 1,
            "id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
            "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
            "timestamp": "2026-08-31T10:00:00Z",
            "providerId": "freizeitkarte",
            "eventType": "DOWNLOAD_STARTED",
            "outcome": "UNKNOWN",
            "releaseLabel": "1.0.0-beta.8",
            "unitId": "must-not-be-accepted",
        }
        with self.assertRaises(MapEventValidationError):
            validate_map_event(json.dumps(payload).encode())
        custom_payload = {
            key: value for key, value in payload.items()
            if key != "unitId"
        }
        custom_payload.update({
            "providerId": "custom",
            "mapId": "custom-map",
            "region": None,
        })
        with self.assertRaisesRegex(MapEventValidationError, "unsupported_provider"):
            validate_map_event(json.dumps(custom_payload).encode())
        with self.assertRaises(MapEventValidationError):
            validate_statistics_filters({"region": "LT", "dateFrom": "2026-09-01T00:00:00Z", "dateTo": "2026-08-31T00:00:00Z"})

    def test_release_label_is_strict_and_local_classification_is_exact(self):
        base = {
            "schemaVersion": 1,
            "id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
            "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
            "timestamp": "2026-08-31T10:00:00Z",
            "providerId": "freizeitkarte",
            "eventType": "DOWNLOAD_STARTED",
            "outcome": "UNKNOWN",
        }
        accepted = validate_map_event(json.dumps({**base, "releaseLabel": "1.0.0"}).encode())
        self.assertFalse(is_local_release_label(accepted["releaseLabel"]))
        local = validate_map_event(json.dumps({**base, "releaseLabel": "1.0.0-beta.10-local"}).encode())
        self.assertTrue(is_local_release_label(local["releaseLabel"]))
        for label in (None, "", "development", "1.0", "1.0.0-local ", "v1.0.0"):
            with self.subTest(label=label), self.assertRaises(MapEventValidationError):
                validate_map_event(json.dumps({**base, "releaseLabel": label}).encode())

"""Optional inventoryMetrics on installation reports (A10): acceptance, storage, Admin, read model."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from pglite_support import PGliteTestCase
from terento_catalog.admin import _diagnostic_technical_details
from terento_catalog.compatibility_evidence import EvidenceValidationError, validate_event

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "compatibility-event.schema.json").read_text()))
FIXTURE = json.loads((CONTRACTS / "fixtures" / "compatibility-event.valid-inventory-metrics.json").read_text())


def event(metrics=..., **changes):
    body = deepcopy(FIXTURE)
    body["id"], body["operationId"] = str(uuid4()), str(uuid4())
    if metrics is ...:
        pass
    elif metrics is None:
        body.pop("inventoryMetrics")
    else:
        body["inventoryMetrics"] = metrics
    body.update(changes)
    return body


class InventoryMetricsValidationTests(unittest.TestCase):
    def test_valid_metrics_are_accepted_and_optional(self):
        SCHEMA.validate(FIXTURE)
        self.assertEqual(validate_event(json.dumps(FIXTURE).encode())["inventoryMetrics"]["scope"], "GARMIN")
        minimal = {"scope": "FULL", "prewriteObjectCount": 0, "prewriteDurationMs": 0}
        SCHEMA.validate(event(minimal))
        self.assertEqual(validate_event(json.dumps(event(minimal)).encode())["inventoryMetrics"], minimal)
        without = validate_event(json.dumps(event(None)).encode())
        self.assertNotIn("inventoryMetrics", without)
        self.assertNotIn("inventoryMetrics", validate_event(json.dumps(event(None) | {"inventoryMetrics": None}).encode()))

    def test_invalid_metrics_are_rejected(self):
        good = FIXTURE["inventoryMetrics"]
        for metrics in (
            {**good, "path": "/GARMIN"},
            {**good, "scope": "ROOT"},
            {**good, "prewriteObjectCount": 10_000_001},
            {**good, "prewriteDurationMs": 86_400_001},
            {**good, "postwriteDurationMs": -1},
            {**good, "prewriteDurationMs": 1.5},
            {**good, "prewriteObjectCount": True},
            {"scope": "FULL", "prewriteObjectCount": 1},
            [],
        ):
            with self.subTest(metrics=metrics):
                self.assertFalse(SCHEMA.is_valid(event(metrics)))
                with self.assertRaises(EvidenceValidationError) as raised:
                    validate_event(json.dumps(event(metrics)).encode())
                self.assertIn(str(raised.exception), {"invalid_inventory_metrics", "forbidden_field"})

    def test_admin_technical_details_show_metrics(self):
        details = _diagnostic_technical_details({"inventory_metrics": FIXTURE["inventoryMetrics"]}, 1)
        self.assertIn("<dt>Inventory scope</dt><dd>GARMIN</dd>", details)
        self.assertIn("<dt>Pre-write check (ms)</dt><dd>4210</dd>", details)
        self.assertIn("<dt>Post-write objects</dt><dd>1844</dd>", details)
        self.assertNotIn("Inventory scope", _diagnostic_technical_details({}, 1))


class InventoryMetricsStorageTests(PGliteTestCase):
    def store(self, metrics, **changes):
        self.assertTrue(self.db.insert_compatibility_event(validate_event(json.dumps(event(metrics, **changes)).encode())))

    def test_metrics_are_stored_and_summarised_for_public_reports_only(self):
        for duration, count in ((1000, 100), (2000, 200), (3000, 300), (4000, 400), (10000, 1000)):
            self.store({"scope": "GARMIN", "prewriteObjectCount": count, "prewriteDurationMs": duration})
        self.store({"scope": "FULL", "prewriteObjectCount": 5000, "prewriteDurationMs": 9000})
        self.store({"scope": "GARMIN", "prewriteObjectCount": 9, "prewriteDurationMs": 999999},
                   releaseLabel="1.0.0-beta.19-local", terentoVersion="1.0.0-beta.19-local")
        self.store(None)
        stored = self.sql("SELECT inventory_metrics FROM compatibility_evidence_event WHERE inventory_metrics IS NOT NULL")
        self.assertEqual(len(stored), 7)
        models = self.db.inventory_metrics_distribution()
        garmin = next(row for row in models if row["scope"] == "GARMIN")
        self.assertEqual(garmin["reportCount"], 5)
        self.assertEqual(garmin["prewriteDurationMs"], {"median": 3000.0, "p90": 7600.0})
        self.assertEqual(garmin["prewriteObjectCount"]["median"], 300.0)
        self.assertEqual(sum(row["reportCount"] for row in models), 6)
        # Metrics are diagnostics only: the install counts are unchanged by them.
        statistics = self.db.compatibility_statistics()
        self.assertEqual(sum(int(row.get("successful_install_count") or 0) for row in statistics), 7)

    def test_update_reports_keep_metrics_in_their_payload(self):
        body = json.loads((CONTRACTS / "fixtures" / "compatibility-event.valid-update-failed.json").read_text())
        body["id"], body["operationId"] = str(uuid4()), str(uuid4())
        body["inventoryMetrics"] = {"scope": "FULL", "prewriteObjectCount": 12, "prewriteDurationMs": 345}
        self.assertTrue(self.db.insert_compatibility_event(validate_event(json.dumps(body).encode())))
        payload = self.sql("SELECT payload FROM map_update_diagnostic WHERE event_id = %s", (body["id"],))[0]["payload"]
        self.assertEqual(payload["inventoryMetrics"]["prewriteDurationMs"], 345)


if __name__ == "__main__":
    unittest.main()

"""App first-run funnel telemetry (F-01): validation, storage, retention and read model."""
import json
import threading
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from pglite_support import PGliteTestCase
from terento_catalog.app_funnel import ALLOWED_FUNNEL_KEYS, FUNNEL_OUTCOMES, FunnelValidationError, validate_funnel_event
from terento_catalog.http_api import CatalogService, make_handler

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "app-funnel-event.schema.json").read_text()))


def fixture(name="app-funnel-event.valid"):
    return json.loads((CONTRACTS / "fixtures" / f"{name}.json").read_text())


def funnel(**changes):
    body = {
        "schemaVersion": 1, "id": str(uuid4()), "sessionId": str(uuid4()),
        "occurredAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "appBuild": "41", "releaseLabel": "1.0.0-beta.19", "stage": "DEVICE_CONNECT", "outcome": "CONNECTED",
    }
    body.update(changes)
    return {key: value for key, value in body.items() if value is not ...}


class ValidationMatrixTests(unittest.TestCase):
    def assert_valid(self, body):
        SCHEMA.validate(body)
        return validate_funnel_event(json.dumps(body).encode())

    def assert_invalid(self, body, code):
        self.assertFalse(SCHEMA.is_valid(body), body)
        with self.assertRaises(FunnelValidationError) as raised:
            validate_funnel_event(json.dumps(body).encode())
        self.assertEqual(str(raised.exception), code)

    def test_schema_allowlist_matches_the_server(self):
        self.assertEqual(set(SCHEMA.schema["properties"]), ALLOWED_FUNNEL_KEYS)
        for name in ("app-funnel-event.valid", "app-funnel-event.valid-catalog-partial", "app-funnel-event.valid-device-timeout"):
            self.assert_valid(fixture(name))

    def test_every_stage_outcome_pair_and_only_those(self):
        for stage, outcomes in FUNNEL_OUTCOMES.items():
            for outcome in outcomes:
                event = self.assert_valid(funnel(stage=stage, outcome=outcome))
                self.assertEqual((event["stage"], event["outcome"]), (stage, outcome))
        self.assert_invalid(funnel(stage="CATALOG", outcome="CONNECTED"), "invalid_outcome")
        self.assert_invalid(funnel(stage="INSTALL", outcome="OTHER"), "invalid_stage")

    def test_field_rules(self):
        self.assertEqual(self.assert_valid(funnel(stage="AUTHORIZATION", outcome="AMBIGUOUS", baseModel="fenix 8"))["baseModel"], "fenix 8")
        self.assertEqual(self.assert_valid(funnel(baseModel="Forerunner 965"))["baseModel"], "Forerunner 965")
        self.assertEqual(self.assert_valid(funnel(stage="CATALOG", outcome="REMOTE_PARTIAL", droppedPackageCount=0))["droppedPackageCount"], 0)
        self.assertIsNone(validate_funnel_event(json.dumps(funnel(baseModel=None)).encode())["baseModel"])
        for body, code in (
            (funnel(serialNumber="1"), "unknown_fields"),
            (funnel(sessionId=...), "missing_fields"),
            (funnel(schemaVersion=True), "unsupported_schema"),
            (funnel(schemaVersion=2), "unsupported_schema"),
            (funnel(id="-" * 36), "invalid_id"),
            (funnel(sessionId="not-a-uuid"), "invalid_sessionId"),
            (funnel(occurredAt="2026-10-05T12:00:00+02:00"), "invalid_occurredAt"),
            (funnel(occurredAt="2026-10-05T12:00:00"), "invalid_occurredAt"),
            (funnel(appBuild=""), "invalid_appBuild"),
            (funnel(releaseLabel="development"), "invalid_releaseLabel"),
            (funnel(stage="DEVICE_CONNECT", outcome="BUSY", baseModel="fenix 8"), "unexpected_baseModel"),
            (funnel(stage="CATALOG", outcome="REMOTE", baseModel="fenix 8"), "unexpected_baseModel"),
            (funnel(baseModel="x" * 81), "invalid_baseModel"),
            (funnel(stage="CATALOG", outcome="REMOTE", droppedPackageCount=1), "unexpected_droppedPackageCount"),
            (funnel(stage="CATALOG", outcome="REMOTE_PARTIAL", droppedPackageCount=-1), "invalid_droppedPackageCount"),
            (funnel(stage="CATALOG", outcome="REMOTE_PARTIAL", droppedPackageCount=True), "invalid_droppedPackageCount"),
        ):
            with self.subTest(code=code, body=body):
                self.assert_invalid(body, code)
        with self.assertRaises(FunnelValidationError):
            validate_funnel_event(json.dumps(funnel(baseModel="/Users/someone")).encode())
        with self.assertRaises(FunnelValidationError) as raised:
            validate_funnel_event(json.dumps(funnel(appBuild="x" * 5000)).encode())
        self.assertEqual(str(raised.exception), "payload_size")

    def test_local_label_is_classified(self):
        self.assertTrue(validate_funnel_event(json.dumps(funnel(releaseLabel="1.0.0-beta.19-local")).encode())["isLocalTest"])
        self.assertFalse(validate_funnel_event(json.dumps(funnel()).encode())["isLocalTest"])


class WaitingModelCatalogStatusTests(unittest.TestCase):
    def test_status_explains_pending_from_the_current_policy_without_family_matching(self):
        def row(device_id, model, map_capable, active=True):
            return {"device_id": device_id, "manufacturer": "Garmin", "model": model, "canonical_model": model,
                    "active": active, "map_capable": map_capable}

        class PolicyDatabase:
            def installation_policy_snapshot(self):
                return [
                    row("garmin-fenix-6x-51", "fēnix 6X", True),
                    row("garmin-venu-x1", "Venu X1", None),
                    row("garmin-a-47", "Instinct 9", True), row("garmin-a-51", "Instinct 9 51 mm", False),
                    row("garmin-fr-70", "Forerunner 70", False),
                    row("garmin-old", "Old Watch", True, active=False),
                ], datetime(2026, 10, 9, tzinfo=timezone.utc)

        service = CatalogService(PolicyDatabase())
        models = [{"baseModel": name, "outcome": "PENDING", "sessionCount": 1} for name in (
            "fenix 6x pro", "fenix 6x asia", "fēnix 6X", "Venu X1", "instinct 9", "forerunner 70", "old watch")]
        statuses = [item["catalogStatus"] for item in service._funnel_model_catalog_status(models)]
        self.assertEqual(statuses, ["NOT_IN_CATALOG", "NOT_IN_CATALOG", "APPROVED_NOW", "MAPS_UNKNOWN",
                                    "MIXED", "NO_MAPS", "WITHDRAWN"])
        self.assertEqual(service._funnel_model_catalog_status([]), [])

        class BrokenDatabase:
            def installation_policy_snapshot(self):
                raise RuntimeError("down")

        with self.assertLogs("terento_catalog.http_api", level="ERROR"):
            broken = CatalogService(BrokenDatabase())._funnel_model_catalog_status(models[:1])
        self.assertEqual(broken[0]["catalogStatus"], "UNAVAILABLE")


class FunnelStorageTests(PGliteTestCase):
    def store(self, **changes):
        return self.db.insert_app_funnel_event(validate_funnel_event(json.dumps(funnel(**changes)).encode()))

    def test_idempotent_insert_and_read_model_counts_distinct_sessions(self):
        session_a, session_b, session_c = (str(uuid4()) for _ in range(3))
        event_id = str(uuid4())
        self.assertTrue(self.store(id=event_id, sessionId=session_a))
        self.assertFalse(self.store(id=event_id, sessionId=session_a))
        self.store(sessionId=session_b)
        self.store(sessionId=session_a, stage="AUTHORIZATION", outcome="PENDING", baseModel="Forerunner 965")
        self.store(sessionId=session_b, stage="AUTHORIZATION", outcome="PENDING", baseModel="Forerunner 965")
        self.store(sessionId=session_c, stage="AUTHORIZATION", outcome="UNKNOWN_MODEL", baseModel="Venu X1")
        self.store(sessionId=session_c, stage="AUTHORIZATION", outcome="APPROVED", baseModel="fenix 8")
        # Local builds are stored but excluded from statistics.
        self.store(sessionId=str(uuid4()), releaseLabel="1.0.0-beta.19-local", stage="CATALOG", outcome="BUNDLED_FALLBACK")
        self.assertEqual(self.sql("SELECT count(*) AS n FROM app_funnel_event")[0]["n"], 7)
        summary = self.db.app_funnel_summary(None)
        counts = {(row["stage"], row["outcome"]): row["sessionCount"] for row in summary["stages"]}
        self.assertEqual(summary["sessionCount"], 3)
        self.assertEqual(counts[("DEVICE_CONNECT", "CONNECTED")], 2)
        self.assertEqual(counts[("AUTHORIZATION", "PENDING")], 2)
        self.assertNotIn(("CATALOG", "BUNDLED_FALLBACK"), counts)
        self.assertEqual(summary["modelsNeedingReview"], [
            {"baseModel": "Forerunner 965", "outcome": "PENDING", "sessionCount": 2},
            {"baseModel": "Venu X1", "outcome": "UNKNOWN_MODEL", "sessionCount": 1},
        ])

    def test_period_and_retention(self):
        now = self.sql("SELECT now() AS now")[0]["now"]
        old = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        self.store(occurredAt=old)
        self.store()
        self.assertEqual(self.db.app_funnel_summary(now - timedelta(days=7))["sessionCount"], 1)
        self.assertEqual(self.db.app_funnel_summary(None)["sessionCount"], 2)
        self.sql("UPDATE app_funnel_event SET received_at = now() - interval '25 months' WHERE occurred_at < now() - interval '1 day'")
        self.db.prune_compatibility_events()
        self.assertEqual(self.sql("SELECT count(*) AS n FROM app_funnel_event")[0]["n"], 1)

    def test_never_connected_counts_distinct_period_sessions_without_a_connection(self):
        now = self.sql("SELECT now() AS now")[0]["now"]
        connected_only, problem_then_connected, problem_only, catalog_only = (str(uuid4()) for _ in range(4))
        self.store(sessionId=connected_only)
        self.store(sessionId=problem_then_connected, outcome="NOT_MTP_MODE")
        self.store(sessionId=problem_then_connected, outcome="BUSY")
        self.store(sessionId=problem_then_connected)
        self.store(sessionId=problem_only, outcome="TIMEOUT_NO_USB")
        self.store(sessionId=problem_only, outcome="NOT_MTP_MODE")
        self.store(sessionId=catalog_only, stage="CATALOG", outcome="REMOTE")
        # Local test builds and sessions outside the period are excluded; a
        # connection outside the period does not count for the period.
        self.store(sessionId=str(uuid4()), releaseLabel="1.0.0-beta.19-local", outcome="TIMEOUT_NO_USB")
        old = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        self.store(sessionId=str(uuid4()), outcome="FAILED", occurredAt=old)
        earlier_connection = str(uuid4())
        self.store(sessionId=earlier_connection, occurredAt=old)
        self.store(sessionId=earlier_connection, outcome="DISCONNECTED")
        summary = self.db.app_funnel_summary(now - timedelta(days=7))
        counts = {(row["stage"], row["outcome"]): row["sessionCount"] for row in summary["stages"]}
        self.assertEqual(summary["sessionCount"], 5)
        self.assertEqual(summary["neverConnectedSessionCount"], 3)
        self.assertEqual(counts[("DEVICE_CONNECT", "CONNECTED")], 2)
        self.assertEqual(counts[("DEVICE_CONNECT", "NOT_MTP_MODE")], 2)
        all_time = self.db.app_funnel_summary(None)
        self.assertEqual((all_time["sessionCount"], all_time["neverConnectedSessionCount"]), (6, 3))
        self.assertEqual(self.db.app_funnel_summary(now + timedelta(days=1))["neverConnectedSessionCount"], 0)

    def test_journey_never_connected_reasons_and_trend(self):
        now = self.sql("SELECT now() AS now")[0]["now"]
        approved, pending, busy_only, silent = (str(uuid4()) for _ in range(4))
        self.store(sessionId=approved, outcome="BUSY")
        self.store(sessionId=approved)
        self.store(sessionId=approved, stage="AUTHORIZATION", outcome="APPROVED", baseModel="fenix 8")
        self.store(sessionId=pending)
        self.store(sessionId=pending, stage="AUTHORIZATION", outcome="PENDING", baseModel="fenix 6x pro")
        self.store(sessionId=busy_only, outcome="BUSY")
        self.store(sessionId=busy_only, outcome="TIMEOUT_NO_USB")
        self.store(sessionId=silent, stage="CATALOG", outcome="REMOTE")
        summary = self.db.app_funnel_summary(now - timedelta(days=1), trend_bucket="hour", time_zone="Europe/Vilnius")
        self.assertEqual((summary["sessionCount"], summary["neverConnectedSessionCount"],
                          summary["approvedSessionCount"], summary["neverConnectedWithoutSignalCount"]), (4, 2, 1, 1))
        # Only never-connected sessions: BUSY of the approved session is not here.
        self.assertEqual(sorted((row["outcome"], row["sessionCount"]) for row in summary["neverConnectedOutcomes"]),
                         [("BUSY", 1), ("TIMEOUT_NO_USB", 1)])
        self.assertEqual(sum(row["sessionCount"] for row in summary["trend"]), 4)
        self.assertEqual(sum(row["connectedSessionCount"] for row in summary["trend"]), 2)
        self.assertTrue(all(row["bucket"].tzinfo is not None and row["bucket"].minute == 0 for row in summary["trend"]))
        self.assertNotIn("trend", self.db.app_funnel_summary(None))

    def test_funnel_never_enters_install_statistics(self):
        self.store(stage="INSTALL_BLOCKED", outcome="DEVICE_STORAGE")
        self.assertEqual(self.db.map_statistics({}), [])
        self.assertEqual(self.db.admin_review_summary()["installationIssues"], 0)


class FunnelHTTPTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.service = CatalogService(self.db)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, content_type="application/json"):
        connection = HTTPConnection(*self.server.server_address)
        headers = {"Content-Type": content_type} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response, payload

    def test_intake_statuses(self):
        body = json.dumps(funnel()).encode()
        self.assertEqual(self.request("POST", "/app-funnel/events", body)[0].status, 201)
        self.assertEqual(self.request("POST", "/app-funnel/events", body)[0].status, 200)
        self.assertEqual(self.request("POST", "/app-funnel/events", json.dumps(funnel(extra=1)).encode())[0].status, 400)
        self.assertEqual(self.request("POST", "/app-funnel/events", body, content_type="text/plain")[0].status, 415)
        self.assertEqual(self.request("POST", "/app-funnel/events", b"x" * 5000)[0].status, 413)

    def test_admin_json_requires_authentication(self):
        response, _ = self.request("GET", "/admin/app-funnel.json")
        self.assertIn(response.status, {302, 303})
        self.assertNotIn("application/json", response.getheader("Content-Type") or "")

    def test_admin_read_model_payload(self):
        self.request("POST", "/app-funnel/events",
                     json.dumps(funnel(stage="AUTHORIZATION", outcome="PENDING", baseModel="fenix 8")).encode())
        payload = self.service.app_funnel({"period": "24h"})
        self.assertEqual(payload["sessionCount"], 1)
        self.assertEqual(payload["neverConnectedSessionCount"], 1)
        stages = {item["stage"]: {o["outcome"]: o["sessionCount"] for o in item["outcomes"]} for item in payload["stages"]}
        self.assertEqual(set(stages), set(FUNNEL_OUTCOMES))
        self.assertEqual(stages["AUTHORIZATION"]["PENDING"], 1)
        self.assertEqual(stages["CATALOG"]["REMOTE"], 0)
        # The current policy approves fenix 8, so that Pending predates or
        # differs from today's catalog; the status is diagnostic only.
        self.assertEqual(payload["modelsNeedingReview"], [
            {"baseModel": "fenix 8", "outcome": "PENDING", "sessionCount": 1, "catalogStatus": "APPROVED_NOW"},
        ])
        self.assertEqual(payload["journey"], {"sessionCount": 1, "connectedSessionCount": 0, "approvedSessionCount": 0})
        self.assertEqual(payload["neverConnected"], {"sessionCount": 1, "withoutConnectionSignalCount": 1, "outcomes": []})
        self.assertEqual(payload["previous"]["sessionCount"], 0)
        self.assertEqual(payload["bucket"], "hour")
        self.assertEqual(sum(item["sessionCount"] for item in payload["trend"]), 1)
        self.assertGreaterEqual(len(payload["trend"]), 24)
        self.assertIsNone(self.service.app_funnel({"period": "all"})["previous"])
        for bad in ({"period": "1y"}, {"other": "x"}):
            with self.assertRaises(FunnelValidationError):
                self.service.app_funnel(bad)


if __name__ == "__main__":
    unittest.main()

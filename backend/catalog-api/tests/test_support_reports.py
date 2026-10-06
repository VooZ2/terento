"""Support reports without GitHub (S1): validation, idempotency, storage, retention, purge, intake."""
import json
import threading
import unittest
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from jsonschema import Draft202012Validator

from api_test_fixtures import FakeProviderDatabase
from pglite_support import PGliteTestCase
from terento_catalog import http_api
from terento_catalog.support_reports import (
    ALLOWED_REPORT_KEYS,
    ALLOWED_SUPPORT_REPORT_KEYS,
    MAX_SUPPORT_REPORT_BYTES,
    SupportReportValidationError,
    support_reference,
    validate_support_report,
)
from terento_catalog.http_api import CatalogService, make_handler

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "support-report.schema.json").read_text()))
COMPATIBILITY_SCHEMA = json.loads((CONTRACTS / "compatibility-event.schema.json").read_text())


def fixture(name="support-report.valid"):
    return json.loads((CONTRACTS / "fixtures" / f"{name}.json").read_text())


def support(**changes):
    body = fixture()
    body["id"] = str(uuid4())
    for key, value in changes.items():
        if value is ...:
            body.pop(key, None)
        else:
            body[key] = value
    return body


def with_report(**changes):
    body = support()
    for key, value in changes.items():
        if value is ...:
            body["report"].pop(key, None)
        else:
            body["report"][key] = value
    return body


def encode(body):
    return json.dumps(body, ensure_ascii=False).encode()


class ValidationMatrixTests(unittest.TestCase):
    def assert_valid(self, body):
        SCHEMA.validate(body)
        return validate_support_report(encode(body))

    def assert_invalid(self, body, code, *, schema=True):
        if schema:
            self.assertFalse(SCHEMA.is_valid(body), body)
        with self.assertRaises(SupportReportValidationError) as raised:
            validate_support_report(encode(body))
        self.assertEqual(str(raised.exception), code)

    def test_schema_allowlists_match_the_server(self):
        self.assertEqual(set(SCHEMA.schema["properties"]), ALLOWED_SUPPORT_REPORT_KEYS)
        self.assertEqual(set(SCHEMA.schema["properties"]["report"]["properties"]), ALLOWED_REPORT_KEYS)
        # The failure context is the same closed shape the installation diagnostics accept.
        self.assertEqual(SCHEMA.schema["$defs"]["failureContext"], COMPATIBILITY_SCHEMA["$defs"]["failureContext"])
        for name in ("support-report.valid", "support-report.valid-minimal", "support-report.valid-local-update"):
            with self.subTest(fixture=name):
                self.assert_valid(fixture(name))
        for name, code in (
            ("support-report.invalid-disallowed-field", "unknown_report_fields"),
            ("support-report.invalid-local-path", "invalid_report_message"),
        ):
            with self.subTest(fixture=name):
                self.assert_invalid(fixture(name), code)

    def test_privacy_fields_are_rejected_at_every_level(self):
        for key in ("serialNumber", "unitId", "account", "ip", "log", "path"):
            with self.subTest(key=key):
                self.assert_invalid(support(**{key: "x"}), "unknown_fields")
                self.assert_invalid(with_report(**{key: "x"}), "unknown_report_fields")
        body = with_report(device={"model": "fēnix 8", "serial": "3999999999"})
        self.assert_invalid(body, "invalid_report_device")
        body = with_report(maps=[{"provider": "maprando", "path": "/GARMIN/x.img"}])
        self.assert_invalid(body, "invalid_report_maps")
        for message in ("see file:///tmp/a", "/private/var/folders/x", "C:\\Users\\me", "/Volumes/Garmin/x"):
            with self.subTest(message=message):
                self.assert_invalid(with_report(message=message), "invalid_report_message")

    def test_validation_matrix(self):
        for body, code in (
            (support(id=...), "missing_fields"),
            (support(report=...), "missing_fields"),
            (support(schemaVersion=2), "unsupported_schema"),
            (support(schemaVersion=True), "unsupported_schema"),
            (support(id="not-a-uuid"), "invalid_id"),
            (support(createdAt="2026-10-06T12:00:00+02:00"), "invalid_createdAt"),
            (support(createdAt="2026-10-06T12:00:00"), "invalid_createdAt"),
            (support(appBuild=""), "invalid_appBuild"),
            (support(appBuild="x" * 81), "invalid_appBuild"),
            (support(releaseLabel="development"), "invalid_releaseLabel"),
            (support(category="CRASH"), "invalid_category"),
            (support(operationId="123"), "invalid_operationId"),
            (support(userMessage="x" * 2001), "invalid_userMessage"),
            (support(userMessage="   "), "invalid_userMessage"),
            (support(userMessage="bad\rline"), "invalid_userMessage"),
            (support(userMessage="my log is in /Users/someone/Library"), "invalid_userMessage"),
            (support(report=[]), "invalid_report"),
            (with_report(macOSVersion=...), "missing_report_fields"),
            (with_report(title="x" * 181), "invalid_report_title"),
            (with_report(stage=" Finishing"), "invalid_report_stage"),
            (with_report(message="two\nlines"), "invalid_report_message"),
            (with_report(operation="DOWNLOAD"), "invalid_report_operation"),
            (with_report(failureStages=[]), "invalid_report_failureStages"),
            (with_report(failureStages=["x"] * 9), "invalid_report_failureStages"),
            (with_report(errorCodes=["has space"]), "invalid_report_errorCodes"),
            (with_report(errorCodes=[1]), "invalid_report_errorCodes"),
            (with_report(writeStarted="yes"), "invalid_report_writeStarted"),
            (with_report(transferProgressPercent=101), "invalid_report_transferProgressPercent"),
            (with_report(transferProgressPercent=True), "invalid_report_transferProgressPercent"),
            (with_report(device={}), "invalid_report_device"),
            (with_report(device={"firmware": "x" * 41}), "invalid_report_device"),
            (with_report(maps=[{"region": "Lithuania"}]), "invalid_report_maps"),
            (with_report(maps=[{"provider": "maprando", "plannedBytes": -1}]), "invalid_report_maps"),
            (with_report(maps=[{"provider": "maprando"}] * 9), "invalid_report_maps"),
            (with_report(verification={"sourceBytes": 1.5}), "invalid_report_verification"),
            (with_report(verification={"originalFailure": "free text error"}), "invalid_report_verification"),
            (with_report(verification={"rawError": "x"}), "invalid_report_verification"),
            (with_report(lifecycleFacts=["x" * 501]), "invalid_report_lifecycleFacts"),
            (with_report(failureContext={"boundary": "write"}), "invalid_report_failureContext"),
            (with_report(failureContext={"boundary": "write", "classificationSource": "native",
                                         "devicePresence": "present", "rawError": "x"}), "invalid_report_failureContext"),
            (with_report(finishingTrace=["FINISH_TRACE swift attempt=1"]), "invalid_report_finishingTrace"),
            (with_report(finishingTrace=["FINISH_TRACE native event=target_size path=/GARMIN/x.img"]),
             "invalid_report_finishingTrace"),
            (with_report(finishingTrace=["kernel: usb error"]), "invalid_report_finishingTrace"),
            (with_report(finishingTrace=["FINISH_TRACE swift event=x"] * 65), "invalid_report_finishingTrace"),
        ):
            with self.subTest(code=code, body=json.dumps(body)[:160]):
                self.assert_invalid(body, code)
        with self.assertRaises(SupportReportValidationError) as raised:
            validate_support_report(b"[")
        self.assertEqual(str(raised.exception), "invalid_json")
        with self.assertRaises(SupportReportValidationError) as raised:
            validate_support_report(encode(with_report(lifecycleFacts=["x" * 400] * 16)) + b" " * MAX_SUPPORT_REPORT_BYTES)
        self.assertEqual(str(raised.exception), "payload_size")

    def test_accepted_values_and_normalization(self):
        message = "Line one\nLine two\twith a tab " + "x" * 1960
        self.assertEqual(len(message), len(message[:2000]))
        report = self.assert_valid(support(userMessage=message[:2000]))
        self.assertEqual(report["userMessage"], message[:2000])
        # Optional values sent as null are omitted, at both levels.
        report = validate_support_report(encode(with_report(device=None, maps=None) | {"operationId": None, "userMessage": None}))
        self.assertIsNone(report["operationId"])
        self.assertIsNone(report["userMessage"])
        self.assertNotIn("device", report["report"])
        self.assertEqual(self.assert_valid(fixture("support-report.valid-minimal"))["report"],
                         {"macOSVersion": "Version 26.0 (Build 25A354)"})
        self.assertEqual(self.assert_valid(with_report(message="Watch [REDACTED] path [LOCAL PATH REDACTED]"))["report"]["message"],
                         "Watch [REDACTED] path [LOCAL PATH REDACTED]")
        for category in ("INSTALL_FAILED", "UPDATE_FAILED", "REMOVE_FAILED", "CONNECTION", "OTHER"):
            self.assertEqual(self.assert_valid(support(category=category))["category"], category)

    def test_local_label_is_classified(self):
        self.assertTrue(self.assert_valid(fixture("support-report.valid-local-update"))["isLocalTest"])
        self.assertFalse(self.assert_valid(support())["isLocalTest"])

    def test_reference_is_deterministic_from_the_id(self):
        report_id = "6f1d2c3b-8a4e-4f60-9b7a-2c1d0e9f8a71"
        self.assertEqual(support_reference(report_id), "TR-FYMEFT")
        self.assertEqual(support_reference(report_id.upper()), "TR-FYMEFT")
        self.assertEqual(validate_support_report(encode(fixture()))["reference"], "TR-FYMEFT")
        references = {support_reference(str(uuid4())) for _ in range(200)}
        self.assertTrue(all(len(ref) == 9 and ref.startswith("TR-") and set(ref[3:]) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
                            for ref in references))
        self.assertGreater(len(references), 195)


class SupportReportStorageTests(PGliteTestCase):
    def store(self, body):
        return self.db.insert_support_report(validate_support_report(encode(body)))

    def count(self, where="TRUE"):
        return self.sql(f"SELECT count(*) AS n FROM support_report WHERE {where}")[0]["n"]

    def admin(self):
        return self.db.create_admin_user("operator", "x")["id"]

    def test_idempotent_insert_and_reference_conflict(self):
        body = support()
        self.assertEqual(self.store(body), "stored")
        changed = deepcopy(body)
        changed["userMessage"] = "A different description"
        self.assertEqual(self.store(changed), "duplicate")
        self.assertEqual(self.count(), 1)
        stored = self.sql("SELECT * FROM support_report")[0]
        self.assertEqual(stored["reference"], support_reference(body["id"]))
        self.assertEqual(stored["user_message"], body["userMessage"])
        self.assertEqual(stored["status"], "OPEN")
        self.assertEqual(stored["report"]["device"]["model"], "fēnix 8")
        # Another id that happens to own the same reference is a conflict, not an overwrite.
        other = validate_support_report(encode(support()))
        other["reference"] = stored["reference"]
        self.assertEqual(self.db.insert_support_report(other), "conflict")
        self.assertEqual(self.count(), 1)

    def test_list_counts_open_count_and_local_separation(self):
        for _ in range(3):
            self.store(support())
        self.store(support(releaseLabel="1.0.0-beta.19-local"))
        self.assertEqual(self.db.support_report_open_count(), 3)
        page = self.db.support_reports(status="OPEN", limit=2)
        self.assertEqual((len(page["rows"]), page["openCount"], page["handledCount"], page["filteredTotal"]), (2, 3, 0, 3))
        self.assertEqual(len(self.db.support_reports(status="OPEN", limit=2, offset=2)["rows"]), 1)
        local = self.db.support_reports(status="ALL", local=True)
        self.assertEqual((local["totalCount"], local["rows"][0]["is_local_test"]), (1, True))
        with self.assertRaises(ValueError):
            self.db.support_reports(status="DONE")

    def test_review_actions_are_audited_and_do_not_change_content(self):
        admin_id = self.admin()
        body = support()
        self.store(body)
        reference = support_reference(body["id"])
        before = self.sql("SELECT report, user_message FROM support_report")[0]
        self.assertTrue(self.db.review_support_report(reference, action="handle", admin_user_id=admin_id, note="Replied by email"))
        self.assertEqual(self.db.support_report_open_count(), 0)
        self.assertTrue(self.db.review_support_report(reference, action="handle", admin_user_id=admin_id))
        self.assertTrue(self.db.review_support_report(reference, action="issue", admin_user_id=admin_id, linked_github_issue="#41"))
        self.assertTrue(self.db.review_support_report(reference, action="reopen", admin_user_id=admin_id))
        self.assertFalse(self.db.review_support_report("TR-AAAAAA", action="handle", admin_user_id=admin_id))
        detail = self.db.support_report_detail(reference)
        self.assertEqual((detail["status"], detail["linked_github_issue"], detail["note"]), ("OPEN", "#41", "Replied by email"))
        self.assertIsNone(detail["handled_at"])
        self.assertEqual([item["action"] for item in detail["audit"]], ["REOPENED", "ISSUE_LINKED", "HANDLED"])
        self.assertEqual(detail["audit"][-1]["changed_by_username"], "operator")
        after = self.sql("SELECT report, user_message FROM support_report")[0]
        self.assertEqual(before, after)
        actions = [row["action"] for row in self.sql("SELECT action FROM admin_audit_log WHERE action LIKE 'support_report.%%' ORDER BY id")]
        self.assertEqual(actions, ["support_report.handled", "support_report.issue_linked", "support_report.reopened"])

    def test_detail_links_public_update_diagnostics_by_operation(self):
        body = support(category="UPDATE_FAILED")
        self.store(body)
        diagnostic_id = str(uuid4())
        self.sql(
            "INSERT INTO map_update_diagnostic (event_id, operation_id, occurred_at, provider, region, outcome, payload)"
            " VALUES (%s, %s, now(), 'maprando', 'lituanie', 'FAILED', '{}'::jsonb)",
            (diagnostic_id, body["operationId"]),
        )
        detail = self.db.support_report_detail(support_reference(body["id"]))
        self.assertEqual([str(item["event_id"]) for item in detail["updateDiagnostics"]], [diagnostic_id])
        self.assertEqual(detail["installationDiagnostics"], [])
        self.assertIsNone(self.db.support_report_detail("TR-AAAAAA"))

    def test_retention_is_twelve_months_after_receipt(self):
        old, recent = support(), support()
        self.store(old)
        self.store(recent)
        self.sql("UPDATE support_report SET received_at = now() - interval '13 months' WHERE id = %s", (old["id"],))
        self.sql("UPDATE support_report SET received_at = now() - interval '11 months' WHERE id = %s", (recent["id"],))
        self.db.prune_compatibility_events()
        self.assertEqual([str(row["id"]) for row in self.sql("SELECT id FROM support_report")], [recent["id"]])

    def test_local_purge_removes_only_local_reports_and_is_audited(self):
        self.store(support())
        self.store(support(releaseLabel="1.0.0-beta.19-local"))
        service = CatalogService(self.db)
        summary = service.local_test_data()
        self.assertEqual(summary["supportReports"]["totalCount"], 1)
        counts = service.purge_local_test_data(admin_user_id=None, request_id="purge-1")
        self.assertEqual(counts["supportReportCount"], 1)
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.count("is_local_test IS TRUE"), 0)
        self.assertIn("support_report.local_test_purged", [row["action"] for row in self.sql("SELECT action FROM admin_audit_log")])

    def test_reports_never_enter_statistics(self):
        self.store(support())
        self.assertEqual(self.db.map_statistics({}), [])
        self.assertEqual(self.db.admin_review_summary()["installationIssues"], 0)


class SupportReportHTTPTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.service = CatalogService(self.db)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)

    def post(self, body, content_type="application/json", forwarded=None):
        connection = HTTPConnection(*self.http.server_address)
        headers = {"Content-Type": content_type}
        if forwarded:
            headers["X-Forwarded-For"] = forwarded
        connection.request("POST", "/support/reports", body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, json.loads(payload or b"{}")

    def test_intake_statuses_and_replay(self):
        body = encode(fixture())
        self.assertEqual(self.post(body), (201, {"reference": "TR-FYMEFT", "status": "stored"}))
        self.assertEqual(self.post(body), (200, {"reference": "TR-FYMEFT", "status": "duplicate"}))
        self.assertEqual(self.post(encode(support(extra=1))), (400, {"error": "unknown_fields"}))
        self.assertEqual(self.post(body, content_type="text/plain")[0], 415)
        self.assertEqual(self.post(b"x" * (MAX_SUPPORT_REPORT_BYTES + 1))[0], 413)
        stored = self.sql("SELECT * FROM support_report")
        self.assertEqual(len(stored), 1)
        self.assertNotIn("127.0.0.1", json.dumps(stored, default=str))

    def test_rate_limit_uses_the_trusted_proxy_client(self):
        with patch.object(http_api, "SUPPORT_REPORT_RATE_LIMIT", 2):
            first = [self.post(encode(support()), forwarded="198.51.100.7")[0] for _ in range(3)]
            second = self.post(encode(support()), forwarded="198.51.100.8")[0]
        self.assertEqual(first, [201, 201, 429])
        self.assertEqual(second, 201)

    def test_storage_failure_is_503(self):
        with patch.object(self.db, "insert_support_report", side_effect=RuntimeError("down")):
            with self.assertLogs("terento_catalog.http_api", level="ERROR"):
                self.assertEqual(self.post(encode(support())), (503, {"error": "support_reports_unavailable"}))


class FakeDatabaseCompatibilityTests(unittest.TestCase):
    def test_local_test_data_without_support_reports_keeps_working(self):
        service = CatalogService(FakeProviderDatabase())
        self.assertNotIn("supportReports", service.local_test_data())
        self.assertNotIn("supportReportCount", service.purge_local_test_data(admin_user_id=1))


if __name__ == "__main__":
    unittest.main()

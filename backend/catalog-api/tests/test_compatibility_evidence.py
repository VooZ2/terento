from __future__ import annotations

import json
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from terento_catalog.admin import dashboard_page, format_timestamp, hash_password, login_page, setup_page, verify_password
from terento_catalog.compatibility_evidence import EvidenceValidationError, validate_event
from terento_catalog.db import Database
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
        "region": "DEU",
        "mapRelease": "2026-08",
        "terentoVersion": "1.0.0",
        "macOSVersion": "macOS 15.6",
        "phaseOutcome": "SUCCEEDED",
        "automaticFinishingResult": "VERIFIED",
        "errorCategory": None,
        "deletionToken": "a" * 64,
    }
    value.update(changes)
    return value


class FakeEvidenceDatabase:
    def __init__(self):
        self.events = {}
        self.users = []
        self.sessions = {}
        self.device_support_status = "SUPPORTED"
        self.authorization_audit = []

    def insert_compatibility_event(self, value):
        if value["id"] in self.events:
            return False
        self.events[value["id"]] = value
        return True

    def delete_compatibility_event(self, event_id, deletion_token):
        value = self.events.get(event_id)
        if not value or value.get("deletionToken") != deletion_token:
            return False
        del self.events[event_id]
        return True

    def prune_compatibility_events(self):
        return 0

    def compatibility_statistics(self):
        return [{
            "model": "fēnix 8", "firmware_versions": "20.19", "attempted_install_count": 1,
            "successful_install_count": 1, "failed_install_count": 0, "success_rate": 100,
            "last_success": "2026-08-24", "last_failure": None, "error_categories": {},
            "calculated_status": "TESTED", "physical_device_evidence_count": 1,
            "review_notes": "Owner evidence",
        }]

    def compatibility_operation_details(self):
        return []

    def public_compatibility_statistics(self, limit):
        return [{
            "model": "fēnix 8 · 47 mm AMOLED", "canonical_model": "fēnix 8",
            "compatibility_identity": "fēnix 8 · 47 mm AMOLED", "variant": "AMOLED", "case_size_mm": 47,
            "display_type": "AMOLED", "canonical_device_model_id": "garmin-fenix-8-47-amoled",
            "attempted_install_count": 4, "reconnect_verified_install_count": 0,
            "successful_install_count": 3, "failed_install_count": 1,
            "success_rate": 75.0, "calculated_status": "SUPPORTED",
            "recognized_map_capable_evidence": True,
            "last_success": datetime(2026, 8, 24, tzinfo=timezone.utc),
            "last_evidence": datetime(2026, 8, 24, tzinfo=timezone.utc),
        }, {
            "model": "fēnix 8 · 51 mm AMOLED", "canonical_model": "fēnix 8",
            "compatibility_identity": "fēnix 8 · 51 mm AMOLED", "variant": "AMOLED", "case_size_mm": 51,
            "display_type": "AMOLED", "canonical_device_model_id": "garmin-fenix-8-51-amoled",
            "attempted_install_count": 1, "reconnect_verified_install_count": 0,
            "successful_install_count": 1, "failed_install_count": 0,
            "success_rate": 100.0, "calculated_status": "SUPPORTED",
            "recognized_map_capable_evidence": True,
            "last_success": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "last_evidence": datetime(2026, 8, 25, tzinfo=timezone.utc),
        }][:limit]

    def public_compatibility_models(self, limit):
        rows = self.public_compatibility_statistics(limit)
        for row in rows:
            row.update({
                "evidence_model": row["canonical_model"],
                "family": "fenix",
                "family_name": "fēnix",
                "canonical_model": "fenix 8",
                "asset_status": "MISSING",
                "asset_url": None,
                "source_image_url": None,
            })
        return rows

    def admin_device_snapshot(self):
        return [{
            "device_id": "garmin-fenix-8-47-amoled",
            "manufacturer": "Garmin",
            "family_canonical_name": "fenix",
            "family_name": "fēnix",
            "model": "fēnix 8",
            "canonical_model": "fenix 8",
            "variant": "47 mm, AMOLED",
            "case_size_mm": 47,
            "display_type": "AMOLED",
            "part_number": "010-02904-10",
            "product_url": "https://www.garmin.com/en-US/p/1228429/",
            "active": True,
            "map_capable": True,
            "support_status": self.device_support_status,
            "asset_status": "MISSING",
            "asset_url": None,
            "attempted_install_count": 1,
            "successful_install_count": 1,
            "failed_install_count": 0,
            "first_success": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "last_success": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "last_evidence": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "first_seen_at": datetime(2026, 8, 20, tzinfo=timezone.utc),
            "created_at": datetime(2026, 8, 20, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "last_seen_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "first_seen_collection_run_id": 1,
            "last_seen_collection_run_id": 1,
            "usb_identities": [],
        }], {
            "id": 1,
            "status": "SUCCEEDED",
            "started_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 8, 25, 1, tzinfo=timezone.utc),
            "records_total_before": 0,
            "records_total_after": 1,
            "records_added": 1,
            "records_updated": 0,
        }

    def admin_user_count(self):
        return len(self.users)

    def create_admin_user(self, username, password_hash):
        user = {"id": len(self.users) + 1, "username": username, "password_hash": password_hash,
                "created_at": datetime.now(timezone.utc), "last_login_at": None}
        self.users.append(user)
        return user

    def admin_user_by_username(self, username):
        return next((user for user in self.users if user["username"] == username), None)

    def create_admin_session(self, user_id, session_hash, csrf_hash, expires_at):
        user = next(user for user in self.users if user["id"] == user_id)
        self.sessions[session_hash] = {**user, "csrf_token_hash": csrf_hash, "expires_at": expires_at}

    def admin_session(self, session_hash):
        return self.sessions.get(session_hash)

    def delete_admin_session(self, session_hash):
        self.sessions.pop(session_hash, None)

    def update_admin_user(self, user_id, username, password_hash):
        user = next(user for user in self.users if user["id"] == user_id)
        user.update(username=username, password_hash=password_hash)
        return user

    def update_device_support_status(self, device_id, support_status, admin_user_id=None, reason=None, note=None):
        if device_id != "garmin-fenix-8-47-amoled":
            return False
        self.device_support_status = support_status
        self.authorization_audit.append({
            "device_id": device_id,
            "admin_user_id": admin_user_id,
            "reason": reason,
            "note": note,
        })
        return True


class CaptureDatabase(Database):
    def __init__(self):
        super().__init__("unused")
        self.parameters = None

    @contextmanager
    def connection(self):
        database = self

        class Result:
            def fetchone(self):
                return {"event_id": "stored"}

        class Connection:
            def execute(self, query, parameters=None):
                database.parameters = parameters
                return Result()

        yield Connection()


class CompatibilityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeEvidenceDatabase()
        service = CatalogService(
            self.database,
            admin_bootstrap_secret="one-time-bootstrap-secret",
            public_compatibility_stats_enabled=True,
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

    def test_event_deletion_requires_matching_token(self):
        body = json.dumps(event()).encode()
        created, _ = self.request("POST", "/compatibility/events", body, {"Content-Type": "application/json"})
        self.assertEqual(created.status, 201)

        wrong = json.dumps({"id": event()["id"], "deletionToken": "b" * 64}).encode()
        denied, _ = self.request("DELETE", "/compatibility/events", wrong, {"Content-Type": "application/json"})
        self.assertEqual(denied.status, 404)

        correct = json.dumps({"id": event()["id"], "deletionToken": "a" * 64}).encode()
        deleted, response_body = self.request("DELETE", "/compatibility/events", correct, {"Content-Type": "application/json"})
        self.assertEqual(deleted.status, 200)
        self.assertEqual(json.loads(response_body)["status"], "deleted")
        self.assertFalse(self.database.events)

    def test_database_binds_omitted_optional_fields_as_null(self):
        database = CaptureDatabase()
        payload = event()
        payload.pop("family")
        payload.pop("firmwareVersion")
        payload.pop("errorCategory")

        self.assertTrue(database.insert_compatibility_event(payload))
        self.assertIsNone(database.parameters["family"])
        self.assertIsNone(database.parameters["firmwareVersion"])
        self.assertIsNone(database.parameters["errorCategory"])
        self.assertIsNone(database.parameters["displayType"])
        self.assertIsNone(database.parameters["canonicalDeviceId"])
        self.assertEqual(len(database.parameters["deletionTokenHash"]), 64)

    def test_historical_fenix_7_evidence_is_canonicalized_without_retail_row(self):
        database = CaptureDatabase()
        payload = event(
            model="fēnix 7",
            compatibilityIdentity="fēnix 7 · 47 mm",
            variant="47 mm",
            caseSizeMm=47,
        )
        self.assertTrue(database.insert_compatibility_event(payload))
        self.assertEqual(
            database.parameters["canonicalDeviceId"],
            "garmin-fenix-7-47",
        )

    def test_admin_dashboard_uses_compact_english_evidence_layout(self):
        row = {
            "model": "fēnix 8",
            "compatibility_identity": "fēnix 8 · 51 mm",
            "variant": "51mm",
            "family": "fēnix",
            "firmware_versions": "2244",
            "attempted_install_count": 1,
            "successful_install_count": 1,
            "failed_install_count": 0,
            "success_rate": 100.0,
            "calculated_status": "TESTED",
            "recognized_map_capable_evidence": True,
            "last_success": datetime(2026, 8, 25, 16, 4, tzinfo=timezone.utc),
            "last_failure": None,
            "error_categories": {},
            "review_status": "APPROVED",
            "public_statistics_enabled": True,
        }
        body = dashboard_page([row], {"username": "gediminas"}, "csrf", public_stats_enabled=True).decode()
        self.assertIn("Installations", body)
        self.assertIn("Installation activity and compatibility evidence from Terento users.", body)
        self.assertIn(">Install attempts<", body)
        self.assertIn(">51 mm<", body)
        self.assertIn("Latest activity", body)
        self.assertNotIn("Public compatibility", body)
        self.assertNotIn("1 model published", body)
        self.assertNotIn("Diegimų", body)
        self.assertNotIn("ADMINISTRAVIMAS", body)
        self.assertNotIn("Georgia", body)
        self.assertNotIn("Logged in as", body)
        self.assertIn(">Attempts<", body)
        self.assertIn("logo-sky.svg", body)
        self.assertIn("Times follow the selected time zone", body)
        self.assertIn("data-admin-timestamp", body)
        self.assertIn("admin-timezone", body)
        self.assertEqual(format_timestamp(row["last_success"]), "25 Aug 2026, 16:04 UTC")

        unknown_variant = dict(row)
        unknown_variant.pop("compatibility_identity")
        unknown_variant.pop("variant")
        unknown_variant.pop("case_size_mm", None)
        unknown_body = dashboard_page([unknown_variant], {"username": "gediminas"}, "csrf").decode()
        self.assertIn(">—<", unknown_body)

        self.assertIn("Sign in", login_page().decode())
        self.assertIn("Create the first admin account", setup_page().decode())

    def test_admin_dashboard_links_errors_to_structured_operation_details(self):
        row = {
            "model": "fēnix 8", "compatibility_identity": "fēnix 8 · 51 mm AMOLED",
            "variant": "51 mm, AMOLED", "firmware_versions": "2326",
            "attempted_install_count": 1, "successful_install_count": 0,
            "failed_install_count": 1, "success_rate": 0,
            "calculated_status": "TESTING", "last_success": None,
            "last_failure": datetime(2026, 8, 26, 8, 30, tzinfo=timezone.utc),
            "error_categories": {"write:INSTALL_FAILED_WRITE": 1},
        }
        operation = {
            "operation_key": "223e4567-e89b-12d3-a456-426614174000",
            "occurred_at": row["last_failure"], "compatibility_identity": row["compatibility_identity"],
            "firmware_version": "2326", "region": "DEU", "phase_outcome": "FAILED",
            "release_label": "1.0.0-beta.6", "app_build": "5", "write_started": True,
            "failure_stage": "write", "failure_code": "INSTALL_FAILED_WRITE",
            "native_failure_code": "SEND_OBJECT_FAILED", "transfer_progress_bucket": "25-99",
            "raw_mtp_model": "fenix 8 pro - 51mm", "identity_resolution_code": "GARMIN_UNIT_ID",
            "map_result_index": 0,
        }
        body = dashboard_page(
            [row], {"username": "operator"}, "csrf", operations=[operation]
        ).decode()
        self.assertIn("aria-label='View 1 unresolved errors", body)
        self.assertIn("/admin/diagnostics?identity=", body)
        self.assertNotIn("Diagnostic record", body)
        self.assertNotIn("1.0.0-beta.6 (build 5)", body)
        self.assertNotIn("fenix 8 pro - 51mm", body)
        self.assertNotIn("GARMIN_UNIT_ID", body)

    def test_admin_dashboard_separates_resolved_legacy_failures_from_active_data(self):
        active_row = {
            "model": "fēnix 8", "compatibility_identity": "fēnix 8 · 47 mm AMOLED",
            "variant": "47 mm, AMOLED", "firmware_versions": "2244",
            "attempted_install_count": 1, "successful_install_count": 1,
            "failed_install_count": 0, "success_rate": 100,
            "calculated_status": "TESTED", "last_success": datetime(2026, 8, 26, tzinfo=timezone.utc),
            "last_failure": None, "error_categories": {},
        }
        resolved = {
            "operation_key": "legacy:issue-32",
            "occurred_at": datetime(2026, 8, 26, 8, 30, tzinfo=timezone.utc),
            "compatibility_identity": "Identity pending · issue #32 · fēnix 8 Pro 51 mm",
            "region": "CHE+", "phase_outcome": "FAILED", "failure_stage": "preflight",
            "failure_code": "INSTALL_BLOCKED_UNKNOWN_TARGET",
            "native_failure_code": "UNSUPPORTED_DEVICE", "write_started": False,
            "remote_object_created": False, "cleanup_attempted": False,
            "cleanup_succeeded": False, "transfer_progress_bucket": "0",
            "release_label": "1.0.0", "app_build": None,
            "raw_mtp_model": None, "identity_resolution_code": "UNAVAILABLE",
            "diagnostic_status": "RESOLVED",
            "resolution_note": "Historical pre-beta.6 failure; excluded from current compatibility statistics.",
            "map_result_index": 0,
        }
        body = dashboard_page(
            [active_row], {"username": "operator"}, "csrf",
            operations=[], resolved_operations=[resolved],
        ).decode()
        self.assertNotIn("Resolved / historical diagnostics", body)
        self.assertNotIn("fēnix 8 Pro · 51 mm", body)
        self.assertNotIn("Historical pre-beta.6 failure", body)
        self.assertNotIn("INSTALL_BLOCKED_UNKNOWN_TARGET", body)
        self.assertIn("Resolved historical diagnostics", body)

    def test_issue_32_quarantine_is_narrow_and_non_destructive(self):
        from pathlib import Path

        migration = (
            Path(__file__).parents[1]
            / "src/terento_catalog/migrations/018_device_identity_diagnostics.sql"
        ).read_text()
        self.assertIn("region = 'CHE+'", migration)
        self.assertIn("firmware_version = '2326'", migration)
        self.assertIn("case_size_mm = 51", migration)
        self.assertIn("phase_outcome = 'FAILED'", migration)
        self.assertIn("Identity pending · issue #32 · fēnix 8 Pro 51 mm", migration)
        self.assertNotIn("DELETE FROM compatibility_evidence_event", migration)

    def test_schema_v2_keeps_exact_variant_and_treats_reconnect_as_optional(self):
        payload = event(
            schemaVersion=2,
            compatibilityIdentity="fēnix 8 · 51 mm",
            variant="51 mm",
            caseSizeMm=51,
            displayType="AMOLED",
            canonicalDeviceId="garmin-fenix-8-51-amoled",
            reconnectVerified=False,
            mapVisibleAfterReconnect=False,
        )
        validated = validate_event(json.dumps(payload).encode())
        self.assertEqual(validated["compatibilityIdentity"], "fēnix 8 · 51 mm")
        self.assertEqual(validated["caseSizeMm"], 51)
        self.assertEqual(validated["displayType"], "AMOLED")
        self.assertEqual(validated["canonicalDeviceId"], "garmin-fenix-8-51-amoled")

        database = CaptureDatabase()
        self.assertTrue(database.insert_compatibility_event(validated))
        self.assertFalse(database.parameters["reconnectVerified"])
        self.assertFalse(database.parameters["mapVisibleAfterReconnect"])
        self.assertEqual(database.parameters["displayType"], "AMOLED")
        self.assertEqual(database.parameters["canonicalDeviceId"], "garmin-fenix-8-51-amoled")

    def test_schema_v3_accepts_structured_diagnostics_and_rejects_raw_or_inconsistent_data(self):
        payload = event(
            schemaVersion=3,
            phaseOutcome="FAILED",
            automaticFinishingResult="FAILED",
            operationId="223e4567-e89b-12d3-a456-426614174000",
            mapResultIndex=0,
            selectedMapCount=3,
            appBuild="5",
            releaseLabel="1.0.0-beta.6",
            failureStage="write",
            failureCode="INSTALL_FAILED_WRITE",
            nativeFailureCode="SEND_OBJECT_FAILED",
            writeStarted=True,
            remoteObjectCreated=False,
            cleanupAttempted=False,
            cleanupSucceeded=False,
            transferProgressBucket="25-99",
            rawMTPModel="fenix 8 pro - 51mm",
            identityResolutionCode="GARMIN_UNIT_ID",
        )
        validated = validate_event(json.dumps(payload).encode())
        self.assertEqual(validated["operationId"], payload["operationId"])
        database = CaptureDatabase()
        self.assertTrue(database.insert_compatibility_event(validated))
        self.assertEqual(database.parameters["appBuild"], "5")
        self.assertEqual(database.parameters["failureStage"], "write")
        self.assertEqual(database.parameters["rawMTPModel"], "fenix 8 pro - 51mm")
        self.assertEqual(database.parameters["identityResolutionCode"], "GARMIN_UNIT_ID")

        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "nativeFailureCode": "RAW: libmtp failed /Users/me"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "releaseLabel": "file:///Users/me/build"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "rawMTPModel": "/Users/me/watch"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "rawMTPModel": "fenix 8\nserial"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "identityResolutionCode": "UNIT_ID:123"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "writeStarted": False, "remoteObjectCreated": True}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**payload, "phaseOutcome": "NOT_STARTED", "writeStarted": True}).encode())

    def test_privacy_fields_and_local_paths_are_rejected(self):
        without_deletion_token = event()
        without_deletion_token.pop("deletionToken")
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(without_deletion_token).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps({**event(), "serialNumber": "secret"}).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(event(model="/Users/alice/watch")).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(event(phaseOutcome="SUCCEEDED", automaticFinishingResult="FAILED")).encode())
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(event(usbVendorID=70000)).encode())

    def test_admin_setup_login_dashboard_and_account_update(self):
        initial, _ = self.request("GET", "/admin")
        self.assertEqual(initial.status, 303)
        self.assertEqual(initial.headers["Location"], "/admin/setup")
        initial_campaign, _ = self.request("GET", "/admin/campaign-links")
        self.assertEqual(initial_campaign.status, 303)
        self.assertEqual(initial_campaign.headers["Location"], "/admin/setup")

        setup_body = urlencode({
            "username": "operator", "password": "long-test-password",
            "password_confirmation": "long-test-password",
            "bootstrap_secret": "one-time-bootstrap-secret",
        })
        setup, _ = self.request("POST", "/admin/setup", setup_body, {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(setup.status, 303)
        self.assertTrue(verify_password("long-test-password", self.database.users[0]["password_hash"]))

        login_body = urlencode({"username": "operator", "password": "long-test-password"})
        login, _ = self.request("POST", "/admin/login", login_body, {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(login.status, 303)
        cookies = login.headers.get_all("Set-Cookie")
        session_cookie = next(value.split(";", 1)[0] for value in cookies if value.startswith("terento_admin_session="))
        csrf_cookie = next(value.split(";", 1)[0] for value in cookies if value.startswith("terento_admin_csrf="))
        csrf_token = csrf_cookie.split("=", 1)[1]
        cookie_header = f"{session_cookie}; {csrf_cookie}"

        allowed, body = self.request("GET", "/admin", headers={"Cookie": cookie_header})
        self.assertEqual(allowed.status, 200)
        self.assertEqual(allowed.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn(b"f\xc4\x93nix 8", body)

        devices, devices_body = self.request("GET", "/admin/devices", headers={"Cookie": cookie_header})
        self.assertEqual(devices.status, 200)
        self.assertIn(b">Devices<", devices_body)
        self.assertIn(b'data-device-sort="maps"', devices_body)
        self.assertIn(
            "img-src https://terento.app https://api.terento.app https://res.garmin.com data:",
            devices.headers["Content-Security-Policy"],
        )

        devices_json, devices_json_body = self.request("GET", "/admin/devices.json", headers={"Cookie": cookie_header})
        self.assertEqual(devices_json.status, 200)
        self.assertEqual(json.loads(devices_json_body)["summary"]["successful"], 1)
        self.assertNotIn("tested", json.loads(devices_json_body)["summary"])

        review_body = urlencode({
            "csrf_token": csrf_token,
            "device_id": "garmin-fenix-8-47-amoled",
            "support_status": "SUPPORTED",
            "reason": "Validated on hardware",
            "note": "Keep this profile enabled",
        })
        reviewed, _ = self.request("POST", "/admin/devices/authorization", review_body, {
            "Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie_header,
        })
        self.assertEqual(reviewed.status, 303)
        self.assertEqual(self.database.device_support_status, "SUPPORTED")
        self.assertEqual(self.database.authorization_audit[-1]["reason"], "Validated on hardware")

        unauthenticated_campaign, _ = self.request("GET", "/admin/campaign-links")
        self.assertEqual(unauthenticated_campaign.status, 303)
        self.assertEqual(unauthenticated_campaign.headers["Location"], "/admin/login")

        campaign_links, campaign_body = self.request("GET", "/admin/campaign-links", headers={"Cookie": cookie_header})
        self.assertEqual(campaign_links.status, 200)
        self.assertIn("script-src 'nonce-", campaign_links.headers["Content-Security-Policy"])
        self.assertRegex(campaign_body, rb'<script nonce="[A-Za-z0-9_-]+">')
        self.assertIn(b"Campaign link builder", campaign_body)
        self.assertIn(b"Reddit community post", campaign_body)

        update_body = urlencode({
            "csrf_token": csrf_token, "username": "owner",
            "current_password": "long-test-password", "new_password": "another-long-password",
            "new_password_confirmation": "another-long-password",
        })
        updated, _ = self.request("POST", "/admin/account", update_body, {
            "Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie_header,
        })
        self.assertEqual(updated.status, 200)
        self.assertEqual(self.database.users[0]["username"], "owner")

    def test_admin_rejects_wrong_bootstrap_secret_and_csrf(self):
        setup_body = urlencode({
            "username": "operator", "password": "long-test-password",
            "password_confirmation": "long-test-password", "bootstrap_secret": "wrong",
        })
        denied, _ = self.request("POST", "/admin/setup", setup_body, {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(denied.status, 400)
        self.assertFalse(self.database.users)

        cross_site, _ = self.request("POST", "/admin/setup", setup_body, {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://attacker.example",
        })
        self.assertEqual(cross_site.status, 400)

    def test_public_statistics_are_explicit_aggregates(self):
        response, body = self.request("GET", "/compatibility/public/top-models.json?limit=5")
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertEqual(document["schemaVersion"], 2)
        self.assertEqual(document["models"][0]["model"], "fēnix 8 · 47 mm AMOLED")
        self.assertEqual(document["models"][0]["canonicalModel"], "fēnix 8")
        self.assertEqual(document["models"][0]["compatibilityIdentity"], "fēnix 8 · 47 mm AMOLED")
        self.assertEqual(document["models"][0]["caseSizeMm"], 47)
        self.assertEqual(document["models"][0]["displayType"], "AMOLED")
        self.assertEqual(document["models"][0]["canonicalDeviceId"], "garmin-fenix-8-47-amoled")
        self.assertEqual(document["models"][0]["successfulInstallations"], 3)
        self.assertEqual(document["models"][1]["compatibilityIdentity"], "fēnix 8 · 51 mm AMOLED")
        self.assertEqual(document["models"][1]["caseSizeMm"], 51)
        self.assertEqual(document["models"][1]["evidenceStatus"], "TESTED")
        self.assertEqual(document["models"][0]["evidenceStatus"], "SUPPORTED")
        self.assertEqual(document["models"][0]["successfulInstallations"], 3)
        self.assertEqual(document["models"][0]["mapCapable"], True)
        self.assertNotIn("firmwareVersion", document["models"][0])
        self.assertEqual(
            set(document["models"][0]),
            {
                "model", "canonicalModel", "compatibilityIdentity", "variant",
                "caseSizeMm", "displayType", "canonicalDeviceId",
                "attemptedInstallations", "successfulInstallations",
                "reconnectVerifiedInstallations", "failedInstallations",
                "successRate", "evidenceStatus", "lastSuccessfulInstallation",
                "lastEvidence", "mapCapable",
            },
        )

    def test_public_models_is_additive_and_evidence_only(self):
        response, body = self.request("GET", "/compatibility/public/models.json?limit=5")
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertEqual(document["schemaVersion"], 1)
        self.assertEqual(document["models"][1]["evidenceStatus"], "TESTED")
        self.assertEqual(document["models"][1]["image"]["origin"], "fallback")
        self.assertEqual(document["models"][1]["image"]["status"], "FALLBACK")
        self.assertEqual(document["models"][1]["image"]["source"]["type"], "GENERIC_FALLBACK")
        self.assertNotIn("supportStatus", document["models"][1])
        self.assertNotIn("writeAuthorization", document["models"][1])

    def test_fenix_8_pro_identity_is_preserved_for_admin_and_public_web(self):
        pro_row = {
            "model": "fēnix 8 Pro · 51 mm AMOLED",
            "evidence_model": "fēnix 8 Pro",
            "canonical_model": "fenix 8 pro",
            "compatibility_identity": "fēnix 8 Pro · 51 mm, AMOLED",
            "variant": "51 mm, AMOLED", "case_size_mm": 51,
            "display_type": "AMOLED",
            "canonical_device_model_id": "garmin-fenix-8-pro-51-amoled",
            "attempted_install_count": 1, "successful_install_count": 1,
            "reconnect_verified_install_count": 0, "failed_install_count": 0,
            "success_rate": 100.0, "calculated_status": "TESTED",
            "recognized_map_capable_evidence": True,
            "last_success": datetime(2026, 8, 26, tzinfo=timezone.utc),
            "last_evidence": datetime(2026, 8, 26, tzinfo=timezone.utc),
            "family": "fenix", "family_name": "fēnix",
            "asset_status": "MISSING", "asset_url": None,
            "source_image_url": None,
        }
        self.database.public_compatibility_models = lambda limit: [pro_row][:limit]

        response, body = self.request("GET", "/compatibility/public/models.json?limit=5")
        public_model = json.loads(body)["models"][0]
        self.assertEqual(response.status, 200)
        self.assertEqual(public_model["model"], "fēnix 8 Pro · 51 mm AMOLED")
        self.assertEqual(public_model["canonicalModel"], "fenix 8 pro")
        self.assertEqual(
            public_model["canonicalDeviceId"],
            "garmin-fenix-8-pro-51-amoled",
        )

        admin = dashboard_page([pro_row], {"username": "operator"}, "csrf").decode()
        self.assertIn("fēnix 8 Pro", admin)
        self.assertNotIn(">fēnix 8<", admin)


class PasswordHashTests(unittest.TestCase):
    def test_password_hash_round_trip_and_wrong_password(self):
        encoded = hash_password("a-sufficiently-long-password")
        self.assertTrue(verify_password("a-sufficiently-long-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))
        self.assertNotIn("a-sufficiently-long-password", encoded)


if __name__ == "__main__":
    unittest.main()

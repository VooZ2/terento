"""Web installer statistics: validation, ingest, storage, Admin page (end to end)."""
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from pglite_support import PGliteTestCase
from test_compatibility_evidence import event as compatibility_event
from terento_catalog.admin import _admin_device_payload, device_detail_page, hash_password
from terento_catalog.compatibility_evidence import validate_event as validate_compatibility_event
from terento_catalog.http_api import CatalogService, _public_install_counts, make_handler
from terento_catalog.migrate import _statements
from terento_catalog.web_installer import (
    STAGES,
    WebInstallerValidationError,
    counted_result,
    summarize,
    validate_event,
    validate_relay_job,
)

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
OWNER_CLEANUP_MIGRATION = (Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
                           / "079_remove_owner_web_installer_test_records.sql")
SECRET = "w" * 48
NOW = datetime(2026, 10, 10, 21, tzinfo=timezone.utc)


def session_events():
    return json.loads((FIXTURES / "web-installer-events.valid-session.json").read_text())


def relay_job(**changes):
    body = json.loads((FIXTURES / "web-installer-relay-job.valid-failed.json").read_text())
    body.update(changes)
    return {key: value for key, value in body.items() if value is not ...}


def event(**changes):
    body = {"schemaVersion": 1, "id": str(uuid4()), "sessionId": str(uuid4()),
            "occurredAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "stage": "GATE", "outcome": "PASSED"}
    body.update(changes)
    return body


def encode(body):
    return json.dumps(body).encode()


class ValidationTests(unittest.TestCase):
    def invalid(self, body, code, validator=validate_event):
        with self.assertRaises(WebInstallerValidationError) as raised:
            validator(encode(body))
        self.assertEqual(str(raised.exception), code)

    def test_fixture_session_is_valid_and_normalized(self):
        rows = [validate_event(encode(body), now=NOW) for body in session_events()]
        self.assertEqual(rows[1]["model"], "fenix 8 - 47mm")
        self.assertEqual(rows[2]["error_name"], "NetworkError")
        self.assertIs(rows[3]["write_started"], True)
        self.assertEqual(rows[4]["mtp_response"], 0x200D)
        self.assertFalse(any(row["is_test"] for row in rows))

    def test_every_stage_outcome_and_closed_allowlist(self):
        for stage, outcomes in STAGES.items():
            for outcome in outcomes:
                extra = {"operation": "install"} if stage == "MAP_RESULT" else {}
                self.assertEqual(validate_event(encode(event(stage=stage, outcome=outcome, **extra)))["outcome"], outcome)
        self.invalid(event(outcome="CONNECTED"), "invalid_outcome")
        self.invalid(event(stage="INSTALL"), "invalid_stage")
        # Anything the contract does not list is refused, never dropped.
        self.invalid(event(serial="123"), "unknown_fields")
        self.invalid(event(model="fenix 8"), "unknown_fields")  # no watch data on GATE
        self.invalid(event(stage="CONNECT", outcome="CONNECTED", model="Fenix <8>"), "invalid_model")
        self.invalid(event(stage="MAP_RESULT", outcome="FAILED"), "missing_operation")
        self.invalid(event(stage="MAP_RESULT", outcome="SUCCEEDED", operation="install", reason="OTHER"), "unexpected_reason")
        blocked = event(stage="MAP_RESULT", outcome="FAILED", operation="install", reason="DOWNLOAD_BLOCKED",
                        failureStage="DOWNLOAD", errorName="TypeError")
        self.assertEqual(validate_event(encode(blocked))["reason"], "DOWNLOAD_BLOCKED")
        self.invalid(event(stage="MAP_RESULT", outcome="SUCCEEDED", operation="install", errorName="NetworkError"), "unknown_fields")
        self.invalid(event(stage="CONNECT", outcome="FAILED", errorName="Boom"), "invalid_errorName")
        self.invalid(event(stage="REMOVE", outcome="FAILED", mtpResponse=0x1000), "invalid_mtpResponse")
        self.invalid(event(osMajor="15"), "invalid_osMajor")
        self.invalid(event(isTest="yes"), "invalid_isTest")
        self.invalid(event(schemaVersion=2), "unsupported_schema")
        self.invalid(event(id="not-a-uuid"), "invalid_id")
        self.invalid(event(stage=["GATE"]), "invalid_stage")
        self.invalid(event(outcome={}), "invalid_outcome")
        self.invalid(event(occurredAt="2026-10-10T20:00:00"), "invalid_occurredAt")

    def test_far_future_time_uses_receipt_time(self):
        row = validate_event(encode(event(occurredAt="2026-10-10T22:00:00Z")), now=NOW)
        self.assertEqual(row["occurred_at"], NOW)

    def test_relay_job_rules(self):
        row = validate_relay_job(encode(relay_job()))
        self.assertEqual((row["outcome"], row["reason"], row["provider_http_status"]), ("FAILED", "PROVIDER_HTTP_ERROR", 503))
        self.assertEqual(validate_relay_job(encode(relay_job(outcome="DELIVERED", reason=None, providerHttpStatus=...)))["reason"], None)
        self.invalid(relay_job(reason=None, providerHttpStatus=...), "invalid_reason", validate_relay_job)
        self.invalid(relay_job(outcome="DELIVERED", providerHttpStatus=...), "invalid_reason", validate_relay_job)
        self.invalid(relay_job(reason="DISK_FULL"), "invalid_providerHttpStatus", validate_relay_job)
        self.invalid(relay_job(error="No space left on device: '/var/lib'"), "unknown_fields", validate_relay_job)
        self.invalid(relay_job(finishedAt="2026-10-10T20:00:00Z"), "invalid_finishedAt", validate_relay_job)
        self.invalid(relay_job(id="JOBKEY-secret"), "invalid_id", validate_relay_job)
        self.invalid(relay_job(region="Lat\nvia"), "invalid_region", validate_relay_job)
        self.invalid(relay_job(outcome=["FAILED"]), "invalid_outcome", validate_relay_job)
        self.invalid(relay_job(reason={}), "invalid_reason", validate_relay_job)
        for via in ("direct", "proxied", "mixed"):
            self.assertEqual(validate_relay_job(encode(relay_job(servedVia=via)))["served_via"], via)
        self.invalid(relay_job(servedVia="cloudflare"), "invalid_servedVia", validate_relay_job)
        self.invalid(relay_job(readyAt="2026-10-10T20:00:00Z"), "invalid_readyAt", validate_relay_job)
        self.invalid(relay_job(readyAt="2026-10-10T20:02:00Z"), "invalid_readyAt", validate_relay_job)
        self.invalid(relay_job(requestedAt="2099-01-01T00:00:00Z", finishedAt="2099-01-01T00:01:00Z"),
                     "invalid_finishedAt", validate_relay_job)

    def test_refused_jobs_count_as_failed_in_the_provider_row_too(self):
        refused = validate_relay_job(encode(relay_job(outcome="REFUSED", reason="NOT_REVIEWED", providerHttpStatus=...)))
        server = summarize([], [refused])["server"]
        self.assertEqual((server["requests"], server["failed"]), (0, 1))
        self.assertEqual(server["providers"], [{"provider": "opentopomap", "requests": 0, "delivered": 0, "failed": 1, "servedBytes": 0}])

    def test_every_attempt_counts_and_a_failure_only_after_writing_started(self):
        rows = [validate_event(encode(body), now=NOW) for body in session_events()]
        self.assertEqual([row["outcome"] for row in rows if counted_result(row)], ["FAILED", "SUCCEEDED"])
        for body, counted in (
            (event(stage="MAP_RESULT", outcome="CANCELLED", operation="install", reason="CANCELLED", writeStarted=True), False),
            (event(stage="MAP_RESULT", outcome="FAILED", operation="install", failureStage="DOWNLOAD",
                   reason="DOWNLOAD_STOPPED", writeStarted=False), False),
            (event(stage="MAP_RESULT", outcome="FAILED", operation="update", failureStage="VERIFY",
                   reason="CHECK_MISMATCH", writeStarted=True), True),
            (event(stage="CONNECT", outcome="CONNECTION_LOST"), False),
        ):
            self.assertIs(counted_result(validate_event(encode(body))), counted)

    def test_usb_model_code_needs_both_numbers(self):
        row = validate_event(encode(event(stage="CONNECT", outcome="CONNECTED", model="fenix 8 - 47mm",
                                          usbVendorId=0x091E, usbProductId=0x51B8)))
        self.assertEqual((row["usb_vendor_id"], row["usb_product_id"]), (0x091E, 0x51B8))
        self.invalid(event(stage="CONNECT", outcome="CONNECTED", usbVendorId=0x091E), "invalid_usbProductId")
        self.invalid(event(stage="CONNECT", outcome="CONNECTED", usbVendorId=0x091E, usbProductId=70000),
                     "invalid_usbProductId")
        self.invalid(event(usbVendorId=0x091E, usbProductId=1), "unknown_fields")  # not on GATE


class SharedCountTests(unittest.TestCase):
    """App and web install counts side by side (owner decision 2026-10-11)."""

    def test_public_counts_add_web_and_keep_each_part(self):
        last_app, last_web = datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 11, tzinfo=timezone.utc)
        row = {"attempted_install_count": 10, "successful_install_count": 9, "failed_install_count": 1,
               "success_rate": 90.0, "last_success": last_app, "web_attempted_install_count": 2,
               "web_successful_install_count": 1, "web_failed_install_count": 1, "web_last_success": last_web}
        self.assertEqual(_public_install_counts(row), {
            "attemptedInstallations": 12, "successfulInstallations": 10, "appSuccessfulInstallations": 9,
            "webSuccessfulInstallations": 1, "failedInstallations": 2, "successRate": 83.3,
            "lastSuccessfulInstallation": last_web.isoformat()})
        app_only = _public_install_counts({**row, "web_attempted_install_count": 0, "web_successful_install_count": 0,
                                           "web_failed_install_count": 0, "web_last_success": None})
        self.assertEqual((app_only["successRate"], app_only["webSuccessfulInstallations"]), (90.0, 0))

    def test_model_page_shows_app_web_and_all_rows_while_evidence_stays_app_only(self):
        payload = _admin_device_payload([{
            "device_id": "garmin-fenix-8-47-amoled", "model": "fēnix 8", "attempted_install_count": 0,
            "successful_install_count": 0, "failed_install_count": 0, "compatibility_successful_install_count": 0,
            "web_attempted_install_count": 3, "web_successful_install_count": 2, "web_failed_install_count": 1,
            "web_successful_update_count": 1, "web_failed_update_count": 0,
        }], None)
        device = payload["devices"][0]
        self.assertEqual((device["installationStats"]["attempts"], device["installationStats"]["successful"]), (3, 2))
        self.assertIsNone(device["evidenceStatus"])  # web results never make a model tested
        page = device_detail_page(device, {"username": "operator"}, "csrf").decode()
        installs = page.split("aria-label='Installs by source'", 1)[1].split("</section>", 1)[0]
        for source, values in (("app", ("0", "0", "0")), ("web", ("3", "2", "1")), ("all", ("3", "2", "1"))):
            row = installs.split(f"source-count-{source}'", 1)[1].split("</div>", 1)[0]
            self.assertIn(f"admin-icon-source-{source}", row)
            for key, value in zip(("attempts", "successful", "failed"), values):
                self.assertIn(f"data-stat='{source}-{key}'>{value}<", row)
        updates = page.split("aria-label='Updates by source'", 1)[1].split("</section>", 1)[0]
        self.assertIn("data-stat='web-successful'>1<", updates)
        self.assertIn("data-stat='web-blocked'>—<", updates)


class SupportTests(unittest.TestCase):
    def test_support_follows_the_current_page_rule_not_old_records(self):
        now = datetime.now(timezone.utc)
        rows = [{"stage": "GATE", "outcome": outcome, "os_family": os, "os_major": None, "browser_family": browser,
                 "browser_major": None, "session_id": str(uuid4()), "occurred_at": now}
                for os, browser, outcome in [
                    ("Windows", "Edge", "BLOCKED_BROWSER"),  # recorded before Chromium browsers were allowed
                    ("macOS", "Edge", "BLOCKED_BROWSER"), ("macOS", "Chrome", "PASSED"),
                    ("Linux", "Chrome", "PASSED_TESTING_PLATFORM"), ("macOS", "Firefox", "BLOCKED_BROWSER"),
                    ("Android", "Chrome", "BLOCKED_MOBILE"), ("macOS", "Other", "PASSED_TESTING_PLATFORM")]]
        support = {(s["system"], s["browser"]): s["support"] for s in summarize(rows, [])["watch"]["systems"]}
        self.assertEqual(support, {
            ("Windows", "Edge"): "BLOCKED_SYSTEM", ("macOS", "Edge"): "TESTING", ("macOS", "Chrome"): "SUPPORTED",
            ("Linux", "Chrome"): "TESTING", ("macOS", "Firefox"): "BLOCKED_BROWSER",
            ("Android", "Chrome"): "BLOCKED_SYSTEM", ("macOS", "Other"): "TESTING"})


class WebInstallerEndToEndTests(PGliteTestCase):
    """Page event payload → installer server forward → ingest → storage → Admin page."""

    def setUp(self):
        super().setUp()
        self.service = CatalogService(self.db, web_installer_ingest_secret=SECRET, operations_ingest_secret="o" * 48)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.db.create_admin_user("operator", hash_password("correct horse battery staple"))
        self.session, self.csrf = self.service.login_admin("operator", "correct horse battery staple")

    def request(self, method, path, body=None, *, secret=SECRET, admin=False, content_type="application/json"):
        connection = HTTPConnection(*self.http.server_address)
        headers = {}
        if body is not None:
            headers["Content-Type"] = content_type
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        if admin:
            headers["Cookie"] = f"terento_admin_session={self.session}; terento_admin_csrf={self.csrf}"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read().decode()
        connection.close()
        return response, payload

    def forward(self, body, kind="events", **options):
        return self.request("POST", f"/internal/web-installer/{kind}", encode(body), **options)[0].status

    def recent(self, body):
        """Fixture times moved into the last hour so the 24-hour Admin view shows them."""
        shift = datetime.now(timezone.utc) - timedelta(minutes=30) - datetime(2026, 10, 10, 20, tzinfo=timezone.utc)
        for key in ("occurredAt", "requestedAt", "finishedAt", "readyAt"):
            if key in body:
                moment = datetime.fromisoformat(body[key].replace("Z", "+00:00")) + shift
                body[key] = moment.isoformat().replace("+00:00", "Z")
        return body

    def test_ingest_statuses_and_authentication(self):
        body = event()
        self.assertEqual(self.forward(body, secret=None), 401)
        # The operations secret is a different principal and is not accepted.
        self.assertEqual(self.forward(body, secret="o" * 48), 401)
        self.assertEqual(self.forward(body), 201)
        self.assertEqual(self.forward(body), 200)
        self.assertEqual(self.forward(event(extra=1)), 400)
        self.assertEqual(self.request("POST", "/internal/web-installer/events", encode(body), content_type="text/plain")[0].status, 415)
        self.assertEqual(self.request("POST", "/internal/web-installer/events", b"x" * 5000)[0].status, 413)
        self.assertEqual(self.forward(relay_job(), "relay-jobs"), 201)
        self.assertEqual(self.forward(relay_job(), "relay-jobs"), 200)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_event")[0]["n"], 1)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_relay_job")[0]["n"], 1)

    def test_unconfigured_secret_refuses_everything(self):
        self.service.web_installer_ingest_secret = None
        self.assertEqual(self.forward(event()), 401)

    def test_page_session_reaches_the_admin_page(self):
        for body in session_events():
            self.assertEqual(self.forward(self.recent(body)), 201)
        # The system refused open (Windows driver, maybe another app): not a lost connection.
        self.assertEqual(self.forward(event(stage="CONNECT", outcome="OPEN_ACCESS_DENIED", osFamily="Windows", browserFamily="Edge",
                                            errorName="SecurityError")), 201)
        # Any Chromium browser with WebUSB passes as testing; Firefox has no WebUSB.
        self.assertEqual(self.forward(event(stage="GATE", outcome="PASSED_TESTING_PLATFORM", osFamily="macOS", browserFamily="Brave")), 201)
        self.assertEqual(self.forward(event(stage="GATE", outcome="BLOCKED_BROWSER", osFamily="macOS", browserFamily="Firefox")), 201)
        self.assertEqual(self.forward(self.recent(relay_job()), "relay-jobs"), 201)
        self.assertEqual(self.forward(self.recent(relay_job(id="3f2a9c1b7d4e5a61", outcome="DELIVERED", reason=None,
                         providerHttpStatus=..., readyAt="2026-10-10T20:01:10Z", sizeBytes=200_000_000,
                         servedBytes=200_000_000, servedVia="proxied", finishedAt="2026-10-10T20:02:10Z")), "relay-jobs"), 201)
        # A check record is stored but stays out of every number.
        self.assertEqual(self.forward(event(isTest=True, stage="CONNECT", outcome="CONNECTED", model="test watch")), 201)

        data = self.service.web_installer({"period": "24h"})
        watch, server = data["watch"], data["server"]
        # Every attempt counts: the write that lost the connection and the retry that succeeded.
        self.assertEqual((watch["connectedSessions"], watch["installed"], watch["updated"], watch["failed"]), (1, 1, 0, 1))
        self.assertEqual((watch["medianWriteS"], watch["medianVerifyS"]), (240, 30))
        self.assertEqual([(m["model"], m["system"], m["installed"]) for m in watch["models"]], [("fenix 8 - 47mm", "macOS 15", 1)])
        # Every failed attempt stays visible in Problems, with its codes.
        self.assertEqual([(p["stage"], p["reason"], p["error_name"]) for p in watch["mapProblems"]],
                         [("REMOVE", "OTHER", None), ("MAP_RESULT", "CONNECTION_LOST", "NetworkError")])
        self.assertEqual([r["outcome"] for r in watch["recent"]], ["FAILED", "SUCCEEDED", "FAILED"])  # remove, retry, first try
        self.assertEqual(sorted((s["browser"].split()[0], s["support"]) for s in watch["systems"]),
                         [("Brave", "TESTING"), ("Chrome", "SUPPORTED"), ("Firefox", "BLOCKED_BROWSER")])
        self.assertEqual([(p["os_family"], p["browser_family"]) for p in watch["connectProblems"]], [("Windows", "Edge")])
        self.assertEqual((server["requests"], server["delivered"], server["failed"], server["medianSendS"]), (2, 1, 1, 60))
        self.assertEqual(server["problems"][0]["providerHttpStatus"], 503)
        self.assertEqual(server["viaFallback"], 1)  # the dl port was blocked; sent through Cloudflare
        self.assertEqual(data["testRecords"]["count"], 1)

        response, page = self.request("GET", "/admin/web-installer?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        for text in ("<h1>Web installer</h1>", "Watch connected", "Maps installed", "Maps updated", "Writing",
                     "Watch models", "fenix 8 - 47mm", "macOS 15", "Systems and browsers", "Connection problems",
                     "Install and removal problems", "The connection to the watch ended", "CONNECTION_LOST · NetworkError",
                     "The browser could not open the watch", "OPEN_ACCESS_DENIED · SecurityError",
                     "Supported", "Testing", "title='Browser not supported'", "web-installer-support", "<th scope='col'>Browser</th>",
                     "admin-icon-browser-brave", "admin-icon-browser-firefox", "admin-icon-browser-edge",
                     "MTP 0x200D", "Recent results on watches", "On the server", "Providers", "Problems",
                     "Provider returned an error", "PROVIDER_HTTP_ERROR · HTTP 503", "Recent requests", "Test records: 1",
                     "Sent through Cloudflare", "100% of sent",
                     'href="/admin/web-installer">Web installer</a>'):
            self.assertIn(text, page)
        for gone in ("Now on the server", "Page visits", "Private lab", "test watch"):
            self.assertNotIn(gone, page)

        response, payload = self.request("GET", "/admin/web-installer.json?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        document = json.loads(payload)
        self.assertEqual(document["watch"]["installed"], 1)
        self.assertTrue(document["watch"]["recent"][0]["occurred_at"].endswith("Z"))  # admin JSON time format
        _, page = self.request("GET", "/admin/web-installer?period=24h&timeZone=Europe/Vilnius", secret=None, admin=True)
        self.assertIn("data-time-zone='Europe/Vilnius'", page)

    def test_dashboard_switch_shows_all_first_then_app_and_web(self):
        for body in session_events():
            self.forward(self.recent(body))
        self.forward(self.recent(relay_job()), "relay-jobs")
        overview = self.service.admin_overview("24h")
        web, combined = overview["web"], overview["all"]
        self.assertEqual((web["completedInstallCount"], web["failedInstallCount"], web["failedDownloadCount"]), (1, 1, 1))
        self.assertEqual(sum(row.get("success_count", 0) for row in web["trend"]), 1)
        self.assertEqual(overview["data"].get("completedInstallCount") or 0, 0)  # App view stays app-only
        self.assertEqual((combined["completedInstallCount"], combined["failedInstallCount"],
                          combined["failedDownloadCount"], combined["installSuccessRate"]), (1, 1, 1, 50.0))
        self.assertEqual(sum(row.get("failed_count", 0) for row in combined["trend"]), 1)
        self.assertEqual([(item["event_type"], item["source"]) for item in combined["recentActivity"]],
                         [("INSTALL_SUCCEEDED", "web"), ("INSTALL_FAILED", "web")])
        for period in ("7d", "all"):  # day/month buckets counted in SQL, in the admin time zone
            web = self.service.admin_overview(period, "Europe/Vilnius")["web"]
            self.assertEqual((sum(row.get("success_count", 0) for row in web["trend"]),
                              sum(row.get("download_failed_count", 0) for row in web["trend"])), (1, 1))
        response, page = self.request("GET", "/admin?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        switch = page.split("id='overview-period-form'", 1)[1].split("</form>", 1)[0]
        for source in ("all", "app", "web"):
            self.assertIn(f"data-source-switch='{source}'", switch)
            self.assertIn(f"admin-icon-source-{source}", switch)
        self.assertIn("class='active' data-source-switch='all' aria-pressed='true' aria-label='All'", switch)
        installs = page.split("id='overview-trend-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("<div data-source-panel='all'>", installs)
        self.assertIn("<div data-source-panel='app' hidden>", installs)
        web_panel = installs.split("<div data-source-panel='web' hidden>", 1)[1]
        self.assertIn("Install successful", web_panel)
        self.assertNotIn("Custom .img install", web_panel)
        activity = page.split("id='overview-activity'", 1)[1].split("</section>", 1)[0]
        self.assertEqual(activity.count("class='activity-source-web' role='img' aria-label='Web'"), 2)

    def test_admin_page_requires_a_session(self):
        response, _ = self.request("GET", "/admin/web-installer", secret=None)
        self.assertIn(response.status, {302, 303})

    def test_app_read_models_stay_app_only(self):
        for body in session_events():
            self.forward(self.recent(body))
        self.assertEqual(self.db.map_statistics({}), [])
        self.assertEqual(self.db.app_funnel_summary(None)["sessionCount"], 0)
        self.assertEqual(self.db.admin_review_summary()["installationIssues"], 0)

    def test_counted_web_results_join_the_shared_install_statistics(self):
        # The catalog's fēnix 8 47 mm (migration seed) is the one model the watch's text matches.
        events = [self.recent(body) for body in session_events()]
        for body in events:
            if body["stage"] in ("CONNECT", "MAP_RESULT"):
                body.update(usbVendorId=0x091E, usbProductId=0x51B8)
            self.assertEqual(self.forward(body), 201)
        # A cancelled map and a download failure never count.
        self.forward(event(stage="MAP_RESULT", outcome="CANCELLED", operation="install", provider="opentopomap",
                           packageId="otm-lithuania", reason="CANCELLED", writeStarted=False, model="fenix 8 - 47mm"))
        self.forward(event(stage="MAP_RESULT", outcome="FAILED", operation="install", provider="opentopomap",
                           packageId="otm-lithuania", failureStage="DOWNLOAD", reason="DOWNLOAD_STOPPED",
                           writeStarted=False, model="fenix 8 - 47mm"))
        stored = self.sql("SELECT DISTINCT canonical_device_model_id AS id, identity_resolution AS resolution, "
                          "usb_product_id FROM web_installer_event WHERE stage = 'MAP_RESULT' AND usb_product_id IS NOT NULL")
        self.assertEqual(stored, [{"id": "garmin-fenix-8-47-amoled", "resolution": "SINGLE_MATCH", "usb_product_id": 0x51B8}])

        # Maps page: one combined number per map and provider.
        statistics = self.service.map_statistics({"period": "24h"})
        self.assertEqual((statistics["summary"]["completedInstalls"], statistics["summary"]["failedInstalls"]), (1, 1))
        self.assertEqual(statistics["detailRows"], [])  # Event detail stays app reports only

        # Devices and the model page: App, Web and All.
        rows, _ = self.db.admin_device_snapshot()
        device = next(row for row in rows if row["device_id"] == "garmin-fenix-8-47-amoled")
        self.assertEqual((device["web_attempted_install_count"], device["web_successful_install_count"],
                          device["web_failed_install_count"]), (2, 1, 1))

        # A row received before its model was known resolves on the next cycle.
        self.sql("UPDATE web_installer_event SET canonical_device_model_id = NULL, identity_resolution = NULL")
        self.assertEqual(self.db.resolve_web_installer_identities()["resolved"], 5)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_event "
                                  "WHERE canonical_device_model_id = 'garmin-fenix-8-47-amoled'")[0]["n"], 5)

    def test_epix_pro_web_success_joins_the_47_mm_row_next_to_its_app_successes(self):
        # Production 2026-10-11: a Linux install on a watch reporting "epix pro - 47mm"
        # (no USB code yet) stayed off Devices; two earlier app successes were there.
        device_id = "garmin-epix-pro-gen-2-47"
        for index, day in enumerate((23, 24)):
            app = validate_compatibility_event(encode(compatibility_event(
                id=str(uuid4()), timestamp=f"2026-09-{day}T18:51:00Z", model="epix Pro (Gen 2)", family="epix",
                usbProductID=0x50D8, compatibilityIdentity="epix Pro (Gen 2) · 47 mm", variant="47 mm", caseSizeMm=47)))
            self.assertTrue(self.db.insert_compatibility_event(app))
            self.sql("UPDATE compatibility_evidence_event SET canonical_device_model_id = %s, "
                     "identity_resolution_state = 'RESOLVED' WHERE event_id = %s", (device_id, app["id"]))

        def stats():
            rows, _ = self.db.admin_device_snapshot()
            device = next(d for d in _admin_device_payload(rows, None)["devices"] if d["id"] == device_id)
            return device["installationStats"], device["evidenceStatus"]

        before, evidence = stats()
        self.assertEqual((before["attempts"], before["successful"]), (2, 2))
        succeeded = event(stage="MAP_RESULT", outcome="SUCCEEDED", operation="install", provider="bbbike",
                          packageId="bbbike-north-america-us-washington-bbbike-latin1", model="epix pro - 47mm",
                          firmware="2718", osFamily="Linux", writeStarted=True, writeS=16, verifyS=21,
                          occurredAt=(datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(self.forward(succeeded), 201)
        # The same event again, a test record and a watch with no size never add to the 47 mm row.
        self.forward(succeeded)
        self.forward(dict(succeeded, id=str(uuid4()), isTest=True))
        self.forward(dict(succeeded, id=str(uuid4()), model="epix pro"))
        stored = self.sql("SELECT model, canonical_device_model_id AS id, identity_resolution AS resolution "
                          "FROM web_installer_event WHERE is_test IS NOT TRUE ORDER BY model")
        self.assertEqual(stored, [{"model": "epix pro", "id": None, "resolution": "UNRESOLVED"},
                                  {"model": "epix pro - 47mm", "id": device_id, "resolution": "SINGLE_MATCH"}])
        after, evidence_after = stats()
        self.assertEqual((after["attempts"], after["successful"]), (3, 3))
        self.assertEqual(datetime.fromisoformat(after["lastSuccessfulAt"]), datetime.fromisoformat(succeeded["occurredAt"].replace("Z", "+00:00")))
        self.assertEqual(evidence_after, evidence)  # a web success never changes Tested status

        # A row stored before the fix resolves on the scheduler's next pass, once.
        self.sql("UPDATE web_installer_event SET canonical_device_model_id = NULL, identity_resolution = NULL")
        self.assertEqual(self.db.resolve_web_installer_identities(), {"pending": 2, "resolved": 1})
        self.db.resolve_web_installer_identities()
        self.assertEqual(stats()[0], after)

    def test_connection_problems_count_visits_and_name_the_model_from_the_usb_code(self):
        # One page load retried twice, another tried once; the open was refused
        # before the watch reported its model text, so a reviewed USB mapping names it.
        ids = [r["id"] for r in self.sql("SELECT id FROM device_model ORDER BY id LIMIT 3")]
        self.sql("DELETE FROM device_identity_mapping WHERE kind = 'USB' AND value IN ('091e:aaa1', '091e:aaa2', '091e:aaa3')")
        for value, device_id, status in (("091e:aaa1", ids[0], "APPROVED"),
                                         ("091e:aaa2", ids[1], "APPROVED"), ("091e:aaa2", ids[2], "APPROVED"),
                                         ("091e:aaa3", ids[0], "APPROVED"), ("091e:aaa3", ids[1], "PENDING")):
            self.sql("INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, status) "
                     "VALUES ('USB', %s, %s, 'https://example.test', 'test', %s)", (value, device_id, status))
        session = str(uuid4())
        for product, session_id in ((0xAAA1, session), (0xAAA1, session), (0xAAA1, None), (0xAAA2, None), (0xAAA3, None)):
            body = event(sessionId=session_id or str(uuid4()))
            body.update(stage="CONNECT", outcome="OPEN_ACCESS_DENIED", osFamily="Linux", browserFamily="Chromium",
                        errorName="SecurityError", usbVendorId=0x091E, usbProductId=product)
            self.assertEqual(self.forward(self.recent(body)), 201)
        # Identity rules need the model text: nothing is resolved or counted for a model.
        self.db.resolve_web_installer_identities()
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_event WHERE canonical_device_model_id IS NOT NULL")[0]["n"], 0)
        name = self.sql("SELECT canonical_model AS name FROM device_model WHERE id = %s", (ids[0],))[0]["name"]
        problems = self.service.web_installer({"period": "24h"})["watch"]["connectProblems"]
        # A shared code (two models) and a code with an unreviewed second model name no watch.
        self.assertEqual([(p["browser_family"], p["sessions"], p["count"], p["models"]) for p in problems],
                         [("Chromium", 4, 5, [name])])
        _, page = self.request("GET", "/admin/web-installer?period=24h", secret=None, admin=True)
        connect = page.split("id='web-installer-connect'", 1)[1].split("</section>", 1)[0]
        for text in ("<th scope='col' class='column-number'>Visits</th>", "<th scope='col'>Watch models</th>",
                     f"<td>{name}</td>", "admin-icon-browser-other"):
            self.assertIn(text, connect)

    def test_retention(self):
        self.forward(event())
        self.sql("UPDATE web_installer_event SET received_at = now() - interval '25 months'")
        self.db.prune_compatibility_events()
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_event")[0]["n"], 0)

    def test_owner_cleanup_migration_removes_records_before_the_boundary_only_after_the_reviewed_counts(self):
        cutoff = "2026-10-11T15:39:48.365772Z"
        statements = _statements(OWNER_CLEANUP_MIGRATION.read_text(encoding="utf-8"))

        def seed(reviewed_events):
            later = ["TIMESTAMPTZ '2026-10-11T15:49:59Z'", "TIMESTAMPTZ '2026-10-11T15:50:00Z'"]
            for index in range(reviewed_events + 2):
                received = f"TIMESTAMPTZ '{cutoff}' - interval '{index} minutes'" if index < reviewed_events else later[index - reviewed_events]
                self.sql("INSERT INTO web_installer_event (event_id, session_id, occurred_at, received_at, stage, outcome) "
                         f"VALUES (gen_random_uuid(), gen_random_uuid(), now(), {received}, 'GATE', 'PASSED')")
            for index in range(4):
                received = f"TIMESTAMPTZ '{cutoff}'" if index < 3 else "TIMESTAMPTZ '2026-10-11T15:45:00Z'"
                self.sql("INSERT INTO web_installer_relay_job (job_id, requested_at, finished_at, provider, package_id, "
                         f"served_bytes, outcome, received_at) VALUES ('{index:016x}', now(), now(), 'freizeitkarte', 'p', 0, "
                         f"'DELIVERED', {received})")

        def run():
            for statement in statements:
                self.sql(statement)
            self.sql("DROP TABLE _web_installer_cleanup_guard")  # ON COMMIT DROP, and the test never commits

        def count(table):
            return self.sql(f"SELECT count(*) AS n FROM {table}")[0]["n"]

        run()  # an empty database is a no-op
        self.assertEqual(count("web_installer_event"), 0)

        seed(32)
        self.sql("SAVEPOINT wrong_counts")
        with self.assertRaises(Exception):
            run()
        self.sql("ROLLBACK TO SAVEPOINT wrong_counts")
        self.assertEqual(count("web_installer_event"), 34)
        self.sql("DELETE FROM web_installer_event")
        self.sql("DELETE FROM web_installer_relay_job")

        seed(33)
        run()
        kept = self.sql("SELECT received_at FROM web_installer_event")
        self.assertEqual([row["received_at"] for row in kept], [datetime(2026, 10, 11, 15, 50, tzinfo=timezone.utc)])
        self.assertEqual(count("web_installer_relay_job"), 0)
        details = self.sql("SELECT details FROM admin_audit_log WHERE action = 'web_installer.owner_test_records_purged'")
        self.assertEqual(len(details), 1)
        self.assertEqual({key: value for key, value in details[0]["details"].items() if key != "checkCutoff"},
                         {"receivedBefore": "2026-10-11T15:50:00Z", "eventCount": 34, "eventsAfterCheck": 1,
                          "relayJobCount": 4, "relayJobsAfterCheck": 1})


if __name__ == "__main__":
    unittest.main()

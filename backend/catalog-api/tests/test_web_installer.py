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
from terento_catalog.admin import hash_password
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.web_installer import (
    STAGES,
    WebInstallerValidationError,
    final_map_results,
    summarize,
    validate_event,
    validate_relay_job,
)

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
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
        self.invalid(relay_job(readyAt="2026-10-10T20:00:00Z"), "invalid_readyAt", validate_relay_job)
        self.invalid(relay_job(readyAt="2026-10-10T20:02:00Z"), "invalid_readyAt", validate_relay_job)
        self.invalid(relay_job(requestedAt="2099-01-01T00:00:00Z", finishedAt="2099-01-01T00:01:00Z"),
                     "invalid_finishedAt", validate_relay_job)

    def test_refused_jobs_count_as_failed_in_the_provider_row_too(self):
        refused = validate_relay_job(encode(relay_job(outcome="REFUSED", reason="NOT_REVIEWED", providerHttpStatus=...)))
        server = summarize([], [refused])["server"]
        self.assertEqual((server["requests"], server["failed"]), (0, 1))
        self.assertEqual(server["providers"], [{"provider": "opentopomap", "requests": 0, "delivered": 0, "failed": 1, "servedBytes": 0}])

    def test_final_result_is_the_last_one_of_the_page_load(self):
        rows = [validate_event(encode(body), now=NOW) for body in session_events()]
        final = final_map_results(rows)
        self.assertEqual([row["outcome"] for row in final], ["SUCCEEDED"])


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
        self.assertEqual(self.forward(self.recent(relay_job()), "relay-jobs"), 201)
        self.assertEqual(self.forward(self.recent(relay_job(id="3f2a9c1b7d4e5a61", outcome="DELIVERED", reason=None,
                         providerHttpStatus=..., readyAt="2026-10-10T20:01:10Z", sizeBytes=200_000_000,
                         servedBytes=200_000_000, finishedAt="2026-10-10T20:02:10Z")), "relay-jobs"), 201)
        # A check record is stored but stays out of every number.
        self.assertEqual(self.forward(event(isTest=True, stage="CONNECT", outcome="CONNECTED", model="test watch")), 201)

        data = self.service.web_installer({"period": "24h"})
        watch, server = data["watch"], data["server"]
        self.assertEqual((watch["connectedSessions"], watch["installed"], watch["updated"], watch["failed"]), (1, 1, 0, 0))
        self.assertEqual((watch["medianWriteS"], watch["medianVerifyS"]), (240, 30))
        self.assertEqual([(m["model"], m["system"], m["installed"]) for m in watch["models"]], [("fenix 8 - 47mm", "macOS 15", 1)])
        # Every failed attempt stays visible in Problems, with its codes.
        self.assertEqual([(p["stage"], p["reason"], p["error_name"]) for p in watch["mapProblems"]],
                         [("REMOVE", "OTHER", None), ("MAP_RESULT", "CONNECTION_LOST", "NetworkError")])
        self.assertEqual([r["outcome"] for r in watch["recent"]], ["FAILED", "SUCCEEDED"])  # remove, final install
        self.assertEqual((server["requests"], server["delivered"], server["failed"], server["medianSendS"]), (2, 1, 1, 60))
        self.assertEqual(server["problems"][0]["providerHttpStatus"], 503)
        self.assertEqual(data["testRecords"]["count"], 1)

        response, page = self.request("GET", "/admin/web-installer?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        for text in ("<h1>Web installer</h1>", "Watch connected", "Maps installed", "Maps updated", "Writing",
                     "Watch models", "fenix 8 - 47mm", "macOS 15", "Systems and browsers", "Connection problems",
                     "Install and removal problems", "The connection to the watch ended", "CONNECTION_LOST · NetworkError",
                     "MTP 0x200D", "Recent results on watches", "On the server", "Providers", "Problems",
                     "Provider returned an error", "PROVIDER_HTTP_ERROR · HTTP 503", "Recent requests", "Test records: 1",
                     'href="/admin/web-installer">Web installer</a>'):
            self.assertIn(text, page)
        for gone in ("Now on the server", "Page visits", "Private lab", "test watch"):
            self.assertNotIn(gone, page)

        response, payload = self.request("GET", "/admin/web-installer.json?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload)["watch"]["installed"], 1)

    def test_dashboard_web_switch_shows_web_records_only_behind_web(self):
        for body in session_events():
            self.forward(self.recent(body))
        self.forward(self.recent(relay_job()), "relay-jobs")
        overview = self.service.admin_overview("24h")
        web = overview["web"]
        self.assertEqual((web["completedInstallCount"], web["failedInstallCount"], web["failedDownloadCount"]), (1, 0, 1))
        self.assertEqual(sum(row.get("success_count", 0) for row in web["trend"]), 1)
        self.assertEqual(overview["data"].get("completedInstallCount") or 0, 0)  # App view stays app-only
        response, page = self.request("GET", "/admin?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        installs = page.split("id='overview-trend-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("data-source-switch='web'", installs)
        web_panel = installs.split("<div data-source-panel='web' hidden>", 1)[1]
        self.assertIn("Install successful", web_panel)
        self.assertNotIn("Custom .img install", web_panel)

    def test_admin_page_requires_a_session(self):
        response, _ = self.request("GET", "/admin/web-installer", secret=None)
        self.assertIn(response.status, {302, 303})

    def test_web_records_never_enter_app_statistics(self):
        for body in session_events():
            self.forward(self.recent(body))
        self.assertEqual(self.db.map_statistics({}), [])
        self.assertEqual(self.db.app_funnel_summary(None)["sessionCount"], 0)
        self.assertEqual(self.db.admin_review_summary()["installationIssues"], 0)

    def test_retention(self):
        self.forward(event())
        self.sql("UPDATE web_installer_event SET received_at = now() - interval '25 months'")
        self.db.prune_compatibility_events()
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_event")[0]["n"], 0)


if __name__ == "__main__":
    unittest.main()

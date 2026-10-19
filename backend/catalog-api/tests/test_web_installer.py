"""Web installer statistics: validation, ingest, storage, Admin page (end to end)."""
import csv
import io
import json
import os
import re
import subprocess
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from pglite_support import PGliteTestCase
from test_compatibility_evidence import event as compatibility_event
from terento_catalog.admin import (
    _admin_device_payload, _admin_timezone_script, _overview_activity_device, dashboard_page, device_detail_page,
    hash_password, map_statistics_page,
)
from terento_catalog.map_events import MapEventValidationError, validate_map_event
from terento_catalog.admin_web_installer import WORDS, _grouped_card_script, web_installer_csv, web_installer_page
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
        # Every connection outcome has its plain words in the Admin, so none
        # reads as "Other connection error" by accident.
        self.assertEqual(sorted(outcome for outcome in STAGES["CONNECT"] - {"CONNECTED"} if outcome not in WORDS), [])
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


class PageTests(unittest.TestCase):
    """Admin Web installer page layout (owner layout A, 2026-10-12)."""

    def page(self, events, jobs=()):
        return web_installer_page({**summarize(events, list(jobs)), "testRecords": {"count": 2, "last": NOW}},
                                  {"username": "operator"}, "csrf", period="24h").decode()

    def row(self, stage, outcome, **fields):
        return {"session_id": fields.pop("session", "s1"), "occurred_at": NOW, "stage": stage, "outcome": outcome,
                "os_family": "macOS", "os_major": 15, "browser_family": "Chrome", "browser_major": 141, **fields}

    def test_sections_answer_results_problems_watches_server_then_history(self):
        main = self.page([self.row("CONNECT", "CONNECTED", model="fenix 8")]).split("<main", 1)[1]
        order = ["web-installer-kpis", "id='web-installer-problems'", "id='web-installer-watches'",
                 "id='web-installer-server'", "id='web-installer-recent'", "Test records: 2"]
        self.assertEqual([main.index(part) for part in order], sorted(main.index(part) for part in order))
        kpis = main.split("web-installer-kpis", 1)[1].split("</section>", 1)[0]
        labels = ["Maps installed", "Maps updated", "Failed after write start", "Connected visits", "Writing · median", "Checking · median"]
        self.assertEqual([kpis.index(f">{label}<") for label in labels], sorted(kpis.index(f">{label}<") for label in labels))
        # No failure: no danger tone; no success yet: the medians stay unknown, not zero.
        self.assertNotIn("data-tone='danger'", kpis)
        self.assertEqual(kpis.count("—<span class='sr-only'>Unknown</span>"), 2)
        self.assertNotIn("% ", kpis)
        self.assertIn("<details><summary><h2 id='web-installer-recent-title'>Recent results on watches", main)

    def test_each_problem_record_has_one_step_and_none_is_lost(self):
        events = [self.row("CONNECT", "NO_WATCH_CHOSEN", session=f"s{n % 2}") for n in range(3)] + [
            self.row("MAP_RESULT", "FAILED", failure_stage="WRITE", reason="CONNECTION_LOST", write_started=True, model="fenix 8"),
            self.row("MAP_RESULT", "FAILED", failure_stage="WRITE", reason="CONNECTION_LOST", write_started=True, model="fenix 8"),
            self.row("MAP_RESULT", "FAILED", reason="OTHER", model="fenix 8"),  # no step reported
            self.row("REMOVE", "FAILED", failure_stage="VERIFY", reason="CONNECTION_LOST", model="fenix 8"),
            self.row("MAP_RESULT", "CANCELLED", failure_stage="DOWNLOAD", reason="CANCELLED"),
        ]
        page = self.page(events)
        problems = page.split("id='web-installer-problems'", 1)[1].split("</section>", 1)[0]
        tabs = {step: problems.split(f"data-group-switch='{step}'", 1)[1].split("</button>", 1)[0] for step in
                ("connect", "PREPARE", "DOWNLOAD", "WRITE", "VERIFY", "REMOVE", "OTHER")}
        counts = {step: tab.rsplit("web-installer-count'>", 1)[1].split("<", 1)[0] for step, tab in tabs.items()}
        # Connection counts attempts (3), not visits (2); the removal is Removal although it failed while checking;
        # the cancelled install is no problem; the record without a step is Other.
        self.assertEqual(counts, {"connect": "3", "PREPARE": "0", "DOWNLOAD": "0", "WRITE": "2", "VERIFY": "0", "REMOVE": "1", "OTHER": "1"})
        self.assertIn("data-group-default='connect'", problems)
        panel = lambda step: problems.split(f"<div data-group-panel='{step}'", 1)[1].split("<div data-group-panel=", 1)[0]
        self.assertEqual(sum(panel(step).count("<details class='web-installer-record'>") for step in tabs if step != "connect"), 3)
        self.assertIn("VERIFY · CONNECTION_LOST", panel("REMOVE"))
        self.assertIn("<small>After writing started</small><strong>2</strong>", panel("WRITE"))

    def test_phone_records_show_results_at_once_and_support_is_text(self):
        events = [self.row("GATE", "PASSED"), self.row("CONNECT", "CONNECTED", model="fenix 8", firmware="23.39"),
                  self.row("MAP_RESULT", "FAILED", failure_stage="WRITE", reason="CONNECTION_LOST", write_started=True,
                           model="fenix 8", operation="install")]
        page = self.page(events)
        watches = page.split("id='web-installer-watches'", 1)[1].split("</section>", 1)[0]
        record = watches.split("<div class='web-installer-narrow'>", 1)[1].split("</details>", 1)[0]
        summary = record.split("</summary>", 1)[0]
        for label in ("Installed", "Updated", "Failed"):
            self.assertIn(f"<small>{label}</small>", summary)
        self.assertIn("<strong class='web-installer-failed'>1</strong>", summary)
        for label in ("Firmware", "Connected", "Last seen"):
            self.assertIn(f"<dt>{label}</dt>", record)
        self.assertIn("<span class='web-installer-support'><span class='admin-pill admin-pill-success' data-status='SUPPORTED'>", page)
        self.assertNotIn("title='", page)
        history = page.split("id='web-installer-recent'", 1)[1].split("</section>", 1)[0]
        self.assertIn("Recent results on watches <span class='web-installer-count'>1</span>", history)
        self.assertIn("<small>Result</small><span class='admin-pill admin-pill-danger' data-status='FAILED'>",
                      history.split("<div class='web-installer-narrow'>", 1)[1])


    def test_nested_switches_stay_apart_and_a_missing_choice_falls_back(self):
        # A tiny DOM: the Problems step switch holds the Connection group-by switch.
        harness = r"""
const make = (attrs = {}, children = []) => {
  const node = {attrs, children, parent: null, hidden: 'hidden' in attrs, classList: {toggle() {}},
    get dataset() { return Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith('data-'))
      .map(([k, v]) => [k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase()), v])); },
    setAttribute(k, v) { attrs[k] = v; }, getAttribute(k) { return attrs[k]; },
    matches(selector) { return selector.slice(1, -1) in attrs; },
    closest(selector) { for (let x = this; x; x = x.parent) if (x.matches(selector)) return x; return null; },
    querySelectorAll(selector) { const out = []; const walk = (m) => m.children.forEach((c) => { if (c.matches(selector)) out.push(c); walk(c); }); walk(this); return out; }};
  children.forEach((child) => { child.parent = node; });
  return node;
};
const page = (other) => {
  const inner = make({'data-group-card': 'groups', 'data-group-default': 'problem'}, [
    make({'data-group-switch': 'problem'}), make({'data-group-switch': 'system'}),
    make({'data-group-panel': 'problem'}), make({'data-group-panel': 'system', hidden: ''})]);
  return make({}, [make({'data-group-card': 'steps', 'data-group-default': 'connect'}, [
    make({'data-group-switch': 'connect'}), ...(other ? [make({'data-group-switch': 'OTHER'})] : []),
    make({'data-group-panel': 'connect'}, [inner]), ...(other ? [make({'data-group-panel': 'OTHER', hidden: ''})] : [])])]);
};
const listeners = {};
let root = page(true);
global.document = {querySelectorAll: (s) => root.querySelectorAll(s), getElementById: () => null,
                   addEventListener: (type, fn) => { listeners[type] = fn; }};
global.window = {addEventListener: (type, fn) => { listeners[type] = fn; }};
eval(process.argv[1]);
const click = (name) => listeners.click({target: root.querySelectorAll('[data-group-switch]').find((b) => b.attrs['data-group-switch'] === name)});
const shown = () => root.querySelectorAll('[data-group-panel]').filter((p) => !p.hidden).map((p) => p.attrs['data-group-panel']).join(',');
const result = [];
click('OTHER'); result.push(shown());
click('system'); result.push(shown());
root = page(false); listeners['terento-admin-content-changed'](); result.push(shown());
console.log(JSON.stringify(result));
"""
        result = subprocess.run([os.environ.get("TERENTO_NODE_BIN", "node"), "-e", harness, _grouped_card_script()],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["problem,OTHER", "system,OTHER", "connect,system"])


    def test_dates_and_time_zone_carry_no_tooltip_here_but_keep_them_elsewhere(self):
        # The shared time script after start, a period reload (main replaced) and a time zone change.
        harness = r"""
const element = (attrs = {}) => ({attrs, dataset: {}, textContent: '', listeners: {},
  setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
  set title(v) { this.attrs.title = v; }, get title() { return this.attrs.title || ''; },
  closest: () => null, replaceChildren() {}, addEventListener(type, fn) { this.listeners[type] = fn; }});
const run = (noTitles) => {
  const select = element({title: 'Time zone'});
  let main = {noTitles, times: [1, 2].map(() => Object.assign(element(), {dataset: {adminTimestamp: '2026-10-12T13:35:00Z'}}))};
  global.window = {addEventListener() {}, dispatchEvent() {}};
  global.Event = class {};
  global.localStorage = {getItem: () => null, setItem() {}};
  global.document = {documentElement: {style: {setProperty() {}}}, createElement: () => element(),
    querySelector: (s) => s === '#admin-timezone' ? select : s === '[data-admin-no-titles]' ? (main.noTitles ? {} : null) : null,
    querySelectorAll: (s) => s === '[data-admin-timestamp]' ? main.times : []};
  eval(process.argv[1]);
  const titles = () => main.times.filter((t) => 'title' in t.attrs).length + ('title' in select.attrs ? 1 : 0);
  const seen = [titles()];
  main = {noTitles, times: [Object.assign(element(), {dataset: {adminTimestamp: '2026-10-12T14:00:00Z'}})]};
  window.TerentoAdminTime.render(); seen.push(titles());
  select.value = 'UTC'; select.listeners.change(); seen.push(titles(), main.times[0].textContent);
  return seen;
};
console.log(JSON.stringify([run(true), run(false)]));
"""
        result = subprocess.run([os.environ.get("TERENTO_NODE_BIN", "node"), "-e", harness, _admin_timezone_script()],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [[0, 0, 0, "2026-10-12 14:00"], [3, 2, 2, "2026-10-12 14:00"]])
        self.assertIn("id='main-content' data-admin-no-titles>", self.page([]))


class ExportAndActivityTests(unittest.TestCase):
    def test_csv_quotes_text_a_spreadsheet_would_run_and_keeps_unknown_values_empty(self):
        job = {"job_id": "a" * 16, "requested_at": NOW, "finished_at": NOW, "ready_at": None, "provider": "bbbike",
               "package_id": "x", "region": "=HYPERLINK(1)", "outcome": "FAILED", "reason": "OTHER", "served_bytes": 0}
        rows = list(csv.reader(io.StringIO(web_installer_csv([], [job], "UTC").decode().removeprefix("\ufeff"))))
        header, row = rows
        self.assertEqual(row[header.index("Region")], "'=HYPERLINK(1)")
        self.assertEqual((row[header.index("Preparing s")], row[header.index("Sending s")]), ("", ""))

    def test_web_activity_without_one_catalog_model_shows_the_reported_name_unlinked(self):
        web = {"source": "web", "canonical_device_model_id": None, "model": None, "reported_model": "fenix 7x pro"}
        self.assertEqual(_overview_activity_device(web), "<span class='overview-activity-reported'>fenix 7x pro</span>")
        self.assertEqual(_overview_activity_device({**web, "source": "app"}), "")
        self.assertIn("href=", _overview_activity_device({**web, "canonical_device_model_id": "garmin-fenix-7x-pro",
                                                          "model": "fēnix 7X Pro"}))


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
        self.assertEqual({(s["os_family"], s["browser_family"]) for s in watch["systems"]},
                         {(s["system"].split()[0], s["browser"].split()[0]) for s in watch["systems"]})  # grouping keys
        self.assertEqual(sorted((s["browser"].split()[0], s["support"]) for s in watch["systems"]),
                         [("Brave", "TESTING"), ("Chrome", "SUPPORTED"), ("Firefox", "BLOCKED_BROWSER")])
        self.assertEqual([(p["os_family"], p["browser_family"]) for p in watch["connectProblems"]], [("Windows", "Edge")])
        self.assertEqual({name: [(g["outcome" if name == "problem" else name.replace("system", "os") + "_family"], g["sessions"], g["count"])
                                 for g in groups] for name, groups in watch["connectGroups"].items()},
                         {"problem": [("OPEN_ACCESS_DENIED", 1, 1)], "system": [("Windows", 1, 1)], "browser": [("Edge", 1, 1)]})
        self.assertEqual((server["requests"], server["delivered"], server["failed"], server["medianSendS"]), (2, 1, 1, 60))
        self.assertEqual(server["problems"][0]["providerHttpStatus"], 503)
        self.assertEqual(server["viaFallback"], 1)  # the dl port was blocked; sent through Cloudflare
        self.assertEqual(data["testRecords"]["count"], 1)

        response, page = self.request("GET", "/admin/web-installer?period=24h", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        for text in ("<h1>Web installer</h1>", "Connected visits", "Maps installed", "Maps updated", "Failed after write start",
                     "Writing · median", "Checking · median", "Watch models", "fenix 8 - 47mm", "macOS 15", "Systems and browsers",
                     "id='web-installer-problems'", "The connection to the watch ended", "CONNECTION_LOST · NetworkError",
                     "USB access denied", "OPEN_ACCESS_DENIED · SecurityError",
                     "<span>Supported</span>", "<span>Testing</span>", "<span>Browser not supported</span>", "web-installer-support",
                     "<th scope='col'>Browser</th>",
                     "data-group-card='web-installer-systems-groups'", "data-group-switch='browser'", "<tr data-group-key='macOS'>",
                     "<tr data-group-key='Brave'>", "class='web-installer-group-rows' id='web-installer-systems-groups-system-0' hidden>",
                     "data-group-card='web-installer-connect-groups' data-group-default='problem'", "<tr data-group-key='OPEN_ACCESS_DENIED'>",
                     "admin-icon-browser-brave", "admin-icon-browser-firefox", "admin-icon-browser-edge", "admin-icon-source-web",
                     "MTP 0x200D", "Recent results on watches", "id='web-installer-server'", "Providers",
                     "Provider returned an error", "PROVIDER_HTTP_ERROR · HTTP 503", "Recent requests", "Test records: 1",
                     "Through Cloudflare", "100% of sent",
                     'href="/admin/web-installer">Web installer</a>'):
            self.assertIn(text, page)
        for gone in ("Now on the server", "Page visits", "Private lab", "test watch", "On the watch", "On the server",
                     "title='", "admin-scope-chip"):
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
        response, _ = self.request("GET", "/admin/web-installer.csv", secret=None)
        self.assertIn(response.status, {302, 303})

    def test_csv_export_has_every_record_of_the_period_without_test_records(self):
        bodies = [self.recent(body) for body in session_events()]
        for body in bodies:
            self.assertEqual(self.forward(body), 201)
        self.assertEqual(self.forward(self.recent(relay_job()), "relay-jobs"), 201)
        self.assertEqual(self.forward(event(isTest=True, stage="CONNECT", outcome="CONNECTED", model="test watch")), 201)
        old = event(stage="CONNECT", outcome="FAILED", occurredAt="2026-01-01T00:00:00Z")
        self.assertEqual(self.forward(old), 201)

        _, page = self.request("GET", "/admin/web-installer?period=24h&timeZone=Europe/Vilnius", secret=None, admin=True)
        self.assertIn("href='/admin/web-installer.csv?period=24h&amp;timeZone=Europe%2FVilnius' download>", page)
        response, payload = self.request("GET", "/admin/web-installer.csv?period=24h&timeZone=Europe/Vilnius", secret=None, admin=True)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/csv; charset=utf-8")
        self.assertRegex(response.getheader("Content-Disposition"),
                         r'^attachment; filename="terento-web-installer-24h-\d{4}-\d{2}-\d{2}\.csv"$')
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        rows = list(csv.DictReader(io.StringIO(payload.removeprefix("\ufeff"))))
        self.assertEqual(len(rows), len(bodies) + 1)  # every page event and the server request; no test, no older record
        self.assertEqual({row["ID"] for row in rows if row["Record"] == "Page"}, {body["id"] for body in bodies})
        self.assertNotIn("test watch", payload)
        self.assertNotIn(old["id"], payload)
        times = [row["Time (Europe/Vilnius)"] for row in rows]
        self.assertEqual(times, sorted(times, reverse=True))
        lost = next(row for row in rows if row["Reason"] == "CONNECTION_LOST")
        self.assertEqual((lost["Step"], lost["Action"], lost["Result"], lost["Problem"], lost["Error"], lost["Write started"],
                          lost["Watch"], lost["System"]),
                         ("Map", "Install", "FAILED", "The connection to the watch ended", "NetworkError", "yes",
                          "fenix 8 - 47mm", "macOS 15"))
        self.assertIn("0x200D", {row["MTP"] for row in rows})
        server = next(row for row in rows if row["Record"] == "Server")
        self.assertEqual((server["Step"], server["Reason"], server["HTTP"]), ("Map request", "PROVIDER_HTTP_ERROR", "503"))

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

    def test_installations_and_maps_show_all_app_and_web_with_equal_web_totals(self):
        # Owner 2026-10-13: Installations, Maps and the Dashboard count web
        # installs the same way, with an All/App/Web switch.
        device_id = "garmin-epix-pro-gen-2-47"
        app = validate_compatibility_event(encode(compatibility_event(
            id=str(uuid4()), timestamp=(datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            model="epix Pro (Gen 2)", family="epix", usbProductID=0x50D8,
            compatibilityIdentity="epix Pro (Gen 2) · 47 mm", variant="47 mm", caseSizeMm=47)))
        self.assertTrue(self.db.insert_compatibility_event(app))
        self.sql("UPDATE compatibility_evidence_event SET canonical_device_model_id = %s, "
                 "identity_resolution_state = 'RESOLVED' WHERE event_id = %s", (device_id, app["id"]))
        at = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = dict(stage="MAP_RESULT", operation="install", provider="bbbike",
                      packageId="bbbike-north-america-us-washington-bbbike-latin1", occurredAt=at)
        self.forward(event(**result, outcome="SUCCEEDED", model="epix pro - 47mm", writeStarted=True))
        self.forward(event(**result, outcome="FAILED", model="epix pro - 47mm", writeStarted=True, reason="CONNECTION_LOST",
                           failureStage="WRITE"))
        # A watch with no single catalog model counts in totals as its own Web row.
        self.forward(event(**result, outcome="SUCCEEDED", model="fenix 7x pro", writeStarted=True))
        # Never counted: a download failure and a test record.
        self.forward(event(**result, outcome="FAILED", model="fenix 7x pro", writeStarted=False,
                           failureStage="DOWNLOAD", reason="DOWNLOAD_STOPPED"))
        self.forward(event(**result, outcome="SUCCEEDED", model="epix pro - 47mm", writeStarted=True, isTest=True))

        web_rows = self.db.web_installer_installation_rows()
        counts = {(row["canonical_device_model_id"], row["reported_model"]): (
            row["attempted_install_count"], row["successful_install_count"], row["failed_install_count"]) for row in web_rows}
        self.assertEqual(counts, {(device_id, None): (2, 1, 1), (None, "fenix 7x pro"): (1, 1, 0)})

        def installations(source):
            body = dashboard_page(
                self.service.compatibility_statistics(), {"username": "test"}, "csrf",
                diagnostic_summary=self.service.compatibility_diagnostic_summary(),
                identity_devices=self.service.admin_devices()["devices"], web_rows=web_rows, source=source,
            ).decode()
            tiles = {key: int(value) for key, value in re.findall(
                r"data-stat='(attempts|successful|failed)'[^>]*>(\d+)<", body)}
            return tiles, body

        app_tiles, app_body = installations("app")
        web_tiles, web_body = installations("web")
        all_tiles, all_body = installations("all")
        self.assertEqual(web_tiles, {"attempts": 3, "successful": 2, "failed": 1})
        self.assertEqual(all_tiles, {key: app_tiles[key] + web_tiles[key] for key in all_tiles})
        self.assertIn("fenix 7x pro<span class='activity-source-web'", all_body)
        self.assertNotIn("fenix 7x pro", app_body)
        self.assertIn("name='source' value='web' class='active' aria-pressed='true'", web_body)
        # The epix row joins its app and web results; Evidence stays app-only.
        epix = re.search(r"<tr class='evidence-model-row'[^>]*data-identity='canonical:garmin-epix-pro-gen-2-47'[^>]*>", all_body).group(0)
        self.assertIn("data-attempts='3'", epix)

        # Maps: All sums both sources, App and Web show one; Web equals the Installations Web install totals.
        def maps(source):
            summary = self.service.map_statistics({"period": "24h", "source": source})["summary"]
            return summary["completedInstalls"], summary["failedInstalls"]

        self.assertEqual(maps("web"), (web_tiles["successful"], web_tiles["failed"]))
        self.assertEqual(maps("all"), tuple(a + w for a, w in zip(maps("app"), maps("web"))))
        self.assertEqual(self.service.map_statistics({"period": "24h", "source": "web"})["detailRows"], [])
        with self.assertRaises(MapEventValidationError):
            self.service.map_statistics({"source": "phone"})
        page = map_statistics_page(self.service.map_statistics({"period": "24h", "source": "web"}), [],
                                   {"username": "test"}, "csrf").decode()
        self.assertIn("<input type='hidden' name='source' value='web'>", page)
        self.assertIn("name='source' value='web' class='active' aria-pressed='true'", page)
        self.assertNotIn("id='map-statistics-event-detail'", page)
        # Dashboard Web shows the same web installs.
        web = self.service.admin_overview("24h")["web"]
        self.assertEqual((web["completedInstallCount"], web["failedInstallCount"]), maps("web"))

    def test_installations_app_total_equals_maps_app_installs_with_unreported_watches(self):
        # Production 2026-10-13: Installations 220, Maps 223. Three app map
        # installs had no watch report; Installations now shows them as one row.
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        backed, unreported = str(uuid4()), str(uuid4())
        app = validate_compatibility_event(encode(compatibility_event(
            id=str(uuid4()), timestamp=hour_ago, operationId=backed, mapResultIndex=0)))
        self.assertTrue(self.db.insert_compatibility_event(app))

        def install(operation, index, **changes):
            body = {"schemaVersion": 1, "id": str(uuid4()), "operationId": operation, "timestamp": hour_ago,
                    "providerId": "freizeitkarte", "releaseLabel": "1.0.0-beta.18", "mapId": "freizeitkarte-deu", "region": "DEU",
                    "eventType": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED", "mapResultIndex": index, "appBuild": "40",
                    **changes}
            self.assertTrue(self.db.insert_map_event(validate_map_event(json.dumps(body).encode())))

        install(backed, 0)  # backed by the watch report: counted once, under its model
        install(backed, 1)  # same operation, no report for this map
        install(unreported, 0)  # no report at all
        install(unreported, 1, eventType="INSTALL_FAILED", outcome="FAILED")  # Maps needs a report to count a failure
        self.assertEqual(self.db.app_installs_without_model_report()["successful_install_count"], 2)

        body = dashboard_page(
            self.service.compatibility_statistics(), {"username": "test"}, "csrf",
            diagnostic_summary=self.service.compatibility_diagnostic_summary(),
            identity_devices=self.service.admin_devices()["devices"], web_rows=[],
            unreported_app=self.db.app_installs_without_model_report(), source="app",
        ).decode()
        tiles = {key: int(value) for key, value in re.findall(
            r"data-stat='(attempts|successful|failed)'[^>]*>(\d+)<", body)}
        summary = self.service.map_statistics({"period": "24h", "source": "app"})["summary"]
        self.assertEqual((tiles["successful"], tiles["failed"]), (summary["completedInstalls"], summary["failedInstalls"]))
        self.assertEqual(tiles["successful"], 3)
        self.assertIn("Watch not reported<span class='activity-source-app'", body)
        row = re.search(r"<tr class='evidence-model-row'[^>]*data-model='Watch not reported'[^>]*>", body).group(0)
        self.assertIn("data-attempts='2'", row)
        self.assertIn("data-diagnostics-url=''", row)
        # The Web view never shows it.
        web = dashboard_page(
            self.service.compatibility_statistics(), {"username": "test"}, "csrf",
            diagnostic_summary=self.service.compatibility_diagnostic_summary(), web_rows=[],
            unreported_app=self.db.app_installs_without_model_report(), source="web").decode()
        self.assertNotIn("Watch not reported", web)

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
        self.assertEqual(self.db.resolve_web_installer_identities(),
                         {"pending": 2, "resolved": 1, "rechecked": 0, "changed": 0})
        self.db.resolve_web_installer_identities()
        self.assertEqual(stats()[0], after)

    def test_model_page_installation_history_lists_counted_web_installs_with_the_web_icon(self):
        device_id = "garmin-epix-pro-gen-2-47"
        self.sql("""INSERT INTO map_package (id, provider_id, provider_region_id, canonical_region_id, name, region,
                        release, country, source_updated_at, map_type, geographic_region_id)
                    VALUES ('bbbike-north-america-us-washington-bbbike-latin1', 'bbbike', 'washington', 'US-WA',
                            'Washington', 'US-WA', '2026-10', 'US', '2026-10-01T00:00:00Z', 'bbbike-latin1', 'US-WA')""")
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = dict(stage="MAP_RESULT", operation="install", provider="bbbike", model="epix pro - 47mm",
                    packageId="bbbike-north-america-us-washington-bbbike-latin1", osFamily="Linux", occurredAt=hour_ago)
        for body in (dict(base, outcome="SUCCEEDED", writeStarted=True),
                     dict(base, outcome="FAILED", writeStarted=True, failureStage="WRITE", reason="WATCH_FULL"),
                     # Not counted: a failure before writing, a test record, an update.
                     dict(base, outcome="FAILED", writeStarted=False, failureStage="DOWNLOAD", reason="DOWNLOAD_STOPPED"),
                     dict(base, outcome="SUCCEEDED", writeStarted=True, isTest=True),
                     dict(base, outcome="SUCCEEDED", writeStarted=True, operation="update")):
            self.assertEqual(self.forward(event(**body)), 201)
        _, page = self.request("GET", f"/admin/devices/{device_id}", secret=None, admin=True)
        rows = page.split("<tbody id='diagnostic-rows'>", 1)[1].split("</tbody>", 1)[0].split("<tr ")[1:]
        self.assertEqual([row.split("data-diagnostic-result='", 1)[1].split("'", 1)[0] for row in rows],
                         ["succeeded", "failed"])
        for row in rows:
            self.assertIn("data-source='web'", row)
            self.assertIn("<span class='history-source-web'>", row)
            self.assertIn("admin-icon-source-web", row)
            self.assertIn("Washington – United States · BBBike", row)
        self.assertIn("Not enough space on the watch · Writing to the watch", rows[1])
        self.assertNotIn("Download stopped", page)

    def test_reported_epix_names_both_generations_so_only_the_usb_code_decides(self):
        # Production 2026-10-19: an epix (Gen 2) on the web installer reported
        # "epix" with USB 091e:4f67 and was counted on the original epix row.
        gen1, gen2 = "garmin-epix-gen-1", "garmin-epix-gen-2-47"
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = dict(stage="MAP_RESULT", operation="install", outcome="SUCCEEDED", writeStarted=True,
                    provider="maprando", packageId="maprando-hebei", model="epix", firmware="2718",
                    osFamily="macOS", usbVendorId=0x091E, usbProductId=0x4F67, occurredAt=hour_ago)
        coded = event(**base)
        self.assertEqual(self.forward(coded), 201)
        self.assertEqual(self.forward(event(**{k: v for k, v in base.items() if not k.startswith("usb")})), 201)

        def resolved():
            return {r["usb_product_id"]: (r["id"], r["resolution"]) for r in self.sql(
                "SELECT usb_product_id, canonical_device_model_id AS id, identity_resolution AS resolution "
                "FROM web_installer_event")}

        # The name keeps both generations open; the libmtp code (migration 084) names Gen 2 only.
        self.assertEqual(resolved(), {0x4F67: (gen2, "USB_LEARNED"), None: (None, "UNRESOLVED")})
        # A row counted on the original epix before the fix moves on the next pass.
        self.sql("UPDATE web_installer_event SET canonical_device_model_id = %s, identity_resolution = 'SINGLE_MATCH'",
                 (gen1,))
        self.assertEqual(self.db.resolve_web_installer_identities(),
                         {"pending": 0, "resolved": 0, "rechecked": 2, "changed": 2})
        self.assertEqual(resolved(), {0x4F67: (gen2, "USB_LEARNED"), None: (None, "UNRESOLVED")})
        # Every row is checked on each call, whatever the batch size: an
        # unchanged first batch never hides later rows.
        self.sql("UPDATE web_installer_event SET canonical_device_model_id = %s, identity_resolution = 'SINGLE_MATCH'",
                 (gen1,))
        self.assertEqual(self.db.resolve_web_installer_identities(limit=1),
                         {"pending": 0, "resolved": 0, "rechecked": 2, "changed": 2})
        self.assertEqual(self.db.resolve_web_installer_identities(limit=1),
                         {"pending": 1, "resolved": 0, "rechecked": 1, "changed": 0})
        self.assertEqual(resolved(), {0x4F67: (gen2, "USB_LEARNED"), None: (None, "UNRESOLVED")})
        # An app report of the same code confirmed as the original epix makes the
        # code name two models, so the web install waits for review.
        app = validate_compatibility_event(encode(compatibility_event(
            id=str(uuid4()), timestamp="2026-10-13T20:27:00Z", model="EPIX", family="epix", usbProductID=0x4F67)))
        self.assertTrue(self.db.insert_compatibility_event(app))
        self.sql("UPDATE compatibility_evidence_event SET canonical_device_model_id = %s, "
                 "identity_resolution_state = 'RESOLVED' WHERE event_id = %s", (gen1, app["id"]))
        self.db.resolve_web_installer_identities()
        self.assertEqual(resolved()[0x4F67], (None, "UNRESOLVED"))
        # Reassigned to Gen 2, the code names one model again.
        self.sql("UPDATE compatibility_evidence_event SET canonical_device_model_id = %s WHERE event_id = %s",
                 (gen2, app["id"]))
        self.db.resolve_web_installer_identities()
        self.assertEqual(resolved()[0x4F67], (gen2, "USB_LEARNED"))

    def test_a_usb_code_learned_from_a_confirmed_watch_resolves_web_installs_only_while_it_names_one_model(self):
        # Production 2026-10-13: "fenix 7x pro" names two catalog rows (Wi-Fi and
        # Solar no Wi-Fi), so the text alone never resolves it.
        wifi, no_wifi = "garmin-fenix-7x-pro", "garmin-fenix-7x-pro-solar-no-wifi"

        def confirmed_app_report(product, device_id, *, local_test=False):
            app = validate_compatibility_event(encode(compatibility_event(
                id=str(uuid4()), timestamp="2026-10-01T10:00:00Z", model="fēnix 7X Pro", family="fēnix",
                usbProductID=product)))
            self.assertTrue(self.db.insert_compatibility_event(app))
            self.sql("UPDATE compatibility_evidence_event SET canonical_device_model_id = %s, "
                     "identity_resolution_state = 'RESOLVED', is_local_test = %s WHERE event_id = %s",
                     (device_id, local_test, app["id"]))

        confirmed_app_report(0xAAB1, wifi)
        confirmed_app_report(0xAAB2, wifi, local_test=True)
        # libmtp's 091e:5117 is a catalog mapping of both fēnix 7 Pro editions.
        confirmed_app_report(0x5117, "garmin-fenix-7-pro")
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = dict(stage="MAP_RESULT", operation="install", outcome="SUCCEEDED", writeStarted=True, provider="maprando",
                    packageId="maprando-hebei", model="fenix 7x pro", firmware="2718", osFamily="macOS",
                    usbVendorId=0x091E, usbProductId=0xAAB1, occurredAt=hour_ago)
        learned = event(**base)
        for body in (learned,
                     event(**{**base, "usbProductId": 0xAAB2}),             # taught only by a local test report
                     event(**{k: v for k, v in base.items() if not k.startswith("usb")}),  # no code
                     event(**{**base, "model": "epix pro"}),               # the text names other models
                     event(**{**base, "model": "fenix 7 pro", "usbProductId": 0x5117})):
            self.assertEqual(self.forward(body), 201)

        def resolved():
            return {(r["model"], r["usb_product_id"]): (r["id"], r["resolution"]) for r in self.sql(
                "SELECT model, usb_product_id, canonical_device_model_id AS id, identity_resolution AS resolution "
                "FROM web_installer_event")}

        self.assertEqual(resolved(), {("fenix 7x pro", 0xAAB1): (wifi, "USB_LEARNED"),
                                      ("fenix 7x pro", 0xAAB2): (None, "UNRESOLVED"),
                                      ("fenix 7x pro", None): (None, "UNRESOLVED"),
                                      ("epix pro", 0xAAB1): (None, "UNRESOLVED"),
                                      ("fenix 7 pro", 0x5117): (None, "UNRESOLVED")})
        self.db.resolve_web_installer_identities()
        self.assertEqual(resolved()[("fenix 7x pro", 0xAAB1)], (wifi, "USB_LEARNED"))

        # A confirmed watch of the other edition reports the same code: it now
        # names two models, so the learned install loses its model.
        confirmed_app_report(0xAAB1, no_wifi)
        self.db.resolve_web_installer_identities()
        self.assertEqual(resolved()[("fenix 7x pro", 0xAAB1)], (None, "UNRESOLVED"))

        _, page = self.request("GET", "/admin/review/identity", secret=None, admin=True)
        card = page.split("<h2 id='identity-web-", 1)[0].rsplit("<section ", 1)[1] + page.split("<h2 id='identity-web-", 1)[1]
        self.assertIn("data-source='web'", card)
        learned_item = next(item for item in card.split("data-identity-review-item")[1:] if "USB 091e:aab1" in item)
        self.assertIn("2 possible models", learned_item)
        self.assertIn(f"data-identity-device-id='{wifi}'", learned_item)
        self.assertIn(f"data-identity-device-id='{no_wifi}'", learned_item)

    def post_identity(self, key, action, device_id="", return_to="/admin/review/identity"):
        body = urlencode({"csrf_token": self.csrf, "operation_key": key, "identity_action": action,
                          "canonical_device_model_id": device_id, "return_to": return_to})
        return self.request("POST", "/admin/diagnostics/identity", body.encode(), secret=None, admin=True,
                            content_type="application/x-www-form-urlencoded")

    def test_identity_review_assigns_a_web_install_like_an_app_result_and_unassign_reverses_it(self):
        wifi = "garmin-fenix-7x-pro"
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = dict(stage="MAP_RESULT", operation="install", outcome="SUCCEEDED", writeStarted=True, provider="maprando",
                    packageId="maprando-hebei", model="fenix 7x pro", osFamily="macOS", occurredAt=hour_ago)
        counted, test, before_write = event(**base), event(**base, isTest=True), event(
            **{**base, "outcome": "FAILED", "writeStarted": False, "failureStage": "DOWNLOAD", "reason": "DOWNLOAD_STOPPED"})
        for body in (counted, test, before_write):
            self.assertEqual(self.forward(body), 201)
        key = f"web:{counted['id']}"

        def stored():
            return self.sql("SELECT canonical_device_model_id AS id, identity_resolution AS resolution "
                            "FROM web_installer_event WHERE event_id = %s", (counted["id"],))[0]

        def audit():
            return [(r["action"], r["new_canonical_device_model_id"]) for r in self.sql(
                "SELECT action, new_canonical_device_model_id FROM web_installer_identity_audit ORDER BY id")]

        self.assertEqual(self.db.admin_review_summary()["identityPending"], 1)
        # The queue item: the same inline form as an app result, for the counted install only.
        _, page = self.request("GET", "/admin/review/identity", secret=None, admin=True)
        self.assertIn("<span data-identity-review-count>1 installation</span>", page)
        forms = re.findall(r"<form method='post' action='/admin/diagnostics/identity'.*?</form>", page, re.S)
        self.assertEqual(len(forms), 1)
        self.assertIn(f"name='operation_key' value='{key}'", forms[0])
        self.assertIn("name='identity_action' value='ASSIGN'", forms[0])
        self.assertIn("name='identity_action' value='MANUAL_ASSIGN'", forms[0])
        self.assertIn("Pick model", forms[0])

        # Records outside the counted population cannot be assigned.
        for other in (test, before_write):
            self.assertEqual(self.post_identity(f"web:{other['id']}", "ASSIGN", wifi)[0].status, 404)
        # A model the reported text contradicts needs the explicit manual action.
        response, payload = self.post_identity(key, "ASSIGN", "garmin-epix-pro-gen-2-47")
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(payload)["error"], "identity_conflict_manual_required")
        self.assertEqual(stored(), {"id": None, "resolution": "UNRESOLVED"})
        self.assertEqual(audit(), [])

        response, _ = self.post_identity(key, "ASSIGN", wifi)
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), f"/admin/devices/{wifi}?from=installations#installations")
        self.assertEqual(stored(), {"id": wifi, "resolution": "MANUAL"})
        self.assertEqual(self.post_identity(key, "ASSIGN", wifi)[0].status, 303)  # a repeat writes nothing
        self.assertEqual(audit(), [("ASSIGN", wifi)])
        self.db.resolve_web_installer_identities()
        self.assertEqual(stored(), {"id": wifi, "resolution": "MANUAL"})
        self.assertEqual(self.sql("SELECT count(*) AS n FROM web_installer_map_result WHERE canonical_device_model_id = %s",
                                  (wifi,))[0]["n"], 1)
        _, page = self.request("GET", "/admin/review/identity", secret=None, admin=True)
        self.assertIn("No installations wait for identity review.", page)
        self.assertEqual(self.db.admin_review_summary()["identityPending"], 0)

        # The model page lists it with Unassign, which puts it back in the queue.
        _, page = self.request("GET", f"/admin/devices/{wifi}", secret=None, admin=True)
        row = page.split("data-source='web'", 1)[1].split("</tr>", 1)[0]
        self.assertIn(f"name='operation_key' value='{key}'", row)
        self.assertIn("value='LEAVE_UNRESOLVED'>Unassign</button>", row)
        model_page = f"/admin/devices/{wifi}?from=installations#installations"
        response, _ = self.post_identity(key, "LEAVE_UNRESOLVED", return_to=model_page)
        self.assertEqual((response.status, response.getheader("Location")), (303, model_page))
        self.assertEqual(stored(), {"id": None, "resolution": "UNRESOLVED"})
        self.assertEqual(audit(), [("ASSIGN", wifi), ("LEAVE_UNRESOLVED", None)])
        self.db.resolve_web_installer_identities()
        self.assertEqual(stored(), {"id": None, "resolution": "UNRESOLVED"})
        _, page = self.request("GET", "/admin/review/identity", secret=None, admin=True)
        self.assertIn(f"name='operation_key' value='{key}'", page)

        response, _ = self.post_identity(key, "MANUAL_ASSIGN", "garmin-epix-pro-gen-2-47")
        self.assertEqual(response.status, 303)
        self.assertEqual(stored(), {"id": "garmin-epix-pro-gen-2-47", "resolution": "MANUAL"})
        self.assertEqual(audit()[-1], ("MANUAL_ASSIGN", "garmin-epix-pro-gen-2-47"))

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
        connect = page.split("data-group-card='web-installer-connect-groups'", 1)[1].split("data-group-panel='PREPARE'", 1)[0]
        for text in ("<th scope='col' class='column-number web-installer-col-visits-cell'>Visits</th>",
                     "<th scope='col' class='web-installer-col-models-cell'>Watch models</th>",
                     f"<td class='web-installer-col-models-cell'>{name}</td>", "admin-icon-browser-other"):
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

"""Identity review queue: one page that confirms pending identities in place."""

from __future__ import annotations

import re
import threading
import unittest
from html import unescape
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.admin import (
    _ATTENTION_ROWS,
    _identity_review_anchor,
    _statistics_row,
    dashboard_page,
    diagnostics_page,
    identity_review_page,
)
from terento_catalog.http_api import CatalogService, make_handler

COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"
USER = {"username": "operator"}
BATCH = "7a1b2c3d-0000-4000-8000-0000000000aa"
DEVICES = [
    {"id": "fenix-8-47-amoled", "device_id": "fenix-8-47-amoled", "model": "fēnix 8", "variant": "47 mm, AMOLED"},
    {"id": "fenix-8-51-amoled", "device_id": "fenix-8-51-amoled", "model": "fēnix 8", "variant": "51 mm, AMOLED"},
    {"id": "forerunner-965", "device_id": "forerunner-965", "model": "Forerunner 965", "variant": ""},
]


def _candidate(device_id, *missing):
    checks = [{"name": "model", "state": "MATCH"}] + [{"name": name, "state": "MISSING"} for name in missing]
    return {"deviceId": device_id, "model": "fēnix 8", "checks": checks, "conflict": False}


def _event(index, identity, *, operation=None, map_index=0, day=20, candidates=(), **extra):
    operation = operation or f"7a1b2c3d-0000-4000-8000-{index:012d}"
    return {
        "event_id": f"8b1b2c3d-0000-4000-8000-{index:010d}{map_index:02d}",
        "operation_id": operation, "map_result_index": map_index,
        "operation_key": f"result:{operation}:{map_index}",
        "compatibility_identity": identity, "model": identity, "variant": None,
        "canonical_device_model_id": None, "identity_resolution_state": "UNRESOLVED",
        "provider": "opentopomap", "region": "Lithuania", "phase_outcome": "SUCCEEDED",
        "automatic_finishing_result": "VERIFIED", "write_started": True, "diagnostic_status": "ACTIVE",
        "occurred_at": f"2026-09-{day:02d}T09:00:00Z",
        "current_identity_assessment": {"state": "UNRESOLVED", "candidates": list(candidates)},
        **extra,
    }


def _operations():
    two = (_candidate("fenix-8-47-amoled", "size"), _candidate("fenix-8-51-amoled", "size"))
    return [
        _event(1, "fēnix 8", day=22, candidates=two),
        _event(2, "fēnix 8", day=24, candidates=two, phase_outcome="FAILED", automatic_finishing_result=None),
        _event(3, "Forerunner 965", day=23, candidates=(_candidate("forerunner-965", "screen"),)),
        # One install operation (a batch) with two pending map results.
        _event(4, "Forerunner 965", operation=BATCH, day=21, region="Poland",
               candidates=(_candidate("forerunner-965"),)),
        _event(5, "Forerunner 965", operation=BATCH, map_index=1, day=21, region="Latvia",
               candidates=(_candidate("forerunner-965"),)),
        # Not pending: already resolved identity, and a provider download failure.
        _event(6, "fēnix 8", identity_resolution_state="RESOLVED"),
        _event(7, "fēnix 8", phase_outcome="FAILED", write_started=False, failure_stage="download"),
    ]


def _forms(body):
    return re.findall(r"<form method='post' action='/admin/diagnostics/identity'.*?</form>", body, re.S)


def _fields(form):
    return {name: unescape(value) for name, value in re.findall(
        r"<input type='hidden' name='([a-z_]+)'(?: id='[^']*')? value='([^']*)'", form)}


class IdentityReviewPageTests(unittest.TestCase):
    def render(self, operations=None):
        return identity_review_page(
            _operations() if operations is None else operations, USER, "csrf", identity_devices=DEVICES,
        ).decode()

    def test_lists_every_pending_operation_newest_first_grouped_by_identity(self):
        body = self.render()
        self.assertIn("<h1>Identity review</h1>", body)
        # Unit = install operation, as Needs attention counts it: the batch is one item.
        self.assertEqual(body.count("data-identity-review-item "), 4)
        self.assertIn("<span data-identity-review-count>4 installations</span>", body)
        groups = re.findall(r"<section class='admin-card identity-review-group' id='([^']+)'", body)
        self.assertEqual(groups, [_identity_review_anchor("fēnix 8"), _identity_review_anchor("Forerunner 965")])
        fenix = body.split(f"id='{groups[0]}'", 1)[1].split("</section>", 1)[0]
        self.assertIn("2 installations", fenix)
        self.assertLess(fenix.index("2026-09-24"), fenix.index("2026-09-22"))
        # Resolved and provider-download rows never enter the queue.
        self.assertNotIn("8b1b2c3d-0000-4000-8000-000000000600", body)
        self.assertNotIn("result:7a1b2c3d-0000-4000-8000-000000000007:0", body)
        self.assertIn("2 possible models", fenix)
        self.assertIn("One match · display not confirmed", body)

    def test_each_pending_result_has_the_dialog_identity_form_and_a_details_link(self):
        body = self.render()
        forms = _forms(body)
        # One form per pending result: the batch keeps two exact result keys.
        self.assertEqual(len(forms), 5)
        for form in forms:
            self.assertEqual(set(_fields(form)), {"csrf_token", "operation_key", "return_to", "canonical_device_model_id"})
            self.assertEqual(_fields(form)["return_to"], "/admin/review/identity")
            self.assertIn("name='identity_action' value='ASSIGN' data-identity-confirm>Confirm</button>", form)
            self.assertIn("name='identity_action' value='MANUAL_ASSIGN'", form)
            self.assertIn("admin-async-action' data-identity-form data-identity-inline>", form)
        keys = [_fields(form)["operation_key"] for form in forms]
        self.assertIn(f"result:{BATCH}:0", keys)
        self.assertIn(f"result:{BATCH}:1", keys)
        suggested = next(form for form in forms if _fields(form)["operation_key"].endswith("000000000003:0"))
        self.assertEqual(_fields(suggested)["canonical_device_model_id"], "forerunner-965")
        self.assertIn("<dt>Suggested model</dt>", suggested)
        self.assertIn(">Edit</button>", suggested)
        ambiguous = next(form for form in forms if _fields(form)["operation_key"].endswith("000000000002:0"))
        self.assertEqual(_fields(ambiguous)["canonical_device_model_id"], "")
        self.assertIn(">Pick model</button>", ambiguous)
        self.assertEqual(ambiguous.count("data-identity-device-id="), 2, "quick pick lists the candidates")
        self.assertIn("data-canonical-device-wrap hidden", ambiguous)
        self.assertIn("/admin/diagnostics?identity=f%C4%93nix+8&amp;identity_scope=unresolved#diagnostic-detail-", body)
        self.assertNotIn(">Inspect<", body)

    def test_empty_and_unavailable_states(self):
        body = self.render([])
        self.assertIn("No installations wait for identity review.", body)
        self.assertNotIn("<li class='identity-review-item'", body)
        body = identity_review_page(None, USER, "csrf").decode()
        self.assertIn("Could not load this section.", body)
        self.assertIn("href='/admin/review/identity'", body)


class IdentityReviewEntryPointTests(unittest.TestCase):
    def test_needs_attention_identity_row_opens_the_queue(self):
        row = next(row for row in _ATTENTION_ROWS if row[0] == "identityPending")
        self.assertEqual(row[2], "/admin/review/identity")

    def test_installations_badge_and_link_open_the_queue(self):
        row = {"model": "fēnix 8", "compatibility_identity": "fēnix 8", "attempted_install_count": 2}
        markup = _statistics_row(row, {"identity_pending": 2})
        self.assertIn(f"<a class='identity-pending-indicator' href='/admin/review/identity#{_identity_review_anchor('fēnix 8')}'", markup)
        # The model link keeps its own destination and no link is nested.
        self.assertIn("<a class='device-model-button' href='/admin/diagnostics?identity=", markup)
        self.assertNotIn("</span></a>", markup)
        body = dashboard_page([row, {**row, "model": "Forerunner 965", "compatibility_identity": "Forerunner 965"}],
                              USER, "csrf", diagnostic_summary={"identity:fēnix 8": {"identity_pending": 2}}).decode()
        self.assertIn("class='secondary-button identity-review-link' href='/admin/review/identity'>Review identities", body)
        body = dashboard_page([row, {**row, "model": "Forerunner 965"}], USER, "csrf", diagnostic_summary={}).decode()
        self.assertNotIn("Review identities", body)

    def test_reported_identity_page_matches_the_device_page(self):
        operations = [event for event in _operations() if event["compatibility_identity"] == "fēnix 8"]
        body = diagnostics_page(
            [{"model": "fēnix 8", "compatibility_identity": "fēnix 8", "attempted_install_count": 2,
              "successful_install_count": 1, "failed_install_count": 1, "calculated_status": "TESTING"}],
            USER, "csrf", identity="fēnix 8", operations=operations, identity_devices=DEVICES, unresolved_only=True,
        ).decode()
        self.assertIn("href='/admin/review/identity'>Review all pending identities", body)
        kpis = body.split("class='admin-card admin-kpi-panel diagnostic-model-metrics model-statistics'", 1)[1].split("</section>", 1)[0]
        self.assertNotIn("admin-scope-chip", kpis)
        self.assertIn(">Installs</h2>", kpis)
        self.assertIn("data-stat='failed'>1</strong>", kpis)
        self.assertIn("admin-pill", kpis)
        self.assertNotIn("<select", body.split("id='diagnostic-filters'", 1)[1].split("</form>", 1)[0])
        for value in ("all", "failed", "open", "identity-pending", "resolved", "with-issue", "succeeded"):
            self.assertIn(f"data-history-filter='{value}'", body)
        self.assertNotIn("records</p>", body)
        self.assertIn("class='diagnostic-list-table mobile-record-table'", body)
        self.assertIn("data-label='Review'", body)


class QueueDatabase(FakeProviderDatabase):
    def __init__(self, *, fail=False):
        super().__init__()
        self.fail = fail
        self.identity_calls: list[tuple[str, str]] = []
        self.resolutions: list[dict] = []

    def compatibility_diagnostic_population(self):
        if self.fail:
            raise RuntimeError("population unavailable")
        return [{**event, "operation_key": event["operation_key"]} for event in _operations()]

    def compatibility_identity_details(self, status, *, device_id="", identity=""):
        self.identity_calls.append((status, identity))
        identities = identity if isinstance(identity, list) else [identity]
        return [event for event in _operations()
                if event["diagnostic_status"] == status and event["compatibility_identity"] in identities]

    def admin_device_snapshot(self):
        return [{**device, "map_capable": True, "active": True} for device in DEVICES], None

    def resolve_compatibility_identity(self, operation_key, **kwargs):
        self.resolutions.append({"operation_key": operation_key, **kwargs})
        return 1


class IdentityReviewHttpTests(unittest.TestCase):
    def start(self, database):
        self.database = database
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CatalogService(database)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, headers=None, cookie=COOKIE):
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, path, body=body, headers={**({"Cookie": cookie} if cookie else {}), **(headers or {})})
        response = connection.getresponse()
        data = response.read().decode()
        connection.close()
        return response, data

    def test_route_requires_an_admin_session(self):
        self.start(QueueDatabase())
        response, _ = self.request("GET", "/admin/review/identity", cookie=None)
        self.assertIn(response.status, {302, 303})
        self.assertEqual(response.headers["Location"], "/admin/login")
        self.assertEqual(self.database.identity_calls, [])

    def test_route_lists_active_pending_identities_and_forms_post_unchanged_fields(self):
        self.start(QueueDatabase())
        response, body = self.request("GET", "/admin/review/identity")
        self.assertEqual(response.status, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        # One read for every pending identity, never one per identity (audit #13).
        self.assertEqual(self.database.identity_calls, [("ACTIVE", ["Forerunner 965", "fēnix 8"])])
        self.assertEqual(body.count("data-identity-review-item "), 4)
        form = next(form for form in _forms(body) if _fields(form)["operation_key"].endswith("000000000003:0"))
        fields = {**_fields(form), "identity_action": "ASSIGN"}
        response, _ = self.request("POST", "/admin/diagnostics/identity", urlencode(fields),
                                   {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.status, 303)
        self.assertEqual(self.database.resolutions[-1]["operation_key"], "result:7a1b2c3d-0000-4000-8000-000000000003:0")
        self.assertEqual(self.database.resolutions[-1]["canonical_device_model_id"], "forerunner-965")
        self.assertEqual(self.database.resolutions[-1]["action"], "ASSIGN")
        # The queue is an accepted return target for non-assignment identity actions.
        fields = {**fields, "identity_action": "LEAVE_UNRESOLVED"}
        response, _ = self.request("POST", "/admin/diagnostics/identity", urlencode(fields),
                                   {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.headers["Location"], "/admin/review/identity")

    def test_failed_read_renders_an_unavailable_card(self):
        self.start(QueueDatabase(fail=True))
        with self.assertLogs("terento_catalog.http_api", level="ERROR"):
            response, body = self.request("GET", "/admin/review/identity")
        self.assertEqual(response.status, 200)
        self.assertIn("<h1>Identity review</h1>", body)
        self.assertIn("Could not load this section.", body)


if __name__ == "__main__":
    unittest.main()

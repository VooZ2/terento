"""POST /internal/attention: the agent's writes (Resolve one diagnostic, Reopen its own)."""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api_test_fixtures import FakeProviderDatabase
from terento_catalog import http_api
from terento_catalog.db import Database
from test_update_review import EVENT as UPDATE_EVENT, ReviewDatabase
from terento_catalog.http_api import ATTENTION_ACTION_NOTE_MAX, ATTENTION_ACTION_RATE_LIMIT, CatalogService, make_handler

TOKEN = "attention-action-test-token-" + "x" * 32
DIAGNOSTIC = "result:2bd926cd-8929-4a10-bf46-9cae7321a8f1:0"
VALID = {
    "action": "resolve_installation_diagnostic",
    "diagnosticId": DIAGNOSTIC,
    "reason": "NOT_TERENTO_ISSUE",
    "note": "Watch was not visible after a long download (-2); nothing was written.",
}
REOPEN = {"action": "reopen_installation_diagnostic", "diagnosticId": DIAGNOSTIC, "note": "Closed too early; same error came back."}
UPDATE_DIAGNOSTIC = "754cfd1d-8913-4274-8e03-fab6a4c84fe8"
UPDATE_RESOLVE = {**VALID, "action": "resolve_update_diagnostic", "diagnosticId": UPDATE_DIAGNOSTIC}
UPDATE_REOPEN = {**REOPEN, "action": "reopen_update_diagnostic", "diagnosticId": UPDATE_DIAGNOSTIC}


class AttentionActionTests(unittest.TestCase):
    def setUp(self):
        self.service = CatalogService(FakeProviderDatabase(), admin_read_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest())
        self.calls = []

        def lifecycle(operation_key, **kwargs):
            self.calls.append((operation_key, kwargs))
            return 1

        def review(diagnostic_id, **kwargs):
            self.calls.append((diagnostic_id, kwargs))
            return True

        patcher = patch.object(self.service, "update_diagnostic_lifecycle", side_effect=lifecycle)
        self.lifecycle = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(self.service, "review_update_diagnostic", side_effect=review)
        self.review = patcher.start()
        self.addCleanup(patcher.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, document, *, token=TOKEN, path="/internal/attention", content_type="application/json"):
        headers = {"Content-Type": content_type}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body = document if isinstance(document, bytes) else json.dumps(document).encode()
        connection = HTTPConnection(*self.server.server_address)
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response, json.loads(payload) if payload else None

    def test_resolves_exactly_one_result_with_a_marked_note_and_no_admin_user(self):
        response, body = self.post(VALID)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertIn("noindex", response.getheader("X-Robots-Tag") or "")
        self.assertEqual(body, {"status": "resolved", "diagnosticId": DIAGNOSTIC})
        self.assertEqual(self.calls, [(DIAGNOSTIC, {
            "new_status": "RESOLVED", "admin_user_id": None, "resolution_reason": "NOT_TERENTO_ISSUE",
            "resolution_note": "Claude agent: " + VALID["note"], "reopen_only_note_prefix": None,
        })])

    def test_reopens_only_through_the_own_resolution_guard(self):
        response, body = self.post(REOPEN)
        self.assertEqual((response.status, body), (200, {"status": "reopened", "diagnosticId": DIAGNOSTIC}))
        self.assertEqual(self.calls, [(DIAGNOSTIC, {
            "new_status": "ACTIVE", "admin_user_id": None, "resolution_reason": None,
            "resolution_note": "Claude agent: " + REOPEN["note"], "reopen_only_note_prefix": "Claude agent: ",
        })])

    def test_resolves_and_reopens_one_update_diagnostic(self):
        response, body = self.post(UPDATE_RESOLVE)
        self.assertEqual((response.status, body), (200, {"status": "resolved", "diagnosticId": UPDATE_DIAGNOSTIC}))
        response, body = self.post(UPDATE_REOPEN)
        self.assertEqual((response.status, body), (200, {"status": "reopened", "diagnosticId": UPDATE_DIAGNOSTIC}))
        self.assertEqual(self.calls, [
            (UPDATE_DIAGNOSTIC, {"action": "resolve", "admin_user_id": None, "resolution_reason": "NOT_TERENTO_ISSUE",
                                 "resolution_note": "Claude agent: " + VALID["note"], "reopen_only_note_prefix": None}),
            (UPDATE_DIAGNOSTIC, {"action": "reopen", "admin_user_id": None, "resolution_reason": None,
                                 "resolution_note": "Claude agent: " + REOPEN["note"], "reopen_only_note_prefix": "Claude agent: "}),
        ])

    def test_reopen_of_an_owner_resolution_is_a_conflict(self):
        self.lifecycle.side_effect = PermissionError("not_agent_resolution")
        self.review.side_effect = PermissionError("not_agent_resolution")
        for document in (REOPEN, UPDATE_REOPEN):
            response, body = self.post(document)
            self.assertEqual((response.status, body), (409, {"error": "not_agent_resolution"}))

    def test_token_is_required(self):
        for token in (None, "wrong-token-" + "y" * 32):
            response, body = self.post(VALID, token=token)
            self.assertEqual(response.status, 401)
            self.assertEqual(body, {"error": "unauthorized"})
        self.assertEqual(self.calls, [])

    def test_only_the_closed_resolve_shape_is_accepted(self):
        invalid = [
            {**VALID, "action": "reopen_installation_diagnostic"},  # Reopen takes no reason
            {**VALID, "action": "delete_installation_diagnostic"},
            {**VALID, "action": "link_installation_issue"},
            {**REOPEN, "note": ""},
            {key: value for key, value in REOPEN.items() if key != "note"},
            {**UPDATE_RESOLVE, "diagnosticId": DIAGNOSTIC},  # installation key on the update action
            {**UPDATE_RESOLVE, "diagnosticId": UPDATE_DIAGNOSTIC.upper()},
            {**UPDATE_RESOLVE, "diagnosticId": "{" + UPDATE_DIAGNOSTIC + "}"},
            {**UPDATE_RESOLVE, "reason": "OTHER"},
            {key: value for key, value in UPDATE_RESOLVE.items() if key != "reason"},
            {**UPDATE_REOPEN, "reason": "FIXED"},
            {**UPDATE_REOPEN, "diagnosticId": DIAGNOSTIC},
            {**VALID, "reason": "IDENTITY_CORRECTED"},
            {**VALID, "reason": "OTHER"},
            {**VALID, "reason": "not_terento_issue"},
            {**VALID, "reason": []},
            {**VALID, "reason": {}},
            {**VALID, "action": []},
            {**VALID, "diagnosticId": "2bd926cd-8929-4a10-bf46-9cae7321a8f1"},  # whole operation
            {**VALID, "diagnosticId": "web:2bd926cd-8929-4a10-bf46-9cae7321a8f1"},
            {**VALID, "diagnosticId": "legacy:2bd926cd-8929-4a10-bf46-9cae7321a8f1"},
            {**VALID, "diagnosticId": DIAGNOSTIC.upper()},
            {**VALID, "diagnosticId": DIAGNOSTIC + "0"},
            {**VALID, "diagnosticId": "result:2bd926cd-8929-4a10-bf46-9cae7321a8f1:01"},
            {**VALID, "diagnosticId": 1},
            {**VALID, "note": "   "},
            {**VALID, "note": "x" * (ATTENTION_ACTION_NOTE_MAX + 1)},
            {**VALID, "note": None},
            {**VALID, "linkedGithubIssue": "#1"},
            {key: value for key, value in VALID.items() if key != "note"},
        ]
        for document in invalid:
            with patch.object(http_api, "ATTENTION_ACTION_RATE_LIMIT", 1000):
                response, body = self.post(document)
            self.assertEqual(response.status, 400, document)
            self.assertEqual(body, {"error": "invalid_action"})
        with patch.object(http_api, "ATTENTION_ACTION_RATE_LIMIT", 1000):
            response, _ = self.post(VALID, content_type="application/x-www-form-urlencoded")
            self.assertEqual(response.status, 415)
            response, body = self.post(VALID, path="/internal/attention?page=%2Fadmin")
        self.assertEqual((response.status, body), (400, {"error": "invalid_action"}))
        self.assertEqual(self.calls, [])

    def test_unknown_diagnostic_is_not_found(self):
        self.lifecycle.side_effect = lambda *args, **kwargs: 0
        self.review.side_effect = lambda *args, **kwargs: False
        for document in (VALID, REOPEN, UPDATE_RESOLVE, UPDATE_REOPEN):
            response, body = self.post(document)
            self.assertEqual((response.status, body), (404, {"error": "diagnostic_not_found"}))

    def test_storage_failure_is_unavailable(self):
        self.lifecycle.side_effect = RuntimeError("db down")
        with self.assertLogs("terento_catalog.http_api", "ERROR"):
            response, body = self.post(VALID)
        self.assertEqual((response.status, body), (503, {"error": "action_unavailable"}))

    def test_actions_have_their_own_rate_limit(self):
        for _ in range(ATTENTION_ACTION_RATE_LIMIT):
            self.post(VALID, token=None)
        response, body = self.post(VALID)
        self.assertEqual((response.status, body), (429, {"error": "rate_limited"}))
        self.assertEqual(self.calls, [])


class LifecycleRows(Database):
    """Installation lifecycle rows behind ``update_diagnostic_lifecycle``."""

    def __init__(self, rows):
        super().__init__("unused")
        self.rows, self.writes = rows, []

    @contextmanager
    def connection(self):
        database = self

        class Connection:
            def execute(self, query, parameters=None):
                if query.lstrip().startswith(("UPDATE", "INSERT")):
                    database.writes.append(query)

                class Result:
                    def fetchall(self):
                        return [dict(row) for row in database.rows] if "FOR UPDATE" in query else []

                return Result()

        yield Connection()


class AgentReopenGuardTests(unittest.TestCase):
    PREFIX = "Claude agent: "

    def test_installation_reopen_undoes_only_the_agents_own_resolution(self):
        agent = {"event_id": "e1", "diagnostic_status": "RESOLVED", "resolved_by": None, "resolution_note": "Claude agent: -2"}
        database = LifecycleRows([agent])
        self.assertEqual(database.update_diagnostic_lifecycle(
            DIAGNOSTIC, new_status="ACTIVE", admin_user_id=None, resolution_note="Claude agent: back",
            reopen_only_note_prefix=self.PREFIX), 1)
        self.assertTrue(any("SET diagnostic_status = 'ACTIVE'" in query for query in database.writes))
        for other in ({**agent, "resolved_by": 1}, {**agent, "resolution_note": "Owner: fixed"}, {**agent, "resolution_note": None}):
            database = LifecycleRows([other])
            with self.assertRaises(PermissionError):
                database.update_diagnostic_lifecycle(
                    DIAGNOSTIC, new_status="ACTIVE", admin_user_id=None, resolution_note="Claude agent: back",
                    reopen_only_note_prefix=self.PREFIX)
            self.assertEqual(database.writes, [])
        # Admin Reopen has no guard.
        database = LifecycleRows([{**agent, "resolved_by": 1}])
        self.assertEqual(database.update_diagnostic_lifecycle(DIAGNOSTIC, new_status="ACTIVE", admin_user_id=7), 1)

    def test_update_reopen_undoes_only_the_agents_own_resolution(self):
        database = ReviewDatabase()
        self.assertTrue(database.review_update_diagnostic(
            UPDATE_EVENT, action="resolve", admin_user_id=None, resolution_reason="NOT_TERENTO_ISSUE",
            resolution_note="Claude agent: old beta"))
        self.assertIsNone(database.row["resolved_by"])
        self.assertTrue(database.review_update_diagnostic(
            UPDATE_EVENT, action="reopen", admin_user_id=None, resolution_note="Claude agent: came back",
            reopen_only_note_prefix=self.PREFIX))
        self.assertEqual(database.row["diagnostic_status"], "ACTIVE")
        audit = [params for query, params in database.calls if "INSERT INTO admin_audit_log" in query][-1]
        self.assertEqual(json.loads(audit[-1])["note"], "Claude agent: came back")
        for resolved_by, note in ((7, "Claude agent: x"), (None, "Owner closed")):
            database.row.update(diagnostic_status="RESOLVED", resolved_by=resolved_by, resolution_note=note)
            database.calls.clear()
            with self.assertRaises(PermissionError):
                database.review_update_diagnostic(
                    UPDATE_EVENT, action="reopen", admin_user_id=None, resolution_note="Claude agent: x",
                    reopen_only_note_prefix=self.PREFIX)
            self.assertFalse(any(query.lstrip().startswith(("UPDATE", "INSERT")) for query, _ in database.calls))


class AgentResolutionLabelTests(unittest.TestCase):
    def render(self, **result):
        from terento_catalog.admin import _diagnostic_detail_dialog
        return _diagnostic_detail_dialog("Unknown", "test", [{
            "phase_outcome": "FAILED", "resolution_reason": "NOT_TERENTO_ISSUE", **result,
        }], resolved=True, csrf_token="test", identity_devices=[])

    def test_admin_names_the_agent_only_for_its_own_marked_resolution(self):
        self.assertIn("· by Claude agent", self.render(resolved_by=None, resolution_note="Claude agent: watch -2"))
        self.assertIn("· by owner", self.render(resolved_by=1, resolved_by_username="owner",
                                                resolution_note="Claude agent: watch -2"))
        self.assertNotIn("Claude agent", self.render(resolved_by=1, resolution_note="Claude agent: x"))
        self.assertNotIn("by Claude agent", self.render(resolved_by=None, resolution_note="GitHub issue closed"))


if __name__ == "__main__":
    unittest.main()

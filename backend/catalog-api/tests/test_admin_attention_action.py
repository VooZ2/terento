"""POST /internal/attention: the agent's one write, Resolve of one installation diagnostic."""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api_test_fixtures import FakeProviderDatabase
from terento_catalog import http_api
from terento_catalog.http_api import ATTENTION_ACTION_NOTE_MAX, ATTENTION_ACTION_RATE_LIMIT, CatalogService, make_handler

TOKEN = "attention-action-test-token-" + "x" * 32
DIAGNOSTIC = "result:2bd926cd-8929-4a10-bf46-9cae7321a8f1:0"
VALID = {
    "action": "resolve_installation_diagnostic",
    "diagnosticId": DIAGNOSTIC,
    "reason": "NOT_TERENTO_ISSUE",
    "note": "Watch was not visible after a long download (-2); nothing was written.",
}


class AttentionActionTests(unittest.TestCase):
    def setUp(self):
        self.service = CatalogService(FakeProviderDatabase(), admin_read_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest())
        self.calls = []

        def lifecycle(operation_key, **kwargs):
            self.calls.append((operation_key, kwargs))
            return 1

        patcher = patch.object(self.service, "update_diagnostic_lifecycle", side_effect=lifecycle)
        self.lifecycle = patcher.start()
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
            "resolution_note": "Claude agent: " + VALID["note"],
        })])

    def test_token_is_required(self):
        for token in (None, "wrong-token-" + "y" * 32):
            response, body = self.post(VALID, token=token)
            self.assertEqual(response.status, 401)
            self.assertEqual(body, {"error": "unauthorized"})
        self.assertEqual(self.calls, [])

    def test_only_the_closed_resolve_shape_is_accepted(self):
        invalid = [
            {**VALID, "action": "reopen_installation_diagnostic"},
            {**VALID, "action": "resolve_update_diagnostic"},
            {**VALID, "reason": "IDENTITY_CORRECTED"},
            {**VALID, "reason": "OTHER"},
            {**VALID, "reason": "not_terento_issue"},
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
        response, body = self.post(VALID)
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


if __name__ == "__main__":
    unittest.main()

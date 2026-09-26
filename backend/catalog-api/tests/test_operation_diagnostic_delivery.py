"""Native payload → real HTTP intake/identity assessment/INSERT → admin renderers.

SQLite executes the production INSERT with placeholder/cast translation only.
This is not a PostgreSQL integration or a production-data repair.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import unittest
from urllib.parse import urlencode
from types import SimpleNamespace
from unittest.mock import patch

from terento_catalog.admin import (
    _github_issue_report, _failure_context_summary, _diagnostic_technical_details,
    _admin_device_payload, _diagnostic_summary_by_identity, diagnostics_page, device_detail_page,
    hash_password, overview_page, token_hash,
)
from terento_catalog.db import Database
from terento_catalog.http_api import CatalogService, make_handler
from test_compatibility_evidence import FakeEvidenceDatabase

DEVICE = dict(id='test-fenix8-47', model='fēnix 8', canonical_model='fēnix 8',
              case_size_mm=47, screen_technology='AMOLED', solar=False, inreach=False,
              asset_url='https://api.terento.app/assets/devices/synthetic-watch.png', asset_status='AVAILABLE', map_capable=True)
MAPPINGS = [dict(kind=kind, value=value, device_model_id=DEVICE['id'], status='APPROVED',
                 source_url='https://example.org/test-evidence', source_version='fixture')
            for kind, value in [('USB', '091e:51b8'), ('XML_PART_NUMBER', '006-B4536-00')]]


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class IntakeDatabase(FakeEvidenceDatabase, Database):
    def __init__(self):
        FakeEvidenceDatabase.__init__(self)
        self.sqlite = sqlite3.connect(':memory:', check_same_thread=False)
        self.sqlite.row_factory = sqlite3.Row
        # Independent schema: assertions below verify the production parameter mapping.
        columns = '''event_id TEXT PRIMARY KEY, occurred_at TEXT, model TEXT, compatibility_identity TEXT,
            variant TEXT, case_size_mm INTEGER, display_type TEXT, canonical_device_model_id TEXT,
            identity_resolution_state TEXT, family TEXT, firmware_version TEXT, usb_vendor_id INTEGER,
            usb_product_id INTEGER, transport TEXT, provider TEXT, region TEXT, map_release TEXT,
            terento_version TEXT, macos_version TEXT, phase_outcome TEXT, automatic_finishing_result TEXT,
            reconnect_verified BOOLEAN, map_visible_after_reconnect BOOLEAN, error_category TEXT,
            deletion_token_hash TEXT, operation_id TEXT, map_result_index INTEGER, selected_map_count INTEGER,
            app_build TEXT, release_label TEXT, failure_stage TEXT, failure_code TEXT, native_failure_code TEXT,
            write_started BOOLEAN, remote_object_created BOOLEAN, cleanup_attempted BOOLEAN,
            cleanup_succeeded BOOLEAN, transfer_progress_bucket TEXT, raw_mtp_model TEXT,
            identity_resolution_code TEXT, is_local_test BOOLEAN, garmin_model_description TEXT,
            garmin_model_part_number TEXT, identity_assessment TEXT,
            optional_component_selected BOOLEAN, optional_component_outcome TEXT,
            optional_component_failure_stage TEXT, optional_component_failure_code TEXT,
            optional_component_native_failure_code TEXT,
            failure_context TEXT, original_failure_context TEXT,
            statistics_exclusion_code TEXT, statistics_exclusion_reason TEXT,
            security_issue_code TEXT'''
        self.sqlite.execute('CREATE TABLE compatibility_evidence_event (' + columns + ')')
        self.mappings = deepcopy(MAPPINGS)
        self.identity_scope_calls = []

    def insert_compatibility_event(self, event):
        return Database.insert_compatibility_event(self, event)

    def resolve_compatibility_identity(
        self, operation_key, *, action, canonical_device_model_id,
        admin_user_id=None, reason=None, note=None,
    ):
        """Exercise the HTTP-to-storage scope with the real result key shape."""
        self.identity_scope_calls.append({
            "operation_key": operation_key, "action": action,
            "canonical_device_model_id": canonical_device_model_id,
            "reason": reason, "note": note,
        })
        match = re.fullmatch(r"result:([0-9a-fA-F-]{36}):(0|[1-9][0-9]*)", operation_key)
        if match:
            rows = self.sqlite.execute(
                'SELECT event_id FROM compatibility_evidence_event WHERE operation_id = ? AND map_result_index = ?',
                (match.group(1), int(match.group(2))),
            ).fetchall()
        else:
            rows = self.sqlite.execute(
                'SELECT event_id FROM compatibility_evidence_event WHERE operation_id = ?',
                (operation_key,),
            ).fetchall()
        if not rows:
            return 0
        self.sqlite.execute(
            'UPDATE compatibility_evidence_event SET canonical_device_model_id = ?, identity_resolution_state = ? WHERE event_id IN ('
            + ','.join('?' for _ in rows) + ')',
            [canonical_device_model_id, 'RESOLVED', *(row[0] for row in rows)],
        )
        self.sqlite.commit()
        return len(rows)

    @contextmanager
    def connection(self):
        database = self
        class Connection:
            def execute(self, sql, parameters=None):
                if sql == 'SELECT * FROM device_model': return Result([deepcopy(DEVICE)])
                if sql == 'SELECT * FROM device_identity_mapping': return Result(database.mappings)
                sql = re.sub(r'%\((\w+)\)s', r':\1', sql).replace('::jsonb', '')
                values = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in parameters.items()}
                return Result([dict(r) for r in database.sqlite.execute(sql, values).fetchall()])
        yield Connection()

    def rows(self):
        rows = [dict(r) for r in self.sqlite.execute('SELECT * FROM compatibility_evidence_event')]
        for row in rows:
            operation_key = (
                f"result:{row['operation_id']}:{row['map_result_index']}"
                if row['operation_id'] and row['map_result_index'] is not None
                else row['operation_id'] or f"legacy:{row['event_id']}"
            )
            row.update(operation_key=operation_key, diagnostic_status='ACTIVE',
                       identity_assessment=json.loads(row['identity_assessment']))
            for key in ('failure_context', 'original_failure_context'):
                row[key] = json.loads(row[key]) if row[key] is not None else None
        return rows


class OperationDiagnosticDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.db = IntakeDatabase()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(CatalogService(self.db)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.db.sqlite.close()

    def send(self, payload):
        connection = HTTPConnection(*self.server.server_address)
        connection.request('POST', '/compatibility/events', json.dumps(payload), {'Content-Type': 'application/json'})
        response = connection.getresponse(); body = response.read(); connection.close()
        return response.status, body

    def authenticated_identity_headers(self):
        session = 'diagnostic-test-session'
        csrf = 'diagnostic-test-csrf'
        self.db.users = [{
            'id': 1, 'username': 'operator', 'password_hash': hash_password('test-password-123'),
        }]
        self.db.create_admin_session(
            1, token_hash(session), token_hash(csrf), datetime.now(timezone.utc),
        )
        return {'Cookie': f'terento_admin_session={session}; terento_admin_csrf={csrf}', 'csrf_token': csrf}

    def fixture(self):
        dynamic = os.environ.get('TERENTO_DIAGNOSTIC_FIXTURE_OUTPUT')
        if dynamic:
            values = json.loads(Path(dynamic).read_text())
            return next(v for v in values if v.get('failureCode') == 'INSTALL_FAILED_WRITE')
        return json.loads((Path(__file__).resolve().parents[3] / 'contracts/fixtures/compatibility-event.valid-failed-operation.json').read_text())

    def test_structured_context_http_storage_duplicate_and_rejection(self):
        path = Path(__file__).resolve().parents[3] / 'contracts/fixtures/compatibility-event.valid-context-contours-cleanup.json'
        payload = json.loads(path.read_text())
        self.assertEqual(self.send(payload)[0], 201)
        row = self.db.rows()[0]
        self.assertEqual(row['failure_context'], payload['failureContext'])
        self.assertEqual(row['original_failure_context'], payload['originalFailureContext'])
        _, report = _github_issue_report('Test watch', [row])
        self.assertIn('Failure stage: cleanup', report)
        self.assertIn(r'Original failure boundary: postwrite\_protection', report)
        self.assertIn('Failure component: contours', report)
        self.assertIn('cleanup', _failure_context_summary([row]))
        changed = deepcopy(payload)
        changed['failureContext']['devicePresence'] = 'absent'
        self.assertEqual(self.send(changed)[0], 200)
        self.assertEqual(self.db.rows()[0]['failure_context'], payload['failureContext'])
        rejected = deepcopy(payload)
        rejected['failureContext']['rawPath'] = '/Users/private/secret.img'
        status, body = self.send(rejected)
        self.assertEqual(status, 400)
        self.assertNotIn(b'secret.img', body)
        self.assertEqual(len(self.db.rows()), 1)

    def test_build32_http_null_and_omission_store_sql_null_and_render_equally(self):
        path = Path(__file__).resolve().parents[3] / 'contracts/fixtures/compatibility-event.valid-build32-without-context.json'
        base = json.loads(path.read_text())
        rendered = []
        for index, fields in enumerate(({}, {'failureContext': None}, {'originalFailureContext': None}, {'failureContext': None, 'originalFailureContext': None})):
            payload = {**base, **fields, 'id': f'aabbccdd-1111-4111-8111-{index:012d}'}
            self.assertEqual(self.send(payload)[0], 201)
            row = self.db.rows()[-1]
            self.assertIsNone(row['failure_context'])
            self.assertIsNone(row['original_failure_context'])
            raw = self.db.sqlite.execute(
                'SELECT failure_context IS NULL, original_failure_context IS NULL FROM compatibility_evidence_event WHERE event_id = ?',
                (payload['id'],),
            ).fetchone()
            self.assertEqual(tuple(raw), (1, 1))
            replay = {**payload, 'failureContext': None, 'originalFailureContext': None}
            self.assertEqual(self.send(replay)[0], 200)
            row['event_id'] = base['id']  # Compare rendering without unrelated unique test IDs.
            rendered.append((_failure_context_summary([row]), _diagnostic_technical_details(row, 1), _github_issue_report('Test watch', [row])))
        self.assertTrue(all(value == rendered[0] for value in rendered))
        self.assertIn('Failure boundary: unavailable', rendered[0][2][1])
        self.assertEqual(len(self.db.rows()), 4)

    def test_every_native_failure_code_is_accepted_by_schema_and_api(self):
        from jsonschema import Draft202012Validator
        from terento_catalog.compatibility_evidence import validate_event
        root = Path(__file__).resolve().parents[3]
        source = (root / 'app/TerentoCore/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift').read_text()
        enum = source.split('enum InstallationFailure:', 1)[1].split('\n}', 1)[0]
        codes = set(re.findall(r'case \w+ = "([A-Z_]+)"', enum))
        self.assertGreaterEqual(len(codes), 22)
        schema = Draft202012Validator(json.loads((root / 'contracts/compatibility-event.schema.json').read_text()))
        for code in codes | {'INSTALL_FAILED_UNKNOWN'}:
            with self.subTest(code=code):
                payload = self.fixture()
                payload['failureCode'] = code
                schema.validate(payload)
                validate_event(json.dumps(payload).encode())

    def test_all_available_native_payloads_pass_the_real_api_validator(self):
        from jsonschema import Draft202012Validator
        from terento_catalog.compatibility_evidence import validate_event
        root = Path(__file__).resolve().parents[3]
        schema = Draft202012Validator(json.loads((root / 'contracts/compatibility-event.schema.json').read_text()))
        path = os.environ.get('TERENTO_DIAGNOSTIC_FIXTURE_OUTPUT')
        values = json.loads(Path(path).read_text()) if path else [
            self.fixture(),
            *[json.loads((root / f'contracts/fixtures/compatibility-event.valid-context-{name}.json').read_text())
              for name in ('preflight', 'cleanup', 'contours-cleanup')],
        ]
        require_context = os.environ.get('TERENTO_DIAGNOSTIC_REQUIRE_FAILURE_CONTEXT') == '1'
        if require_context:
            self.assertTrue(path, 'Current encoder coverage requires a fresh Swift fixture path')
            # A fresh Swift run must supply the new producer paths. Never let
            # the committed fallback silently substitute for missing emissions.
            contexts = [value for value in values if value.get('failureContext')]
            self.assertTrue(any(
                value['failureContext']['boundary'] in ('initial_snapshot', 'initial_inventory', 'prewrite_inventory')
                and value.get('failureStage') == 'preflight'
                and value.get('failureCode') == 'INSTALL_FAILED_PREFLIGHT_MTP_READ'
                and value.get('writeStarted') is False
                and value.get('errorCategory') == 'transport'
                for value in contexts
            ), 'Fresh Swift preflight read context missing')
            self.assertTrue(any(
                value['failureContext'].get('protection')
                and value['failureContext']['boundary'] in ('prewrite_protection', 'postwrite_protection', 'target_validation')
                for value in contexts
            ), 'Fresh Swift protection context missing')
            self.assertTrue(any(
                value.get('phaseOutcome') == 'SUCCEEDED'
                and value['failureContext'].get('componentKind') == 'contours'
                and value['failureContext']['boundary'] == 'cleanup'
                and value.get('optionalComponentSelected') is True
                and value.get('optionalComponentOutcome') == 'FAILED'
                and value.get('optionalComponentFailureStage') == 'cleanup'
                and (value.get('originalFailureContext') or {}).get('protection')
                for value in contexts
            ), 'Fresh Swift successful-main/failed-contours cleanup provenance missing')
        if not path:
            # Committed examples intentionally reuse an example UUID. Give only
            # these fallback copies distinct IDs so each shape reaches INSERT.
            for index, payload in enumerate(values):
                payload['id'] = f'aabbccdd-1111-4111-8111-{index:012d}'
        stored = {}
        source_payloads = {}
        # Each fixture/replay pair represents a separate delivery window. Patch
        # only the HTTP module's clock, not process/thread timeout clocks or the
        # production limiter. Dedicated intake tests cover rate limiting.
        delivery_time = [1000.0]
        clock = patch('terento_catalog.http_api.time', SimpleNamespace(monotonic=lambda: delivery_time[0]))
        clock.start()
        self.addCleanup(clock.stop)
        for payload in values:
            delivery_time[0] += 61
            with self.subTest(event=payload['id'], context=payload.get('failureContext')):
                schema.validate(payload)
                validated = validate_event(json.dumps(payload).encode())
                self.assertEqual(str(validated['operationId']).lower(), payload['operationId'].lower())
                # Send the actual encoder output unchanged; requests and INSERTs
                # stay entirely on loopback and the disposable in-memory DB.
                status, body = self.send(payload)
                fresh = payload['id'] not in stored
                self.assertEqual(status, 201 if fresh else 200)
                self.assertEqual(json.loads(body)['status'], 'stored' if fresh else 'duplicate')
                row = next(row for row in self.db.rows() if row['event_id'] == payload['id'])
                if not fresh:
                    self.assertEqual(payload, source_payloads[payload['id']], 'Fresh fixture reused an event ID for different observations')
                    self.assertEqual(row, stored[payload['id']])
                    continue
                stored[payload['id']] = deepcopy(row)
                source_payloads[payload['id']] = deepcopy(payload)
                for wire, column in (
                    ('failureContext', 'failure_context'), ('originalFailureContext', 'original_failure_context'),
                    ('failureStage', 'failure_stage'), ('failureCode', 'failure_code'),
                    ('optionalComponentFailureStage', 'optional_component_failure_stage'),
                    ('optionalComponentOutcome', 'optional_component_outcome'),
                ):
                    self.assertEqual(row[column], payload.get(wire))
                self.assertEqual(row['map_result_index'], payload['mapResultIndex'])
                self.assertEqual(row['phase_outcome'], payload['phaseOutcome'])
                _, report = _github_issue_report('Test watch', [row])
                summary = _failure_context_summary([row])
                context = payload.get('failureContext') or {}
                if context:
                    self.assertIn('Failure boundary: ' + context['boundary'].replace('_', r'\_'), report)
                    self.assertIn('Failure classification source: ' + context['classificationSource'], report)
                    self.assertIn('Failure device presence: ' + context['devicePresence'], report)
                    self.assertIn(context['boundary'], summary)
                    stage = payload.get('optionalComponentFailureStage') if context.get('componentKind') == 'contours' else payload.get('failureStage')
                    self.assertIn('Failure stage: ' + (stage or 'unavailable'), report)
                    if context.get('protection'):
                        self.assertIn('Failure protection reason: ' + context['protection']['protectionReason'], report)
                else:
                    self.assertIn('Failure boundary: unavailable', report)
                original = payload.get('originalFailureContext')
                if original:
                    self.assertIn('Original failure boundary: ' + original['boundary'].replace('_', r'\_'), report)
                    if original.get('protection'):
                        self.assertIn('Original failure protection reason: ' + original['protection']['protectionReason'], report)
                else:
                    self.assertIn('Original failure context: unavailable', report)
                status, body = self.send(payload)
                self.assertEqual((status, json.loads(body)['status']), (200, 'duplicate'))
                self.assertEqual(next(row for row in self.db.rows() if row['event_id'] == payload['id']), stored[payload['id']])
        self.assertEqual(len(self.db.rows()), len(stored))

    def test_native_failure_reaches_model_diagnostic_actions_and_review_queue(self):
        payload = self.fixture()
        # All requests stay on loopback/in-memory DB. Use release labels only to
        # exercise ordinary admin filtering, never send synthetic public evidence.
        payload.update(releaseLabel='1.0.0-beta.12', appBuild='30', terentoVersion='1.0.0-beta.12')
        self.assertEqual(self.send(payload)[0], 201)
        self.assertEqual(self.send(payload)[0], 200)
        rows = self.db.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['phase_outcome'], 'FAILED')
        self.assertEqual(row['operation_id'].lower(), payload['operationId'].lower())
        self.assertEqual(row['canonical_device_model_id'], DEVICE['id'])
        self.assertEqual(row['garmin_model_part_number'], payload['garminModelPartNumber'])
        self.assertEqual(row['failure_code'], 'INSTALL_FAILED_WRITE')
        summary = next(iter(_diagnostic_summary_by_identity(rows).values()))
        self.assertEqual((summary['attempts'], summary['failed']), (1, 1))
        user = {'username': 'test-operator'}
        html = diagnostics_page([], user, 'test-csrf', identity=row['compatibility_identity'],
            canonical_device_model_id=DEVICE['id'], operations=rows, identity_devices=[DEVICE]).decode()
        self.assertIn('diagnostic-detail-', html)
        self.assertIn('/admin/diagnostics/identity', html)
        self.assertIn('data-github-create', html)
        self.assertTrue('INSTALL_FAILED_WRITE' in html)
        device = _admin_device_payload([dict(DEVICE, device_id=DEVICE['id'], attempted_install_count=summary['attempts'], failed_install_count=summary['failed'])], None)['devices'][0]
        detail = device_detail_page(device, user, 'test-csrf', operations=rows, identity_devices=[DEVICE]).decode()
        self.assertTrue(DEVICE['asset_url'] in detail, 'exact-model image missing')
        self.assertTrue('INSTALL_FAILED_WRITE' in detail)
        self.assertIn('data-github-create', detail)
        attention = dict(row, has_failed=True, open_error=True, last_occurred_at=row['occurred_at'])
        overview = overview_page({'data': {'hasData': False}, 'compatibility': {
            'hasData': True, 'allTimeOpenErrorCount': 1, 'attention': [attention]}}, user, 'test-csrf').decode()
        panel = overview.split("aria-labelledby='overview-attention-title'>", 1)[1].split('</section>', 1)[0]
        self.assertIn('Installation problems', panel)
        self.assertIn('Installation problems · 1', panel)
        self.assertIn('/admin/installations?state=open', panel)
        self.assertNotIn('No device diagnostic report received', panel)
        self.assertIn('Inspect', panel)
        # Rendering is read-only: no assignment or GitHub action was submitted.
        self.assertEqual(self.db.identity_reviews, [])

    def test_result_zero_form_http_and_db_scope_update_only_that_result(self):
        first = self.fixture()
        second = dict(first, id='aabbccdd-1111-4111-8111-111111111112', mapResultIndex=1,
                      selectedMapCount=2, caseSizeMm=51)
        self.assertEqual(self.send(first)[0], 201)
        self.assertEqual(self.send(second)[0], 201)
        rows = self.db.rows()
        html = diagnostics_page(
            [], {'username': 'operator'}, 'diagnostic-test-csrf',
            identity=rows[0]['compatibility_identity'], operations=rows,
            identity_devices=[DEVICE],
        ).decode()
        canonical_key = f"result:{first['operationId']}:0"
        self.assertIn(f"name='operation_key' value='{canonical_key}'", html)
        self.assertIn("name='canonical_device_model_id'", html)

        auth = self.authenticated_identity_headers()
        form = urlencode({
            'csrf_token': auth['csrf_token'], 'operation_key': canonical_key,
            'identity_action': 'ASSIGN', 'canonical_device_model_id': DEVICE['id'],
            'return_to': '/admin/installations',
        })
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            'POST', '/admin/diagnostics/identity', form,
            {'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': auth['Cookie']},
        )
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(response.status, 303)
        self.assertEqual(self.db.identity_scope_calls[-1]['operation_key'], canonical_key)
        updated = {
            row['map_result_index']: row['canonical_device_model_id']
            for row in self.db.rows()
        }
        self.assertEqual(updated[0], DEVICE['id'])
        self.assertIsNone(updated[1])

    def test_unknown_failure_is_accepted_without_faking_disconnect(self):
        payload = self.fixture()
        payload.update(failureCode='INSTALL_FAILED_UNKNOWN', failureStage='preflight', errorCategory='unknown',
                       nativeFailureCode='PREFLIGHT_MTP_READ_FAILED', writeStarted=False,
                       remoteObjectCreated=False, cleanupAttempted=False, cleanupSucceeded=False, transferProgressBucket='0')
        from test_shared_contracts import validator
        validator('compatibility-event').validate(payload)
        self.assertEqual(self.send(payload)[0], 201)
        row = self.db.rows()[0]
        self.assertEqual(row['failure_code'], 'INSTALL_FAILED_UNKNOWN')
        self.assertFalse(row['write_started'])
        self.assertTrue(row['is_local_test'])

    def test_missing_identity_proof_keeps_report_unassigned(self):
        self.db.mappings = []
        self.assertEqual(self.send(self.fixture())[0], 201)
        row = self.db.rows()[0]
        self.assertIsNone(row['canonical_device_model_id'])
        self.assertEqual(row['phase_outcome'], 'FAILED')
        self.assertEqual(row['model'], self.fixture()['model'])

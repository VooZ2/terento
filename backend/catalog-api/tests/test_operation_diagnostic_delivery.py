"""Native payload → real HTTP intake/identity assessment/INSERT → admin renderers.

SQLite executes the production INSERT with placeholder/cast translation only.
This is not a PostgreSQL integration or a production-data repair.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import unittest

from terento_catalog.admin import (
    _admin_device_payload, _diagnostic_summary_by_identity, diagnostics_page, device_detail_page, overview_page,
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
            optional_component_native_failure_code TEXT'''
        self.sqlite.execute('CREATE TABLE compatibility_evidence_event (' + columns + ')')
        self.mappings = deepcopy(MAPPINGS)

    def insert_compatibility_event(self, event):
        return Database.insert_compatibility_event(self, event)

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
            row.update(operation_key=row['operation_id'], diagnostic_status='ACTIVE',
                       identity_assessment=json.loads(row['identity_assessment']))
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

    def fixture(self):
        dynamic = os.environ.get('TERENTO_DIAGNOSTIC_FIXTURE_OUTPUT')
        if dynamic:
            values = json.loads(Path(dynamic).read_text())
            return next(v for v in values if v['failureCode'] == 'INSTALL_FAILED_WRITE')
        return json.loads((Path(__file__).resolve().parents[3] / 'contracts/fixtures/compatibility-event.valid-failed-operation.json').read_text())

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
        values = json.loads(Path(path).read_text()) if path else [self.fixture()]
        for payload in values:
            schema.validate(payload)
            validated = validate_event(json.dumps(payload).encode())
            self.assertEqual(str(validated['operationId']).lower(), payload['operationId'].lower())

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
        self.assertIn('test-fenix8-47', panel)
        self.assertNotIn('No device diagnostic report received', panel)
        self.assertIn('Details', panel)
        # Rendering is read-only: no assignment or GitHub action was submitted.
        self.assertEqual(self.db.identity_reviews, [])

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

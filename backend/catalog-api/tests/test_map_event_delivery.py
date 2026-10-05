"""Actual map-event HTTP validation and production INSERT on a local SQL fixture."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer
from uuid import uuid4

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.db import Database
from terento_catalog.http_api import CatalogService, make_handler
import test_catalog_api


class MapIntakeDatabase(FakeProviderDatabase):
    insert_map_event = Database.insert_map_event

    def __init__(self):
        super().__init__()
        self.sql = sqlite3.connect(':memory:', check_same_thread=False)
        self.sql.row_factory = sqlite3.Row
        self.sql.execute('CREATE TABLE map_package (id TEXT PRIMARY KEY)')
        self.sql.execute('CREATE TABLE map_download_event (event_id TEXT PRIMARY KEY, operation_id TEXT, provider_id TEXT, map_package_id TEXT, region TEXT, event_type TEXT, outcome TEXT, occurred_at TEXT, app_build TEXT, release_label TEXT, is_local_test BOOLEAN, acquisition_id TEXT, component_kind TEXT, map_result_index INTEGER, acquisition_purpose TEXT)')

    @contextmanager
    def connection(self):
        yield self

    def execute(self, query, params=()):
        if query.startswith('DELETE FROM map_download_event'):
            return self.sql.execute('SELECT 1 WHERE 0')
        return self.sql.execute(query.replace('%s', '?'), tuple(value.isoformat() if hasattr(value, 'isoformat') else value for value in params))


class MapEventDeliveryTests(unittest.TestCase):
    def test_http_purpose_storage_legacy_and_idempotent_replay(self):
        database = MapIntakeDatabase()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(CatalogService(database)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = json.loads((Path(__file__).resolve().parents[3] / 'contracts/fixtures/map-event.valid-acquisition-purpose.json').read_text())
        try:
            for purpose in ('install', 'update', None, 'absent'):
                event = dict(base, id=str(uuid4()), acquisitionPurpose=purpose)
                if purpose == 'absent':
                    del event['acquisitionPurpose']
                raw = json.dumps(event).encode()
                for expected in (201, 200):
                    response, _ = test_catalog_api.CatalogAPITests._request(server, 'POST', '/map-events', raw, {'Content-Type': 'application/json'})
                    self.assertEqual(response.status, expected)
                row = database.sql.execute('SELECT * FROM map_download_event WHERE event_id=?', (event['id'],)).fetchone()
                self.assertEqual(row['acquisition_purpose'], None if purpose == 'absent' else purpose)
            for changes in ({'outcome': 'SUCCEEDED'}, {'mapResultIndex': True}, {'acquisitionPurpose': 'unknown'}):
                response, _ = test_catalog_api.CatalogAPITests._request(server, 'POST', '/map-events', json.dumps(dict(base, id=str(uuid4()), **changes)).encode(), {'Content-Type': 'application/json'})
                self.assertEqual(response.status, 400)
            self.assertEqual(database.sql.execute('SELECT count(*) FROM map_download_event').fetchone()[0], 4)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            database.sql.close()

    @unittest.skipUnless(os.environ.get('TERENTO_MAP_EVENT_FIXTURES'), 'Fresh Swift encoder fixtures not supplied')
    def test_fresh_swift_download_payloads_reach_storage(self):
        events = json.loads(Path(os.environ['TERENTO_MAP_EVENT_FIXTURES']).read_text())
        self.assertEqual({event.get('acquisitionPurpose') for event in events}, {'install', 'update'})
        database = MapIntakeDatabase()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(CatalogService(database)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for event in events:
                with self.subTest(event_type=event['eventType'], purpose=event['acquisitionPurpose']):
                    for expected in (201, 200):
                        response, _ = test_catalog_api.CatalogAPITests._request(server, 'POST', '/map-events', json.dumps(event).encode(), {'Content-Type': 'application/json'})
                        self.assertEqual(response.status, expected)
                    row = database.sql.execute('SELECT * FROM map_download_event WHERE event_id=?', (event['id'].lower(),)).fetchone()
                    self.assertEqual(row['acquisition_purpose'], event['acquisitionPurpose'])
                    self.assertEqual(row['acquisition_id'], event['acquisitionId'].lower())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            database.sql.close()

    @unittest.skipUnless(os.environ.get('PGLITE_MODULE_PATH'), 'PGLITE_MODULE_PATH required')
    def test_additive_migration_preserves_old_rows_and_writers(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(Path(__file__).with_name('acquisition_purpose_postgres.cjs')), os.environ['PGLITE_MODULE_PATH'], str(root / 'src/terento_catalog/migrations/068_acquisition_purpose.sql')], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

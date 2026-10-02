"""Provider recovery safety and bounded inspection contracts; no live sources."""
import json
import os
from pathlib import Path
import subprocess
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import patch, Mock

from terento_catalog import provider_rechecks as checks
from terento_catalog.provider_catalog import ProviderCollectionError
from terento_catalog.collectors.freizeitkarte.range_zip import HTTPRangeFetcher, InvalidRangeResponse


class RecheckInspectionTests(unittest.TestCase):
    def row(self, provider='freizeitkarte', **values):
        return {'provider_id': provider, 'source_url': 'https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip',
                'region': 'DEU', 'country_codes': ['DE'], 'kind': 'main', **values}

    def test_policy_precedes_every_network_validator(self):
        for provider in ('bbbike', 'maprando', 'opentopomap', 'freizeitkarte'):
            for policy in ({'country_codes': ['RU']}, {'country_codes': ['UA'], 'region': 'CRIMEA'}, {'availability': 'WITHHELD'}):
                with self.subTest(provider=provider, policy=policy), patch.object(checks, 'build_opener') as opener:
                    with self.assertRaisesRegex(ValueError, 'acquisition_withheld'):
                        checks.inspect_artifact(self.row(provider, **policy))
                    opener.assert_not_called()

    def test_freizeitkarte_legacy_russia_alias_is_mapped_before_request(self):
        for extra in ({'provider_region_id':'RUS-NW'}, {'country_codes':['RUS+']}):
            with patch.object(checks, 'build_opener') as opener:
                with self.assertRaisesRegex(ValueError, 'acquisition_withheld'):
                    checks.inspect_artifact(self.row(**extra))
                opener.assert_not_called()

    def test_freizeitkarte_uses_bounded_zip_measurement(self):
        measurement = SimpleNamespace(download_size_bytes=1234, install_size_bytes=4321, payload_path='gmapsupp.img')
        with patch('terento_catalog.collectors.freizeitkarte.range_zip.ZipRangeInspector.inspect', return_value=measurement) as inspect:
            result = checks.inspect_artifact(self.row())
        self.assertEqual(result['install_size_bytes'], 4321)
        self.assertEqual(inspect.call_args.kwargs, {'expected_payload_path': 'gmapsupp.img'})

    def test_unreviewed_zip_sources_never_reach_inspector(self):
        for url in ('http://download.freizeitkarte-osm.de/garmin/latest/DEU_gmapsupp.img.zip',
                    'https://download.freizeitkarte-osm.de:8443/garmin/latest/DEU_gmapsupp.img.zip',
                    'https://download.freizeitkarte-osm.de/garmin/%2e%2e/DEU_gmapsupp.img.zip',
                    'https://download.freizeitkarte-osm.de/unknown.zip',
                    'https://evil.test/garmin/latest/DEU_gmapsupp.img.zip'):
            with self.subTest(url=url), patch('terento_catalog.collectors.freizeitkarte.range_zip.ZipRangeInspector.inspect') as inspect:
                with self.assertRaisesRegex(ValueError, 'unreviewed_source'):
                    checks.inspect_artifact(self.row(source_url=url))
                inspect.assert_not_called()

    def test_maprando_requires_identity(self):
        with patch('terento_catalog.maprando.inspect_maprando_img', return_value=SimpleNamespace(identity_validated=False)):
            with self.assertRaisesRegex(ProviderCollectionError, 'identity is unavailable'):
                checks.inspect_artifact(self.row('maprando'))
        with patch('terento_catalog.maprando.inspect_maprando_img', return_value=SimpleNamespace(identity_validated=True, size_bytes=1234)):
            self.assertEqual(checks.inspect_artifact(self.row('maprando')), {'size_bytes':1234, 'install_size_bytes':1234})

    def test_bbbike_and_contour_preserve_source_proof(self):
        generated = datetime.now(timezone.utc)
        measurement = SimpleNamespace(download_size_bytes=500, install_size_bytes=900, payload_path='main.img',
                                      source_proof={'revision':'abc'}, generated_at=generated, source_updated_at=generated)
        for provider, target, extra in (
            ('bbbike', 'terento_catalog.bbbike.inspect_bbbike', {'provider_region_id':'europe/lithuania', 'map_type':'bbbike-latin1'}),
            ('opentopomap', 'terento_catalog.contour_source.inspect_contour', {'kind':'contours'})):
            with self.subTest(provider=provider), patch(target, return_value=measurement):
                result = checks.inspect_artifact(self.row(provider, **extra))
                self.assertEqual(result['source_proof'], {'revision':'abc'})
                self.assertEqual(result['source_updated_at'], generated)

    def test_redirect_rejected_before_following(self):
        with self.assertRaisesRegex(ValueError, 'redirect'):
            checks._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test')

    def test_head_429_is_not_swallowed(self):
        error = HTTPError('https://source.test', 429, 'limited', {'Retry-After':'3600'}, None)
        with patch('terento_catalog.collectors.freizeitkarte.range_zip.urlopen', side_effect=error):
            with self.assertRaises(HTTPError):
                HTTPRangeFetcher().head_size('https://source.test')

    def test_nested_http_failure_preserves_status_and_retry_after(self):
        error = HTTPError('https://source.test', 429, 'limited', {'Retry-After':'3600'}, None)
        wrapped = InvalidRangeResponse('provider Range request failed')
        wrapped.__cause__ = error
        result = checks.check_failure(wrapped)
        self.assertEqual(result['httpStatus'], 429)
        self.assertEqual(result['code'], 'rate_limited')
        self.assertGreater(datetime.fromisoformat(result['retryNotBefore']), datetime.now(timezone.utc)+timedelta(minutes=59))
        self.assertNotIn('source.test', result['message'])


class Result:
    def __init__(self, rows): self.rows=rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class WorkerDatabase:
    """Small stateful SQL boundary fixture: records and simulates result publication."""
    def __init__(self, rows, changed=False, busy=False):
        self.rows=rows
        self.changed=changed
        self.busy=busy
        self.commands=[]
        self.job={'id':1, 'provider_id':'bbbike', 'package_id':None}
        self.state='QUEUED'
        self.results=[]
    @contextmanager
    def connection(self): yield self
    def execute(self, sql, args=()):
        self.commands.append((sql,args))
        if sql.startswith('SELECT pg_try_advisory_lock'):
            return Result([{'acquired':not self.busy}])
        if sql.startswith('SELECT * FROM provider_recheck'):
            return Result([self.job] if self.state=='QUEUED' else [])
        if sql.startswith("UPDATE provider_recheck SET state='RUNNING'"):
            self.state='RUNNING'
        if sql.startswith("UPDATE provider_recheck SET state='QUEUED'"):
            self.state='QUEUED'
        if sql.startswith('SELECT a.*'):
            return Result(self.rows)
        if sql.startswith('SELECT a.source_url'):
            row=next(r for r in self.rows if r['id']==args[0])
            return Result([{'source_url':'changed' if self.changed else row['source_url'], 'updated_at':row['updated_at']}])
        if sql.startswith('UPDATE provider_recheck SET results='):
            self.results=json.loads(args[0])
        if sql.startswith('UPDATE provider_recheck SET state=%s'):
            self.state=args[0]
        return Result([])


class RecheckWorkerTests(unittest.TestCase):
    def database(self, **args):
        rows=[{'id':str(i), 'package_id':'p'+str(i), 'provider_id':'bbbike', 'source_url':'https://source/'+str(i),
               'updated_at':datetime.now(timezone.utc)} for i in range(2)]
        return WorkerDatabase(rows, **args)

    def test_429_stops_remaining_artifacts_and_persists_cooldown(self):
        db=self.database()
        with patch.object(checks,'inspect_artifact', side_effect=HTTPError('https://source',429,'limited',{'Retry-After':'1800'},None)) as inspect:
            checks.process_one(db)
        self.assertEqual(inspect.call_count,1)
        self.assertEqual(db.state,'FAILED')
        self.assertEqual(db.results[0]['httpStatus'],429)
        self.assertTrue(any('retry_not_before=%s' in sql for sql,args in db.commands))

    def test_stale_result_does_not_overwrite_artifact_or_package(self):
        db=self.database(changed=True)
        with patch.object(checks,'inspect_artifact',return_value={'size_bytes':100}):
            checks.process_one(db)
        self.assertEqual(db.state,'FAILED')
        self.assertTrue(all(r['status']=='STALE' for r in db.results))
        self.assertFalse(any(sql.startswith(('UPDATE map_artifact','UPDATE map_package')) for sql,args in db.commands))

    def test_busy_collection_requeues_without_network_or_false_failure(self):
        db=self.database(busy=True)
        with patch.object(checks,'inspect_artifact') as inspect:
            checks.process_one(db)
        self.assertEqual(db.state,'QUEUED')
        inspect.assert_not_called()

    def test_bbbike_success_updates_release_proof_and_source(self):
        db=self.database()
        generated=datetime(2026,9,30,tzinfo=timezone.utc)
        with patch.object(checks,'inspect_artifact',return_value={'size_bytes':100,'source_updated_at':generated,'source_proof':{'revision':'abc'}}):
            checks.process_one(db)
        self.assertEqual(db.state,'SUCCEEDED')
        release=[args for sql,args in db.commands if sql.startswith('UPDATE map_package SET release=')]
        self.assertEqual(len(release),2)
        self.assertEqual(release[0][:3],('2026-09-30','2026-09-30','abc'))
        self.assertTrue(any(sql.startswith('UPDATE provider_source') for sql,args in db.commands))

    def test_second_worker_cannot_interrupt_active_jobs(self):
        db=self.database(busy=True)
        stop=Mock()
        checks.run_worker(db,stop)
        self.assertFalse(any('INTERRUPTED' in sql for sql,args in db.commands))
        stop.wait.assert_not_called()


class RecheckEnqueueTests(unittest.TestCase):
    def database(self, recent):
        db = Mock()
        connection = Mock()
        connection.execute.side_effect = [Result([{'id':'bbbike'}]), Result([{'id':'pkg'}]), Result([recent])]
        db.connection.return_value.__enter__ = Mock(return_value=connection)
        db.connection.return_value.__exit__ = Mock(return_value=False)
        return db

    def test_same_active_scope_is_reused(self):
        db = self.database({'id':3, 'state':'RUNNING', 'package_id':'pkg'})
        self.assertEqual(checks.enqueue(db,'bbbike','pkg',1), {'jobId':3})

    def test_other_active_scope_is_explicitly_busy(self):
        db = self.database({'id':3, 'state':'RUNNING', 'package_id':'other'})
        with self.assertRaisesRegex(ValueError,'provider_busy'):
            checks.enqueue(db,'bbbike','pkg',1)

    def test_completed_scope_is_not_returned_as_new_work(self):
        db = self.database({'id':3, 'state':'SUCCEEDED', 'package_id':'pkg', 'retry_at':datetime.now(timezone.utc)})
        with self.assertRaisesRegex(ValueError,'cooldown: retry after'):
            checks.enqueue(db,'bbbike','pkg',1)

    def test_execution_honors_persisted_retry_limit(self):
        db = RecheckWorkerTests().database()
        with patch.object(checks,'ensure_retry_allowed',side_effect=ValueError('Provider rate limit: retry later')), patch.object(checks,'inspect_artifact') as inspect:
            with self.assertLogs(checks.__name__, level='ERROR'):
                checks.process_one(db)
        inspect.assert_not_called()


class RecheckCooldownIntegrationTests(unittest.TestCase):
    def test_collection_checks_cooldown_under_lock_even_for_dry_run(self):
        from api_test_fixtures import FakeProviderDatabase
        from terento_catalog.collect import collect_provider_once, collect_once
        class RecordingDatabase(FakeProviderDatabase):
            def __init__(self):
                super().__init__()
                self.queries=[]
            def execute(self, sql, args=()):
                self.queries.append(sql)
                return super().execute(sql,args)
        for legacy in (False, True):
            database=RecordingDatabase()
            with patch.object(checks,'ensure_retry_allowed',side_effect=ValueError('retry later')) as cooldown, patch('terento_catalog.collect._collect_provider_once') as collect, patch('terento_catalog.collect._collect_once') as legacy_collect:
                with self.assertRaisesRegex(ValueError,'retry later'):
                    if legacy:
                        collect_once(database,dry_run=True)
                    else:
                        collect_provider_once(database,SimpleNamespace(definition=SimpleNamespace(id='bbbike')),dry_run=True)
                self.assertTrue(database.queries[0].startswith('SELECT pg_try_advisory_lock'))
                self.assertTrue(database.queries[-1].startswith('SELECT pg_advisory_unlock'))
                cooldown.assert_called_once()
                collect.assert_not_called()
                legacy_collect.assert_not_called()

    def test_dry_run_collects_without_database_mutation(self):
        from api_test_fixtures import FakeProviderDatabase
        from terento_catalog.collect import collect_provider_once
        adapter=SimpleNamespace(definition=SimpleNamespace(id='bbbike'),
                                collect=lambda:SimpleNamespace(packages=[SimpleNamespace(artifacts=[])]))
        database=FakeProviderDatabase()
        result=collect_provider_once(database,adapter,dry_run=True)
        self.assertEqual(result,{'provider':'bbbike','runId':0,'packages':1,'artifacts':0})

    def test_provider_health_does_not_probe_during_retry_after(self):
        from api_test_fixtures import FakeProviderDatabase
        from terento_catalog.http_api import CatalogService
        class LimitedDatabase(FakeProviderDatabase):
            def execute(self, sql, args=()):
                if sql.startswith('SELECT max(retry_not_before)'):
                    return Result([{'retry_at':datetime.now(timezone.utc)+timedelta(hours=1)}])
                return super().execute(sql,args)
        with patch('terento_catalog.http_api.run_provider_health_check') as probe:
            with self.assertRaisesRegex(ValueError,'Provider rate limit: retry after'):
                CatalogService(LimitedDatabase()).check_provider('bbbike')
            probe.assert_not_called()


class RecheckHTTPTests(unittest.TestCase):
    def test_post_requires_session_csrf_and_rejects_source_injection(self):
        from api_test_fixtures import FakeProviderDatabase
        from terento_catalog.http_api import CatalogService, make_handler
        database = FakeProviderDatabase()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(CatalogService(database)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def post(body, headers):
            connection = HTTPConnection(*server.server_address)
            connection.request('POST', '/admin/providers/bbbike/rechecks', json.dumps(body),
                               {'Content-Type':'application/json', **headers})
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            return response.status, payload
        try:
            with patch.object(checks, 'enqueue', return_value={'jobId':7}) as enqueue:
                self.assertEqual(post({'packageId':'pkg'}, {})[0], 401)
                cookie = {'Cookie':'terento_admin_session=session'}
                self.assertEqual(post({'packageId':'pkg'}, cookie)[0], 403)
                self.assertEqual(post({'packageId':'pkg'}, {**cookie,'X-CSRF-Token':'wrong'})[0], 403)
                headers = {**cookie, 'X-CSRF-Token':'csrf'}
                self.assertEqual(post({'sourceURL':'https://evil.test'}, headers)[0], 400)
                self.assertEqual(post({'packageId':3}, headers)[0], 400)
                self.assertEqual(post({'packageId':''}, headers)[0], 400)
                self.assertEqual(post({'packageId':'   '}, headers)[0], 400)
                self.assertEqual(post({'packageId':'x'*161}, headers)[0], 400)
                for invalid in ('', '   ', 'x' * 161):
                    self.assertEqual(post({'packageId':invalid}, headers)[0], 400)
                enqueue.assert_not_called()
                status, payload = post({'packageId':'pkg'}, headers)
                self.assertEqual(status, 200)
                self.assertEqual(payload, {'status':'ok', 'result':{'jobId':7}})
                enqueue.assert_called_once_with(database, 'bbbike', 'pkg', 7)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@unittest.skipUnless(os.environ.get('PGLITE_MODULE_PATH'), 'Set PGLITE_MODULE_PATH for isolated PostgreSQL tests')
class RecheckPostgresTests(unittest.TestCase):
    def test_publication_and_cooldown_sql_against_postgres(self):
        for failure in (False, True):
            db = RecheckWorkerTests().database()
            generated = datetime(2026, 9, 30, tzinfo=timezone.utc)
            settings = {'side_effect': HTTPError('https://source', 429, 'limited', {'Retry-After':'1800'}, None)} if failure else {
                'return_value': {'size_bytes':100, 'source_updated_at':generated, 'source_proof':{'revision':'abc'}}}
            with patch.object(checks, 'inspect_artifact', **settings):
                checks.process_one(db)
            root = Path(__file__).parent
            payload = {'migration': (root.parent / 'src/terento_catalog/migrations/064_provider_rechecks_update_diagnostics.sql').read_text(),
                       'rows':db.rows, 'commands':db.commands, 'expectedState':db.state, 'resultCount':len(db.results)}
            result = subprocess.run(['node', str(root / 'provider_rechecks_postgres.cjs'), os.environ['PGLITE_MODULE_PATH']],
                                    input=json.dumps(payload, default=lambda value:value.isoformat()), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__': unittest.main()

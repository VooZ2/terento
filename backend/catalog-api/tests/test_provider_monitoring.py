import json
import ast
import inspect
import textwrap
import os
from pathlib import Path
import subprocess
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

from terento_catalog.db import Database
from terento_catalog.provider_monitoring import monitoring_state, provider_block_reason, run_health_cycle, run_worker
from pglite_support import require_pglite

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)

class RecordingDatabase(Database):
    def __init__(self):
        super().__init__('unused')
        self.commands = []
    @contextmanager
    def connection(self):
        yield self
    def execute(self, sql, args=()):
        self.commands.append((sql,args))
        return self
    def fetchone(self): return {'id':1}
    def fetchall(self): return []
    rowcount = 1

class MonitoringTests(unittest.TestCase):
    def test_schedule_intervals_and_staleness_grace(self):
        for hours in (1,6,24):
            state = monitoring_state(NOW.isoformat(),hours,NOW)
            self.assertEqual(state['nextCheckAt'],(NOW+timedelta(hours=hours)).isoformat())
            self.assertFalse(state['stale'])
            self.assertFalse(monitoring_state(NOW,hours,NOW+timedelta(hours=hours,minutes=10))['stale'])
            self.assertTrue(monitoring_state(NOW,hours,NOW+timedelta(hours=hours,minutes=11))['stale'])
        self.assertTrue(monitoring_state(None,now=NOW)['stale'])

    def test_cooldown_pause_outage_and_recovery(self):
        self.assertEqual(provider_block_reason('ACTIVE','HEALTHY',NOW,now=NOW,retry_at=NOW+timedelta(hours=2)),'PROVIDER_RATE_LIMITED')
        self.assertEqual(provider_block_reason('PAUSED','HEALTHY',NOW,now=NOW),'PROVIDER_PAUSED')
        self.assertEqual(provider_block_reason('ACTIVE','DOWN',NOW-timedelta(days=2),now=NOW),'PROVIDER_DOWN')
        self.assertEqual(provider_block_reason('ACTIVE','HEALTHY',NOW-timedelta(days=2),now=NOW),'STATUS_STALE')
        self.assertIsNone(provider_block_reason('ACTIVE','HEALTHY',NOW,now=NOW))
        self.assertIsNone(provider_block_reason('ACTIVE','DEGRADED',NOW,now=NOW))
        self.assertEqual(monitoring_state(NOW,1,NOW,retry_at=NOW+timedelta(hours=4))['nextCheckAt'],(NOW+timedelta(hours=4)).isoformat())

    def test_cycle_isolates_failed_and_locked_providers(self):
        db=Mock()
        db.due_provider_health_checks.return_value=[{'id':v} for v in ('broken','locked','healthy')]
        check=Mock(side_effect=[RuntimeError('failed'),ValueError('locked'),None])
        with self.assertLogs('terento_catalog.provider_monitoring',level='INFO'):
            run_health_cycle(db,check)
        db.prune_provider_health_history.assert_called_once()
        self.assertEqual([c.args[0] for c in check.call_args_list],['broken','locked','healthy'])
        self.assertTrue(all(c.kwargs == {'scheduled':True} for c in check.call_args_list))

    def test_worker_stops_without_checking_when_requested(self):
        stop=threading.Event();stop.set();db=Mock()
        run_worker(db,stop)
        db.prune_provider_health_history.assert_not_called()

    def test_control_validation_before_database_changes(self):
        db=RecordingDatabase()
        for hours in (True,0,2,12,25,'1',None):
            with self.assertRaises(ValueError): db.set_provider_health_interval('p',hours,1,'request')
        for enabled,reason in ((1,'why'),(False,''),(False,' '*3),(False,'x'*501),(False,None)):
            with self.assertRaises(ValueError): db.set_package_downloads('p','pkg',enabled,reason,1,'request')
        self.assertEqual(db.commands,[])

    def test_policy_filters_before_eight_sample_limit_and_deduplicates(self):
        denied=[{'country_codes':['RU']}, {'country_codes':['UA'],'region':'CRIMEA'},
                {'country_codes':['UA'],'canonical_region_id':'CRIMEA','region':'KYIV'},
                {'country_codes':['LT'],'availability':'WITHHELD'}, {'provider_region_id':'RUS-NW'}]
        rows=[{'source_url':f'https://source/{i}',**policy} for i,policy in enumerate(denied)]
        valid=[{'source_url':f'https://source/valid{i}','country_codes':['LT']} for i in range(10)]
        rows += [valid[0],*valid]
        db=RecordingDatabase(); db.fetchall=lambda:rows
        selected=db.provider_download_urls('freizeitkarte')
        self.assertEqual([r['source_url'] for r in selected],[r['source_url'] for r in valid[:8]])
        self.assertNotIn('LIMIT',db.commands[0][0])
        self.assertIn('mp.canonical_region_id',db.commands[0][0])

    def test_unknown_non_russia_regions_remain_eligible(self):
        rows=[{'source_url':'https://source/unknown'},
              {'source_url':'https://source/ukraine','country_codes':['UA'],'region':'KYIV'},
              {'source_url':'https://source/other','country_codes':['LT'],'provider_region_id':'RUS-NW'}]
        db=RecordingDatabase(); db.fetchall=lambda:rows
        self.assertEqual(db.provider_download_urls('maprando'),rows)

    def test_control_changes_are_audited(self):
        db=RecordingDatabase()
        db.set_provider_health_interval('p',6,1,'r')
        db.set_package_downloads('p','pkg',False,' Broken map ',1,'r')
        db.set_package_downloads('p','pkg',True,'',1,'r')
        audits=[args for sql,args in db.commands if 'INSERT INTO admin_audit_log' in sql]
        self.assertEqual([a[1] for a in audits],['provider.health_schedule_changed','package.downloads_disabled','package.downloads_enabled'])

    def test_missing_or_retired_target_does_not_write_audit(self):
        db=RecordingDatabase()
        db.fetchone=lambda:None
        with self.assertRaises(LookupError):
            db.set_package_downloads('retired','pkg',True,'',1,'r')
        self.assertFalse(any('INSERT INTO admin_audit_log' in sql for sql,args in db.commands))

    def test_http_controls_require_session_csrf_and_strict_payload(self):
        from api_test_fixtures import FakeProviderDatabase
        from terento_catalog.http_api import CatalogService, make_handler
        db=FakeProviderDatabase()
        db.set_provider_health_interval=Mock(return_value={'intervalHours':6})
        db.set_package_downloads=Mock(return_value={'enabled':False})
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(CatalogService(db)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(action,body,headers):
            conn=HTTPConnection(*server.server_address)
            conn.request('POST','/admin/providers/bbbike/'+action,json.dumps(body),{'Content-Type':'application/json',**headers})
            response=conn.getresponse();response.read();conn.close()
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            return response.status
        try:
            for action,body in [('health-schedule',{'intervalHours':6}),('downloads',{'packageId':'pkg','enabled':False,'reason':'Broken map'})]:
                self.assertEqual(post(action,body,{}),401)
                cookie={'Cookie':'terento_admin_session=session'}
                self.assertEqual(post(action,body,cookie),403)
                headers={**cookie,'X-CSRF-Token':'csrf'}
                self.assertEqual(post(action,{**body,'sourceURL':'https://evil.test'},headers),400)
                self.assertEqual(post(action,body,headers),200)
            db.set_provider_health_interval.assert_called_once()
            db.set_package_downloads.assert_called_once()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

class MonitoringPostgresTests(unittest.TestCase):
    def test_migration_controls_due_and_retention(self):
        db=RecordingDatabase()
        db.set_provider_health_interval('due',6,1,'r')
        interval=db.commands[:];db.commands=[]
        db.set_package_downloads('due','pkg',False,'Broken map',1,'r')
        disable=db.commands[:];db.commands=[]
        db.set_package_downloads('due','pkg',True,'',1,'r')
        enable=db.commands[:];db.commands=[]
        db.due_provider_health_checks();due=db.commands[0];db.commands=[]
        db.prune_provider_health_history();prune=db.commands[0];db.commands=[]
        db.provider_detail('due');history=next(c for c in db.commands if "interval '30 days'" in c[0])
        from terento_catalog.provider_health import check_provider
        from terento_catalog.provider_catalog import OPENTOPO_MAP
        from test_provider_health import Probe
        from dataclasses import replace
        db.commands=[]
        db.record_provider_health(replace(check_provider(OPENTOPO_MAP,probe=Probe()),provider_id='due',retry_after_seconds=7200))
        cooldown=db.commands[-1]
        tree=ast.parse(textwrap.dedent(inspect.getsource(Database.upsert_provider_snapshot)))
        package_sql=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and 'INSERT INTO map_package (' in n.value)
        root=Path(__file__).parent
        payload={'migration':next((root.parent/'src/terento_catalog/migrations').glob('066_*.sql')).read_text(),
                 'interval':interval,'disable':disable,'enable':enable,'due':due,'prune':prune,'history':history,'cooldown':cooldown,'packageSql':package_sql}
        result=subprocess.run(['node',str(root/'provider_monitoring_postgres.cjs'),require_pglite(self)],input=json.dumps(payload),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

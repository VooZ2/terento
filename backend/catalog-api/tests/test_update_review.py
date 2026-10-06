"""Update review state must never rewrite telemetry or installation evidence."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from terento_catalog.db import Database
from terento_catalog.github_issue_sync import apply_closed_update_issue
from pglite_support import require_pglite

EVENT = '11111111-1111-4111-8111-111111111111'


class Result:
    def __init__(self, rows=()): self.rows=list(rows)
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class ReviewDatabase(Database):
    def __init__(self, *, local=False):
        super().__init__('unused')
        self.calls=[]
        self.row=dict(event_id=EVENT,diagnostic_status='ACTIVE',diagnostic_workflow_status='OPEN',
                      linked_github_issue=None,resolution_code=None,resolution_note=None,
                      resolved_at=None,resolved_by=None,is_local_test=local,outcome='FAILED',
                      payload={'writeStarted':True,'automaticFinishingResult':'FAILED'})
    @contextmanager
    def connection(self): yield self
    def execute(self, sql, params=None):
        self.calls.append((sql,params))
        if 'SELECT event_id,diagnostic_status' in sql:
            if self.row['is_local_test']: return Result()
            if 'WHERE event_id=' in sql:
                return Result([deepcopy(self.row)]) if params[0]==self.row['event_id'] else Result()
            return Result([deepcopy(self.row)]) if self.row['diagnostic_status']=='ACTIVE' and self.row['linked_github_issue']==params[0] else Result()
        if 'UPDATE map_update_diagnostic SET diagnostic_status=%s' in sql:
            for key,value in zip(('diagnostic_status','diagnostic_workflow_status','linked_github_issue','resolution_code','resolution_note'),params):
                self.row[key]=value
        elif "UPDATE map_update_diagnostic SET diagnostic_status='RESOLVED'" in sql:
            self.row.update(diagnostic_status='RESOLVED',diagnostic_workflow_status='OPEN',resolution_code=params[0],resolution_note=params[1])
        return Result()


class UpdateReviewTests(unittest.TestCase):
    def test_review_transitions_are_exact_audited_and_evidence_immutable(self):
        db=ReviewDatabase()
        evidence=deepcopy(db.row['payload'])
        actions=[dict(action='issue',linked_github_issue='#12'),
                 dict(action='workflow',workflow_status='UNDER_REVIEW'),
                 dict(action='resolve',resolution_reason='FIXED',resolution_note='Verified fix'),
                 dict(action='reopen'),dict(action='issue',linked_github_issue=None)]
        for action in actions:
            self.assertTrue(db.review_update_diagnostic(EVENT,admin_user_id=7,**action))
        self.assertEqual(db.row['diagnostic_status'],'ACTIVE')
        self.assertEqual(db.row['diagnostic_workflow_status'],'OPEN')
        self.assertIsNone(db.row['linked_github_issue'])
        self.assertEqual(db.row['outcome'],'FAILED')
        self.assertEqual(db.row['payload'],evidence)
        audits=[params for sql,params in db.calls if 'INSERT INTO map_update_diagnostic_audit' in sql]
        self.assertEqual(len(audits),5)
        self.assertTrue(all(params[0]==EVENT for params in audits))
        for sql,_ in db.calls:
            if sql.lstrip().startswith('UPDATE'):
                self.assertNotIn('payload=',sql)
                self.assertNotIn('outcome=',sql)
                self.assertNotIn('canonical_device_model_id=',sql)
            self.assertNotIn('compatibility_evidence_event',sql)

    def test_local_or_absent_report_cannot_be_mutated(self):
        for db,identifier in ((ReviewDatabase(local=True),EVENT),(ReviewDatabase(),'22222222-2222-4222-8222-222222222222')):
            self.assertFalse(db.review_update_diagnostic(identifier,action='issue',linked_github_issue='#12',admin_user_id=7))
            self.assertFalse(any(sql.lstrip().startswith('UPDATE') for sql,_ in db.calls))

    def test_validation_and_linked_workflow_rules(self):
        db=ReviewDatabase()
        for changes in (dict(action='resolve'), dict(action='workflow',workflow_status='CLOSED'),
                        dict(action='issue',linked_github_issue='https://evil.test/12'),dict(action='issue',linked_github_issue='#0'),
                        dict(action='resolve',resolution_reason='FIXED',resolution_note='x'*2001)):
            with self.assertRaises(ValueError): db.review_update_diagnostic(EVENT,admin_user_id=7,**changes)
        self.assertEqual(db.calls,[])
        db.review_update_diagnostic(EVENT,action='issue',linked_github_issue='#12',admin_user_id=7)
        with self.assertRaises(ValueError): db.review_update_diagnostic(EVENT,action='workflow',workflow_status='OPEN',admin_user_id=7)
        db.review_update_diagnostic(EVENT,action='resolve',resolution_reason='FIXED',admin_user_id=7)
        with self.assertRaises(ValueError): db.review_update_diagnostic(EVENT,action='workflow',workflow_status='UNDER_REVIEW',admin_user_id=7)

    def test_github_close_resolves_exact_update_and_does_not_rewrite_result(self):
        db=ReviewDatabase()
        db.review_update_diagnostic(EVENT,action='issue',linked_github_issue='#12',admin_user_id=7)
        self.assertEqual(apply_closed_update_issue(db,13,'completed'),0)
        self.assertEqual(apply_closed_update_issue(db,12,'completed'),1)
        self.assertEqual(apply_closed_update_issue(db,12,'completed'),0)
        self.assertEqual(db.row['outcome'],'FAILED')
        self.assertEqual(db.row['diagnostic_status'],'RESOLVED')
        self.assertEqual(db.row['resolution_code'],'FIXED')
        self.assertTrue(any('github.closed' in sql for sql,_ in db.calls))

    def test_postgres_model_stats_and_review_preserve_outcomes(self):
        db=ReviewDatabase()
        stats_sql=None
        db.update_model_statistics()
        stats_sql=db.calls[-1][0]
        db.calls.clear()
        db.admin_review_summary()
        summary_sql=db.calls[-1][0]
        db.calls.clear()
        for action in (dict(action='issue',linked_github_issue='#12'),dict(action='workflow',workflow_status='UNDER_REVIEW'),
                       dict(action='resolve',resolution_reason='FIXED'),dict(action='reopen')):
            db.review_update_diagnostic(EVENT,admin_user_id=7,**action)
        apply_closed_update_issue(db,12,'completed')
        mutations=list(db.calls)
        db.update_issue_queue_diagnostics()
        root=Path(__file__).parent
        payload={'migrations':[(root.parent/'src/terento_catalog/migrations'/name).read_text() for name in
                              ('064_provider_rechecks_update_diagnostics.sql','065_update_diagnostic_review.sql')],
                 'stats':stats_sql,'summary':summary_sql,'mutations':mutations,'queue':db.calls[-1][0]}
        result=subprocess.run(['node',str(root/'update_review_postgres.cjs'),require_pglite(self)],
                              input=json.dumps(payload),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class UpdateHistoryScopeTests(unittest.TestCase):
    def test_exact_variant_pagination_outcome_and_review_scope(self):
        import sqlite3
        from terento_catalog.update_diagnostics import load_update_diagnostics
        connection=sqlite3.connect(':memory:')
        connection.row_factory=sqlite3.Row
        connection.executescript('''CREATE TABLE device_model(id TEXT,model TEXT,variant TEXT,case_size_mm INTEGER,screen_technology TEXT);
            INSERT INTO device_model VALUES('exact-47','fenix 8','47 mm',47,'AMOLED'),('exact-51','fenix 8','51 mm',51,'AMOLED');
            CREATE TABLE map_update_diagnostic(event_id TEXT,operation_id TEXT,provider TEXT,region TEXT,outcome TEXT,
                payload TEXT,occurred_at TEXT,canonical_device_model_id TEXT,is_local_test BOOLEAN,diagnostic_status TEXT);
        ''')
        for i in range(53):
            connection.execute('INSERT INTO map_update_diagnostic VALUES(?,?,?,?,?,?,?,?,?,?)',
                (str(i),str(i),'bbbike','LTU','FAILED','{}','2026-10-02','exact-47',False,'ACTIVE'))
        for model,local,status in [('exact-51',False,'ACTIVE'),(None,False,'ACTIVE'),('exact-47',True,'ACTIVE'),('exact-47',False,'RESOLVED')]:
            connection.execute('INSERT INTO map_update_diagnostic VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('extra',model,'bbbike','LTU','FAILED','{}','2026-10-02',model,local,status))
        class Store:
            @contextmanager
            def connection(self): yield self
            def execute(self,sql,args):
                cursor=connection.execute(sql.replace('%s','?'),args)
                return Result([dict(row) for row in cursor.fetchall()])
            def update_model_statistics(self): return {'exact-47':{'attemptedUpdateCount':53}}
        try:
            first=load_update_diagnostics(Store(),device_id='exact-47',outcome='failed',lifecycle='ACTIVE')
            second=load_update_diagnostics(Store(),device_id='exact-47',outcome='failed',lifecycle='ACTIVE',offset=50)
            self.assertEqual(len(first['rows']),50)
            self.assertTrue(first['has_more'])
            self.assertEqual(len(second['rows']),3)
            self.assertFalse(second['has_more'])
            self.assertTrue(all(row['canonical_device_model_id']=='exact-47' for row in first['rows']+second['rows']))
            self.assertEqual(first['device']['case_size_mm'],47)
            self.assertEqual(first['summary'],{'attemptedUpdateCount':53})
            with self.assertRaisesRegex(ValueError,'unknown_device'):
                load_update_diagnostics(Store(),device_id='unreviewed')
        finally:
            connection.close()


class UpdateReviewHTTPTests(unittest.TestCase):
    def test_authenticated_csrf_exact_scope_and_safe_return(self):
        from terento_catalog.http_api import make_handler
        class Service:
            def __init__(self): self.database=ReviewDatabase()
            def admin_session(self,token): return {'id':7} if token=='session' else None
            def csrf_valid(self,session,token): return token=='csrf'
        service=Service()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(action,fields,auth=True):
            connection=HTTPConnection(*server.server_address)
            connection.request('POST','/admin/update-diagnostics/'+action,urlencode(fields),
                {'Content-Type':'application/x-www-form-urlencoded',**({'Cookie':'terento_admin_session=session'} if auth else {})})
            response=connection.getresponse();response.read();connection.close();return response
        try:
            fields={'csrf_token':'csrf','diagnostic_id':EVENT,'linked_github_issue':'#12'}
            self.assertEqual(post('issue',fields,False).status,403)
            self.assertEqual(post('issue',{**fields,'csrf_token':'wrong'}).status,403)
            self.assertEqual(post('issue',{**fields,'diagnostic_id':'bad'}).status,400)
            self.assertEqual(post('issue',{**fields,'linked_github_issue':'https://evil.test/12'}).status,400)
            self.assertEqual(service.database.calls,[])
            response=post('issue',{**fields,'return_to':'//evil.test'})
            self.assertEqual(response.status,303)
            self.assertEqual(response.headers['Location'],'/admin/update-diagnostics?diagnosticId='+EVENT)
            self.assertEqual(service.database.row['linked_github_issue'],'#12')
            self.assertEqual(post('resolve',{'csrf_token':'csrf','diagnostic_id':EVENT,'resolution_reason':'FIXED'}).status,303)
            self.assertEqual(post('reopen',{'csrf_token':'csrf','diagnostic_id':EVENT}).status,303)
            self.assertEqual(post('workflow',{'csrf_token':'csrf','diagnostic_id':EVENT,'diagnostic_workflow_status':'UNDER_REVIEW'}).status,303)
            self.assertEqual(service.database.row['outcome'],'FAILED')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

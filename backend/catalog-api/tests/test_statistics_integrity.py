"""Execute production SQL against PostgreSQL/WASM, not SQL spelling assertions."""
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from terento_catalog.db import Database
from terento_catalog.migrate import _statements

class Capture:
    def execute(self, sql, params=()):
        self.sql,self.params=sql,params
        if 'acquisition_activity AS' in sql: self.activity_sql,self.activity_params=sql,params
        return self
    def fetchall(self): return []
    def fetchone(self): return {}

class StatisticsIntegrityTests(unittest.TestCase):
    def test_postgres_result_integrity(self):
        module=os.environ.get('PGLITE_MODULE_PATH') or os.environ.get('TERENTO_PGLITE_MODULE')
        if not module: self.skipTest('PGLITE_MODULE_PATH required for PostgreSQL regression')
        cursor=Capture()
        class D(Database):
            @contextmanager
            def connection(self): yield cursor
        db=D(''); queries={}
        def capture(name, fn):
            fn(); indices=iter(range(1,100))
            queries[name]={'sql':re.sub('%s',lambda _: '$'+str(next(indices)),cursor.sql).replace('%%','%'), 'params':cursor.params}
        capture('stats',lambda:db.map_statistics({}))
        capture('period',lambda:db.map_statistics({'dateFrom':datetime(2026,10,5,10,tzinfo=timezone.utc),'dateTo':datetime(2026,10,5,11,tzinfo=timezone.utc)}))
        capture('trend',lambda:db.map_statistics({},trend_bucket='hour',time_zone='UTC'))
        capture('dst',lambda:db.map_statistics({},trend_bucket='hour',time_zone='Europe/Vilnius'))
        capture('link',lambda:db.map_statistics_linkage({}))
        capture('link_period',lambda:db.map_statistics_linkage({'dateFrom':datetime(2026,10,5,10,tzinfo=timezone.utc),'dateTo':datetime(2026,10,5,11,tzinfo=timezone.utc)}))
        db.admin_overview_map_snapshot(datetime(2026,10,5,10,tzinfo=timezone.utc))
        indices=iter(range(1,100))
        queries['activity']={'sql':re.sub('%s',lambda _: '$'+str(next(indices)),cursor.activity_sql).replace('%%','%'),'params':cursor.activity_params}
        root=Path(__file__).parent
        queries['schema']=(root/'migration_062_postgres.cjs').read_text().split('await db.exec(`',1)[1].split('`);',1)[0]
        queries['previousView']=next(s for s in _statements((root.parent/'src/terento_catalog/migrations/062_reconcile_installation_statistics_schema.sql').read_text()) if 'CREATE OR REPLACE VIEW' in s)
        queries['view']=next(s for s in _statements((root.parent/'src/terento_catalog/migrations/067_statistics_integrity.sql').read_text()) if 'CREATE OR REPLACE VIEW' in s)
        run=subprocess.run(['node',str(root/'statistics_integrity_postgres.cjs'),module],input=json.dumps(queries,default=lambda d:d.isoformat()),text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
        self.assertIn('statistics integrity PASS',run.stdout)

    def test_historical_interval_stops_at_requested_end(self):
        class Frozen(datetime):
            @classmethod
            def now(cls,tz=None): return cls(2026,10,5,17,tzinfo=timezone.utc)
        class D(Database):
            def map_statistics(self,filters,**kwargs): return [{'bucket':Frozen(2026,9,1,tzinfo=timezone.utc),'success_count':1}]
        end=Frozen(2026,9,2,tzinfo=timezone.utc)
        with patch('terento_catalog.db.datetime',Frozen):
            rows,bucket=D('').map_statistics_trend({'dateFrom':Frozen(2026,9,1,tzinfo=timezone.utc),'dateTo':end},period='all')
        self.assertEqual(bucket,'day')
        self.assertEqual(rows[-1]['bucket'],end)
        self.assertEqual(sum(r['success_count'] for r in rows),1)

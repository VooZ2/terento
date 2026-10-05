"""Activity labels come from exact server-assessed diagnostic identities."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from terento_catalog.db import _enrich_activity_models


def activity(number=1, **changes):
    row=dict(event_type='INSTALL_SUCCEEDED',outcome='SUCCEEDED',operation_id=f'00000000-0000-4000-8000-{number:012}',
             provider_id='bbbike',region='Lithuania',map_package_id='lt',model='Untrusted label',variant='Wrong variant')
    row.update(changes)
    return row


class Capture:
    def __init__(self, rows=()): self.rows=rows; self.calls=[]
    def execute(self, sql, params): self.calls.append((sql,params)); return self
    def fetchall(self): return self.rows


class ActivityModelTests(unittest.TestCase):
    def test_unresolved_rows_clear_labels_and_invalid_operation_never_queries(self):
        connection=Capture()
        original=activity(operation_id=None)
        result=_enrich_activity_models(connection,[original])
        self.assertIsNone(result[0]['model'])
        self.assertIsNone(result[0]['canonical_device_model_id'])
        self.assertEqual(original['model'],'Untrusted label')
        self.assertEqual(connection.calls,[])

    def test_one_batch_enrichment_preserves_event_and_population(self):
        connection=Capture([dict(index=0,canonical_device_model_id='exact',model='Catalog name',variant='47 mm',case_size_mm=47,screen_technology='AMOLED')])
        rows=[activity(event_id='event-id',map_result_index=0),activity(2,event_type='DOWNLOAD_SUCCEEDED')]
        result=_enrich_activity_models(connection,rows)
        self.assertEqual(len(connection.calls),1)
        self.assertEqual(json.loads(connection.calls[0][1][0])[0]['map_result_index'],0)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['event_id'],'event-id')
        self.assertEqual(result[0]['model'],'Catalog name')
        self.assertEqual(result[0]['display_type'],'AMOLED')
        self.assertEqual(result[1],rows[1])

    def test_exact_correlation_in_postgresql(self):
        module=os.environ.get('PGLITE_MODULE_PATH')
        if not module or not Path(module).exists(): self.skipTest('PGLITE_MODULE_PATH not configured')
        capture=Capture()
        _enrich_activity_models(capture,[activity()])
        sql=capture.calls[0][0].replace('%s','$1')
        result=subprocess.run([shutil.which('node'),str(Path(__file__).with_name('activity_models_postgres.cjs')),module],
                              input=json.dumps({'sql':sql}),text=True,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Activity exact correlation PASS',result.stdout)

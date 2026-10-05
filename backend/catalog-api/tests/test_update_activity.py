"""Retained update outcomes in Activity, independent of write-attempt KPIs."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import unittest

from terento_catalog.db import Database
from pglite_support import require_pglite


class Capture:
    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return self
    def fetchall(self):
        return []


class UpdateActivityTests(unittest.TestCase):
    def test_retained_not_started_query_with_conflicts_and_limits(self):
        capture = Capture()
        Database._update_not_started_activity(capture, datetime(2026, 10, 5, tzinfo=timezone.utc), 8)
        index = iter(range(1, 20))
        import re
        sql = re.sub(r'%s', lambda _: '$' + str(next(index)), capture.sql)
        result = subprocess.run(['node', str(Path(__file__).with_name('update_activity_postgres.cjs')), require_pglite(self)], input=json.dumps({'sql':sql}), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_activity_summary_is_authored_and_raw_payload_not_returned(self):
        class Rows(Capture):
            def fetchall(self):
                return [dict(outcome='UNKNOWN', payload={'failureCode':'UPDATE_FAILED_ACQUISITION', 'failureStage':'preflight', 'raw':'private'}, diagnostic_report_id='exact')]
        rows = Database._update_not_started_activity(Rows(), datetime.now(timezone.utc), 8)
        self.assertEqual(rows[0]['reason_summary'], 'Replacement preparation was blocked.')
        self.assertNotIn('payload', rows[0])

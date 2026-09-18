"""Exercise the actual review SQL with independent telemetry stream fixtures."""
from datetime import datetime, timezone
import sqlite3
import unittest

from test_admin_semantics import RecordingDatabase
from terento_catalog.admin import (
    _identity_is_pending,
    _is_preinstall_download_failure,
    _operation_is_problematic,
    _overview_operation_href,
    _overview_operation_label,
    overview_page,
)


class MissingDiagnosticReviewTests(unittest.TestCase):
    def test_only_unlinked_real_install_failures_need_diagnostics(self):
        recording = RecordingDatabase()
        recording.admin_overview_map_snapshot(datetime.now(timezone.utc))
        query, parameters = next(
            (sql, args) for sql, args in recording.calls
            if 'AS total_missing_diagnostics' in sql
        )
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE map_download_event(event_id TEXT, operation_id TEXT,
                provider_id TEXT, map_package_id TEXT, region TEXT, event_type TEXT,
                outcome TEXT, occurred_at TEXT, is_local_test BOOLEAN);
            CREATE TABLE map_provider(id TEXT, name TEXT);
            CREATE TABLE map_package(id TEXT, provider_id TEXT, name TEXT,
                provider_region_id TEXT, canonical_region_id TEXT, region TEXT);
            CREATE TABLE compatibility_evidence_event(operation_id TEXT,
                provider TEXT, region TEXT, phase_outcome TEXT, is_local_test BOOLEAN,
                diagnostic_status TEXT, map_result_index INTEGER);
            INSERT INTO map_provider VALUES ('fzk', 'Freizeitkarte');
            INSERT INTO map_package VALUES ('fr', 'fzk', 'France', 'FRA', 'FR', 'France');
        ''')
        def event(key, region='FR', event_type='INSTALL_FAILED', local=False):
            db.execute('INSERT INTO map_download_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (key, key, 'fzk', 'fr', region, event_type, 'FAILED', '2020-01-01', local))
        def diagnostic(key, region='FR', status='ACTIVE', provider='fzk', local=False,
                       map_result_index=0):
            db.execute('INSERT INTO compatibility_evidence_event VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (key, provider, region, 'FAILED', local, status, map_result_index))
        for key in ('missing', 'active', 'resolved', 'alias', 'other-region', 'other-provider', 'test-report'):
            event(key)
        diagnostic('active')
        diagnostic('resolved', status='RESOLVED')
        diagnostic('alias', region='FRA')
        diagnostic('other-region', region='DE')
        diagnostic('other-provider', provider='otm')
        diagnostic('test-report', local=True)
        event('download', event_type='DOWNLOAD_FAILED')
        event('local', local=True)
        rows = db.execute(query.replace('%s', '?'), parameters).fetchall()
        self.assertEqual({r['event_id'] for r in rows},
                         {'missing', 'other-region', 'other-provider', 'test-report'})
        self.assertTrue(all(r['total_missing_diagnostics'] == 4 for r in rows))
        # Arrival of the matching report removes the gap, even after resolution.
        diagnostic('missing', status='RESOLVED')
        rows = db.execute(query.replace('%s', '?'), (1,)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['total_missing_diagnostics'], 3)
        db.close()

    def test_overview_shows_missing_diagnostic_failure_without_faking_open_error(self):
        body = overview_page({
            'data': {'hasData': True, 'missingDiagnosticFailureCount': 1,
                     'missingDiagnosticFailures': [{
                         'event_type': 'INSTALL_FAILED', 'outcome': 'FAILED',
                         'provider_id': 'fzk', 'provider_name': 'Freizeitkarte',
                         'region': 'France', 'map_package_name': 'France',
                         'occurred_at': '2026-09-15T19:47:00Z',
                     }]},
            'compatibility': {'allTimeOpenErrorCount': 0},
        }, {'username': 'operator'}, 'csrf').decode()
        panel = body.split("aria-labelledby='overview-attention-title'>", 1)[1].split('</section>', 1)[0]
        self.assertIn('Install failed', panel)
        self.assertIn('No device diagnostic report received', panel)
        self.assertIn('Missing diagnostics <strong>1</strong>', panel)
        self.assertIn("Failure diagnostics <strong>—</strong>", panel)
        self.assertIn('period=all&amp;eventType=INSTALL_FAILED', panel)
        self.assertIn('France', panel)
        self.assertNotIn('overview-attention-empty', body)
class PreinstallDownloadFailureTests(unittest.TestCase):
    def test_preinstall_download_failure_is_activity_only(self):
        operation = {
            "model": "fēnix 9 Pro",
            "variant": "51 mm",
            "provider": "opentopomap",
            "error_category": "acquisition",
            "phase_outcome": "FAILED",
            "failure_stage": "download",
            "failure_code": "INSTALL_BLOCKED_DOWNLOAD_FAILED",
            "write_started": 0,
            "has_failed": True,
            "has_not_started": True,
            "operation_succeeded": False,
            "open_error": False,
            "identity_pending": False,
            "operation_id": "0c3a14fe-089c-4c06-bb8a-764642729b02",
        }

        self.assertTrue(_is_preinstall_download_failure(operation))
        self.assertFalse(_operation_is_problematic([operation]))
        self.assertFalse(_identity_is_pending([operation]))
        self.assertEqual(_overview_operation_label(operation), ("Download failed", "failed"))
        self.assertNotIn("state=", _overview_operation_href(operation))

        body = overview_page(
            {
                "data": {"hasData": False},
                "compatibility": {
                    "hasData": True,
                    "allTimeOpenErrorCount": 1,
                    "attention": [],
                    "recentActivity": [operation],
                },
            },
            {"username": "operator"},
            "csrf",
        ).decode()
        panel = body.split("aria-labelledby='overview-attention-title'>", 1)[1].split(
            "</section>", 1
        )[0]
        self.assertNotIn("fēnix 9 Pro", panel)
        self.assertIn("Download failed", body)

    def test_aggregated_preinstall_download_failure_flag_is_not_review(self):
        operation = {
            "preinstall_download_failure": True,
            "phase_outcome": "FAILED",
            "has_failed": True,
            "identity_pending": True,
        }
        self.assertTrue(_is_preinstall_download_failure(operation))
        self.assertFalse(_operation_is_problematic([operation]))
        self.assertFalse(_identity_is_pending([operation]))


if __name__ == "__main__":
    unittest.main()

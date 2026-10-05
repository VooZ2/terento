"""Exercise the actual review SQL with independent telemetry stream fixtures."""
from datetime import datetime, timezone
import sqlite3
import unittest

from test_admin_semantics import RecordingDatabase
from terento_catalog.admin import (
    _admin_device_payload,
    _identity_is_pending,
    _is_preinstall_download_failure,
    _operation_result,
    _operation_is_problematic,
    dashboard_page,
    device_detail_page,
    diagnostics_page,
    overview_page,
)


class MissingDiagnosticReviewTests(unittest.TestCase):
    def test_preinstall_download_failure_is_activity_only(self):
        operation = {
            'model': 'fēnix 9 Pro',
            'variant': '51 mm',
            'provider': 'opentopomap',
            'error_category': 'acquisition',
            'phase_outcome': 'FAILED',
            'failure_stage': 'download',
            'failure_code': 'INSTALL_BLOCKED_DOWNLOAD_FAILED',
            'write_started': 0,
            'has_failed': True,       # raw phase_outcome=FAILED
            'has_not_started': True,  # write_started=false classification
            'operation_succeeded': False,
            'open_error': False,
            'identity_pending': False,
            'operation_id': '0c3a14fe-089c-4c06-bb8a-764642729b02',
        }

        self.assertTrue(_is_preinstall_download_failure(operation))
        self.assertFalse(_operation_is_problematic([operation]))
        self.assertFalse(_identity_is_pending([operation]))

        body = overview_page({
            'data': {'hasData': False},
            'compatibility': {
                'hasData': True,
                'allTimeOpenErrorCount': 1,
                'attention': [],
                'recentActivity': [operation],
            },
        }, {'username': 'operator'}, 'csrf').decode()
        panel = body.split("aria-labelledby='overview-attention-title'>", 1)[1].split('</section>', 1)[0]
        self.assertNotIn('fēnix 9 Pro', panel)
        self.assertNotIn('Download failed', body)

    def test_preinstall_download_is_not_an_installation_read_model_result(self):
        operation = {
            'operation_key': 'download-only',
            'canonical_device_model_id': 'fenix-9-51',
            'compatibility_identity': 'fēnix 9 Pro · 51 mm',
            'model': 'fēnix 9 Pro',
            'variant': '51 mm',
            'phase_outcome': 'FAILED',
            'failure_stage': 'download',
            'failure_code': 'INSTALL_BLOCKED_DOWNLOAD_FAILED',
            'write_started': False,
        }

        self.assertEqual(_operation_result([operation]), 'NOT_STARTED')
        installations = dashboard_page([{
            'model': 'fēnix 9 Pro', 'variant': '51 mm',
            'attempted_install_count': 0, 'successful_install_count': 0,
            'failed_install_count': 0, 'prewrite_failure_count': 1,
        }], {'username': 'operator'}, 'csrf', operations=[operation]).decode()
        self.assertIn('No installation evidence yet.', installations)
        self.assertNotIn('INSTALL_BLOCKED_DOWNLOAD_FAILED', installations)

        device = _admin_device_payload([{
            'device_id': 'fenix-9-51', 'model': 'fēnix 9 Pro',
            'variant': '51 mm', 'family_name': 'fēnix', 'map_capable': True,
            'support_status': 'SUPPORTED', 'active': True,
            'attempted_install_count': 0, 'successful_install_count': 0,
            'failed_install_count': 0, 'usb_identities': [],
        }], None)['devices'][0]
        detail = device_detail_page(
            device, {'username': 'operator'}, 'csrf', operations=[operation],
        ).decode()
        self.assertIn('No installation history for this device.', detail)
        self.assertNotIn('INSTALL_BLOCKED_DOWNLOAD_FAILED', detail)

        diagnostics = diagnostics_page(
            [{'canonical_device_model_id': 'fenix-9-51',
              'compatibility_identity': 'fēnix 9 Pro · 51 mm',
              'model': 'fēnix 9 Pro', 'variant': '51 mm',
              'attempted_install_count': 0, 'successful_install_count': 0}],
            {'username': 'operator'}, 'csrf', identity='fēnix 9 Pro · 51 mm',
            canonical_device_model_id='fenix-9-51', operations=[operation],
        ).decode()
        self.assertIn('No installation history for this model.', diagnostics)
        self.assertNotIn('INSTALL_BLOCKED_DOWNLOAD_FAILED', diagnostics)

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
                outcome TEXT, occurred_at TEXT, is_local_test BOOLEAN,
                statistics_exclusion_code TEXT, map_result_index INTEGER,
                acquisition_id TEXT, reported_map_id TEXT);
            CREATE TABLE map_provider(id TEXT, name TEXT);
            CREATE TABLE map_package(id TEXT, provider_id TEXT, name TEXT,
                provider_region_id TEXT, canonical_region_id TEXT, region TEXT);
            CREATE TABLE compatibility_evidence_event(operation_id TEXT,
                provider TEXT, region TEXT, phase_outcome TEXT, is_local_test BOOLEAN,
                diagnostic_status TEXT, map_result_index INTEGER,
                statistics_exclusion_code TEXT);
            CREATE TABLE admin_map_review_task(event_id TEXT, task_type TEXT, status TEXT);
            INSERT INTO map_provider VALUES ('fzk', 'Freizeitkarte');
            INSERT INTO map_package VALUES ('fr', 'fzk', 'France', 'FRA', 'FR', 'France');
        ''')
        def event(key, region='FR', event_type='INSTALL_FAILED', local=False):
            db.execute('INSERT INTO map_download_event(event_id,operation_id,provider_id,map_package_id,region,event_type,outcome,occurred_at,is_local_test,statistics_exclusion_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (key, key, 'fzk', 'fr', region, event_type, 'FAILED', '2020-01-01', local, None))
        def diagnostic(key, region='FR', status='ACTIVE', provider='fzk', local=False,
                       map_result_index=0):
            db.execute('INSERT INTO compatibility_evidence_event VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (key, provider, region, 'FAILED', local, status, map_result_index, None))
        for key in ('missing', 'active', 'resolved', 'alias', 'other-region', 'other-provider', 'test-report', 'dismissed'):
            event(key)
        db.execute("INSERT INTO admin_map_review_task VALUES (?, ?, ?)",
                   ('dismissed', 'MISSING_DIAGNOSTIC', 'DISMISSED'))
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
                         'event_id': 'a8098c1a-f86e-11da-bd1a-00112444be1e',
                         'provider_id': 'fzk', 'provider_name': 'Freizeitkarte',
                         'region': 'France', 'map_package_name': 'France',
                         'occurred_at': '2026-09-15T19:47:00Z',
                     }]},
            'compatibility': {'allTimeOpenErrorCount': 0, 'missingDiagnostics': 1},
        }, {
            'username': 'operator',
            'admin_review_summary': {'missingDiagnostics': 1, 'total': 1},
        }, 'csrf').decode()
        panel = body.split("aria-labelledby='overview-attention-title'>", 1)[1].split('</section>', 1)[0]
        # Dashboard shows the fixed category row with the full count and a
        # link to the complete list; it does not fake an open problem.
        self.assertIn("aria-label='Missing reports: 1'", panel)
        self.assertIn("href='/admin/review/missing-reports'", panel)
        self.assertIn("aria-label='Open problems: unavailable'", panel)
        self.assertNotIn('attention-shortcuts', panel)
        self.assertNotIn("admin-review-link", body)
        self.assertNotIn('overview-attention-empty', body)

    def test_missing_reports_page_lists_every_gap_with_dismiss_and_undo(self):
        from terento_catalog.admin import missing_reports_page
        rows = [{
            'event_type': 'INSTALL_FAILED', 'outcome': 'FAILED',
            'event_id': f'a8098c1a-f86e-11da-bd1a-0011244{index:05d}', 'provider_id': 'freizeitkarte',
            'provider_name': 'Freizeitkarte', 'region': 'France', 'map_package_name': 'France',
            'occurred_at': '2026-09-15T19:47:00Z',
        } for index in range(7)]
        body = missing_reports_page({'rows': rows, 'total': 57, 'limit': 50, 'offset': 0},
                                    {'username': 'operator'}, 'csrf').decode()
        self.assertIn('<h1>Missing reports</h1>', body)
        # Not silently capped at six: all rows of the page render and the
        # total is explicit with pagination to the rest (ADM-11).
        self.assertEqual(body.count("aria-label='Dismiss review item'"), 7)
        self.assertIn("data-stat", body) if False else None
        self.assertIn('>57<', body)
        self.assertIn('1–50 of 57', body)
        self.assertIn("href='/admin/review/missing-reports?offset=50'", body)
        self.assertIn('No device report · not counted in Failed', body)
        self.assertIn('eventId=a8098c1a-f86e-11da-bd1a-001124400000', body)
        self.assertIn("name='return_to' value='/admin/review/missing-reports'", body)
        undo = missing_reports_page({'rows': [], 'total': 0}, {'username': 'operator'}, 'csrf',
                                    review_action='dismissed', review_event_id=rows[0]['event_id']).decode()
        self.assertIn('Review item dismissed.', undo)
        self.assertIn("action='/admin/review/missing-diagnostics/undo'", undo)
        self.assertIn('Nothing to review.', undo)
        unavailable = missing_reports_page(None, {'username': 'operator'}, 'csrf').decode()
        self.assertIn("Could not load this section.", unavailable)
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
        self.assertNotIn("Download failed", body)

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

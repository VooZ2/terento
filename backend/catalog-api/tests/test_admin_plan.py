"""Approved Admin plan regressions: population, revision and duration boundaries."""
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import unittest

from terento_catalog.admin import (_download_time_markup, _overview_map_activity_row,
    dashboard_page, overview_page, providers_page, provider_detail_page, system_health_page,
    map_statistics_page, devices_page, _diagnostic_summary_by_identity)
from terento_catalog import admin
from terento_catalog.admin_revisions import section_revisions, statistics_revisions
from terento_catalog.db import Database


class CaptureDB(Database):
    @contextmanager
    def connection(self):
        yield self
    def execute(self, query, values=()):
        self.query, self.values = query, values
        return self
    def fetchall(self):
        return []


class AdminPlanTests(unittest.TestCase):
    def test_duration_format_and_missing(self):
        for seconds, expected in [(277, '04:37'), (8, '00:08'), (3912, '65:12'), (0, '00:00'), (59.5, '01:00'), (None, '—'), (-1, '—')]:
            with self.subTest(seconds=seconds):
                markup = _download_time_markup({'averageSeconds': seconds, 'sampleCount': 3, 'populationCount': 8}, 'Last 30 days')
                self.assertIn('>' + expected + '<small', markup)
                self.assertIn('3 measured of 8', markup)
                self.assertIn('3 downloads</small>', markup)
                self.assertNotIn('n=3', markup)
                self.assertIn("tabindex='0'", markup)
                self.assertIn('Processing minus Started', markup)

    def test_revisions_ignore_observation_noise_and_order(self):
        a = {'rows': [{'operation_id':'op', 'map_result_index':0, 'event_id':'a', 'occurred_at':'2026-09-17', 'result':'FAILED'}], 'generatedAt':'a', 'health': {'checked_at':'a', 'status':'HEALTHY'}}
        b = {'rows': [dict(a['rows'][0], event_id='b'), a['rows'][0]], 'generatedAt':'b', 'health': {'checked_at':'b', 'status':'HEALTHY'}}
        self.assertEqual(section_revisions({'view':a}), section_revisions({'view':b}))
        b['health']['status'] = 'WARNING'
        self.assertNotEqual(section_revisions({'view':a}), section_revisions({'view':b}))
        self.assertEqual(section_revisions({'rows':[1,2]}), section_revisions({'rows':[2,1]}))
        self.assertNotEqual(section_revisions({'rows':[1,2]}), section_revisions({'rows':[1,2,3]}))

    def test_download_poll_and_scheduler_heartbeats_are_not_new_activity(self):
        a = {'downloads': {'dmgTotal': 10, 'zipTotal': 2, 'lastObservedAt':'a', 'trend': []},
             'scheduler': {'status':'HEALTHY','completed_at':'a','next_run_at':'b'}}
        b = {'downloads': {'dmgTotal': 10, 'zipTotal': 2, 'lastObservedAt':'b',
             'trend': [{'state':'observed_zero','bucket':'b','dmg_count':0,'zip_count':0}]},
             'scheduler': {'status':'RUNNING','completed_at':'b','next_run_at':'c'}}
        self.assertEqual(section_revisions(a), section_revisions(b))
        b['downloads']['dmgTotal'] = 11
        self.assertNotEqual(section_revisions(a)['downloads'], section_revisions(b)['downloads'])
        b['scheduler']['status'] = 'STALE'
        self.assertNotEqual(section_revisions(a)['scheduler'], section_revisions(b)['scheduler'])

    def test_download_revision_detects_interval_semantics_without_observation_noise(self):
        a = {'downloads': {
            'dmgTotal': 269, 'zipTotal': 59, 'lastObservedAt': 'first',
            'trend': [{'bucket': '2026-09-21T17:00:00Z', 'state': 'discontinuity',
                       'dmg_count': None, 'zip_count': None}],
        }}
        b = {'downloads': {
            'dmgTotal': 269, 'zipTotal': 59, 'lastObservedAt': 'second',
            'trend': [{'bucket': '2026-09-21T17:00:00Z', 'state': 'observed_increase',
                       'dmg_count': 1, 'zip_count': 2}],
        }}
        self.assertNotEqual(section_revisions(a)['downloads'], section_revisions(b)['downloads'])

    def test_identity_history_scopes_before_limit_and_requires_identity(self):
        db = CaptureDB('unused')
        with self.assertRaises(ValueError):
            db.compatibility_identity_details('ACTIVE')
        db.compatibility_identity_details('ACTIVE', device_id='exact-model')
        self.assertNotIn('LIMIT', db.query.split('ORDER BY occurred_at DESC')[-1])
        self.assertIn('canonical_device_model_id = %s', db.query)
        self.assertEqual(db.values, ('ACTIVE', 'exact-model'))
        db.compatibility_identity_details('RESOLVED', identity='Unknown variant')
        self.assertIn('canonical_device_model_id IS NULL', db.query)
        self.assertEqual(db.values, ('RESOLVED', 'Unknown variant'))

    def test_section_acknowledgement_has_separate_populations(self):
        a = statistics_revisions({'rows':[{'event_count':2}], 'detailRows':[{'event_count':1}]})
        b = statistics_revisions({'rows':[{'event_count':2}], 'detailRows':[{'event_count':2}]})
        self.assertEqual(a['statistics'], b['statistics'])
        self.assertNotEqual(a['eventDetail'], b['eventDetail'])

    def test_all_activity_outcomes_have_text_icon_and_semantic_color(self):
        tones = {'DOWNLOAD_STARTED':'info','DOWNLOAD_PROCESSING':'info','DOWNLOAD_SUCCEEDED':'success',
            'DOWNLOAD_FAILED':'error','DOWNLOAD_CANCELLED':'neutral','DOWNLOAD_INTERRUPTED':'warning',
            'INSTALL_SUCCEEDED':'success','INSTALL_FAILED':'error','MAP_UPDATE_SUCCEEDED':'success','MAP_UPDATE_FAILED':'error','UNKNOWN':'neutral'}
        for event, tone in tones.items():
            with self.subTest(event=event):
                markup = _overview_map_activity_row({'event_type':event})
                self.assertIn('map-activity-' + tone, markup)
                self.assertIn('<svg', markup)
                self.assertNotIn('animation:', markup)

    def test_more_than_500_diagnostics_are_summarized_without_browser_history(self):
        events = [{'operation_id':f'op-{i}', 'map_result_index':0, 'canonical_device_model_id':'garmin',
                   'phase_outcome':'FAILED', 'write_started':True, 'diagnostic_status':'ACTIVE'} for i in range(701)]
        summary = _diagnostic_summary_by_identity(events + [events[0]])
        self.assertEqual(summary['canonical:garmin']['open_errors'], 701)
        markup = dashboard_page([{'model':'fēnix 8', 'canonical_device_model_id':'garmin'}], {}, 'csrf', diagnostic_summary=summary).decode()
        self.assertIn("data-errors='701'", markup)
        self.assertNotIn('op-700', markup)
        db = CaptureDB('unused'); db.compatibility_diagnostic_population()
        self.assertNotIn('LIMIT', db.query)
        for field in ('write_started','map_result_index','identity_resolution_state','is_local_test'):
            self.assertIn(field, db.query)

    def test_all_page_headers_are_title_only(self):
        user = {'username':'test'}
        pages = [overview_page({},user,'csrf'),dashboard_page([],user,'csrf'),providers_page([],user,'csrf'),
            provider_detail_page({'id':'test','name':'Long Authentic Provider Name'},[],[],user,'csrf'),
            system_health_page({},user,'csrf'), map_statistics_page({'rows':[]},[],user,'csrf'),devices_page([],None,user,'csrf')]
        pages += [admin.account_page(user,'csrf',error='Keep this warning'),
            admin.campaign_links_page(user,'csrf'), admin.device_detail_page({},user,'csrf'),
            admin.device_identification_page([],user,'csrf'),
            admin.diagnostics_page([],user,'csrf',identity='Unknown'),
            admin.github_issue_queue_page([],[],user,'csrf'),
            admin.local_test_data_page({},user,'csrf'),
            admin.login_page(error='Keep login warning'), admin.setup_page(error='Keep setup warning')]
        class Headings(HTMLParser):
            def __init__(self):
                super().__init__(); self.tag=None; self.current=[]; self.titles=[]
            def handle_starttag(self, tag, attrs):
                if tag in {'h1','h2','h3','h4','h5','h6'}:
                    self.tag=tag; self.current=[]
            def handle_data(self, data):
                if self.tag: self.current.append(data)
            def handle_endtag(self, tag):
                if tag == self.tag:
                    self.titles.append(''.join(self.current).strip()); self.tag=None
        for page in pages:
            text = page.decode().split('</style>',1)[-1]
            headings = Headings(); headings.feed(text)
            for title in headings.titles:
                if title == 'Long Authentic Provider Name': continue
                self.assertLessEqual(len([word for word in title.split() if word != 'by']), 3, title)
            for klass in ('eyebrow','section-kicker','detail-kicker'):
                self.assertNotRegex(text, r'class=[\'\"][^\'\"]*\b'+klass+r'\b')
        self.assertIn(b'Keep this warning', pages[7])
        self.assertIn(b'Keep login warning', pages[-2])
        self.assertIn(b'Long Authentic Provider Name', pages[3])
        self.assertNotIn(b'Compatibility evidence \xc2\xb7 details and activity', pages[0])

    def test_timing_query_uses_full_phase_population_and_completion_filters(self):
        db = CaptureDB('unused')
        db.provider_download_times({'dateFrom':'2026-09-01','provider':'test','eventType':'INSTALL_FAILED','outcome':'FAILED'})
        self.assertEqual(db.values, ['test','2026-09-01'])
        self.assertNotIn('LIMIT', db.query)
        self.assertIn('SELECT DISTINCT', db.query)
        self.assertIn('count(*) = 3', db.query)
        self.assertIn("e.component_kind, e.event_type, e.outcome, e.occurred_at", db.query)

    @unittest.skipUnless(os.environ.get('TERENTO_PGLITE_MODULE'), 'Set TERENTO_PGLITE_MODULE for isolated PostgreSQL query execution')
    def test_download_time_sql_on_isolated_postgresql(self):
        db = CaptureDB('unused'); db.provider_download_times({'dateFrom':'2026-09-01','eventType':'INSTALL_FAILED'})
        script = Path(__file__).with_name('admin_download_time_postgres.cjs')
        result = subprocess.run(['node', str(script), os.environ['TERENTO_PGLITE_MODULE']], input=json.dumps({'query':db.query.replace('%s','$1'), 'values':db.values}), text=True, capture_output=True, check=True)
        data = json.loads(result.stdout)
        self.assertNotIn('custom', [r['provider_id'] for r in data])
        main = next(r for r in data if r['provider_id']=='test')
        self.assertEqual(int(main['sample_count']), 5)
        self.assertAlmostEqual(float(main['average_seconds']), (8+277+3912+0+20)/5)
        self.assertEqual(int(main['population_count']), 14)
        other = next(r for r in data if r['provider_id']=='other')
        self.assertEqual(float(other['average_seconds']), 7)

if __name__ == '__main__': unittest.main()

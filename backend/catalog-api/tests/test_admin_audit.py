"""Regression cases from the authenticated September 7 admin audit."""
from datetime import datetime, timezone
from html.parser import HTMLParser
from contextlib import contextmanager
from pathlib import Path
import os
import subprocess
import unittest

from terento_catalog.admin import (
    _admin_map_display_name, _admin_region_identity, _system_health_card,
    _overview_map_event_context, provider_detail_page, local_test_data_page,
    _admin_disclosure_script,
)
from terento_catalog.admin_world_map import WORLD_MAP_COUNTRY_ALIASES
from terento_catalog.telemetry import is_local_release_label
from terento_catalog.db import Database


class Tags(HTMLParser):
    def __init__(self, markup):
        super().__init__(); self.tags = []; self.feed(markup)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class AdminAuditTests(unittest.TestCase):
    def test_health_disclosure_defaults_and_escaped_evidence(self):
        for state in ('HEALTHY', 'FAILED', 'WARNING', 'UNKNOWN', None):
            with self.subTest(state=state):
                card = _system_health_card('API <test>', state, '<p>Live check</p>',
                    {'observed_at':'2026-09-07T16:43:00Z'}, reason='failure', action='inspect')
                attrs = next(attrs for tag,attrs in Tags(card['html']).tags if tag=='details')
                self.assertEqual('open' in attrs, state != 'HEALTHY')
                self.assertIn('API &lt;test&gt;',card['html'])
                self.assertIn('Evidence recorded:',card['html'])

    def test_provider_explains_mixed_releases_without_relabelling_packages(self):
        body = provider_detail_page({'provider':{'id':'opentopomap','maps':[
            {'id':'albania','release':'2026-05','availability':'AVAILABLE'},
            {'id':'algeria','release':'2026-08','availability':'AVAILABLE'},
            {'id':'old','release':'2026-01','availability':'RETIRED'},
        ]}}, [{'status':'SUCCEEDED','release_change_detected':False,'latest_release':'2026-08'}], [], {'username':'audit'},'csrf').decode()
        self.assertIn('2026-08: 1 packages',body)
        self.assertIn('2026-05: 1 packages',body)
        self.assertNotIn('2026-01: 1 packages',body)
        self.assertIn('No release change detected',body)
        self.assertIn('Each region keeps its own provider release.',body)

    def test_svn_and_pol_aliases_and_distinct_islands(self):
        for code,name,country in [('SVN+','Slovenia','si'),('POL+','Poland','pl'),('CHE+','Switzerland','ch')]:
            with self.subTest(code=code):
                self.assertEqual(_admin_map_display_name(code),name)
                self.assertEqual(_admin_region_identity(None,None,code),name.upper())
                self.assertEqual(WORLD_MAP_COUNTRY_ALIASES[code.rstrip('+')],country)
        self.assertEqual(_admin_region_identity(None,'PT','AZORES'),'AZORES')
        self.assertEqual(_admin_region_identity(None,'PT','MADEIRA'),'MADEIRA')
        self.assertNotEqual(_admin_region_identity(None,'PT','AZORES'),_admin_region_identity(None,'PT','MADEIRA'))
        self.assertEqual(_admin_region_identity(None,None,'POL+'),_admin_region_identity(None,'PL','POLAND'))
        self.assertEqual(_admin_region_identity('USA-CALIFORNIA','US','CALIFORNIA'),'USACALIFORNIA')

    def test_overview_fallback_keeps_region_readable(self):
        self.assertEqual(_overview_map_event_context({'region':'SVN+','provider_name':'Freizeitkarte'}),'Slovenia · Freizeitkarte')

    def test_local_dashboard_shows_flag_and_latest_result_without_raw_logs(self):
        body=local_test_data_page({'activity':[{'stream':'Map usage','release_label':'1.0.0-beta.10-local','outcome':'FAILED','event_count':2,'last_occurred_at':'2026-09-07T16:43:00Z'}]}, {'username':'audit'},'csrf').decode()
        for text in ('is_local_test=true','is_local_test=false','FAILED','Distinct operations','Latest local activity'):
            self.assertIn(text,body)

    def test_build_guard_separates_debug_and_public_release(self):
        guard=Path(__file__).resolve().parents[3]/'Packaging'/'verify-release-label.sh'
        for configuration,label,allowed in [('Debug','1.0.0-beta.10-local',True),('Debug','1.0.0-beta.9',False),('Debug','',False),('Release','1.0.0-beta.9',True),('Release','1.0.0-beta.10-local',False),('Release','development',False)]:
            with self.subTest(configuration=configuration,label=label):
                result=subprocess.run(['/bin/sh',str(guard)],env={**os.environ,'CONFIGURATION':configuration,'TERENTO_RELEASE_LABEL':label},capture_output=True)
                self.assertEqual(result.returncode==0,allowed)
                if allowed:
                    self.assertEqual(is_local_release_label(label),configuration=='Debug')

    def test_disclosure_navigation_script_syntax(self):
        result=subprocess.run([os.environ.get('TERENTO_NODE_BIN','node'),'--check'],input=_admin_disclosure_script(),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_filtered_fallback_preserves_all_regions_of_complete_operations(self):
        calls = []
        class Result:
            def fetchall(self): return []
        class Connection:
            def execute(self, query, parameters):
                calls.append((query, parameters)); return Result()
        class QueryDatabase(Database):
            @contextmanager
            def connection(self): yield Connection()
        QueryDatabase('unused').map_statistics({'region':'SVN+'})
        query, parameters = calls[0]
        # Region filtering cannot turn one result of an incomplete two-map
        # operation into a complete install, or drop its other map region.
        complete, filtered = query.split('), compatibility_fallback AS (', 1)
        self.assertIn("count(*) = max(COALESCE(e.selected_map_count, 1))", complete)
        self.assertIn('installed.is_local_test IS NOT TRUE', complete)
        self.assertNotIn('e.region = %s', complete)
        self.assertIn('e.region = %s', filtered)
        self.assertIn('GROUP BY c.operation_key, e.provider, e.region', filtered)
        self.assertEqual(tuple(parameters), ('SVN+', 'SVN+'))

if __name__=='__main__': unittest.main()

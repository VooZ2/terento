"""Regression cases from the authenticated September 7 admin audit."""
from datetime import datetime, timezone
from collections import Counter
from html.parser import HTMLParser
from contextlib import contextmanager
from pathlib import Path
import os
import subprocess
import unittest

from terento_catalog.admin import (
    _admin_map_display_name, _admin_region_display_name, _admin_region_identity, _system_health_card,
    _overview_map_event_context, provider_detail_page, local_test_data_page,
    _admin_disclosure_script,
    map_statistics_page, _identity_parts, _dashboard_script,
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
    def test_overview_kpis_match_installation_card_density(self):
        from terento_catalog.admin import ADMIN_STYLES

        self.assertIn(
            '.overview-kpi{display:flex;min-height:84px;flex-direction:column;justify-content:flex-start;padding:14px 16px;',
            ADMIN_STYLES,
        )
        self.assertIn(
            '.overview-kpi{min-height:80px;padding:12px}',
            ADMIN_STYLES,
        )

    def test_overview_model_activity_matches_chart_height_and_scrolls(self):
        from terento_catalog.admin import ADMIN_STYLES

        self.assertIn('.overview-primary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}', ADMIN_STYLES)
        self.assertIn('.overview-primary-grid,.overview-secondary-grid{align-items:stretch}', ADMIN_STYLES)
        self.assertIn(
            '.overview-secondary-grid>.overview-panel{display:flex;min-height:0;max-height:320px;flex-direction:column;overflow:hidden}',
            ADMIN_STYLES,
        )
        self.assertIn(
            '.overview-secondary-grid .overview-activity-list,.overview-secondary-grid .overview-model-list{flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain}',
            ADMIN_STYLES,
        )

    def test_inline_filter_controls_do_not_inherit_vertical_flex_basis(self):
        from terento_catalog.admin import ADMIN_STYLES
        # Labels became columns: the old select flex-basis (170px) must not
        # become a height. Reset both input and select, including tablet sizes.
        self.assertIn('.inline-filter-row label>input,.inline-filter-row label>select{flex:none}', ADMIN_STYLES)
        self.assertIn('.inline-filter-row label>input,.inline-filter-row label>select{width:100%;height:var(--admin-control-height)}', ADMIN_STYLES)
        self.assertIn('.inline-filter-row{align-items:flex-end}', ADMIN_STYLES)
        self.assertIn('@media(max-width:700px){.inline-filter-row{align-items:stretch}.inline-filter-row label{flex-basis:auto}}', ADMIN_STYLES)

    def test_identity_search_exposes_results_without_opening_select(self):
        from terento_catalog.admin import _diagnostics_script, _diagnostic_detail_dialog
        markup = _diagnostic_detail_dialog('Unknown', 'test', [{'phase_outcome': 'FAILED'}], resolved=False, csrf_token='test', identity_devices=[])
        self.assertIn('data-identity-results', markup)
        script = _diagnostics_script()
        self.assertIn("button.type = 'button'", script)
        self.assertIn('canonical.value = option.value;', script)
        self.assertIn('suggestions.hidden = !query;', script)
        self.assertIn("empty.textContent = 'No models match your search'", script)

    def test_github_actions_share_alignment_without_form_button_margin(self):
        from terento_catalog.admin import _layout
        markup = _layout('Test', '').decode()
        self.assertIn('.github-actions>.secondary-button{display:inline-flex;align-items:center;justify-content:center;margin:0;align-self:stretch;text-align:center;text-decoration:none;white-space:normal}', markup)
        self.assertIn('.github-actions>.copy-status{flex-basis:100%}', markup)

    def test_mobile_chart_keeps_last_bucket_and_unique_clip_ids(self):
        import re
        import xml.etree.ElementTree as ET
        from terento_catalog.admin import _overview_trend_chart
        trend = [{"bucket": f"2026-09-10T{hour:02d}:00:00Z", "custom_count": int(hour == 23)} for hour in range(24)]
        markup = _overview_trend_chart(trend, 'hour')
        charts = [ET.fromstring(svg) for svg in re.findall(r'<svg.*?</svg>', markup)]
        self.assertEqual(len(charts), 2)
        ids = [node.attrib['id'] for chart in charts for node in chart.iter() if 'id' in node.attrib]
        self.assertEqual(len(ids), len(set(ids)))
        for chart in charts:
            bars = [node for node in chart.iter('rect') if node.attrib.get('class') == 'overview-chart-custom']
            self.assertEqual(len(bars), 1)
            self.assertIn('23:00', bars[0].attrib['aria-label'])
            width = float(chart.attrib['viewBox'].split()[2])
            self.assertLess(float(bars[0].attrib['x']) + float(bars[0].attrib['width']), width)
        self.assertEqual(charts[1].attrib['viewBox'], '0 0 360 220')
        self.assertIn('No map install operations', _overview_trend_chart([], 'hour'))

    def test_identity_uses_required_native_select_with_exact_ids(self):
        from terento_catalog.admin import _diagnostic_detail_dialog
        markup = _diagnostic_detail_dialog('Unknown', 'preview', [{'phase_outcome': 'FAILED'}],
            resolved=False, csrf_token='preview', identity_devices=[
                {'device_id': 'fenix-43', 'model': 'fēnix 8', 'variant': '43 mm'},
                {'device_id': 'fenix-51', 'model': 'fēnix 8', 'variant': '51 mm'},
                {'device_id': 'safe-id', 'model': '<unsafe>'}])
        tags = Tags(markup).tags
        selects = [attrs for tag, attrs in tags if tag == 'select' and attrs.get('name') == 'canonical_device_model_id']
        self.assertEqual(len(selects), 1)
        self.assertIn('required', selects[0])
        self.assertNotIn('<datalist', markup)
        self.assertIn("value='fenix-43'", markup)
        self.assertIn("value='fenix-51'", markup)
        self.assertIn('&lt;unsafe&gt;', markup)

    def test_control_alignment_typography_and_coverage_focus(self):
        body = map_statistics_page({"rows": []}, [], {"username": "audit"}, "csrf").decode()
        for rule in (".filter-bar>.filter-disclosure{align-self:flex-end}",
                     ".filter-bar input,.filter-bar select{font-weight:400}",
                     ".filter-bar .device-mobile-sort{display:flex;flex-direction:column;gap:6px}",
                     "coverage-map-v1.js?v=20260911-osm-boundaries-1"):
            self.assertIn(rule, body)
        result = subprocess.run([os.environ.get('TERENTO_NODE_BIN', 'node'),
                                 str(Path(__file__).with_name('coverage-map-tests.cjs'))],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_post_audit_layout_copy_and_recovery_contract(self):
        body = map_statistics_page({"rows": []}, [], {"username": "audit"}, "csrf").decode()
        for text in ("Completed downloads", "Download success", "Completed map-package installs",
                     "Package install success", "View all map activity",
                     "No maps match your search", "flex-direction:column", "min-width:960px"):
            self.assertIn(text, body)
        self.assertNotIn("<strong data-stat='providerIssues'>", body)
        self.assertNotIn("installSuccessFraction", body)
        self.assertNotIn("opted-in", body)
        self.assertNotIn("table-layout:fixed}", body.split("@media(min-width:701px){", 1)[1].split("}", 1)[0])
        self.assertIn("min-height:44px", body)
        self.assertIn(".popularity-all-maps-disclosure .disclosure-body>label", body)
        self.assertIn("installation-empty", _dashboard_script())

    def test_display_cleanup_keeps_identity_and_functional_name(self):
        identity = "fēnix 9 Pro · inReach, · 51 mm"
        model, variant, unchanged = _identity_parts({"model": "fēnix 9 Pro · inReach,", "variant": "51 mm", "compatibility_identity": identity})
        self.assertEqual((model, variant, unchanged), ("fēnix 9 Pro · inReach", "51 mm", identity))
        self.assertEqual(_identity_parts({"model": "fēnix 8 51 mm", "variant": "51 mm"})[0], "fēnix 8")

    def test_map_statistics_has_one_dom_target_per_component(self):
        for rows in ([], [{"provider_id": "freizeitkarte", "event_type": "INSTALL_SUCCEEDED",
                           "outcome": "SUCCEEDED", "operation_count": 2}]):
            with self.subTest(has_data=bool(rows)):
                body = map_statistics_page({"rows": rows}, [], {"username": "audit"}, "csrf").decode()
                ids = Counter(attrs["id"] for _, attrs in Tags(body).tags if "id" in attrs)
                self.assertEqual({key: count for key, count in ids.items() if count > 1}, {})
                for target in ("map-statistics-metrics", "map-statistics-coverage",
                               "provider-statistic-rows", "world-map-svg", "map-rows"):
                    self.assertEqual(ids[target], 1, target)
                self.assertEqual(body.count("Counts map packages, not watches. One installation can include several packages. Success rates use completed outcomes (successful + failed), excluding operations still in progress. Compatibility evidence is counted separately."), 1)

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
        self.assertEqual(_admin_map_display_name('Suisse'), 'Switzerland')
        self.assertEqual(_admin_region_identity(None, 'CH', 'Suisse'), 'SWITZERLAND')
        self.assertEqual(_admin_map_display_name('CZECHREPUBLIC'), 'Czechia')
        self.assertEqual(_admin_map_display_name('CAROLINEDUNORD'), 'North Carolina')
        self.assertEqual(_admin_region_identity('CZECHREPUBLIC', 'CZ', 'CZECHREPUBLIC'), 'CZECHIA')
        self.assertEqual(
            _admin_region_display_name('CAROLINEDUNORD', 'US', 'CAROLINEDUNORD', 'North Carolina'),
            'North Carolina – United States',
        )
        self.assertEqual(
            _admin_region_display_name('CZECHREPUBLIC', 'CZ', 'CZECHREPUBLIC', 'Czechia'),
            'Czechia',
        )
        self.assertEqual(
            _overview_map_event_context({
                'display_name': 'Switzerland',
                'region': 'Suisse',
                'provider_name': 'MapRando',
            }),
            'Switzerland · MapRando',
        )
        self.assertEqual(_admin_region_identity(None,'PT','AZORES'),'AZORES')
        self.assertEqual(_admin_region_identity(None,'PT','MADEIRA'),'MADEIRA')
        self.assertNotEqual(_admin_region_identity(None,'PT','AZORES'),_admin_region_identity(None,'PT','MADEIRA'))
        self.assertEqual(_admin_region_identity(None,None,'POL+'),_admin_region_identity(None,'PL','POLAND'))
        self.assertEqual(_admin_region_identity('USA-CALIFORNIA','US','CALIFORNIA'),'USACALIFORNIA')

    def test_country_aliases_merge_providers_without_collapsing_subregions(self):
        country_aliases = {
            'BELGIUM': ('BE', 'BEL', 'BELGIUM', 'BELGIQUE'),
            'AUSTRIA': ('AT', 'AUT', 'AUSTRIA', 'AUTRICHE'),
            'DENMARK': ('DK', 'DNK', 'DENMARK', 'DANEMARK'),
            'ESTONIA': ('EE', 'EST', 'ESTONIA', 'ESTONIE'),
            'FINLAND': ('FI', 'FIN', 'FINLAND', 'FINLANDE'),
            'GREECE': ('GR', 'GRC', 'GREECE', 'GRECE'),
        }
        for expected, aliases in country_aliases.items():
            with self.subTest(expected=expected):
                identities = {
                    _admin_region_identity(alias, aliases[0], alias)
                    for alias in aliases
                }
                self.assertEqual(identities, {expected})

        self.assertEqual(_admin_map_display_name('BE'), 'Belgium')
        self.assertEqual(
            _admin_region_display_name('BELGIQUE', 'BE', 'BELGIQUE', 'Belgium'),
            'Belgium',
        )
        self.assertNotEqual(
            _admin_region_identity('BALEARICS', 'ES', 'BALEARICS'),
            _admin_region_identity('ESP', 'ES', 'ESP'),
        )
        self.assertNotEqual(
            _admin_region_identity('CAROLINEDUNORD', 'US', 'CAROLINEDUNORD'),
            _admin_region_identity('USA', 'US', 'USA'),
        )

    def test_overview_fallback_keeps_region_readable(self):
        self.assertEqual(_overview_map_event_context({'region':'SVN+','provider_name':'Freizeitkarte'}),'Slovenia · Freizeitkarte')
        self.assertEqual(
            _overview_map_event_context({
                'display_name': 'North Carolina',
                'map_package_name': 'North Carolina',
                'region': 'CAROLINEDUNORD',
                'region_country': 'US',
                'provider_name': 'MapRando',
            }),
            'North Carolina – United States · MapRando',
        )

    def test_local_dashboard_shows_flag_and_latest_result_without_raw_logs(self):
        body=local_test_data_page({'activity':[{'stream':'Map usage','release_label':'1.0.0-beta.10-local','outcome':'FAILED','event_count':2,'last_occurred_at':'2026-09-07T16:43:00Z'}]}, {'username':'audit'},'csrf').decode()
        for text in ('is_local_test=true','is_local_test=false','FAILED','Distinct operations','Latest local activity'):
            self.assertIn(text,body)

    def test_local_activity_caption_keeps_a_readable_mobile_width(self):
        body=local_test_data_page({'activity':[]}, {'username':'audit'},'csrf').decode()
        self.assertIn('<caption class="test-data-activity-caption">Latest local activity',body)
        self.assertIn('.test-data-activity-caption{display:block;width:100%;max-width:100%;box-sizing:border-box;white-space:normal;overflow-wrap:anywhere;',body)

    def test_build_guard_separates_debug_and_public_release(self):
        guard=Path(__file__).resolve().parents[3]/'Packaging'/'verify-release-label.sh'
        for configuration,label,allowed in [('Debug','1.0.0-beta.10-local',True),('Debug','1.0.0-beta.9',False),('Debug','',False),('Release','1.0.0-beta.9',True),('Release','1.0.0-beta.10-local',False),('Release','development',False)]:
            with self.subTest(configuration=configuration,label=label):
                result=subprocess.run(['/bin/sh',str(guard)],env={**os.environ,'CONFIGURATION':configuration,'TERENTO_RELEASE_LABEL':label},capture_output=True)
                self.assertEqual(result.returncode==0,allowed)
                if allowed:
                    self.assertEqual(is_local_release_label(label),configuration=='Debug')

    def test_clear_handlers_resolve_their_form_before_registering(self):
        from terento_catalog.admin import _providers_list_script, _map_statistics_script, _diagnostics_script
        for script, selector in [(_providers_list_script(), '#provider-filters'), (_map_statistics_script(), '#map-statistics-filters'), (_diagnostics_script(), '#diagnostic-filters')]:
            self.assertIn("document.querySelector('" + selector + "')?.addEventListener('terento-admin-clear-filters'", script)
            self.assertNotIn("form?.addEventListener('terento-admin-clear-filters'", script)
            self.assertNotIn("filterForm?.addEventListener('terento-admin-clear-filters'", script)

    def test_chart_shows_integer_axis_and_exact_event_time(self):
        from terento_catalog.admin import _overview_trend_chart
        markup = _overview_trend_chart([{'bucket':'2026-09-07T16:00:00Z','success_count':1,'success_times':['2026-09-07 19:43']}], 'hour', 'Europe/Vilnius')
        self.assertIn('2026-09-07 19:43', markup)
        self.assertIn("text-anchor='end'>1</text>", markup)
        self.assertIn("text-anchor='end'>4</text>", markup)
        self.assertIn("text-anchor='end'>0</text>", markup)
        self.assertRegex(markup, r"class='overview-chart-success'[^>]*height='51.50'")

    def test_collection_changes_have_readable_regions_and_escape_values(self):
        from terento_catalog.admin import _provider_audit_row
        markup = _provider_audit_row({'action':'CATALOG_RELEASES_UPDATED','details':{'packages':[{'region':'<unsafe>','previousRelease':'2026-05','release':'2026-08'}]}})
        self.assertIn('&lt;unsafe&gt;: 2026-05 → 2026-08', markup)
        self.assertNotIn('<unsafe>', markup)

    def test_openstreetmap_svg_has_unique_country_ids_and_no_external_resources(self):
        import xml.etree.ElementTree as ET
        from terento_catalog.admin_world_map import WORLD_MAP_SVG
        root = ET.fromstring(WORLD_MAP_SVG)
        paths = root.findall('{http://www.w3.org/2000/svg}path')
        ids = [node.attrib['id'] for node in paths]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertGreater(len(ids),200)
        self.assertIn('si',ids)
        self.assertIn('pl',ids)
        self.assertIn('ua',ids)
        self.assertIn('ru',ids)
        self.assertLess(ids.index('ru'), ids.index('ua'))
        self.assertIn('OpenStreetMap', WORLD_MAP_SVG)
        self.assertIn('ODbL', WORLD_MAP_SVG)
        self.assertNotIn('<script',WORLD_MAP_SVG)
        self.assertNotIn('href=',WORLD_MAP_SVG)

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
        # A verified result is counted even if its sibling is missing/failed.
        complete, filtered = query.split('), compatibility_fallback AS (', 1)
        self.assertIn("e.event_id::text AS operation_key", complete)
        self.assertIn("installed.provider_id = e.provider", complete)
        self.assertNotIn("selected_map_count", complete)
        self.assertIn('installed.is_local_test IS NOT TRUE', complete)
        self.assertNotIn('e.region = %s', complete)
        self.assertIn('e.region = %s', filtered)
        self.assertIn('GROUP BY c.operation_key, e.provider, e.region', filtered)
        self.assertIn(
            "e.phase_outcome = 'SUCCEEDED'\n                    OR e.write_started IS NOT FALSE",
            complete,
        )
        self.assertNotIn("e.phase_outcome = 'NOT_STARTED'", complete)
        self.assertIn("event_type IN ('INSTALL_SUCCEEDED', 'INSTALL_FAILED')", complete)
        self.assertEqual(tuple(parameters), ('SVN+', 'SVN+'))

if __name__=='__main__': unittest.main()

import json
import shutil
import subprocess
import unittest

from terento_catalog.admin import _map_statistics_script, _map_statistics_summary, _overview_map_activity_row, map_statistics_page, device_detail_page


class AdminStatisticsReconciliationTests(unittest.TestCase):
    def test_model_timestamp_identifies_installation_population(self):
        body = device_detail_page(
            {"id": "model-a", "model": "fēnix 8", "installationStats": {"attempts": 1, "successful": 1, "lastEvidenceAt": "2026-10-05T10:00:00Z"}},
            {"username": "operator"}, "csrf",
            update_history={"rows": [], "summary": {"successful": 0, "failed": 1, "notStarted": 2}},
        ).decode()
        # The installation timestamp is the last installation report, not a
        # combined installation/update activity time.
        self.assertIn("<span class='admin-metric-label'>Last report</span>", body)
        self.assertNotIn("Last activity", body)
        self.assertIn("2026-10-05T10:00:00", body)
        self.assertIn(">Updates</h2>", body)

    def test_download_purposes_preserve_unknown_and_independent_totals(self):
        rows = [dict(event_type='DOWNLOAD_SUCCEEDED', outcome='SUCCEEDED', operation_count=n, acquisition_purpose=purpose)
                for purpose, n in [('install', 2), ('update', 3), (None, 4)]]
        rows.append(dict(event_type='DOWNLOAD_FAILED', outcome='FAILED', operation_count=1, acquisition_purpose='update'))
        summary = _map_statistics_summary(rows)
        self.assertEqual(summary['completedDownloads'], 9)
        self.assertEqual(summary['downloadPurposes'], {'install': {'succeeded': 2, 'failed': 0}, 'update': {'succeeded': 3, 'failed': 1}, 'unknown': {'succeeded': 4, 'failed': 0}})
        # The breakdown stays in the summary payload, but Maps no longer renders
        # it under the Downloads chart (owner decision 2026-10-06).
        body = map_statistics_page({'rows': rows, 'summary': summary}, [], {'username': 'operator'}, 'csrf').decode()
        for text in ["Downloads by purpose", '<dt>For installs</dt>', '<dt>For updates</dt>', '<dt>Not recorded</dt>']:
            self.assertNotIn(text, body)

    def test_prewrite_update_is_visible_but_not_failed(self):
        body = _overview_map_activity_row(dict(event_type='MAP_UPDATE_NOT_STARTED', diagnostic_report_id='test-report', provider_id='freizeitkarte', region='LTU'))
        self.assertIn('Update blocked before writing', body)
        self.assertIn('/admin/update-diagnostics?diagnosticId=test-report', body)
        self.assertNotIn('Map update failed', body)
        self.assertEqual(_map_statistics_summary([dict(event_type='MAP_UPDATE_NOT_STARTED', outcome='NOT_STARTED', operation_count=1)])['failedMapUpdates'], 0)

    @unittest.skipUnless(shutil.which('node'), 'Node required for actual renderer')
    def test_dates_and_rankings_ignore_ineligible_rows(self):
        base = dict(provider_id='freizeitkarte', map_package_id='lt', region='LT', event_type='INSTALL_SUCCEEDED', outcome='SUCCEEDED', operation_count=1, last_occurred_at='2026-10-01T10:00:00Z')
        rows = [base, {**base, 'operation_count': 0, 'last_occurred_at': '2026-10-05T10:00:00Z'},
                {**base, 'region': 'FR', 'operation_count': 0},
                {**base, 'region': 'DE', 'map_package_id': None},
                {**base, 'region': 'ES', 'component_kind': 'contours'},
                {**base, 'event_type': 'MAP_UPDATE_SUCCEEDED', 'last_occurred_at': '2026-10-03T10:00:00Z'}]
        harness = r"""
const assert=require('node:assert/strict');
const nodes=Object.fromEntries(['#provider-statistic-rows','#map-rows','#all-map-rows'].map(key=>[key,{innerHTML:''}]));
global.document={querySelector:key=>nodes[key]||null,querySelectorAll:()=>[]};
global.window={terentoAdminProviders:[{id:'freizeitkarte',name:'Freizeitkarte'}],terentoMapStatistics:{rows:JSON.parse(process.argv[2])},addEventListener(){}};
eval(process.argv[1]);
window.terentoRenderProviderStream('installs');
const provider=nodes['#provider-statistic-rows'].innerHTML;
assert.match(provider,/Last install[^>]*>2026-10-01 10:00/);
assert.doesNotMatch(provider,/2026-10-05/);
window.terentoRenderProviderStream('updates');
assert.match(nodes['#provider-statistic-rows'].innerHTML,/Last update[^>]*>2026-10-03 10:00/);
const countries=nodes['#map-rows'].innerHTML;
assert.match(countries,/data-map-country="lt"/);
assert.doesNotMatch(countries,/data-map-country="(fr|de|es)"/);
assert.doesNotMatch(nodes['#all-map-rows'].innerHTML,/2026-10-05/);
// Top maps names are plain text with the provider/date line; Top countries keeps its buttons.
const topMaps=nodes['#all-map-rows'].innerHTML;
assert.match(topMaps,/<span class="popular-map-name">[^<]+<\/span><small class="popular-map-detail">Freizeitkarte · 2026-10-01 10:00/);
assert.doesNotMatch(topMaps,/<button|region-map-link|data-map-country/);
"""
        result = subprocess.run(['node', '-e', harness, _map_statistics_script(), json.dumps(rows)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

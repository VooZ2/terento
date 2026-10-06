import unittest
from contextlib import contextmanager

from terento_catalog.update_diagnostics import load_update_diagnostics, update_diagnostics_page

EVENT = '11111111-1111-4111-8111-111111111111'
OPERATION = '22222222-2222-4222-8222-222222222222'


class FakeDatabase:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    @contextmanager
    def connection(self):
        yield self

    def execute(self, sql, args):
        self.calls.append((sql, args))
        self.current = [] if 'FROM map_update_diagnostic_audit' in sql else next(self.results)
        return self

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class UpdateDiagnosticsTests(unittest.TestCase):
    def event(self):
        return dict(event_id=EVENT, operation_id=OPERATION, provider_id='maprando',
                    region='france', outcome='FAILED')

    def test_exact_link_and_ambiguity(self):
        report = {'event_id': EVENT, 'outcome': 'FAILED', 'payload': {}}
        db = FakeDatabase([self.event(), [report]])
        result = load_update_diagnostics(db, event_id=EVENT)
        self.assertEqual(result['detail']['event_id'], report['event_id'])
        self.assertEqual(result['detail']['audit'], [])
        self.assertEqual(db.calls[1][1], (OPERATION, 'maprando', 'france'))
        self.assertIn('provider = %s AND lower(region) = lower(%s)', db.calls[1][0])
        ambiguous = load_update_diagnostics(FakeDatabase([self.event(), [report, report]]), event_id=EVENT)
        self.assertIsNone(ambiguous['detail'])
        self.assertIn('More than one', ambiguous['status'])
        conflict = load_update_diagnostics(FakeDatabase([self.event(), [{**report, 'outcome': 'SUCCEEDED'}]]), event_id=EVENT)
        self.assertIsNone(conflict['detail'])
        self.assertIn('does not match', conflict['status'])

    def test_canonical_uppercase_diagnostic_links_to_lowercase_statistics_region(self):
        import sqlite3
        # Execute the production SELECT against a relational store rather than
        # returning a predetermined mock match; only placeholder syntax differs.
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        connection.execute('CREATE TABLE map_download_event(event_id TEXT, operation_id TEXT, provider_id TEXT, region TEXT, event_type TEXT, outcome TEXT, occurred_at TEXT, app_build TEXT, release_label TEXT, is_local_test BOOLEAN DEFAULT FALSE)')
        connection.execute("CREATE TABLE map_update_diagnostic(event_id TEXT, operation_id TEXT, provider TEXT, region TEXT, outcome TEXT, occurred_at TEXT, payload TEXT, is_local_test BOOLEAN DEFAULT FALSE,canonical_device_model_id TEXT,diagnostic_status TEXT DEFAULT 'ACTIVE')")
        connection.execute('CREATE TABLE device_model(id TEXT,model TEXT,variant TEXT,case_size_mm INTEGER,screen_technology TEXT)')
        connection.execute('CREATE TABLE map_update_diagnostic_audit(id INTEGER,event_id TEXT,action TEXT,previous_state TEXT,next_state TEXT,changed_by INTEGER,changed_at TEXT)')
        connection.execute('INSERT INTO map_download_event(event_id,operation_id,provider_id,region,event_type,outcome,occurred_at,app_build,release_label) VALUES(?,?,?,?,?,?,?,?,?)',
            (EVENT, OPERATION, 'maprando', 'fra', 'MAP_UPDATE_FAILED', 'FAILED', '2026-10-02', None, None))
        connection.execute('INSERT INTO map_update_diagnostic(event_id,operation_id,provider,region,outcome,occurred_at) VALUES(?,?,?,?,?,?)',
            ('diagnostic', OPERATION, 'maprando', 'FRA', 'FAILED', '2026-10-02'))
        # Similar names, other providers and other operations must not match.
        connection.executemany('INSERT INTO map_update_diagnostic(event_id,operation_id,provider,region,outcome,occurred_at) VALUES(?,?,?,?,?,?)', [
            ('other-region', OPERATION, 'maprando', 'France', 'FAILED', '2026-10-02'),
            ('other-provider', OPERATION, 'bbbike', 'FRA', 'FAILED', '2026-10-02'),
            ('other-operation', EVENT, 'maprando', 'FRA', 'FAILED', '2026-10-02'),
        ])

        local_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        connection.execute('INSERT INTO map_update_diagnostic(event_id,operation_id,provider,region,outcome,occurred_at,is_local_test) VALUES(?,?,?,?,?,?,TRUE)',
            (local_id, OPERATION, 'maprando', 'FRA', 'FAILED', '2026-10-02'))
        connection.execute('INSERT INTO map_download_event(event_id,operation_id,provider_id,region,event_type,outcome,is_local_test) VALUES(?,?,?,?,?,?,TRUE)',
            (local_id, OPERATION, 'maprando', 'fra', 'MAP_UPDATE_FAILED', 'FAILED'))

        class Database:
            @contextmanager
            def connection(self):
                yield self

            def execute(self, sql, args):
                cursor = connection.execute(sql.replace('%s', '?'), args)
                class Result:
                    def fetchone(self):
                        row = cursor.fetchone()
                        return dict(row) if row else None
                    def fetchall(self):
                        return [dict(row) for row in cursor.fetchall()]
                return Result()

        try:
            data = load_update_diagnostics(Database(), event_id=EVENT)
            self.assertEqual(data['detail']['event_id'], 'diagnostic')
            self.assertEqual(data['detail']['region'], 'FRA')
            self.assertIsNone(load_update_diagnostics(Database(), diagnostic_id=local_id)['detail'])
            self.assertIsNone(load_update_diagnostics(Database(), event_id=local_id)['event'])
            self.assertNotIn(local_id, [r['event_id'] for r in load_update_diagnostics(Database())['rows']])
        finally:
            connection.close()

    def test_missing_diagnostics_do_not_guess(self):
        data = load_update_diagnostics(FakeDatabase([self.event(), []]), event_id=EVENT)
        page = update_diagnostics_page(data, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('Failure details were not received', page)
        self.assertIn('France', page)
        self.assertNotIn('The device disconnected', page)

    def test_invalid_identifier_does_not_query_uuid_column(self):
        db = FakeDatabase([])
        with self.assertRaises(ValueError):
            load_update_diagnostics(db, event_id='invalid')
        self.assertEqual(db.calls, [])

    def test_exact_report_rejects_mixed_model_or_list_filters(self):
        for filters in ({'device_id':'other-model'}, {'outcome':'failed'}, {'lifecycle':'RESOLVED'}, {'offset':50}):
            db=FakeDatabase([])
            with self.assertRaises(ValueError):
                load_update_diagnostics(db, diagnostic_id=EVENT, **filters)
            self.assertEqual(db.calls,[])

    def test_safe_rendering_and_unknown_safety_facts(self):
        detail = dict(region='<script>x</script>', provider='bbbike', outcome='FAILED',
                      payload={'failureCode': 'UPDATE_FAILED_WRITE', 'failureStage': 'write',
                               'rawLogs': 'PRIVATE LOG', 'localPath': '/private/secret'})
        page = update_diagnostics_page({'detail': detail}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('The replacement could not be written', page)
        self.assertIn('Previous map confirmed preserved</dt><dd>Unknown', page)
        self.assertNotIn('PRIVATE LOG', page)
        self.assertNotIn('/private/secret', page)
        self.assertNotIn('<script>x</script>', page)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', page)

    def test_false_and_true_facts_are_not_conflated(self):
        detail = {'payload': {'oldMapPreserved': True, 'writeStarted': False}}
        page = update_diagnostics_page({'detail': detail}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('Previous map confirmed preserved</dt><dd>Yes', page)
        self.assertIn('Write started</dt><dd>No', page)

    def test_preservation_failure_is_uncertain_and_validation_has_action(self):
        detail = {'provider': 'bbbike', 'outcome': 'FAILED', 'payload': {
            'failureCode': 'UPDATE_FAILED_COMMIT', 'oldMapPreserved': False}}
        page = update_diagnostics_page({'detail': detail}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('Previous map confirmed preserved</dt><dd>Not confirmed — inspect device', page)
        detail['payload']['failureCode'] = 'UPDATE_FAILED_SOURCE_VALIDATION'
        page = update_diagnostics_page({'detail': detail}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn("href='/admin/providers/bbbike'", page)
        detail['provider'] = '//untrusted.example'
        page = update_diagnostics_page({'detail': detail}, {'username': 'admin'}, 'csrf').decode()
        self.assertNotIn("href='/admin/providers/", page)

    def test_acquisition_reason_follows_reported_stage(self):
        for stage, reason in [('download', 'could not be downloaded'), ('extract', 'could not be extracted'),
                              ('source-validation', 'failed source validation'), ('preflight', 'preparation was blocked')]:
            with self.subTest(stage=stage):
                detail = {'provider': 'bbbike', 'outcome': 'NOT_STARTED', 'payload': {
                    'failureCode': 'UPDATE_FAILED_ACQUISITION', 'failureStage': stage}}
                page = update_diagnostics_page({'detail': detail}, {'username': 'admin'}, 'csrf').decode()
                self.assertIn(reason, page)
                self.assertNotIn('There is not enough room', page)
                if stage == 'preflight':
                    self.assertNotIn('Review provider packages', page)

    def test_filter_pagination_and_direct_diagnostic(self):
        rows = [{'event_id': EVENT}] * 51
        db = FakeDatabase([rows])
        result = load_update_diagnostics(db, outcome='not_started', offset=50)
        self.assertEqual(len(result['rows']), 50)
        self.assertTrue(result['has_more'])
        self.assertEqual(db.calls[0][1], ('NOT_STARTED', 'NOT_STARTED', '', '', '', '', 50))
        direct = load_update_diagnostics(FakeDatabase([{'event_id': EVENT}]), diagnostic_id=EVENT)
        self.assertEqual(direct['detail']['event_id'], EVENT)


class UpdateDiagnosticsHTTPTests(unittest.TestCase):
    def test_authentication_filters_and_missing_details(self):
        import threading
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from api_test_fixtures import FakeProviderDatabase
        from terento_catalog.http_api import CatalogService, make_handler

        class Database(FakeProviderDatabase):
            @contextmanager
            def connection(self):
                yield FakeDatabase([dict(event_id=EVENT, operation_id=OPERATION,
                    provider_id='maprando', region='france', outcome='FAILED'), []])

        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(CatalogService(Database())))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(path, authenticated=True):
                conn = HTTPConnection(*server.server_address)
                headers = {'Cookie': 'terento_admin_session=session; terento_admin_csrf=csrf'} if authenticated else {}
                conn.request('GET', path, headers=headers)
                response = conn.getresponse()
                result = response.status, dict(response.getheaders()), response.read()
                conn.close()
                return result
            status, headers, _ = request('/admin/update-diagnostics', False)
            self.assertEqual(status, 303)
            self.assertEqual(headers['Location'], '/admin/login')
            status, headers, body = request('/admin/update-diagnostics?eventId=' + EVENT)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['X-Robots-Tag'], 'noindex, nofollow')
            self.assertIn(b'Failure details were not received', body)
            for query in ('offset=-1', 'offset=no', 'eventId=bad', 'outcome=bad'):
                self.assertEqual(request('/admin/update-diagnostics?' + query)[0], 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


    def test_report_list_shows_totals_for_the_report_stream(self):
        rows = [{'event_id': EVENT, 'outcome': 'FAILED', 'provider': 'bbbike', 'region': 'FRA', 'payload': {}}]
        totals = {'total': 52, 'succeeded': 44, 'failed': 5, 'not_started': 3, 'open_failed': 2}
        data = load_update_diagnostics(FakeDatabase([rows, totals]))
        self.assertEqual(data['totals'], totals)
        page = update_diagnostics_page(data, {'username': 'operator'}, 'csrf').decode()
        self.assertIn('<h1>Update reports</h1>', page)
        for label, value in (('Reports', '52'), ('Successful', '44'), ('Failed', '5'), ('Blocked', '3'), ('Open', '2')):
            self.assertIn(f"<span class='admin-metric-label'>{label}", page)
            self.assertIn(f">{value}</strong>", page)
        # One Installations-style summary card, plain numbers, no scope chips and
        # no duplicate Reports card title (owner decision 2026-10-06).
        self.assertIn("<section class='admin-card installation-kpis update-report-kpis' aria-label='Update report summary'>", page)
        self.assertEqual(page.count("<div class='admin-metric-row'"), 1)
        self.assertNotIn('All time</span>', page)
        self.assertNotIn('All update reports', page)
        self.assertNotIn('update-history-title', page)
        self.assertIn("data-tone='danger'", page)
        self.assertIn("href='/admin/update-diagnostics?outcome=failed&amp;lifecycle=ACTIVE'", page)
        self.assertIn('France · BBBike', page)
        self.assertNotIn('FRA · bbbike', page)
        self.assertNotIn('Diagnostic sharing is independent', page)
        # A failing totals query leaves the list usable and marks the tiles unavailable.
        degraded = load_update_diagnostics(FakeDatabase([rows]))
        self.assertIsNone(degraded['totals'])
        self.assertIn('<span>Unavailable</span>', update_diagnostics_page(degraded, {'username': 'operator'}, 'csrf').decode())

    def test_report_list_filters_table_and_pages_follow_installations(self):
        failed = {'event_id': EVENT, 'outcome': 'FAILED', 'provider': 'bbbike', 'region': 'FRA', 'payload': {}}
        succeeded = {**failed, 'event_id': OPERATION, 'outcome': 'SUCCEEDED'}
        totals = {'total': 2, 'succeeded': 1, 'failed': 1, 'not_started': 0, 'open_failed': 0}
        page = update_diagnostics_page({'rows': [failed, succeeded], 'totals': totals, 'has_more': True},
                                       {'username': 'operator'}, 'csrf').decode()
        main = page.split('<main', 1)[1].split('</main>', 1)[0]
        # Filter bar directly above the table, quick-filter links in the shared order.
        self.assertIn("<nav class='filter-bar diagnostic-filter-bar update-report-filters' aria-label='Filter update reports'>"
                      "<div class='quick-filter-group'><a class='quick-filter active' href='/admin/update-diagnostics' aria-current='page'>All</a>", main)
        labels = [part.split('>', 1)[1].split('<', 1)[0] for part in main.split("<a class='quick-filter")[1:]]
        self.assertEqual(labels, ['All', 'Failed', 'Blocked', 'Successful'])
        self.assertEqual(main.count("aria-current='page'"), 1)
        self.assertIn("</nav><div class='table-wrap update-report-table-wrap'>", main)
        self.assertNotIn('filter-clear', main)
        self.assertNotIn('records', main)
        # No linked issue on this page: no GitHub issue column.
        self.assertNotIn('GitHub issue', main)
        self.assertIn("<a class='secondary-button update-history-inspect' href='/admin/update-diagnostics?diagnosticId=" + EVENT
                      + "' aria-label='Inspect update 1'>Inspect</a>", main)
        self.assertIn("<nav class='provider-pagination' aria-label='Update report pages'><a class='secondary-button' "
                      "href='/admin/update-diagnostics?offset=50' aria-label='Next update reports'>Next</a></nav>", main)
        # Zero open reports stay a plain, neutral number.
        self.assertNotIn('lifecycle=ACTIVE', main)
        linked = update_diagnostics_page({'rows': [failed, {**succeeded, 'linked_github_issue': '#325'}], 'totals': totals,
                                          'outcome': 'failed', 'lifecycle': 'ACTIVE', 'offset': 50},
                                         {'username': 'operator'}, 'csrf').decode()
        self.assertIn("<th scope='col'>GitHub issue</th>", linked)
        self.assertEqual(linked.count("<td data-label='GitHub issue'>"), 2)
        self.assertIn("<a class='quick-filter active' href='/admin/update-diagnostics?outcome=failed&amp;lifecycle=ACTIVE' aria-current='page'>Failed</a>", linked)
        self.assertIn("<a class='secondary-button filter-clear' href='/admin/update-diagnostics' aria-label='Clear update report filters'>Clear</a>", linked)
        self.assertIn("aria-label='Previous update reports'>Previous</a>", linked)
        self.assertIn("aria-label='Inspect update 51'", linked)
        empty = update_diagnostics_page({'rows': [], 'totals': totals, 'outcome': 'not_started'},
                                        {'username': 'operator'}, 'csrf').decode()
        self.assertIn("No update reports match this filter.", empty)
        self.assertNotIn('<table', empty.split('<main', 1)[1].split('</main>', 1)[0])
        self.assertIn('filter-clear', empty.split('<main', 1)[1].split('</main>', 1)[0])
        none = update_diagnostics_page({'rows': [], 'totals': totals}, {'username': 'operator'}, 'csrf').decode()
        self.assertIn('No update reports yet.', none)
        self.assertNotIn('quick-filter', none.split('<main', 1)[1].split('</main>', 1)[0])

    def test_detail_states_lead_with_back_link_and_result_heading(self):
        back = "<p class='back-link'><a href='/admin/update-diagnostics'>"
        missing = update_diagnostics_page(load_update_diagnostics(FakeDatabase([UpdateDiagnosticsTests.event(self), []]), event_id=EVENT),
                                          {'username': 'admin'}, 'csrf').decode()
        self.assertIn(back, missing)
        self.assertIn('<h1>Map update failed</h1>', missing)
        self.assertIn('<title>Map update failed · Update reports · Terento</title>', missing)
        self.assertLess(missing.index('update-report-card'), missing.index('Report status'))
        self.assertNotIn('All update reports', missing)
        self.assertNotIn('installation-kpis', missing.split('<main', 1)[1].split('</main>', 1)[0])
        unknown = update_diagnostics_page(load_update_diagnostics(FakeDatabase([None]), diagnostic_id=EVENT),
                                          {'username': 'admin'}, 'csrf').decode()
        self.assertIn(back, unknown)
        self.assertIn('<h1>Update report not found</h1>', unknown)
        self.assertIn('Diagnostic not found.', unknown)
        self.assertNotIn('quick-filter', unknown.split('<main', 1)[1].split('</main>', 1)[0])

    def test_update_reports_live_in_the_tools_menu_not_the_maps_heading(self):
        from terento_catalog.admin import map_statistics_page
        user = {'username': 'operator'}
        page = update_diagnostics_page(load_update_diagnostics(FakeDatabase([[], {}])), user, 'csrf').decode()
        tools = page.split('<details class="admin-tools-menu">', 1)[1].split('</details>', 1)[0]
        self.assertIn("<summary class='active'>Tools</summary>", tools)
        self.assertIn("<a class='active' href=\"/admin/update-diagnostics\">Update reports</a>", tools)
        self.assertLess(tools.index('Model sources'), tools.index('Update reports'))
        primary = page.split('aria-label="Primary"', 1)[1].split('</div>', 1)[0]
        self.assertNotIn("class='active'", primary)
        maps = map_statistics_page({'rows': []}, [], user, 'csrf').decode()
        self.assertIn("<a href=\"/admin/update-diagnostics\">Update reports</a>", maps)
        heading = maps.split("class='dashboard map-statistics-page'", 1)[1].split('<form', 1)[0]
        self.assertIn('<h1>Maps</h1>', heading)
        self.assertNotIn('update-diagnostics', heading)


if __name__ == '__main__':
    unittest.main()

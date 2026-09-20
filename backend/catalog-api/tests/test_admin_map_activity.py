import unittest

from terento_catalog.admin import _overview_map_activity_row


class AdminMapActivityTests(unittest.TestCase):
    def test_download_title_expands_start_duration_finish_and_preserves_map_link(self):
        row = dict(event_type='DOWNLOAD_SUCCEEDED', provider_id='freizeitkarte', region='FRA',
                   lifecycle=[dict(type='DOWNLOAD_STARTED', at='2026-09-15T23:59:00Z'),
                              dict(type='DOWNLOAD_PROCESSING', at='2026-09-16T00:01:00Z'),
                              dict(type='DOWNLOAD_SUCCEEDED', at='2026-09-16T00:01:30Z')])
        markup = _overview_map_activity_row(row)
        summary = markup.split('<summary>')[1].split('</summary>')[0]
        self.assertIn('Download completed', summary)
        self.assertIn('download-context', summary)
        self.assertIn('/admin/map-statistics?', summary)
        self.assertNotIn('Download history', markup)
        self.assertNotIn("class='download-history' open", markup)
        self.assertIn('>2m 30s</span>', markup)
        self.assertIn('2026-09-15T23:59:00', markup)
        self.assertIn('2026-09-16T00:01:30', markup)
        self.assertEqual(markup.count("class='download-elapsed'"), 1)
        self.assertNotIn('>0s</span>', markup)
        row['lifecycle'][0]['at'] = None
        self.assertNotIn('download-elapsed', _overview_map_activity_row(row))

    def test_download_history_uses_requested_fontawesome_icons(self):
        phases = ('STARTED', 'PROCESSING', 'SUCCEEDED')
        row = dict(event_type='DOWNLOAD_SUCCEEDED', lifecycle=[
            dict(type='DOWNLOAD_' + phase, at='2026-09-14T12:00:00Z') for phase in phases])
        markup = _overview_map_activity_row(row)
        for phase, icon in zip(phases, ('hourglass-start', 'spinner', 'hourglass-end')):
            self.assertIn('fa-' + icon, markup)
            self.assertIn(phase.title(), markup)
        self.assertEqual(markup.count('Font Awesome Free 7.3.1'), 4)
        self.assertNotIn('fa-spin', markup.replace('fa-spinner', ''))

    def test_admin_shows_missing_outcome_component_and_timeline(self):
        row = dict(event_type='DOWNLOAD_PROCESSING', component_kind='contours',
                   lifecycle=[dict(type='DOWNLOAD_STARTED', at='2026-09-14T12:00:00Z'),
                              dict(type='DOWNLOAD_PROCESSING', at='2026-09-14T12:01:00Z')])
        markup = _overview_map_activity_row(row)
        for text in ('Outcome not received', 'Contours', "class='download-history'", 'Processing'):
            self.assertIn(text, markup)
        legacy = _overview_map_activity_row(dict(event_type='DOWNLOAD_STARTED', has_recorded_outcome=True))
        self.assertIn('Outcome recorded', legacy)
        self.assertNotIn('Outcome not received', legacy)
        for event_type in ('DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED'):
            self.assertNotIn('failed', _overview_map_activity_row(dict(event_type=event_type)))

    def test_stale_download_phase_is_history_not_active_work(self):
        markup = _overview_map_activity_row(dict(
            event_type='DOWNLOAD_STARTED', is_stale=True,
            occurred_at='2026-09-18T15:32:00Z',
        ))
        self.assertIn('Outcome missing', markup)
        self.assertNotIn('Outcome not received', markup)
        self.assertIn('overview-activity-stale', markup)
        self.assertIn('map-activity-neutral', markup)

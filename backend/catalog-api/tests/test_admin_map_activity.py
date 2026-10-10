import unittest

from terento_catalog.admin import _overview_map_activity_row


class AdminMapActivityTests(unittest.TestCase):
    def test_install_and_update_context_keep_assessed_device_inline(self):
        for event_type in ('INSTALL_SUCCEEDED', 'INSTALL_FAILED', 'MAP_UPDATE_SUCCEEDED', 'MAP_UPDATE_FAILED'):
            with self.subTest(event_type=event_type):
                row = dict(event_type=event_type, provider_id='bbbike', provider_name='BBBike',
                    region='LTU', model='fēnix 8', variant='47 mm', canonical_device_model_id='fenix-8-47')
                markup = _overview_map_activity_row(row)
                context = markup.split("<span class='activity-context'>")[1].split('</span>')[0]
                self.assertIn("Lithuania · BBBike · <a class='overview-activity-device'", context)
                self.assertIn('fēnix 8 · 47 mm</a>', context)
                self.assertNotIn('</span></span><a', markup)
                custom = _overview_map_activity_row({**row, 'provider_id':'custom'})
                self.assertIn("Custom .img · <a class='overview-activity-device'", custom)
                self.assertNotIn('BBBike', custom)
                unknown = _overview_map_activity_row({**row, 'canonical_device_model_id':None})
                self.assertNotIn('fēnix', unknown)
                self.assertNotIn('overview-activity-device', unknown)

    def test_activity_omits_historical_placeholder_but_preserves_real_variants(self):
        for event_type in ('INSTALL_SUCCEEDED', 'INSTALL_FAILED', 'MAP_UPDATE_SUCCEEDED', 'MAP_UPDATE_FAILED'):
            with self.subTest(event_type=event_type):
                row = dict(event_type=event_type, provider_id='bbbike', region='LTU',
                           model='fēnix 7S Pro', canonical_device_model_id='fenix-7s-pro', variant='Historical')
                markup = _overview_map_activity_row(row)
                self.assertIn('>fēnix 7S Pro</a>', markup)
                self.assertNotIn('Historical', markup)
                self.assertIn('>fēnix 7S Pro · Solar</a>',
                              _overview_map_activity_row({**row, 'variant': 'Solar'}))

    def test_download_title_expands_start_duration_finish_without_generic_map_link(self):
        row = dict(event_type='DOWNLOAD_SUCCEEDED', provider_id='freizeitkarte', region='FRA',
                   lifecycle=[dict(type='DOWNLOAD_STARTED', at='2026-09-15T23:59:00Z'),
                              dict(type='DOWNLOAD_PROCESSING', at='2026-09-16T00:01:00Z'),
                              dict(type='DOWNLOAD_SUCCEEDED', at='2026-09-16T00:01:30Z')])
        markup = _overview_map_activity_row(row)
        summary = markup.split('<summary>')[1].split('</summary>')[0]
        self.assertIn('Download successful', summary)
        self.assertIn('download-context', summary)
        self.assertNotIn('<a ', summary)
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

    def test_admin_shows_component_and_timeline(self):
        row = dict(event_type='DOWNLOAD_INTERRUPTED', component_kind='contours',
                   lifecycle=[dict(type='DOWNLOAD_STARTED', at='2026-09-14T12:00:00Z'),
                              dict(type='DOWNLOAD_PROCESSING', at='2026-09-14T12:01:00Z'),
                              dict(type='DOWNLOAD_INTERRUPTED', at='2026-09-14T12:02:00Z')])
        markup = _overview_map_activity_row(row)
        for text in ('Download interrupted', 'Contours', "class='download-history'", 'Processing'):
            self.assertIn(text, markup)
        for event_type in ('DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED'):
            self.assertNotIn('failed', _overview_map_activity_row(dict(event_type=event_type)))

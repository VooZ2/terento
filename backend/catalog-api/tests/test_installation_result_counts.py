"""The batch is correlation context, never the admin attempt denominator."""
import unittest
from terento_catalog.admin import _diagnostic_summary_by_identity, _group_operations


class InstallationResultCountsTests(unittest.TestCase):
    def test_custom_activity_does_not_link_to_catalog_statistics(self):
        from terento_catalog.admin import _overview_map_event_context, _overview_map_event_href
        event = {'provider_id': 'custom', 'region': 'custom'}
        self.assertEqual(_overview_map_event_context(event), 'Custom .img')
        self.assertEqual(_overview_map_event_href(event), '/admin/installations')

    def test_table_status_uses_sessions_not_package_summary(self):
        from terento_catalog.admin import _statistics_row
        markup = _statistics_row({'model': 'Watch', 'compatibility_identity': 'Watch',
                                  'successful_install_count': 2, 'map_capable': True},
                                 {'attempts': 3, 'successful': 3, 'failed': 0})
        self.assertIn('Tested:', markup)
        self.assertNotIn('Supported:', markup)

    def events(self):
        return [dict(event_id=f'result-{index}', operation_id='mixed-session',
                     compatibility_identity='Test watch', map_result_index=index,
                     selected_map_count=2, provider=provider, write_started=True,
                     phase_outcome='SUCCEEDED', automatic_finishing_result='VERIFIED')
                for index, provider in enumerate(('custom', 'opentopomap'))]

    def summary(self, events, resolved=None):
        return next(iter(_diagnostic_summary_by_identity(events, resolved).values()))

    def test_mixed_session_is_two_successes_but_one_diagnostic_group(self):
        events = self.events()
        summary = self.summary(events)
        self.assertEqual((summary['attempts'], summary['successful'], summary['failed']), (2, 2, 0))
        self.assertEqual(len(_group_operations(events)), 1)

    def test_failed_sibling_does_not_cancel_success(self):
        events = self.events()
        events[1].update(phase_outcome='FAILED', automatic_finishing_result='FAILED')
        summary = self.summary(events)
        self.assertEqual((summary['attempts'], summary['successful'], summary['failed']), (2, 1, 1))

    def test_duplicate_delivery_does_not_add_attempts(self):
        events = self.events()
        self.assertEqual(self.summary(events + events)['attempts'], 2)

    def test_resolved_failures_remain_in_denominator(self):
        events = self.events()
        for event in events:
            event.update(phase_outcome='FAILED', diagnostic_status='RESOLVED')
        summary = self.summary([], events)
        self.assertEqual((summary['attempts'], summary['failed'], summary['open_errors']), (2, 2, 0))

    def test_missing_or_not_started_sibling_is_not_invented(self):
        events = self.events()
        self.assertEqual(self.summary(events[:1])['attempts'], 1)
        events[1].update(phase_outcome='NOT_STARTED', write_started=False)
        self.assertEqual(self.summary(events)['attempts'], 1)

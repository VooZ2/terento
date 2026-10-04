import unittest
from terento_catalog.admin import provider_detail_page


class ProviderMonitoringPresentationTests(unittest.TestCase):
    def render(self, **overrides):
        check = dict(status='DOWN', checked_at='2026-10-04T19:24:00Z', download_status='DOWN',
                     error_detail='Download timed out <script>', http_status=None, duration_ms=0)
        provider = dict(id='freizeitkarte', name='Freizeitkarte', status='ACTIVE',
                        downloadBlockReason='PROVIDER_DOWN', healthHistory=[check], maps=[],
                        monitoring=dict(intervalHours=6, nextCheckAt='2026-10-05T01:24:00Z', stale=True))
        provider.update(overrides)
        return provider_detail_page({'provider': provider}, [], [], {'username':'fixture'}, 'csrf').decode()

    def test_current_check_is_readable_and_does_not_use_history_table(self):
        body = self.render()
        current = body.split("id='provider-health-details'", 1)[1].split('</details>', 1)[0]
        self.assertNotIn('<table', current)
        self.assertIn('Download server', current)
        self.assertIn('Observed issue:', current)
        self.assertIn('Download timed out &lt;script&gt;', current)
        self.assertIn('Check overdue.', current)
        self.assertIn('Next scheduled check', current)
        self.assertIn('2026-10-05', current)
        self.assertIn('Duration: 0 ms', current)
        self.assertIn("value='6' selected", body)
        self.assertIn("data-provider-action='health-schedule'", body)

    def test_history_is_bounded_compact_and_separate_from_current(self):
        history = [dict(status='HEALTHY', checked_at=f'2026-10-04T{hour:02d}:00:00Z') for hour in range(23, 0, -1)]
        body = self.render(healthHistory=history)
        previous = body.split("id='provider-health-history'", 1)[1].split('</details>', 1)[0]
        self.assertEqual(previous.count('<li>'), 10)
        self.assertIn('last 30 days', previous)
        self.assertNotIn('<table', previous)
        self.assertNotIn('23:00:00', previous)
        self.assertNotIn('01:00:00', previous)
        self.assertNotIn('data-page=', previous)

    def test_map_download_control_is_explicit_escaped_and_current_only(self):
        body = self.render(maps=[dict(id='fzk-lt',name='Lithuania',availability='AVAILABLE',
                            downloads_disabled=True,downloads_disabled_reason='<private note>'),
                            dict(id='retired-map',availability='RETIRED')])
        self.assertIn('Downloads disabled by admin', body)
        self.assertIn('&lt;private note&gt;', body)
        self.assertIn("data-downloads-enabled='true'>Enable downloads", body)
        markup = body.split('<script>', 1)[0]
        self.assertNotIn("data-package-id='retired-map'", markup)
        self.assertIn('if (answer === null) return;', body)
        self.assertIn('Enter a reason to disable downloads.', body)
        self.assertIn("'X-CSRF-Token': csrf", body)

    def test_retired_provider_does_not_offer_map_download_controls(self):
        body = self.render(status='RETIRED',maps=[dict(id='fzk-lt',availability='AVAILABLE')])
        self.assertNotIn("data-provider-action='downloads'", body)

    def test_old_latest_observation_survives_recent_history_window(self):
        body = self.render(healthHistory=[], health=dict(status='DOWN',
            checked_at='2026-08-01T12:00:00Z', download_status='DOWN', error_detail='Old server timeout'))
        current = body.split("id='provider-health-details'", 1)[1].split('</details>', 1)[0]
        self.assertIn('2026-08-01', current)
        self.assertIn('Old server timeout', current)
        self.assertIn('Check overdue.', current)
        self.assertNotIn('No health checks recorded yet.', current)
        history = body.split("id='provider-health-history'", 1)[1].split('</details>', 1)[0]
        self.assertNotIn('2026-08-01', history)
        self.assertIn('No previous health checks recorded.', history)

    def test_not_applicable_check_is_not_counted_as_a_problem(self):
        body = self.render(healthHistory=[dict(status='HEALTHY', checked_at='2026-10-04T12:00:00Z',
            zip_status='NOT_APPLICABLE', download_status='HEALTHY')])
        self.assertIn('1 passed · 0 need attention · 7 not evaluated', body)

    def test_inactive_provider_explains_why_no_check_is_scheduled(self):
        for status, label in (("PAUSED", "Automatic checks paused"), ("RETIRED", "Automatic checks stopped")):
            body = self.render(status=status, monitoring=dict(intervalHours=1, nextCheckAt=None, stale=True))
            current = body.split("id='provider-health-details'", 1)[1].split('</details>', 1)[0]
            self.assertIn(label, current)

    def test_missing_check_is_explicit(self):
        body = self.render(healthHistory=[])
        self.assertIn('No health checks recorded yet.', body)
        self.assertIn('Check overdue.', body)
        self.assertIn('Next check:', body)


if __name__ == '__main__':
    unittest.main()

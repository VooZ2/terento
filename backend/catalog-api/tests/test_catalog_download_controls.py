from datetime import datetime, timedelta, timezone
import unittest
from terento_catalog.catalog import build_catalog


class CatalogDownloadControlsTests(unittest.TestCase):
    def row(self, **changes):
        return dict(provider_id='freizeitkarte', provider_name='Freizeitkarte',
            provider_status='ACTIVE', provider_health='DOWN',
            provider_download_health='HEALTHY', provider_last_checked_at=datetime.now(timezone.utc),
            provider_website='https://www.freizeitkarte-osm.de/', provider_attribution='OSM',
            provider_license_information='ODbL', package_id='freizeitkarte-lithuania',
            package_name='Lithuania', package_region='LT', release='2026-05',
            artifact_id='lt-main', artifact_kind='main', artifact_required=True,
            artifact_source_url='https://download.freizeitkarte-osm.de/garmin/latest/LTU.zip',
            artifact_size_bytes=100, artifact_validation_status='VALIDATED', **changes)

    def catalog(self, row):
        return build_catalog([row], datetime.now(timezone.utc))['providers'][0]

    def test_website_failure_does_not_block_healthy_downloads(self):
        provider = self.catalog(self.row())
        self.assertIsNone(provider['downloadBlockReason'])
        self.assertIsNone(provider['maps'][0]['downloadBlockReason'])

    def test_down_and_admin_disabled_packages_remain_visible(self):
        for updates, expected in (({'provider_download_health':'DOWN'}, 'PROVIDER_DOWN'),
            ({'downloads_disabled':True}, 'ADMIN_DISABLED'),
            ({'provider_last_checked_at':datetime.now(timezone.utc)-timedelta(hours=2)}, 'STATUS_STALE'),
            ({'artifact_validation_status':'FAILED'}, 'PACKAGE_UNAVAILABLE')):
            with self.subTest(expected=expected):
                row = self.row(); row.update(updates)
                provider = self.catalog(row)
                self.assertEqual(len(provider['maps']),1)
                self.assertEqual(provider['maps'][0]['downloadBlockReason'], expected)
                self.assertNotIn('downloads_disabled_reason', provider['maps'][0])

    def test_optional_bad_artifact_does_not_block_main_map(self):
        row = self.row()
        contour = {**row, 'artifact_id':'lt-contours', 'artifact_kind':'contours',
                   'artifact_required':False, 'artifact_validation_status':'FAILED'}
        result = build_catalog([row,contour],datetime.now(timezone.utc),contour_mode='public')
        self.assertIsNone(result['providers'][0]['maps'][0]['downloadBlockReason'])

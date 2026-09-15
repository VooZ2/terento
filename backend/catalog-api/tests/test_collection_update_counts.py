import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from dataclasses import replace

from terento_catalog.db import Database
from terento_catalog.provider_catalog import CatalogPackage, ProviderSnapshot, OPENTOPO_MAP
from terento_catalog.admin import _provider_update_count


class CollectionUpdateCountsTests(unittest.TestCase):
    def package(self, key, release='2026-09', **kw):
        return CatalogPackage(id=key, provider_id='opentopomap', provider_region_id=key,
            canonical_region_id=key, name=key, region=key, country=None, release=release,
            release_id=None, version_label=None, generated_at=None, source_updated_at=None,
            availability='AVAILABLE', country_codes=(), region_kind='country', tags=(),
            capabilities=(), artifacts=(), **kw)

    def test_counts_new_and_changed_packages_not_removed_or_unchanged(self):
        previous = [dict(id=k, release='2026-09', source_updated_at=None) for k in ('same','release','date','removed')]
        packages = (self.package('same'), self.package('release', '2026-10'),
                    replace(self.package('date'), source_updated_at=datetime(2026,9,15,tzinfo=timezone.utc)),
                    self.package('new'))
        self.assert_counts(previous, packages, (1, 2))
        self.assert_counts([], packages, (4, 0))
        self.assert_counts([previous[0]], (self.package('same'),), (0, 0))

    def assert_counts(self, previous, packages, expected):
        database = Database('postgresql://unused')
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = previous
        connection.execute.return_value.fetchone.return_value = {'id':7}
        database.connection = MagicMock()
        database.connection.return_value.__enter__.return_value = connection
        database.ensure_provider_definition = MagicMock()
        database._insert_admin_audit = MagicMock()
        database.upsert_provider_snapshot(ProviderSnapshot(OPENTOPO_MAP, packages, datetime.now(timezone.utc)), run_id=7)
        writes = [c for c in connection.execute.call_args_list if 'SET new_package_count' in c.args[0]]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[1], (*expected, 7, 'opentopomap'))
        self.assertIn("status = 'RUNNING'", writes[0].args[0])

    def test_unknown_and_failed_are_not_zero(self):
        self.assertIn('—', _provider_update_count({'status':'SUCCEEDED', 'release_change_detected':False}))
        self.assertIn('—', _provider_update_count({'status':'FAILED', 'new_package_count':2,'updated_package_count':1}))
        self.assertIn('<strong>0</strong>', _provider_update_count({'status':'SUCCEEDED','new_package_count':0,'updated_package_count':0}))
        rendered = _provider_update_count({'status':'SUCCEEDED','new_package_count':2,'updated_package_count':3})
        self.assertIn('<strong>5</strong>', rendered)
        self.assertIn('2 new · 3 updated', rendered)

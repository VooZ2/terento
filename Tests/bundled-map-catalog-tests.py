"""The bundled fallback catalog never lists withheld or FAT32-oversized packages."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundled', ROOT / 'scripts/build-bundled-map-catalog.py')
bundled = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundled)


def document(*maps, provider='freizeitkarte'):
    providers = [{'id': provider_id, 'name': provider_id, 'maps': list(maps) if provider_id == provider else []}
                 for provider_id in bundled.PROVIDER_ORDER]
    return {'catalogVersion': 1, 'updatedAt': '2026-10-14T00:00:00Z', 'providers': providers}


def package(package_id, **fields):
    return {'id': package_id, 'region': fields.pop('region', package_id.upper()), 'name': package_id,
            'sizeBytes': 1, 'downloadSizeBytes': 1, 'installSizeBytes': 1,
            'sourceURL': 'https://example.invalid/map.img', **fields}


class BundledCatalogTests(unittest.TestCase):
    def test_committed_catalog_passes(self):
        counts = bundled.check(bundled.BUNDLED.read_text(encoding='utf-8'))
        self.assertEqual(counts, {'freizeitkarte': 56, 'opentopomap': 173, 'bbbike': 760, 'maprando': 160})

    def test_withheld_and_oversized_packages_are_removed(self):
        rows = [package('freizeitkarte-blr', region='BLR'),
                package('freizeitkarte-rus-central', region='RUS-CENTRAL'),
                package('freizeitkarte-rus-crimea', region='RUS-CRIMEA'),
                package('freizeitkarte-ukr-crimea', region='CRIMEA', countryCodes=['UA']),
                package('freizeitkarte-big', installSizeBytes=bundled.FAT32_MAX + 1),
                package('freizeitkarte-contours', artifacts=[
                    {'id': 'main', 'required': True, 'sizeBytes': 1},
                    {'id': 'contours', 'required': False, 'sizeBytes': bundled.FAT32_MAX + 1}])]
        text, dropped = bundled.prune(bundled.render(document(*rows)))
        self.assertEqual([package_id for package_id, _ in dropped],
                         ['freizeitkarte-rus-central', 'freizeitkarte-rus-crimea', 'freizeitkarte-ukr-crimea',
                          'freizeitkarte-big', 'freizeitkarte-contours'])
        kept = json.loads(text)['providers'][0]['maps']
        self.assertEqual([row['id'] for row in kept], ['freizeitkarte-blr', 'freizeitkarte-contours'])
        self.assertEqual([artifact['id'] for artifact in kept[1]['artifacts']], ['main'])
        bundled.check(text)

    def test_check_rejects_unsafe_catalogs(self):
        for doc in (document(package('opentopomap-russia', countryCodes=['RU']), provider='opentopomap'),
                    document(package('freizeitkarte-big', sizeBytes=bundled.FAT32_MAX + 1)),
                    document(package('freizeitkarte-b'), package('freizeitkarte-a')),
                    document(package('freizeitkarte-a'), package('freizeitkarte-a'))):
            with self.assertRaises(ValueError):
                bundled.check(bundled.render(doc))
        with self.assertRaises(ValueError):
            bundled.check(json.dumps(document(package('freizeitkarte-a'))))  # not canonical formatting


if __name__ == '__main__':
    unittest.main()

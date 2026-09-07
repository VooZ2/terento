import io
import unittest
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from terento_catalog.contour_source import inspect_contour
from terento_catalog.provider_catalog import OpenTopoMapProviderAdapter

URL = 'https://garmin.opentopomap.org/europe/andorra/otm-andorra-contours.zip'


def archive_bytes(identity=b'OpenTopoMap Andorra', name='otm-andorra-contours.img'):
    header = bytearray(8192)
    header[0x10:0x16] = b'DSKIMG'
    header[0x41:0x47] = b'GARMIN'
    header[100:100+len(identity)] = identity
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, header)
    return output.getvalue()


class ContourSourceTests(unittest.TestCase):
    def inspect(self, payload, *, changed=False):
        class Fetcher:
            def fetch_range(self, url, start, end):
                return SimpleNamespace(url=url, total_size=len(payload), body=payload[start:end+1])
        metadata = (len(payload), '"stable"', 'Thu, 17 Jun 2021 07:58:51 GMT')
        with patch('terento_catalog.contour_source.HTTPRangeFetcher', return_value=Fetcher()), patch('terento_catalog.contour_source._metadata', side_effect=[metadata, (len(payload), '"changed"', metadata[2]) if changed else metadata]):
            return inspect_contour(URL)

    def test_bounded_zip_header_and_independent_date(self):
        result = self.inspect(archive_bytes())
        self.assertEqual(result.install_size_bytes, 8192)
        self.assertEqual(result.source_updated_at.year, 2021)
        self.assertEqual(result.source_proof['sourceIdentity'], 'opentopomap:andorra:contours')
        self.assertEqual(len(result.source_proof['revision']), 64)

    def test_changed_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.inspect(archive_bytes(), changed=True)

    def test_wrong_region_header_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'header'):
            self.inspect(archive_bytes(b'OpenTopoMap Lithuania'))

    def test_wrong_payload_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'expected IMG'):
            self.inspect(archive_bytes(name='unexpected.img'))

    def test_non_official_path_is_rejected_before_network(self):
        for url in (URL.replace('https:', 'http:'), URL+'?x=1', URL.replace('/andorra/', '/lithuania/')):
            with self.assertRaises(ValueError):
                inspect_contour(url)

    def test_optional_failure_retains_main_and_off_skips_inspection(self):
        class Fetcher:
            def fetch_text(self, url):
                return '<table><tr class="country"><td>Andorra</td><td><a href="europe/andorra/otm-andorra.zip">Garmin</a></td><td><a href="europe/andorra/otm-andorra-contours.zip">Contours</a></td><td>2026-05-24 20:24:18</td></tr></table>'
            def measure_zip(self, url):
                return SimpleNamespace(download_size_bytes=100, install_size_bytes=200, payload_path='otm-andorra.img')
        for mode in ('off', 'public'):
            with patch('terento_catalog.contour_source.inspect_contour', side_effect=OSError('unavailable')) as inspect:
                snapshot = OpenTopoMapProviderAdapter(fetcher=Fetcher(), expected_main_package_count=1, contour_mode=mode).collect()
                self.assertEqual(len(snapshot.packages), 1)
                self.assertEqual([a.kind for a in snapshot.packages[0].artifacts], ['main'])
                self.assertEqual(inspect.call_count, int(mode == 'public'))

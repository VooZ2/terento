import unittest


class MapRandoTests(unittest.TestCase):
    def test_maprando_directory_adapter_daily_identity_and_standalone_variant(self):
        from terento_catalog.maprando import MapRandoProviderAdapter, ImageMeasurement, image_links, policy_identity
        from terento_catalog.provider_catalog import ProviderCollectionError
        root = 'https://ravenfeld.fr/MapRando/'
        class Fetcher:
            def fetch_text(self, url):
                if url == root:
                    return '<a href="France/">France/</a><a href="France_Courbes_IGN/">IGN/</a><a href="https://evil.example/X/">x</a>'
                region = url.rstrip('/').rsplit('/', 1)[1]
                return ''.join(f'<a href="MapRando_{region}_2026_09_{day}.img">map</a>' for day in ('01', '02')) + '<a href="BaseCamp/">BaseCamp/</a>'
            def measure_img(self, url):
                assert url.endswith('_2026_09_02.img')
                return ImageMeasurement(1024)
        snapshot = MapRandoProviderAdapter(fetcher=Fetcher()).collect()
        self.assertEqual(snapshot.definition.default_status, 'ACTIVE')
        self.assertEqual([p.id for p in snapshot.packages], ['maprando-france', 'maprando-france-courbes-ign'])
        self.assertEqual([p.name for p in snapshot.packages], ['France', 'France (IGN contours)'])
        from terento_catalog.maprando_geography import maprando_display_name
        self.assertEqual(maprando_display_name('lituanie', 'Lituanie'), 'Lithuania')
        self.assertEqual(maprando_display_name('californie', 'Californie'), 'California')
        self.assertEqual(maprando_display_name('future-region', 'Future_Region'), 'Future Region')
        self.assertTrue(all(p.release == '2026-09-02' and p.capabilities == ('main',) for p in snapshot.packages))
        self.assertTrue(all(p.artifacts[0].install_size_bytes == 1024 for p in snapshot.packages))
        self.assertEqual(policy_identity('russie-europe'), ('RUSSIEEUROPE', ('RU',)))
        self.assertEqual(policy_identity('crimee'), ('CRIMEA', ('UA',)))
        with self.assertRaises(ProviderCollectionError):
            image_links('<a href="MapRando_France_2026_02_31.img">x</a>', root+'France/', 'France')

    def test_maprando_header_title_and_daily_release_must_match(self):
        from unittest.mock import patch
        from terento_catalog.maprando import inspect_maprando_img
        from terento_catalog.collectors.freizeitkarte.range_zip import RangeResponse
        url = 'https://ravenfeld.fr/MapRando/Lituanie/MapRando_Lituanie_2026_09_02.img'
        header = bytearray(512)
        header[16:22], header[65:71] = b'DSKIMG', b'GARMIN'
        title = b'MapRando Lituanie 02.09.2026'.ljust(50, b' ')
        header[0x49:0x5D], header[0x65:0x83] = title[:20], title[20:]
        def response():
            return RangeResponse(206, 0, 511, 1024, bytes(header), url)
        with patch('terento_catalog.maprando.HTTPRangeFetcher.fetch_range', side_effect=lambda *args: response()):
            self.assertTrue(inspect_maprando_img(url).identity_validated)
            self.assertFalse(inspect_maprando_img(url.replace('_09_02', '_09_03')).identity_validated)
            header[0x65:0x83] = b' '.ljust(30, b' ')
            self.assertFalse(inspect_maprando_img(url).identity_validated)

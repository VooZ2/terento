from __future__ import annotations

import unittest

from terento_catalog.collectors.freizeitkarte.collector import FreizeitkarteCollector


class FakeFetcher:
    release_html = '<p>The Freizeitkarte maps "2/2026" are based on OpenStreetMap data of 2026/05/03.</p>'
    map_html = '<h3><a id="LTU">Republic of Lithuania (LTU+):</a></h3><a href="https://download.freizeitkarte-osm.de/garmin/latest/LTU+_en_gmapsupp.img.zip">gmapsupp</a><hr>'

    def fetch_text(self, url: str) -> str:
        return self.release_html if "release" in url else self.map_html

    def head_size(self, url: str) -> int:
        self.last_url = url
        return 361187697


class FreizeitkarteCollectorTests(unittest.TestCase):
    def test_collects_map_metadata_without_downloading_archive(self) -> None:
        fetcher = FakeFetcher()
        records = FreizeitkarteCollector(
            fetcher=fetcher,
            map_page_urls=("https://www.freizeitkarte-osm.de/garmin/en/maps.html",),
        ).collect()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.map.id, "freizeitkarte-ltu")
        self.assertEqual(record.map.identifier, "LTU+")
        self.assertEqual((record.version.year, record.version.month), (2026, 5))
        self.assertEqual(record.file_size_bytes, 361187697)
        self.assertTrue(record.source_url.endswith("LTU+_en_gmapsupp.img.zip"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from terento_catalog.collectors.freizeitkarte.parser import (
    parse_region_download,
    parse_region_downloads,
    parse_release_page,
)
from terento_catalog.migrate import _statements


class FreizeitkarteParserTests(unittest.TestCase):
    def test_migration_splitter_preserves_semicolons_in_sql_strings(self) -> None:
        statements = _statements(
            "INSERT INTO x VALUES ('license; attribution');\n"
            "INSERT INTO y VALUES ('done');"
        )
        self.assertEqual(len(statements), 2)
        self.assertIn("license; attribution", statements[0])

    def test_current_release_uses_underlying_osm_date_for_comparable_version(self) -> None:
        release = parse_release_page(
            '<p>The Freizeitkarte maps "2/2026" are based on '
            "OpenStreetMap data of 2026/05/03.</p>"
        )
        self.assertEqual(release.raw_version, "2/2026")
        self.assertEqual((release.version.year, release.version.month), (2026, 5))
        self.assertEqual(release.release_date.isoformat(), "2026-05-03")

    def test_legacy_release_is_normalized(self) -> None:
        release = parse_release_page("<p>Release 26.05</p>")
        self.assertEqual(release.raw_version, "Release 26.05")
        self.assertEqual((release.version.year, release.version.month), (2026, 5))

    def test_region_download_only_accepts_gmapsupp_link_in_region_section(self) -> None:
        html = """
        <h3><a id="DEU">Germany (DEU):</a></h3>
        <table><a href="https://download.example/DEU_en_gmapsupp.img.zip">gmapsupp</a></table>
        <hr>
        <h3><a id="LTU">Republic of Lithuania (LTU+):</a></h3>
        <table><a href="https://download.example/LTU+_en_gmapsupp.img.zip">gmapsupp</a></table>
        <hr>
        """
        self.assertEqual(
            parse_region_download(
                html,
                region_code="LTU",
                base_url="https://www.freizeitkarte-osm.de/garmin/en/",
            ),
            "https://download.example/LTU+_en_gmapsupp.img.zip",
        )

    def test_region_downloads_cover_all_sections_and_prefer_english(self) -> None:
        html = """
        <h3><a id="DEU">Federal Republic of Germany (DEU):</a></h3>
        <table>
          <a href="https://download.example/DEU_de_gmapsupp.img.zip">gmapsupp</a>
          <a href="https://download.example/DEU_en_gmapsupp.img.zip">gmapsupp</a>
        </table>
        <h3><a id="RUS-NORTHWEST">Russian Federation (RUS, Northwest):</a></h3>
        <table>
          <a href="https://download.example/RUS_NORTHWEST_ru_gmapsupp.img.zip">gmapsupp</a>
        </table>
        <h3><a id="LTU">Republic of Lithuania (LTU+):</a></h3>
        <table>
          <a href="https://download.example/LTU+_en_gmapsupp.img.zip">gmapsupp</a>
        </table>
        """
        downloads = parse_region_downloads(
            html,
            base_url="https://www.freizeitkarte-osm.de/garmin/en/",
        )
        self.assertEqual([download.region for download in downloads], ["DEU", "RUS-NORTHWEST", "LTU"])
        self.assertEqual(downloads[0].identifier, "DEU")
        self.assertTrue(downloads[0].source_url.endswith("DEU_en_gmapsupp.img.zip"))
        self.assertEqual(downloads[1].identifier, "RUS_NORTHWEST")
        self.assertEqual(downloads[2].name, "Republic of Lithuania")


if __name__ == "__main__":
    unittest.main()

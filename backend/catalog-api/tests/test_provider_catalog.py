from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import unittest

from terento_catalog.catalog import build_catalog
from terento_catalog.opentopomap_contour_audit import audit_opentopomap_contours
from terento_catalog.provider_catalog import OPENTOPO_MAP, OpenTopoMapProviderAdapter, parse_opentopomap_catalog
from terento_catalog.provider_health import HTTPProbeResult, check_provider


UTC = timezone.utc


class ProviderCatalogTests(unittest.TestCase):
    def test_provider_neutral_catalog_keeps_legacy_fields_and_artifacts(self):
        document = build_catalog([
            {
                "provider_id": "opentopomap",
                "provider_name": "OpenTopoMap",
                "provider_adapter_id": "opentopomap",
                "provider_status": "PAUSED",
                "provider_health": "UNKNOWN",
                "provider_website": "https://opentopomap.org/",
                "provider_attribution": "OpenTopoMap",
                "provider_license_information": "ODbL",
                "package_id": "opentopomap-lithuania",
                "provider_region_id": "lithuania",
                "canonical_region_id": "LT",
                "package_name": "OpenTopoMap Lithuania",
                "package_region": "LT",
                "package_country": "Lithuania",
                "release": "2026-05",
                "release_id": "2026-05",
                "version_label": "2026-05",
                "country_codes": ["LT"],
                "region_kind": "country",
                "capabilities": ["main", "contours"],
                "artifact_id": "opentopomap-lithuania-main",
                "artifact_kind": "main",
                "artifact_source_url": "https://garmin.opentopomap.org/LT.zip",
                "artifact_size_bytes": 219000000,
                "artifact_install_size_bytes": 276000000,
                "artifact_required": True,
                "artifact_validation_status": "VALIDATED",
                "artifact_content_type": "application/zip",
            },
        ], datetime(2026, 8, 31, tzinfo=UTC))
        provider = document["providers"][0]
        package = provider["maps"][0]
        artifact = package["artifacts"][0]
        self.assertEqual(document["schemaVersion"], 2)
        self.assertEqual(provider["status"], "PAUSED")
        self.assertEqual(package["release"], "2026-05")
        self.assertEqual(package["sizeBytes"], 219000000)
        self.assertEqual(artifact["sizeBytes"], 276000000)
        self.assertEqual(artifact["downloadSizeBytes"], 219000000)
        self.assertEqual(artifact["validationState"], "validated")

    def test_contour_rollout_modes_are_fail_closed_at_public_catalog_boundary(self):
        common = {
            "provider_id": "opentopomap",
            "provider_name": "OpenTopoMap",
            "provider_adapter_id": "opentopomap",
            "provider_status": "PAUSED",
            "provider_health": "UNKNOWN",
            "provider_website": "https://opentopomap.org/",
            "provider_attribution": "OpenTopoMap",
            "provider_license_information": "ODbL",
            "package_id": "opentopomap-andorra",
            "provider_region_id": "andorra",
            "canonical_region_id": "ANDORRA",
            "package_name": "OpenTopoMap Andorra",
            "package_region": "ANDORRA",
            "package_country": "Andorra",
            "release": "2026-05",
            "release_id": "2026-05",
            "version_label": "2026-05",
            "country_codes": [],
            "region_kind": "country",
            "capabilities": ["main", "contours"],
            "artifact_source_url": "https://garmin.opentopomap.org/europe/andorra/otm-andorra.zip",
            "artifact_size_bytes": 100,
            "artifact_install_size_bytes": 120,
            "artifact_required": True,
            "artifact_validation_status": "VALIDATED",
        }
        rows = [
            {**common, "artifact_id": "opentopomap-andorra-main", "artifact_kind": "main"},
            {
                **common,
                "artifact_id": "opentopomap-andorra-contours",
                "artifact_kind": "contours",
                "artifact_source_url": "https://garmin.opentopomap.org/europe/andorra/otm-andorra-contours.zip",
                "artifact_required": False,
            },
        ]
        timestamp = datetime(2026, 8, 31, tzinfo=UTC)
        for mode, allowlist, expected in (
            ("off", set(), 1),
            ("shadow", set(), 1),
            ("allowlist", {"opentopomap-andorra"}, 2),
            ("public", set(), 2),
        ):
            document = build_catalog(
                list(reversed(rows)),
                timestamp,
                contour_mode=mode,
                contour_allowlist=allowlist,
            )
            self.assertEqual(len(document["providers"][0]["maps"][0]["artifacts"]), expected)
            self.assertEqual(document["providers"][0]["maps"][0]["sourceURL"], common["artifact_source_url"])

    def test_catalog_preserves_unavailable_package_without_placeholder_artifact(self):
        unknown_install = build_catalog([
            {
                    "provider_id": "freizeitkarte",
                    "provider_name": "Freizeitkarte",
                    "provider_adapter_id": "freizeitkarte",
                    "provider_status": "ACTIVE",
                    "provider_health": "UNKNOWN",
                    "provider_website": "https://www.freizeitkarte-osm.de/",
                    "provider_attribution": "OSM",
                    "provider_license_information": "ODbL",
                    "package_id": "freizeitkarte-lithuania",
                    "provider_region_id": "LTU+",
                    "canonical_region_id": "LT",
                    "package_name": "Lithuania",
                    "package_region": "LT",
                    "release": "2026-05",
                    "country_codes": ["LT"],
                    "region_kind": "country",
                    "artifact_id": "freizeitkarte-lithuania-main",
                    "artifact_kind": "main",
                    "artifact_source_url": "https://download.freizeitkarte-osm.de/LTU.zip",
                    "artifact_size_bytes": 100,
                    "artifact_install_size_bytes": None,
                    "artifact_required": True,
                    "artifact_validation_status": "NOT_VALIDATED",
            },
            {
                "provider_id": "freizeitkarte",
                "provider_name": "Freizeitkarte",
                "provider_adapter_id": "freizeitkarte",
                "provider_status": "ACTIVE",
                "provider_health": "UNKNOWN",
                "provider_website": "https://www.freizeitkarte-osm.de/",
                "provider_attribution": "OSM",
                "provider_license_information": "ODbL",
                "package_id": "freizeitkarte-unavailable",
                "provider_region_id": "UNKNOWN",
                "canonical_region_id": "XX",
                "package_name": "Unavailable",
                "package_region": "XX",
                "release": "unknown",
                "availability": "UNAVAILABLE",
                "artifact_id": None,
            },
        ], datetime(2026, 8, 31, tzinfo=UTC))
        unknown_artifact = unknown_install["providers"][0]["maps"][0]["artifacts"][0]
        self.assertIsNone(unknown_artifact["sizeBytes"])
        self.assertEqual(len(unknown_install["providers"][0]["maps"]), 1)

    def test_provider_native_release_uses_source_date_for_comparable_version(self):
        document = build_catalog([
            {
                "provider_id": "freizeitkarte",
                "provider_name": "Freizeitkarte",
                "provider_adapter_id": "freizeitkarte",
                "provider_status": "ACTIVE",
                "provider_health": "HEALTHY",
                "provider_website": "https://www.freizeitkarte-osm.de/",
                "provider_attribution": "OSM",
                "provider_license_information": "ODbL",
                "package_id": "freizeitkarte-lithuania",
                "provider_region_id": "LTU+",
                "canonical_region_id": "LT",
                "package_name": "Lithuania",
                "package_region": "LT",
                "release": "2/2026",
                "release_id": "2/2026",
                "version_label": "2/2026",
                "package_source_updated_at": datetime(2026, 5, 3, tzinfo=UTC),
                "country_codes": ["LT"],
                "region_kind": "country",
                "capabilities": ["main"],
                "artifact_id": "freizeitkarte-lithuania-main",
                "artifact_kind": "main",
                "artifact_source_url": "https://download.freizeitkarte-osm.de/LTU.zip",
                "artifact_size_bytes": 219000000,
                "artifact_install_size_bytes": 276000000,
                "artifact_required": True,
                "artifact_validation_status": "VALIDATED",
                "artifact_content_type": "application/zip",
            },
        ], datetime(2026, 8, 31, tzinfo=UTC))

        package = document["providers"][0]["maps"][0]
        self.assertEqual(package["release"], "2/2026")
        self.assertEqual(package["version"], {"year": 2026, "month": 5})
        self.assertEqual(package["releaseDate"], "2026-05-03T00:00:00+00:00")
        self.assertEqual(
            package["releaseMetadata"]["versionLabel"],
            "2/2026",
        )
        self.assertNotEqual(package["version"], {"year": 2000, "month": 1})

    def test_provider_neutral_catalog_does_not_emit_historical_version_sentinel(self):
        document = build_catalog([
            {
                "provider_id": "freizeitkarte",
                "provider_name": "Freizeitkarte",
                "provider_adapter_id": "freizeitkarte",
                "provider_status": "ACTIVE",
                "provider_health": "UNKNOWN",
                "package_id": "freizeitkarte-unknown",
                "provider_region_id": "UNKNOWN",
                "canonical_region_id": "XX",
                "package_name": "Unknown",
                "package_region": "XX",
                "release": "unknown",
                "artifact_id": "freizeitkarte-unknown-main",
                "artifact_kind": "main",
                "artifact_source_url": "https://download.freizeitkarte-osm.de/unknown.zip",
                "artifact_size_bytes": 100,
                "artifact_install_size_bytes": None,
                "artifact_required": True,
            },
        ], datetime(2026, 8, 31, tzinfo=UTC))

        self.assertEqual(document["providers"][0]["maps"], [])

    def test_opentopomap_parser_accepts_only_provider_zip_sources(self):
        html = """
        <table>
        <tr class="country"><td>Afghanistan</td>
          <td><a href="asia/afghanistan/otm-afghanistan.zip">Garmin</a></td>
          <td><a href="asia/afghanistan/otm-afghanistan-contours.zip">Garmin contours</a></td>
          <td><a href="asia/afghanistan/otm-afghanistan-basecamp.zip">Basecamp</a></td>
          <td>2026-05-26 08:33:53</td></tr>
        <tr class="country"><td>US-Midwest</td>
          <td><a href="north-america/us-midwest/otm-us-midwest.zip">Garmin</a></td>
          <td><a href="north-america/us-midwest/otm-us-midwest-contours.zip">Garmin contours</a></td>
          <td>2026-06-22 03:53:18</td></tr>
        </table>
        <a href="https://evil.example/otm-afghanistan.zip">evil</a>
        <a href="/maps/README.txt">readme</a>
        """
        links = parse_opentopomap_catalog(html, OPENTOPO_MAP.catalog_url)
        self.assertEqual(
            [(item.provider_region_id, item.region, item.kind) for item in links],
            [
                ("afghanistan", "AFGHANISTAN", "main"),
                ("afghanistan", "AFGHANISTAN", "contours"),
                ("us-midwest", "USMIDWEST", "main"),
                ("us-midwest", "USMIDWEST", "contours"),
            ],
        )
        self.assertEqual(links[0].country_name, "Afghanistan")
        self.assertEqual(links[0].source_updated_at.isoformat(), "2026-05-26T08:33:53+00:00")
        self.assertTrue(all(
            (urlsplit(item.source_url).hostname or "").casefold() == "opentopomap.org"
            or (urlsplit(item.source_url).hostname or "").casefold().endswith(".opentopomap.org")
            for item in links
        ))

    def test_opentopomap_parser_supports_all_provider_region_shapes(self):
        html = """
        <a href="europe/andorra/otm-andorra.zip">Garmin</a>
        <a href="europe/azores/otm-azores.zip">Garmin</a>
        <a href="europe/bosnia-herzegovina/otm-bosnia-herzegovina.zip">Garmin</a>
        <a href="asia/russia-asian-part/otm-russia-asian-part.zip">Garmin</a>
        <a href="north-america/us-midwest/otm-us-midwest.zip">Garmin</a>
        <a href="north-america/canada-east/otm-canada-east.zip">Garmin</a>
        <a href="north-america/canada-west/otm-canada-west.zip">Garmin</a>
        <a href="north-america/canada/otm-canada-contours.zip">Garmin contours</a>
        """
        links = parse_opentopomap_catalog(html, OPENTOPO_MAP.catalog_url)
        self.assertEqual(
            [(item.provider_region_id, item.region) for item in links],
            [
                ("andorra", "ANDORRA"),
                ("azores", "AZORES"),
                ("bosnia-herzegovina", "BOSNIAHERZEGOVINA"),
                ("russia-asian-part", "RUSSIAASIANPART"),
                ("us-midwest", "USMIDWEST"),
                ("canada-east", "CANADAEAST"),
                ("canada-west", "CANADAWEST"),
                ("canada-east", "CANADAEAST"),
                ("canada-west", "CANADAWEST"),
            ],
        )

    def test_opentopomap_adapter_preserves_provider_identity_and_release(self):
        html = """
        <table><tr class="country"><td>Azores</td>
          <td><a href="europe/azores/otm-azores.zip">Garmin</a></td>
          <td><a href="europe/azores/otm-azores-contours.zip">Garmin contours</a></td>
          <td>2026-05-24 20:24:18</td></tr></table>
        """

        class Measurement:
            download_size_bytes = 100
            install_size_bytes = 120
            payload_path = "otm-azores.img"

        class Fetcher:
            def fetch_text(self, url):
                return html

            def measure_zip(self, url):
                return Measurement()

        snapshot = OpenTopoMapProviderAdapter(
            fetcher=Fetcher(), expected_main_package_count=1, max_workers=1
        ).collect()
        package = snapshot.packages[0]
        self.assertEqual(package.id, "opentopomap-azores")
        self.assertEqual(package.provider_region_id, "azores")
        self.assertEqual(package.canonical_region_id, "AZORES")
        self.assertEqual(package.release, "2026-05")
        self.assertEqual(package.source_updated_at.isoformat(), "2026-05-24T20:24:18+00:00")
        self.assertEqual(
            [artifact.id for artifact in package.artifacts],
            ["opentopomap-azores-main"],
        )
        self.assertEqual(package.capabilities, ("main",))

        class RecordingFetcher(Fetcher):
            def __init__(self):
                self.measured_urls = []

            def measure_zip(self, url):
                self.measured_urls.append(url)
                return Measurement()

        recording_fetcher = RecordingFetcher()
        OpenTopoMapProviderAdapter(
            fetcher=recording_fetcher, expected_main_package_count=1, max_workers=1
        ).collect()
        self.assertEqual(recording_fetcher.measured_urls, [
            "https://garmin.opentopomap.org/europe/azores/otm-azores.zip"
        ])

        with self.assertRaisesRegex(RuntimeError, "expected 2, found 1"):
            OpenTopoMapProviderAdapter(
                fetcher=Fetcher(), expected_main_package_count=2
            ).collect()

    def test_opentopomap_contour_audit_counts_shared_sources(self):
        html = """
        <table>
          <tr class="country"><td>Andorra</td>
            <td><a href="europe/andorra/otm-andorra.zip">Garmin</a></td>
            <td><a href="europe/andorra/otm-andorra-contours.zip">Contours</a></td>
          </tr>
          <tr class="country"><td>Canada East</td>
            <td><a href="north-america/canada-east/otm-canada-east.zip">Garmin</a></td>
            <td><a href="north-america/canada/otm-canada-contours.zip">Contours</a></td>
          </tr>
          <tr class="country"><td>Canada West</td>
            <td><a href="north-america/canada-west/otm-canada-west.zip">Garmin</a></td>
          </tr>
        </table>
        """

        class Measurement:
            download_size_bytes = 100
            install_size_bytes = 120
            payload_path = "gmapsupp.img"

        class Fetcher:
            def fetch_text(self, url):
                return html

            def measure_zip(self, url):
                return Measurement()

        report = audit_opentopomap_contours(
            fetcher=Fetcher(),
            expected_main_package_count=3,
            sample_region=None,
        )
        self.assertEqual(report.main_package_count, 3)
        self.assertEqual(report.unique_contour_source_count, 2)
        self.assertEqual(report.package_to_contour_attachment_count, 3)
        self.assertEqual(report.shared_contour_sources, 1)
        self.assertEqual(report.validated_contours, 3)
        self.assertEqual(report.sample_status, "NOT_REQUESTED")

    def test_opentopomap_russia_packages_emit_policy_country_code(self):
        html = """
        <table>
          <tr class="country"><td>Russia-Asian-Part</td>
            <td><a href="asia/russia-asian-part/otm-russia-asian-part.zip">Garmin</a></td>
            <td>2026-05-24 20:24:18</td></tr>
          <tr class="country"><td>Russia-European-Part</td>
            <td><a href="europe/russia-european-part/otm-russia-european-part.zip">Garmin</a></td>
            <td>2026-05-24 20:24:18</td></tr>
        </table>
        """

        class Measurement:
            download_size_bytes = 100
            install_size_bytes = 120
            payload_path = "otm-russia.img"

        class Fetcher:
            def fetch_text(self, url):
                return html

            def measure_zip(self, url):
                return Measurement()

        snapshot = OpenTopoMapProviderAdapter(
            fetcher=Fetcher(), expected_main_package_count=2, max_workers=1
        ).collect()
        self.assertEqual(
            [(package.provider_region_id, package.country_codes) for package in snapshot.packages],
            [
                ("russia-asian-part", ("RU",)),
                ("russia-european-part", ("RU",)),
            ],
        )

    def test_otm_snapshot_cleanup_hides_deferred_contours(self):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "db.py"
        ).read_text(encoding="utf-8")
        self.assertIn('if definition.id in {"opentopomap", "maprando", "bbbike"}:', source)
        self.assertIn("DELETE FROM map_artifact", source)
        self.assertIn("availability = 'RETIRED'", source)
        self.assertIn("A complete provider snapshot retires only that provider", source)

    def test_collection_failure_audit_keeps_provider_error_detail(self):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "http_api.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"detail": str(exc)[:500]', source)

    def test_provider_health_checks_mime_zip_and_img(self):
        class Measurement:
            install_size_bytes = 123

        class Probe:
            def inspect(self, url, *, read_body=False):
                return HTTPProbeResult(200, url, "application/zip", body=b"catalog")

            def inspect_zip(self, url):
                return Measurement()

            def inspect_magic(self, url):
                return b"PK\x03\x04"

        result = check_provider(
            OPENTOPO_MAP,
            download_urls=["https://garmin.opentopomap.org/LT.zip"],
            source_updated_at="2026-08-30T00:00:00Z",
            probe=Probe(),
        )
        self.assertEqual(result.status, "HEALTHY")
        self.assertEqual(result.mime_status, "HEALTHY")
        self.assertEqual(result.magic_status, "HEALTHY")
        self.assertEqual(result.zip_status, "HEALTHY")
        self.assertEqual(result.img_status, "HEALTHY")

        from terento_catalog.provider_catalog import MAPRANDO
        from terento_catalog.maprando import ImageMeasurement
        class RawProbe(Probe):
            def inspect(self, url, *, read_body=False):
                return HTTPProbeResult(200, url, "application/octet-stream", body=b"catalog")
            def inspect_img(self, url):
                return ImageMeasurement(1024)
            def inspect_zip(self, url):
                raise AssertionError("Raw IMG must not enter ZIP inspection")
        raw = check_provider(MAPRANDO, download_urls=["https://ravenfeld.fr/MapRando/Lituanie/MapRando_Lituanie_2026_09_02.img"], probe=RawProbe())
        self.assertEqual(raw.status, "HEALTHY")
        self.assertEqual(raw.img_status, "HEALTHY")
        self.assertEqual(raw.zip_status, "NOT_APPLICABLE")

        no_date = check_provider(
            OPENTOPO_MAP,
            download_urls=["https://garmin.opentopomap.org/LT.zip"],
            probe=Probe(),
        )
        self.assertEqual(no_date.status, "HEALTHY")
        self.assertEqual(no_date.last_update_status, "UNKNOWN")

        source_only = check_provider(OPENTOPO_MAP, probe=Probe())
        self.assertEqual(source_only.status, "HEALTHY")
        self.assertEqual(source_only.download_status, "UNKNOWN")

        class FailedDownloadProbe(Probe):
            def inspect(self, url, *, read_body=False):
                if url.endswith("map.zip"):
                    raise OSError("offline")
                return super().inspect(url, read_body=read_body)

        failed_download = check_provider(
            OPENTOPO_MAP,
            download_urls=["https://garmin.opentopomap.org/map.zip"],
            probe=FailedDownloadProbe(),
        )
        self.assertEqual(failed_download.status, "DOWN")
        self.assertEqual(failed_download.download_status, "DOWN")

import json
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from terento_catalog.catalog import build_catalog
from terento_catalog.admin import token_hash
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.map_events import (
    MapEventValidationError,
    validate_map_event,
    validate_statistics_filters,
)
from terento_catalog.provider_catalog import (
    OPENTOPO_MAP,
    OpenTopoMapProviderAdapter,
    parse_opentopomap_catalog,
)
from terento_catalog.provider_health import HTTPProbeResult, check_provider


UTC = timezone.utc


class FakeProviderDatabase:
    def __init__(self) -> None:
        self.events: set[str] = set()
        self.status = "ACTIVE"
        self.audits: list[dict] = []

    def admin_user_count(self) -> int:
        return 1

    def admin_review_summary(self):
        return {
            "installationIssues": 0,
            "identityPending": 0,
            "readyToPublish": 0,
            "total": 0,
        }

    def admin_session(self, token: str):
        return {"id": 7, "csrf_token_hash": token_hash("csrf")} if token == token_hash("session") else None

    def catalog_snapshot(self):
        return [], datetime(2026, 8, 31, tzinfo=UTC)

    def provider_rows(self):
        return [{
            "provider_id": "freizeitkarte",
            "provider_name": "Freizeitkarte",
            "adapter_id": "freizeitkarte",
            "status": self.status,
            "website": "https://www.freizeitkarte-osm.de/",
            "license_information": "OSM / FZK",
            "attribution": "OSM",
            "last_catalog_sync": datetime(2026, 8, 30, tzinfo=UTC),
            "health": "HEALTHY",
            "last_checked_at": datetime(2026, 8, 30, tzinfo=UTC),
            "active_package_count": 1,
            "broken_package_count": 0,
        }]

    def provider_detail(self, provider_id: str):
        if provider_id != "freizeitkarte":
            return None
        return {
            "provider_id": provider_id,
            "provider_name": "Freizeitkarte",
            "adapter_id": provider_id,
            "status": self.status,
            "website": "https://www.freizeitkarte-osm.de/",
            "license_information": "OSM / FZK",
            "attribution": "OSM",
            "sources": [],
            "packages": [],
            "health": None,
            "health_history": [],
        }

    def map_statistics(self, filters):
        return [{
            "provider_id": filters.get("provider", "freizeitkarte"),
            "map_package_id": filters.get("map"),
            "region": filters.get("region", "LT"),
            "event_type": filters.get("eventType", "INSTALL_SUCCEEDED"),
            "outcome": "SUCCEEDED",
            "event_count": 1,
            "operation_count": 1,
            "first_occurred_at": datetime(2026, 8, 31, tzinfo=UTC),
            "last_occurred_at": datetime(2026, 8, 31, tzinfo=UTC),
        }]

    def insert_map_event(self, event):
        if event["id"] in self.events:
            return False
        self.events.add(event["id"])
        return True

    def ensure_provider_definition(self, definition):
        return None

    def provider_download_urls(self, provider_id):
        return []

    def provider_runs(self, provider_id):
        return []

    def audit_rows(self, provider_id):
        return []

    def record_provider_health(self, result):
        return 11

    def record_admin_audit(self, **kwargs):
        self.audits.append(kwargs)

    def set_provider_status(self, provider_id, status, **kwargs):
        if provider_id != "freizeitkarte":
            return False
        self.status = status
        return True

    def csrf_valid(self, session, token):
        return token == "csrf"


class Beta8APITests(unittest.TestCase):
    def test_provider_api_migration_is_additive_and_has_required_contract(self):
        migration = (
            Path(__file__).parents[1]
            / "src"
            / "terento_catalog"
            / "migrations"
            / "026_provider_neutral_map_api.sql"
        ).read_text(encoding="utf-8")
        for table in (
            "provider_source",
            "map_package",
            "map_artifact",
            "provider_health_check",
            "catalog_collection_run",
            "map_download_event",
            "admin_audit_log",
        ):
            self.assertIn(f"CREATE TABLE {table}", migration)
        for column in ("adapter_id", "status", "license", "last_catalog_sync"):
            self.assertIn(column, migration)
        for column in ("kind", "source_url", "size_bytes", "checksum_sha256", "content_type", "required"):
            self.assertIn(column, migration)
        self.assertIn("magic_status", migration)
        for column in ("old_status", "new_status", "reason"):
            self.assertIn(column, migration)
        self.assertNotIn("DROP TABLE", migration)
        self.assertNotIn("BYTEA", migration)

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

    def test_map_event_validation_is_private_and_normalizes_identifiers(self):
        event = validate_map_event(json.dumps({
            "schemaVersion": 1,
            "id": "A8098C1A-F86E-11DA-BD1A-00112444BE1E",
            "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
            "timestamp": "2026-08-31T10:00:00Z",
            "providerId": "Freizeitkarte",
            "mapId": "FZK-LTU",
            "region": "lt",
            "eventType": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED",
            "appBuild": "beta.8",
        }).encode())
        self.assertEqual(event["providerId"], "freizeitkarte")
        self.assertEqual(event["mapId"], "fzk-ltu")
        self.assertEqual(event["region"], "LT")
        self.assertNotIn("deviceId", event)
        self.assertEqual(event["id"], "a8098c1a-f86e-11da-bd1a-00112444be1e")

    def test_map_event_validation_rejects_raw_device_fields_and_bad_filters(self):
        payload = {
            "schemaVersion": 1,
            "id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
            "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
            "timestamp": "2026-08-31T10:00:00Z",
            "providerId": "freizeitkarte",
            "eventType": "DOWNLOAD_STARTED",
            "outcome": "UNKNOWN",
            "unitId": "must-not-be-accepted",
        }
        with self.assertRaises(MapEventValidationError):
            validate_map_event(json.dumps(payload).encode())
        with self.assertRaises(MapEventValidationError):
            validate_statistics_filters({"region": "LT", "dateFrom": "2026-09-01T00:00:00Z", "dateTo": "2026-08-31T00:00:00Z"})

    def test_opentopomap_parser_accepts_only_provider_zip_sources(self):
        html = """
        <a href="/maps/Lithuania_2026-05.zip">Lithuania Garmin map</a>
        <a href="https://garmin.opentopomap.org/maps/Lithuania_contours.zip">contours</a>
        <a href="https://evil.example/Lithuania.zip">evil</a>
        <a href="/maps/README.txt">readme</a>
        """
        links = parse_opentopomap_catalog(html, OPENTOPO_MAP.catalog_url)
        self.assertEqual([(item.region, item.kind) for item in links], [("LT", "main"), ("LT", "contours")])
        self.assertTrue(all("opentopomap.org" in item.source_url for item in links))

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

    def test_http_map_events_and_admin_provider_routes(self):
        database = FakeProviderDatabase()
        service = CatalogService(database)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cookie = "terento_admin_session=session; terento_admin_csrf=csrf"
            response, body = self._request(server, "GET", "/admin/providers.json", headers={"Cookie": cookie})
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(body)["providers"][0]["id"], "freizeitkarte")
            self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

            event = json.dumps({
                "schemaVersion": 1,
                "id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
                "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
                "timestamp": "2026-08-31T10:00:00Z",
                "providerId": "freizeitkarte",
                "mapId": "fzk-ltu",
                "region": "LT",
                "eventType": "INSTALL_SUCCEEDED",
                "outcome": "SUCCEEDED",
                "appBuild": "beta.8",
            }).encode()
            first, first_body = self._request(server, "POST", "/map-events", event, {"Content-Type": "application/json"})
            second, second_body = self._request(server, "POST", "/map-events", event, {"Content-Type": "application/json"})
            self.assertEqual(first.status, 201)
            self.assertEqual(second.status, 200)
            self.assertEqual(json.loads(first_body)["operationId"], json.loads(second_body)["operationId"])

            with patch("terento_catalog.http_api.run_provider_health_check") as health_check:
                health_check.return_value = type("Health", (), {
                    "status": "HEALTHY",
                    "as_database_values": lambda self: {"provider_id": "freizeitkarte", "status": "HEALTHY"},
                })()
                checked, checked_body = self._request(
                    server,
                    "POST",
                    "/admin/providers/freizeitkarte/check",
                    b"{}",
                    {"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": "csrf"},
                )
            self.assertEqual(checked.status, 200)
            self.assertEqual(json.loads(checked_body)["status"], "ok")
            self.assertTrue(database.audits)

            statistics, statistics_body = self._request(
                server,
                "GET",
                "/admin/map-statistics.json?provider=freizeitkarte&region=lt",
                headers={"Cookie": cookie},
            )
            self.assertEqual(statistics.status, 200)
            self.assertEqual(json.loads(statistics_body)["rows"][0]["region"], "LT")

            state, state_body = self._request(
                server,
                "POST",
                "/admin/providers/freizeitkarte/state",
                json.dumps({"status": "paused"}).encode(),
                {"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": "csrf"},
            )
            self.assertEqual(state.status, 200)
            self.assertEqual(json.loads(state_body)["result"]["status"], "PAUSED")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_admin_pages_require_login_and_render_provider_statistics_views(self):
        database = FakeProviderDatabase()
        service = CatalogService(database)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/admin/providers", "/admin/map-statistics", "/admin/providers/freizeitkarte"):
                response, _ = self._request(server, "GET", path)
                self.assertEqual(response.status, 303)
                self.assertEqual(response.headers["Location"], "/admin/login")

            cookie = "terento_admin_session=session; terento_admin_csrf=csrf"
            providers, providers_body = self._request(server, "GET", "/admin/providers", headers={"Cookie": cookie})
            self.assertEqual(providers.status, 200)
            self.assertIn(b"Providers", providers_body)
            self.assertIn(b"Freizeitkarte", providers_body)

            detail, detail_body = self._request(server, "GET", "/admin/providers/freizeitkarte", headers={"Cookie": cookie})
            self.assertEqual(detail.status, 200)
            self.assertIn(b"Provider metadata", detail_body)
            self.assertIn(b"Health check history", detail_body)
            self.assertIn(b"Collect catalog", detail_body)

            statistics, statistics_body = self._request(server, "GET", "/admin/map-statistics", headers={"Cookie": cookie})
            self.assertEqual(statistics.status, 200)
            self.assertIn(b"Map statistics", statistics_body)
            self.assertIn(b"7 days", statistics_body)
            self.assertIn(b"Install success", statistics_body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    @staticmethod
    def _request(server, method, path, body=None, headers=None):
        connection = HTTPConnection(*server.server_address)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data


if __name__ == "__main__":
    unittest.main()

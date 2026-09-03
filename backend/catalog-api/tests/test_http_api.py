from __future__ import annotations

import json
import struct
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection

from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.db import Database
from terento_catalog.device_catalog import build_device_catalog
from terento_catalog.asset_storage import AssetStorage
from http.server import ThreadingHTTPServer
from pathlib import Path


class FakeDatabase(Database):
    def __init__(self) -> None:
        self.operational_observations = []

    def health(self) -> bool:
        return True

    def prune_compatibility_events(self) -> int:
        return 0

    def provider_rows(self):
        now = datetime.now(timezone.utc)
        return [{
            "provider_id": "freizeitkarte", "provider_name": "Freizeitkarte",
            "adapter_id": "freizeitkarte", "status": "ACTIVE",
            "health": "HEALTHY", "last_catalog_sync": now,
            "last_collection_status": "SUCCEEDED",
            "last_collection_success_at": now,
            "latest_release": "2026-09", "active_package_count": 63,
        }]

    def record_operational_observation(self, observation):
        if any(item["observation_id"] == observation["observation_id"] for item in self.operational_observations):
            return False
        self.operational_observations.append(observation)
        return True

    def catalog_snapshot(self):
        return [
            {
                "provider_id": "freizeitkarte",
                "provider_name": "Freizeitkarte",
                "provider_website": "https://www.freizeitkarte-osm.de/garmin/en/mitteleuropa.html",
                "provider_license_information": "OSM / FZK",
                "provider_attribution": "Map data © OpenStreetMap contributors",
                "provider_license_url": "https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
                "map_id": "freizeitkarte-deu",
                "map_name": "Germany",
                "region": "DEU",
                "country": "Germany",
                "identifier": "DEU+",
                "version_year": 2026,
                "version_month": 5,
                "file_size_bytes": 361187697,
                "download_size_bytes": 361187697,
                "install_size_bytes": 348684288,
                "source_url": "https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip",
                "release_date": datetime(2026, 5, 3, tzinfo=timezone.utc).date(),
            }
        ], datetime(2026, 5, 3, tzinfo=timezone.utc)

    def device_catalog_snapshot(self):
        return [
            {
                "family_canonical_name": "fenix",
                "family_name": "fēnix",
                "device_id": "garmin-fenix-8-47-amoled",
                "manufacturer": "Garmin",
                "model": "fēnix 8",
                "canonical_model": "fenix 8",
                "variant": "47 mm, AMOLED",
                "case_size_mm": 47,
                "display_type": "AMOLED",
                "part_number": "010-02904-10",
                "product_url": "https://www.garmin.com/en-US/p/1228429/",
                "active": True,
                "map_capable": True,
                "asset_status": "AVAILABLE",
                "asset_url": "https://api.terento.app/assets/devices/garmin/fenix-8.webp",
                "asset_type": "product-image",
                "asset_sha256": "abc123",
                "asset_mime_type": "image/webp",
                "asset_width": 640,
                "asset_height": 640,
                "asset_version": 1,
                "asset_scope": "MODEL_SIZE",
                "asset_attribution": "Garmin; approved Terento asset record",
                "asset_source_type": "OFFICIAL_PRODUCT_MEDIA",
                "asset_source_brand": "Garmin",
                "asset_attribution_required": True,
                "asset_storage_key": "devices/garmin/fenix-8.webp",
                "source_image_url": "https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg",
            }
        ], datetime(2026, 5, 3, tzinfo=timezone.utc)


class HTTPAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(CatalogService(FakeDatabase(), operations_ingest_secret="test-operations-secret")),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path: str, headers: dict[str, str] | None = None):
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def post_json(self, path: str, document: dict, headers: dict[str, str] | None = None):
        connection = HTTPConnection(*self.server.server_address)
        body = json.dumps(document).encode()
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        connection.request("POST", path, body=body, headers=request_headers)
        response = connection.getresponse()
        response_body = response.read()
        connection.close()
        return response, response_body

    def test_catalog_contract_and_cache_headers(self) -> None:
        response, body = self.request("/maps/catalog.json")
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertEqual(document["catalogVersion"], 1)
        self.assertEqual(document["providers"][0]["maps"][0]["region"], "DEU")
        self.assertEqual(
            document["providers"][0]["maps"][0]["downloadSizeBytes"], 361187697
        )
        self.assertEqual(
            document["providers"][0]["maps"][0]["installSizeBytes"], 348684288
        )
        self.assertIn("ETag", response.headers)
        self.assertIn("Last-Modified", response.headers)
        self.assertIn("Cache-Control", response.headers)

        cached, cached_body = self.request(
            "/maps/catalog.json",
            {"If-None-Match": response.headers["ETag"]},
        )
        self.assertEqual(cached.status, 304)
        self.assertEqual(cached_body, b"")

    def test_health_is_not_cached(self) -> None:
        response, body = self.request("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_operational_observation_requires_bearer_secret_and_is_idempotent(self) -> None:
        document = {
            "schemaVersion": 1,
            "observationId": "weekly-123",
            "kind": "WEEKLY_TEST",
            "component": "test-matrix",
            "status": "HEALTHY",
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "sourceRunId": "123",
            "sourceRunUrl": "https://github.com/VooZ2/terento/actions/runs/123",
            "commitSha": "a" * 40,
            "releaseVersion": "1.0.0-beta.9",
            "buildNumber": "9",
            "summary": "All canonical suites passed.",
            "details": {"site": "success", "backend": "success"},
        }
        unauthorized, _ = self.post_json("/internal/operations/observations", document)
        self.assertEqual(unauthorized.status, 401)
        headers = {"Authorization": "Bearer test-operations-secret"}
        created, body = self.post_json("/internal/operations/observations", document, headers)
        self.assertEqual(created.status, 201)
        self.assertEqual(json.loads(body), {"status": "stored"})
        duplicate, body = self.post_json("/internal/operations/observations", document, headers)
        self.assertEqual(duplicate.status, 200)
        self.assertEqual(json.loads(body), {"status": "duplicate"})

    def test_operational_report_context_is_private_and_contains_provider_release(self) -> None:
        unauthorized, _ = self.request("/internal/operations/report-context")
        self.assertEqual(unauthorized.status, 401)
        response, body = self.request(
            "/internal/operations/report-context",
            {"Authorization": "Bearer test-operations-secret"},
        )
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        provider = next(item for item in document["providers"] if item["id"] == "freizeitkarte")
        self.assertEqual(provider["status"], "HEALTHY")
        self.assertEqual(provider["latestRelease"], "2026-09")
        self.assertFalse(provider["newReleaseDetectedInLast7Days"])

    def test_device_catalog_contract_and_conditional_get(self) -> None:
        response, body = self.request("/devices/catalog.json")
        document = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertEqual(document["catalogVersion"], 2)
        self.assertEqual(document["manufacturer"], "Garmin")
        self.assertEqual(document["devices"][0]["family"], "fenix")
        self.assertEqual(document["devices"][0]["model"], "fēnix 8")
        self.assertEqual(document["devices"][0]["asset"]["sha256"], "abc123")
        self.assertEqual(
            document["devices"][0]["asset"]["attribution"],
            "Garmin; approved Terento asset record",
        )
        self.assertEqual(document["devices"][0]["asset"]["scope"], "MODEL_SIZE")
        self.assertEqual(document["devices"][0]["asset"]["status"], "AVAILABLE")
        self.assertEqual(
            document["devices"][0]["sourceAsset"]["url"],
            "https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg",
        )
        self.assertEqual(
            document["devices"][0]["asset"]["source"],
            {
                "type": "OFFICIAL_PRODUCT_MEDIA",
                "brand": "Garmin",
                "attributionRequired": True,
            },
        )
        self.assertEqual(
            set(document["devices"][0]),
            {
                "id", "manufacturer", "family", "familyName", "model",
                "canonicalModel", "variant", "caseSizeMm", "displayType",
                "partNumber", "productURL", "active", "mapCapable", "asset", "sourceAsset",
            },
        )
        self.assertTrue(document["devices"][0]["mapCapable"])
        self.assertEqual(document["legal"]["manufacturerNotice"], True)
        self.assertIn("Terento is an independent open-source project", document["legal"]["text"])
        raw_json = json.dumps(document, ensure_ascii=False)
        self.assertNotIn("[https://", raw_json)
        self.assertNotIn("](https://", raw_json)
        self.assertIn("ETag", response.headers)
        self.assertIn("Last-Modified", response.headers)

        cached, cached_body = self.request(
            "/devices/catalog.json",
            {"If-None-Match": response.headers["ETag"]},
        )
        self.assertEqual(cached.status, 304)
        self.assertEqual(cached_body, b"")

    def test_device_catalog_database_projection_includes_map_capability(self) -> None:
        import inspect

        source = inspect.getsource(Database.device_catalog_snapshot)
        self.assertIn("dm.map_capable", source)

    def test_non_approved_asset_is_not_serialized(self) -> None:
        row = {
            "family_canonical_name": "fenix",
            "family_name": "fēnix",
            "device_id": "garmin-fenix-8-47-amoled",
            "manufacturer": "Garmin",
            "model": "fēnix 8",
            "canonical_model": "fenix 8",
            "variant": "47 mm, AMOLED",
            "case_size_mm": 47,
            "display_type": "AMOLED",
            "part_number": None,
            "product_url": "https://www.garmin.com/en-US/p/1228429/",
            "active": True,
            "asset_status": "PENDING_REVIEW",
            "asset_url": "https://api.terento.app/assets/devices/garmin/pending.webp",
        }
        document = build_device_catalog([row], datetime(2026, 5, 3, tzinfo=timezone.utc))
        self.assertEqual(document["devices"][0]["asset"], {"status": "MISSING"})

    def test_non_controlled_approved_asset_is_not_serialized(self) -> None:
        row = {
            "family_canonical_name": "fenix",
            "family_name": "fēnix",
            "device_id": "garmin-fenix-8-47-amoled",
            "manufacturer": "Garmin",
            "model": "[fēnix 8](https://www.garmin.com/device)",
            "canonical_model": "fenix 8",
            "variant": "47 mm",
            "case_size_mm": 47,
            "display_type": None,
            "part_number": None,
            "product_url": "https://www.garmin.com/en-US/p/1228429/",
            "active": True,
            "asset_status": "AVAILABLE",
            "asset_url": "https://www.garmin.com/images/fenix.webp",
            "asset_scope": "EXACT_VARIANT",
        }
        document = build_device_catalog([row], datetime(2026, 5, 3, tzinfo=timezone.utc))
        self.assertEqual(document["devices"][0]["asset"], {"status": "MISSING"})
        self.assertEqual(document["devices"][0]["model"], "fēnix 8")

    def test_source_types_and_compatibility_are_independent(self) -> None:
        base = {
            "family_canonical_name": "fenix",
            "family_name": "fēnix",
            "device_id": "garmin-fenix-8-47-amoled",
            "manufacturer": "Garmin",
            "model": "fēnix 8",
            "canonical_model": "fenix 8",
            "variant": "47 mm, AMOLED",
            "case_size_mm": 47,
            "display_type": "AMOLED",
            "part_number": None,
            "product_url": "https://www.garmin.com/en-US/p/1228429/",
            "active": True,
            "asset_status": "AVAILABLE",
            "asset_url": "https://api.terento.app/assets/devices/garmin/fenix-8.webp",
            "asset_scope": "EXACT_VARIANT",
            "asset_storage_key": "devices/garmin/fenix-8.webp",
            "asset_version": 1,
        }
        source_rows = (
            ("OFFICIAL_PRODUCT_MEDIA", "Garmin", True),
            ("TERENTO_RENDER", "Terento", False),
            ("GENERIC_FALLBACK", "Terento", False),
        )
        for source_type, brand, required in source_rows:
            row = {
                **base,
                "asset_source_type": source_type,
                "asset_source_brand": brand,
                "asset_attribution_required": required,
                "compatibility_status": "SUPPORTED",
            }
            device = build_device_catalog(
                [row], datetime(2026, 5, 3, tzinfo=timezone.utc)
            )["devices"][0]
            self.assertEqual(device["asset"]["source"]["type"], source_type)
            self.assertNotIn("compatibility", device)

        testing_row = {
            **base,
            "asset_status": "AVAILABLE",
            "asset_source_type": "OFFICIAL_PRODUCT_MEDIA",
            "asset_source_brand": "Garmin",
            "asset_attribution_required": True,
            "compatibility_status": "TESTING",
        }
        testing_device = build_device_catalog(
            [testing_row], datetime(2026, 5, 3, tzinfo=timezone.utc)
        )["devices"][0]
        self.assertEqual(testing_device["asset"]["status"], "AVAILABLE")
        self.assertNotIn("compatibility", testing_device)

        verified_row = {
            **base,
            "asset_status": "MISSING",
            "asset_url": None,
            "asset_storage_key": None,
            "compatibility_status": "VERIFIED",
        }
        verified_device = build_device_catalog(
            [verified_row], datetime(2026, 5, 3, tzinfo=timezone.utc)
        )["devices"][0]
        self.assertEqual(verified_device["asset"], {"status": "MISSING"})
        self.assertNotIn("compatibility", verified_device)

    def test_available_asset_without_source_metadata_fails_closed(self) -> None:
        row = {
            "family_canonical_name": "fenix",
            "family_name": "fēnix",
            "device_id": "garmin-fenix-8-47-amoled",
            "manufacturer": "Garmin",
            "model": "fēnix 8",
            "canonical_model": "fenix 8",
            "variant": "47 mm, AMOLED",
            "case_size_mm": 47,
            "display_type": "AMOLED",
            "part_number": None,
            "product_url": "https://www.garmin.com/en-US/p/1228429/",
            "active": True,
            "asset_status": "AVAILABLE",
            "asset_url": "https://api.terento.app/assets/devices/garmin/legacy.webp",
            "asset_scope": "MODEL",
            "asset_storage_key": "devices/garmin/legacy.webp",
        }
        device = build_device_catalog(
            [row], datetime(2026, 5, 3, tzinfo=timezone.utc)
        )["devices"][0]
        self.assertEqual(device["asset"], {"status": "MISSING"})

    def test_official_source_image_is_public_metadata_only(self) -> None:
        row = {
            "family_canonical_name": "lily",
            "family_name": "Lily",
            "device_id": "garmin-lily-2-active",
            "manufacturer": "Garmin",
            "model": "Lily 2 Active",
            "canonical_model": "lily 2 active",
            "variant": "",
            "case_size_mm": None,
            "display_type": None,
            "part_number": None,
            "product_url": "https://www.garmin.com/en-US/p/1196650/",
            "active": True,
            "asset_status": "MISSING",
            "asset_url": None,
            "source_image_url": "https://res.garmin.com/en/products/010-02891-00/g/cf-lg.jpg",
        }
        device = build_device_catalog(
            [row], datetime(2026, 5, 3, tzinfo=timezone.utc)
        )["devices"][0]
        self.assertEqual(device["asset"], {"status": "MISSING"})
        self.assertEqual(device["sourceAsset"]["scope"], "MODEL")
        self.assertEqual(
            device["sourceAsset"]["source"],
            {
                "type": "OFFICIAL_PRODUCT_MEDIA",
                "brand": "Garmin",
                "attributionRequired": True,
            },
        )

        row["source_image_url"] = "https://example.com/not-garmin.jpg"
        without_external = build_device_catalog(
            [row], datetime(2026, 5, 3, tzinfo=timezone.utc)
        )["devices"][0]
        self.assertNotIn("sourceAsset", without_external)

    def test_asset_is_served_from_api_domain_and_traversal_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = AssetStorage(Path(directory))
            data = _minimal_vp8x_webp(64, 64)
            stored = storage.store_webp(data, "devices/garmin/fenix-8.webp")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                make_handler(CatalogService(FakeDatabase(), asset_storage=storage)),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", "/assets/devices/garmin/fenix-8.webp")
                response = connection.getresponse()
                body = response.read()
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Content-Type"], "image/webp")
                self.assertEqual(response.headers["ETag"], f'"{stored.sha256}"')
                self.assertEqual(body, data)

                connection = HTTPConnection(*server.server_address)
                connection.request("GET", "/assets/devices/../secret.webp")
                response = connection.getresponse()
                response.read()
                connection.close()
                self.assertEqual(response.status, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


def _minimal_vp8x_webp(width: int, height: int) -> bytes:
    payload = (
        b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    return (
        b"RIFF"
        + struct.pack("<I", 4 + 8 + len(payload))
        + b"WEBP"
        + b"VP8X"
        + struct.pack("<I", len(payload))
        + payload
    )


if __name__ == "__main__":
    unittest.main()

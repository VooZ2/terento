from __future__ import annotations

import struct
import unittest
from datetime import datetime, timezone

from terento_catalog.asset_storage import AssetStorage
from terento_catalog.device_catalog import build_device_catalog


class DeviceAssetPublicationTests(unittest.TestCase):
    def test_available_asset_returns_correctly(self) -> None:
        device = self._catalog_device(scope="MODEL_SIZE")
        asset = device["asset"]

        self.assertEqual(asset["status"], "AVAILABLE")
        self.assertEqual(
            asset["url"],
            "https://api.terento.app/assets/devices/garmin/fenix-8-47-amoled.webp",
        )
        self.assertEqual(asset["sha256"], "18548c918598ae4be80087ae4e2022c28536792941e2ef345a86478f3ff24e6b")

    def test_fenix_8_47_mm_resolves_model_size_asset(self) -> None:
        device = self._catalog_device(scope="MODEL_SIZE")

        self.assertEqual(device["id"], "garmin-fenix-8-47-amoled")
        self.assertEqual(device["family"], "fenix")
        self.assertEqual(device["canonicalModel"], "fenix 8")
        self.assertEqual(device["variant"], "47 mm, AMOLED")
        self.assertEqual(device["asset"]["scope"], "MODEL_SIZE")
        self.assertEqual(device["asset"]["status"], "AVAILABLE")

    def test_missing_asset_still_returns_missing(self) -> None:
        device = self._catalog_device(asset_status="MISSING")

        self.assertEqual(device["asset"], {"status": "MISSING"})

    def test_invalid_asset_url_is_not_published(self) -> None:
        device = self._catalog_device(asset_url="https://www.garmin.com/image.webp")

        self.assertEqual(device["asset"], {"status": "MISSING"})

    def test_non_https_source_url_is_rejected(self) -> None:
        from terento_catalog.asset_admin import _validated_source_url

        with self.assertRaises(SystemExit):
            _validated_source_url("http://example.test/image.jpg")

    def test_attribution_metadata_is_included(self) -> None:
        asset = self._catalog_device(scope="MODEL_SIZE")["asset"]

        self.assertEqual(
            asset["source"],
            {
                "type": "OFFICIAL_PRODUCT_MEDIA",
                "brand": "Garmin",
                "attributionRequired": True,
            },
        )
        self.assertIn("Garmin product media", asset["attribution"])

    def test_validated_webp_produces_dimensions_and_checksum(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            stored = AssetStorage(Path(directory)).store_webp(
                _minimal_vp8x_webp(600, 600),
                "devices/garmin/fenix-8-47-amoled.webp",
            )

        self.assertEqual((stored.width, stored.height), (600, 600))
        self.assertEqual(len(stored.sha256), 64)
        self.assertEqual(stored.url, "https://api.terento.app/assets/devices/garmin/fenix-8-47-amoled.webp")

    def _catalog_device(
        self,
        *,
        asset_status: str = "AVAILABLE",
        asset_url: str | None = "https://api.terento.app/assets/devices/garmin/fenix-8-47-amoled.webp",
        scope: str = "MODEL_SIZE",
    ) -> dict:
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
            "part_number": "010-02904-10",
            "product_url": "https://www.garmin.com/en-US/p/1228429/",
            "active": True,
            "asset_status": asset_status,
            "asset_url": asset_url,
            "asset_scope": scope,
            "asset_storage_key": "devices/garmin/fenix-8-47-amoled.webp",
            "asset_sha256": "18548c918598ae4be80087ae4e2022c28536792941e2ef345a86478f3ff24e6b",
            "asset_version": 1,
            "asset_attribution": "Garmin product media used solely for device identification.",
            "asset_source_type": "OFFICIAL_PRODUCT_MEDIA",
            "asset_source_brand": "Garmin",
            "asset_attribution_required": True,
        }
        return build_device_catalog(
            [row], datetime(2026, 8, 22, tzinfo=timezone.utc)
        )["devices"][0]


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

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from terento_catalog.admin import _admin_device_payload, devices_page


UTC = timezone.utc


def device_row(**changes):
    row = {
        "device_id": "garmin-fenix-8-47-amoled",
        "manufacturer": "Garmin",
        "family_canonical_name": "fenix",
        "family_name": "fēnix",
        "model": "fēnix 8",
        "canonical_model": "fenix 8",
        "variant": "47 mm, AMOLED",
        "case_size_mm": 47,
        "display_type": "AMOLED",
        "part_number": "010-02904-10",
        "product_url": "https://www.garmin.com/en-US/p/1228429/",
        "active": True,
        "map_capable": True,
        "support_status": "SUPPORTED",
        "asset_status": "MISSING",
        "asset_url": None,
        "source_image_url": None,
        "attempted_install_count": 3,
        "successful_install_count": 2,
        "failed_install_count": 1,
        "first_success": datetime(2026, 8, 20, tzinfo=UTC),
        "last_success": datetime(2026, 8, 25, tzinfo=UTC),
        "last_evidence": datetime(2026, 8, 25, tzinfo=UTC),
        "first_seen_at": datetime(2026, 8, 19, tzinfo=UTC),
        "created_at": datetime(2026, 8, 19, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 25, tzinfo=UTC),
        "last_seen_at": datetime(2026, 8, 25, tzinfo=UTC),
        "first_seen_collection_run_id": 7,
        "last_seen_collection_run_id": 7,
        "usb_identities": [{"vendorId": 2334, "productId": 20920}],
    }
    row.update(changes)
    return row


class AdminDevicesTests(unittest.TestCase):
    def test_summary_counts_use_independent_capability_support_and_evidence(self):
        payload = _admin_device_payload(
            [
                device_row(),
                device_row(
                    device_id="garmin-venu-3",
                    model="Venu 3",
                    canonical_model="venu 3",
                    variant="",
                    case_size_mm=None,
                    display_type=None,
                    part_number=None,
                    map_capable=False,
                    support_status="NOT_EVALUATED",
                    attempted_install_count=0,
                    successful_install_count=0,
                    failed_install_count=0,
                    first_success=None,
                    last_success=None,
                    last_evidence=None,
                    first_seen_collection_run_id=None,
                    last_seen_collection_run_id=7,
                ),
                device_row(
                    device_id="garmin-new-watch",
                    model="New watch",
                    canonical_model="new watch",
                    variant=None,
                    case_size_mm=None,
                    display_type=None,
                    map_capable=None,
                    support_status="UNSUPPORTED",
                    attempted_install_count=1,
                    successful_install_count=0,
                    failed_install_count=1,
                    first_success=None,
                    last_success=None,
                    last_evidence=datetime(2026, 8, 26, tzinfo=UTC),
                    first_seen_collection_run_id=7,
                ),
            ],
            {
                "id": 7,
                "status": "SUCCEEDED",
                "started_at": datetime(2026, 8, 26, tzinfo=UTC),
                "finished_at": datetime(2026, 8, 26, 1, tzinfo=UTC),
                "records_total_before": 2,
                "records_total_after": 3,
                "records_added": 1,
                "records_updated": 1,
            },
        )

        self.assertEqual(
            {key: payload["summary"][key] for key in (
                "models", "mapCapable", "approved", "successful",
                "installAttempts", "successfulInstalls", "successRate", "newThisSync",
            )},
            {
                "models": 3,
                "mapCapable": 1,
                "approved": 1,
                "successful": 2,
                "installAttempts": 4,
                "successfulInstalls": 2,
                "successRate": 50.0,
                "newThisSync": 1,
            },
        )
        self.assertNotIn("supported", payload["summary"])
        self.assertNotIn("tested", payload["summary"])
        self.assertEqual(payload["devices"][0]["installationStats"]["successRate"], 66.7)
        self.assertTrue(payload["devices"][2]["catalog"]["newInLatestSync"])
        self.assertIsNone(payload["devices"][1]["installationStats"]["lastSuccessfulAt"])
        self.assertFalse(payload["devices"][1]["mapCapable"])
        self.assertEqual(payload["devices"][1]["image"]["origin"], "fallback")
        self.assertEqual(payload["devices"][1]["image"]["status"], "FALLBACK")

    def test_null_map_capable_is_classified_from_the_native_prefix_list(self) -> None:
        payload = _admin_device_payload(
            [
                device_row(map_capable=None),
                device_row(
                    device_id="garmin-fenix-7-47",
                    model="fēnix 7",
                    canonical_model="fenix 7",
                    variant="47 mm",
                    map_capable=None,
                    support_status="NOT_EVALUATED",
                    attempted_install_count=0,
                    successful_install_count=0,
                    failed_install_count=0,
                    first_success=None,
                    last_success=None,
                    last_evidence=None,
                ),
                device_row(
                    device_id="garmin-unknown-watch",
                    model="Future Watch",
                    canonical_model="future watch",
                    map_capable=None,
                    support_status="NOT_EVALUATED",
                    attempted_install_count=0,
                    successful_install_count=0,
                    failed_install_count=0,
                    first_success=None,
                    last_success=None,
                    last_evidence=None,
                ),
            ],
            None,
        )
        self.assertTrue(payload["devices"][0]["mapCapable"])
        self.assertTrue(payload["devices"][1]["mapCapable"])
        self.assertIsNone(payload["devices"][2]["mapCapable"])
        self.assertEqual(payload["summary"]["mapCapable"], 2)

    def test_fenix_8_51mm_has_independent_tested_evidence_status(self) -> None:
        payload = _admin_device_payload(
            [device_row(
                device_id="garmin-fenix-8-51-amoled",
                variant="51 mm, AMOLED",
                case_size_mm=51,
                support_status="NOT_EVALUATED",
                successful_install_count=1,
                attempted_install_count=1,
                failed_install_count=0,
            )],
            None,
        )
        device = payload["devices"][0]
        self.assertEqual(device["supportStatus"], "NOT_EVALUATED")
        self.assertEqual(device["evidenceStatus"], "TESTED")
        self.assertEqual(device["installationStats"]["successful"], 1)

    def test_garmin_source_image_is_used_when_controlled_asset_is_missing(self) -> None:
        source = "https://res.garmin.com/en/products/010-02905-10/v/cf-lg.jpg"
        payload = _admin_device_payload(
            [
                device_row(
                    asset_status="MISSING",
                    asset_url=None,
                    source_image_url=source,
                )
            ],
            None,
        )
        self.assertEqual(payload["devices"][0]["asset"]["status"], "MISSING")
        self.assertEqual(payload["devices"][0]["sourceAsset"]["url"], source)
        self.assertEqual(payload["devices"][0]["image"]["origin"], "garmin-source")
        self.assertEqual(payload["devices"][0]["image"]["url"], source)
        body = devices_page(
            [device_row(asset_status="MISSING", asset_url=None, source_image_url=source)],
            None,
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn(source, body)
        self.assertIn("device-thumb", body)

    def test_controlled_asset_wins_over_garmin_source_image(self) -> None:
        payload = _admin_device_payload(
            [
                device_row(
                    asset_status="AVAILABLE",
                    asset_url="https://api.terento.app/assets/devices/garmin/fenix-8-47-amoled.webp",
                    source_image_url="https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg",
                )
            ],
            None,
        )
        self.assertEqual(payload["devices"][0]["image"]["origin"], "controlled")
        self.assertTrue(
            payload["devices"][0]["image"]["url"].startswith(
                "https://api.terento.app/assets/devices/"
            )
        )

    def test_missing_image_uses_neutral_fallback(self) -> None:
        payload = _admin_device_payload(
            [device_row(asset_status="MISSING", asset_url=None, source_image_url=None)],
            None,
        )
        image = payload["devices"][0]["image"]
        self.assertEqual(image["origin"], "fallback")
        self.assertEqual(image["status"], "FALLBACK")
        self.assertEqual(image["source"]["type"], "GENERIC_FALLBACK")
        self.assertTrue(image["url"].endswith("/assets/generic-garmin-watch.png"))

    def test_historical_sync_without_counts_is_not_presented_as_zero(self):
        payload = _admin_device_payload(
            [device_row(first_seen_collection_run_id=None)],
            {
                "id": 3,
                "status": "SUCCEEDED",
                "started_at": datetime(2026, 8, 1, tzinfo=UTC),
                "finished_at": datetime(2026, 8, 1, 1, tzinfo=UTC),
                "records_total_before": None,
                "records_total_after": None,
                "records_added": None,
                "records_updated": None,
            },
        )

        self.assertIsNone(payload["summary"]["newThisSync"])
        self.assertIsNone(payload["sync"]["recordsAdded"])
        body = devices_page(
            [device_row(first_seen_collection_run_id=None)],
            {
                "id": 3,
                "status": "SUCCEEDED",
                "started_at": datetime(2026, 8, 1, tzinfo=UTC),
                "finished_at": datetime(2026, 8, 1, 1, tzinfo=UTC),
                "records_total_before": None,
                "records_total_after": None,
                "records_added": None,
                "records_updated": None,
            },
            {"username": "operator"},
            "csrf",
        ).decode()
        self.assertIn("Counts unavailable for this historical run", body)

    def test_page_has_required_filters_modal_and_neutral_image_fallback(self):
        body = devices_page(
            [device_row()],
            None,
            {"username": "operator"},
            "csrf",
        ).decode()
        for value in (
            "Garmin devices", "Map capability: Yes", "Map capability: No",
            "Map capability: Unknown", "Approved", "Blocked", "Pending",
            "Newest in catalog", "Most attempts", "Last evidence", "device-dialog", "admin-timezone",
            "Automatic (browser)", "data-admin-timestamp", "TerentoAdminTime",
            "selected time zone",
        ):
            self.assertIn(value, body)
        self.assertNotIn("src='None'", body)
        self.assertIn("generic-garmin-watch.png", body)
        self.assertIn("Compatibility status and installation counts remain backend-derived", body)
        self.assertIn("Compatibility status", body)
        self.assertIn("aria-label=\"Installation authorization\"", body)
        self.assertNotIn("Support decision", body)
        self.assertNotIn("Evidence status", body)


if __name__ == "__main__":
    unittest.main()

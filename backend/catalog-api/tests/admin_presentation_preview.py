"""Build read-only Admin pages with deterministic presentation evidence."""

from pathlib import Path
import shutil
import sys

from admin_plan_preview import build
from terento_catalog.admin import (
    _admin_device_payload,
    _diagnostic_summary_by_identity,
    _map_statistics_summary,
    dashboard_page,
    device_detail_page,
    device_identification_page,
    devices_page,
    diagnostics_page,
    map_statistics_page,
)


def _trend() -> list[dict[str, object]]:
    return [
        {
            "bucket": f"2026-09-{day:02d}T00:00:00Z",
            "download_success_count": 7 + day % 5,
            "download_failed_count": 1 if day in {20, 23} else 0,
            "success_count": 5 + day % 4,
            "failed_count": 1 if day in {19, 22, 24} else 0,
            "custom_count": 1 if day == 21 else 0,
            "map_update_count": 1 if day == 24 else 0,
        }
        for day in range(18, 25)
    ]


def _statistics(
    rows: list[dict[str, object]], *, trend: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "rows": rows,
        "summary": _map_statistics_summary(rows),
        "allTimeSummary": _map_statistics_summary(rows),
        "trend": _trend() if trend is None else trend,
        "bucket": "day",
        "timeZone": "UTC",
        "linkage": {
            "freshMapAttemptCount": 34,
            "freshMapLinkedDiagnosticCount": 31,
            "freshMapMissingDiagnosticCount": 3,
            "freshMapDiagnosticCoverageRate": 91.2,
        },
    }


def create(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    build(root)
    map_assets = Path(__file__).parents[1] / "src" / "terento_catalog" / "static" / "map"
    shutil.copytree(map_assets, root / "admin" / "map-assets", dirs_exist_ok=True)
    user = {"username": "Preview"}
    providers = [
        {"id": provider, "name": name, "health": "HEALTHY"}
        for provider, name in (
            ("opentopomap", "OpenTopoMap"), ("maprando", "MapRando"),
            ("freizeitkarte", "Freizeitkarte"), ("bbbike", "BBBike"),
            ("custom", "custom"),
        )
    ]
    rows = []
    for provider, successful, failed in (
        ("opentopomap", 14, 6), ("maprando", 23, 2),
        ("freizeitkarte", 19, 6), ("bbbike", 8, 1), ("custom", 20, 3),
    ):
        for event_type, outcome, count in (
            ("INSTALL_SUCCEEDED", "SUCCEEDED", successful),
            ("INSTALL_FAILED", "FAILED", failed),
        ):
            rows.append({
                "provider_id": provider, "map_package_id": provider + "-fixture",
                "region": "LT", "region_identity": "LITHUANIA",
                "region_display_name": "Lithuania", "region_country": "LT",
                "component_kind": "main", "event_type": event_type,
                "outcome": outcome, "operation_count": count, "event_count": count,
                "last_occurred_at": "2026-09-18T09:39:00Z",
            })
    rows.extend([
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED", "operation_count": 84, "event_count": 84},
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_FAILED", "outcome": "FAILED", "operation_count": 4, "event_count": 4},
        {"provider_id": "opentopomap", "event_type": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED", "operation_count": 6, "event_count": 6},
        {"provider_id": "opentopomap", "event_type": "MAP_UPDATE_FAILED", "outcome": "FAILED", "operation_count": 1, "event_count": 1},
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_INTERRUPTED", "outcome": "UNKNOWN", "operation_count": 7, "event_count": 7},
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_STARTED", "outcome": "STARTED", "operation_count": 3, "event_count": 3},
    ])
    rows.extend([
        {
            "provider_id": "opentopomap", "map_package_id": "de-fixture",
            "region": "DE", "region_identity": "GERMANY",
            "region_display_name": "Germany", "region_country": "DE",
            "component_kind": "main", "event_type": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED", "operation_count": 12, "event_count": 12,
            "last_occurred_at": "2026-09-19T09:39:00Z",
        },
        {
            "provider_id": "maprando", "map_package_id": "fr-fixture",
            "region": "FR", "region_identity": "FRANCE",
            "region_display_name": "France", "region_country": "FR",
            "component_kind": "main", "event_type": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED", "operation_count": 8, "event_count": 8,
            "last_occurred_at": "2026-09-20T09:39:00Z",
        },
    ])
    statistics = _statistics(rows)
    (root / "statistics.html").write_bytes(map_statistics_page(
        statistics, providers, user, "fixture",
    ))
    sparse_rows = [row for row in rows if row.get("region_country") == "LT"]
    sparse_trend = [
        {
            "bucket": f"2026-09-{day:02d}T00:00:00Z",
            "download_success_count": 0, "download_failed_count": 0,
            "success_count": 12,
            "failed_count": (3, 3, 3, 3, 2, 2, 2)[index],
            "custom_count": (3, 3, 3, 3, 3, 3, 2)[index],
            "map_update_count": 0,
        }
        for index, day in enumerate(range(18, 25))
    ]
    (root / "statistics-sparse.html").write_bytes(map_statistics_page(
        _statistics(sparse_rows, trend=sparse_trend), providers, user, "fixture",
    ))
    (root / "statistics-empty.html").write_bytes(map_statistics_page(
        {"rows": [], "summary": _map_statistics_summary([])}, providers, user,
        "fixture", selected_filters={"period": "7d", "provider": "bbbike"},
    ))
    (root / "statistics-event-open.html").write_bytes(map_statistics_page(
        statistics, providers, user, "fixture",
        selected_filters={"period": "30d", "eventId": "fixture-diagnostic"},
    ))

    device_row = {
        "device_id": "fenix-8-51-amoled", "model": "fēnix 8",
        "variant": "51 mm, AMOLED", "family_name": "fēnix",
        "map_capable": True, "active": True, "support_status": "SUPPORTED",
        "install_authorization": "APPROVED", "attempted_install_count": 12,
        "successful_install_count": 11, "failed_install_count": 1,
        "last_success": "2026-09-18T09:39:00Z", "usb_identities": [],
    }
    operation = {
        "event_id": "fixture-diagnostic", "operation_id": "fixture-operation",
        "operation_key": "fixture-operation", "map_result_index": 0,
        "canonical_device_model_id": "fenix-8-51-amoled",
        "compatibility_identity": "fēnix 8 · 51 mm, AMOLED",
        "model": "fēnix 8", "variant": "51 mm, AMOLED",
        "provider": "opentopomap", "region": "Lithuania",
        "phase_outcome": "FAILED", "diagnostic_status": "ACTIVE",
        "error_category": "TRANSFER_FAILED", "write_started": True,
        "occurred_at": "2026-09-18T09:39:00Z",
    }
    device = _admin_device_payload([device_row], None)["devices"][0]
    (root / "devices.html").write_bytes(devices_page([device_row], None, user, "fixture"))
    (root / "devices-empty.html").write_bytes(devices_page([], None, user, "fixture"))
    (root / "device.html").write_bytes(device_detail_page(
        device, user, "fixture", operations=[operation], identity_devices=[device_row],
    ))
    (root / "device-empty.html").write_bytes(device_detail_page(
        device, user, "fixture", operations=[], identity_devices=[device_row],
    ))
    identification_device = {
        "id": "fenix-8-51-amoled", "model": "fēnix 8",
        "variant": "51 mm, AMOLED", "mapCapable": True,
        "identityMappings": [{
            "id": 1, "kind": "XML_PART_NUMBER", "value": "006-B4953-00",
            "status": "PENDING", "source_url": "https://www.garmin.com/",
            "source_version": "2026-09 catalog review",
            "source_names": ["fēnix 8 · 51 mm, AMOLED"], "history": [],
        }],
    }
    (root / "identification.html").write_bytes(device_identification_page(
        [identification_device], user, "fixture", device_id="fenix-8-51-amoled",
    ))
    ambiguous_devices = [identification_device, {
        "id": "fenix-8-47-amoled", "model": "fēnix 8",
        "variant": "47 mm, AMOLED", "mapCapable": True,
        "identityMappings": [{
            "id": 2, "kind": "XML_PART_NUMBER", "value": "006-B4953-00",
            "status": "REJECTED", "source_url": "https://www.garmin.com/",
            "source_version": "2026-09 catalog review",
            "source_names": ["fēnix 8 · 47 mm, AMOLED"], "history": [],
        }],
    }, {
        "id": "fenix-8-51-solar", "model": "fēnix 8 Solar",
        "variant": "51 mm, MIP", "mapCapable": True,
        "identityMappings": [{
            "id": 3, "kind": "XML_PART_NUMBER", "value": "006-B4953-00",
            "status": "APPROVED", "source_url": "https://www.garmin.com/",
            "source_version": "2026-09 catalog review",
            "source_names": ["fēnix 8 Solar · 51 mm, MIP"], "history": [],
        }],
    }]
    (root / "identification-ambiguous.html").write_bytes(device_identification_page(
        ambiguous_devices, user, "fixture", device_id="fenix-8-51-amoled",
    ))
    decided_device = {
        **identification_device,
        "identityMappings": [{
            **identification_device["identityMappings"][0],
            "id": 4, "status": "APPROVED", "review_reason": "Garmin source names the exact 51 mm AMOLED variant.",
            "reviewed_at": "2026-09-20T10:30:00Z",
            "history": [{
                "previous_status": "PENDING", "new_status": "APPROVED",
                "reason": "Garmin source names the exact variant.",
                "reviewed_by": 1, "created_at": "2026-09-20T10:30:00Z",
            }],
        }],
    }
    (root / "identification-decided.html").write_bytes(device_identification_page(
        [decided_device], user, "fixture", device_id="fenix-8-51-amoled",
    ))
    (root / "identification-no-others.html").write_bytes(device_identification_page(
        [identification_device], user, "fixture", device_id="fenix-8-51-amoled",
    ))
    (root / "installations-empty.html").write_bytes(dashboard_page(
        [], user, "fixture", diagnostic_summary={},
    ))
    (root / "diagnostics.html").write_bytes(diagnostics_page(
        [], user, "fixture", identity="fēnix 8 · 51 mm, AMOLED",
        operations=[operation], identity_devices=[device_row],
    ))
if __name__ == "__main__":
    create(Path(sys.argv[1]))

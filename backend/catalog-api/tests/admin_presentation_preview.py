"""Build read-only Admin pages with deterministic presentation evidence."""

import json
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
    identity_review_page,
    missing_reports_page,
    device_identification_page,
    devices_page,
    diagnostics_page,
    map_statistics_page,
)
from terento_catalog.support_report_admin import support_report_detail_page, support_reports_page
from terento_catalog.support_reports import validate_support_report


def _daily_trend() -> list[dict[str, object]]:
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


def _weekly_trend() -> list[dict[str, object]]:
    return [
        {
            "bucket": bucket,
            "download_success_count": 42 + index * 3,
            "download_failed_count": 1 if index in {1, 4} else 0,
            "success_count": 31 + index * 2,
            "failed_count": 1 if index in {2, 5} else 0,
            "custom_count": 1 if index == 3 else 0,
            "map_update_count": 1 if index == 5 else 0,
        }
        for index, bucket in enumerate((
            "2026-08-17T00:00:00Z", "2026-08-24T00:00:00Z",
            "2026-08-31T00:00:00Z", "2026-09-07T00:00:00Z",
            "2026-09-14T00:00:00Z", "2026-09-21T00:00:00Z",
        ))
    ]


def _monthly_trend() -> list[dict[str, object]]:
    return [
        {
            "bucket": f"2026-{month:02d}-01T00:00:00Z",
            "download_success_count": 120 + month * 4,
            "download_failed_count": month % 3,
            "success_count": 90 + month * 3,
            "failed_count": month % 2,
            "custom_count": 1,
            "map_update_count": month % 2,
        }
        for month in range(3, 10)
    ]


def _reconciled_trend(
    rows: list[dict[str, object]], trend: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep the chart shape but make bucket totals equal the tile totals."""
    def total(event_type: str, outcome: str, custom: bool | None = None) -> int:
        return sum(
            int(row.get("operation_count") or 0) for row in rows
            if row.get("event_type") == event_type and row.get("outcome") == outcome
            and (custom is None or (row.get("provider_id") == "custom") == custom)
        )

    targets = {
        "download_success_count": total("DOWNLOAD_SUCCEEDED", "SUCCEEDED"),
        "download_failed_count": total("DOWNLOAD_FAILED", "FAILED"),
        "success_count": total("INSTALL_SUCCEEDED", "SUCCEEDED", custom=False),
        "custom_count": total("INSTALL_SUCCEEDED", "SUCCEEDED", custom=True),
        "failed_count": total("INSTALL_FAILED", "FAILED"),
        "map_update_success_count": total("MAP_UPDATE_SUCCEEDED", "SUCCEEDED"),
        "map_update_failed_count": total("MAP_UPDATE_FAILED", "FAILED"),
    }
    buckets = [dict(item) for item in trend]
    for field, target in targets.items():
        weights = [max(1, int(item.get(field) or 0)) for item in buckets]
        shares = [target * weight // sum(weights) for weight in weights]
        for index in range(target - sum(shares)):
            shares[-1 - index % len(shares)] += 1
        for item, share in zip(buckets, shares):
            item[field] = share
    for item in buckets:
        item["map_update_count"] = item["map_update_success_count"] + item["map_update_failed_count"]
    return buckets


def _statistics(
    rows: list[dict[str, object]], *, trend: list[dict[str, object]] | None = None,
    bucket: str = "week",
) -> dict[str, object]:
    return {
        "rows": rows,
        "summary": _map_statistics_summary(rows),
        "allTimeSummary": _map_statistics_summary(rows),
        "trend": _reconciled_trend(rows, _weekly_trend() if trend is None else trend) if rows else (trend or []),
        "bucket": bucket,
        "timeZone": "UTC",
        "linkage": {
            "freshMapAttemptCount": 34,
            "freshMapLinkedDiagnosticCount": 32,
            "freshMapMissingDiagnosticCount": 2,
            "linkedPrewriteFailureCount": 4,
            "freshMapDiagnosticCoverageRate": 94.1,
        },
    }


def _identity_review_fixture():
    """Pending installations across identities; three share fēnix 8, one batch holds two maps."""
    devices = [
        {"id": "fenix-8-47-amoled", "device_id": "fenix-8-47-amoled", "model": "fēnix 8", "variant": "47 mm, AMOLED",
         "case_size_mm": 47, "screen_technology": "AMOLED", "solar": False, "inreach": False},
        {"id": "fenix-8-51-amoled", "device_id": "fenix-8-51-amoled", "model": "fēnix 8", "variant": "51 mm, AMOLED",
         "case_size_mm": 51, "screen_technology": "AMOLED", "solar": False, "inreach": False},
        {"id": "forerunner-965", "device_id": "forerunner-965", "model": "Forerunner 965", "variant": "",
         "case_size_mm": 47, "screen_technology": "AMOLED", "solar": False, "inreach": False},
        {"id": "instinct-3-45-amoled", "device_id": "instinct-3-45-amoled", "model": "Instinct 3",
         "variant": "45 mm, AMOLED", "case_size_mm": 45, "screen_technology": "AMOLED", "solar": False, "inreach": False},
    ]

    def candidate(device_id, model, *missing):
        checks = [{"name": "model", "state": "MATCH", "features": []}]
        checks += [{"name": name, "state": "MISSING"} for name in missing]
        return {"deviceId": device_id, "model": model, "checks": checks, "conflict": False}

    def event(index, identity, model, variant, *, outcome="SUCCEEDED", region="Lithuania",
              provider="opentopomap", day=20, candidates=(), map_index=0, operation=None, **extra):
        operation = operation or f"7a1b2c3d-0000-4000-8000-{index:012d}"
        failed = outcome == "FAILED"
        return {
            "event_id": f"8b1b2c3d-0000-4000-8000-{index:010d}{map_index:02d}",
            "operation_id": operation, "map_result_index": map_index,
            "operation_key": f"result:{operation}:{map_index}",
            "compatibility_identity": identity, "model": model, "variant": variant,
            "canonical_device_model_id": None, "identity_resolution_state": "UNRESOLVED",
            "provider": provider, "region": region, "phase_outcome": outcome,
            "automatic_finishing_result": None if failed else "VERIFIED",
            "failure_stage": "verify" if failed else None,
            "failure_code": "INSTALL_FAILED_HASH_MISMATCH" if failed else None,
            "write_started": True, "diagnostic_status": "ACTIVE",
            "occurred_at": f"2026-09-{day:02d}T09:{10 + index:02d}:00Z",
            "release_label": "1.0.0-beta.19", "app_build": "42",
            "current_identity_assessment": {"state": "UNRESOLVED", "candidates": list(candidates)},
            **extra,
        }

    fenix = (candidate("fenix-8-47-amoled", "fēnix 8", "size"), candidate("fenix-8-51-amoled", "fēnix 8", "size"))
    instinct = (candidate("instinct-3-45-amoled", "Instinct 3", "screen"),)
    batch = "7a1b2c3d-0000-4000-8000-0000000000aa"
    operations = [
        event(1, "fēnix 8", "fēnix 8", None, outcome="FAILED", region="France", provider="bbbike", day=24,
              candidates=fenix),
        event(2, "fēnix 8", "fēnix 8", None, day=22, candidates=fenix),
        event(3, "fēnix 8", "fēnix 8", None, region="Latvia", day=19, candidates=fenix),
        event(4, "Forerunner 965", "Forerunner 965", None, region="Germany", provider="freizeitkarte", day=23,
              candidates=(candidate("forerunner-965", "Forerunner 965", "screen"),)),
        event(5, "Instinct 3 · 45 mm", "Instinct 3", "45 mm", region="Poland", day=21, operation=batch,
              candidates=instinct),
        event(6, "Instinct 3 · 45 mm", "Instinct 3", "45 mm", region="Czechia", day=21, operation=batch,
              map_index=1, candidates=instinct),
        event(7, "Unknown", None, None, outcome="FAILED", region="Spain", day=18),
    ]
    resolved = [{
        **event(8, "fēnix 8", "fēnix 8", None, outcome="FAILED", region="Italy", day=12, candidates=fenix),
        "diagnostic_status": "RESOLVED", "resolution_reason": "FIXED", "resolved_at": "2026-09-14T10:00:00Z",
    }]
    statistics = [{
        "model": "fēnix 8", "variant": None, "compatibility_identity": "fēnix 8",
        "canonical_device_model_id": None, "attempted_install_count": 4, "successful_install_count": 2,
        "failed_install_count": 2, "calculated_status": "TESTING", "recognized_map_capable_evidence": True,
        "last_success": "2026-09-22T09:12:00Z", "last_evidence": "2026-09-24T09:11:00Z",
    }]
    return operations, resolved, statistics, devices


def create(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    build(root)
    # Keep the large plan fixture (125 models) for the sorting/pagination browser checks.
    shutil.copy2(root / "installations.html", root / "installations-plan.html")
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
        ("opentopomap", 4, 3), ("maprando", 4, 1),
        ("freizeitkarte", 4, 2), ("bbbike", 3, 2), ("custom", 4, 2),
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
    for index, (country, code) in enumerate((
        ("United Kingdom", "GB"), ("Poland", "PL"), ("Spain", "ES"),
        ("Italy", "IT"), ("Switzerland", "CH"), ("Austria", "AT"),
        ("Czechia", "CZ"),
    ), start=1):
        rows.append({
            "provider_id": "opentopomap", "map_package_id": f"country-{code.lower()}",
            "region": code, "region_identity": country.upper().replace(" ", ""),
            "region_display_name": country, "region_country": code,
            "component_kind": "main", "event_type": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED", "operation_count": 12 - index,
            "event_count": 12 - index,
            "last_occurred_at": "2026-09-20T09:39:00Z",
        })
    statistics = _statistics(rows)
    (root / "statistics.html").write_bytes(map_statistics_page(
        statistics, providers, user, "fixture",
    ))
    (root / "statistics-short.html").write_bytes(map_statistics_page(
        _statistics(rows, trend=_daily_trend(), bucket="day"),
        providers, user, "fixture", selected_filters={"period": "7d"},
    ))
    (root / "statistics-monthly.html").write_bytes(map_statistics_page(
        _statistics(rows, trend=_monthly_trend(), bucket="month"),
        providers, user, "fixture",
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
        _statistics(sparse_rows, trend=sparse_trend, bucket="day"), providers, user, "fixture",
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
    installation_rows = [
        ("fēnix 8", "47 mm, AMOLED", 17, 17, 0),
        ("Forerunner 970", "AMOLED", 9, 6, 3),
        ("Forerunner 965", "—", 8, 6, 2),
        ("fēnix 8 Pro", "51 mm, AMOLED, inReach", 8, 6, 2),
        ("fēnix 9 Pro", "51 mm, AMOLED", 9, 8, 1),
        ("fēnix 7X", "51 mm", 6, 5, 1),
        ("epix Pro (Gen 2)", "47 mm, AMOLED", 10, 10, 0),
        ("fēnix 9", "47 mm, AMOLED", 12, 12, 0),
        ("Forerunner 955", "Standard", 9, 9, 0),
        ("fēnix 9 Pro", "47 mm, AMOLED, inReach", 20, 19, 1),
    ]
    (root / "installations.html").write_bytes(dashboard_page([
        {
            "model": model,
            "variant": variant,
            "compatibility_identity": f"fixture-model-{index}",
            "canonical_device_model_id": f"fixture-model-{index}",
            "attempted_install_count": attempts,
            "successful_install_count": successful,
            "failed_install_count": failed,
            "recognized_map_capable_evidence": True,
            "calculated_status": "VERIFIED" if successful >= 5 else "TESTED",
            "last_success": "2026-09-24T18:20:00Z",
            "last_evidence": "2026-09-24T18:30:00Z",
        }
        for index, (model, variant, attempts, successful, failed)
        in enumerate(installation_rows)
    ], user, "fixture", diagnostic_summary={}))
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
    device_history = [
        {
            **operation,
            "event_id": f"fixture-diagnostic-{index}",
            "operation_id": f"fixture-operation-{index}",
            "operation_key": f"fixture-operation-{index}",
            "phase_outcome": "FAILED" if index in {0, 4} else "SUCCEEDED",
            "automatic_finishing_result": None if index in {0, 4} else "VERIFIED",
            "diagnostic_status": "ACTIVE",
            "occurred_at": f"2026-09-{18 - index:02d}T09:39:00Z",
        }
        for index in range(8)
    ]
    device = _admin_device_payload([device_row], None)["devices"][0]
    # A Maps: Unknown model keeps Pending policy above zero (danger tone).
    pending_device_row = {
        "device_id": "instinct-e-40", "model": "Instinct E", "variant": "40 mm",
        "family_name": "Instinct", "map_capable": None, "active": True,
        "support_status": "NOT_EVALUATED", "attempted_install_count": 0,
        "successful_install_count": 0, "failed_install_count": 0, "usb_identities": [],
    }
    (root / "devices.html").write_bytes(devices_page([device_row, pending_device_row], None, user, "fixture"))
    (root / "devices-empty.html").write_bytes(devices_page([], None, user, "fixture"))
    update_rows = [
        {
            "event_id": f"33333333-3333-4333-8333-33333333333{index}",
            "operation_id": f"33333333-3333-4333-8333-33333333333{index}",
            "canonical_device_model_id": "fenix-8-51-amoled",
            "provider": provider, "region": region, "outcome": outcome,
            "diagnostic_status": "ACTIVE", "linked_github_issue": "#325" if index == 1 else None,
            "occurred_at": f"2026-09-{20 - index:02d}T08:15:00Z",
            "payload": {"terentoVersion": "beta.15", "appBuild": "37"},
        }
        for index, (provider, region, outcome) in enumerate([
            ("opentopomap", "Lithuania", "SUCCEEDED"),
            ("bbbike", "FRA", "FAILED"),
            ("freizeitkarte", "Germany", "NOT_STARTED"),
            ("opentopomap", "Latvia", "SUCCEEDED"),
        ])
    ]
    (root / "device.html").write_bytes(device_detail_page(
        device, user, "fixture", operations=device_history, identity_devices=[device_row],
        update_history={"device_id": "fenix-8-51-amoled", "rows": update_rows,
                        "outcome": "", "offset": 0, "has_more": True},
    ))
    (root / "device-empty.html").write_bytes(device_detail_page(
        device, user, "fixture", operations=[], identity_devices=[device_row],
    ))
    (root / "device-updates-filtered.html").write_bytes(device_detail_page(
        device, user, "fixture", operations=device_history, identity_devices=[device_row],
        update_history={"device_id": "fenix-8-51-amoled", "rows": [],
                        "outcome": "failed", "offset": 0, "has_more": False},
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
    # Model sources list: every state, more than one 25-row page.
    source_states = ("PENDING", "APPROVED", "REJECTED", None)
    source_list = [*ambiguous_devices, *[
        {
            "id": f"preview-model-{index}", "model": f"Forerunner {200 + index * 5}",
            "variant": "AMOLED" if index % 2 else "MIP", "mapCapable": index % 3 != 0,
            "identityMappings": [] if source_states[index % 4] is None else [{
                "id": 100 + index, "kind": "XML_PART_NUMBER", "value": f"006-B{4000 + index}-00",
                "status": source_states[index % 4], "source_url": "https://www.garmin.com/",
                "source_version": "2026-09 catalog review",
                "source_names": [f"Forerunner {200 + index * 5}"], "history": [],
            }],
        }
        for index in range(1, 37)
    ]]
    (root / "identification-list.html").write_bytes(device_identification_page(
        source_list, user, "fixture",
    ))
    (root / "identification-list-search.html").write_bytes(device_identification_page(
        source_list, user, "fixture", query="fēnix",
    ))
    (root / "installations-empty.html").write_bytes(dashboard_page(
        [], user, "fixture", diagnostic_summary={},
    ))
    (root / "diagnostics.html").write_bytes(diagnostics_page(
        [], user, "fixture", identity="fēnix 8 · 51 mm, AMOLED",
        operations=[operation], identity_devices=[device_row],
    ))
    identity_operations, identity_resolved, identity_statistics, identity_devices = _identity_review_fixture()
    (root / "identity-review.html").write_bytes(identity_review_page(
        identity_operations, user, "fixture", identity_devices=identity_devices,
    ))
    (root / "identity-review-empty.html").write_bytes(identity_review_page(
        [], user, "fixture", identity_devices=identity_devices,
    ))
    (root / "diagnostics-identity.html").write_bytes(diagnostics_page(
        identity_statistics, user, "fixture", identity="fēnix 8",
        operations=[event for event in identity_operations if event["compatibility_identity"] == "fēnix 8"],
        resolved_operations=identity_resolved, identity_devices=identity_devices, unresolved_only=True,
    ))
    (root / "missing-reports.html").write_bytes(missing_reports_page({
        "rows": [{
            "event_type": "INSTALL_FAILED", "outcome": "FAILED",
            "event_id": f"a8098c1a-f86e-11da-bd1a-0011244{index:05d}", "provider_id": "freizeitkarte",
            "provider_name": "Freizeitkarte", "region": region, "map_package_name": region,
            "occurred_at": f"2026-09-{20 - index:02d}T19:47:00Z",
        } for index, region in enumerate(("France", "Lithuania", "Germany"))],
        "total": 3, "limit": 50, "offset": 0,
    }, user, "fixture"))
    support_fixture = json.loads((Path(__file__).parents[3] / "contracts" / "fixtures" / "support-report.valid.json").read_text())
    support = validate_support_report(json.dumps(support_fixture).encode())
    support_rows = [{
        "id": support["id"], "reference": support["reference"], "received_at": "2026-10-06T09:41:09Z",
        "created_at": "2026-10-06T09:41:07Z", "app_build": "42", "release_label": "1.0.0-beta.19",
        "is_local_test": False, "category": category, "operation_id": support["operationId"], "status": "OPEN",
        "handled_at": None, "linked_github_issue": None, "title": title, "device_model": model,
        "device_variant": variant, "has_user_message": index == 0,
    } for index, (category, title, model, variant) in enumerate((
        ("INSTALL_FAILED", support["report"]["title"], "fēnix 8", "51 mm, AMOLED"),
        ("CONNECTION", None, None, None),
        ("UPDATE_FAILED", "Map update stopped during failedInsufficientSpace — freizeitkarte / Germany", "Forerunner 965", None),
    ))]
    for index, row in enumerate(support_rows[1:], start=1):
        row["reference"] = "TR-PREV" + "AB"[index - 1] * 2
    (root / "support-reports.html").write_bytes(support_reports_page({
        "rows": support_rows, "status": "OPEN", "limit": 50, "offset": 0,
        "openCount": 3, "handledCount": 12, "totalCount": 15, "filteredTotal": 3,
    }, user, "fixture"))
    (root / "support-reports-empty.html").write_bytes(support_reports_page({
        "rows": [], "status": "OPEN", "limit": 50, "offset": 0,
        "openCount": 0, "handledCount": 12, "totalCount": 12, "filteredTotal": 0,
    }, user, "fixture"))
    (root / "support-report.html").write_bytes(support_report_detail_page({
        **support_rows[0], "user_message": support["userMessage"], "report": support["report"],
        "note": None, "handled_by_username": None,
        "audit": [{"action": "REOPENED", "changed_by_username": "Preview", "changed_at": "2026-10-06T12:10:00Z",
                   "note": "Waiting for a new report after the cable change."},
                  {"action": "HANDLED", "changed_by_username": "Preview", "changed_at": "2026-10-06T11:00:00Z", "note": None}],
        "installationDiagnostics": [{"compatibility_identity": "fēnix 8 · 51 mm, AMOLED", "model": "fēnix 8",
                                     "canonical_device_model_id": "fenix-8-51-amoled", "result_count": 1,
                                     "last_occurred_at": "2026-10-06T09:40:00Z"}],
        "updateDiagnostics": [],
    }, user, "fixture"))
    site_assets = Path(__file__).parents[3] / "site"
    shutil.copytree(site_assets / "assets" / "fonts", root / "fonts", dirs_exist_ok=True)
    shutil.copy2(site_assets / "favicon.ico", root / "favicon.ico")
    for page in root.glob("*.html"):
        page.write_text(
            page.read_text().replace(
                "https://terento.app/assets/fonts/", "/admin/fonts/",
            )
        )
if __name__ == "__main__":
    create(Path(sys.argv[1]))

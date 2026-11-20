"""Helpers that only tests use.

They used to live in the production package; production code never called
them, so they are kept here next to the tests that exercise them.
"""
from __future__ import annotations

from typing import Any

from terento_catalog.asset_storage import AssetStorage, StoredAsset
from terento_catalog.collectors.freizeitkarte.parser import (
    ProviderPageParseError,
    parse_region_downloads,
)
from terento_catalog.collectors.freizeitkarte.range_zip import (
    ZipPayloadMeasurement,
    ZipRangeError,
)
from terento_catalog.historical_devices import (
    HISTORICAL_DEVICE_REGISTRY,
    HistoricalDeviceSpec,
)
from terento_catalog.installation_policy import installation_authorization_for_row


def store_webp(storage: AssetStorage, data: bytes, storage_key: str) -> StoredAsset:
    """Store a WebP directly in the public asset tree (no review staging)."""
    return storage._store(data, storage_key, storage.root, public=True)


def parse_region_download(html: str, *, region_code: str, base_url: str) -> str:
    for download in parse_region_downloads(html, base_url=base_url):
        if download.region == region_code:
            return download.source_url
    raise ProviderPageParseError(f"Freizeitkarte region section not found: {region_code}")


def validate_extracted_payload_size(measurement: ZipPayloadMeasurement, actual_size: int) -> None:
    if actual_size < 0 or measurement.install_size_bytes != actual_size:
        raise ZipRangeError(
            "extracted payload size does not match ZIP central-directory metadata"
        )


def historical_device_spec(device_id: str | None) -> HistoricalDeviceSpec | None:
    by_id = {spec.id: spec for spec in HISTORICAL_DEVICE_REGISTRY}
    return by_id.get(device_id or "")


def summarize_installation_catalog(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count all Garmin policy rows by the stored nullable map capability."""
    summary = {
        "total": len(rows),
        "mapCapableTrue": 0,
        "mapCapableFalse": 0,
        "mapCapableNull": 0,
        "activeMapCapableTrueApproved": 0,
        "activeMapCapableFalseBlocked": 0,
        "activeMapCapableNullPending": 0,
    }
    for row in rows:
        value = row.get("map_capable")
        if value is True:
            summary["mapCapableTrue"] += 1
        elif value is False:
            summary["mapCapableFalse"] += 1
        else:
            summary["mapCapableNull"] += 1

        scope, authorization = installation_authorization_for_row(row)
        if row.get("active") is True and value is True and scope == "IN_SCOPE" and authorization == "APPROVED":
            summary["activeMapCapableTrueApproved"] += 1
        elif row.get("active") is True and value is False and authorization == "BLOCKED":
            summary["activeMapCapableFalseBlocked"] += 1
        elif row.get("active") is True and value is None and authorization == "PENDING":
            summary["activeMapCapableNullPending"] += 1
    return summary

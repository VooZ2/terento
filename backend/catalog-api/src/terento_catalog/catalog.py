from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from . import CATALOG_VERSION


def build_catalog(rows: list[dict[str, Any]], updated_at: datetime) -> dict[str, Any]:
    """Build the versioned public contract from database rows.

    Rows without a normalized version or a known download size are kept out of
    the public package list. An install size is intentionally optional: the
    client must block storage approval until it has a measured IMG size when
    this metadata is not available.
    """

    if any("package_id" in row for row in rows):
        return _build_provider_neutral_catalog(rows, updated_at)

    providers: dict[str, dict[str, Any]] = {}
    for row in rows:
        provider_id = row["provider_id"]
        provider = providers.setdefault(
            provider_id,
            {
                "id": provider_id,
                "name": row["provider_name"],
                "adapterId": provider_id,
                "status": "ACTIVE",
                "health": "UNKNOWN",
                "website": row["provider_website"],
                "attribution": row["provider_attribution"],
                "licenseURL": row["provider_license_url"],
                "licenseInformation": row["provider_license_information"],
                "maps": [],
            },
        )

        download_size = row.get("download_size_bytes")
        if download_size is None:
            download_size = row.get("file_size_bytes")
        if row["version_year"] is None or download_size is None:
            continue

        map_document: dict[str, Any] = {
            "id": row["map_id"],
            "region": row["region"],
            "name": row["map_name"],
            "country": row["country"],
            "version": {
                "year": row["version_year"],
                "month": row["version_month"],
            },
            # Keep the legacy field stable while exposing unambiguous fields
            # for new clients. `sizeBytes` is the historical package size.
            "sizeBytes": row.get("file_size_bytes") or download_size,
            "downloadSizeBytes": download_size,
            "installSizeBytes": row.get("install_size_bytes"),
            "sourceURL": row["source_url"],
            "releaseDate": (
                row["release_date"].isoformat()
                if row["release_date"] is not None
                else None
            ),
            "identifier": row["identifier"],
            "providerRegionId": row["identifier"],
            "canonicalRegionId": row["region"],
            "countryCodes": [row["region"]],
            "regionKind": "country",
            "tags": [],
            "capabilities": ["main"],
            "release": f"{row['version_year']:04d}-{row['version_month']:02d}",
            "sourceUrl": row["source_url"],
            "artifacts": [
                {
                    "id": f"{row['map_id']}-main",
                    "kind": "main",
                    "required": True,
                    "sourceUrl": row["source_url"],
                    "sourceURL": row["source_url"],
                    # Native storage planning consumes this field. The
                    # download/archive size remains explicit below.
                    "sizeBytes": row.get("install_size_bytes"),
                    "downloadSizeBytes": download_size,
                    "installSizeBytes": row.get("install_size_bytes"),
                    "checksumSha256": row.get("checksum_sha256"),
                    "checksum": row.get("checksum_sha256"),
                    "contentType": "application/zip",
                    "validationStatus": (
                        "VALIDATED"
                        if row.get("install_size_bytes") is not None
                        else "NOT_VALIDATED"
                    ),
                    "validationState": _native_validation_state(
                        "VALIDATED" if row.get("install_size_bytes") is not None else "NOT_VALIDATED"
                    ),
                }
            ],
        }
        provider["maps"].append(map_document)

    for provider in providers.values():
        provider["maps"].sort(key=lambda item: item["id"])

    return {
        "schemaVersion": 2,
        "catalogVersion": CATALOG_VERSION,
        "updatedAt": _format_timestamp(updated_at),
        "providers": [providers[key] for key in sorted(providers)],
    }


def _build_provider_neutral_catalog(
    rows: list[dict[str, Any]], updated_at: datetime
) -> dict[str, Any]:
    """Serialize the beta.8 package/artifact read model.

    The legacy map fields are intentionally retained because the current
    native beta.8 decoder requires them. New consumers should use `release`
    and `artifacts`; `artifact.sizeBytes` is the final install size when it is
    known, while `downloadSizeBytes` is the provider source/archive size.
    """

    providers: dict[str, dict[str, Any]] = {}
    packages: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        provider_id = str(row["provider_id"])
        provider = providers.setdefault(
            provider_id,
            {
                "id": provider_id,
                "name": row["provider_name"],
                "adapterId": row.get("provider_adapter_id") or provider_id,
                "status": row.get("provider_status") or "ACTIVE",
                "health": row.get("provider_health") or "UNKNOWN",
                "lastCheckedAt": _format_optional_date(row.get("provider_last_checked_at")),
                "lastSuccessfulCatalogSync": _format_optional_date(
                    row.get("provider_last_catalog_sync")
                ),
                "website": row.get("provider_website"),
                "attribution": row.get("provider_attribution"),
                "licenseURL": row.get("provider_license_url"),
                "licenseInformation": row.get("provider_license_information"),
                "maps": [],
            },
        )
        package_id = row.get("package_id")
        if not package_id:
            continue
        artifact_id = row.get("artifact_id")
        artifact_source_url = row.get("artifact_source_url")
        artifact_download_size = row.get("artifact_size_bytes")
        if (
            not artifact_id
            or not artifact_source_url
            or artifact_download_size is None
            or int(artifact_download_size) <= 0
        ):
            continue
        key = (provider_id, str(package_id))
        package = packages.get(key)
        if package is None:
            release = str(row.get("release") or "unknown")
            normalized_version = _release_version(
                release,
                source_updated_at=row.get("package_source_updated_at"),
            )
            if normalized_version is None:
                # A provider-native release label is not necessarily a
                # calendar version. Do not expose the old technical sentinel
                # (2000-01) when neither the label nor the provider date can
                # establish a comparable version.
                continue
            year, month = normalized_version
            source_size = row.get("artifact_size_bytes")
            download_size = row.get("artifact_download_size_bytes") or source_size
            install_size = row.get("artifact_install_size_bytes")
            package = {
                "id": str(package_id),
                "region": row["package_region"],
                "name": row["package_name"],
                "country": row.get("package_country"),
                "version": {"year": year, "month": month},
                "sizeBytes": download_size or 0,
                "downloadSizeBytes": download_size,
                "installSizeBytes": install_size,
                "sourceURL": row.get("artifact_source_url"),
                "sourceUrl": row.get("artifact_source_url"),
                "releaseDate": _format_optional_date(row.get("package_source_updated_at")),
                "identifier": row.get("provider_region_id"),
                "providerRegionId": row.get("provider_region_id"),
                "canonicalRegionId": row.get("canonical_region_id"),
                "countryCodes": row.get("country_codes") or [],
                "regionKind": row.get("region_kind") or "country",
                "tags": row.get("tags") or [],
                "capabilities": row.get("capabilities") or [],
                "release": release,
                "availability": row.get("availability") or "AVAILABLE",
                "releaseMetadata": {
                    "releaseId": row.get("release_id"),
                    "versionLabel": row.get("version_label"),
                    "generatedAt": _format_optional_date(row.get("generated_at")),
                    "sourceUpdatedAt": _format_optional_date(row.get("package_source_updated_at")),
                },
                "artifacts": [],
            }
            packages[key] = package
            provider["maps"].append(package)

        if artifact_id:
            install_size = row.get("artifact_install_size_bytes")
            source_size = row.get("artifact_size_bytes")
            artifact = {
                "id": str(artifact_id),
                "kind": row["artifact_kind"],
                "required": bool(row.get("artifact_required", True)),
                "sourceUrl": row["artifact_source_url"],
                "sourceURL": row["artifact_source_url"],
                "sizeBytes": install_size,
                "downloadSizeBytes": source_size,
                "installSizeBytes": install_size,
                "checksumSha256": row.get("artifact_checksum_sha256"),
                "checksum": row.get("artifact_checksum_sha256"),
                "contentType": row.get("artifact_content_type"),
                "validationStatus": row.get("artifact_validation_status") or "NOT_VALIDATED",
                "validationState": _native_validation_state(
                    row.get("artifact_validation_status") or "NOT_VALIDATED"
                ),
            }
            if not any(item["id"] == artifact["id"] for item in package["artifacts"]):
                package["artifacts"].append(artifact)

    for provider in providers.values():
        valid_packages = []
        for package in provider["maps"]:
            package["artifacts"].sort(key=lambda item: (item["kind"] != "main", item["id"]))
            if any(item["kind"] == "main" for item in package["artifacts"]):
                valid_packages.append(package)
            else:
                package.pop("artifacts", None)
        provider["maps"] = sorted(valid_packages, key=lambda item: item["id"])

    return {
        "schemaVersion": 2,
        "catalogVersion": CATALOG_VERSION,
        "updatedAt": _format_timestamp(updated_at),
        "providers": [providers[key] for key in sorted(providers)],
    }


def _release_version(
    value: str,
    *,
    source_updated_at: Any = None,
) -> tuple[int, int] | None:
    """Return a comparable year/month without inventing a provider version.

    Some providers publish a release sequence such as Freizeitkarte's
    ``2/2026``. That is a provider-native label, not February 2026. When the
    provider also supplies a source date, that date is the authoritative
    comparable version (for example ``2026-05-03`` becomes ``2026-05``).
    """

    if source_updated_at is not None:
        year = getattr(source_updated_at, "year", None)
        month = getattr(source_updated_at, "month", None)
        if (
            isinstance(year, int)
            and isinstance(month, int)
            and _valid_version(year, month)
        ):
            return year, month

    match = re.search(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])\b", value)
    if match:
        version = int(match.group(1)), int(match.group(2))
        return version if _valid_version(*version) else None

    # `2/2026` is intentionally not reversed to `2026-02`: the first number
    # is a provider release sequence and only the source date can establish
    # the calendar month used for comparisons.
    if re.search(r"\b(?:0?[1-9]|1[0-2])/20\d{2}\b", value):
        return None

    return None


def _valid_version(year: int, month: int) -> bool:
    # 2000-01 was the historical serializer fallback and is never a valid
    # public provider version.
    return year >= 2000 and 1 <= month <= 12 and (year, month) != (2000, 1)


def _native_validation_state(value: str) -> str:
    return {
        "NOT_VALIDATED": "notValidated",
        "VALIDATING": "validating",
        "VALIDATED": "validated",
        "FAILED": "failed",
        "UNAVAILABLE": "unavailable",
    }.get(value, "notValidated")


def _format_optional_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def serialize_catalog(catalog: dict[str, Any]) -> bytes:
    return json.dumps(
        catalog,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def catalog_etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )

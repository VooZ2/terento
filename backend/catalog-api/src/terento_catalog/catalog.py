from __future__ import annotations

import hashlib
import json
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

    providers: dict[str, dict[str, Any]] = {}
    for row in rows:
        provider_id = row["provider_id"]
        provider = providers.setdefault(
            provider_id,
            {
                "id": provider_id,
                "name": row["provider_name"],
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
        }
        provider["maps"].append(map_document)

    for provider in providers.values():
        provider["maps"].sort(key=lambda item: item["id"])

    return {
        "catalogVersion": CATALOG_VERSION,
        "updatedAt": _format_timestamp(updated_at),
        "providers": [providers[key] for key in sorted(providers)],
    }


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

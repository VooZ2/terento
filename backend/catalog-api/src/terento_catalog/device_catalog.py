from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from . import DEVICE_CATALOG_VERSION
from .asset_attribution import LEGAL_METADATA, public_asset_source

CONTROLLED_ASSET_PREFIX = "https://api.terento.app/assets/devices/"
OFFICIAL_MEDIA_HOSTS = {"res.garmin.com"}
ALLOWED_ASSET_SCOPES = {
    "FAMILY",
    "MODEL",
    "MODEL_SIZE",
    "EXACT_VARIANT",
    "GENERIC",
}
ASSET_AVAILABLE = "AVAILABLE"
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)")


def build_device_catalog(
    rows: list[dict[str, Any]], updated_at: datetime
) -> dict[str, Any]:
    devices: list[dict[str, Any]] = []
    for row in rows:
        asset = {"status": "MISSING"}
        source_asset = None
        source_image_url = _official_source_image_url(row.get("source_image_url"))
        if source_image_url is not None:
            source_asset = {
                "url": source_image_url,
                "scope": "MODEL",
                "version": 1,
                "attribution": "Garmin official product media",
                "source": {
                    "type": "OFFICIAL_PRODUCT_MEDIA",
                    "brand": "Garmin",
                    "attributionRequired": True,
                },
            }
        asset_url = row.get("asset_url")
        asset_scope = row.get("asset_scope") or "MODEL"
        if (
            row.get("asset_status") == ASSET_AVAILABLE
            and isinstance(asset_url, str)
            and asset_url.startswith(CONTROLLED_ASSET_PREFIX)
            and asset_scope in ALLOWED_ASSET_SCOPES
            and isinstance(row.get("asset_storage_key"), str)
            and public_asset_source(row) is not None
        ):
            source = public_asset_source(row)
            assert source is not None
            asset = {
                "status": ASSET_AVAILABLE,
                "type": _clean_text(row.get("asset_type") or "product-image"),
                "url": asset_url,
                "scope": asset_scope,
                "sha256": row.get("asset_sha256"),
                "mimeType": row.get("asset_mime_type"),
                "width": row.get("asset_width"),
                "height": row.get("asset_height"),
                "version": row.get("asset_version") or 1,
                "attribution": _clean_text(row.get("asset_attribution")),
                "source": source,
            }
        devices.append(
            {
                "id": row["device_id"],
                "manufacturer": _clean_text(row["manufacturer"]),
                "family": _clean_text(row["family_canonical_name"]),
                "familyName": _clean_text(row["family_name"]),
                "model": _clean_text(row["model"]),
                "canonicalModel": _clean_text(row["canonical_model"]),
                "variant": _clean_text(row["variant"]),
                "caseSizeMm": row["case_size_mm"],
                "displayType": _clean_text(row["display_type"]),
                "partNumber": _clean_text(row["part_number"]),
                "productURL": _public_https_url(row.get("product_url")),
                "active": row["active"],
                "mapCapable": bool(row["map_capable"]) if row.get("map_capable") is not None else None,
                "asset": asset,
            }
        )
        if source_asset is not None:
            devices[-1]["sourceAsset"] = source_asset

    devices.sort(key=lambda item: item["id"])
    return {
        "catalogVersion": DEVICE_CATALOG_VERSION,
        "updatedAt": _format_timestamp(updated_at),
        "manufacturer": "Garmin",
        "legal": LEGAL_METADATA,
        "devices": devices,
    }


def serialize_device_catalog(catalog: dict[str, Any]) -> bytes:
    return json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def device_catalog_etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def _clean_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    # The public contract contains plain text and direct URL fields, never
    # Markdown links copied from an upstream page.
    return MARKDOWN_LINK_RE.sub(r"\1", value).strip()


def _public_https_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith("https://") and "[" not in value and "](" not in value:
        return value
    return None


def _official_source_image_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() not in OFFICIAL_MEDIA_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or not parsed.path
    ):
        return None
    return value


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )

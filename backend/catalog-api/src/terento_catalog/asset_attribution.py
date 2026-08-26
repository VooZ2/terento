from __future__ import annotations

from typing import Any


ASSET_SOURCE_TYPES = frozenset(
    {
        "OFFICIAL_PRODUCT_MEDIA",
        "TERENTO_RENDER",
        "GENERIC_FALLBACK",
    }
)
OFFICIAL_PRODUCT_MEDIA = "OFFICIAL_PRODUCT_MEDIA"
TERENTO_RENDER = "TERENTO_RENDER"
GENERIC_FALLBACK = "GENERIC_FALLBACK"
GENERIC_FALLBACK_IMAGE_URL = "https://terento.app/assets/generic-garmin-watch.png?v=20260826-1"

LEGAL_METADATA = {
    "manufacturerNotice": True,
    "text": (
        "Garmin and fēnix are trademarks of Garmin Ltd. "
        "Terento is an independent open-source project and is not affiliated with Garmin."
    ),
}


def normalize_asset_source(
    source_type: Any,
    brand: Any,
    attribution_required: Any,
    *,
    required: bool = False,
) -> tuple[str, str, bool] | None:
    """Validate the controlled source metadata used by public assets.

    Missing metadata is allowed for non-public lifecycle rows. An AVAILABLE
    row must provide a complete, semantically correct source declaration.
    """

    if source_type is None and brand is None and attribution_required is None:
        if required:
            raise ValueError("available assets require source attribution metadata")
        return None
    if source_type not in ASSET_SOURCE_TYPES:
        raise ValueError("unsupported device asset source type")
    if not isinstance(brand, str) or not brand.strip():
        raise ValueError("device asset source brand is required")
    if not isinstance(attribution_required, bool):
        raise ValueError("device asset attribution requirement must be boolean")

    normalized_brand = brand.strip()
    expected = {
        OFFICIAL_PRODUCT_MEDIA: ("Garmin", True),
        TERENTO_RENDER: ("Terento", False),
        GENERIC_FALLBACK: ("Terento", False),
    }[source_type]
    if (normalized_brand, attribution_required) != expected:
        raise ValueError(
            f"source metadata does not match the {source_type} attribution policy"
        )
    return source_type, normalized_brand, attribution_required


def public_asset_source(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        normalized = normalize_asset_source(
            row.get("asset_source_type"),
            row.get("asset_source_brand"),
            row.get("asset_attribution_required"),
            required=True,
        )
    except ValueError:
        return None
    assert normalized is not None
    source_type, brand, attribution_required = normalized
    return {
        "type": source_type,
        "brand": brand,
        "attributionRequired": attribution_required,
    }


def generic_fallback_image() -> dict[str, Any]:
    """Return the stable, neutral image used when no model photo is available."""

    return {
        "url": GENERIC_FALLBACK_IMAGE_URL,
        "origin": "fallback",
        "status": "FALLBACK",
        "source": {
            "type": GENERIC_FALLBACK,
            "brand": "Terento",
            "attributionRequired": False,
        },
    }

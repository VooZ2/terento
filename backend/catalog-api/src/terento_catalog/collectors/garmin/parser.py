from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin


CATEGORY_SOURCE_URL = "https://www.garmin.com/en-US/c/wearables-smartwatches/"
MANUFACTURER = "Garmin"


class GarminCatalogParserError(ValueError):
    pass


@dataclass(frozen=True)
class GarminProduct:
    source_id: str
    name: str
    product_url: str
    description: str
    group: bool


@dataclass(frozen=True)
class NormalizedGarminDevice:
    id: str
    family_id: str
    family_name: str
    manufacturer: str
    model: str
    canonical_model: str
    variant: str
    case_size_mm: int | None
    display_type: str | None
    product_url: str
    source_url: str = CATEGORY_SOURCE_URL
    part_number: str | None = None


def parse_category_products(document: dict[str, Any]) -> list[GarminProduct]:
    """Parse the official Garmin category API response.

    The category page itself is the public source. Garmin's own page currently
    obtains its product cards through the accompanying official category API;
    this parser accepts only the non-group product records so family summary
    cards do not become duplicate device models.
    """

    products = document.get("products")
    if not isinstance(products, list) or not products:
        raise GarminCatalogParserError("Garmin category response has no products")
    meta = document.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("totalProductCount"), int):
        expected_count = meta["totalProductCount"]
        if len(products) < expected_count:
            raise GarminCatalogParserError(
                "Garmin category response is incomplete; refusing partial source scan"
            )

    parsed: list[GarminProduct] = []
    for item in products:
        if not isinstance(item, dict) or item.get("group") is True:
            continue
        source_id = _text(item.get("id"))
        name = _clean_display_text(_text(item.get("name")))
        product_url = _https_url(_text(item.get("url")))
        if not source_id or not name or product_url is None:
            continue
        description_value = item.get("description")
        if isinstance(description_value, dict):
            description = _clean_display_text(
                _text(description_value.get("shortText"))
            )
        else:
            description = _clean_display_text(_text(description_value))
        parsed.append(
            GarminProduct(
                source_id=source_id,
                name=name,
                product_url=product_url,
                description=description,
                group=False,
            )
        )

    if not parsed:
        raise GarminCatalogParserError(
            "Garmin category response has no concrete product records"
        )
    return parsed


def normalize_products(products: list[GarminProduct]) -> list[NormalizedGarminDevice]:
    """Normalize products and collapse cosmetic SKU differences deterministically."""

    devices: dict[str, NormalizedGarminDevice] = {}
    for product in products:
        device = normalize_product(product)
        existing = devices.get(device.id)
        if existing is None or _device_sort_key(device) < _device_sort_key(existing):
            devices[device.id] = device
    return [devices[key] for key in sorted(devices)]


def normalize_product(product: GarminProduct) -> NormalizedGarminDevice:
    display_name = _clean_display_text(product.name)
    model_text, variant = _split_model_variant(display_name)
    case_size_mm = _case_size_mm(display_name)
    display_type = _display_type(display_name)
    family_name = model_text.split(" ", 1)[0]
    family_slug = canonical_slug(family_name)
    canonical_model = canonical_text(model_text)
    meaningful_variant = _meaningful_variant(variant)

    id_parts = ["garmin", canonical_slug(canonical_model)]
    if case_size_mm is not None:
        id_parts.append(str(case_size_mm))
    if display_type is not None:
        id_parts.append(canonical_slug(display_type))
    if meaningful_variant:
        id_parts.append(meaningful_variant)

    return NormalizedGarminDevice(
        id="-".join(part for part in id_parts if part),
        family_id=f"garmin-{family_slug}",
        family_name=family_name,
        manufacturer=MANUFACTURER,
        model=model_text,
        canonical_model=canonical_model,
        variant=variant,
        case_size_mm=case_size_mm,
        display_type=display_type,
        product_url=product.product_url,
    )


def parse_product_page(
    html: str,
    *,
    product_id: str | None = None,
) -> str | None:
    """Return one deterministic representative part number from Garmin HTML.

    Garmin exposes a JSON bootstrap object in the product page. We parse only
    metadata; image URLs in that object are deliberately ignored.
    """

    marker = "var GarminAppBootstrap = "
    start = html.find(marker)
    if start < 0:
        raise GarminCatalogParserError("Garmin product page bootstrap is missing")
    start += len(marker)
    try:
        bootstrap, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError as exc:
        raise GarminCatalogParserError("Garmin product page bootstrap is invalid") from exc
    if not isinstance(bootstrap, dict):
        raise GarminCatalogParserError("Garmin product page bootstrap is not an object")

    skus = bootstrap.get("skus")
    if not isinstance(skus, dict):
        return None
    candidates: list[str] = []
    for sku in skus.values():
        if not isinstance(sku, dict):
            continue
        if product_id is not None and str(sku.get("productId", "")) != str(product_id):
            continue
        part_number = _text(sku.get("partNumber"))
        if part_number:
            candidates.append(part_number)
    return sorted(set(candidates))[0] if candidates else None


def canonical_slug(value: str) -> str:
    """Canonicalize identity strings while leaving display strings untouched."""

    return canonical_text(value).replace(" ", "-")


def canonical_text(value: str) -> str:
    """Return a stable ASCII, lower-case canonical display identity."""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = normalized.replace("®", "").replace("™", "")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _split_model_variant(value: str) -> tuple[str, str]:
    match = re.search(r"\s+[–—-]\s+", value)
    if match is None:
        return value.strip(), ""
    return value[: match.start()].strip(), value[match.end() :].strip()


def _case_size_mm(value: str) -> int | None:
    match = re.search(r"\b(\d{2})\s*mm\b", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _display_type(value: str) -> str | None:
    upper = value.upper()
    for token, display in (
        ("MICROLED", "MicroLED"),
        ("AMOLED", "AMOLED"),
        ("SOLAR", "Solar"),
    ):
        if token in upper:
            return display
    return None


_COSMETIC_TOKENS = {
    "and",
    "band",
    "bezel",
    "black",
    "blue",
    "carbon",
    "cerakote",
    "combination",
    "gold",
    "gray",
    "grey",
    "leather",
    "lens",
    "nylon",
    "rose",
    "sapphire",
    "silver",
    "silicone",
    "slate",
    "stainless",
    "steel",
    "titanium",
    "white",
    "with",
    "yellow",
}


def _meaningful_variant(value: str) -> str:
    if not value:
        return ""
    without_case = re.sub(r"\b\d{2}\s*mm\b", " ", value, flags=re.IGNORECASE)
    without_display = re.sub(
        r"\b(?:AMOLED|SOLAR|MICROLED)\b", " ", without_case, flags=re.IGNORECASE
    )
    tokens = re.findall(r"[A-Za-z0-9]+", without_display)
    meaningful = [token for token in tokens if token.lower() not in _COSMETIC_TOKENS]
    return canonical_slug(" ".join(meaningful))


def _device_sort_key(device: NormalizedGarminDevice) -> tuple[str, str, str]:
    return (device.product_url, device.variant, device.model)


def _clean_display_text(value: str) -> str:
    value = value.replace("®", "").replace("™", "")
    return " ".join(value.replace("\u00a0", " ").split()).strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _https_url(value: str) -> str | None:
    if not value:
        return None
    absolute = urljoin("https://www.garmin.com", value)
    return absolute if absolute.startswith("https://") else None

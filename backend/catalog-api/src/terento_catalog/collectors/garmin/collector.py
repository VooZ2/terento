from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from ...models import CollectedDevice
from .parser import (
    CATEGORY_SOURCE_URL,
    GarminCatalogParserError,
    GarminProduct,
    normalize_product,
    normalize_products,
    parse_category_products,
    parse_product_page,
)

LOGGER = logging.getLogger(__name__)


GARMIN_PRODUCTS_URL = (
    "https://www.garmin.com/c/api/getCategoryProducts?categoryKey=10002"
    "&locale=en-US&storeCode=US&appName=www-category-pages"
)


class Fetcher:
    user_agent = "TerentoCatalog/0.1 (+https://terento.app)"

    def fetch_json(self, url: str) -> dict[str, Any]:
        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=30) as response:
            import json

            value = json.loads(response.read().decode("utf-8", errors="replace"))
        if not isinstance(value, dict):
            raise GarminCatalogParserError("Garmin category response is not an object")
        return value

    def fetch_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")


@dataclass(frozen=True)
class GarminCollectionResult:
    records: list[CollectedDevice]
    discovered_products: int
    canonical_devices: int
    warnings: tuple[str, ...] = ()
    complete: bool = True


@dataclass(frozen=True)
class GarminCollector:
    fetcher: Fetcher | None = None
    category_source_url: str = CATEGORY_SOURCE_URL
    products_url: str = GARMIN_PRODUCTS_URL
    enrich_part_numbers: bool = True

    def collect(self) -> GarminCollectionResult:
        fetcher = self.fetcher or Fetcher()
        document = fetcher.fetch_json(self.products_url)
        products = parse_category_products(document)
        normalized = normalize_products(products)
        warnings: list[str] = []

        part_numbers: dict[str, str | None] = {}
        if self.enrich_part_numbers:
            for product in products:
                try:
                    part_numbers[product.source_id] = parse_product_page(
                        fetcher.fetch_text(product.product_url),
                        product_id=product.source_id,
                    )
                except (OSError, GarminCatalogParserError, ValueError) as exc:
                    warning = f"product metadata unavailable for {product.product_url}: {exc}"
                    warnings.append(warning)
                    LOGGER.warning(warning)

        products_by_identity: dict[str, list[GarminProduct]] = {}
        for product in products:
            device = normalize_product(product)
            products_by_identity.setdefault(device.id, []).append(product)

        records: list[CollectedDevice] = []
        for device in normalized:
            source_products = products_by_identity[device.id]
            source_product = sorted(
                source_products,
                key=lambda item: (item.product_url, item.source_id),
            )[0]
            part_number = part_numbers.get(source_product.source_id)
            records.append(
                CollectedDevice(
                    id=device.id,
                    family_id=device.family_id,
                    family_name=device.family_name,
                    manufacturer=device.manufacturer,
                    model=device.model,
                    canonical_model=device.canonical_model,
                    variant=device.variant,
                    case_size_mm=device.case_size_mm,
                    display_type=device.display_type,
                    part_number=part_number,
                    product_url=device.product_url,
                    source_url=self.category_source_url,
                )
            )

        if not records:
            raise GarminCatalogParserError("Garmin collector returned no devices")
        LOGGER.info(
            "Garmin category: discovered %d products, normalized %d devices, warnings=%d",
            len(products),
            len(records),
            len(warnings),
        )
        return GarminCollectionResult(
            records=records,
            discovered_products=len(products),
            canonical_devices=len(records),
            warnings=tuple(warnings),
            complete=not warnings,
        )

from __future__ import annotations

import unittest

from terento_catalog.collectors.garmin.collector import (
    GARMIN_CYCLING_PRODUCTS_URL,
    GARMIN_PRODUCTS_URL,
    GarminCollector,
)
from terento_catalog.collectors.garmin.parser import (
    CATEGORY_SOURCE_URL,
    CYCLING_CATEGORY_SOURCE_URL,
)


class FakeGarminFetcher:
    document = {
        "products": [
            {
                "id": "family",
                "name": "fēnix 8",
                "url": "https://www.garmin.com/en-US/p/1/",
                "group": True,
            },
            {
                "id": "1",
                "name": "fēnix 8 – 47 mm, AMOLED",
                "url": "https://www.garmin.com/en-US/p/1/",
                "group": False,
                "image": {
                    "large": "https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg"
                },
            },
        ]
    }

    # Garmin's cycling category mixes Edge computers with radars, lights,
    # pedals and sensors, and lists family cards next to concrete products.
    cycling_document = {
        "products": [
            {"id": "50208", "name": "Edge® 850/550", "url": "https://www.garmin.com/en-US/p/1630197/",
             "group": True},
            {"id": "1967830", "name": "Edge® 1060", "url": "https://www.garmin.com/en-US/p/1967830/",
             "group": False, "image": {"large": "https://res.garmin.com/en/products/010-04598-00/g/cf-lg.jpg"}},
            {"id": "731136", "name": "Edge® 1040 Solar", "url": "https://www.garmin.com/en-US/p/731136/",
             "group": False, "image": {"large": "https://res.garmin.com/en/products/010-02503-20/g/cf-lg.jpg"}},
            {"id": "1600117", "name": "Edge® MTB", "url": "https://www.garmin.com/en-US/p/1600117/",
             "group": False},
            {"id": "900", "name": "Varia™ Radar", "url": "https://www.garmin.com/en-US/p/900/", "group": False},
            {"id": "901", "name": "Rally™ RS210", "url": "https://www.garmin.com/en-US/p/901/", "group": False},
            {"id": "902", "name": "HRM 600", "url": "https://www.garmin.com/en-US/p/902/", "group": False},
        ]
    }

    def __init__(self) -> None:
        self.json_urls: list[str] = []
        self.text_urls: list[str] = []

    def fetch_json(self, url: str):
        self.json_urls.append(url)
        return self.cycling_document if url == GARMIN_CYCLING_PRODUCTS_URL else self.document

    def fetch_text(self, url: str) -> str:
        self.text_urls.append(url)
        return 'var GarminAppBootstrap = {"skus": {}};'


class GarminCollectorTests(unittest.TestCase):
    def test_collects_metadata_only_and_does_not_fetch_images(self) -> None:
        fetcher = FakeGarminFetcher()
        result = GarminCollector(
            fetcher=fetcher,
            enrich_part_numbers=False,
            cycling_products_url=None,
        ).collect()
        self.assertEqual(result.discovered_products, 1)
        self.assertEqual(result.canonical_devices, 1)
        self.assertEqual(result.records[0].id, "garmin-fenix-8-47-amoled")
        self.assertEqual(
            result.records[0].source_image_url,
            "https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg",
        )
        self.assertEqual(fetcher.text_urls, [])
        self.assertEqual(len(fetcher.json_urls), 1)

    def test_product_page_failure_keeps_discovered_record_as_partial(self) -> None:
        fetcher = FakeGarminFetcher()

        def failing_fetch_text(url: str) -> str:
            raise OSError("temporary upstream failure")

        fetcher.fetch_text = failing_fetch_text  # type: ignore[method-assign]
        result = GarminCollector(fetcher=fetcher, cycling_products_url=None).collect()
        self.assertEqual(len(result.records), 1)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.warnings), 1)

    def test_cycling_category_adds_only_edge_products(self) -> None:
        fetcher = FakeGarminFetcher()
        result = GarminCollector(fetcher=fetcher, enrich_part_numbers=False).collect()
        self.assertTrue(result.complete)
        self.assertEqual(fetcher.json_urls, [GARMIN_PRODUCTS_URL, GARMIN_CYCLING_PRODUCTS_URL])
        by_id = {record.id: record for record in result.records}
        self.assertEqual(sorted(by_id), [
            "garmin-edge-1040-solar-solar", "garmin-edge-1060", "garmin-edge-mtb", "garmin-fenix-8-47-amoled",
        ])
        self.assertEqual(result.discovered_products, 4)
        self.assertEqual(by_id["garmin-fenix-8-47-amoled"].source_url, CATEGORY_SOURCE_URL)
        for device_id in ("garmin-edge-1060", "garmin-edge-1040-solar-solar", "garmin-edge-mtb"):
            record = by_id[device_id]
            self.assertEqual((record.family_id, record.family_name), ("garmin-edge", "Edge"))
            self.assertEqual(record.source_url, CYCLING_CATEGORY_SOURCE_URL)
        solar = by_id["garmin-edge-1040-solar-solar"]
        self.assertEqual((solar.model, solar.canonical_model, solar.display_type),
                         ("Edge 1040 Solar", "edge 1040 solar", "Solar"))
        self.assertEqual(by_id["garmin-edge-1060"].source_image_url,
                         "https://res.garmin.com/en/products/010-04598-00/g/cf-lg.jpg")

    def test_failed_cycling_category_keeps_watches_and_is_partial(self) -> None:
        fetcher = FakeGarminFetcher()
        original = fetcher.fetch_json

        def failing_cycling(url: str):
            if url == GARMIN_CYCLING_PRODUCTS_URL:
                fetcher.json_urls.append(url)
                raise OSError("temporary upstream failure")
            return original(url)

        fetcher.fetch_json = failing_cycling  # type: ignore[method-assign]
        result = GarminCollector(fetcher=fetcher, enrich_part_numbers=False).collect()
        self.assertEqual([record.id for record in result.records], ["garmin-fenix-8-47-amoled"])
        self.assertFalse(result.complete)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Edge category unavailable", result.warnings[0])

    def test_cycling_category_without_edge_products_is_partial(self) -> None:
        fetcher = FakeGarminFetcher()
        fetcher.cycling_document = {"products": [
            {"id": "900", "name": "Varia™ Radar", "url": "https://www.garmin.com/en-US/p/900/", "group": False},
        ]}
        result = GarminCollector(fetcher=fetcher, enrich_part_numbers=False).collect()
        self.assertEqual([record.id for record in result.records], ["garmin-fenix-8-47-amoled"])
        self.assertFalse(result.complete)
        self.assertIn("no Edge products", result.warnings[0])


if __name__ == "__main__":
    unittest.main()

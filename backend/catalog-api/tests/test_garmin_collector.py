from __future__ import annotations

import unittest

from terento_catalog.collectors.garmin.collector import GarminCollector


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
            },
        ]
    }

    def __init__(self) -> None:
        self.json_urls: list[str] = []
        self.text_urls: list[str] = []

    def fetch_json(self, url: str):
        self.json_urls.append(url)
        return self.document

    def fetch_text(self, url: str) -> str:
        self.text_urls.append(url)
        return 'var GarminAppBootstrap = {"skus": {}};'


class GarminCollectorTests(unittest.TestCase):
    def test_collects_metadata_only_and_does_not_fetch_images(self) -> None:
        fetcher = FakeGarminFetcher()
        result = GarminCollector(
            fetcher=fetcher,
            enrich_part_numbers=False,
        ).collect()
        self.assertEqual(result.discovered_products, 1)
        self.assertEqual(result.canonical_devices, 1)
        self.assertEqual(result.records[0].id, "garmin-fenix-8-47-amoled")
        self.assertEqual(fetcher.text_urls, [])
        self.assertEqual(len(fetcher.json_urls), 1)

    def test_product_page_failure_keeps_discovered_record_as_partial(self) -> None:
        fetcher = FakeGarminFetcher()

        def failing_fetch_text(url: str) -> str:
            raise OSError("temporary upstream failure")

        fetcher.fetch_text = failing_fetch_text  # type: ignore[method-assign]
        result = GarminCollector(fetcher=fetcher).collect()
        self.assertEqual(len(result.records), 1)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.warnings), 1)


if __name__ == "__main__":
    unittest.main()

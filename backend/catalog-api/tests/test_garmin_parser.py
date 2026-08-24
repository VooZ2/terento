from __future__ import annotations

import unittest

from terento_catalog.collectors.garmin.parser import (
    GarminCatalogParserError,
    GarminProduct,
    normalize_product,
    normalize_products,
    parse_category_products,
    parse_product_page,
)


class GarminParserTests(unittest.TestCase):
    def test_incomplete_category_page_is_rejected(self) -> None:
        with self.assertRaises(GarminCatalogParserError):
            parse_category_products(
                {
                    "meta": {"totalProductCount": 2},
                    "products": [
                        {
                            "id": "1",
                            "name": "Venu X1",
                            "url": "https://www.garmin.com/en-US/p/1/",
                            "group": False,
                        }
                    ],
                }
            )

    def test_category_parser_ignores_family_summary_cards(self) -> None:
        products = parse_category_products(
            {
                "meta": {"totalProductCount": 2},
                "products": [
                    {
                        "id": "family",
                        "name": "fēnix 8",
                        "url": "https://www.garmin.com/en-US/p/1/",
                        "group": True,
                    },
                    {
                        "id": "variant",
                        "name": "fēnix® 8 – 47 mm, AMOLED",
                        "url": "https://www.garmin.com/en-US/p/2/",
                        "group": False,
                    },
                ],
            }
        )
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "fēnix 8 – 47 mm, AMOLED")

    def test_category_parser_preserves_only_official_large_product_image(self) -> None:
        products = parse_category_products(
            {
                "products": [
                    {
                        "id": "lily",
                        "name": "Lily 2 Active",
                        "url": "https://www.garmin.com/en-US/p/1/",
                        "group": False,
                        "image": {
                            "large": "https://res.garmin.com/en/products/010-02891-00/g/cf-lg.jpg"
                        },
                    },
                    {
                        "id": "external",
                        "name": "Venu X1",
                        "url": "https://www.garmin.com/en-US/p/2/",
                        "group": False,
                        "image": {"large": "https://example.com/not-garmin.jpg"},
                    },
                ]
            }
        )
        self.assertEqual(
            products[0].source_image_url,
            "https://res.garmin.com/en/products/010-02891-00/g/cf-lg.jpg",
        )
        self.assertIsNone(products[1].source_image_url)

    def test_normalization_preserves_display_diacritics_and_stable_identity(self) -> None:
        device = normalize_product(
            GarminProduct(
                "1",
                "fēnix® 8 – 47 mm, AMOLED",
                "https://www.garmin.com/en-US/p/1/",
                "",
                False,
            )
        )
        self.assertEqual(device.id, "garmin-fenix-8-47-amoled")
        self.assertEqual(device.family_id, "garmin-fenix")
        self.assertEqual(device.family_name, "fēnix")
        self.assertEqual(device.model, "fēnix 8")
        self.assertEqual(device.canonical_model, "fenix 8")
        self.assertEqual(device.case_size_mm, 47)
        self.assertEqual(device.display_type, "AMOLED")

    def test_cosmetic_skus_collapse_to_one_canonical_device(self) -> None:
        products = [
            GarminProduct(
                "1",
                "fēnix 8 – 47 mm, AMOLED, Sapphire, Titanium",
                "https://www.garmin.com/en-US/p/1/",
                "",
                False,
            ),
            GarminProduct(
                "2",
                "fēnix 8 – 47 mm, AMOLED, Black, Silicone",
                "https://www.garmin.com/en-US/p/2/",
                "",
                False,
            ),
        ]
        devices = normalize_products(products)
        self.assertEqual([device.id for device in devices], ["garmin-fenix-8-47-amoled"])

    def test_missing_case_and_display_are_null(self) -> None:
        device = normalize_product(
            GarminProduct(
                "1",
                "Venu X1",
                "https://www.garmin.com/en-US/p/1/",
                "",
                False,
            )
        )
        self.assertIsNone(device.case_size_mm)
        self.assertIsNone(device.display_type)
        self.assertEqual(device.id, "garmin-venu-x1")

    def test_product_page_extracts_metadata_without_touching_images(self) -> None:
        html = (
            'var GarminAppBootstrap = '
            '{"skus":{"010-02904-10":{"productId":"1228429",'
            '"partNumber":"010-02904-10",'
            '"productName":"fēnix 8 – 47 mm, AMOLED",'
            '"images":["https://res.garmin.com/image.jpg"]}}};'
        )
        self.assertEqual(parse_product_page(html, product_id="1228429"), "010-02904-10")


if __name__ == "__main__":
    unittest.main()

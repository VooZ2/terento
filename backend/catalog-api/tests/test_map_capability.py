from __future__ import annotations

import unittest

from terento_catalog.map_capability import classify_map_capable


class MapCapabilityTests(unittest.TestCase):
    def test_map_manager_prefixes_match_the_native_client(self) -> None:
        self.assertTrue(classify_map_capable("fēnix 7"))
        self.assertTrue(classify_map_capable("Forerunner 970"))
        self.assertTrue(classify_map_capable("MARQ Adventurer (Gen 2)"))
        self.assertTrue(classify_map_capable("fēnix 6 Pro"))
        self.assertTrue(classify_map_capable("Descent Mk2S"))
        self.assertTrue(classify_map_capable("Garmin fēnix 8 - 51mm"))
        self.assertTrue(classify_map_capable("venu x1"))
        self.assertTrue(classify_map_capable("fēnix 8 Pro"))
        self.assertFalse(classify_map_capable("Lily 2 Active"))
        self.assertFalse(classify_map_capable("Approach S70"))
        self.assertFalse(classify_map_capable("Venu 4"))
        self.assertFalse(classify_map_capable("Instinct 3"))
        self.assertIsNone(classify_map_capable("Garmin Future Watch"))
        self.assertIsNone(classify_map_capable("Forerunner 170"))
        self.assertIsNone(classify_map_capable("fēnix 9"))
        self.assertIsNone(classify_map_capable("fenix 7", manufacturer="Suunto"))

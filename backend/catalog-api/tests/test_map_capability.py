from __future__ import annotations

import unittest
from pathlib import Path
import re

from terento_catalog.map_capability import (
    KNOWN_NON_MAP_PREFIXES,
    SUPPORTED_PREFIXES,
    classify_map_capable,
)


class MapCapabilityTests(unittest.TestCase):
    def test_python_and_native_prefix_contracts_are_exactly_aligned(self) -> None:
        swift_source = (
            Path(__file__).parents[3]
            / "lab/native-connectivity-poc/Sources/TerentoPoC/Compatibility/MapCapability.swift"
        ).read_text()

        def values(name: str) -> set[str]:
            match = re.search(
                rf"private let {name}: Set<String> = \[(.*?)\n    \]",
                swift_source,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match)
            return set(re.findall(r'"([^"]+)"', match.group(1)))

        self.assertEqual(values("supportedPrefixes"), set(SUPPORTED_PREFIXES))
        self.assertEqual(values("knownNonMapPrefixes"), set(KNOWN_NON_MAP_PREFIXES))

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

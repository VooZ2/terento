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
            / "app/TerentoCore/Sources/TerentoPoC/Compatibility/MapCapability.swift"
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
        self.assertTrue(classify_map_capable("fēnix 9"))
        self.assertIsNone(classify_map_capable("fenix 7", manufacturer="Suunto"))

    def test_existing_fenix9_rows_are_classified_without_rewriting_specs_or_approval(self):
        from copy import deepcopy
        from datetime import datetime, timezone
        from test_admin_devices import device_row
        from terento_catalog.admin import _admin_device_payload
        from terento_catalog.device_catalog import build_device_catalog

        variants = [(size, '', False) for size in (43, 47, 51)]
        variants += [(size, 'Pro', reach) for size in (43, 47, 51) for reach in (False, True)]
        variants += [(size, 'Pro Solar', reach) for size in (47, 51) for reach in (False, True)]
        self.assertEqual(len(variants), 13)
        for size, edition, reach in variants:
            with self.subTest(size=size, edition=edition, inreach=reach):
                row = device_row(model='fēnix 9' + (' Pro' if edition else ''),
                    canonical_model='fenix 9' + (' pro' if edition else ''),
                    variant=f'{size} mm' + (', Solar' if 'Solar' in edition else '') + (', inReach' if reach else ''),
                    case_size_mm=size, screen_technology='MIP' if 'Solar' in edition else 'AMOLED',
                    solar='Solar' in edition, inreach=reach, map_capable=None,
                    support_status='NOT_EVALUATED', public_review_status='PENDING',
                    public_statistics_enabled=False, successful_install_count=0, attempted_install_count=0,
                    failed_install_count=0)
                original = deepcopy(row)
                device = build_device_catalog([row], datetime.now(timezone.utc))['devices'][0]
                admin = _admin_device_payload([row], None)['devices'][0]
                self.assertTrue(device['mapCapable'])
                self.assertIsNone(admin['mapCapable'])
                self.assertTrue(admin['observedMapCapability'])
                self.assertEqual(admin['installationAuthorization'], 'PENDING')
                self.assertFalse(admin['publicCompatibility']['published'])
                self.assertEqual(admin['supportStatus'], 'NOT_EVALUATED')
                self.assertEqual(device['model'], row['model'])
                self.assertEqual(device['variant'], row['variant'])
                self.assertEqual(device['inReach'], reach)
                self.assertEqual(row, original)
        row['map_capable'] = False
        self.assertFalse(build_device_catalog([row], datetime.now(timezone.utc))['devices'][0]['mapCapable'])

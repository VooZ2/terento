from __future__ import annotations

import unittest

from terento_catalog.compatibility_status import (
    STATUS_PUBLIC_COPY,
    CompatibilityStatus,
    calculate_compatibility_status,
)


class CompatibilityStatusTests(unittest.TestCase):
    def status(self, successful_install_count: int, **changes):
        values = {
            "successful_install_count": successful_install_count,
            "recognized_map_capable_evidence": True,
        }
        values.update(changes)
        return calculate_compatibility_status(**values)

    def test_threshold_boundaries(self):
        expected = {
            0: CompatibilityStatus.TESTING,
            1: CompatibilityStatus.TESTED,
            2: CompatibilityStatus.TESTED,
            3: CompatibilityStatus.SUPPORTED,
            4: CompatibilityStatus.SUPPORTED,
            5: CompatibilityStatus.VERIFIED,
            6: CompatibilityStatus.VERIFIED,
        }
        for count, status in expected.items():
            with self.subTest(count=count):
                self.assertEqual(self.status(count), status)

    def test_failed_reports_are_not_successes(self):
        self.assertEqual(self.status(1), CompatibilityStatus.TESTED)

    def test_non_map_devices_have_no_compatibility_status(self):
        self.assertIsNone(self.status(0, recognized_map_capable_evidence=False))
        self.assertIsNone(self.status(5, recognized_map_capable_evidence=False))

    def test_old_promotion_dimensions_do_not_change_status(self):
        self.assertEqual(self.status(1), CompatibilityStatus.TESTED)
        self.assertEqual(self.status(3), CompatibilityStatus.SUPPORTED)
        self.assertEqual(self.status(5), CompatibilityStatus.VERIFIED)

    def test_statuses_and_copy_are_exactly_canonical(self):
        self.assertEqual(
            {status.value for status in CompatibilityStatus},
            {"TESTING", "TESTED", "SUPPORTED", "VERIFIED"},
        )
        self.assertEqual(
            STATUS_PUBLIC_COPY[CompatibilityStatus.TESTING],
            "Terento has recognized this model as map-capable, but no successful shared installation has been received yet.",
        )
        self.assertEqual(
            STATUS_PUBLIC_COPY[CompatibilityStatus.TESTED],
            "1–2 successful installations have been shared by Terento users.",
        )
        self.assertEqual(
            STATUS_PUBLIC_COPY[CompatibilityStatus.SUPPORTED],
            "3–4 successful installations have been shared by Terento users.",
        )
        self.assertEqual(
            STATUS_PUBLIC_COPY[CompatibilityStatus.VERIFIED],
            "5 or more successful installations have been shared by Terento users.",
        )


if __name__ == "__main__":
    unittest.main()

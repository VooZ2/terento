from __future__ import annotations

import unittest

from terento_catalog.compatibility_status import (
    CompatibilityStatus,
    calculate_compatibility_status,
)


class CompatibilityStatusTests(unittest.TestCase):
    def status(self, **changes):
        values = {
            "evidence_count": 1,
            "successful_install_count": 1,
            "reconnect_verified_install_count": 0,
            "firmware_version_count": 1,
            "physical_device_count": 0,
        }
        values.update(changes)
        return calculate_compatibility_status(**values)

    def test_unknown_has_no_exact_identity_evidence(self):
        self.assertEqual(self.status(evidence_count=0, successful_install_count=0), CompatibilityStatus.UNKNOWN)

    def test_partial_or_failed_hardware_evidence_is_testing(self):
        self.assertEqual(self.status(successful_install_count=0), CompatibilityStatus.TESTING)

    def test_successful_install_without_reconnect_is_supported(self):
        self.assertEqual(self.status(), CompatibilityStatus.SUPPORTED)

    def test_reconnect_is_optional_diagnostic_evidence(self):
        self.assertEqual(
            self.status(successful_install_count=1, reconnect_verified_install_count=1),
            CompatibilityStatus.SUPPORTED,
        )

    def test_verified_requires_multiple_devices_and_firmware_variation(self):
        self.assertEqual(
            self.status(
                successful_install_count=2,
                reconnect_verified_install_count=1,
                firmware_version_count=2,
                physical_device_count=1,
            ),
            CompatibilityStatus.SUPPORTED,
        )
        self.assertEqual(
            self.status(
                successful_install_count=2,
                reconnect_verified_install_count=1,
                firmware_version_count=2,
                physical_device_count=2,
            ),
            CompatibilityStatus.VERIFIED,
        )

    def test_repeated_one_device_count_does_not_make_verified(self):
        self.assertNotEqual(
            self.status(
                evidence_count=8,
                successful_install_count=8,
                reconnect_verified_install_count=0,
                firmware_version_count=1,
                physical_device_count=1,
            ),
            CompatibilityStatus.VERIFIED,
        )


if __name__ == "__main__":
    unittest.main()

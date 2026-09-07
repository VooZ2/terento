import unittest

from terento_catalog.compatibility_status import (
    CompatibilityStatus,
    calculate_compatibility_status,
)


class CompatibilityStatusContractTests(unittest.TestCase):
    def test_all_threshold_boundaries_are_canonical(self):
        expected = {
            0: CompatibilityStatus.TESTING,
            1: CompatibilityStatus.TESTED,
            2: CompatibilityStatus.TESTED,
            3: CompatibilityStatus.SUPPORTED,
            4: CompatibilityStatus.SUPPORTED,
            5: CompatibilityStatus.VERIFIED,
            25: CompatibilityStatus.VERIFIED,
        }
        for count, status in expected.items():
            with self.subTest(count=count):
                self.assertEqual(
                    calculate_compatibility_status(
                        successful_install_count=count,
                        recognized_map_capable_evidence=True,
                    ),
                    status,
                )

    def test_unknown_identity_is_promoted_by_successful_evidence(self):
        self.assertIsNone(
            calculate_compatibility_status(
                successful_install_count=0,
                recognized_map_capable_evidence=False,
            )
        )
        self.assertEqual(
            calculate_compatibility_status(
                successful_install_count=1,
                recognized_map_capable_evidence=False,
            ),
            CompatibilityStatus.TESTED,
        )


if __name__ == "__main__":
    unittest.main()

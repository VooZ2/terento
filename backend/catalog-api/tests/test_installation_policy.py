from datetime import datetime, timezone
import unittest

from terento_catalog.installation_policy import (
    build_installation_policy,
    installation_base_model,
    summarize_installation_catalog,
)


class InstallationPolicyTests(unittest.TestCase):
    def test_base_model_uses_catalog_model_not_variant_rich_canonical_identity(self):
        self.assertEqual(installation_base_model("fēnix 7 Pro"), "fenix 7 pro")
        self.assertEqual(installation_base_model("Garmin fēnix 7 Pro Solar"), "fenix 7 pro")
        self.assertNotEqual(installation_base_model("fēnix 7X Pro"), "fenix 7 pro")
        self.assertNotEqual(installation_base_model("fēnix 8"), "fenix 7 pro")
        self.assertNotEqual(installation_base_model("Edge 840"), "fenix 7 pro")
        rows = [
            dict(device_id="pro", manufacturer="Garmin", model="fēnix 7 Pro",
                 canonical_model="fenix 7 pro", active=True, map_capable=True),
            dict(device_id="solar", manufacturer="Garmin", model="fēnix 7 Pro",
                 canonical_model="fenix 7 pro solar no wifi", active=True, map_capable=False),
        ]
        policy = build_installation_policy(rows, datetime(2026, 9, 22, tzinfo=timezone.utc))
        self.assertEqual({row["baseModel"] for row in policy["devices"]}, {"fenix 7 pro"})

    def test_policy_is_derived_from_active_and_map_capable_only(self):
        rows = [
            {
                "device_id": "fenix-8",
                "manufacturer": "Garmin",
                "model": "fenix 8",
                "canonical_model": "fenix 8",
                "variant": "47 mm AMOLED",
                "case_size_mm": 47,
                "display_type": "AMOLED",
                "active": True,
                "map_capable": True,
                "support_status": "NOT_EVALUATED",
                "successful_install_count": 0,
            },
            {
                "device_id": "fenix-7",
                "manufacturer": "Garmin",
                "model": "fenix 8",
                "canonical_model": "fenix 7",
                "variant": "51 mm AMOLED",
                "case_size_mm": 51,
                "display_type": "AMOLED",
                "active": True,
                "map_capable": True,
                "support_status": "UNSUPPORTED",
            },
            {
                "device_id": "enduro-3",
                "manufacturer": "Garmin",
                "model": "Enduro 3",
                "canonical_model": "Enduro 3",
                "variant": "51 mm",
                "case_size_mm": 51,
                "display_type": "MIP",
                "active": True,
                "map_capable": True,
                "support_status": "NOT_EVALUATED",
            },
            {
                "device_id": "edge-840",
                "manufacturer": "Garmin",
                "model": "Edge 840",
                "canonical_model": "Edge 840",
                "variant": "",
                "active": True,
                "map_capable": False,
                "support_status": "SUPPORTED",
            },
            {
                "device_id": "unknown-capability",
                "manufacturer": "Garmin",
                "model": "future model",
                "canonical_model": "future model",
                "variant": "",
                "active": True,
                "map_capable": None,
                "support_status": "SUPPORTED",
            },
            {
                "device_id": "inactive-map-model",
                "manufacturer": "Garmin",
                "model": "retired model",
                "canonical_model": "retired model",
                "variant": "",
                "active": False,
                "map_capable": True,
                "support_status": "SUPPORTED",
            },
        ]

        policy = build_installation_policy(
            rows, datetime(2026, 9, 22, tzinfo=timezone.utc)
        )

        by_id = {row["id"]: row for row in policy["devices"]}
        self.assertEqual(policy["schemaVersion"], 3)
        self.assertEqual(policy["policyVersion"], 3)
        self.assertEqual(by_id["fenix-8"]["baseModel"], "fenix 8")
        self.assertEqual(by_id["fenix-8"]["installationAuthorization"], "APPROVED")
        self.assertEqual(by_id["fenix-7"]["installationAuthorization"], "APPROVED")
        self.assertEqual(by_id["enduro-3"]["installationAuthorization"], "APPROVED")
        self.assertEqual(by_id["edge-840"]["scope"], "OUT_OF_SCOPE")
        self.assertEqual(by_id["edge-840"]["installationAuthorization"], "BLOCKED")
        self.assertEqual(by_id["unknown-capability"]["installationAuthorization"], "PENDING")
        self.assertEqual(by_id["inactive-map-model"]["installationAuthorization"], "BLOCKED")
        self.assertNotIn("supportStatus", by_id["fenix-7"])
        self.assertNotIn("successful_install_count", policy)

        summary = summarize_installation_catalog(rows)
        self.assertEqual(summary["mapCapableTrue"], 4)
        self.assertEqual(summary["mapCapableFalse"], 1)
        self.assertEqual(summary["mapCapableNull"], 1)
        self.assertEqual(summary["activeMapCapableTrueApproved"], 3)
        self.assertEqual(summary["activeMapCapableFalseBlocked"], 1)
        self.assertEqual(summary["activeMapCapableNullPending"], 1)

        active_yes = [row for row in policy["devices"] if row["active"] and row["mapCapable"] is True]
        self.assertTrue(all(row["installationAuthorization"] == "APPROVED" for row in active_yes))


if __name__ == "__main__":
    unittest.main()

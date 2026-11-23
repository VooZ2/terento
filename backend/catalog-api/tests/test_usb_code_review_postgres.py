"""Migration 100: Garmin USB code review (2026-11-23).

USB 091e:51b8 is Garmin device type 006-B4536-00 (0x4000 + 4536): fēnix 8 and
quatix 8 AMOLED, 47 and 51 mm. quatix 8 47 mm AMOLED waited in Identity review
because its link was missing and the 43/51 mm links were still PENDING.
"""
from __future__ import annotations

import json
import unittest

from pglite_support import PGliteTestCase

from terento_catalog.db import IDENTITY_DEVICE_QUERY, IDENTITY_MAPPING_QUERY, migration_directory
from terento_catalog.identity_assessment import assess_identity, hard_identity_conflicts, selected_identity_conflicts
from terento_catalog.migrate import _statements

MIGRATION = migration_directory() / "100_garmin_usb_code_review.sql"
SOURCE = "https://example.org/source"
F43, F47, F51 = "garmin-fenix-8-43-amoled", "garmin-fenix-8-47-amoled", "garmin-fenix-8-51-amoled"
F47S, F51S = "garmin-fenix-8-47-solar", "garmin-fenix-8-51-solar"
Q47, Q51 = "garmin-quatix-8-47-amoled", "garmin-quatix-8-51-amoled"
# Production catalog rows (collector managed, so absent from a fresh database).
ROWS = (
    (F43, "fēnix 8", "43 mm, AMOLED", 43, "AMOLED", None),
    (F47, "fēnix 8", "47 mm, AMOLED", 47, "AMOLED", None),
    (F51, "fēnix 8", "51 mm, AMOLED", 51, "AMOLED", None),
    (F47S, "fēnix 8", "47 mm, Solar", 47, "MIP", True),
    (F51S, "fēnix 8", "51 mm, Solar", 51, "MIP", True),
    (Q47, "quatix 8", "47 mm, AMOLED", 47, "AMOLED", None),
    (Q51, "quatix 8", "51 mm, AMOLED", 51, "AMOLED", None),
)
USB = (0x091E, 0x51B8)


class UsbCodeReviewTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        for device_id, model, variant, size, screen, solar in ROWS:
            self.sql(
                """INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                       case_size_mm, product_url, source_url, screen_technology, solar)
                   VALUES (%s, 'garmin-fenix', 'Garmin', %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET model = EXCLUDED.model, variant = EXCLUDED.variant,
                       case_size_mm = EXCLUDED.case_size_mm, screen_technology = EXCLUDED.screen_technology,
                       solar = EXCLUDED.solar""",
                (device_id, model, model.lower(), variant, size, SOURCE, SOURCE, screen, solar))
        self.sql("DELETE FROM device_identity_mapping_audit")
        self.sql("DELETE FROM device_identity_mapping WHERE value IN ('091e:51b8', '006-B4536-00')")
        # Production state 2026-11-23 (Admin Model sources).
        for device_id, status in ((F47, "APPROVED"), (F43, "PENDING"), (F51, "PENDING"),
                                  (F47S, "REJECTED"), (F51S, "REJECTED")):
            self.link("USB", "091e:51b8", device_id, status)
        for device_id, status in ((F47, "APPROVED"), (F51, "APPROVED"), (Q47, "APPROVED"), (Q51, "APPROVED"),
                                  (F47S, "REJECTED"), (F51S, "REJECTED")):
            self.link("XML_PART_NUMBER", "006-B4536-00", device_id, status)

    def link(self, kind, value, device_id, status="PENDING"):
        return self.sql(
            """INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, status)
               VALUES (%s, %s, %s, %s, 'test', %s) RETURNING id""",
            (kind, value, device_id, SOURCE, status))[0]["id"]

    def migrate(self):
        for statement in _statements(MIGRATION.read_text(encoding="utf-8")):
            self.sql(statement)

    def links(self, value="091e:51b8"):
        return {row["device_model_id"]: row["status"] for row in self.sql(
            "SELECT device_model_id, status FROM device_identity_mapping WHERE value = %s", (value,))}

    def assess(self, raw, description=None):
        return assess_identity({"rawMTPModel": raw, "garminModelDescription": description or raw,
                                "garminModelPartNumber": "006-B4536-00",
                                "usbVendorID": USB[0], "usbProductID": USB[1]},
                               self.sql(IDENTITY_DEVICE_QUERY), self.sql(IDENTITY_MAPPING_QUERY))

    def test_quatix_8_47_waits_for_review_before_the_migration(self):
        # Production 2026-11-22: two quatix 8 47 mm installs landed in Identity review.
        self.assertIsNone(self.assess("quatix 8 - 47mm", "quatix 8 - 47mm, AMOLED")["canonicalDeviceId"])

    def test_51b8_names_the_47_and_51_mm_amoled_models_of_both_watches(self):
        self.migrate()
        self.assertEqual(self.links(), {F47: "APPROVED", F51: "APPROVED", Q47: "APPROVED", Q51: "APPROVED",
                                        F43: "REJECTED", F47S: "REJECTED", F51S: "REJECTED"})
        audit = self.sql("SELECT d.device_model_id, a.previous_status, a.new_status, a.reviewed_by, a.reason"
                         " FROM device_identity_mapping_audit a JOIN device_identity_mapping d ON d.id = a.mapping_id"
                         " WHERE d.value = '091e:51b8' ORDER BY d.device_model_id")
        self.assertEqual([(a["device_model_id"], a["previous_status"], a["new_status"], a["reviewed_by"])
                          for a in audit],
                         [(F43, "PENDING", "REJECTED", None), (F51, "PENDING", "APPROVED", None),
                          (Q47, "PENDING", "APPROVED", None), (Q51, "PENDING", "APPROVED", None)])
        self.assertTrue(all(a["reason"].startswith("Migration 100:") for a in audit))

    def test_reports_resolve_to_their_own_model_without_code_conflicts(self):
        self.migrate()
        devices, mappings = self.sql(IDENTITY_DEVICE_QUERY), self.sql(IDENTITY_MAPPING_QUERY)
        by_id = {device["id"]: device for device in devices}
        for raw, description, expected in (
                ("quatix 8 - 47mm", "quatix 8 - 47mm, AMOLED", Q47),
                ("quatix 8 - 51mm", "quatix 8 - 51mm, AMOLED", Q51),
                ("fenix 8 - 47mm", "fenix 8 - 47mm, AMOLED", F47),
                ("fenix 8 - 51mm", "fenix 8 - 51mm, AMOLED", F51)):
            with self.subTest(raw=raw):
                assessment = self.assess(raw, description)
                self.assertEqual(assessment["canonicalDeviceId"], expected)
                event = {"rawMTPModel": raw, "garminModelDescription": description,
                         "garminModelPartNumber": "006-B4536-00", "usbVendorID": USB[0], "usbProductID": USB[1]}
                self.assertEqual(selected_identity_conflicts(event, by_id[expected], mappings), [])
                # The shared code never moves a fēnix to a quatix or back: the name decides.
                other = Q47 if expected.startswith("garmin-fenix") else F47
                fields = {c["field"] for c in selected_identity_conflicts(event, by_id[other], mappings)}
                self.assertIn("model", fields)
                self.assertNotIn("USB", fields)
        # A 43 mm watch reporting 51b8 is now a code conflict, as it would be a different device type.
        event = {"rawMTPModel": "fenix 8 - 43mm", "usbVendorID": USB[0], "usbProductID": USB[1]}
        self.assertEqual([c["field"] for c in hard_identity_conflicts(
            selected_identity_conflicts(event, by_id[F43], mappings))], ["USB"])

    def test_administrator_decisions_and_missing_catalog_rows_stay(self):
        self.sql("UPDATE device_identity_mapping SET status = 'APPROVED', reviewed_at = now()"
                 " WHERE value = '091e:51b8' AND device_model_id = %s", (F43,))
        self.sql("DELETE FROM device_identity_mapping WHERE device_model_id = %s", (Q51,))
        self.sql("DELETE FROM device_model WHERE id = %s", (Q51,))
        self.migrate()
        links = self.links()
        self.assertEqual(links[F43], "APPROVED")
        self.assertNotIn(Q51, links)
        self.assertEqual(links[Q47], "APPROVED")

    def test_fenix_8_solar_codes_follow_the_reported_device_types(self):
        # Production 2026-11-23: 006-B4532-00 (47 mm Solar) always with 51b4 (29 reports),
        # 006-B4533-00 (51 mm Solar) always with 51b5.
        for device_id, model, variant, size in (("garmin-fenix-8-dual-power-47", "fēnix 8 Dual Power", "47 mm", 47),
                                                ("garmin-fenix-8-dual-power-51", "fēnix 8 Dual Power", "51 mm", 51)):
            self.sql("""INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                            case_size_mm, product_url, source_url, screen_technology)
                        VALUES (%s, 'garmin-fenix', 'Garmin', %s, %s, %s, %s, %s, %s, 'MIP') ON CONFLICT (id) DO NOTHING""",
                     (device_id, model, model.lower(), variant, size, SOURCE, SOURCE))
        self.sql("DELETE FROM device_identity_mapping WHERE value IN ('091e:51b4', '091e:51b5')")
        for device_id, status in ((F43, "REJECTED"), (F47, "REJECTED"), (F51, "REJECTED"), (F47S, "PENDING"),
                                  (F51S, "PENDING")):
            self.link("USB", "091e:51b5", device_id, status)
        self.migrate()
        self.assertEqual(self.links("091e:51b4"), {F47S: "APPROVED", "garmin-fenix-8-dual-power-47": "APPROVED"})
        self.assertEqual(self.links("091e:51b5"), {F43: "REJECTED", F47: "REJECTED", F51: "REJECTED",
                                                   F47S: "REJECTED", F51S: "APPROVED",
                                                   "garmin-fenix-8-dual-power-51": "APPROVED"})
        # A report without the Garmin XML file is now told apart by its USB code alone.
        devices, mappings = self.sql(IDENTITY_DEVICE_QUERY), self.sql(IDENTITY_MAPPING_QUERY)
        for product, expected in ((0x51B4, F47S), (0x51B8, F47)):
            assessment = assess_identity({"rawMTPModel": "fenix 8 - 47mm", "usbVendorID": 0x091E,
                                          "usbProductID": product}, devices, mappings)
            self.assertEqual(assessment["canonicalDeviceId"], expected, hex(product))

    def test_fenix_9_pro_sizes_and_solar_get_their_own_usb_codes(self):
        rows = []
        for size, product, xml in ((43, 0x5358, "006-B4952-00"), (47, 0x5359, "006-B4953-00"),
                                   (51, 0x535A, "006-B4954-00")):
            for solar in (False, True):
                if solar and size == 43:
                    continue
                xml_code = xml if not solar else {47: "006-B4955-00", 51: "006-B4956-00"}[size]
                for inreach in (False, True):
                    device_id = f"garmin-fenix-9-pro-{size}" + ("-solar" if solar else "") + ("-inreach" if inreach else "")
                    rows.append((device_id, size, solar, inreach, xml_code))
        for device_id, size, solar, inreach, xml_code in rows:
            self.sql("""INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                            case_size_mm, product_url, source_url, solar, inreach)
                        VALUES (%s, 'garmin-fenix', 'Garmin', 'fēnix 9 Pro', 'fenix 9 pro', %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING""",
                     (device_id, device_id, size, SOURCE, SOURCE, solar or None, inreach))
            self.link("XML_PART_NUMBER", xml_code, device_id, "APPROVED")
        # libmtp named 091e:5359 for every size (migrations 048/086): all PENDING in production.
        self.sql("DELETE FROM device_identity_mapping WHERE kind = 'USB' AND value LIKE '091e:535%%'")
        for device_id, *_ in rows:
            self.link("USB", "091e:5359", device_id)
        self.migrate()
        links = self.links("091e:5359")
        self.assertEqual({d for d, s in links.items() if s == "APPROVED"},
                         {"garmin-fenix-9-pro-47", "garmin-fenix-9-pro-47-inreach"})
        self.assertEqual({s for d, s in links.items() if d not in {"garmin-fenix-9-pro-47", "garmin-fenix-9-pro-47-inreach"}},
                         {"REJECTED"})
        self.assertEqual(set(self.links("091e:535a")), {"garmin-fenix-9-pro-51", "garmin-fenix-9-pro-51-inreach"})
        devices, mappings = self.sql(IDENTITY_DEVICE_QUERY), self.sql(IDENTITY_MAPPING_QUERY)
        # Production: 3 "fenix 9 Pro - inReach, 51mm" reports without the XML file waited for review.
        assessment = assess_identity({"rawMTPModel": "fenix 9 Pro - inReach, 51mm", "usbVendorID": 0x091E,
                                      "usbProductID": 0x535A}, devices, mappings)
        self.assertEqual(assessment["canonicalDeviceId"], "garmin-fenix-9-pro-51-inreach")
        # Without the inReach word the code still cannot tell inReach apart (an absent word is no fact).
        assessment = assess_identity({"rawMTPModel": "fenix 9 Pro - 47mm", "usbVendorID": 0x091E,
                                      "usbProductID": 0x5359}, devices, mappings)
        self.assertEqual(sorted(c["deviceId"] for c in assessment["candidates"] if not c["conflict"]),
                         ["garmin-fenix-9-pro-47", "garmin-fenix-9-pro-47-inreach"])

    def test_every_seed_decision_follows_the_device_type_rule(self):
        seed = [json.loads(line.split("('", 1)[1].rsplit("'::jsonb)", 1)[0].replace("''", "'"))
                for line in MIGRATION.read_text(encoding="utf-8").splitlines() if line.startswith("('{")]
        self.assertTrue(seed)
        for facts in seed:
            with self.subTest(code=facts["value"], device=facts["device_model_id"]):
                self.assertEqual(facts["kind"], "USB")
                self.assertIn(facts["decision"], {"APPROVED", "REJECTED", "PENDING"})
                self.assertTrue(facts["reason"].startswith("Migration 100: this model"))
                if facts["decision"] == "APPROVED":
                    self.assertIn(f"reported only with USB {facts['value']}", facts["reason"])
                if facts["decision"] == "REJECTED":
                    self.assertIn(f"not {facts['value']}", facts["reason"])
        # tactix 8 Solar Elite's device type link is undecided, so 091e:52a8 is not reviewed here.
        self.assertNotIn("091e:52a8", {facts["value"] for facts in seed})
        # Web installer results resolve fēnix 7X Pro and epix (Gen 2) by a code that names one model:
        # this review must not make those codes name a second model.
        self.assertNotIn("091e:5118", {facts["value"] for facts in seed})
        self.assertEqual({facts["device_model_id"] for facts in seed if facts["value"] == "091e:4f67"}, set())

    def test_migration_is_data_only(self):
        code = "\n".join(line for line in MIGRATION.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("--")).upper()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "COMPATIBILITY_EVIDENCE_EVENT", "WEB_INSTALLER", "DEVICE_MODEL SET"):
            self.assertNotIn(forbidden, code)
        self.assertIn("M.STATUS = 'PENDING'", code)


if __name__ == "__main__":
    unittest.main()

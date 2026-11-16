"""Garmin code links protect catalog assignments (owner decision 2026-11-16).

A: no assignment, manual or not, may contradict a reviewed Garmin XML part
number or USB code link; manual assignment against other reported facts needs
a written reason. B: the Admin picker offers the models the code names first
and disables the ones it rules out. C: assigned results the current catalog
contradicts are counted (attention API, Identity review "Conflicts"). D: a code
link that real results contradict cannot be approved. E: catalog invariants of
every approved code link. Variant unknown: results no reported fact can tell
apart are NOT_IDENTIFIABLE automatically. Migration 094: Forerunner 955 /
955 Solar are one row and share code 006-B4024-00.
"""
from __future__ import annotations

import json
import unittest
from collections import defaultdict
from pathlib import Path

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows
from terento_catalog.admin import _identity_code_scope, _identity_review_form, identity_review_page
from terento_catalog.admin_attention import _identity_conflicts
from terento_catalog.db import IDENTITY_DEVICE_QUERY, IDENTITY_MAPPING_QUERY, IdentityResolutionError
from terento_catalog.identity_assessment import (
    assess_identity,
    hard_identity_conflicts,
    indistinguishable_candidates,
    model_label,
    selected_identity_conflicts,
)

MIGRATION_094 = (
    Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
    / "094_forerunner_955_solar_identity.sql"
)
SEVEN_PRO = "garmin-fenix-7-pro"
SEVEN_PRO_NO_WIFI = "garmin-fenix-7-pro-solar-no-wifi"
SEVEN_X_51 = "garmin-fenix-7x-51"
SEVEN_X_PRO = "garmin-fenix-7x-pro"
FR955 = "garmin-forerunner-955"
FR955_DUAL_POWER = "garmin-forerunner-955-dual-power"


def mapping(kind, value, device_id, status):
    return {"kind": kind, "value": value, "device_model_id": device_id, "status": status,
            "source_url": "https://example.org", "source_version": "test"}


class ConflictRuleTests(unittest.TestCase):
    device = {"id": "watch-a", "model": "Testwatch", "case_size_mm": None,
              "screen_technology": None, "solar": None, "inreach": None}
    event = {"rawMTPModel": "Testwatch", "garminModelPartNumber": "006-B0001-00"}

    def test_approved_link_to_another_model_is_a_hard_conflict(self):
        conflicts = selected_identity_conflicts(
            self.event, self.device, [mapping("XML_PART_NUMBER", "006-B0001-00", "watch-b", "APPROVED")])
        self.assertEqual([c["field"] for c in hard_identity_conflicts(conflicts)], ["XML_PART_NUMBER"])

    def test_rejected_link_to_the_selected_model_is_a_hard_conflict(self):
        conflicts = selected_identity_conflicts(
            self.event, self.device, [mapping("XML_PART_NUMBER", "006-B0001-00", "watch-a", "REJECTED")])
        [conflict] = hard_identity_conflicts(conflicts)
        self.assertTrue(conflict["rejectedMapping"])

    def test_incomplete_code_review_stays_a_soft_conflict(self):
        # Another target is still PENDING: the approved one does not rule the
        # selected model out for certain, so manual assignment stays possible.
        conflicts = selected_identity_conflicts(self.event, self.device, [
            mapping("XML_PART_NUMBER", "006-B0001-00", "watch-b", "APPROVED"),
            mapping("XML_PART_NUMBER", "006-B0001-00", "watch-c", "PENDING"),
        ])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(hard_identity_conflicts(conflicts), [])

    def test_generation_label_alias_is_no_name_conflict(self):
        # Production 2026-11-16: "EPIX PRO" / "epix Pro 51mm" results assigned
        # to epix Pro (Gen 2) were counted as name conflicts.
        epix = {**self.device, "id": "garmin-epix-pro-gen-2-51", "model": "epix Pro (Gen 2)", "case_size_mm": 51}
        for raw in ("EPIX PRO", "epix Pro 51mm"):
            self.assertEqual(selected_identity_conflicts({"rawMTPModel": raw}, epix, []), [], raw)
        self.assertEqual([c["field"] for c in selected_identity_conflicts(
            {"rawMTPModel": "fenix 8"}, epix, [])], ["model"])

    def test_assessment_marks_a_rejected_candidate_as_conflict(self):
        devices = [{**self.device}, {**self.device, "id": "watch-b"}]
        assessment = assess_identity(self.event, devices, [
            mapping("XML_PART_NUMBER", "006-B0001-00", "watch-a", "REJECTED")])
        by_id = {c["deviceId"]: c for c in assessment["candidates"]}
        self.assertTrue(by_id["watch-a"]["conflict"])
        self.assertFalse(by_id["watch-b"]["conflict"])
        self.assertEqual(assessment["canonicalDeviceId"], "watch-b")

    def test_indistinguishable_variants_need_a_shared_reviewed_code(self):
        devices = [{**self.device, "screen_technology": "AMOLED"},
                   {**self.device, "id": "watch-b", "screen_technology": "MicroLED"}]
        shared = [mapping("XML_PART_NUMBER", "006-B0001-00", "watch-a", "APPROVED"),
                  mapping("XML_PART_NUMBER", "006-B0001-00", "watch-b", "APPROVED")]
        assessment = assess_identity(self.event, devices, shared)
        self.assertIsNone(assessment["canonicalDeviceId"])
        self.assertEqual(indistinguishable_candidates(assessment), ["watch-a", "watch-b"])
        # Without a reviewed code, or with an incomplete review, Identity review decides.
        self.assertEqual(indistinguishable_candidates(assess_identity({"rawMTPModel": "Testwatch"}, devices, shared)), [])
        pending = [mapping("XML_PART_NUMBER", "006-B0001-00", "watch-a", "PENDING"), shared[1]]
        self.assertEqual(indistinguishable_candidates(assess_identity(self.event, devices, pending)), [])
        # Different model names are never "the same watch".
        other = [{**devices[0]}, {**devices[1], "model": "Testwatch Pro"}]
        self.assertEqual(indistinguishable_candidates(assess_identity(
            {"rawMTPModel": "Testwatch", "garminModelPartNumber": "006-B0001-00"}, other, shared)), [])


class CodeProtectionPostgresTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.admin = self.sql(
            "INSERT INTO admin_user (username, password_hash) VALUES ('code-admin', 'x') RETURNING id")[0]["id"]

    def result(self, *, part_number, raw, device=None, usb=None):
        event_id = self.rows.diagnostic(
            canonical_device_model_id=device, identity_resolution_state="RESOLVED" if device else "UNRESOLVED",
            model=raw, compatibility_identity=raw, raw_mtp_model=raw, garmin_model_description=raw,
            garmin_model_part_number=part_number)
        vendor, product = usb or (2334, 1)  # an unmapped USB code
        self.sql("UPDATE compatibility_evidence_event SET operation_id = NULL, usb_vendor_id = %s, usb_product_id = %s"
                 " WHERE event_id = %s", (vendor, product, event_id))
        return event_id

    def resolve(self, event_id, action, device, note=None):
        return self.db.resolve_compatibility_identity(
            f"legacy:{event_id}", action=action, canonical_device_model_id=device,
            admin_user_id=self.admin, note=note)

    def assigned(self, event_id):
        return self.sql("SELECT canonical_device_model_id FROM compatibility_evidence_event WHERE event_id = %s",
                        (event_id,))[0]["canonical_device_model_id"]

    # A -----------------------------------------------------------------
    def test_code_conflict_refuses_assign_and_manual_assign(self):
        # B4375 = fēnix 7 Pro (Wi-Fi) in Garmin's list; REJECTED for the no-Wi-Fi row (086).
        seven_pro_solar = self.result(part_number="006-B4375-00", raw="fenix 7 Pro Solar")
        # B3910 = fēnix 7X (Solar); APPROVED for 7X 51 mm and quatix 7X Solar, not for 7X Pro.
        seven_x_solar = self.result(part_number="006-B3910-00", raw="fenix 7X Solar")
        for event_id, wrong in ((seven_pro_solar, SEVEN_PRO_NO_WIFI), (seven_x_solar, SEVEN_X_PRO)):
            for action in ("ASSIGN", "MANUAL_ASSIGN"):
                with self.subTest(event=event_id, action=action), self.assertRaises(IdentityResolutionError) as error:
                    self.resolve(event_id, action, wrong, note="I am sure")
                self.assertEqual(error.exception.code, "identity_code_conflict")
                self.assertTrue(error.exception.details["conflicts"])
            self.assertIsNone(self.assigned(event_id))
        self.assertEqual(self.resolve(seven_pro_solar, "ASSIGN", SEVEN_PRO), 1)
        self.assertEqual(self.resolve(seven_x_solar, "ASSIGN", SEVEN_X_51), 1)

    def test_manual_assignment_against_reported_facts_needs_a_reason(self):
        event_id = self.result(part_number=None, raw="fenix 7 Pro Solar")
        with self.assertRaises(IdentityResolutionError) as error:
            self.resolve(event_id, "ASSIGN", SEVEN_X_51)
        self.assertEqual(error.exception.code, "identity_conflict_manual_required")
        with self.assertRaises(IdentityResolutionError) as error:
            self.resolve(event_id, "MANUAL_ASSIGN", SEVEN_X_51)
        self.assertEqual(error.exception.code, "identity_manual_reason_required")
        self.assertEqual(self.resolve(event_id, "MANUAL_ASSIGN", SEVEN_X_51, note="Seen on the watch"), 1)
        self.assertEqual(self.assigned(event_id), SEVEN_X_51)

    def test_web_result_refuses_a_usb_code_conflict(self):
        self.sql("INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, status)"
                 " VALUES ('USB', '091e:abcd', %s, 'https://example.org', 'test', 'APPROVED')", (SEVEN_PRO,))
        event_id = self.rows.uuid()
        self.sql(
            "INSERT INTO web_installer_event (event_id, session_id, occurred_at, received_at, stage, outcome,"
            " operation, write_started, model, usb_vendor_id, usb_product_id, is_test)"
            " VALUES (%s, %s, now(), now(), 'MAP_RESULT', 'SUCCEEDED', 'install', TRUE, 'fenix 7 Pro',"
            " 2334, 43981, FALSE)", (event_id, self.rows.uuid()))
        with self.assertRaises(IdentityResolutionError) as error:
            self.db.resolve_web_installer_identity(event_id, action="MANUAL_ASSIGN",
                                                   canonical_device_model_id=SEVEN_PRO_NO_WIFI,
                                                   admin_user_id=self.admin, note="Sure")
        self.assertEqual(error.exception.code, "identity_code_conflict")
        self.assertEqual(self.db.resolve_web_installer_identity(
            event_id, action="ASSIGN", canonical_device_model_id=SEVEN_PRO, admin_user_id=self.admin), 1)

    # B -----------------------------------------------------------------
    def test_identity_form_names_the_models_the_code_allows(self):
        devices = self.sql(IDENTITY_DEVICE_QUERY)
        mappings = self.sql(IDENTITY_MAPPING_QUERY)
        assessment = assess_identity({"rawMTPModel": "fenix 7 Pro Solar", "garminModelPartNumber": "006-B4375-00"},
                                     devices, mappings)
        result = {"event_id": "e1", "canonical_device_model_id": None, "current_identity_assessment": assessment}
        allowed, rejected = _identity_code_scope([result])
        self.assertEqual(allowed, {SEVEN_PRO})
        self.assertIn(SEVEN_PRO_NO_WIFI, rejected)
        form = _identity_review_form("legacy:e1", [result], csrf_token="t", identity_devices=devices,
                                     return_to="/admin", id_suffix="x")
        self.assertIn(f"data-identity-code-models='{SEVEN_PRO}'", form)
        self.assertIn(f"data-identity-code-rejected='{SEVEN_PRO_NO_WIFI}'", form)
        # A preselected code conflict hides the manual action.
        conflicted = {**result, "canonical_device_model_id": SEVEN_PRO_NO_WIFI}
        form = _identity_review_form("legacy:e1", [conflicted], csrf_token="t", identity_devices=devices,
                                     return_to="/admin", id_suffix="y")
        self.assertIn("Choose the model this code names.", form)
        self.assertRegex(form, r"value='MANUAL_ASSIGN' class='secondary-button' data-manual-confirm hidden")

    # C -----------------------------------------------------------------
    def test_contradicted_assignments_are_counted_until_corrected(self):
        self.assertEqual(self.db.identity_assignment_conflicts(), [])
        wrong = self.result(part_number="006-B4375-00", raw="fenix 7 Pro Solar", device=SEVEN_PRO_NO_WIFI)
        self.result(part_number="006-B4375-00", raw="fenix 7 Pro Solar", device=SEVEN_PRO)
        [finding] = self.db.identity_assignment_conflicts()
        self.assertEqual((finding["eventId"], finding["hard"], finding["fields"]),
                         (wrong, True, ["XML_PART_NUMBER"]))
        report = _identity_conflicts(self.db, "https://api.example/admin")
        self.assertEqual(report["total"], 1)
        self.assertTrue(report["items"][0]["adminUrl"].endswith("/admin/review/identity#identity-conflicts"))
        page = identity_review_page([], {"username": "a", "csrf_token": "t"}, "t",
                                    conflicts=self.db.identity_assignment_conflicts()).decode()
        self.assertIn("id='identity-conflicts'", page)
        self.assertEqual(page.count("data-identity-conflict-row"), 1)
        self.sql("UPDATE compatibility_evidence_event SET canonical_device_model_id = %s WHERE event_id = %s",
                 (SEVEN_PRO, wrong))
        self.assertEqual(self.db.identity_assignment_conflicts(), [])
        self.assertNotIn("id='identity-conflicts'", identity_review_page(
            [], {"username": "a", "csrf_token": "t"}, "t", conflicts=[]).decode())

    def test_incomplete_code_review_is_not_counted(self):
        # Production 2026-11-16: a USB code APPROVED for one fēnix 8 51 mm row
        # with another target still PENDING is no fact yet, so the other row's
        # assignments are not conflicts.
        for device, status in ((SEVEN_PRO, "APPROVED"), (SEVEN_PRO_NO_WIFI, "PENDING")):
            self.sql("INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version,"
                     " status) VALUES ('USB', '091e:abcd', %s, 'https://example.org', 'test', %s)", (device, status))
        self.result(part_number=None, raw="fenix 7 Pro Solar", device=SEVEN_PRO_NO_WIFI, usb=(2334, 43981))
        self.assertEqual(self.db.identity_assignment_conflicts(), [])
        self.sql("UPDATE device_identity_mapping SET status = 'REJECTED' WHERE value = '091e:abcd'"
                 " AND device_model_id = %s", (SEVEN_PRO_NO_WIFI,))
        [finding] = self.db.identity_assignment_conflicts()
        self.assertEqual((finding["hard"], finding["fields"]), (True, ["USB"]))

    def test_manual_reason_confirms_soft_facts_but_never_a_code(self):
        soft = self.result(part_number=None, raw="fenix 7 Pro Solar")
        self.resolve(soft, "MANUAL_ASSIGN", SEVEN_X_51, note="Seen on the watch")
        self.assertEqual(self.db.identity_assignment_conflicts(), [])
        # Without a reason (a decision made before 2026-11-16) it is listed.
        self.sql("UPDATE compatibility_identity_resolution_audit SET note = NULL WHERE event_id = %s", (soft,))
        [finding] = self.db.identity_assignment_conflicts()
        self.assertFalse(finding["hard"])

    # D -----------------------------------------------------------------
    def test_a_code_link_that_results_contradict_cannot_be_approved(self):
        link = self.sql(
            "INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version)"
            " VALUES ('XML_PART_NUMBER', '006-B9999-00', %s, 'https://example.org', 'test') RETURNING id",
            (SEVEN_X_51,))[0]["id"]
        self.result(part_number="006-B9999-00", raw="fenix 7 Pro")
        with self.assertRaises(IdentityResolutionError) as error:
            self.db.review_identity_mapping(link, "APPROVED", "Source names it", self.admin)
        self.assertEqual(error.exception.code, "identity_mapping_report_conflict")
        self.assertEqual(error.exception.details["total"], 1)
        # A linked model that fits the result lets the shared code be approved.
        self.sql("INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version)"
                 " VALUES ('XML_PART_NUMBER', '006-B9999-00', %s, 'https://example.org', 'test')", (SEVEN_PRO,))
        self.assertTrue(self.db.review_identity_mapping(link, "APPROVED", "Source names it", self.admin))
        # Rejecting is always possible.
        self.assertTrue(self.db.review_identity_mapping(link, "REJECTED", "Wrong", self.admin))

    # Variant unknown -----------------------------------------------------
    def test_indistinguishable_variants_become_variant_unknown(self):
        for device_id, screen in (("test-pro-51-amoled", "AMOLED"), ("test-pro-51-microled", "MicroLED")):
            self.sql(
                """INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                       case_size_mm, product_url, source_url, screen_technology, solar, inreach)
                   VALUES (%s, 'garmin-fenix', 'Garmin', 'Testwatch 8 Pro', 'testwatch 8 pro', %s, 51,
                       'https://example.org/p', 'https://example.org/p', %s, FALSE, TRUE)""",
                (device_id, f"51 mm, {screen}", screen))
            self.sql("INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, status)"
                     " VALUES ('XML_PART_NUMBER', '006-B8888-00', %s, 'https://example.org', 'test', 'APPROVED')",
                     (device_id,))
        unknown = self.result(part_number="006-B8888-00", raw="Testwatch 8 Pro - 51mm")
        no_code = self.result(part_number=None, raw="Testwatch 8 Pro - 51mm")
        self.assertEqual(self.db.auto_resolve_pending_identities(apply=False)["notIdentifiable"], 1)
        summary = self.db.auto_resolve_pending_identities()
        self.assertEqual((summary["notIdentifiable"], summary["resolvedResults"]), (1, 0))
        state = self.sql("SELECT canonical_device_model_id, identity_resolution_state FROM compatibility_evidence_event"
                         " WHERE event_id = %s", (unknown,))[0]
        self.assertEqual(state, {"canonical_device_model_id": None, "identity_resolution_state": "NOT_IDENTIFIABLE"})
        [audit] = self.sql("SELECT action, assessment FROM compatibility_identity_resolution_audit WHERE event_id = %s",
                           (unknown,))
        assessment = audit["assessment"] if isinstance(audit["assessment"], dict) else json.loads(audit["assessment"])
        self.assertEqual((audit["action"], assessment["decision"]["candidates"]),
                         ("NOT_IDENTIFIABLE", ["test-pro-51-amoled", "test-pro-51-microled"]))
        # Without the shared code it still waits for Identity review.
        self.assertEqual(self.sql("SELECT identity_resolution_state FROM compatibility_evidence_event WHERE event_id = %s",
                                  (no_code,))[0]["identity_resolution_state"], "UNRESOLVED")
        self.assertEqual(self.db.auto_resolve_pending_identities()["notIdentifiable"], 0)

    # Migration 094 -------------------------------------------------------
    def test_forerunner_955_and_955_solar_share_one_row_and_code(self):
        [row] = self.sql("SELECT variant, solar, map_capable FROM device_model WHERE id = %s", (FR955,))
        self.assertEqual((row["variant"], row["solar"], row["map_capable"]), ("Historical", None, True))
        links = {r["device_model_id"]: r["status"] for r in self.sql(
            "SELECT device_model_id, status FROM device_identity_mapping WHERE value = '006-B4024-00'")}
        self.assertEqual(links, {FR955: "APPROVED", FR955_DUAL_POWER: "APPROVED"})
        audited = self.sql("SELECT count(*) AS n FROM device_identity_mapping_audit a JOIN device_identity_mapping m"
                           " ON m.id = a.mapping_id WHERE m.value = '006-B4024-00' AND a.new_status = 'APPROVED'")
        self.assertEqual(audited[0]["n"], 2)
        devices, mappings = self.sql(IDENTITY_DEVICE_QUERY), self.sql(IDENTITY_MAPPING_QUERY)
        for raw in ("Forerunner 955 Solar", "Forerunner 955"):
            with self.subTest(raw=raw):
                assessment = assess_identity({"rawMTPModel": raw, "garminModelDescription": raw,
                                              "garminModelPartNumber": "006-B4024-00",
                                              "usbVendorID": 0x091E, "usbProductID": 0x4FB8}, devices, mappings)
                self.assertEqual(assessment["canonicalDeviceId"], FR955)
        dual = assess_identity({"rawMTPModel": "Forerunner 955 Dual Power", "garminModelPartNumber": "006-B4024-00"},
                               devices, mappings)
        self.assertEqual(dual["canonicalDeviceId"], FR955_DUAL_POWER)

    def test_migration_094_is_data_only_and_keeps_decisions(self):
        code = "\n".join(line for line in MIGRATION_094.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("--")).upper()
        for forbidden in ("DROP ", "ALTER ", "DELETE ", "COMPATIBILITY_EVIDENCE_EVENT", "WEB_INSTALLER"):
            self.assertNotIn(forbidden, code)
        self.assertIn("M.STATUS = 'PENDING'", code)
        self.assertIn("AND VARIANT = 'STANDARD'", code)

    # E -----------------------------------------------------------------
    def test_every_approved_code_link_names_its_model(self):
        devices, mappings = self.sql(IDENTITY_DEVICE_QUERY), self.sql(IDENTITY_MAPPING_QUERY)
        by_id = {device["id"]: device for device in devices}
        groups: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for link in mappings:
            groups[(link["kind"], link["value"])][link["status"]].add(link["device_model_id"])
        self.assertTrue(groups)
        for (kind, value), status in groups.items():
            approved = status["APPROVED"]
            self.assertFalse(approved & status["REJECTED"], (kind, value))
            for device_id in approved:
                device = by_id[device_id]
                event = {"rawMTPModel": device["model"]}
                if kind == "USB":
                    vendor, product = value.split(":")
                    event.update(usbVendorID=int(vendor, 16), usbProductID=int(product, 16))
                else:
                    event["garminModelPartNumber"] = value
                with self.subTest(kind=kind, value=value, device=device_id):
                    assessment = assess_identity(event, devices, mappings)
                    self.assertTrue(any(c["deviceId"] == device_id and not c["conflict"]
                                        for c in assessment["candidates"]))
                    same_name = [i for i in approved if model_label(by_id[i]["model"]) == model_label(device["model"])]
                    if len(same_name) == 1 and not (status["PENDING"] - approved):
                        self.assertEqual(assessment["canonicalDeviceId"], device_id)
                    self.assertEqual(hard_identity_conflicts(selected_identity_conflicts(event, device, mappings)), [])


if __name__ == "__main__":
    unittest.main()

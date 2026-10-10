"""Admin identity and diagnostic reviews are idempotent and fully audited (audit pack B)."""
import json
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.github_issue_sync import apply_closed_issue

OTHER_DEVICE = "garmin-d2-delta"


class AdminReviewIdempotencyTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.admin = self.sql(
            "INSERT INTO admin_user (username, password_hash) VALUES ('pack-b', 'x') RETURNING id"
        )[0]["id"]

    def identity_audits(self, event_id):
        return self.sql(
            "SELECT action, new_canonical_device_model_id, assessment"
            " FROM compatibility_identity_resolution_audit WHERE event_id = %s ORDER BY id",
            (event_id,),
        )

    def lifecycle_audits(self, event_id):
        return self.sql(
            "SELECT previous_status, new_status, linked_github_issue,"
            " previous_workflow_status, new_workflow_status"
            " FROM compatibility_diagnostic_lifecycle_audit WHERE event_id = %s ORDER BY id",
            (event_id,),
        )

    def resolve(self, event_id, action, device=None):
        return self.db.resolve_compatibility_identity(
            f"legacy:{event_id}", action=action, canonical_device_model_id=device,
            admin_user_id=self.admin,
        )

    def legacy_diagnostic(self, **overrides):
        event_id = self.rows.uuid()
        self.rows.diagnostic(event_id=event_id, **overrides)
        self.sql("UPDATE compatibility_evidence_event SET operation_id = NULL WHERE event_id = %s", (event_id,))
        return event_id

    def test_identical_identity_retry_after_correction_keeps_one_decision(self):
        event_id = self.legacy_diagnostic(
            canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
        )
        self.assertEqual(self.resolve(event_id, "MANUAL_ASSIGN", FENIX_8), 1)
        self.assertEqual(self.resolve(event_id, "MANUAL_ASSIGN", OTHER_DEVICE), 1)
        self.assertEqual(self.resolve(event_id, "MANUAL_ASSIGN", OTHER_DEVICE), 1)  # double submit
        audits = self.identity_audits(event_id)
        self.assertEqual([row["new_canonical_device_model_id"] for row in audits], [FENIX_8, OTHER_DEVICE])
        assessment = audits[-1]["assessment"]
        assessment = json.loads(assessment) if isinstance(assessment, str) else assessment
        self.assertEqual(assessment["decision"]["deviceId"], OTHER_DEVICE)

    def test_unresolved_and_not_identifiable_retries_add_no_second_audit(self):
        event_id = self.legacy_diagnostic(
            canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
        )
        for action in ("LEAVE_UNRESOLVED", "LEAVE_UNRESOLVED", "NOT_IDENTIFIABLE", "NOT_IDENTIFIABLE"):
            self.assertEqual(self.resolve(event_id, action), 1)
        self.assertEqual(
            [row["action"] for row in self.identity_audits(event_id)],
            ["LEAVE_UNRESOLVED", "NOT_IDENTIFIABLE"],
        )

    def test_issue_relink_and_resolved_link_are_audited_but_identical_link_is_not(self):
        active = self.legacy_diagnostic(phase_outcome="FAILED", linked_github_issue="#5")
        self.sql("UPDATE compatibility_evidence_event SET diagnostic_workflow_status = 'IN_PROGRESS'"
                 " WHERE event_id = %s", (active,))
        self.db.update_diagnostic_issue(f"legacy:{active}", linked_github_issue="#7", admin_user_id=self.admin)
        self.db.update_diagnostic_issue(f"legacy:{active}", linked_github_issue="7", admin_user_id=self.admin)
        self.assertEqual(
            [(row["linked_github_issue"], row["previous_workflow_status"], row["new_workflow_status"])
             for row in self.lifecycle_audits(active)],
            [("#7", "IN_PROGRESS", "IN_PROGRESS")],
        )
        resolved = self.legacy_diagnostic(phase_outcome="FAILED", diagnostic_status="RESOLVED")
        self.db.update_diagnostic_issue(f"legacy:{resolved}", linked_github_issue="#9", admin_user_id=self.admin)
        self.db.update_diagnostic_issue(f"legacy:{resolved}", linked_github_issue=None, admin_user_id=self.admin)
        self.assertEqual(
            [(row["new_status"], row["linked_github_issue"]) for row in self.lifecycle_audits(resolved)],
            [("RESOLVED", "#9"), ("RESOLVED", None)],
        )

    def test_workflow_change_on_resolved_diagnostic_is_rejected(self):
        resolved = self.legacy_diagnostic(phase_outcome="FAILED", diagnostic_status="RESOLVED")
        with self.assertRaises(ValueError):
            self.db.update_diagnostic_workflow(
                f"legacy:{resolved}", workflow_status="UNDER_REVIEW", admin_user_id=self.admin,
            )
        self.assertEqual(self.lifecycle_audits(resolved), [])

    def test_github_close_audits_the_real_previous_workflow(self):
        event_id = self.legacy_diagnostic(phase_outcome="FAILED", linked_github_issue="#94")
        self.sql("UPDATE compatibility_evidence_event SET diagnostic_workflow_status = 'UNDER_REVIEW'"
                 " WHERE event_id = %s", (event_id,))
        with self.db.connection() as connection:
            self.assertEqual(apply_closed_issue(connection, 94, "completed"), 1)
        audit = self.lifecycle_audits(event_id)[-1]
        self.assertEqual((audit["previous_workflow_status"], audit["new_workflow_status"]), ("UNDER_REVIEW", "OPEN"))

    def test_publish_does_not_collide_with_a_legacy_review_row_using_the_same_model_key(self):
        self.sql(
            "INSERT INTO compatibility_model_review (model, identity_key, review_status, public_display_name)"
            " VALUES ('fēnix 8', 'fēnix 8 · 47 mm AMOLED', 'APPROVED', 'fēnix 8 · 47 mm AMOLED')"
        )
        self.rows.diagnostic(compatibility_identity="fēnix 8", canonical_device_model_id=OTHER_DEVICE)
        self.assertTrue(self.db.update_public_compatibility_review(OTHER_DEVICE, action="PUBLISH", admin_user_id=self.admin))
        self.assertTrue(self.db.update_public_compatibility_review(OTHER_DEVICE, action="UNPUBLISH", admin_user_id=self.admin))
        reviews = {row["identity_key"]: row for row in self.sql(
            "SELECT model, identity_key, review_status FROM compatibility_model_review")}
        self.assertEqual(reviews["fēnix 8 · 47 mm AMOLED"]["model"], "fēnix 8")
        self.assertEqual(reviews["fēnix 8 · 47 mm AMOLED"]["review_status"], "APPROVED")
        self.assertEqual(reviews["fēnix 8"]["review_status"], "PENDING")
        self.assertEqual(len(self.sql(
            "SELECT 1 FROM public_compatibility_review_audit WHERE device_model_id = %s", (OTHER_DEVICE,))), 2)


if __name__ == "__main__":
    unittest.main()

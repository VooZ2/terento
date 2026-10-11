"""Waiting identities that resolve to one catalog model are assigned and audited."""
import json
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows

WATCH_47 = "test-watch-9-47"
WATCH_51 = "test-watch-9-51"


class IdentityAutoResolutionTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        for device_id, size in ((WATCH_47, 47), (WATCH_51, 51)):
            self.sql(
                """INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                       case_size_mm, product_url, source_url, screen_technology, solar, inreach)
                   VALUES (%s, 'garmin-fenix', 'Garmin', 'Testwatch 9', 'testwatch 9', %s, %s,
                       'https://example.org/p', 'https://example.org/p', 'AMOLED', FALSE, FALSE)""",
                (device_id, f"{size} mm", size),
            )

    def pending(self, **overrides):
        values = dict(canonical_device_model_id=None, identity_resolution_state="UNRESOLVED",
                      model="Testwatch 9", compatibility_identity="Testwatch 9", raw_mtp_model="Testwatch 9 - 47mm")
        values.update(overrides)
        event_id = self.rows.diagnostic(**values)
        # The fixture's USB code has a reviewed mapping to another watch.
        self.sql("UPDATE compatibility_evidence_event SET usb_product_id = 1 WHERE event_id = %s", (event_id,))
        return event_id

    def stored(self, event_id):
        return self.sql(
            "SELECT canonical_device_model_id, identity_resolution_state, identity_assessment"
            " FROM compatibility_evidence_event WHERE event_id = %s", (event_id,),
        )[0]

    def audits(self, event_id):
        return self.sql(
            "SELECT action, new_canonical_device_model_id, new_identity, corrected_by, reason, assessment"
            " FROM compatibility_identity_resolution_audit WHERE event_id = %s ORDER BY id", (event_id,),
        )

    def test_dry_run_counts_without_writing(self):
        single = self.pending()
        self.pending(raw_mtp_model="Testwatch 9")
        summary = self.db.auto_resolve_pending_identities(apply=False)
        self.assertEqual(summary, {"pendingResults": 2, "resolvedResults": 1, "exact": 0, "singleMatch": 1,
                                   "pendingOperations": 2, "clearedOperations": 1})
        self.assertIsNone(self.stored(single)["canonical_device_model_id"])
        self.assertEqual(self.audits(single), [])

    def test_single_match_is_assigned_with_an_automatic_audit(self):
        single = self.pending()
        ambiguous = self.pending(raw_mtp_model="Testwatch 9")
        summary = self.db.auto_resolve_pending_identities()
        self.assertEqual((summary["resolvedResults"], summary["clearedOperations"]), (1, 1))
        row = self.stored(single)
        self.assertEqual((row["canonical_device_model_id"], row["identity_resolution_state"]), (WATCH_47, "RESOLVED"))
        # The intake assessment stays as received.
        self.assertEqual(row["identity_assessment"], {"state": "RESOLVED"})
        [audit] = self.audits(single)
        self.assertEqual((audit["action"], audit["new_canonical_device_model_id"], audit["new_identity"],
                          audit["corrected_by"]), ("ASSIGN", WATCH_47, "Testwatch 9 · 47 mm", None))
        assessment = audit["assessment"]
        assessment = json.loads(assessment) if isinstance(assessment, str) else assessment
        self.assertEqual(assessment["resolution"], "SINGLE_MATCH")
        self.assertEqual(assessment["decision"]["method"], "AUTOMATIC")
        self.assertIsNone(self.stored(ambiguous)["canonical_device_model_id"])
        self.assertEqual(self.audits(ambiguous), [])
        # A second pass finds nothing new to assign.
        self.assertEqual(self.db.auto_resolve_pending_identities()["resolvedResults"], 0)

    def test_earlier_decision_and_out_of_queue_rows_are_left_alone(self):
        decided = self.pending(operation_id=None)
        self.sql("UPDATE compatibility_evidence_event SET operation_id = NULL WHERE event_id = %s", (decided,))
        self.db.resolve_compatibility_identity(f"legacy:{decided}", action="LEAVE_UNRESOLVED",
                                               canonical_device_model_id=None, admin_user_id=None)
        local = self.pending(is_local_test=True)
        resolved_lifecycle = self.pending(diagnostic_status="RESOLVED")
        download = self.pending(phase_outcome="FAILED", write_started=False, failure_stage="download")
        summary = self.db.auto_resolve_pending_identities()
        self.assertEqual((summary["pendingOperations"], summary["resolvedResults"], summary["clearedOperations"]),
                         (1, 0, 0))
        for event_id in (decided, local, resolved_lifecycle, download):
            self.assertIsNone(self.stored(event_id)["canonical_device_model_id"])
        self.assertEqual([row["action"] for row in self.audits(decided)], ["LEAVE_UNRESOLVED"])

    def test_multi_map_operation_clears_only_when_every_result_resolves(self):
        operation = self.rows.uuid()
        self.pending(operation_id=operation, map_result_index=0, selected_map_count=2)
        self.pending(operation_id=operation, map_result_index=1, selected_map_count=2, raw_mtp_model="Testwatch 9")
        summary = self.db.auto_resolve_pending_identities(apply=False)
        self.assertEqual((summary["pendingOperations"], summary["resolvedResults"], summary["clearedOperations"]),
                         (1, 1, 0))


if __name__ == "__main__":
    unittest.main()

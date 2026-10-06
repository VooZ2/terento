"""Migration 069: reported map identity and evidence schema version (audit M6/M9)."""
import json
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows
from terento_catalog.admin import _result_classification
from terento_catalog.compatibility_evidence import validate_event
from terento_catalog.map_events import validate_map_event
from test_compatibility_evidence import event as legacy_event


class ReportedMapIdTests(PGliteTestCase):
    def map_event(self, map_id, event_id):
        return validate_map_event(json.dumps({
            "schemaVersion": 1, "id": event_id, "operationId": "3f2a1b0c-4d5e-4f60-8a7b-9c0d1e2f3a4b",
            "timestamp": "2026-10-01T12:00:00Z", "providerId": "freizeitkarte", "releaseLabel": "1.0.0-beta.18",
            "mapId": map_id, "region": "AUT", "eventType": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED",
            "mapResultIndex": 0, "appBuild": "40",
        }).encode())

    def popular_package_ids(self):
        return {row["map_package_id"] for row in self.db.map_statistics({})
                if row["event_type"] == "INSTALL_SUCCEEDED" and row["operation_count"]}

    def test_unknown_map_is_retained_and_attributed_when_published(self):
        self.assertTrue(self.db.insert_map_event(self.map_event("freizeitkarte-aut", "8d1c3a52-9e4b-4f0a-b7c1-2d5e6f708192")))
        stored = self.sql("SELECT map_package_id, reported_map_id FROM map_download_event")[0]
        self.assertEqual(stored, {"map_package_id": None, "reported_map_id": "freizeitkarte-aut"})
        self.assertEqual(self.popular_package_ids(), {None})
        StatisticsRows(self.server).package("freizeitkarte-aut", region="AUT", country="AT")
        self.assertEqual(self.popular_package_ids(), {"freizeitkarte-aut"})
        self.assertEqual(len(self.db.map_statistics({"map": "freizeitkarte-aut"})), 1)

    def test_known_map_keeps_the_foreign_key_and_no_reported_copy(self):
        StatisticsRows(self.server).package("freizeitkarte-aut", region="AUT", country="AT")
        self.db.insert_map_event(self.map_event("freizeitkarte-aut", "8d1c3a52-9e4b-4f0a-b7c1-2d5e6f708193"))
        stored = self.sql("SELECT map_package_id, reported_map_id FROM map_download_event")[0]
        self.assertEqual(stored, {"map_package_id": "freizeitkarte-aut", "reported_map_id": None})


class SchemaVersionLegacyRuleTests(PGliteTestCase):
    def counts(self):
        rows = self.sql("SELECT sum(attempted_install_count)::int AS attempts, sum(failed_install_count)::int AS failed"
                        " FROM compatibility_model_statistics")
        return rows[0]["attempts"] or 0, rows[0]["failed"] or 0

    def test_stored_v2_failure_with_app_build_keeps_its_legacy_interpretation(self):
        body = legacy_event(schemaVersion=2, phaseOutcome="FAILED", automaticFinishingResult="FAILED",
                            appBuild="12", releaseLabel="1.0.0-beta.4")
        self.assertTrue(self.db.insert_compatibility_event(validate_event(json.dumps(body).encode())))
        self.assertEqual(self.sql("SELECT schema_version FROM compatibility_evidence_event")[0]["schema_version"], 2)
        self.assertEqual(self.counts(), (1, 1))

    def test_rows_without_a_stored_version_keep_the_existing_rule(self):
        rows = StatisticsRows(self.server)
        rows.diagnostic(phase_outcome="FAILED", write_started=None, app_build="12", release_label="1.0.0-beta.4")
        self.assertEqual(self.counts(), (0, 0))
        rows.diagnostic(phase_outcome="FAILED", write_started=None, app_build=None, release_label=None)
        self.assertEqual(self.counts(), (1, 1))

    def test_current_schema_never_uses_the_legacy_allowance(self):
        rows = StatisticsRows(self.server)
        rows.diagnostic(phase_outcome="FAILED", write_started=None, schema_version=4, app_build=None, release_label=None)
        self.assertEqual(self.counts(), (0, 0))


class PythonTwinLegacyRuleTests(unittest.TestCase):
    def test_python_classifier_matches_the_sql_function(self):
        base = {"phase_outcome": "FAILED", "automatic_finishing_result": "FAILED", "write_started": None}
        self.assertEqual(_result_classification({**base, "schema_version": 2, "app_build": "12"}), "FAILURE")
        self.assertEqual(_result_classification({**base, "schema_version": 4}), "UNKNOWN")
        self.assertEqual(_result_classification({**base, "app_build": "12"}), "UNKNOWN")
        self.assertEqual(_result_classification(base), "FAILURE")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import unittest

from terento_catalog.admin import test_data_page
from terento_catalog.db import Database, is_local_test_release_label
from terento_catalog.map_events import validate_map_event


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "src" / "terento_catalog" / "migrations" / "035_local_test_telemetry.sql"


class RecordingResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class RecordingDatabase(Database):
    def __init__(self, row):
        super().__init__("unused")
        self.row = row
        self.calls = []

    @contextmanager
    def connection(self):
        database = self

        class Connection:
            def execute(self, query, parameters=None):
                database.calls.append((query, parameters))
                if "SELECT" in query and "compatibility_event_count" in query:
                    return RecordingResult(row=database.row)
                return RecordingResult(row=None)

        yield Connection()


class LocalTestTelemetryTests(unittest.TestCase):
    def test_only_explicit_semver_local_labels_are_classified(self):
        self.assertTrue(is_local_test_release_label("1.0.0-beta.10-local"))
        self.assertTrue(is_local_test_release_label("1.0.0-local"))
        for value in (None, "", "1.0.0-beta.10", "v1.0.0-local", "1.0.0-local-build", "1.0.0--local", "file:///tmp/build"):
            self.assertFalse(is_local_test_release_label(value))

    def test_map_event_accepts_optional_release_label(self):
        event = validate_map_event(b'''{
            "schemaVersion": 1,
            "id": "39409c53-ca0c-4ebc-bf8a-4356bef3aad1",
            "operationId": "ff493127-cd29-4e69-87f2-07c15c7e9453",
            "timestamp": "2026-09-06T12:00:00+00:00",
            "providerId": "freizeitkarte",
            "mapId": "fzk-ltu",
            "region": "LTU",
            "eventType": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED",
            "appBuild": "12",
            "releaseLabel": "1.0.0-beta.10-local"
        }''')
        self.assertEqual(event["releaseLabel"], "1.0.0-beta.10-local")

    def test_snapshot_exposes_classified_events_only(self):
        database = RecordingDatabase({
            "compatibility_event_count": 2,
            "map_event_count": 3,
            "operation_count": 1,
            "last_occurred_at": datetime(2026, 9, 6, tzinfo=timezone.utc),
        })
        snapshot = database.local_test_telemetry_snapshot()
        self.assertEqual(snapshot["compatibilityEventCount"], 2)
        self.assertEqual(snapshot["mapEventCount"], 3)
        self.assertEqual(snapshot["operationCount"], 1)
        self.assertIn("is_local_test IS TRUE", database.calls[0][0])

    def test_purge_sql_is_scoped_and_audited(self):
        database = RecordingDatabase({
            "compatibility_event_count": 0,
            "map_event_count": 0,
            "operation_count": 0,
            "last_occurred_at": None,
        })
        result = database.delete_local_test_telemetry(admin_user_id=7, request_id="req-1")
        self.assertEqual(result["eventCount"], 0)
        query_text = "\n".join(query for query, _ in database.calls)
        self.assertIn("DELETE FROM map_download_event", query_text)
        self.assertIn("DELETE FROM compatibility_evidence_event", query_text)
        self.assertIn("WHERE is_local_test IS TRUE", query_text)
        self.assertIn("telemetry.local_test_data_deleted", [
            parameter
            for _, parameters in database.calls
            for parameter in (parameters or ())
            if isinstance(parameter, str)
        ])

    def test_admin_page_explains_and_confirms_local_only_purge(self):
        body = test_data_page(
            {
                "compatibilityEventCount": 2,
                "mapEventCount": 3,
                "operationCount": 1,
                "lastOccurredAt": None,
            },
            {"username": "operator"},
            "csrf-token",
        ).decode()
        self.assertIn("Local test data", body)
        self.assertIn("ending in <code>-local</code>", body)
        self.assertIn("/admin/test-data/delete", body)
        self.assertIn("data-confirm=", body)

    def test_migration_adds_classification_and_excludes_local_rows_from_aggregate(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN is_local_test BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("ADD COLUMN release_label TEXT", sql)
        self.assertIn("UPDATE map_download_event AS m", sql)
        self.assertIn("AND e.is_local_test IS NOT TRUE", sql)
        self.assertIn("WHERE is_local_test IS TRUE", sql)
        self.assertIn("DROP VIEW compatibility_model_statistics", sql)


if __name__ == "__main__":
    unittest.main()

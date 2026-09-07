from __future__ import annotations

from contextlib import contextmanager
import unittest

from terento_catalog.db import Database


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.row if isinstance(self.row, list) else []


class Connection:
    def __init__(self):
        self.queries: list[tuple[str, object]] = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if "array_agg" in query:
            if "compatibility_evidence_event" in query:
                return Result({"event_count": 2, "operation_count": 1, "labels": ["1.0.0-beta.10-local"]})
            return Result({"event_count": 3, "operation_count": 1, "labels": ["1.0.0-beta.10-local"]})
        if "local_operations" in query and "count(DISTINCT operation_id)" not in query:
            return Result({"operation_count": 1})
        if "count(DISTINCT operation_id)" in query:
            return Result({"operation_count": 4})
        if "DELETE FROM compatibility_evidence_event" in query:
            return Result({"event_count": 6})
        if "DELETE FROM map_download_event" in query:
            return Result({"event_count": 8})
        return Result({})


class LocalTelemetryDatabase(Database):
    def __init__(self, connection):
        super().__init__("unused")
        self._test_connection = connection

    @contextmanager
    def connection(self):
        yield self._test_connection


class LocalTelemetryTests(unittest.TestCase):
    def test_summary_is_local_only(self):
        connection = Connection()
        database = LocalTelemetryDatabase(connection)
        self.assertEqual(
            database.local_test_telemetry_summary(),
            {
                "diagnosticEventCount": 2,
                "mapEventCount": 3,
                "operationCount": 1,
                "releaseLabels": ["1.0.0-beta.10-local"],
                "activity": [],
            },
        )
        self.assertTrue(all("is_local_test IS TRUE" in query for query, _ in connection.queries))

    def test_purge_is_transactional_and_cannot_target_production_rows(self):
        connection = Connection()
        database = LocalTelemetryDatabase(connection)
        result = database.purge_local_test_telemetry(
            admin_user_id=7,
            request_id="local-test-1",
        )
        self.assertEqual(
            result,
            {"diagnosticEventCount": 6, "mapEventCount": 8, "operationCount": 4},
        )
        delete_queries = [query for query, _ in connection.queries if query.lstrip().startswith("WITH deleted")]
        self.assertEqual(len(delete_queries), 2)
        self.assertTrue(all("WHERE is_local_test IS TRUE" in query for query in delete_queries))
        audit = next((params for query, params in connection.queries if "INSERT INTO admin_audit_log" in query), None)
        self.assertIsNotNone(audit)
        self.assertEqual(audit[1], "telemetry.local_test_purged")
        self.assertEqual(audit[7], "local-test-1")


if __name__ == "__main__":
    unittest.main()

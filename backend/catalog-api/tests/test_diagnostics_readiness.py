from contextlib import contextmanager
import unittest
from terento_catalog.db import Database, migration_directory


class ReadinessDatabase(Database):
    def __init__(self, nullable="YES", missing=False):
        super().__init__("unused")
        self.nullable, self.missing, self.queries = nullable, missing, []

    @contextmanager
    def connection(self):
        owner = self
        class Result:
            def fetchall(self):
                return [] if owner.missing else [
                    {"version": p.name.split("_", 1)[0]}
                    for p in migration_directory().glob("[0-9]*.sql")]
            def fetchone(self):
                return {"is_nullable": owner.nullable}
        class Connection:
            def execute(self, query):
                owner.queries.append(query)
                return Result()
        yield Connection()


class DiagnosticsReadinessTests(unittest.TestCase):
    def test_legacy_not_null_constraint_is_not_ready(self):
        with self.assertRaisesRegex(RuntimeError, "schema v4"):
            ReadinessDatabase(nullable="NO").health()

    def test_missing_migration_is_not_ready(self):
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            ReadinessDatabase(missing=True).health()

    def test_both_streams_are_checked_without_test_writes(self):
        db = ReadinessDatabase()
        self.assertTrue(db.health())
        sql = " ".join(db.queries).upper()
        self.assertIn("FROM MAP_DOWNLOAD_EVENT WHERE FALSE", sql)
        self.assertIn("FROM COMPATIBILITY_EVIDENCE_EVENT WHERE FALSE", sql)
        for keyword in ("INSERT ", "UPDATE ", "DELETE ", "ALTER "):
            self.assertNotIn(keyword, sql)

    def test_schema_v4_migration_preserves_legacy_rows(self):
        sql = (migration_directory() / "033_diagnostics_schema_v4.sql").read_text().upper()
        self.assertIn("ALTER COLUMN DELETION_TOKEN_HASH DROP NOT NULL", sql)
        self.assertNotIn("DELETE FROM", sql)
        self.assertNotIn("DROP TABLE", sql)

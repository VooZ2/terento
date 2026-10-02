"""Focused generic forward-migration and ledger-prefix tests."""

from __future__ import annotations

from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path

from terento_catalog.db import migration_directory
from terento_catalog.migrate import apply_migrations, validate_migration_versions


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class TransactionalDatabase:
    def __init__(self, ledger, fail_on=None):
        self.ledger = None if ledger is None else list(ledger)
        self.fail_on = fail_on
        self.ddl = []
        self.statements = []
        self.outcome = None

    @contextmanager
    def connection(self):
        pending_ledger = None if self.ledger is None else list(self.ledger)
        pending_ddl = list(self.ddl)

        class Connection:
            def execute(_, sql, params=None):
                nonlocal pending_ledger
                self.statements.append(sql)
                if self.fail_on and self.fail_on in sql:
                    raise RuntimeError("injected statement failure")
                if "CREATE TABLE IF NOT EXISTS schema_migrations" in sql:
                    if pending_ledger is None:
                        pending_ledger = []
                elif sql.startswith("SELECT version FROM schema_migrations"):
                    if pending_ledger is None:
                        raise RuntimeError("schema_migrations does not exist")
                    return Rows([{"version": version} for version in pending_ledger])
                elif sql.startswith("INSERT INTO schema_migrations"):
                    pending_ledger.append(params[0])
                elif "LOCK TABLE schema_migrations" not in sql:
                    pending_ddl.append(sql)
                return Rows([])

        try:
            yield Connection()
        except BaseException:
            self.outcome = "ROLLBACK"
            raise
        else:
            self.ledger = pending_ledger
            self.ddl = pending_ddl
            self.outcome = "COMMIT"


def ledger_through(version):
    return [f"{number:03d}" for number in range(1, version + 1)]


class GenericMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for version in range(1, 64):
            (self.directory / f"{version:03d}_migration.sql").write_text(
                "SELECT 'migration';", encoding="utf-8"
            )

    def test_repository_inventory_is_canonical(self):
        validate_migration_versions(list(migration_directory().glob("*.sql")))

    def test_062_to_063_applies_one_pending_file_transactionally(self):
        database = TransactionalDatabase(ledger_through(62))
        self.assertEqual(apply_migrations(database, self.directory), ["063"])
        self.assertEqual(database.ledger, ledger_through(63))
        self.assertEqual(database.outcome, "COMMIT")

    def test_063_to_065_applies_two_pending_files_in_order(self):
        for version in (64, 65):
            (self.directory / f"{version:03d}_migration.sql").write_text("SELECT 'migration';")
        database = TransactionalDatabase(ledger_through(63))
        self.assertEqual(apply_migrations(database, self.directory), ["064", "065"])
        self.assertEqual(database.ledger, ledger_through(65))

    def test_equal_inventory_is_noop(self):
        database = TransactionalDatabase(ledger_through(63))
        self.assertEqual(apply_migrations(database, self.directory), [])

    def test_ledger_gap_or_ahead_fails_before_sql(self):
        for ledger in (ledger_through(60) + ["062"], ledger_through(63) + ["064"], ["1"]):
            with self.subTest(ledger=ledger):
                database = TransactionalDatabase(ledger)
                with self.assertRaisesRegex(RuntimeError, "exact canonical prefix"):
                    apply_migrations(database, self.directory)
                self.assertEqual(database.ddl, [])
                self.assertEqual(database.outcome, "ROLLBACK")

    def test_candidate_gap_alias_and_malformed_name_fail_before_database_access(self):
        cases = (
            lambda: (self.directory / "061_migration.sql").unlink(),
            lambda: (self.directory / "063_migration.sql").rename(self.directory / "63_migration.sql"),
            lambda: (self.directory / "063_migration.sql").rename(self.directory / "063 bad.sql"),
        )
        for change in cases:
            with self.subTest(change=change):
                database = TransactionalDatabase(ledger_through(62))
                original = {path.name: path.read_bytes() for path in self.directory.glob("*.sql")}
                change()
                try:
                    with self.assertRaises(RuntimeError):
                        apply_migrations(database, self.directory)
                    self.assertIsNone(database.outcome)
                finally:
                    for path in self.directory.glob("*.sql"):
                        path.unlink()
                    for name, content in original.items():
                        (self.directory / name).write_bytes(content)

    def test_sql_and_ledger_are_one_transaction(self):
        database = TransactionalDatabase(ledger_through(62), fail_on="INSERT INTO schema_migrations")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            apply_migrations(database, self.directory)
        self.assertEqual(database.ledger, ledger_through(62))
        self.assertEqual(database.ddl, [])
        self.assertEqual(database.outcome, "ROLLBACK")


if __name__ == "__main__":
    unittest.main()

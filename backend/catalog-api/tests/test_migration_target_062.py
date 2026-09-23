"""Focused, offline transaction and precondition tests for --target 062."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from terento_catalog.migrate import apply_migrations, main
from terento_catalog.db import migration_directory


BASE_LEDGER = {f"{version:03d}" for version in range(1, 62)}


class Rows:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, str]]:
        return self.rows


class TransactionalDatabase:
    """Records SQL and commits only on normal context exit, like psycopg."""

    def __init__(self, ledger: set[str] | None, fail_on: str | None = None) -> None:
        self.ledger = None if ledger is None else set(ledger)
        self.applied_ddl: list[str] = []
        self.fail_on = fail_on
        self.connection_count = 0
        self.outcome: str | None = None
        self.statements: list[str] = []

    @contextmanager
    def connection(self):
        self.connection_count += 1
        pending_ledger = None if self.ledger is None else set(self.ledger)
        pending_ddl = list(self.applied_ddl)

        class Connection:
            def execute(_, sql: str, params: tuple[str] | None = None):
                nonlocal pending_ledger
                self.statements.append(sql)
                if self.fail_on and self.fail_on in sql:
                    raise RuntimeError("injected statement failure")
                if sql.startswith("LOCK TABLE schema_migrations"):
                    if pending_ledger is None:
                        raise RuntimeError("schema_migrations does not exist")
                elif sql.startswith("SELECT version FROM schema_migrations"):
                    if pending_ledger is None:
                        raise RuntimeError("schema_migrations does not exist")
                    return Rows([{"version": version} for version in pending_ledger])
                elif sql.startswith("INSERT INTO schema_migrations"):
                    assert params is not None and pending_ledger is not None
                    pending_ledger.add(params[0])
                elif "CREATE TABLE IF NOT EXISTS schema_migrations" in sql:
                    pending_ledger = pending_ledger or set()
                else:
                    pending_ddl.append(sql)
                return Rows([])

        try:
            yield Connection()
        except BaseException:
            self.outcome = "ROLLBACK"
            raise
        else:
            self.ledger = pending_ledger
            self.applied_ddl = pending_ddl
            self.outcome = "COMMIT"


class Target062MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for version in range(1, 63):
            sql = "SELECT 'older migration';" if version < 62 else (
                "CREATE TABLE target_marker (id integer); CREATE INDEX target_marker_idx "
                "ON target_marker(id);"
            )
            (self.directory / f"{version:03d}_migration.sql").write_text(sql, encoding="utf-8")

    def test_exact_061_to_062_executes_only_062_in_one_transaction(self) -> None:
        database = TransactionalDatabase(BASE_LEDGER)

        self.assertEqual(apply_migrations(database, self.directory, target="062"), ["062"])

        self.assertEqual(database.ledger, BASE_LEDGER | {"062"})
        self.assertEqual(database.connection_count, 1)
        self.assertEqual(database.outcome, "COMMIT")
        self.assertEqual(len(database.applied_ddl), 2)
        self.assertTrue(database.applied_ddl[0].startswith("CREATE TABLE target_marker"))
        self.assertTrue(database.applied_ddl[1].startswith("CREATE INDEX target_marker_idx"))
        self.assertEqual(sum("INSERT INTO schema_migrations" in sql for sql in database.statements), 1)
        self.assertFalse(any("older migration" in sql for sql in database.statements))
        self.assertFalse(any("CREATE TABLE IF NOT EXISTS schema_migrations" in sql
                             for sql in database.statements))
        self.assertFalse(any("systemctl" in sql or "docker" in sql for sql in database.statements))

    def test_repository_source_runs_only_062(self) -> None:
        database = TransactionalDatabase(BASE_LEDGER)
        self.assertEqual(apply_migrations(database, migration_directory(), target="062"), ["062"])
        self.assertEqual(len(database.applied_ddl), 7)
        self.assertFalse(any("older migration" in sql for sql in database.statements))

    def test_already_062_is_no_op(self) -> None:
        database = TransactionalDatabase(BASE_LEDGER | {"062"})
        self.assertEqual(apply_migrations(database, self.directory, target="062"), [])
        self.assertEqual(database.outcome, "COMMIT")
        self.assertEqual(database.applied_ddl, [])
        self.assertEqual(len(database.statements), 2)  # ledger lock and read only

    def test_rejects_noncanonical_or_incomplete_ledger_without_ddl(self) -> None:
        bad_ledgers = (
            BASE_LEDGER - {"061"},  # only through 060
            BASE_LEDGER - {"034"},  # history hole
            BASE_LEDGER | {"063"},  # unexpected later version
            (BASE_LEDGER - {"001"}) | {"1"},  # numeric alias
            BASE_LEDGER | {"062", "063"},
        )
        for ledger in bad_ledgers:
            with self.subTest(ledger=ledger):
                database = TransactionalDatabase(ledger)
                with self.assertRaisesRegex(RuntimeError, "exact applied ledger"):
                    apply_migrations(database, self.directory, target="062")
                self.assertEqual(database.ledger, ledger)
                self.assertEqual(database.applied_ddl, [])
                self.assertEqual(database.outcome, "ROLLBACK")

    def test_missing_ledger_is_not_created(self) -> None:
        database = TransactionalDatabase(None)
        with self.assertRaisesRegex(RuntimeError, "does not exist"):
            apply_migrations(database, self.directory, target="062")
        self.assertIsNone(database.ledger)
        self.assertFalse(any("CREATE TABLE" in sql for sql in database.statements))

    def test_rejects_source_holes_aliases_and_063_before_db_access(self) -> None:
        cases = (
            ("hole", lambda: (self.directory / "061_migration.sql").unlink()),
            ("alias", lambda: (self.directory / "062_migration.sql").rename(
                self.directory / "62_migration.sql")),
            ("later", lambda: (self.directory / "063_migration.sql").write_text("SELECT 1;")),
        )
        for name, change in cases:
            with self.subTest(name=name):
                original = {path.name: path.read_bytes() for path in self.directory.glob("*.sql")}
                try:
                    change()
                    database = TransactionalDatabase(BASE_LEDGER)
                    with self.assertRaisesRegex(RuntimeError, "canonical migration file"):
                        apply_migrations(database, self.directory, target="062")
                    self.assertEqual(database.connection_count, 0)
                finally:
                    for path in self.directory.glob("*.sql"):
                        path.unlink()
                    for filename, content in original.items():
                        (self.directory / filename).write_bytes(content)

    def test_rejects_unsupported_target_before_db_access(self) -> None:
        database = TransactionalDatabase(BASE_LEDGER)
        for target in ("060", "62", "063", "062 "):
            with self.subTest(target=target), self.assertRaisesRegex(RuntimeError, "exact --target 062"):
                apply_migrations(database, self.directory, target=target)
        self.assertEqual(database.connection_count, 0)

        with patch("terento_catalog.migrate.Settings.from_env") as settings:
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                main(["--target", "060"])
            self.assertEqual(error.exception.code, 2)
            settings.assert_not_called()

    def test_untargeted_runner_preserves_existing_apply_all_behavior(self) -> None:
        database = TransactionalDatabase(set())
        self.assertEqual(
            apply_migrations(database, self.directory),
            [f"{version:03d}" for version in range(1, 63)],
        )
        self.assertEqual(database.ledger, BASE_LEDGER | {"062"})
        self.assertEqual(database.connection_count, 1)

    def test_sql_or_ledger_failure_rolls_back_ddl_and_version_together(self) -> None:
        for failure in ("CREATE INDEX target_marker_idx", "INSERT INTO schema_migrations"):
            with self.subTest(failure=failure):
                database = TransactionalDatabase(BASE_LEDGER, fail_on=failure)
                with self.assertRaisesRegex(RuntimeError, "injected statement failure"):
                    apply_migrations(database, self.directory, target="062")
                self.assertEqual(database.ledger, BASE_LEDGER)
                self.assertEqual(database.applied_ddl, [])
                self.assertEqual(database.connection_count, 1)
                self.assertEqual(database.outcome, "ROLLBACK")


if __name__ == "__main__":
    unittest.main()

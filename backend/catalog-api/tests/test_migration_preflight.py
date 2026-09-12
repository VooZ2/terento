import tempfile
import unittest
from pathlib import Path
from terento_catalog.migrate import apply_migrations, validate_migration_versions
from terento_catalog.db import migration_directory

class MigrationPreflightTests(unittest.TestCase):
    def test_repository_versions_are_unique(self):
        validate_migration_versions(list(migration_directory().glob("*.sql")))

    def test_duplicate_fails_before_database_access(self):
        class ForbiddenDatabase:
            def connection(self):
                raise AssertionError("duplicate migration reached the database")
        for names in [("044_first.sql", "044_second.sql"), ("044_first.sql", "44_second.sql")]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                for name in names:
                    (Path(directory) / name).write_text("SELECT 1;")
                with self.assertRaisesRegex(RuntimeError, "duplicate migration version"):
                    apply_migrations(ForbiddenDatabase(), Path(directory))

    def test_bad_filename_fails_preflight(self):
        with self.assertRaisesRegex(RuntimeError, "filename"):
            validate_migration_versions([Path("not-numbered.sql")])

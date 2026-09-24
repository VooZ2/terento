"""Non-DB guardrails for the additive 061 reconciliation.

These tests do not assert that production has the other 060 objects. Their
presence and types require a separate SELECT-only pre-deploy schema audit.
"""

import hashlib
from pathlib import Path
import unittest

from terento_catalog.migrate import _statements


MIGRATIONS = Path(__file__).parents[1] / "src" / "terento_catalog" / "migrations"
PROVENANCE = Path(__file__).parents[1] / "docs" / "migration-source-provenance"


class ReconciliationMigrationTests(unittest.TestCase):
    def test_canonical_060_061_versions_are_unique_and_untracked_candidates_are_archived(self):
        names = {path.name for path in MIGRATIONS.glob("*.sql")}
        self.assertIn("060_missing_diagnostic_review_tasks.sql", names)
        self.assertIn("061_indexnow_operational_observations.sql", names)
        self.assertIn("062_reconcile_installation_statistics_schema.sql", names)
        self.assertEqual(len([name for name in names if name.startswith("060_")]), 1)
        self.assertEqual(
            len([name for name in names if name.startswith("061_")]), 1
        )
        self.assertTrue((PROVENANCE / "060_installation_authorization_statistics_exclusions.sql.txt").is_file())
        self.assertTrue((PROVENANCE / "061_reconcile_installation_statistics_schema.sql.txt").is_file())

    def test_archived_060_and_061_source_bytes_match_the_reviewed_origin(self):
        expected = {
            "060_installation_authorization_statistics_exclusions.sql.txt":
                "efe9bd6cb802ffa521704ac2ddd0e384a67bb032c6222ff59c5f78f79da86963",
            "061_reconcile_installation_statistics_schema.sql.txt":
                "e382e24cb8176a7359b66c12a73c9039e8af7cbc01d7ff5a20f298ae2b68f8a1",
        }
        for filename, sha256 in expected.items():
            with self.subTest(filename=filename):
                source = (PROVENANCE / filename).read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(), sha256)

    def test_archived_061_reconciliation_source_is_additive_and_non_destructive(self):
        sql = (PROVENANCE / "061_reconcile_installation_statistics_schema.sql.txt").read_text(
            encoding="utf-8"
        )
        statements = _statements(sql)
        self.assertEqual(len(statements), 3)
        self.assertIn("ADD COLUMN IF NOT EXISTS map_result_index INTEGER", statements[0])
        self.assertIn("CREATE TABLE IF NOT EXISTS statistics_exclusion_audit", statements[1])
        self.assertIn("UNIQUE (stream, event_id, exclusion_code)", statements[1])
        self.assertIn("CREATE INDEX IF NOT EXISTS statistics_exclusion_audit_event_idx", statements[2])
        for forbidden in ("UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "INSERT ", "CREATE OR REPLACE VIEW"):
            self.assertNotIn(forbidden, "\n".join(
                line for line in sql.splitlines() if not line.lstrip().startswith("--")
            ).upper())


if __name__ == "__main__":
    unittest.main()

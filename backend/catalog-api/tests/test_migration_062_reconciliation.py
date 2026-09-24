"""Regression coverage for the additive 062 live-schema reconciliation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest

from terento_catalog.migrate import _statements


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "src" / "terento_catalog" / "migrations"
PROVENANCE = ROOT / "docs" / "migration-source-provenance"
MIGRATION_056 = MIGRATIONS / "056_statistics_semantics.sql"
MIGRATION_060_SOURCE = PROVENANCE / "060_installation_authorization_statistics_exclusions.sql.txt"
MIGRATION_061_SOURCE = PROVENANCE / "061_reconcile_installation_statistics_schema.sql.txt"
MIGRATION_062 = MIGRATIONS / "062_reconcile_installation_statistics_schema.sql"


def view_statement(path: Path) -> str:
    statement = next(
        statement
        for statement in _statements(path.read_text(encoding="utf-8"))
        if "CREATE OR REPLACE VIEW COMPATIBILITY_MODEL_STATISTICS" in statement.upper()
    )
    start = statement.upper().index("CREATE OR REPLACE VIEW COMPATIBILITY_MODEL_STATISTICS")
    return statement[start:]


def projection_columns(statement: str) -> list[str]:
    projection = statement.split("\nSELECT\n", 1)[1].split("\nFROM event_stats e", 1)[0]
    expressions: list[str] = []
    current: list[str] = []
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(projection):
        char = projection[index]
        if char == "'":
            if in_single_quote and index + 1 < len(projection) and projection[index + 1] == "'":
                current.extend((char, projection[index + 1]))
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif not in_single_quote and char == "(":
            depth += 1
        elif not in_single_quote and char == ")":
            depth -= 1
        if char == "," and not in_single_quote and depth == 0:
            expressions.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    if current:
        expressions.append("".join(current).strip())

    names: list[str] = []
    for expression in expressions:
        explicit_alias = expression.rsplit(" AS ", 1)
        if len(explicit_alias) == 2:
            names.append(explicit_alias[1].strip())
        else:
            names.append(expression.rsplit(".", 1)[-1].strip())
    return names


class Migration062ReconciliationTests(unittest.TestCase):
    def test_062_is_the_single_new_additive_version_and_leaves_060_061_untouched(self) -> None:
        names = {path.name for path in MIGRATIONS.glob("*.sql")}
        self.assertIn(MIGRATION_062.name, names)
        self.assertEqual(len([name for name in names if name.startswith("062_")]), 1)
        self.assertIn("060_missing_diagnostic_review_tasks.sql", names)
        self.assertIn("061_indexnow_operational_observations.sql", names)
        self.assertTrue(MIGRATION_060_SOURCE.is_file())
        self.assertTrue(MIGRATION_061_SOURCE.is_file())

        sql = MIGRATION_062.read_text(encoding="utf-8")
        self.assertIn("do not replay or rewrite them", sql)
        self.assertIn("map_result_index", sql)
        self.assertNotIn("UPDATE map_download_event", sql.upper())

    def test_062_is_additive_idempotent_and_does_not_rewrite_event_rows(self) -> None:
        sql = MIGRATION_062.read_text(encoding="utf-8")
        statements = _statements(sql)
        self.assertEqual(len(statements), 7)
        statements = [
            "\n".join(line for line in statement.splitlines() if not line.lstrip().startswith("--")).strip()
            for statement in statements
        ]
        self.assertIn("ADD COLUMN IF NOT EXISTS statistics_exclusion_code TEXT", statements[0])
        self.assertIn("ADD COLUMN IF NOT EXISTS map_result_index INTEGER", statements[1])
        self.assertIn("CREATE TABLE IF NOT EXISTS statistics_exclusion_audit", statements[2])
        self.assertIn("CREATE INDEX IF NOT EXISTS compatibility_statistics_exclusion_idx", statements[3])
        self.assertIn("CREATE INDEX IF NOT EXISTS map_statistics_exclusion_idx", statements[4])
        self.assertIn("CREATE INDEX IF NOT EXISTS statistics_exclusion_audit_event_idx", statements[5])
        self.assertTrue(statements[6].startswith("CREATE OR REPLACE VIEW"))

        executable_sql = "\n".join(
            line for line in sql.splitlines() if not line.lstrip().startswith("--")
        ).upper()
        for forbidden in ("UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "INSERT "):
            self.assertNotIn(forbidden, executable_sql)
        self.assertNotIn("DEFAULT 0", executable_sql)
        self.assertIn("PRIMARY KEY", statements[2].upper())
        self.assertIn("UNIQUE (STREAM, EVENT_ID, EXCLUSION_CODE)", statements[2].upper())

    def test_062_replacement_view_matches_archived_reconciliation_definition(self) -> None:
        # This exact statement includes the established 29-column projection,
        # result-index grouping, local-test exclusion, and exclusion predicates.
        self.assertEqual(view_statement(MIGRATION_062), view_statement(MIGRATION_060_SOURCE))

        # The audited live view used the same legacy result-index/local-test
        # projection as 056. Confirm the replacement retains every output alias
        # and order; PostgreSQL integration below additionally compares types.
        old_columns = projection_columns(view_statement(MIGRATION_056))
        new_columns = projection_columns(view_statement(MIGRATION_062))
        self.assertEqual(old_columns, new_columns)
        self.assertEqual(len(new_columns), 29)

    @unittest.skipUnless(
        os.environ.get("TERENTO_PGLITE_MODULE"),
        "Set TERENTO_PGLITE_MODULE for isolated PostgreSQL migration execution",
    )
    def test_clean_live_like_and_reconciled_postgresql_paths(self) -> None:
        payload = {
            "legacyView": view_statement(MIGRATION_056),
            "migration062": _statements(MIGRATION_062.read_text(encoding="utf-8")),
            "precheck": (ROOT / "tools" / "installation-statistics-062-live-precheck.sql").read_text(encoding="utf-8"),
            "postcheck": (ROOT / "tools" / "installation-statistics-062-live-postcheck.sql").read_text(encoding="utf-8"),
        }
        script = Path(__file__).with_name("migration_062_postgres.cjs")
        result = subprocess.run(
            ["node", str(script), os.environ["TERENTO_PGLITE_MODULE"]],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        outcome = json.loads(result.stdout)
        self.assertEqual(outcome["cleanMigration"], "PASS")
        self.assertEqual(outcome["liveLikeRepair"], "PASS")
        self.assertEqual(outcome["alreadyReconciled"], "PASS")
        self.assertEqual(outcome["historicalMapIndex"], "NULL")
        self.assertEqual(outcome["viewColumns"], 29)
        self.assertEqual(
            [(column["column_name"], column["data_type"]) for column in outcome["viewContract"]],
            [
                ("compatibility_identity", "text"),
                ("model", "text"),
                ("variant", "text"),
                ("case_size_mm", "integer"),
                ("display_type", "text"),
                ("canonical_device_model_id", "text"),
                ("firmware_versions", "text"),
                ("attempted_install_count", "bigint"),
                ("successful_install_count", "bigint"),
                ("reconnect_verified_install_count", "bigint"),
                ("failed_install_count", "bigint"),
                ("firmware_version_count", "bigint"),
                ("success_rate", "numeric"),
                ("last_success", "timestamp with time zone"),
                ("last_failure", "timestamp with time zone"),
                ("last_evidence", "timestamp with time zone"),
                ("map_result_count", "numeric"),
                ("successful_map_result_count", "numeric"),
                ("failed_map_result_count", "numeric"),
                ("not_started_map_result_count", "numeric"),
                ("prewrite_failure_count", "bigint"),
                ("error_categories", "jsonb"),
                ("calculated_status", "text"),
                ("recognized_map_capable_evidence", "boolean"),
                ("physical_device_evidence_count", "integer"),
                ("review_notes", "text"),
                ("review_status", "text"),
                ("public_statistics_enabled", "boolean"),
                ("public_display_name", "text"),
            ],
        )


if __name__ == "__main__":
    unittest.main()

"""Contract for the PostgreSQL/WASM regression harness itself."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from pglite_support import PGliteTestCase, convert_query, require_pglite


class RequirePgliteTests(unittest.TestCase):
    def test_missing_module_skips_locally_and_fails_in_ci(self):
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"PGLITE_MODULE_PATH", "TERENTO_PGLITE_MODULE", "CI"}}
        probe = unittest.TestCase()
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(unittest.SkipTest):
                require_pglite(probe)
            os.environ["CI"] = "true"
            with self.assertRaises(AssertionError) as raised:
                require_pglite(probe)
        self.assertIn("must not be skipped", str(raised.exception))

    def test_psycopg_placeholders_are_translated_exactly(self):
        self.assertEqual(convert_query("SELECT %s, %s, '5%%'", (1, 2)), ("SELECT $1, $2, '5%'", [1, 2]))
        self.assertEqual(
            convert_query("SELECT %(a)s, %(b)s, %(a)s", {"a": "x", "b": None}),
            ("SELECT $1, $2, $1", ["x", None]),
        )
        self.assertEqual(convert_query("SELECT 'a%%'", None), ("SELECT 'a%%'", []))


class MigratedSchemaTests(PGliteTestCase):
    def test_every_migration_applies_and_types_round_trip(self):
        row = self.sql(
            "SELECT now() AS at, 1.5::numeric AS n, '00000000-0000-4000-8000-000000000001'::uuid AS id,"
            " count(*) AS c FROM schema_migrations"
        )[0]
        self.assertIsInstance(row["at"], datetime)
        self.assertEqual(row["at"].tzinfo, timezone.utc)
        self.assertIsInstance(row["id"], UUID)
        self.assertEqual(str(row["n"]), "1.5")
        self.assertGreaterEqual(row["c"], 0)
        providers = {item["id"] for item in self.sql("SELECT id FROM map_provider")}
        self.assertTrue({"freizeitkarte", "opentopomap", "maprando", "bbbike"} <= providers)

    def test_each_test_is_rolled_back(self):
        self.sql("CREATE TABLE harness_probe (id integer)")
        self.assertIsNotNone(self.sql("SELECT to_regclass('harness_probe') AS name")[0]["name"])

    def test_rollback_isolation_holds(self):
        self.assertIsNone(self.sql("SELECT to_regclass('harness_probe') AS name")[0]["name"])


if __name__ == "__main__":
    unittest.main()

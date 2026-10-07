"""Maps page cost guards on the real migrated PostgreSQL schema.

``/admin/map-statistics`` (and its JSON) reads the full-history map statistics
model several times per request under ``enable_nestloop = off``. A date-scoped
linkage lookup, or a provider filter that leaves a clauseless join, can only
run as a nested loop, so the planner adds its disable cost and the estimate
crosses ``jit_above_cost``. On production PostgreSQL that spent seconds in
LLVM compilation for queries that execute in milliseconds. Every Maps read
whose estimate crosses the threshold must therefore run with JIT disabled.
"""
import json
import unittest

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.http_api import CatalogService

# PostgreSQL's default jit_above_cost.
JIT_ABOVE_COST = 100000
SETTINGS = ("SET LOCAL enable_nestloop = off", "SET LOCAL jit = off")


def _plan_nodes(node):
    yield node
    for child in node.get("Plans", []):
        yield from _plan_nodes(child)


class MapsQueryCostTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.service = CatalogService(self.db)
        self.rows.package("fzk-deu", region="DEU")
        self.rows.package("fzk-aut", region="AUT", country="AT")
        batch = self.rows.uuid()
        for index, package in enumerate(("fzk-deu", "fzk-aut")):
            region = "DEU" if package == "fzk-deu" else "AUT"
            acquisition = self.rows.uuid()
            self.rows.map_event(operation_id=batch, map_package_id=package, region=region,
                                event_type="DOWNLOAD_SUCCEEDED", acquisition_id=acquisition,
                                component_kind="main", map_result_index=None, acquisition_purpose="install")
            self.rows.map_event(operation_id=batch, map_package_id=package, region=region, map_result_index=index)
            self.rows.diagnostic(operation_id=batch, map_result_index=index, selected_map_count=2, region=region)
        failed = self.rows.uuid()
        self.rows.map_event(operation_id=failed, map_package_id="fzk-deu", event_type="INSTALL_FAILED",
                            outcome="FAILED")
        self.rows.diagnostic(operation_id=failed, phase_outcome="FAILED", failure_stage="write",
                             failure_code="INSTALL_FAILED_WRITE")
        legacy = self.rows.uuid()
        self.rows.map_event(operation_id=legacy, map_package_id="fzk-aut", region="AUT", map_result_index=None)
        self.rows.diagnostic(operation_id=legacy, region="AUT", canonical_device_model_id=FENIX_8)

    def capture(self, read):
        """Return [(settings, sql, params)] for each statement, scoped per connection."""
        statements = []
        scope = []
        original_exec, original_query = self.server.exec, self.server.query

        def exec_(sql):
            if sql.startswith("SAVEPOINT"):
                scope.clear()
            return original_exec(sql)

        def query(sql, params=None):
            text = " ".join(sql.split())
            if text in SETTINGS:
                scope.append(text)
            else:
                statements.append((tuple(scope), sql, params))
            return original_query(sql, params)

        self.server.exec, self.server.query = exec_, query
        try:
            read()
        finally:
            self.server.exec, self.server.query = original_exec, original_query
        return statements

    def estimated_cost(self, settings, sql, params):
        """Return (total cost, disabled plan nodes) under the statement's settings.

        PGlite runs PostgreSQL 18, which marks a plan node the settings forbid
        as ``Disabled`` instead of adding ``disable_cost`` (1e10) to its
        estimate as production PostgreSQL 16 does. Each disabled node is
        therefore a certain JIT trigger in production.
        """
        with self.db.connection() as connection:
            for setting in settings:
                connection.execute(setting)
            result = connection.execute("EXPLAIN (FORMAT JSON) " + sql, params).fetchone()
        plan = next(iter(result.values()))
        plan = json.loads(plan) if isinstance(plan, str) else plan
        top = plan[0]["Plan"]
        nodes = list(_plan_nodes(top))
        return float(top["Total Cost"]), sum(1 for n in nodes if n.get("Disabled"))

    def assert_expensive_reads_skip_jit(self, filters):
        statements = self.capture(lambda: self.service.map_statistics(filters))
        expensive = 0
        for settings, sql, params in statements:
            # Measure the plan as PostgreSQL would see it without the JIT guard.
            cost, disabled = self.estimated_cost(tuple(s for s in settings if "jit" not in s), sql, params)
            if cost >= JIT_ABOVE_COST or disabled:
                expensive += 1
                self.assertIn("SET LOCAL jit = off", settings, " ".join(sql.split())[:80])
        return statements, expensive

    def test_date_scoped_maps_reads_run_without_jit(self):
        statements, expensive = self.assert_expensive_reads_skip_jit({"period": "24h", "timeZone": "UTC"})
        # The date-scoped linkage lookup needs a nested loop even on this tiny
        # history (a JIT trigger in production); the guard must be exercised.
        self.assertGreaterEqual(expensive, 1)
        # population, all-time, linkage and trend: a fixed number of reads,
        # each evaluated with JIT disabled.
        self.assertEqual(len(statements), 4, [" ".join(s[1].split())[:60] for s in statements])
        self.assertTrue(all("SET LOCAL jit = off" in settings for settings, _, _ in statements))

    def test_provider_filtered_maps_reads_run_without_jit(self):
        statements, expensive = self.assert_expensive_reads_skip_jit(
            {"period": "30d", "timeZone": "UTC", "provider": "freizeitkarte", "outcome": "FAILED"}
        )
        self.assertGreaterEqual(expensive, 1)
        # population, all-time, detail (outcome filter), linkage and trend.
        self.assertEqual(len(statements), 5)

    def test_all_time_maps_reuses_population_rows(self):
        statements, _ = self.assert_expensive_reads_skip_jit({"period": "all", "timeZone": "UTC"})
        self.assertEqual(len(statements), 3)


if __name__ == "__main__":
    unittest.main()

"""Behavior of Database queries that used to be checked only by source text.

Each test runs the production SQL on migrated PostgreSQL (PGlite) and checks
the stored or returned rows.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows
from terento_catalog.provider_catalog import (
    OPENTOPO_MAP,
    CatalogArtifact,
    CatalogPackage,
    ProviderSnapshot,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
TEST_PROVIDER = replace(OPENTOPO_MAP, id="query-test", name="Query test provider", adapter_id="query-test")


def artifact(artifact_id: str, *, status: str = "VALIDATED", url: str | None = None) -> CatalogArtifact:
    return CatalogArtifact(
        id=artifact_id, kind="main",
        source_url=url or f"https://example.org/{artifact_id}.zip",
        size_bytes=100, install_size_bytes=200, checksum_sha256=None,
        content_type="application/zip", required=True, validation_status=status,
    )


def package(package_id: str, *, release: str = "2026-10", availability: str = "AVAILABLE",
            artifacts: tuple[CatalogArtifact, ...] = (), provider_id: str = TEST_PROVIDER.id) -> CatalogPackage:
    return CatalogPackage(
        id=package_id, provider_id=provider_id, provider_region_id=package_id,
        canonical_region_id=package_id, name=package_id, region=package_id, country="LT",
        release=release, release_id=None, version_label=None, generated_at=None,
        source_updated_at=None, availability=availability, country_codes=("LT",),
        region_kind="country", tags=(), capabilities=(), artifacts=artifacts,
    )


class ProviderRowsTests(PGliteTestCase):
    def test_counts_only_live_packages_and_distinct_problem_sources(self):
        self.db.ensure_provider_definition(TEST_PROVIDER)
        shared_broken = "https://example.org/shared-broken.zip"
        self.db.upsert_provider_snapshot(ProviderSnapshot(TEST_PROVIDER, (
            package("ok", artifacts=(artifact("ok-main"),)),
            package("broken-a", release="2026-11", artifacts=(artifact("a-main", status="FAILED", url=shared_broken),)),
            package("broken-b", artifacts=(artifact("b-main", status="UNAVAILABLE", url=shared_broken),)),
            package("withheld", availability="WITHHELD", artifacts=(artifact("w-main", status="FAILED"),)),
        ), NOW))
        # A retired package with a failed source must not count anywhere.
        self.sql("""INSERT INTO map_package (id, provider_id, provider_region_id, canonical_region_id,
                        name, region, release, availability)
                    VALUES ('retired', %s, 'retired', 'retired', 'retired', 'retired', '2027-01', 'RETIRED')""",
                 (TEST_PROVIDER.id,))
        self.sql("""INSERT INTO map_artifact (id, package_id, kind, source_url, size_bytes, validation_status)
                    VALUES ('retired-main', 'retired', 'main', 'https://example.org/retired.zip', 1, 'FAILED')""")

        row = next(item for item in self.db.provider_rows() if item["provider_id"] == TEST_PROVIDER.id)
        self.assertEqual(row["active_package_count"], 3)
        # broken-a, broken-b and withheld have a FAILED/UNAVAILABLE artifact.
        self.assertEqual(row["affected_package_count"], 3)
        # Two packages share one failing URL: sources are counted once.
        self.assertEqual(row["problematic_source_count"], 2)
        self.assertEqual(row["broken_package_count"], row["affected_package_count"])
        self.assertEqual(row["broken_url_count"], row["problematic_source_count"])
        self.assertEqual(row["latest_release"], "2026-11")
        self.assertEqual(row["package_releases"], ["2026-10", "2026-11"])

    def test_provider_without_packages_reports_zero_counts(self):
        self.db.ensure_provider_definition(TEST_PROVIDER)
        row = next(item for item in self.db.provider_rows() if item["provider_id"] == TEST_PROVIDER.id)
        self.assertEqual(
            (row["active_package_count"], row["affected_package_count"], row["problematic_source_count"]),
            (0, 0, 0),
        )
        self.assertIsNone(row["latest_release"])


class UpdateDeviceSupportStatusTests(PGliteTestCase):
    DEVICE = "garmin-query-test-device"

    def setUp(self):
        super().setUp()
        self.sql(
            """INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                   product_url, source_url, active, map_capable)
               VALUES (%s, 'garmin-fenix', 'Garmin', 'Query Test', 'query test', '',
                       'https://example.org/p', 'https://example.org/s', TRUE, TRUE)""",
            (self.DEVICE,),
        )

    def device(self):
        return self.sql(
            "SELECT support_status, active, map_capable FROM device_model WHERE id = %s", (self.DEVICE,)
        )[0]

    def audits(self):
        return self.sql(
            """SELECT previous_status, new_status, reason, note FROM device_authorization_audit
               WHERE device_model_id = %s ORDER BY id""",
            (self.DEVICE,),
        )

    def test_change_is_audited_and_leaves_authorization_and_evidence_untouched(self):
        evidence_before = self.sql("SELECT count(*)::int AS n FROM compatibility_evidence_event")[0]["n"]
        policy_before = self.db.installation_policy_snapshot()

        self.assertTrue(self.db.update_device_support_status(
            self.DEVICE, " unsupported ", reason="Reviewed", note="Operator note"))

        self.assertEqual(self.device(), {"support_status": "UNSUPPORTED", "active": True, "map_capable": True})
        self.assertEqual(self.audits(), [{
            "previous_status": "NOT_EVALUATED", "new_status": "UNSUPPORTED",
            "reason": "Reviewed", "note": "Operator note",
        }])
        self.assertEqual(
            self.sql("SELECT count(*)::int AS n FROM compatibility_evidence_event")[0]["n"], evidence_before)
        # Installation write authorization comes from active + map_capable only.
        policy_after = self.db.installation_policy_snapshot()
        before = [row for row in policy_before[0] if row["device_id"] == self.DEVICE]
        after = [row for row in policy_after[0] if row["device_id"] == self.DEVICE]
        self.assertEqual(len(before), 1)
        self.assertEqual(before, after)
        self.assertNotIn("support_status", after[0])

    def test_same_status_writes_no_audit_and_unknown_device_is_false(self):
        self.assertTrue(self.db.update_device_support_status(self.DEVICE, "NOT_EVALUATED"))
        self.assertEqual(self.audits(), [])
        self.assertFalse(self.db.update_device_support_status("garmin-missing-device", "SUPPORTED"))
        with self.assertRaises(ValueError):
            self.db.update_device_support_status(self.DEVICE, "APPROVED")
        self.assertEqual(self.device()["support_status"], "NOT_EVALUATED")


class OperationalHealthSnapshotTests(PGliteTestCase):
    def observe(self, observation_id: str, *, kind: str, component: str, status: str, minutes: int) -> None:
        self.sql(
            """INSERT INTO operational_observation (
                   observation_id, kind, component, status, observed_at,
                   source_run_id, source_run_url, commit_sha, summary, details)
               VALUES (%s, %s, %s, %s, %s, 'run', 'https://example.org/run', 'abc', %s, %s::jsonb)""",
            (observation_id, kind, component, status, NOW + timedelta(minutes=minutes),
             observation_id, json.dumps({})),
        )

    def test_latest_observation_per_component_latest_weekly_and_scheduler(self):
        self.sql("DELETE FROM operational_observation")
        self.sql("DELETE FROM scheduler_heartbeat")
        self.observe("site-old", kind="DEPLOYMENT", component="site", status="FAILED", minutes=0)
        self.observe("site-new", kind="DEPLOYMENT", component="site", status="HEALTHY", minutes=10)
        self.observe("api-only", kind="DEPLOYMENT", component="catalog-api", status="WARNING", minutes=5)
        self.observe("weekly-old", kind="WEEKLY_TEST", component="test-matrix", status="FAILED", minutes=1)
        self.observe("weekly-new", kind="WEEKLY_TEST", component="test-matrix", status="HEALTHY", minutes=2)
        for index in range(3):
            self.observe(f"indexnow-{index}", kind="INDEXNOW", component="indexnow", status="HEALTHY", minutes=index)
        self.db.record_scheduler_heartbeat(status="HEALTHY", next_run_at=NOW)

        snapshot = self.db.operational_health_snapshot()

        latest = {row["component"]: row["observation_id"] for row in snapshot["observations"]}
        # One row per component, no shared history limit across components.
        self.assertEqual(latest, {
            "site": "site-new", "catalog-api": "api-only",
            "test-matrix": "weekly-new", "indexnow": "indexnow-2",
        })
        self.assertEqual(len(snapshot["observations"]), 4)
        self.assertEqual(snapshot["weekly"]["observation_id"], "weekly-new")
        self.assertEqual(snapshot["scheduler"]["job_name"], "catalog-collector")
        self.assertEqual(snapshot["scheduler"]["status"], "HEALTHY")
        self.assertIn("linked", snapshot["githubSync"])

    def test_empty_store_returns_no_weekly_and_no_scheduler(self):
        self.sql("DELETE FROM operational_observation")
        self.sql("DELETE FROM scheduler_heartbeat")
        snapshot = self.db.operational_health_snapshot()
        self.assertEqual(snapshot["observations"], [])
        self.assertIsNone(snapshot["weekly"])
        self.assertIsNone(snapshot["scheduler"])


class UpsertProviderSnapshotTests(PGliteTestCase):
    def packages(self):
        return {row["id"]: row for row in self.sql(
            "SELECT id, release, availability FROM map_package WHERE provider_id = %s",
            (OPENTOPO_MAP.id,),
        )}

    def start_run(self) -> int:
        return self.sql(
            "INSERT INTO catalog_collection_run (provider_id, status) VALUES (%s, 'RUNNING') RETURNING id",
            (OPENTOPO_MAP.id,),
        )[0]["id"]

    def test_snapshot_stores_counts_audits_changes_and_retires_stale_packages(self):
        provider = OPENTOPO_MAP.id
        first_run = self.start_run()
        self.db.upsert_provider_snapshot(ProviderSnapshot(OPENTOPO_MAP, (
            package("otm-keep", provider_id=provider, artifacts=(artifact("otm-keep-main"),)),
            package("otm-stale", provider_id=provider, artifacts=(artifact("otm-stale-main"),)),
        ), NOW), run_id=first_run)
        self.assertEqual(set(self.packages()) >= {"otm-keep", "otm-stale"}, True)

        second_run = self.start_run()
        self.db.upsert_provider_snapshot(ProviderSnapshot(OPENTOPO_MAP, (
            package("otm-keep", provider_id=provider, release="2026-11", artifacts=(artifact("otm-keep-main"),)),
            package("otm-new", provider_id=provider, artifacts=(artifact("otm-new-main"),)),
        ), NOW + timedelta(days=1)), run_id=second_run)

        stored = self.packages()
        self.assertEqual(stored["otm-keep"]["release"], "2026-11")
        self.assertEqual(stored["otm-new"]["availability"], "AVAILABLE")
        # A complete snapshot retires the provider's stale package and its artifacts.
        self.assertEqual(stored["otm-stale"]["availability"], "RETIRED")
        self.assertEqual(self.sql("SELECT count(*)::int AS n FROM map_artifact WHERE package_id = 'otm-stale'")[0]["n"], 0)

        run = self.sql("SELECT new_package_count, updated_package_count FROM catalog_collection_run WHERE id = %s",
                       (second_run,))[0]
        self.assertEqual((run["new_package_count"], run["updated_package_count"]), (1, 1))
        audit = self.sql(
            """SELECT details FROM admin_audit_log
               WHERE provider_id = %s AND action = 'CATALOG_RELEASES_UPDATED' ORDER BY id DESC LIMIT 1""",
            (provider,),
        )[0]["details"]
        details = audit if isinstance(audit, dict) else json.loads(audit)
        self.assertEqual([item["packageId"] for item in details["packages"]], ["otm-keep"])
        self.assertEqual(details["packages"][0]["previousRelease"], "2026-10")
        last_sync = self.sql("SELECT last_catalog_sync FROM map_provider WHERE id = %s", (provider,))[0]
        self.assertEqual(last_sync["last_catalog_sync"], NOW + timedelta(days=1))
        sources = {row["source_url"] for row in self.sql(
            "SELECT source_url FROM provider_source WHERE provider_id = %s", (provider,))}
        self.assertIn("https://example.org/otm-new-main.zip", sources)

    def test_run_that_is_not_running_is_rejected_and_rolled_back(self):
        run = self.start_run()
        self.sql("UPDATE catalog_collection_run SET status = 'FAILED' WHERE id = %s", (run,))
        with self.assertRaises(ValueError):
            self.db.upsert_provider_snapshot(ProviderSnapshot(OPENTOPO_MAP, (
                package("otm-rejected", provider_id=OPENTOPO_MAP.id),
            ), NOW), run_id=run)
        self.assertNotIn("otm-rejected", self.packages())


class MapStatisticsLinkageTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.sql("DELETE FROM map_download_event")
        self.sql("DELETE FROM compatibility_evidence_event")
        self.rows = StatisticsRows(self.server)

    def test_links_only_by_shared_operation_result_and_provider(self):
        rows = self.rows
        linked_success = rows.uuid()
        rows.map_event(operation_id=linked_success)
        rows.diagnostic(operation_id=linked_success)
        linked_failure = rows.uuid()
        rows.map_event(operation_id=linked_failure, event_type="INSTALL_FAILED", outcome="FAILED")
        rows.diagnostic(operation_id=linked_failure, phase_outcome="FAILED",
                        failure_stage="write", failure_code="WRITE_FAILED")
        # Same operation, but another result index: not this map result's evidence.
        other_result = rows.uuid()
        rows.map_event(operation_id=other_result)
        rows.diagnostic(operation_id=other_result, map_result_index=1)
        # Same operation and index, another provider: not linked.
        other_provider = rows.uuid()
        rows.map_event(operation_id=other_provider)
        rows.diagnostic(operation_id=other_provider, provider="opentopomap")
        # Map result with no watch evidence at all.
        rows.map_event()
        # Map result without an index and two possible results: ambiguous, not linked.
        ambiguous = rows.uuid()
        rows.map_event(operation_id=ambiguous, map_result_index=None)
        rows.diagnostic(operation_id=ambiguous, map_result_index=0)
        rows.diagnostic(operation_id=ambiguous, map_result_index=1)
        # Local test data never counts.
        local = rows.uuid()
        rows.map_event(operation_id=local, is_local_test=True)
        rows.diagnostic(operation_id=local, is_local_test=True)

        linkage = self.db.map_statistics_linkage({})

        self.assertEqual(linkage["mapInstallationCount"], 6)
        self.assertEqual(linkage["linkedInstallationCount"], 2)
        self.assertEqual(linkage["mapOnlyInstallationCount"], 4)
        self.assertEqual(linkage["linkedSuccessfulInstallCount"], 1)
        self.assertEqual(linkage["linkedFailedInstallCount"], 1)
        self.assertEqual(linkage["freshMapMissingDiagnosticCount"], 4)
        self.assertEqual(linkage["freshMapLinkedDiagnosticCount"], 2)


if __name__ == "__main__":
    unittest.main()

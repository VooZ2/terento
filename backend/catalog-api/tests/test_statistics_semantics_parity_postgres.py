"""The documented pure classifier and the real SQL read models must agree (audit H3).

Every case is run through ``statistics_semantics`` and through PostgreSQL with
all migrations applied: ``compatibility_model_statistics`` (view) and the Maps /
Dashboard ``map_statistics`` read model.
"""
import unittest
import uuid
from datetime import datetime

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.statistics_semantics import (
    summarize_acquisitions,
    summarize_fresh_installs,
    summarize_updates,
)
from test_statistics_semantics import fresh

NAMESPACE = uuid.UUID("6f1d0c1e-2b0a-4c8e-9f55-0a1b2c3d4e5f")


def as_uuid(value):
    return str(uuid.uuid5(NAMESPACE, str(value)))


def legacy(index, **changes):
    value = {
        "id": f"legacy-{index}", "schemaVersion": 2, "operationId": None, "mapResultIndex": None,
        "provider": "freizeitkarte", "region": "DEU", "phaseOutcome": "FAILED",
        "automaticFinishingResult": "FAILED", "writeStarted": None, "appBuild": "12",
        "releaseLabel": "1.0.0-beta.4", "timestamp": f"2026-09-17T00:0{index}:00+00:00",
    }
    value.update(changes)
    return value


FRESH_CASES = {
    "two provider maps": [fresh("op", 0), fresh("op", 1, provider="opentopomap", region="AUT")],
    "provider and custom": [fresh("op", 0), fresh("op", 1, custom=True)],
    "two custom images": [fresh("one", 0, custom=True), fresh("two", 0, custom=True)],
    "replay": [fresh("op", 0), fresh("op", 0)],
    "retry": [fresh("op", 0), fresh("retry", 0)],
    "download prewrite": [dict(fresh("blocked", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=False),
                               failureStage="download", failureCode="INSTALL_BLOCKED_DOWNLOAD_FAILED")],
    "preflight prewrite": [dict(fresh("blocked", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=False),
                                failureStage="preflight", failureCode="INSTALL_BLOCKED_INSUFFICIENT_SPACE")],
    "current missing write fact": [fresh("unknown", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=None)],
    "started failure": [fresh("failed", 0, outcome="FAILED", finishing="FAILED")],
    "success and sibling failure": [fresh("op", 0), fresh("op", 1, outcome="FAILED", finishing="FAILED")],
    "success vs not started conflict": [
        fresh("conflict", 0),
        fresh("conflict", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=False, event_id="later"),
    ],
    "same result reported for two regions": [fresh("region", 0), fresh("region", 0, region="AUT", event_id="other")],
    "worked example 9+1": [fresh(f"ok{i}", 0) for i in range(9)] + [fresh("bad", 0, outcome="FAILED", finishing="FAILED")],
    "legacy v2 failure with build": [legacy(1)],
    "legacy v1 success": [legacy(2, schemaVersion=1, phaseOutcome="SUCCEEDED", automaticFinishingResult="VERIFIED")],
}


class FreshParityTests(PGliteTestCase):
    def insert(self, events):
        rows = StatisticsRows(self.server)
        seen = set()
        for event in events:
            if event["id"] in seen:
                continue  # the event_id primary key makes a replay zero additional work
            seen.add(event["id"])
            rows.diagnostic(
                event_id=as_uuid(event["id"]),
                operation_id=as_uuid(event["operationId"]) if event.get("operationId") else as_uuid("op-" + event["id"]),
                map_result_index=event.get("mapResultIndex"),
                selected_map_count=event.get("selectedMapCount") or 1,
                occurred_at=datetime.fromisoformat(event["timestamp"]),
                provider=event["provider"], region=event["region"],
                phase_outcome=event["phaseOutcome"], automatic_finishing_result=event["automaticFinishingResult"],
                write_started=event.get("writeStarted"), app_build=event.get("appBuild"),
                release_label=event.get("releaseLabel"), schema_version=event.get("schemaVersion"),
                failure_stage=event.get("failureStage"), failure_code=event.get("failureCode"),
            )

    def sql_counts(self):
        view = self.sql("SELECT COALESCE(sum(successful_install_count), 0)::int AS s,"
                        " COALESCE(sum(failed_install_count), 0)::int AS f FROM compatibility_model_statistics")[0]
        totals = {}
        for row in self.db.map_statistics({}):
            totals[row["event_type"]] = totals.get(row["event_type"], 0) + int(row["operation_count"] or 0)
        return {
            "view": (view["s"], view["f"]),
            "map_statistics": (totals.get("INSTALL_SUCCEEDED", 0), totals.get("INSTALL_FAILED", 0)),
        }

    def test_every_case_agrees_across_pure_and_sql_read_models(self):
        for name, events in FRESH_CASES.items():
            with self.subTest(case=name):
                self.server.exec("SAVEPOINT parity_case")
                try:
                    self.insert(events)
                    summary = summarize_fresh_installs(events)
                    expected = (summary.successes, summary.failures)
                    for model, counts in self.sql_counts().items():
                        self.assertEqual(counts, expected, f"{model} disagrees with statistics_semantics")
                finally:
                    self.server.exec("ROLLBACK TO SAVEPOINT parity_case")


class AcquisitionAndUpdateParityTests(PGliteTestCase):
    def map_rows(self, events):
        rows = StatisticsRows(self.server)
        for event in events:
            rows.map_event(
                event_id=as_uuid(event["id"]), operation_id=as_uuid(event.get("operationId") or event["id"]),
                provider_id=event.get("providerId", "freizeitkarte"), map_package_id=None,
                event_type=event["eventType"], outcome=event["outcome"],
                acquisition_id=as_uuid(event["acquisitionId"]) if event.get("acquisitionId") else None,
                component_kind=event.get("componentKind") or ("main" if event.get("acquisitionId") else None),
                map_result_index=None,
            )
        totals = {}
        for row in self.db.map_statistics({}):
            totals[row["event_type"]] = totals.get(row["event_type"], 0) + int(row["operation_count"] or 0)
        return totals

    def test_acquisition_identity_and_terminal_conflicts_agree(self):
        events = [
            {"id": "a", "acquisitionId": "a1", "eventType": "DOWNLOAD_STARTED", "outcome": "UNKNOWN"},
            {"id": "b", "acquisitionId": "a1", "eventType": "DOWNLOAD_PROCESSING", "outcome": "UNKNOWN"},
            {"id": "c", "acquisitionId": "a1", "eventType": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED"},
            {"id": "d", "acquisitionId": "a2", "eventType": "DOWNLOAD_FAILED", "outcome": "FAILED"},
            {"id": "e", "acquisitionId": "a3", "eventType": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED"},
            # Legacy terminals without an acquisition ID keep their event identity.
            {"id": "g", "operationId": "legacy", "eventType": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED"},
            {"id": "h", "operationId": "legacy", "eventType": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED"},
        ]
        pure = summarize_acquisitions(events)
        totals = self.map_rows(events)
        self.assertEqual((totals.get("DOWNLOAD_SUCCEEDED", 0), totals.get("DOWNLOAD_FAILED", 0)),
                         (pure["successful"], pure["failed"]))
        self.assertEqual((pure["successful"], pure["failed"]), (4, 1))

    def test_update_results_agree(self):
        events = [
            {"id": "u1", "eventType": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED"},
            {"id": "u2", "eventType": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED"},
            {"id": "u3", "eventType": "MAP_UPDATE_FAILED", "outcome": "FAILED"},
        ]
        pure = summarize_updates(events)
        totals = self.map_rows(events)
        self.assertEqual((totals.get("MAP_UPDATE_SUCCEEDED", 0), totals.get("MAP_UPDATE_FAILED", 0)),
                         (pure["successful"], pure["failed"]))
        fresh_pure = summarize_fresh_installs(events)
        self.assertEqual((fresh_pure.successes, fresh_pure.failures), (0, 0))
        self.assertEqual((totals.get("INSTALL_SUCCEEDED", 0), totals.get("INSTALL_FAILED", 0)), (0, 0))


if __name__ == "__main__":
    unittest.main()

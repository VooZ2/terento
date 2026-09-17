from __future__ import annotations

import unittest

from terento_catalog.statistics_semantics import (
    FAILURE,
    NOT_STARTED,
    SUCCESS,
    summarize_acquisitions,
    summarize_fresh_installs,
    summarize_updates,
)


def fresh(
    operation: str,
    index: int,
    *,
    provider: str = "freizeitkarte",
    region: str = "DEU",
    outcome: str = "SUCCEEDED",
    finishing: str = "VERIFIED",
    write_started: bool | None = True,
    event_id: str | None = None,
    custom: bool = False,
) -> dict:
    return {
        "id": event_id or f"event-{operation}-{index}",
        "schemaVersion": 4,
        "operationId": operation,
        "mapResultIndex": index,
        "selectedMapCount": 2,
        "provider": "custom" if custom else provider,
        "region": "custom" if custom else region,
        "phaseOutcome": outcome,
        "automaticFinishingResult": finishing,
        "writeStarted": write_started,
        "appBuild": "30",
        "releaseLabel": "1.0.0-beta.12",
        "timestamp": f"2026-09-17T00:0{index}:00+00:00",
    }


class StatisticsSemanticsTests(unittest.TestCase):
    def assert_counts(self, events, successes, failures, completed=None):
        summary = summarize_fresh_installs(events)
        self.assertEqual(summary.successes, successes)
        self.assertEqual(summary.failures, failures)
        self.assertEqual(summary.completed, successes + failures if completed is None else completed)

    def test_two_provider_maps_are_two_fresh_successes(self):
        self.assert_counts([fresh("op", 0), fresh("op", 1, provider="opentopomap", region="AUT")], 2, 0)

    def test_main_map_and_contours_are_one_fresh_success(self):
        # The optional contour is represented by the same main-map outcome;
        # it never becomes another compatibility result.
        self.assert_counts([fresh("op", 0)], 1, 0)

    def test_provider_main_and_custom_are_two_fresh_successes(self):
        self.assert_counts([fresh("op", 0), fresh("op", 1, custom=True)], 2, 0)

    def test_open_topo_main_contours_and_custom_are_two_fresh_successes(self):
        self.assert_counts([fresh("op", 0, provider="opentopomap"), fresh("op", 1, custom=True)], 2, 0)

    def test_two_open_topo_maps_each_with_contours_are_two(self):
        self.assert_counts([
            fresh("op", 0, provider="opentopomap", region="DEU"),
            fresh("op", 1, provider="opentopomap", region="AUT"),
        ], 2, 0)

    def test_fresh_and_update_stay_in_separate_populations(self):
        fresh_summary = summarize_fresh_installs([fresh("install", 0)])
        update_summary = summarize_updates([{
            "id": "update-1", "operationId": "update", "eventType": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED"
        }])
        self.assertEqual((fresh_summary.successes, fresh_summary.failures), (1, 0))
        self.assertEqual((update_summary["successful"], update_summary["failed"]), (1, 0))

    def test_two_updates_do_not_create_fresh_attempts(self):
        updates = [
            {"id": "update-1", "operationId": "u1", "eventType": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED"},
            {"id": "update-2", "operationId": "u2", "eventType": "MAP_UPDATE_FAILED", "outcome": "FAILED"},
        ]
        self.assert_counts(updates, 0, 0)
        self.assertEqual(summarize_updates(updates)["completed"], 2)

    def test_update_replay_is_zero_additional_work(self):
        update = {
            "id": "update-replay", "operationId": "u1", "mapId": "otm-de",
            "eventType": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED",
        }
        self.assertEqual(summarize_updates([update, dict(update)])["completed"], 1)

    def test_real_retry_has_new_operation_identity_but_replay_is_zero(self):
        event = fresh("op", 0)
        self.assert_counts([event, dict(event)], 1, 0)
        self.assert_counts([event, fresh("retry", 0)], 2, 0)

    def test_provider_region_does_not_collapse_distinct_custom_images(self):
        self.assert_counts([fresh("one", 0, custom=True), fresh("two", 0, custom=True)], 2, 0)

    def test_preinstall_failure_with_false_write_started_is_not_fresh_failure(self):
        event = fresh(
            "blocked", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=False
        )
        event["failureCode"] = "INSTALL_BLOCKED_DOWNLOAD_FAILED"
        event["failureStage"] = "download"
        summary = summarize_fresh_installs([event])
        self.assertEqual((summary.successes, summary.failures, summary.completed), (0, 0, 0))
        self.assertEqual(summary.results[0].classification, NOT_STARTED)

    def test_missing_write_fact_is_unknown_for_current_data(self):
        event = fresh("unknown", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=None)
        self.assertEqual(summarize_fresh_installs([event]).results[0].classification, "unknown")

    def test_conflicting_success_and_not_started_facts_are_unknown(self):
        success = fresh("conflict", 0)
        not_started = fresh(
            "conflict", 0, outcome="FAILED", finishing="NOT_REACHED", write_started=False,
            event_id="event-conflict-later",
        )
        summary = summarize_fresh_installs([success, not_started])
        self.assertEqual((summary.successes, summary.failures, summary.completed), (0, 0, 0))
        self.assertEqual(summary.results[0].classification, "unknown")

    def test_acquisition_lifecycle_ignores_started_processing_and_custom(self):
        events = [
            {"id": "a", "acquisitionId": "a1", "eventType": "DOWNLOAD_STARTED", "providerId": "freizeitkarte"},
            {"id": "b", "acquisitionId": "a1", "eventType": "DOWNLOAD_PROCESSING", "providerId": "freizeitkarte"},
            {"id": "c", "acquisitionId": "a1", "eventType": "DOWNLOAD_SUCCEEDED", "providerId": "freizeitkarte"},
            {"id": "d", "acquisitionId": "a2", "eventType": "DOWNLOAD_FAILED", "providerId": "freizeitkarte"},
            {"id": "e", "acquisitionId": "a3", "eventType": "DOWNLOAD_SUCCEEDED", "providerId": "custom"},
        ]
        self.assertEqual(summarize_acquisitions(events), {
            "successful": 1, "failed": 1, "completed": 2, "success_rate": 0.5,
        })

    def test_main_and_contours_acquisitions_are_separate_from_fresh_results(self):
        events = [
            {"id": "main-terminal", "operationId": "install", "acquisitionId": "main-acquisition",
             "componentKind": "main", "eventType": "DOWNLOAD_SUCCEEDED", "providerId": "opentopomap"},
            {"id": "contours-terminal", "operationId": "install", "acquisitionId": "contours-acquisition",
             "componentKind": "contours", "eventType": "DOWNLOAD_FAILED", "providerId": "opentopomap"},
        ]
        self.assertEqual(summarize_acquisitions(events)["completed"], 2)
        self.assertEqual(summarize_fresh_installs([fresh("install", 0)]).completed, 1)


if __name__ == "__main__":
    unittest.main()

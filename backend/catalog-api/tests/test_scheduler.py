from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from terento_catalog.collect import collect_all_providers, snapshot_release_evidence
from terento_catalog.config import Settings
from terento_catalog.scheduler import _parse_schedule, run_collection_cycle


class FakeSchedulerDatabase:
    def __init__(self) -> None:
        self.heartbeats = []
        self.definitions = []

    def record_scheduler_heartbeat(self, **values) -> None:
        self.heartbeats.append(values)

    def ensure_provider_definition(self, definition) -> None:
        self.definitions.append(definition.id)


class SchedulerTests(unittest.TestCase):
    def test_default_schedule_is_daily_at_0300_utc(self) -> None:
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://example"}, clear=True):
            self.assertEqual(Settings.from_env().collector_schedule_utc, "03:00")

    def test_weekly_schedule_is_parsed(self) -> None:
        self.assertEqual(_parse_schedule("MON 03:00"), (0, 3, 0))

    def test_legacy_time_only_schedule_remains_daily(self) -> None:
        self.assertEqual(_parse_schedule("03:00"), (None, 3, 0))

    def test_invalid_weekday_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "MON-SUN"):
            _parse_schedule("FUNDAY 03:00")

    def test_provider_collection_failure_does_not_stop_the_next_provider(self) -> None:
        database = FakeSchedulerDatabase()
        adapters = [
            SimpleNamespace(definition=SimpleNamespace(id="freizeitkarte")),
            SimpleNamespace(definition=SimpleNamespace(id="opentopomap")),
        ]
        with patch(
            "terento_catalog.collect.collect_provider_once",
            side_effect=[RuntimeError("FZK unavailable"), {"provider": "opentopomap", "packages": 177, "artifacts": 177, "runId": 2}],
        ) as collect:
            outcomes = collect_all_providers(database, adapters)
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(outcomes["freizeitkarte"]["status"], "FAILED")
        self.assertEqual(outcomes["opentopomap"]["status"], "SUCCEEDED")

    def test_collection_cycle_retains_partial_failure_as_warning(self) -> None:
        database = FakeSchedulerDatabase()
        outcomes = {
            "freizeitkarte": {"status": "SUCCEEDED"},
            "opentopomap": {"status": "FAILED"},
        }
        with patch("terento_catalog.scheduler.official_provider_adapters", return_value=()), \
             patch("terento_catalog.scheduler.collect_all_providers", return_value=outcomes), \
             patch("terento_catalog.scheduler.collect_devices_once"):
            result = run_collection_cycle(database)
        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(database.heartbeats[-1]["status"], "WARNING")
        self.assertIn("opentopomap", database.heartbeats[-1]["error_summary"])

    def test_daily_provider_cycle_does_not_run_weekly_device_collection(self) -> None:
        database = FakeSchedulerDatabase()
        outcomes = {
            "freizeitkarte": {"status": "SUCCEEDED"},
            "opentopomap": {"status": "SUCCEEDED"},
        }
        with patch("terento_catalog.scheduler.official_provider_adapters", return_value=()), \
             patch("terento_catalog.scheduler.collect_all_providers", return_value=outcomes), \
             patch("terento_catalog.scheduler.collect_devices_once") as collect_devices:
            result = run_collection_cycle(database, collect_device_catalog=False)
        collect_devices.assert_not_called()
        self.assertEqual(result["status"], "HEALTHY")

    def test_release_evidence_is_deterministic_and_changes_with_provider_release(self) -> None:
        artifact = SimpleNamespace(
            id="map-main", source_url="https://provider.example/map.zip",
            source_updated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        package = SimpleNamespace(
            id="map", release="2026-09", release_id="2026-09",
            version_label="2026-09",
            source_updated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            generated_at=None, artifacts=(artifact,),
        )
        snapshot = SimpleNamespace(packages=(package,))
        release, fingerprint = snapshot_release_evidence(snapshot)
        self.assertEqual(release, "2026-09")
        self.assertEqual(fingerprint, snapshot_release_evidence(snapshot)[1])
        changed_package = SimpleNamespace(**{**vars(package), "release": "2026-10"})
        self.assertNotEqual(
            fingerprint,
            snapshot_release_evidence(SimpleNamespace(packages=(changed_package,)))[1],
        )


if __name__ == "__main__":
    unittest.main()

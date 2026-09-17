from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import ANY

from terento_catalog.db import Database
from terento_catalog.github_downloads import (
    MAX_RESPONSE_BYTES,
    fetch_github_download_totals,
    release_download_totals,
    collect_once,
)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


class FakeOpener:
    def __init__(self, pages: list[list[dict]]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def open(self, request, *, timeout: int):
        self.urls.append(request.full_url)
        page = int(request.full_url.rsplit("page=", 1)[1])
        return FakeResponse(json.dumps(self.pages[page - 1]).encode())


class SnapshotConnection:
    def __init__(self, latest, trend):
        self.latest = latest
        self.trend = trend
        self.queries = []

    def execute(self, query, parameters=None):
        self.queries.append((query, parameters))
        return SnapshotResult(self.latest if "SELECT dmg_total, zip_total, observed_at" in query else self.trend)


class SnapshotResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class SnapshotDatabase(Database):
    def __init__(self, latest, trend):
        super().__init__("unused")
        self.connection_instance = SnapshotConnection(latest, trend)

    @contextmanager
    def connection(self):
        yield self.connection_instance


class CollectDatabase:
    def __init__(self):
        self.values = None

    def record_github_download_snapshot(self, **values):
        self.values = values
        return True


class WriteConnection:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.calls = []

    def execute(self, query, parameters=None):
        self.calls.append((query, parameters))
        if "pg_try_advisory_xact_lock" in query:
            return SnapshotResult({"acquired": self.acquired})
        return SnapshotResult(None)


class WriteDatabase(Database):
    def __init__(self, acquired=True):
        super().__init__("unused")
        self.connection_instance = WriteConnection(acquired)

    @contextmanager
    def connection(self):
        yield self.connection_instance


class GithubDownloadTests(unittest.TestCase):
    def test_release_download_totals_only_count_dmg_and_zip_assets(self):
        totals = release_download_totals([
            {"assets": [
                {"name": "Terento.DMG", "download_count": 4},
                {"name": "Terento.zip", "download_count": 3},
                {"name": "checksums.txt", "download_count": 99},
            ]},
            {"assets": [{"name": "Terento-legacy.dmg", "download_count": 2}]},
            {"draft": True, "assets": [{"name": "unpublished.zip", "download_count": 100}]},
        ])
        self.assertEqual(totals["dmg_total"], 6)
        self.assertEqual(totals["zip_total"], 3)
        self.assertEqual(totals["release_count"], 2)
        self.assertEqual(totals["asset_count"], 3)
        self.assertTrue(totals["population_fingerprint"])

    def test_fetch_reads_all_release_pages(self):
        first_page = [{"assets": [{"name": "one.dmg", "download_count": 2}]}]
        first_page.extend({"assets": []} for _ in range(99))
        opener = FakeOpener([
            first_page,
            [{"assets": [{"name": "two.zip", "download_count": 5}]}],
        ])
        self.assertEqual(
            fetch_github_download_totals(opener=opener),
            {
                "dmg_total": 2, "zip_total": 5, "release_count": 101,
                "asset_count": 2, "population_fingerprint": ANY,
            },
        )
        self.assertEqual(len(opener.urls), 2)
        self.assertIn("per_page=100", opener.urls[0])
        self.assertIn("page=2", opener.urls[1])

    def test_fetch_rejects_oversized_response(self):
        class OversizedOpener:
            def open(self, request, *, timeout):
                return FakeResponse(b"x" * (MAX_RESPONSE_BYTES + 1))

        with self.assertRaisesRegex(ValueError, "exceeds limit"):
            fetch_github_download_totals(opener=OversizedOpener())

    def test_collect_persists_current_cumulative_totals(self):
        database = CollectDatabase()
        observed_at = datetime(2026, 9, 11, 20, 13, tzinfo=timezone.utc)
        result = collect_once(
            database,
            now=observed_at,
            fetch=lambda: {"dmg_total": 12, "zip_total": 8, "release_count": 4},
        )
        self.assertTrue(result["stored"])
        self.assertEqual(database.values["dmg_total"], 12)
        self.assertEqual(database.values["zip_total"], 8)
        self.assertEqual(database.values["release_count"], 4)
        self.assertEqual(database.values["observed_at"], observed_at)

    def test_database_snapshot_uses_observed_intervals_without_filling_gaps(self):
        now = datetime(2026, 9, 11, 20, 13, tzinfo=timezone.utc)
        start = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 15, "zip_total": 9, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 10, 19, tzinfo=timezone.utc), "dmg_total": 10, "zip_total": 5, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": start, "dmg_total": 12, "zip_total": 6, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 11, 1, tzinfo=timezone.utc), "dmg_total": 15, "zip_total": 9, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
            ],
        )
        result = database.github_downloads_snapshot(now=now)
        self.assertTrue(result["hasData"])
        self.assertEqual((result["dmgTotal"], result["zipTotal"]), (15, 9))
        self.assertEqual(len(result["trend"]), 2)
        self.assertEqual(result["trend"][0]["bucket"], start)
        self.assertEqual(result["trend"][0]["dmg_count"], 2)
        self.assertEqual(
            result["trend"][0]["previous_observed_at"],
            datetime(2026, 9, 10, 19, tzinfo=timezone.utc),
        )
        self.assertEqual(result["trend"][0]["state"], "period_boundary")
        self.assertEqual(result["trend"][1]["state"], "gap")
        self.assertEqual(result["trend"][1]["dmg_count"], 3)
        self.assertEqual(
            result["trend"][1]["previous_observed_at"],
            start,
        )
        self.assertEqual(result["trend"][1]["observed_at"], datetime(2026, 9, 11, 1, tzinfo=timezone.utc))
        query = database.connection_instance.queries[1][0]
        self.assertNotIn("lag(dmg_total)", query)
        self.assertNotIn("greatest", query)

    def test_database_snapshot_without_observations_is_empty(self):
        database = SnapshotDatabase(None, [])
        result = database.github_downloads_snapshot(
            now=datetime(2026, 9, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(result["hasData"], False)
        self.assertEqual(result["trend"], [])

    def test_database_snapshot_keeps_baseline_zero_and_discontinuity_distinct(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 90, "zip_total": 40, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 90, "zip_total": 40, "release_count": 1, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 11, 11, tzinfo=timezone.utc), "dmg_total": 90, "zip_total": 40, "release_count": 1, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 11, 12, tzinfo=timezone.utc), "dmg_total": 80, "zip_total": 40, "release_count": 1, "asset_count": 2, "population_fingerprint": "same"},
            ],
        )
        result = database.github_downloads_snapshot(now=now)
        self.assertEqual(result["trend"][0]["state"], "baseline")
        self.assertIsNone(result["trend"][0]["dmg_count"])
        self.assertEqual(result["trend"][1]["state"], "observed_zero")
        self.assertEqual(result["trend"][1]["dmg_count"], 0)
        self.assertEqual(result["trend"][2]["state"], "discontinuity")
        self.assertIsNone(result["trend"][2]["dmg_count"])

    def test_database_snapshot_marks_missing_hour_as_an_uncertain_interval(self):
        now = datetime(2026, 9, 11, 13, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 110, "zip_total": 40, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 100, "zip_total": 40, "release_count": 1, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 11, 11, tzinfo=timezone.utc), "dmg_total": 103, "zip_total": 40, "release_count": 1, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": now, "dmg_total": 110, "zip_total": 40, "release_count": 1, "asset_count": 2, "population_fingerprint": "same"},
            ],
        )
        result = database.github_downloads_snapshot(now=now)
        self.assertEqual(result["trend"][0]["state"], "baseline")
        self.assertEqual(result["trend"][1]["dmg_count"], 3)
        self.assertEqual(result["trend"][2]["state"], "gap")
        self.assertEqual(result["trend"][2]["dmg_count"], 7)
        self.assertEqual(
            result["trend"][2]["previous_observed_at"],
            datetime(2026, 9, 11, 11, tzinfo=timezone.utc),
        )

    def test_legacy_snapshots_keep_nonnegative_counter_deltas(self):
        """Pre-057 rows retain useful deltas while population identity is unknown."""
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 108, "zip_total": 209, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 100, "zip_total": 200, "release_count": 2, "asset_count": None, "population_fingerprint": None},
                {"observed_at": datetime(2026, 9, 11, 11, tzinfo=timezone.utc), "dmg_total": 103, "zip_total": 202, "release_count": 2, "asset_count": None, "population_fingerprint": None},
                {"observed_at": now, "dmg_total": 108, "zip_total": 209, "release_count": 2, "asset_count": None, "population_fingerprint": None},
            ],
        )
        trend = database.github_downloads_snapshot(now=now)["trend"]
        self.assertEqual([item["dmg_count"] for item in trend], [None, 3, 5])
        self.assertEqual([item["zip_count"] for item in trend], [None, 2, 7])
        self.assertTrue(all(item.get("legacy") for item in trend[1:]))
        self.assertTrue(all(item["population_comparability"] == "unconfirmed" for item in trend[1:]))
        self.assertNotIn("discontinuity", [item["state"] for item in trend[1:]])

    def test_legacy_to_new_metadata_arrival_is_not_a_discontinuity(self):
        now = datetime(2026, 9, 11, 11, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 114, "zip_total": 51, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 110, "zip_total": 50, "release_count": 2, "asset_count": None, "population_fingerprint": None},
                {"observed_at": now, "dmg_total": 114, "zip_total": 51, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
            ],
        )
        item = database.github_downloads_snapshot(now=now)["trend"][1]
        self.assertEqual(item["state"], "observed_increase")
        self.assertEqual((item["dmg_count"], item["zip_count"]), (4, 1))
        self.assertEqual(item["confidence"], "legacy")
        self.assertEqual(item["population_comparability"], "unconfirmed")

    def test_comparable_new_snapshots_are_verified_deltas(self):
        now = datetime(2026, 9, 11, 11, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 114, "zip_total": 50, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 110, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": now, "dmg_total": 114, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
            ],
        )
        item = database.github_downloads_snapshot(now=now)["trend"][1]
        self.assertEqual(item["dmg_count"], 4)
        self.assertEqual(item["confidence"], "verified")
        self.assertEqual(item["population_comparability"], "verified")
        self.assertFalse(item.get("legacy", False))

    def test_first_observation_is_only_a_baseline(self):
        now = datetime(2026, 9, 11, 10, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 110, "zip_total": 50, "observed_at": now},
            [{"observed_at": now, "dmg_total": 110, "zip_total": 50, "release_count": 2}],
        )
        item = database.github_downloads_snapshot(now=now)["trend"][0]
        self.assertEqual(item["state"], "baseline")
        self.assertIsNone(item["dmg_count"])
        self.assertIsNone(item["zip_count"])

    def test_counter_decrease_and_confirmed_population_change_stay_discontinuous(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 120, "zip_total": 50, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 110, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 11, 11, tzinfo=timezone.utc), "dmg_total": 105, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": now, "dmg_total": 120, "zip_total": 50, "release_count": 2, "asset_count": 3, "population_fingerprint": "changed"},
            ],
        )
        trend = database.github_downloads_snapshot(now=now)["trend"]
        self.assertEqual(trend[1]["state"], "discontinuity")
        self.assertEqual(trend[1]["discontinuity_reason"], "counter_decrease")
        self.assertIsNone(trend[1]["dmg_count"])
        self.assertEqual(trend[2]["state"], "discontinuity")
        self.assertEqual(trend[2]["discontinuity_reason"], "population_change")
        self.assertIsNone(trend[2]["dmg_count"])

    def test_daily_aggregation_keeps_known_delta_next_to_unknown_interval(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 112, "zip_total": 50, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 10, 1, tzinfo=timezone.utc), "dmg_total": 100, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 10, 2, tzinfo=timezone.utc), "dmg_total": 102, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 10, 23, tzinfo=timezone.utc), "dmg_total": 112, "zip_total": 50, "release_count": 2, "asset_count": 3, "population_fingerprint": "changed"},
            ],
        )
        item = database.github_downloads_snapshot(now=now, period="7d")["trend"][0]
        self.assertEqual(item["dmg_count"], 2)
        self.assertEqual(item["state"], "partial")
        self.assertTrue(item["partial"])
        self.assertTrue(item["contains_discontinuity"])
        self.assertEqual(item["unknown_interval_count"], 1)

    def test_daily_aggregation_does_not_call_known_zero_a_confirmed_full_day_zero(self):
        now = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 100, "zip_total": 50, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 10, 1, tzinfo=timezone.utc), "dmg_total": 100, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 10, 2, tzinfo=timezone.utc), "dmg_total": 100, "zip_total": 50, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": now, "dmg_total": 100, "zip_total": 50, "release_count": 2, "asset_count": 3, "population_fingerprint": "changed"},
            ],
        )
        item = database.github_downloads_snapshot(now=now, period="7d")["trend"][0]
        self.assertEqual((item["dmg_count"], item["zip_count"]), (0, 0))
        self.assertEqual(item["state"], "partial")
        self.assertTrue(item["partial"])
        self.assertTrue(item["contains_discontinuity"])

    def test_period_views_preserve_known_deltas_across_gaps(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 113, "zip_total": 50, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 5, 1, tzinfo=timezone.utc), "dmg_total": 100, "zip_total": 50, "release_count": 2},
                {"observed_at": datetime(2026, 9, 5, 2, tzinfo=timezone.utc), "dmg_total": 102, "zip_total": 50, "release_count": 2},
                {"observed_at": datetime(2026, 9, 7, 4, tzinfo=timezone.utc), "dmg_total": 105, "zip_total": 50, "release_count": 2},
                {"observed_at": datetime(2026, 9, 10, 13, tzinfo=timezone.utc), "dmg_total": 110, "zip_total": 50, "release_count": 2},
                {"observed_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc), "dmg_total": 113, "zip_total": 50, "release_count": 2},
            ],
        )
        views = {
            period: database.github_downloads_snapshot(now=now, period=period)["trend"]
            for period in ("24h", "7d", "all")
        }
        self.assertEqual(sum(item["dmg_count"] or 0 for item in views["24h"]), 8)
        self.assertEqual(sum(item["dmg_count"] or 0 for item in views["7d"]), 13)
        self.assertEqual(sum(item["dmg_count"] or 0 for item in views["all"]), 13)
        self.assertEqual(views["all"][0]["dmg_count"], 13)

    def test_collection_failure_does_not_replace_last_successful_snapshot(self):
        database = CollectDatabase()
        with self.assertRaisesRegex(RuntimeError, "GitHub unavailable"):
            collect_once(database, fetch=lambda: (_ for _ in ()).throw(RuntimeError("GitHub unavailable")))
        self.assertIsNone(database.values)

    def test_database_snapshot_aggregates_long_periods_in_local_days(self):
        now = datetime(2026, 9, 11, 20, 13, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 15, "zip_total": 9, "observed_at": now},
            [
                {"observed_at": datetime(2026, 9, 9, 20, tzinfo=timezone.utc), "dmg_total": 10, "zip_total": 5, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 10, 21, tzinfo=timezone.utc), "dmg_total": 12, "zip_total": 6, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
                {"observed_at": datetime(2026, 9, 11, 20, tzinfo=timezone.utc), "dmg_total": 15, "zip_total": 9, "release_count": 2, "asset_count": 2, "population_fingerprint": "same"},
            ],
        )
        result = database.github_downloads_snapshot(
            now=now, time_zone="Europe/Vilnius", period="7d",
        )
        self.assertEqual(result["bucket"], "day")
        self.assertEqual(len(result["trend"]), 2)
        self.assertEqual(sum(item["dmg_count"] or 0 for item in result["trend"]), 5)
        self.assertEqual(sum(item["zip_count"] or 0 for item in result["trend"]), 4)
        self.assertTrue(all(item["observed_at"] for item in result["trend"]))

    def test_record_snapshot_upserts_a_utc_hour_and_serializes_counts(self):
        database = WriteDatabase()
        self.assertTrue(database.record_github_download_snapshot(
            dmg_total=12,
            zip_total=8,
            release_count=4,
            observed_at=datetime(2026, 9, 11, 20, 13, 44, tzinfo=timezone.utc),
        ))
        insert = database.connection_instance.calls[1]
        self.assertEqual(insert[1][0], datetime(2026, 9, 11, 20, tzinfo=timezone.utc))
        self.assertEqual(insert[1][2:], (12, 8, 4, None, None))
        self.assertIn("ON CONFLICT (hour_start)", insert[0])

    def test_record_snapshot_skips_when_another_collector_holds_the_lock(self):
        database = WriteDatabase(acquired=False)
        self.assertFalse(database.record_github_download_snapshot(
            dmg_total=1, zip_total=1, release_count=1,
            observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        ))
        self.assertEqual(len(database.connection_instance.calls), 1)


if __name__ == "__main__":
    unittest.main()

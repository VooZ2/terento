from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import unittest

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
        self.assertEqual(totals, {"dmg_total": 6, "zip_total": 3, "release_count": 2})

    def test_fetch_reads_all_release_pages(self):
        first_page = [{"assets": [{"name": "one.dmg", "download_count": 2}]}]
        first_page.extend({"assets": []} for _ in range(99))
        opener = FakeOpener([
            first_page,
            [{"assets": [{"name": "two.zip", "download_count": 5}]}],
        ])
        self.assertEqual(
            fetch_github_download_totals(opener=opener),
            {"dmg_total": 2, "zip_total": 5, "release_count": 101},
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

    def test_database_snapshot_fills_rolling_24_hour_window_and_uses_deltas(self):
        now = datetime(2026, 9, 11, 20, 13, tzinfo=timezone.utc)
        start = datetime(2026, 9, 10, 21, tzinfo=timezone.utc)
        database = SnapshotDatabase(
            {"dmg_total": 15, "zip_total": 9, "observed_at": now},
            [
                {"bucket": start, "dmg_count": 2, "zip_count": 1},
                {"bucket": datetime(2026, 9, 11, 20, tzinfo=timezone.utc), "dmg_count": 3, "zip_count": 4},
            ],
        )
        result = database.github_downloads_snapshot(now=now)
        self.assertTrue(result["hasData"])
        self.assertEqual((result["dmgTotal"], result["zipTotal"]), (15, 9))
        self.assertEqual(len(result["trend"]), 25)
        self.assertEqual(result["trend"][0]["bucket"], datetime(2026, 9, 10, 20, tzinfo=timezone.utc))
        self.assertEqual(result["trend"][1]["dmg_count"], 2)
        self.assertEqual(result["trend"][-1]["zip_count"], 4)
        query = database.connection_instance.queries[1][0]
        self.assertIn("lag(dmg_total)", query)
        self.assertIn("greatest", query)

    def test_database_snapshot_without_observations_is_empty(self):
        database = SnapshotDatabase(None, [])
        result = database.github_downloads_snapshot(
            now=datetime(2026, 9, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(result["hasData"], False)
        self.assertEqual(result["trend"], [])

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
        self.assertEqual(insert[1][2:], (12, 8, 4))
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

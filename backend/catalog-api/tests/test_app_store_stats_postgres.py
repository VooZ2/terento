"""App Store statistics storage on the real migrated schema (migration 095,
asc_stats.py; contracts/STATISTICS_CONTRACT.md, App Store Connect)."""
import unittest
from datetime import date, datetime, timezone

from pglite_support import PGliteTestCase
from terento_catalog import asc_stats


def _rows(day: str, first: int, again: int = 0, campaign: str = "") -> dict:
    rows = {(day, "first_time_downloads", "App Store search", campaign, "LT", "Desktop"): first}
    if again:
        rows[(day, "redownloads", "App Store search", campaign, "LT", "Desktop")] = again
    return rows


class AppStoreStoragePostgresTests(PGliteTestCase):
    def store(self, instance, processing, rows, *, kind="downloads", level="standard"):
        return self.db.store_app_store_instance(
            instance_id=instance, kind=kind, level=level, processing_date=date.fromisoformat(processing), rows=rows,
        )

    def test_a_second_run_never_doubles_a_count(self):
        self.assertEqual(self.store("i-1", "2026-11-19", _rows("2026-11-18", 4, 2)), 1)
        self.assertIsNone(self.store("i-1", "2026-11-19", _rows("2026-11-18", 4, 2)))
        self.assertEqual(self.db.app_store_download_days(date(2026, 11, 1), date(2026, 11, 30)), {date(2026, 11, 18): 6})
        self.assertEqual(self.db.app_store_download_total(), 6)
        self.assertEqual(self.db.app_store_processed_instance_ids(), {"i-1"})

    def test_a_newer_processing_date_replaces_the_day_and_an_older_one_does_not(self):
        self.store("i-1", "2026-11-19", _rows("2026-11-18", 4))
        self.store("i-2", "2026-11-20", _rows("2026-11-18", 5, 1))  # Apple restated the day
        self.assertEqual(self.store("i-0", "2026-11-18", _rows("2026-11-18", 99)), 0)  # late, older instance
        self.assertEqual(self.db.app_store_download_days(date(2026, 11, 18), date(2026, 11, 18)), {date(2026, 11, 18): 6})
        owner = self.sql("SELECT instance_id FROM app_store_report_day WHERE day = '2026-11-18'")
        self.assertEqual(owner, [{"instance_id": "i-2"}])
        self.assertEqual(self.db.app_store_reported_through(), {"downloads": date(2026, 11, 19)})

    def test_reports_and_levels_stay_apart(self):
        self.store("d-1", "2026-11-19", _rows("2026-11-18", 4))
        self.store("e-1", "2026-11-19", {("2026-11-18", "product_page_views", "Web referrer", "", "LT", "Desktop"): 30},
                   kind="engagement")
        self.store("c-1", "2026-11-19", _rows("2026-11-18", 6, campaign="fb-nov"), level="detailed")
        # Replacing the downloads day leaves page views and the Detailed campaign rows alone.
        self.store("d-2", "2026-11-20", _rows("2026-11-18", 5))
        standard = self.db.app_store_daily("standard", date(2026, 11, 18), date(2026, 11, 18))
        self.assertEqual(sorted((row["metric"], row["count"]) for row in standard),
                         [("first_time_downloads", 5), ("product_page_views", 30)])
        detailed = self.db.app_store_daily("detailed", date(2026, 11, 18), date(2026, 11, 18))
        self.assertEqual([(row["campaign"], row["count"]) for row in detailed], [("fb-nov", 6)])
        self.assertEqual(self.db.app_store_download_total(), 5)  # Detailed is never added to the totals
        self.assertEqual(self.db.app_store_first_day(), date(2026, 11, 18))

    def test_updates_are_stored_apart_and_an_older_parse_is_read_again(self):
        update = ("2026-11-18", "updates", "App Store search", "", "LT", "Desktop")
        self.assertEqual(self.store("d-1", "2026-11-19", _rows("2026-11-18", 4, 1)), 1)  # read by parser 1
        self.assertEqual(self.db.app_store_processed_instance_ids(asc_stats.PARSE_VERSIONS), set())
        self.assertEqual(self.db.app_store_processed_instance_ids(), {"d-1"})
        rows = {**_rows("2026-11-18", 4, 1), update: 7}
        self.assertEqual(self.db.store_app_store_instance(instance_id="d-1", kind="downloads", level="standard",
                                                          processing_date=date(2026, 11, 19), rows=rows,
                                                          parse_version=2), 1)
        self.assertIsNone(self.db.store_app_store_instance(instance_id="d-1", kind="downloads", level="standard",
                                                           processing_date=date(2026, 11, 19), rows=rows,
                                                           parse_version=2))
        self.assertEqual(self.db.app_store_processed_instance_ids(asc_stats.PARSE_VERSIONS), {"d-1"})
        self.assertEqual(self.db.app_store_update_days(date(2026, 11, 1), date(2026, 11, 30)), {date(2026, 11, 18): 7})
        self.assertEqual(self.db.app_store_download_total(), 5)  # an update is never a download
        self.assertEqual(self.sql("SELECT DISTINCT metric FROM app_store_daily_metric ORDER BY metric"),
                         [{"metric": "first_time_downloads"}, {"metric": "redownloads"}])
        # A newer instance restates the day: its updates replace the old ones.
        self.store("d-2", "2026-11-20", {**_rows("2026-11-18", 4), update: 2})
        self.assertEqual(self.db.app_store_update_days(date(2026, 11, 18), date(2026, 11, 18)), {date(2026, 11, 18): 2})
        with self.assertRaises(ValueError):  # Detailed keeps no updates
            self.store("c-1", "2026-11-19", {update: 1}, level="detailed")

    def test_a_metric_from_another_report_is_refused(self):
        with self.assertRaises(ValueError):
            self.store("x-1", "2026-11-19", {("2026-11-18", "impressions", "", "", "", ""): 1})

    def test_sync_state_keeps_the_last_success(self):
        first = datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc)
        later = datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc)
        self.db.record_app_store_sync(attempted_at=first, succeeded=True, error=None, request_state="active")
        self.db.record_app_store_sync(attempted_at=later, succeeded=False, error="HTTP 401", request_state=None)
        state = self.db.app_store_sync_state()
        self.assertEqual(state["last_attempt_at"], later)
        self.assertEqual(state["last_success_at"], first)
        self.assertEqual(state["last_error"], "HTTP 401")
        self.assertEqual(state["request_state"], "active")

    def test_admin_snapshot_reads_the_stored_rows(self):
        self.store("d-1", "2026-11-19", _rows("2026-11-18", 4, 1))
        self.store("e-1", "2026-11-19", {("2026-11-18", "product_page_views", "Web referrer", "", "LT", "Desktop"): 20},
                   kind="engagement")
        self.db.record_app_store_sync(attempted_at=datetime(2026, 11, 20, 6, tzinfo=timezone.utc), succeeded=True,
                                      error=None, request_state="active")
        snapshot = asc_stats.admin_snapshot(self.db, "7d", configured=True)
        self.assertEqual(snapshot["state"], "ok")
        self.assertEqual(snapshot["data"]["totals"]["first_time_downloads"], 4)
        self.assertEqual(snapshot["data"]["totals"]["product_page_views"], 20)
        self.assertEqual(snapshot["data"]["totals"]["impressions"], 20)  # page views count as impressions
        self.assertEqual(snapshot["data"]["totals"]["updates"], 0)
        store = asc_stats.dashboard_downloads(self.db, date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(store["days"], {"2026-11-18": 5})
        self.assertEqual(store["total"], 5)


if __name__ == "__main__":
    unittest.main()

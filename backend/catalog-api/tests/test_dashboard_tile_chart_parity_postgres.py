"""Dashboard tiles and their charts describe the same population (owner rule).

For every selectable period, the period tiles (installs, updates, downloads)
must equal the sum of the chart buckets beside them, including custom .img
installs, failed installs, both update outcomes and both download outcomes.
"""
import unittest
from datetime import timedelta

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows


PERIODS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


class DashboardTileChartParityTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.now = self.sql("SELECT now() AS now")[0]["now"]
        self.rows.package("fzk-deu", region="DEU")
        offsets = (timedelta(hours=2), timedelta(days=3), timedelta(days=12), timedelta(days=40))
        for offset in offsets:
            at = self.now - offset
            # Provider fresh install success, linked diagnostic.
            operation = self.rows.uuid()
            self.rows.map_event(operation_id=operation, map_package_id="fzk-deu",
                                map_result_index=0, occurred_at=at)
            self.rows.diagnostic(operation_id=operation, map_result_index=0, occurred_at=at)
            # Custom .img fresh install (diagnostic stream only).
            self.rows.diagnostic(provider="custom", region="custom-img", occurred_at=at)
            # Confirmed started fresh-install failure.
            failed = self.rows.uuid()
            self.rows.map_event(operation_id=failed, map_package_id="fzk-deu", map_result_index=0,
                                event_type="INSTALL_FAILED", outcome="FAILED", occurred_at=at)
            self.rows.diagnostic(operation_id=failed, map_result_index=0, phase_outcome="FAILED",
                                 write_started=True, occurred_at=at)
            # Updates: one success, one failure.
            self.rows.map_event(map_package_id="fzk-deu", event_type="MAP_UPDATE_SUCCEEDED",
                                outcome="SUCCEEDED", occurred_at=at)
            self.rows.map_event(map_package_id="fzk-deu", event_type="MAP_UPDATE_FAILED",
                                outcome="FAILED", occurred_at=at)
            # Downloads: install and update purposes, one failure.
            for event_type, outcome, purpose in (
                ("DOWNLOAD_SUCCEEDED", "SUCCEEDED", "install"),
                ("DOWNLOAD_SUCCEEDED", "SUCCEEDED", "update"),
                ("DOWNLOAD_FAILED", "FAILED", "install"),
            ):
                self.rows.map_event(map_package_id="fzk-deu", event_type=event_type, outcome=outcome,
                                    acquisition_id=self.rows.uuid(), component_kind="main",
                                    acquisition_purpose=purpose, occurred_at=at)

    def assert_tiles_match_chart(self, period: str, since):
        snapshot = self.db.admin_overview_map_snapshot(since, period=period, time_zone="Europe/Vilnius")
        trend = snapshot.get("trend") or []

        def total(field):
            return sum(int(bucket.get(field) or 0) for bucket in trend)

        message = f"period={period}"
        self.assertEqual(snapshot["completedInstallCount"],
                         total("success_count") + total("custom_count"), message)
        self.assertEqual(snapshot["failedInstallCount"], total("failed_count"), message)
        self.assertEqual(snapshot["completedMapUpdateCount"], total("map_update_success_count"), message)
        self.assertEqual(snapshot["failedMapUpdateCount"], total("map_update_failed_count"), message)
        self.assertEqual(snapshot["completedDownloadCount"], total("download_success_count"), message)
        self.assertEqual(snapshot["failedDownloadCount"], total("download_failed_count"), message)
        return snapshot

    def test_every_period_tile_equals_its_chart_total(self):
        expected_windows = {"24h": 1, "7d": 2, "30d": 3}
        for period, span in PERIODS.items():
            with self.subTest(period=period):
                snapshot = self.assert_tiles_match_chart(period, self.now - span)
                windows = expected_windows[period]
                self.assertEqual(snapshot["completedInstallCount"], 2 * windows,
                                 "provider and custom .img installs both count")
                self.assertEqual(snapshot["failedInstallCount"], windows)
                self.assertEqual(snapshot["completedMapUpdateCount"], windows)
                self.assertEqual(snapshot["failedMapUpdateCount"], windows)
                self.assertEqual(snapshot["completedDownloadCount"], 2 * windows)
                self.assertEqual(snapshot["failedDownloadCount"], windows)

    def test_maps_page_tiles_equal_chart_totals(self):
        from terento_catalog.http_api import CatalogService

        service = CatalogService(self.db)
        for period in ("24h", "7d", "30d", "all"):
            with self.subTest(period=period):
                payload = service.map_statistics({"period": period, "timeZone": "Europe/Vilnius"})
                summary, trend = payload["summary"], payload["trend"]

                def total(field):
                    return sum(int(bucket.get(field) or 0) for bucket in trend)

                self.assertEqual(summary["completedInstalls"], total("success_count") + total("custom_count"))
                self.assertEqual(summary["failedInstalls"], total("failed_count"))
                self.assertEqual(summary["completedDownloads"], total("download_success_count"))
                self.assertEqual(summary["failedDownloads"], total("download_failed_count"))
                self.assertEqual(summary["completedMapUpdates"], total("map_update_success_count"))
                self.assertEqual(summary["failedMapUpdates"], total("map_update_failed_count"))


if __name__ == "__main__":
    unittest.main()

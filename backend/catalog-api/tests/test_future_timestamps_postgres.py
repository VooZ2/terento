"""Future-dated client timestamps: KPIs and charts agree (audit L2)."""
import unittest
from datetime import datetime, timedelta, timezone

from pglite_support import PGliteTestCase
from statistics_fixtures import StatisticsRows


def installs(rows):
    return sum(int(row["operation_count"] or 0) for row in rows if row["event_type"] == "INSTALL_SUCCEEDED")


class FutureTimestampTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.now = self.sql("SELECT now() AS now")[0]["now"]
        self.since = self.now - timedelta(hours=1)

    def test_far_future_event_counts_at_receipt_in_kpi_and_trend(self):
        self.rows.map_event(occurred_at=self.now + timedelta(days=2))
        kpi = installs(self.db.map_statistics({"dateFrom": self.since}))
        trend, bucket = self.db.map_statistics_trend({"dateFrom": self.since}, period="24h")
        self.assertEqual(bucket, "hour")
        self.assertEqual(kpi, 1)
        self.assertEqual(sum(int(row.get("success_count") or 0) for row in trend), kpi)
        row = next(r for r in self.db.map_statistics({}) if r["event_type"] == "INSTALL_SUCCEEDED")
        self.assertEqual(row["last_occurred_at"], self.now)
        stored = self.sql("SELECT occurred_at FROM map_download_event")[0]["occurred_at"]
        self.assertEqual(stored, self.now + timedelta(days=2), "the reported fact is not rewritten")

    def test_small_clock_skew_keeps_the_reported_time(self):
        reported = self.now + timedelta(minutes=5)
        self.rows.map_event(occurred_at=reported)
        row = next(r for r in self.db.map_statistics({}) if r["event_type"] == "INSTALL_SUCCEEDED")
        self.assertEqual(row["last_occurred_at"], reported)

    def test_future_diagnostic_fallback_uses_receipt_time(self):
        self.rows.diagnostic(occurred_at=self.now + timedelta(days=3))
        self.assertEqual(installs(self.db.map_statistics({"dateFrom": self.since, "dateTo": self.now + timedelta(minutes=1)})), 1)


if __name__ == "__main__":
    unittest.main()

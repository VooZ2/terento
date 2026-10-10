"""The Today period (owner request 2026-10-07) and the shared period window.

Today runs from local midnight in the selected Admin time zone until now,
with hourly trend buckets like Last 24 hours. The other periods and the
defaults are unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

from api_test_fixtures import FakeProviderDatabase
from test_github_downloads import SnapshotDatabase
from terento_catalog.admin import _overview_downloads_chart, map_statistics_page, overview_page
from terento_catalog.app_funnel import FunnelValidationError
from terento_catalog.db import Database
from terento_catalog.http_api import CatalogService
from terento_catalog.map_events import MapEventValidationError
from terento_catalog.statistics_periods import (
    ADMIN_PERIOD_LABELS,
    ADMIN_PERIODS,
    PERIOD_BUCKETS,
    local_day_start,
    period_start,
)


UTC = timezone.utc
PICKER_ORDER = [
    ("today", "Today"),
    ("24h", "Last 24 hours"),
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
    ("all", "All time"),
]


def frozen_datetime(moment: datetime) -> type[datetime]:
    """A ``datetime`` whose ``now`` is fixed, patched into one module."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls.fromtimestamp(moment.timestamp(), tz=UTC)
            return value if tz is None or tz is UTC else value.astimezone(tz)

    return Frozen


class PeriodWindowTests(unittest.TestCase):
    def test_period_set_order_labels_and_buckets(self):
        self.assertEqual(ADMIN_PERIODS, tuple(value for value, _ in PICKER_ORDER))
        self.assertEqual(list(ADMIN_PERIOD_LABELS.items()), PICKER_ORDER)
        self.assertEqual(PERIOD_BUCKETS["today"], "hour")
        self.assertEqual(PERIOD_BUCKETS["24h"], "hour")

    def test_today_starts_at_utc_midnight_in_utc(self):
        now = datetime(2026, 10, 7, 15, 42, 11, tzinfo=UTC)
        self.assertEqual(period_start("today", now=now, time_zone="UTC"), datetime(2026, 10, 7, tzinfo=UTC))

    def test_today_starts_at_local_midnight_in_vilnius(self):
        # 18:42 EEST (+03:00): the local day began at 21:00 UTC the day before.
        now = datetime(2026, 10, 7, 15, 42, tzinfo=UTC)
        self.assertEqual(local_day_start(now, "Europe/Vilnius"), datetime(2026, 10, 6, 21, tzinfo=UTC))
        # 00:30 local on 7 October is still 6 October in UTC.
        self.assertEqual(
            period_start("today", now=datetime(2026, 10, 6, 21, 30, tzinfo=UTC), time_zone="Europe/Vilnius"),
            datetime(2026, 10, 6, 21, tzinfo=UTC),
        )
        # 23:59 local on 6 October belongs to the previous local day.
        self.assertEqual(
            period_start("today", now=datetime(2026, 10, 6, 20, 59, tzinfo=UTC), time_zone="Europe/Vilnius"),
            datetime(2026, 10, 5, 21, tzinfo=UTC),
        )

    def test_today_on_dst_boundary_days_uses_the_midnight_offset(self):
        # 25 October 2026: Vilnius falls back at 04:00 EEST; midnight was +03:00.
        self.assertEqual(
            local_day_start(datetime(2026, 10, 25, 10, 30, tzinfo=UTC), "Europe/Vilnius"),
            datetime(2026, 10, 24, 21, tzinfo=UTC),
        )
        # 29 March 2026: Vilnius springs forward at 03:00 EET; midnight was +02:00.
        self.assertEqual(
            local_day_start(datetime(2026, 3, 29, 10, tzinfo=UTC), "Europe/Vilnius"),
            datetime(2026, 3, 28, 22, tzinfo=UTC),
        )
        # 8 March 2026: Havana skips 00:00–01:00; the day starts at its first
        # existing instant (01:00 CDT = 05:00 UTC).
        self.assertEqual(
            local_day_start(datetime(2026, 3, 8, 15, tzinfo=UTC), "America/Havana"),
            datetime(2026, 3, 8, 5, tzinfo=UTC),
        )

    def test_today_falls_back_to_utc_and_accepts_naive_now(self):
        now = datetime(2026, 10, 7, 1, 5, tzinfo=UTC)
        self.assertEqual(local_day_start(now, "Not/AZone"), datetime(2026, 10, 7, tzinfo=UTC))
        self.assertEqual(local_day_start(now, None), datetime(2026, 10, 7, tzinfo=UTC))
        self.assertEqual(local_day_start(datetime(2026, 10, 7, 1, 5), "UTC"), datetime(2026, 10, 7, tzinfo=UTC))

    def test_rolling_periods_and_all_time_are_unchanged(self):
        now = datetime(2026, 10, 7, 15, 42, tzinfo=UTC)
        for period, duration in (("24h", timedelta(hours=24)), ("7d", timedelta(days=7)), ("30d", timedelta(days=30))):
            self.assertEqual(period_start(period, now=now, time_zone="Europe/Vilnius"), now - duration)
        self.assertIsNone(period_start("all", now=now))
        with self.assertRaises(ValueError):
            period_start("1d", now=now)


class TodayHourlyTrendTests(unittest.TestCase):
    def trend(self, now: datetime, time_zone: str, rows: list[dict]):
        class TrendDatabase(Database):
            def map_statistics(self, filters, **kwargs):
                self.kwargs = kwargs
                return rows

        # The read model checks ``isinstance(value, datetime)`` against the
        # patched class, so inputs are built from it (as in
        # test_statistics_integrity).
        frozen = frozen_datetime(now)

        def as_frozen(value: datetime) -> datetime:
            return frozen.fromtimestamp(value.timestamp(), tz=UTC)

        rows = [{**row, "bucket": as_frozen(row["bucket"])} for row in rows]
        database = TrendDatabase("")
        since = as_frozen(local_day_start(now, time_zone))
        with patch("terento_catalog.db.datetime", frozen):
            trend, bucket = database.map_statistics_trend({"dateFrom": since}, period="today", time_zone=time_zone)
        self.assertEqual(database.kwargs, {"trend_bucket": "hour", "time_zone": time_zone})
        return trend, bucket

    def test_today_is_hourly_from_local_midnight_to_the_current_hour(self):
        now = datetime(2026, 10, 7, 15, 42, tzinfo=UTC)  # 18:42 in Vilnius
        event_hour = datetime(2026, 10, 7, 6, tzinfo=UTC)  # 09:00 local
        trend, bucket = self.trend(now, "Europe/Vilnius", [{"bucket": event_hour, "success_count": 2}])
        self.assertEqual(bucket, "hour")
        self.assertEqual(trend[0]["bucket"], datetime(2026, 10, 6, 21, tzinfo=UTC))
        self.assertEqual(trend[-1]["bucket"], datetime(2026, 10, 7, 15, tzinfo=UTC))
        self.assertEqual(len(trend), 19)  # 00:00 … 18:00 local
        # Zero-fill is display-only: the one observed bucket keeps its count.
        self.assertEqual(sum(row.get("success_count", 0) for row in trend), 2)
        self.assertEqual([row["bucket"] for row in trend if row.get("success_count")], [event_hour])

    def test_today_on_the_dst_rollback_day_keeps_the_repeated_hour(self):
        # 25 October 2026, 12:30 EET: local hours 00:00 … 12:00 with 03:00 twice.
        now = datetime(2026, 10, 25, 10, 30, tzinfo=UTC)
        trend, bucket = self.trend(now, "Europe/Vilnius", [{"bucket": datetime(2026, 10, 25, 1, tzinfo=UTC), "success_count": 1}])
        self.assertEqual(bucket, "hour")
        self.assertEqual(len(trend), 14)
        self.assertEqual(trend[0]["bucket"], datetime(2026, 10, 24, 21, tzinfo=UTC))
        self.assertEqual(len({row["bucket"] for row in trend}), 14)

    def test_today_github_download_window_starts_at_local_midnight(self):
        now = datetime(2026, 10, 7, 15, 42, tzinfo=UTC)
        observations = [
            {"observed_at": datetime(2026, 10, 6, 20, 30, tzinfo=UTC), "dmg_total": 10, "zip_total": 5, "release_count": 2},
            {"observed_at": datetime(2026, 10, 6, 21, 30, tzinfo=UTC), "dmg_total": 12, "zip_total": 5, "release_count": 2},
            {"observed_at": datetime(2026, 10, 7, 9, 30, tzinfo=UTC), "dmg_total": 15, "zip_total": 6, "release_count": 2},
        ]
        database = SnapshotDatabase({"dmg_total": 15, "zip_total": 6, "observed_at": observations[-1]["observed_at"]}, observations)
        vilnius = database.github_downloads_snapshot(now=now, time_zone="Europe/Vilnius", period="today")
        self.assertEqual(vilnius["bucket"], "hour")
        # 20:30 UTC is 23:30 local on 6 October: before Today, so it is only
        # the previous observation of the boundary interval.
        self.assertEqual([item["observed_at"] for item in vilnius["trend"]], [o["observed_at"] for o in observations[1:]])
        self.assertEqual(sum(item["dmg_count"] or 0 for item in vilnius["trend"]), 5)
        self.assertEqual(vilnius["trend"][0]["state"], "period_boundary")
        utc = database.github_downloads_snapshot(now=now, time_zone="UTC", period="today")
        self.assertEqual([item["observed_at"] for item in utc["trend"]], [observations[-1]["observed_at"]])


class FunnelDatabase(FakeProviderDatabase):
    def __init__(self) -> None:
        super().__init__()
        self.funnel_windows: list[tuple] = []

    def app_funnel_summary(self, since, until=None, **_):
        self.funnel_windows.append((since, until))
        return {"sessionCount": 0, "neverConnectedSessionCount": 0, "stages": [], "modelsNeedingReview": []}


class TodayServiceTests(unittest.TestCase):
    now = datetime(2026, 10, 7, 15, 42, tzinfo=UTC)

    def test_map_statistics_today_uses_local_midnight_and_hourly_trend(self):
        class TrendDatabase(FakeProviderDatabase):
            def map_statistics_trend(self, filters, *, period, time_zone):
                self.trend_call = (dict(filters), period, time_zone)
                return [], "hour"

        database = TrendDatabase()
        with patch("terento_catalog.http_api.datetime", frozen_datetime(self.now)):
            payload = CatalogService(database).map_statistics({
                "period": "today", "timeZone": "Europe/Vilnius", "dateFrom": "2000-01-01T00:00:00+00:00",
            })
        midnight = datetime(2026, 10, 6, 21, tzinfo=UTC)
        self.assertEqual(payload["filters"]["period"], "today")
        self.assertEqual(payload["timeZone"], "Europe/Vilnius")
        self.assertEqual(database.map_statistic_filters[0]["dateFrom"], midnight)
        self.assertNotIn("dateFrom", database.map_statistic_filters[1])  # all-time summary
        filters, period, time_zone = database.trend_call
        self.assertEqual((filters["dateFrom"], period, time_zone), (midnight, "today", "Europe/Vilnius"))

    def test_map_statistics_today_falls_back_to_utc_and_unknown_periods_stay_rejected(self):
        database = FakeProviderDatabase()
        with patch("terento_catalog.http_api.datetime", frozen_datetime(self.now)):
            payload = CatalogService(database).map_statistics({"period": "today", "timeZone": "Mars/Base"})
        self.assertEqual(payload["timeZone"], "UTC")
        self.assertEqual(payload["bucket"], "hour")
        self.assertEqual(database.map_statistic_filters[0]["dateFrom"], datetime(2026, 10, 7, tzinfo=UTC))
        for bad in ("1d", "yesterday", "today2"):
            with self.subTest(period=bad), self.assertRaisesRegex(MapEventValidationError, "invalid_period_filter"):
                CatalogService(FakeProviderDatabase()).map_statistics({"period": bad})

    def test_app_funnel_today_uses_the_time_zone_and_keeps_validation(self):
        database = FunnelDatabase()
        service = CatalogService(database)
        with patch("terento_catalog.http_api.datetime", frozen_datetime(self.now)):
            payload = service.app_funnel({"period": "today", "timeZone": "Europe/Vilnius"})
            utc = service.app_funnel({"period": "today", "timeZone": "Not/AZone"})
            default = service.app_funnel({})
        self.assertEqual(payload["period"], "today")
        self.assertEqual(payload["timeZone"], "Europe/Vilnius")
        self.assertEqual(payload["since"], "2026-10-06T21:00:00+00:00")
        self.assertEqual(database.funnel_windows[0][0], datetime(2026, 10, 6, 21, tzinfo=UTC))
        self.assertEqual((utc["timeZone"], utc["since"]), ("UTC", "2026-10-07T00:00:00+00:00"))
        self.assertEqual(default["period"], "7d")
        for bad in ({"period": "1d"}, {"period": "today", "other": "x"}):
            with self.assertRaises(FunnelValidationError):
                service.app_funnel(bad)

    def test_dashboard_today_scopes_every_period_section_to_local_midnight(self):
        database = FunnelDatabase()
        with patch("terento_catalog.http_api.datetime", frozen_datetime(self.now)):
            overview = CatalogService(database).admin_overview("today", "Europe/Vilnius")
            fallback = CatalogService(database).admin_overview("yesterday", "Europe/Vilnius")
        midnight = datetime(2026, 10, 6, 21, tzinfo=UTC)
        self.assertEqual((overview["period"], overview["since"]), ("today", midnight))
        self.assertEqual(database.overview_map_requests[0], (midnight, "today", "Europe/Vilnius"))
        self.assertEqual(database.overview_download_requests[0], ("today", "Europe/Vilnius"))
        self.assertEqual(overview["funnel"]["since"], midnight.isoformat())
        self.assertEqual(overview["funnel"]["timeZone"], "Europe/Vilnius")
        # Unknown values keep falling back to the unchanged default.
        self.assertEqual(fallback["period"], "24h")
        self.assertEqual(database.overview_map_requests[1][0], self.now - timedelta(hours=24))


class PickerOptions(HTMLParser):
    def __init__(self, select_id: str) -> None:
        super().__init__()
        self.select_id = select_id
        self.inside = False
        self.options: list[list] = []
        self.buttons: list[list] = []
        self.group = False
        self.button: list | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select":
            self.inside = attributes.get("id") == self.select_id
        elif tag == "option" and self.inside:
            self.options.append([attributes.get("value"), "", "selected" in attributes])
        elif tag == "div" and attributes.get("data-quick-select") == self.select_id:
            self.group = True
        elif tag == "button" and self.group:
            self.button = [attributes.get("data-quick-value"), "", attributes.get("aria-pressed")]
            self.buttons.append(self.button)

    def handle_endtag(self, tag):
        if tag == "select":
            self.inside = False
        elif tag == "div":
            self.group = False
        elif tag == "button":
            self.button = None

    def handle_data(self, data):
        if self.inside and self.options:
            self.options[-1][1] += data
        if self.button is not None:
            self.button[1] += data


def picker(body: str, select_id: str) -> PickerOptions:
    parser = PickerOptions(select_id)
    parser.feed(body)
    return parser


def dashboard(period: str | None) -> str:
    return overview_page(
        {
            **({"period": period} if period is not None else {}),
            "timeZone": "Europe/Vilnius",
            "data": {
                "hasData": True, "completedInstallCount": 1, "failedInstallCount": 0,
                "completedDownloadCount": 1, "failedDownloadCount": 0,
                "recentActivity": [], "attention": [], "trend": [], "bucket": "hour",
            },
            "downloads": {
                "hasData": True, "dmgTotal": 3, "zipTotal": 1, "bucket": "hour",
                "trend": [{"bucket": datetime(2026, 10, 7, 6, tzinfo=UTC), "dmg_count": 1, "zip_count": 0}],
            },
            "funnel": {"sessionCount": 0, "stages": []},
            "providers": [],
        },
        {"username": "operator"}, "csrf",
    ).decode()


class TodayPickerMarkupTests(unittest.TestCase):
    def test_dashboard_period_dropdown_lists_today_first_and_keeps_the_default(self):
        default = picker(dashboard(None), "overview-period")
        self.assertEqual([(value, label) for value, label, _ in default.options], PICKER_ORDER)
        self.assertEqual([value for value, _, selected in default.options if selected], ["24h"])
        today = picker(dashboard("today"), "overview-period")
        self.assertEqual([value for value, _, selected in today.options if selected], ["today"])
        self.assertEqual(
            [value for value, _, selected in picker(dashboard("tomorrow"), "overview-period").options if selected],
            ["24h"],
        )

    def test_dashboard_scope_chips_name_today(self):
        body = dashboard("today")
        self.assertIn("<span class='admin-scope-chip' data-scope='period'>Today</span>", body)
        self.assertNotIn("Last 24 hours</span>", body)
        for card in ("overview-download-trend", "overview-trend", "overview-activity", "overview-funnel", "overview-downloads"):
            with self.subTest(card=card):
                section = body.split(f"id='{card}'", 1)[1].split("</section>", 1)[0]
                self.assertIn("data-scope='period'>Today</span>", section)
        self.assertIn("/admin/map-statistics?period=today", body)

    def test_app_downloads_chart_names_today(self):
        chart = _overview_downloads_chart({
            "hasData": True, "trend": [{"bucket": datetime(2026, 10, 7, 6, tzinfo=UTC), "dmg_count": 1, "zip_count": 0}],
        }, "Europe/Vilnius", period="today")
        self.assertIn("observed counter increases between checks over today", chart)
        self.assertIn(">09:00<", chart)

    def test_maps_time_range_quick_filter_lists_today_first_and_keeps_the_default(self):
        def render(filters):
            return map_statistics_page(
                {"rows": [], "trend": [], "filters": filters}, [], {"username": "operator"}, "csrf",
                selected_filters=filters,
            ).decode()

        default = picker(render({}), "map-statistics-range")
        self.assertEqual([(value, label) for value, label, _ in default.options], PICKER_ORDER)
        self.assertEqual([(value, label) for value, label, _ in default.buttons], PICKER_ORDER)
        self.assertEqual([value for value, _, pressed in default.buttons if pressed == "true"], ["all"])
        today = picker(render({"period": "today"}), "map-statistics-range")
        self.assertEqual([value for value, _, pressed in today.buttons if pressed == "true"], ["today"])
        self.assertEqual([value for value, _, selected in today.options if selected], ["today"])


if __name__ == "__main__":
    unittest.main()

"""Admin freshness notice: revisions change only when displayed data changes.

Owner report 2026-10-07: "New activity is available." appeared on an unchanged
Dashboard. The First run section hashed its request window (``since`` /
``until`` = now), so every poll produced a different revision.
"""
from __future__ import annotations

import copy
import html
import json
import re
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from test_admin_dashboard_redesign import COOKIE, REVIEW, CountingDatabase, _funnel
from terento_catalog.admin import map_statistics_page, overview_page
from terento_catalog.admin_revisions import active_trend_buckets, section_revisions
from terento_catalog.http_api import CatalogService, make_handler

USER = {"username": "operator", "admin_review_summary": REVIEW}


def revisions(body: bytes | str) -> dict[str, str]:
    text = body.decode() if isinstance(body, bytes) else body
    return json.loads(html.unescape(re.search(r'data-admin-revisions="([^"]+)"', text)[1]))


def zero_bucket(bucket: str) -> dict:
    return {"bucket": bucket, "success_count": 0, "failed_count": 0, "custom_count": 0,
            "download_success_count": 0, "download_failed_count": 0, "map_update_count": 0,
            "map_update_success_count": 0, "map_update_failed_count": 0}


def overview(*, now: str = "2026-10-07T10:00:00+00:00", since: str = "2026-10-06T10:00:00+00:00") -> dict:
    """One Dashboard snapshot; ``now`` only moves request-time values."""
    hour = now[:13]
    return {
        "period": "24h", "timeZone": "UTC", "since": since,
        "data": {
            "hasData": True, "eventCount": 3, "completedInstallCount": 2, "failedInstallCount": 1,
            "installSuccessRate": 66.7, "completedDownloadCount": 4, "failedDownloadCount": 0,
            "downloadSuccessRate": 100.0, "mapUpdateCount": 0, "completedMapUpdateCount": 0,
            "failedMapUpdateCount": 0, "allTimeSuccessCount": 20, "allTimeFailedCount": 2,
            "recentActivity": [
                {"event_id": "done", "event_type": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED",
                 "provider_id": "freizeitkarte", "display_name": "Germany", "occurred_at": "2026-10-07T09:00:00+00:00"},
                # In-progress downloads are not rendered on the Dashboard; their
                # stale flag is computed from now().
                {"event_id": "busy", "event_type": "DOWNLOAD_STARTED", "outcome": None,
                 "provider_id": "freizeitkarte", "occurred_at": "2026-10-07T08:00:00+00:00",
                 "is_stale": now >= "2026-10-07T10:30"},
            ],
            "attention": [], "missingDiagnosticFailures": [{"event_id": now}],
            "missingDiagnosticFailureCount": 1,
            "trend": [
                zero_bucket(f"{hour}:00:00+00:00"),  # current hour filler moves with the clock
                {**zero_bucket("2026-10-07T09:00:00+00:00"), "success_count": 2, "failed_count": 1},
            ],
            "bucket": "hour",
        },
        # Not rendered on the Dashboard.
        "compatibility": {"rows": [{"checked": now}]},
        "providers": [{"id": "freizeitkarte", "name": "Freizeitkarte", "health": "HEALTHY",
                       "lastCollectionAttempt": now, "lastCollectionFinished": now}],
        "mapsUnknown": {"modelCount": int(now[11:13])},
        "downloads": {"hasData": True, "dmgTotal": 10, "zipTotal": 2, "lastObservedAt": now, "bucket": "hour",
                      "trend": [{"bucket": f"{hour}:00:00+00:00", "state": "period_boundary", "uncertain": True,
                                 "dmg_count": 0, "zip_count": 0, "observed_at": now}]},
        "system": {"api": "HEALTHY", "database": "HEALTHY", "providers": [], "observations": []},
        "funnel": {"schemaVersion": 1, "period": "24h", "since": since, "until": now,
                   **_funnel(sessions=5, connected=4, no_usb=1, approved=3, pending=1)},
        "supportReports": {"openCount": 0},
    }


class DashboardRevisionTests(unittest.TestCase):
    def render(self, payload: dict) -> dict[str, str]:
        return revisions(overview_page(payload, USER, "csrf"))

    def test_same_displayed_data_at_two_times_has_the_same_revision(self):
        first = self.render(overview(now="2026-10-07T10:00:01.123456+00:00", since="2026-10-06T10:00:01.123456+00:00"))
        second = self.render(overview(now="2026-10-07T11:02:00.654321+00:00", since="2026-10-06T11:02:00.654321+00:00"))
        self.assertEqual(first, second)

    def test_first_run_window_bounds_alone_do_not_change_the_revision(self):
        payload = overview()
        later = copy.deepcopy(payload)
        later["funnel"]["until"] = "2026-10-07T10:02:00.000001+00:00"
        later["funnel"]["since"] = "2026-10-06T10:02:00.000001+00:00"
        self.assertEqual(self.render(payload)["funnel"], self.render(later)["funnel"])

    def test_displayed_changes_still_change_the_revision(self):
        base = self.render(overview())

        new_install = overview()
        new_install["data"]["completedInstallCount"] = 3
        new_install["data"]["trend"][1]["success_count"] = 3
        new_install["data"]["recentActivity"].insert(0, {
            "event_id": "new", "event_type": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED",
            "provider_id": "opentopomap", "display_name": "Austria", "occurred_at": "2026-10-07T09:58:00+00:00"})
        self.assertNotEqual(base["mapActivity"], self.render(new_install)["mapActivity"])

        new_session = overview()
        new_session["funnel"]["sessionCount"] = 6
        self.assertNotEqual(base["funnel"], self.render(new_session)["funnel"])

        never_connected = overview()
        never_connected["funnel"]["neverConnectedSessionCount"] = 2
        self.assertNotEqual(base["funnel"], self.render(never_connected)["funnel"])

        for stage, outcome in (("CATALOG", "REMOTE"), ("INSTALL_BLOCKED", "DEVICE_STORAGE")):
            shown = overview()
            for item in shown["funnel"]["stages"]:
                for row in item["outcomes"]:
                    if (item["stage"], row["outcome"]) == (stage, outcome):
                        row["sessionCount"] = 2
            self.assertNotEqual(base["funnel"], self.render(shown)["funnel"], stage)

        new_report = overview()
        new_report["supportReports"] = {"openCount": 1}
        self.assertNotEqual(base["supportReports"], self.render(new_report)["supportReports"])

        new_downloads = overview()
        new_downloads["downloads"]["dmgTotal"] = 11
        self.assertNotEqual(base["downloads"], self.render(new_downloads)["downloads"])

        review_payload = overview()
        user = {**USER, "admin_review_summary": {**REVIEW, "installationIssues": 3}}
        self.assertNotEqual(base["review"], revisions(overview_page(review_payload, user, "csrf"))["review"])

    def test_undisplayed_first_run_data_does_not_change_the_revision(self):
        # Waiting models are shown under their outcome row; a model whose
        # outcome has no row, the population text and zero trend buckets that
        # only move with the rolling window are not displayed data.
        payload = overview()
        payload["funnel"]["modelsNeedingReview"] = [
            {"baseModel": name, "outcome": "PENDING", "sessionCount": 1}
            for name in ("fenix 8", "Forerunner 965", "Venu X1")
        ]
        payload["funnel"]["trend"] = [
            {"bucket": "2026-10-10T08:00:00+00:00", "sessionCount": 0, "connectedSessionCount": 0},
            {"bucket": "2026-10-10T09:00:00+00:00", "sessionCount": 1, "connectedSessionCount": 1},
        ]
        hidden = copy.deepcopy(payload)
        hidden["funnel"]["modelsNeedingReview"].append({"baseModel": "Edge 1050", "outcome": "AMBIGUOUS", "sessionCount": 1})
        hidden["funnel"]["population"] = "changed description"
        hidden["funnel"]["trend"][0]["bucket"] = "2026-10-10T07:00:00+00:00"
        self.assertEqual(self.render(payload)["funnel"], self.render(hidden)["funnel"])
        shown = copy.deepcopy(payload)
        shown["funnel"]["modelsNeedingReview"][0]["catalogStatus"] = "NOT_IN_CATALOG"
        self.assertNotEqual(self.render(payload)["funnel"], self.render(shown)["funnel"])


class DashboardHttpRevisionTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CatalogService(CountingDatabase())))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get(self, path: str) -> str:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path, headers={"Cookie": COOKIE})
        body = connection.getresponse().read().decode()
        connection.close()
        return body

    def test_polling_an_unchanged_dashboard_returns_the_rendered_revision(self):
        # The real route computes First run with datetime.now() per request.
        for path in ("/admin", "/admin?period=7d", "/admin?period=all"):
            with self.subTest(path=path):
                self.assertEqual(revisions(self.get(path)), revisions(self.get(path)))


class RevisionCanonicalizationTests(unittest.TestCase):
    def test_zero_chart_buckets_are_not_activity(self):
        rows = [zero_bucket("2026-10-07T09:00:00Z"), {**zero_bucket("2026-10-07T10:00:00Z"), "failed_count": 1}]
        self.assertEqual(active_trend_buckets(rows), [rows[1]])

    def test_rolling_download_window_start_without_an_increase_is_not_new_data(self):
        def downloads(*points):
            return {"downloads": {"dmgTotal": 10, "zipTotal": 2, "trend": list(points)}}
        increase = {"bucket": "2026-10-07T05:00:00Z", "state": "observed_increase", "dmg_count": 1, "zip_count": 0}
        a = downloads({"bucket": "2026-10-06T10:00:00Z", "state": "period_boundary", "uncertain": True,
                       "dmg_count": 0, "zip_count": 0}, increase)
        b = downloads({"bucket": "2026-10-06T11:00:00Z", "state": "period_boundary", "uncertain": True,
                       "dmg_count": 0, "zip_count": 0}, increase)
        self.assertEqual(section_revisions(a), section_revisions(b))
        # The same increase reaching the window start is not a new fact either.
        c = downloads({**increase, "state": "period_boundary", "uncertain": True})
        self.assertEqual(section_revisions(downloads(increase)), section_revisions(c))
        # Leaving the window, or a new increase, changes what the card shows.
        self.assertNotEqual(section_revisions(downloads(increase)), section_revisions(downloads()))
        self.assertNotEqual(section_revisions(a), section_revisions(downloads(increase, {
            "bucket": "2026-10-07T09:00:00Z", "state": "observed_increase", "dmg_count": 2, "zip_count": 0})))

    def test_next_provider_check_time_is_a_schedule_clock(self):
        a = {"provider": {"health": "HEALTHY", "monitoring": {"intervalHours": 1, "stale": False,
                                                             "nextCheckAt": "2026-10-07T10:00:00+00:00"}}}
        b = copy.deepcopy(a)
        b["provider"]["monitoring"]["nextCheckAt"] = "2026-10-07T11:00:00+00:00"
        self.assertEqual(section_revisions(a), section_revisions(b))
        b["provider"]["monitoring"]["stale"] = True
        self.assertNotEqual(section_revisions(a), section_revisions(b))


class MapsRevisionTests(unittest.TestCase):
    def render(self, providers: list[dict], rows: list[dict]) -> dict[str, str]:
        return revisions(map_statistics_page({"rows": rows}, providers, USER, "csrf"))

    def test_provider_health_and_collection_clocks_do_not_change_maps(self):
        provider = {"id": "freizeitkarte", "name": "Freizeitkarte", "health": "HEALTHY",
                    "lastCollectionAttempt": "2026-10-06T03:00:00Z", "lastCatalogSync": "2026-10-06T03:00:00Z"}
        later = {**provider, "health": "DEGRADED", "lastCollectionAttempt": "2026-10-07T03:00:00Z",
                 "lastCatalogSync": "2026-10-07T03:00:00Z"}
        self.assertEqual(self.render([provider], []), self.render([later], []))
        self.assertNotEqual(self.render([provider], []), self.render([{**provider, "name": "FZK"}], []))

    def test_new_map_result_changes_maps(self):
        row = {"event_type": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED", "provider_id": "freizeitkarte",
               "map_package_id": "fzk-deu", "event_count": 1, "operation_count": 1}
        self.assertNotEqual(self.render([], [row])["statistics"],
                            self.render([], [{**row, "event_count": 2, "operation_count": 2}])["statistics"])


if __name__ == "__main__":
    unittest.main()

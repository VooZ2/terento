"""Dashboard redesign: period tiles, fixed Needs attention rows, First run and resilience."""

from __future__ import annotations

import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.admin import _funnel_card, _provider_problem_state, overview_page
from terento_catalog.http_api import CatalogService, make_handler


COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"
REVIEW = {
    "available": True, "installationIssues": 2, "githubIssuesInProgress": 1,
    "identityPending": 3, "readyToPublish": 0, "missingDiagnostics": 57,
}


def _funnel(**counts):
    return {
        "sessionCount": counts.get("sessions", 0),
        "stages": [
            {"stage": "DEVICE_CONNECT", "outcomes": [
                {"outcome": "CONNECTED", "sessionCount": counts.get("connected", 0)},
                {"outcome": "TIMEOUT_NO_USB", "sessionCount": counts.get("no_usb", 0)},
                {"outcome": "NOT_MTP_MODE", "sessionCount": counts.get("not_mtp", 0)},
            ]},
            {"stage": "AUTHORIZATION", "outcomes": [
                {"outcome": "APPROVED", "sessionCount": counts.get("approved", 0)},
                {"outcome": "PENDING", "sessionCount": counts.get("pending", 0)},
            ]},
        ],
        "modelsNeedingReview": counts.get("models", []),
    }


class DashboardPresentationTests(unittest.TestCase):
    def render(self, **overview):
        payload = {
            "period": "7d",
            "data": {
                "hasData": True, "completedInstallCount": 12, "failedInstallCount": 2,
                "installSuccessRate": 85.7, "completedMapUpdateCount": 4, "failedMapUpdateCount": 1,
                "mapUpdateCount": 5, "completedDownloadCount": 30, "failedDownloadCount": 3,
                "downloadSuccessRate": 90.9,
                "downloadPurposes": {
                    "install": {"succeeded": 20, "failed": 2},
                    "update": {"succeeded": 6, "failed": 0},
                    "unknown": {"succeeded": 4, "failed": 1},
                },
                "allTimeSuccessCount": 900, "allTimeFailedCount": 40, "allTimeInstallSuccessRate": 95.7,
                "allTimeMapUpdateSuccessCount": 80, "allTimeMapUpdateFailedCount": 2,
                "allTimeCompletedDownloadCount": 2000, "allTimeFailedDownloadCount": 50,
                "allTimeDownloadSuccessRate": 97.6,
                "recentActivity": [], "trend": [{
                    "bucket": "2026-10-01T00:00:00Z", "success_count": 10, "custom_count": 2,
                    "failed_count": 2, "map_update_success_count": 4, "map_update_failed_count": 1,
                    "download_success_count": 30, "download_failed_count": 3,
                }], "bucket": "day",
            },
            "compatibility": {}, "providers": [], "system": {},
            "funnel": _funnel(sessions=5, connected=4, no_usb=1, approved=3, pending=1,
                              models=[{"baseModel": "fenix 8", "outcome": "PENDING", "sessionCount": 1}]),
        }
        payload.update(overview)
        return overview_page(payload, {"username": "operator", "admin_review_summary": REVIEW}, "csrf").decode()

    def test_tiles_carry_period_totals_and_the_legend_names_series(self):
        body = self.render()
        tiles = body.split("aria-label='Dashboard summary'", 1)[1].split("overview-primary-grid", 1)[0]
        self.assertEqual(tiles.count("data-scope='period'>Last 7 days</span>"), 3)
        self.assertIn("data-stat='completedInstallCount'>12</strong>", tiles)
        self.assertIn("data-stat='completedMapUpdateCount'>4</strong>", tiles)
        self.assertIn("Failed 1</span> · 80%", tiles)
        # Installs card: tiles carry the period totals, so the legend names the
        # series and counts only the custom .img split no tile shows.
        installs = body.split("id='overview-trend-title'", 1)[1].split("</section>", 1)[0]
        legend = installs.split("<ul class='overview-chart-legend", 1)[1].split("</ul>", 1)[0]
        self.assertIn("<span>Install successful</span></li>", legend)
        self.assertIn("<span>Custom .img install</span><strong>2</strong>", legend)
        self.assertIn("<span>Update successful</span></li>", legend)
        self.assertIn("<span>Update failed</span></li>", legend)
        self.assertEqual(legend.count("<strong>"), 1)
        self.assertIn("data-scope='all'>All time</span>", installs)
        self.assertIn("Updates <strong>80</strong>", installs)
        self.assertEqual(installs.count("class='overview-all-time'"), 1)
        downloads = body.split("id='overview-download-trend-title'", 1)[1].split("</section>", 1)[0]
        legend = downloads.split("<ul class='overview-chart-legend", 1)[1].split("</ul>", 1)[0]
        self.assertNotIn("<strong>", legend)

    def test_all_time_lines_are_omitted_when_the_period_is_all_time(self):
        body = self.render(period="all")
        for card in ("overview-trend-title", "overview-download-trend-title"):
            section = body.split(f"id='{card}'", 1)[1].split("</section>", 1)[0]
            self.assertNotIn("class='overview-all-time'", section)

    def test_downloads_card_breaks_down_purpose(self):
        body = self.render()
        downloads = body.split("id='overview-download-trend-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("aria-label='Downloads by purpose'", downloads)
        self.assertIn("<dt>For installs</dt><dd>20", downloads)
        self.assertIn("<dt>For updates</dt><dd>6", downloads)
        self.assertIn("<dt>Not recorded</dt><dd>4", downloads)

    def test_needs_attention_has_nine_fixed_rows_and_a_total(self):
        body = self.render(supportReports={"openCount": 2}, mapsUnknown={"modelCount": 4})
        attention = body.split("id='overview-attention-title'", 1)[1].split("</section>", 1)[0]
        labels = ["Open problems", "GitHub issues", "Identity review", "Publication review",
                  "Missing reports", "Support reports", "Maps unknown", "Provider problems", "System checks"]
        self.assertEqual(attention.count("class='overview-attention-row'"), 9)
        positions = [attention.index(f"<span class='overview-attention-label'>{label}</span>") for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("aria-label='Missing reports: 57'", attention)
        self.assertIn("href='/admin/review/missing-reports'", attention)
        self.assertIn("href='/admin/installations?state=identity-pending'", attention)
        self.assertIn("data-state='zero'", attention)
        import re
        rows = [int(value) for value in re.findall(r"aria-label='[A-Za-z ]+: (\d+)'><svg", attention)]
        self.assertEqual(len(rows), 9)
        self.assertIn("aria-label='Maps unknown: 4'", attention)
        self.assertIn("href='/admin/devices?maps=unknown&amp;active=1'", attention)
        self.assertIn("aria-label='Support reports: 2'", attention)
        self.assertIn("href='/admin/support-reports'", attention)
        tiles = body.split("aria-label='Dashboard summary'", 1)[1].split("overview-primary-grid", 1)[0]
        # The tile total is exactly the sum of the rendered category rows.
        self.assertIn(f"aria-label='Needs attention, now: {sum(rows)}'", tiles)

    def test_first_run_card_shows_connected_failed_authorization_and_waiting_models(self):
        body = self.render()
        card = body.split("id='overview-funnel-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn(">First run</h2>", body)
        self.assertIn("data-scope='period'>Last 7 days</span>", card)
        self.assertIn(">5</strong>", card)
        # Each reason/outcome is a small bar with its label and count as text;
        # the bar width is the share of the period's first-run sessions.
        def bar(label, count, share):
            return (f"<li><span class='overview-funnel-label'>{label}</span>"
                    f"<span class='overview-funnel-bar' aria-hidden='true'><i style='width:{share:.1f}%'></i></span>"
                    f"<strong>{count}</strong><span class='sr-only'> of 5 sessions</span></li>")
        self.assertIn(bar("No USB", 1, 20), card)
        self.assertIn(bar("Approved", 3, 60) + bar("Pending", 1, 20), card)  # ordered by count
        self.assertIn(bar("fenix 8", 1, 20), card)
        for title in ("Not connected", "Authorization", "Waiting models"):
            self.assertIn(f"<h3>{title}</h3><ul class='overview-funnel-bars' aria-label='{title}'>", card)
        self.assertNotIn("Not in MTP mode", card)  # zero outcomes are not listed
        self.assertNotIn("<dl class='overview-funnel-breakdown'>", card)

    def test_first_run_card_states(self):
        self.assertIn("Could not load this section.", _funnel_card({"available": False}, "7d"))
        self.assertIn("No first-run sessions in this period.", _funnel_card(_funnel(), "7d"))

    def test_unavailable_map_snapshot_keeps_the_page_and_marks_sections(self):
        body = self.render(data={"available": False})
        self.assertIn("<h1>Dashboard</h1>", body)
        self.assertGreaterEqual(body.count("admin-card-unavailable"), 2)
        self.assertIn("data-stat='completedInstallCount'>—<span class='sr-only'>Unavailable</span>", body)
        self.assertNotIn("No map activity in this period.", body)

    def test_provider_problem_definition_is_shared_and_excludes_deliberate_states(self):
        self.assertFalse(_provider_problem_state({"status": "RETIRED", "health": "DOWN"})["problem"])
        self.assertFalse(_provider_problem_state({"status": "PAUSED", "health": "DOWN"})["problem"])
        degraded = _provider_problem_state({"status": "ACTIVE", "health": "DEGRADED", "affectedPackageCount": 0,
                                            "lastCollectionStatus": "SUCCEEDED",
                                            "lastCollectionSuccess": "2099-01-01T00:00:00Z", "latestRelease": "x"})
        self.assertTrue(degraded["problem"])
        packages = _provider_problem_state({"status": "ACTIVE", "health": "HEALTHY", "affectedPackageCount": 3,
                                            "lastCollectionStatus": "SUCCEEDED",
                                            "lastCollectionSuccess": "2099-01-01T00:00:00Z", "latestRelease": "x"})
        self.assertEqual(packages["reasons"], ["3 package problems"])
        unknown = _provider_problem_state({"status": "ACTIVE", "health": "HEALTHY", "affectedPackageCount": None,
                                           "lastCollectionStatus": "SUCCEEDED",
                                           "lastCollectionSuccess": "2099-01-01T00:00:00Z", "latestRelease": "x"})
        self.assertFalse(unknown["packagesKnown"])
        self.assertFalse(unknown["problem"])


class CountingDatabase(FakeProviderDatabase):
    def __init__(self) -> None:
        super().__init__()
        self.review_calls = 0
        self.fail_map = False
        self.missing_calls: list[tuple[int, int]] = []
        self.review_updates: list[tuple[str, str]] = []

    def admin_review_summary(self):
        self.review_calls += 1
        return dict(REVIEW)

    def admin_overview_map_snapshot(self, since, *, period="24h", time_zone="UTC"):
        if self.fail_map:
            raise RuntimeError("map snapshot unavailable")
        return super().admin_overview_map_snapshot(since, period=period, time_zone=time_zone)

    def app_funnel_summary(self, since, until=None, *, model_limit=10):
        return {"sessionCount": 2, "stages": [{"stage": "DEVICE_CONNECT", "outcome": "CONNECTED", "sessionCount": 2}],
                "modelsNeedingReview": []}

    def missing_diagnostic_failures(self, *, limit=50, offset=0):
        self.missing_calls.append((limit, offset))
        return {"rows": [{
            "event_type": "INSTALL_FAILED", "outcome": "FAILED",
            "event_id": "a8098c1a-f86e-11da-bd1a-00112444be1e", "provider_id": "freizeitkarte",
            "provider_name": "Freizeitkarte", "region": "France", "occurred_at": "2026-09-15T19:47:00Z",
        }], "total": 1, "limit": limit, "offset": offset}

    def set_missing_diagnostic_review(self, event_id, *, status, admin_user_id, note=None, request_id=None):
        self.review_updates.append((event_id, status))
        return True


class DashboardHttpTests(unittest.TestCase):
    def setUp(self):
        self.database = CountingDatabase()
        self.service = CatalogService(self.database)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, path, body=body, headers={"Cookie": COOKIE, **(headers or {})})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data.decode()

    def test_review_summary_is_computed_only_for_the_dashboard(self):
        response, _ = self.request("GET", "/admin/providers")
        self.assertEqual(response.status, 200)
        self.assertEqual(self.database.review_calls, 0)
        response, body = self.request("GET", "/admin?period=7d")
        self.assertEqual(response.status, 200)
        self.assertEqual(self.database.review_calls, 1)
        self.assertIn("aria-label='Open problems: 2'", body)

    def test_failing_map_snapshot_renders_unavailable_sections_not_json(self):
        self.database.fail_map = True
        with self.assertLogs("terento_catalog.http_api", level="ERROR"):
            response, body = self.request("GET", "/admin")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.headers["Content-Type"])
        self.assertIn("<h1>Dashboard</h1>", body)
        self.assertIn("Could not load this section.", body)
        self.assertIn(">App downloads</h2>", body)
        self.assertIn(">First run</h2>", body)

    def test_missing_reports_list_and_dismiss_return_to_the_list(self):
        response, body = self.request("GET", "/admin/review/missing-reports?offset=0")
        self.assertEqual(response.status, 200)
        self.assertIn("<h1>Missing reports</h1>", body)
        self.assertEqual(self.database.missing_calls, [(50, 0)])
        response, _ = self.request(
            "POST", "/admin/review/missing-diagnostics/dismiss",
            urlencode({"csrf_token": "csrf", "event_id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
                       "return_to": "/admin/review/missing-reports"}),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(response.status, 303)
        self.assertTrue(response.headers["Location"].startswith("/admin/review/missing-reports?reviewAction=dismissed"))
        response, _ = self.request(
            "POST", "/admin/review/missing-diagnostics/undo",
            urlencode({"csrf_token": "csrf", "event_id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
                       "return_to": "https://example.com/"}),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertTrue(response.headers["Location"].startswith("/admin?reviewAction=reopened"))
        response, body = self.request("GET", "/admin/review/missing-reports?offset=-1")
        self.assertEqual(response.status, 400)
        self.assertIn("text/html", response.headers["Content-Type"])


if __name__ == "__main__":
    unittest.main()

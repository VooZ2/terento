"""Dashboard redesign: period tiles, fixed Needs attention rows, First run and resilience."""

from __future__ import annotations

import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.admin import ADMIN_STYLES, _funnel_card, _provider_problem_state, overview_page
from terento_catalog.http_api import CatalogService, make_handler


COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"
REVIEW = {
    "available": True, "installationIssues": 2, "githubIssuesInProgress": 1,
    "identityPending": 3, "readyToPublish": 0, "missingDiagnostics": 57,
}


def _funnel(**counts):
    return {
        "sessionCount": counts.get("sessions", 0),
        "neverConnectedSessionCount": counts.get("never_connected", 0),
        "stages": [
            {"stage": "DEVICE_CONNECT", "outcomes": [
                {"outcome": "CONNECTED", "sessionCount": counts.get("connected", 0)},
                {"outcome": "TIMEOUT_NO_USB", "sessionCount": counts.get("no_usb", 0)},
                {"outcome": "NOT_MTP_MODE", "sessionCount": counts.get("not_mtp", 0)},
                {"outcome": "BUSY", "sessionCount": counts.get("busy", 0)},
            ]},
            {"stage": "AUTHORIZATION", "outcomes": [
                {"outcome": "APPROVED", "sessionCount": counts.get("approved", 0)},
                {"outcome": "PENDING", "sessionCount": counts.get("pending", 0)},
                {"outcome": "UPDATE_REQUIRED", "sessionCount": counts.get("auth_update", 0)},
            ]},
            {"stage": "CATALOG", "outcomes": [
                {"outcome": "REMOTE", "sessionCount": counts.get("remote", 0)},
                {"outcome": "BUNDLED_FALLBACK", "sessionCount": counts.get("bundled", 0)},
                {"outcome": "UPDATE_REQUIRED", "sessionCount": counts.get("catalog_update", 0)},
            ]},
            {"stage": "INSTALL_BLOCKED", "outcomes": [
                {"outcome": "AUTHORIZATION", "sessionCount": counts.get("blocked_authorization", 0)},
                {"outcome": "DEVICE_STORAGE", "sessionCount": counts.get("device_storage", 0)},
                {"outcome": "LOCAL_CAPABILITY", "sessionCount": counts.get("local_capability", 0)},
            ]},
        ],
        "modelsNeedingReview": counts.get("models", []),
    }


class DashboardPresentationTests(unittest.TestCase):
    def render(self, review=REVIEW, **overview):
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
            "funnel": _funnel(sessions=5, connected=4, never_connected=1, no_usb=1, approved=3, pending=1,
                              remote=4, catalog_update=1, device_storage=1,
                              models=[{"baseModel": "fenix 8", "outcome": "PENDING", "sessionCount": 1}]),
        }
        payload.update(overview)
        return overview_page(payload, {"username": "operator", "admin_review_summary": review}, "csrf").decode()

    def test_card_headers_carry_period_totals_and_the_legend_names_series(self):
        body = self.render()
        self.assertNotIn("Dashboard summary", body)
        self.assertNotIn("overview-tiles", body)
        installs = body.split("id='overview-trend-title'", 1)[1].split("</section>", 1)[0]
        head = installs.split("</header>", 1)[0]
        self.assertIn("data-scope='period'>Last 7 days</span>", head)
        self.assertIn("data-stat='completedInstallCount'>12</strong><small>Successful</small>", head)
        self.assertIn("data-stat='failedInstallCount'>", head)
        self.assertIn("<small>Success rate</small>", head)
        self.assertNotIn("admin-icon", head)
        # The header totals cover installs only, so the legend names the
        # series and counts the custom .img split and both update series.
        legend = installs.split("<ul class='overview-chart-legend", 1)[1].split("</ul>", 1)[0]
        for name in ("Install successful", "Custom .img install", "Install failed", "Update successful", "Update failed"):
            self.assertIn(f"<span>{name}</span></li>", legend)
        downloads = body.split("id='overview-download-trend-title'", 1)[1].split("</section>", 1)[0]
        for card in (installs, downloads):
            # Header totals, the chart and a count-free legend; nothing else.
            legend = card.split("<ul class='overview-chart-legend", 1)[1].split("</ul>", 1)[0]
            self.assertNotIn("<strong>", legend)
            self.assertNotIn("class='overview-all-time'", card)
            self.assertNotIn("Downloads by purpose", card)
            self.assertEqual(card.split("</ul>", 1)[1].replace("</div>", "").strip(), "")

    def test_needs_attention_lists_only_nonzero_rows_and_a_total(self):
        body = self.render(supportReports={"openCount": 2}, mapsUnknown={"modelCount": 4})
        attention = body.split("id='overview-attention-title'", 1)[1].split("</section>", 1)[0]
        labels = ["Open problems", "GitHub issues", "Identity review", "Missing reports", "Support reports"]
        self.assertEqual(attention.count("class='overview-attention-row'"), len(labels))
        positions = [attention.index(f"<span class='overview-attention-label'>{label}</span>") for label in labels]
        self.assertEqual(positions, sorted(positions))
        # A measured zero (Publication review) renders no row; Maps unknown and
        # Provider problems are not Needs attention rows, and System checks
        # appears only with failed or degraded Health checks (none here).
        for label in ("Publication review", "Maps unknown", "Provider problems", "System checks"):
            self.assertNotIn(f">{label}<", attention)
        self.assertNotIn("data-state='zero'", attention)
        self.assertIn("aria-label='Missing reports: 57'", attention)
        self.assertIn("href='/admin/review/missing-reports'", attention)
        self.assertIn("href='/admin/review/identity'", attention)
        import re
        rows = [int(value) for value in re.findall(r"aria-label='[A-Za-z ]+: (\d+)'><svg", attention)]
        self.assertEqual(len(rows), len(labels))
        self.assertIn("aria-label='Support reports: 2'", attention)
        self.assertIn("href='/admin/support-reports'", attention)
        head = attention.split("</header>", 1)[0]
        # The header total is exactly the sum of the rendered category rows.
        self.assertIn(f"data-stat='attentionTotal'>{sum(rows)}</strong><small>Total</small>", head)

    def test_needs_attention_with_nothing_open_says_so_without_rows(self):
        zero_review = {"available": True, "installationIssues": 0, "githubIssuesInProgress": 0,
                       "identityPending": 0, "readyToPublish": 0, "missingDiagnostics": 0}
        body = self.render(review=zero_review, supportReports={"openCount": 0})
        attention = body.split("id='overview-attention-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("Nothing to review.", attention)
        self.assertNotIn("overview-attention-row", attention)
        self.assertIn("data-stat='attentionTotal'>0</strong>", attention)

    def test_first_run_card_shows_tiles_and_per_stage_groups(self):
        body = self.render()
        card = body.split("id='overview-funnel-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn(">First run</h2>", body)
        self.assertIn("data-scope='period'>Last 7 days</span>", card)
        self.assertIn("<span class='admin-metric-label'>Sessions</span><strong class='admin-metric-value'>5</strong>", card)
        self.assertIn("<span class='admin-metric-label'>Connected</span><strong class='admin-metric-value'>4</strong>", card)
        self.assertIn("data-tone='danger'><span class='admin-metric-label'>Never connected</span>"
                      "<strong class='admin-metric-value'>1</strong>", card)
        self.assertNotIn("Not connected", card)
        # Each outcome is a small bar with its label and count as text; the bar
        # width is the share of the period's first-run sessions.
        def bar(label, count, share):
            return (f"<li><span class='overview-funnel-label'>{label}</span>"
                    f"<span class='overview-funnel-bar' aria-hidden='true'><i style='width:{share:.1f}%'></i></span>"
                    f"<strong>{count}</strong><span class='sr-only'> of 5 sessions</span></li>")
        self.assertIn(bar("No watch plugged in", 1, 20), card)
        self.assertIn(bar("Approved", 3, 60) + bar("Pending", 1, 20), card)  # ordered by count
        self.assertIn(bar("Loaded", 4, 80) + bar("App update required", 1, 20), card)
        self.assertIn(bar("Watch storage full", 1, 20), card)
        self.assertIn(bar("fenix 8", 1, 20), card)
        titles = ("Connection problems", "Authorization", "Catalog", "Install blocked", "Waiting models")
        for title in titles:
            self.assertIn(f"<h3>{title}</h3>", card)
            self.assertIn(f"<ul class='overview-funnel-bars' aria-label='{title}'>", card)
        self.assertEqual([card.index(f"<h3>{title}</h3>") for title in titles],
                         sorted(card.index(f"<h3>{title}</h3>") for title in titles))
        self.assertIn("<h3>Connection problems</h3><p class='overview-funnel-note muted-value'>"
                      "A session can hit several problems and still connect.</p>", card)
        for hidden in ("Not in file-transfer mode", "Watch in use by another app", "Built-in copy",
                       "Not allowed for this watch", "Watch not identified", "Update required<"):
            self.assertNotIn(hidden, card)  # zero outcomes are not listed
        self.assertNotIn("<dl class='overview-funnel-breakdown'>", card)
        # Owner 2026-10-07: beside App downloads a wide card shows the groups in
        # two balanced columns (a group is never split); labels keep their width.
        self.assertIn(".overview-funnel-panel{container:overview-funnel/inline-size}", ADMIN_STYLES)
        self.assertIn("@media(min-width:901px){@container overview-funnel (min-width:620px){", ADMIN_STYLES)
        self.assertIn(".overview-funnel-breakdown{display:block;columns:2;column-gap:24px}", ADMIN_STYLES)
        self.assertIn(".overview-funnel-group{display:block;break-inside:avoid;padding-bottom:12px}", ADMIN_STYLES)
        self.assertIn(".overview-funnel-bars{grid-template-columns:minmax(0,max-content) minmax(24px,1fr) minmax(24px,auto);", ADMIN_STYLES)
        # One column: one aligned label column for every group; the bar shrinks first.
        self.assertIn(".overview-funnel-breakdown{display:grid;grid-template-columns:minmax(0,max-content) minmax(24px,1fr) minmax(24px,auto);", ADMIN_STYLES)
        self.assertIn(".overview-funnel-bars li{display:grid;grid-template-columns:subgrid;grid-column:1/-1;", ADMIN_STYLES)
        # Owner 2026-10-07: the three First run tiles stay on one row at every
        # width with numbers on one baseline; other metric rows keep auto-fit.
        self.assertIn("<div class='admin-metric-row overview-funnel-metrics' role='group' aria-label='First run sessions'>", card)
        self.assertIn(".overview-funnel-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}", ADMIN_STYLES)
        self.assertIn(".overview-funnel-metrics .admin-metric-value{margin-top:auto}", ADMIN_STYLES)
        self.assertIn(".admin-metric-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));", ADMIN_STYLES)

    def test_one_card_kpi_rows_fit_two_rows_on_phones(self):
        # Owner 2026-10-07: at <=760 px a one-card KPI row uses three columns
        # for five or three tiles and two for four or two; labels and values
        # share subgrid rows so numbers keep one baseline; long values wrap.
        self.assertIn("@media(max-width:760px){\n  :is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row{", ADMIN_STYLES)
        row = ":is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row"
        for declaration in (
            row + "{grid-template-columns:repeat(3,minmax(min-content,1fr));row-gap:0}",
            row + ":has(>:nth-child(2):last-child,>:nth-child(4):last-child){grid-template-columns:repeat(2,minmax(min-content,1fr))}",
            row + ">.admin-metric{display:grid;grid-row:span 3;grid-template-rows:subgrid;",
            row + " .admin-metric-label{align-self:start}",
            row + " .admin-metric-value{flex-wrap:wrap;",
        ):
            self.assertIn(declaration, ADMIN_STYLES)
        # The provider detail card no longer has its own 2 + 2 + 1 phone layout.
        self.assertNotIn(".provider-kpis>.admin-metric-row>:last-child:nth-child(odd){grid-column:1/-1}", ADMIN_STYLES)
        self.assertNotIn(".provider-kpis>.admin-metric-row{grid-template-columns:repeat(2,minmax(0,1fr))}", ADMIN_STYLES)
        # Quick-filter groups wrap on phones instead of scrolling sideways.
        self.assertIn(".quick-filter-group{min-width:0;max-width:100%;display:flex;flex-wrap:wrap;overflow-x:visible;flex-basis:100%}", ADMIN_STYLES)
        self.assertNotIn("flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain", ADMIN_STYLES)

    def test_first_run_card_states(self):
        self.assertIn("Could not load this section.", _funnel_card({"available": False}, "7d"))
        self.assertIn("No first-run sessions in this period.", _funnel_card(_funnel(), "7d"))

    def test_never_connected_tile_is_the_session_count_not_the_sum_of_problems(self):
        # Owner 2026-10-07: 12 sessions, 8 connected; problem rows overlap and
        # their sum (19) exceeded the sessions. The tile is the API's distinct
        # never-connected count; failure tone only above zero.
        card = _funnel_card(_funnel(sessions=12, connected=8, never_connected=4, no_usb=9, not_mtp=6,
                                    busy=4), "24h")
        self.assertIn("<span class='admin-metric-label'>Never connected</span>"
                      "<strong class='admin-metric-value'>4</strong>", card)
        self.assertNotIn(">19<", card)
        self.assertIn("<span class='overview-funnel-label'>No watch plugged in</span>", card)
        self.assertIn("<span class='overview-funnel-label'>Not in file-transfer mode</span>", card)
        self.assertIn("<span class='overview-funnel-label'>Watch in use by another app</span>", card)
        self.assertLess(card.index("No watch plugged in"), card.index("Not in file-transfer mode"))
        for title in ("Catalog", "Install blocked"):
            group = card.split(f"<h3>{title}</h3>", 1)[1].split("</ul>", 1)[0]
            self.assertIn("overview-funnel-none", group)  # empty groups show "—"
        all_connected = _funnel_card(_funnel(sessions=3, connected=3, never_connected=0, remote=3,
                                             blocked_authorization=1, local_capability=2), "24h")
        self.assertIn("data-tone='neutral'><span class='admin-metric-label'>Never connected</span>"
                      "<strong class='admin-metric-value'>0</strong>", all_connected)
        self.assertNotIn("overview-funnel-note", all_connected)  # no problems, no note
        self.assertIn("<span class='overview-funnel-label'>Watch not identified</span>", all_connected)
        self.assertIn("<span class='overview-funnel-label'>Not allowed for this watch</span>", all_connected)

    def test_unavailable_map_snapshot_keeps_the_page_and_marks_sections(self):
        body = self.render(data={"available": False})
        self.assertIn("<h1>Dashboard</h1>", body)
        self.assertGreaterEqual(body.count("admin-card-unavailable"), 2)
        # Unavailable charts show no header totals rather than zeros.
        self.assertNotIn("data-stat='completedInstallCount'", body)
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
        return {"sessionCount": 2, "neverConnectedSessionCount": 0,
                "stages": [{"stage": "DEVICE_CONNECT", "outcome": "CONNECTED", "sessionCount": 2}],
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

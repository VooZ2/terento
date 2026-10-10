"""Dashboard redesign: period tiles, fixed Needs attention rows, First run and resilience."""

from __future__ import annotations

import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from api_test_fixtures import FakeProviderDatabase
from terento_catalog.admin import (
    ADMIN_STYLES, _overview_period_script, _provider_problem_state, first_run_page, overview_page,
)
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
        **({"journey": {"sessionCount": counts.get("sessions", 0),
                        "connectedSessionCount": counts.get("connected", 0),
                        "approvedSessionCount": counts["journey_approved"]}}
           if "journey_approved" in counts else {}),
        **({"neverConnected": counts["never"]} if "never" in counts else {}),
        **({"previous": counts["previous"]} if "previous" in counts else {}),
        **({"trend": counts["trend"], "bucket": counts.get("bucket", "hour")} if "trend" in counts else {}),
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
            # After the App chart only the hidden Web panel follows (App/Web switch).
            rest = card.split("</ul>", 1)[1].replace("</div>", "").strip()
            self.assertTrue(rest.startswith("<div data-source-panel='web' hidden>"), rest[:80])

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

    FIRST_RUN = dict(
        sessions=5, connected=4, never_connected=1, no_usb=1, approved=3, pending=1, remote=4,
        catalog_update=1, device_storage=1, journey_approved=3,
        models=[{"baseModel": "fenix 8", "outcome": "PENDING", "sessionCount": 1,
                 "catalogStatus": "NOT_IN_CATALOG"}],
        never={"sessionCount": 1, "withoutConnectionSignalCount": 0,
               "outcomes": [{"outcome": "TIMEOUT_NO_USB", "sessionCount": 1}]},
        previous={"sessionCount": 3, "connectedSessionCount": 4, "approvedSessionCount": 3},
    )

    def test_dashboard_first_run_shows_totals_and_what_was_lost(self):
        # Owner 2026-10-10 (second pass): the card says whether First run is
        # worth opening: journey totals in the header, one Needs attention
        # style row per loss with its most common reason, each linking to its
        # card on First run, and the previous period in one muted line.
        body = self.render(funnel=_funnel(**self.FIRST_RUN))
        card = body.split("id='overview-funnel-title'", 1)[1].split("</section>", 1)[0]
        head = card.split("</header>", 1)[0]
        self.assertIn("<a class='admin-card-action section-link' href='/admin/first-run?period=7d'>View all", head)
        for value, noun in (("5", "Opened"), ("4", "Connected"), ("3", "Allowed")):
            self.assertIn(f"<span class='overview-card-total'><strong>{value}</strong><small>{noun}</small></span>", head)
        self.assertIn("<a href='/admin/first-run?period=7d#first-run-not-connected' "
                      "aria-label='Never connected: 1. Mostly: No watch plugged in (1)'>", card)
        self.assertIn("<span class='overview-attention-label'>Never connected"
                      "<small class='funnel-hint'>Mostly: No watch plugged in (1)</small></span><strong>1</strong>", card)
        self.assertIn("<span class='overview-attention-label'>Connected but not allowed"
                      "<small class='funnel-hint'>Mostly: Pending (1)</small></span><strong>1</strong>", card)
        self.assertIn("href='/admin/first-run?period=7d#first-run-models'", card)
        self.assertIn("<span class='overview-attention-label'>Waiting models"
                      "<small class='funnel-hint'>fenix 8</small></span><strong>1</strong>", card)
        self.assertIn("<p class='admin-card-note muted-value'>Previous 7 days: 3 opened · 4 connected · 3 allowed</p>", card)
        for detail in ("Sessions over time", "Connection problems", "admin-metric", "<table"):
            self.assertNotIn(detail, card)
        self.assertIn('<a href="/admin/first-run">First run</a>', body)

    def test_dashboard_first_run_names_at_most_three_waiting_models(self):
        models = [{"baseModel": f"model {index}", "outcome": "PENDING", "sessionCount": index}
                  for index in range(1, 6)]
        body = self.render(funnel=_funnel(**{**self.FIRST_RUN, "models": models}))
        card = body.split("id='overview-funnel-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("Waiting models<small class='funnel-hint'>model 5, model 4, model 3 +2 more</small></span>"
                      "<strong>5</strong>", card)

    def test_dashboard_first_run_without_losses_says_so(self):
        body = self.render(funnel=_funnel(sessions=3, connected=3, never_connected=0, approved=3,
                                          journey_approved=3, remote=3))
        card = body.split("id='overview-funnel-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("Every session connected and was allowed to install.", card)
        self.assertNotIn("overview-attention-row", card)
        self.assertNotIn("Previous", card)  # no previous window reported

    def test_first_run_page_has_the_period_picker_and_active_nav(self):
        body = first_run_page(_funnel(**self.FIRST_RUN), {"username": "operator"}, "csrf", period="nope").decode()
        self.assertIn("<h1>First run</h1>", body)
        self.assertIn("id='overview-period-form' method='get' action='/admin/first-run'", body)
        self.assertIn("<option value='24h' selected>", body)  # unknown period falls back to 24 h
        self.assertIn('<a class=\'active\' href="/admin/first-run">First run</a>', body)
        self.assertIn("getAttribute('action') || '/admin'", body)
        self.assertIn("data-admin-revisions=", body)
        unavailable = first_run_page({"available": False}, {"username": "operator"}, "csrf", period="7d").decode()
        self.assertIn("id='overview-funnel'", unavailable)
        self.assertIn("Could not load this section.", unavailable)
        self.assertIn("href='/admin/first-run?period=7d'>Retry", unavailable)
        empty = first_run_page(_funnel(), {"username": "operator"}, "csrf", period="7d").decode()
        self.assertIn("No first-run sessions in this period.", empty)
        self.assertNotIn("admin-metric-row", empty)

    def test_first_run_page_follows_the_admin_page_structure(self):
        # Owner 2026-10-10: the page reads like the other Admin pages: journey
        # tiles, Sessions over time, then one heading per topic with its cards
        # (Admin tables) in a two-column grid.
        body = first_run_page(_funnel(**self.FIRST_RUN), {"username": "operator"}, "csrf", period="7d").decode()
        main = body.split("<main", 1)[1].split("</main>", 1)[0]
        tiles = main.split("<div class='admin-metric-row' role='group' aria-label='First run journey'>", 1)[1].split(
            "<h2 class='web-installer-part'>", 1)[0]
        self.assertEqual(tiles.count("class='admin-metric'"), 5)
        for label in ("Opened app", "Watch connected", "Install allowed", "Never connected", "Not allowed"):
            self.assertIn(f"<span class='admin-metric-label'>{label}</span>", tiles)
        self.assertIn("80% of opened · <span class='funnel-delta'", tiles)
        self.assertIn("75% of connected · <span class='funnel-delta'", tiles)
        self.assertIn("<span aria-hidden='true'>▲</span> +2 vs previous 7 days</span>", tiles)
        self.assertIn("<span aria-hidden='true'>=</span> Same as previous 7 days</span>", tiles)
        self.assertIn("data-tone='danger'", tiles)  # measured losses above zero
        headings = ["Connecting the watch", "Install permission", "Maps"]
        cards = ["Why not connected", "Connection problems", "Permission check", "Waiting models",
                 "Map list", "Install blocked"]
        positions = [main.index(f"<h2 class='web-installer-part'>{title}</h2>") for title in headings]
        self.assertEqual(positions, sorted(positions))
        card_positions = [main.index(f"-title'>{title}</h2>") for title in cards]
        self.assertEqual(card_positions, sorted(card_positions))
        self.assertLess(positions[0], card_positions[0])
        self.assertLess(card_positions[1], positions[1])
        self.assertEqual(main.count("<div class='web-installer-grid'>"), 3)
        self.assertNotIn("<h3>", main)

        def card(card_id):
            return main.split(f"id='{card_id}'", 1)[1].split("</section>", 1)[0]

        def row(label, count, share, hint="", of="of sessions"):
            hint = f"<small class='funnel-hint'>{hint}</small>" if hint else ""
            return (f"<tr><td>{label}{hint}</td><td class='column-number'>{count}</td>"
                    f"<td class='column-number'>{share}<span class='sr-only'> {of}</span></td></tr>")
        self.assertIn(row("No watch plugged in", 1, "100%", of="of never-connected sessions"),
                      card("first-run-not-connected"))
        self.assertIn("<th scope='col'>Result</th><th scope='col' class='column-number'>Sessions</th>"
                      "<th scope='col' class='column-number'>Share</th>", card("first-run-connection"))
        self.assertIn(row("No watch plugged in", 1, "20%"), card("first-run-connection"))
        self.assertIn("<p class='admin-card-note muted-value'>Every session, including those that connected later.</p>",
                      card("first-run-connection"))
        permission = card("first-run-permission")
        self.assertIn(row("Approved", 3, "60%") + row(
            "Pending", 1, "20%", "Model not in the catalog, or its Maps value is unknown or mixed"), permission)
        self.assertIn("<tr><td><a href='/admin/devices?search=fenix+8'>fenix 8</a></td><td>Pending</td>"
                      "<td>Not in catalog</td><td class='column-number'>1</td></tr>", card("first-run-models"))
        self.assertIn(row("Loaded", 4, "80%"), card("first-run-catalog"))
        self.assertIn(row("Watch storage full", 1, "20%"), card("first-run-blocked"))
        for hidden in ("Not in file-transfer mode", "Watch in use by another app", "Built-in copy",
                       "Not allowed for this watch", "Watch not identified", "Update required<"):
            self.assertNotIn(hidden, main)  # zero outcomes are not listed

    def test_first_run_sessions_over_time_is_focusable_and_textual(self):
        trend = [
            {"bucket": "2026-10-10T08:00:00+00:00", "sessionCount": 2, "connectedSessionCount": 1},
            {"bucket": "2026-10-10T09:00:00+00:00", "sessionCount": 0, "connectedSessionCount": 0},
            {"bucket": "2026-10-10T10:00:00+00:00", "sessionCount": 4, "connectedSessionCount": 4},
        ]
        page = first_run_page(_funnel(sessions=6, connected=5, never_connected=1, trend=trend),
                              {"username": "operator"}, "csrf", period="24h").decode()
        card = page.split("id='first-run-trend'", 1)[1].split("</section>", 1)[0]
        self.assertIn(">Sessions over time</h2>", card)
        self.assertIn("<li tabindex='0' aria-label='08:00: 2 sessions, 1 connected, 1 never connected'", card)
        self.assertIn("<span class='funnel-trend-never' style='height:25.0%'></span>"
                      "<span class='funnel-trend-connected' style='height:25.0%'></span>", card)
        self.assertIn("<span class='funnel-trend-connected' style='height:100.0%'></span>", card)
        self.assertIn("<span>Connected</span>", card)
        self.assertIn("<span>Never connected</span>", card)
        # One bucket draws no card.
        one = first_run_page(_funnel(sessions=1, connected=1, trend=trend[:1]), {"username": "operator"}, "csrf",
                             period="24h").decode()
        self.assertNotIn("Sessions over time", one)

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

    def test_never_connected_is_the_session_count_not_the_sum_of_problems(self):
        # Owner 2026-10-07: 12 sessions, 8 connected; problem rows overlap and
        # their sum (19) exceeded the sessions. The loss is the API's distinct
        # never-connected count.
        page = first_run_page(_funnel(sessions=12, connected=8, never_connected=4, no_usb=9, not_mtp=6, busy=4),
                              {"username": "operator"}, "csrf", period="24h").decode()
        self.assertIn("<span class='admin-metric-label'>Never connected</span>"
                      "<strong class='admin-metric-value'>4</strong>", page)
        self.assertNotIn(">19<", page)
        connection = page.split("id='first-run-connection'", 1)[1].split("</section>", 1)[0]
        self.assertLess(connection.index("No watch plugged in"), connection.index("Not in file-transfer mode"))
        self.assertIn("Watch in use by another app", connection)
        # Older payload: no never-connected breakdown, so that card says so.
        self.assertIn("Every session connected a watch.",
                      page.split("id='first-run-not-connected'", 1)[1].split("</section>", 1)[0])
        for card_id in ("first-run-catalog", "first-run-blocked"):
            self.assertIn("Nothing in this period.", page.split(f"id='{card_id}'", 1)[1].split("</section>", 1)[0])
        all_connected = first_run_page(_funnel(sessions=3, connected=3, never_connected=0, remote=3,
                                               blocked_authorization=1, local_capability=2),
                                       {"username": "operator"}, "csrf", period="24h").decode()
        self.assertNotIn("admin-card-note", all_connected.split("id='first-run-not-connected'", 1)[1].split("</section>", 1)[0])
        self.assertIn("<td>Watch not identified</td>", all_connected)
        self.assertIn("<td>Not allowed for this watch<small class='funnel-hint'>"
                      "Install was refused because the watch was not approved</small></td>", all_connected)
        # The never-connected breakdown counts only those sessions, including
        # ones that closed before any connection signal.
        explained = first_run_page(_funnel(sessions=6, connected=2, never_connected=4, no_usb=5, never={
            "sessionCount": 4, "withoutConnectionSignalCount": 1,
            "outcomes": [{"outcome": "TIMEOUT_NO_USB", "sessionCount": 2}, {"outcome": "BUSY", "sessionCount": 1}],
        }), {"username": "operator"}, "csrf", period="24h").decode()
        group = explained.split("id='first-run-not-connected'", 1)[1].split("</section>", 1)[0]
        self.assertIn("Sessions that never connected; one can show several signals.", group)
        self.assertLess(group.index("No watch plugged in"), group.index("Closed before any watch signal"))
        self.assertIn("<td class='column-number'>25%<span class='sr-only'> of never-connected sessions</span></td>", group)

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

    def app_funnel_summary(self, since, until=None, *, model_limit=10, **_):
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

    def test_first_run_page_route(self):
        response, body = self.request("GET", "/admin/first-run?period=7d")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.headers["Content-Type"])
        self.assertIn("<h1>First run</h1>", body)
        self.assertIn("aria-label='First run journey'", body)
        self.assertEqual(self.database.review_calls, 0)
        response, body = self.request("GET", "/admin/first-run?period=bogus")
        self.assertEqual(response.status, 200)
        self.assertIn("<option value='24h' selected>", body)

    def test_saved_time_zone_cookie_is_the_default_so_the_page_is_built_once(self):
        # Nav links carry no timeZone; the zone the script saved renders the
        # page directly instead of a UTC render plus a client refetch (audit #10).
        zone_cookie = {"Cookie": COOKIE + "; terento_admin_tz=Europe/Vilnius"}
        for path, zone in (("/admin", "Europe/Vilnius"), ("/admin?timeZone=Asia%2FTokyo", "Asia/Tokyo")):
            _, body = self.request("GET", path, headers=zone_cookie)
            self.assertEqual(self.database.overview_map_requests[-1][2], zone, path)
            self.assertIn(f"action='/admin' data-time-zone='{zone}'", body)
        _, body = self.request("GET", "/admin/first-run", headers=zone_cookie)
        self.assertIn("action='/admin/first-run' data-time-zone='Europe/Vilnius'", body)
        _, body = self.request("GET", "/admin", headers={"Cookie": COOKIE + "; terento_admin_tz=Mars/Base"})
        self.assertEqual(self.database.overview_map_requests[-1][2], "UTC")
        script = _overview_period_script()
        self.assertIn("document.cookie = `terento_admin_tz=${timeZone}; Path=/admin; SameSite=Strict; Secure`", script)
        self.assertIn("if (renderedTimeZone !== timeZone) load(period, false, timeZone);", script)

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

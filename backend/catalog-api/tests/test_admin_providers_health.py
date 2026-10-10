"""Providers, provider detail and Health simplifications keep every capability."""

from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta, timezone

from admin_test_utils import metric_tone, metric_value, visible_text
from terento_catalog.admin import ADMIN_STYLES, _system_health_cards, overview_page, provider_detail_page, providers_page, system_health_page


def _package(index: int, *, reason: str = "Download unavailable", broken: bool = True) -> dict:
    return {
        "id": f"bbbike-region-{index}", "name": f"Region {index}", "release": "2026-09-30",
        "availability": "UNAVAILABLE" if broken else "AVAILABLE", "artifact_count": 1,
        "broken_artifact_count": 1 if broken else 0,
        "artifacts": [{
            "kind": "main", "validation_status": "FAILED" if broken else "VALIDATED",
            "source_url": f"https://download.bbbike.org/region-{index}.zip",
            "last_check": {"message": reason, "nextAction": "Recheck later.", "checkedAt": "2026-10-01T10:00:00Z"} if broken else {},
        }],
    }


class ProviderDetailTests(unittest.TestCase):
    def render(self, packages):
        return provider_detail_page(
            {"provider": {"id": "bbbike", "name": "BBBike", "status": "ACTIVE", "healthStatus": "DEGRADED",
                          "maps": packages, "affectedPackageCount": sum(p["broken_artifact_count"] for p in packages)}},
            [], [], {"username": "operator"}, "csrf",
        ).decode()

    def test_problems_are_grouped_by_reason_with_a_preview_of_five(self):
        packages = [_package(index) for index in range(8)] + [_package(8, reason="Source date missing")]
        packages.append(_package(9, broken=False))
        body = self.render(packages)
        problems = body.split("id='provider-problems-title'", 1)[1].split("id='provider-packages'", 1)[0]
        self.assertTrue(problems.startswith(">Issues</h2>"))
        self.assertEqual(problems.count("class='provider-problem-group'"), 2)
        self.assertIn(">8 packages</span>", problems)
        self.assertIn(">Download unavailable</span>", problems)
        # Preview is capped at five rows per group, with a link to the full list.
        self.assertEqual(problems.count("<li class='provider-problem'>"), 6)
        self.assertIn("Show all 8 in Packages", problems)
        self.assertIn("data-show-problems", problems)
        # A single-package group rechecks that package; a larger group says what it does.
        self.assertIn("data-package-id='bbbike-region-8'>Recheck</button>", problems)
        self.assertIn(">Recheck affected</button>", problems)
        self.assertIn(">Recheck affected packages</button>", problems)
        self.assertIn("BBBike · Main map", problems)
        self.assertNotIn("Bbbike", body)
        self.assertNotIn("Installation availability", body)

    def test_packages_is_one_list_with_a_row_menu_and_problems_preselected(self):
        body = self.render([_package(0), _package(1, broken=False)])
        packages = body.split("id='provider-packages'", 1)[1]
        self.assertIn("<option value='broken' selected>Issues</option>", packages)
        self.assertEqual(packages.count("class='provider-row-menu'"), 2)
        self.assertIn("aria-label='Actions for ", packages)
        self.assertIn("data-provider-action='downloads'", packages)
        self.assertIn(">Disable downloads</button>", packages)
        self.assertIn("data-provider-action='rechecks'", packages)

    def test_summary_is_one_card_and_the_page_says_issues(self):
        body = self.render([_package(0)])
        main = body.split("<main", 1)[1]
        # One KPI card holding every tile, like Installations (owner decision 2026-10-06).
        self.assertEqual(main.count("class='admin-metric-row"), 1)
        summary = main.split("<section class='admin-card installation-kpis provider-kpis' aria-label='Provider summary'>", 1)[1].split("</section>", 1)[0]
        for label in ("Health", "Catalog", "Package issues", "Downloads", "Previews"):
            self.assertIn(f"<span class='admin-metric-label'>{label}</span>", summary)
            self.assertIsNotNone(metric_value(body, label), label)
        self.assertNotIn("admin-scope-chip", summary)
        self.assertEqual(metric_value(body, "Package issues"), "1")
        self.assertEqual(metric_value(body, "Previews"), "Off")
        # The page says Issues; the "Problems" wording stays on other pages.
        self.assertIn(">Issues</h2>", main)
        self.assertNotIn(">Problems</h2>", main)
        self.assertNotIn("Package problems", main)
        self.assertIn("aria-labelledby='provider-problems-title'", main)

    def test_previews_switch_lives_in_the_action_bar_as_a_secondary_action(self):
        body = self.render([_package(0)])
        bar = body.split("<section class='provider-action-bar'", 1)[1].split("</section>", 1)[0]
        self.assertIn(
            "<button type='button' class='secondary-button' data-provider-action='previews' data-provider-id='bbbike' data-previews-enabled='true'>Turn previews on</button>",
            bar,
        )
        # Interactive Primary stays on the main action only.
        self.assertEqual(bar.count("<button type='button' class=''"), 1)
        self.assertIn("data-provider-action='check'", bar.split("<button type='button' class=''", 1)[1].split("</button>", 1)[0])
        self.assertNotIn("aria-label='Map style previews'", body)
        self.assertNotIn(">Map style previews</h2>", body)
        retired = provider_detail_page(
            {"provider": {"id": "bbbike", "name": "BBBike", "status": "RETIRED", "previews": {"enabled": True, "layers": []}}},
            [], [], {"username": "operator"}, "csrf",
        ).decode()
        self.assertIn("data-previews-enabled='false' disabled>Turn previews off</button>", retired)

    def test_rarely_needed_lists_share_one_collapsed_technical_details_card(self):
        body = self.render([_package(0)])
        main = body.split("<main", 1)[1]
        technical = main.split("id='provider-technical-details'", 1)[1]
        self.assertIn("<details class='provider-technical-disclosure' id='provider-technical-disclosure'><summary>", technical)
        self.assertNotIn("id='provider-technical-disclosure' open", technical)
        self.assertIn("role='tablist' aria-label='Technical details sections'", technical)
        for key, panel in (("history", "provider-history"), ("health", "provider-health-history"),
                           ("syncs", "provider-collection-history"), ("previews", "provider-preview-layers"),
                           ("attribution", "provider-attribution")):
            self.assertIn(f"data-technical-tab='{key}' aria-controls='{panel}'", technical)
            self.assertIn(f"role='tabpanel' id='{panel}'", technical)
        # Releases sits with Syncs; Original links with Attribution.
        self.assertIn(">Releases</h3>", technical.split("id='provider-collection-history'", 1)[1].split("role='tabpanel'", 1)[0])
        self.assertIn(">Original links</h3>", technical.split("id='provider-attribution'", 1)[1])
        # Only the first panel is visible; no half-width grid of disclosures remains.
        self.assertEqual(technical.count("role='tabpanel'"), technical.count("tabindex='0' hidden>") + 1)
        self.assertNotIn("provider-technical-grid", main)
        self.assertNotIn("provider-technical-section", main)
        # Checks and Syncs keep their latest summary and link to their history.
        self.assertIn("data-technical-open='health'", main)
        self.assertIn("data-technical-open='syncs'", main)
        self.assertIn("<summary>View check details</summary>", main)

    def test_long_release_change_lists_are_truncated_but_reachable(self):
        packages = [{"region": f"Region {n}", "previousRelease": "2026-08", "release": "2026-09"} for n in range(200)]
        body = provider_detail_page(
            {"provider": {"id": "bbbike", "name": "BBBike", "status": "ACTIVE", "maps": []}}, [],
            [{"action": "CATALOG_RELEASES_UPDATED", "reason": "200 map releases changed during catalog collection",
              "details": {"packages": packages}, "occurred_at": "2026-09-16T10:20:00Z"}],
            {"username": "operator"}, "csrf",
        ).decode()
        history = body.split("id='provider-history'", 1)[1].split("<div class='provider-technical-panel'", 1)[0]
        visible = history.split("<ul class='catalog-release-changes'>", 1)[1].split("</ul>", 1)[0]
        self.assertEqual(visible.count("<li>"), 3)
        self.assertIn("<summary>+197 more</summary>", history)
        self.assertIn("Region 199: 2026-08 → 2026-09", history)
        self.assertIn("<tbody data-row-limit='5'>", history)
        self.assertIn("class='provider-reason-cell'", history)

    def test_health_interval_is_one_native_control_row(self):
        from terento_catalog.admin import ADMIN_STYLES
        body = self.render([_package(0)])
        schedule = body.split("<div class='provider-health-schedule'>", 1)[1].split("</div>", 1)[0]
        self.assertIn("<label for='provider-health-interval'>Automatic health checks</label><select id='provider-health-interval'>", schedule)
        self.assertNotIn("data-admin-dropdown", schedule)
        self.assertIn(">Save interval</button>", schedule)
        self.assertIn(".provider-health-schedule select,.provider-health-schedule button{box-sizing:border-box;height:var(--admin-control-height);min-height:var(--admin-control-height);margin:0}", ADMIN_STYLES)

    def test_no_problems_shows_an_empty_state(self):
        body = self.render([_package(0, broken=False)])
        self.assertIn("No known package issues.", body)
        self.assertNotIn(">Recheck affected packages</button>", body)


class ProvidersListTests(unittest.TestCase):
    def _page(self, providers):
        return providers_page(providers, {"username": "operator"}, "csrf").decode()

    def test_issues_cell_is_plain_number_with_numeric_sort_value(self):
        # Owner decision 2026-10-06: Issues looks like the zero cells, no pill or icon.
        body = self._page([
            {"id": "a", "name": "A", "status": "ACTIVE", "health": "HEALTHY", "packageCount": 3,
             "affectedPackageCount": 0, "problematicSourceCount": 0},
            {"id": "b", "name": "B", "status": "ACTIVE", "health": "DEGRADED", "packageCount": 3,
             "affectedPackageCount": 2, "problematicSourceCount": 2},
            {"id": "c", "name": "C", "status": "ACTIVE", "health": "HEALTHY", "packageCount": None,
             "affectedPackageCount": None, "problematicSourceCount": None},
        ])
        rows = body.split("<tbody id='provider-rows'>", 1)[1].split("</tbody>", 1)[0].split("</tr>")[:3]
        zero, positive, unknown = (row.split("</td>")[4].rsplit("<td", 1)[1] for row in rows)
        self.assertIn("class='column-number numeric' data-sort-value='0'>", zero)
        self.assertIn("<strong class='admin-error-counter'>0</strong>", zero)
        self.assertIn("class='column-number numeric' data-sort-value='2'>", positive)
        self.assertIn("<strong class='admin-error-counter is-positive'>2</strong>", positive)
        self.assertEqual(visible_text(positive.split(">", 1)[1]), "2 packages · 2 sources")
        self.assertIn("<span class='sr-only'> with issues</span>", positive)
        self.assertNotIn("data-sort-value", unknown)
        issue_cells = zero + positive + unknown
        self.assertNotIn("<svg", issue_cells)
        self.assertNotIn("admin-pill", issue_cells)
        self.assertIn(".provider-issue-count.is-positive{color:var(--danger)}", ADMIN_STYLES)
        self.assertNotIn("border-radius:999px;color:var(--graphite);font-weight:750}.provider-issue-count", ADMIN_STYLES)

    def test_summary_is_one_card_without_scope_chips_and_last_sync_in_heading(self):
        body = self._page([
            {"id": "a", "name": "A", "status": "ACTIVE", "health": "HEALTHY", "packageCount": 3,
             "affectedPackageCount": 0, "problematicSourceCount": 0, "lastCatalogSync": "2026-09-16T10:30:00Z"},
            {"id": "b", "name": "B", "status": "PAUSED", "health": "HEALTHY", "packageCount": 3,
             "affectedPackageCount": 1, "problematicSourceCount": 1, "lastCatalogSync": "2026-09-15T10:30:00Z"},
        ])
        main = body.split("<main", 1)[1]
        heading = main.split("<div class='heading-row installation-heading'>", 1)[1].split("<section", 1)[0]
        self.assertIn("<p class='page-meta provider-summary-sync'><strong>Last sync</strong> ", heading)
        self.assertIn("2026-09-16T10:30:00", heading)
        card = main.split("<section class='admin-card installation-kpis provider-summary' aria-label='Provider summary'>", 1)[1].split("</section>", 1)[0]
        self.assertEqual(re.findall(r"<span class='admin-metric-label'>([^<]+)</span>", card),
                         ["Active", "Healthy", "Package issues", "Provider issues"])
        self.assertEqual(main.count("class='admin-metric-row"), 1)
        self.assertNotIn("admin-scope-chip", main.split("<section class='provider-section'", 1)[0])
        self.assertEqual(card.count("<span class='admin-metric-secondary'>of 2</span>"), 2)
        self.assertIsNone(metric_value(body, "Last sync"))

    def test_empty_provider_list_has_no_summary_or_sync_meta(self):
        main = self._page([]).split("<main", 1)[1]
        self.assertNotIn("installation-kpis", main)
        self.assertNotIn("provider-summary-sync", main)

    def test_problems_column_counts_packages_and_keeps_unknown_distinct(self):
        body = providers_page([
            {"id": "a", "name": "A", "status": "ACTIVE", "health": "HEALTHY", "packageCount": 3,
             "affectedPackageCount": 0, "problematicSourceCount": 0, "latestRelease": "2026-09",
             "lastCollectionStatus": "SUCCEEDED", "lastCollectionSuccess": "2099-01-01T00:00:00Z"},
            {"id": "b", "name": "B", "status": "ACTIVE", "health": "DOWN", "packageCount": 3,
             "affectedPackageCount": 2, "problematicSourceCount": 1, "lastHealthError": "timeout"},
            {"id": "c", "name": "C", "status": "RETIRED", "health": "UNKNOWN", "packageCount": None,
             "affectedPackageCount": None, "problematicSourceCount": None},
        ], {"username": "operator"}, "csrf").decode()
        rows = body.split("<tbody id='provider-rows'>", 1)[1].split("</tbody>", 1)[0].split("</tr>")[:3]
        issues = [row.split("</td>")[4].rsplit("<td", 1)[1].split(">", 1)[1] for row in rows]
        self.assertEqual([visible_text(cell) for cell in issues], ["0", "2 packages · 1 source", "—"])
        self.assertIn("—<span class='sr-only'> Unknown</span>", body)
        self.assertEqual(metric_value(body, "Package issues"), "—")
        # Retired providers are not problems; the degraded active one is.
        self.assertEqual(metric_value(body, "Provider issues"), "1")
        self.assertIn("<span>Failed</span>", body)  # DOWN reads as Failed in one vocabulary



HEALTH = {
    "api": "HEALTHY", "database": "FAILED", "scheduler": None, "weekly": None, "observations": [],
    "providers": [
        {"id": "freizeitkarte", "name": "Freizeitkarte", "status": "ACTIVE", "health": "HEALTHY",
         "lastCollectionStatus": "SUCCEEDED", "lastCollectionSuccess": "2099-01-01T00:00:00Z", "latestRelease": "x"},
        {"id": "bbbike", "name": "BBBike", "status": "ACTIVE", "health": "DOWN",
         "lastCollectionStatus": "SUCCEEDED", "lastCollectionSuccess": "2099-01-01T00:00:00Z", "latestRelease": "x"},
    ],
}


class HealthPageTests(unittest.TestCase):
    def test_provider_catalogs_collapse_into_one_catalogs_row(self):
        cards, _, _ = _system_health_cards(HEALTH)
        titles = [card["title"] for card in cards]
        self.assertIn("Catalogs", titles)
        self.assertNotIn("Freizeitkarte", titles)
        self.assertNotIn("BBBike", titles)
        catalogs = next(card for card in cards if card["title"] == "Catalogs")
        self.assertEqual(catalogs["group"], "catalogs")
        self.assertEqual(catalogs["status"], "FAILED")
        self.assertIn("BBBike", catalogs["reason"])

    def render(self, health=HEALTH):
        return system_health_page(health, {"username": "operator"}, "csrf").decode()

    def test_one_plain_summary_card_and_the_quick_filter_is_the_filter(self):
        body = self.render()
        main = body.split("<main", 1)[1]
        # One KPI card like Installations: plain numbers, no icons, no chips,
        # no tiles doubling as filter buttons (owner decision 2026-10-06).
        card = main.split("<section class='admin-card installation-kpis health-kpis'", 1)[1].split("</section>", 1)[0]
        self.assertEqual(main.count("installation-kpis"), 1)
        for label in ("Failed", "Degraded", "No data", "Healthy"):
            self.assertIn(f"<span class='admin-metric-label'>{label}</span>", card)
        self.assertNotIn("admin-icon", card)
        self.assertNotIn("admin-scope-chip", card)
        self.assertNotIn("<button", card)
        self.assertNotIn("data-health-filter", body)
        self.assertEqual(metric_value(body, "Failed"), "2")
        self.assertEqual(metric_tone(body, "Failed"), "danger")
        self.assertEqual(metric_tone(body, "Degraded"), "neutral")
        healthy = system_health_page({"api": "HEALTHY", "database": "HEALTHY", "githubSync": {"overdue": 0, "errors": 0}},
                                     {"username": "operator"}, "csrf").decode()
        self.assertEqual(metric_value(healthy, "Failed"), "0")
        self.assertEqual(metric_tone(healthy, "Failed"), "neutral")
        # Status filter is an Installations-style quick-filter group (owner decision 2026-10-06).
        quick = body.split("data-quick-select='health-status'>", 1)[1].split("</div>", 1)[0]
        for value, label in (("all", "All"), ("FAILED", "Failed"), ("WARNING", "Degraded"), ("UNKNOWN", "No data"), ("HEALTHY", "Healthy")):
            self.assertIn(f"data-quick-value='{value}' aria-pressed='{'true' if value == 'all' else 'false'}'>{label}</button>", quick)
        self.assertNotIn("Warning", quick)
        self.assertNotIn("data-admin-dropdown", body.split("id='health-filters'", 1)[1].split("</form>", 1)[0])
        # Dashboard links preselect the filter with ?status=FAILED.
        self.assertIn("new URLSearchParams(location.search).get('status')", body)

    def test_issues_card_lists_failed_and_degraded_checks_with_inline_details(self):
        body = self.render()
        main = body.split("<main", 1)[1]
        issues = main.split("id='health-attention-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn(">Issues</h2>", main.split("id='health-attention-title'", 1)[1][:20])
        self.assertNotIn("Problems", main)
        self.assertNotIn("admin-scope-chip", issues.split("</header>", 1)[0])
        rows = re.findall(r"<tr class='system-health-row system-health-issue' data-health-status='(\w+)' data-health-name='([^']+)'", issues)
        self.assertEqual(sorted(name for _, name in rows), ["catalogs", "database"])
        self.assertEqual({status for status, _ in rows}, {"FAILED"})
        # No data checks are not issues; they stay in Technical details.
        self.assertNotIn("data-health-status='UNKNOWN'", issues)
        for heading in ("Check", "Status", "Reason", "Last checked"):
            self.assertIn(f">{heading}</th>", issues)
        # One small Details control per row opens an attached, hidden row.
        self.assertEqual(issues.count("data-health-details aria-expanded='false'"), 2)
        self.assertEqual(issues.count("class='health-details-row'"), 2)
        self.assertNotIn("<details", issues)
        # A real target makes the action a link; otherwise it is muted text.
        catalogs = issues.split("data-health-name='catalogs'", 1)[1].split("</tr>", 1)[0]
        self.assertIn("<a class='system-health-action section-link' href='/admin/providers'>Open Providers", catalogs)
        database = issues.split("data-health-name='database'", 1)[1].split("</tr>", 1)[0]
        self.assertIn("<span class='system-health-action'>Inspect the database connection", database)
        empty = system_health_page({"api": "HEALTHY", "database": "HEALTHY"}, {"username": "operator"}, "csrf").decode()
        empty_issues = empty.split("id='health-attention-title'", 1)[1].split("</section>", 1)[0]
        self.assertIn("<span>No issues.</span>", empty_issues)
        self.assertNotIn("<table", empty_issues)

    def test_technical_details_is_one_collapsed_card_with_accessible_tabs(self):
        body = self.render()
        main = body.split("<main", 1)[1]
        self.assertLess(main.index("id='health-attention-title'"), main.index("id='health-technical-title'"))
        self.assertEqual(main.count("id='health-technical-disclosure'"), 1)
        self.assertNotIn("system-health-group", main)
        self.assertNotIn("system-health-weekly", main)
        self.assertIn("<details class='health-technical-disclosure' id='health-technical-disclosure'>", main)
        tablist = main.split("role='tablist'", 1)[1].split("</div>", 1)[0]
        tabs = re.findall(r"role='tab' class='quick-filter(?: active)?' id='health-tab-(\w+)'", tablist)
        self.assertEqual(tabs, ["service", "releases", "catalogs", "search", "weekly"])
        self.assertIn("aria-selected='true' tabindex='0'>Service</button>", tablist)
        self.assertIn("aria-selected='false' tabindex='-1'>Weekly results</button>", tablist)
        for group in ("service", "releases", "catalogs", "search"):
            self.assertIn(f"data-health-group-card='{group}'", main)
            self.assertIn(f"role='tabpanel' id='health-panel-{group}' aria-labelledby='health-tab-{group}'", main)
        self.assertIn("id='health-panel-weekly'", main)
        service = main.split("id='health-panel-service'", 1)[1].split("role='tabpanel'", 1)[0]
        # Group summary plus every check not already listed under Issues.
        self.assertIn("<span>1/4 healthy</span>", service)
        self.assertIn("1 listed under Issues", service)
        for name in ("api", "scheduler", "issue sync"):
            self.assertIn(f"data-health-name='{name}'", service)
        self.assertNotIn("data-health-name='database'", service)
        catalogs = main.split("id='health-panel-catalogs'", 1)[1].split("role='tabpanel'", 1)[0]
        self.assertIn("Every check in this group is listed under Issues.", catalogs)
        self.assertIn("href='/admin/providers'>Open Providers", catalogs)
        # Arrow keys, Home and End move between tabs; a matching filter or
        # search opens the card on the tab that holds the match.
        for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            self.assertIn(key, body)
        self.assertIn("technical.open = true", body)

    def test_every_check_shows_its_last_checked_time_and_says_when_none_is_recorded(self):
        now = datetime.now(timezone.utc)
        heartbeat = now - timedelta(hours=3)
        synced = now - timedelta(minutes=7)
        probed = now - timedelta(minutes=40)
        health = {
            "api": "HEALTHY", "database": "HEALTHY", "observations": [], "weekly": None,
            "scheduler": {"status": "WAITING", "next_run_at": now + timedelta(hours=2),
                          "completed_at": now - timedelta(hours=4), "updated_at": heartbeat},
            "githubSync": {"overdue": 0, "errors": 0, "checked_at": synced},
            "providers": [{"id": "freizeitkarte", "name": "Freizeitkarte", "status": "ACTIVE", "health": "HEALTHY",
                           "lastCollectionStatus": "SUCCEEDED", "latestRelease": "x",
                           "lastCollectionSuccess": (now - timedelta(hours=5)).isoformat(),
                           "lastHealthCheck": probed.isoformat()}],
        }
        before = now - timedelta(seconds=5)
        cards = {card["title"]: card for card in _system_health_cards(health)[0]}
        # Live probes are checked when the snapshot is read for this page.
        for title in ("API", "Database"):
            self.assertGreaterEqual(cards[title]["lastChecked"], before)
        self.assertEqual(cards["Scheduler"]["lastChecked"], heartbeat)
        self.assertEqual(cards["Issue sync"]["lastChecked"], synced)
        self.assertEqual(cards["Catalogs"]["lastChecked"], probed)
        body = self.render(health)
        for title in ("api", "database", "scheduler", "issue sync", "catalogs"):
            row = body.split(f"data-health-name='{title}'", 1)[1].split("</tr>", 1)[0]
            when = row.split("system-health-when'>", 1)[1].split("</td>", 1)[0]
            self.assertIn("data-admin-timestamp", when, title)
        # Only a check with no recorded time shows the dash, with accessible text.
        weekly = body.split("data-health-name='weekly tests'", 1)[1].split("</tr>", 1)[0]
        self.assertIn("—<span class='sr-only'>Not recorded</span>", weekly)

    def test_dashboard_needs_attention_shows_system_checks_but_not_provider_checks(self):
        review = {"available": True, "installationIssues": 2, "githubIssuesInProgress": 0,
                  "identityPending": 0, "readyToPublish": 0, "missingDiagnostics": 0}

        def attention(system):
            body = overview_page({"period": "24h", "data": {"hasData": False}, "providers": HEALTH["providers"],
                                  "review": review, "supportReports": {"openCount": 1}, "system": system},
                                 {"username": "operator"}, "csrf").decode()
            return body.split("id='overview-attention-title'", 1)[1].split("</section>", 1)[0]

        # HEALTH: Database failed, Catalogs failed (a provider problem, which
        # stays on Providers) -> one System checks issue.
        card = attention(HEALTH)
        self.assertIn("<span class='overview-attention-label'>System checks</span><strong>1</strong>", card)
        self.assertIn("href='/admin/system-health?status=FAILED' aria-label='System checks: 1'", card)
        self.assertNotIn("Provider problems", card)
        self.assertIn("data-stat='attentionTotal'>4</strong>", card)
        labels = re.findall(r"<span class='overview-attention-label'>([^<]+)</span>", card)
        self.assertEqual(labels[-1], "System checks")
        # Only degraded checks: the link preselects Degraded.
        degraded = dict(HEALTH, database="HEALTHY", githubSync={"overdue": 1, "errors": 0})
        card = attention(degraded)
        self.assertIn("href='/admin/system-health?status=WARNING' aria-label='System checks: 1'", card)
        # No failed or degraded system check (provider failures alone do not
        # count): no row, and the total excludes it.
        healthy = dict(HEALTH, database="HEALTHY", githubSync={"overdue": 0, "errors": 0})
        card = attention(healthy)
        self.assertNotIn("System checks", card)
        self.assertIn("data-stat='attentionTotal'>3</strong>", card)
        # An unavailable Health snapshot adds no row.
        self.assertNotIn("System checks", attention({"available": False}))


if __name__ == "__main__":
    unittest.main()

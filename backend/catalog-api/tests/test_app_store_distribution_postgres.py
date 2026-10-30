"""App and App Store parts of the app results on the real migrated schema
(contracts/STATISTICS_CONTRACT.md, App and App Store; owner request 2026-10-30)."""
import re
import unittest
from datetime import datetime, timezone

from pglite_support import PGliteTestCase
from statistics_fixtures import FENIX_8, StatisticsRows
from terento_catalog.admin import (
    _map_statistics_summary, _overview_map_activity_row, _source_switch, dashboard_page, device_detail_page,
)
from terento_catalog.update_diagnostics import update_summary_markup
from terento_catalog.http_api import CatalogService
from terento_catalog.telemetry import is_app_store_release_label

STORE = "1.1.0+appstore"
DIRECT = "1.1.0"
LABELS = (
    "1.1.0", "1.1.0+appstore", "1.1.0+build.appstore", "1.1.0+appstore.2", "1.1.0-rc.1+appstore",
    "1.1.0+appstorex", "1.1.0+xappstore", "1.1.0-appstore", "1.1.0-local", "1.0.0-beta.11-local",
    "1.1.0+build.46",
)
USER = {"id": 1, "username": "admin"}


class AppStoreDistributionTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.rows = StatisticsRows(self.server)
        self.service = CatalogService(self.db)
        self.rows.package("fzk-deu")

    def install(self, label, *, failed=False, minutes=0):
        operation = self.rows.uuid()
        self.rows.diagnostic(
            operation_id=operation, release_label=label, occurred_at=self.rows.at(minutes),
            **({"phase_outcome": "FAILED", "failure_stage": "write", "failure_code": "INSTALL_FAILED_WRITE"}
               if failed else {}),
        )
        self.rows.map_event(
            operation_id=operation, release_label=label, map_package_id="fzk-deu", occurred_at=self.rows.at(minutes),
            **({"event_type": "INSTALL_FAILED", "outcome": "FAILED"} if failed else {}),
        )
        return operation

    def seed(self):
        self.install(DIRECT, minutes=0)
        self.install(DIRECT, minutes=1)
        self.install(STORE, minutes=2)
        self.install(STORE, failed=True, minutes=3)

    def test_sql_rule_matches_the_python_twin(self):
        for label in LABELS:
            sql = self.sql("SELECT terento_is_app_store_release(%s) AS store", (label,))[0]["store"]
            self.assertEqual(sql, is_app_store_release_label(label), label)
        self.assertIs(self.sql("SELECT terento_is_app_store_release(NULL) AS store")[0]["store"], False)
        self.assertEqual([label for label in LABELS if is_app_store_release_label(label)],
                         ["1.1.0+appstore", "1.1.0+build.appstore", "1.1.0+appstore.2", "1.1.0-rc.1+appstore"])

    def test_model_view_adds_the_app_store_part_without_changing_totals(self):
        self.seed()
        view = self.sql("SELECT * FROM compatibility_model_statistics WHERE canonical_device_model_id=%s", (FENIX_8,))[0]
        self.assertEqual((view["attempted_install_count"], view["successful_install_count"], view["failed_install_count"]),
                         (4, 3, 1))
        self.assertEqual((view["app_store_attempted_install_count"], view["app_store_successful_install_count"],
                          view["app_store_failed_install_count"]), (2, 1, 1))
        self.assertEqual(view["app_store_last_success"], self.rows.at(2))
        self.assertEqual(view["app_store_last_failure"], self.rows.at(3))
        self.assertEqual(view["direct_last_success"], self.rows.at(1))
        self.assertIsNone(view["direct_last_failure"])

    def test_model_page_shows_app_app_store_web_and_all_rows(self):
        self.seed()
        device = next(item for item in self.service.admin_devices()["devices"] if item["id"] == FENIX_8)
        stats = device["installationStats"]
        self.assertEqual(stats["app"], {"attempts": 2, "successful": 2, "failed": 0})
        self.assertEqual(stats["appStore"], {"attempts": 2, "successful": 1, "failed": 1})
        self.assertEqual((stats["attempts"], stats["successful"], stats["failed"]), (4, 3, 1))
        body = device_detail_page(device, USER, "csrf").decode()
        card = body.split("id='model-installation-kpis-title'", 1)[1].split("</section>", 1)[0]
        order = [card.index(f"source-count-row source-count-{name}'") for name in ("app", "appstore", "web", "all")]
        self.assertEqual(order, sorted(order))
        for stat, value in (("app-attempts", 2), ("appstore-attempts", 2), ("appstore-successful", 1),
                            ("appstore-failed", 1), ("all-attempts", 4), ("all-successful", 3)):
            self.assertIn(f"data-stat='{stat}'>{value}</span>", card)
        self.assertIn("<span class='sr-only'>App Store</span>", card)

    def test_maps_and_dashboard_parts_add_up_to_the_app_total(self):
        self.seed()
        for label in (DIRECT, STORE, STORE):
            self.rows.map_event(release_label=label, map_package_id="fzk-deu", event_type="DOWNLOAD_SUCCEEDED",
                                acquisition_id=self.rows.uuid(), component_kind="main", acquisition_purpose="install")
        parts = {name: _map_statistics_summary(self.db.map_statistics({} if name is None else {"distribution": name}))
                 for name in (None, "app", "appstore")}
        for key, values in (("completedInstalls", (3, 2, 1)), ("failedInstalls", (1, 0, 1)),
                            ("completedDownloads", (3, 1, 2))):
            self.assertEqual(tuple(parts[name][key] for name in (None, "app", "appstore")), values, key)
        snapshots = {name: self.db.admin_overview_map_snapshot(
            datetime(1970, 1, 1, tzinfo=timezone.utc), period="all", distribution=name)
            for name in (None, "app", "appstore")}
        self.assertEqual([snapshots[name]["completedInstallCount"] for name in (None, "app", "appstore")], [3, 2, 1])
        self.assertEqual([snapshots[name]["failedInstallCount"] for name in (None, "app", "appstore")], [1, 0, 1])
        self.assertEqual(snapshots["appstore"]["recentActivity"], [])
        store_activity = [row for row in snapshots[None]["recentActivity"] if row.get("release_label") == STORE]
        self.assertEqual(len(store_activity), 4)  # two installs and two downloads
        maps = self.service.map_statistics({"source": "appstore"})
        self.assertEqual(maps["source"], "appstore")
        self.assertEqual(maps["summary"], parts["appstore"])

    def test_installations_app_store_view_takes_its_own_rows_and_problems(self):
        self.seed()
        self.install(STORE, failed=True, minutes=4)
        rows = self.service.compatibility_statistics()
        identity = f"canonical:{FENIX_8}"
        summaries = {name: self.service.compatibility_diagnostic_summary(name) for name in (None, "app", "appstore")}
        self.assertEqual([summaries[name].get(identity, {}).get("open_errors", 0) for name in (None, "app", "appstore")],
                         [2, 0, 2])
        for source, attempts, successful, failed in (("app", 2, 2, 0), ("appstore", 3, 1, 2), ("all", 5, 3, 2)):
            distribution = source if source != "all" else None
            body = dashboard_page(
                rows, USER, "csrf", diagnostic_summary=summaries[distribution], web_rows=[],
                unreported_app=self.db.app_installs_without_model_report(distribution=distribution), source=source,
            ).decode()
            self.assertIn(f"value='{source}' class='active' aria-pressed='true'", body)
            for stat, value in (("attempts", attempts), ("successful", successful), ("failed", failed),
                                ("openProblems", {"app": 0, "appstore": 2, "all": 2}[source])):
                self.assertIn(f"data-stat='{stat}'>{value}</strong>", body, f"{source} {stat}")

    def test_only_app_store_identities_appear_in_the_app_store_view(self):
        self.install(DIRECT)
        rows = self.service.compatibility_statistics()
        body = dashboard_page(rows, USER, "csrf", diagnostic_summary={}, web_rows=[],
                              unreported_app={"successful_install_count": 0}, source="appstore").decode()
        self.assertIn("No installation evidence yet.", body)

    def test_unreported_app_installs_split_by_distribution(self):
        self.rows.map_event(release_label=STORE, map_package_id="fzk-deu")
        self.rows.map_event(release_label=DIRECT, map_package_id="fzk-deu")
        self.rows.map_event(release_label=DIRECT, map_package_id="fzk-deu")
        counts = [self.db.app_installs_without_model_report(distribution=name)["successful_install_count"]
                  for name in (None, "app", "appstore")]
        self.assertEqual(counts, [3, 2, 1])


class AppStorePresentationTests(unittest.TestCase):
    def test_switch_lists_all_app_app_store_and_web(self):
        switch = _source_switch("appstore", label="Maps source")
        self.assertEqual(re.findall(r"value='(\w+)'", switch), ["all", "app", "appstore", "web"])
        self.assertIn("value='appstore' class='active' aria-pressed='true' aria-label='App Store'>"
                      "<svg class='admin-icon admin-icon-source-appstore'", switch)

    def test_updates_card_splits_the_app_reports(self):
        summary = {"successfulUpdateCount": 5, "failedUpdateCount": 2, "notStartedCount": 1,
                   "appStore": {"successfulUpdateCount": 2, "failedUpdateCount": 1, "notStartedCount": 0}}
        card = update_summary_markup(summary, FENIX_8, web={"updatesSuccessful": 4, "updatesFailed": 0})
        for stat, value in (("app-successful", 3), ("app-failed", 1), ("app-blocked", 1), ("appstore-successful", 2),
                            ("appstore-failed", 1), ("web-successful", 4), ("all-successful", 9), ("all-failed", 2)):
            self.assertIn(f"data-stat='{stat}'>{value}</span>", card)

    def test_activity_marks_app_store_rows(self):
        row = {"event_type": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED", "provider_id": "freizeitkarte",
               "occurred_at": datetime(2026, 10, 29, 21, 40, tzinfo=timezone.utc), "display_name": "Alabama"}
        store = _overview_map_activity_row({**row, "release_label": STORE})
        self.assertIn("<span class='activity-source-appstore' role='img' aria-label='App Store'>", store)
        self.assertNotIn("activity-source-appstore", _overview_map_activity_row({**row, "release_label": DIRECT}))


if __name__ == "__main__":
    unittest.main()

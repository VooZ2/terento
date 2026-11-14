"""Admin Web visits, Google Search (Search Console): settings, requests, cache, failures, markup and routes."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from admin_test_utils import visible_text
from api_test_fixtures import FakeProviderDatabase
from terento_catalog import gsc_stats
from terento_catalog.admin_website_stats import search_console_blocks, website_stats_page
from terento_catalog.gsc_stats import (
    final_totals,
    CACHE_SECONDS,
    GscRequestError,
    GscSettings,
    GscStats,
    page_path,
    parse_dates,
    parse_queries,
    period_dates,
)
from terento_catalog.http_api import CatalogService, make_handler

COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"
# 2026-11-14 20:30 UTC is 12:30 on 2026-11-14 in Pacific Time.
NOW = datetime(2026, 11, 14, 20, 30, tzinfo=timezone.utc)
SECRET_KEY = "-----BEGIN PRIVATE KEY-----\nsecret-key-material\n-----END PRIVATE KEY-----\n"
TOKEN = "ya29.secret-access-token"
ACCOUNT = {"type": "service_account", "client_email": "reader@example.iam.gserviceaccount.com",
           "private_key": SECRET_KEY, "token_uri": "https://oauth2.googleapis.com/token"}
SETTINGS = GscSettings(property_name="sc-domain:terento.app", service_account=ACCOUNT)

DAYS = [("2026-11-08", 1, 96), ("2026-11-09", 2, 78), ("2026-11-10", 8, 102), ("2026-11-11", 1, 93),
        ("2026-11-12", 0, 79), ("2026-11-13", 9, 121), ("2026-11-14", 6, 60)]
# The previous 7 days; only the last 5 count against the 5 final days above
# (11-13 and 11-14 are preliminary).
PREVIOUS_DAYS = [("2026-11-01", 50, 500), ("2026-11-02", 50, 500), ("2026-11-03", 2, 100), ("2026-11-04", 1, 90),
                 ("2026-11-05", 3, 110), ("2026-11-06", 2, 95), ("2026-11-07", 2, 105)]
QUERIES = [
    ("garmin maps free", 2, 300, 0.007, 7.2),       # position 4–10, impressions ≥ 20 % of the top: Near top
    ("terento", 4, 40, 0.1, 1.1),
    ("<script>alert(1)</script>", 1, 1500, 0.001, 12.4),
    ("openstreetmap garmin", 1, 200, 0.005, 9.0),  # 200 < 300 (20 % of 1500): not Near top
]


def answer(body: dict) -> dict:
    """Answers like Search Console for the request body."""
    dimensions = body.get("dimensions") or []
    if dimensions == ["date"]:
        if body["startDate"] < "2026-11-08":  # the previous period
            return {"rows": [{"keys": [day], "clicks": c, "impressions": i, "ctr": 0, "position": 6} for day, c, i in PREVIOUS_DAYS]}
        return {"rows": [{"keys": [day], "clicks": c, "impressions": i, "ctr": 0, "position": 5} for day, c, i in DAYS],
                "metadata": {"firstIncompleteDate": "2026-11-13"}}
    if dimensions == ["query"]:
        return {"rows": [{"keys": [q], "clicks": c, "impressions": i, "ctr": r, "position": p} for q, c, i, r, p in QUERIES]}
    if dimensions == ["page"]:
        return {"rows": [{"keys": ["https://terento.app/en/compatibility/"], "clicks": 5, "impressions": 90, "ctr": 0.05, "position": 4.2},
                         {"keys": ["https://terento.app/"], "clicks": 9, "impressions": 140, "ctr": 0.06, "position": 3.1}]}
    raise AssertionError(dimensions)


class Clock:
    def __init__(self) -> None:
        self.now = NOW.timestamp()

    def __call__(self) -> float:
        return self.now


class FakeGsc:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.tokens: list[str] = []
        self.fail: Exception | None = None
        self.lock = threading.Lock()

    def __call__(self, settings, token, body):
        with self.lock:
            self.calls.append(body)
            self.tokens.append(token)
        if self.fail:
            raise self.fail
        return answer(body)


def stats(fake=None, clock=None, token=lambda: TOKEN) -> tuple[GscStats, FakeGsc, Clock]:
    fake = fake or FakeGsc()
    clock = clock or Clock()
    return GscStats(SETTINGS, query=fake, token=token, clock=clock), fake, clock


class SettingsTests(unittest.TestCase):
    def test_unset_is_disabled_without_a_warning(self):
        with self.assertNoLogs(gsc_stats.LOGGER, level="WARNING"):
            self.assertIsNone(GscSettings.from_env({}))

    def test_json_or_a_file_and_the_key_stays_out_of_repr(self):
        settings = GscSettings.from_env({"GSC_SERVICE_ACCOUNT_JSON": json.dumps(ACCOUNT)})
        self.assertEqual(settings.property_name, "sc-domain:terento.app")
        self.assertNotIn("secret-key-material", repr(settings))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as file:
            json.dump(ACCOUNT, file)
        try:
            settings = GscSettings.from_env({"GSC_SERVICE_ACCOUNT_JSON": file.name, "GSC_PROPERTY": "sc-domain:example.test"})
        finally:
            os.unlink(file.name)
        self.assertEqual((settings.property_name, settings.service_account["client_email"]),
                         ("sc-domain:example.test", ACCOUNT["client_email"]))

    def test_invalid_settings_disable_and_never_log_a_value(self):
        for raw in ("{not json", json.dumps({**ACCOUNT, "type": "authorized_user"}), json.dumps({**ACCOUNT, "private_key": ""}),
                    "/nonexistent/secret.json"):
            with self.subTest(raw=raw[:12]), self.assertLogs(gsc_stats.LOGGER, level="WARNING") as logs:
                self.assertIsNone(GscSettings.from_env({"GSC_SERVICE_ACCOUNT_JSON": raw}))
            self.assertNotIn("secret-key-material", "\n".join(logs.output))


class PeriodTests(unittest.TestCase):
    def test_whole_pacific_days_ending_today_and_the_previous_period(self):
        self.assertEqual(period_dates("7d", NOW), (datetime(2026, 11, 8).date(), datetime(2026, 11, 14).date(),
                                                   datetime(2026, 11, 1).date()))
        start, end, previous = period_dates("30d", NOW)
        self.assertEqual((start.isoformat(), end.isoformat(), previous.isoformat()), ("2026-10-16", "2026-11-14", "2026-09-16"))
        self.assertIsNone(period_dates("all", NOW)[2])
        # 07:30 UTC is still the day before in Pacific Time.
        self.assertEqual(period_dates("7d", datetime(2026, 11, 15, 7, 30, tzinfo=timezone.utc))[1].isoformat(), "2026-11-14")


class ParseTests(unittest.TestCase):
    def test_dates_keep_the_first_incomplete_day(self):
        data = parse_dates(answer({"dimensions": ["date"], "startDate": "2026-11-08"}))
        self.assertEqual(data["firstIncompleteDate"], "2026-11-13")
        self.assertEqual(data["days"][0], {"date": "2026-11-08", "clicks": 1, "impressions": 96, "position": 5})

    def test_final_totals_weight_the_position_by_impressions(self):
        days = [{"date": "2026-11-01", "clicks": 1, "impressions": 100, "position": 2.0},
                {"date": "2026-11-02", "clicks": 3, "impressions": 300, "position": 6.0},
                {"date": "2026-11-03", "clicks": 9, "impressions": 900, "position": 1.0}]
        first, last = datetime(2026, 11, 1).date(), datetime(2026, 11, 2).date()
        self.assertEqual(final_totals(days, first, last),
                         {"clicks": 4, "impressions": 400, "ctr": 0.01, "position": 5.0, "days": 2})
        self.assertEqual(final_totals([], first, last), {"clicks": 0, "impressions": 0, "ctr": None, "position": None, "days": 2})

    def test_queries_top_ten_by_clicks_then_impressions_and_near_top(self):
        data = parse_queries(answer({"dimensions": ["query"], "startDate": "2026-11-08"}))
        self.assertEqual([row["query"] for row in data["rows"]],
                         ["terento", "garmin maps free", "<script>alert(1)</script>", "openstreetmap garmin"])
        self.assertEqual([row["nearTop"] for row in data["rows"]], [False, True, False, False])
        self.assertEqual(data["clicks"], 8)

    def test_page_path_drops_the_site_origin(self):
        self.assertEqual(page_path("https://terento.app/en/compatibility/"), "/en/compatibility/")
        self.assertEqual(page_path("https://terento.app"), "/")


class SnapshotTests(unittest.TestCase):
    def test_totals_count_only_final_days_against_as_many_days_before(self):
        blocks = stats()[0].snapshot("7d", NOW)["blocks"]
        self.assertEqual(blocks["totals"]["data"], {"clicks": 12, "impressions": 448, "ctr": 12 / 448, "position": 5.0, "days": 5})
        self.assertEqual(blocks["previousTotals"]["data"], {"clicks": 10, "impressions": 500, "ctr": 0.02, "position": 6.0, "days": 5})
        self.assertEqual(blocks["dates"]["data"]["days"][-1]["date"], "2026-11-14")  # the chart keeps preliminary days

    def test_one_request_per_block_with_web_and_all_data(self):
        snapshot = stats()[0].snapshot("7d", NOW)
        self.assertEqual(list(snapshot["blocks"]), ["totals", "previousTotals", "dates", "queries", "pages"])
        self.assertTrue(all(block["state"] == "ok" for block in snapshot["blocks"].values()))
        self.assertEqual((snapshot["startDate"], snapshot["endDate"], snapshot["previousStartDate"]),
                         ("2026-11-08", "2026-11-14", "2026-11-01"))
        self.assertEqual(snapshot["blocks"]["totals"]["data"]["clicks"], 12)
        self.assertEqual(snapshot["blocks"]["pages"]["data"][1]["path"], "/")

    def test_request_bodies(self):
        _, fake, _ = stats()
        GscStats(SETTINGS, query=fake, token=lambda: TOKEN, clock=Clock()).snapshot("30d", NOW)
        by_dimensions = {tuple(body.get("dimensions") or ()) + (body["startDate"],): body for body in fake.calls}
        self.assertEqual(len(fake.calls), 4)  # no totals request: totals come from the days
        self.assertTrue(all(body["type"] == "web" for body in fake.calls))
        # Only the trend reads preliminary days.
        self.assertEqual({key: body["dataState"] for key, body in by_dimensions.items()},
                         {("date", "2026-10-16"): "all", ("date", "2026-09-16"): "final",
                          ("query", "2026-10-16"): "final", ("page", "2026-10-16"): "final"})
        self.assertEqual(by_dimensions[("query", "2026-10-16")]["rowLimit"], 100)
        self.assertEqual(by_dimensions[("page", "2026-10-16")]["rowLimit"], 5)
        self.assertEqual(by_dimensions[("date", "2026-09-16")]["endDate"], "2026-10-15")
        self.assertEqual(set(fake.tokens), {TOKEN})

    def test_an_unknown_period_is_last_30_days(self):
        service, fake, _ = stats()
        for period in ("today", "24h", "1y"):
            with self.subTest(period=period):
                self.assertEqual(service.snapshot(period, NOW)["period"], "30d")
        self.assertEqual(len(fake.calls), 4)  # one 30-day read, then the cache

    def test_all_time_has_no_previous_period(self):
        snapshot = stats()[0].snapshot("all", NOW)
        self.assertNotIn("previousTotals", snapshot["blocks"])
        self.assertIsNone(snapshot["previousStartDate"])

    def test_cached_for_an_hour_per_period(self):
        service, fake, clock = stats()
        service.snapshot("7d", NOW)
        service.snapshot("7d", NOW)
        self.assertEqual(len(fake.calls), 4)
        service.snapshot("30d", NOW)
        self.assertEqual(len(fake.calls), 8)
        clock.now += CACHE_SECONDS + 1
        service.snapshot("7d", NOW)
        self.assertEqual(len(fake.calls), 12)

    def test_403_logs_only_gsc_403_and_keeps_the_last_result(self):
        service, fake, clock = stats()
        service.snapshot("7d", NOW)
        clock.now += CACHE_SECONDS + 1
        fake.fail = GscRequestError("HTTP 403", 403)
        with self.assertLogs(gsc_stats.LOGGER, level="WARNING") as logs:
            snapshot = service.snapshot("7d", NOW)
        self.assertEqual({line.split(":", 2)[2] for line in logs.output}, {"GSC 403"})
        self.assertTrue(all(block["state"] == "stale" for block in snapshot["blocks"].values()))
        self.assertEqual(snapshot["blocks"]["totals"]["fetchedAt"], NOW.timestamp())

    def test_a_failed_token_is_unavailable_and_logs_no_secret(self):
        def token():
            raise GscRequestError("token failed (RefreshError)")
        service, fake, _ = stats(token=token)
        with self.assertLogs(gsc_stats.LOGGER, level="WARNING") as logs:
            snapshot = service.snapshot("7d", NOW)
        self.assertEqual(fake.calls, [])
        self.assertTrue(all(block["state"] == "unavailable" for block in snapshot["blocks"].values()))
        self.assertNotIn("secret", "\n".join(logs.output))

    def test_a_bad_shape_stays_inside_its_block(self):
        class Broken(FakeGsc):
            def __call__(self, settings, token, body):
                return {"rows": "nope"} if body.get("dimensions") == ["page"] else answer(body)
        with self.assertLogs(gsc_stats.LOGGER, level="WARNING"):
            snapshot = stats(fake=Broken())[0].snapshot("7d", NOW)
        self.assertEqual(snapshot["blocks"]["pages"]["state"], "unavailable")
        self.assertEqual(snapshot["blocks"]["totals"]["state"], "ok")


class MarkupTests(unittest.TestCase):
    URL = "https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aterento.app"

    def render(self, period="7d", fake=None):
        service = stats(fake=fake)[0]
        return search_console_blocks(service.snapshot(period, NOW), console_url=service.console_url)

    def test_kpis_with_changes_coloured_by_meaning(self):
        text = visible_text(self.render())
        # The 5 final days against the 5 days before them; 13–14 Nov are preliminary.
        for expected in ("Google Search", "Search Console", "Clicks", "12", "+2 vs previous 5 days", "Impressions", "448",
                         "−52 vs previous 5 days", "CTR", "2.7%", "+0.7 pp vs previous 5 days", "Avg position", "5.0",
                         "−1.0 vs previous 5 days"):
            self.assertIn(expected, text)
        markup = self.render()
        position = markup.split("Avg position", 1)[1]
        self.assertIn("data-trend='better'", position.split("</div>", 1)[0])  # lower is better
        impressions = markup.split(">Impressions<", 1)[1]
        self.assertIn("data-trend='worse'", impressions.split("</div>", 1)[0])

    def test_two_stacked_charts_one_date_axis_and_preliminary_days(self):
        markup = self.render()
        svg = markup.split("<svg class='overview-trend-chart overview-trend-desktop gsc-chart'", 1)[1].split("</svg>", 1)[0]
        self.assertIn(">Clicks</text>", svg)
        self.assertIn(">Impressions</text>", svg)
        self.assertEqual(svg.count("gsc-chart-line is-preliminary"), 2)
        self.assertIn(">Preliminary</text>", svg)
        self.assertEqual(svg.count("class='overview-chart-group gsc-chart-day'"), 7)
        self.assertIn("13 Nov (preliminary) · Clicks 9 · Impressions 121", svg)
        self.assertIn("Google Search Console · dates in Pacific Time · data delayed 2–3 days", markup)
        # Each series in its own group (its own colour) with a named swatch.
        for metric, label in (("clicks", "Clicks"), ("impressions", "Impressions")):
            group = svg.split(f"<g class='gsc-series-{metric}'>", 1)[1].split("</g>", 1)[0]
            self.assertIn("class='gsc-chart-swatch'", group)
            self.assertIn(f">{label}</text>", group)
            self.assertIn("class='gsc-chart-line'", group)

    def test_queries_escaped_with_near_top_and_hidden_rare_queries(self):
        markup = self.render()
        self.assertNotIn("<script>alert", markup)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", markup)
        self.assertEqual(markup.count(">Near top</span>"), 1)
        self.assertIn("title='Position 4–10 with many impressions: closest to page-one top'", markup)
        self.assertIn("Rare queries are hidden by Google", markup)  # 8 query clicks < 12 total
        self.assertIn(">/en/compatibility/</span>", markup)
        self.assertIn(f"href='{self.URL.replace('&', '&amp;')}'", markup)
        self.assertIn("Open Search Console", markup)

    def test_all_time_has_no_change_lines(self):
        self.assertNotIn("vs previous", self.render("all"))

    def test_its_own_period_picker(self):
        markup = self.render("7d")
        picker = markup.split("<select id='gsc-period' data-admin-dropdown>", 1)[1].split("</select>", 1)[0]
        self.assertEqual(picker, "<option value='7d' selected>Last 7 days</option><option value='30d'>Last 30 days</option>"
                                 "<option value='all'>All time</option>")
        self.assertIn("data-gsc-period='7d'", markup)
        self.assertIn("<option value='30d' selected>", search_console_blocks(None, console_url=None))
        self.assertNotIn("whole days", visible_text(self.render("today")))

    def test_unavailable_stale_and_empty(self):
        self.assertIn("Search Console unavailable.", visible_text(search_console_blocks(None, console_url=None)))
        fake = FakeGsc()
        fake.fail = GscRequestError("connection failed")
        with self.assertLogs(gsc_stats.LOGGER, level="WARNING"):
            self.assertIn("Search Console unavailable.", visible_text(self.render(fake=fake)))
        service, fake, clock = stats()
        service.snapshot("7d", NOW)
        clock.now += CACHE_SECONDS + 1
        fake.fail = GscRequestError("timeout")
        with self.assertLogs(gsc_stats.LOGGER, level="WARNING"):
            markup = search_console_blocks(service.snapshot("7d", NOW), console_url=None)
        self.assertIn("Search Console unavailable</span>", markup)
        self.assertIn("Last result", markup)
        empty = {"period": "7d", "startDate": "2026-11-08", "endDate": "2026-11-14", "previousStartDate": None,
                 "blocks": {name: {"state": "ok", "fetchedAt": 1.0, "data": data} for name, data in {
                     "totals": {"clicks": 0, "impressions": 0, "ctr": None, "position": None},
                     "dates": {"days": [], "firstIncompleteDate": None}, "queries": {"rows": [], "clicks": 0}, "pages": []}.items()}}
        text = visible_text(search_console_blocks(empty, console_url=None))
        self.assertIn("No Google Search impressions in this period.", text)
        self.assertIn("No queries in this period.", text)


class _Database(FakeProviderDatabase):
    def delete_admin_session(self, token_hash):
        pass


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGsc()
        self.service = CatalogService(_Database(), gsc_stats=GscStats(SETTINGS, query=self.fake, token=lambda: TOKEN))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def get(self, path, cookie=COOKIE):
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        response = connection.getresponse()
        body = response.read().decode()
        connection.close()
        return response, body

    def test_the_api_needs_an_admin_session(self):
        for cookie in (None, "terento_admin_session=wrong; terento_admin_csrf=csrf", "terento_admin_session=session"):
            with self.subTest(cookie=cookie):
                response, body = self.get("/admin/api/gsc?period=7d", cookie=cookie)
                self.assertEqual((response.status, json.loads(body)), (401, {"error": "unauthorized"}))
        self.assertEqual(self.fake.calls, [])

    def test_the_api_answers_blocks_without_the_key_or_token(self):
        response, body = self.get("/admin/api/gsc?period=30d")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
        payload = json.loads(body)
        self.assertEqual((payload["configured"], payload["period"]), (True, "30d"))
        self.assertEqual(payload["blocks"]["totals"]["state"], "ok")
        self.assertIn("id='web-visits-gsc'", payload["html"])
        for secret in ("secret-key-material", TOKEN, ACCOUNT["client_email"], "Bearer"):
            self.assertNotIn(secret, body)

    def test_its_own_period_never_the_admin_period(self):
        _, body = self.get("/admin/api/gsc", cookie=COOKIE + "; terento_admin_period=7d")
        self.assertEqual(json.loads(body)["period"], "30d")
        for asked, answered in (("7d", "7d"), ("all", "all"), ("30d", "30d"), ("24h", "30d"), ("today", "30d"), ("1y", "30d")):
            with self.subTest(period=asked):
                _, body = self.get(f"/admin/api/gsc?period={asked}", cookie=COOKIE + "; terento_admin_period=7d")
                self.assertEqual(json.loads(body)["period"], answered)

    def test_without_settings_the_api_says_unavailable(self):
        self.service.gsc_stats = None
        _, body = self.get("/admin/api/gsc?period=7d")
        payload = json.loads(body)
        self.assertEqual((payload["configured"], payload["blocks"]), (False, None))
        self.assertIn("Search Console unavailable.", payload["html"])

    def test_the_page_loads_google_search_after_umami(self):
        _, body = self.get("/admin/web-visits")
        self.assertIn("/admin/api/gsc", body)
        self.assertLess(body.index("id='website-stats-failed'"), body.index("id='web-visits-gsc'"))
        self.assertNotIn("secret-key-material", body)
        self.assertEqual(self.fake.calls, [])  # the page never waits for Search Console


class PageTests(unittest.TestCase):
    def test_page_has_the_loading_block_and_its_failed_template(self):
        body = website_stats_page({"username": "owner"}, "csrf", period="7d").decode()
        self.assertIn("<section class='web-visits-gsc' id='web-visits-gsc'", body)
        self.assertIn("<template id='gsc-failed'>", body)

    def test_the_admin_period_does_not_set_the_google_search_period(self):
        for period in ("today", "24h", "7d", "all"):
            with self.subTest(period=period):
                body = website_stats_page({"username": "owner"}, "csrf", period=period).decode()
                gsc = body.split("<section class='web-visits-gsc'", 1)[1]
                self.assertIn("data-gsc-period='30d'", gsc.split(">", 1)[0])
                self.assertIn("let period = '30d';", body)
                self.assertNotIn("#overview-period')?.value", body.split("let period = '30d';", 1)[1])


if __name__ == "__main__":
    unittest.main()

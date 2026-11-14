"""Admin Website stats (Umami): settings, requests, cache, failures, markup and routes."""

from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import umami_fixtures as fx
from admin_test_utils import metric_value, visible_text
from api_test_fixtures import FakeProviderDatabase
from terento_catalog import umami_stats
from terento_catalog.admin_website_stats import website_stats_blocks, website_stats_page
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.umami_stats import (
    CACHE_SECONDS,
    UmamiRequestError,
    UmamiSettings,
    UmamiStats,
    http_fetch,
    period_window,
)

COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"
NOW = datetime(2026, 11, 14, 12, 30, tzinfo=timezone.utc)
SETTINGS = UmamiSettings(base_url="https://stats.example.test", website_id=fx.WEBSITE_ID, api_key=fx.SECRET_KEY)


class Clock:
    def __init__(self) -> None:
        self.now = NOW.timestamp()

    def __call__(self) -> float:
        return self.now


class FakeUmami:
    """Answers like Umami; ``fail`` maps a path suffix to an error or a status."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail: dict[str, Exception] = {}
        self.lock = threading.Lock()

    def __call__(self, settings, path, params):
        with self.lock:
            self.calls.append((path, dict(params)))
        for suffix, error in self.fail.items():
            if path.endswith(suffix):
                raise error
        return fx.answer(path, params)


def stats(fake=None, clock=None, **kwargs) -> tuple[UmamiStats, FakeUmami, Clock]:
    fake = fake or FakeUmami()
    clock = clock or Clock()
    return UmamiStats(SETTINGS, fetch=fake, clock=clock, **kwargs), fake, clock


class SettingsTests(unittest.TestCase):
    def test_unset_is_disabled_without_a_warning(self):
        with self.assertNoLogs(umami_stats.LOGGER, level="WARNING"):
            self.assertIsNone(UmamiSettings.from_env({}))

    def test_incomplete_or_invalid_settings_disable_and_never_log_a_value(self):
        cases = [
            {"UMAMI_API_KEY": fx.SECRET_KEY},
            {"UMAMI_API_KEY": fx.SECRET_KEY, "UMAMI_BASE_URL": "http://stats.example.test", "UMAMI_WEBSITE_ID": fx.WEBSITE_ID},
            {"UMAMI_API_KEY": fx.SECRET_KEY, "UMAMI_BASE_URL": "https://stats.example.test", "UMAMI_WEBSITE_ID": "nope"},
            {"UMAMI_API_KEY": "two words", "UMAMI_BASE_URL": "https://stats.example.test", "UMAMI_WEBSITE_ID": fx.WEBSITE_ID},
        ]
        for environ in cases:
            with self.subTest(environ=sorted(environ)), self.assertLogs(umami_stats.LOGGER, level="WARNING") as logs:
                self.assertIsNone(UmamiSettings.from_env(environ))
            self.assertNotIn(fx.SECRET_KEY, "\n".join(logs.output))
            self.assertNotIn("two words", "\n".join(logs.output))

    def test_valid_settings_and_the_key_stays_out_of_repr(self):
        settings = UmamiSettings.from_env({
            "UMAMI_API_KEY": f" {fx.SECRET_KEY} ", "UMAMI_BASE_URL": "https://stats.example.test/",
            "UMAMI_WEBSITE_ID": fx.WEBSITE_ID.upper(),
        })
        self.assertEqual((settings.base_url, settings.website_id, settings.api_key),
                         ("https://stats.example.test", fx.WEBSITE_ID, fx.SECRET_KEY))
        self.assertEqual(settings.dashboard_url, f"https://stats.example.test/websites/{fx.WEBSITE_ID}")
        self.assertNotIn(fx.SECRET_KEY, repr(settings))


class WindowTests(unittest.TestCase):
    def test_periods_end_now(self):
        end = int(NOW.timestamp() * 1000)
        self.assertEqual(period_window("7d", NOW, "UTC"), (end - 7 * 86_400_000, end))
        self.assertEqual(period_window("24h", NOW, "UTC"), (end - 86_400_000, end))
        self.assertEqual(period_window("all", NOW, "UTC"), (0, end))
        # Today starts at local midnight (Vilnius is UTC+2 in November).
        self.assertEqual(period_window("today", NOW, "Europe/Vilnius"),
                         (int(datetime(2026, 11, 13, 22, tzinfo=timezone.utc).timestamp() * 1000), end))


class SnapshotTests(unittest.TestCase):
    def test_one_request_per_block_with_the_period_window(self):
        client, fake, _ = stats()
        snapshot = client.snapshot("7d", "UTC", now=NOW)
        start, end = period_window("7d", NOW, "UTC")
        base = f"/api/websites/{fx.WEBSITE_ID}"
        self.assertCountEqual(fake.calls, [
            (f"{base}/stats", {"startAt": start, "endAt": end}),
            (f"{base}/events/stats", {"startAt": start, "endAt": end, "event": "download-click"}),
            (f"{base}/metrics", {"startAt": start, "endAt": end, "type": "referrer", "limit": 10}),
            (f"{base}/metrics", {"startAt": start, "endAt": end, "type": "entry", "limit": 5}),
            (f"{base}/performance/stats", {"startAt": start, "endAt": end}),
            (f"{base}/errors", {"startAt": start, "endAt": end, "pageSize": 100}),
        ])
        blocks = snapshot["blocks"]
        self.assertEqual({block["state"] for block in blocks.values()}, {"ok"})
        self.assertEqual(blocks["visitors"]["data"]["current"]["visitors"], 120)
        self.assertEqual(blocks["visitors"]["data"]["previous"]["visitors"], 100)
        self.assertEqual(blocks["downloads"]["data"]["current"], {"events": 30, "visitors": 18})
        self.assertEqual(blocks["referrers"]["data"][0], {"name": "google.com", "visitors": 40})
        self.assertEqual(blocks["vitals"]["data"], {"lcp": 2300, "inp": 260, "cls": 0.31, "count": 64})
        # Ignored issues (a DevTools test) are left out; the most frequent first.
        self.assertEqual(blocks["errors"]["data"]["total"], 14)
        self.assertEqual([issue["count"] for issue in blocks["errors"]["data"]["top"]], [7, 4, 2])

    def test_requests_run_in_parallel(self):
        barrier = threading.Barrier(6, timeout=2)

        def fetch(settings, path, params):
            barrier.wait()  # all six requests are open at once, or this times out
            return fx.answer(path, params)

        client = UmamiStats(SETTINGS, fetch=fetch, clock=Clock())
        snapshot = client.snapshot("7d", "UTC", now=NOW)
        self.assertEqual({block["state"] for block in snapshot["blocks"].values()}, {"ok"})

    def test_results_are_cached_for_15_minutes_per_block_period_and_time_zone(self):
        client, fake, clock = stats()
        client.snapshot("7d", "UTC", now=NOW)
        clock.now += CACHE_SECONDS - 1
        client.snapshot("7d", "UTC", now=NOW)
        self.assertEqual(len(fake.calls), 6)
        client.snapshot("30d", "UTC", now=NOW)
        client.snapshot("7d", "Europe/Vilnius", now=NOW)
        self.assertEqual(len(fake.calls), 18)
        clock.now += 2
        client.snapshot("7d", "UTC", now=NOW)
        self.assertEqual(len(fake.calls), 24)

    def test_a_failure_keeps_the_last_result_and_logs_no_key_url_or_query(self):
        client, fake, clock = stats()
        first = client.snapshot("7d", "UTC", now=NOW)
        clock.now += CACHE_SECONDS + 1
        fake.fail["/stats"] = UmamiRequestError("HTTP 503", 503)
        with self.assertLogs(umami_stats.LOGGER, level="WARNING") as logs:
            snapshot = client.snapshot("7d", "UTC", now=NOW)
        visitors = snapshot["blocks"]["visitors"]
        self.assertEqual(visitors["state"], "stale")
        self.assertEqual(visitors["data"], first["blocks"]["visitors"]["data"])
        self.assertEqual(visitors["fetchedAt"], NOW.timestamp())
        self.assertEqual(snapshot["blocks"]["referrers"]["state"], "ok")
        output = "\n".join(logs.output)
        self.assertIn("visitors unavailable: HTTP 503", output)
        for secret in (fx.SECRET_KEY, "startAt", "stats.example.test", fx.WEBSITE_ID):
            self.assertNotIn(secret, output)

    def test_no_cache_and_a_failure_is_unavailable(self):
        fake = FakeUmami()
        fake.fail["/performance/stats"] = UmamiRequestError("not JSON")
        client, _, _ = stats(fake)
        with self.assertLogs(umami_stats.LOGGER, level="WARNING"):
            snapshot = client.snapshot("7d", "UTC", now=NOW)
        self.assertEqual(snapshot["blocks"]["vitals"], {"state": "unavailable", "fetchedAt": None, "data": None})

    def test_400_and_404_hide_only_that_block(self):
        fake = FakeUmami()
        fake.fail["/performance/stats"] = UmamiRequestError("HTTP 404", 404)
        fake.fail["/errors"] = UmamiRequestError("HTTP 400", 400)
        client, _, _ = stats(fake)
        snapshot = client.snapshot("7d", "UTC", now=NOW)
        self.assertEqual(snapshot["blocks"]["vitals"]["state"], "hidden")
        self.assertEqual(snapshot["blocks"]["errors"]["state"], "hidden")
        self.assertEqual(snapshot["blocks"]["visitors"]["state"], "ok")

    def test_a_slow_umami_is_a_timeout_and_the_page_does_not_wait_for_it(self):
        def fetch(settings, path, params):
            if path.endswith("/errors"):
                time.sleep(1)
            return fx.answer(path, params)

        client = UmamiStats(SETTINGS, fetch=fetch, clock=Clock(), deadline_seconds=0.2)
        started = time.monotonic()
        with self.assertLogs(umami_stats.LOGGER, level="WARNING") as logs:
            snapshot = client.snapshot("7d", "UTC", now=NOW)
        self.assertLess(time.monotonic() - started, 0.9)
        self.assertEqual(snapshot["blocks"]["errors"]["state"], "unavailable")
        self.assertIn("errors unavailable: timeout", "\n".join(logs.output))

    def test_unexpected_shapes_and_bugs_stay_inside_their_block(self):
        fake = FakeUmami()
        fake.fail["/metrics"] = KeyError("boom")
        client, _, _ = stats(fake)
        with self.assertLogs(umami_stats.LOGGER, level="WARNING"):
            snapshot = client.snapshot("7d", "UTC", now=NOW)
        self.assertEqual(snapshot["blocks"]["referrers"]["state"], "unavailable")
        with self.assertRaises(UmamiRequestError):
            umami_stats.parse_errors(["not", "a", "page"])


class _UmamiServer(BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None]] = []
    mode = "ok"

    def do_GET(self):  # noqa: N802 - http.server hook
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        if self.path.startswith("/elsewhere"):
            body, status, kind = b"{}", 200, "application/json"
        elif self.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.end_headers()
            return
        elif self.mode == "challenge":
            body, status, kind = b"<html>Just a moment...</html>", 403, "text/html"
        elif self.mode == "html":
            body, status, kind = b"<html>Just a moment...</html>", 200, "text/html"
        else:
            body, status, kind = json.dumps(fx.STATS).encode(), 200, "application/json"
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class HttpFetchTests(unittest.TestCase):
    def setUp(self):
        _UmamiServer.seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _UmamiServer)
        self.running = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        host, port = self.server.server_address
        self.settings = UmamiSettings(base_url=f"http://{host}:{port}", website_id=fx.WEBSITE_ID, api_key=fx.SECRET_KEY)

    def tearDown(self):
        if self.running:
            self.server.shutdown()
            self.server.server_close()

    def fetch(self, mode):
        _UmamiServer.mode = mode
        return http_fetch(self.settings, f"/api/websites/{fx.WEBSITE_ID}/stats", {"startAt": 0, "endAt": 1})

    def test_the_key_goes_only_in_the_bearer_header(self):
        self.assertEqual(self.fetch("ok")["visitors"], 120)
        path, authorization = _UmamiServer.seen[0]
        self.assertEqual(authorization, f"Bearer {fx.SECRET_KEY}")
        self.assertNotIn(fx.SECRET_KEY, path)
        self.assertEqual(path, f"/api/websites/{fx.WEBSITE_ID}/stats?startAt=0&endAt=1")

    def test_a_redirect_is_not_followed_with_the_key(self):
        with self.assertRaises(UmamiRequestError) as raised:
            self.fetch("redirect")
        self.assertEqual(raised.exception.reason, "redirect HTTP 302")
        self.assertEqual([path for path, _ in _UmamiServer.seen], [f"/api/websites/{fx.WEBSITE_ID}/stats?startAt=0&endAt=1"])

    def test_a_cloudflare_challenge_is_an_error_not_data(self):
        with self.assertRaises(UmamiRequestError) as raised:
            self.fetch("challenge")
        self.assertEqual((raised.exception.reason, raised.exception.status), ("HTTP 403", 403))
        with self.assertRaises(UmamiRequestError) as raised:
            self.fetch("html")
        self.assertEqual(raised.exception.reason, "not JSON")

    def test_an_unreachable_umami_is_a_connection_error(self):
        self.server.shutdown()
        self.server.server_close()
        self.running = False
        with self.assertRaises(UmamiRequestError) as raised:
            self.fetch("ok")
        self.assertTrue(raised.exception.reason.startswith("connection failed"))


class MarkupTests(unittest.TestCase):
    def render(self, fake=None, period="7d"):
        client, _, _ = stats(fake)
        snapshot = client.snapshot(period, "UTC", now=NOW)
        return website_stats_blocks(snapshot, dashboard_url=SETTINGS.dashboard_url), snapshot

    def test_blocks_in_order_with_values_and_changes(self):
        body, _ = self.render()
        order = [body.index(f"id='website-stats-{name}'") for name in ("visitors", "downloads", "referrers", "entries", "vitals", "errors")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(metric_value(body, "Visitors"), "120")
        self.assertEqual(metric_value(body, "Views"), "410")
        self.assertEqual(metric_value(body, "Bounce rate"), "40%")
        self.assertEqual(metric_value(body, "Visit duration"), "1 min 30 s")
        self.assertIn("+20 vs previous 7 days", body)
        self.assertIn("−10 pp vs previous 7 days", visible_text(body))  # bounce 50% → 40%
        self.assertEqual(metric_value(body, "Downloads"), "30")
        self.assertEqual(metric_value(body, "Conversion"), "15%")  # 18 of 120 visitors
        self.assertIn("−5 pp vs previous 7 days", visible_text(body))  # 20 of 100 before
        self.assertIn("google.com", body)
        self.assertIn("/download/", body)
        self.assertIn(f"href='https://stats.example.test/websites/{fx.WEBSITE_ID}'", body)
        self.assertNotIn(fx.SECRET_KEY, body)

    def test_web_vitals_ratings_and_the_sample_size(self):
        body, _ = self.render()
        text = visible_text(body.split("id='website-stats-vitals'", 1)[1].split("id='website-stats-errors'", 1)[0])
        self.assertIn("LCP · p752.30 sGood", text)
        self.assertIn("INP · p75260 msNeeds improvement", text)
        self.assertIn("CLS · p750.31Poor", text)
        self.assertIn("Samples64", text)

    def test_too_few_web_vitals_samples(self):
        original = fx.PERFORMANCE["count"]
        fx.PERFORMANCE["count"] = 19
        try:
            body, _ = self.render()
        finally:
            fx.PERFORMANCE["count"] = original
        vitals = body.split("id='website-stats-vitals'", 1)[1].split("id='website-stats-errors'", 1)[0]
        self.assertEqual(vitals.count("Too little data"), 3)
        self.assertNotIn("Good", vitals)

    def test_error_messages_are_text_not_markup(self):
        body, _ = self.render()
        self.assertNotIn("<img src=x", body)
        self.assertIn("TypeError: &lt;img src=x onerror=alert(1)&gt;", body)
        self.assertNotIn("test from DevTools", body)
        self.assertEqual(metric_value(body, "Errors"), "14")

    def test_all_time_has_no_change_lines(self):
        body, _ = self.render(period="all")
        self.assertNotIn("funnel-delta", body)

    def test_hidden_unavailable_and_stale_blocks(self):
        fake = FakeUmami()
        fake.fail["/performance/stats"] = UmamiRequestError("HTTP 404", 404)
        fake.fail["/errors"] = UmamiRequestError("HTTP 503", 503)
        with self.assertLogs(umami_stats.LOGGER, level="WARNING"):
            body, _ = self.render(fake)
        self.assertNotIn("website-stats-vitals", body)
        errors = body.split("id='website-stats-errors'", 1)[1]
        self.assertIn("Statistics unavailable.", errors)
        client, fake, clock = stats()
        client.snapshot("7d", "UTC", now=NOW)
        clock.now += CACHE_SECONDS + 1
        fake.fail["/stats"] = UmamiRequestError("timeout")
        with self.assertLogs(umami_stats.LOGGER, level="WARNING"):
            body = website_stats_blocks(client.snapshot("7d", "UTC", now=NOW), dashboard_url=None)
        visitors = body.split("id='website-stats-visitors'", 1)[1].split("id='website-stats-downloads'", 1)[0]
        self.assertIn("Statistics unavailable", visitors)
        self.assertIn("Last result", visitors)
        self.assertEqual(metric_value(body, "Visitors"), "120")

    def test_empty_period(self):
        empty = {"pageviews": 0, "visitors": 0, "visits": 0, "bounces": 0, "totaltime": 0,
                 "comparison": {"pageviews": 0, "visitors": 0, "visits": 0, "bounces": 0, "totaltime": 0}}

        def fetch(settings, path, params):
            if path.endswith("/metrics"):
                return []
            if path.endswith("/errors"):
                return {"data": [], "count": 0, "page": 1}
            if path.endswith("/events/stats"):
                return {"data": {"events": 0, "visitors": 0, "visits": 0, "uniqueEvents": 0}}
            if path.endswith("/performance/stats"):
                return {**fx.PERFORMANCE, "count": 0}
            return empty

        snapshot = UmamiStats(SETTINGS, fetch=fetch, clock=Clock()).snapshot("today", "UTC", now=NOW)
        body = website_stats_blocks(snapshot, dashboard_url=None)
        self.assertEqual(metric_value(body, "Visitors"), "0")
        self.assertEqual(metric_value(body, "Bounce rate"), "—")  # no visits: unknown, not 0%
        self.assertIn("No referrers in this period.", body)
        self.assertIn("No errors in this period.", body)
        self.assertIn("Same as previous period", body)

    def test_not_configured(self):
        body = website_stats_blocks(None, dashboard_url=None)
        self.assertIn("Statistics unavailable.", body)


class _Database(FakeProviderDatabase):
    def delete_admin_session(self, token_hash):
        pass


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeUmami()
        self.service = CatalogService(_Database(), umami_stats=UmamiStats(SETTINGS, fetch=self.fake))
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
                response, body = self.get("/admin/api/umami?period=7d", cookie=cookie)
                self.assertEqual((response.status, json.loads(body)), (401, {"error": "unauthorized"}))
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.fake.calls, [])

    def test_the_api_answers_blocks_without_the_key(self):
        response, body = self.get("/admin/api/umami?period=30d&timeZone=Europe/Vilnius")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
        payload = json.loads(body)
        self.assertEqual((payload["configured"], payload["period"], payload["timeZone"]), (True, "30d", "Europe/Vilnius"))
        self.assertEqual(payload["blocks"]["visitors"]["state"], "ok")
        self.assertIn("id='website-stats-visitors'", payload["html"])
        self.assertNotIn(fx.SECRET_KEY, body)
        self.assertNotIn("Bearer", body)

    def test_unknown_period_and_time_zone_fall_back(self):
        _, body = self.get("/admin/api/umami?period=1y&timeZone=../../etc/passwd")
        payload = json.loads(body)
        self.assertEqual((payload["period"], payload["timeZone"]), ("7d", "UTC"))

    def test_the_page_renders_loading_blocks_and_needs_a_login(self):
        response, body = self.get("/admin/website-stats?period=24h")
        self.assertEqual(response.status, 200)
        self.assertIn("<h1>Website stats</h1>", body)
        self.assertIn("<option value='24h' selected>", body)
        self.assertEqual(body.count("Loading…"), 6)
        self.assertIn("href=\"/admin/website-stats\">Website stats</a>", body)
        self.assertIn("/admin/api/umami", body)
        self.assertNotIn(fx.SECRET_KEY, body)
        self.assertEqual(self.fake.calls, [])  # the page itself never waits for Umami
        response, _ = self.get("/admin/website-stats", cookie=None)
        self.assertEqual((response.status, response.headers["Location"]), (303, "/admin/login"))

    def test_without_settings_the_api_says_unavailable(self):
        self.service.umami_stats = None
        _, body = self.get("/admin/api/umami?period=7d")
        payload = json.loads(body)
        self.assertEqual((payload["configured"], payload["blocks"]), (False, None))
        self.assertIn("Statistics unavailable.", payload["html"])


class PageTests(unittest.TestCase):
    def test_page_shell_uses_the_shared_period_picker(self):
        body = website_stats_page({"username": "owner"}, "csrf", period="nope").decode()
        self.assertIn("id='overview-period-form' method='get' action='/admin/website-stats'", body)
        self.assertIn("<option value='7d' selected>", body)
        self.assertIn("<template id='website-stats-failed'>", body)


if __name__ == "__main__":
    unittest.main()

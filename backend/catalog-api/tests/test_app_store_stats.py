"""App Store statistics (Apple Analytics Reports API, asc_stats): settings,
token, report requests, report files, sync, Admin block, Dashboard card and
routes, all against a fake App Store Connect API (no network)."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import logging
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from admin_test_utils import visible_text
from api_test_fixtures import FakeProviderDatabase
from terento_catalog import asc_stats
from terento_catalog.admin import _overview_downloads_chart, overview_page
from terento_catalog.admin_website_stats import app_store_blocks, website_stats_page
from terento_catalog.asc_stats import (
    AscClient, AscError, AscSettings, AscSync, admin_snapshot, campaign_groups, make_token, parse_report,
)
from terento_catalog.http_api import CatalogService, make_handler

APP = "6828556832"
ISSUER = "69a6de70-03db-47e3-e053-5b8c7c11a4d1"
KEY_ID = "ABCDE12345"
ADMIN_KEY_ID = "ZYXWV98765"
COOKIE = "terento_admin_session=session; terento_admin_csrf=csrf"


def _new_key():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, pem


KEY, PEM = _new_key()
ADMIN_KEY, ADMIN_PEM = _new_key()
PEM_BODY = "".join(line for line in PEM.splitlines() if not line.startswith("-----"))
ENV = {"ASC_ISSUER_ID": ISSUER, "ASC_KEY_ID": KEY_ID, "ASC_PRIVATE_KEY": PEM}


def _decode(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def _tsv(header: list[str], rows: list[list[str]]) -> bytes:
    text = "\n".join("\t".join(row) for row in [header] + rows) + "\n"
    return gzip.compress(text.encode())


ENGAGEMENT_HEADER = ["Date", "App Name", "App Apple Identifier", "Event", "Page Type", "Source Type",
                     "Engagement Type", "Device", "Platform Version", "Territory", "Counts", "Unique Counts"]
DOWNLOAD_HEADER = ["Date", "App Name", "App Apple Identifier", "Download Type", "App Version", "Device",
                   "Platform Version", "Source Type", "Page Type", "Pre-Order", "Territory", "Counts"]
DETAILED_DOWNLOAD_HEADER = DOWNLOAD_HEADER + ["Campaign", "Source Info", "Page Title"]
DETAILED_ENGAGEMENT_HEADER = ENGAGEMENT_HEADER + ["Campaign", "Source Info", "Page Title"]


def engagement(day, event, source, count, page="Product page", territory="LT"):
    return [day, "Terento", APP, event, page, source, "", "Desktop", "macOS 15", territory, str(count), "1"]


def download(day, kind, source, count, territory="LT"):
    return [day, "Terento", APP, kind, "1.2.2", "Desktop", "macOS 15", source, "Product page", "No", territory, str(count)]


class FakeApple:
    """App Store Connect API and the report file host, answering from
    ``self.instances``: {report id: [(instance id, processing date, [file bytes])]}."""

    REPORTS = {
        "r-eng-std": ("APP_STORE_ENGAGEMENT", "App Store Discovery and Engagement Standard"),
        "r-eng-det": ("APP_STORE_ENGAGEMENT", "App Store Discovery and Engagement Detailed"),
        "r-dl-std": ("COMMERCE", "App Downloads Standard"),
        "r-dl-det": ("COMMERCE", "App Downloads Detailed"),
        "r-other": ("COMMERCE", "App Store Purchases Standard"),
    }

    def __init__(self):
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self.requests = [{"id": "req-1", "accessType": "ONGOING", "stopped": False}]
        self.instances: dict[str, list[tuple[str, str, list[bytes]]]] = {name: [] for name in self.REPORTS}
        self.fail: int | None = None
        self.post_status = 201

    def __call__(self, method, url, headers, body, limit):
        self.calls.append((method, url, dict(headers), body))
        parts = urlsplit(url)
        if parts.hostname == "reports.example":
            return 200, self.files[parts.path]
        assert parts.hostname == asc_stats.API_HOST, url
        if self.fail:
            return self.fail, b""
        query = parse_qs(parts.query)
        path = parts.path
        if method == "POST" and path == "/v1/analyticsReportRequests":
            payload = json.loads(body)
            access = payload["data"]["attributes"]["accessType"]
            if self.post_status == 201:
                self.requests.append({"id": f"req-{len(self.requests) + 1}", "accessType": access, "stopped": False})
            return self.post_status, json.dumps({"data": {"id": "new", "attributes": {"accessType": access}}}).encode()
        if path == f"/v1/apps/{APP}/analyticsReportRequests":
            data = [{"type": "analyticsReportRequests", "id": item["id"],
                     "attributes": {"accessType": item["accessType"], "stoppedDueToInactivity": item["stopped"]}}
                    for item in self.requests]
            return 200, json.dumps({"data": data, "links": {}}).encode()
        if path.endswith("/reports"):
            wanted = set(query.get("filter[category]", [""])[0].split(","))
            data = [{"type": "analyticsReports", "id": rid, "attributes": {"category": category, "name": name}}
                    for rid, (category, name) in self.REPORTS.items() if category in wanted]
            # The second page comes through links.next, like Apple.
            if "cursor" not in query:
                return 200, json.dumps({"data": data[:2], "links": {"next": url + "&cursor=2"}}).encode()
            return 200, json.dumps({"data": data[2:], "links": {}}).encode()
        if path.startswith("/v1/analyticsReports/") and path.endswith("/instances"):
            rid = path.split("/")[3]
            assert query["filter[granularity]"] == ["DAILY"]
            data = [{"type": "analyticsReportInstances", "id": iid,
                     "attributes": {"granularity": "DAILY", "processingDate": processing}}
                    for iid, processing, _ in self.instances.get(rid, [])]
            return 200, json.dumps({"data": data, "links": {}}).encode()
        if path.startswith("/v1/analyticsReportInstances/") and path.endswith("/segments"):
            iid = path.split("/")[3]
            files = next(files for items in self.instances.values() for i, _, files in items if i == iid)
            data = []
            for index, raw in enumerate(files):
                name = f"/{iid}/{index}.txt.gz"
                self.files[name] = raw
                data.append({"type": "analyticsReportSegments", "id": f"{iid}-{index}", "attributes": {
                    "checksum": hashlib.md5(raw).hexdigest(), "sizeInBytes": len(raw),
                    "url": f"https://reports.example{name}?X-Amz-Signature=signed-secret"}})
            return 200, json.dumps({"data": data, "links": {}}).encode()
        if path == f"/v1/apps/{APP}":
            return 200, json.dumps({"data": {"id": APP}}).encode()
        raise AssertionError(f"unexpected {method} {url}")

    files: dict[str, bytes] = {}


class FakeAscDatabase:
    """The asc_stats database methods in memory, with the same replace rule
    as db.Database.store_app_store_instance (that SQL is tested on PostgreSQL
    in test_app_store_stats_postgres)."""

    def __init__(self):
        self.metrics: dict[tuple, int] = {}  # (day, level, metric, source, campaign, territory, device) -> count
        self.owner: dict[tuple, date] = {}   # (kind, level, day) -> processing date
        self.instances: dict[str, tuple[str, str, date]] = {}
        self.sync: dict | None = None

    def app_store_processed_instance_ids(self):
        return set(self.instances)

    def store_app_store_instance(self, *, instance_id, kind, level, processing_date, rows):
        if instance_id in self.instances:
            return None
        self.instances[instance_id] = (kind, level, processing_date)
        metrics = asc_stats.KIND_METRICS[kind]
        replaced = 0
        for day in sorted({key[0] for key in rows}):
            owner = self.owner.get((kind, level, day))
            if owner is not None and processing_date < owner:
                continue
            self.owner[(kind, level, day)] = processing_date
            for key in [key for key in self.metrics if key[0] == day and key[1] == level and key[2] in metrics]:
                del self.metrics[key]
            for (row_day, metric, *rest), count in rows.items():
                if row_day == day:
                    self.metrics[(day, level, metric, *rest)] = count
            replaced += 1
        return replaced

    def record_app_store_sync(self, *, attempted_at, succeeded, error, request_state):
        before = self.sync or {}
        self.sync = {"last_attempt_at": attempted_at,
                     "last_success_at": attempted_at if succeeded else before.get("last_success_at"),
                     "last_error": error, "request_state": request_state or before.get("request_state")}

    def app_store_sync_state(self):
        return self.sync

    def app_store_reported_through(self):
        newest: dict[str, date] = {}
        for kind, level, processing in self.instances.values():
            if level == "standard":
                newest[kind] = max(newest.get(kind, processing), processing)
        return {kind: processing - timedelta(days=1) for kind, processing in newest.items()}

    def app_store_first_day(self):
        days = [date.fromisoformat(key[0]) for key in self.metrics if key[1] == "standard"]
        return min(days) if days else None

    def app_store_daily(self, level, first, last):
        out: dict[tuple, int] = {}
        for (day, row_level, metric, source, campaign, _, _), count in self.metrics.items():
            when = date.fromisoformat(day)
            if row_level == level and first <= when <= last:
                key = (when, metric, source, campaign)
                out[key] = out.get(key, 0) + count
        return [{"day": d, "metric": m, "source_type": s, "campaign": c, "count": n} for (d, m, s, c), n in sorted(out.items())]

    def app_store_download_days(self, first, last):
        out: dict[date, int] = {}
        for row in self.app_store_daily("standard", first, last):
            if row["metric"] in ("first_time_downloads", "redownloads"):
                out[row["day"]] = out.get(row["day"], 0) + row["count"]
        return out

    def app_store_download_total(self):
        return sum(count for key, count in self.metrics.items()
                   if key[1] == "standard" and key[2] in ("first_time_downloads", "redownloads"))


def seeded(apple: FakeApple) -> None:
    """Two processing days: the second restates 11-17 (higher) and adds 11-18."""
    apple.instances["r-eng-std"] = [
        ("i-e1", "2026-11-18", [_tsv(ENGAGEMENT_HEADER, [
            engagement("2026-11-16", "Impression", "App Store search", 100),
            engagement("2026-11-16", "Page view", "App Store search", 20),
            engagement("2026-11-16", "Page view", "Web referrer", 10),
            engagement("2026-11-16", "Page view", "App Store search", 5, page="App privacy"),  # not a product page
            engagement("2026-11-17", "Page view", "Web referrer", 8),
            engagement("2026-11-17", "Tap", "Web referrer", 3),  # not counted
        ])]),
        ("i-e2", "2026-11-19", [_tsv(ENGAGEMENT_HEADER, [
            engagement("2026-11-17", "Page view", "Web referrer", 12),
            engagement("2026-11-18", "Impression", "App Store browse", 40),
            engagement("2026-11-18", "Page view", "web referrer", 4),  # values are not case sensitive
        ])]),
    ]
    apple.instances["r-dl-std"] = [
        ("i-d1", "2026-11-18", [_tsv(DOWNLOAD_HEADER, [
            download("2026-11-16", "First-time Download", "App Store search", 6),
            download("2026-11-16", "Redownload", "App Store search", 2),
            download("2026-11-16", "Manual update", "App Store search", 9),  # not a download here
            download("2026-11-17", "First-time Download", "Web referrer", 3),
        ])]),
        ("i-d2", "2026-11-19", [_tsv(DOWNLOAD_HEADER, [
            download("2026-11-17", "First-time Download", "Web referrer", 4),
            download("2026-11-18", "First-time Download", "Web referrer", 2),
            download("2026-11-18", "Redownload", "Web referrer", 1),
        ])]),
    ]
    apple.instances["r-dl-det"] = [
        ("i-dd1", "2026-11-19", [_tsv(DETAILED_DOWNLOAD_HEADER, [
            download("2026-11-17", "First-time Download", "Web referrer", 3) + ["fb-lt", "facebook.com", ""],
            download("2026-11-17", "First-time Download", "Web referrer", 5) + ["rd-fenix", "", ""],
            download("2026-11-18", "First-time Download", "Web referrer", 2) + ["site-home", "", ""],
            download("2026-11-18", "First-time Download", "Web referrer", 7) + ["", "", ""],  # no campaign
        ])]),
    ]
    apple.instances["r-eng-det"] = [
        ("i-ed1", "2026-11-19", [_tsv(DETAILED_ENGAGEMENT_HEADER, [
            engagement("2026-11-17", "Page view", "Web referrer", 9) + ["fb-lt", "", ""],
            engagement("2026-11-17", "Page view", "Web referrer", 20) + ["rd-fenix", "", ""],
            engagement("2026-11-18", "Page view", "Web referrer", 6) + ["fb-en", "", ""],
        ])]),
    ]


def client(apple, clock=lambda: 1_763_000_000.0):
    return AscClient(ISSUER, KEY_ID, KEY, transport=apple, clock=clock)


class SettingsAndTokenTests(unittest.TestCase):
    def test_settings_take_the_key_itself_its_one_line_body_or_a_file(self):
        self.assertIsNone(AscSettings.from_env({}))
        for raw in (PEM, PEM.replace("\n", "\\n"), PEM_BODY):
            with self.subTest(raw=raw[:12]):
                settings = AscSettings.from_env({**ENV, "ASC_PRIVATE_KEY": raw})
                self.assertEqual((settings.issuer_id, settings.key_id, settings.app_id), (ISSUER, KEY_ID, APP))
        with tempfile.NamedTemporaryFile("w", suffix=".p8", delete=False) as handle:
            handle.write(PEM)
        try:
            self.assertIsNotNone(AscSettings.from_env({**ENV, "ASC_PRIVATE_KEY": handle.name}))
        finally:
            os.unlink(handle.name)

    def test_invalid_settings_name_the_setting_never_the_value(self):
        for override, name in (({"ASC_ISSUER_ID": "nope"}, "ASC_ISSUER_ID"), ({"ASC_KEY_ID": "abc"}, "ASC_KEY_ID"),
                               ({"ASC_PRIVATE_KEY": "not-a-key-secret-text"}, "ASC_PRIVATE_KEY")):
            with self.subTest(name=name), self.assertLogs("terento_catalog.asc_stats", "WARNING") as logs:
                self.assertIsNone(AscSettings.from_env({**ENV, **override}))
            text = "\n".join(logs.output)
            self.assertIn(name, text)
            self.assertNotIn(PEM_BODY[:40], text)
            self.assertNotIn("not-a-key-secret-text", text)
        self.assertNotIn(PEM_BODY[:40], repr(AscSettings.from_env(ENV)))

    def test_token_claims_follow_apple(self):
        token = make_token(ISSUER, KEY_ID, KEY, 1_763_000_000.7)
        header, payload, signature = token.split(".")
        self.assertEqual(_decode(header), {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"})
        self.assertEqual(_decode(payload), {"iss": ISSUER, "iat": 1_763_000_000, "exp": 1_763_000_600,
                                            "aud": "appstoreconnect-v1"})
        raw = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        self.assertEqual(len(raw), 64)  # JOSE r||s, not DER
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        KEY.public_key().verify(der, f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))
        with self.assertRaises(ValueError):
            make_token(ISSUER, KEY_ID, KEY, 0, lifetime=21 * 60)

    def test_token_is_reused_then_renewed_before_it_expires(self):
        apple, now = FakeApple(), [1_763_000_000.0]
        api = client(apple, clock=lambda: now[0])
        api.get(f"/v1/apps/{APP}")
        api.get(f"/v1/apps/{APP}")
        now[0] += 545  # within a minute of expiry
        api.get(f"/v1/apps/{APP}")
        tokens = [call[2]["Authorization"] for call in apple.calls]
        self.assertEqual(tokens[0], tokens[1])
        self.assertNotEqual(tokens[1], tokens[2])


class ClientTests(unittest.TestCase):
    def test_the_token_goes_only_to_apples_api_host(self):
        apple = FakeApple()
        seeded(apple)
        AscSync(FakeAscDatabase(), client(apple), APP).run_once()
        for method, url, headers, _ in apple.calls:
            host = urlsplit(url).hostname
            self.assertEqual("Authorization" in headers, host == asc_stats.API_HOST, url)
        self.assertTrue(any(urlsplit(url).hostname == "reports.example" for _, url, _, _ in apple.calls))

    def test_another_host_or_plain_http_is_refused_before_sending(self):
        api = client(FakeApple())
        for url in ("https://evil.example/v1/apps", "http://api.appstoreconnect.apple.com/v1/apps",
                    "https://api.appstoreconnect.apple.com.evil.example/v1/apps",
                    "https://user@api.appstoreconnect.apple.com/v1/apps"):
            with self.subTest(url=url), self.assertRaises(AscError):
                api.get(url)
        with self.assertRaises(AscError):
            api.download("http://reports.example/x")

    def test_a_next_link_to_another_host_stops(self):
        def answer(method, url, headers, body, limit):
            return 200, json.dumps({"data": [], "links": {"next": "https://evil.example/next"}}).encode()
        with self.assertRaises(AscError) as caught:
            list(client(answer).pages("/v1/apps/1/analyticsReportRequests"))
        self.assertEqual(caught.exception.reason, "unexpected address")

    def test_errors_and_oversized_answers_are_reasons_only(self):
        api = client(lambda *args: (401, b""))
        with self.assertRaises(AscError) as caught:
            api.get(f"/v1/apps/{APP}")
        self.assertEqual((caught.exception.reason, caught.exception.status), ("HTTP 401", 401))
        api = client(lambda *args: (200, b"x" * (asc_stats.MAX_RESPONSE_BYTES + 1)))
        with self.assertRaises(AscError) as caught:
            api.get(f"/v1/apps/{APP}")
        self.assertEqual(caught.exception.reason, "response too large")


class ReportFileTests(unittest.TestCase):
    def test_columns_are_found_by_name_and_an_unknown_column_is_ignored(self):
        header = ["Territory", "Brand New Column", "Counts", "Date", "Source Type", "Download Type", "App Apple Identifier"]
        raw = _tsv(header, [["LT", "whatever", "3", "2026-11-17", "App Store search", "First-time Download", APP],
                            ["DE", "x", "2", "2026-11-17", "app store search", "first-time download", APP],
                            ["DE", "x", "9", "2026-11-17", "App Store search", "First-time Download", "999"],  # other app
                            ["DE", "x", "bad", "2026-11-17", "App Store search", "First-time Download", APP]])
        rows = parse_report(raw, "downloads", "standard", APP)
        self.assertEqual(rows, {("2026-11-17", "first_time_downloads", "App Store search", "", "LT", ""): 3,
                                ("2026-11-17", "first_time_downloads", "App Store search", "", "DE", ""): 2})

    def test_a_missing_column_stops_the_instance(self):
        with self.assertRaises(AscError) as caught:
            parse_report(_tsv(["Date", "Counts", "Territory"], [["2026-11-17", "1", "LT"]]), "downloads", "standard", APP)
        self.assertIn("download type", caught.exception.reason)

    def test_detailed_rows_keep_only_campaign_rows(self):
        raw = _tsv(DETAILED_DOWNLOAD_HEADER, [
            download("2026-11-17", "First-time Download", "Web referrer", 3) + ["fb-lt", "", ""],
            download("2026-11-17", "First-time Download", "Web referrer", 4) + ["", "", ""]])
        rows = parse_report(raw, "downloads", "detailed", APP)
        self.assertEqual(list(rows.values()), [3])
        self.assertEqual(next(iter(rows))[3], "fb-lt")

    def test_a_file_that_is_not_gzip_or_too_large_is_refused(self):
        with self.assertRaises(AscError):
            parse_report(b"\x1f\x8bnot really gzip", "downloads", "standard", APP)
        self.assertEqual(parse_report(b"", "downloads", "standard", APP), {})

    def test_report_names(self):
        self.assertEqual(asc_stats.report_kind("COMMERCE", "App Downloads Standard"), ("downloads", "standard"))
        self.assertEqual(asc_stats.report_kind("COMMERCE", "App Store Downloads Detailed"), ("downloads", "detailed"))
        self.assertEqual(asc_stats.report_kind("APP_STORE_ENGAGEMENT", "App Store Discovery and Engagement Detailed"),
                         ("engagement", "detailed"))
        self.assertIsNone(asc_stats.report_kind("COMMERCE", "App Store Purchases Standard"))
        self.assertIsNone(asc_stats.report_kind("APP_USAGE", "App Downloads Standard"))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.apple = FakeApple()
        seeded(self.apple)
        self.db = FakeAscDatabase()

    def run_sync(self):
        return AscSync(self.db, client(self.apple), APP).run_once()

    def test_a_second_run_never_doubles_a_count(self):
        first = self.run_sync()
        self.assertEqual((first["instances"], first["error"], first["request"]), (6, None, "active"))
        before = dict(self.db.metrics)
        calls = len(self.apple.calls)
        second = self.run_sync()
        self.assertEqual((second["instances"], self.db.metrics), (0, before))
        downloads = [call for call in self.apple.calls[calls:] if urlsplit(call[1]).hostname == "reports.example"]
        self.assertEqual(downloads, [])  # processed instances are not downloaded again
        # Even a forced re-store of the same instance changes nothing.
        self.assertIsNone(self.db.store_app_store_instance(instance_id="i-d2", kind="downloads", level="standard",
                                                           processing_date=date(2026, 11, 19), rows={}))

    def test_a_newer_processing_date_replaces_a_day_and_an_older_one_does_not(self):
        self.run_sync()
        standard = admin_snapshot(self.db, "all", configured=True)["data"]
        self.assertEqual(standard["days"][1]["date"], "2026-11-17")
        self.assertEqual(standard["days"][1]["product_page_views"], 12)  # i-e2 replaced i-e1's 8
        self.assertEqual(standard["days"][1]["first_time_downloads"], 4)
        self.db.store_app_store_instance(instance_id="old", kind="downloads", level="standard",
                                         processing_date=date(2026, 11, 17),
                                         rows={("2026-11-17", "first_time_downloads", "Web referrer", "", "LT", ""): 99})
        again = admin_snapshot(self.db, "all", configured=True)["data"]
        self.assertEqual(again["days"][1]["first_time_downloads"], 4)

    def test_totals_sources_campaigns_and_period(self):
        self.run_sync()
        snapshot = admin_snapshot(self.db, "7d", configured=True)
        self.assertEqual((snapshot["state"], snapshot["startDate"], snapshot["endDate"]), ("ok", "2026-11-12", "2026-11-18"))
        totals = snapshot["data"]["totals"]
        self.assertEqual((totals["impressions"], totals["product_page_views"], totals["first_time_downloads"],
                          totals["redownloads"]), (140, 20 + 10 + 12 + 4, 6 + 4 + 2, 2 + 1))
        self.assertAlmostEqual(totals["conversion"], 12 / 46)
        self.assertEqual(snapshot["data"]["previousTotals"]["first_time_downloads"], 0)
        sources = {row["source"]: row for row in snapshot["data"]["sources"]}
        self.assertEqual(sources["Web referrer"]["product_page_views"], 26)
        self.assertEqual(sources["App Store search"]["first_time_downloads"], 6)
        groups = snapshot["data"]["campaigns"]
        self.assertEqual([group["group"] for group in groups], ["Reddit", "Facebook", "Site"])
        self.assertEqual(groups[1]["campaigns"][0], {"campaign": "fb-lt", "product_page_views": 9,
                                                     "first_time_downloads": 3, "conversion": 3 / 9})
        self.assertEqual(groups[1]["first_time_downloads"], 3)

    def test_apple_failure_keeps_the_last_result(self):
        self.run_sync()
        self.apple.fail = 503
        with self.assertLogs("terento_catalog.asc_stats", "WARNING") as logs:
            summary = self.run_sync()
        self.assertEqual(summary["error"], "HTTP 503")
        snapshot = admin_snapshot(self.db, "30d", configured=True)
        self.assertEqual(snapshot["state"], "stale")
        self.assertEqual(snapshot["data"]["totals"]["first_time_downloads"], 12)
        self.assertNotIn("signed-secret", "\n".join(logs.output))

    def test_a_broken_checksum_stops_without_storing(self):
        original = self.apple.__call__

        def corrupt(method, url, headers, body, limit):
            status, raw = original(method, url, headers, body, limit)
            return (status, raw + b"x") if urlsplit(url).hostname == "reports.example" else (status, raw)
        with self.assertLogs("terento_catalog.asc_stats", "WARNING"):
            summary = AscSync(self.db, client(corrupt), APP).run_once()
        self.assertEqual((summary["error"], self.db.instances), ("report file checksum mismatch", {}))

    def test_no_request_and_a_stopped_request(self):
        self.apple.requests = []
        self.assertEqual(self.run_sync()["error"], "no report request")
        self.assertEqual(admin_snapshot(self.db, "30d", configured=True)["state"], "not_set_up")
        self.apple.requests = [{"id": "req-1", "accessType": "ONGOING", "stopped": True}]
        self.assertEqual(self.run_sync()["error"], "report request stopped")

    def test_the_schedule_runs_at_once_then_waits(self):
        stop, runs = threading.Event(), []

        class Once:
            def run_once(self):
                runs.append(1)
                stop.set()
                return {"instances": 0, "days": 0, "request": "active", "error": None}
        asc_stats.run_schedule(None, stop, None, sync_factory=Once)
        self.assertEqual(runs, [1])


class CampaignGroupTests(unittest.TestCase):
    def test_groups_by_prefix_with_totals_most_downloads_first(self):
        groups = campaign_groups({
            "fb-en": {"product_page_views": 10, "first_time_downloads": 1},
            "FB-IT": {"product_page_views": 5, "first_time_downloads": 4},
            "rd-watches": {"product_page_views": 0, "first_time_downloads": 6},
            "site-download": {"product_page_views": 3, "first_time_downloads": 2},
            "newsletter": {"product_page_views": 7, "first_time_downloads": 0},
        })
        self.assertEqual([(g["group"], g["first_time_downloads"], g["product_page_views"]) for g in groups],
                         [("Reddit", 6, 0), ("Facebook", 5, 15), ("Site", 2, 3), ("Other", 0, 7)])
        self.assertEqual([item["campaign"] for item in groups[1]["campaigns"]], ["FB-IT", "fb-en"])
        self.assertIsNone(groups[0]["conversion"])
        self.assertEqual(campaign_groups({}), [])


class RequestCommandTests(unittest.TestCase):
    def run_command(self, *args, apple, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        old = os.sys.stdin
        os.sys.stdin = io.StringIO(stdin)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = asc_stats.main(["request", *args], environ={"ASC_ISSUER_ID": ISSUER}, transport=apple)
        finally:
            os.sys.stdin = old
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_changes_nothing_then_apply_creates_then_finds_it(self):
        apple = FakeApple()
        apple.requests = []
        code, out, _ = self.run_command("--admin-key-id", ADMIN_KEY_ID, "--admin-key-stdin", apple=apple, stdin=ADMIN_PEM)
        self.assertEqual(code, 0)
        self.assertIn("ONGOING report request: missing (none); run again with --apply", out)
        self.assertFalse(any(call[0] == "POST" for call in apple.calls))
        code, out, _ = self.run_command("--apply", "--admin-key-id", ADMIN_KEY_ID, "--admin-key-stdin", apple=apple, stdin=ADMIN_PEM)
        self.assertEqual(code, 0)
        self.assertIn("ONGOING report request: created", out)
        self.assertIn("ONE_TIME_SNAPSHOT report request: created", out)
        posts = [json.loads(call[3]) for call in apple.calls if call[0] == "POST"]
        self.assertEqual([(p["data"]["attributes"]["accessType"], p["data"]["relationships"]["app"]["data"]["id"])
                          for p in posts], [("ONGOING", APP), ("ONE_TIME_SNAPSHOT", APP)])
        # The Admin key signed these calls.
        kid = {_decode(call[2]["Authorization"].removeprefix("Bearer ").split(".")[0])["kid"] for call in apple.calls}
        self.assertEqual(kid, {ADMIN_KEY_ID})
        code, out, _ = self.run_command("--apply", "--admin-key-id", ADMIN_KEY_ID, "--admin-key-stdin", apple=apple, stdin=ADMIN_PEM)
        self.assertEqual(out.count("already existed"), 2)
        self.assertEqual(len([call for call in apple.calls if call[0] == "POST"]), 2)

    def test_a_conflict_means_it_already_existed(self):
        apple = FakeApple()
        apple.requests, apple.post_status = [], 409
        code, out, _ = self.run_command("--apply", "--no-history", "--admin-key-id", ADMIN_KEY_ID, "--admin-key-stdin",
                                        apple=apple, stdin=ADMIN_PEM)
        self.assertEqual((code, out.strip()), (0, "ONGOING report request: already existed"))

    def test_apply_needs_the_admin_key_and_output_has_no_key(self):
        apple = FakeApple()
        code, _, err = self.run_command("--apply", apple=apple)
        self.assertEqual(code, 2)
        self.assertIn("needs the Admin key", err)
        with tempfile.NamedTemporaryFile("w", suffix=".p8", delete=False) as handle:
            handle.write(ADMIN_PEM)
        try:
            code, out, err = self.run_command("--admin-key-id", ADMIN_KEY_ID, "--admin-key-file", handle.name, apple=apple)
        finally:
            os.unlink(handle.name)
        body = "".join(line for line in ADMIN_PEM.splitlines() if not line.startswith("-----"))
        for text in (out, err):
            self.assertNotIn(body[:30], text)
            self.assertNotIn("Bearer", text)
            self.assertNotIn("eyJ", text)


class BlockTests(unittest.TestCase):
    def snapshot(self, period="30d"):
        apple, db = FakeApple(), FakeAscDatabase()
        seeded(apple)
        AscSync(db, client(apple), APP).run_once()
        return admin_snapshot(db, period, configured=True), db

    def test_the_block_has_kpis_trend_sources_campaigns_and_lines(self):
        snapshot, _ = self.snapshot()
        markup = app_store_blocks(snapshot)
        text = visible_text(markup)
        for label in ("App Store", "Impressions", "Product page views", "First-time downloads", "Conversion",
                      "Trend", "Sources", "Campaigns", "Facebook", "Reddit", "Site", "fb-lt", "rd-fenix",
                      "Open App Store Connect", asc_stats.CONSOLE_URL and "App Store Connect · data updated daily, about 1–2 days late",
                      "Apple shows a campaign only after a day and at least 5 downloads; small sources may be hidden."):
            self.assertIn(label, text if not label.startswith("http") else markup)
        self.assertIn("vs previous 30 days", text)
        self.assertIn("target='_blank'", markup)
        self.assertIn("id='asc-period'", markup)
        self.assertNotIn("unavailable", text.lower())
        self.assertNotIn("not-a-campaign", text)

    def test_not_set_up_unavailable_waiting_and_stale(self):
        self.assertIn("App Store statistics are not set up.", visible_text(app_store_blocks(
            admin_snapshot(FakeAscDatabase(), "30d", configured=False))))
        self.assertIn("App Store unavailable.", visible_text(app_store_blocks(None)))
        db = FakeAscDatabase()
        self.assertIn("No App Store data yet.", visible_text(app_store_blocks(admin_snapshot(db, "30d", configured=True))))
        db.record_app_store_sync(attempted_at=datetime(2026, 11, 20, tzinfo=timezone.utc), succeeded=False,
                                 error="HTTP 401", request_state=None)
        self.assertIn("App Store unavailable.", visible_text(app_store_blocks(admin_snapshot(db, "30d", configured=True))))
        snapshot, db = self.snapshot()
        db.record_app_store_sync(attempted_at=datetime.now(timezone.utc) + timedelta(hours=1), succeeded=False,
                                 error="timeout", request_state=None)
        stale = app_store_blocks(admin_snapshot(db, "30d", configured=True))
        self.assertIn("App Store unavailable", visible_text(stale))
        self.assertIn("Last result", visible_text(stale))
        self.assertIn("Campaigns", visible_text(stale))

    def test_its_own_period(self):
        for period, expected in (("7d", "7d"), ("all", "all"), ("24h", "30d"), ("nope", "30d")):
            with self.subTest(period=period):
                snapshot, _ = self.snapshot(period)
                self.assertEqual(snapshot["period"], expected)
                self.assertIn(f"<option value='{expected}' selected>", app_store_blocks(snapshot))

    def test_the_page_loads_app_store_after_google_search(self):
        body = website_stats_page({"username": "owner"}, "csrf", period="7d").decode()
        self.assertLess(body.index("id='web-visits-gsc'"), body.index("id='web-visits-asc'"))
        self.assertIn("/admin/api/app-store", body)
        self.assertIn("<template id='asc-failed'>", body)


class _Database(FakeProviderDatabase, FakeAscDatabase):
    def __init__(self):
        FakeAscDatabase.__init__(self)

    def delete_admin_session(self, token_hash):
        pass


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.db = _Database()
        apple = FakeApple()
        seeded(apple)
        AscSync(self.db, client(apple), APP).run_once()
        self.service = CatalogService(self.db, app_store_configured=True)
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

    def test_the_endpoint_is_admin_only(self):
        for cookie in (None, "terento_admin_session=wrong; terento_admin_csrf=csrf", "terento_admin_session=session"):
            with self.subTest(cookie=cookie):
                response, body = self.get("/admin/api/app-store?period=7d", cookie=cookie)
                self.assertEqual((response.status, json.loads(body)), (401, {"error": "unauthorized"}))

    def test_the_answer_has_blocks_and_no_secret(self):
        response, body = self.get("/admin/api/app-store")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
        payload = json.loads(body)
        self.assertEqual((payload["configured"], payload["period"], payload["state"]), (True, "30d", "ok"))
        self.assertIn("id='web-visits-asc'", payload["html"])
        for secret in (PEM_BODY[:30], "Bearer", "eyJ", "signed-secret", KEY_ID):
            self.assertNotIn(secret, body)

    def test_never_the_admin_period(self):
        _, body = self.get("/admin/api/app-store", cookie=COOKIE + "; terento_admin_period=7d")
        self.assertEqual(json.loads(body)["period"], "30d")

    def test_without_settings_it_says_not_set_up(self):
        self.service.app_store_configured = False
        _, body = self.get("/admin/api/app-store?period=7d")
        payload = json.loads(body)
        self.assertEqual((payload["configured"], payload["state"], payload["data"]), (False, "not_set_up", None))
        self.assertIn("App Store statistics are not set up.", payload["html"])

    def test_a_database_failure_is_unavailable_and_the_page_still_answers(self):
        def broken():
            raise RuntimeError("boom")
        self.db.app_store_sync_state = broken
        with self.assertLogs("terento_catalog.http_api", "ERROR"):
            _, body = self.get("/admin/api/app-store")
        self.assertIn("App Store unavailable.", json.loads(body)["html"])


def _trend(bucket_starts: list[str]) -> list[dict]:
    return [{"bucket": start, "observed_at": start, "state": "observed_increase", "dmg_count": 1, "zip_count": 0,
             "confidence": "verified"} for start in bucket_starts]


class DashboardTests(unittest.TestCase):
    STORE = {"reportedThrough": "2026-11-18", "firstDay": "2026-11-16",
             "days": {"2026-11-16": 8, "2026-11-17": 4, "2026-11-18": 3}, "total": 15,
             "updatedAt": "2026-11-20T06:00:00+00:00"}

    def test_day_buckets_show_reported_days_only(self):
        days = [f"2026-11-{day:02d}T00:00:00+00:00" for day in range(14, 21)]
        counts = asc_stats_counts(self.STORE, _trend(days), "day")
        # 11-14/15 are before Apple's first day, 11-19/20 not reported yet: no value, never 0.
        self.assertEqual(counts, [None, None, 8, 4, 3, None, None])
        chart = _overview_downloads_chart({"trend": _trend(days), "bucket": "day"}, period="7d", app_store=self.STORE)
        self.assertEqual(chart.count("<rect class='overview-chart-download-app-store'"), 2 * 3)  # desktop and phone charts
        self.assertIn("App Store (daily, 1–2 days late)", visible_text(chart))
        self.assertIn("App Store downloads (Apple, daily): 8", chart)
        self.assertIn("Observed increase: 1", chart)  # the GitHub increase never adds App Store

    def test_hour_buckets_have_no_app_store_segment(self):
        hours = [f"2026-11-18T{hour:02d}:00:00+00:00" for hour in range(0, 24)]
        self.assertEqual(asc_stats_counts(self.STORE, _trend(hours), "hour"), [None] * 24)
        chart = _overview_downloads_chart({"trend": _trend(hours), "bucket": "hour"}, period="24h", app_store=self.STORE)
        self.assertNotIn("<rect class='overview-chart-download-app-store'", chart)
        self.assertIn("App Store: no data for this period", visible_text(chart))

    def test_week_buckets_sum_reported_days(self):
        counts = asc_stats_counts(self.STORE, _trend(["2026-11-09T00:00:00+00:00", "2026-11-16T00:00:00+00:00"]), "week")
        self.assertEqual(counts, [None, 15])

    def test_without_settings_the_card_is_unchanged(self):
        days = [f"2026-11-{day:02d}T00:00:00+00:00" for day in range(14, 21)]
        chart = _overview_downloads_chart({"trend": _trend(days), "bucket": "day"}, period="7d")
        self.assertNotIn("App Store", chart)

    def test_tile_and_all_time_line(self):
        from terento_catalog.admin import _app_store_period_total
        self.assertEqual(_app_store_period_total(self.STORE, "2026-11-14T00:00:00+00:00", "UTC"), 15)
        self.assertEqual(_app_store_period_total(self.STORE, "2026-11-17T00:00:00+00:00", "UTC"), 7)
        self.assertIsNone(_app_store_period_total(self.STORE, "2026-11-19T10:00:00+00:00", "UTC"))
        self.assertEqual(_app_store_period_total(self.STORE, "2026-11-16T10:00:00+00:00", "UTC"), 7)  # 11-16 only partly in


def asc_stats_counts(store, trend, bucket):
    from terento_catalog.admin import _app_store_bucket_counts
    return _app_store_bucket_counts(store, trend, bucket, "UTC")


if __name__ == "__main__":
    unittest.main()

import json
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection
from unittest.mock import patch

from api_test_fixtures import FakeProviderDatabase, UTC
from terento_catalog.http_api import CatalogService, make_handler


class CatalogAPITests(unittest.TestCase):
    def test_http_map_events_and_admin_provider_routes(self):
        database = FakeProviderDatabase()
        service = CatalogService(database)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cookie = "terento_admin_session=session; terento_admin_csrf=csrf"
            response, body = self._request(server, "GET", "/admin/providers.json", headers={"Cookie": cookie})
            self.assertEqual(response.status, 200)
            self.assertEqual({provider["id"] for provider in json.loads(body)["providers"]},
                             {"freizeitkarte", "opentopomap", "maprando", "bbbike"})
            self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

            with patch.object(service, "admin_devices", return_value={"devices": []}):
                identification, identification_body = self._request(
                    server, "GET", "/admin/device-identification?q=missing", headers={"Cookie": cookie}
                )
                self.assertEqual(identification.status, 200)
                self.assertIn(b"No matching models.", identification_body)
                self.assertEqual(identification.headers["Cache-Control"], "no-store")
                self.assertEqual(identification.headers["X-Robots-Tag"], "noindex, nofollow")
            handler = make_handler(service)
            self.assertEqual(handler._safe_admin_return("/admin/device-identification?device=test", "/admin"), "/admin/device-identification?device=test")
            self.assertEqual(handler._safe_admin_return("//evil.example/admin/device-identification", "/admin"), "/admin")

            test_data, test_data_body = self._request(
                server, "GET", "/admin/test-data", headers={"Cookie": cookie}
            )
            self.assertEqual(test_data.status, 200)
            self.assertIn(b"1.0.0-beta.10-local", test_data_body)
            invalid_purge, _ = self._request(
                server,
                "POST",
                "/admin/test-data/purge",
                b"csrf_token=csrf&confirmation=wrong",
                {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie},
            )
            self.assertEqual(invalid_purge.status, 400)
            purge, _ = self._request(
                server,
                "POST",
                "/admin/test-data/purge",
                b"csrf_token=csrf&confirmation=DELETE_LOCAL_TEST_DATA",
                {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie, "X-Request-Id": "local-test-1"},
            )
            self.assertEqual(purge.status, 303)
            self.assertEqual(database.local_purge_calls[0]["request_id"], "local-test-1")

            event = json.dumps({
                "schemaVersion": 1,
                "id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
                "operationId": "b8098c1a-f86e-11da-bd1a-00112444be1e",
                "timestamp": "2026-08-31T10:00:00Z",
                "providerId": "freizeitkarte",
                "mapId": "fzk-ltu",
                "region": "LT",
                "eventType": "INSTALL_SUCCEEDED",
                "outcome": "SUCCEEDED",
                "appBuild": "beta.8",
                "releaseLabel": "1.0.0-beta.8",
            }).encode()
            first, first_body = self._request(server, "POST", "/map-events", event, {"Content-Type": "application/json"})
            second, second_body = self._request(server, "POST", "/map-events", event, {"Content-Type": "application/json"})
            self.assertEqual(first.status, 201)
            self.assertEqual(second.status, 200)
            self.assertEqual(json.loads(first_body)["operationId"], json.loads(second_body)["operationId"])

            with patch("terento_catalog.http_api.run_provider_health_check") as health_check:
                health_check.return_value = type("Health", (), {
                    "status": "HEALTHY",
                    "as_database_values": lambda self: {"provider_id": "freizeitkarte", "status": "HEALTHY"},
                })()
                checked, checked_body = self._request(
                    server,
                    "POST",
                    "/admin/providers/freizeitkarte/check",
                    b"{}",
                    {"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": "csrf"},
                )
            self.assertEqual(checked.status, 200)
            self.assertEqual(json.loads(checked_body)["status"], "ok")
            self.assertTrue(database.audits)

            statistics, statistics_body = self._request(
                server,
                "GET",
                "/admin/map-statistics.json?provider=freizeitkarte&region=lt&period=24h",
                headers={"Cookie": cookie},
            )
            self.assertEqual(statistics.status, 200)
            statistics_payload = json.loads(statistics_body)
            self.assertEqual(statistics_payload["rows"][0]["region"], "LT")
            self.assertEqual(statistics_payload["detailPageSize"], 25)
            self.assertEqual(statistics_payload["detailTotal"], 1)
            self.assertEqual(len(statistics_payload["detailRows"]), 1)
            self.assertEqual(statistics_payload["filters"]["period"], "24h")
            self.assertEqual(statistics_payload["rows"][0]["display_name"], "Lithuania")
            self.assertEqual(statistics_payload["rows"][0]["region_display_name"], "Lithuania")
            self.assertEqual(statistics_payload["linkage"]["mapInstallationCount"], 1)
            self.assertEqual(statistics_payload["linkage"]["mapOnlyInstallationCount"], 1)
            self.assertEqual(statistics_payload["linkage"]["linkedInstallationCount"], 0)

            state, state_body = self._request(
                server,
                "POST",
                "/admin/providers/freizeitkarte/state",
                json.dumps({"status": "paused"}).encode(),
                {"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": "csrf"},
            )
            self.assertEqual(state.status, 200)
            self.assertEqual(json.loads(state_body)["result"]["status"], "PAUSED")

            blocked, blocked_body = self._request(
                server,
                "POST",
                "/admin/providers/freizeitkarte/state",
                json.dumps({"status": "active"}).encode(),
                {"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": "csrf"},
            )
            self.assertEqual(blocked.status, 409)
            self.assertEqual(
                json.loads(blocked_body)["error"],
                "provider_activation_blocked",
            )
            self.assertEqual(database.status, "PAUSED")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_overview_period_reaches_the_private_query_and_rendered_state(self):
        database = FakeProviderDatabase()
        service = CatalogService(database)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cookie = "terento_admin_session=session; terento_admin_csrf=csrf"
            response, body = self._request(
                server, "GET", "/admin?period=30d&timeZone=Europe%2FVilnius",
                headers={"Cookie": cookie},
            )
            self.assertEqual(response.status, 200)
            self.assertEqual(database.overview_map_requests[-1][1], "30d")
            self.assertEqual(database.overview_map_requests[-1][2], "Europe/Vilnius")
            self.assertEqual(database.overview_download_requests[-1], ("30d", "Europe/Vilnius"))
            self.assertIn("value='30d' selected", body.decode())
            self.assertIn("overview-download-total' aria-label='.dmg downloads total: 23'><strong>23</strong><small>.dmg", body.decode())

            response, body = self._request(
                server, "GET", "/admin?period=all", headers={"Cookie": cookie},
            )
            self.assertEqual(response.status, 200)
            self.assertEqual(database.overview_map_requests[-1][1], "all")
            self.assertIn("value='all' selected", body.decode())
            self.assertEqual(database.overview_download_requests[-1], ("all", "UTC"))
            self.assertLess(
                database.overview_map_requests[-1][0],
                database.overview_map_requests[-2][0],
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_provider_activation_requires_complete_health_and_catalog_gate(self):
        database = FakeProviderDatabase()
        database.status = "PAUSED"
        database.detail_overrides["opentopomap"] = {
            "provider_id": "opentopomap",
            "provider_name": "OpenTopoMap",
            "adapter_id": "opentopomap",
            "status": "PAUSED",
            "last_catalog_sync": datetime(2026, 8, 31, tzinfo=UTC),
            "health": {"status": "HEALTHY"},
            "packages": [
                {
                    "availability": "AVAILABLE",
                    "artifact_count": 1,
                    "main_artifact_count": 1,
                    "broken_artifact_count": 0,
                    "unvalidated_artifact_count": 0,
                }
                for _ in range(177)
            ],
        }
        database.run_overrides["opentopomap"] = [{
            "status": "SUCCEEDED",
            "package_count": 177,
            "artifact_count": 177,
        }]

        service = CatalogService(database)
        gate = service.provider_activation_gate("opentopomap")
        self.assertTrue(gate["canActivate"])
        self.assertEqual(gate["blockers"], [])
        result = service.set_provider_status(
            "opentopomap",
            "ACTIVE",
            admin_user_id=7,
            reason="validated",
        )
        self.assertEqual(result, {"id": "opentopomap", "status": "ACTIVE"})

    def test_map_statistics_period_overrides_stale_date_from(self):
        database = FakeProviderDatabase()
        service = CatalogService(database)
        stale_date = "2000-01-01T00:00:00+00:00"

        for period in ("24h", "7d", "30d"):
            database.map_statistic_filters.clear()
            service.map_statistics({"period": period, "dateFrom": stale_date})
            self.assertEqual(len(database.map_statistic_filters), 2)
            self.assertNotEqual(database.map_statistic_filters[0]["dateFrom"], stale_date)
            self.assertEqual(
                database.map_statistic_filters[0]["dateFrom"],
                database.map_statistic_filters[1]["dateFrom"],
            )

        database.map_statistic_filters.clear()
        service.map_statistics({"period": "all", "dateFrom": stale_date})
        self.assertEqual(
            database.map_statistic_filters[0]["dateFrom"].isoformat(),
            stale_date,
        )

    def test_map_statistics_event_filters_only_change_detail_not_population_summary(self):
        class PopulationDatabase(FakeProviderDatabase):
            rows = [
                {"event_type": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED", "event_count": 4, "operation_count": 4},
                {"event_type": "DOWNLOAD_FAILED", "outcome": "FAILED", "event_count": 1, "operation_count": 1},
                {"event_type": "INSTALL_SUCCEEDED", "outcome": "SUCCEEDED", "event_count": 9, "operation_count": 9},
                {"event_type": "INSTALL_FAILED", "outcome": "FAILED", "event_count": 1, "operation_count": 1},
                {"event_type": "MAP_UPDATE_SUCCEEDED", "outcome": "SUCCEEDED", "event_count": 3, "operation_count": 3},
                {"event_type": "MAP_UPDATE_FAILED", "outcome": "FAILED", "event_count": 2, "operation_count": 2},
            ]

            def map_statistics(self, filters, *, limit=None, offset=0):
                self.map_statistic_filters.append(dict(filters))
                rows = list(self.rows)
                if filters.get("eventType"):
                    rows = [row for row in rows if row["event_type"] == filters["eventType"]]
                if filters.get("outcome"):
                    rows = [row for row in rows if row["outcome"] == filters["outcome"]]
                return rows[offset: offset + limit] if limit is not None else rows

        database = PopulationDatabase()
        payload = CatalogService(database).map_statistics({
            "period": "all", "provider": "freizeitkarte", "eventType": "INSTALL_FAILED",
        })
        self.assertEqual(payload["summary"]["completedInstalls"], 9)
        self.assertEqual(payload["summary"]["failedInstalls"], 1)
        self.assertEqual(payload["summary"]["installSuccessRate"], 90.0)
        self.assertEqual(payload["summary"]["downloadSuccessRate"], 80.0)
        self.assertEqual(payload["summary"]["mapUpdateSuccessRate"], 60.0)
        self.assertEqual(payload["detailTotal"], 1)
        self.assertNotIn("eventType", database.map_statistic_filters[0])
        self.assertEqual(database.map_statistic_filters[1]["eventType"], "INSTALL_FAILED")
        self.assertEqual(database.map_statistic_filters[2]["eventType"], "INSTALL_FAILED")
        self.assertEqual(database.map_statistic_filters[0]["provider"], "freizeitkarte")

    def test_admin_pages_require_login_and_render_provider_statistics_views(self):
        database = FakeProviderDatabase()
        service = CatalogService(database)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/admin", "/admin/installations", "/admin/providers", "/admin/map-statistics", "/admin/providers/freizeitkarte"):
                response, _ = self._request(server, "GET", path)
                self.assertEqual(response.status, 303)
                self.assertEqual(response.headers["Location"], "/admin/login")

            cookie = "terento_admin_session=session; terento_admin_csrf=csrf"
            providers, providers_body = self._request(server, "GET", "/admin/providers", headers={"Cookie": cookie})
            self.assertEqual(providers.status, 200)
            self.assertIn(b"Providers", providers_body)
            self.assertIn(b"Freizeitkarte", providers_body)

            detail, detail_body = self._request(server, "GET", "/admin/providers/freizeitkarte", headers={"Cookie": cookie})
            self.assertEqual(detail.status, 200)
            self.assertIn(b"Metadata and attribution", detail_body)
            self.assertIn(b"Health check history", detail_body)
            self.assertIn(b"Collect catalog", detail_body)

            database.status = "PAUSED"
            blocked_detail, blocked_detail_body = self._request(
                server,
                "GET",
                "/admin/providers/freizeitkarte",
                headers={"Cookie": cookie},
            )
            self.assertEqual(blocked_detail.status, 200)
            self.assertIn(b"data-provider-status='ACTIVE' disabled", blocked_detail_body)
            self.assertIn(b"Activation blocked.", blocked_detail_body)

            statistics, statistics_body = self._request(server, "GET", "/admin/map-statistics", headers={"Cookie": cookie})
            self.assertEqual(statistics.status, 200)
            self.assertIn(b"Map statistics", statistics_body)
            self.assertIn(b"7 days", statistics_body)
            self.assertIn(b"Fresh install success", statistics_body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    @staticmethod
    def _request(server, method, path, body=None, headers=None):
        connection = HTTPConnection(*server.server_address)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data

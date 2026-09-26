from datetime import datetime, timezone

from terento_catalog.admin import token_hash


UTC = timezone.utc


class FakeProviderDatabase:
    def operational_health_snapshot(self):
        return {}

    def __init__(self) -> None:
        self.events: set[str] = set()
        self.status = "ACTIVE"
        self.audits: list[dict] = []
        self.detail_overrides: dict[str, dict] = {}
        self.run_overrides: dict[str, list[dict]] = {}
        self.map_statistic_filters: list[dict] = []
        self.overview_map_requests: list[tuple[datetime, str, str]] = []
        self.overview_download_requests: list[tuple[str, str]] = []
        self.local_purge_calls: list[dict] = []

    def admin_user_count(self) -> int:
        return 1

    def admin_review_summary(self):
        return {
            "installationIssues": 0,
            "identityPending": 0,
            "readyToPublish": 0,
            "total": 0,
        }

    def local_test_telemetry_summary(self):
        return {
            "diagnosticEventCount": 2,
            "mapEventCount": 3,
            "operationCount": 1,
            "releaseLabels": ["1.0.0-beta.10-local"],
        }

    def purge_local_test_telemetry(self, **kwargs):
        self.local_purge_calls.append(kwargs)
        return {"diagnosticEventCount": 2, "mapEventCount": 3, "operationCount": 1}

    def admin_overview_snapshot(self, since):
        return {
            "operationCount": 0,
            "successfulInstallCount": 0,
            "failedInstallCount": 0,
            "openErrorCount": 0,
            "writeStartedCount": 0,
            "hasData": False,
            "recentActivity": [],
            "failureReasons": [],
        }

    def admin_overview_map_snapshot(self, since, *, period="24h", time_zone="UTC"):
        self.overview_map_requests.append((since, period, time_zone))
        return {
            "eventCount": 0,
            "completedInstallCount": 0,
            "failedInstallCount": 0,
            "installSuccessRate": None,
            "hasData": False,
            "recentActivity": [],
            "attention": [],
            "trend": [],
            "bucket": "hour",
        }

    def github_downloads_snapshot(self, *, time_zone="UTC", period="24h"):
        self.overview_download_requests.append((period, time_zone))
        return {
            "hasData": True,
            "dmgTotal": 23,
            "zipTotal": 11,
            "lastObservedAt": datetime(2026, 9, 11, 20, tzinfo=UTC),
            "bucket": "hour",
            "trend": [{
                "bucket": datetime(2026, 9, 11, 20, tzinfo=UTC),
                "dmg_count": 1,
                "zip_count": 2,
            }],
        }

    def admin_session(self, token: str):
        return {"id": 7, "csrf_token_hash": token_hash("csrf")} if token == token_hash("session") else None

    def catalog_snapshot(self):
        return [], datetime(2026, 8, 31, tzinfo=UTC)

    def provider_rows(self):
        return [{
            "provider_id": "freizeitkarte",
            "provider_name": "Freizeitkarte",
            "adapter_id": "freizeitkarte",
            "status": self.status,
            "website": "https://www.freizeitkarte-osm.de/",
            "license_information": "OSM / FZK",
            "attribution": "OSM",
            "last_catalog_sync": datetime(2026, 8, 30, tzinfo=UTC),
            "health": "HEALTHY",
            "last_checked_at": datetime(2026, 8, 30, tzinfo=UTC),
            "active_package_count": 1,
            "broken_package_count": 0,
        }]

    def provider_detail(self, provider_id: str):
        if provider_id in self.detail_overrides:
            return self.detail_overrides[provider_id]
        if provider_id != "freizeitkarte":
            return None
        return {
            "provider_id": provider_id,
            "provider_name": "Freizeitkarte",
            "adapter_id": provider_id,
            "status": self.status,
            "website": "https://www.freizeitkarte-osm.de/",
            "license_information": "OSM / FZK",
            "attribution": "OSM",
            "sources": [],
            "packages": [],
            "health": None,
            "health_history": [],
        }

    def map_statistics(self, filters):
        self.map_statistic_filters.append(dict(filters))
        return [{
            "provider_id": filters.get("provider", "freizeitkarte"),
            "map_package_id": filters.get("map"),
            "region": filters.get("region", "LT"),
            "event_type": filters.get("eventType", "INSTALL_SUCCEEDED"),
            "outcome": "SUCCEEDED",
            "event_count": 1,
            "operation_count": 1,
            "first_occurred_at": datetime(2026, 8, 31, tzinfo=UTC),
            "last_occurred_at": datetime(2026, 8, 31, tzinfo=UTC),
        }]

    def map_statistics_linkage(self, filters):
        return {
            "mapOperationCount": 1,
            "mapInstallationCount": 1,
            "linkedOperationCount": 0,
            "linkedInstallationCount": 0,
            "mapOnlyInstallationCount": 1,
            "linkedWriteStartedInstallCount": 0,
            "linkedSuccessfulInstallCount": 0,
            "linkedFailedInstallCount": 0,
            "linkedPrewriteFailureCount": 0,
            "linkageRate": 0.0,
        }

    def insert_map_event(self, event):
        if event["id"] in self.events:
            return False
        self.events.add(event["id"])
        return True

    def ensure_provider_definition(self, definition):
        return None

    def provider_download_urls(self, provider_id):
        return []

    def provider_runs(self, provider_id):
        return self.run_overrides.get(provider_id, [])

    def audit_rows(self, provider_id):
        return []

    def record_provider_health(self, result):
        return 11

    def record_admin_audit(self, **kwargs):
        self.audits.append(kwargs)

    def set_provider_status(self, provider_id, status, **kwargs):
        if provider_id not in {"freizeitkarte", "opentopomap"}:
            return False
        self.status = status
        return True

    def csrf_valid(self, session, token):
        return token == "csrf"

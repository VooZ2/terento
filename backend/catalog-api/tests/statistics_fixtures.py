"""Row builders for PostgreSQL statistics regressions on the migrated schema."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

BASE_TIME = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
FENIX_8 = "garmin-fenix-8-47-amoled"


class StatisticsRows:
    """Insert raw evidence the way intake stores it, with explicit facts."""

    def __init__(self, server: Any) -> None:
        self.server = server
        self.counter = 0

    def uuid(self) -> str:
        self.counter += 1
        return f"00000000-0000-4000-8000-{self.counter:012d}"

    def at(self, minutes: float = 0) -> datetime:
        return BASE_TIME + timedelta(minutes=minutes)

    def package(self, package_id: str, *, provider: str = "freizeitkarte", region: str = "DEU",
                provider_region: str | None = None, canonical_region: str | None = None,
                country: str | None = "DE", map_type: str | None = None,
                geographic_region: str | None = None) -> str:
        self.server.query(
            """INSERT INTO map_package (id, provider_id, provider_region_id, canonical_region_id, name,
                   region, release, country, map_type, geographic_region_id)
               VALUES (%s, %s, %s, %s, %s, %s, '2026-09', %s, %s, %s)""",
            (package_id, provider, provider_region or region.lower(), canonical_region or region,
             package_id, region, country, map_type, geographic_region),
        )
        return package_id

    def diagnostic(self, **overrides: Any) -> str:
        values: dict[str, Any] = {
            "event_id": self.uuid(), "operation_id": None, "map_result_index": 0,
            "selected_map_count": 1, "occurred_at": self.at(), "model": "fēnix 8",
            "compatibility_identity": "fēnix 8 · 47 mm", "canonical_device_model_id": FENIX_8,
            "identity_resolution_state": "RESOLVED", "provider": "freizeitkarte", "region": "DEU",
            "phase_outcome": "SUCCEEDED", "automatic_finishing_result": "VERIFIED",
            "write_started": True, "app_build": "40", "release_label": "1.0.0-beta.18",
            "failure_stage": None, "failure_code": None, "diagnostic_status": "ACTIVE",
            "linked_github_issue": None, "statistics_exclusion_code": None,
            "is_local_test": False, "identity_assessment": '{"state":"RESOLVED"}',
        }
        values.update(overrides)
        if values["operation_id"] is None:
            values["operation_id"] = self.uuid()
        if values["phase_outcome"] != "SUCCEEDED" and values["automatic_finishing_result"] == "VERIFIED":
            values["automatic_finishing_result"] = "FAILED" if values["phase_outcome"] == "FAILED" else "NOT_REACHED"
        columns = list(values)
        placeholders = ", ".join(
            "%s::jsonb" if column == "identity_assessment" else "%s" for column in columns
        )
        self.server.query(
            f"""INSERT INTO compatibility_evidence_event (
                    {', '.join(columns)}, usb_vendor_id, usb_product_id, transport,
                    map_release, terento_version, macos_version)
                VALUES ({placeholders}, 2334, 20920, 'MTP', '2026-09', '1.0.0-beta.18', '15')""",
            [values[column] for column in columns],
        )
        return values["event_id"]

    def map_event(self, **overrides: Any) -> str:
        values: dict[str, Any] = {
            "event_id": self.uuid(), "operation_id": None, "provider_id": "freizeitkarte",
            "map_package_id": None, "region": "DEU", "event_type": "INSTALL_SUCCEEDED",
            "outcome": "SUCCEEDED", "occurred_at": self.at(), "app_build": "40",
            "release_label": "1.0.0-beta.18", "is_local_test": False, "acquisition_id": None,
            "component_kind": None, "map_result_index": 0, "acquisition_purpose": None,
        }
        values.update(overrides)
        if values["operation_id"] is None:
            values["operation_id"] = self.uuid()
        columns = list(values)
        self.server.query(
            f"INSERT INTO map_download_event ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
            [values[column] for column in columns],
        )
        return values["event_id"]

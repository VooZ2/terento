"""Privacy-minimised map operation event validation."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from uuid import UUID


MAX_EVENT_BYTES = 8 * 1024
ALLOWED_EVENT_KEYS = {
    "schemaVersion",
    "id",
    "operationId",
    "timestamp",
    "providerId",
    "mapId",
    "region",
    "eventType",
    "outcome",
    "appBuild",
    "releaseLabel",
}
ALLOWED_EVENT_TYPES = {
    "DOWNLOAD_STARTED",
    "DOWNLOAD_SUCCEEDED",
    "DOWNLOAD_FAILED",
    "INSTALL_SUCCEEDED",
    "INSTALL_FAILED",
}
ALLOWED_OUTCOMES = {"SUCCEEDED", "FAILED", "UNKNOWN"}
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,159}\Z")


class MapEventValidationError(ValueError):
    pass


def validate_map_event(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise MapEventValidationError("payload_size")
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MapEventValidationError("invalid_json") from exc
    if not isinstance(event, dict) or set(event) - ALLOWED_EVENT_KEYS:
        raise MapEventValidationError("unknown_fields")
    required = {
        "schemaVersion", "id", "operationId", "timestamp", "providerId",
        "eventType", "outcome",
    }
    if required - set(event):
        raise MapEventValidationError("missing_fields")
    if event["schemaVersion"] != 1:
        raise MapEventValidationError("unsupported_schema")
    for key in ("id", "operationId"):
        if not isinstance(event[key], str):
            raise MapEventValidationError(f"invalid_{key}")
        try:
            event[key] = str(UUID(event[key]))
        except (ValueError, AttributeError) as exc:
            raise MapEventValidationError(f"invalid_{key}") from exc
    for key in ("providerId", "mapId", "region"):
        value = event.get(key)
        if value is not None and (
            not isinstance(value, str) or not SAFE_ID.fullmatch(value.lower())
        ):
            raise MapEventValidationError(f"invalid_{key}")
    for key in ("appBuild", "releaseLabel"):
        value = event.get(key)
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > 80
        ):
            raise MapEventValidationError(f"invalid_{key}")
        if isinstance(value, str):
            event[key] = value.strip()
    if not isinstance(event["eventType"], str) or event["eventType"] not in ALLOWED_EVENT_TYPES:
        raise MapEventValidationError("invalid_event_type")
    if not isinstance(event["outcome"], str) or event["outcome"] not in ALLOWED_OUTCOMES:
        raise MapEventValidationError("invalid_outcome")
    if not isinstance(event["timestamp"], str):
        raise MapEventValidationError("invalid_timestamp")
    try:
        timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise MapEventValidationError("invalid_timestamp") from exc
    if timestamp.tzinfo is None:
        raise MapEventValidationError("timestamp_requires_timezone")
    event = dict(event)
    event["providerId"] = event["providerId"].lower()
    if event["providerId"] == "custom":
        raise MapEventValidationError("unsupported_provider")
    if event.get("mapId") is not None:
        event["mapId"] = event["mapId"].lower()
    if event.get("region") is not None:
        event["region"] = event["region"].upper()
    event["timestamp"] = timestamp
    return event


def validate_statistics_filters(filters: dict[str, str]) -> dict[str, Any]:
    allowed = {"provider", "map", "region", "dateFrom", "dateTo", "eventType"}
    if set(filters) - allowed:
        raise MapEventValidationError("unknown_filter")
    result: dict[str, Any] = {}
    for key in ("provider", "map", "region"):
        value = filters.get(key)
        if value:
            if not SAFE_ID.fullmatch(value.lower()):
                raise MapEventValidationError(f"invalid_{key}_filter")
            result[key] = value.upper() if key == "region" else value.lower()
    if filters.get("eventType"):
        event_type = filters["eventType"].upper()
        if event_type not in ALLOWED_EVENT_TYPES:
            raise MapEventValidationError("invalid_event_type_filter")
        result["eventType"] = event_type
    for key in ("dateFrom", "dateTo"):
        value = filters.get(key)
        if value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise MapEventValidationError(f"invalid_{key}_filter") from exc
            if parsed.tzinfo is None:
                raise MapEventValidationError(f"invalid_{key}_filter")
            result[key] = parsed
    if result.get("dateFrom") and result.get("dateTo"):
        if result["dateFrom"] > result["dateTo"]:
            raise MapEventValidationError("invalid_date_range")
    return result

"""Privacy-minimised app first-run funnel events (contracts/APP_FUNNEL_CONTRACT.md).

A funnel event records that one app session reached a pre-install stage with
an outcome. It carries no serial, Unit ID, account, path, IP or persistent
user/device identifier; ``sessionId`` is random per app launch and never
persisted by the app.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .telemetry import is_local_release_label, validate_release_label

MAX_FUNNEL_EVENT_BYTES = 4 * 1024
FUNNEL_SCHEMA_VERSION = 1
ALLOWED_FUNNEL_KEYS = frozenset({
    "schemaVersion", "id", "sessionId", "occurredAt", "appBuild", "releaseLabel",
    "stage", "outcome", "baseModel", "droppedPackageCount",
})
REQUIRED_FUNNEL_KEYS = frozenset({
    "schemaVersion", "id", "sessionId", "occurredAt", "appBuild", "releaseLabel", "stage", "outcome",
})
FUNNEL_OUTCOMES: dict[str, frozenset[str]] = {
    "DEVICE_CONNECT": frozenset({
        "CONNECTED", "TIMEOUT_NO_USB", "TIMEOUT_USB_PRESENT", "BUSY", "MULTIPLE_DEVICES",
        "NOT_MTP_MODE", "DISCONNECTED", "FAILED",
    }),
    "AUTHORIZATION": frozenset({
        "APPROVED", "PENDING", "OUT_OF_SCOPE", "UNKNOWN_MODEL", "AMBIGUOUS",
        "CATALOG_UNAVAILABLE", "UPDATE_REQUIRED",
    }),
    "CATALOG": frozenset({"REMOTE", "REMOTE_PARTIAL", "BUNDLED_FALLBACK", "UPDATE_REQUIRED"}),
    "INSTALL_BLOCKED": frozenset({
        "AUTHORIZATION", "DEVICE_STORAGE", "MAC_STORAGE", "CATALOG_UNVERIFIED", "LOCAL_CAPABILITY", "OTHER",
    }),
}
_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_POSTGRES_INTEGER_MAX = 2_147_483_647


class FunnelValidationError(ValueError):
    pass


def _uuid(value: Any, code: str) -> str:
    if not isinstance(value, str) or not _UUID_TEXT.fullmatch(value):
        raise FunnelValidationError(code)
    return str(UUID(value))


def validate_funnel_event(raw: bytes) -> dict[str, Any]:
    """Return a normalized funnel event or raise ``FunnelValidationError`` (HTTP 400)."""
    if not raw or len(raw) > MAX_FUNNEL_EVENT_BYTES:
        raise FunnelValidationError("payload_size")
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FunnelValidationError("invalid_json") from exc
    if not isinstance(event, dict):
        raise FunnelValidationError("invalid_json")
    if set(event) - ALLOWED_FUNNEL_KEYS:
        raise FunnelValidationError("unknown_fields")
    # Optional fields encoded as null are treated as omitted.
    event = {key: value for key, value in event.items() if value is not None or key in REQUIRED_FUNNEL_KEYS}
    if REQUIRED_FUNNEL_KEYS - set(event):
        raise FunnelValidationError("missing_fields")
    if type(event["schemaVersion"]) is not int or event["schemaVersion"] != FUNNEL_SCHEMA_VERSION:
        raise FunnelValidationError("unsupported_schema")
    normalized: dict[str, Any] = {
        "id": _uuid(event["id"], "invalid_id"),
        "sessionId": _uuid(event["sessionId"], "invalid_sessionId"),
    }
    occurred_at = event["occurredAt"]
    if not isinstance(occurred_at, str):
        raise FunnelValidationError("invalid_occurredAt")
    try:
        timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FunnelValidationError("invalid_occurredAt") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(None):
        raise FunnelValidationError("invalid_occurredAt")
    normalized["occurredAt"] = timestamp.astimezone(timezone.utc)
    app_build = event["appBuild"]
    if not isinstance(app_build, str) or not app_build.strip() or len(app_build) > 80 or _unsafe_text(app_build):
        raise FunnelValidationError("invalid_appBuild")
    normalized["appBuild"] = app_build
    try:
        normalized["releaseLabel"] = validate_release_label(event["releaseLabel"])
    except ValueError as exc:
        raise FunnelValidationError("invalid_releaseLabel") from exc
    normalized["isLocalTest"] = is_local_release_label(normalized["releaseLabel"])
    stage, outcome = event["stage"], event["outcome"]
    if not isinstance(stage, str) or stage not in FUNNEL_OUTCOMES:
        raise FunnelValidationError("invalid_stage")
    if not isinstance(outcome, str) or outcome not in FUNNEL_OUTCOMES[stage]:
        raise FunnelValidationError("invalid_outcome")
    normalized["stage"], normalized["outcome"] = stage, outcome
    base_model = event.get("baseModel")
    if base_model is not None:
        if not (stage == "AUTHORIZATION" or (stage == "DEVICE_CONNECT" and outcome == "CONNECTED")):
            raise FunnelValidationError("unexpected_baseModel")
        if (
            not isinstance(base_model, str) or not base_model.strip() or len(base_model) > 80
            or base_model != base_model.strip() or _unsafe_text(base_model)
        ):
            raise FunnelValidationError("invalid_baseModel")
    normalized["baseModel"] = base_model
    dropped = event.get("droppedPackageCount")
    if dropped is not None:
        if not (stage == "CATALOG" and outcome == "REMOTE_PARTIAL"):
            raise FunnelValidationError("unexpected_droppedPackageCount")
        if type(dropped) is not int or not 0 <= dropped <= _POSTGRES_INTEGER_MAX:
            raise FunnelValidationError("invalid_droppedPackageCount")
    normalized["droppedPackageCount"] = dropped
    return normalized


def _unsafe_text(value: str) -> bool:
    return (
        "/Users/" in value or "file://" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    )

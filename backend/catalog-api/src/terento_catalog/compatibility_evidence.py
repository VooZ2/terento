from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MAX_EVENT_BYTES = 16_384
ALLOWED_KEYS = {
    "schemaVersion", "id", "timestamp", "model", "compatibilityIdentity", "variant", "caseSizeMm", "displayType", "canonicalDeviceId", "family", "firmwareVersion",
    "usbVendorID", "usbProductID", "transport", "provider", "region",
    "mapRelease", "terentoVersion", "macOSVersion", "phaseOutcome",
    "automaticFinishingResult", "reconnectVerified", "mapVisibleAfterReconnect",
    "errorCategory", "userConfirmed", "deletionToken",
}
FORBIDDEN_KEY_PARTS = ("serial", "unitid", "unit_id", "path", "manifest", "username", "token", "password")


class EvidenceValidationError(ValueError):
    pass


def validate_event(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise EvidenceValidationError("payload_size")
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError("invalid_json") from exc
    if not isinstance(event, dict) or set(event) - ALLOWED_KEYS:
        raise EvidenceValidationError("unknown_fields")
    if any(
        part in key.lower()
        for key in event
        if key != "deletionToken"
        for part in FORBIDDEN_KEY_PARTS
    ):
        raise EvidenceValidationError("forbidden_field")
    required = {
        "schemaVersion", "id", "timestamp", "model", "usbVendorID", "usbProductID",
        "transport", "provider", "region", "mapRelease", "terentoVersion",
        "macOSVersion", "phaseOutcome", "automaticFinishingResult", "deletionToken",
    }
    if required - set(event):
        raise EvidenceValidationError("missing_fields")
    if event["schemaVersion"] not in {1, 2}:
        raise EvidenceValidationError("unsupported_schema")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(event["id"])):
        raise EvidenceValidationError("invalid_event_id")
    for key in ("model", "transport", "provider", "region", "mapRelease", "terentoVersion", "macOSVersion"):
        if not isinstance(event[key], str) or not event[key].strip() or len(event[key]) > 160:
            raise EvidenceValidationError(f"invalid_{key}")
        if "/Users/" in event[key] or "file://" in event[key]:
            raise EvidenceValidationError("local_path")
    if event["phaseOutcome"] not in {"SUCCEEDED", "FAILED"}:
        raise EvidenceValidationError("invalid_outcome")
    if event["automaticFinishingResult"] not in {"VERIFIED", "FAILED", "NOT_REACHED"}:
        raise EvidenceValidationError("invalid_finishing_result")
    if event["phaseOutcome"] == "SUCCEEDED" and event["automaticFinishingResult"] != "VERIFIED":
        raise EvidenceValidationError("inconsistent_success")
    if event["phaseOutcome"] == "FAILED" and event["automaticFinishingResult"] == "VERIFIED":
        raise EvidenceValidationError("inconsistent_failure")
    if event.get("errorCategory") not in {
        None, "acquisition", "transport", "verification", "storage",
        "deviceDisconnected", "sourceValidation", "unknown",
    }:
        raise EvidenceValidationError("invalid_error_category")
    for key in ("usbVendorID", "usbProductID"):
        if not isinstance(event[key], int) or isinstance(event[key], bool) or not 0 <= event[key] <= 65535:
            raise EvidenceValidationError(f"invalid_{key}")
    try:
        datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceValidationError("invalid_timestamp") from exc
    for key in ("compatibilityIdentity", "variant", "displayType", "family", "firmwareVersion"):
        value = event.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 160 or "/Users/" in value or "file://" in value):
            raise EvidenceValidationError(f"invalid_{key}")
    compatibility_identity = str(event.get("compatibilityIdentity") or event["model"]).strip()
    if not compatibility_identity:
        raise EvidenceValidationError("invalid_compatibilityIdentity")
    if event.get("caseSizeMm") is not None and (
        not isinstance(event["caseSizeMm"], int)
        or isinstance(event["caseSizeMm"], bool)
        or not 1 <= event["caseSizeMm"] <= 999
    ):
        raise EvidenceValidationError("invalid_caseSizeMm")
    canonical_device_id = event.get("canonicalDeviceId")
    if canonical_device_id is not None and (
        not isinstance(canonical_device_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,159}", canonical_device_id) is None
    ):
        raise EvidenceValidationError("invalid_canonicalDeviceId")
    for key in ("reconnectVerified", "mapVisibleAfterReconnect"):
        if key in event and not isinstance(event[key], bool):
            raise EvidenceValidationError(f"invalid_{key}")
    if event.get("reconnectVerified") and (
        event["phaseOutcome"] != "SUCCEEDED"
        or event["automaticFinishingResult"] != "VERIFIED"
    ):
        raise EvidenceValidationError("inconsistent_reconnect_evidence")
    if event.get("mapVisibleAfterReconnect") and not event.get("reconnectVerified"):
        raise EvidenceValidationError("inconsistent_reconnect_evidence")
    if event["provider"].lower() != "freizeitkarte":
        raise EvidenceValidationError("unsupported_provider")
    if "userConfirmed" in event and not isinstance(event["userConfirmed"], bool):
        raise EvidenceValidationError("invalid_confirmation")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(event["deletionToken"])):
        raise EvidenceValidationError("invalid_deletion_token")
    return event


def validate_deletion_request(raw: bytes) -> tuple[str, str]:
    if not raw or len(raw) > 2048:
        raise EvidenceValidationError("payload_size")
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError("invalid_json") from exc
    if not isinstance(request, dict) or set(request) != {"id", "deletionToken"}:
        raise EvidenceValidationError("invalid_deletion_request")
    event_id = str(request["id"])
    deletion_token = str(request["deletionToken"])
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", event_id):
        raise EvidenceValidationError("invalid_event_id")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", deletion_token):
        raise EvidenceValidationError("invalid_deletion_token")
    return event_id, deletion_token


def operator_page(rows: list[dict[str, Any]]) -> bytes:
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(key) if row.get(key) is not None else '—'))}</td>" for key in (
            "model", "firmware_versions", "attempted_install_count", "successful_install_count",
            "failed_install_count", "success_rate", "last_success", "last_failure",
            "error_categories", "calculated_status", "physical_device_evidence_count", "review_notes",
        )) + "</tr>"
        for row in rows
    )
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=robots content=\"noindex,nofollow\">
<title>Terento compatibility evidence</title><style>body{{font:14px system-ui;margin:2rem}}table{{border-collapse:collapse}}th,td{{border:1px solid #ccc;padding:.5rem;text-align:left}}</style></head>
<body><h1>Compatibility evidence</h1><table><thead><tr>{''.join(f'<th>{x}</th>' for x in ('Model','Firmware','Attempts','Successes','Failures','Rate','Last success','Last failure','Errors','Calculated','Physical devices','Review notes'))}</tr></thead><tbody>{body}</tbody></table></body></html>""".encode()

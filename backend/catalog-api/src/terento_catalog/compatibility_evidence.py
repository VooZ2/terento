from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MAX_EVENT_BYTES = 16_384
# `custom` is a local IMG source, not a map provider. It is accepted here so
# shared custom installs can contribute device compatibility evidence while
# the client sends only the coarse custom/custom/custom labels.
SUPPORTED_COMPATIBILITY_SOURCES = frozenset({"freizeitkarte", "opentopomap", "custom"})
ALLOWED_KEYS = {
    "schemaVersion", "id", "timestamp", "model", "compatibilityIdentity", "variant", "caseSizeMm", "displayType", "canonicalDeviceId", "family", "firmwareVersion",
    "usbVendorID", "usbProductID", "transport", "provider", "region",
    "mapRelease", "terentoVersion", "macOSVersion", "phaseOutcome",
    "automaticFinishingResult", "reconnectVerified", "mapVisibleAfterReconnect",
    "errorCategory", "userConfirmed", "deletionToken",
    "operationId", "mapResultIndex", "selectedMapCount", "appBuild", "releaseLabel",
    "failureStage", "failureCode", "nativeFailureCode", "writeStarted",
    "remoteObjectCreated", "cleanupAttempted", "cleanupSucceeded",
    "transferProgressBucket", "rawMTPModel", "identityResolutionCode",
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
    schema_version = event.get("schemaVersion")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise EvidenceValidationError("unsupported_schema")
    if schema_version not in {1, 2, 3, 4}:
        raise EvidenceValidationError("unsupported_schema")
    required = {
        "schemaVersion", "id", "timestamp", "model", "usbVendorID", "usbProductID",
        "transport", "provider", "region", "mapRelease", "terentoVersion",
        "macOSVersion", "phaseOutcome", "automaticFinishingResult",
    }
    if schema_version in {1, 2, 3}:
        required.add("deletionToken")
    if required - set(event):
        raise EvidenceValidationError("missing_fields")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(event["id"])):
        raise EvidenceValidationError("invalid_event_id")
    for key in ("model", "transport", "provider", "region", "mapRelease", "terentoVersion", "macOSVersion"):
        if not isinstance(event[key], str) or not event[key].strip() or len(event[key]) > 160:
            raise EvidenceValidationError(f"invalid_{key}")
        if "/Users/" in event[key] or "file://" in event[key]:
            raise EvidenceValidationError("local_path")
    allowed_outcomes = {"SUCCEEDED", "FAILED", "NOT_STARTED"} if schema_version in {3, 4} else {"SUCCEEDED", "FAILED"}
    if event["phaseOutcome"] not in allowed_outcomes:
        raise EvidenceValidationError("invalid_outcome")
    if event["automaticFinishingResult"] not in {"VERIFIED", "FAILED", "NOT_REACHED"}:
        raise EvidenceValidationError("invalid_finishing_result")
    if event["phaseOutcome"] == "SUCCEEDED" and event["automaticFinishingResult"] != "VERIFIED":
        raise EvidenceValidationError("inconsistent_success")
    if event["phaseOutcome"] == "FAILED" and event["automaticFinishingResult"] == "VERIFIED":
        raise EvidenceValidationError("inconsistent_failure")
    if event["phaseOutcome"] == "NOT_STARTED" and event["automaticFinishingResult"] != "NOT_REACHED":
        raise EvidenceValidationError("inconsistent_not_started")
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
    raw_mtp_model = event.get("rawMTPModel")
    if raw_mtp_model is not None and (
        not isinstance(raw_mtp_model, str)
        or not raw_mtp_model.strip()
        or len(raw_mtp_model) > 160
        or "/Users/" in raw_mtp_model
        or "file://" in raw_mtp_model
        or any(ord(character) < 32 for character in raw_mtp_model)
    ):
        raise EvidenceValidationError("invalid_rawMTPModel")
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
    provider = event["provider"].lower()
    if provider not in SUPPORTED_COMPATIBILITY_SOURCES:
        raise EvidenceValidationError("unsupported_provider")
    if provider == "custom" and (
        event["region"] != "custom" or event["mapRelease"] != "custom"
    ):
        raise EvidenceValidationError("invalid_custom_identity")
    event["provider"] = provider
    if "userConfirmed" in event and not isinstance(event["userConfirmed"], bool):
        raise EvidenceValidationError("invalid_confirmation")
    if schema_version in {1, 2, 3}:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(event["deletionToken"])):
            raise EvidenceValidationError("invalid_deletion_token")
    elif "deletionToken" in event:
        raise EvidenceValidationError("deletion_not_supported")
    if schema_version in {3, 4}:
        _validate_v3(event)
    return event


def _validate_v3(event: dict[str, Any]) -> None:
    required = {
        "operationId", "mapResultIndex", "selectedMapCount", "appBuild", "releaseLabel",
        "writeStarted", "remoteObjectCreated", "cleanupAttempted", "cleanupSucceeded",
        "transferProgressBucket",
    }
    if required - set(event):
        raise EvidenceValidationError("missing_diagnostic_fields")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(event["operationId"])):
        raise EvidenceValidationError("invalid_operation_id")
    if not isinstance(event["mapResultIndex"], int) or isinstance(event["mapResultIndex"], bool):
        raise EvidenceValidationError("invalid_map_result_index")
    if not isinstance(event["selectedMapCount"], int) or isinstance(event["selectedMapCount"], bool):
        raise EvidenceValidationError("invalid_selected_map_count")
    if not 0 <= event["mapResultIndex"] < event["selectedMapCount"] <= 100:
        raise EvidenceValidationError("invalid_map_result_position")
    for key in ("appBuild", "releaseLabel"):
        if (
            not isinstance(event[key], str)
            or not event[key].strip()
            or len(event[key]) > 80
            or "/Users/" in event[key]
            or "file://" in event[key]
        ):
            raise EvidenceValidationError(f"invalid_{key}")
    for key in ("writeStarted", "remoteObjectCreated", "cleanupAttempted", "cleanupSucceeded"):
        if not isinstance(event[key], bool):
            raise EvidenceValidationError(f"invalid_{key}")
    if event["transferProgressBucket"] not in {"0", "1-24", "25-99", "100"}:
        raise EvidenceValidationError("invalid_transfer_progress_bucket")
    stages = {"download", "extract", "source-validation", "preflight", "write", "verify", "cleanup", "manifest"}
    if event.get("failureStage") not in stages | {None}:
        raise EvidenceValidationError("invalid_failure_stage")
    failure_codes = {
        "INSTALL_BLOCKED_EXISTING_MAP_CONFLICT", "INSTALL_BLOCKED_SOURCE_ARTIFACT_INVALID",
        "INSTALL_BLOCKED_INSUFFICIENT_SPACE", "INSTALL_BLOCKED_UNKNOWN_INSTALL_SIZE",
        "INSTALL_BLOCKED_UNKNOWN_TARGET", "INSTALL_BLOCKED_MAP_IDENTITY_AMBIGUOUS",
        "INSTALL_BLOCKED_BACKUP_FAILED", "INSTALL_BLOCKED_DOWNLOAD_FAILED",
        "INSTALL_BLOCKED_SOURCE_VALIDATION_FAILED", "INSTALL_FAILED_DEVICE_DISCONNECTED",
        "INSTALL_FAILED_WRITE", "INSTALL_FAILED_SIZE_MISMATCH", "INSTALL_FAILED_HASH_MISMATCH",
        "INSTALL_FAILED_REMOTE_FILE_MISSING", "INSTALL_FAILED_METADATA_MISMATCH",
        "INSTALL_FAILED_MANIFEST", "INSTALL_FAILED_PROTECTION_VIOLATION",
        "INSTALL_FAILED_CLEANUP", "INSTALL_BLOCKED_TRANSACTION_ALREADY_RUNNING",
        "INSTALL_FAILED_INVALID_STATE_TRANSITION", "INSTALL_BLOCKED_VERIFICATION_REQUIRED",
        "INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE",
        "INSTALL_BLOCKED_STABLE_WATCH_IDENTITY_UNAVAILABLE",
    }
    if event.get("failureCode") not in failure_codes | {None}:
        raise EvidenceValidationError("invalid_failure_code")
    native_codes = {
        "TARGET_ALREADY_EXISTS", "REMOTE_FILE_MISSING", "OBJECT_ID_MISMATCH",
        "UNSUPPORTED_DEVICE", "DEVICE_DISCONNECTED", "SEND_OBJECT_FAILED",
        "READBACK_FAILED", "DELETE_FAILED", "MTP_OPEN_FAILED", "GARMIN_ROOT_COUNT_INVALID",
        "PREFLIGHT_MTP_READ_FAILED", "LIVE_IDENTITY_MISMATCH",
        "STABLE_WATCH_IDENTITY_UNAVAILABLE", "GARMIN_DEVICE_XML_INVALID",
    }
    if event.get("nativeFailureCode") not in native_codes | {None}:
        raise EvidenceValidationError("invalid_native_failure_code")
    if event.get("identityResolutionCode") not in {
        None, "MTP_SERIAL", "GARMIN_UNIT_ID", "UNAVAILABLE"
    }:
        raise EvidenceValidationError("invalid_identity_resolution_code")
    if event["phaseOutcome"] == "SUCCEEDED" and any(event.get(key) is not None for key in ("failureStage", "failureCode", "nativeFailureCode")):
        raise EvidenceValidationError("inconsistent_success_diagnostics")
    if event["phaseOutcome"] in {"FAILED", "NOT_STARTED"} and (
        event.get("failureStage") is None or event.get("failureCode") is None
    ):
        raise EvidenceValidationError("missing_failure_diagnostics")
    if event["phaseOutcome"] == "NOT_STARTED" and event["writeStarted"]:
        raise EvidenceValidationError("inconsistent_not_started")
    if event["remoteObjectCreated"] and not event["writeStarted"]:
        raise EvidenceValidationError("inconsistent_remote_object")
    if event["cleanupSucceeded"] and not event["cleanupAttempted"]:
        raise EvidenceValidationError("inconsistent_cleanup")

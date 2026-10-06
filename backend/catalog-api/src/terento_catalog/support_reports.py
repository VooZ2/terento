"""User-sent support reports (contracts/SUPPORT_REPORT_CONTRACT.md).

A support report is the already-sanitised local issue report that a user
explicitly chose to send to Terento, plus an optional description. It is a
closed, strictly typed structure: no serial, Unit ID, account, local path, raw
log or file content is accepted, and the client IP is never stored. Support
reports are never statistics.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .failure_context import validate_context
from .telemetry import is_local_release_label, validate_release_label

MAX_SUPPORT_REPORT_BYTES = 64 * 1024
SUPPORT_REPORT_SCHEMA_VERSION = 1
MAX_USER_MESSAGE_LENGTH = 2000
MAX_ADMIN_NOTE_LENGTH = 2000
SUPPORT_REPORT_CATEGORIES = ("INSTALL_FAILED", "UPDATE_FAILED", "REMOVE_FAILED", "CONNECTION", "OTHER")
SUPPORT_REPORT_STATUSES = ("OPEN", "HANDLED")
ALLOWED_SUPPORT_REPORT_KEYS = frozenset({
    "schemaVersion", "id", "createdAt", "appBuild", "releaseLabel", "category",
    "operationId", "userMessage", "report",
})
REQUIRED_SUPPORT_REPORT_KEYS = frozenset({
    "schemaVersion", "id", "createdAt", "appBuild", "releaseLabel", "category", "report",
})

# ``report`` mirrors the sections of the app's sanitised GitHub issue report
# (app/TerentoCore/Sources/TerentoPoC/Diagnostics/InstallationIssueReport.swift).
REPORT_OPERATIONS = ("INSTALLATION", "UPDATE", "REMOVAL")
REPORT_TEXT_LIMITS = {
    "title": 180, "stage": 120, "errorCategory": 80, "message": 500, "macOSVersion": 120,
}
REPORT_BOOLEAN_KEYS = ("writeStarted", "objectCreated", "cleanupAttempted", "cleanupSucceeded")
ALLOWED_REPORT_KEYS = frozenset({
    *REPORT_TEXT_LIMITS, *REPORT_BOOLEAN_KEYS,
    "operation", "failureStages", "errorCodes", "device", "maps", "transferProgressPercent",
    "verification", "lifecycleFacts", "failureContext", "originalFailureContext", "finishingTrace",
})
REQUIRED_REPORT_KEYS = frozenset({"macOSVersion"})
DEVICE_TEXT_LIMITS = {"model": 120, "variant": 120, "family": 120, "firmware": 40, "mtpModel": 120}
MAP_TEXT_LIMITS = {"provider": 80, "region": 200, "package": 200, "release": 80}
VERIFICATION_CODE_KEYS = ("originalFailure", "cleanupFailure", "transportClassification", "failedComponent")
VERIFICATION_BYTE_KEYS = ("sourceBytes", "remoteBytes", "transferredBytes", "elapsedMilliseconds", "sampledBytes")
VERIFICATION_COUNT_KEYS = ("sampleCount", "matchedSampleCount")
MAX_FAILURE_STAGES = 8
MAX_ERROR_CODES = 8
MAX_MAPS = 8
MAX_LIFECYCLE_FACTS = 16
MAX_LIFECYCLE_FACT_LENGTH = 500
MAX_TRACE_LINES = 64
MAX_TRACE_LINE_LENGTH = 300
JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991
POSTGRES_INTEGER_MAX = 2_147_483_647

_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}")
# Fixed-field finishing diagnostics only: ``key=value`` tokens with closed
# character sets. A slash, quote or space inside a value is rejected, so a path
# or free-form native error cannot travel in this field.
_TRACE_TOKEN = r"(?: [a-z][a-z0-9_]{0,39}=[A-Za-z0-9_.-]{0,80})*"
TRACE_LINE_PATTERN = re.compile(
    r"FINISH_TRACE (?:swift|native)" + _TRACE_TOKEN + r"(?: event=[A-Za-z0-9_.-]{1,80})" + _TRACE_TOKEN
)
REFERENCE_PATTERN = re.compile(r"TR-[A-Z2-7]{6}")
# Defence in depth behind the app's DiagnosticReportSanitizer.
_LOCAL_PATH_MARKERS = ("/users/", "file://", "/private/", "/volumes/", "\\users\\")


class SupportReportValidationError(ValueError):
    pass


def support_reference(report_id: str) -> str:
    """``TR-`` + the first 6 RFC 4648 base32 characters of SHA-256(lowercase UUID)."""
    canonical = str(UUID(str(report_id))).lower()
    digest = hashlib.sha256(canonical.encode("ascii")).digest()
    return "TR-" + base64.b32encode(digest).decode("ascii")[:6]


def normalise_reference(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if REFERENCE_PATTERN.fullmatch(text) else None


def _has_local_path(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _LOCAL_PATH_MARKERS)


def _has_control(value: str, *, allow_newlines: bool = False) -> bool:
    allowed = {"\n", "\t"} if allow_newlines else set()
    return any((ord(c) < 32 and c not in allowed) or ord(c) == 127 for c in value)


def _text(value: Any, limit: int, code: str) -> str:
    if (
        not isinstance(value, str) or not value.strip() or value != value.strip()
        or len(value) > limit or _has_control(value) or _has_local_path(value)
    ):
        raise SupportReportValidationError(code)
    return value


def _integer(value: Any, maximum: int, code: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SupportReportValidationError(code)
    return value


def _object(value: Any, allowed: set[str] | frozenset[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SupportReportValidationError(code)
    if set(value) - set(allowed):
        raise SupportReportValidationError(code)
    # Optional values encoded as null are treated as omitted.
    return {key: item for key, item in value.items() if item is not None}


def _uuid(value: Any, code: str) -> str:
    if not isinstance(value, str) or not _UUID_TEXT.fullmatch(value):
        raise SupportReportValidationError(code)
    return str(UUID(value))


def _list(value: Any, maximum: int, code: str) -> list[Any]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise SupportReportValidationError(code)
    return value


def validate_report_body(report: Any) -> dict[str, Any]:
    """Return the normalized structured ``report`` object."""
    if not isinstance(report, dict):
        raise SupportReportValidationError("invalid_report")
    if set(report) - ALLOWED_REPORT_KEYS:
        raise SupportReportValidationError("unknown_report_fields")
    report = {key: value for key, value in report.items() if value is not None}
    if REQUIRED_REPORT_KEYS - set(report):
        raise SupportReportValidationError("missing_report_fields")
    normalized: dict[str, Any] = {}
    for key, limit in REPORT_TEXT_LIMITS.items():
        if key in report:
            normalized[key] = _text(report[key], limit, f"invalid_report_{key}")
    if "operation" in report:
        if report["operation"] not in REPORT_OPERATIONS:
            raise SupportReportValidationError("invalid_report_operation")
        normalized["operation"] = report["operation"]
    if "failureStages" in report:
        normalized["failureStages"] = [
            _text(item, 120, "invalid_report_failureStages")
            for item in _list(report["failureStages"], MAX_FAILURE_STAGES, "invalid_report_failureStages")
        ]
    if "errorCodes" in report:
        codes = _list(report["errorCodes"], MAX_ERROR_CODES, "invalid_report_errorCodes")
        if not all(isinstance(code, str) and CODE_PATTERN.fullmatch(code) for code in codes):
            raise SupportReportValidationError("invalid_report_errorCodes")
        normalized["errorCodes"] = list(codes)
    for key in REPORT_BOOLEAN_KEYS:
        if key in report:
            if type(report[key]) is not bool:
                raise SupportReportValidationError(f"invalid_report_{key}")
            normalized[key] = report[key]
    if "transferProgressPercent" in report:
        normalized["transferProgressPercent"] = _integer(
            report["transferProgressPercent"], 100, "invalid_report_transferProgressPercent",
        )
    if "device" in report:
        device = _object(report["device"], set(DEVICE_TEXT_LIMITS), "invalid_report_device")
        if not device:
            raise SupportReportValidationError("invalid_report_device")
        normalized["device"] = {
            key: _text(device[key], limit, "invalid_report_device")
            for key, limit in DEVICE_TEXT_LIMITS.items() if key in device
        }
    if "maps" in report:
        maps = []
        for item in _list(report["maps"], MAX_MAPS, "invalid_report_maps"):
            entry = _object(item, set(MAP_TEXT_LIMITS) | {"plannedBytes"}, "invalid_report_maps")
            if "provider" not in entry:
                raise SupportReportValidationError("invalid_report_maps")
            value = {
                key: _text(entry[key], limit, "invalid_report_maps")
                for key, limit in MAP_TEXT_LIMITS.items() if key in entry
            }
            if "plannedBytes" in entry:
                value["plannedBytes"] = _integer(entry["plannedBytes"], JSON_SAFE_INTEGER_MAX, "invalid_report_maps")
            maps.append(value)
        normalized["maps"] = maps
    if "verification" in report:
        allowed = {*VERIFICATION_CODE_KEYS, *VERIFICATION_BYTE_KEYS, *VERIFICATION_COUNT_KEYS}
        verification = _object(report["verification"], allowed, "invalid_report_verification")
        value: dict[str, Any] = {}
        for key in VERIFICATION_CODE_KEYS:
            if key in verification:
                if not isinstance(verification[key], str) or not CODE_PATTERN.fullmatch(verification[key]):
                    raise SupportReportValidationError("invalid_report_verification")
                value[key] = verification[key]
        for key in VERIFICATION_BYTE_KEYS:
            if key in verification:
                value[key] = _integer(verification[key], JSON_SAFE_INTEGER_MAX, "invalid_report_verification")
        for key in VERIFICATION_COUNT_KEYS:
            if key in verification:
                value[key] = _integer(verification[key], POSTGRES_INTEGER_MAX, "invalid_report_verification")
        if value:
            normalized["verification"] = value
    if "lifecycleFacts" in report:
        normalized["lifecycleFacts"] = [
            _text(item, MAX_LIFECYCLE_FACT_LENGTH, "invalid_report_lifecycleFacts")
            for item in _list(report["lifecycleFacts"], MAX_LIFECYCLE_FACTS, "invalid_report_lifecycleFacts")
        ]
    for key in ("failureContext", "originalFailureContext"):
        if key in report:
            try:
                validate_context(report[key])
            except ValueError as exc:
                raise SupportReportValidationError(f"invalid_report_{key}") from exc
            normalized[key] = report[key]
    if "finishingTrace" in report:
        lines = _list(report["finishingTrace"], MAX_TRACE_LINES, "invalid_report_finishingTrace")
        if not all(
            isinstance(line, str) and len(line) <= MAX_TRACE_LINE_LENGTH
            and TRACE_LINE_PATTERN.fullmatch(line)
            for line in lines
        ):
            raise SupportReportValidationError("invalid_report_finishingTrace")
        normalized["finishingTrace"] = list(lines)
    return normalized


def validate_support_report(raw: bytes) -> dict[str, Any]:
    """Return a normalized support report or raise ``SupportReportValidationError`` (HTTP 400)."""
    if not raw or len(raw) > MAX_SUPPORT_REPORT_BYTES:
        raise SupportReportValidationError("payload_size")
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupportReportValidationError("invalid_json") from exc
    if not isinstance(body, dict):
        raise SupportReportValidationError("invalid_json")
    if set(body) - ALLOWED_SUPPORT_REPORT_KEYS:
        raise SupportReportValidationError("unknown_fields")
    body = {key: value for key, value in body.items() if value is not None or key in REQUIRED_SUPPORT_REPORT_KEYS}
    if REQUIRED_SUPPORT_REPORT_KEYS - set(body):
        raise SupportReportValidationError("missing_fields")
    if type(body["schemaVersion"]) is not int or body["schemaVersion"] != SUPPORT_REPORT_SCHEMA_VERSION:
        raise SupportReportValidationError("unsupported_schema")
    normalized: dict[str, Any] = {"id": _uuid(body["id"], "invalid_id")}
    normalized["reference"] = support_reference(normalized["id"])
    created_at = body["createdAt"]
    if not isinstance(created_at, str):
        raise SupportReportValidationError("invalid_createdAt")
    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupportReportValidationError("invalid_createdAt") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(None):
        raise SupportReportValidationError("invalid_createdAt")
    normalized["createdAt"] = timestamp.astimezone(timezone.utc)
    normalized["appBuild"] = _text(body["appBuild"], 80, "invalid_appBuild")
    try:
        normalized["releaseLabel"] = validate_release_label(body["releaseLabel"])
    except ValueError as exc:
        raise SupportReportValidationError("invalid_releaseLabel") from exc
    normalized["isLocalTest"] = is_local_release_label(normalized["releaseLabel"])
    if body["category"] not in SUPPORT_REPORT_CATEGORIES:
        raise SupportReportValidationError("invalid_category")
    normalized["category"] = body["category"]
    normalized["operationId"] = (
        _uuid(body["operationId"], "invalid_operationId") if "operationId" in body else None
    )
    message = body.get("userMessage")
    if message is not None:
        if (
            not isinstance(message, str) or not message.strip() or len(message) > MAX_USER_MESSAGE_LENGTH
            or _has_control(message, allow_newlines=True) or _has_local_path(message)
        ):
            raise SupportReportValidationError("invalid_userMessage")
    normalized["userMessage"] = message
    normalized["report"] = validate_report_body(body["report"])
    return normalized


def normalise_admin_note(value: Any) -> str | None:
    note = str(value or "").strip()
    if not note:
        return None
    if len(note) > MAX_ADMIN_NOTE_LENGTH or _has_control(note, allow_newlines=True):
        raise ValueError("invalid_support_report_note")
    return note

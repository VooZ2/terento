"""Web installer statistics (contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).

Page events and relay jobs arrive from the web installer server only (bearer
secret), are checked against a closed allowlist and summarized for the Admin
Web installer page. A separate population: nothing here feeds app statistics.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

MAX_WEB_INSTALLER_BYTES = 4 * 1024
SCHEMA_VERSION = 1

REASONS = frozenset({
    "CANCELLED", "WATCH_FULL", "CHECK_MISMATCH", "CONNECTION_LOST", "CATALOG_CHANGED", "COMPUTER_FULL",
    "EARLIER_CHANGE", "SERVER_BUSY", "PREPARE_FAILED", "BAD_FILE", "DOWNLOAD_STOPPED", "OTHER",
})
STAGES: dict[str, frozenset[str]] = {
    "GATE": frozenset({"PASSED", "PASSED_TESTING_PLATFORM", "BLOCKED_BROWSER", "BLOCKED_MOBILE", "BLOCKED_PLATFORM"}),
    "CONNECT": frozenset({
        "CONNECTED", "NO_WATCH_CHOSEN", "CHOOSER_TIMEOUT", "STARTUP_ENTRY", "MODEL_NOT_ENABLED",
        "POLICY_UNAVAILABLE", "OTHER_TAB", "TIMEOUT", "CONNECTION_LOST", "FAILED",
    }),
    "MAP_RESULT": frozenset({"SUCCEEDED", "FAILED", "CANCELLED"}),
    "REMOVE": frozenset({"SUCCEEDED", "FAILED"}),
    "RECOVERY": frozenset({"FINISHED", "STILL_BLOCKED"}),
}
ERROR_NAMES = frozenset({
    "AbortError", "DataError", "InvalidAccessError", "InvalidStateError", "NetworkError", "NotAllowedError",
    "NotFoundError", "NotReadableError", "NotSupportedError", "OperationError", "QuotaExceededError",
    "SecurityError", "TimeoutError", "TypeError", "RangeError", "UnknownError", "Error", "Other",
})
RELAY_OUTCOMES = frozenset({"DELIVERED", "NOT_DOWNLOADED", "FAILED", "CANCELLED", "EXPIRED", "REFUSED", "INTERRUPTED"})
RELAY_REASON_OUTCOMES = frozenset({"FAILED", "REFUSED", "INTERRUPTED"})
RELAY_REASONS = frozenset({
    "NOT_REVIEWED", "SERVER_BUSY", "COMPUTER_LIMIT", "POLICY_WITHHELD", "NO_ARTIFACT", "SOURCE_NOT_ALLOWED",
    "PROVIDER_HTTP_ERROR", "PROVIDER_UNREACHABLE", "PROVIDER_CHANGED", "BAD_ARCHIVE", "SIZE_LIMIT",
    "DISK_FULL", "SERVICE_RESTARTED", "OTHER",
})

_MODEL = re.compile(r"[a-z0-9 .+\-–/()]{1,80}")
_PROVIDER = re.compile(r"[a-z0-9-]{1,40}")
_PACKAGE = re.compile(r"[A-Za-z0-9._-]{1,120}")
_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SYSTEM = {
    "osFamily": frozenset({"macOS", "Windows", "Linux", "ChromeOS", "Android", "iOS", "Other"}),
    "osMajor": (0, 99),
    "browserFamily": frozenset({"Chrome", "Edge", "Opera", "Firefox", "Safari", "Other"}),
    "browserMajor": (1, 999),
}
_DIAGNOSTIC = {"errorName": ERROR_NAMES, "httpStatus": (100, 599), "mtpResponse": (0x2000, 0xA8FF)}
_WATCH = {"model": _MODEL, "firmware": re.compile(r"\d{1,5}(\.\d{1,3})?")}
_FIELDS: dict[str, dict[str, Any]] = {
    "GATE": {},
    "CONNECT": {**_WATCH, "baseModel": _MODEL},
    "MAP_RESULT": {
        **_WATCH, "operation": frozenset({"install", "update"}), "provider": _PROVIDER, "packageId": _PACKAGE,
        "sizeBucket": frozenset({"<100MB", "100-500MB", "500MB-1GB", "1-2GB", "2-4GB", ">4GB"}),
        "failureStage": frozenset({"PREPARE", "DOWNLOAD", "WRITE", "VERIFY"}), "reason": REASONS,
        "writeStarted": bool, "writeS": (0, 86400), "verifyS": (0, 86400),
    },
    "REMOVE": {**_WATCH, "provider": _PROVIDER, "reason": REASONS},
    "RECOVERY": dict(_WATCH),
}
EVENT_COLUMNS = {
    "osFamily": "os_family", "osMajor": "os_major", "browserFamily": "browser_family", "browserMajor": "browser_major",
    "model": "model", "firmware": "firmware", "baseModel": "base_model", "operation": "operation",
    "provider": "provider", "packageId": "package_id", "sizeBucket": "size_bucket", "failureStage": "failure_stage",
    "reason": "reason", "writeStarted": "write_started", "writeS": "write_s", "verifyS": "verify_s",
    "errorName": "error_name", "httpStatus": "http_status", "mtpResponse": "mtp_response",
}
# Outcomes that carry no failure diagnostics.
_SUCCESS_OUTCOMES = frozenset({"PASSED", "PASSED_TESTING_PLATFORM", "CONNECTED", "SUCCEEDED", "FINISHED"})
# A clock this far ahead of the API is not trusted (same rule as map statistics).
FUTURE_SKEW = timedelta(minutes=10)


class WebInstallerValidationError(ValueError):
    pass


def _document(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_WEB_INSTALLER_BYTES:
        raise WebInstallerValidationError("payload_size")
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebInstallerValidationError("invalid_json") from exc
    if not isinstance(body, dict):
        raise WebInstallerValidationError("invalid_json")
    if type(body.get("schemaVersion")) is not int or body["schemaVersion"] != SCHEMA_VERSION:
        raise WebInstallerValidationError("unsupported_schema")
    # Optional fields encoded as null are treated as omitted.
    return {key: value for key, value in body.items() if value is not None and key != "schemaVersion"}


def _allowed(rule: Any, value: Any) -> bool:
    if rule is bool:
        return type(value) is bool
    if isinstance(rule, frozenset):
        return isinstance(value, str) and value in rule
    if isinstance(rule, tuple):
        return type(value) is int and rule[0] <= value <= rule[1]
    return isinstance(value, str) and bool(rule.fullmatch(value))


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        raise WebInstallerValidationError(code)
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WebInstallerValidationError(code) from exc
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise WebInstallerValidationError(code)
    return moment


def _is_test(body: dict[str, Any]) -> bool:
    value = body.pop("isTest", False)
    if type(value) is not bool:
        raise WebInstallerValidationError("invalid_isTest")
    return value


def validate_event(raw: bytes, *, now: datetime | None = None) -> dict[str, Any]:
    """A web_installer_event row, or ``WebInstallerValidationError`` (HTTP 400).
    Anything not allowed is refused, not dropped, so an over-sending page is noticed."""
    body = _document(raw)
    now = now or datetime.now(timezone.utc)
    row: dict[str, Any] = {"is_test": _is_test(body)}
    for key, column in (("id", "event_id"), ("sessionId", "session_id")):
        value = body.pop(key, None)
        if not isinstance(value, str) or not _UUID_TEXT.fullmatch(value):
            raise WebInstallerValidationError("invalid_" + key)
        row[column] = str(UUID(value))
    occurred = _time(body.pop("occurredAt", None), "invalid_occurredAt")
    row["occurred_at"] = now if occurred > now + FUTURE_SKEW else occurred
    stage, outcome = body.pop("stage", None), body.pop("outcome", None)
    if not isinstance(stage, str) or stage not in STAGES:
        raise WebInstallerValidationError("invalid_stage")
    if not isinstance(outcome, str) or outcome not in STAGES[stage]:
        raise WebInstallerValidationError("invalid_outcome")
    row["stage"], row["outcome"] = stage, outcome
    allowed = {**_SYSTEM, **_FIELDS[stage], **(_DIAGNOSTIC if outcome not in _SUCCESS_OUTCOMES else {})}
    for key, value in body.items():
        if key not in allowed:
            raise WebInstallerValidationError("unknown_fields")
        if not _allowed(allowed[key], value):
            raise WebInstallerValidationError("invalid_" + key)
        row[EVENT_COLUMNS[key]] = value
    if stage == "MAP_RESULT" and "operation" not in row:
        raise WebInstallerValidationError("missing_operation")
    if outcome == "SUCCEEDED" and ("failure_stage" in row or "reason" in row):
        raise WebInstallerValidationError("unexpected_reason")
    return row


def validate_relay_job(raw: bytes, *, now: datetime | None = None) -> dict[str, Any]:
    """A web_installer_relay_job row, or ``WebInstallerValidationError`` (HTTP 400)."""
    body = _document(raw)
    now = now or datetime.now(timezone.utc)
    row: dict[str, Any] = {"is_test": _is_test(body)}
    job_id = body.pop("id", None)
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{16,32}", job_id):
        raise WebInstallerValidationError("invalid_id")
    row["job_id"] = job_id
    row["requested_at"] = _time(body.pop("requestedAt", None), "invalid_requestedAt")
    row["finished_at"] = _time(body.pop("finishedAt", None), "invalid_finishedAt")
    # The installer server and the API share a host clock, so a future time is an error.
    if not row["requested_at"] <= row["finished_at"] <= now + FUTURE_SKEW:
        raise WebInstallerValidationError("invalid_finishedAt")
    if "readyAt" in body:
        row["ready_at"] = _time(body.pop("readyAt"), "invalid_readyAt")
        if not row["requested_at"] <= row["ready_at"] <= row["finished_at"]:
            raise WebInstallerValidationError("invalid_readyAt")
    for key, column, rule in (("provider", "provider", _PROVIDER), ("packageId", "package_id", _PACKAGE)):
        value = body.pop(key, None)
        if not _allowed(rule, value):
            raise WebInstallerValidationError("invalid_" + key)
        row[column] = value
    for key, limit in (("region", 120), ("release", 40)):
        if key in body:
            value = body.pop(key)
            if not isinstance(value, str) or not 1 <= len(value) <= limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise WebInstallerValidationError("invalid_" + key)
            row[key] = value
    for key, column, required in (("sizeBytes", "size_bytes", False), ("servedBytes", "served_bytes", True)):
        value = body.pop(key, None)
        if value is None and not required:
            continue
        if type(value) is not int or not 0 <= value <= 2**53:
            raise WebInstallerValidationError("invalid_" + key)
        row[column] = value
    outcome = body.pop("outcome", None)
    if not isinstance(outcome, str) or outcome not in RELAY_OUTCOMES:
        raise WebInstallerValidationError("invalid_outcome")
    row["outcome"] = outcome
    reason = body.pop("reason", None)
    if (reason is None) != (outcome not in RELAY_REASON_OUTCOMES) or (
            reason is not None and (not isinstance(reason, str) or reason not in RELAY_REASONS)):
        raise WebInstallerValidationError("invalid_reason")
    row["reason"] = reason
    if "providerHttpStatus" in body:
        status = body.pop("providerHttpStatus")
        if reason != "PROVIDER_HTTP_ERROR" or not _allowed((100, 599), status):
            raise WebInstallerValidationError("invalid_providerHttpStatus")
        row["provider_http_status"] = status
    if body:
        raise WebInstallerValidationError("unknown_fields")
    return row


def _median(values: list[Any]) -> float | None:
    values = [value for value in values if value is not None and value >= 0]
    return round(statistics.median(values), 1) if values else None


def _seconds(start: Any, end: Any) -> float | None:
    return (end - start).total_seconds() if start and end else None


def joined(*values: Any) -> str | None:
    return " ".join(str(v) for v in values if v is not None) or None


def _system(row: dict[str, Any]) -> str | None:
    return joined(row.get("os_family"), row.get("os_major"))


def final_map_results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One result per (session, package, operation): the latest MAP_RESULT of
    that page load, so a failure replaced by a retry is not a final failure."""
    latest: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in events:
        if row["stage"] != "MAP_RESULT":
            continue
        key = (row["session_id"], row.get("package_id"), row.get("operation"))
        if key not in latest or row["occurred_at"] >= latest[key]["occurred_at"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda row: row["occurred_at"], reverse=True)


def _grouped(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        group = groups.setdefault(tuple(row.get(k) for k in keys), {**{k: row.get(k) for k in keys}, "count": 0,
                                  "writeStarted": 0, "models": [], "last": row["occurred_at"]})
        group["count"] += 1
        group["writeStarted"] += bool(row.get("write_started"))
        group["last"] = max(group["last"], row["occurred_at"])
        if row.get("model") and row["model"] not in group["models"] and len(group["models"]) < 5:
            group["models"].append(row["model"])
    return sorted(groups.values(), key=lambda g: (-g["count"], -g["last"].timestamp()))


def summarize(events: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Admin Web installer read model for one period (test records already excluded)."""
    final = final_map_results(events)
    successes = [row for row in final if row["outcome"] == "SUCCEEDED"]
    connected = {row["session_id"] for row in events if row["stage"] == "CONNECT" and row["outcome"] == "CONNECTED"}
    models: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in events:
        if row["stage"] != "CONNECT" or row["outcome"] != "CONNECTED":
            continue
        model = models.setdefault((row.get("model"), _system(row)), {
            "model": row.get("model"), "system": _system(row), "firmware": [], "sessions": set(),
            "installed": 0, "updated": 0, "failed": 0, "last": row["occurred_at"]})
        model["sessions"].add(row["session_id"])
        model["last"] = max(model["last"], row["occurred_at"])
        if row.get("firmware") and row["firmware"] not in model["firmware"] and len(model["firmware"]) < 6:
            model["firmware"].append(row["firmware"])
    for row in final:
        model = models.get((row.get("model"), _system(row)))
        if model is None:
            continue
        if row["outcome"] == "SUCCEEDED":
            model["updated" if row.get("operation") == "update" else "installed"] += 1
        elif row["outcome"] == "FAILED":
            model["failed"] += 1
    systems: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in events:
        if row["stage"] != "GATE":
            continue
        browser = joined(row.get("browser_family"), row.get("browser_major"))
        item = systems.setdefault((_system(row), browser), {"system": _system(row), "browser": browser, "visits": 0, "blocked": 0})
        item["visits"] += 1
        item["blocked"] += row["outcome"].startswith("BLOCKED")
    recent = sorted(final + [r for r in events if r["stage"] == "REMOVE"], key=lambda row: row["occurred_at"], reverse=True)
    requests = [job for job in jobs if job["outcome"] != "REFUSED"]
    delivered = [job for job in jobs if job["outcome"] == "DELIVERED"]
    providers: dict[str, dict[str, Any]] = {}
    for job in jobs:
        item = providers.setdefault(job["provider"], {"provider": job["provider"], "requests": 0, "delivered": 0,
                                                      "failed": 0, "servedBytes": 0})
        item["requests"] += job["outcome"] != "REFUSED"
        item["delivered"] += job["outcome"] == "DELIVERED"
        item["failed"] += job["outcome"] in RELAY_REASON_OUTCOMES
        item["servedBytes"] += job["served_bytes"] or 0
    server_problems: dict[tuple[Any, ...], dict[str, Any]] = {}
    for job in jobs:
        if job["outcome"] not in RELAY_REASON_OUTCOMES:
            continue
        key = (job["outcome"], job["reason"], job.get("provider_http_status"), job["provider"])
        item = server_problems.setdefault(key, {"outcome": key[0], "reason": key[1], "providerHttpStatus": key[2],
                                                "provider": key[3], "count": 0, "last": job["requested_at"]})
        item["count"] += 1
        item["last"] = max(item["last"], job["requested_at"])
    watch_failures = [row for row in events if row["stage"] in ("MAP_RESULT", "REMOVE") and row["outcome"] == "FAILED"]
    return {
        "watch": {
            "connectedSessions": len(connected),
            "installed": sum(row.get("operation") != "update" for row in successes),
            "updated": sum(row.get("operation") == "update" for row in successes),
            "failed": sum(row["outcome"] == "FAILED" for row in final),
            "medianWriteS": _median([row.get("write_s") for row in successes]),
            "medianVerifyS": _median([row.get("verify_s") for row in successes]),
            "models": sorted(({**m, "sessions": len(m["sessions"])} for m in models.values()),
                             key=lambda m: (-m["sessions"], m["model"] or "~", m["system"] or "")),
            "systems": sorted(systems.values(), key=lambda s: (-s["visits"], s["system"] or "~", s["browser"] or "")),
            "connectProblems": _grouped(
                [row for row in events if row["stage"] == "CONNECT" and row["outcome"] != "CONNECTED"],
                ("outcome", "error_name", "os_family"),
            ),
            "mapProblems": _grouped(
                watch_failures, ("stage", "failure_stage", "reason", "error_name", "http_status", "mtp_response"),
            ),
            "recent": recent[:30],
        },
        "server": {
            "requests": len(requests),
            "delivered": len(delivered),
            "failed": sum(job["outcome"] in RELAY_REASON_OUTCOMES for job in jobs),
            "servedBytes": sum(job["served_bytes"] or 0 for job in jobs),
            "medianReadyS": _median([_seconds(job["requested_at"], job.get("ready_at")) for job in requests]),
            "medianSendS": _median([_seconds(job.get("ready_at"), job["finished_at"]) for job in delivered]),
            "providers": sorted(providers.values(), key=lambda p: (-p["requests"], p["provider"])),
            "problems": sorted(server_problems.values(), key=lambda p: (-p["count"], -p["last"].timestamp())),
            "recent": jobs[:50],
        },
    }


def chart_summary(events: list[dict[str, Any]], jobs: list[dict[str, Any]], bucket_of: Any) -> dict[str, Any]:
    """Dashboard Web view: the same row shape as the app trend, from web records
    only. Downloads are relay jobs; installs are final map results."""
    buckets: dict[Any, dict[str, int]] = {}
    def add(moment: datetime, field: str) -> None:
        row = buckets.setdefault(bucket_of(moment), {"bucket": bucket_of(moment)})
        row[field] = row.get(field, 0) + 1
    final = final_map_results(events)
    for row in final:
        if row["outcome"] in ("SUCCEEDED", "FAILED"):
            update = row.get("operation") == "update"
            add(row["occurred_at"], ("map_update_success_count" if update else "success_count") if row["outcome"] == "SUCCEEDED"
                else ("map_update_failed_count" if update else "failed_count"))
    for job in jobs:
        if job["outcome"] == "DELIVERED" or job["outcome"] in RELAY_REASON_OUTCOMES:
            add(job["requested_at"], "download_success_count" if job["outcome"] == "DELIVERED" else "download_failed_count")
    rate = lambda ok, bad: ok / (ok + bad) * 100 if ok + bad else None
    installs = sum(r["outcome"] == "SUCCEEDED" and r.get("operation") != "update" for r in final)
    failed = sum(r["outcome"] == "FAILED" and r.get("operation") != "update" for r in final)
    delivered = sum(j["outcome"] == "DELIVERED" for j in jobs)
    download_failed = sum(j["outcome"] in RELAY_REASON_OUTCOMES for j in jobs)
    return {
        "trend": [buckets[key] for key in sorted(buckets)],
        "completedInstallCount": installs, "failedInstallCount": failed, "installSuccessRate": rate(installs, failed),
        "mapUpdateCount": sum(r["outcome"] in ("SUCCEEDED", "FAILED") and r.get("operation") == "update" for r in final),
        "completedDownloadCount": delivered, "failedDownloadCount": download_failed,
        "downloadSuccessRate": rate(delivered, download_failed),
    }

"""Read-only Needs attention projection for an authorized operator agent.

The populations are the Dashboard Needs attention ones (open installation
problems, open failed update reports, open support reports, failed or degraded
Health checks). Issue titles and bodies are the sanitised reports Admin already
prepares for GitHub issues; every other text value, including stored support
report bodies, passes through the same sanitiser. Nothing here changes data.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Any

from .admin import (
    _HEALTH_ISSUE_STATES,
    _admin_app_version_label,
    _diagnostic_error_reason,
    _display_identity,
    _github_issue_report,
    _group_operation_tasks,
    _identity_parts,
    _model_detail_url,
    _sanitised_issue_value,
    _system_health_cards,
    _timestamp_iso,
)
from .support_report_admin import support_report_url
from .support_reports import MAX_USER_MESSAGE_LENGTH
from .update_diagnostics import _update_identity, _update_issue_report, load_update_diagnostics

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1
LIST_LIMIT = 50
REVIEW_COUNT_KEYS = (
    "installationIssues", "githubIssuesInProgress", "identityPending",
    "readyToPublish", "missingDiagnostics",
)


def attention_report(service: Any) -> dict[str, Any]:
    """One read; a failing section is unavailable, never a smaller list."""
    admin_url = service.public_base_url + "/admin"

    def section(name: str, reader: Any) -> Any:
        try:
            return _sanitised(reader())
        except Exception:
            LOGGER.exception("attention section %s failed", name)
            return {"available": False}

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "counts": section("counts", lambda: _counts(service.database)),
        "installationProblems": section("installationProblems", lambda: _installation_problems(service, admin_url)),
        "updateProblems": section("updateProblems", lambda: _update_problems(service.database, admin_url)),
        "supportReports": section("supportReports", lambda: _support_reports(service.database, admin_url)),
        "systemChecks": section("systemChecks", lambda: _system_checks(service, admin_url)),
    }


# Already sanitised Markdown reports and server-built links keep their form.
_PRESANITISED_KEYS = frozenset({"issueTitle", "issueBody", "adminUrl", "actionUrl"})


def _sanitised(value: Any, key: str = "") -> Any:
    """Pass every other text value, at any depth, through the issue sanitiser."""
    if isinstance(value, dict):
        return {name: _sanitised(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_sanitised(item, key) for item in value]
    if isinstance(value, str) and key not in _PRESANITISED_KEYS:
        return _sanitised_issue_value(value)
    return value


def _counts(database: Any) -> dict[str, Any]:
    review = database.admin_review_summary()
    if review.get("available") is False:
        raise RuntimeError("review summary unavailable")
    return {
        **{key: review.get(key) for key in REVIEW_COUNT_KEYS},
        "supportReports": database.support_report_open_count(),
    }


def _optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text and text not in {"—", "Unknown"} else None


def _installation_problems(service: Any, admin_url: str) -> dict[str, Any]:
    devices = {
        str(device.get("id") or device.get("device_id") or ""): device
        for device in service.admin_devices().get("devices", [])
    }
    items = []
    for operation_key, results in _group_operation_tasks(service.database.open_installation_problem_details()).items():
        first = results[0]
        identity = str(first.get("compatibility_identity") or first.get("model") or "Unknown device")
        model, variant = _display_identity(identity, first)
        device = devices.get(str(first.get("canonical_device_model_id") or ""))
        if device:
            model, variant, _ = _identity_parts(device)
        title, body = _github_issue_report(identity, results, device=device)
        latest = max(results, key=lambda result: _timestamp_iso(result.get("occurred_at")))
        items.append({
            "operationKey": operation_key,
            "occurredAt": _timestamp_iso(latest.get("occurred_at")) or None,
            "model": model,
            "variant": _optional(variant),
            "canonicalDeviceModelId": first.get("canonical_device_model_id") or None,
            "reason": _diagnostic_error_reason(results),
            "appVersion": _admin_app_version_label(
                latest.get("release_label") or latest.get("terento_version"), latest.get("app_build"),
            ),
            "adminUrl": _absolute(admin_url, _model_detail_url(first)),
            "issueTitle": title,
            "issueBody": body,
        })
    items.sort(key=lambda item: item["occurredAt"] or "", reverse=True)
    return {"total": len(items), "items": items[:LIST_LIMIT]}


def _update_problems(database: Any, admin_url: str) -> dict[str, Any]:
    data = load_update_diagnostics(database, outcome="failed", lifecycle="ACTIVE")
    items = []
    for row in data["rows"]:
        _, variant, model = _update_identity(row)
        title, body = _update_issue_report(row)
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        items.append({
            "diagnosticId": str(row["event_id"]),
            "occurredAt": _timestamp_iso(row.get("occurred_at")) or None,
            "model": model,
            "variant": _optional(variant),
            "canonicalDeviceModelId": row.get("canonical_device_model_id") or None,
            "appVersion": _admin_app_version_label(payload.get("terentoVersion"), payload.get("appBuild")),
            "linkedGithubIssue": row.get("linked_github_issue") or None,
            "adminUrl": f"{admin_url}/update-diagnostics?diagnosticId={row['event_id']}",
            "issueTitle": title,
            "issueBody": body,
        })
    totals = data.get("totals")
    if not isinstance(totals, dict) or totals.get("open_failed") is None:
        # The list read alone cannot give the Open total.
        raise RuntimeError("update report totals unavailable")
    return {"total": int(totals["open_failed"]), "items": items}


def _support_reports(database: Any, admin_url: str) -> dict[str, Any]:
    items = []
    for row in database.open_support_report_details(LIST_LIMIT):
        message = str(row.get("user_message") or "")[:MAX_USER_MESSAGE_LENGTH]
        items.append({
            "reference": row["reference"],
            "receivedAt": _timestamp_iso(row.get("received_at")) or None,
            "category": row.get("category"),
            "appVersion": _admin_app_version_label(row.get("release_label"), row.get("app_build")),
            "operationId": str(row["operation_id"]) if row.get("operation_id") else None,
            "linkedGithubIssue": row.get("linked_github_issue") or None,
            "adminUrl": _absolute(admin_url, support_report_url(row["reference"])),
            "userMessage": message or None,
            "report": row.get("report") if isinstance(row.get("report"), dict) else None,
        })
    return {"total": database.support_report_open_count(), "items": items}


def _plain(value: Any) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def _absolute(admin_url: str, href: Any) -> str | None:
    href = str(href or "").strip()
    if not href:
        return None
    return admin_url.removesuffix("/admin") + href if href.startswith("/") else href


def _system_checks(service: Any, admin_url: str) -> dict[str, Any]:
    cards = _system_health_cards(service.operational_health())[0]
    items = [{
        "check": card["title"],
        "status": card["status"],
        "group": card.get("group"),
        "reason": _plain(card.get("reason")) or None,
        "action": _plain(card.get("action")) or None,
        "actionUrl": _absolute(admin_url, card.get("actionHref")),
        "lastChecked": _timestamp_iso(card.get("lastChecked")) or None,
    } for card in cards if card["status"] in _HEALTH_ISSUE_STATES]
    return {"total": len(items), "adminUrl": f"{admin_url}/system-health", "items": items}

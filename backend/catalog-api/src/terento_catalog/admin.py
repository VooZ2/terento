from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from .admin_revisions import section_revisions, statistics_revisions

import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .campaign_links import CAMPAIGN_SUGGESTIONS, MEDIUM_OPTIONS, SOURCE_OPTIONS
from .asset_attribution import generic_fallback_image
from .admin_brand_tokens_generated import ADMIN_BRAND_TOKENS_CSS
from .compatibility_status import (
    CANONICAL_STATUS_ORDER,
    STATUS_PUBLIC_COPY,
    CompatibilityStatus,
    calculate_compatibility_status,
)
from .device_catalog import _official_source_image_url
from .failure_reasons import failure_reason_label, normalize_failure_reason
from .failure_context import validate_context
from .map_capability import classify_map_capable
from .installation_policy import installation_authorization_for_row
from .device_labels import model_label, variant_label
from .admin_world_map import WORLD_MAP_COUNTRY_ALIASES, WORLD_MAP_SVG
from .maprando_geography import (
    REGION_DISPLAY_NAMES as MAPRANDO_REGION_DISPLAY_NAMES,
    REGION_GEOGRAPHY,
)
from .operational_health import provider_catalog_health


PASSWORD_MIN_LENGTH = 14
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,64}")
PBKDF2_ITERATIONS = 600_000
GITHUB_ADMIN_NOTE_MAX_LENGTH = 500
GITHUB_ISSUE_URL_MAX_LENGTH = 7_000
GITHUB_NEW_ISSUE_URL = "https://github.com/VooZ2/terento/issues/new"
_ADMIN_NONCE_PLACEHOLDER = "__TERENTO_ADMIN_NONCE__"
_ADMIN_TEXT_INPUT_LIMIT = 8_192


class AdminValidationError(ValueError):
    pass


def validate_username(value: str) -> str:
    username = value.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AdminValidationError("Username must contain 3–64 letters, numbers, or . _ - characters.")
    return username


def validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH or len(value) > 256:
        raise AdminValidationError(f"Password must be {PASSWORD_MIN_LENGTH}–256 characters.")
    return value


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2-sha256",
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2-sha256":
            return False
        salt_bytes = _decode_base64(salt)
        expected_bytes = _decode_base64(expected)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt_bytes, int(iterations), len(expected_bytes)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected_bytes)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def format_timestamp(value: Any) -> str:
    if value is None:
        return "—"
    parsed = _parse_timestamp(value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _timestamp_markup(value: Any) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return html.escape(format_timestamp(value))
    iso = parsed.isoformat()
    return (
        f"<time class='admin-timestamp' datetime='{html.escape(iso, quote=True)}' "
        f"data-admin-timestamp='{html.escape(iso, quote=True)}'>"
        f"{html.escape(format_timestamp(parsed))}</time>"
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized_value = value.strip()
        # Accept legacy admin strings that lost the separator between date
        # and time without changing the stored timestamp.
        normalized_value = re.sub(
            r"^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)$",
            r"\1T\2",
            normalized_value,
        )
        try:
            parsed = datetime.fromisoformat(normalized_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_iso(value: Any) -> str:
    parsed = _parse_timestamp(value)
    return parsed.isoformat() if parsed is not None else ""


def _latest_data_timestamp(rows: list[dict[str, Any]]) -> datetime | None:
    values = [
        _parse_timestamp(row.get(key))
        for row in rows
        for key in ("last_success", "last_failure", "last_evidence")
    ]
    parsed = [value for value in values if value is not None]
    return max(parsed) if parsed else None


def _row_compatibility_status(row: dict[str, Any]) -> CompatibilityStatus | None:
    """Recompute the display status from the canonical evidence dimensions."""
    successful = int(row.get("successful_install_count") or 0)
    return calculate_compatibility_status(
        successful_install_count=successful,
        recognized_map_capable_evidence=(
            row.get("recognized_map_capable_evidence") is True or successful > 0
        ),
    )


def _format_rate(value: Any) -> str:
    if value is None:
        return "—"
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "—"
    if rate.is_integer():
        return f"{int(rate)}%"
    return f"{rate:.1f}%"


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _optional_count_label(value: Any, suffix: str = "") -> str:
    number = _optional_nonnegative_int(value)
    return f"{number:,}{suffix}" if number is not None else f"—{suffix}"


def _admin_error_counter(
    value: Any,
    *,
    available: bool = True,
    href: str | None = None,
    aria_label: str | None = None,
    data_stat: str | None = None,
) -> str:
    """Render an error count with neutral unknown and positive-only danger state."""
    number = _optional_nonnegative_int(value) if available else None
    rendered = str(number) if number is not None else "—"
    classes = "admin-error-counter" + (" is-positive" if number is not None and number > 0 else "")
    stat_attribute = f" data-stat='{html.escape(data_stat, quote=True)}'" if data_stat else ""
    counter = f"<strong class='{classes}'{stat_attribute}>{rendered}</strong>"
    if not href:
        return counter
    label = aria_label or f"View {rendered} open error{'s' if rendered != '1' else ''}"
    return (
        f"<a class='error-count' href='{html.escape(href, quote=True)}' "
        f"aria-label='{html.escape(label, quote=True)}'>{counter}</a>"
    )


def _count_label(value: Any, singular: str, plural: str | None = None) -> str:
    """Render a count with consistent singular/plural copy across the admin UI."""
    count = _optional_nonnegative_int(value)
    if count is None:
        return "—"
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def _admin_icon(name: str) -> str:
    """Return one small, accessible SVG icon for repeated admin affordances."""
    paths = {
        "external": (
            "<path d='M9.5 2.5h4v4'/><path d='m8 8 5.5-5.5'/><path "
            "d='M12 9.5v2.75A1.75 1.75 0 0 1 10.25 14h-6.5A1.75 1.75 0 0 1 2 12.25v-6.5A1.75 1.75 0 0 1 3.75 4H6.5'/>"
        ),
        "arrow-right": "<path d='M2.5 8h11'/><path d='m9 3.5 4.5 4.5L9 12.5'/>",
        "arrow-left": "<path d='M13.5 8h-11'/><path d='m7 3.5-4.5 4.5L7 12.5'/>",
        "check": "<path d='m3 8 3 3 7-7'/>",
        "clock": "<circle cx='8' cy='8' r='6'/><path d='M8 4v4l3 2'/>",
        "close": "<path d='m3.5 3.5 9 9'/><path d='m12.5 3.5-9 9'/>",
    }
    path = paths.get(name, "")
    if not path:
        return ""
    css_name = re.sub(r"[^a-z0-9_-]", "-", name.lower())
    return (
        f"<svg class='admin-icon admin-icon-{css_name}' viewBox='0 0 16 16' "
        f"fill='none' aria-hidden='true' focusable='false'>{path}</svg>"
    )


def _historical_catalog_indicator() -> str:
    """Compact provenance; the surrounding model link provides keyboard focus."""
    return (
        "<span class='historical-catalog-indicator'>"
        + '<svg class=\'catalog-archive-icon\' aria-hidden=\'true\' focusable=\'false\' xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M0 64C0 46.3 14.3 32 32 32l448 0c17.7 0 32 14.3 32 32l0 32c0 17.7-14.3 32-32 32L32 128C14.3 128 0 113.7 0 96L0 64zM32 176l448 0 0 240c0 35.3-28.7 64-64 64L96 480c-35.3 0-64-28.7-64-64l0-240zm152 64c-13.3 0-24 10.7-24 24s10.7 24 24 24l144 0c13.3 0 24-10.7 24-24s-10.7-24-24-24l-144 0z"/></svg>'
        + "<span class='historical-catalog-tooltip'>Historical catalog entry</span></span>"
    )


def _normalise_variant(value: Any) -> str:
    return variant_label({"variant": str(value or "")[:256]}) or "—"


def _identity_parts(row: dict[str, Any]) -> tuple[str, str, str]:
    model = str(row.get("model") or "—").strip()
    identity = str(row.get("compatibility_identity") or model).strip()
    variant = str(row.get("variant") or "").strip()
    case_size = row.get("case_size_mm")

    if "·" in identity:
        base, suffix = (part.strip() for part in identity.rsplit("·", 1))
        if base and not re.search(r"\binreach\b", suffix, flags=re.IGNORECASE):
            model = base
        if not variant:
            variant = suffix
    elif not variant:
        size_match = re.search(r"\b\d{2,3}\s*mm\b", identity, flags=re.IGNORECASE)
        if size_match:
            variant = size_match.group(0)
            model = (identity[:size_match.start()].rstrip(" -–—") + identity[size_match.end():]).strip()

    if case_size is not None and not re.search(r"\b\d{2,3}\s*mm\b", variant, flags=re.IGNORECASE):
        try:
            variant = f"{int(case_size)} mm {variant}".strip()
        except (TypeError, ValueError):
            pass
    # Display-only cleanup; the canonical identity remains unchanged.
    size = re.search(r"\b\d{2,3}\s*mm\b", variant, flags=re.IGNORECASE)
    if size:
        model = re.sub(r"\s*[,·|:–—-]?\s*" + re.escape(size.group(0)) + r"\s*$", "", model, flags=re.IGNORECASE)
    model = model.strip(" ,·|:–—-")
    if row.get("canonical_device_model_id"):
        model = row.get("canonical_model") or row.get("catalog_model") or model
    return model_label(model) or "—", variant_label({**row, "model": model, "variant": variant}) or "—", identity


def _operation_key(result: dict[str, Any]) -> str:
    return str(
        result.get("operation_key")
        or result.get("operation_id")
        or result.get("event_id")
        or ""
    ).strip()


def _result_key(result: dict[str, Any]) -> str:
    """Identify one main-map result, not the enclosing install batch."""
    operation = str(result.get("operation_id") or "").strip()
    index = result.get("map_result_index")
    if operation and index is not None:
        return f"result:{operation}:{index}"
    existing_key = str(result.get("operation_key") or "").strip()
    if existing_key:
        return existing_key
    event_id = str(result.get("event_id") or "").strip()
    return f"event:{event_id}" if event_id else _operation_key(result)


def _group_operations(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        key = _result_key(event)
        if key:
            grouped.setdefault(key, []).append(event)
    for results in grouped.values():
        results.sort(key=lambda item: int(item.get("map_result_index") or 0))
    return grouped


def _group_operation_tasks(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group operator work by operation, keeping one task for a multi-map batch."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        # compatibility_operation_details exposes a per-result operation_key;
        # deliberately prefer the raw operation ID here so the queue remains
        # operation-level when one batch contains several map results.
        key = str(
            event.get("operation_id")
            or event.get("operationId")
            or event.get("event_id")
            or event.get("eventId")
            or event.get("operation_key")
            or ""
        ).strip()
        if key:
            grouped.setdefault(key, []).append(event)
    for results in grouped.values():
        results.sort(key=lambda item: (_timestamp_iso(item.get("occurred_at")), str(item.get("event_id") or "")))
    return grouped


def _is_preinstall_download_failure(result: dict[str, Any]) -> bool:
    """Return whether a provider download failed before device installation."""
    if result.get("preinstall_download_failure") is True or result.get("preinstall_download_failure") == 1:
        return True
    write_started = result.get("write_started")
    if not (write_started is False or write_started == 0):
        return False
    stage = str(result.get("failure_stage") or "").strip().casefold()
    code = str(result.get("failure_code") or "").strip().upper()
    return stage == "download" or code == "INSTALL_BLOCKED_DOWNLOAD_FAILED"

def _is_preinstall_download_operation(results: list[dict[str, Any]]) -> bool:
    """Keep provider acquisition failures out of installation history views."""
    return bool(results) and all(_is_preinstall_download_failure(result) for result in results)

def _identity_is_pending(results: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    if all(_is_preinstall_download_failure(result) for result in results):
        return False
    first = results[0]
    if first.get("canonical_device_model_id"):
        return False
    state = str(first.get("identity_resolution_state") or "").strip().upper()
    if state in {"RESOLVED", "NOT_IDENTIFIABLE"}:
        return False
    return state in {"", "UNRESOLVED", "PENDING"}


def _identity_group_key(value: dict[str, Any]) -> str:
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        return f"canonical:{canonical_id}"
    identity = str(value.get("compatibility_identity") or value.get("model") or "Unknown").strip()
    return f"identity:{identity}"


def _device_detail_url(
    device_id: Any, *, origin: str = "devices", state: str | None = None,
    anchor: str | None = None,
) -> str:
    parameters = {"from": "installations" if origin == "installations" else "devices"}
    if state:
        parameters["state"] = state
    url = f"/admin/devices/{quote(str(device_id or '').strip(), safe='')}?{urlencode(parameters)}"
    return f"{url}#{quote(anchor, safe='')}" if anchor else url


def _diagnostics_url(value: dict[str, Any], *, state: str | None = None) -> str:
    identity = str(value.get("compatibility_identity") or value.get("model") or "Unknown").strip()
    parameters = {"identity": identity}
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        parameters["canonical_device_id"] = canonical_id
    else:
        # A textual identity can be shared by both a canonical aggregate and a
        # still-unresolved aggregate. Preserve the unresolved scope so the
        # diagnostics route cannot redirect the pending row to the canonical
        # device before an operator reviews it.
        parameters["identity_scope"] = "unresolved"
    if state:
        parameters["state"] = state
    return "/admin/diagnostics?" + urlencode(parameters)


def _model_detail_url(value: dict[str, Any], *, state: str | None = None) -> str:
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        return _device_detail_url(
            canonical_id, origin="installations", state=state, anchor="installations",
        )
    return _diagnostics_url(value, state=state)


def _operation_is_problematic(results: list[dict[str, Any]]) -> bool:
    """Return whether an install operation needs diagnostic attention.

    Successful evidence is intentionally not a diagnostic error. A diagnostic
    is actionable when an install failed, never started, was blocked, or
    carries an explicit failure diagnostic.
    """
    for result in results:
        if _is_preinstall_download_failure(result):
            # Provider acquisition problems are expected operational history,
            # not installation defects requiring operator review.
            continue
        outcome = str(result.get("phase_outcome") or "").strip().upper()
        if outcome in {"FAILED", "NOT_STARTED", "INCOMPLETE", "BLOCKED"}:
            return True
        finishing = str(result.get("automatic_finishing_result") or "").strip().upper()
        if outcome == "SUCCEEDED" and finishing and finishing != "VERIFIED":
            return True
        if any(
            str(result.get(field) or "").strip()
            for field in ("failure_stage", "failure_code", "native_failure_code", "error_category")
        ):
            return True
        if result.get("write_started") is False:
            return True
    return False


def _diagnostic_summary_by_identity(
    events: list[dict[str, Any]], resolved_events: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, int]]:
    by_identity: dict[str, dict[str, int]] = {}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in events:
        identity = _identity_group_key(event)
        key = _result_key(event)
        if identity and key:
            grouped.setdefault(identity, {}).setdefault(key, []).append(event)
    resolved_grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in resolved_events or []:
        identity = _identity_group_key(event)
        key = _result_key(event)
        if identity and key:
            resolved_grouped.setdefault(identity, {}).setdefault(key, []).append(event)
    for identity in set(grouped) | set(resolved_grouped):
        operations = grouped.get(identity, {})
        historical = resolved_grouped.get(identity, {})
        historical_failures = sum(
            1 for results in historical.values()
            if _operation_counts_as_installation_attempt(results) and _operation_result(results) == "FAILED"
        )
        attempts = (
            sum(1 for results in operations.values() if _operation_counts_as_installation_attempt(results))
            + historical_failures
        )
        successful = sum(
            1 for results in operations.values()
            if _operation_counts_as_installation_attempt(results) and _operation_result(results) == "SUCCEEDED"
        )
        open_errors = sum(
            1 for results in operations.values()
            if _operation_counts_as_installation_attempt(results) and _operation_result(results) == "FAILED"
        )
        failed = open_errors + historical_failures
        pending = sum(1 for results in operations.values() if _identity_is_pending(results))
        by_identity[identity] = {
            "errors": open_errors,
            "open_errors": open_errors,
            "failed": failed,
            "attempts": attempts,
            "successful": successful,
            "identity_pending": pending,
        }
    return by_identity


def _normalise_github_issue_reference(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    match = re.fullmatch(r"#?(\d{1,10})", raw)
    if not match:
        raise ValueError("GitHub issue must be a Terento issue number such as #32")
    return f"#{int(match.group(1))}"


def _diagnostic_state_badge(value: str) -> str:
    normalized = str(value).upper()
    if normalized == "NONE":
        return "<span class='muted-value'>—</span>"
    if normalized == "RESOLVED":
        state, label = "RESOLVED", "Resolved"
    elif normalized in {"IN_PROGRESS", "IN-PROGRESS"}:
        state, label = "IN_PROGRESS", "In progress"
    elif normalized in {"UNDER_REVIEW", "UNDER-REVIEW"}:
        state, label = "UNDER_REVIEW", "Under review"
    elif normalized in {"IDENTITY_PENDING", "UNRESOLVED", "PENDING"}:
        state, label = "IDENTITY_PENDING", "Identity review"
    else:
        state, label = "OPEN", "Open"
    return f"<span class='diagnostic-state diagnostic-state-{state.lower()}'>{label}</span>"


def _diagnostic_value(value: Any) -> str:
    if value is None or value == "":
        return "<span class='muted-value'>—</span>"
    return html.escape(str(value))


def _diagnostic_boolean(value: Any) -> str:
    if value is None:
        return "<span class='muted-value'>—</span>"
    if isinstance(value, str):
        normalised = value.strip().casefold()
        if normalised in {"true", "1", "yes"}:
            return "Yes"
        if normalised in {"false", "0", "no"}:
            return "No"
    return "Yes" if bool(value) else "No"


def _diagnostic_result(value: Any) -> str:
    raw = str(value or "").strip().upper()
    labels = {
        "SUCCEEDED": "Successful",
        "FAILED": "Failed",
        "NOT_STARTED": "Not started",
        "INCOMPLETE": "Incomplete",
        "BLOCKED": "Blocked",
    }
    label = labels.get(raw, raw.title() if raw else "—")
    kind = {
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "NOT_STARTED": "not-started",
        "INCOMPLETE": "failed",
        "BLOCKED": "failed",
    }.get(raw, "unknown")
    return (
        f"<span class='diagnostic-result diagnostic-result-{kind}' "
        f"aria-label='Result: {html.escape(label)}'>{html.escape(label)}</span>"
    )


def _failure_context_fields(result: dict[str, Any], key: str, *, technical: bool = False) -> list[tuple[str, Any]]:
    context = result.get(key)
    try:
        validate_context(context)
    except ValueError:
        context = {}
    protection = context.get('protection', {})
    fields = [
        ('Boundary', context.get('boundary')), ('Protection reason', protection.get('protectionReason')),
        ('Native category', context.get('nativeCategory')), ('Retry count', context.get('retryCount')),
        ('Classification source', context.get('classificationSource')), ('Device presence', context.get('devicePresence')),
        ('Component', context.get('componentKind')),
    ]
    if technical:
        fields.extend((label, context.get(name)) for label, name in (
            ('Last successful boundary', 'lastSuccessfulBoundary'), ('Operation', 'operation'),
            ('Execution mode', 'executionMode'), ('Result kind', 'resultKind'),
            ('Native code namespace', 'nativeCodeNamespace'), ('Native result code', 'nativeResultCode'),
        ))
        fields.extend((name, protection.get(name)) for name in (
            'protectionBoundary', 'stableIdentityComparisonVersion', 'beforeObjectCount', 'afterObjectCount',
            'addedObjectCount', 'removedObjectCount', 'changedObjectCount', 'targetPresent', 'targetUnique',
            'targetKindMatches', 'targetFilenameMatches', 'targetSizeMatches', 'targetPathMatches', 'targetItemIDMatches',
        ))
    return [(label, 'unavailable' if value is None else value) for label, value in fields]


def _failure_context_summary(results: list[dict[str, Any]]) -> str:
    summaries = []
    for number, result in enumerate(results, 1):
        context = result.get('failure_context') or {}
        stage = result.get('optional_component_failure_stage') if isinstance(context, dict) and context.get('componentKind') == 'contours' else result.get('failure_stage')
        fields = [('Stage', stage or 'unavailable')] + _failure_context_fields(result, 'failure_context')
        rows = ''.join(f'<div><dt>{html.escape(label)}</dt><dd>{_diagnostic_value(value)}</dd></div>' for label, value in fields)
        summaries.append(f'<p>Failure context · {html.escape(_failure_result_label(result, number))}</p><dl class="diagnostic-detail-summary">{rows}</dl>')
    return ''.join(summaries)


def _failure_result_label(result: dict[str, Any], number: int) -> str:
    index = result.get('map_result_index')
    return f'mapResultIndex {index}' if type(index) is int and 0 <= index < 100 else f'displayed result {number} (mapResultIndex unavailable)'


def _diagnostic_technical_details(result: dict[str, Any], result_number: int) -> str:
    fields: list[tuple[str, Any]] = []
    for label, key in (
        ("Raw MTP model", "raw_mtp_model"),
        ("Local identity", "identity_resolution_code"),
        ("Native code", "native_failure_code"),
        ("Transfer progress", "transfer_progress_bucket"),
        ("Map result", "map_result_index"),
        ("Selected maps", "selected_map_count"),
        ("Optional component selected", "optional_component_selected"),
        ("Optional component outcome", "optional_component_outcome"),
        ("Optional component failure stage", "optional_component_failure_stage"),
        ("Optional component failure code", "optional_component_failure_code"),
        ("Optional component native code", "optional_component_native_failure_code"),
        ("Error category", "error_category"),
        ("Transport", "transport"),
    ):
        value = result.get(key)
        if value is not None and value != "":
            fields.append((label, value))
    for label, key in (
        ("Object created", "remote_object_created"),
        ("Cleanup attempted", "cleanup_attempted"),
        ("Cleanup succeeded", "cleanup_succeeded"),
    ):
        if result.get(key) is not None:
            fields.append((label, _diagnostic_boolean(result.get(key))))
    for key, prefix in (('failure_context', 'Failure'), ('original_failure_context', 'Original failure')):
        if key == 'original_failure_context' and result.get(key) is None:
            fields.append(('Original failure context', 'unavailable'))
        else:
            fields.extend((f'{prefix}: {label}', value) for label, value in _failure_context_fields(result, key, technical=result.get(key) is not None))
    rows = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{value if isinstance(value, str) and value.startswith('<span') else _diagnostic_value(value)}</dd></div>"
        for label, value in fields
    )
    content = (
        f"<dl>{rows}</dl>" if rows else
        "<p class='diagnostic-technical-empty'>Detailed diagnostics were not collected for this installation.</p>"
    )
    return (
        f"<details class='diagnostic-technical-details'>"
        f"<summary>Technical details <span class='disclosure-meta'>· map result {result_number}</span></summary>"
        f"{content}</details>"
    )


def _admin_brand(*, show_badge: bool = True) -> str:
    badge = '<span class="admin-badge">Admin</span>' if show_badge else ""
    return f"""<a class="admin-brand" href="/admin" aria-label="Terento admin home">
      <img src="https://terento.app/assets/logo-sky.svg" alt="" width="25" height="29">
      <span>Terento</span>{badge}
    </a>"""


def _admin_header(user: dict[str, Any], csrf_token: str, *, active: str = "evidence") -> str:
    username = html.escape(str(user.get("username") or ""))
    overview_class = " class='active'" if active == "overview" else ""
    evidence_class = " class='active'" if active in {"evidence", "installations"} else ""
    campaign_class = " class='active'" if active == "campaigns" else ""
    devices_class = " class='active'" if active == "devices" else ""
    providers_class = " class='active'" if active == "providers" else ""
    map_statistics_class = " class='active'" if active == "map-statistics" else ""
    system_health_class = " class='active'" if active == "system-health" else ""
    test_data_class = " class='active'" if active == "test-data" else ""
    tools_class = " class='active'" if active in {"test-data", "campaigns", "device-identification"} else ""
    account_class = " active" if active == "account" else ""
    tools_menu = f"""<details class="admin-tools-menu">
        <summary{tools_class}>Tools</summary>
        <div class="admin-tools-popover" role="group" aria-label="Admin tools">
          <a href="/admin/device-identification">Model source review</a>
          <a href="/admin/devices/identity-audit.json">Assignment audit</a>
          <a{test_data_class} href="/admin/test-data">Test data</a>
          <a{campaign_class} href="/admin/campaign-links">Campaign links</a>
        </div>
      </details>"""
    return f"""<a class="admin-skip-link" href="#main-content">Skip to content</a><header class="admin-topbar"><div class="admin-topbar-inner">
      <div class="admin-header-zone admin-header-left">{_admin_brand(show_badge=False)}<span class="admin-badge">Admin area</span><a class="admin-website-link" href="https://terento.app/" target="_blank" rel="noopener noreferrer" aria-label="Open Terento website in a new tab">Website {_admin_icon('external')}</a></div>
      <button id="admin-menu-toggle" class="secondary-button" type="button" aria-controls="admin-menu-panel" aria-expanded="false" hidden>Menu</button>
      <div id="admin-menu-panel"><nav class="admin-section-nav" aria-label="Admin sections"><div class="admin-nav-group" role="group" aria-label="Primary"><a{overview_class} href="/admin">Dashboard</a><a{evidence_class} href="/admin/installations">Installations</a><a{devices_class} href="/admin/devices">Devices</a><a{map_statistics_class} href="/admin/map-statistics">Maps</a><a{providers_class} href="/admin/providers">Providers</a><a{system_health_class} href="/admin/system-health">Health</a></div>{tools_menu}</nav>
      <nav class="admin-nav" aria-label="Admin navigation"><label class="timezone-control"><span class="sr-only">Time zone</span><select id="admin-timezone" aria-label="Time zone" title="Time zone"><option value="browser">Automatic (browser)</option><option value="UTC">UTC</option><option value="Europe/Vilnius">Europe/Vilnius</option><option value="Europe/London">Europe/London</option><option value="Europe/Berlin">Europe/Berlin</option><option value="America/New_York">America/New_York</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="Asia/Tokyo">Asia/Tokyo</select></label><a class="admin-user{account_class}" href="/admin/account" aria-label="Account settings for {username}">{username}</a>
      <a class="admin-mobile-website" href="https://terento.app/" target="_blank" rel="noopener noreferrer">Website {_admin_icon('external')}</a><form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><button class="link-button" type="submit">Sign out</button></form></nav></div>
    </div></header>"""


def local_test_data_page(
    summary: dict[str, Any], user: dict[str, Any], csrf_token: str,
    *, success: str | None = None, error: str | None = None,
) -> bytes:
    """Authenticated, explicit purge UI for local-only telemetry."""
    diagnostic_event_count = int(summary.get("diagnosticEventCount") or 0)
    map_event_count = int(summary.get("mapEventCount") or 0)
    operation_count = int(summary.get("operationCount") or 0)
    labels = ", ".join(
        html.escape(str(label)) for label in summary.get("releaseLabels", [])
    ) or "None"
    activity_rows = ''.join(
        f"<tr><td>{html.escape(str(row.get('stream') or '—'))}</td>"
        f"<td><code>{html.escape(str(row.get('release_label') or '—'))}</code></td>"
        f"<td class='column-status'>{html.escape(str(row.get('outcome') or '—'))}</td>"
        f"<td class='column-number'>{int(row.get('event_count') or 0)}</td>"
        f"<td class='column-date'>{_timestamp_markup(row.get('last_occurred_at'))}</td></tr>"
        for row in summary.get('activity', [])
    ) or "<tr><td colspan='5'>No local test events recorded.</td></tr>"
    content = f"""
      {_admin_header(user, csrf_token, active='test-data')}
      <main id="main-content" class="dashboard test-data-page" aria-labelledby="test-data-title">
        <div class="heading-row">
          <div>

            <h1 id="test-data-title">Test data</h1>

          </div>
        </div>
        {_success(success)}{_error(error)}
        <section class="provider-card test-data-card" aria-labelledby="local-telemetry-title">
          <div class="section-heading">
            <div>

              <h2 id="local-telemetry-title">Purgeable local telemetry</h2>
            </div>
          </div>
          <section class="admin-kpi-grid test-data-metrics" aria-label="Local test telemetry summary">
            <article><span>Diagnostic events</span><strong>{diagnostic_event_count}</strong></article>
            <article><span>Map events</span><strong>{map_event_count}</strong></article>
            <article><span>Distinct operations</span><strong>{operation_count}</strong></article>
          </section>
          <p class="test-data-release-labels">Release labels <code>{labels}</code></p>
          <p class="table-help">Local builds end in <code>-local</code> and are stored with <code>is_local_test=true</code>. Public beta builds use a public release label and <code>is_local_test=false</code>. These test events never contribute to user dashboards or public compatibility counts.</p>
          <div class="table-wrap"><table class="admin-table"><caption class="test-data-activity-caption">Latest local activity · up to 50 release/outcome groups</caption><thead><tr><th scope="col">Stream</th><th scope="col">Release</th><th scope="col" class="column-status">Result</th><th scope="col" class="column-number">Events</th><th scope="col" class="column-date">Last activity</th></tr></thead><tbody>{activity_rows}</tbody></table></div>
          <div class="test-data-danger-zone">
            <div>

              <h3>Delete test data</h3>
              <p class="table-help">This removes only server-classified local test telemetry.</p>
            </div>
            <form method="post" action="/admin/test-data/purge" class="admin-danger-form">
              <input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}">
              <label>Type <code>DELETE_LOCAL_TEST_DATA</code> to confirm
                <input name="confirmation" required autocomplete="off" pattern="DELETE_LOCAL_TEST_DATA" placeholder="DELETE_LOCAL_TEST_DATA" spellcheck="false">
              </label>
              <button type="submit" class="danger-button">Delete local test data</button>
            </form>
          </div>
        </section>
      </main>
    """
    return _layout("Test data", content, sections={"testData": summary})


def setup_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Create admin account",
        """
        <main class="auth-card" aria-labelledby="auth-title">
          {brand}

          <h1 id="auth-title">Create admin account</h1>

          {error}
          <form method="post" action="/admin/setup">
            <label>Username<input name="username" autocomplete="username" required minlength="3" maxlength="64"></label>
            <label>Password<input type="password" name="password" autocomplete="new-password" required minlength="14"></label>
            <label>Confirm password<input type="password" name="password_confirmation" autocomplete="new-password" required minlength="14"></label>
            <label>Deployment secret<input type="password" name="bootstrap_secret" autocomplete="one-time-code" required></label>
            <button type="submit">Create account</button>
          </form>
        </main>
        """.format(error=_error(error), brand=_admin_brand()),
    )


def login_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Admin sign in",
        """
        <main class="auth-card" aria-labelledby="auth-title">
          {brand}

          <h1 id="auth-title">Sign in</h1>

          {error}
          <form method="post" action="/admin/login">
            <label>Username<input name="username" autocomplete="username" required></label>
            <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
            <button type="submit">Sign in</button>
          </form>
        </main>
        """.format(error=_error(error), brand=_admin_brand()),
    )


def _diagnostic_error_reason(results: list[dict[str, Any]], *, resolved: bool = False) -> str:
    """Return a concise primary reason while keeping raw codes in Details."""
    for result in results:
        reason = normalize_failure_reason(result.get("error_category"))
        if reason != "unknown":
            return failure_reason_label(reason)
    for result in results:
        stage = str(result.get("failure_stage") or "").strip()
        if stage and stage.casefold() not in {"unknown", "none"}:
            return re.sub(r"[_-]+", " ", stage).strip().title() + " failed"
    if resolved:
        return "No normalized reason"
    return "Installation error"


def _overview_missing_diagnostic_item(
    event: dict[str, Any], csrf_token: str = "",
) -> str:
    href = html.escape(_overview_map_event_href(event), quote=True)
    context = html.escape(_overview_map_event_context(event))
    event_id = str(event.get("event_id") or event.get("eventId") or "").strip()
    try:
        event_id = str(UUID(event_id))
    except (ValueError, AttributeError):
        event_id = ""
    dismiss = ""
    if event_id:
        dismiss = (
            "<form method='post' action='/admin/review/missing-diagnostics/dismiss' "
            "class='admin-async-action overview-review-dismiss-form'>"
            f"<input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>"
            f"<input type='hidden' name='event_id' value='{html.escape(event_id, quote=True)}'>"
            "<button type='submit' class='overview-dismiss-button' "
            "aria-label='Dismiss review item' title='Dismiss review item'>×</button>"
            "</form>"
        )
    return (
        "<li class='overview-attention-item overview-attention-failed'>"
        "<span class='overview-attention-dot' aria-hidden='true'>●</span>"
        f"<div><strong>Install failed</strong>"
        f"<span>{context}</span>"
        "<small>No device diagnostic report received · "
        f"{_timestamp_markup(event.get('occurred_at'))}</small></div>"
        f"<div class='overview-attention-actions'><a class='overview-detail-link' href='{href}'>Inspect&nbsp;{_admin_icon('arrow-right')}</a>{dismiss}</div></li>"
    )


def _overview_provider_attention_item(provider: dict[str, Any]) -> str:
    provider_id = str(provider.get("id") or "").strip()
    name = str(provider.get("name") or provider_id or "Provider")
    health = str(provider.get("health") or "UNKNOWN").upper()
    health_label = {"WARNING": "Degraded", "UNKNOWN": "Evidence missing"}.get(health, health.title())
    href = f"/admin/providers/{quote(provider_id, safe='')}"
    return (
        f"<li class='overview-attention-item overview-attention-provider'>"
        f"<span class='overview-attention-dot' aria-hidden='true'>●</span>"
        f"<div><strong>{html.escape(name)} health {html.escape(health_label)}</strong>"
        f"<span>Provider health requires review</span>"
        f"<small>{_timestamp_markup(provider.get('lastHealthCheck'))}</small></div>"
        f"<a class='overview-detail-link' href='{html.escape(href, quote=True)}'>Inspect&nbsp;{_admin_icon('arrow-right')}</a></li>"
    )


def _overview_system_attention_item(card: dict[str, Any]) -> str:
    status = str(card.get("status") or "UNKNOWN").upper()
    status_label = {
        "WARNING": "Degraded",
        "FAILED": "Failed",
        "UNKNOWN": "Evidence missing",
    }.get(status, status.title())
    return (
        f"<li class='overview-attention-item overview-attention-review'>"
        f"<span aria-hidden='true'>!</span>"
        f"<div><strong>{html.escape(str(card.get('title') or 'System check'))} · {html.escape(status_label)}</strong>"
        f"<span>Review system check</span><small>{html.escape(str(card.get('reason') or 'System evidence needs review.'))} · {_timestamp_markup(card.get('lastChecked'))}</small></div>"
        f"<a class='overview-detail-link' href='/admin/system-health'>Inspect&nbsp;{_admin_icon('arrow-right')}</a></li>"
    )


_MAP_ACTIVITY_STATES = {
    "DOWNLOAD_STARTED": ("Download started · Outcome not received", "started", "info"),
    "DOWNLOAD_PROCESSING": ("Checking / unpacking · Outcome not received", "started", "info"),
    "DOWNLOAD_CANCELLED": ("Download cancelled", "unknown", "neutral"),
    "DOWNLOAD_INTERRUPTED": ("Download interrupted", "unknown", "warning"),
    "DOWNLOAD_SUCCEEDED": ("Download completed", "succeeded", "success"),
    "DOWNLOAD_FAILED": ("Download failed", "failed", "error"),
    "INSTALL_SUCCEEDED": ("Install succeeded", "succeeded", "success"),
    "INSTALL_FAILED": ("Install failed", "failed", "error"),
    "MAP_UPDATE_SUCCEEDED": ("Map update succeeded", "succeeded", "success"),
    "MAP_UPDATE_FAILED": ("Map update failed", "failed", "error"),
}


def _overview_map_event_label(event: dict[str, Any]) -> tuple[str, str]:
    if event.get("event_type") == "DOWNLOAD_STARTED" and event.get("has_recorded_outcome"):
        return "Download started · Outcome recorded", "started"
    if (
        event.get("event_type") in {"DOWNLOAD_STARTED", "DOWNLOAD_PROCESSING"}
        and event.get("is_stale")
    ):
        return (
            "Download started · Outcome missing"
            if event.get("event_type") == "DOWNLOAD_STARTED"
            else "Checking / unpacking · Outcome missing",
            "stale",
        )
    return _MAP_ACTIVITY_STATES.get(str(event.get("event_type") or "").upper(),
                                    ("Map activity", "unknown", "neutral"))[:2]


def _admin_event_outcome_label(value: Any) -> str:
    """Keep a non-terminal UNKNOWN outcome neutral in admin presentation."""
    normalized = str(value or "").strip().upper()
    if normalized == "UNKNOWN":
        return "—"
    return "Successful" if normalized == "SUCCEEDED" else normalized.title() if normalized else "—"


_ADMIN_REGION_DISPLAY_NAMES = {
    "SVN": "Slovenia", "SI": "Slovenia", "POL": "Poland",
    "CHE": "Switzerland", "DEU": "Germany", "AUT": "Austria",
    "FRA": "France", "ITA": "Italy", "ESP": "Spain",
    "PRT": "Portugal", "CZE": "Czechia", "SVK": "Slovakia",
    "HRV": "Croatia", "HUN": "Hungary", "ROU": "Romania",
    "BGR": "Bulgaria", "BEL": "Belgium", "NLD": "Netherlands",
    "DNK": "Denmark", "SWE": "Sweden", "NOR": "Norway",
    "FIN": "Finland", "EST": "Estonia", "GBR": "United Kingdom",
    "IRL": "Ireland", "GRC": "Greece", "LUX": "Luxembourg",
    "AND": "Andorra",
    "ANDORRA": "Andorra",
    "AT": "Austria",
    "CAPEVERDE": "Cape Verde",
    "CH": "Switzerland",
    "CENTRALAFRICANREPUBLIC": "Central African Republic",
    "DE": "Germany",
    "EE": "Estonia",
    "FAROEISLANDS": "Faroe Islands",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "IT": "Italy",
    "LT": "Lithuania",
    "LTU": "Lithuania",
    "LVA": "Latvia",
    "LV": "Latvia",
    "NO": "Norway",
    "PL": "Poland",
    "REPUBLICOFLATVIA": "Latvia",
    "REPUBLICOFLITHUANIA": "Lithuania",
    "PRINCIPALITYOFANDORRA": "Andorra",
    "ES": "Spain",
    "SWITZERLAND": "Switzerland",
    "SUISSE": "Switzerland",
    "US": "United States",
    "USA": "United States",
    "UNITEDSTATES": "United States",
    "CZECHIA": "Czechia",
    "CZECHREPUBLIC": "Czechia",
    "SE": "Sweden",
    "UA": "Ukraine",
}

# MapRando keeps reviewed provider-region identities separately from the
# human-readable package names. Keep that vocabulary available for admin
# fallback paths without changing the stored catalog IDs.
_ADMIN_PROVIDER_REGION_DISPLAY_NAMES = {
    re.sub(r"[^A-Za-z0-9]+", "", slug).upper(): name
    for slug, name in MAPRANDO_REGION_DISPLAY_NAMES.items()
}

# OpenTopoMap publishes broad North American regions rather than state
# packages. These hints make labels and country-map links clear; they do not
# change the world map's country-level aggregation.
_ADMIN_REGION_PARENT_COUNTRIES = {
    "CANADAEAST": "Canada",
    "CANADAWEST": "Canada",
    "USMIDWEST": "United States",
    "USNORTHEAST": "United States",
    "USPACIFIC": "United States",
    "USSOUTH": "United States",
    "USWEST": "United States",
}

_ADMIN_REGION_IDENTITY_ALIASES = {
    "SI": "SLOVENIA", "SVN": "SLOVENIA",
    "PL": "POLAND", "POL": "POLAND",
    "CH": "SWITZERLAND", "CHE": "SWITZERLAND",
    "SWISSCONFEDERATION": "SWITZERLAND",
    "SUISSE": "SWITZERLAND",
    "US": "UNITEDSTATES", "USA": "UNITEDSTATES",
    "UNITEDSTATES": "UNITEDSTATES",
    "CZ": "CZECHIA", "CZE": "CZECHIA",
    "CZECHIA": "CZECHIA", "CZECHREPUBLIC": "CZECHIA",
    "REPUBLIQUETCHEQUE": "CZECHIA",
    "DE": "GERMANY", "DEU": "GERMANY",
    "AND": "ANDORRA",
    "ANDORRA": "ANDORRA",
    "PRINCIPALITYOFANDORRA": "ANDORRA",
    "LT": "LITHUANIA",
    "LTU": "LITHUANIA",
    "LITHUANIA": "LITHUANIA",
    "REPUBLICOFLITHUANIA": "LITHUANIA",
}


def _admin_region_token(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def _admin_country_alias_data() -> tuple[dict[str, str], dict[str, str]]:
    """Build country aliases without collapsing provider subregions.

    The world-map alias table knows many country spellings, while MapRando's
    reviewed geography table identifies which provider slugs are whole-country
    regions. Combine only those sources; broad map aliases such as Balearics
    must remain region-specific in the Regions statistics.
    """
    identities_by_country: dict[str, str] = {}
    displays_by_identity: dict[str, str] = {}

    # Preserve established admin identities where the existing display table
    # already names an ISO-2/ISO-3 country code.
    for alias, display in _ADMIN_REGION_DISPLAY_NAMES.items():
        token = _admin_region_token(alias)
        map_country = WORLD_MAP_COUNTRY_ALIASES.get(token)
        if len(token) not in {2, 3} or not map_country:
            continue
        country_code = _admin_region_token(map_country)
        identity = _admin_region_token(display)
        if country_code and identity and identity != "UNKNOWN":
            identities_by_country.setdefault(country_code, identity)
            displays_by_identity.setdefault(identity, display)

    # MapRando supplies the provider-native spellings (for example
    # BELGIQUE) and explicitly marks whole-country regions. Its display name
    # also gives the preferred human-readable label for other providers' IDs.
    for slug, (country_codes, region_kind) in REGION_GEOGRAPHY.items():
        if region_kind != "country" or len(country_codes) != 1:
            continue
        country_code = _admin_region_token(country_codes[0])
        display = str(MAPRANDO_REGION_DISPLAY_NAMES.get(slug) or "").strip()
        if not country_code or not display:
            continue
        identity = identities_by_country.setdefault(
            country_code, _admin_region_token(display),
        )
        displays_by_identity.setdefault(identity, display)

    aliases: dict[str, str] = {}

    # Add reviewed MapRando country slugs and their English labels.
    for slug, (country_codes, region_kind) in REGION_GEOGRAPHY.items():
        if region_kind != "country" or len(country_codes) != 1:
            continue
        country_code = _admin_region_token(country_codes[0])
        identity = identities_by_country.get(country_code)
        if not identity:
            continue
        display = str(MAPRANDO_REGION_DISPLAY_NAMES.get(slug) or "").strip()
        for alias in (slug, display, country_code):
            token = _admin_region_token(alias)
            if token:
                aliases.setdefault(token, identity)

    # Add ISO-3 aliases (BEL, CHE, CZE, …) and only the short country aliases
    # from the world-map table. Do not import its region-to-country aliases.
    for alias, map_country in WORLD_MAP_COUNTRY_ALIASES.items():
        token = _admin_region_token(alias)
        if len(token) not in {2, 3}:
            continue
        identity = identities_by_country.get(_admin_region_token(map_country))
        if identity:
            aliases.setdefault(token, identity)

    for token, identity in aliases.items():
        _ADMIN_REGION_IDENTITY_ALIASES.setdefault(token, identity)
        display = displays_by_identity.get(identity)
        if display:
            _ADMIN_REGION_DISPLAY_NAMES.setdefault(token, display)
    return aliases, displays_by_identity


_ADMIN_COUNTRY_IDENTITY_ALIASES, _ADMIN_COUNTRY_DISPLAY_NAMES = _admin_country_alias_data()


def _admin_region_identity(
    canonical_region_id: Any, country: Any = None, region: Any = None,
) -> str:
    """Return one cross-provider admin geography key from existing metadata."""
    canonical_token = _admin_region_token(canonical_region_id)
    if canonical_token:
        return _ADMIN_REGION_IDENTITY_ALIASES.get(
            canonical_token, canonical_token,
        )
    # A country is a fallback, not a region identity: Azores and Madeira
    # must never collapse into whichever Portuguese region appears first.
    region_token = _admin_region_token(region)
    if region_token:
        return _ADMIN_REGION_IDENTITY_ALIASES.get(region_token, region_token)
    country_identity = _admin_region_token(_admin_map_display_name(country)) if country else ""
    if country_identity and country_identity != "UNKNOWN":
        return _ADMIN_REGION_IDENTITY_ALIASES.get(
            country_identity, country_identity,
        )
    region_identity = _admin_region_token(region)
    return _ADMIN_REGION_IDENTITY_ALIASES.get(
        region_identity, region_identity or "UNKNOWN",
    )


def _admin_map_display_name(*values: Any) -> str:
    """Return one human-readable admin label without changing stored IDs."""
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        candidate = re.sub(r"^(?:OpenTopoMap|Freizeitkarte)\s+", "", raw, flags=re.IGNORECASE).strip()
        key = re.sub(r"[^A-Za-z0-9]+", "", candidate).upper()
        if key in _ADMIN_REGION_DISPLAY_NAMES:
            return _ADMIN_REGION_DISPLAY_NAMES[key]
        if key in _ADMIN_PROVIDER_REGION_DISPLAY_NAMES:
            return _ADMIN_PROVIDER_REGION_DISPLAY_NAMES[key]
        display_candidate = re.sub(r"_+", " ", candidate)
        display_candidate = " ".join(display_candidate.split())
        display_candidate = re.sub(
            r"^(?:Federal\s+)?Republic\s+of\s+|^(?:Kingdom|Principality|State)\s+of\s+|^Grand\s+Duchy\s+of\s+|^Region\s+",
            "",
            display_candidate,
            flags=re.IGNORECASE,
        ).strip()
        display_candidate = re.sub(r"\s+-\s+", " – ", display_candidate)
        if candidate.isupper() or re.fullmatch(r"[A-Z][A-Z0-9_-]+", candidate):
            return display_candidate.title()
        return display_candidate or "—"
    return "—"


def _admin_region_display_name(
    canonical_region_id: Any = None,
    country: Any = None,
    region: Any = None,
    map_package_name: Any = None,
) -> str:
    """Return a readable region label, adding a known parent country."""
    region_name = _admin_map_display_name(
        map_package_name, region, canonical_region_id, country,
    )
    if region_name == "—":
        return "—"

    parent_token = ""
    for value in (country, canonical_region_id, region):
        token = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
        if token in _ADMIN_REGION_PARENT_COUNTRIES:
            parent_token = _ADMIN_REGION_PARENT_COUNTRIES[token]
            break
    country_name = _admin_map_display_name(parent_token or country)
    if country_name == "—" or region_name.casefold() == country_name.casefold():
        return region_name

    region_identity = _admin_region_identity(canonical_region_id, country, region)
    country_identity = _admin_region_identity(None, parent_token or country, None)
    if region_identity == country_identity:
        return region_name
    return f"{region_name} – {country_name}"


def _overview_map_event_context(event: dict[str, Any]) -> str:
    if event.get("provider_id") == "custom":
        return "Custom .img"
    display_name = _admin_map_display_name(
        event.get("display_name")
        or event.get("map_package_name")
        or event.get("map_package_id")
        or event.get("region")
        or "Map",
    )
    region = (
        _admin_region_display_name(
            event.get("canonical_region_id"),
            event.get("region_country"),
            event.get("region"),
            event.get("map_package_name"),
        )
        if event.get("region") or event.get("map_package_name")
        else ""
    )
    provider = str(event.get("provider_name") or "").strip()
    parts = [region] if region and display_name.casefold() in region.casefold() else [display_name]
    if region and parts[0] != region and region.casefold() != display_name.casefold():
        parts.append(region)
    if provider:
        parts.append(provider)
    return " · ".join(parts)


def _overview_activity_device(event: dict[str, Any]) -> str:
    model = str(event.get("model") or event.get("compatibility_identity") or "").strip()
    if not model:
        return ""
    variant = _normalise_variant(event.get("variant")) if event.get("variant") else ""
    label = model if not variant or variant in model else f"{model} · {variant}"
    device_id = str(event.get("canonical_device_model_id") or "").strip()
    if device_id:
        href = _device_detail_url(device_id, origin="overview")
        return (
            f"<a class='overview-activity-device' href='{html.escape(href, quote=True)}'>"
            f"{html.escape(label)}</a>"
        )
    return f"<span class='overview-activity-device'>{html.escape(label)}</span>"


def _overview_map_event_href(event: dict[str, Any]) -> str:
    if event.get("provider_id") == "custom":
        return "/admin/installations"
    parameters = {
        "eventType": str(event.get("event_type") or ""),
        "provider": str(event.get("provider_id") or ""),
        "map": str(event.get("map_package_id") or ""),
        "region": str(event.get("region") or ""),
        "eventId": str(event.get("event_id") or event.get("eventId") or ""),
    }
    return "/admin/map-statistics?" + urlencode({key: value for key, value in parameters.items() if value})


def _download_history_icon(event_type: str) -> str:
    """Original Font Awesome Free 7.3.1 assets; historical phases stay static."""
    icons = {
        'DOWNLOAD_STARTED': '<svg class="download-phase-icon fa-solid fa-hourglass-start" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M32 0C14.3 0 0 14.3 0 32S14.3 64 32 64l0 11c0 42.4 16.9 83.1 46.9 113.1l67.9 67.9-67.9 67.9C48.9 353.9 32 394.6 32 437l0 11c-17.7 0-32 14.3-32 32s14.3 32 32 32l320 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l0-11c0-42.4-16.9-83.1-46.9-113.1l-67.9-67.9 67.9-67.9c30-30 46.9-70.7 46.9-113.1l0-11c17.7 0 32-14.3 32-32S369.7 0 352 0L32 0zM288 437l0 11-192 0 0-11c0-25.5 10.1-49.9 28.1-67.9l67.9-67.9 67.9 67.9c18 18 28.1 42.4 28.1 67.9z"/></svg>',
        'DOWNLOAD_PROCESSING': '<svg class="download-phase-icon fa-solid fa-spinner" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M208 48a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zm0 416a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zM48 208a48 48 0 1 1 0 96 48 48 0 1 1 0-96zm368 48a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zM75 369.1A48 48 0 1 1 142.9 437 48 48 0 1 1 75 369.1zM75 75A48 48 0 1 1 142.9 142.9 48 48 0 1 1 75 75zM437 369.1A48 48 0 1 1 369.1 437 48 48 0 1 1 437 369.1z"/></svg>',
        'DOWNLOAD_SUCCEEDED': '<svg class="download-phase-icon fa-solid fa-hourglass-end" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M32 0C14.3 0 0 14.3 0 32S14.3 64 32 64l0 11c0 42.4 16.9 83.1 46.9 113.1l67.9 67.9-67.9 67.9C48.9 353.9 32 394.6 32 437l0 11c-17.7 0-32 14.3-32 32s14.3 32 32 32l320 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l0-11c0-42.4-16.9-83.1-46.9-113.1l-67.9-67.9 67.9-67.9c30-30 46.9-70.7 46.9-113.1l0-11c17.7 0 32-14.3 32-32S369.7 0 352 0L32 0zM96 75l0-11 192 0 0 11c0 25.5-10.1 49.9-28.1 67.9l-67.9 67.9-67.9-67.9C106.1 124.9 96 100.4 96 75z"/></svg>',
    }
    extra_icons = {'circle-xmark': '<svg class="download-phase-icon fa-solid fa-circle-xmark" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM167 167c9.4-9.4 24.6-9.4 33.9 0l55 55 55-55c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9l-55 55 55 55c9.4 9.4 9.4 24.6 0 33.9s-24.6 9.4-33.9 0l-55-55-55 55c-9.4 9.4-24.6 9.4-33.9 0s-9.4-24.6 0-33.9l55-55-55-55c-9.4-9.4-9.4-24.6 0-33.9z"/></svg>', 'ban': '<svg class="download-phase-icon fa-solid fa-ban" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M367.2 412.5L99.5 144.8c-22.4 31.4-35.5 69.8-35.5 111.2 0 106 86 192 192 192 41.5 0 79.9-13.1 111.2-35.5zm45.3-45.3c22.4-31.4 35.5-69.8 35.5-111.2 0-106-86-192-192-192-41.5 0-79.9 13.1-111.2 35.5L412.5 367.2zM0 256a256 256 0 1 1 512 0 256 256 0 1 1 -512 0z"/></svg>', 'triangle-exclamation': '<svg class="download-phase-icon fa-solid fa-triangle-exclamation" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 0c14.7 0 28.2 8.1 35.2 21l216 400c6.7 12.4 6.4 27.4-.8 39.5S486.1 480 472 480L40 480c-14.1 0-27.2-7.4-34.4-19.5s-7.5-27.1-.8-39.5l216-400c7-12.9 20.5-21 35.2-21zm0 352a32 32 0 1 0 0 64 32 32 0 1 0 0-64zm0-192c-18.2 0-32.7 15.5-31.4 33.7l7.4 104c.9 12.5 11.4 22.3 23.9 22.3 12.6 0 23-9.7 23.9-22.3l7.4-104c1.3-18.2-13.1-33.7-31.4-33.7z"/></svg>', 'circle-check': '<svg class="download-phase-icon fa-solid fa-circle-check" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 512a256 256 0 1 1 0-512 256 256 0 1 1 0 512zM374 145.7c-10.7-7.8-25.7-5.4-33.5 5.3L221.1 315.2 169 263.1c-9.4-9.4-24.6-9.4-33.9 0s-9.4 24.6 0 33.9l72 72c5 5 11.8 7.5 18.8 7s13.4-4.1 17.5-9.8L379.3 179.2c7.8-10.7 5.4-25.7-5.3-33.5z"/></svg>', 'circle-info': '<svg class="download-phase-icon fa-solid fa-circle-info" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM224 160a32 32 0 1 1 64 0 32 32 0 1 1 -64 0zm-8 64l48 0c13.3 0 24 10.7 24 24l0 88 8 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-80 0c-13.3 0-24-10.7-24-24s10.7-24 24-24l24 0 0-64-24 0c-13.3 0-24-10.7-24-24s10.7-24 24-24z"/></svg>'}
    if event_type in {"MAP_UPDATE_SUCCEEDED", "MAP_UPDATE_FAILED"}:
        return '<svg class="download-phase-icon fa-solid fa-arrows-rotate" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path fill="currentColor" d="M105 203c8 8 21 8 29 0l51-51 51 51c8 8 8 21 0 29s-21 8-29 0l-15-15v59c0 35 29 64 64 64 18 0 35-8 47-20 9-9 23-9 32-1s9 23 1 32c-21 22-49 36-80 36-62 0-112-50-112-112v-59l-51 51c-8 8-21 8-29 0s-8-21 0-29l40-40zm302 106c-8-8-21-8-29 0l-51 51-51-51c-8-8-8-21 0-29s21-8 29 0l15 15v-59c0-35-29-64-64-64-18 0-35 8-47 20-9 9-23 9-32 1s-9-23-1-32c21-22 49-36 80-36 62 0 112 50 112 112v59l51-51c8-8 21-8 29 0s8 21 0 29l-40 40z"/></svg>'
    names = {"DOWNLOAD_FAILED": "circle-xmark", "DOWNLOAD_CANCELLED": "ban", "DOWNLOAD_INTERRUPTED": "triangle-exclamation", "INSTALL_SUCCEEDED": "circle-check", "INSTALL_FAILED": "circle-xmark"}
    return icons.get(event_type) or extra_icons[names.get(event_type, "circle-info")]


def _overview_map_activity_row(event: dict[str, Any]) -> str:
    label, state = _overview_map_event_label(event)
    event_type = str(event.get("event_type") or "")
    tone = _MAP_ACTIVITY_STATES.get(event_type.upper(), ("Map activity", "unknown", "neutral"))[2]
    if state == "stale":
        tone = "neutral"
    status_markup = _download_history_icon(event_type) + html.escape(label)
    component = {"main": "Main map", "contours": "Contours"}.get(event.get("component_kind"), "")
    context = html.escape(_overview_map_event_context(event)) + (' · ' + component if component else '')
    device = _overview_activity_device(event)
    lifecycle = event.get("lifecycle") or []
    if len(lifecycle) > 1:
        started = next((_parse_timestamp(item.get("at")) for item in lifecycle
                        if item.get("type") == "DOWNLOAD_STARTED"), None)
        finished = next((_parse_timestamp(item.get("at")) for item in lifecycle
                         if item.get("type") in {"DOWNLOAD_SUCCEEDED", "DOWNLOAD_FAILED",
                                                 "DOWNLOAD_CANCELLED", "DOWNLOAD_INTERRUPTED"}), None)
        entries = []
        for item in lifecycle:
            phase = str(item.get("type") or "")
            timing = _timestamp_markup(item.get("at"))
            if phase == "DOWNLOAD_PROCESSING" and started is not None and finished is not None and finished >= started:
                seconds = int((finished - started).total_seconds())
                hours, remainder = divmod(seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration = " ".join(part for part in (
                    f"{hours}h" if hours else "", f"{minutes}m" if minutes else "",
                    f"{seconds}s" if seconds or not (hours or minutes) else "") if part)
                timing = (f"<span class='download-elapsed' title='Total time from download start to finish'>"
                          f"{duration}</span>")
            elif phase == "DOWNLOAD_PROCESSING":
                timing = "<span title='Start or finish time unavailable'>—</span>"
            entries.append("<li>" + _download_history_icon(phase)
                           + html.escape(phase.removeprefix("DOWNLOAD_").replace("_", " ").title())
                           + " · " + timing + "</li>")
        return (
            f"<li class='overview-activity-item overview-activity-{state} map-activity-row map-activity-{tone}'>"
            "<details class='download-history'><summary>"
            f"<span class='overview-activity-label'>{status_markup}</span>"
            f"{_timestamp_markup(event.get('occurred_at'))}"
            f"<span class='download-context'>{context}</span>"
            f"{device}"
            "</summary><ol class='download-timeline' aria-label='Download start, total duration and finish'>"
            + "".join(entries) + "</ol></details></li>"
        )
    return (
        f"<li class='overview-activity-item overview-activity-{state} map-activity-row map-activity-{tone}'>"
        f"<span class='map-activity-copy'><span class='overview-activity-label'>{status_markup}</span>"
        f"<span>{context}</span></span>{device}"
        f"{_timestamp_markup(event.get('occurred_at'))}</li>"
    )


def _admin_app_version_label(value: Any, build: Any = None) -> str:
    release = str(value or "—").strip() or "—"
    if release != "—":
        match = re.search(r"\b(beta\.\d+)(?:\s*[-·( ]\s*(RC))?\b", release, re.IGNORECASE)
        if match:
            release = match.group(1).lower() + (" RC" if match.group(2) else "")
    if build is not None and str(build).strip():
        release += f" · build {str(build).strip()}"
    return release


def _overview_chart_bucket_label(
    value: Any, bucket: str, time_zone: str = "UTC",
) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return str(value or "—")
    try:
        parsed = parsed.astimezone(ZoneInfo(time_zone))
    except (ZoneInfoNotFoundError, ValueError):
        parsed = parsed.astimezone(timezone.utc)
    if bucket == "hour":
        return parsed.strftime("%H:00")
    if bucket == "month":
        return parsed.strftime("%b %Y")
    if bucket == "week":
        return "Week of " + parsed.strftime("%d %b")
    return parsed.strftime("%d %b")


def _overview_trend_chart(
    trend: list[dict[str, Any]], bucket: str, time_zone: str = "UTC",
    *, metric: str = "installs", has_activity: bool = False,
    _compact: bool = False,
) -> str:
    if not trend:
        if has_activity:
            return "<p class='overview-empty-state'>Trend data is unavailable for this period.</p>"
        empty_label = "downloads" if metric == "downloads" else "map installations"
        return f"<p class='overview-empty-state'>No {empty_label} in this period.</p>"
    if metric == "downloads":
        series = (
            ("download-success", "Download succeeded", "download_success_count"),
            ("download-failed", "Download failed", "download_failed_count"),
        )
        chart_label = "Map download trend"
    else:
        series = (
            ("success", "Install succeeded", "success_count"),
            ("failed", "Install failed", "failed_count"),
            ("update", "Map update", "map_update_count"),
        )
        chart_label = "Map installation trend"
    values = []
    for item in trend:
        counts = []
        for name, _, field in series:
            value = max(0, int(item.get(field) or 0))
            if name == "success":
                value += max(0, int(item.get("custom_count") or 0))
            counts.append(value)
        values.append(tuple(counts))
    maximum = max((max(counts, default=0) for counts in values), default=1) or 1
    tick_step = max(1, math.ceil(maximum / 4))
    scale_maximum = tick_step * 4
    chart_width, chart_height = (360, 220) if _compact else (720, 260)
    left, top, bottom = 38, 20, 34
    plot_height = chart_height - top - bottom
    plot_width = chart_width - left - 12
    grid = []
    for amount in range(0, scale_maximum + 1, tick_step):
        tick_y = top + plot_height * (1 - amount / scale_maximum)
        grid.append(f"<line class='overview-chart-grid' x1='{left}' x2='{chart_width-12}' y1='{tick_y:.1f}' y2='{tick_y:.1f}'/><text class='overview-chart-axis-label' x='{left-8}' y='{tick_y+4:.1f}' text-anchor='end'>{amount}</text>")
    lines: list[str] = []
    labels: list[str] = []
    x_positions = [
        left + (plot_width / 2 if len(values) == 1 else index * plot_width / (len(values) - 1))
        for index in range(len(values))
    ]
    for series_index, (name, label, field) in enumerate(series):
        points = []
        dots = []
        for index, (counts, item) in enumerate(zip(values, trend)):
            count = counts[series_index]
            x = x_positions[index]
            y = top + plot_height * (1 - count / scale_maximum)
            points.append(f"{x:.1f},{y:.1f}")
            timestamps = list(item.get(f'{field.removesuffix("_count")}_times') or [])
            if name == "success":
                timestamps += list(item.get("custom_times") or [])
            title = f"{label}: {count} · {_overview_chart_bucket_label(item.get('bucket'), bucket, time_zone)} · {time_zone}"
            if timestamps:
                title = f"{label}: {count} · " + ", ".join(str(value) for value in timestamps) + f" · {time_zone}"
            dots.append(
                f"<circle class='overview-chart-{name}' cx='{x:.1f}' cy='{y:.1f}' r='4' tabindex='0' role='img' aria-label='{html.escape(title, quote=True)}'><title>{html.escape(title)}</title></circle>"
            )
        lines.append(
            f"<polyline class='overview-chart-line overview-chart-{name}' points='{' '.join(points)}'></polyline>{''.join(dots)}"
        )
    for index, item in enumerate(trend):
        label_step = max(1, round((len(values) - 1) / (11 if bucket == "hour" else 5)))
        show_label = len(values) <= 12 or index % label_step == 0 or index == len(values) - 1
        if _compact:
            show_label = index in {0, (len(values) - 1) // 2, len(values) - 1}
        if show_label:
            anchor = 'start' if index == 0 else 'end' if index == len(values) - 1 else 'middle'
            labels.append(f"<text x='{x_positions[index]:.1f}' y='{chart_height - 8}' text-anchor='{anchor}'>{html.escape(_overview_chart_bucket_label(item.get('bucket'), bucket, time_zone))}</text>")
    svg = (
        f"<svg class='overview-trend-chart overview-trend-{'mobile' if _compact else 'desktop'}' viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='{chart_label}'>"
        f"{''.join(grid)}{''.join(lines)}{''.join(labels)}</svg>"
    )
    if _compact:
        return svg
    return (
        "<div class='overview-chart-wrap'>"
        + svg
        + _overview_trend_chart(
            trend, bucket, time_zone, metric=metric,
            has_activity=has_activity, _compact=True,
        )
        + (
            "<div class='overview-chart-legend'><span><i class='overview-chart-download-success'></i>Successful</span><span><i class='overview-chart-download-failed'></i>Failed</span></div></div>"
            if metric == "downloads"
            else "<div class='overview-chart-legend'><span><i class='overview-chart-success'></i>Successful</span><span><i class='overview-chart-failed'></i>Failed</span><span><i class='overview-chart-update'></i>Map update</span></div></div>"
        )
    )


def _overview_downloads_chart(
    downloads: dict[str, Any], time_zone: str = "UTC", *, period: str = "24h",
    _compact: bool = False,
) -> str:
    trend = [item for item in downloads.get("trend") or [] if isinstance(item, dict)]
    if not trend:
        return "<p class='overview-empty-state'>No GitHub download data yet.</p>"
    chart_bucket = str(downloads.get("bucket") or {
        "24h": "hour", "7d": "day", "30d": "day", "all": "month",
    }.get(period, "hour"))
    if chart_bucket not in {"hour", "day", "week", "month"}:
        chart_bucket = "hour"
    period_label = {
        "24h": "the last 24 hours",
        "7d": "the last 7 days",
        "30d": "the last 30 days",
        "all": "all time",
    }.get(period, "the selected period")
    values = []
    for item in trend:
        counts = []
        for key in ("dmg_count", "zip_count"):
            value = item.get(key)
            try:
                counts.append(int(value) if value is not None and int(value) >= 0 else None)
            except (TypeError, ValueError):
                counts.append(None)
        values.append(tuple(counts))
    maximum = max((sum(value for value in series if value is not None) for series in values), default=1) or 1
    scale_maximum = max(4, math.ceil(maximum * 1.2))
    chart_width, chart_height = (360, 220) if _compact else (720, 260)
    left, top, bottom = 38, 20, 34
    plot_height = chart_height - top - bottom
    slot = (chart_width - left - 12) / max(len(values), 1)
    tick_step = max(1, (scale_maximum + 3) // 4)
    grid = []
    for amount in sorted(set(range(0, scale_maximum + 1, tick_step)) | {scale_maximum}):
        tick_y = top + plot_height * (1 - amount / scale_maximum)
        grid.append(
            f"<line class='overview-chart-grid' x1='{left}' x2='{chart_width-12}' "
            f"y1='{tick_y:.1f}' y2='{tick_y:.1f}'/>"
            f"<text class='overview-chart-axis-label' x='{left-8}' y='{tick_y+4:.1f}' "
            f"text-anchor='end'>{amount}</text>"
        )
    bars: list[str] = []
    labels: list[str] = []
    plot_width = chart_width - left - 12
    position_times = [
        _parse_timestamp(item.get("observed_at") or item.get("bucket"))
        for item in trend
    ]
    valid_position_times = [value for value in position_times if value is not None]
    position_start = min(valid_position_times) if valid_position_times else None
    position_end = max(valid_position_times) if valid_position_times else None
    position_span = (
        position_end - position_start
        if position_start is not None and position_end is not None
        else None
    )
    edge_inset = min(slot / 2, plot_width / 2)
    timeline_width = max(0.0, plot_width - edge_inset * 2)

    def position_center(index: int) -> float:
        """Use ordered hourly slots; exact observation time stays metadata."""
        if chart_bucket == "hour":
            return left + (index + 0.5) * slot
        observed_at = position_times[index]
        if position_start is None or position_span is None or observed_at is None:
            return left + (index + 0.5) * slot
        if position_span.total_seconds() <= 0:
            return left + plot_width / 2
        fraction = (observed_at - position_start).total_seconds() / position_span.total_seconds()
        return left + edge_inset + max(0.0, min(1.0, fraction)) * timeline_width

    series = (
        (".dmg downloads", "overview-chart-download-dmg"),
        (".zip downloads", "overview-chart-download-zip"),
    )
    for index, (counts, item) in enumerate(zip(values, trend)):
        center = position_center(index)
        bar_width = min(44, slot * 0.58)
        x = center - bar_width / 2
        y = top + plot_height
        clip_id = f"overview-download-bar-clip-{'mobile-' if _compact else ''}{index}"
        observed_at = item.get("observed_at") or item.get("bucket")
        legacy_note = (
            " · legacy observed counter delta · population comparability unconfirmed"
            if item.get("legacy")
            or item.get("confidence") == "legacy"
            or item.get("population_comparability") == "unconfirmed"
            else ""
        )
        partial_note = " · partial known total" if item.get("partial") else ""
        zero_titles = []
        for (label, _), count in zip(series, counts):
            if count != 0:
                continue
            zero_description = (
                "known zero increase in partial bucket ending"
                if item.get("partial")
                else "observed zero increase between checks ending"
            )
            zero_title = f"{label}: 0 · {zero_description} {_overview_chart_bucket_label(observed_at, chart_bucket, time_zone)} · {time_zone}"
            zero_titles.append(zero_title + legacy_note + partial_note)
        group_accessibility = ""
        group_title = ""
        if zero_titles:
            interval_title = "Download interval: " + " · ".join(zero_titles)
            group_accessibility = (
                " role='group' aria-label='"
                + html.escape(interval_title, quote=True)
                + "'"
            )
            group_title = f"<title>{html.escape(interval_title)}</title>"
        bars.append(
            f"<defs><clipPath id='{clip_id}'><rect x='{x:.1f}' "
            f"y='{top:.1f}' width='{bar_width:.1f}' height='{plot_height:.1f}' rx='3'></rect></clipPath></defs>"
            f"<g clip-path='url(#{clip_id})'{group_accessibility}>{group_title}"
        )
        for (label, css_class), count in zip(series, counts):
            if count is None:
                continue
            if count == 0:
                continue
            height = plot_height * count / scale_maximum
            y -= height
            previous_observed_at = item.get("previous_observed_at")
            if item.get("state") in {"gap", "period_boundary", "partial"} and previous_observed_at is not None:
                interval_start = _overview_chart_bucket_label(previous_observed_at, chart_bucket, time_zone)
                interval_end = _overview_chart_bucket_label(observed_at, chart_bucket, time_zone)
                title = f"{label}: {count} · observed increase across {interval_start}–{interval_end} · {time_zone} · interval uncertain"
            else:
                title = f"{label}: {count} · observed increase ending {_overview_chart_bucket_label(observed_at, chart_bucket, time_zone)} · {time_zone}"
            title += legacy_note + partial_note
            bars.append(
                f"<rect class='{css_class}' x='{x:.1f}' y='{y:.2f}' width='{bar_width:.1f}' "
                f"height='{height:.2f}' tabindex='0' role='img' "
                f"aria-label='{html.escape(title, quote=True)}'>"
                f"<title>{html.escape(title)}</title></rect>"
            )
        bars.append("</g>")
        if item.get("contains_discontinuity") or (
            not any(count is not None for count in counts)
            and item.get("state") == "discontinuity"
        ):
            discontinuity_title = f"Download counters discontinuity ending {_overview_chart_bucket_label(item.get('observed_at') or item.get('bucket'), chart_bucket, time_zone)} · interval unknown"
            if item.get("discontinuity_count"):
                discontinuity_title += f" · {item['discontinuity_count']} unknown interval retained"
            bars.append(
                f"<g class='overview-chart-download-unknown' tabindex='0' role='img' aria-label='{html.escape(discontinuity_title, quote=True)}'><line x1='{center:.1f}' x2='{center:.1f}' y1='{top + 14:.1f}' y2='{top + plot_height - 4:.1f}'></line><text x='{center:.1f}' y='{top + 12:.1f}' text-anchor='middle'>Unknown</text><title>{html.escape(discontinuity_title)}</title></g>"
            )
        label_step = max(1, round((len(values) - 1) / 11))
        show_label = len(values) <= 12 or index % label_step == 0 or index == len(values) - 1
        if _compact:
            show_label = index in {0, (len(values) - 1) // 2, len(values) - 1}
        if show_label:
            anchor = (
                'start' if _compact and index == 0
                else 'end' if _compact and index == len(values) - 1
                else 'middle'
            )
            labels.append(
                f"<text x='{center:.1f}' y='{chart_height - 8}' text-anchor='{anchor}'>"
                f"{html.escape(_overview_chart_bucket_label(item.get('bucket'), chart_bucket, time_zone))}</text>"
            )
    svg = (
        f"<svg class='overview-trend-chart overview-trend-{'mobile' if _compact else 'desktop'}' "
        f"viewBox='0 0 {chart_width} {chart_height}' role='img' "
        f"aria-label='Observed download increases between checks over {period_label}'>"
        f"{''.join(grid)}{''.join(bars)}{''.join(labels)}</svg>"
    )
    if _compact:
        return svg
    return (
        "<div class='overview-chart-wrap'>"
        + svg
        + _overview_downloads_chart(downloads, time_zone, period=period, _compact=True)
        + "<div class='overview-chart-legend'>"
        "<span><i class='overview-chart-download-dmg'></i>.dmg</span>"
        "<span><i class='overview-chart-download-zip'></i>.zip</span>"
        "</div></div>"
    )


def _overview_period_script() -> str:
    return r"""(() => {
      let loadingKey = '';
      let overviewRequest = 0;
      const activeTimeZone = () => window.TerentoAdminTime?.timeZone?.()
        || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      const bind = () => {
        const form = document.querySelector('#overview-period-form');
        const select = document.querySelector('#overview-period');
        if (!form || !select || select.dataset.bound === 'true') return;
        select.dataset.bound = 'true';
        form.addEventListener('submit', (event) => {
          event.preventDefault();
          load(select.value, true, activeTimeZone());
        });
        select.addEventListener('change', () => form.requestSubmit());
      };
      const load = async (period, push, timeZone = activeTimeZone()) => {
        const current = document.querySelector('#main-content');
        const select = document.querySelector('#overview-period');
        const url = new URL('/admin', window.location.origin);
        url.searchParams.set('period', period);
        url.searchParams.set('timeZone', timeZone);
        const requestKey = `${period}\u0000${timeZone}`;
        if (loadingKey === requestKey) return;
        loadingKey = requestKey;
        const requestNumber = ++overviewRequest;
        if (current) current.setAttribute('aria-busy', 'true');
        if (select) select.disabled = true;
        try {
          const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'text/html'}});
          if (!response.ok) throw new Error(`Overview refresh failed (${response.status})`);
          const documentNext = new DOMParser().parseFromString(await response.text(), 'text/html');
          if (requestNumber !== overviewRequest) return;
          const mainNext = documentNext.querySelector('#main-content');
          if (!mainNext) throw new Error('Overview content is unavailable.');
          current?.replaceWith(mainNext);
          window.dispatchEvent(new Event('terento-admin-content-changed'));
          if (push) window.history.pushState({period, timeZone}, '', url);
          else window.history.replaceState({period, timeZone}, '', url);
          window.TerentoAdminTime?.render();
          bind();
        } catch (error) {
          window.location.assign(url);
        } finally {
          if (requestNumber === overviewRequest) loadingKey = '';
        }
      };
      window.addEventListener('popstate', () => {
        const period = new URL(window.location.href).searchParams.get('period') || '24h';
        load(period, false, activeTimeZone());
      });
      const synchronizeTimeZone = () => {
        const url = new URL(window.location.href);
        const period = url.searchParams.get('period') || document.querySelector('#overview-period')?.value || '24h';
        const timeZone = activeTimeZone();
        if (url.searchParams.get('timeZone') !== timeZone) load(period, false, timeZone);
      };
      window.addEventListener('terento-admin-timezone-ready', synchronizeTimeZone);
      window.addEventListener('terento-admin-timezone-change', synchronizeTimeZone);
      bind();
    })();"""


def overview_page(
    overview: dict[str, Any], user: dict[str, Any], csrf_token: str,
    *, review_action: str = "", review_event_id: str = "",
) -> bytes:
    data = overview.get("data") if isinstance(overview.get("data"), dict) else {}
    compatibility = overview.get("compatibility") if isinstance(overview.get("compatibility"), dict) else {}
    downloads = overview.get("downloads") if isinstance(overview.get("downloads"), dict) else {}
    providers = list(overview.get("providers") or [])
    period = str(overview.get("period") or "24h")
    time_zone = str(overview.get("timeZone") or "UTC")
    period_labels = {"24h": "Last 24 hours", "7d": "Last 7 days", "30d": "Last 30 days", "all": "All time"}
    period_options = "".join(
        f"<option value='{value}'{' selected' if value == period else ''}>{label}</option>"
        for value, label in period_labels.items()
    )
    recent = [
        item for item in data.get("recentActivity") or []
        if str(item.get("event_type") or "").upper()
        not in {"DOWNLOAD_STARTED", "DOWNLOAD_PROCESSING"}
    ]
    attention_providers = [
        provider for provider in providers
        if str(provider.get("health") or "UNKNOWN").upper() not in {"HEALTHY", ""}
    ]
    review = user.get("admin_review_summary") or {}
    if review.get("available") is False:
        review = {}
    attention_item_markup: list[str] = []
    category_rows = (
        ("installationIssues", "Installation problems", "/admin/installations?state=open", compatibility.get("allTimeOpenErrorCount")),
        ("githubIssuesInProgress", "GitHub issues", "/admin/review/github-issues", 0),
        ("identityPending", "Device identity", "/admin/installations?state=identity-pending", compatibility.get("allTimeIdentityPendingCount")),
        ("readyToPublish", "Publication review", "/admin/devices?review=publication", len(compatibility.get("reviewRequired") or [])),
    )
    for key, label, href, fallback in category_rows:
        try:
            count = max(0, int(review.get(key) if review.get(key) is not None else fallback or 0))
        except (TypeError, ValueError):
            count = 0
        if count:
            attention_item_markup.append(
                "<li class='overview-attention-item overview-attention-review'>"
                "<span class='overview-attention-dot' aria-hidden='true'>●</span>"
                f"<div><strong>{html.escape(label)} · {count}</strong></div>"
                f"<a class='overview-detail-link' href='{html.escape(href, quote=True)}'>Inspect&nbsp;{_admin_icon('arrow-right')}</a></li>"
            )
    attention_item_markup.extend(
        _overview_missing_diagnostic_item(item, csrf_token)
        for item in data.get("missingDiagnosticFailures") or []
    )
    attention_item_markup.extend(_overview_provider_attention_item(provider) for provider in attention_providers)
    if isinstance(overview.get("system"), dict):
        health_cards, _, _ = _system_health_cards(overview["system"])
        attention_item_markup.extend(
            _overview_system_attention_item(card)
            for card in health_cards
            if card["status"] != "HEALTHY"
        )
    attention_items = "".join(attention_item_markup)
    has_review_queue = bool(attention_item_markup)
    if not attention_items:
        attention_content = ""
    else:
        attention_content = f"<ul class='overview-attention-list'>{attention_items}</ul>"
    recent_content = (
        "<p class='empty'>No map activity in this period.</p>"
        if not recent else
        "<ul class='overview-activity-list'>" + "".join(_overview_map_activity_row(item) for item in recent) + "</ul>"
    )
    map_statistics_href = "/admin/map-statistics"
    map_statistics_href += "?" + urlencode({"period": period})
    download_has_data = bool(downloads.get("hasData")) and (downloads.get("dmgTotal") is not None or downloads.get("zipTotal") is not None or bool(downloads.get("trend")))
    download_last_update = downloads.get("lastSuccessfulObservedAt", downloads.get("lastObservedAt"))
    download_update_note = (
        f"Last successful data update: {_timestamp_markup(download_last_update)}."
        if download_has_data and download_last_update is not None
        else "Last successful data update: —."
    )

    def download_total(key: str) -> str:
        if downloads.get(key) is None:
            return "—"
        try:
            return str(max(0, int(downloads[key])))
        except (TypeError, ValueError):
            return "—"

    def map_total(key: str) -> str:
        if key not in data or data.get(key) is None:
            return "—"
        try:
            return str(max(0, int(data[key])))
        except (TypeError, ValueError):
            return "—"

    period_statistics_href = html.escape(f"/admin/map-statistics?period={period}", quote=True)
    all_statistics_href = html.escape("/admin/map-statistics?period=all", quote=True)
    map_totals = (
        "<div class='overview-map-totals' aria-label='All-time installation totals'>"
        f"<a class='overview-map-total' href='{all_statistics_href}' title='All time' aria-label='Successful, all time: {map_total('allTimeSuccessCount')}'><strong>{map_total('allTimeSuccessCount')}</strong><small>Successful</small></a>"
        f"<a class='overview-map-total' href='{all_statistics_href}' title='All time' aria-label='Failed, all time: {map_total('allTimeFailedCount')}'>{_admin_error_counter(data.get('allTimeFailedCount'), available='allTimeFailedCount')}<small>Failed</small></a>"
        f"<a class='overview-map-total' href='{all_statistics_href}' title='All time' aria-label='Success rate, all time: {_format_rate(data.get('allTimeInstallSuccessRate'))}'><strong>{_format_rate(data.get('allTimeInstallSuccessRate'))}</strong><small>Success rate</small></a>"
        "</div>"
    )
    download_totals = (
        "<div class='overview-map-totals' aria-label='All-time download totals'>"
        f"<a class='overview-map-total' href='{all_statistics_href}' title='All time' aria-label='Successful, all time: {map_total('allTimeCompletedDownloadCount')}'><strong>{map_total('allTimeCompletedDownloadCount')}</strong><small>Successful</small></a>"
        f"<a class='overview-map-total' href='{all_statistics_href}' title='All time' aria-label='Failed, all time: {map_total('allTimeFailedDownloadCount')}'>{_admin_error_counter(data.get('allTimeFailedDownloadCount'), available='allTimeFailedDownloadCount')}<small>Failed</small></a>"
        f"<a class='overview-map-total' href='{all_statistics_href}' title='All time' aria-label='Success rate, all time: {_format_rate(data.get('allTimeDownloadSuccessRate'))}'><strong>{_format_rate(data.get('allTimeDownloadSuccessRate'))}</strong><small>Success rate</small></a>"
        "</div>"
    )
    downloads_section = (
        "<section class='overview-panel overview-download-panel' aria-labelledby='overview-downloads-title'>"
        "<div class='section-heading overview-download-heading'><div>"
        "<h2 id='overview-downloads-title'>App downloads</h2></div>"
        "<div class='overview-download-totals' aria-label='Total GitHub downloads'>"
        f"<div class='overview-download-total' aria-label='.dmg downloads total: {download_total('dmgTotal')}'><strong>{download_total('dmgTotal')}</strong><small>.dmg</small></div>"
        f"<div class='overview-download-total' aria-label='.zip downloads total: {download_total('zipTotal')}'><strong>{download_total('zipTotal')}</strong><small>.zip</small></div>"
        "</div></div>"
        f"{_overview_downloads_chart(downloads, time_zone, period=period)}"
        f"<p class='overview-chart-note'>{download_update_note}</p>"
        "</section>"
    ) if download_has_data else ""
    notice_event_id = ""
    try:
        notice_event_id = str(UUID(str(review_event_id).strip()))
    except (ValueError, AttributeError):
        pass
    review_notice = ""
    if notice_event_id and review_action in {"dismissed", "reopened"}:
        if review_action == "dismissed":
            review_notice = (
                "<div class='overview-review-notice' role='status'>Review item dismissed. "
                "<form method='post' action='/admin/review/missing-diagnostics/undo' "
                "class='admin-async-action'>"
                f"<input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>"
                f"<input type='hidden' name='event_id' value='{html.escape(notice_event_id, quote=True)}'>"
                "<button type='submit' class='link-button'>Undo</button></form></div>"
            )
        else:
            review_notice = "<div class='overview-review-notice' role='status'>Review item reopened.</div>"
    attention_section = (
        f"<section class='overview-panel overview-attention-panel{' overview-attention-empty' if not has_review_queue else ''}' aria-labelledby='overview-attention-title'><div class='section-heading'><div><h2 id='overview-attention-title'>Needs attention</h2></div></div>{review_notice}{attention_content}"
        + ("<p class='empty'>No pending work.</p>" if not has_review_queue else "")
        + "</section>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard overview-page' id='main-content'>
        <div class='heading-row overview-heading'><div><h1>Dashboard</h1></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin'><label><span class='sr-only'>Time period</span><select id='overview-period' name='period'>{period_options}</select></label></form></div>
        <div class='overview-primary-grid'><section class='overview-panel overview-chart-panel' aria-labelledby='overview-download-trend-title'><div class='section-heading overview-map-heading'><div><h2 id='overview-download-trend-title'>Map downloads</h2></div>{download_totals}</div>{_overview_trend_chart(list(data.get('trend') or []), str(data.get('bucket') or 'day'), time_zone, metric='downloads', has_activity=bool((data.get('completedDownloadCount') or 0) + (data.get('failedDownloadCount') or 0)))}</section><section class='overview-panel overview-chart-panel' aria-labelledby='overview-trend-title'><div class='section-heading overview-map-heading'><div><h2 id='overview-trend-title'>Map installs</h2></div>{map_totals}</div>{_overview_trend_chart(list(data.get('trend') or []), str(data.get('bucket') or 'day'), time_zone, has_activity=bool((data.get('completedInstallCount') or 0) + (data.get('failedInstallCount') or 0) + (data.get('mapUpdateCount') or 0)))}</section></div>
        <div class='overview-composition-grid'>{attention_section}<section class='overview-panel overview-activity-panel' aria-labelledby='overview-activity-title'><div class='section-heading'><div><h2 id='overview-activity-title'>Activity</h2></div><a class='section-link' href='{html.escape(map_statistics_href, quote=True)}'>View all&nbsp;{_admin_icon('arrow-right')}</a></div>{recent_content}</section>{downloads_section}</div>
      </main>
      <script>{_overview_period_script()}</script>
    """
    return _layout("Dashboard", content, sections={"mapActivity": data, "compatibility": compatibility, "downloads": downloads, "providers": providers, "review": user.get("admin_review_summary"), "system": [(card["title"], card["status"], card["reason"]) for card in _system_health_cards(overview.get("system") or {})[0]]})


def _health_status_badge(status: Any) -> str:
    normalized = str(status or "UNKNOWN").strip().upper()
    labels = {
        "HEALTHY": "Healthy", "WARNING": "Degraded",
        "FAILED": "Failed", "UNKNOWN": "Evidence missing",
    }
    if normalized not in labels:
        normalized = "UNKNOWN"
    return f"<span class='system-health-badge system-health-{normalized.lower()}'>{labels[normalized]}</span>"


def _health_run_link(observation: dict[str, Any] | None, *, label: str = "GitHub Actions") -> str:
    url = str((observation or {}).get("source_run_url") or "").strip()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not re.fullmatch(r"/VooZ2/terento/actions/runs/\d+", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return f"<a class='section-link' href='{html.escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{html.escape(label)}&nbsp;{_admin_icon('external')}</a>"


def _system_health_card(
    title: str,
    status: Any,
    description: str,
    observation: dict[str, Any] | None = None,
    *,
    reason: str = "",
    action: str = "",
) -> dict[str, Any]:
    normalized_status = str(status or "UNKNOWN").upper()
    checked = (observation or {}).get("observed_at")
    when = _timestamp_markup(checked) if checked else "—"
    attrs = (
        f"data-health-status='{html.escape(normalized_status, quote=True)}' "
        f"data-health-name='{html.escape(title.casefold(), quote=True)}'"
    )
    heading = f"<h2>{html.escape(title)}</h2>{_health_status_badge(normalized_status)}"
    technical = ""
    if description.strip() or observation:
        technical = (
            "<details class='admin-disclosure system-health-technical'>"
            "<summary>Technical details</summary><div class='disclosure-body'>"
            f"<div class='system-health-description'>{description}</div>"
            f"{_health_run_link(observation)}</div></details>"
        )
    if normalized_status == "HEALTHY":
        markup = (
            f"<div class='system-health-row' {attrs}>"
            f"{heading}<span class='system-health-when'>{when}</span></div>"
        )
    else:
        markup = (
            f"<article class='system-health-row system-health-issue' {attrs}>"
            f"<div class='system-health-issue-heading'>{heading}</div>"
            f"<p class='system-health-cause'>{html.escape(reason)}</p>"
            f"<p class='system-health-action'>{html.escape(action)}</p>"
            f"<span class='system-health-when'>Last checked {when}</span>"
            f"{technical}</article>"
        )
    return {"title": title, "status": normalized_status, "html": markup, "reason": reason, "lastChecked": checked}


def _health_details(observation: dict[str, Any] | None) -> dict[str, Any]:
    details = (observation or {}).get("details")
    if isinstance(details, dict):
        return details
    if isinstance(details, str):
        try:
            decoded = json.loads(details)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _safe_indexnow_preview(details: dict[str, Any]) -> list[str]:
    raw = details.get("url_preview")
    if not isinstance(raw, str):
        return []
    urls = []
    for value in raw.splitlines():
        parsed = urlsplit(value)
        if (
            parsed.scheme == "https"
            and parsed.netloc == "terento.app"
            and parsed.path.startswith("/")
            and (parsed.path == "/" or parsed.path.endswith("/"))
            and not parsed.query
            and not parsed.fragment
        ):
            urls.append(value)
    return urls[:10]


def _indexnow_count(value: Any) -> int | None:
    return _optional_nonnegative_int(value)


def _indexnow_card(
    indexnow: dict[str, Any] | None,
    site: dict[str, Any] | None,
    *,
    now: datetime,
) -> dict[str, Any]:
    report = indexnow if isinstance(indexnow, dict) else None
    report_details = _health_details(report)
    site_details = _health_details(site)
    publication_id = str(site_details.get("indexnow_publication_id") or "").strip()
    reported_publication_id = str(report_details.get("publication_id") or "").strip()
    expected = site_details.get("indexnow_expected") is True
    matching_report = bool(report and publication_id and reported_publication_id == publication_id)
    report_status = str((report or {}).get("status") or "UNKNOWN").upper()
    result = str(report_details.get("result") or "not_initialized")
    reason = str((report or {}).get("summary") or "No IndexNow production report has been retained.")
    action = "Review the deployment workflow and sender state; no search-indexing claim is implied."
    status = report_status if report else "UNKNOWN"
    if status not in {"HEALTHY", "WARNING", "FAILED", "UNKNOWN"}:
        status = "UNKNOWN"

    if expected and not matching_report:
        deployed_at = _parse_timestamp((site or {}).get("observed_at"))
        grace_seconds = _indexnow_count(site_details.get("indexnow_grace_seconds")) or 1_800
        grace_elapsed = deployed_at is not None and now >= deployed_at + timedelta(seconds=grace_seconds)
        if grace_elapsed:
            status = "WARNING"
            result = "missing_report"
            reason = "IndexNow report missing for the latest deployment."
            action = "Inspect the workflow run and retry only the operational report after confirming sender state."
        else:
            status = "UNKNOWN"
            result = "awaiting_report"
            reason = "The latest deployment is still within the documented IndexNow report grace period."
            action = "Wait for the workflow report or inspect the linked deployment run if it exceeds the grace period."
    elif not report:
        if expected:
            reason = "No IndexNow report has been retained for the latest deployment."
        action = "Run a confirmed production deployment before treating IndexNow as initialized."

    pending_count = _indexnow_count(report_details.get("pending_url_count"))
    if report and (matching_report or not expected):
        if result in {"validation_pending", "pending_retry", "partial_success"}:
            status = "WARNING"
        elif result in {"action_required", "live_verification_failed"}:
            status = "FAILED"
        elif result in {"bootstrap", "not_initialized"}:
            status = "UNKNOWN"
        elif result in {"submitted", "no_changes"}:
            status = "HEALTHY" if pending_count == 0 else "WARNING" if pending_count is not None else "UNKNOWN"
    if matching_report and pending_count is not None and pending_count > 0 and status == "HEALTHY":
        status = "WARNING"
        reason = "IndexNow has pending URLs retained for retry."
        action = "Inspect the sender result and allow the next eligible workflow to retry the pending URLs."

    last_submission = report_details.get("last_submission_at")
    last_successful = report_details.get("last_successful_submission_at")
    attempted = _indexnow_count(report_details.get("attempted_url_count"))
    http_200_count = _indexnow_count(report_details.get("http_200_count"))
    http_202_count = _indexnow_count(report_details.get("http_202_count"))
    http_status = _indexnow_count(report_details.get("http_status"))
    if http_status is None:
        http_result = "No request"
    else:
        http_result = f"HTTP {http_status} · 200: {http_200_count if http_200_count is not None else '—'} · 202: {http_202_count if http_202_count is not None else '—'}"
    preview = _safe_indexnow_preview(report_details)
    preview_total = _indexnow_count(report_details.get("url_preview_total"))
    preview_markup = (
        f"<p>Showing {len(preview)} of {preview_total if preview_total is not None else len(preview)} URLs:</p>"
        "<ul class='indexnow-url-preview'>"
        + "".join(f"<li><code>{html.escape(url)}</code></li>" for url in preview)
        + "</ul>"
        if preview else "<p>No URL preview retained.</p>"
    )
    error_summary = report_details.get("error_summary")
    if not isinstance(error_summary, str) or len(error_summary) > 240:
        error_summary = None
    safe_error = html.escape(error_summary or "No additional error recorded.")
    checked = (report or site or {}).get("observed_at")
    short_result = {
        "submitted": "Submitted",
        "validation_pending": "Validation pending",
        "no_changes": "No changes to submit",
        "pending_retry": "Pending retry",
        "partial_success": "Partial success",
        "action_required": "Action required",
        "bootstrap": "Initialized — no submission yet",
        "not_initialized": "Not initialized",
        "missing_report": "Report missing",
        "awaiting_report": "Awaiting report",
    }.get(result, result.replace("_", " ").title())
    technical = (
        "<details class='admin-disclosure system-health-technical'>"
        "<summary>Technical details</summary><div class='disclosure-body'>"
        f"<p class='indexnow-status-note'>Submission status only. This does not confirm search indexing.</p>"
        f"<p class='sr-only'>Result: {html.escape(short_result)}</p>"
        "<dl class='indexnow-details'>"
        f"<div><dt>Last check</dt><dd>{_timestamp_markup(checked)}</dd></div>"
        f"<div><dt>Last submission</dt><dd>{_timestamp_markup(last_submission) if last_submission else 'No submissions yet'}</dd></div>"
        f"<div><dt>Last successful submission (HTTP 200)</dt><dd>{_timestamp_markup(last_successful) if last_successful else '—'}</dd></div>"
        f"<div><dt>Last execution</dt><dd>{attempted if attempted is not None else '—'} URL(s) · {html.escape(http_result)}</dd></div>"
        f"<div><dt>Pending URLs</dt><dd>{pending_count if pending_count is not None else '—'}</dd></div>"
        f"<div><dt>Oldest pending</dt><dd>{_timestamp_markup(report_details.get('oldest_pending_at'))}</dd></div>"
        "</dl>"
        f"<div class='system-health-description'>{preview_markup}</div>"
        f"<p class='indexnow-error'><strong>Safe error</strong>: {safe_error}</p>"
        f"{_health_run_link(report or site, label='View workflow')}</div></details>"
    )
    markup = (
        "<article class='system-health-row system-health-issue' "
        f"data-health-status='{html.escape(status, quote=True)}' "
        f"data-health-name='indexnow submissions'>"
        f"<div class='system-health-issue-heading'><h2>IndexNow submissions</h2>{_health_status_badge(status)}</div>"
        f"<p class='system-health-cause'>{html.escape(reason)}</p>"
        f"<p class='system-health-action'>{html.escape(action)}</p>"
        f"<span class='system-health-when'>Last checked {_timestamp_markup(checked)}</span>"
        f"{technical}</article>"
    )
    return {
        "title": "IndexNow submissions",
        "status": status,
        "html": markup,
        "reason": reason,
        "lastChecked": checked,
    }


def _system_health_cards(health: dict[str, Any]) -> tuple[list[dict[str, Any]], Any, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    providers = [
        provider for provider in health.get("providers") or []
        if str(provider.get("id") or "") in {"freizeitkarte", "opentopomap", "maprando", "bbbike"}
    ]
    observations = {
        str(item.get("component") or ""): item
        for item in health.get("observations") or [] if isinstance(item, dict)
    }
    weekly = health.get("weekly") if isinstance(health.get("weekly"), dict) else None
    scheduler = health.get("scheduler") if isinstance(health.get("scheduler"), dict) else None

    scheduler_status = "UNKNOWN"
    scheduler_reason = "No scheduler heartbeat has been retained yet."
    if scheduler:
        scheduler_status = {
            "HEALTHY": "HEALTHY", "WAITING": "HEALTHY", "RUNNING": "HEALTHY",
            "WARNING": "WARNING", "FAILED": "FAILED",
        }.get(str(scheduler.get("status") or "UNKNOWN").upper(), "UNKNOWN")
        next_run = _parse_timestamp(scheduler.get("next_run_at"))
        completed = _parse_timestamp(scheduler.get("completed_at"))
        if scheduler_status == "HEALTHY" and (
            (next_run is not None and next_run < now - timedelta(hours=6))
            or (completed is not None and now - completed > timedelta(days=10))
        ):
            scheduler_status = "WARNING"
            scheduler_reason = "The retained scheduler heartbeat is overdue or stale."
        elif scheduler_status in {"WARNING", "FAILED"}:
            scheduler_reason = str(scheduler.get("error_summary") or "The latest scheduler run did not complete cleanly.")

    weekly_status = str((weekly or {}).get("status") or "UNKNOWN").upper()
    weekly_at = _parse_timestamp((weekly or {}).get("observed_at"))
    if weekly_status == "HEALTHY" and weekly_at and now - weekly_at > timedelta(days=8):
        weekly_status = "WARNING"
    weekly_reason = str((weekly or {}).get("summary") or "No weekly quality-gate report has been received.")
    if weekly_status == "WARNING" and weekly_at and now - weekly_at > timedelta(days=8):
        weekly_reason = "The latest weekly quality-gate report is more than 8 days old."

    release = observations.get("release")
    site = observations.get("site")
    api = observations.get("catalog-api")
    drift_status = "UNKNOWN"
    drift_text = "Release or deployed website metadata has not been reported yet."
    if release and site:
        expected = (str(release.get("release_version") or ""), str(release.get("build_number") or ""))
        deployed = (str(site.get("release_version") or ""), str(site.get("build_number") or ""))
        drift_status = "HEALTHY" if expected == deployed and all(expected) else "WARNING"
        drift_text = (
            f"Manifest and release agree: {expected[0]} · build {expected[1]}."
            if drift_status == "HEALTHY" else
            f"Release expects {expected[0] or '—'} · build {expected[1] or '—'}; website reports {deployed[0] or '—'} · build {deployed[1] or '—'}."
        )
    elif site:
        deployed = (str(site.get("release_version") or ""), str(site.get("build_number") or ""))
        drift_status = str(site.get("status") or "UNKNOWN").upper() if all(deployed) else "WARNING"
        drift_text = (
            f"The deployed website manifest was verified as {deployed[0]} · build {deployed[1]}. "
            "No separate release-gate observation is required for this deployed-manifest check."
        )

    weekly_details = (weekly or {}).get("details") or {}
    if isinstance(weekly_details, str):
        try:
            weekly_details = json.loads(weekly_details)
        except json.JSONDecodeError:
            weekly_details = {}
    email_result = str(weekly_details.get("email") or "unknown").lower()
    email_status = (
        "HEALTHY" if email_result in {"success", "passed", "healthy"}
        else "FAILED" if email_result in {"failure", "failed", "cancelled", "timed_out"}
        else "UNKNOWN"
    )
    cards = [
        _system_health_card(
            "API", health.get("api"), "<p>Authenticated response received.</p>",
            reason="The API health state could not be confirmed.",
            action="Reload the page, then inspect the catalog API deployment and service logs.",
        ),
        _system_health_card(
            "Database", health.get("database"), "<p>Database snapshot read.</p>",
            reason="A live PostgreSQL health state could not be confirmed.",
            action="Inspect the database connection and migration state.",
        ),
    ]
    for provider in providers:
        state = provider_catalog_health(provider, now=now)
        releases = ', '.join(str(value) for value in provider.get('packageReleases', []))
        description = (
            f"<p>Newest package release <strong>{html.escape(str(provider.get('latestRelease') or '—'))}</strong>; "
            f"{_optional_count_label(provider.get('packageCount'))} packages.</p>"
            ""
            f"<p>Catalog releases: {html.escape(releases or str(provider.get('latestRelease') or 'Not recorded'))}.</p>"
            f"<p>Latest collection attempt: {_timestamp_markup(provider.get('lastCollectionAttempt'))}. "
            f"Result: {html.escape(str(provider.get('lastCollectionStatus') or 'Not recorded'))}.</p>"
            f"<p>Last successful collection: {_timestamp_markup(provider.get('lastCollectionSuccess') or provider.get('lastCatalogSync'))}. "
            f"Last detected release change: {_timestamp_markup(provider.get('latestReleaseDetectedAt'))}.</p>"
            f"<a class='section-link' href='/admin/providers/{quote(str(provider.get('id')), safe='')}#provider-collection-history'>Collection results and history →</a> "
            f"<a class='section-link' href='/admin/providers/{quote(str(provider.get('id')), safe='')}#provider-packages'>Package releases →</a>"
        )
        cards.append(_system_health_card(
            str(provider.get('name') or provider.get('id') or 'Provider'),
            state["status"], description, reason=state["reason"], action=state["action"],
        ))
    cards.append(_indexnow_card(observations.get("indexnow"), site, now=now))
    scheduler_action = "Inspect the catalog scheduler container and its next scheduled run."
    cards.extend([
        _system_health_card(
            "Catalog scheduler", scheduler_status,
            f"<p>Last completed: {_timestamp_markup((scheduler or {}).get('completed_at'))}.</p>"
            + (f"<p>Next check: {_timestamp_markup(scheduler['next_run_at'])}.</p>" if (scheduler or {}).get('next_run_at') else ''),
            reason=scheduler_reason, action=scheduler_action,
        ),
        _system_health_card(
            "Weekly quality gates", weekly_status,
            f"<p>{html.escape(str((weekly or {}).get('summary') or 'No weekly test report received yet.'))}</p><p>Observed: {_timestamp_markup((weekly or {}).get('observed_at'))}.</p>",
            weekly,
            reason=weekly_reason,
            action="Open the linked workflow and rerun the complete weekly matrix.",
        ),
        _system_health_card(
            "Weekly email delivery", email_status,
            f"<p>Latest SMTP2GO delivery step: <strong>{html.escape(email_result)}</strong>.</p>",
            weekly,
            reason=(
                "No weekly email-delivery result is retained."
                if email_result == "unknown"
                else f"The latest SMTP2GO delivery step ended as {email_result}."
            ),
            action="Check the SMTP2GO step and credentials, then resend the weekly report.",
        ),
        _system_health_card(
            "Website deployment", (site or {}).get("status"),
            f"<p>Commit {html.escape(str((site or {}).get('commit_sha') or '—')[:12])}; deployed {_timestamp_markup((site or {}).get('observed_at'))}.</p>",
            site,
            reason=str((site or {}).get("summary") or "No website deployment observation has been received."),
            action="Run the public-site deployment workflow and verify the live manifest.",
        ),
        _system_health_card(
            "API deployment", (api or {}).get("status"),
            f"<p>Commit {html.escape(str((api or {}).get('commit_sha') or '—')[:12])}; deployed {_timestamp_markup((api or {}).get('observed_at'))}.</p>",
            api,
            reason=str((api or {}).get("summary") or "No catalog API deployment observation has been received."),
            action="Run the catalog API deployment workflow and confirm its retained observation.",
        ),
        _system_health_card(
            "Release / manifest", drift_status, f"<p>{html.escape(drift_text)}</p>", release or site,
            reason=drift_text,
            action="Deploy the website manifest again or run the release gate so both observations can be compared.",
        ),
    ])
    sync = health.get("githubSync")
    sync_status = "UNKNOWN" if sync is None else "WARNING" if sync.get("overdue") or sync.get("errors") else "HEALTHY"
    cards.append(_system_health_card(
        "GitHub issue sync", sync_status,
        f"<p>Closed linked issues resolve diagnostics automatically. Checks run every 15 minutes.</p><p>Last check: {_timestamp_markup((sync or {}).get('checked_at'))}.</p>",
        reason="Linked issue checks are overdue or could not be verified.",
        action="Check the API worker and GitHub availability. Existing diagnostic states are preserved on errors.",
    ))
    rank = {"FAILED": 0, "WARNING": 1, "UNKNOWN": 2, "HEALTHY": 3}
    cards.sort(key=lambda card: rank.get(card['status'], 2))
    return cards, weekly, weekly_details


def system_health_page(health: dict[str, Any], user: dict[str, Any], csrf_token: str) -> bytes:
    cards, weekly, weekly_details = _system_health_cards(health)
    counts = {state: sum(card['status'] == state for card in cards) for state in ('FAILED', 'WARNING', 'UNKNOWN', 'HEALTHY')}
    health_options = "".join(f"<option value='{state}'>{state.title()} · {count}</option>" for state, count in counts.items())
    health_summary = " · ".join(f"{count} {state.lower()}" for state, count in counts.items() if count)
    issue_cards = [card for card in cards if card["status"] != "HEALTHY"]
    healthy_cards = [card for card in cards if card["status"] == "HEALTHY"]
    issue_markup = "".join(card["html"] for card in issue_cards)
    healthy_markup = "".join(card["html"] for card in healthy_cards)
    attention_section = (
        f"<section aria-labelledby='health-attention-title'><div class='section-heading'><h2 id='health-attention-title'>Needs attention</h2></div><div class='system-health-list' aria-label='System checks needing attention'>{issue_markup}</div></section>"
        if issue_cards else ""
    )
    suite_labels = {
        "selection": "Test-suite selection",
        "site": "Public website",
        "backend": "Backend / API",
        "app": "macOS application",
        "native": "Native device safety",
        "release": "Release contracts",
        "shared_ci": "Shared / CI contracts",
        "live_catalog": "Live catalog contract",
    }
    detail_rows = "".join(
        f"<tr><th scope='row'>{html.escape(suite_labels.get(str(name), str(name).replace('_', ' ').title()))}</th><td class='column-status'>{_health_status_badge('HEALTHY' if str(value).lower() in {'success', 'passed', 'healthy'} else 'FAILED' if str(value).lower() in {'failure', 'failed', 'cancelled', 'timed_out'} else 'UNKNOWN')}</td><td class='column-status'>{html.escape(str(value))}</td></tr>"
        for name, value in sorted(weekly_details.items())
        if name != "email" and not str(name).startswith("catalog_")
    ) or "<tr><td colspan='3'>No weekly suite details received yet.</td></tr>"
    content = f"""
      {_admin_header(user, csrf_token, active='system-health')}
      <main class='dashboard system-health-page' id='main-content'>
        <div class='heading-row'><div><h1>Health</h1></div></div>
        <form class='filter-bar' id='health-filters' role='search'><label class='filter-search'><span class='sr-only'>Search checks</span><input type='search' id='health-search' placeholder='Search checks'></label><label><span class='sr-only'>Check status</span><select id='health-status'><option value='all'>All statuses</option>{health_options}</select></label><p class='results-count'>{health_summary}</p></form>
        <p class='empty' id='health-empty' hidden>No checks match your filters.</p>
        {attention_section}
        <details class='overview-panel admin-disclosure system-health-healthy'><summary>Healthy checks <span class='disclosure-meta'>· {len(healthy_cards)}</span></summary><div class='disclosure-body system-health-list' aria-label='Healthy system checks'>{healthy_markup}</div></details>
        <details class='overview-panel admin-disclosure'><summary>Weekly results</summary>{_health_run_link(weekly)}<div class='table-wrap'><table class='admin-table'><thead><tr><th scope='col'>Check</th><th scope='col' class='column-status'>Health</th><th scope='col' class='column-status'>Result</th></tr></thead><tbody>{detail_rows}</tbody></table></div></details>
      </main>
      <script>(() => {{
        const form = document.querySelector('#health-filters');
        const search = document.querySelector('#health-search');
        const status = document.querySelector('#health-status');
        const healthy = document.querySelector('.system-health-healthy');
        form.addEventListener('submit', event => event.preventDefault());
        const filter = () => {{
          let visible = 0;
          document.querySelectorAll('[data-health-status]').forEach(row => {{
            row.hidden = !(row.dataset.healthName.includes(search.value.trim().toLocaleLowerCase()) && (status.value === 'all' || row.dataset.healthStatus === status.value));
            if (!row.hidden) visible++;
          }});
          document.querySelector('#health-empty').hidden = visible > 0;
          if (healthy && (search.value.trim() || status.value === 'HEALTHY')) healthy.open = true;
        }};
        search.addEventListener('input', filter); status.addEventListener('change', filter);
      }})();</script>
    """
    return _layout("Health", content, sections={"health": health, "states": [(card["title"], card["status"], card["reason"]) for card in cards]})


def dashboard_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    public_stats_enabled: bool = False,
    identity_devices: list[dict[str, Any]] | None = None,
    diagnostic_summary: dict[str, dict[str, int]] | None = None,
) -> bytes:
    # The statistics view may retain a zero-attempt identity row so raw
    # pre-install evidence remains queryable, but it is not an installation
    # variant and must not appear in the Installations table.
    rows = [
        row for row in rows
        if not (
            int(row.get("attempted_install_count") or 0) == 0
            and int(row.get("prewrite_failure_count") or 0) > 0
        )
    ]
    latest_copy = "All time"
    if not rows:
        content = f"""
          {_admin_header(user, csrf_token, active='installations')}
          <main class="dashboard" id="main-content">
            <div class="heading-row installation-heading"><div><h1>Installations</h1></div><p class="page-meta">{latest_copy}</p></div>
            <p class='empty'>No installation evidence yet.</p>
          </main>
        """
        return _layout("Installations", content, sections={"installations": []})

    catalog_by_id = {str(device.get("id") or device.get("device_id")): device
                     for device in identity_devices or []}
    status_values = [status.value for status in CANONICAL_STATUS_ORDER]
    status_options = "".join(
        f"<option value='{status.lower()}'>{status.title()}</option>"
        for status in status_values
    )
    diagnostic_summary = diagnostic_summary if diagnostic_summary is not None else _diagnostic_summary_by_identity(
        operations or [], resolved_operations or [],
    )
    def metric(row: dict[str, Any], summary_key: str, row_key: str) -> int:
        summary = diagnostic_summary.get(_identity_group_key(row), {})
        if row_key in row:
            return int(row[row_key] or 0)
        return int(summary[summary_key]) if summary_key in summary else int(row.get(row_key) or 0)

    attempts = sum(metric(row, "attempts", "attempted_install_count") for row in rows)
    successes = sum(metric(row, "successful", "successful_install_count") for row in rows)
    failures = sum(metric(row, "failed", "failed_install_count") for row in rows)
    open_errors = sum(
        int(summary.get("open_errors") or 0) for summary in diagnostic_summary.values()
    )
    success_rate = (successes / attempts * 100) if attempts else None
    table_rows = "".join(
        _statistics_row(
            row,
            diagnostic_summary.get(_identity_group_key(row), {}),
            catalog_device=catalog_by_id.get(str(row.get("canonical_device_model_id") or "")),
        )
        for row in rows
    )
    pagination = "" if len(rows) <= 25 else f"""
          <div class='provider-pagination' id='installation-pagination' aria-live='polite'>
            <label>Rows <select id='installation-page-size' aria-label='Rows per installation page'><option value='25' selected>25</option><option value='50'>50</option></select></label>
            <button type='button' data-installation-page='previous' disabled>Previous</button>
            <span>Showing 1–25 of {len(rows)} · page 1 of {(len(rows) + 24) // 25}</span>
            <button type='button' data-installation-page='next'>Next</button>
          </div>
    """
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class="dashboard" id="main-content">
        <div class="heading-row installation-heading"><div><h1>Installations</h1></div><p class="page-meta">{latest_copy}</p></div>
        <section class="map-statistics-kpi-panel provider-card admin-kpi-panel installation-kpis" aria-label="Installation summary">
          <div class="map-statistics-kpi-groups installation-kpi-groups"><section class="map-statistics-kpi-group" aria-labelledby="installation-kpis-title"><h2 id="installation-kpis-title" class="sr-only">Installation summary</h2><div class="map-statistics-kpi-values installation-kpi-values">
            <div class="map-statistics-kpi-value"><span>Attempts</span><strong>{attempts}</strong></div>
            <div class="map-statistics-kpi-value"><span>Successful</span><strong>{successes}</strong></div>
            <div class="map-statistics-kpi-value"><span>Failed</span><strong class="installation-failed-value">{failures}</strong></div>
            <div class="map-statistics-kpi-value"><span>Success rate</span><strong>{_format_rate(success_rate)}</strong></div>
            <div class="map-statistics-kpi-value error-counter-kpi"><span>Open errors</span>{_admin_error_counter(open_errors)}</div>
          </div></section></div>
        </section>
        <section class="evidence-section" aria-label="Installation evidence table">
          <form class="filter-bar admin-filter-bar" id="evidence-filters" role="search"{' hidden' if len(rows) <= 1 else ''}>
            <div class="quick-filter-group" role="group" aria-label="Quick installation filters"><button type="button" class="quick-filter active" data-installation-filter="all" aria-pressed="true">All</button><button type="button" class="quick-filter" data-installation-filter="failed" aria-pressed="false">Failed</button><button type="button" class="quick-filter" data-installation-filter="open" aria-pressed="false">Open errors</button><button type="button" class="quick-filter" data-installation-filter="successful" aria-pressed="false">Successful</button></div>
            <label class="filter-search"> <span class="sr-only">Search models</span><input id="evidence-search" type="search" placeholder="Search models" autocomplete="off"></label>
            <details class="admin-disclosure filter-disclosure" id="installation-more-filters"><summary>More filters</summary><div class="disclosure-body">
              <label><span class="sr-only">Filter by status</span><select id="evidence-status"><option value="all">All statuses</option>{status_options}</select></label>
            </div></details><label class="device-mobile-sort"><span class="sr-only">Sort models</span><select id="evidence-sort"><option value="latest" selected>Latest activity</option><option value="model:ascending">Model ↑</option><option value="model:descending">Model ↓</option><option value="variant:ascending">Variant ↑</option><option value="variant:descending">Variant ↓</option><option value="status:ascending">Status ↑</option><option value="status:descending">Status ↓</option><option value="attempts:ascending">Attempts ↑</option><option value="attempts:descending">Attempts ↓</option><option value="successfulCount:ascending">Successful ↑</option><option value="successfulCount:descending">Successful ↓</option><option value="failedCount:ascending">Failed ↑</option><option value="failedCount:descending">Failed ↓</option><option value="errors:ascending">Open errors ↑</option><option value="errors:descending">Open errors ↓</option><option value="lastSuccess:ascending">Last success ↑</option><option value="lastSuccess:descending">Last success ↓</option></select></label>
            <p class="results-count" id="results-count" aria-live="polite">{_count_label(len(rows), 'variant')}</p>
            <button type="button" class="secondary-button filter-clear" data-filter-clear aria-label="Clear installation filters" hidden>Clear</button>
          </form>
          <p id="installation-empty" class="table-help" role="status" hidden>No matching models.</p>
          <div class="table-wrap evidence-table-wrap" id="installation-table" tabindex="0" role="region" aria-label="Installation evidence table"><table class="admin-table"><caption class="sr-only">Installations by exact device identity</caption><colgroup><col class="evidence-column-model"><col class="evidence-column-variant"><col class="evidence-column-status"><col class="evidence-column-attempts"><col class="evidence-column-successful"><col class="evidence-column-failed"><col class="evidence-column-open-errors"><col class="evidence-column-last-success"></colgroup><thead><tr><th scope="col" class="" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="model" aria-label="Model">Model <span aria-hidden="true">↕</span></button></th><th scope="col" class="" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="variant" aria-label="Variant">Variant <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="status" aria-label="Status">Status <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="attempts" aria-label="Attempts">Attempts <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="successfulCount" aria-label="Successful">Successful <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="failedCount" aria-label="Failed">Failed <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="errors" aria-label="Open errors">Open errors <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-date" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="lastSuccess" aria-label="Last success">Last success <span aria-hidden="true">↕</span></button></th></tr></thead><tbody id="evidence-rows">{table_rows}</tbody></table></div>
          {pagination}
        </section>
      </main>
      <script>{_dashboard_script()}</script>
    """
    return _layout("Installations", content, sections={"installations": rows, "diagnostics": diagnostic_summary, "catalog": identity_devices})


def _admin_json(value: Any) -> str:
    """Serialize data for an inert/nonce-protected inline admin script."""

    encoded = json.dumps(value, ensure_ascii=False, default=_admin_json_default)
    # Keep server-provided text from terminating a script element or becoming
    # HTML markup when an adapter/source value is unexpectedly user-controlled.
    return (
        encoded.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _admin_json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _provider_status_badge(value: Any, *, kind: str = "status") -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    labels = {
        "ACTIVE": "Active",
        "PAUSED": "Paused",
        "RETIRED": "Retired",
        "HEALTHY": "Healthy",
        "DEGRADED": "Degraded",
        "DOWN": "Down",
        "UNKNOWN": "Unknown",
        "RUNNING": "Running",
        "SUCCEEDED": "Successful",
        "FAILED": "Failed",
    }
    css_value = re.sub(r"[^a-z0-9_-]", "-", normalized.lower()) or "unknown"
    label = labels.get(normalized, normalized.title())
    return f"<span class='provider-status provider-status-{html.escape(css_value)}'>{html.escape(label)}</span>"


def _provider_url(value: Any, *, label: str | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "<span class='muted-value'>—</span>"
    escaped = html.escape(raw, quote=True)
    text = html.escape(label or raw)
    if raw.startswith(("https://", "http://")):
        return f"<a href='{escaped}' target='_blank' rel='noopener noreferrer'>{text} {_admin_icon('external')}</a>"
    return text


def _provider_source_label(value: Any) -> str:
    # Source details are already collapsed; show the full URL when expanded.
    return str(value or "").strip() or "—"


def _provider_source_type_label(value: Any) -> str:
    labels = {
        "WEBSITE": "Website",
        "CATALOG": "Catalog",
        "LICENSE": "License",
        "DOWNLOAD": "Package download",
    }
    normalized = str(value or "").strip().upper()
    return labels.get(normalized, normalized.title() or "Source")


def _provider_check_badge(value: Any) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    if normalized == "UNKNOWN":
        return "<span class='provider-status provider-status-unknown' title='Evidence missing'>Evidence missing</span>"
    return _provider_status_badge(normalized, kind="health")


def _provider_health_counts(health: dict[str, Any] | None) -> tuple[int, int]:
    if not health:
        return 0, 0
    component_keys = (
        "website_status", "catalog_status", "redirect_status", "download_status",
        "mime_status", "magic_status", "zip_status", "img_status",
        "last_update_status",
    )
    passed = sum(1 for key in component_keys if str(health.get(key) or "").upper() == "HEALTHY")
    not_evaluated = sum(1 for key in component_keys if str(health.get(key) or "UNKNOWN").upper() == "UNKNOWN")
    return passed, not_evaluated


def _provider_action_label(value: Any) -> str:
    labels = {
        "provider.health_checked": "Health checked",
        "provider.catalog_collected": "Catalog collected",
        "provider.catalog_collection_failed": "Catalog collection failed",
        "provider.status_changed": "Status changed",
        "provider.retired": "Provider retired",
    }
    raw = str(value or "").strip()
    return labels.get(raw, raw.replace("_", " ").title() or "Provider action")


def _provider_action_button(
    provider_id: str,
    action: str,
    label: str,
    *,
    status: str | None = None,
    secondary: bool = False,
    disabled: bool = False,
) -> str:
    attributes = (
        f" data-provider-status='{html.escape(status, quote=True)}'" if status else ""
    )
    class_name = "secondary-button" if secondary else ""
    disabled_attribute = " disabled" if disabled else ""
    return (
        f"<button type='button' class='{class_name}' data-provider-action='{html.escape(action, quote=True)}'"
        f" data-provider-id='{html.escape(provider_id, quote=True)}'{attributes}{disabled_attribute}>"
        f"{html.escape(label)}</button>"
    )


def _provider_summary_row(provider: dict[str, Any]) -> str:
    provider_id = str(provider.get("id") or "").strip()
    name = str(provider.get("name") or provider_id or "Unknown provider")
    status = str(provider.get("status") or "UNKNOWN")
    health = str(provider.get("health") or "UNKNOWN")
    affected_packages = provider.get("affectedPackageCount")
    if affected_packages is None and "brokenPackageCount" in provider:
        affected_packages = provider.get("brokenPackageCount")
    problematic_sources = provider.get("problematicSourceCount")
    if problematic_sources is None and "brokenUrlCount" in provider:
        problematic_sources = provider.get("brokenUrlCount")
    def count_label(value: Any, singular: str, plural: str) -> str:
        try:
            return f"{int(value)} {singular if int(value) == 1 else plural}" if value is not None else "—"
        except (TypeError, ValueError):
            return "—"
    provider_href = html.escape(quote(provider_id, safe=""), quote=True)
    problem_label = f"{count_label(affected_packages, 'package', 'packages')} · {count_label(problematic_sources, 'source', 'sources')}"
    has_problems = any(isinstance(value, (int, float)) and value > 0 for value in (affected_packages, problematic_sources))
    issue_markup = (
        f"<span class='provider-issue-count is-positive' title='Current catalog problems: {html.escape(problem_label, quote=True)}' aria-label='Current catalog problems: {html.escape(problem_label, quote=True)}'>{html.escape(problem_label)}</span>"
        if has_problems else "<span class='muted-value'>0</span>"
    )
    package_value = count_label(provider.get("packageCount"), "package", "packages")
    health_error = str(provider.get("lastHealthError") or "").strip()
    health_title = (
        f" title='{html.escape(health_error, quote=True)}'" if health_error else ""
    )
    latest_release = provider.get("latestRelease")
    latest_markup = (
        f"<small class='table-secondary'>Newest package: {html.escape(str(latest_release))}</small>"
        if latest_release else ""
    )
    return (
        "<tr>"
        f"<td><a class='provider-name-link' href='/admin/providers/{provider_href}'><strong>{html.escape(name)}</strong></a>{latest_markup}</td>"
        f"<td class='column-status'>{_provider_status_badge(status)}</td>"
        f"<td class='column-status'{health_title}>{_provider_status_badge(health, kind='health')}</td>"
        f"<td class='column-number numeric'>{html.escape(package_value)}</td>"
        f"<td class='column-number numeric'>{issue_markup}</td>"
        f"<td class='column-date'>{_timestamp_markup(provider.get('lastCatalogSync'))}</td>"
        "</tr>"
    )


def providers_page(
    providers: list[dict[str, Any]] | dict[str, Any], user: dict[str, Any], csrf_token: str
) -> bytes:
    provider_rows = providers.get("providers", []) if isinstance(providers, dict) else providers
    provider_rows = list(provider_rows or [])
    rows = "".join(_provider_summary_row(provider) for provider in provider_rows)
    empty = "<p class='empty'>No known providers are registered.</p>" if not provider_rows else ""
    active = sum(1 for provider in provider_rows if str(provider.get("status")).upper() == "ACTIVE")
    healthy = sum(1 for provider in provider_rows if str(provider.get("health")).upper() == "HEALTHY")
    affected_packages = [provider.get("affectedPackageCount", provider.get("brokenPackageCount")) for provider in provider_rows]
    problematic_sources = [provider.get("problematicSourceCount", provider.get("brokenUrlCount")) for provider in provider_rows]
    affected_package_total = sum(int(value) for value in affected_packages) if all(value is not None for value in affected_packages) else None
    problematic_source_total = sum(int(value) for value in problematic_sources) if all(value is not None for value in problematic_sources) else None
    exceptions = []
    if active != len(provider_rows):
        exceptions.append(f"{len(provider_rows) - active} inactive")
    if healthy != len(provider_rows):
        exceptions.append(f"{len(provider_rows) - healthy} health exceptions")
    if affected_package_total:
        exceptions.append(f"{affected_package_total} affected packages")
    if problematic_source_total:
        exceptions.append(f"{problematic_source_total} problematic sources")
    provider_summary = (
        "<section class='admin-summary-strip' aria-label='Provider problems'>"
        f"<p class='admin-summary-metrics'><strong>Needs attention</strong><span> · {html.escape(' · '.join(exceptions))}</span></p></section>"
        if exceptions else ""
    )
    content = f"""
      {_admin_header(user, csrf_token, active='providers')}
      <main class='dashboard providers-page' id='main-content'>
        <div class='heading-row'><div><h1>Providers</h1></div></div>
        {provider_summary}
        {empty}
        <section class='provider-section' aria-label='Provider list'>
          <div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Map provider status</caption><thead><tr><th scope='col'>Provider</th><th scope='col' class='column-status'>State</th><th scope='col' class='column-status'>Health</th><th scope='col' class='column-number'>Packages</th><th scope='col' class='column-number'>Problems</th><th scope='col' class='column-date'>Last sync</th></tr></thead><tbody id='provider-rows'>{rows}</tbody></table></div>
        </section>
      </main>
    """
    return _layout("Providers", content, sections={"providers": provider_rows})


def _provider_package_row(package: dict[str, Any]) -> str:
    broken_count = _optional_nonnegative_int(package.get("broken_artifact_count"))
    availability = str(package.get("availability") or "UNKNOWN")
    is_broken = broken_count is not None and broken_count > 0
    row_class = " provider-package-broken" if is_broken else ""
    package_state = "FAILED" if is_broken else "UNKNOWN" if broken_count is None else availability
    broken_markup = _provider_status_badge(package_state)
    package_id = str(package.get("id") or "—")
    package_name = _admin_map_display_name(
        package.get("country"), package.get("name"), package.get("region"), package_id,
    )
    region = str(package.get("region") or "").strip()
    search = " ".join((package_id, package_name, region, str(package.get("release") or ""))).casefold()
    artifact_details = ""
    for artifact in package.get("artifacts") or []:
        url = str(artifact.get("source_url") or "")
        source = html.escape(url)
        if url.startswith("https://"):
            source = f"<a href='{html.escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{source}</a>"
        artifact_details += (
            f"<p><strong>{html.escape(str(artifact.get('kind') or ''))}</strong> · "
            f"{html.escape(str(artifact.get('validation_status') or 'UNKNOWN'))}<br>"
            f"Download: {_optional_count_label(artifact.get('size_bytes'), ' bytes')} · IMG: {_optional_count_label(artifact.get('install_size_bytes'), ' bytes')}<br>"
            f"Source date: {html.escape(str(artifact.get('source_updated_at') or 'Unknown'))}<br>{source}</p>"
        )
    if artifact_details:
        artifact_details = f"<details class='admin-disclosure' style='text-align:left;overflow-wrap:anywhere'><summary>Artifact details</summary>{artifact_details}</details>"
    return (
        f"<tr class='{row_class.strip()}' data-package-search='{html.escape(search, quote=True)}' data-package-broken='{str(is_broken).lower()}'><td><span class='provider-package-name'>{html.escape(package_name)}</span><code class='provider-package-id'>{html.escape(package_id)}</code>{f'<small>{html.escape(region)}</small>' if region and region.casefold() != package_name.casefold() else ''}{artifact_details}</td>"
        f"<td>{html.escape(str(package.get('release') or '—'))}</td><td class='column-number numeric'>{_optional_count_label(package.get('artifact_count'))}</td>"
        f"<td class='column-status'>{broken_markup}{f' <small>{broken_count} broken</small>' if is_broken else ''}</td></tr>"
    )


def _provider_source_row(source: dict[str, Any]) -> str:
    source_type = str(source.get("source_type") or "").upper()
    source_url = str(source.get("source_url") or "")
    source_label = _provider_source_label(source_url)
    search = " ".join((source_type, source_url)).casefold()
    broken = str(source.get("validation_status") or "").upper() in {"FAILED", "UNAVAILABLE"}
    return (
        f"<tr data-source-type='{html.escape(source_type, quote=True)}' data-source-search='{html.escape(search, quote=True)}' data-source-broken='{str(broken).lower()}'><td>{html.escape({'main': 'Main map', 'contours': 'Contours'}.get(source.get('artifact_kind'), _provider_source_type_label(source_type)))}</td>"
        f"<td class='provider-url-cell' title='{html.escape(source_url, quote=True)}'>{_provider_url(source_url, label=source_label)}</td>"
        f"<td class='column-status'>{_provider_status_badge('ACTIVE' if source.get('enabled', True) else 'PAUSED')}</td>"
        f"<td class='column-date'>{_timestamp_markup(source.get('last_checked_at'))}</td></tr>"
    )


def _provider_health_row(health: dict[str, Any]) -> str:
    components = (
        ("website_status", "Website"), ("catalog_status", "Catalog"),
        ("redirect_status", "Redirects"), ("download_status", "Download"),
        ("mime_status", "MIME"), ("magic_status", "Magic bytes"),
        ("zip_status", "ZIP"), ("img_status", "IMG"),
        ("last_update_status", "Freshness"),
    )
    component_markup = " ".join(
        f"<span class='provider-component'><span>{html.escape(label)}</span>{_provider_check_badge(health.get(key))}</span>"
        for key, label in components
    )
    error = str(health.get("error_code") or health.get("error_detail") or "").strip()
    error_markup = (
        f"<span class='provider-error' title='{html.escape(error, quote=True)}'>{html.escape(error)}</span>"
        if error else "<span class='muted-value'>—</span>"
    )
    http_status = _optional_nonnegative_int(health.get("http_status"))
    if http_status is not None and not 100 <= http_status <= 599:
        http_status = None
    return (
        f"<tr><td class='column-date'>{_timestamp_markup(health.get('checked_at'))}</td><td class='column-status'>{_provider_status_badge(health.get('status'), kind='health')}</td>"
        f"<td class='column-status'><div class='provider-component-list'>{component_markup}</div></td><td class='column-number'>{_optional_count_label(http_status)}</td>"
        f"<td class='column-number'>{_optional_count_label(health.get('artifact_count'))}</td><td class='column-number'>{_optional_count_label(health.get('duration_ms'), ' ms')}</td>"
        f"<td>{error_markup}</td></tr>"
    )


def _provider_update_count(run: dict[str, Any]) -> str:
    new, updated = run.get('new_package_count'), run.get('updated_package_count')
    if run.get('status') != 'SUCCEEDED' or new is None or updated is None:
        return "<span class='muted-value' title='Update count was not recorded for this collection'>—</span>"
    return f"<strong>{int(new) + int(updated)}</strong><small class='table-secondary'>{int(new)} new · {int(updated)} updated</small>"


def _provider_run_row(run: dict[str, Any]) -> str:
    error = str(run.get("error_code") or run.get("error_detail") or "").strip()
    error_markup = html.escape(error) if error else "<span class='muted-value'>—</span>"
    return (
        f"<tr><td><code>{html.escape(str(run.get('id') or '—'))}</code></td><td class='column-date'>{_timestamp_markup(run.get('started_at'))}</td>"
        f"<td class='column-date'>{_timestamp_markup(run.get('finished_at'))}</td><td class='column-status'>{_provider_status_badge(run.get('status'))}<small class='table-secondary'>{'Release change detected' if run.get('release_change_detected') is True else 'No release change detected' if run.get('release_change_detected') is False else 'Release change not recorded'} · {html.escape(str(run.get('latest_release') or '—'))}</small></td>"
        f"<td class='column-number numeric'>{_provider_update_count(run)}</td><td class='column-number numeric'>{_optional_count_label(run.get('package_count'))}</td><td class='column-number numeric'>{_optional_count_label(run.get('artifact_count'))}</td>"
        f"<td>{error_markup}</td></tr>"
    )


def _provider_audit_row(audit: dict[str, Any]) -> str:
    details = audit.get("details")
    changes_markup = ""
    if audit.get('action') == 'CATALOG_RELEASES_UPDATED' and isinstance(details, dict):
        changes_markup = "<ul class='catalog-release-changes'>" + ''.join(
            f"<li>{html.escape(str(item.get('region') or item.get('packageId') or 'Map'))}: {html.escape(str(item.get('previousRelease') or '—'))} → {html.escape(str(item.get('release') or '—'))}</li>"
            for item in details.get('packages', []) if isinstance(item, dict)
        ) + "</ul>"
    technical_values = {
        "adminUserId": audit.get("admin_user_id"),
        "target": audit.get("target"),
        "details": details,
    }
    technical_text = json.dumps(
        {key: value for key, value in technical_values.items() if value not in (None, "", {})},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        f"<tr><td title='{html.escape(str(audit.get('action') or ''), quote=True)}'>{html.escape(_provider_action_label(audit.get('action')))}</td>"
        f"<td class='column-status'>{html.escape(str(audit.get('old_status') or '—'))}</td><td class='column-status'>{html.escape(str(audit.get('new_status') or '—'))}</td>"
        f"<td>{html.escape(str(audit.get('reason') or '—'))}{changes_markup}</td><td class='column-date'>{_timestamp_markup(audit.get('occurred_at'))}</td>"
        f"<td><details class='audit-technical-details admin-disclosure'><summary>Technical details</summary><code>{html.escape(technical_text if technical_text != '{}' else '—')}</code></details></td></tr>"
    )


def provider_detail_page(
    detail: dict[str, Any], runs: list[dict[str, Any]], audits: list[dict[str, Any]],
    user: dict[str, Any], csrf_token: str,
) -> bytes:
    provider = detail.get("provider", detail)
    provider_id = str(provider.get("id") or "").strip()
    name = str(provider.get("name") or provider_id or "Provider")
    status = str(provider.get("status") or "UNKNOWN").upper()
    health_record = provider.get("health") if isinstance(provider.get("health"), dict) else {}
    health = str(provider.get("healthStatus") or health_record.get("status") or provider.get("health") or "UNKNOWN").upper()
    packages = [
        package for package in list(provider.get("maps") or [])
        if str(package.get("availability") or "").upper() != "RETIRED"
    ]
    sources = list(provider.get("sources") or [])
    provider_sources = [
        source for source in sources
        if str(source.get("source_type") or "").upper() != "DOWNLOAD"
    ]
    download_sources = [
        source for source in sources
        if str(source.get("source_type") or "").upper() == "DOWNLOAD"
    ]
    health_history = list(provider.get("healthHistory") or [])
    broken_artifact_counts = [
        _optional_nonnegative_int(package.get("broken_artifact_count"))
        for package in packages
    ]
    broken_packages = (
        sum(count for count in broken_artifact_counts if count is not None)
        if all(count is not None for count in broken_artifact_counts)
        else None
    )
    affected_package_count = provider.get("affectedPackageCount")
    if affected_package_count is None:
        affected_values = [
            _optional_nonnegative_int(package.get("broken_artifact_count"))
            for package in packages
        ]
        affected_package_count = (
            sum(value > 0 for value in affected_values if value is not None)
            if all(value is not None for value in affected_values)
            else None
        )
    problematic_source_count = provider.get("problematicSourceCount")
    if problematic_source_count is None:
        problematic_source_count = len({
            str(artifact.get("source_url"))
            for package in packages
            for artifact in package.get("artifacts") or []
            if str(artifact.get("validation_status") or "").upper() in {"FAILED", "UNAVAILABLE"}
            and artifact.get("source_url")
        })
    package_count = int(provider["packageCount"]) if provider.get("packageCount") is not None else sum(p.get("availability") == "AVAILABLE" for p in packages)
    release_counts: dict[str, int] = {}
    for package in packages:
        release = str(package.get('release') or 'Not recorded')
        release_counts[release] = release_counts.get(release, 0) + 1
    release_summary = ' · '.join(
        f"{html.escape(release)}: {count} packages"
        for release, count in sorted(release_counts.items(), reverse=True)
    ) or 'No package releases recorded.'
    latest_health = health_history[0] if health_history else {}
    previous_health = health_history[1:] if latest_health else []
    health_passed, health_not_evaluated = _provider_health_counts(latest_health)
    latest_health_status = str(latest_health.get("status") or health or "UNKNOWN").upper()
    latest_run = runs[0] if runs else {}
    latest_run_status = str(latest_run.get("status") or "NONE").upper()
    activation_gate = provider.get("activationGate")
    if not isinstance(activation_gate, dict):
        activation_gate = {}
    can_activate = bool(activation_gate.get("canActivate"))
    activation_blockers = [
        str(item.get("message") or "")
        for item in activation_gate.get("blockers", [])
        if isinstance(item, dict) and str(item.get("message") or "")
    ]
    state_button = ""
    if status != "RETIRED":
        next_status = "PAUSED" if status == "ACTIVE" else "ACTIVE"
        state_button = _provider_action_button(
            provider_id,
            "state",
            "Pause" if next_status == "PAUSED" else "Activate",
            status=next_status,
            secondary=True,
            disabled=next_status == "ACTIVE" and not can_activate,
        )
    activation_note = ""
    if status != "ACTIVE" and status != "RETIRED" and not can_activate:
        if not activation_blockers:
            activation_blockers = ["Activation checks are not available."]
        activation_note = (
            "<p class='provider-activation-note' role='status'><strong>Activation blocked.</strong> "
            + html.escape(" ".join(activation_blockers))
            + "</p>"
        )
    rows_packages = "".join(_provider_package_row(package) for package in packages)
    rows_sources = "".join(_provider_source_row(source) for source in provider_sources)
    artifact_kinds = {str(a.get("source_url") or ""): str(a.get("kind") or "main")
                      for package in packages for a in package.get("artifacts") or []}
    typed_sources = [dict(source, artifact_kind=artifact_kinds.get(str(source.get("source_url") or ""), "unknown")) for source in download_sources]
    contour_sources = sum(source["artifact_kind"] == "contours" for source in typed_sources)
    main_sources = sum(source["artifact_kind"] == "main" for source in typed_sources)
    source_counts = f"<span class='status-badge'>Main maps · {main_sources}</span> <span class='status-badge'>Contours · {contour_sources}</span>"
    rows_download_sources = "".join(_provider_source_row(source) for source in typed_sources)
    rows_health = "".join(_provider_health_row(item) for item in previous_health)
    rows_runs = "".join(_provider_run_row(run) for run in runs)
    rows_audits = "".join(_provider_audit_row(audit) for audit in audits)
    empty_packages = "<p class='empty'>No catalog packages collected yet.</p>" if not packages else ""
    empty_sources = "<p class='empty'>No provider source links recorded.</p>" if not provider_sources else ""
    empty_download_sources = "<p class='empty'>No download source URLs recorded.</p>" if not download_sources else ""
    empty_health = "<p class='empty'>No health checks recorded yet.</p>" if not health_history else ""
    empty_previous_health = "<p class='empty'>No previous health checks recorded.</p>" if not previous_health else ""
    empty_runs = "<p class='empty'>No catalog collection runs recorded yet.</p>" if not runs else ""
    empty_audits = "<p class='empty'>No provider audit entries recorded yet.</p>" if not audits else ""
    source_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-source-table'><caption class='sr-only'>Provider-level original sources</caption><thead><tr><th scope='col'>Source</th><th scope='col'>Original link</th><th scope='col' class='column-status'>Status</th><th scope='col' class='column-date'>Last checked</th></tr></thead><tbody>{rows_sources}</tbody></table></div>" if provider_sources else ""
    download_source_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-source-table'><caption class='sr-only'>Download source URLs</caption><thead><tr><th scope='col'>Source</th><th scope='col'>Original link</th><th scope='col' class='column-status'>Status</th><th scope='col' class='column-date'>Last checked</th></tr></thead><tbody id='provider-download-source-rows'>{rows_download_sources}</tbody></table></div>" if download_sources else ""
    download_source_section = f"<details class='admin-disclosure' id='provider-download-sources'><summary>Download source URLs <span class='disclosure-meta'>· {len(download_sources)}</span></summary><div class='disclosure-body'><p>{source_counts}</p><div class='inline-filter-row'><label><span class='sr-only'>Search source URLs</span><input id='provider-source-search' type='search' placeholder='Search source URLs' autocomplete='off'></label><label><span class='sr-only'>Source status</span><select id='provider-source-filter'><option value='all'>All sources</option><option value='broken'>Broken only</option></select></label><label><span class='sr-only'>Source page size</span><select id='provider-source-page-size'><option value='25'>25 per page</option><option value='50'>50 per page</option></select></label></div>{download_source_table}<div class='provider-pagination' id='provider-source-pagination' aria-live='polite'></div></div></details>" if download_sources else ""
    package_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-package-table'><caption class='sr-only'>Regions and packages</caption><thead><tr><th scope='col'>Region / package</th><th scope='col'>Release</th><th scope='col' class='column-number'>Artifacts</th><th scope='col' class='column-status'>State</th></tr></thead><tbody id='provider-package-rows'>{rows_packages}</tbody></table></div>" if packages else ""
    latest_health_table = f"<div class='table-wrap provider-table-wrap provider-history-wrap'><table class='admin-table'><caption class='sr-only'>Health check details</caption><thead><tr><th scope='col' class='column-date'>Checked</th><th scope='col' class='column-status'>Result</th><th scope='col' class='column-status'>Checks</th><th scope='col' class='column-number'>HTTP</th><th scope='col' class='column-number'>Artifacts</th><th scope='col' class='column-number'>Duration</th><th scope='col'>Error</th></tr></thead><tbody>{_provider_health_row(latest_health)}</tbody></table></div>" if latest_health else ""
    health_history_table = f"<div class='table-wrap provider-table-wrap provider-history-wrap'><table class='admin-table'><thead><tr><th scope='col' class='column-date'>Checked</th><th scope='col' class='column-status'>Result</th><th scope='col' class='column-status'>Checks</th><th scope='col' class='column-number'>HTTP</th><th scope='col' class='column-number'>Artifacts</th><th scope='col' class='column-number'>Duration</th><th scope='col'>Error</th></tr></thead><tbody>{rows_health}</tbody></table></div>" if previous_health else ""
    run_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-run-table'><thead><tr><th scope='col'>Run</th><th scope='col' class='column-date'>Started</th><th scope='col' class='column-date'>Finished</th><th scope='col' class='column-status'>Result</th><th scope='col' class='column-number'>Updates</th><th scope='col' class='column-number'>Packages</th><th scope='col' class='column-number'>Artifacts</th><th scope='col'>Error</th></tr></thead><tbody>{rows_runs}</tbody></table></div>" if runs else ""
    audit_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Provider audit history</caption><thead><tr><th scope='col'>Action</th><th scope='col' class='column-status'>Old status</th><th scope='col' class='column-status'>New status</th><th scope='col'>Reason</th><th scope='col' class='column-date'>Timestamp</th><th scope='col'>Details</th></tr></thead><tbody>{rows_audits}</tbody></table></div>" if audits else ""
    health_summary = (
        f"{_provider_status_badge(latest_health_status, kind='health')} "
        f"<span>{health_passed} checks passed · {health_not_evaluated} not evaluated</span>"
        if latest_health else "<span class='muted-value'>No health check recorded yet.</span>"
    )
    health_transport = (
        f"HTTP {html.escape(str(latest_health.get('http_status') or '—'))} · "
        f"{html.escape(str(latest_health.get('duration_ms') or '—'))} ms"
        if latest_health else "—"
    )
    collection_summary = (
        f"{_provider_status_badge(latest_run_status)} "
        f"<span>{_optional_count_label(latest_run.get('package_count'), ' packages')} · "
        f"{_optional_count_label(latest_run.get('artifact_count'), ' artifacts')} · "
        f"{_timestamp_markup(latest_run.get('finished_at') or latest_run.get('started_at'))}</span>"
        if latest_run else "<span class='muted-value'>No collection run recorded yet.</span>"
    )
    collection_section = (
        f"<section class='provider-card'><div class='section-heading'><div><h2>Collection</h2></div></div><div class='provider-latest-summary'>{collection_summary}</div><details class='admin-disclosure' id='provider-collection-history'><summary>Collection history <span class='disclosure-meta'>· {len(runs)} runs</span></summary><div class='disclosure-body'><p class='table-help'>Updates counts new maps and maps with a changed release or source date. — means the count was not recorded.</p><p class='table-help'>Catalog sync: {_timestamp_markup(provider.get('lastCatalogSync'))}</p>{empty_runs}{run_table}</div></details></section>"
        if latest_run or runs else
        f"<section class='provider-card provider-empty-disclosure'><details class='admin-disclosure' id='provider-collection-history'><summary>Collection <span class='table-help'>No runs yet</span></summary><div class='disclosure-body'><p class='empty'>No catalog collection runs recorded yet.</p><p>Catalog sync: {_timestamp_markup(provider.get('lastCatalogSync'))}</p></div></details></section>"
    )
    provider_attention = ""
    if broken_packages is None:
        provider_attention = (
            "<p class='provider-attention'><strong>Problem count unavailable.</strong> "
            "<a href='#provider-packages'>Review packages</a></p>"
        )
    elif broken_packages > 0:
        provider_attention = (
            f"<p class='provider-attention'><strong>{broken_packages} broken artifacts "
            "need review.</strong> <a href='#provider-packages'>Review packages</a></p>"
        )
    content = f"""
      {_admin_header(user, csrf_token, active='providers')}
      <main class='dashboard provider-detail' id='main-content'>
        <p class='back-link'><a href='/admin/providers'>{_admin_icon('arrow-left')} Back to providers</a></p>
        <div class='heading-row'><div><h1>{html.escape(name)}</h1></div><div class='provider-heading-status'>{_provider_status_badge(status)}</div></div>
        <section class='provider-action-bar' data-provider-id='{html.escape(provider_id, quote=True)}' aria-label='Provider actions'>
          {_provider_action_button(provider_id, 'check', 'Check now')}
          {_provider_action_button(provider_id, 'collect', 'Collect catalog', secondary=True)}
          {state_button}
          <details class='provider-action-overflow'><summary>More</summary><div>{_provider_action_button(provider_id, 'retire', 'Retire provider', secondary=True, disabled=status == 'RETIRED')}</div></details>
          {activation_note}
          <p class='admin-action-status' id='provider-action-status' aria-live='polite'></p>
        </section>
        {provider_attention}
        <section class='map-statistics-kpi-panel provider-card admin-kpi-panel' aria-label='Provider summary'><div class='map-statistics-kpi-groups installation-kpi-groups'><section class='map-statistics-kpi-group'><h2 class='sr-only'>Provider summary</h2><div class='map-statistics-kpi-values provider-kpi-values'><div class='map-statistics-kpi-value'><span>Affected packages</span><strong><a href='#provider-packages'>{_optional_count_label(affected_package_count)}</a></strong></div><div class='map-statistics-kpi-value'><span>Problematic sources</span><strong><a href='#provider-download-sources'>{_optional_count_label(problematic_source_count)}</a></strong></div><div class='map-statistics-kpi-value'><span>Broken artifacts</span><strong>{_optional_count_label(broken_packages)}</strong></div></div></section></div></section>
        <div class='provider-state-grid'>
        <section class='provider-card'><div class='section-heading'><div><h2>Health</h2></div></div><div class='provider-latest-summary'><div>{health_summary}</div><span>{_timestamp_markup(provider.get('lastHealthCheck'))}</span></div><details class='admin-disclosure' id='provider-health-details'><summary>View check details</summary><div class='disclosure-body'>{empty_health}{latest_health_table}</div></details><details class='admin-disclosure' id='provider-health-history'><summary>Health check history <span class='disclosure-meta'>· {len(previous_health)} previous {'check' if len(previous_health) == 1 else 'checks'}</span></summary><div class='disclosure-body'>{empty_previous_health}{health_history_table}</div></details></section>
        {collection_section}</div>
        <section class='provider-card'><details class='admin-disclosure' id='provider-packages'><summary>Regions and packages <span class='disclosure-meta'>· {len(packages)} catalog entries · {_optional_count_label(broken_packages)} broken artifacts</span></summary><div class='disclosure-body'><div class='inline-filter-row'><label><span class='sr-only'>Search packages</span><input id='provider-package-search' type='search' placeholder='Search packages' autocomplete='off'></label><label><span class='sr-only'>Package status</span><select id='provider-package-filter'><option value='all'>All packages</option><option value='broken'>Broken only</option></select></label><label><span class='sr-only'>Package page size</span><select id='provider-package-page-size'><option value='25'>25 per page</option><option value='50'>50 per page</option></select></label></div>{empty_packages}{package_table}<div class='provider-pagination' id='provider-package-pagination' aria-live='polite'></div></div></details></section>
        <details class='provider-card admin-disclosure' id='provider-technical-details'><summary>Technical details</summary><div class='disclosure-body'>
        <details class='admin-disclosure'><summary>Package releases</summary><div class='disclosure-body'><p>{release_summary}</p><p class='table-help'>Each region keeps its own provider release.</p></div></details>
        {download_source_section}
        <details class='admin-disclosure'><summary>Metadata and attribution</summary><dl class='provider-information-list'><div><dt>Provider ID</dt><dd><code>{html.escape(provider_id)}</code></dd></div><div><dt>Adapter</dt><dd><code>{html.escape(str(provider.get('adapterId') or '—'))}</code></dd></div><div><dt>Website</dt><dd>{_provider_url(provider.get('website'))}</dd></div><div><dt>License</dt><dd>{html.escape(str(provider.get('license') or '—'))}</dd></div><div><dt>Attribution</dt><dd>{html.escape(str(provider.get('attribution') or '—'))}</dd></div><div><dt>License URL</dt><dd>{_provider_url(provider.get('licenseUrl'))}</dd></div></dl></details>
        <details class='admin-disclosure'><summary>Original links</summary>{empty_sources}{source_table}</details>
        <details class='admin-disclosure' id='provider-history'><summary>Provider history <span class='disclosure-meta'>· {len(audits)} events</span></summary><div class='disclosure-body'>{empty_audits}{audit_table}</div></details>
        </div></details>
      </main>
      <script>window.terentoAdminCsrf = {_admin_json(csrf_token)};{_provider_detail_script()}</script>
    """
    return _layout(name, content, sections={"provider": detail, "collection": runs, "history": audits})


def _map_statistics_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    has_event_data = bool(rows)

    def row_count(row: dict[str, Any], key: str) -> int | None:
        if key not in row or row.get(key) is None:
            return None
        try:
            value = int(row[key])
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    def count(event_type: str, outcome: str | None = None) -> int | None:
        values = [
            row_count(row, "operation_count")
            for row in rows
            if row.get("event_type") == event_type
            and (outcome is None or row.get("outcome") == outcome)
        ]
        return sum(value for value in values if value is not None) if all(value is not None for value in values) else None

    downloads = count("DOWNLOAD_SUCCEEDED", "SUCCEEDED")
    failed_downloads = count("DOWNLOAD_FAILED", "FAILED")
    download_attempts = downloads + failed_downloads if downloads is not None and failed_downloads is not None else None
    installs = count("INSTALL_SUCCEEDED", "SUCCEEDED")
    failed_installs = count("INSTALL_FAILED", "FAILED")
    install_attempts = installs + failed_installs if installs is not None and failed_installs is not None else None
    successful_updates = count("MAP_UPDATE_SUCCEEDED", "SUCCEEDED")
    failed_updates = count("MAP_UPDATE_FAILED", "FAILED")
    updates = successful_updates + failed_updates if successful_updates is not None and failed_updates is not None else None
    event_counts = [row_count(row, "event_count") for row in rows]
    event_count = sum(value for value in event_counts if value is not None) if all(value is not None for value in event_counts) else None
    return {
        "hasEventData": has_event_data,
        "eventGroupCount": len(rows),
        # An empty result from a successful full query is a measured zero
        # population. Rates remain unavailable because their denominator is 0.
        "eventCount": event_count,
        "completedDownloads": downloads,
        "failedDownloads": failed_downloads,
        "downloadAttempts": download_attempts,
        "downloadSuccessRate": (downloads / download_attempts * 100) if download_attempts else None,
        "completedInstalls": installs,
        "failedInstalls": failed_installs,
        "installAttempts": install_attempts,
        "installSuccessRate": (installs / install_attempts * 100) if install_attempts else None,
        "completedMapUpdates": successful_updates,
        "failedMapUpdates": failed_updates,
        "mapUpdates": updates,
        "mapUpdateSuccessRate": (successful_updates / updates * 100) if updates else None,
    }


def _map_statistics_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tr><td colspan='7' class='muted-value'>No map events in this period.</td></tr>"
    markup: list[str] = []
    for row in rows:
        operation_count = row.get("operation_count")
        if operation_count is None:
            operation_label = "—"
        else:
            try:
                operation_label = str(int(operation_count))
            except (TypeError, ValueError):
                operation_label = "—"
        region_name = str(row.get("region_display_name") or "").strip()
        if not region_name:
            region_name = _admin_region_display_name(
                row.get("canonical_region_id"),
                row.get("region_country"),
                row.get("region"),
                row.get("map_package_name"),
            )
        markup.append(
            f"<tr><td>{html.escape(str(row.get('provider_id') or '—'))}</td>"
            f"<td><code>{html.escape(str(row.get('map_package_id') or '—'))}</code></td>"
            f"<td>{html.escape(region_name)}</td><td>{html.escape(str(row.get('event_type') or '—'))}</td>"
            f"<td class='column-status'>{html.escape(_admin_event_outcome_label(row.get('outcome')))}</td><td class='column-number numeric'>{operation_label}</td>"
            f"<td class='column-date'>{_timestamp_markup(row.get('last_occurred_at'))}</td></tr>"
        )
    return "".join(markup)


def map_statistics_page(
    statistics: dict[str, Any], providers: list[dict[str, Any]], user: dict[str, Any],
    csrf_token: str, *, selected_filters: dict[str, str] | None = None,
) -> bytes:
    rows = list(statistics.get("rows") or [])
    summary = statistics.get("summary") if isinstance(statistics.get("summary"), dict) else _map_statistics_summary(rows)
    all_time_summary = (
        statistics.get("allTimeSummary")
        if isinstance(statistics.get("allTimeSummary"), dict)
        else summary
    )
    statistics = dict(statistics)
    selected = selected_filters or {}
    event_detail_open = " open" if selected.get("eventId") else ""
    has_event_data = bool(rows)
    has_all_time_data = bool(all_time_summary.get("hasEventData", has_event_data))
    def event_value(source: dict[str, Any], key: str) -> str:
        return "—" if source.get(key) is None else str(source[key])
    event_status = "No matching event groups"
    provider_options = "".join(
        f"<option value='{html.escape(str(provider.get('id') or ''), quote=True)}'>{html.escape(str(provider.get('name') or provider.get('id') or ''))}</option>"
        for provider in providers
    )
    detail_rows = list(statistics.get("detailRows") or (rows[:25] if "detailRows" not in statistics else []))
    detail_total = int(statistics.get("detailTotal") if statistics.get("detailTotal") is not None else len(detail_rows))
    detail_page = int(statistics.get("detailPage") or 1)
    detail_page_size = int(statistics.get("detailPageSize") or 25)
    detail_pages = max(1, (detail_total + detail_page_size - 1) // detail_page_size)
    detail_start = min(detail_total, (detail_page - 1) * detail_page_size + 1) if detail_total else 0
    detail_end = min(detail_total, detail_page * detail_page_size)
    detail_event_counts = [
        _optional_nonnegative_int(row.get("event_count"))
        for row in detail_rows
    ]
    detail_event_count = (
        sum(count for count in detail_event_counts if count is not None)
        if all(count is not None for count in detail_event_counts)
        else None
    )
    if detail_rows:
        detail_event_label = (
            f"{detail_event_count} event record{'s' if detail_event_count != 1 else ''}"
            if detail_event_count is not None
            else "— event records"
        )
        event_status = (
            f"{len(detail_rows)} event group{'s' if len(detail_rows) != 1 else ''} · "
            f"{detail_event_label}"
        )
    def failed_metric_markup(source: dict[str, Any], key: str) -> str:
        value = source.get(key)
        return _admin_error_counter(value, data_stat=key)

    updates_section = (
        "<section class='map-statistics-kpi-group' id='map-statistics-updates' aria-labelledby='map-statistics-updates-title'><h2 id='map-statistics-updates-title'>Updates <span class='metric-scope'>All time</span></h2><div class='map-statistics-kpi-values'>"
        f"<div class='map-statistics-kpi-value'><span>Successful</span><strong data-stat='completedMapUpdates'>{event_value(all_time_summary, 'completedMapUpdates')}</strong></div>"
        f"<div class='map-statistics-kpi-value'><span>Success rate</span><strong data-stat='mapUpdateSuccessRate'>{_format_rate(all_time_summary.get('mapUpdateSuccessRate'))}</strong></div>"
        f"<div class='map-statistics-kpi-value failed'><span>Failed</span>{failed_metric_markup(all_time_summary, 'failedMapUpdates')}</div>"
        "</div></section>"
    )
    metrics_section = (
        "<section class='map-statistics-kpi-panel provider-card' id='map-statistics-metrics' aria-label='Map statistics summary'>"
        "<div class='map-statistics-kpi-groups'>"
        "<section class='map-statistics-kpi-group' aria-labelledby='map-statistics-downloads-title'><h2 id='map-statistics-downloads-title'>Map downloads <span class='metric-scope'>All time</span></h2><div class='map-statistics-kpi-values'>"
        f"<div class='map-statistics-kpi-value'><span>Successful</span><strong data-stat='completedDownloads'>{event_value(all_time_summary, 'completedDownloads')}</strong></div>"
        f"<div class='map-statistics-kpi-value'><span>Success rate</span><strong data-stat='downloadSuccessRate'>{_format_rate(all_time_summary.get('downloadSuccessRate'))}</strong></div>"
        f"<div class='map-statistics-kpi-value failed'><span>Failed</span>{failed_metric_markup(all_time_summary, 'failedDownloads')}</div>"
        "</div></section>"
        "<section class='map-statistics-kpi-group' aria-labelledby='map-statistics-installs-title'><h2 id='map-statistics-installs-title'>Map installs <span class='metric-scope'>All time</span></h2><div class='map-statistics-kpi-values'>"
        f"<div class='map-statistics-kpi-value'><span>Successful</span><strong data-stat='completedInstalls'>{event_value(all_time_summary, 'completedInstalls')}</strong></div>"
        f"<div class='map-statistics-kpi-value'><span>Success rate</span><strong data-stat='installSuccessRate'>{_format_rate(all_time_summary.get('installSuccessRate'))}</strong></div>"
        f"<div class='map-statistics-kpi-value failed'><span>Failed</span>{failed_metric_markup(all_time_summary, 'failedInstalls')}</div>"
        "</div></section>"
        f"{updates_section}"
        "</div></section>"
    )
    selected_period = str(
        selected.get("period")
        or (statistics.get("filters") or {}).get("period")
        or "all"
    ).strip().lower()
    if selected_period not in {"24h", "7d", "30d", "all"}:
        selected_period = "all"
    statistics_period_options = "".join(
        f"<option value='{value}'{' selected' if value == selected_period else ''}>{label}</option>"
        for value, label in (
            ("24h", "Last 24 hours"),
            ("7d", "Last 7 days"),
            ("30d", "Last 30 days"),
            ("all", "All time"),
        )
    )
    detail_query = {
        key: value for key, value in selected.items()
        if key not in {"detailPage", "detailPageSize"} and value
    }
    detail_query["detailPageSize"] = str(detail_page_size)
    def detail_page_url(page: int) -> str:
        return "/admin/map-statistics?" + urlencode({**detail_query, "detailPage": page})
    event_pagination = ""
    if detail_pages > 1:
        previous = (
            f"<a class='secondary-button' href='{html.escape(detail_page_url(detail_page - 1), quote=True)}'>Previous</a>"
            if detail_page > 1 else ""
        )
        following = (
            f"<a class='secondary-button' href='{html.escape(detail_page_url(detail_page + 1), quote=True)}'>Next</a>"
            if detail_page < detail_pages else ""
        )
        event_pagination = (
            "<div class='provider-pagination' aria-label='Event pages'>"
            f"{previous}<span>Showing {detail_start}–{detail_end} of {detail_total}</span>{following}</div>"
        )
    event_table = f"""<div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Map operation events</caption><thead><tr><th scope='col'>Provider</th><th scope='col'>Map</th><th scope='col'>Region</th><th scope='col'>Event</th><th scope='col' class='column-status'>Outcome</th><th scope='col' class='column-number'>Operations</th><th scope='col' class='column-date'>Last activity</th></tr></thead><tbody id='map-statistics-rows'>{_map_statistics_rows(detail_rows)}</tbody></table></div>{event_pagination}"""
    has_active_filters = any(
        selected.get(key) for key in ("provider", "map", "region", "eventType", "outcome", "eventId")
    ) or selected_period != "all"
    trend = list(statistics.get("trend") or [])
    bucket = str(statistics.get("bucket") or "day")
    chart_time_zone = str(statistics.get("timeZone") or "UTC")
    trends = (
        "<section class='overview-primary-grid map-statistics-trends' aria-label='Activity trends'>"
        "<section class='overview-panel overview-chart-panel' aria-labelledby='map-download-trend-title'>"
        "<div class='section-heading'><h2 id='map-download-trend-title'>Map downloads</h2></div>"
        f"{_overview_trend_chart(trend, bucket, chart_time_zone, metric='downloads', has_activity=bool((summary.get('completedDownloads') or 0) + (summary.get('failedDownloads') or 0)))}"
        "</section><section class='overview-panel overview-chart-panel' aria-labelledby='map-install-trend-title'>"
        "<div class='section-heading'><h2 id='map-install-trend-title'>Map installs</h2></div>"
        f"{_overview_trend_chart(trend, bucket, chart_time_zone, has_activity=bool((summary.get('completedInstalls') or 0) + (summary.get('failedInstalls') or 0) + (summary.get('mapUpdates') or 0)))}"
        "</section></section>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='map-statistics')}
      <main class='dashboard map-statistics-page' id='main-content'>
        <div class='heading-row'><div><h1>Maps</h1></div></div>
        <form class='filter-bar map-statistics-filter-bar' id='map-statistics-filters' role='search' method='get' action='/admin/map-statistics'><label><span class='sr-only'>Time range</span><select id='map-statistics-range' name='period'>{statistics_period_options}</select></label><label><span class='sr-only'>Provider</span><select id='map-statistics-provider' name='provider'><option value=''>All providers</option>{provider_options}</select></label><details class='admin-disclosure filter-disclosure' id='map-statistics-more-filters'><summary>More filters</summary><div class='disclosure-body'><label><span class='sr-only'>Map ID</span><input id='map-statistics-map' name='map' type='search' placeholder='Map ID'></label><label><span class='sr-only'>Region</span><input id='map-statistics-region' name='region' type='search' placeholder='Region'></label><label><span class='sr-only'>Event type</span><select id='map-statistics-event' name='eventType'><option value=''>All events</option><option value='DOWNLOAD_SUCCEEDED'>Download succeeded</option><option value='DOWNLOAD_FAILED'>Download failed</option><option value='INSTALL_SUCCEEDED'>Install succeeded</option><option value='INSTALL_FAILED'>Install failed</option><option value='MAP_UPDATE_SUCCEEDED'>Map update succeeded</option><option value='MAP_UPDATE_FAILED'>Map update failed</option><option value='DOWNLOAD_STARTED'>Download started</option><option value='DOWNLOAD_PROCESSING'>Checking / unpacking</option><option value='DOWNLOAD_CANCELLED'>Download cancelled</option><option value='DOWNLOAD_INTERRUPTED'>Download interrupted</option></select></label><label><span class='sr-only'>Outcome</span><select id='map-statistics-outcome' name='outcome'><option value=''>All outcomes</option><option value='SUCCEEDED'>Succeeded</option><option value='FAILED'>Failed</option><option value='UNKNOWN'>Unknown</option></select></label><button type='submit'>Apply</button></div></details><p class='results-count' id='map-statistics-status' aria-live='polite'>{event_status}</p>{"<a class='secondary-button filter-clear' href='/admin/map-statistics?period=all'>Clear</a>" if has_active_filters else ""}</form>
        {metrics_section if has_all_time_data else ""}
        {"" if has_event_data else "<section class='map-statistics-empty' aria-live='polite'><h2>No map activity for this scope</h2></section>"}
        {"" if not has_event_data else f"""
        <section class='map-statistics-coverage-layout' id='map-statistics-coverage' aria-label='Installation coverage'><section class='provider-card map-statistics-world-map-card' aria-labelledby='map-statistics-world-map-title'><div class='section-heading'><div><h2 id='map-statistics-world-map-title'>Installations by country</h2></div><p class='table-help' id='map-statistics-world-map-status'>Successful installs</p></div><div class='map-statistics-world-map' id='map-statistics-world-map' role='group' aria-label='World map showing successful installs by country'><div class='world-map-controls' role='group' aria-label='Map navigation'><button type='button' data-map-zoom='in' aria-label='Zoom in'>+</button><button type='button' data-map-zoom='out' aria-label='Zoom out'>−</button><button type='button' data-map-zoom='reset'>Reset map</button><span id='world-map-zoom-status' role='status'>100%</span></div><div class='world-map-svg' id='world-map-svg' tabindex='0' aria-label='Map viewport. Use arrow keys to pan, plus and minus to zoom, or drag the map.'></div><div class='world-map-tooltip' id='world-map-tooltip' role='status' aria-live='polite' hidden></div></div><div class='world-map-legend' aria-label='Installation coverage legend'><span>0</span><i class='world-map-legend-gradient' aria-hidden='true'></i><span id='world-map-legend-max'>Most</span></div></section><section class='provider-card map-statistics-popularity' id='map-statistics-popularity' aria-labelledby='top-countries-title'><div class='section-heading'><h2 id='top-countries-title'>Top countries</h2></div><div class='table-wrap provider-table-wrap'><table class='admin-table popular-maps-table'><caption class='sr-only'>Top countries</caption><thead><tr><th scope='col'>Country</th><th scope='col' class='column-number'>Installs</th></tr></thead><tbody id='map-rows'></tbody></table></div></section></section>
        <section class='provider-card map-statistics-provider-table' id='map-statistics-provider-table' aria-labelledby='provider-statistics-title'><div class='section-heading'><div><h2 id='provider-statistics-title'>Provider comparison</h2></div></div><div class='table-wrap provider-table-wrap' tabindex='0' role='region' aria-label='Provider comparison table'><table class='admin-table mobile-record-table'><caption class='sr-only'>Provider comparison</caption><colgroup span='1'></colgroup><colgroup span='3'></colgroup><colgroup span='3'></colgroup><colgroup span='3'></colgroup><colgroup span='1'></colgroup><thead><tr><th scope='col' rowspan='2'>Provider</th><th scope='colgroup' colspan='3'>Downloads</th><th scope='colgroup' colspan='3'>Installs</th><th scope='colgroup' colspan='3'>Updates</th><th scope='col' rowspan='2' class='column-date'>Last install</th></tr><tr><th scope='col' class='column-number'>Success</th><th scope='col' class='column-number'>Failed</th><th scope='col' class='column-number'>Rate</th><th scope='col' class='column-number'>Success</th><th scope='col' class='column-number'>Failed</th><th scope='col' class='column-number'>Rate</th><th scope='col' class='column-number'>Success</th><th scope='col' class='column-number'>Failed</th><th scope='col' class='column-number'>Rate</th></tr></thead><tbody id='provider-statistic-rows'></tbody></table></div></section>
        <section class='provider-card map-statistics-ranking' aria-labelledby='maps-by-provider-title'><div class='section-heading'><h2 id='maps-by-provider-title'>Maps by provider</h2></div><label class='popularity-search-label' for='all-maps-search'>Search</label><input type='search' id='all-maps-search' placeholder='Map or provider'><div class='table-wrap provider-table-wrap'><table class='admin-table popular-maps-table'><caption class='sr-only'>Maps by provider</caption><thead><tr><th scope='col'>Map</th><th scope='col' class='column-number'>Installs</th></tr></thead><tbody id='all-map-rows'></tbody></table></div><div class='provider-pagination' id='all-maps-pagination' aria-live='polite'><button type='button' id='all-maps-prev'>Previous</button><span id='all-maps-page' role='status'></span><button type='button' id='all-maps-next'>Next</button></div></section>
        <section class='provider-card map-events-card'><details class='admin-disclosure' id='map-statistics-event-detail'{event_detail_open}><summary id='map-statistics-event-summary'>Event detail <span class='disclosure-meta'>· {event_status}</span></summary><div class='disclosure-body' id='map-statistics-event-body'>{event_table}</div></details></section>
        """}
        {trends}
      </main>
      <link rel="stylesheet" href="/admin/map-assets/leaflet-1.9.4.css"><link rel="stylesheet" href="/admin/map-assets/coverage-map-v1.css"><script nonce="{_ADMIN_NONCE_PLACEHOLDER}" src="/admin/map-assets/leaflet-1.9.4.js"></script><script nonce="{_ADMIN_NONCE_PLACEHOLDER}" src="/admin/map-assets/coverage-map-v1.js?v=20260913-coverage-sidebar-3"></script><script>window.terentoMapStatistics = {_admin_json(statistics)};window.terentoAdminProviders = {_admin_json(providers)};window.terentoMapStatisticsFilters = {_admin_json(selected)};window.terentoWorldMapSvg = {_admin_json(WORLD_MAP_SVG)};window.terentoWorldMapCountryAliases = {_admin_json(WORLD_MAP_COUNTRY_ALIASES)};{_map_statistics_script()}</script>
    """
    return _layout("Maps", content, revisions={**statistics_revisions(statistics), **section_revisions({"providers": providers})})


def _provider_detail_script() -> str:
    return r"""(() => {
      const csrf = window.terentoAdminCsrf;
      const status = document.querySelector('#provider-action-status');
      document.querySelectorAll('[data-provider-action]').forEach((button) => {
        button.addEventListener('click', async () => {
          const action = button.dataset.providerAction;
          const id = button.dataset.providerId;
          if (action === 'retire' && !window.confirm('Retire this provider? Historical events and packages will be retained.')) return;
          let reason = '';
          if (action === 'retire' || action === 'state') reason = window.prompt('Reason for this provider status change (optional):', '') || '';
          const body = action === 'state' ? JSON.stringify({status: button.dataset.providerStatus, reason}) : action === 'retire' ? JSON.stringify({reason}) : '{}';
          const original = button.textContent;
          button.disabled = true;
          if (status) status.textContent = `${original}…`;
          try {
            const response = await fetch(`/admin/providers/${encodeURIComponent(id)}/${action}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body});
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(payload.error || `Action failed (${response.status})`);
            if (status) status.textContent = 'Saved. Refreshing…';
            window.location.reload();
          } catch (error) { button.disabled = false; if (status) status.textContent = error.message || 'Provider action failed.'; }
        });
      });
      const setupPagination = ({rowsSelector, searchSelector, filterSelector, pageSizeSelector, paginationSelector, noun}) => {
        const rows = [...document.querySelectorAll(rowsSelector)];
        const search = document.querySelector(searchSelector);
        const filter = document.querySelector(filterSelector);
        const pageSizeControl = document.querySelector(pageSizeSelector);
        const pagination = document.querySelector(paginationSelector);
        if (!pagination) return;
        if (!rows.length) { pagination.hidden = true; return; }
        pagination.hidden = false;
        let page = 0;
        const refresh = () => {
          const pageSize = Number(pageSizeControl?.value || 25) === 50 ? 50 : 25;
          const query = (search?.value || '').trim().toLocaleLowerCase();
          const brokenOnly = filter?.value === 'broken';
          const visible = rows.filter((row) => {
            const matchesSearch = !query || (row.dataset[`${noun}Search`] || '').includes(query);
            const matchesFilter = !brokenOnly || row.dataset[`${noun}Broken`] === 'true';
            return matchesSearch && matchesFilter;
          });
          const pages = Math.max(1, Math.ceil(visible.length / pageSize));
          page = Math.min(page, pages - 1);
          rows.forEach((row) => { row.hidden = true; });
          visible.slice(page * pageSize, (page + 1) * pageSize).forEach((row) => { row.hidden = false; });
          if (!visible.length) {
            pagination.innerHTML = `<span class="muted-value">No matching ${noun}s.</span>`;
            return;
          }
          const start = page * pageSize + 1;
          const end = Math.min((page + 1) * pageSize, visible.length);
          pagination.innerHTML = `<button type="button" data-page="previous" aria-label="Previous ${noun}s" ${page === 0 ? 'disabled' : ''}>Previous</button><span>Showing ${start}–${end} of ${visible.length} · page ${page + 1} of ${pages}</span><button type="button" data-page="next" aria-label="Next ${noun}s" ${page >= pages - 1 ? 'disabled' : ''}>Next</button>`;
          pagination.querySelector('[data-page="previous"]')?.addEventListener('click', () => { page -= 1; refresh(); });
          pagination.querySelector('[data-page="next"]')?.addEventListener('click', () => { page += 1; refresh(); });
        };
        search?.addEventListener('input', () => { page = 0; refresh(); });
        filter?.addEventListener('change', () => { page = 0; refresh(); });
        pageSizeControl?.addEventListener('change', () => { page = 0; refresh(); });
        refresh();
      };
      setupPagination({rowsSelector: '#provider-download-source-rows tr[data-source-search]', searchSelector: '#provider-source-search', filterSelector: '#provider-source-filter', pageSizeSelector: '#provider-source-page-size', paginationSelector: '#provider-source-pagination', noun: 'source'});
      setupPagination({rowsSelector: '#provider-package-rows tr[data-package-search]', searchSelector: '#provider-package-search', filterSelector: '#provider-package-filter', pageSizeSelector: '#provider-package-page-size', paginationSelector: '#provider-package-pagination', noun: 'package'});
    })();"""


def _map_statistics_script() -> str:
    return r"""(() => {
      const payload = window.terentoMapStatistics || {rows: []};
      const rows = Array.isArray(payload.rows) ? payload.rows : [];
      const providers = window.terentoAdminProviders || [];
      const filters = window.terentoMapStatisticsFilters || {};
      const form = document.querySelector('#map-statistics-filters');
      const range = document.querySelector('#map-statistics-range');
      const provider = document.querySelector('#map-statistics-provider');
      const map = document.querySelector('#map-statistics-map');
      const region = document.querySelector('#map-statistics-region');
      const event = document.querySelector('#map-statistics-event');
      const outcome = document.querySelector('#map-statistics-outcome');
      const moreFilters = document.querySelector('#map-statistics-more-filters');
      const worldMap = document.querySelector('#map-statistics-world-map');
      const worldMapSvg = document.querySelector('#world-map-svg');
      const worldMapTooltip = document.querySelector('#world-map-tooltip');
      const worldMapStatus = document.querySelector('#map-statistics-world-map-status');
      const worldMapLegendMax = document.querySelector('#world-map-legend-max');
      const allMapsSearch = document.querySelector('#all-maps-search');
      const allMapsPagination = document.querySelector('#all-maps-pagination');
      const eventDetail = document.querySelector('#map-statistics-event-detail');
      const providerName = Object.fromEntries(providers.map((item) => [item.id, item.name || item.id]));
      const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
      const humanize = (value) => String(value || '—').replace(/[-_]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
      const operations = (row) => {
        if (row.operation_count === null || row.operation_count === undefined) return null;
        const value = Number(row.operation_count);
        return Number.isFinite(value) && value >= 0 ? value : null;
      };
      const countValue = (value) => value === null || value === undefined ? '—' : String(value);
      const addValue = (target, key, value) => { target[key] = target[key] === null || value === null ? null : target[key] + value; };
      const addOperation = (target, key, row) => addValue(target, key, operations(row));
      const formatRate = (value) => value === null || value === undefined ? '—' : `${Number(value).toFixed(Number(value) % 1 ? 1 : 0)}%`;
      const formatTimestamp = (value) => {
        if (!value) return '—';
        if (typeof window.TerentoAdminTime?.format === 'function') return window.TerentoAdminTime.format(value);
        const normalized = typeof value === 'string' ? value.trim().replace(/^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2})/, '$1T$2') : value;
        const date = new Date(normalized);
        return Number.isNaN(date.getTime()) ? String(value) : date.toISOString().slice(0, 16).replace('T', ' ');
      };
      const countryAliases = window.terentoWorldMapCountryAliases || {};
      const regionCountryAliases = {CANADAEAST:'ca',CANADAWEST:'ca',USMIDWEST:'us',USNORTHEAST:'us',USPACIFIC:'us',USSOUTH:'us',USWEST:'us'};
      const countryNames = {};
      Object.entries(countryAliases).forEach(([key, code]) => { if (key.length > 3 && !countryNames[code]) countryNames[code] = humanize(key.toLowerCase()); });
      if (typeof Intl.DisplayNames === 'function') {
        const displayNames = new Intl.DisplayNames(['en'], {type: 'region'});
        Object.values(countryAliases).forEach((code) => { countryNames[code] = displayNames.of(code.toUpperCase()) || countryNames[code]; });
      }
      const countryCode = (row) => {
        for (const candidate of [row.region_country, row.canonical_region_id, row.region_identity, row.region, row.region_display_name]) {
          const token = String(candidate || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9]+/g, '').toUpperCase();
          const resolved = countryAliases[token] || regionCountryAliases[token] || (/^[A-Z]{2}$/.test(token) ? token.toLowerCase() : null);
          if (resolved) return resolved;
        }
        return null;
      };
      const installRows = rows.filter((row) => row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED');
      let coverageMap = null;
      const countryCoverage = () => {
        const byCountry = {};
        installRows.forEach((row) => {
          const code = countryCode(row);
          if (!code) return;
          const providerId = row.provider_id || 'unknown';
          byCountry[code] ||= {code, name: countryNames[code], count: 0, providers: {}};
          addOperation(byCountry[code], 'count', row);
          byCountry[code].providers[providerId] ||= {id: providerId, count: 0};
          addOperation(byCountry[code].providers[providerId], 'count', row);
        });
        return Object.values(byCountry).sort((a, b) => (b.count ?? -1) - (a.count ?? -1) || a.name.localeCompare(b.name));
      };
      const showWorldMapTooltip = (item, code) => {
        if (!worldMapTooltip) return;
        const providerLines = item?.providers ? Object.values(item.providers).sort((a,b) => (b.count ?? -1) - (a.count ?? -1)).map((entry) => `<div class="world-map-provider-line"><span>${escapeHtml(providerName[entry.id] || entry.id)}</span><strong>${countValue(entry.count)}</strong></div>`).join('') : '';
        worldMapTooltip.innerHTML = `<strong>${escapeHtml(item?.name || countryNames[code] || code.toUpperCase())}</strong><span class="world-map-tooltip-total">${countValue(item?.count)} completed installs</span>${providerLines}`;
        worldMapTooltip.hidden = false;
      };
      const renderWorldMap = () => {
        if (!worldMapSvg || typeof window.TerentoCoverageMap !== 'function') return;
        coverageMap ||= new window.TerentoCoverageMap(worldMapSvg, {
          svg: window.terentoWorldMapSvg, names: countryNames,
          onCountry: (item, code) => { if (code) showWorldMapTooltip(item, code); else if (worldMapTooltip) worldMapTooltip.hidden = true; },
          onZoom: (zoom, initial) => { const status = document.querySelector('#world-map-zoom-status'); if (status) status.textContent = `${Math.round(Math.pow(2, zoom - initial) * 100)}%`; }
        });
        const items = countryCoverage().filter((item) => coverageMap.codes.has(item.code));
        coverageMap.update(items);
        const total = items.some((item) => item.count === null) ? null : items.reduce((sum, item) => sum + item.count, 0);
        if (worldMapStatus) worldMapStatus.textContent = total === null ? 'Country coverage is partially unavailable' : `${items.length} ${items.length === 1 ? 'country' : 'countries'} · ${total} installs`;
        if (worldMapLegendMax) worldMapLegendMax.textContent = String(Math.max(0, ...items.map((item) => item.count || 0))) || 'Most';
        if (worldMap) worldMap.dataset.countryCount = String(items.length);
      };
      document.querySelectorAll('[data-map-zoom]').forEach((button) => button.addEventListener('click', () => coverageMap?.zoom(button.dataset.mapZoom)));
      const renderProviders = () => {
        const selected = String(filters.provider || '').toLowerCase();
        const scoped = selected ? providers.filter((item) => String(item.id || '').toLowerCase() === selected) : providers;
        const byProvider = Object.fromEntries(scoped.map((item) => [item.id, {downloads:0,failedDownloads:0,installs:0,failedInstalls:0,completedUpdates:0,failedUpdates:0,lastInstall:null}]));
        rows.forEach((row) => {
          const id = row.provider_id || 'unknown';
          byProvider[id] ||= {downloads:0,failedDownloads:0,installs:0,failedInstalls:0,completedUpdates:0,failedUpdates:0,lastInstall:null};
          if (row.event_type === 'DOWNLOAD_SUCCEEDED' && row.outcome === 'SUCCEEDED') addOperation(byProvider[id], 'downloads', row);
          if (row.event_type === 'DOWNLOAD_FAILED' && row.outcome === 'FAILED') addOperation(byProvider[id], 'failedDownloads', row);
          if (row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED') { addOperation(byProvider[id], 'installs', row); if (String(row.last_occurred_at || '') > String(byProvider[id].lastInstall || '')) byProvider[id].lastInstall = row.last_occurred_at; }
          if (row.event_type === 'INSTALL_FAILED' && row.outcome === 'FAILED') addOperation(byProvider[id], 'failedInstalls', row);
          if (row.event_type === 'MAP_UPDATE_SUCCEEDED' && row.outcome === 'SUCCEEDED') addOperation(byProvider[id], 'completedUpdates', row);
          if (row.event_type === 'MAP_UPDATE_FAILED' && row.outcome === 'FAILED') addOperation(byProvider[id], 'failedUpdates', row);
        });
        const rate = (success, failed) => success !== null && failed !== null && success + failed ? success / (success + failed) * 100 : null;
        const labels = ['Provider','Downloads · Success','Downloads · Failed','Downloads · Rate','Installs · Success','Installs · Failed','Installs · Rate','Updates · Success','Updates · Failed','Updates · Rate','Last install'];
        const body = document.querySelector('#provider-statistic-rows');
        if (!body) return;
        body.innerHTML = Object.entries(byProvider).map(([id, item]) => {
          const values = [providerName[id] || id,item.downloads,item.failedDownloads,formatRate(rate(item.downloads,item.failedDownloads)),item.installs,item.failedInstalls,formatRate(rate(item.installs,item.failedInstalls)),item.completedUpdates,item.failedUpdates,formatRate(rate(item.completedUpdates,item.failedUpdates)),formatTimestamp(item.lastInstall)];
          const emptyGroups = {
            downloads: item.downloads === 0 && item.failedDownloads === 0,
            installs: item.installs === 0 && item.failedInstalls === 0,
            updates: item.completedUpdates === 0 && item.failedUpdates === 0,
          };
          return `<tr>${values.map((value, index) => index === 0
            ? `<td>${escapeHtml(countValue(value))}</td>`
            : `<td data-label="${labels[index]}"${index < 10 ? ` data-empty-group="${index <= 3 ? emptyGroups.downloads : index <= 6 ? emptyGroups.installs : emptyGroups.updates}"` : ''} class="${index === 10 ? 'column-date' : 'column-number numeric'}">${escapeHtml(countValue(value))}</td>`
          ).join('')}</tr>`;
        }).join('');
      };
      const knownProviderIds = new Set(providers.map((item) => String(item.id || '')).filter(Boolean));
      const byMap = {};
      rows.filter((row) => row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED' && row.map_package_id && knownProviderIds.has(String(row.provider_id || '')) && (!row.component_kind || row.component_kind === 'main')).forEach((row) => {
        const providerId = String(row.provider_id || '');
        const regionIdentity = row.region_identity || row.canonical_region_id || row.region || 'UNKNOWN';
        const key = `${regionIdentity}\u0000${providerId}`;
        byMap[key] ||= {regionIdentity, regionName:row.region_display_name || humanize(row.region),provider:providerId,country:countryCode(row),installs:0,lastInstall:null};
        addOperation(byMap[key], 'installs', row);
        if (String(row.last_occurred_at || '') > String(byMap[key].lastInstall || '')) byMap[key].lastInstall = row.last_occurred_at;
      });
      const allMapItems = Object.values(byMap).filter((item) => item.installs > 0).sort((a,b) => b.installs - a.installs || a.regionName.localeCompare(b.regionName) || a.provider.localeCompare(b.provider));
      const mapRow = (item, providerDetail = false) => {
        const label = item.regionName || '—';
        const mapLink = item.country ? `<button type="button" class="region-map-link" data-map-country="${escapeHtml(item.country)}">${escapeHtml(label)}</button>` : escapeHtml(label);
        const detail = providerDetail ? `${providerName[item.provider] || item.provider} · ${formatTimestamp(item.lastInstall)}` : formatTimestamp(item.lastInstall);
        return `<tr class="popular-map-row"><td data-label="${providerDetail ? 'Map' : 'Country'}"><div class="popular-map-name-content">${mapLink}<small class="popular-map-detail">${escapeHtml(detail)}</small></div></td><td data-label="Installs" class="column-number numeric popular-map-count"><strong>${item.installs}</strong></td></tr>`;
      };
      const topBody = document.querySelector('#map-rows');
      if (topBody) topBody.innerHTML = countryCoverage().slice(0,5).map((item) => `<tr class="popular-map-row"><td data-label="Country"><button type="button" class="region-map-link" data-map-country="${escapeHtml(item.code)}">${escapeHtml(item.name || item.code.toUpperCase())}</button></td><td data-label="Installs" class="column-number numeric popular-map-count"><strong>${countValue(item.count)}</strong></td></tr>`).join('') || '<tr><td colspan="2" class="muted-value">No country activity.</td></tr>';
      let page = 1;
      const renderRanking = () => {
        const query = String(allMapsSearch?.value || '').toLowerCase().trim();
        const matches = allMapItems.filter((item) => `${item.regionName} ${providerName[item.provider] || item.provider}`.toLowerCase().includes(query));
        const pages = Math.max(1, Math.ceil(matches.length / 10)); page = Math.min(page, pages);
        const body = document.querySelector('#all-map-rows'); if (body) body.innerHTML = matches.slice((page-1)*10,page*10).map((item) => mapRow(item,true)).join('') || '<tr><td colspan="2" class="muted-value">No maps match.</td></tr>';
        const summary = document.querySelector('#all-maps-page'); if (summary) summary.textContent = `${matches.length} ${matches.length === 1 ? 'map' : 'maps'} · page ${page} of ${pages}`;
        const previous = document.querySelector('#all-maps-prev'); const next = document.querySelector('#all-maps-next');
        if (previous) previous.disabled = page <= 1; if (next) next.disabled = page >= pages;
        if (allMapsPagination) allMapsPagination.hidden = matches.length <= 10;
        document.querySelectorAll('[data-map-country]').forEach((button) => {
          button.onmouseenter = button.onfocus = () => coverageMap?.highlight(button.dataset.mapCountry);
          button.onmouseleave = button.onblur = () => coverageMap?.highlight(null);
          button.onclick = () => coverageMap?.highlight(button.dataset.mapCountry, true);
        });
      };
      allMapsSearch?.addEventListener('input', () => { page = 1; renderRanking(); });
      document.querySelector('#all-maps-prev')?.addEventListener('click', () => { page--; renderRanking(); });
      document.querySelector('#all-maps-next')?.addEventListener('click', () => { page++; renderRanking(); });
      if (range) range.value = filters.period || 'all';
      if (provider && filters.provider) provider.value = filters.provider;
      if (map) map.value = filters.map || '';
      if (region) region.value = filters.region || '';
      if (event) event.value = filters.eventType || '';
      if (outcome) outcome.value = filters.outcome || '';
      if (moreFilters && (filters.map || filters.region || filters.eventType || filters.outcome || filters.eventId)) moreFilters.open = true;
      [range, provider].forEach((control) => control?.addEventListener('change', () => form?.requestSubmit()));
      window.addEventListener('terento-admin-timezone-ready', () => { renderProviders(); renderRanking(); });
      window.addEventListener('terento-admin-timezone-change', () => { renderProviders(); renderRanking(); });
      renderProviders(); renderWorldMap(); renderRanking();
      if (filters.eventId && eventDetail) { eventDetail.open = true; eventDetail.scrollIntoView?.({block:'start'}); eventDetail.querySelector('summary')?.focus({preventScroll:true}); }
    })();"""


def _display_identity(identity: str, row: dict[str, Any] | None = None) -> tuple[str, str]:
    clean = re.sub(
        r"^(?:Identity pending|Identity unresolved|Identity not identifiable|Identity resolved)\s*[·•]\s*",
        "",
        identity.strip(),
        flags=re.IGNORECASE,
    ).strip()
    if row:
        model, variant, _ = _identity_parts({**row, "compatibility_identity": clean})
        if model != "—":
            return model, variant
    model, variant, _ = _identity_parts({"model": clean, "compatibility_identity": clean})
    return model, variant


def _known_variant_description(row: dict) -> str:
    return variant_label(row) or "—"


def _identification_label(device: dict) -> str:
    model, variant, _ = _identity_parts(device)
    return model + (" · " + variant if variant != "—" else "")


def _identification_badge(state: str, label: str) -> str:
    icon = {'approved': '✓', 'rejected': '✕', 'pending': '!', 'missing': '?', 'shared': '↔'}[state]
    return f"<span class='identification-badge identification-{state}'><span aria-hidden='true'>{icon}</span> {html.escape(label)}</span>"


def _identification_summary(mappings: list[dict]) -> str:
    if not mappings:
        return _identification_badge('missing', 'No code sources')
    labels = (
        ('PENDING', 'pending', 'Needs review'),
        ('APPROVED', 'approved', 'Approved'),
        ('REJECTED', 'rejected', 'Rejected'),
    )
    return "<span class='identification-badges'>" + ''.join(
        _identification_badge(style, label)
        for state, style, label in labels
        if any(mapping.get('status') == state for mapping in mappings)
    ) + '</span>'


def _identity_mapping_markup(device: dict, csrf_token: str, *, code_models: dict | None = None) -> str:
    groups: dict[tuple[str, str], list[dict]] = {}
    for mapping in device.get("identityMappings", []):
        groups.setdefault((mapping['kind'], mapping['value']), []).append(mapping)
    if not groups:
        return "<div class='identification-empty'><h2>No source reported</h2><p>No imported source identity is available for this model.</p></div>"
    labels = {'RETAIL_SKU': 'Retail product code', 'XML_PART_NUMBER': 'Watch product code', 'USB': 'USB connection code'}
    decisions = {'PENDING': 'Needs review', 'APPROVED': 'Approved', 'REJECTED': 'Rejected'}
    label = html.escape(_identification_label(device))
    map_label, _ = _admin_map_capability(device.get('mapCapable'))
    map_fact = f"<span>Maps: {html.escape(map_label)}</span>" if device.get('mapCapable') is not None else ''
    items: list[str] = []
    technical_items: list[str] = []
    technical_number = 0
    for (kind, value), group in sorted(groups.items(), key=lambda item: (not any(m['status'] == 'PENDING' for m in item[1]), ({'XML_PART_NUMBER': 0, 'USB': 1, 'RETAIL_SKU': 2}.get(item[0][0], 3), item[0][1]))):
        peers = (code_models or {}).get((kind, value), {})
        others = [(key, peer) for key, peer in peers.items() if str(key) != str(device['id'])]
        other_models = ''
        if others:
            links = ''.join(
                f"<li><a href='/admin/device-identification?{urlencode({'device': key})}'>{html.escape(peer['label'])}</a>"
                f"<span>{html.escape(' / '.join(decisions.get(mapping.get('status'), str(mapping.get('status') or '').title()) for mapping in peer['mappings']))}</span></li>"
                for key, peer in others
            )
            other_models = f"<section class='identification-step identification-other-models'><h3>Other models using this code</h3><ul>{links}</ul></section>"
        for mapping_index, mapping in enumerate(sorted(group, key=lambda m: m['status'] != 'PENDING')):
            raw_source = str(mapping['source_url'])
            source_host = (urlsplit(raw_source).hostname or '').removeprefix('www.')
            source_link = (
                f'<a class="section-link" href="{html.escape(raw_source, quote=True)}" target="_blank" rel="noopener noreferrer">Open {html.escape(source_host or "source")} ↗</a>'
                if raw_source.startswith('https://') else '<span class="identification-source-unavailable">Source link unavailable</span>'
            )
            names = html.escape('; '.join(mapping.get('source_names') or [])) or 'No model name supplied'
            current_decision = ''
            if mapping['status'] != 'PENDING':
                reviewed = f" · {_timestamp_markup(mapping.get('reviewed_at'))}" if mapping.get('reviewed_at') else ''
                reason = html.escape(str(mapping.get('review_reason') or 'No reason recorded'))
                current_decision = f"<p class='identification-existing-decision'><strong>Current decision:</strong> {decisions[mapping['status']]} · {reason}{reviewed}</p>"
            items.append(f"""<article class='identity-mapping-source'>
            <section class='identification-step'><h3>Source reported</h3><strong class='identification-reported-name'>{names}</strong><div class='identification-source-link'>{source_link}</div></section>
            <section class='identification-step identification-match'><h3>Match to</h3><strong>{label}</strong>{map_fact}</section>
            {other_models if mapping_index == 0 else ''}
            <section class='identification-step identification-confirm'><h3>Confirm match</h3>{current_decision}
            <form method='post' action='/admin/devices/identity-mapping' class='admin-async-action identity-mapping-review'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='mapping_id' value='{int(mapping['id'])}'>
            <input type='hidden' name='return_to' value='/admin/device-identification?device={quote(str(device['id']), safe='')}'>
            <label>Decision note<textarea name='reason' required maxlength='1000' rows='2' placeholder='Name the source evidence that supports this decision.'></textarea></label>
            <div class='identification-decision-actions'><button type='submit' name='status' value='APPROVED'>Approve match</button><button class='secondary-button' type='submit' name='status' value='REJECTED'>Reject match</button></div>
            <p class='admin-action-status' role='status' aria-live='polite'></p></form></section></article>""")

            technical_number += 1
            history = ''.join(
                '<li>' + html.escape(f"{entry['previous_status']} → {entry['new_status']} · {entry['reason']} · {'administrator ' + str(entry['reviewed_by']) if entry['reviewed_by'] is not None else 'catalog import'} · {entry['created_at']}") + '</li>'
                for entry in mapping.get('history') or []
            ) or '<li>No previous decisions</li>'
            technical_items.append(
                f"<section><h4>Source {technical_number}</h4><dl class='model-information-list'>"
                f"<div><dt>Code type</dt><dd>{html.escape(labels.get(kind, kind))}</dd></div>"
                f"<div><dt>Raw code</dt><dd><code>{html.escape(value)}</code></dd></div>"
                f"<div><dt>Catalog model ID</dt><dd><code>{html.escape(str(device['id']))}</code></dd></div>"
                f"<div><dt>Mapping ID</dt><dd><code>{int(mapping['id'])}</code></dd></div>"
                f"<div><dt>Source URL</dt><dd><code>{html.escape(raw_source)}</code></dd></div>"
                f"<div><dt>Source revision</dt><dd>{html.escape(str(mapping.get('source_version') or 'Unavailable'))}</dd></div>"
                f"</dl><h4>Decision history</h4><ul>{history}</ul></section>"
            )
    mappings = device.get('identityMappings') or []
    missing = [name for kind, name in [('XML_PART_NUMBER', 'watch product code'), ('USB', 'USB connection code')] if not any(mapping['kind'] == kind for mapping in mappings)]
    missing_note = f"<p><strong>Missing imported sources:</strong> {html.escape(' and '.join(missing))}.</p>" if missing else ''
    technical = (
        "<details class='admin-disclosure identification-technical'><summary>Technical details</summary><div class='disclosure-body'>"
        + missing_note
        + "<p>Each decision updates only its imported source link. It does not change installations, installation permission or public compatibility.</p>"
        + ''.join(technical_items)
        + "</div></details>"
    )
    return "<div class='identity-mappings'>" + ''.join(items) + technical + '</div>'


def device_identification_page(devices: list[dict], user: dict, csrf_token: str, *, device_id: str = "", query: str = "") -> bytes:
    selected = next((d for d in devices if str(d.get('id')) == device_id), None)
    code_models: dict = {}
    for device in devices:
        for mapping in device.get('identityMappings') or []:
            peer = code_models.setdefault((mapping['kind'], mapping['value']), {}).setdefault(str(device['id']), {'label': _identification_label(device), 'mappings': []})
            peer['mappings'].append(mapping)
    choices = []
    ordered = sorted(devices, key=lambda d: (not any(m['status'] == 'PENDING' for m in d.get('identityMappings') or []), _identification_label(d).casefold()))
    for device in ordered:
        label = _identification_label(device)
        mappings = device.get('identityMappings') or []
        searchable = ' '.join([label] + [str(m['value']) for m in mappings])
        if query and query.casefold() not in searchable.casefold():
            continue
        choices.append(f"<a class='identification-choice' href='/admin/device-identification?{urlencode({'device': device['id']})}'><span class='identification-choice-title'><strong>{html.escape(label)}</strong><span>Review source match →</span></span>{_identification_summary(mappings)}</a>")
    pending_models = sum(any(m['status'] == 'PENDING' for m in d.get('identityMappings') or []) for d in devices)
    pending_label = '1 model needs source review.' if pending_models == 1 else f'{pending_models} models need source review.'
    if selected:
        content = f"<section class='overview-panel identification-workspace'><a class='section-link' href='/admin/device-identification'>← Back to model list</a>{_identity_mapping_markup(selected, csrf_token, code_models=code_models)}<a class='section-link identification-model-detail-link' href='/admin/devices/{quote(str(selected['id']), safe='')}'>View model details and installation evidence →</a></section>"
    else:
        empty = f"<div class='identification-empty'><h3>No matching models.</h3><p>No model or code matches “{html.escape(query)}”. Try a shorter model name or clear the search.</p><a class='section-link' href='/admin/device-identification'>Clear search</a></div>" if query else "<div class='identification-empty'><h3>No models available</h3><p>Run the device catalog collection, then return here to review its sources.</p><a class='section-link' href='/admin/devices'>Open device catalog</a></div>"
        invalid = "<p class='identification-not-found' role='alert'>This model is unavailable. Search the catalog below and select an existing model.</p>" if device_id else ''
        content = f"<section class='overview-panel identification-workspace'>{invalid}<h2>Select a model</h2><p><strong>{pending_label}</strong> Pending decisions appear first.</p><form method='get' class='identification-search'><label for='identification-search'>Find a model or code<input id='identification-search' name='q' placeholder='For example, fēnix 8 or 006-B…' value='{html.escape(query, quote=True)}'></label><button class='secondary-button' type='submit'>Search</button></form><div class='identification-choices'>{''.join(choices) or empty}</div></section>"
    body = _admin_header(user, csrf_token, active='device-identification') + "<main id='main-content' class='dashboard identification-page'><h1>Model source review</h1>" + content + '</main>'
    return _layout('Model source review', body + '<script>' + _identification_review_script() + '</script>', sections={'identification': devices})



def _identification_review_script() -> str:
    return r"""(() => {
      document.querySelectorAll('.identity-mapping-review').forEach(form => {
        form.addEventListener('submit', async event => {
          event.preventDefault();
          if (form.dataset.submitting === 'true') return;
          const payload = new URLSearchParams(new FormData(form, event.submitter));
          const controls = [...form.querySelectorAll('button,input,select,textarea')];
          const status = form.querySelector('.admin-action-status');
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 20000);
          form.dataset.submitting = 'true';
          form.setAttribute('aria-busy', 'true');
          controls.forEach(control => control.disabled = true);
          status.dataset.error = 'false';
          status.textContent = 'Saving source decision…';
          try {
            const response = await fetch(form.action, {method:'POST', body:payload,
              credentials:'same-origin', signal:controller.signal});
            if (!response.ok) throw new Error('save');
            if (response.redirected && new URL(response.url).pathname === '/admin/login') {
              status.textContent = 'Your session expired. Open this page in another tab to sign in, then retry. Your text is kept here.';
              status.dataset.error = 'true';
              return;
            }
            if (!response.redirected) throw new Error('save');
            window.location.assign(response.url);
          } catch (_) {
            status.dataset.error = 'true';
            status.textContent = 'Could not confirm the save. Your text is kept here. Check your connection and the current decision in another tab before retrying.';
          } finally {
            clearTimeout(timeout);
            controls.forEach(control => control.disabled = false);
            form.dataset.submitting = 'false';
            form.removeAttribute('aria-busy');
          }
        });
      });
    })();"""


def _identity_presentation_candidates(assessment: dict) -> list[dict]:
    """Prefer explicitly observed features over less-specific catalog rows.

    This narrows operator suggestions only. The authoritative assessment retains
    every candidate and never treats an unknown feature as a negative fact.
    """
    candidates = [c for c in assessment.get("candidates", [])
                  if not c.get("conflict") and c.get("checks")
                  and not any(k.get("state") == "CONFLICT" for k in c["checks"])]
    for feature_name in ("inreach", "solar"):
        explicit = [c for c in candidates if any(
            f.get("name") == feature_name and f.get("expected") is True
            and any(e.get("source") == "model text" and e.get("value") is True for e in f.get("evidence", []))
            for k in c["checks"] for f in k.get("features", []))]
        if explicit:
            candidates = explicit
    return candidates


def _identity_recommendation(results: list[dict[str, Any]]) -> dict | None:
    """Recommend only a single non-conflicting target shared by every report."""
    choices = []
    for result in results:
        assessment = result.get("current_identity_assessment") or result.get("identity_assessment") or {}
        possible = _identity_presentation_candidates(assessment)
        if len(possible) != 1:
            return None
        choices.append(possible[0])
    return choices[0] if choices and len({c["deviceId"] for c in choices}) == 1 else None


def _identity_assessments(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r.get("current_identity_assessment") or r.get("identity_assessment") or {} for r in results]


def _identity_selected_id(results: list[dict[str, Any]]) -> str | None:
    return next((str(r.get("canonical_device_model_id")).strip() for r in results
                 if str(r.get("canonical_device_model_id") or "").strip()), None)


def _identity_candidate(results: list[dict[str, Any]], device_id: str | None = None) -> dict[str, Any] | None:
    target = device_id or _identity_selected_id(results)
    if target:
        for assessment in _identity_assessments(results):
            candidate = next((c for c in assessment.get("candidates", []) if c.get("deviceId") == target), None)
            if candidate:
                return candidate
        # A selected catalog ID must not borrow the facts of a different
        # suggested candidate when an old assessment lacks that ID.
        return None
    return _identity_recommendation(results)


def _identity_check(candidate: dict[str, Any] | None, name: str) -> dict[str, Any]:
    return next((check for check in (candidate or {}).get("checks", []) if check.get("name") == name), {})


def _identity_feature(candidate: dict[str, Any] | None, name: str) -> dict[str, Any]:
    return next((feature for check in (candidate or {}).get("checks", [])
                 for feature in check.get("features", []) if feature.get("name") == name), {})


def _identity_conflict_lines(
    results: list[dict[str, Any]], selected_id: str | None,
    identity_devices: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Render every concrete selected-model conflict across all result rows."""
    if not selected_id:
        return []
    devices = {
        str(device.get("id") or device.get("device_id") or ""): device
        for device in identity_devices or []
    }
    selected_device = devices.get(str(selected_id))
    selected_label = _identity_device_label(selected_device) if selected_device else "selected catalog model"
    field_labels = {
        "model": "Model", "size": "Case size", "screen": "Display",
        "solar": "Solar", "inreach": "inReach", "xmlPartNumber": "Product mapping",
        "usb": "USB mapping",
    }
    lines: list[str] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for result_index, result in enumerate(results, start=1):
        assessment = result.get("current_identity_assessment") or result.get("identity_assessment") or {}
        candidate = next((item for item in assessment.get("candidates", [])
                          if str(item.get("deviceId") or "") == str(selected_id)), None)
        if not candidate:
            continue
        result_id = str(result.get("event_id") or "").strip()
        result_label = f"Diagnostic result {result_id}" if result_id else f"Diagnostic result {result_index}"

        def add(field: str, reported: Any, source: Any, *, mapping_models: list[str] | None = None) -> None:
            reported_text = "Not reported" if reported is None or reported == "" else str(reported)
            source_text = str(source or "reported data")
            mappings_text = ", ".join(mapping_models or [])
            key = (result_label, field, reported_text, source_text, mappings_text)
            if key in seen:
                return
            seen.add(key)
            line = (f"{result_label}: {field_labels.get(field, field)}: reported "
                    f"{reported_text} from {source_text}; selected model {selected_label}.")
            if mappings_text:
                line += f" Approved mapping models for this code: {mappings_text}."
            lines.append(line)

        for check in candidate.get("checks", []):
            name = str(check.get("name") or "")
            if (check.get("state") == "CONFLICT" and name == "model"
                    and check.get("observedState", check.get("state")) == "CONFLICT"):
                for evidence in check.get("evidence") or []:
                    if evidence.get("value") != check.get("expected"):
                        add(name, evidence.get("value"), evidence.get("source"))
            if check.get("state") == "CONFLICT" and name in {"size", "screen"}:
                for evidence in check.get("evidence") or []:
                    if evidence.get("value") != check.get("expected"):
                        add(name, evidence.get("value"), evidence.get("source"))
            if check.get("state") == "CONFLICT" and name not in {"model", "size", "screen", "xmlPartNumber", "usb"}:
                for evidence in check.get("evidence") or []:
                    add(name, evidence.get("value"), evidence.get("source"))
            if check.get("state") == "CONFLICT" and name in {"xmlPartNumber", "usb"}:
                mapping_models = [
                    _identity_device_label(devices.get(str(evidence.get("deviceId") or "")))
                    for evidence in check.get("evidence") or []
                    if str(evidence.get("deviceId") or "") in devices
                ]
                add(name, check.get("value"), check.get("codeKind") or name,
                    mapping_models=[label for label in mapping_models if label != "selected catalog model"])
            for feature in check.get("features") or []:
                if feature.get("state") == "CONFLICT":
                    for evidence in feature.get("evidence") or []:
                        if evidence.get("value") != feature.get("expected"):
                            add(str(feature.get("name") or "feature"), evidence.get("value"), evidence.get("source"))
    return lines


def _identity_source_label(evidence: list[dict[str, Any]] | None) -> str:
    sources = [str(item.get("source") or "") for item in evidence or []]
    has_catalog = any(source.startswith("catalog specification:") for source in sources)
    has_mapping = any(":" in source and source.split(":", 1)[0] in {"USB", "XML_PART_NUMBER", "RETAIL_SKU"} for source in sources)
    if has_catalog and has_mapping:
        return "From catalog / mapping"
    if has_catalog:
        return "From catalog"
    if has_mapping:
        return "From mapping"
    return "Reported" if evidence else "Not confirmed"


def _identity_evidence_values(check: dict[str, Any]) -> list[Any]:
    return list(dict.fromkeys(item.get("value") for item in check.get("evidence", [])
                             if item.get("value") is not None))


def _identity_value(value: Any, *, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not reported"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return f"{value}{suffix}"


def _identity_fact_markup(label: str, value: str, state: str, source: str) -> str:
    icon = {"match": "✓", "conflict": "!", "missing": "?"}.get(state, "?")
    return (f"<article class='identity-fact identity-fact-{state}'>"
            f"<div class='identity-fact-heading'><span class='identity-fact-icon' aria-hidden='true'>{icon}</span><span>{html.escape(label)}</span></div>"
            f"<strong>{html.escape(value)}</strong><small>{html.escape(source)}</small></article>")


def _identity_observations_markup(
    results: list[dict[str, Any]], identity_devices: list[dict[str, Any]] | None = None,
) -> str:
    selected_id = _identity_selected_id(results)
    candidate = _identity_candidate(results, selected_id)
    assessments = _identity_assessments(results)
    def fact_records(name: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for assessment in assessments:
            records.extend(assessment.get("facts", {}).get(name, []) or [])
        return records

    def fact_values(name: str) -> list[Any]:
        values: list[Any] = []
        for record in fact_records(name):
            value = record.get("value")
            if value is not None and value not in values:
                values.append(value)
        return values

    reported_values = list(dict.fromkeys(
        str(result.get(field)).strip() for result in results
        for field in ("raw_mtp_model", "garmin_model_description", "model")
        if str(result.get(field) or "").strip()
    ))
    if not reported_values:
        reported_values = [str(value).strip() for value in fact_values("model") if str(value).strip()]
    reported = reported_values[0] if reported_values else "Not reported"
    reported_markup = "<p class='identity-reported-device'><strong>Reported device:</strong> " + html.escape(reported) + "</p>"
    if len(reported_values) > 1:
        reported_markup += "<p class='identity-reported-also'>Also reported: " + html.escape(" / ".join(reported_values[1:])) + "</p>"

    model_check = _identity_check(candidate, "model")
    model_values = [str(value) for value in _identity_evidence_values(model_check)] if candidate else [str(value) for value in fact_values("model")]
    model_observed_state = model_check.get("observedState", model_check.get("state"))
    model_state = ("conflict" if model_observed_state == "CONFLICT" else "match" if model_observed_state == "MATCH" else "missing") if candidate else ("match" if model_values else "missing")
    model_source = _identity_source_label(model_check.get("evidence")) if candidate else ("Reported" if model_values else "Not confirmed")
    facts = [_identity_fact_markup("Model", " / ".join(model_values) if model_values else "Not reported", model_state, model_source)]
    size_check = _identity_check(candidate, "size")
    size_values = _identity_evidence_values(size_check) if candidate else fact_values("caseSizeMm")
    size_from_catalog = bool(candidate and not size_values and size_check.get("expected") is not None and size_check.get("state") != "CONFLICT")
    facts.append(_identity_fact_markup("Case size", _identity_value(size_values[0] if size_values else size_check.get("expected") if size_from_catalog else None, suffix=" mm"),
                                       ("conflict" if size_check.get("state") == "CONFLICT" else "match" if size_check.get("state") == "MATCH" or size_from_catalog else "missing") if candidate else ("match" if size_values else "missing"),
                                       "From catalog" if size_from_catalog else _identity_source_label(size_check.get("evidence")) if candidate else ("Reported" if size_values else "Not confirmed")))
    screen_check = _identity_check(candidate, "screen")
    screen_values = _identity_evidence_values(screen_check) if candidate else fact_values("screenTechnology")
    screen_from_catalog = bool(candidate and not screen_values and screen_check.get("expected") and screen_check.get("state") != "CONFLICT")
    facts.append(_identity_fact_markup("Display", _identity_value(screen_values[0] if screen_values else screen_check.get("expected") if screen_from_catalog else None),
                                       ("conflict" if screen_check.get("state") == "CONFLICT" else "match" if screen_check.get("state") == "MATCH" or screen_from_catalog else "missing") if candidate else ("match" if screen_values else "missing"),
                                       "From catalog" if screen_from_catalog else _identity_source_label(screen_check.get("evidence")) if candidate else ("Reported" if screen_values else "Not confirmed")))
    for label, feature_name in (("Solar", "solar"), ("inReach", "inreach")):
        feature = _identity_feature(candidate, feature_name)
        fact_name = "inReach" if feature_name == "inreach" else feature_name
        values = _identity_evidence_values(feature) if candidate else fact_values(fact_name)
        from_catalog = bool(candidate and not values and feature.get("expected") is not None and feature.get("state") != "CONFLICT")
        feature_value = values[0] if values else feature.get("expected") if from_catalog else None
        facts.append(_identity_fact_markup(label, _identity_value(feature_value),
                                           "conflict" if feature.get("state") == "CONFLICT" else "match" if from_catalog or feature.get("state") == "MATCH" else "missing" if candidate else ("match" if values else "missing"),
                                           "From catalog" if from_catalog else _identity_source_label(feature.get("evidence")) if candidate else ("Reported" if values else "Not confirmed")))
    code_checks = [_identity_check(candidate, "xmlPartNumber"), _identity_check(candidate, "usb")]
    code_lines = []
    code_states = []
    for label, check in (("Product", code_checks[0]), ("USB", code_checks[1])):
        kind = "RETAIL_SKU" if label == "Product" and check.get("codeKind") == "RETAIL_SKU" else "XML_PART_NUMBER" if label == "Product" else "USB"
        value = check.get("value") if candidate else next((record.get("value") for record in fact_records("codes") if record.get("kind") == kind), None)
        if value is None:
            code_lines.append(f"{label}: Not reported")
        else:
            status = ("mapped" if check.get("state") == "MATCH" else "mapping not confirmed" if check.get("state") != "CONFLICT" else "conflict") if candidate else "received"
            code_lines.append(f"{label}: {value} · {status}")
        code_states.append(check.get("state"))
    code_state = "conflict" if "CONFLICT" in code_states else "match" if "MATCH" in code_states else "missing" if candidate else ("match" if any("Not reported" not in line for line in code_lines) else "missing")
    code_source = "From mapping" if candidate and code_state == "match" else "Reported" if any(check.get("value") is not None for check in code_checks) or fact_values("codes") else "Not confirmed"
    facts.append(_identity_fact_markup("Device codes", " · ".join(code_lines), code_state, code_source))
    selected_device = next((device for device in identity_devices or []
                            if str(device.get("id") or device.get("device_id") or "") == str(selected_id or "")), None)
    selection_label = _identity_device_label(selected_device) if selected_device else (
        _identity_device_label(candidate) if candidate else "No catalog model selected"
    )
    recommendation_label = "Suggested model" if not selected_id else "Selected catalog model"
    status = "Confirmed by administrator" if any(
        isinstance((result.get("identity_decision") or {}).get("decision"), dict)
        for result in results
    ) else "Assigned catalog model" if selected_id else "Suggested model" if candidate else "Select catalog variant"
    if any(assessment.get("candidates") and not _identity_candidate([result]) for result, assessment in zip(results, assessments)):
        status = "Select variant"
    return ("<div class='identity-review-facts'>" + reported_markup
            + "<div class='identity-facts' aria-label='Identity facts'>" + "".join(facts) + "</div>"
            + f"<div class='identity-selected-model'><strong>{html.escape(selection_label)}</strong><small>{html.escape(status)}</small></div>"
            + "</div>")


def _identity_checks_markup(
    results: list[dict[str, Any]], identity_devices: list[dict[str, Any]] | None = None,
) -> str:
    assigned = _identity_selected_id(results)
    candidate = _identity_candidate(results, assigned)
    decision = {}
    for result in results:
        value = (result.get("identity_decision") or {}).get("decision")
        if isinstance(value, dict):
            decision = value
            break
    selected_id = assigned or (str(candidate.get("deviceId")) if candidate else None)
    conflict_lines = _identity_conflict_lines(results, selected_id, identity_devices)
    candidate_conflict = bool(conflict_lines) or bool(candidate and (candidate.get("conflict") or any(
        check.get("state") == "CONFLICT" for check in candidate.get("checks", []))))
    if candidate_conflict:
        title = "Conflicting assignment"
        details = (" " + "<br>".join(html.escape(line) for line in conflict_lines)) if conflict_lines else ""
        action = ("A regular Confirm is blocked for this selection. Use the explicit manual assignment action "
                  "if the report is known to be wrong." + details)
    elif decision.get("decisionType") == "MANUAL_ASSIGNMENT":
        title, action = "Manual assignment", "The reported conflict and the administrator's choice remain in the audit."
    elif decision.get("deviceId"):
        title, action = "Confirmed by administrator", "The selected catalog model is saved for this diagnostic result."
    elif assigned:
        title, action = "Assigned catalog model", "The existing catalog assignment is shown below. Use Edit only if it needs correction."
    elif candidate:
        title, action = "Review model assignment", "Review the compact facts and confirm the suggested model, or use Edit to choose another variant."
    else:
        title, action = "Select catalog variant", "Missing evidence remains visible, but it does not prevent an explicit catalog selection."
    return ("<section class='identity-summary identity-outcome'><h3>" + title + "</h3><p>" + action + "</p>"
            + _identity_observations_markup(results, identity_devices)
            + "</section>")


def _identity_device_label(device: dict[str, Any] | None) -> str:
    if not device:
        return "No catalog model selected"
    model, variant, _ = _identity_parts(device)
    parts = [part for part in (model, variant if variant != "—" else "") if part]
    screen = device.get("screen_technology") or device.get("screenTechnology")
    if screen and not any(str(screen).casefold() in part.casefold() for part in parts):
        parts.append(str(screen))
    solar = device.get("solar")
    if not any(re.search(r"\bSolar:\s*(?:Yes|No|Not confirmed)\b", part, re.IGNORECASE) for part in parts):
        parts.append("Solar: Yes" if solar is True else "Solar: No" if solar is False else "Solar: Not confirmed")
    inreach = device.get("inreach", device.get("inReach"))
    if not any(re.search(r"\binReach:\s*(?:Yes|No|Not confirmed)\b", part, re.IGNORECASE) for part in parts):
        parts.append("inReach: Yes" if inreach is True else "inReach: No" if inreach is False else "inReach: Not confirmed")
    return " · ".join(parts) or "Unknown Garmin model"


def _identity_device_options(devices: list[dict[str, Any]] | None, current_id: Any = None, *, properties_only: bool = False) -> tuple[str, str]:
    """Render one keyboard-friendly picker while preserving exact catalog IDs."""
    current = str(current_id or "").strip()
    current_label = current or "No canonical device selected"
    options: list[str] = []
    for device in devices or []:
        device_id = str(device.get("device_id") or device.get("id") or "").strip()
        if not device_id:
            continue
        label = _identity_device_label(device)
        if device_id == current:
            current_label = label
        options.append(
            f"<button type='button' class='identity-picker-option' role='option' data-identity-device-id='{html.escape(device_id, quote=True)}' data-identity-device-label='{html.escape(label, quote=True)}'>{html.escape(label)}</button>"
        )
    return "".join(options), current_label


def _operation_state(results: list[dict[str, Any]], *, resolved: bool) -> str:
    if resolved:
        return "resolved"
    workflow = str(results[0].get("diagnostic_workflow_status") or "").strip().upper() if results else ""
    if _operation_issue(results):
        return {
            "UNDER_REVIEW": "under-review",
            "IN_PROGRESS": "in-progress",
        }.get(workflow, "in-progress")
    if workflow == "UNDER_REVIEW":
        return "under-review"
    if _operation_is_problematic(results):
        return "open"
    if _identity_is_pending(results):
        return "identity-pending"
    return "history"


def _result_classification(result: dict[str, Any]) -> str:
    outcome = str(result.get("phase_outcome") or "").strip().upper()
    finishing = str(result.get("automatic_finishing_result") or "").strip().upper()
    if outcome == "SUCCEEDED" and finishing == "VERIFIED":
        return "SUCCESS"
    if outcome == "FAILED":
        write_started = result.get("write_started")
        if write_started is True or write_started == 1 or (
            write_started is None
            and result.get("app_build") is None
            and result.get("release_label") is None
        ):
            return "FAILURE"
        if write_started is False or write_started == 0:
            return "NOT_STARTED"
        return "UNKNOWN"
    if outcome == "NOT_STARTED":
        return "NOT_STARTED"
    return "UNKNOWN"


def _operation_result(results: list[dict[str, Any]]) -> str:
    classifications = {_result_classification(result) for result in results}
    if len(classifications) != 1:
        return "UNKNOWN"
    classification = next(iter(classifications))
    if classification == "NOT_STARTED" and all(
        str(result.get("phase_outcome") or "").strip().upper() == "FAILED"
        for result in results
    ) and not all(_is_preinstall_download_failure(result) for result in results):
        # Preserve the existing display for non-download preflight failures.
        # Provider acquisition failures are the explicit PRE-INSTALL exception.
        return "FAILED"
    return {
        "SUCCESS": "SUCCEEDED",
        "FAILURE": "FAILED",
        "NOT_STARTED": "NOT_STARTED",
        "UNKNOWN": "UNKNOWN",
    }.get(classification, "UNKNOWN")


def _operation_write_started(results: list[dict[str, Any]]) -> bool:
    return any(
        result.get("write_started") is True or result.get("write_started") == 1
        for result in results
    )


def _operation_counts_as_installation_attempt(results: list[dict[str, Any]]) -> bool:
    """Count only a verified result or a failure after writing began."""
    result = _operation_result(results)
    if result == "SUCCEEDED":
        return True
    if result == "FAILED":
        return _operation_write_started(results) or all(
            item.get("write_started") is None
            and item.get("app_build") is None
            and item.get("release_label") is None
            for item in results
        )
    return False


def _operation_text(results: list[dict[str, Any]], field: str, *, fallback: str = "—") -> str:
    values = []
    for result in results:
        value = str(result.get(field) or "").strip()
        if value and value not in values:
            values.append(value)
    return ", ".join(values) if values else fallback


def _operation_region_label(results: list[dict[str, Any]]) -> str:
    """Render result regions through the shared human-readable resolver."""
    values: list[str] = []
    for result in results:
        label = _admin_region_display_name(
            result.get("canonical_region_id"),
            result.get("region_country"),
            result.get("region"),
            result.get("map_package_name"),
        )
        if label != "—" and label not in values:
            values.append(label)
    return ", ".join(values) if values else "—"


def _operation_issue(results: list[dict[str, Any]]) -> str | None:
    for result in results:
        try:
            value = _normalise_github_issue_reference(result.get("linked_github_issue"))
        except ValueError:
            value = None
        if value:
            return value
    return None


def _github_issue_link(value: Any) -> str:
    try:
        issue = _normalise_github_issue_reference(value)
    except ValueError:
        issue = None
    if not issue:
        return "<span class='muted-value'>—</span>"
    number = issue[1:]
    return (
        f"<a class='github-issue' href='https://github.com/VooZ2/terento/issues/{number}' "
        f"target='_blank' rel='noreferrer' aria-label='Open GitHub issue {number}'>"
        f"#{number} {_admin_icon('external')}</a>"
    )


def _sanitised_issue_value(value: Any, *, max_length: int | None = None) -> str:
    """Sanitise one allowlisted report value before Markdown or URL encoding."""
    text = str(value or "")[:_ADMIN_TEXT_INPUT_LIMIT]
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()
    # This is report text, not HTML. Remove angle brackets directly instead of
    # attempting to parse HTML with a backtracking regular expression.
    text = text.replace("<", "[redacted markup]").replace(">", "[redacted markup]")
    text = re.sub(r"(?i)\b(?:ghp|github_pat)_[A-Za-z0-9_\-]+", "[redacted token]", text)
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(
        r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie)\s*:\s*[^\s,;]+(?:\s+[^\s,;]+)?",
        lambda match: f"{match.group(1)}: [redacted]",
        text,
    )
    text = re.sub(
        r"(?i)([?&](?:token|access_token|api_key|apikey|secret)=)[^&\s]+",
        lambda match: f"{match.group(1)}[redacted]",
        text,
    )
    text = re.sub(
        r"(?i)[?&](?:title|body)=[^&\s]+",
        "[redacted query value]",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|access[_ -]?token|api[_ -]?key|apikey|secret|password|cookie|authorization)\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    text = re.sub(r"\b[A-Z][A-Z0-9_]{2,}\s*=\s*\S+", "[redacted environment value]", text)
    text = re.sub(
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[redacted email]",
        text,
    )
    text = re.sub(r"(?i)/Users/[^/\s]+(?:/[^\s]*)?", "/Users/<redacted>/[redacted]", text)
    text = re.sub(
        r"(?i)(?:/private|/var/folders|/home|/Volumes)/(?:[^\s]+)",
        "[redacted path]",
        text,
    )
    text = re.sub(
        r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s]+(?:[\\/][^\s]*)?",
        "[redacted path]",
        text,
    )
    text = re.sub(
        r"(?i)\b(serial(?:[_ -]?number)?|unit[_ -]?id|device[_ -]?id|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if max_length is not None:
        text = text[:max_length]
    return text


def _markdown_issue_value(value: Any, *, max_length: int | None = None) -> str:
    text = _sanitised_issue_value(value, max_length=max_length)
    return re.sub(r"([\\`*_{}\[\]<>#+!|])", r"\\\1", text)


def _operation_report_value(results: list[dict[str, Any]], *fields: str) -> str:
    for field in fields:
        value = _operation_text(results, field, fallback="")
        if value:
            return _markdown_issue_value(value)
    return ""


def _operation_report_boolean(results: list[dict[str, Any]], field: str) -> str:
    values: list[str] = []
    for result in results:
        if field not in result or result.get(field) is None:
            continue
        label = "Yes" if bool(result.get(field)) else "No"
        if label not in values:
            values.append(label)
    return ", ".join(values)


def _github_issue_report(
    identity: str,
    results: list[dict[str, Any]],
    *,
    device: dict[str, Any] | None = None,
    admin_note: str | None = None,
) -> tuple[str, str]:
    """Build a public report exclusively from explicitly allowlisted fields."""
    model, variant = _display_identity(identity)
    first = results[0] if results else {}
    device = device or {}
    result = _markdown_issue_value(_operation_result(results))
    stage = _operation_report_value(results, "failure_stage")
    code = _operation_report_value(results, "failure_code")
    native_code = _operation_report_value(results, "native_failure_code")
    model_value = _markdown_issue_value(model)
    variant_value = _markdown_issue_value(variant) if variant != "—" else ""
    title_stage = _sanitised_issue_value(_operation_text(results, "failure_stage", fallback=""))
    title_code = _sanitised_issue_value(_operation_text(results, "failure_code", fallback=""))
    title_model = _sanitised_issue_value(model)
    title_variant = _sanitised_issue_value(variant) if variant != "—" else ""
    model_variant = " · ".join(value for value in (title_model, title_variant) if value)
    title = (
        f"[Install][{title_stage.title()}] {model_variant}"
        if result == "FAILED" and title_stage else
        f"[Installation failure] {model_variant}"
        if result == "FAILED" else
        f"[Installation anomaly] {model_variant}"
    )
    if title_code:
        title += f" — {title_code}"

    family = _markdown_issue_value(
        device.get("familyName") or device.get("family_name") or device.get("family")
        or _operation_text(results, "family", fallback="")
    )
    part_number = _markdown_issue_value(device.get("partNumber") or device.get("part_number"))
    sections: list[tuple[str, list[tuple[str, str]]]] = [
        ("Summary", [
            ("Result", result),
            ("Failure stage", stage),
            ("Error category", _operation_report_value(results, "error_category")),
            ("Error code", code),
        ]),
        ("Device", [
            ("Model", model_value),
            ("Variant", variant_value),
            ("Family", family),
            ("Part number", part_number),
            ("Firmware", _operation_report_value(results, "firmware_version")),
            ("Raw MTP model", _operation_report_value(results, "raw_mtp_model")),
        ]),
        ("Installation", [
            ("Operation", "Map installation"),
            ("Map", _operation_report_value(results, "provider")),
            ("Region", _operation_report_value(results, "region")),
            ("Map version", _operation_report_value(results, "map_release")),
            ("App version", _operation_report_value(results, "release_label", "terento_version")),
            ("Build", _operation_report_value(results, "app_build")),
            ("Timestamp", _operation_report_value(results, "occurred_at")),
        ]),
        ("Failure details", [
            ("Write started", _operation_report_boolean(results, "write_started")),
            ("Transfer progress", _operation_report_value(results, "transfer_progress_bucket")),
            ("Object created", _operation_report_boolean(results, "remote_object_created")),
            ("Cleanup attempted", _operation_report_boolean(results, "cleanup_attempted")),
            ("Cleanup succeeded", _operation_report_boolean(results, "cleanup_succeeded")),
            ("Transport", _operation_report_value(results, "transport")),
            ("Reported transport category (may be inferred)", native_code),
        ]),
        ("Reference", [
            ("Diagnostic ID", _markdown_issue_value(_operation_key(first))),
            ("Installation ID", _operation_report_value(results, "event_id")),
        ]),
    ]
    rendered_sections: list[str] = []
    for heading, fields in sections:
        rows = [f"- {label}: {value}" for label, value in fields if value]
        if rows:
            rendered_sections.append(f"## {heading}\n\n" + "\n".join(rows))
    for number, item in enumerate(results, 1):
        source = 'Custom import' if item.get('provider') == 'custom' else _markdown_issue_value(item.get('provider')) or 'unavailable'
        context = item.get('failure_context') or {}
        stage = item.get('optional_component_failure_stage') if isinstance(context, dict) and context.get('componentKind') == 'contours' else item.get('failure_stage')
        rows = [f'- Source: {source}', f'- Failure stage: {_markdown_issue_value(stage) or "unavailable"}']
        if item.get('provider') == 'custom':
            rows.extend(['- Acquisition: manually imported IMG', '- Original file provenance: not tracked'])
        for key, label in (('failure_context', 'Failure'), ('original_failure_context', 'Original failure')):
            if key == 'original_failure_context' and item.get(key) is None:
                rows.append('- Original failure context: unavailable')
            else:
                rows.extend(f'- {label} {name.lower()}: {_markdown_issue_value(str(value))}' for name, value in _failure_context_fields(item, key, technical=item.get(key) is not None))
        rendered_sections.append(f'## {_failure_result_label(item, number)} diagnostics\n\n' + '\n'.join(rows))
    if result == "FAILED":
        rendered_sections.append(
            "## Detailed diagnostics\n\n"
            "This administrator summary contains uploaded outcome fields, not the local Finishing trace. "
            "The transport category may be inferred from the application failure; it is not a raw native return code. "
            "For the detailed sequence, use Report issue in the failing app (beta.10 build 15 or later) "
            "and review the copied report before sharing. Earlier reports cannot be expanded retroactively."
        )
    note = _markdown_issue_value(admin_note, max_length=GITHUB_ADMIN_NOTE_MAX_LENGTH)
    if note:
        rendered_sections.append(f"## Admin note\n\n{note}")
    return _sanitised_issue_value(title, max_length=180), "\n\n".join(rendered_sections)


def _github_issue_url(
    identity: str,
    results: list[dict[str, Any]],
    *,
    device: dict[str, Any] | None = None,
    admin_note: str | None = None,
) -> tuple[str, bool]:
    title, body = _github_issue_report(identity, results, device=device, admin_note=admin_note)
    candidate = GITHUB_NEW_ISSUE_URL + "?" + urlencode({"title": title, "body": body})
    if len(candidate) > GITHUB_ISSUE_URL_MAX_LENGTH:
        return GITHUB_NEW_ISSUE_URL, False
    return candidate, True


def _diagnostic_detail_dialog(
    identity: str,
    operation_key: str,
    results: list[dict[str, Any]],
    *,
    resolved: bool,
    csrf_token: str,
    identity_devices: list[dict[str, Any]] | None,
    canonical_device_model_id: str | None = None,
    return_to: str | None = None,
) -> str:
    first = results[0]
    dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
    model, variant = _display_identity(identity)
    catalog_device = next((d for d in identity_devices or []
                           if (d.get('id') or d.get('device_id')) == first.get('canonical_device_model_id')), None)
    if catalog_device:
        model, variant, _ = _identity_parts(catalog_device)
    issue = _operation_issue(results)
    result_label = _operation_result(results)
    state = _operation_state(results, resolved=resolved)
    identity_pending = _identity_is_pending(results)
    return_to = return_to or _diagnostics_url({
        "compatibility_identity": identity,
        "canonical_device_model_id": canonical_device_model_id,
    })
    recommendation = _identity_recommendation(results)
    selection_id = str(first.get("canonical_device_model_id") or (recommendation or {}).get("deviceId") or "").strip()
    picker_devices = list(identity_devices or [])
    if not selection_id:
        candidate_ids = {
            str(candidate.get("deviceId") or "").strip()
            for assessment in _identity_assessments(results)
            for candidate in _identity_presentation_candidates(assessment)
            if str(candidate.get("deviceId") or "").strip()
        }
        if candidate_ids:
            picker_devices = [
                device for device in picker_devices
                if str(device.get("id") or device.get("device_id") or "").strip() in candidate_ids
            ]
    options, current_label = _identity_device_options(picker_devices, selection_id)
    selected_candidate = _identity_candidate(results, selection_id or None)
    conflict_lines = _identity_conflict_lines(results, selection_id, identity_devices)
    selection_conflict = bool(conflict_lines) or bool(selected_candidate and (selected_candidate.get("conflict") or any(
        check.get("state") == "CONFLICT" for check in selected_candidate.get("checks", []))))
    conflict_detail = " ".join(conflict_lines) if conflict_lines else (
        "The selected model conflicts with reported information." if selection_conflict else ""
    )
    picker_hidden = bool(selection_id)
    search_id = f"identity-search-{dialog_id}"
    canonical_id = f"identity-canonical-{dialog_id}"
    technical = "".join(
        _diagnostic_technical_details(result, index)
        for index, result in enumerate(results, start=1)
    )
    resolution = ""
    if resolved:
        resolution = "".join(
            part for part in (
                f" · {html.escape(str(first.get('resolution_reason') or 'Resolved'))}" if first.get("resolution_reason") else "",
                f" · {_timestamp_markup(first.get('resolved_at'))}" if first.get("resolved_at") else "",
                f" · by {html.escape(str(first.get('resolved_by_username')))}" if first.get("resolved_by_username") else "",
            )
        )
    if resolved:
        lifecycle_action = f"""
          <form method='post' action='/admin/diagnostics/reopen' class='diagnostic-action-form admin-async-action'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
            <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
            <button type='submit' class='secondary-button'>Reopen diagnostic</button>
          </form>"""
    elif state in {"open", "in-progress", "under-review"}:
        lifecycle_action = f"""
          <form method='post' action='/admin/diagnostics/resolve' class='diagnostic-action-form admin-async-action' data-confirm='Mark this error as resolved? The installation will remain failed in history and statistics.'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
            <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
            <h4>Resolve diagnostic</h4>
            <label>Reason<select name='resolution_reason' required><option value='FIXED'>Fixed</option><option value='HISTORICAL_SUPERSEDED'>Historical / superseded</option><option value='DUPLICATE'>Duplicate</option><option value='IDENTITY_CORRECTED'>Identity corrected</option><option value='NOT_TERENTO_ISSUE'>Not a Terento issue</option><option value='OTHER'>Other</option></select></label>
            <label>Resolution note <span class='optional-label'>Optional</span><textarea name='resolution_note' rows='3'></textarea></label>
            <button type='submit'>Resolve diagnostic</button>
          </form>"""
    else:
        lifecycle_action = ""
    identity_form = f"""
      <form method='post' action='/admin/diagnostics/identity' class='diagnostic-action-form identity-review-form admin-async-action' data-identity-form>
        <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
        <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
        <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
        <div class='identity-picker-heading'><h4>Assign model</h4><button type='button' class='secondary-button' data-identity-edit{'' if selection_id else ' hidden'}>Edit</button></div>
        <div class='identity-picker' data-canonical-device-wrap{' hidden' if picker_hidden else ''}>
          <label for='{search_id}'>Find a catalog model<input id='{search_id}' type='search' data-identity-search role='combobox' aria-expanded='{'false' if picker_hidden else 'true'}' aria-controls='{canonical_id}-options' placeholder='Search model, size or variant' autocomplete='off' value='{html.escape(current_label if selection_id else '', quote=True)}'></label>
          <input type='hidden' name='canonical_device_model_id' id='{canonical_id}' value='{html.escape(selection_id, quote=True)}'>
          <div class='identity-search-results' id='{canonical_id}-options' data-identity-results role='listbox' aria-label='Matching Garmin catalog models'>{options}</div>
        </div>
        <p class='identity-selection' data-identity-selection>{'Selected model: ' + html.escape(current_label) if selection_id else 'Model not assigned.'}</p>
        {f"<p class='identity-conflict-warning' data-identity-conflict role='alert'>{html.escape(conflict_detail)} Use the explicit manual assignment action if this is the intended correction.</p>" if conflict_detail else ""}
        <div class='identity-review-actions'><button type='submit' name='identity_action' value='ASSIGN' data-identity-confirm>Confirm</button><button type='submit' name='identity_action' value='MANUAL_ASSIGN' class='secondary-button' data-manual-confirm{' hidden' if not selection_conflict else ''}>Confirm manual assignment</button></div>
        <p class='admin-action-status' data-identity-status role='status' aria-live='polite'></p>
      </form>"""
    report_device = next((
        device for device in (identity_devices or [])
        if str(device.get("id") or device.get("device_id") or "") == str(canonical_device_model_id or "")
    ), None)
    issue_title, issue_body = _github_issue_report(identity, results, device=report_device)
    issue_url, issue_prefilled = _github_issue_url(identity, results, device=report_device)
    issue_controls = f"""
        <div class='github-actions'><a class='secondary-button' href='{html.escape(issue_url, quote=True)}' data-github-create data-issue-title='{html.escape(issue_title, quote=True)}' data-issue-body='{html.escape(issue_body, quote=True)}' data-prefilled='{'true' if issue_prefilled else 'false'}' data-url-limit='{GITHUB_ISSUE_URL_MAX_LENGTH}' target='_blank' rel='noreferrer'>Prepare GitHub issue</a><button class='secondary-button' type='button' data-copy-issue-report>Copy issue report</button><span class='copy-status' data-copy-status role='status' aria-live='polite'>{'Report is too large to prefill; copy it instead.' if not issue_prefilled else ''}</span></div>
        <details class='github-issue-preview'><summary>Preview issue report</summary><label>Title<input value='{html.escape(issue_title, quote=True)}' readonly data-issue-preview-title></label><label>Body<textarea rows='8' readonly data-issue-preview-body>{html.escape(issue_body)}</textarea></label><label>Admin note <span class='optional-label'>Optional · maximum {GITHUB_ADMIN_NOTE_MAX_LENGTH} characters</span><textarea rows='3' maxlength='{GITHUB_ADMIN_NOTE_MAX_LENGTH}' data-issue-note></textarea></label></details>
        <form method='post' action='/admin/diagnostics/issue' class='github-link-form admin-async-action'>
          <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
          <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
          <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
          <label>{'Change' if issue else 'Link'} issue <span class='optional-label'>e.g. #32</span><input name='linked_github_issue' placeholder='#32' inputmode='numeric' pattern='#?[0-9]{{1,10}}'></label>
          <button type='submit' class='secondary-button'>{'Change linked issue' if issue else 'Link issue'}</button>
        </form>
        {f"<form method='post' action='/admin/diagnostics/issue' class='github-remove-form admin-async-action' data-confirm='Unlink this GitHub issue from the installation?'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'><input type='hidden' name='linked_github_issue' value=''><button type='submit' class='secondary-button'>Unlink issue</button></form>" if issue else ''}"""
    issue_content = f"""
        <p class='github-current'>{_github_issue_link(issue) if issue else '<span class="muted-value">No linked issue</span>'}</p>
        <p class='table-help'>Closed linked issues resolve this diagnostic after synchronization, normally within 15 minutes. Installation results stay in history.</p>
        <details class='github-issue-disclosure'><summary>{'Manage linked issue' if issue else 'Report an anomaly or link issue'}</summary><div class='github-issue-controls'>{issue_controls}</div></details>"""
    issue_form = (
        "<details class='admin-disclosure diagnostic-action-form diagnostic-secondary-disclosure'>"
        "<summary>GitHub issue</summary><div class='disclosure-body github-review'>"
        + issue_content + "</div></details>"
    )
    workflow_form = ""
    if not resolved and issue:
        workflow_value = {
            "in-progress": "IN_PROGRESS",
            "under-review": "UNDER_REVIEW",
        }.get(state, "IN_PROGRESS")
        workflow_form = f"""
      <form method='post' action='/admin/diagnostics/workflow' class='diagnostic-action-form diagnostic-workflow-form admin-async-action'>
        <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
        <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
        <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
        <h4>GitHub issue workflow</h4>
        <p class='table-help'>The linked issue stays in Review Queue until GitHub reports it as closed.</p>
        <label>Status<select name='diagnostic_workflow_status' required><option value='IN_PROGRESS'{" selected" if workflow_value == "IN_PROGRESS" else ""}>In progress</option><option value='UNDER_REVIEW'{" selected" if workflow_value == "UNDER_REVIEW" else ""}>Under review</option></select></label>
        <button type='submit' class='secondary-button'>Save workflow status</button>
      </form>"""
    review_state = ""
    if resolved:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('RESOLVED')}{resolution}</dd></div>"
    elif state in {"open", "in-progress", "under-review"}:
        identity_badge = f" {_diagnostic_state_badge('IDENTITY_PENDING')}" if identity_pending else ""
        state_badge = _diagnostic_state_badge(state.replace("-", "_"))
        review_state = f"<div><dt>Review state</dt><dd>{state_badge}{identity_badge}</dd></div>"
    elif identity_pending:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('IDENTITY_PENDING')}</dd></div>"
    verification_note = (
        " Terento could not verify the transferred map. This identifies the failed check, not its root cause; review the technical report before deciding what to fix."
        if result_label == "FAILED" and _diagnostic_error_reason(results, resolved=resolved) == "Transfer verification" else ""
    )
    failure_summary = (
        f"<p class='diagnostic-failure-summary'><strong>Failure reason:</strong> {html.escape(_diagnostic_error_reason(results, resolved=resolved))}{verification_note}</p>"
        if result_label == "FAILED" else ""
    )
    technical_details = f"<details class='admin-disclosure diagnostic-action-form diagnostic-secondary-disclosure'><summary>Technical details</summary><div class='disclosure-body'><p class='diagnostic-id'>Diagnostic ID: <code>{html.escape(operation_key)}</code></p><div class='technical-copy-actions'><button type='button' class='secondary-button' data-copy-diagnostic-id='{html.escape(operation_key, quote=True)}'>Copy diagnostic ID</button><button type='button' class='secondary-button' data-copy-technical-report data-report='{html.escape(issue_body, quote=True)}'>Copy technical report</button><span class='copy-status' data-copy-status role='status' aria-live='polite'></span></div>{technical}</div></details>"
    identity_state = (
        "<p class='diagnostic-identity-state'><strong>Identity incomplete.</strong> Assign the exact catalog model.</p>"
        if identity_pending else ""
    )
    secondary_lifecycle = (
        f"<details class='admin-disclosure diagnostic-secondary-action'><summary>Resolve diagnostic</summary><div class='disclosure-body'>{lifecycle_action}</div></details>"
        if identity_pending and lifecycle_action else ""
    )
    action_markup = (
        f"{identity_form}{secondary_lifecycle}{workflow_form}"
        if identity_pending else
        f"{lifecycle_action}{workflow_form}{identity_form}"
    )
    return f"""
      <dialog class='diagnostic-detail-dialog' id='{dialog_id}' aria-labelledby='{dialog_id}-title'>
        <div class='diagnostic-detail-inner'>
          <div class='device-dialog-header'><div><h2 id='{dialog_id}-title'>Diagnostic detail</h2></div><button class='dialog-close' type='button' data-close-dialog aria-label='Close diagnostic detail'>{_admin_icon('close')}</button></div>
          <dl class='diagnostic-detail-summary'>
            <div><dt>Device</dt><dd>{html.escape(model)}</dd></div>
            <div><dt>Variant</dt><dd>{html.escape(variant)}</dd></div>
            <div><dt>Date</dt><dd>{_timestamp_markup(first.get('occurred_at'))}</dd></div>
            <div><dt>Map / region</dt><dd>{html.escape(_operation_region_label(results))}</dd></div>
            <div><dt>Result</dt><dd>{_diagnostic_result(result_label)}</dd></div>
            <div><dt>App version</dt><dd>{html.escape(_admin_app_version_label(first.get('release_label') or first.get('terento_version'), first.get('app_build')))}</dd></div>
            {review_state}
          </dl>
          {failure_summary}
          {identity_state}
          <div class='diagnostic-actions-grid'>{action_markup}</div>
          <div class='diagnostic-secondary-grid'>{issue_form}{technical_details}</div>
        </div>
      </dialog>"""


def _detail_rows(items: list[tuple[str, Any, bool]]) -> str:
    rows: list[str] = []
    for label, value, is_markup in items:
        if value is None or value == "" or value == "—":
            continue
        rendered = str(value) if is_markup else html.escape(str(value))
        rows.append(f"<div><dt>{html.escape(label)}</dt><dd>{rendered}</dd></div>")
    return "".join(rows)


def _usb_identity_details(identities: list[dict[str, Any]] | None) -> str:
    values: list[str] = []
    for identity in identities or []:
        vendor = identity.get("vendorId")
        product = identity.get("productId")
        if vendor is None or product is None:
            continue
        try:
            values.append(f"VID 0x{int(vendor):04X} · PID 0x{int(product):04X}")
        except (TypeError, ValueError):
            continue
    return ", ".join(values)


def _device_information_markup(device: dict[str, Any]) -> str:
    """Catalog facts first; absence stays unknown and is never inferred from a name."""
    def feature(key: str) -> str:
        value = device.get(key)
        return "Available" if value is True else "Not included" if value is False else "Not confirmed"

    size = device.get("caseSizeMm")
    facts = _detail_rows([(label, f"<bdi>{html.escape(str(value))}</bdi>", True) for label, value in [
        ("Watch size", f"{size} mm" if size else "Not confirmed"),
        ("Display", device.get("screenTechnology") or "Not confirmed"),
        ("Solar charging", feature("solar")),
        ("inReach", feature("inReach")),
    ]])
    evidence = device.get("specificationEvidence") or {}
    more = _detail_rows([
        ("Dimensions", (evidence.get("physical_size") or {}).get("value"), False),
        ("Screen size", (evidence.get("display_size") or {}).get("value"), False),
        ("Resolution", (evidence.get("display_resolution") or {}).get("value"), False),
        ("Family", device.get("familyName") or device.get("family"), False),
    ])
    more = ("<details class='device-extra-specifications admin-disclosure'><summary>More specifications</summary>"
            f"<dl class='model-information-list'>{more}</dl></details>") if more else ""
    source_url = str(device.get("specificationSource") or "")
    try:
        source = urlsplit(source_url)
        official_source = source.scheme == "https" and (source.hostname == "garmin.com" or (source.hostname or "").endswith(".garmin.com"))
    except ValueError:
        official_source = False
    source_link = (f"<a class='device-specification-link' href='{html.escape(source_url, quote=True)}' "
                   f"target='_blank' rel='noopener noreferrer'>View Garmin specifications {_admin_icon('external')}</a>") if official_source else ""
    note = ("<p class='device-information-note'>Not confirmed means the catalog does not yet have a verified value.</p>"
            if not size or not device.get("screenTechnology") or any(device.get(key) is None for key in ("solar", "inReach")) else "")
    return (f"<dl class='device-key-facts'>{facts}</dl>"
            f"{note}"
            f"<div class='device-information-more'>{more}{source_link}</div>")


def device_detail_page(
    device: dict[str, Any], user: dict[str, Any], csrf_token: str, *,
    operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    identity_devices: list[dict[str, Any]] | None = None,
    origin: str = "devices",
    requested_state: str | None = None,
) -> bytes:
    device_id = str(device.get("id") or "").strip()
    model, variant, _ = _identity_parts(device)
    identity = " · ".join(part for part in (model, variant if variant != "—" else "") if part)

    def matches(event: dict[str, Any]) -> bool:
        return str(event.get("canonical_device_model_id") or "").strip() == device_id

    active_events = [
        event for event in (operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    resolved_events = [
        event for event in (resolved_operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    active_groups = _group_operations(active_events)
    resolved_groups = _group_operations(resolved_events)
    history = [(key, results, False) for key, results in active_groups.items()]
    history.extend((key, results, True) for key, results in resolved_groups.items())
    history.sort(key=lambda item: _timestamp_iso(item[1][0].get("occurred_at")), reverse=True)

    stats = device.get("installationStats") or {}
    attempts = int(stats.get("attempts") or 0)
    successful = int(stats.get("successful") or 0)
    failed = int(stats.get("failed") or 0)
    open_errors = sum(
        1 for results in active_groups.values()
        if _operation_counts_as_installation_attempt(results) and _operation_result(results) == "FAILED"
    )
    status = calculate_compatibility_status(
        successful_install_count=successful,
        recognized_map_capable_evidence=device.get("observedMapCapability") is True,
    )
    status_value = device.get("evidenceStatus") or (status.value if status else "")
    last_activity = _timestamp_markup(stats.get("lastEvidenceAt")) if stats.get("lastEvidenceAt") else "—"
    publication = device.get("publicCompatibility") or {}
    map_label, map_kind = _admin_map_capability(device.get("mapCapable"))
    authorization_label, authorization_kind, _ = _admin_installation_authorization_code(
        device.get("installationAuthorization")
    )
    if variant == "Historical":
        variant = "—"
        provenance = "<span class='admin-state'>Historical catalog entry</span>"
    else:
        provenance = ""
    status_line = (
        f"<div class='model-status-line'>{provenance}"
        f"<span><strong>Maps</strong> {_admin_status_badge(map_label, f'map-{map_kind}')}</span>"
        f"<span><strong>Install policy</strong> {_admin_status_badge(authorization_label, f'authorization-{authorization_kind}')}</span>"
        f"<span><strong>Evidence</strong> {_status_badge(status_value)}</span>"
        "</div>"
    )
    image_url = (device.get("image") or {}).get("url")
    image = (
        f"<img class='model-page-image' src='{html.escape(str(image_url), quote=True)}' alt='' loading='eager'>"
        if image_url else ""
    )
    back_href = "/admin/installations" if origin == "installations" else "/admin/devices"
    back_label = "Back to Installations" if origin == "installations" else "Back to Devices"
    detail_url = _device_detail_url(device_id, origin=origin)
    public_link = (
        f"<a class='secondary-button model-public-link' href='https://terento.app/compatibility/' target='_blank' rel='noreferrer'>View public page {_admin_icon('external')}</a>"
        if publication.get("published") else ""
    )
    alert = (
        f"<aside class='model-review-alert' role='status'><span><strong>{open_errors} installation {'error needs' if open_errors == 1 else 'errors need'} review.</strong> Resolved failures remain in the historical failed count.</span><a href='#installations' data-filter-open-errors>Review open errors</a></aside>"
        if open_errors else ""
    )

    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results, resolved) in enumerate(history):
        first = results[0]
        result = _operation_result(results)
        issue = _operation_issue(results)
        is_open_error = not resolved and result == "FAILED"
        is_resolved_error = resolved and result == "FAILED"
        region = _operation_text(results, "region", fallback="")
        map_release = _operation_text(results, "map_release", fallback="")
        map_names = list(dict.fromkeys(
            _admin_map_display_name(item.get('region')) for item in results if item.get('region')
        ))
        map_copy = html.escape(', '.join(map_names) or "Map not recorded")
        providers_in_operation = {str(item.get('provider') or '') for item in results}
        regions_in_operation = {str(item.get('region') or '') for item in results}
        if len(providers_in_operation) == len(regions_in_operation) == 1 and providers_in_operation <= {'freizeitkarte', 'opentopomap', 'maprando'} and region:
            href = '/admin/map-statistics?' + urlencode({'provider': next(iter(providers_in_operation)), 'region': region, 'period': 'all'})
            map_copy = f"<a href='{html.escape(href, quote=True)}' title='View map statistics'>{map_copy}</a>"
        if map_release:
            map_copy += f"<small>{html.escape(region)} · {html.escape(map_release)}</small>"
        if result == "FAILED":
            error_state = _diagnostic_state_badge(
                "RESOLVED" if resolved else _operation_state(results, resolved=False).replace("-", "_")
            )
            error_markup = error_state + f"<small>{html.escape(_diagnostic_error_reason(results, resolved=resolved))}</small>"
        else:
            error_markup = "<span class='muted-value'>No error</span>"
        release = _admin_app_version_label(
            first.get("release_label") or first.get("terento_version"),
            first.get("app_build"),
        )
        release_markup = html.escape(release) if release != "—" else "<span class='muted-value'>—</span>"
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr data-diagnostic-state='{'resolved-error' if is_resolved_error else 'open' if is_open_error else 'history'}' data-review-open='{'true' if is_open_error else 'false'}' data-review-resolved='{'true' if is_resolved_error else 'false'}' data-diagnostic-result='{html.escape(result.lower(), quote=True)}' data-has-issue='{'true' if issue else 'false'}'>"
            f"<td class='column-date' data-label='Date'>{_timestamp_markup(first.get('occurred_at'))}</td>"
            f"<td class='history-map' data-label='Map'>{map_copy}</td>"
            f"<td class='column-status' data-label='Result'>{_diagnostic_result(result)}</td>"
            f"<td class='history-error' data-label='Error'>{error_markup}</td>"
            f"<td data-label='GitHub issue'>{_github_issue_link(issue)}</td>"
            f"<td data-label='App version'>{release_markup}</td>"
            f"<td class='column-status' data-label='Action'><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='Inspect installation {index + 1}'>Inspect</button></td>"
            "</tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity, operation_key, results, resolved=resolved,
            csrf_token=csrf_token, identity_devices=identity_devices,
            canonical_device_model_id=device_id, return_to=detail_url + "#installations",
        ))
    history_rows = "".join(rows_markup) or "<tr><td colspan='7' class='empty'>No installation history for this device.</td></tr>"
    history_pagination = "" if len(history) <= 25 else f"""
          <div class='provider-pagination' id='diagnostic-history-pagination' aria-live='polite'><label>Rows <select id='diagnostic-history-page-size' aria-label='Rows per installation history page'><option value='25' selected>25</option><option value='50'>50</option></select></label><button type='button' data-history-page='previous' disabled>Previous</button><span>Showing 1–25 of {len(history)} · page 1 of {(len(history) + 24) // 25}</span><button type='button' data-history-page='next'>Next</button></div>
    """

    public_copy = (
        f"Shown as {html.escape(status.value.title() if status else 'Unavailable')}."
        if publication.get("published") else
        "Not shown."
    )
    public_form = ""
    if publication.get("eligible"):
        action = "UNPUBLISH" if publication.get("published") else "PUBLISH"
        confirm = (
            " data-confirm='This device will no longer appear on the public compatibility page.'"
            if action == "UNPUBLISH" else ""
        )
        public_form = f"""<form method='post' action='/admin/devices/public-compatibility' class='admin-async-action'{confirm}>
          <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='device_id' value='{html.escape(device_id, quote=True)}'><input type='hidden' name='publication_action' value='{action}'><input type='hidden' name='return_to' value='{html.escape(detail_url, quote=True)}'>
          <label>Note <span class='optional-label'>Optional</span><textarea name='note' rows='2'></textarea></label><button type='submit' class='{'secondary-button' if action == 'UNPUBLISH' else ''}'>{'Remove from public compatibility' if action == 'UNPUBLISH' else 'Approve and publish'}</button>
        </form>"""

    lifecycle = (
        "Historical" if device.get("recordSource") == "HISTORICAL_REVIEWED" else
        "Inactive" if device.get("active") is False else "Current retail"
    )
    catalog_source = (
        "Historical reviewed registry" if device.get("recordSource") == "HISTORICAL_REVIEWED" else
        "Garmin retail catalog"
    )
    catalog = device.get("catalog") or {}
    device_info = _device_information_markup(device)
    all_events = active_events + resolved_events
    firmware = ", ".join(sorted({str(item.get("firmware_version")).strip() for item in all_events if item.get("firmware_version")}))
    raw_models = ", ".join(sorted({str(item.get("raw_mtp_model")).strip() for item in all_events if item.get("raw_mtp_model")}))
    transports = ", ".join(sorted({str(item.get("transport")).strip() for item in all_events if item.get("transport")}))
    technical_rows = _detail_rows([
        ("Catalog ID", device_id, False),
        ("Catalog variant", variant, False),
        ("Retail part number", device.get("partNumber"), False),
        ("USB identity", _usb_identity_details(device.get("usbIdentities")), False),
        ("Firmware", firmware, False),
        ("Raw MTP model", raw_models, False),
        ("XML model description", ", ".join(sorted({str(e["garmin_model_description"]) for e in all_events if e.get("garmin_model_description")})), False),
        ("XML part number", ", ".join(sorted({str(e["garmin_model_part_number"]) for e in all_events if e.get("garmin_model_part_number")})), False),
        ("Transport", transports, False),
        ("Specification source", device.get("specificationSource"), False),
        ("Catalog source", catalog_source, False),
        ("Catalog status", lifecycle, False),
        ("Last synced", _timestamp_markup(catalog.get("lastSeenAt")) if catalog.get("lastSeenAt") else None, True),
    ])
    if not technical_rows:
        technical_rows = "<p class='diagnostic-technical-empty'>Detailed technical data is not available for this record.</p>"

    statistics_section = "" if not history and not attempts and not failed else f"""
        <section class='map-statistics-kpi-panel provider-card admin-kpi-panel diagnostic-model-metrics model-statistics' aria-label='Model installation statistics'><div class='map-statistics-kpi-groups model-kpi-groups'><section class='map-statistics-kpi-group' aria-labelledby='model-installation-kpis-title'><h2 id='model-installation-kpis-title' class='sr-only'>Installation outcomes</h2><div class='map-statistics-kpi-values'><div class='map-statistics-kpi-value attempts-metric' aria-label='Attempts. Each map result counts once, including custom .img and resolved failures.'><span>Attempts</span><strong>{attempts}</strong></div><div class='map-statistics-kpi-value'><span>Successful</span><strong>{successful}</strong></div><div class='map-statistics-kpi-secondary'><div class='map-statistics-kpi-value error-counter-kpi'><span>Failed</span>{_admin_error_counter(failed)}</div><div class='map-statistics-kpi-value error-counter-kpi'><span>Open errors</span>{_admin_error_counter(open_errors)}</div></div></div></section><section class='map-statistics-kpi-group model-activity-kpi-group' aria-labelledby='model-activity-kpis-title'><h2 id='model-activity-kpis-title'>Activity</h2><div class='map-statistics-kpi-values'><div class='map-statistics-kpi-value timestamp-metric'><span>Last activity</span><strong>{last_activity}</strong></div></div></section></div></section>
    """
    history_section = "<section class='diagnostics-detail-section model-page-section compact-empty-state' id='installations' aria-labelledby='installation-history-title'><h2 id='installation-history-title'>Installation history</h2><p class='empty'>No installation history for this device.</p></section>" if not history else f"""
        <section class='diagnostics-detail-section model-page-section' id='installations' aria-labelledby='installation-history-title'>
          <div class='section-heading'><div><h2 id='installation-history-title'>Installation history</h2></div><p class='table-help'>Failed results remain historical after their error is resolved.</p></div>
          <form class='filter-bar diagnostic-filter-bar' id='diagnostic-filters'><div class='quick-filter-group' role='group' aria-label='Quick history filters'><button type='button' class='quick-filter active' data-history-filter='all' aria-pressed='true'>All</button><button type='button' class='quick-filter' data-history-filter='failed' aria-pressed='false'>Failed</button><button type='button' class='quick-filter' data-history-filter='open' aria-pressed='false'>Open errors</button><button type='button' class='quick-filter' data-history-filter='succeeded' aria-pressed='false'>Successful</button></div><details class='admin-disclosure filter-disclosure history-more-filters'><summary>More filters</summary><div class='disclosure-body'><label><span class='sr-only'>Filter installation history</span><select id='diagnostic-state-filter'><option value='all'>All</option><option value='succeeded'>Successful</option><option value='failed'>Failed</option><option value='open'>Open errors</option><option value='resolved-errors'>Resolved errors</option></select></label></div></details><button type='button' class='secondary-button filter-clear' data-filter-clear aria-label='Clear diagnostic filters'>Clear</button></form>
          <p class='results-count' id='diagnostic-results-count' aria-live='polite'>{len(history)} records</p>
          <div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table model-history-table mobile-record-table'><caption class='sr-only'>Installation history for this exact model and variant</caption><thead><tr><th scope='col' class='column-date'>Date</th><th scope='col'>Map</th><th scope='col' class='column-status'>Result</th><th scope='col'>Error</th><th scope='col'>GitHub issue</th><th scope='col'>App version</th><th scope='col' class='column-status'>Action</th></tr></thead><tbody id='diagnostic-rows'>{history_rows}</tbody></table></div>
          {history_pagination}
        </section>
    """
    active_header = "evidence" if origin == "installations" else "devices"
    content = f"""
      {_admin_header(user, csrf_token, active=active_header)}
      <main class='dashboard model-detail-page' id='main-content'>
        <p class='back-link'><a href='{back_href}'>{_admin_icon('arrow-left')} {back_label}</a></p>
        <header class='model-page-header'>{image}<div class='model-page-heading'><h1>{html.escape(model)}{f' · <span>{html.escape(variant)}</span>' if variant != '—' else ''}</h1>{status_line}</div>{public_link}</header>
        {f"<div class='model-evidence-grid'><div class='model-evidence-summary'>{statistics_section}{alert}</div><div class='model-evidence-history'>{history_section}</div></div>" if statistics_section else f"{alert}{history_section}"}
        <details class='model-page-section model-administration admin-disclosure'><summary id='administration-title'>Administration</summary><div class='administration-grid'>
          <article><h3>Install policy</h3><p class='table-help'>Catalog Maps is the stored value used for write authorization. Observed map capability is separate evidence and cannot grant installation.</p><p class='admin-state'>Current: {html.escape(authorization_label)}</p><p class='model-status-line'><strong>Public compatibility</strong><span>{public_copy}</span></p>{public_form}<h3>Support metadata</h3><p class='table-help'>This operator field is retained for review and evidence workflow only. Changing it cannot grant or revoke native map-write access.</p><form method='post' action='/admin/devices/authorization' class='admin-async-action' data-authorization-form data-current-support-status='{html.escape(str(device.get('supportStatus') or 'NOT_EVALUATED'), quote=True)}'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='device_id' value='{html.escape(device_id, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(detail_url, quote=True)}'><label>Support status<select name='support_status'><option value='SUPPORTED'{' selected' if device.get('supportStatus') == 'SUPPORTED' else ''}>Supported</option><option value='UNSUPPORTED'{' selected' if device.get('supportStatus') == 'UNSUPPORTED' else ''}>Unsupported</option><option value='NOT_EVALUATED'{' selected' if device.get('supportStatus') == 'NOT_EVALUATED' else ''}>Not evaluated</option></select></label><label>Note <span class='optional-label'>Optional</span><textarea name='note' rows='2'></textarea></label><button type='submit'>Save support metadata</button></form></article>
        </div></details>
        <div class='model-information-columns device-overview-sections'>
        <details class='model-page-section device-information-section admin-disclosure'><summary id='device-information-title'>Device information</summary>{device_info}</details>
        <details class='model-technical-details admin-disclosure'><summary>Technical details</summary><dl class='model-information-list'>{technical_rows}</dl></details>
        </div>
        {''.join(dialogs)}
      </main>
      <script>{_diagnostics_script()}</script>
    """
    return _layout(f"{model} {variant}", content, sections={"device": device, "diagnostics": operations, "resolved": resolved_operations})


def diagnostics_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, identity: str,
    operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    identity_devices: list[dict[str, Any]] | None = None,
    canonical_device_model_id: str | None = None,
    unresolved_only: bool = False,
) -> bytes:
    identity = identity.strip()
    canonical_device_model_id = str(canonical_device_model_id or "").strip() or None

    def matches(value: dict[str, Any]) -> bool:
        if unresolved_only:
            return (
                not str(value.get("canonical_device_model_id") or "").strip()
                and str(value.get("compatibility_identity") or value.get("model") or "").strip() == identity
            )
        if canonical_device_model_id:
            return str(value.get("canonical_device_model_id") or "").strip() == canonical_device_model_id
        return str(value.get("compatibility_identity") or value.get("model") or "").strip() == identity

    model_row = next(
        (row for row in rows if matches(row)),
        None,
    )
    active_events = [
        event for event in (operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    resolved_events = [
        event for event in (resolved_operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    active_groups = _group_operations(active_events)
    resolved_groups = _group_operations(resolved_events)
    active_diagnostics = {
        key: results for key, results in active_groups.items()
        if _operation_is_problematic(results) or _operation_issue(results)
    }
    diagnostic_groups = [(key, results, False) for key, results in active_groups.items()]
    diagnostic_groups.extend((key, results, True) for key, results in resolved_groups.items())
    diagnostic_groups.sort(key=lambda item: _timestamp_iso(item[1][0].get("occurred_at")), reverse=True)
    model, variant = _display_identity(identity, model_row)
    result_summary = _diagnostic_summary_by_identity(active_events, resolved_events)
    attempts = sum(item["attempts"] for item in result_summary.values())
    successes = sum(item["successful"] for item in result_summary.values())
    if model_row:
        attempts = int(model_row.get("attempted_install_count") or 0)
        successes = int(model_row.get("successful_install_count") or 0)
    errors = sum(1 for results in active_diagnostics.values() if _operation_is_problematic(results))
    status = _row_compatibility_status(model_row) if model_row else None
    filters = """<label><span class='sr-only'>Filter installation history</span><select id='diagnostic-state-filter'><option value='all' selected>All</option><option value='succeeded'>Successful</option><option value='failed'>Failed</option><option value='open'>Open</option><option value='resolved'>Resolved</option><option value='identity-pending'>Identity review</option><option value='with-issue'>With issue</option></select></label><button type='button' class='secondary-button filter-clear' data-filter-clear aria-label='Clear diagnostic filters'>Clear</button>"""
    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results, resolved) in enumerate(diagnostic_groups):
        first = results[0]
        state = _operation_state(results, resolved=resolved)
        result = _operation_result(results)
        issue = _operation_issue(results)
        identity_pending = _identity_is_pending(results)
        review_badge = _diagnostic_state_badge(
            "RESOLVED" if resolved else state.replace("-", "_")
            if state in {"open", "in-progress", "under-review"}
            else "IDENTITY_PENDING" if identity_pending else "NONE"
        )
        if state in {"open", "in-progress", "under-review"} and identity_pending:
            review_badge += " " + _diagnostic_state_badge("IDENTITY_PENDING")
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr data-diagnostic-state='{state}' data-review-open='{'true' if state in {'open', 'in-progress', 'under-review', 'identity-pending'} else 'false'}' data-review-resolved='{'true' if resolved else 'false'}' data-identity-pending='{'true' if identity_pending else 'false'}' data-diagnostic-result='{html.escape(result.lower(), quote=True)}' data-has-issue='{'true' if issue else 'false'}'>"
            f"<td class='column-date'>{_timestamp_markup(first.get('occurred_at'))}</td>"
            f"<td>{html.escape(_operation_text(results, 'region'))}</td>"
            f"<td class='column-status'>{_diagnostic_result(result)}</td>"
            f"<td>{_github_issue_link(issue)}</td>"
            f"<td class='column-status'>{review_badge}</td>"
            f"<td class='column-status'><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='Inspect installation {index + 1}'>Inspect</button></td>"
            "</tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity, operation_key, results, resolved=resolved,
            csrf_token=csrf_token, identity_devices=identity_devices,
            canonical_device_model_id=canonical_device_model_id,
        ))
    rows_body = "".join(rows_markup) or "<tr><td colspan='6' class='empty'>No installation history for this model.</td></tr>"
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class='dashboard diagnostics-page' id='main-content'>
        <p class='back-link'><a href='/admin/installations'>{_admin_icon('arrow-left')} Installations</a></p>
        <div class='heading-row'><div><h1>{html.escape(model)}{f' · {html.escape(variant)}' if variant != '—' else ''}</h1></div></div>
        <section class='diagnostic-model-metrics' aria-label='Model diagnostic summary'><article><span>Attempts</span><strong>{attempts}</strong></article><article><span>Successful</span><strong>{successes}</strong></article><article><span>Errors</span>{_admin_error_counter(errors)}</article><article><span>Compatibility status</span><strong>{_status_badge(status.value if status else '')}</strong></article></section>
        <section class='diagnostics-detail-section' aria-labelledby='diagnostic-list-title'>
          <div class='section-heading'><div><h2 id='diagnostic-list-title'>Installations</h2></div></div>
          <form class='filter-bar diagnostic-filter-bar' id='diagnostic-filters'{' hidden' if len(diagnostic_groups) <= 1 else ''}>{filters}</form>
          <p class='results-count' id='diagnostic-results-count' aria-live='polite'>{len(diagnostic_groups)} records</p>
          <div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table'><caption class='sr-only'>Installation and diagnostic records for exact model and variant</caption><thead><tr><th scope='col' class='column-date'>Date</th><th scope='col'>Region</th><th scope='col' class='column-status'>Result</th><th scope='col'>Issue</th><th scope='col' class='column-status'>Review</th><th scope='col' class='column-status'>Action</th></tr></thead><tbody id='diagnostic-rows'>{rows_body}</tbody></table></div>
        </section>
        {''.join(dialogs)}
      </main>
      <script>{_diagnostics_script()}</script>
    """
    return _layout("Installation details", content, sections={"model": model_row, "diagnostics": active_events, "resolved": resolved_operations})


def github_issue_queue_page(
    operations: list[dict[str, Any]] | None,
    identity_devices: list[dict[str, Any]] | None,
    user: dict[str, Any],
    csrf_token: str,
) -> bytes:
    """Render the active linked-issue queue separately from closed diagnostics."""
    def has_valid_issue(event: dict[str, Any]) -> bool:
        try:
            return bool(_normalise_github_issue_reference(event.get("linked_github_issue")))
        except ValueError:
            return False

    groups = _group_operation_tasks([event for event in (operations or []) if has_valid_issue(event)])
    queue: list[tuple[str, list[dict[str, Any]]]] = []
    for operation_key, results in groups.items():
        if _operation_issue(results):
            queue.append((operation_key, results))
    queue.sort(
        key=lambda item: max(_timestamp_iso(result.get("occurred_at")) for result in item[1]),
        reverse=True,
    )
    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results) in enumerate(queue):
        first = results[0]
        identity = str(first.get("compatibility_identity") or first.get("model") or "Unknown device")
        model, variant = _display_identity(identity, first)
        issue = _operation_issue(results)
        state = _operation_state(results, resolved=False)
        result = _operation_result(results)
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr><td>{_github_issue_link(issue)}</td>"
            f"<td><strong>{html.escape(model)}</strong><small class='table-secondary'>{html.escape(variant) if variant != '—' else ''}</small></td>"
            f"<td>{html.escape(_operation_text(results, 'region'))}</td>"
            f"<td class='column-status'>{_diagnostic_result(result)}</td>"
            f"<td class='column-status'>{_diagnostic_state_badge(state)}</td>"
            f"<td class='column-date'>{_timestamp_markup(max((result.get('occurred_at') for result in results), key=_timestamp_iso))}</td>"
            f"<td class='column-status'><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='Inspect GitHub issue {index + 1}'>Inspect</button></td></tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity,
            operation_key,
            results,
            resolved=False,
            csrf_token=csrf_token,
            identity_devices=identity_devices,
            canonical_device_model_id=first.get("canonical_device_model_id"),
            return_to="/admin/review/github-issues",
        ))
    rows = "".join(rows_markup) or (
        "<tr><td colspan='7' class='empty'>No active GitHub review tasks are waiting for resolution.</td></tr>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class='dashboard diagnostics-page' id='main-content'>
        <p class='back-link'><a href='/admin/installations'>{_admin_icon('arrow-left')} Installations</a></p>
        <div class='heading-row'><div><h1>GitHub review tasks</h1></div></div>
        <section class='diagnostics-detail-section' aria-labelledby='github-issue-queue-title'>
          <div class='section-heading'><div><h2 id='github-issue-queue-title'>Linked diagnostics</h2><span class='table-help'>{len(queue)} tasks</span></div></div>
          <div class='table-wrap diagnostic-list-wrap'><table class='admin-table diagnostic-list-table'><caption class='sr-only'>GitHub issues linked to active diagnostics</caption><thead><tr><th scope='col'>Issue</th><th scope='col'>Device</th><th scope='col'>Map / region</th><th scope='col' class='column-status'>Result</th><th scope='col' class='column-status'>Workflow</th><th scope='col' class='column-date'>Last activity</th><th scope='col' class='column-status'>Action</th></tr></thead><tbody>{rows}</tbody></table></div>
        </section>
        {''.join(dialogs)}
      </main>
      <script>{_diagnostics_script()}</script>
    """
    return _layout("GitHub issue queue", content, sections={"queue": operations})


def _admin_map_capability(value: Any) -> tuple[str, str]:
    if value is True:
        return "Yes", "yes"
    if value is False:
        return "No", "no"
    return "Unknown", "unknown"


def _admin_installation_authorization(map_capable: Any, active: Any = True) -> tuple[str, str, str]:
    _, authorization = installation_authorization_for_row({
        "active": active is True,
        "map_capable": map_capable,
    })
    return _admin_installation_authorization_code(authorization)


def _admin_installation_authorization_code(value: Any) -> tuple[str, str, str]:
    status = str(value or "PENDING").upper()
    labels = {
        "APPROVED": ("Approved", "approved", "APPROVED"),
        "BLOCKED": ("Blocked", "blocked", "BLOCKED"),
        "PENDING": ("Pending", "pending", "PENDING"),
    }
    return labels.get(status, ("Pending", "pending", "PENDING"))


def _admin_device_payload(
    rows: list[dict[str, Any]], sync: dict[str, Any] | None,
) -> dict[str, Any]:
    def sync_count(key: str) -> int | None:
        value = (sync or {}).get(key)
        return int(value) if value is not None else None

    devices: list[dict[str, Any]] = []
    for row in rows:
        attempts = int(row.get("attempted_install_count") or 0)
        successful = int(row.get("successful_install_count") or 0)
        failed = int(row.get("failed_install_count") or 0)
        asset_url = row.get("asset_url")
        if not (
            row.get("asset_status") == "AVAILABLE"
            and isinstance(asset_url, str)
            and asset_url.startswith("https://api.terento.app/assets/devices/")
        ):
            asset_url = None
        source_image_url = _official_source_image_url(row.get("source_image_url"))
        stored_map_capable = row.get("map_capable")
        classified_map_capable = classify_map_capable(
            row.get("canonical_model") or row.get("model"),
            row.get("manufacturer") or "Garmin",
        )
        map_capable = classified_map_capable
        if map_capable is None and successful > 0:
            # A verified successful installation is model/variant-specific
            # evidence that the catalog classifier has not learned yet.
            map_capable = True
        evidence_status = calculate_compatibility_status(
            successful_install_count=int(row.get("compatibility_successful_install_count", successful) or 0),
            recognized_map_capable_evidence=map_capable is True,
        )
        authorization_label, _, authorization_code = _admin_installation_authorization(
            row.get("map_capable"),
            row.get("active"),
        )
        public_identity = str(row.get("public_compatibility_identity") or "").strip()
        public_review_status = str(row.get("public_review_status") or "PENDING").upper()
        public_enabled = bool(row.get("public_statistics_enabled", False))
        public_eligible = bool(public_identity and evidence_status)
        public_published = bool(
            public_eligible
            and public_review_status == "APPROVED"
            and public_enabled
        )
        if asset_url and not (source_image_url and row.get("asset_scope") == "GENERIC"):
            image = {"url": asset_url, "origin": "controlled", "status": "AVAILABLE"}
        elif source_image_url:
            image = {"url": source_image_url, "origin": "garmin-source", "status": "SOURCE"}
        else:
            image = generic_fallback_image()
        usb_identities = row.get("usb_identities") or []
        devices.append({
            "id": row.get("device_id"),
            "manufacturer": row.get("manufacturer") or "Garmin",
            "family": row.get("family_canonical_name"),
            "familyName": row.get("family_name"),
            "model": row.get("model"),
            "canonicalModel": row.get("canonical_model"),
            "variant": _known_variant_description(row),
            "caseSizeMm": row.get("case_size_mm"),
            "displayType": row.get("display_type"),
            "identityMappings": row.get("identity_mappings") or [],
            "screenTechnology": row.get("screen_technology"),
            "solar": row.get("solar"), "inReach": row.get("inreach"),
            "specificationSource": row.get("specification_source"),
            "specificationEvidence": row.get("specification_evidence") or {},
            "partNumber": row.get("part_number"),
            "productURL": row.get("product_url"),
            "active": bool(row.get("active", True)),
            "mapCapable": stored_map_capable,
            "observedMapCapability": map_capable,
            "supportStatus": str(row.get("support_status") or "NOT_EVALUATED").upper(),
            "installationAuthorization": authorization_code,
            "installationAuthorizationLabel": authorization_label,
            "evidenceStatus": evidence_status.value if evidence_status else None,
            "publicCompatibility": {
                "eligible": public_eligible,
                "published": public_published,
                "reviewStatus": public_review_status,
                "statisticsEnabled": public_enabled,
                "compatibilityIdentity": public_identity or None,
                "displayName": row.get("public_display_name"),
            },
            "recordSource": str(row.get("record_source") or "CURRENT_RETAIL").upper(),
            "collectorManaged": bool(row.get("collector_managed", True)),
            "asset": {"status": "AVAILABLE", "url": asset_url} if asset_url else {"status": "MISSING"},
            "sourceAsset": {"url": source_image_url, "scope": "MODEL"} if source_image_url else None,
            "image": image,
            "usbIdentities": usb_identities,
            "installationStats": {
                "attempts": attempts,
                "successful": successful,
                "failed": failed,
                "successRate": round(successful * 100 / attempts, 1) if attempts else None,
                "firstSuccessfulAt": _timestamp_iso(row.get("first_success")) or None,
                "lastSuccessfulAt": _timestamp_iso(row.get("last_success")) or None,
                "lastEvidenceAt": _timestamp_iso(row.get("last_evidence")) or None,
            },
            "catalog": {
                "firstSeenAt": _timestamp_iso(row.get("first_seen_at")) or None,
                "createdAt": _timestamp_iso(row.get("created_at")) or None,
                "updatedAt": _timestamp_iso(row.get("updated_at")) or None,
                "lastSeenAt": _timestamp_iso(row.get("last_seen_at")) or None,
                "newInLatestSync": bool(
                    sync and row.get("first_seen_collection_run_id") == sync.get("id")
                ),
                "firstSeenSyncId": row.get("first_seen_collection_run_id"),
                "lastSeenSyncId": row.get("last_seen_collection_run_id"),
            },
        })

    attempts = sum(device["installationStats"]["attempts"] for device in devices)
    successful = sum(device["installationStats"]["successful"] for device in devices)
    eligible_map_models = sum(
        device["active"] is True and device["mapCapable"] is True
        for device in devices
    )
    map_models_with_success = sum(
        device["active"] is True
        and device["mapCapable"] is True
        and device["installationStats"]["successful"] > 0
        for device in devices
    )
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "models": len(devices),
            "mapCapable": sum(device["mapCapable"] is True for device in devices),
            "approved": sum(device["installationAuthorization"] == "APPROVED" for device in devices),
            "successful": successful,
            "installAttempts": attempts,
            "successfulInstalls": successful,
            "successRate": round(successful * 100 / attempts, 1) if attempts else None,
            "eligibleMapModels": eligible_map_models,
            "mapModelsWithSuccess": map_models_with_success,
            "mapModelCoverageRate": (
                round(map_models_with_success * 100 / eligible_map_models, 1)
                if eligible_map_models else None
            ),
            "newThisSync": sync_count("records_added"),
        },
        "sync": {
            "id": sync.get("id") if sync else None,
            "status": sync.get("status") if sync else None,
            "startedAt": _timestamp_iso(sync.get("started_at")) or None if sync else None,
            "completedAt": _timestamp_iso(
                sync.get("finished_at") or sync.get("completed_at")
            ) or None if sync else None,
            "recordsTotalBefore": sync_count("records_total_before"),
            "recordsTotalAfter": sync_count("records_total_after"),
            "recordsAdded": sync_count("records_added"),
            "recordsUpdated": sync_count("records_updated"),
        },
        "devices": devices,
    }


def _admin_status_badge(label: str, kind: str) -> str:
    return f"<span class='admin-state admin-state-{html.escape(kind)}'>{html.escape(label)}</span>"


def _admin_device_row(device: dict[str, Any], index: int) -> str:
    model, variant, _ = _identity_parts(device)
    provenance = _historical_catalog_indicator() if variant == "Historical" else ""
    variant = "—" if provenance else variant or "—"
    family = str(device.get("familyName") or device.get("family") or "")
    map_label, map_kind = _admin_map_capability(device.get("mapCapable"))
    authorization_label, authorization_kind, _ = _admin_installation_authorization_code(
        device.get("installationAuthorization")
    )
    evidence_status = str(device.get("evidenceStatus") or "").upper()
    stats = device["installationStats"]
    catalog = device["catalog"]
    search = " ".join(str(value or "") for value in (
        model, device.get("canonicalModel"), family, variant,
        device.get("caseSizeMm"), device.get("partNumber"), device.get("displayType"),
    )).strip()
    image_url = (device.get("image") or {}).get("url") or device.get("asset", {}).get("url")
    image = (
        f"<img class='device-thumb' src='{html.escape(image_url, quote=True)}' alt='' loading='lazy'>"
        if image_url else
        "<span class='device-thumb device-thumb-placeholder' aria-hidden='true'></span>"
    )
    new_badge = "<span class='new-badge'>New</span>" if catalog.get("newInLatestSync") else ""
    last_success = _timestamp_markup(stats.get("lastSuccessfulAt")) if stats.get("lastSuccessfulAt") else "—"
    detail_url = _device_detail_url(device.get("id"), origin="devices")
    return f"""<tr data-device-index='{index}' data-device-url='{html.escape(detail_url, quote=True)}' data-search='{html.escape(search, quote=True)}' data-model='{html.escape(model.lower(), quote=True)}' data-updated='{html.escape(str(catalog.get('updatedAt') or ''), quote=True)}' data-installs='{stats['attempts']}' data-evidence='{html.escape(str(stats.get('lastSuccessfulAt') or ''), quote=True)}' data-status='{html.escape(evidence_status.lower())}'>
      <td><a class='device-model-button' href='{html.escape(detail_url, quote=True)}'>{image}<span class='device-model-copy'><strong>{html.escape(model)}</strong>{provenance}{new_badge}</span></a></td>
      <td>{html.escape(variant)}</td>
      <td class='column-status' title='Observed map capability: {html.escape(_admin_map_capability(device.get("observedMapCapability"))[0], quote=True)}'>{_admin_status_badge(map_label, f'map-{map_kind}')}</td>
      <td class='column-status'>{_admin_status_badge(authorization_label, f'authorization-{authorization_kind}')}</td>
      <td class='column-status'>{_status_badge(evidence_status)}</td>
      <td class='column-number numeric'>{stats['attempts']}</td>
      <td class='column-number numeric'>{stats['successful']}</td>
      <td class='column-date'>{last_success}</td>
    </tr>"""


def devices_page(
    rows: list[dict[str, Any]], sync: dict[str, Any] | None,
    user: dict[str, Any], csrf_token: str,
) -> bytes:
    payload = _admin_device_payload(rows, sync)
    summary = payload["summary"]
    sync_data = payload["sync"]
    completed = _timestamp_markup(sync_data["completedAt"]) if sync_data["completedAt"] else "No successful sync recorded"
    sync_line = (
        f"<button type='button' class='summary-filter-link' id='device-show-new'>{sync_data['recordsAdded']} new</button> · {sync_data['recordsUpdated']} updated"
        if sync_data["id"] is not None and sync_data["recordsAdded"] is not None
        else ("Counts unavailable for this historical run" if sync_data["id"] is not None else "No sync recorded")
    )
    family_values = sorted({
        str(device.get("familyName") or device.get("family") or "").strip()
        for device in payload["devices"]
        if str(device.get("familyName") or device.get("family") or "").strip()
    }, key=str.casefold)
    family_options = "".join(
        f"<option value='{html.escape(value, quote=True)}'>{html.escape(value)}</option>"
        for value in family_values
    )
    rows_html = "".join(
        _admin_device_row(device, index)
        for index, device in enumerate(payload["devices"])
    )
    payload_json = _admin_json({**payload, "csrfToken": csrf_token})
    mobile_sort_options = "".join(
        f"<option value='{key}:{direction}'>{label} · {suffix}</option>"
        for key, label in [("model", "Model"), ("variant", "Variant"), ("maps", "Maps"),
                           ("authorization", "Install policy"), ("status", "Evidence"),
                           ("attempts", "Attempts"), ("success", "Successful"), ("evidence", "Last success")]
        for direction, suffix in [("ascending", "ascending"), ("descending", "descending")]
    )
    table_header = _device_table_header()
    table_columns = _device_table_columns()
    device_list = "<section class='compact-empty-state' aria-labelledby='device-list-title'><h2 id='device-list-title'>No devices</h2><p>No Garmin device records are available. Run or check the latest catalog sync.</p></section>" if not rows_html else f"""
        <section class="admin-summary-strip device-summary-strip" aria-label="Device catalog summary and sync">
          <p class="device-summary-metrics"><strong>{summary['mapModelsWithSuccess']} of {summary['eligibleMapModels']}</strong><span> models covered · {_format_rate(summary['mapModelCoverageRate'])}</span></p>
          <p class="device-summary-sync"><strong>Last sync</strong> {completed}<span> · {sync_line}</span>{f"<span> · {html.escape(str(sync_data['status'] or '').title())}</span>" if sync_data['status'] else ''}</p>
        </section>
        <section class="evidence-section" aria-label="Device catalog">
          <p class="sr-only">Compatibility status and installation counts remain backend-derived.</p>
          <form class="filter-bar admin-filter-bar device-filter-bar" id="device-filters" role="search">
            <label class="filter-search"><span class="sr-only">Search devices</span><input id="device-search" type="search" placeholder="Search devices" autocomplete="off"></label>
            <label><span class="sr-only">Filter by map capability</span><select id="device-map"><option value="yes" selected>Maps: Yes</option><option value="no">Maps: No</option><option value="unknown">Maps: Unknown</option><option value="all">All maps</option></select></label>
            <details class="admin-disclosure filter-disclosure" id="device-more-filters"><summary>More filters</summary><div class="disclosure-body">
              <label><span class="sr-only">Filter by family</span><select id="device-family"><option value="all">All families</option>{family_options}</select></label>
              <label><span class="sr-only">Filter by install policy</span><select id="device-support"><option value="all">All policies</option><option value="APPROVED">Approved</option><option value="BLOCKED">Blocked</option><option value="PENDING">Pending</option></select></label>
              <label><span class="sr-only">Filter by evidence</span><select id="device-status"><option value="all">All evidence</option><option value="TESTING">Testing</option><option value="TESTED">Tested</option><option value="SUPPORTED">Supported</option><option value="VERIFIED">Verified</option><option value="unavailable">Unavailable</option></select></label>
            </div></details>
            <label class="device-mobile-sort"><span class="sr-only">Sort devices</span><select id="device-mobile-sort">{mobile_sort_options}</select></label>
            <p class="results-count" id="device-results-count" aria-live="polite">{_count_label(summary['mapCapable'], 'result')}</p>
            <button type="button" class="secondary-button filter-clear" data-filter-clear aria-label="Clear device filters">Clear</button>
          </form>
          <div class="device-sticky-header" id="device-sticky-header"><div class="device-sticky-header-scroll"><table class="admin-table"><caption class="sr-only">Device catalog columns</caption>{table_columns}{table_header}</table></div></div>
          <div class="table-wrap device-table-wrap"><table class="admin-table"><caption class="sr-only">Device catalog and Terento installation evidence</caption>{table_columns}{table_header}<tbody id="device-rows">{rows_html}</tbody></table></div>
          <div class="device-pagination" id="device-pagination" hidden><button type="button" id="device-previous">Previous</button><span id="device-page-status"></span><button type="button" id="device-next">Next</button></div>
        </section>
    """
    content = f"""
      {_admin_header(user, csrf_token, active="devices")}
      <main class="dashboard devices-page" id="main-content">
        <div class="heading-row"><div><h1>Devices</h1></div></div>
        {device_list}
      </main>
      <script>const terentoAdminDevices = {payload_json};{_devices_script()}</script>
    """
    return _layout("Devices", content, sections={"devices": payload})


def _device_table_header() -> str:
    return """<thead><tr><th scope="col" class="column-text" aria-sort="ascending"><button type="button" class="device-sort-button" data-device-sort="model" aria-label="Model">Model <span aria-hidden="true">↑</span></button></th><th scope="col" class="column-text" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="variant" aria-label="Variant">Variant <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="maps" aria-label="Maps" title="Stored catalog map capability">Maps <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="authorization" aria-label="Install policy" title="Install policy">Install policy <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="status" aria-label="Evidence" title="Compatibility evidence">Evidence <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="attempts" aria-label="Install attempts" title="Install attempts">Attempts <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="success" aria-label="Successful installations" title="Successful installations">Successful <span aria-hidden="true">↕</span></button></th><th scope="col" class="column-date" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="evidence" aria-label="Last successful installation" title="Last successful installation">Last success <span aria-hidden="true">↕</span></button></th></tr></thead>"""


def _device_table_columns() -> str:
    return """<colgroup class="device-table-columns"><col class="device-column-model"><col class="device-column-variant"><col class="device-column-maps"><col class="device-column-authorization"><col class="device-column-status"><col class="device-column-attempts"><col class="device-column-successful"><col class="device-column-last-success"></colgroup>"""


def _campaign_info(control_id: str, title: str, body: str) -> str:
    info_id = f"{control_id}-info"
    return (
        f"<button class='info-control' type='button' aria-expanded='false' "
        f"aria-controls='{info_id}' aria-label='More information about {html.escape(title)}'>i</button>"
        f"<div class='info-popover' id='{info_id}' role='region' aria-label='{html.escape(title)} information' hidden><strong>{html.escape(title)}</strong>{body}</div>"
    )


def campaign_links_page(user: dict[str, Any], csrf_token: str) -> bytes:
    destination_options = "".join(
        f"<option value='{html.escape(key)}'>{html.escape(label)}</option>"
        for key, label in (("home", "Home"), ("download", "Download"), ("compatibility", "Compatibility"), ("other", "Other"))
    )
    source_options = "".join(
        f"<option value='{html.escape(value)}'>{html.escape(label)}</option>"
        for value, label in SOURCE_OPTIONS
    )
    medium_options = "".join(
        f"<option value='{html.escape(value)}'>{html.escape(label)}</option>"
        for value, label in MEDIUM_OPTIONS
    )
    campaign_options = "".join(f"<option value='{html.escape(value)}'></option>" for value in CAMPAIGN_SUGGESTIONS)
    content = f"""
      {_admin_header(user, csrf_token, active="campaigns")}
      <main class="dashboard campaign-page" id="main-content">
        <div class="heading-row"><div><h1>Campaign links</h1></div></div>
        <section class="campaign-card" aria-labelledby="campaign-builder-title">
          <div class="section-heading"><div><h2 id="campaign-builder-title">Campaign link builder</h2></div><p class="table-help">Links are generated locally in this browser.</p></div>
          <div class="filter-bar admin-filter-bar campaign-preset-row">
            <label class="campaign-label" for="campaign-preset">Preset { _campaign_info("campaign-preset", "Preset", "<p>Choose a common campaign setup, then edit any field before copying.</p><p><strong>Recommendation:</strong> use the Reddit preset for a community post.</p>") }</label>
            <select id="campaign-preset"><option value="reddit-community" selected>Reddit community post</option><option value="">Custom</option></select>
          </div>
          <form id="campaign-link-form" class="campaign-form" novalidate>
            <div class="campaign-fields">
              <div class="campaign-field campaign-field-wide">
                <label class="campaign-label" for="destination">Destination <span class="required-label">Required</span> { _campaign_info("destination", "Destination", "<p>Choose the Terento page a visitor should reach.</p><p><strong>Recommendation:</strong> use the most specific page for the campaign.</p><p><strong>Example:</strong> Home → <code>https://terento.app/</code></p>") }</label>
                <select id="destination" required>{destination_options}</select>
                <div class="custom-input" id="destination-custom-wrap" hidden aria-hidden="true"><label for="destination-custom">Custom Terento URL or path <span class="required-label">Required for Other</span></label><input id="destination-custom" type="url" inputmode="url" placeholder="https://terento.app/your-page" autocomplete="off"></div>
              </div>
              <div class="campaign-field">
                <label class="campaign-label" for="source">Source <span class="required-label">Required</span> { _campaign_info("source", "Source", "<p>Identifies the platform or referrer that sends traffic.</p><p><strong>Recommendation:</strong> keep one source value per platform.</p><p><strong>Example:</strong> Reddit → <code>reddit</code></p>") }</label>
                <select id="source" required>{source_options}</select>
                <div class="custom-input" id="source-custom-wrap" hidden aria-hidden="true"><label for="source-custom">Custom source <span class="required-label">Required for Other</span></label><input id="source-custom" type="text" placeholder="forum" autocomplete="off"></div>
              </div>
              <div class="campaign-field">
                <label class="campaign-label" for="medium">Medium <span class="required-label">Required</span> { _campaign_info("medium", "Medium", "<p>Describes the channel type used by the source.</p><p><strong>Recommendation:</strong> use <code>social</code> for social networks and <code>community</code> for forums.</p><p><strong>Example:</strong> Social → <code>social</code></p>") }</label>
                <select id="medium" required>{medium_options}</select>
                <div class="custom-input" id="medium-custom-wrap" hidden aria-hidden="true"><label for="medium-custom">Custom medium <span class="required-label">Required for Other</span></label><input id="medium-custom" type="text" placeholder="partner" autocomplete="off"></div>
              </div>
              <div class="campaign-field">
                <label class="campaign-label" for="campaign">Campaign <span class="required-label">Required</span> { _campaign_info("campaign", "Campaign", "<p>Names the launch, initiative, or audience being measured.</p><p><strong>Recommendation:</strong> use a stable name such as <code>early_beta</code>.</p><p><strong>Example:</strong> <code>early_beta</code></p>") }</label>
                <input id="campaign" type="text" value="early_beta" list="campaign-suggestions" required autocomplete="off"><datalist id="campaign-suggestions">{campaign_options}</datalist>
              </div>
              <div class="campaign-field">
                <label class="campaign-label" for="content">Content <span class="optional-label">Optional</span> { _campaign_info("content", "Content", "<p>Distinguishes different creatives, posts, or calls to action in one campaign.</p><p><strong>Recommendation:</strong> use it when one placement has multiple variants.</p><p><strong>Example:</strong> <code>garminwatches</code></p>") }</label>
                <input id="content" type="text" placeholder="garminwatches" autocomplete="off">
              </div>
              <div class="campaign-field">
                <label class="campaign-label" for="term">Term <span class="optional-label">Optional</span> { _campaign_info("term", "Term", "<p>Usually used for paid-search keywords or targeting.</p><p><strong>Recommendation:</strong> leave blank for normal social or community links.</p><p><strong>Example:</strong> <code>garmin maps</code></p>") }</label>
                <input id="term" type="text" placeholder="garmin maps" autocomplete="off">
              </div>
            </div>
          </form>
          <section class="campaign-result" aria-labelledby="generated-link-title">
            <div class="section-heading"><div><h2 id="generated-link-title">Generated URL</h2></div></div>
            <p class="incomplete-state" id="incomplete-state" aria-live="polite">Complete the required fields to generate a link.</p>
            <div class="generated-url-row" id="generated-url-row" hidden><output id="generated-url" class="generated-url" aria-live="polite"></output><button id="copy-link" type="button" class="copy-button">Copy link</button><span id="copy-status" class="copy-status" role="status" aria-live="polite"></span></div>
          </section>
          <section class="attribution-preview" aria-labelledby="attribution-title">
            <div><h2 id="attribution-title">Umami attribution preview</h2><p class="table-help">This preview explains the attribution values; no Umami query parameter is added.</p></div>
            <dl class="preview-grid"><div><dt>Source</dt><dd id="preview-source">—</dd></div><div><dt>Medium</dt><dd id="preview-medium">—</dd></div><div><dt>Campaign</dt><dd id="preview-campaign">—</dd></div><div><dt>Content</dt><dd id="preview-content">—</dd></div><div><dt>Term</dt><dd id="preview-term">—</dd></div></dl>
          </section>
        </section>
      </main>
      <script>{_campaign_links_script()}</script>
    """
    return _layout("Campaign links", content)


def account_page(user: dict[str, Any], csrf_token: str, *, error: str | None = None, success: str | None = None) -> bytes:
    notice = _error(error) if error else (f"<p class='success'>{html.escape(success or '')}</p>" if success else "")
    return _layout(
        "Account",
        f"""
        {_admin_header(user, csrf_token, active="account")}
        <main class="auth-card account" id="main-content"><h1>Account</h1>{notice}
          <form method="post" action="/admin/account">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
            <label>Username<input name="username" value="{html.escape(str(user['username']))}" autocomplete="username" required></label>
            <label>Current password<input type="password" name="current_password" autocomplete="current-password" required></label>
            <label>New password <small>(leave blank to keep it)</small><input type="password" name="new_password" autocomplete="new-password" minlength="14"></label>
            <label>Confirm new password<input type="password" name="new_password_confirmation" autocomplete="new-password" minlength="14"></label>
            <button type="submit">Save changes</button>
          </form>
        </main>
        """,
    )


def _statistics_row(
    row: dict[str, Any],
    diagnostic_summary: dict[str, int] | None = None,
    *, catalog_device: dict[str, Any] | None = None,
) -> str:
    model, variant, identity = _identity_parts(row)
    if catalog_device is not None:
        # Exact catalog identity drives display; original reported identity remains searchable.
        model, variant, _ = _identity_parts(catalog_device)
    summary = diagnostic_summary or {}
    attempted = int(row.get("attempted_install_count", summary.get("attempts", 0)) or 0)
    successful = int(row.get("successful_install_count", summary.get("successful", 0)) or 0)
    failed = int(row.get("failed_install_count", summary.get("failed", 0)) or 0)
    open_errors = int(summary.get("open_errors") or 0)
    status_value = _row_compatibility_status(row)
    status = status_value.value if status_value else ""
    search_text = " ".join((model, variant, str(row.get("family") or ""), identity)).strip()
    activity = max((_timestamp_iso(row.get(key)) for key in ("last_success", "last_failure", "last_evidence")), default="")
    diagnostics_url = _model_detail_url(row)
    pending_count = int(summary.get("identity_pending") or 0)
    model_cell = html.escape(model)
    if variant == "Historical":
        model_cell += " " + _historical_catalog_indicator()
        variant = "—"
    if pending_count:
        model_cell += (
            f" <span class='identity-pending-indicator' aria-label='{pending_count} identity review'>"
            "Identity review</span>"
        )
    model_cell = (
        f"<a class='device-model-button' href='{html.escape(diagnostics_url, quote=True)}'>"
        f"{model_cell}</a>"
    )
    open_errors_markup = _admin_error_counter(
        open_errors,
        href=_model_detail_url(row, state="open") if open_errors else None,
        aria_label=f"View {open_errors} open {'error' if open_errors == 1 else 'errors'}",
    )
    cells = (
        ("", model_cell),
        ("", html.escape(variant)),
        ("column-status", _status_badge(status)),
        ("column-number numeric", html.escape(str(attempted))),
        ("column-number numeric", html.escape(str(successful))),
        ("column-number numeric installation-failed-value", html.escape(str(failed))),
        ("column-number numeric", open_errors_markup),
        ("column-date", _timestamp_markup(row.get("last_success"))),
    )
    return (
        f"<tr class='evidence-model-row' data-search='{html.escape(search_text, quote=True)}' data-model='{html.escape(model, quote=True)}' data-variant='{html.escape(variant if variant != '—' else '', quote=True)}' data-identity='{html.escape(_identity_group_key(row), quote=True)}' data-successful-count='{successful}' data-failed-count='{failed}' data-last-success='{_timestamp_iso(row.get('last_success'))}' data-status='{html.escape(status.lower(), quote=True)}' data-activity='{html.escape(activity, quote=True)}' data-attempts='{attempted}' data-errors='{open_errors}' data-failed='{str(failed > 0).lower()}' data-successful='{str(successful > 0).lower()}' data-diagnostics-url='{html.escape(diagnostics_url, quote=True)}'>"
        + "".join(f"<td class='{css_class}'>{cell}</td>" if css_class else f"<td>{cell}</td>" for css_class, cell in cells)
        + f"</tr>"
    )


def _status_badge(value: str) -> str:
    try:
        status = CompatibilityStatus(str(value).upper())
    except ValueError:
        return "<span class='status-badge status-unavailable' role='img' aria-label='Compatibility status unavailable'>Unavailable</span>"
    label = status.value.title()
    return (
        f"<span class='status-badge status-{status.value.lower()}' role='img' "
        f"aria-label='{html.escape(label)}: {html.escape(STATUS_PUBLIC_COPY[status])}'>"
        f"{html.escape(label)}</span>"
    )


def _device_last_success_comparator_script() -> str:
    return r"""(a, b, direction, textCompare) => {
        const timestamp = (device) => device.installationStats.lastSuccessfulAt
          ? Date.parse(device.installationStats.lastSuccessfulAt) : null;
        const aValue = timestamp(a);
        const bValue = timestamp(b);
        if (aValue === null) return bValue === null ? textCompare(a.id, b.id) : 1;
        if (bValue === null) return -1;
        const comparison = aValue - bValue;
        return (direction === 'descending' ? -comparison : comparison) || textCompare(a.id, b.id);
      }"""


def _table_filter_state_script() -> str:
    return r"""let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}'); } catch (_) { saved = {}; }
      const restoreSelect = (control, key, fallback) => {
        const value = parameters.has(key) ? parameters.get(key) : saved[key];
        control.value = [...control.options].some(option => option.value === value) ? value : fallback;
      };"""


def _devices_script() -> str:
    script = r"""(() => {
      const devices = terentoAdminDevices.devices || [];
      const body = document.querySelector('#device-rows');
      const form = document.querySelector('#device-filters');
      const search = document.querySelector('#device-search');
      const family = document.querySelector('#device-family');
      const map = document.querySelector('#device-map');
      const support = document.querySelector('#device-support');
      const status = document.querySelector('#device-status');
      const sortButtons = [...document.querySelectorAll('[data-device-sort]')];
      const count = document.querySelector('#device-results-count');
      const pagination = document.querySelector('#device-pagination');
      const previous = document.querySelector('#device-previous');
      const next = document.querySelector('#device-next');
      const pageStatus = document.querySelector('#device-page-status');
      const showNewButton = document.querySelector('#device-show-new');
      const tableScroll = document.querySelector('.device-table-wrap');
      const stickyHeaderScroll = document.querySelector('.device-sticky-header-scroll');
      const stickyHeaderTable = stickyHeaderScroll?.querySelector('table');
      if (!body || !form || !search || !family || !map || !support || !status || !count) return;

      const pageSize = 50;
      let page = 0;
      let sortKey = 'model';
      let sortDirection = 'ascending';
      let showNew = false;
      let publicationReview = false;
      const storageKey = 'terento.admin.devices.filters';
      const parameters = new URLSearchParams(window.location.search);
      __TABLE_FILTER_STATE__
      search.value = parameters.has('search') ? parameters.get('search') : (saved.search || '');
      restoreSelect(family, 'family', 'all');
      restoreSelect(map, 'maps', 'yes');
      restoreSelect(support, 'authorization', 'all');
      restoreSelect(status, 'status', 'all');
      sortKey = parameters.get('sort') || saved.sort || 'model';
      sortDirection = parameters.get('direction') || saved.direction || 'ascending';
      publicationReview = parameters.get('review') === 'publication';
      if (publicationReview) { search.value = ''; family.value = 'all'; map.value = 'all'; support.value = 'all'; status.value = 'all'; }
      showNew = parameters.get('new') === '1' || (!parameters.size && saved.new === true);
      const mapValue = (device) => device.mapCapable === true ? 'yes' : device.mapCapable === false ? 'no' : 'unknown';
      const deviceSearch = (device) => [device.id, device.model, device.canonicalModel, device.family, device.familyName, device.variant, device.caseSizeMm, device.partNumber, device.displayType].filter(Boolean).join(' ').toLocaleLowerCase();
      const textCompare = (a, b) => String(a || '').localeCompare(String(b || ''), undefined, {sensitivity: 'base', numeric: true});
      const statusOrder = {unavailable: 0, TESTING: 1, TESTED: 2, SUPPORTED: 3, VERIFIED: 4};
      const mapOrder = {unknown: 0, no: 1, yes: 2};
      const authorizationOrder = {PENDING: 0, BLOCKED: 1, APPROVED: 2};
      const compareLastSuccess = __TERENTO_LAST_SUCCESS_COMPARATOR__;
      const sortValue = (device, key) => ({
        model: device.model,
        variant: device.variant,
        maps: mapOrder[mapValue(device)],
        authorization: authorizationOrder[device.installationAuthorization || 'PENDING'],
        status: statusOrder[device.evidenceStatus || 'unavailable'],
        attempts: Number(device.installationStats.attempts || 0),
        success: Number(device.installationStats.successful || 0),
        evidence: device.installationStats.lastSuccessfulAt ? Date.parse(device.installationStats.lastSuccessfulAt) : null,
      })[key];
      const compareDevices = (a, b) => {
        if (sortKey === 'evidence') return compareLastSuccess(a, b, sortDirection, textCompare);
        const aValue = sortValue(a, sortKey);
        const bValue = sortValue(b, sortKey);
        if (aValue === null || aValue === undefined || aValue === '') return bValue === null || bValue === undefined || bValue === '' ? textCompare(a.id, b.id) : 1;
        if (bValue === null || bValue === undefined || bValue === '') return -1;
        const comparison = typeof aValue === 'number' && typeof bValue === 'number' ? aValue - bValue : textCompare(aValue, bValue);
        return (sortDirection === 'descending' ? -comparison : comparison) || textCompare(a.id, b.id);
      };
      const updateSortHeaders = () => sortButtons.forEach((button) => {
        const active = button.dataset.deviceSort === sortKey;
        const header = button.closest('th');
        const indicator = button.querySelector('span');
        if (header) header.setAttribute('aria-sort', active ? sortDirection : 'none');
        if (indicator) indicator.textContent = active ? (sortDirection === 'ascending' ? '↑' : '↓') : '↕';
      });
      const saveState = () => {
        const state = {
          search: search.value, family: family.value, maps: map.value,
          authorization: support.value, status: status.value,
          sort: sortKey, direction: sortDirection, new: showNew,
        };
        try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* optional */ }
        const query = new URLSearchParams();
        if (search.value) query.set('search', search.value);
        query.set('maps', map.value);
        if (family.value !== 'all') query.set('family', family.value);
        if (support.value !== 'all') query.set('authorization', support.value);
        if (status.value !== 'all') query.set('status', status.value);
        if (sortKey !== 'model') query.set('sort', sortKey);
        if (sortDirection !== 'ascending') query.set('direction', sortDirection);
        if (showNew) query.set('new', '1');
        if (publicationReview) query.set('review', 'publication');
        history.replaceState(null, '', `${window.location.pathname}?${query.toString()}`);
      };
      const matching = () => {
        const query = search.value.trim().toLocaleLowerCase();
        return devices.filter((device) => {
          if (publicationReview && !(device.publicCompatibility?.eligible && ['TESTED', 'SUPPORTED', 'VERIFIED'].includes(device.evidenceStatus) && !device.publicCompatibility?.published && device.publicCompatibility?.reviewStatus !== 'REJECTED')) return false;
          if (showNew) return device.catalog?.newInLatestSync === true;
          const matchesSearch = !query || deviceSearch(device).includes(query);
          const matchesFamily = family.value === 'all' || family.value === (device.familyName || device.family);
          const matchesMap = map.value === 'all' || mapValue(device) === map.value;
          const matchesAuthorization = support.value === 'all' || (device.installationAuthorization || 'PENDING') === support.value;
          const matchesStatus = status.value === 'all' || (device.evidenceStatus || 'unavailable') === status.value;
          return matchesSearch && matchesFamily && matchesMap && matchesAuthorization && matchesStatus;
        }).sort(compareDevices);
      };
      const refresh = () => {
        const visible = matching();
        const totalPages = Math.max(1, Math.ceil(visible.length / pageSize));
        page = Math.min(page, totalPages - 1);
        const pageRows = visible.slice(page * pageSize, (page + 1) * pageSize);
        const rowsById = new Map([...body.querySelectorAll('tr[data-device-index]')].map((row) => {
          const device = devices[Number(row.dataset.deviceIndex)];
          return [device && device.id, row];
        }));
        rowsById.forEach((row) => { row.hidden = true; });
        pageRows.forEach((device) => {
          const row = rowsById.get(device.id);
          if (!row) return;
          row.hidden = false;
          body.appendChild(row);
        });
        count.textContent = `${visible.length} ${publicationReview ? 'awaiting publication review' : visible.length === 1 ? 'result' : 'results'}`;
        pagination.hidden = visible.length <= pageSize;
        pageStatus.textContent = `Page ${page + 1} of ${totalPages}`;
        previous.disabled = page === 0;
        next.disabled = page >= totalPages - 1;
        saveState();
      };
      const reset = () => { showNew = false; publicationReview = false; page = 0; refresh(); };
      const mobileSort = document.querySelector('#device-mobile-sort');
      if (mobileSort) {
        mobileSort.value = `${sortKey}:${sortDirection}`;
        mobileSort.addEventListener('change', () => { [sortKey, sortDirection] = mobileSort.value.split(':'); updateSortHeaders(); page = 0; refresh(); });
      }
      form.addEventListener('terento-admin-clear-filters', () => {
        search.value = '';
        family.value = 'all';
        map.value = 'yes';
        support.value = 'all';
        status.value = 'all';
        sortKey = 'model';
        sortDirection = 'ascending';
        if (mobileSort) mobileSort.value = 'model:ascending';
        showNew = false;
        publicationReview = false;
        page = 0;
        updateSortHeaders();
        refresh();
      });
      form.addEventListener('submit', (event) => event.preventDefault());
      [search, family, map, support, status].forEach((control) => control.addEventListener(control === search ? 'input' : 'change', reset));
      sortButtons.forEach((button) => button.addEventListener('click', () => {
        const key = button.dataset.deviceSort;
        if (sortKey === key) sortDirection = sortDirection === 'ascending' ? 'descending' : 'ascending';
        else { sortKey = key; sortDirection = 'ascending'; }
        updateSortHeaders();
        if (mobileSort) mobileSort.value = `${sortKey}:${sortDirection}`;
        reset();
      }));
      showNewButton?.addEventListener('click', () => {
        search.value = '';
        family.value = 'all';
        map.value = 'all';
        support.value = 'all';
        status.value = 'all';
        showNew = true;
        page = 0;
        refresh();
      });
      previous.addEventListener('click', () => { page -= 1; refresh(); });
      next.addEventListener('click', () => { page += 1; refresh(); });
      body.addEventListener('click', (event) => {
        const row = event.target.closest('tr[data-device-index]');
        if (!row || event.target.closest('a,button,input,select,textarea')) return;
        window.location.assign(row.dataset.deviceUrl);
      });
      body.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const row = event.target.closest('tr[data-device-index]');
        if (!row || event.target.closest('a,button')) return;
        event.preventDefault();
        window.location.assign(row.dataset.deviceUrl);
      });
      const syncStickyHeader = () => {
        if (tableScroll && stickyHeaderTable) {
          stickyHeaderTable.style.transform = `translateX(${-tableScroll.scrollLeft}px)`;
        }
      };
      tableScroll?.addEventListener('scroll', syncStickyHeader, {passive: true});
      updateSortHeaders();
      refresh();
      syncStickyHeader();
    })();"""
    return script.replace("__TABLE_FILTER_STATE__", _table_filter_state_script()).replace(
        "__TERENTO_LAST_SUCCESS_COMPARATOR__",
        _device_last_success_comparator_script(),
    )


def _campaign_links_script() -> str:
    return r"""(() => {
      const destinations = {
        home: 'https://terento.app/',
        download: 'https://terento.app/download/',
        compatibility: 'https://terento.app/compatibility/'
      };
      const utmKeys = new Set(['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']);
      const presets = {
        'reddit-community': { destination: 'home', source: 'reddit', medium: 'social', campaign: 'early_beta', content: '', term: '' }
      };
      const form = document.querySelector('#campaign-link-form');
      if (!form) return;
      const controls = {
        destination: document.querySelector('#destination'),
        destinationCustom: document.querySelector('#destination-custom'),
        destinationCustomWrap: document.querySelector('#destination-custom-wrap'),
        source: document.querySelector('#source'),
        sourceCustom: document.querySelector('#source-custom'),
        sourceCustomWrap: document.querySelector('#source-custom-wrap'),
        medium: document.querySelector('#medium'),
        mediumCustom: document.querySelector('#medium-custom'),
        mediumCustomWrap: document.querySelector('#medium-custom-wrap'),
        campaign: document.querySelector('#campaign'),
        content: document.querySelector('#content'),
        term: document.querySelector('#term'),
        preset: document.querySelector('#campaign-preset'),
        incomplete: document.querySelector('#incomplete-state'),
        urlRow: document.querySelector('#generated-url-row'),
        output: document.querySelector('#generated-url'),
        copy: document.querySelector('#copy-link'),
        copyStatus: document.querySelector('#copy-status'),
        previewSource: document.querySelector('#preview-source'),
        previewMedium: document.querySelector('#preview-medium'),
        previewCampaign: document.querySelector('#preview-campaign'),
        previewContent: document.querySelector('#preview-content'),
        previewTerm: document.querySelector('#preview-term')
      };
      const normalizeValue = (value) => {
        let text = String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
        text = text.replace(/\s+/g, '_').replace(/[^a-z0-9_-]/g, '').replace(/[-_]{2,}/g, (match) => match[0]);
        return text.replace(/^[-_]+|[-_]+$/g, '');
      };
      const destinationUrl = () => {
        if (controls.destination.value !== 'other') return destinations[controls.destination.value];
        const value = controls.destinationCustom.value.trim();
        if (!value || (value.startsWith('/') && value.startsWith('//'))) return null;
        if (value.startsWith('/')) return `https://terento.app${value}`;
        try {
          const parsed = new URL(value);
          if (parsed.protocol !== 'https:' || parsed.hostname !== 'terento.app' || parsed.username || parsed.password || (parsed.port && parsed.port !== '443')) return null;
          return `https://terento.app${parsed.pathname || '/'}${parsed.search}${parsed.hash}`;
        } catch (_) {
          return null;
        }
      };
      const buildUrl = () => {
        const base = destinationUrl();
        const source = normalizeValue(controls.source.value === 'other' ? controls.sourceCustom.value : controls.source.value);
        const medium = normalizeValue(controls.medium.value === 'other' ? controls.mediumCustom.value : controls.medium.value);
        const campaign = normalizeValue(controls.campaign.value);
        const content = normalizeValue(controls.content.value);
        const term = normalizeValue(controls.term.value);
        if (!base || !source || !medium || !campaign) return null;
        const parsed = new URL(base);
        const existing = [...parsed.searchParams.entries()].filter(([key]) => !utmKeys.has(key.toLowerCase()));
        parsed.search = new URLSearchParams(existing).toString();
        parsed.searchParams.append('utm_source', source);
        parsed.searchParams.append('utm_medium', medium);
        parsed.searchParams.append('utm_campaign', campaign);
        if (content) parsed.searchParams.append('utm_content', content);
        if (term) parsed.searchParams.append('utm_term', term);
        return { url: parsed.toString(), source, medium, campaign, content, term };
      };
      window.TerentoCampaignLinkBuilder = { normalizeValue, buildUrl };
      const setCustomVisibility = (select, wrapper, input) => {
        const visible = select.value === 'other';
        wrapper.hidden = !visible;
        wrapper.setAttribute('aria-hidden', String(!visible));
        input.required = visible;
      };
      const updateCustomVisibility = () => {
        setCustomVisibility(controls.destination, controls.destinationCustomWrap, controls.destinationCustom);
        setCustomVisibility(controls.source, controls.sourceCustomWrap, controls.sourceCustom);
        setCustomVisibility(controls.medium, controls.mediumCustomWrap, controls.mediumCustom);
      };
      const setPreview = (value, control) => { control.textContent = value || '—'; };
      const syncPresetLabel = () => {
        const preset = presets['reddit-community'];
        const matches = ['destination', 'source', 'medium', 'campaign', 'content', 'term']
          .every((key) => controls[key].value === preset[key]);
        controls.preset.value = matches ? 'reddit-community' : '';
      };
      const refresh = () => {
        updateCustomVisibility();
        const result = buildUrl();
        syncPresetLabel();
        controls.urlRow.hidden = !result;
        controls.incomplete.hidden = Boolean(result);
        controls.copy.disabled = !result;
        controls.output.textContent = result ? result.url : '';
        setPreview(result ? result.source : '', controls.previewSource);
        setPreview(result ? result.medium : '', controls.previewMedium);
        setPreview(result ? result.campaign : '', controls.previewCampaign);
        setPreview(result ? result.content : '', controls.previewContent);
        setPreview(result ? result.term : '', controls.previewTerm);
      };
      const applyPreset = () => {
        if (controls.preset.value === 'reddit-community') {
          controls.destination.value = 'home';
          controls.source.value = 'reddit';
          controls.medium.value = 'social';
          controls.campaign.value = 'early_beta';
          controls.content.value = '';
          controls.term.value = '';
        }
        refresh();
      };
      const copyText = async (value) => {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(value);
          return;
        }
        const helper = document.createElement('textarea');
        helper.value = value;
        helper.setAttribute('readonly', '');
        helper.style.position = 'fixed';
        helper.style.opacity = '0';
        document.body.appendChild(helper);
        helper.select();
        document.execCommand('copy');
        helper.remove();
      };
      form.addEventListener('submit', (event) => event.preventDefault());
      form.querySelectorAll('input, select').forEach((control) => control.addEventListener('input', refresh));
      form.querySelectorAll('select').forEach((control) => control.addEventListener('change', refresh));
      controls.preset.addEventListener('change', applyPreset);
      controls.copy.addEventListener('click', async () => {
        const result = buildUrl();
        if (!result) return;
        try {
          await copyText(result.url);
          controls.copyStatus.textContent = 'Copied';
          window.setTimeout(() => { controls.copyStatus.textContent = ''; }, 1400);
        } catch (_) {
          controls.copyStatus.textContent = 'Copy failed — select the URL to copy it.';
        }
      });
      document.querySelectorAll('.info-control').forEach((button) => {
        button.addEventListener('click', () => {
          const target = document.getElementById(button.getAttribute('aria-controls'));
          const open = button.getAttribute('aria-expanded') === 'true';
          document.querySelectorAll('.info-control[aria-expanded="true"]').forEach((other) => {
            other.setAttribute('aria-expanded', 'false');
            const otherTarget = document.getElementById(other.getAttribute('aria-controls'));
            if (otherTarget) otherTarget.hidden = true;
          });
          if (target && !open) {
            button.setAttribute('aria-expanded', 'true');
            target.hidden = false;
          }
        });
      });
      refresh();
    })();"""


def _dashboard_script() -> str:
    return """(() => {
      const form = document.querySelector('#evidence-filters');
      const search = document.querySelector('#evidence-search');
      const status = document.querySelector('#evidence-status');
      const sort = document.querySelector('#evidence-sort');
      const quickFilters = [...document.querySelectorAll('[data-installation-filter]')];
      const body = document.querySelector('#evidence-rows');
      const count = document.querySelector('#results-count');
      const clear = document.querySelector('[data-filter-clear]');
      const table = document.querySelector('#installation-table');
      const empty = document.querySelector('#installation-empty');
      const pagination = document.querySelector('#installation-pagination');
      const pageSize = document.querySelector('#installation-page-size');
      const previousPage = pagination?.querySelector('[data-installation-page="previous"]');
      const nextPage = pagination?.querySelector('[data-installation-page="next"]');
      const pageSummary = pagination?.querySelector('span');
      if (!form || !search || !status || !sort || !body || !count || !quickFilters.length) return;
      const rows = [...body.querySelectorAll('tr')];
      let page = 1;
      const storageKey = 'terento.admin.installations.filters';
      const parameters = new URLSearchParams(window.location.search);
      __TABLE_FILTER_STATE__
      search.value = parameters.has('search') ? parameters.get('search') : (saved.search || '');
      const quickFilterValues = quickFilters.map((button) => button.dataset.installationFilter);
      let selectedQuickFilter = parameters.get('state') || saved.quick || 'all';
      if (!quickFilterValues.includes(selectedQuickFilter)) selectedQuickFilter = 'all';
      restoreSelect(status, 'status', 'all');
      const legacySort = {attempts:'attempts:descending', errors:'errors:descending', model:'model:ascending'};
      const requestedSort = parameters.get('sort') || saved.sort;
      if (legacySort[requestedSort]) saved.sort = legacySort[requestedSort];
      if (legacySort[parameters.get('sort')]) parameters.set('sort', legacySort[parameters.get('sort')]);
      restoreSelect(sort, 'sort', 'latest');
      const sortButtons = [...document.querySelectorAll('[data-installation-sort]')];
      const textCompare = (a, b) => String(a).localeCompare(String(b), undefined, {numeric:true, sensitivity:'base'});
      const statusOrder = __STATUS_ORDER__;
      const sortValue = (row, key) => {
        const raw = row.dataset[key];
        if (raw === undefined || raw === '') return null;
        if (key === 'status') { const rank = statusOrder.indexOf(raw); return rank < 0 ? null : rank; }
        if (['activity', 'lastSuccess'].includes(key)) { const stamp = Date.parse(raw); return Number.isFinite(stamp) ? stamp : null; }
        if (['attempts','successfulCount','failedCount','errors'].includes(key)) { const n = Number(raw); return Number.isFinite(n) ? n : null; }
        return raw;
      };
      const refresh = (resetPage = false) => {
        if (resetPage) page = 1;
        const searchQuery = search.value.trim().toLocaleLowerCase();
        const selectedStatus = status.value;
        const visible = rows.filter((row) => {
          const matchesSearch = !searchQuery || row.dataset.search.toLocaleLowerCase().includes(searchQuery);
          const matchesStatus = selectedStatus === 'all' || row.dataset.status === selectedStatus;
          const matchesQuick = selectedQuickFilter === 'all'
            || (selectedQuickFilter === 'failed' && row.dataset.failed === 'true')
            || (selectedQuickFilter === 'open' && Number(row.dataset.errors || 0) > 0)
            || (selectedQuickFilter === 'successful' && row.dataset.successful === 'true');
          return matchesSearch && matchesStatus && matchesQuick;
        });
        const [key, direction] = sort.value === 'latest' ? ['activity','descending'] : sort.value.split(':');
        visible.sort((a, b) => {
          const av = sortValue(a, key), bv = sortValue(b, key);
          const tie = textCompare(a.dataset.identity, b.dataset.identity);
          if (av === null) return bv === null ? tie : 1;
          if (bv === null) return -1;
          const order = typeof av === 'number' ? av - bv : textCompare(av, bv);
          return (direction === 'descending' ? -order : order) || tie;
        });
        sortButtons.forEach(button => {
          const active = button.dataset.installationSort === key;
          button.closest('th').setAttribute('aria-sort', active ? direction : 'none');
          button.querySelector('span').textContent = active ? (direction === 'ascending' ? '↑' : '↓') : '↕';
        });
        const size = pageSize && Number(pageSize.value) === 50 ? 50 : 25;
        const pages = Math.max(1, Math.ceil(visible.length / size));
        page = Math.min(Math.max(page, 1), pages);
        const startIndex = (page - 1) * size;
        const pageRows = visible.slice(startIndex, startIndex + size);
        rows.forEach((row) => { row.hidden = true; });
        pageRows.forEach((row) => { row.hidden = false; body.appendChild(row); });
        count.textContent = `${visible.length} ${visible.length === 1 ? 'variant' : 'variants'}`;
        empty.hidden = visible.length > 0;
        table.hidden = visible.length === 0;
        if (pagination) {
          pagination.hidden = visible.length <= size;
          const start = visible.length ? startIndex + 1 : 0;
          const end = visible.length ? Math.min(visible.length, startIndex + size) : 0;
          pageSummary.textContent = `Showing ${start}–${end} of ${visible.length} · page ${page} of ${pages}`;
          previousPage.disabled = page <= 1;
          nextPage.disabled = page >= pages;
        }
        quickFilters.forEach((button) => {
          const active = button.dataset.installationFilter === selectedQuickFilter;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const hasActiveFilters = Boolean(search.value.trim()) || status.value !== 'all'
          || selectedQuickFilter !== 'all' || sort.value !== 'latest';
        form.hidden = rows.length <= 1 && !hasActiveFilters;
        clear.hidden = !hasActiveFilters;
        const state = {search: search.value, status: status.value, sort: sort.value, quick: selectedQuickFilter};
        try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* optional */ }
        const stateQuery = new URLSearchParams();
        if (search.value) stateQuery.set('search', search.value);
        if (selectedQuickFilter !== 'all') stateQuery.set('state', selectedQuickFilter);
        if (status.value !== 'all') stateQuery.set('status', status.value);
        if (sort.value !== 'latest') stateQuery.set('sort', sort.value);
        history.replaceState(null, '', stateQuery.size ? `${window.location.pathname}?${stateQuery}` : window.location.pathname);
      };
      sortButtons.forEach(button => button.addEventListener('click', () => {
        const key = button.dataset.installationSort;
        sort.value = key + ':' + (sort.value === key + ':ascending' ? 'descending' : 'ascending');
        refresh(true);
      }));
      form.addEventListener('submit', (event) => event.preventDefault());
      form.addEventListener('terento-admin-clear-filters', () => {
        search.value = '';
        status.value = 'all';
        sort.value = 'latest';
        selectedQuickFilter = 'all';
        refresh(true);
      });
      quickFilters.forEach((button) => button.addEventListener('click', () => {
        selectedQuickFilter = button.dataset.installationFilter || 'all';
        refresh(true);
      }));
      search.addEventListener('input', () => refresh(true));
      [status, sort, pageSize].filter(Boolean).forEach((control) => control.addEventListener('change', () => refresh(true)));
      previousPage?.addEventListener('click', () => { page -= 1; refresh(); });
      nextPage?.addEventListener('click', () => { page += 1; refresh(); });
      refresh();
    })();""".replace("__TABLE_FILTER_STATE__", _table_filter_state_script()).replace("__STATUS_ORDER__", _admin_json([status.value.lower() for status in CANONICAL_STATUS_ORDER]))


def _client_issue_note_sanitizer_script() -> str:
    """Return the browser sanitizer used before note preview and URL creation."""
    return r"""(value) => value
          .slice(0, 500)
          .replace(/[\u0000-\u001f\u007f]+/g, ' ')
          .replace(/[<>]/g, '[redacted markup]')
          .replace(/\b(?:ghp|github_pat)_[A-Za-z0-9_-]+/gi, '[redacted token]')
          .replace(/\bBearer\s+[^\s,;]+/gi, 'Bearer [redacted]')
          .replace(/\b(?:Authorization|Proxy-Authorization|Cookie|Set-Cookie)\s*:\s*[^\s,;]+(?:\s+[^\s,;]+)?/gi, '[redacted header]')
          .replace(/([?&](?:token|access_token|api_key|apikey|secret)=)[^&\s]+/gi, '$1[redacted]')
          .replace(/[?&](?:title|body)=[^&\s]+/gi, '[redacted query value]')
          .replace(/\b(?:token|access[_ -]?token|api[_ -]?key|apikey|secret|password|cookie|authorization)\s*[:=]\s*\S+/gi, '[redacted credential]')
          .replace(/\b[A-Z][A-Z0-9_]{2,}\s*=\s*\S+/g, '[redacted environment value]')
          .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[redacted email]')
          .replace(/\/Users\/[^/\s]+(?:\/[^\s]*)?/gi, '[redacted path]')
          .replace(/(?:\/private|\/var\/folders|\/home|\/Volumes)\/[^\s]+/gi, '[redacted path]')
          .replace(/\b[A-Z]:[\\/]Users[\\/][^\\/\s]+(?:[\\/][^\s]*)?/gi, '[redacted path]')
          .replace(/\b(?:serial(?:[_ -]?number)?|unit[_ -]?id|device[_ -]?id|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S+/gi, '[redacted private identifier]')
          .replace(/\s+/g, ' ')
          .trim()
          .replace(/([\\`*_{}\[\]<>#+!|])/g, '\\$1')"""


def _diagnostics_script() -> str:
    script = r"""(() => {
      const filter = document.querySelector('#diagnostic-state-filter');
      const quickFilters = [...document.querySelectorAll('[data-history-filter]')];
      const body = document.querySelector('#diagnostic-rows');
      const count = document.querySelector('#diagnostic-results-count');
      const pagination = document.querySelector('#diagnostic-history-pagination');
      const pageSize = document.querySelector('#diagnostic-history-page-size');
      if ((!filter && !quickFilters.length) || !body || !count) return;
      const rows = [...body.querySelectorAll('tr[data-diagnostic-state]')];
      const dialogs = [...document.querySelectorAll('.diagnostic-detail-dialog')];
      let page = 1;
      let lastFocused = null;
      const filterValues = filter ? [...filter.options].map((option) => option.value) : [];
      const quickValues = quickFilters.map((button) => button.dataset.historyFilter);
      const validFilters = new Set([...filterValues, ...quickValues]);
      let selectedFilter = new URLSearchParams(window.location.search).get('state') || filter?.value || quickValues[0] || 'all';
      if (!validFilters.has(selectedFilter)) selectedFilter = 'all';
      if (filter && filterValues.includes(selectedFilter)) filter.value = selectedFilter;
      const syncFilterControls = () => {
        if (filter && filterValues.includes(selectedFilter)) filter.value = selectedFilter;
        quickFilters.forEach((button) => {
          const active = button.dataset.historyFilter === selectedFilter;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
      };
      const refresh = () => {
          const selected = selectedFilter;
          const matching = rows.filter((row) => {
            const matches = selected === 'all'
            || (selected === 'succeeded' && row.dataset.diagnosticResult === 'succeeded')
            || (selected === 'open' && row.dataset.reviewOpen === 'true')
            || (selected === 'resolved' && row.dataset.reviewResolved === 'true')
            || (selected === 'resolved-errors' && row.dataset.reviewResolved === 'true' && row.dataset.diagnosticResult === 'failed')
            || (selected === 'identity-pending' && row.dataset.identityPending === 'true')
            || (selected === 'failed' && row.dataset.diagnosticResult === 'failed')
            || (selected === 'with-issue' && row.dataset.hasIssue === 'true');
          return matches;
        });
        const label = matching.length === 1 ? 'record' : 'records';
        count.textContent = matching.length ? `${matching.length} ${label}` : selected === 'failed' ? 'No failed installations for this model' : 'No records match these filters';
        syncFilterControls();
        if (!pagination || !pageSize) {
          rows.forEach((row) => { row.hidden = !matching.includes(row); });
          return;
        }
        const size = Number(pageSize.value) === 50 ? 50 : 25;
        const pages = Math.max(1, Math.ceil(matching.length / size));
        page = Math.min(Math.max(page, 1), pages);
        const startIndex = (page - 1) * size;
        const visible = new Set(matching.slice(startIndex, startIndex + size));
        rows.forEach((row) => { row.hidden = !visible.has(row); });
        const start = matching.length ? startIndex + 1 : 0;
        const end = matching.length ? Math.min(matching.length, startIndex + size) : 0;
        const summary = pagination.querySelector('span');
        if (summary) summary.textContent = matching.length ? `Showing ${start}–${end} of ${matching.length} · page ${page} of ${pages}` : 'Change the filter to view installation history';
        const previous = pagination.querySelector('[data-history-page="previous"]');
        const next = pagination.querySelector('[data-history-page="next"]');
        if (previous) previous.disabled = page <= 1;
        if (next) next.disabled = page >= pages;
      };
      const close = (dialog) => {
        if (!dialog) return;
        if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
        lastFocused?.focus();
      };
      const open = (dialog, trigger) => {
        if (!dialog) return;
        lastFocused = trigger;
        if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
        dialog.querySelector('button, input, select, textarea')?.focus();
      };
      document.querySelector('[data-filter-open-errors]')?.addEventListener('click', () => {
        selectedFilter = 'open';
        refresh();
      });
      quickFilters.forEach((button) => button.addEventListener('click', () => {
        selectedFilter = button.dataset.historyFilter || 'all';
        page = 1;
        refresh();
      }));
      document.querySelector('#diagnostic-filters')?.addEventListener('terento-admin-clear-filters', () => {
        selectedFilter = 'all';
        page = 1;
        const parameters = new URLSearchParams(window.location.search);
        parameters.delete('state');
        const query = parameters.toString();
        history.replaceState(null, '', query ? `${window.location.pathname}?${query}` : window.location.pathname);
        refresh();
      });
      document.querySelectorAll('[data-source-field]').forEach((select) => {
        const renderOriginal = () => {
          const output = select.form?.querySelector('[data-source-original]');
          if (output) output.textContent = select.selectedOptions[0]?.dataset.originalValue || 'Not reported';
        };
        select.addEventListener('change', renderOriginal);
        renderOriginal();
      });
      document.querySelectorAll('form[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
        if (!window.confirm(form.dataset.confirm || 'Continue?')) event.preventDefault();
      }));
      document.querySelectorAll('[data-authorization-form]').forEach((form) => form.addEventListener('submit', (event) => {
        const current = form.dataset.currentSupportStatus;
        const next = form.querySelector('select[name="support_status"]')?.value;
        if (current !== next
          && !window.confirm('Change support metadata? This does not change native map-write authorization, compatibility evidence, or installation history.')) {
          event.preventDefault();
        }
      }));
      document.querySelectorAll('form.admin-async-action').forEach((form) => form.addEventListener('submit', async (event) => {
        if (event.defaultPrevented) return;
        event.preventDefault();
        if (form.dataset.submitting === 'true') return;
        const formData = new FormData(form);
        // FormData(form) omits the clicked submit button. Identity Review
        // uses named Confirm buttons for the normal and manual paths.
        if (event.submitter?.name) formData.append(event.submitter.name, event.submitter.value);
        const payload = new URLSearchParams();
        formData.forEach((value, key) => payload.append(key, String(value)));
        const controls = [...form.querySelectorAll('button,input,select,textarea')];
        const submit = form.querySelector('button[type="submit"]');
        const originalLabel = submit?.textContent || '';
        let status = form.querySelector('.admin-action-status');
        if (!status) {
          status = document.createElement('p');
          status.className = 'admin-action-status';
          status.setAttribute('role', 'status');
          status.setAttribute('aria-live', 'polite');
          form.appendChild(status);
        }
        form.dataset.submitting = 'true';
        controls.forEach((control) => {
          control.dataset.preSubmitDisabled = control.disabled ? 'true' : 'false';
          control.disabled = true;
        });
        if (submit) submit.textContent = 'Saving…';
        status.textContent = 'Saving…';
        try {
          const response = await fetch(form.action, {
            method: 'POST',
            body: payload,
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
            redirect: 'follow',
          });
          if (!response.ok) {
            let payload = {};
            try { payload = await response.json(); } catch (_) {}
            const safeIdentityText = (value, fallback = 'Not reported') => {
              if (value === null || value === undefined || value === '') return fallback;
              if (typeof value === 'boolean') return value ? 'Yes' : 'No';
              return String(value).replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, 200);
            };
            const identityFieldLabels = {
              model: 'Model', caseSizeMm: 'Case size', screenTechnology: 'Display',
              solar: 'Solar', inReach: 'inReach', USB: 'USB mapping',
              XML_PART_NUMBER: 'Product mapping', RETAIL_SKU: 'Retail SKU mapping',
            };
            const identityConflictMessage = (responsePayload) => {
              const conflicts = responsePayload?.details?.conflicts;
              if (!Array.isArray(conflicts) || !conflicts.length) {
                return 'The selected model conflicts with reported information. Confirm manual assignment if this is the intended correction.';
              }
              const lines = conflicts.map((detail, index) => {
                const field = identityFieldLabels[detail?.field] || safeIdentityText(detail?.field, 'Identity field');
                const source = safeIdentityText(detail?.source, 'reported data');
                const reported = safeIdentityText(detail?.reported);
                const selected = safeIdentityText(detail?.selectedModel || detail?.selected, 'selected catalog model');
                const result = detail?.result || {};
                const resultLabel = result.eventId ? `Diagnostic result ${safeIdentityText(result.eventId)}` : `Diagnostic result ${index + 1}`;
                const mappings = Array.isArray(detail?.mappingModels) && detail.mappingModels.length
                  ? ` Approved mapping models for this code: ${detail.mappingModels.map((value) => safeIdentityText(value, 'Unknown model')).join(', ')}.`
                  : '';
                return `${resultLabel}: ${field}: reported ${reported} from ${source}; selected model ${selected}.${mappings}`;
              });
              return `The selected model conflicts with reported information. ${lines.join(' ')} Use manual assignment to confirm it.`;
            };
            const messages = {
              missing_model_selection: 'Choose a specific catalog model before confirming.',
              canonical_device_not_found: 'That catalog model is no longer available. Choose another model.',
              diagnostic_not_found: 'This diagnostic result is no longer available. Reload the review queue.',
              identity_conflict_manual_required: identityConflictMessage(payload),
              invalid_diagnostic_record: 'This diagnostic result identifier is invalid. Reload the review queue.',
            };
            const message = messages[payload.error] || (form.matches('[data-identity-form]')
              ? 'The identity review could not be saved. Your selection is kept; check the current record and retry.'
              : `Save failed (${response.status})`);
            const error = new Error(message);
            error.identityCode = payload.error;
            throw error;
          }
          if (response.redirected) {
            window.location.assign(response.url);
          } else {
            window.location.reload();
          }
        } catch (error) {
          controls.forEach((control) => {
            control.disabled = control.dataset.preSubmitDisabled === 'true';
            delete control.dataset.preSubmitDisabled;
          });
          if (submit) submit.textContent = originalLabel;
          status.textContent = error?.message || 'Could not save. Check the values and try again.';
          if (form.matches('[data-identity-form]') && error?.identityCode === 'identity_conflict_manual_required') {
            const manual = form.querySelector('[data-manual-confirm]');
            if (manual) manual.hidden = false;
          }
          delete form.dataset.submitting;
          submit?.focus();
        }
      }));
      const copyText = async (value, status) => {
        try {
          await navigator.clipboard.writeText(value);
          if (status) status.textContent = 'Copied';
        } catch (_) {
          if (status) status.textContent = 'Copy failed';
        }
      };
      document.querySelectorAll('[data-github-create]').forEach((link) => {
        const container = link.closest('.github-issue-controls, .github-review');
        const note = container?.querySelector('[data-issue-note]');
        const preview = container?.querySelector('[data-issue-preview-body]');
        const status = container?.querySelector('[data-copy-status]');
        const sanitiseNote = __TERENTO_CLIENT_ISSUE_NOTE_SANITIZER__;
        const sync = () => {
          const noteValue = sanitiseNote(note?.value || '');
          const body = link.dataset.issueBody + (noteValue ? `\n\n## Admin note\n\n${noteValue}` : '');
          const candidate = `https://github.com/VooZ2/terento/issues/new?${new URLSearchParams({title: link.dataset.issueTitle, body})}`;
          const limit = Number(link.dataset.urlLimit || 7000);
          const prefilled = candidate.length <= limit;
          link.href = prefilled ? candidate : 'https://github.com/VooZ2/terento/issues/new';
          link.dataset.prefilled = prefilled ? 'true' : 'false';
          link.textContent = prefilled ? 'Prepare GitHub issue' : 'Copy report to continue';
          if (status) status.textContent = prefilled ? '' : 'Report is too large to prefill; copy it instead.';
          if (preview) preview.value = body;
          return body;
        };
        note?.addEventListener('input', sync);
        link.addEventListener('click', (event) => {
          const body = sync();
          if (link.dataset.prefilled === 'false') {
            event.preventDefault();
            copyText(`${link.dataset.issueTitle}\n\n${body}`, status);
          }
        });
        container?.querySelector('[data-copy-issue-report]')?.addEventListener('click', () => {
          copyText(`${link.dataset.issueTitle}\n\n${sync()}`, status);
        });
        sync();
      });
      document.querySelectorAll('[data-copy-diagnostic-id]').forEach((button) => button.addEventListener('click', () => {
        copyText(button.dataset.copyDiagnosticId, button.parentElement?.querySelector('[data-copy-status]'));
      }));
      document.querySelectorAll('[data-copy-technical-report]').forEach((button) => button.addEventListener('click', () => {
        copyText(button.dataset.report, button.parentElement?.querySelector('[data-copy-status]'));
      }));
      ['input', 'change'].forEach((eventName) => filter?.addEventListener(eventName, () => { selectedFilter = filter.value; page = 1; refresh(); }));
      pageSize?.addEventListener('change', () => { page = 1; refresh(); });
      pagination?.querySelector('[data-history-page="previous"]')?.addEventListener('click', () => { page = Math.max(1, page - 1); refresh(); });
      pagination?.querySelector('[data-history-page="next"]')?.addEventListener('click', () => { page += 1; refresh(); });
      document.querySelectorAll('.diagnostic-review').forEach((button) => button.addEventListener('click', () => open(document.getElementById(button.dataset.dialogId), button)));
      document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => close(button.closest('dialog'))));
      dialogs.forEach((dialog) => {
        dialog.addEventListener('click', (event) => { if (event.target === dialog) close(dialog); });
        dialog.addEventListener('cancel', () => window.setTimeout(() => lastFocused?.focus(), 0));
        dialog.addEventListener('keydown', (event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            close(dialog);
            return;
          }
          if (event.key !== 'Tab') return;
          const focusable = [...dialog.querySelectorAll('button,select,input,textarea,a,summary')]
            .filter((element) => !element.disabled && element.offsetParent !== null);
          if (!focusable.length) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        dialog.querySelectorAll('[data-identity-form]').forEach((form) => {
          const wrap = form.querySelector('[data-canonical-device-wrap]');
          const search = form.querySelector('[data-identity-search]');
          const canonical = form.querySelector('input[name="canonical_device_model_id"]');
          const selection = form.querySelector('[data-identity-selection]');
          const results = form.querySelector('[data-identity-results]');
          const edit = form.querySelector('[data-identity-edit]');
          const confirm = form.querySelector('[data-identity-confirm]');
          const choices = results ? [...results.querySelectorAll('[data-identity-device-id]')].map((option) => ({
            id: option.dataset.identityDeviceId,
            label: option.dataset.identityDeviceLabel || option.textContent.trim(),
          })) : [];
          const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
          const clearStaleSelectionState = () => {
            form.querySelector('[data-identity-conflict]')?.setAttribute('hidden', '');
            form.querySelector('[data-manual-confirm]')?.setAttribute('hidden', '');
          };
          const sync = () => {
            const hasSelection = Boolean(canonical?.value);
            if (confirm) confirm.disabled = !hasSelection;
            if (selection) selection.textContent = hasSelection
              ? `Selected model: ${search?.value || canonical.value}`
              : 'Select a specific catalog model.';
            if (search) search.setAttribute('aria-expanded', wrap?.hidden ? 'false' : 'true');
          };
          const render = (query = '') => {
            if (!results) return [];
            const matches = choices.filter(choice => normalize(choice.label).includes(normalize(query.trim())));
            results.replaceChildren(...matches.map(choice => {
              const button = document.createElement('button');
              button.type = 'button';
              button.className = 'identity-picker-option';
              button.setAttribute('role', 'option');
              button.dataset.identityDeviceId = choice.id;
              button.dataset.identityDeviceLabel = choice.label;
              button.textContent = choice.label;
              button.addEventListener('click', () => {
                clearStaleSelectionState();
                if (canonical) canonical.value = choice.id;
                if (search) search.value = choice.label;
                if (results) results.hidden = true;
                if (edit) edit.hidden = false;
                sync();
                search?.focus();
              });
              return button;
            }));
            results.hidden = false;
            if (!matches.length) {
              const empty = document.createElement('p');
              empty.className = 'identity-picker-empty';
              empty.setAttribute('role', 'status');
              empty.textContent = 'No catalog models match this search.';
              results.append(empty);
            }
            return matches;
          };
          edit?.addEventListener('click', () => {
            clearStaleSelectionState();
            if (wrap) wrap.hidden = false;
            if (results) results.hidden = false;
            render('');
            search?.focus();
            sync();
          });
          search?.addEventListener('input', () => {
            clearStaleSelectionState();
            const selected = choices.find(choice => choice.id === canonical?.value);
            if (!selected || normalize(search.value) !== normalize(selected.label)) {
              if (canonical) canonical.value = '';
              form.querySelector('[data-manual-confirm]')?.setAttribute('hidden', '');
            }
            if (wrap) wrap.hidden = false;
            render(search.value);
            sync();
          });
          search?.addEventListener('keydown', (event) => {
            const visible = results ? [...results.querySelectorAll('[data-identity-device-id]')] : [];
            if (event.key === 'ArrowDown' && visible.length) { event.preventDefault(); visible[0].focus(); }
            if (event.key === 'ArrowUp' && visible.length) { event.preventDefault(); visible[visible.length - 1].focus(); }
            if (event.key === 'Escape' && wrap) { wrap.hidden = Boolean(canonical?.value); if (results) results.hidden = true; sync(); }
          });
          sync();
        });
      });
      refresh();
    })();"""
    return script.replace(
        "__TERENTO_CLIENT_ISSUE_NOTE_SANITIZER__",
        _client_issue_note_sanitizer_script(),
    )


def _admin_timezone_script() -> str:
    return r"""(() => {
      const topbar = document.querySelector('.admin-topbar');
      const select = document.querySelector('#admin-timezone');
      const filter = document.querySelector('.device-filter-bar');
      const updateLayoutMetrics = () => {
        if (topbar) document.documentElement.style.setProperty('--admin-topbar-height', `${Math.ceil(topbar.getBoundingClientRect().height)}px`);
        if (filter) document.documentElement.style.setProperty('--device-filter-height', `${Math.ceil(filter.getBoundingClientRect().height)}px`);
      };
      updateLayoutMetrics();
      if (typeof ResizeObserver === 'function') {
        const observer = new ResizeObserver(updateLayoutMetrics);
        if (topbar) observer.observe(topbar);
        if (filter) observer.observe(filter);
      }
      window.addEventListener('resize', updateLayoutMetrics, { passive: true });
      if (!select) return;
      const storageKey = 'terento.admin.timeZone';
      const browserTimeZone = (() => {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch (_) { return 'UTC'; }
      })();
      const isValidTimeZone = (value) => {
        try {
          new Intl.DateTimeFormat('en-GB', { timeZone: value }).format();
          return true;
        } catch (_) {
          return false;
        }
      };
      const commonTimeZones = [
        'Europe/Vilnius', 'Europe/Riga', 'Europe/Warsaw', 'Europe/Berlin',
        'Europe/London', 'America/New_York', 'America/Los_Angeles',
        'America/Toronto', 'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney'
      ];
      const timeZones = ['browser', 'UTC', browserTimeZone, ...commonTimeZones]
        .filter((value, index, values) => values.indexOf(value) === index)
        .filter((value) => value === 'browser' || isValidTimeZone(value));
      const readStoredTimeZone = () => {
        try { return localStorage.getItem(storageKey) || 'browser'; } catch (_) { return 'browser'; }
      };
      const storedTimeZone = readStoredTimeZone();
      const selectedTimeZone = timeZones.includes(storedTimeZone) ? storedTimeZone : 'browser';
      const activeTimeZone = () => select.value === 'browser' ? browserTimeZone : select.value;
      const format = (value) => {
        if (!value) return '—';
        const normalizedValue = typeof value === 'string'
          ? value.trim().replace(/^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)$/, '$1T$2')
          : value;
        const date = new Date(normalizedValue);
        if (Number.isNaN(date.getTime())) return String(value);
        try {
          const parts = Object.fromEntries(
            new Intl.DateTimeFormat('en-CA', {
              year: 'numeric', month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
              timeZone: activeTimeZone()
            }).formatToParts(date)
              .filter((part) => part.type !== 'literal')
              .map((part) => [part.type, part.value])
          );
          return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
        } catch (_) {
          return date.toISOString().slice(0, 16).replace('T', ' ');
        }
      };
      const render = () => {
        const zone = activeTimeZone();
        document.querySelectorAll('[data-admin-timestamp]').forEach((element) => {
          element.textContent = format(element.dataset.adminTimestamp);
          element.title = `${element.textContent} · ${zone}`;
          if (element.closest('.download-timeline')) element.setAttribute('aria-label', element.title);
        });
        document.querySelectorAll('.download-timeline').forEach((timeline) => {
          const times = [...timeline.querySelectorAll('[data-admin-timestamp]')];
          const dates = new Set(times.map(el => format(el.dataset.adminTimestamp).slice(0, 10)));
          if (dates.size === 1) times.forEach(el => { el.setAttribute('aria-label', el.title); el.textContent = format(el.dataset.adminTimestamp).slice(11); });
        });
        select.title = select.value === 'browser' ? `Automatic browser time zone: ${browserTimeZone}` : zone;
        select.setAttribute('aria-label', `Time zone: ${select.value === 'browser' ? `Automatic (${browserTimeZone})` : select.value}`);
      };
      select.replaceChildren(...timeZones.map((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value === 'browser' ? `Auto · ${browserTimeZone}` : value;
        return option;
      }));
      select.value = selectedTimeZone;
      window.TerentoAdminTime = { format, render, timeZone: activeTimeZone };
      select.addEventListener('change', () => {
        try { localStorage.setItem(storageKey, select.value); } catch (_) { /* local preference is optional */ }
        render();
        window.dispatchEvent(new Event('terento-admin-timezone-change'));
      });
      render();
      window.dispatchEvent(new Event('terento-admin-timezone-ready'));
    })();"""


ADMIN_STYLES = ADMIN_BRAND_TOKENS_CSS + """
:root{--admin-control-height:40px;--admin-control-radius:8px;--admin-control-padding-x:10px;--admin-control-font-size:13px;--admin-topbar-height:68px;--max-width:1440px}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{min-width:0}
body{margin:0;min-width:0;background:var(--off-white);color:var(--graphite);font-family:var(--font-ui);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
button,input,select,textarea{font-family:var(--font-ui);font-size:var(--admin-control-font-size);line-height:1.3}
input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]),select,textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-weight:500}
select{padding-right:28px;color-scheme:light}
textarea{min-height:78px;resize:vertical}
input::placeholder,textarea::placeholder{color:var(--admin-placeholder);opacity:1;font-weight:400}
input:disabled,select:disabled,textarea:disabled,button:disabled{cursor:not-allowed;background:var(--surface-muted);border-color:color-mix(in srgb,var(--border) 78%,var(--surface-muted));color:var(--secondary);opacity:1}
button{cursor:pointer}
.admin-action-dialog button:not(.secondary-button),.auth-card button:not(.link-button),.copy-button,.device-support-review button[type="submit"],.model-administration button[type="submit"],.identity-mapping-review button[type="submit"]{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}
.admin-action-dialog button:not(.secondary-button):hover,.auth-card button:not(.link-button):hover,.copy-button:hover,.device-support-review button[type="submit"]:hover,.model-administration button[type="submit"]:hover{background:var(--interactive-hover)}
.admin-topbar{position:sticky;top:0;z-index:30;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);background:var(--off-white);box-shadow:0 1px 0 rgba(34,42,43,.04)}
.admin-topbar-inner{width:min(calc(100% - 48px),var(--max-width));min-height:68px;margin:0 auto;display:grid;grid-template-columns:minmax(300px,1fr) max-content minmax(335px,1fr);align-items:center;gap:16px}
.admin-header-zone{min-width:0}
.admin-header-left{display:flex;align-items:center;justify-self:start;gap:9px}
.admin-brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--graphite);font-family:var(--font-brand);font-size:20px;font-weight:700;letter-spacing:-.02em}
.admin-brand img{width:25px;height:29px;object-fit:contain}
.admin-badge{display:inline-flex;align-items:center;min-height:22px;padding:3px 8px;border:1px solid color-mix(in srgb,var(--sky) 48%,var(--border));border-radius:999px;color:var(--interactive);font-family:var(--font-ui);font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.admin-section-nav{display:flex;align-items:center;justify-content:center;gap:4px;justify-self:center;color:var(--secondary);font-size:13px;font-weight:650}
.admin-section-nav a,.admin-nav a,.link-button{display:inline-flex;align-items:center;min-height:32px;padding:6px 8px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:none;text-decoration:none;color:var(--secondary);font-weight:650;transition:background-color .15s ease,border-color .15s ease,color .15s ease}
.admin-section-nav a:hover,.admin-nav a:hover,.link-button:hover,.admin-section-nav a:active,.admin-nav a:active,.link-button:active{background:color-mix(in srgb,var(--sky) 12%,transparent);color:var(--interactive)}
.admin-section-nav a.active{background:color-mix(in srgb,var(--sky) 13%,var(--off-white));border-color:color-mix(in srgb,var(--sky) 28%,var(--border));color:var(--interactive);box-shadow:none}
.admin-nav{display:flex;align-items:center;justify-self:end;min-width:0;gap:8px;color:var(--secondary);font-size:13px;white-space:nowrap}
.admin-nav form{display:flex;align-items:center;margin:0}
.admin-user{padding:6px 0;color:var(--graphite);font-weight:650;white-space:nowrap}
.timezone-control{display:flex;align-items:center;gap:7px;color:var(--secondary);font-size:11px;font-weight:650;white-space:nowrap}
.timezone-control select{width:clamp(150px,17vw,205px);min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-size:var(--admin-control-font-size)}
.admin-website-link{white-space:nowrap}
.admin-header-left .admin-website-link{min-height:30px;padding:5px 7px;color:var(--secondary);font-size:12px;font-weight:650;text-decoration:none}
.dashboard{width:min(calc(100% - 48px),var(--max-width));margin:0 auto;padding:40px 0 64px}
.heading-row{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;margin-bottom:28px}
.eyebrow,.section-kicker{margin:0 0 8px;color:var(--interactive);font-size:12px;font-weight:750;letter-spacing:.14em;text-transform:uppercase}
h1,h2{margin:0;font-family:var(--font-ui);letter-spacing:-.015em;text-wrap:balance}
h1{font-size:clamp(32px,3.5vw,44px);line-height:1.06}
h2{font-size:22px;line-height:1.15}
.lede{max-width:680px;margin:12px 0 0;color:var(--secondary);font-size:16px}
.evidence-section{margin-top:2px}
.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:14px}
.section-heading .section-kicker{margin-bottom:5px}
.table-help,.results-count{margin:0;color:var(--secondary);font-size:12px}
.filter-bar{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap;margin:0 0 10px;padding:8px;background:var(--surface-muted);border:1px solid var(--border);border-radius:12px}
.filter-bar label{display:flex;align-items:stretch;margin:0}
.filter-bar input,.filter-bar select{height:var(--admin-control-height);min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius);font:600 var(--admin-control-font-size)/1.2 var(--font-ui)}
.filter-bar .filter-search{flex:1 1 310px}
.filter-bar input{width:100%}
.filter-bar select{min-width:150px}
.filter-bar input::placeholder{color:var(--admin-placeholder);font-weight:500}
.filter-bar .results-count{align-self:center;margin:0 4px 0 auto;white-space:nowrap}
.filter-bar .filter-clear{align-self:center;flex:0 0 auto;white-space:nowrap}
.table-wrap{max-height:none;overflow-x:auto;overflow-y:visible;background:var(--surface);border:1px solid var(--border);border-radius:14px}
table{border-collapse:collapse;width:100%;min-width:1060px}
th,td{padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);text-align:left;white-space:nowrap;vertical-align:middle}
thead th{background:var(--surface);box-shadow:0 1px 0 var(--border);color:var(--secondary);font-size:11px;font-weight:750;letter-spacing:.07em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:0}
tbody tr[hidden]{display:none}
td:first-child{font-weight:650}
td.column-number,td.column-date,.numeric{font-variant-numeric:tabular-nums}
.muted-value{color:var(--secondary)}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:700}
.evidence-table-wrap table{min-width:760px}.evidence-model-row{cursor:pointer}.evidence-model-row:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}.evidence-model-row:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:-3px}.evidence-model-row td.column-number{font-variant-numeric:tabular-nums}.error-count{text-decoration:none}.identity-pending-indicator{display:inline-flex;align-items:center;margin-left:6px;padding:3px 6px;border:1px solid var(--border);border-radius:999px;color:var(--secondary);font-size:10px;font-weight:700;white-space:nowrap}.evidence-table-note{margin:10px 3px 0}.back-link{margin:0 0 20px;color:var(--interactive);font-size:13px;font-weight:700}.back-link a{text-underline-offset:3px}.diagnostic-model-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 30px}.diagnostic-model-metrics article{min-height:82px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.diagnostic-model-metrics span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.diagnostic-model-metrics strong{display:block;margin-top:4px;font-family:var(--font-brand);font-size:25px;line-height:1.15}.diagnostic-model-metrics .status-badge{margin-top:5px}.diagnostic-filter-bar{justify-content:flex-start}.diagnostic-list-wrap{max-height:min(70vh,720px)}.diagnostic-list-table{min-width:920px}.diagnostic-list-table th,.diagnostic-list-table td{white-space:normal;overflow-wrap:anywhere}.diagnostic-list-table td:first-child{white-space:nowrap}.diagnostic-list-table tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}.diagnostic-state{display:inline-flex;align-items:center;min-height:24px;padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-state-open{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}.diagnostic-state-resolved{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}.diagnostic-state-identity_pending{background:var(--surface-muted);color:var(--secondary)}.diagnostic-list-table .github-issue,.github-current .github-issue{color:var(--interactive);font-weight:700;white-space:nowrap}.diagnostic-detail-dialog{width:min(1160px,calc(100% - 32px));max-height:min(900px,calc(100% - 32px));padding:0;border:0;border-radius:16px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}.diagnostic-detail-dialog::backdrop{background:rgba(34,42,43,.34)}.diagnostic-detail-inner{max-height:min(900px,calc(100vh - 32px));padding:24px;overflow:auto}.diagnostic-detail-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px;margin:0;border-top:1px solid var(--border)}.diagnostic-detail-summary div{display:grid;grid-template-columns:minmax(95px,.8fr) minmax(0,1.2fr);gap:12px;padding:9px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-detail-summary dt{color:var(--secondary);font-size:12px}.diagnostic-detail-summary dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.diagnostic-actions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:22px}.diagnostic-action-form{min-width:0;padding:14px;background:var(--surface-muted);border-radius:10px}.diagnostic-action-form h4{margin:0 0 10px;font-size:13px}.diagnostic-action-form label{display:block;margin:10px 0;color:var(--graphite);font-size:12px;font-weight:650}.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{display:block;width:100%;margin-top:5px;min-height:36px;padding:7px 9px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite);font-size:12px}.diagnostic-action-form textarea{resize:vertical}.diagnostic-action-form button{margin-top:6px}.identity-summary{font-size:14px;line-height:1.5}.identity-summary h4{font:600 22px/1.3 var(--font-ui);margin:8px 0;text-wrap:balance}.identity-match-list{list-style:none;padding:0;display:grid;gap:6px}.identity-technical-evidence>summary{min-height:40px}.identity-review-form input,.identity-review-form select,.identity-review-form button{min-height:40px}.identity-selection{margin:8px 0;color:var(--secondary);font-size:11px}.identity-selection code{color:var(--graphite);font-family:var(--font-mono);overflow-wrap:anywhere}.github-review{overflow-wrap:anywhere}.github-current{margin:0 0 8px;font-size:13px}.github-actions{margin:0 0 4px}.github-link-form{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px}.github-link-form label{margin:0}.github-link-form button{white-space:nowrap}.github-remove-form{display:inline-block;margin:8px 0 0}
.diagnostic-state-in_progress{background:color-mix(in srgb,var(--sky) 12%,var(--surface));border-color:color-mix(in srgb,var(--sky) 42%,var(--border));color:var(--interactive)}.diagnostic-state-under_review{background:color-mix(in srgb,var(--stone) 18%,var(--surface));border-color:color-mix(in srgb,var(--stone) 55%,var(--border));color:var(--graphite)}
.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius)}
.github-issue-disclosure{margin-top:8px}.github-issue-disclosure>summary{width:max-content;cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750;text-underline-offset:3px}.github-issue-disclosure>summary:hover{text-decoration:underline}.github-issue-controls{margin-top:12px}
.diagnostic-id{font-size:11px!important;color:var(--secondary)!important}.diagnostic-id code{overflow-wrap:anywhere;font-size:10px;color:var(--secondary)}.diagnostic-result{display:inline-flex;align-items:center;min-height:22px;padding:4px 7px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-result-succeeded{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}.diagnostic-result-failed{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}.diagnostic-result-not-started,.diagnostic-result-unknown{background:var(--surface-muted);color:var(--secondary)}.diagnostic-chip{display:inline-flex;align-items:center;min-height:21px;padding:3px 7px;border:1px solid var(--border);border-radius:999px;background:var(--surface-muted);color:var(--secondary);font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-chip.github-issue{color:var(--interactive)}.diagnostic-technical-details{margin:10px 0 0;padding:9px 11px;background:var(--surface-muted);border-radius:8px}.diagnostic-technical-details>summary{cursor:pointer;color:var(--secondary);font-size:12px;font-weight:700}.diagnostic-technical-details dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px;margin:10px 0 0}.diagnostic-technical-details dl div{min-width:0;display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-top:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-technical-details dt{min-width:0;overflow-wrap:anywhere;color:var(--secondary);font-size:11px}.diagnostic-technical-details dd{min-width:0;margin:0;text-align:right;font:500 11px var(--font-mono);overflow-wrap:anywhere}
.status-badge{display:inline-flex;align-items:center;justify-content:center;min-width:74px;min-height:28px;padding:6px 10px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;letter-spacing:.03em;line-height:1;text-transform:uppercase}
.status-tested{background:var(--status-tested-surface);border-color:var(--status-tested-border);color:var(--status-tested-text)}
.status-supported{background:var(--status-supported-surface);border-color:var(--status-supported-border);color:var(--status-supported-text)}
.status-verified{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}
.status-testing{background:var(--status-neutral-surface);border-color:var(--status-neutral-border);color:var(--status-neutral-text)}
.status-enabled{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}
.status-disabled{background:var(--status-neutral-surface);border-color:var(--status-neutral-border);color:var(--status-neutral-text)}
.public-status{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-top:28px;padding:18px 20px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.public-status .section-kicker{margin-bottom:5px}
.public-status-value{display:flex;align-items:center;gap:12px;color:var(--secondary);font-size:13px;font-weight:600}
.status-guide{margin-top:24px;padding:20px 0;border-top:1px solid var(--border)}
.status-guide-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 24px}
.status-guide-row{display:flex;align-items:center;gap:12px;min-height:42px;color:var(--secondary)}
.status-unavailable{background:var(--surface-muted);border-color:var(--border);color:var(--secondary)}
.empty{margin:0 0 20px;padding:16px 18px;background:var(--surface);border:1px solid var(--border);border-radius:12px;color:var(--secondary)}
.auth-card{width:min(480px,calc(100% - 48px));margin:8vh auto;padding:32px;background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:0 16px 44px rgba(34,42,43,.08)}
.auth-card .admin-brand{margin-bottom:28px}
.auth-card h1{font-size:34px}
.auth-card form{margin-top:24px}
.auth-card label{display:block;margin:16px 0;color:var(--graphite);font-weight:650}
.auth-card label small{color:var(--secondary);font-weight:400}
.auth-card input{display:block;width:100%;margin-top:7px}
.auth-card button:not(.link-button){margin-top:8px}
.error,.success{margin:16px 0;padding:11px 13px;border-radius:8px;font-size:13px}
.error{background:var(--error-surface);color:var(--error-text)}
.success{background:var(--success-bg);color:var(--success-text)}
.account{margin-top:48px}
.campaign-card{padding:24px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.campaign-card>.section-heading{margin-bottom:22px}
.campaign-preset-row{display:flex;align-items:center;gap:12px;margin-bottom:20px;padding:8px;background:var(--surface-muted);border:1px solid var(--border);border-radius:12px}
.campaign-preset-row .campaign-label{margin:0;white-space:nowrap}
.campaign-preset-row select{width:min(360px,100%);margin-left:auto}
.campaign-field input,.campaign-field select,.campaign-preset-row select{height:var(--admin-control-height);min-height:var(--admin-control-height);box-sizing:border-box;padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);font-family:var(--font-ui);font-size:var(--admin-control-font-size);font-weight:500;line-height:1.3}
.campaign-field input,.campaign-field select{width:100%}
.campaign-form{margin:0}
.campaign-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 16px}
.campaign-field{min-width:0}
.campaign-field-wide{grid-column:1/-1}
.campaign-label{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:0 0 7px;color:var(--graphite);font-size:13px;font-weight:700}
.required-label,.optional-label{color:var(--secondary);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.required-label{color:var(--danger)}
.info-control{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;min-height:19px;padding:0;border:1px solid var(--border);border-radius:50%;background:var(--surface);color:var(--interactive);font-size:12px;font-weight:750;line-height:1}
.info-control-inline{vertical-align:middle;margin-left:4px;cursor:help}
.info-control:hover{border-color:var(--interactive);background:var(--success-bg)}
.info-popover{position:relative;margin:8px 0 10px;padding:10px 12px;background:var(--surface-muted);border:1px solid var(--border);border-radius:8px;color:var(--secondary);font-size:12px;font-weight:400}
.info-popover strong{display:block;margin-bottom:3px;color:var(--graphite);font-size:12px}
.info-popover p{margin:3px 0}
.info-popover code{font-family:var(--font-mono);font-size:11px;color:var(--graphite)}
.custom-input{margin-top:9px;padding:10px;background:var(--surface-muted);border-radius:8px}
.custom-input label{display:block;margin:0 0 6px;color:var(--secondary);font-size:11px;font-weight:650}
.custom-input input{min-height:38px}
.campaign-result{margin-top:26px;padding-top:21px;border-top:1px solid var(--border)}
.incomplete-state{margin:0;padding:12px 14px;background:var(--surface-muted);border:1px dashed var(--border);border-radius:8px;color:var(--secondary);font-size:13px}
.generated-url-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px}
.generated-url{display:block;min-width:0;padding:12px 13px;overflow:auto;border:1px solid var(--border);border-radius:8px;background:var(--surface-muted);color:var(--graphite);font-family:var(--font-mono);font-size:12px;white-space:nowrap}
.copy-button{min-height:42px;padding:9px 15px;border:0;border-radius:8px;background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}
.copy-button:hover{background:var(--interactive-hover)}
.copy-button:disabled{cursor:not-allowed;opacity:.45}
.copy-status{min-width:54px;color:var(--interactive);font-size:12px;font-weight:700}
.admin-action-status{margin:8px 0 0;color:var(--interactive);font-size:12px;font-weight:700}.admin-async-action [disabled]{cursor:wait;opacity:.68}
.button-link,.provider-action-bar button{display:inline-flex;align-items:center;justify-content:center;min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700;text-decoration:none}.button-link:hover,.provider-action-bar button:hover{background:var(--interactive-hover)}.provider-action-bar button.secondary-button{border:1px solid var(--border);background:var(--surface);color:var(--graphite)}.provider-action-bar button.secondary-button:hover{border-color:var(--interactive);background:var(--surface-muted);color:var(--interactive)}
.provider-table-wrap table{min-width:980px}.provider-name-link{display:flex;flex-direction:column;gap:2px;text-decoration:none}.provider-name-link:hover strong{text-decoration:underline}.provider-name-link small{color:var(--secondary);font:500 11px var(--font-mono)}.provider-table-wrap code{font:500 11px var(--font-mono);overflow-wrap:anywhere}.provider-status{display:inline-flex;align-items:center;justify-content:center;min-height:25px;padding:5px 8px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;text-transform:uppercase;white-space:nowrap}.provider-status-active,.provider-status-healthy,.provider-status-succeeded{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}.provider-status-paused,.provider-status-unknown,.provider-status-running{background:var(--surface-muted);color:var(--secondary)}.provider-status-retired,.provider-status-down,.provider-status-failed{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}.provider-status-degraded{background:var(--status-tested-surface);border-color:var(--status-tested-border);color:var(--status-tested-text)}.provider-broken-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:750}.provider-error{display:block;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--danger);font-size:12px}.provider-table-wrap .numeric{text-align:right;font-variant-numeric:tabular-nums}.provider-action-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 20px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.provider-action-bar .admin-action-status{flex:1 1 180px;margin:0}.provider-activation-note{flex:1 1 100%;margin:2px 0 0;padding:9px 11px;border:1px solid var(--status-tested-border);border-radius:8px;background:var(--status-tested-surface);color:var(--status-tested-text);font-size:12px;line-height:1.45}.provider-heading-status{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.provider-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 24px}.provider-metrics article{min-width:0;min-height:84px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.provider-metrics article>span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.provider-metrics article>strong{display:block;margin-top:6px;font-family:var(--font-brand);font-size:20px;line-height:1.15}.provider-metrics article>strong .admin-timestamp{font-size:15px}.provider-card{margin-top:24px;padding:22px 24px;background:var(--surface);border:1px solid var(--border);border-radius:14px}.provider-card .section-heading{margin-bottom:16px}.provider-card .section-heading h2{font-size:20px}.provider-information-list{margin:0;border-top:1px solid var(--border)}.provider-information-list div{display:grid;grid-template-columns:minmax(150px,.45fr) minmax(0,1.55fr);gap:18px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.provider-information-list dt{color:var(--secondary);font-size:12px}.provider-information-list dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.provider-information-list a,.provider-url-cell a{color:var(--interactive);text-underline-offset:3px}.provider-package-broken{background:color-mix(in srgb,var(--error-surface) 35%,var(--surface))}.provider-package-broken small{display:block;margin-top:3px;color:var(--danger);font-size:10px}.provider-component-list{display:flex;gap:5px;flex-wrap:wrap}.provider-component{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.provider-component .provider-status{min-height:21px;padding:4px 6px;font-size:9px}.provider-history-wrap table{min-width:1240px}.provider-dashboard-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.provider-dashboard-grid .provider-card{min-width:0}.map-statistics-filter-bar label{flex:0 1 auto}.map-statistics-filter-bar input,.map-statistics-filter-bar select{min-width:130px}.map-statistics-filter-bar .results-count{flex:1 1 120px}
.attribution-preview{display:grid;grid-template-columns:minmax(220px,.65fr) minmax(0,1.35fr);gap:24px;margin-top:26px;padding-top:21px;border-top:1px solid var(--border)}
.attribution-preview h2{font-size:20px}
.attribution-preview .table-help{margin-top:8px;max-width:420px}
.preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:0}
.preview-grid div{padding:10px 12px;background:var(--surface-muted);border-radius:8px}
.preview-grid dt{color:var(--secondary);font-size:11px;font-weight:650}
.preview-grid dd{margin:2px 0 0;overflow-wrap:anywhere;font-family:var(--font-mono);font-size:12px}
.admin-summary-strip{display:flex;align-items:center;justify-content:space-between;gap:24px;margin:0 0 28px;padding:13px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;color:var(--secondary);font-size:13px}
.admin-summary-strip p{margin:0;min-width:0}
.admin-summary-metrics strong,.admin-summary-context strong,.device-summary-metrics strong,.device-summary-sync strong{color:var(--graphite);font-weight:750}
.admin-summary-context,.device-summary-sync{text-align:right;white-space:nowrap}
.test-data-page{padding-top:30px}.test-data-card{margin-top:0}.test-data-metrics{grid-template-columns:repeat(3,minmax(0,1fr));margin:0 0 20px}.test-data-release-labels{margin:0;color:var(--secondary);font-size:12px;line-height:18px}.test-data-release-labels code{color:var(--graphite);font:500 11px var(--font-mono);overflow-wrap:anywhere}.test-data-danger-zone{display:grid;grid-template-columns:minmax(0,1fr) minmax(320px,.95fr);align-items:start;gap:24px;margin-top:22px;padding-top:20px;border-top:1px solid var(--border)}.test-data-danger-zone h3{margin:0;font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line)}.test-data-danger-zone .section-kicker{margin-bottom:5px;color:var(--danger)}.test-data-danger-zone .table-help{max-width:460px;margin:6px 0 0}.admin-danger-form{display:grid;gap:10px;padding:14px;background:var(--error-surface);border:1px solid var(--status-error-border);border-radius:12px}.admin-danger-form label{display:grid;gap:6px;color:var(--graphite);font-size:12px;font-weight:650}.admin-danger-form code{font:500 11px var(--font-mono)}.admin-danger-form input{width:100%;min-height:var(--admin-control-height);box-sizing:border-box;padding:8px var(--admin-control-padding-x);border:1px solid var(--status-error-border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font:500 var(--admin-control-font-size)/1.2 var(--font-mono)}.admin-danger-form input:focus{border-color:var(--danger);outline:3px solid color-mix(in srgb,var(--danger) 18%,transparent);outline-offset:1px}.danger-button{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--danger);color:var(--interactive-primary-text);font:600 var(--admin-type-button-size)/var(--admin-type-button-line) var(--font-ui)}.danger-button:hover{background:color-mix(in srgb,var(--danger) 86%,var(--graphite))}
@media(max-width:760px){.test-data-danger-zone{grid-template-columns:1fr;gap:16px}}
.evidence-table-wrap table{table-layout:fixed}.evidence-table-wrap .evidence-column-model{width:24%}.evidence-table-wrap .evidence-column-variant{width:14%}.evidence-table-wrap .evidence-column-status{width:12%}.evidence-table-wrap .evidence-column-attempts{width:7%}.evidence-table-wrap .evidence-column-successful{width:9%}.evidence-table-wrap .evidence-column-failed{width:7%}.evidence-table-wrap .evidence-column-open-errors{width:11%}.evidence-table-wrap .evidence-column-last-success{width:16%}
.device-filter-bar{position:sticky;top:var(--admin-topbar-height);z-index:22;align-items:stretch;margin-bottom:0;background:var(--surface);border-radius:12px 12px 0 0;box-shadow:0 2px 0 rgba(34,42,43,.07)}
.device-table-wrap{overflow:visible;border-top:0;border-radius:0 0 14px 14px}
.device-sticky-header{display:none}
.device-table-wrap table,.device-sticky-header table{min-width:0;table-layout:fixed}
.device-column-model{width:20%}.device-column-variant{width:18%}.device-column-maps{width:9%}.device-column-authorization{width:14%}.device-column-status{width:11%}.device-column-attempts{width:9%}.device-column-successful{width:8%}.device-column-last-success{width:11%}
.device-table-wrap thead{position:static}
.device-table-wrap thead th{position:sticky;top:calc(var(--admin-topbar-height) + var(--device-filter-height, 54px));z-index:21}
.device-table-wrap th,.device-table-wrap td{white-space:normal;overflow-wrap:anywhere}
.device-sort-button{display:inline-flex;align-items:center;gap:5px;width:auto;min-height:0;margin:0;padding:0;border:0;background:transparent;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;white-space:nowrap;cursor:pointer}
.device-sort-button:hover{color:var(--graphite)}.device-sort-button:focus-visible{outline:2px solid var(--interactive);outline-offset:1px}
.device-sort-button span{min-width:10px;color:var(--secondary);font-size:12px;opacity:.2;transition:color .15s ease,opacity .15s ease}.device-sort-button:hover span,.device-sort-button:focus-visible span{opacity:.6}.device-table-wrap th[aria-sort="ascending"] .device-sort-button,.device-table-wrap th[aria-sort="descending"] .device-sort-button{color:var(--graphite);font-weight:800}.device-table-wrap th[aria-sort="ascending"] .device-sort-button span,.device-table-wrap th[aria-sort="descending"] .device-sort-button span{color:var(--interactive);opacity:1}
.device-table-wrap td:nth-child(3),.device-table-wrap td:nth-child(4),.device-table-wrap td:nth-child(5),.device-table-wrap td:nth-child(6),.device-table-wrap td:nth-child(7),.device-table-wrap td:nth-child(8){white-space:nowrap}
.device-table-wrap tbody td{padding-top:6px;padding-bottom:6px}
.device-table-wrap tbody tr{cursor:pointer}
.device-table-wrap tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}
.device-table-wrap tbody tr:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:-3px}
.device-model-button{display:flex;align-items:center;gap:10px;width:100%;padding:0;border:0;background:none;color:inherit;text-align:left;text-decoration:none}
.device-model-button strong{display:block;font-weight:700}
.device-model-copy{display:flex;align-items:center;gap:8px;min-width:0}
.historical-catalog-indicator{position:relative;display:inline-flex;align-items:center;justify-content:center;flex:0 0 18px;width:18px;height:18px;color:var(--secondary);font-weight:400}
.historical-catalog-indicator .catalog-archive-icon{width:16px;height:16px}
.historical-catalog-tooltip{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.historical-catalog-indicator:hover .historical-catalog-tooltip,.device-model-button:focus-visible .historical-catalog-tooltip{z-index:5;top:50%;left:calc(100% + 6px);transform:translateY(-50%);width:max-content;height:auto;max-width:220px;padding:6px 8px;margin:0;overflow:visible;clip-path:none;white-space:normal;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--secondary);font-size:12px;line-height:18px}
.device-model-copy strong{min-width:0;overflow-wrap:anywhere}
.device-thumb{display:block;width:38px;height:38px;flex:0 0 38px;object-fit:contain;border-radius:8px;background:var(--surface-muted)}
.device-detail-image{display:block;width:120px;height:120px;object-fit:contain;border-radius:16px;background:var(--surface-muted);margin:0 0 16px}
.device-thumb-placeholder{position:relative;border:1px solid var(--border)}
.device-thumb-placeholder:before{content:"";position:absolute;left:10px;top:8px;width:16px;height:21px;border:2px solid var(--sky);border-radius:5px}
.device-thumb-placeholder:after{content:"";position:absolute;left:15px;top:13px;width:6px;height:2px;border-radius:2px;background:var(--sky);box-shadow:0 8px 0 var(--sky)}
.new-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--lichen) 65%,var(--border));border-radius:999px;background:var(--new-badge-surface);color:var(--new-badge-text);font-size:10px;font-weight:750;letter-spacing:.06em;white-space:nowrap;text-transform:uppercase}
.summary-filter-link{margin:0;padding:0;border:0;background:none;color:var(--interactive);font:inherit;font-weight:750;text-decoration:underline;text-underline-offset:3px}
.admin-state{display:inline-flex;align-items:center;min-height:26px;padding:5px 9px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;line-height:1;white-space:nowrap}
.admin-state-map-yes,.admin-state-authorization-approved,.admin-state-publication-published{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}
.admin-state-map-no,.admin-state-authorization-blocked{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}
.admin-state-map-unknown,.admin-state-authorization-pending,.admin-state-publication-pending,.admin-state-publication-unavailable{background:var(--surface-muted);border-color:var(--border);color:var(--secondary)}
.numeric{font-variant-numeric:tabular-nums}
.device-pagination{display:flex;align-items:center;justify-content:center;gap:16px;margin:14px 0 0;color:var(--secondary);font-size:13px}
.device-pagination button,.dialog-close{min-height:34px;padding:7px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--interactive);font-weight:700}
.device-pagination button:hover,.dialog-close:hover{border-color:var(--interactive);background:var(--success-bg)}
.device-pagination button:disabled{cursor:not-allowed;opacity:.45}
.device-dialog{width:min(780px,calc(100% - 32px));max-height:calc(100% - 32px);padding:0;border:0;border-radius:16px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}
.device-dialog::backdrop{background:rgba(34,42,43,.34)}
.device-dialog-inner{padding:20px}
.device-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:16px}
.device-dialog-header h2{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:25px}
.modal-subtitle{color:var(--secondary);font:500 14px var(--font-ui);letter-spacing:0}
.dialog-close{width:36px;min-height:36px;padding:0;font-size:20px;line-height:1}
.device-modal-hero{display:flex;align-items:center;margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid var(--border)}
.device-modal-hero .device-detail-image{margin:0;width:72px;height:72px;border-radius:12px}
.device-catalog-id{color:var(--secondary);font-size:11px;font-weight:500}.detail-status-value{color:var(--secondary);font-weight:650}
.device-image-source{margin:0 0 3px;color:var(--graphite);font-size:13px;font-weight:700}
.identity-checks-table{width:100%;min-width:0;table-layout:fixed}
.identity-checks-table th,.identity-checks-table td{white-space:normal!important;overflow-wrap:anywhere;text-align:left;vertical-align:top}
.identity-checks-table th:nth-child(1){width:24%}.identity-checks-table th:nth-child(2){width:20%}.identity-checks-table th:nth-child(3){width:56%}
.identity-checks-table caption{text-align:left;padding:12px;font-weight:650}
@media(max-width:600px){.identity-checks-table{min-width:480px}}
.device-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
.device-detail-grid section{min-width:0;padding-top:2px}
.detail-kicker{margin:0 0 8px;color:var(--interactive);font-size:11px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}
.device-detail-grid dl{margin:0;border-top:1px solid var(--border)}
.device-detail-grid dl div{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr);gap:12px;padding:8px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 70%,transparent)}
.device-detail-grid section:last-child dl div{grid-template-columns:minmax(84px,.7fr) minmax(120px,1.3fr)}
.device-detail-grid dt{color:var(--secondary);font-size:12px}
.device-detail-grid dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}
.device-dialog .admin-timestamp{white-space:nowrap}
.device-catalog-details{margin-top:18px;padding-top:14px;border-top:1px solid var(--border);color:var(--secondary)}
.device-catalog-details summary{cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750;list-style-position:inside}
.device-catalog-details dl{max-width:720px;margin:12px 0 0;border-top:1px solid var(--border)}
.device-catalog-details dl div{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr);gap:12px;padding:7px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 70%,transparent)}
.device-catalog-details dt{font-size:12px}
.device-catalog-details dd{margin:0;overflow-wrap:anywhere;font-size:12px;font-weight:600;text-align:right}
.technical-value{font-family:var(--font-mono);font-size:11px!important}
.device-product-link{margin:14px 0 0;padding-top:12px;border-top:1px solid var(--border);font-size:13px;font-weight:700}
.device-product-link a{color:var(--interactive);text-underline-offset:3px}
.device-support-review,.device-public-review{margin-top:18px;padding-top:14px;border-top:1px solid var(--border)}
.device-support-review form,.device-public-review form{display:grid;grid-template-columns:minmax(150px,.75fr) minmax(0,1.25fr);align-items:end;gap:10px 12px;margin-top:10px}
.authorization-current{display:flex;align-items:center;gap:10px;margin:0;padding:8px 10px;background:var(--surface-muted);border-radius:8px;color:var(--secondary);font-size:12px}
.authorization-current-value{margin-right:auto}
.device-support-review label,.device-public-review label{display:block;color:var(--secondary);font-size:12px;font-weight:650}
.device-support-review select,.device-support-review input,.device-support-review textarea,.device-public-review input,.device-public-review textarea,.admin-action-dialog select,.admin-action-dialog input,.admin-action-dialog textarea{display:block;width:100%;margin-top:5px}
.device-support-review textarea,.device-public-review textarea{min-height:64px}
.device-support-review .dialog-actions,.device-public-review .dialog-actions{grid-column:1/-1;margin-top:0}
.review-help{margin:8px 0 0;color:var(--secondary);font-size:12px;line-height:1.45}
.model-page-header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:20px;margin:0 0 24px}.model-page-image{width:96px;height:96px;object-fit:contain;border-radius:14px;background:var(--surface)}.model-page-heading h1 span{color:var(--secondary);font-size:.55em;font-weight:500;letter-spacing:-.01em}.model-public-link{align-self:start;text-decoration:none}.model-statistics{grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:20px}.model-review-alert{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 26px;padding:12px 14px;border:1px solid color-mix(in srgb,var(--stone) 48%,var(--border));border-radius:10px;background:color-mix(in srgb,var(--stone) 9%,var(--surface));font-size:13px}.model-review-alert a{color:var(--interactive);font-weight:750;white-space:nowrap}.model-page-section{scroll-margin-top:calc(var(--admin-topbar-height) + 18px);margin-top:34px}.model-history-table{min-width:980px}.model-history-table th:nth-child(1){width:15%}.model-history-table th:nth-child(2){width:16%}.model-history-table th:nth-child(3){width:11%}.model-history-table th:nth-child(4){width:23%}.model-history-table th:nth-child(5){width:12%}.model-history-table th:nth-child(6){width:15%}.model-history-table th:nth-child(7){width:8%}.history-map small,.history-error small{display:block;margin-top:3px;color:var(--secondary);font-size:10px}.administration-grid article{padding:18px;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.administration-grid h3{margin:0 0 12px;font:700 17px var(--font-brand)}.administration-grid p{color:var(--secondary);font-size:13px}.administration-grid form{display:grid;gap:10px}.administration-grid label{color:var(--secondary);font-size:12px;font-weight:650}.administration-grid label select,.administration-grid label textarea{display:block;width:100%;margin-top:5px}.model-information-list{margin:0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.model-information-list div{display:grid;grid-template-columns:minmax(170px,.7fr) minmax(0,1.3fr);gap:18px;padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.model-information-list div:last-child{border-bottom:0}.model-information-list dt{color:var(--secondary);font-size:12px}.model-information-list dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.model-technical-details{margin-top:18px;padding:0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.model-technical-details>summary{cursor:pointer;color:var(--interactive);font-weight:750}.model-technical-details .model-information-list{margin-top:12px}.github-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.github-issue-preview{margin:10px 0}.github-issue-preview>summary{cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750}.github-issue-preview input,.github-issue-preview textarea{font-family:var(--font-mono)!important}.technical-copy-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}.diagnostic-technical-empty{margin:10px 0;color:var(--secondary);font-size:12px}
.secondary-button{min-height:32px;padding:6px 10px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--interactive);font-size:12px;font-weight:700}
.secondary-button:hover{border-color:var(--interactive);background:var(--success-bg)}
.admin-action-dialog{width:min(520px,calc(100% - 32px));padding:22px;border:0;border-radius:14px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}
.admin-action-dialog::backdrop{background:rgba(34,42,43,.34)}
.admin-action-dialog form>label{display:block;margin:13px 0;color:var(--graphite);font-size:13px;font-weight:650}
.admin-action-dialog textarea{resize:vertical}
.dialog-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.page-meta{margin:0;color:var(--secondary);font-size:12px;white-space:nowrap}.installation-heading{align-items:flex-end}
.admin-kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 12px}.admin-kpi-grid article{min-width:0;min-height:84px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.admin-kpi-grid article>span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.admin-kpi-grid article>strong{display:block;margin-top:6px;color:var(--graphite);font-family:var(--font-brand);font-size:25px;line-height:1.15;font-variant-numeric:tabular-nums}.historical-failure-note{margin:0 0 24px;color:var(--secondary);font-size:12px}.historical-failure-note .info-control{margin-left:3px}
.map-statistics-empty{margin:0 0 18px;padding:28px 24px;border:1px dashed var(--border);border-radius:14px;background:var(--surface);text-align:center}.map-statistics-empty h2{font-size:20px}.map-statistics-empty p{margin:8px 0 0;color:var(--secondary);font-size:13px}.map-events-card{margin-top:24px}
.admin-disclosure{margin:0}.admin-disclosure>summary{cursor:pointer;color:var(--interactive);font-size:13px;font-weight:750;list-style-position:inside;text-underline-offset:3px}.admin-disclosure>summary:hover{text-decoration:underline}.admin-disclosure>summary:focus-visible{outline:3px solid var(--admin-focus-ring);outline-offset:3px}.disclosure-body{margin-top:14px}.filter-disclosure{align-self:stretch;min-width:130px;position:relative}.filter-disclosure>summary{display:flex;align-items:center;justify-content:center;height:var(--admin-control-height);padding:8px 10px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-size:var(--admin-control-font-size);font-weight:650;list-style:none;text-decoration:none}.filter-disclosure>summary::-webkit-details-marker{display:none}.filter-disclosure .disclosure-body{display:flex;gap:8px;flex-wrap:wrap;position:absolute;z-index:5;margin-top:7px;padding:8px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.14)}.filter-disclosure .disclosure-body label{display:flex}.filter-disclosure .disclosure-body input,.filter-disclosure .disclosure-body select{min-width:140px}.inline-filter-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px}.inline-filter-row label{display:flex;flex:1 1 220px}.inline-filter-row select{flex:0 1 170px}.provider-pagination{display:flex;align-items:center;justify-content:center;gap:14px;min-height:34px;margin-top:12px;color:var(--secondary);font-size:12px;text-align:center}.provider-pagination button{min-height:34px;padding:7px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--interactive);font:700 12px var(--font-ui)}.provider-pagination button:hover:not(:disabled){border-color:var(--interactive);background:var(--success-bg)}.provider-pagination button:disabled{cursor:not-allowed;opacity:.45}.provider-latest-summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px;border-radius:10px;background:var(--surface-muted);color:var(--secondary);font-size:12px}.provider-latest-summary>div{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.provider-action-overflow{position:relative}.provider-action-overflow>summary{display:inline-flex;align-items:center;justify-content:center;min-height:var(--admin-control-height);padding:8px 12px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);cursor:pointer;font-size:13px;font-weight:700;list-style:none}.provider-action-overflow>summary::-webkit-details-marker{display:none}.provider-action-overflow>summary:hover{border-color:var(--interactive);color:var(--interactive)}.provider-action-overflow>div{position:absolute;z-index:4;right:0;top:calc(100% + 7px);min-width:180px;padding:7px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.14)}.provider-action-overflow button{width:100%}.provider-package-name{display:block;font-weight:700}.provider-package-id{display:block;margin-top:2px;color:var(--secondary)!important;font-size:10px!important}.provider-package-broken td:last-child{color:var(--danger)}.provider-issue-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid var(--border);border-radius:999px;color:var(--graphite);font-weight:750}.provider-issue-count.is-positive{color:var(--danger);border-color:color-mix(in srgb,var(--danger) 35%,var(--border))}.audit-technical-details{margin-top:5px}.audit-technical-details summary{cursor:pointer;color:var(--interactive);font-size:11px;font-weight:700}.audit-technical-details code{display:block;margin-top:5px;max-width:300px;overflow:auto;white-space:pre-wrap;font:500 10px var(--font-mono);color:var(--secondary)}.provider-information-list dd{text-align:left}.provider-section .provider-table-wrap table{min-width:820px}.provider-detail .provider-table-wrap table{min-width:760px}.provider-detail .provider-history-wrap table{min-width:1240px}
@media(max-width:1100px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.admin-kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.provider-detail .provider-history-wrap{overflow-x:auto}}
@media(max-width:700px){.admin-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.installation-heading{align-items:flex-start}.page-meta{white-space:normal}.provider-latest-summary{align-items:flex-start;flex-direction:column;gap:6px}.filter-disclosure .disclosure-body{position:static;margin-top:8px;box-shadow:none}.map-statistics-filter-bar .filter-disclosure{width:100%}.map-statistics-filter-bar .filter-disclosure>summary{justify-content:flex-start}}
@media(max-width:480px){.admin-kpi-grid{grid-template-columns:1fr}.admin-kpi-grid article{min-height:70px;padding:12px}.inline-filter-row{align-items:stretch;flex-direction:column}.inline-filter-row label,.inline-filter-row select{width:100%;flex-basis:auto}.provider-pagination{gap:8px;font-size:11px}.provider-pagination span{max-width:130px}.provider-action-overflow>div{position:static;margin-top:7px}.provider-action-overflow>summary{width:100%}}
@media(max-width:800px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.diagnostic-model-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.filter-bar .results-count{width:100%;margin:2px 4px 0}.public-status{align-items:flex-start;flex-direction:column}.public-status-value{width:100%;justify-content:space-between;flex-wrap:wrap}.status-guide-grid{grid-template-columns:1fr}.campaign-fields{grid-template-columns:1fr}.campaign-field-wide{grid-column:auto}.attribution-preview{grid-template-columns:1fr}.sync-summary{white-space:normal!important}.device-detail-grid{grid-template-columns:1fr}.device-support-review form{grid-template-columns:1fr}.diagnostic-detail-summary{grid-template-columns:1fr}.diagnostic-actions-grid{grid-template-columns:1fr}.github-review{min-width:0}}
@media(max-width:980px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-header-left,.admin-section-nav,.admin-nav{width:100%}.admin-section-nav{order:0;overflow:auto;justify-content:flex-start}.admin-section-nav a{white-space:nowrap}.admin-nav{justify-content:space-between;gap:10px;flex-wrap:wrap}.timezone-control{width:100%;justify-content:space-between}.timezone-control select{width:auto;flex:1}.dashboard{padding-top:28px}.diagnostic-model-metrics{gap:8px}.diagnostic-model-metrics article{padding:12px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}.campaign-card{padding:16px}.campaign-preset-row{align-items:stretch;flex-direction:column;gap:8px}.campaign-preset-row .campaign-label,.campaign-preset-row select{flex:none}.campaign-preset-row select{width:100%;height:var(--admin-control-height);margin-left:0}.generated-url-row{grid-template-columns:1fr}.copy-button{width:100%}.copy-status{min-height:18px}.device-dialog-inner,.diagnostic-detail-inner{padding:18px}.device-detail-grid dl div,.device-detail-secondary dl div{grid-template-columns:1fr;gap:2px}.device-detail-grid dd,.device-detail-secondary dd{text-align:left}.diagnostic-technical-details dl{grid-template-columns:1fr}.github-link-form{grid-template-columns:1fr}.github-link-form button{width:100%}}
@media(max-width:560px){.admin-section-nav{overflow:visible;flex-wrap:wrap}}
@media(max-width:800px){.admin-summary-strip{align-items:flex-start;flex-direction:column;gap:6px}.admin-summary-context,.device-summary-sync{text-align:left;white-space:normal}.device-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.device-detail-grid{grid-template-columns:1fr}.device-catalog-details dl div{grid-template-columns:1fr;gap:2px}.device-catalog-details dd{text-align:left}.device-detail-grid dd{text-align:left}.device-filter-bar .results-count{margin-left:0}.device-dialog-inner{padding:18px}}
@media(max-width:1100px){.device-sticky-header{display:block;position:sticky;top:calc(var(--admin-topbar-height) + var(--device-filter-height, 54px));z-index:21;overflow:hidden;border:1px solid var(--border);border-bottom:0;background:var(--surface)}.device-sticky-header-scroll{overflow:hidden}.device-sticky-header table,.device-table-wrap table{min-width:1050px}.device-sticky-header th{position:static}.device-table-wrap{overflow-x:auto;overflow-y:hidden}.device-table-wrap thead{display:none}.model-statistics{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:800px){.model-page-header{grid-template-columns:auto minmax(0,1fr)}.model-public-link{grid-column:1/-1;width:max-content}.model-statistics{grid-template-columns:repeat(2,minmax(0,1fr))}.model-review-alert{align-items:flex-start;flex-direction:column}.model-information-list div{grid-template-columns:1fr;gap:3px}.model-information-list dd{text-align:left}}
@media(max-width:1100px){.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.provider-dashboard-grid{grid-template-columns:1fr}}
@media(max-width:900px){.map-statistics-coverage-layout{grid-template-columns:1fr}.map-statistics-world-map{min-height:0}.map-statistics-world-map-card .section-heading .table-help{text-align:start}}
@media(max-width:560px){.provider-card{padding:18px 16px}.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.provider-metrics article{padding:12px}.provider-information-list div{grid-template-columns:1fr;gap:3px}.provider-information-list dd{text-align:left}.provider-action-bar{align-items:stretch;flex-direction:column}.provider-action-bar button,.button-link{width:100%}.provider-action-bar .admin-action-status{flex-basis:auto}.map-statistics-filter-bar label,.map-statistics-filter-bar input,.map-statistics-filter-bar select{width:100%;min-width:0}.map-statistics-filter-bar .results-count{width:100%;margin-left:4px}}
@media(max-height:760px){.device-dialog-inner{max-height:calc(100vh - 32px);overflow:auto}.device-dialog-header{position:sticky;top:-1px;z-index:2;padding-bottom:10px;background:var(--surface)}}
.overview-page{padding-top:30px}.overview-heading{align-items:flex-end;margin-bottom:20px}.overview-period-form{margin:0}.overview-period-form select{min-width:154px}.overview-panel{margin-top:12px;padding:18px 20px;border:1px solid var(--border);border-radius:14px;background:var(--surface)}.overview-panel .section-heading{margin-bottom:10px}.overview-empty-state{margin:0;padding:12px 0;color:var(--secondary);font-weight:650}.overview-attention-list,.overview-activity-list{list-style:none;margin:0;padding:0}.overview-attention-item{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:10px;padding:10px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-attention-item:first-child{border-top:0;padding-top:3px}.overview-attention-dot{font-size:13px;line-height:1.5;color:var(--danger)}.overview-attention-provider .overview-attention-dot{color:var(--warning,var(--stone))}.overview-attention-item div{display:grid;gap:2px;min-width:0}.overview-attention-item a{color:var(--graphite);text-decoration:none}.overview-attention-item a:hover{text-decoration:underline;text-underline-offset:3px}.overview-attention-item strong{font-size:14px}.overview-attention-item span{color:var(--secondary);font-size:12px;overflow:hidden;text-overflow:ellipsis}.overview-attention-item small{color:var(--secondary);font-size:11px}.overview-detail-link,.section-link{color:var(--interactive);font-size:12px;font-weight:700;white-space:nowrap;text-decoration:none}.overview-detail-link:hover,.section-link:hover{text-decoration:underline;text-underline-offset:3px}.overview-activity-item{display:grid;grid-template-columns:126px minmax(0,1fr) max-content;align-items:center;gap:10px;padding:8px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-activity-item:first-child{border-top:0;padding-top:3px}.overview-activity-item>time{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-activity-item .map-activity-copy{display:grid;min-width:0}.overview-activity-label{font-size:13px;font-weight:750}.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){overflow:hidden;text-overflow:ellipsis;color:var(--secondary);font-size:12px;white-space:nowrap}.overview-activity-provider{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-activity-failed .overview-activity-label,.overview-activity-not-started .overview-activity-label{color:var(--danger)}.overview-reason-list{display:grid;gap:11px}.overview-reason-list li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;align-items:center}.overview-reason-list li>span:first-child{font-size:13px}.overview-reason-list strong{font-variant-numeric:tabular-nums}.overview-bar{grid-column:1/-1;height:7px;overflow:hidden;border-radius:999px;background:var(--surface-muted)}.overview-bar i{display:block;height:100%;border-radius:inherit;background:var(--interactive)}.overview-chart-note,.overview-semantic-note{margin:12px 0 0;color:var(--secondary);font-size:11px}.overview-provider-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.overview-provider-summary strong{margin-right:3px;font-variant-numeric:tabular-nums}.overview-provider-summary a{display:inline-flex;gap:5px;align-items:center;padding:5px 8px;border:1px solid var(--border);border-radius:999px;color:var(--graphite);font-size:12px;text-decoration:none}.overview-provider-summary a:hover{border-color:var(--sky);color:var(--interactive)}.overview-provider-summary a span{color:var(--secondary);font-size:11px}.overview-semantic-note{max-width:780px;margin-top:14px}.admin-section-nav{flex-wrap:wrap}
.quick-filter-group{display:flex;align-items:center;gap:4px;flex:0 0 auto;flex-wrap:wrap}.quick-filter{min-height:var(--admin-control-height);padding:8px 10px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:transparent;color:var(--secondary);font-weight:650}.quick-filter:hover{border-color:var(--border);color:var(--interactive)}.quick-filter.active{border-color:color-mix(in srgb,var(--sky) 45%,var(--border));background:var(--surface);color:var(--interactive);box-shadow:0 1px 1px rgba(34,42,43,.05)}
.map-statistics-coverage-layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(280px,1fr);gap:16px;margin-top:16px}.map-statistics-coverage-layout>.provider-card{min-width:0;margin-top:0}.map-statistics-popularity{grid-template-columns:minmax(0,1fr)}.map-statistics-popularity .provider-card{margin-top:0}.table-secondary{display:block;margin-top:3px;color:var(--secondary);font-size:11px;font-weight:500}
.map-statistics-world-map{position:relative;min-height:300px;padding:8px 0 0;overflow:hidden;border:1px solid var(--border);border-radius:10px;background:var(--surface-muted)}.world-map-svg{width:100%;padding:0 8px}.world-map-svg svg{display:block;width:100%;height:auto;overflow:visible}.world-map-country{stroke:color-mix(in srgb,var(--interactive) 42%,var(--border));stroke-width:.65;vector-effect:non-scaling-stroke;cursor:help;outline:none;transition:filter .12s ease,stroke-width .12s ease}.world-map-country:hover,.world-map-country:focus{filter:brightness(.86);stroke:var(--interactive);stroke-width:1.5}.world-map-tooltip{position:absolute;z-index:2;top:12px;right:12px;min-width:170px;max-width:240px;padding:10px 12px;border:1px solid color-mix(in srgb,var(--interactive) 28%,var(--border));border-radius:9px;background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 8px 24px rgba(34,42,43,.14);font-size:12px;pointer-events:none}.world-map-tooltip strong,.world-map-tooltip-total,.world-map-tooltip-empty{display:block}.world-map-tooltip-total{margin-top:2px;color:var(--secondary)}.world-map-tooltip-empty{margin-top:5px;color:var(--secondary);font-style:italic}.world-map-provider-line{display:flex;justify-content:space-between;gap:16px;margin-top:7px;padding-top:6px;border-top:1px solid var(--border)}.world-map-provider-line+ .world-map-provider-line{margin-top:5px;padding-top:5px}.world-map-provider-line span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.world-map-provider-line strong{font-variant-numeric:tabular-nums}.world-map-legend{display:flex;align-items:center;gap:8px;margin:8px 2px 0;color:var(--secondary);font-size:11px;font-variant-numeric:tabular-nums}.world-map-legend-gradient{display:block;flex:1;height:8px;border-radius:99px;background:linear-gradient(90deg,var(--surface),hsl(198 25% 49%));border:1px solid var(--border)}.world-map-note{margin:8px 2px 0}.map-statistics-world-map-card .section-heading{align-items:flex-start}.map-statistics-world-map-card .section-heading .table-help{padding-top:3px;text-align:right}
.overview-chart-wrap{overflow-x:auto}.overview-trend-chart{display:block;width:100%;min-width:520px;height:auto;min-height:180px}.overview-trend-chart text{fill:var(--secondary);font:500 11px var(--font-ui)}.overview-chart-success{fill:var(--interactive);background:var(--interactive)}.overview-chart-failed{fill:var(--danger);background:var(--danger)}.overview-chart-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:7px;color:var(--secondary);font-size:11px}.overview-chart-note{font-size:12px;color:var(--secondary);margin:10px 0 0}.overview-chart-legend span{display:inline-flex;align-items:center;gap:5px}.overview-chart-legend i{display:inline-block;width:9px;height:9px;border-radius:2px}.provider-metrics{grid-template-columns:repeat(4,minmax(0,1fr))}.map-statistics-provider-table{display:block}.provider-empty-disclosure{padding:16px 20px}.provider-empty-disclosure>details>summary{list-style:none}.provider-empty-disclosure>details>summary::-webkit-details-marker{display:none}.diagnostic-failure-summary{margin:14px 0 0;padding:11px 13px;border-left:3px solid var(--danger);border-radius:6px;background:var(--error-surface);color:var(--danger);font-size:13px}.diagnostic-failure-summary strong{font-weight:750}.model-statistics article>.info-control{display:inline-flex;margin-top:6px;vertical-align:middle}.history-more-filters{min-width:130px}.history-more-filters .disclosure-body{min-width:170px}
.overview-chart-update{fill:var(--stone);background:var(--stone)}@media(max-width:760px){.overview-heading{align-items:flex-start;flex-direction:column;gap:12px}.overview-period-form,.overview-period-form select{width:100%}.overview-activity-item{grid-template-columns:1fr max-content;gap:3px 8px}.overview-activity-item>time{grid-column:1/-1}.overview-activity-provider{grid-column:2;grid-row:2}.overview-activity-item .map-activity-copy{grid-column:1;grid-row:2}}
@media(max-width:560px){.overview-panel{padding:16px}.overview-attention-item{grid-template-columns:auto minmax(0,1fr)}.overview-detail-link{grid-column:2}}
@media(max-width:700px){.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
.overview-primary-grid{display:grid;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}.overview-primary-grid .overview-panel{min-width:0}.overview-activity-item{grid-template-columns:minmax(0,1fr) max-content}.overview-activity-item>time{grid-column:2;grid-row:1 / span 2}.overview-activity-item .overview-activity-label{grid-column:1}.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){grid-column:1}.overview-compact-empty{padding-bottom:14px}.inline-filter-row{justify-content:flex-start}.inline-filter-row label{flex:0 1 260px}.inline-filter-row select{flex:0 0 170px}
.system-health-page{padding-top:30px}
.system-health-list{display:grid;gap:0}
.system-health-row{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(8rem,auto);align-items:center;gap:8px 16px;min-height:0;padding:8px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}
.system-health-row:first-child{border-top:0;padding-top:4px}
.system-health-row h2{margin:0;font-size:13px;line-height:20px;font-weight:650}
.system-health-when{color:var(--secondary);font-size:12px;text-align:end}
.system-health-issue{grid-template-columns:minmax(12rem,1fr) minmax(14rem,2fr) minmax(9rem,1.2fr) minmax(8rem,auto);padding:12px 0}.system-health-issue-heading{display:flex;align-items:center;gap:8px}.system-health-cause,.system-health-action{margin:0;font-size:12px;line-height:1.45}.system-health-cause{color:var(--graphite)}.system-health-action{color:var(--secondary)}.system-health-technical{grid-column:1/-1;margin-top:2px}
.system-health-technical{margin-top:8px}
.system-health-description p{margin:0 0 10px;color:var(--secondary);font-size:12px;line-height:1.55}.system-health-explanation{margin:12px 0;font-size:11px}.system-health-explanation div{display:grid;grid-template-columns:48px 1fr;gap:7px;padding:5px 0;border-top:1px solid var(--border)}.system-health-explanation dt{font-weight:750;color:var(--graphite)}.system-health-explanation dd{margin:0;color:var(--secondary)}.indexnow-status-note,.indexnow-error{color:var(--secondary);font-size:11px;line-height:1.55}.indexnow-details{margin:14px 0;font-size:11px}.indexnow-details div{display:grid;grid-template-columns:minmax(150px,auto) minmax(0,1fr);gap:10px;padding:5px 0;border-top:1px solid var(--border)}.indexnow-details dt{font-weight:750;color:var(--graphite)}.indexnow-details dd{margin:0;color:var(--secondary);overflow-wrap:anywhere}.indexnow-url-preview{margin:0 0 10px;padding-left:18px;color:var(--secondary);font-size:11px}.indexnow-url-preview code{font:500 10px var(--font-mono);overflow-wrap:anywhere}.system-health-badge{display:inline-flex;padding:4px 8px;border:1px solid;border-radius:999px;font-size:11px;font-weight:750}.system-health-healthy{border-color:var(--status-success-border);background:var(--status-success-surface);color:var(--status-success-text)}.system-health-warning{border-color:var(--status-tested-border);background:var(--status-tested-surface);color:var(--status-tested-text)}.system-health-failed{border-color:var(--status-error-border);background:var(--status-error-surface);color:var(--status-error-text)}.system-health-unknown{border-color:var(--status-neutral-border);background:var(--status-neutral-surface);color:var(--status-neutral-text)}
.model-statistics .attempts-metric>span{display:inline-flex;align-items:center;gap:6px}
@media(max-width:900px){.overview-primary-grid{grid-template-columns:1fr}}
@media(max-width:760px){.overview-activity-item{grid-template-columns:1fr max-content}.overview-activity-item>time{grid-column:2;grid-row:1 / span 2}.overview-activity-item .map-activity-copy{grid-column:1;grid-row:1 / span 2}.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){white-space:normal}}
@media(max-width:480px){.inline-filter-row label,.inline-filter-row select{flex-basis:auto}}
.overview-attention-review .overview-attention-dot{color:var(--warning,var(--stone))}
.provider-action-bar{padding:0 0 4px;background:transparent;border:0;border-radius:0}
.map-statistics-definition-note{margin:10px 0 0}

/* Shared Admin typography and density contract. Keep page-specific layout
   rules above this block; this is the final type hierarchy consumed by every
   authenticated Admin view. */
:root{
  --admin-type-eyebrow-size:12px;--admin-type-eyebrow-line:16px;
  --admin-type-page-title-size:clamp(32px,3.5vw,44px);--admin-type-page-title-line:1.06;
  --admin-type-section-title-size:22px;--admin-type-section-title-line:26px;
  --admin-type-subsection-size:15px;--admin-type-subsection-line:20px;
  --admin-type-description-size:15px;--admin-type-description-line:22px;
  --admin-type-body-size:15px;--admin-type-body-line:22px;
  --admin-type-label-size:12px;--admin-type-label-line:16px;
  --admin-type-kpi-value-size:30px;--admin-type-kpi-value-line:30px;
  --admin-type-support-size:12px;--admin-type-support-line:17px;
  --admin-type-table-header-size:11px;--admin-type-table-header-line:16px;
  --admin-type-table-primary-size:13px;--admin-type-table-primary-line:18px;
  --admin-type-table-meta-size:12px;--admin-type-table-meta-line:17px;
  --admin-type-control-size:13px;--admin-type-control-line:18px;
  --admin-type-button-size:13px;--admin-type-button-line:18px;
  --admin-type-badge-size:11px;--admin-type-badge-line:15px;
  --admin-type-helper-size:12px;--admin-type-helper-line:18px;
  --admin-type-technical-size:11px;--admin-type-technical-line:16px;
  --admin-control-font-size:var(--admin-type-control-size)
}
body{font-size:var(--admin-type-body-size);line-height:var(--admin-type-body-line)}
.eyebrow,.section-kicker,.detail-kicker{font-size:var(--admin-type-eyebrow-size);line-height:var(--admin-type-eyebrow-line)}
h1{font-size:var(--admin-type-page-title-size);line-height:var(--admin-type-page-title-line)}
h2,.provider-card .section-heading h2,.attribution-preview h2,.map-statistics-empty h2,.device-dialog-header h2{font-size:var(--admin-type-section-title-size);line-height:var(--admin-type-section-title-line)}
.lede{font-size:var(--admin-type-description-size);line-height:var(--admin-type-description-line)}
.table-help,.results-count,.page-meta,.overview-chart-note,.historical-failure-note,.review-help{font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
button,input,select,textarea{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}
.filter-bar input,.filter-bar select,.filter-disclosure>summary,.quick-filter,.provider-action-overflow>summary,.secondary-button,.button-link,.copy-button,.provider-pagination button,.device-pagination button,.admin-action-dialog button:not(.link-button),.auth-card button:not(.link-button),.device-support-review button[type="submit"],.model-administration button[type="submit"]{font-size:var(--admin-type-button-size);line-height:var(--admin-type-button-line)}
.admin-section-nav,.admin-nav,.admin-section-nav a,.admin-nav a,.link-button{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}

.admin-kpi-grid article>span,.provider-metrics article>span,.diagnostic-model-metrics article>span{font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line)}
.admin-kpi-grid article>strong,.provider-metrics article>strong,.diagnostic-model-metrics article>strong,.model-statistics article>strong{font-size:var(--admin-type-kpi-value-size);line-height:var(--admin-type-kpi-value-line)}
.overview-period-form{margin:0;padding:6px}
.overview-period-form label{display:flex}
.overview-period-form select{height:var(--admin-control-height);min-height:var(--admin-control-height);min-width:154px;padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius);font:600 var(--admin-control-font-size)/1.2 var(--font-ui)}
.overview-chart-panel{padding-top:16px;padding-bottom:16px}
.overview-chart-panel .section-heading{margin-bottom:6px}
.overview-chart-wrap{max-width:780px;margin:0 auto}
.overview-download-panel{padding-top:16px;padding-bottom:16px}
.overview-download-panel .section-heading{margin-bottom:6px}
.overview-map-heading,.overview-download-heading{align-items:flex-start;flex-wrap:wrap}
.overview-map-totals,.overview-download-totals{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-inline-start:auto}
.overview-map-total,.overview-download-total{display:inline-flex;align-items:baseline;gap:4px;min-width:0;padding:5px 8px;border:1px solid var(--border);border-radius:8px;background:var(--surface-muted);font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line)}
.overview-map-total strong,.overview-download-total strong{color:var(--graphite);font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}
.overview-map-total small,.overview-download-total small{color:var(--secondary);font-size:var(--admin-type-support-size)}
.overview-map-total{text-decoration:none;color:inherit}
.overview-map-total:hover{border-color:color-mix(in srgb,var(--sky) 52%,var(--border))}
.overview-chart-download-dmg{fill:var(--interactive);background:var(--interactive)}
.overview-chart-download-zip{fill:var(--status-success-text);background:var(--status-success-text)}
.overview-chart-download-unknown line{stroke:var(--secondary);stroke-width:3;stroke-dasharray:4 3}.overview-chart-download-unknown text{fill:var(--secondary);stroke:none;font-size:10px;font-weight:700}
.overview-trend-chart{display:block;width:100%;height:260px;max-width:760px;min-height:0;margin:0 auto}
.overview-trend-mobile{display:none}
@media(min-width:901px) and (max-width:1100px),(max-width:700px){
  .overview-trend-desktop{display:none}
  .overview-trend-mobile{display:block;min-width:0;width:100%;height:auto;aspect-ratio:360/220}
  .overview-chart-wrap{width:100%;min-width:0;overflow:visible}
  .overview-trend-mobile text{font-size:13px}
}
@media(max-width:760px){
  .overview-map-totals,.overview-download-totals{justify-content:flex-start;margin-inline-start:0}
}
@media(max-width:560px){.overview-map-totals,.overview-download-totals{flex-basis:100%}.overview-attention-actions{grid-column:2;justify-content:flex-start;flex-wrap:wrap}}
.overview-provider-panel h2{font-family:var(--font-ui);font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line);letter-spacing:0}
.overview-provider-panel .section-kicker{margin-bottom:1px}
.overview-provider-panel{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:18px;min-height:76px;padding:12px 16px}
.overview-provider-panel .overview-provider-summary{justify-content:flex-start}
.device-information-section .model-information-list{max-width:780px}
.device-information-section .model-information-list div{grid-template-columns:150px minmax(0,1fr);gap:16px}
.device-information-section .model-information-list dd{text-align:left}
.diagnostic-detail-dialog{width:min(1160px,calc(100% - 32px));max-height:min(82vh,760px)}
.diagnostic-detail-inner{max-height:min(82vh,760px)}
.overview-compact-empty{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 16px}
.overview-compact-empty .section-heading{margin:0}
.overview-compact-empty .section-kicker{display:none}
.overview-compact-empty h2{font-family:var(--font-ui);font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line);letter-spacing:0}
.overview-compact-empty .overview-empty-state{padding:0;font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line);font-weight:500}

table{font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
table th,table td{padding:8px 12px;font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
table thead th{font-size:var(--admin-type-table-header-size);line-height:var(--admin-type-table-header-line)}
table td small,.table-secondary,.provider-name-link small,.provider-package-id,.history-map small,.history-error small{font-size:var(--admin-type-table-meta-size);line-height:var(--admin-type-table-meta-line)}
table code,.technical-value,.provider-table-wrap code,.audit-technical-details code{font-size:var(--admin-type-technical-size);line-height:var(--admin-type-technical-line)}
.device-table-wrap tbody td{padding:7px 12px;font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.device-table-wrap th{font-size:var(--admin-type-table-header-size);line-height:var(--admin-type-table-header-line)}
.device-model-button strong,.provider-name-link strong,.provider-package-name{font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.provider-error,.provider-activation-note,.incomplete-state,.diagnostic-failure-summary{font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
.provider-information-list dt,.model-information-list dt,.device-detail-grid dt,.device-catalog-details dt,.device-support-review label,.device-public-review label,.administration-grid label{font-size:var(--admin-type-label-size);line-height:var(--admin-type-helper-line)}
.provider-information-list dd,.model-information-list dd,.device-detail-grid dd,.device-catalog-details dd{font-size:var(--admin-type-table-primary-size);line-height:20px}
.provider-information-list a,.provider-url-cell a{font-size:var(--admin-type-table-meta-size);line-height:var(--admin-type-table-meta-line)}

.status-badge,.provider-status,.admin-state,.diagnostic-state,.diagnostic-result,.diagnostic-chip,.new-badge,.identity-pending-indicator,.provider-component .provider-status{min-height:24px;padding:4px 7px;font-size:var(--admin-type-badge-size);line-height:var(--admin-type-badge-line)}
.admin-disclosure>summary,.provider-action-overflow>summary{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}
.admin-action-dialog h4,.administration-grid h3{font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line)}

.filter-bar{padding:6px;gap:7px}
.provider-card{margin-top:20px;padding:18px 20px}
.provider-card .section-heading{margin-bottom:12px}
.provider-information-list div,.model-information-list div{padding:8px 0}
.provider-dashboard-grid{gap:16px}
.campaign-card{padding:20px}
.diagnostic-model-metrics{margin-bottom:24px}
.model-page-header{margin-bottom:20px}
.model-page-section{margin-top:28px}
.device-detail-grid{gap:16px}
.device-catalog-details,.model-technical-details{margin-top:16px}
.secondary-button,.provider-pagination button,.device-pagination button{min-height:var(--admin-control-height);padding:8px 10px}
.github-actions>.secondary-button{display:inline-flex;align-items:center;justify-content:center;margin:0;align-self:stretch;text-align:center;text-decoration:none;white-space:normal}
.github-actions>.copy-status{flex-basis:100%}
.identity-search-results{display:grid;gap:4px;max-height:240px;overflow-y:auto;margin:8px 0}
.identity-search-results[hidden]{display:none}
.identity-search-results>button.secondary-button{display:block;width:100%;min-height:44px;margin:0;text-align:left;white-space:normal;overflow-wrap:anywhere}
.provider-action-overflow>summary{min-height:var(--admin-control-height);padding:8px 12px}
.provider-action-bar{gap:7px}
.disclosure-body{margin-top:12px}

@media(max-width:760px){
  .provider-card{padding:16px}
  .campaign-card{padding:18px}
  .table-help,.results-count,.page-meta{line-height:16px}
  .overview-compact-empty{align-items:flex-start;flex-direction:column;gap:4px}
  .overview-provider-panel{grid-template-columns:1fr;align-items:flex-start;gap:7px}
  .overview-provider-panel .overview-provider-summary{gap:7px}
  .device-information-section .model-information-list div{grid-template-columns:1fr;gap:2px}
}

/* Admin audit: one UI type family, visible actions, responsive navigation. */
h1,h2,h3,h4,.administration-grid h3,.admin-kpi-grid article>strong,.provider-metrics article>strong,.diagnostic-model-metrics article>strong{font-family:var(--font-ui);letter-spacing:-.015em}
:root{--admin-type-page-title-size:clamp(28px,3vw,36px);--admin-type-page-title-line:1.2;--admin-type-section-title-size:20px;--admin-type-section-title-line:26px}
.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:8px 16px;padding:10px 0}
.admin-skip-link{position:fixed;z-index:100;top:8px;left:8px;padding:9px 12px;border-radius:8px;background:var(--graphite);color:var(--surface);font-weight:700;transform:translateY(-150%)}
.admin-skip-link:focus{transform:none;outline:var(--admin-focus-ring);outline-offset:2px}
.admin-section-nav{flex:1 1 100%;order:3;min-width:0;justify-content:flex-start}
.admin-nav{margin-inline-start:auto;flex:0 1 auto;min-width:0}
.admin-header-left{flex:0 0 auto}
.diagnostic-action-form button[type='submit']{min-height:var(--admin-control-height);padding:8px 12px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:600}
.diagnostic-action-form button[type='submit']:hover{background:var(--interactive-hover)}
.diagnostic-action-form button.secondary-button,.model-administration button.secondary-button{background:var(--surface);color:var(--interactive);border:1px solid var(--border)}
.overview-chart-line{fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}.overview-chart-line.overview-chart-success,.overview-chart-line.overview-chart-download-success{stroke:var(--interactive)}.overview-chart-line.overview-chart-failed,.overview-chart-line.overview-chart-download-failed{stroke:var(--danger)}.overview-chart-line.overview-chart-update{stroke:var(--status-success-text)}.overview-chart-download-success{fill:var(--interactive);background:var(--interactive)}.overview-chart-download-failed{fill:var(--danger);background:var(--danger)}.overview-chart-update{fill:var(--status-success-text);background:var(--status-success-text)}
.model-status-line{display:flex;align-items:center;gap:8px 16px;flex-wrap:wrap;margin-top:8px}.model-status-line>span{display:inline-flex;align-items:center;gap:6px;color:var(--secondary);font-size:12px}.model-status-line strong{color:var(--graphite);font-size:12px}.compact-empty-state{margin-top:20px;padding:18px 20px;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.compact-empty-state h2{margin:0 0 4px}.compact-empty-state p{margin:0;color:var(--secondary)}.diagnostic-identity-state{margin:12px 0;padding:10px 12px;border-left:3px solid var(--warning);background:var(--surface-muted);font-size:13px}
.timestamp-metric strong{font-size:var(--admin-type-subsection-size)!important;line-height:var(--admin-type-subsection-line)!important}
.overview-primary-grid{align-items:start}.overview-primary-grid>.overview-panel{min-height:0}
.model-administration>summary,.device-information-section>summary{margin-bottom:12px}
.model-administration,.device-information-section{padding:0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
.admin-live-update{position:sticky;top:var(--admin-topbar-height);z-index:29;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 24px;background:var(--selected-tint,var(--surface));border-bottom:1px solid var(--border);font-size:14px}
.admin-live-update[hidden]{display:none}
@media(max-width:800px){.admin-section-nav{flex-basis:100%;order:3}.admin-nav{margin-inline-start:auto}.admin-live-update{padding:10px 16px}}
@media(max-width:560px){.admin-header-left{width:auto}.admin-nav{width:100%;justify-content:space-between}.admin-section-nav{overflow:visible}}
/* Phone layouts share the same controls and data as desktop. */
#admin-menu-panel,.mobile-filter-options{display:contents}
.admin-nav .admin-mobile-website,.filter-bar .device-mobile-sort{display:none}
@media(max-width:760px){
  :root{--admin-control-height:44px;--admin-control-font-size:16px;--admin-topbar-height:64px}
  .admin-topbar-inner{min-height:64px;flex-direction:row;align-items:center;flex-wrap:nowrap;gap:8px;padding:8px 0}
  .admin-header-left{width:auto;min-width:0;flex:1 1 auto}
  .admin-header-left>.admin-badge,.admin-header-left>.admin-website-link{display:none}
  .admin-brand{gap:6px;font-size:19px}.admin-brand img{width:22px;height:26px}
  #admin-menu-toggle{flex:0 0 auto;min-height:44px;padding:8px 12px}
  #admin-menu-panel{display:block;position:absolute;top:100%;left:0;right:0;max-height:calc(100dvh - 64px);overflow-y:auto;overscroll-behavior:contain;padding:12px 16px 20px;background:var(--surface);border-bottom:1px solid var(--border);box-shadow:0 8px 16px color-mix(in srgb,var(--graphite) 12%,transparent)}
  .admin-topbar:not(.admin-mobile-ready) .admin-topbar-inner{flex-wrap:wrap}
  .admin-topbar:not(.admin-mobile-ready) #admin-menu-panel{position:static;max-height:none;flex-basis:100%}
  main.dashboard{width:100%;max-width:100%;margin:0;padding:20px 16px 32px}.heading-row{margin-bottom:16px}.eyebrow{margin-bottom:6px}
  .lede{font-size:14px;line-height:1.5}.overview-heading{gap:10px}.overview-period-form{padding:0;border:0;background:none}
  .overview-attention-panel{margin-top:0}.overview-attention-item{gap:6px 10px;padding:12px 0}.overview-detail-link{min-height:36px;display:inline-flex;align-items:center}
  .overview-attention-item span,.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){white-space:normal;overflow:visible;overflow-wrap:anywhere}
  .installation-kpis,.model-statistics,.diagnostic-model-metrics,.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .admin-kpi-grid article{min-width:0;padding:12px;min-height:80px}.installation-kpis article:last-child{grid-column:1/-1}
  .installation-kpis{margin-bottom:12px}.historical-failure-note{margin-bottom:16px}
  .admin-filter-bar,.filter-bar{min-width:0;max-width:100%;gap:8px}.admin-filter-bar{align-items:stretch}
  .filter-bar label,.filter-search{min-width:0!important;max-width:100%;flex:1 1 100%}
  .filter-bar .filter-clear{width:100%}
  input:not([type='checkbox']):not([type='radio']),select,textarea{font-size:16px!important;max-width:100%;min-width:0;min-height:44px}
  .quick-filter-group{min-width:0;max-width:100%;display:flex;flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;flex-basis:100%;gap:5px;padding-bottom:3px}
  .quick-filter{flex:0 0 auto;min-height:44px;font-size:13px}
  .mobile-filter-options{display:grid;grid-template-columns:1fr;gap:8px;width:100%}
  .mobile-filter-toggle{width:100%;text-align:left}
  #overview-attention-title{scroll-margin-top:80px}
  .model-page-header{gap:12px;grid-template-columns:auto minmax(0,1fr)}.model-page-image{width:64px;height:64px}.model-page-heading h1{font-size:24px}
  .model-review-alert{gap:8px;align-items:flex-start}.model-review-alert a{min-height:44px;display:flex;align-items:center}
  .provider-action-bar{display:grid;grid-template-columns:1fr 1fr}.provider-action-bar button{width:100%;min-height:44px}.provider-action-overflow{width:100%}.provider-action-bar>p{grid-column:1/-1}
  details>summary{min-height:44px;align-content:center;line-height:1.45}summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
  .diagnostic-detail-dialog{width:calc(100% - 32px);max-width:none;max-height:calc(100dvh - 16px);margin:auto;border-radius:12px}
  .diagnostic-detail-inner{padding:16px;max-height:calc(100dvh - 16px);overflow:auto;overscroll-behavior:contain}
  .diagnostic-detail-inner>.device-dialog-header{position:sticky;top:-16px;z-index:2;background:var(--surface);padding:12px 0;flex-direction:row;align-items:flex-start;gap:10px}
  .diagnostic-detail-inner .dialog-close{width:44px;min-width:44px;height:44px}
  .diagnostic-detail-summary,.diagnostic-actions-grid{grid-template-columns:1fr}.diagnostic-detail-summary div{grid-template-columns:minmax(80px,.7fr) minmax(0,1fr)}
  .diagnostic-action-form button{min-height:44px}.diagnostic-detail-summary dd{text-align:right}
  .auth-card{margin:24px 16px;max-width:calc(100% - 32px);padding:20px}.auth-card button{min-height:44px}
  .campaign-card{padding:16px}.campaign-grid{gap:16px}.campaign-field input,.campaign-field select{font-size:16px}
  .admin-live-update{top:64px;gap:8px;padding:10px 16px;font-size:13px}.admin-live-update button{min-height:44px}
}
@media(max-width:760px){.filter-bar .device-mobile-sort{display:block}.device-filter-bar{position:static}.device-sticky-header{display:none!important}.table-wrap{min-width:0;max-width:100%}.diagnostic-list-wrap{max-height:none}.table-wrap:has(.mobile-record-table){border:0;background:transparent;overflow:visible;border-radius:0}table.mobile-record-table{display:block;min-width:0!important;width:100%;border:0;table-layout:auto}.mobile-record-table colgroup,.mobile-record-table thead{display:none}.mobile-record-table tbody{display:grid;width:100%;gap:12px}.mobile-record-table tbody tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;min-width:0}.mobile-record-table tbody td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;text-align:left!important;white-space:normal!important;overflow-wrap:anywhere;font-size:13px}.mobile-record-table td a{min-height:44px;display:inline-flex;align-items:center}.mobile-record-table td .provider-name-link{align-items:flex-start}.mobile-record-table td[data-label='']::before{display:none}.mobile-record-table tbody td::before{content:attr(data-label);display:block;margin-bottom:5px;font-size:11px;line-height:1.35;font-weight:600;color:var(--secondary)}.mobile-record-table tbody td:first-child{grid-column:1/-1;font-weight:650}.mobile-record-table tbody td:has(button){grid-column:1/-1}.mobile-record-table td button{min-height:44px;width:100%}.device-model-button{min-height:44px}.device-thumb{width:40px;height:48px}.device-model-copy{min-width:0}.device-model-copy strong{white-space:normal}.provider-pagination,.device-pagination{display:flex;flex-wrap:wrap;gap:8px}.provider-pagination button,.device-pagination button{min-height:44px}.provider-pagination>span{flex:1 1 100%;order:3}.map-statistics-filter-bar .filter-disclosure{width:100%}.map-statistics-filter-bar .filter-disclosure>summary{justify-content:flex-start}.map-statistics-filter-bar .filter-disclosure .disclosure-body{position:static;margin-top:8px;box-shadow:none}}
@media(max-width:760px){.map-statistics-provider-table .mobile-record-table td[data-empty-group='true']{display:none!important}}

/* Full labels and values remain readable at every admin width. */
.overview-attention-item span,.overview-activity-item .map-activity-copy>span:not(.overview-activity-label),.device-model-copy strong,.provider-error{white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;max-width:none}
.overview-panel,.system-health-row,.provider-card,.campaign-card,.admin-kpi-grid article,.provider-metrics article{min-width:0;overflow-wrap:anywhere}
.overview-attention-item .overview-attention-actions{display:inline-flex;align-items:center;justify-content:flex-end;gap:8px}.overview-review-dismiss-form{display:inline-flex;margin:0}.overview-dismiss-button{display:inline-flex;align-items:center;justify-content:center;min-width:32px;min-height:32px;padding:0;border:1px solid var(--border);border-radius:8px;background:var(--surface-muted);color:var(--graphite);font-size:20px;line-height:1;cursor:pointer}.overview-dismiss-button:hover{border-color:var(--interactive);color:var(--interactive)}.overview-dismiss-button:focus-visible{outline:3px solid var(--admin-focus-ring);outline-offset:2px}.overview-review-notice{display:flex;align-items:center;gap:8px;margin:0 0 10px;padding:9px 12px;border:1px solid var(--border);border-radius:9px;background:var(--surface-muted);color:var(--graphite);font-size:13px}.overview-review-notice form{display:inline-flex;margin:0}
.section-heading>div,.heading-row>div,.provider-latest-summary>div,.device-model-copy{min-width:0}
.generated-url{white-space:pre-wrap;overflow-wrap:anywhere;overflow:visible;word-break:normal}
.diagnostic-technical-details pre,.model-technical-details pre,.device-dialog pre,.diagnostic-detail-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}
.diagnostic-list-wrap{max-height:none}
@media(min-width:701px){
  .table-wrap table,.device-sticky-header table{width:100%;table-layout:auto}
  .evidence-table-wrap table,.device-table-wrap table,.device-sticky-header table{min-width:960px}
  .evidence-table-wrap th:first-child,.evidence-table-wrap td:first-child{white-space:nowrap!important;overflow:hidden;text-overflow:ellipsis}
  .table-wrap th,.device-sticky-header th{white-space:nowrap;overflow-wrap:normal}
  .table-wrap td{overflow-wrap:break-word}
  .table-wrap .admin-timestamp,.device-sticky-header .admin-timestamp{white-space:normal}
  .model-history-table th:nth-child(4){width:20%}.model-history-table th:nth-child(7){width:11%}
  .device-table-wrap th button,.device-sticky-header th button{min-width:0;width:100%;white-space:normal;text-align:left;justify-content:flex-start}
  .provider-history-wrap th:nth-child(1){width:14%}.provider-history-wrap th:nth-child(2){width:10%}
  .provider-history-wrap th:nth-child(3){width:26%}.provider-history-wrap th:nth-child(4){width:6%}
  .provider-history-wrap th:nth-child(5){width:10%}.provider-history-wrap th:nth-child(6){width:10%}
  .provider-history-wrap th:nth-child(7){width:24%}
  .provider-source-table th:nth-child(1){width:14%}.provider-source-table th:nth-child(2){width:50%}.provider-source-table th:nth-child(3){width:12%}.provider-source-table th:nth-child(4){width:24%}
  .provider-package-table{min-width:640px!important}.provider-package-table th:nth-child(1){width:49%}.provider-package-table th:nth-child(2){width:18%}.provider-package-table th:nth-child(3){width:16%}.provider-package-table th:nth-child(4){width:17%}.provider-package-table td{vertical-align:top}.provider-package-table details{margin-top:8px;font-weight:400}
  .provider-run-table th:nth-child(1){width:5%}.provider-run-table th:nth-child(2),.provider-run-table th:nth-child(3){width:14%}.provider-run-table th:nth-child(4){width:20%}.provider-run-table th:nth-child(5){width:13%}.provider-run-table th:nth-child(6),.provider-run-table th:nth-child(7){width:8%}.provider-run-table th:nth-child(8){width:18%}
  .provider-component{white-space:normal;flex-wrap:wrap}.provider-component-list{min-width:0}
  .provider-component .provider-status{white-space:normal;line-height:1.3}
  .overview-trend-chart{min-width:0}
  .diagnostic-detail-dialog,.device-dialog{max-height:calc(100dvh - 48px);overflow:hidden}
  .diagnostic-detail-inner,.device-dialog-inner{max-height:calc(100dvh - 48px);overflow-y:auto;overscroll-behavior:contain}
  .diagnostic-detail-inner>.device-dialog-header,.device-dialog-inner>.device-dialog-header{position:sticky;top:-24px;z-index:2;background:var(--surface);padding:12px 0}
}

/* Admin audit: consistent page hierarchy, disclosures and connected diagnostics. */
main.dashboard{padding-top:30px}
main.dashboard>.heading-row{align-items:flex-start}
main.dashboard>.heading-row .eyebrow{margin:0 0 8px}
main.dashboard>.heading-row h1{margin:0}
main.dashboard>.heading-row .lede{margin:12px 0 0}
.admin-disclosure:not(.filter-disclosure)>summary{position:relative;list-style:none;padding:10px 14px 10px 36px;margin:0;min-height:44px;line-height:24px;font-size:13px;font-weight:650}
.admin-disclosure:not(.filter-disclosure)>summary::-webkit-details-marker{display:none}
.admin-disclosure:not(.filter-disclosure)>summary::before{content:'';position:absolute;left:14px;top:50%;width:6px;height:6px;border:solid currentColor;border-width:0 2px 2px 0;transform:translateY(-50%) rotate(-45deg);transform-origin:center}
.admin-disclosure[open]:not(.filter-disclosure)>summary::before{transform:translateY(-65%) rotate(45deg)}
.admin-disclosure[open]:not(.filter-disclosure)>summary{margin-bottom:0}
.model-information-columns>details,details.overview-panel,details.model-page-section{padding:0;min-height:0}
.provider-component-list{display:grid!important;grid-template-columns:1fr!important;gap:6px!important;min-width:200px}.provider-component-list>span{display:grid;grid-template-columns:90px max-content;align-items:center;gap:8px}.provider-detail .provider-history-wrap td{vertical-align:top}
.overview-chart-grid{stroke:var(--border);stroke-width:1}.overview-chart-axis-label{fill:var(--secondary);font-size:11px}
.model-information-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start;margin-top:16px}
.model-information-columns>details{margin:0;min-width:0}
.model-information-columns .model-information-list{max-width:none;margin-top:14px}
.model-information-columns .model-information-list div{padding:10px 12px;gap:4px 16px;grid-template-columns:minmax(100px,1fr) minmax(0,3fr)}
.model-information-columns .device-information-section .model-information-list div{grid-template-columns:minmax(100px,1fr) minmax(0,3fr)}
.model-information-columns .model-information-list dt,.model-information-columns .model-information-list dd{min-width:0;text-align:left;overflow-wrap:anywhere}
.model-information-columns.device-overview-sections{grid-template-columns:minmax(0,1fr)}
.model-detail-page details:is(.model-administration,.device-information-section,.model-technical-details).admin-disclosure{padding:0}

.model-detail-page details:is(.model-administration,.device-information-section,.model-technical-details).admin-disclosure[open]>summary{margin-bottom:16px}
.device-information-section{container-type:inline-size}.device-key-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;margin:0}.device-key-facts>div{min-width:0}.device-key-facts dt{color:var(--secondary);font-size:13px;line-height:20px}.device-key-facts dd{margin:6px 0 0;font-size:16px;line-height:24px;font-weight:600;overflow-wrap:anywhere}@container(min-width:720px){.device-key-facts{grid-template-columns:repeat(4,minmax(0,1fr))}}
.device-information-note{margin:24px 0 0;color:var(--secondary);font-size:13px;line-height:20px;text-wrap:pretty}.device-information-more{display:flex;flex-wrap:wrap;align-items:start;gap:12px 24px;margin-top:16px}.device-extra-specifications{flex:1 1 320px;min-width:0}.device-specification-link{display:inline-flex;align-items:center;gap:6px;min-height:40px;max-width:100%;font-size:13px;line-height:20px;text-wrap:pretty}.device-specification-link svg{flex:none}
.device-overview-sections .admin-disclosure:not([open])>summary:dir(rtl)::before{transform:translateY(-50%) rotate(135deg)}
.device-technical-hint{display:block;color:var(--secondary);font-size:13px;font-weight:400;line-height:20px;margin-top:4px}
.device-overview-sections .device-extra-specifications .model-information-list{border:0;border-radius:0;background:transparent}.device-overview-sections .device-extra-specifications .model-information-list div{padding-inline:0;grid-template-columns:minmax(0,1fr) minmax(0,2fr);text-align:start}.device-overview-sections .device-extra-specifications :is(dt,dd){text-align:start}
@media(max-width:700px){.device-overview-sections .admin-disclosure:not(.filter-disclosure)>summary,.device-specification-link{min-height:44px}}
.world-map-controls{display:flex;align-items:center;gap:8px;padding:4px 10px 10px}
.world-map-controls button{min-height:40px;min-width:40px;padding:6px 10px;border-radius:var(--admin-control-radius);background:var(--surface);color:var(--interactive);border:1px solid var(--border)}
.world-map-controls span{font-size:12px;color:var(--secondary)}
.world-map-svg{height:420px;min-height:300px;touch-action:none;cursor:grab;overflow:hidden;user-select:none;-webkit-user-select:none}.world-map-svg *{user-select:none;-webkit-user-select:none;-webkit-user-drag:none}
.world-map-svg:active{cursor:grabbing}
.world-map-svg:focus-visible{outline:var(--admin-focus-ring);outline-offset:-2px}
.world-map-svg svg{fill:var(--surface)}.world-map-svg.leaflet-container{padding:0;background:var(--surface-muted);font-family:var(--font-ui)}.world-map-svg .leaflet-control-attribution{font-size:10px;background:var(--surface);color:var(--secondary)}
.world-map-svg svg path{vector-effect:non-scaling-stroke}
.world-map-country.is-region-highlight{fill:var(--interactive)!important;stroke:var(--graphite);stroke-width:2}
.region-map-link{display:inline;padding:0;border:0;border-radius:0;background:none;color:var(--interactive);text-align:left;text-decoration:underline;text-underline-offset:3px;white-space:normal;font:inherit;cursor:pointer}
.region-map-link:hover{background:none;color:var(--graphite)}
.map-statistics-coverage-layout{align-items:start;grid-template-columns:minmax(0,3fr) minmax(300px,1fr)}
@media(max-width:1100px){.map-statistics-coverage-layout{grid-template-columns:minmax(0,1fr)}}
.system-health-row[hidden]{display:none}
.test-data-activity-caption{display:block;width:100%;max-width:100%;box-sizing:border-box;white-space:normal;overflow-wrap:anywhere;text-align:left;padding:12px;font-size:13px;font-weight:650}
.telemetry-scope-note{margin:0 0 16px;color:var(--secondary);font-size:12px}.telemetry-scope-note a{color:var(--interactive)}
[id]{scroll-margin-top:calc(var(--admin-topbar-height,100px) + 16px)}
.world-map-tooltip{top:64px}
@media(max-width:900px){.model-information-columns{grid-template-columns:1fr}.model-information-columns .device-information-section .model-information-list div{grid-template-columns:minmax(100px,1fr) minmax(0,3fr)}}
@media(max-width:760px){main.dashboard{padding-top:20px}.system-health-row,.system-health-issue{grid-template-columns:minmax(0,1fr) auto;gap:6px 10px}.system-health-cause,.system-health-action,.system-health-technical,.system-health-when{grid-column:1/-1}.system-health-when{text-align:start}.model-information-columns .model-information-list div{grid-template-columns:1fr}}
/* Admin UI standard: one navigation hierarchy, one control rhythm, concentric surfaces. */
body{font-family:var(--font-ui);text-wrap:pretty}
h1,h2,h3,h4{font-family:var(--font-ui);letter-spacing:-.015em;text-wrap:balance}
.admin-section-nav{align-items:center;gap:16px}
.admin-nav-group{display:flex;align-items:center;gap:4px;min-width:0}
.admin-section-nav details{position:relative;flex:0 0 auto}
.admin-section-nav details>summary{display:inline-flex;align-items:center;min-height:34px;padding:7px 9px;border-radius:var(--admin-control-radius);color:var(--secondary);cursor:pointer;font-size:var(--admin-type-control-size);font-weight:650;list-style:none;white-space:nowrap}
.admin-section-nav details>summary::-webkit-details-marker{display:none}
.admin-section-nav details>summary::after{content:'⌄';margin-inline-start:5px;color:var(--secondary);font-size:12px}
.admin-section-nav details>summary:hover,.admin-section-nav details>summary.active{background:var(--surface-muted);color:var(--interactive)}
.admin-tools-popover{display:grid;gap:2px;position:absolute;z-index:25;top:calc(100% + 7px);left:0;right:auto;min-width:190px;padding:7px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.16)}
.admin-tools-popover a{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 9px;color:var(--graphite);font-size:12px;font-weight:650;text-decoration:none}
.admin-tools-popover a:hover,.admin-tools-popover a.active{background:var(--surface-muted);color:var(--interactive)}
.admin-tools-popover a.active{border-radius:6px}
.admin-user.active{padding:6px 8px;border-radius:var(--admin-control-radius);background:var(--surface-muted);color:var(--interactive)}
.filter-clear{align-self:center;flex:0 0 auto;min-width:58px}
.filter-bar .filter-clear{margin-left:0}
.system-health-explanation div{grid-template-columns:90px minmax(0,1fr)}
.diagnostic-next-action{grid-column:1/-1;margin:0;padding:11px 13px;border-left:3px solid var(--interactive);border-radius:6px;background:var(--surface-muted);color:var(--secondary);font-size:13px}
.diagnostic-next-action strong{color:var(--graphite)}
.diagnostic-secondary-action{grid-column:1/-1;padding-top:2px}
.diagnostic-secondary-action>summary{padding:8px 0;color:var(--interactive);font-size:12px;font-weight:750}
.admin-icon{display:inline-block;width:1em;height:1em;flex:0 0 auto;vertical-align:-.15em;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.device-table-wrap tbody tr,.evidence-model-row{cursor:default}
.device-model-button{border-radius:6px}
.device-model-button:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:3px}
.device-column-model{width:20%}.device-column-variant{width:16%}.device-column-attempts{width:9%}.device-column-successful{width:10%}
.info-control{position:relative}
.info-control::before{content:'';position:absolute;inset:-10px}
.overview-panel,.provider-card,.campaign-card{border-radius:16px}
.table-wrap,.filter-bar{border-radius:12px}
button,.button-link,.copy-button,.secondary-button{transition:background-color .15s ease,border-color .15s ease,color .15s ease,transform .12s ease}
button:active:not(:disabled),.button-link:active,.copy-button:active{transform:scale(.96)}
.filter-bar button:active,.world-map-controls button:active{transform:none}
.filter-bar label,.inline-filter-row label{display:flex;flex-direction:column;gap:6px}
.inline-filter-row label>.sr-only{position:static;width:auto;height:auto;margin:0;overflow:visible;clip:auto;clip-path:none;white-space:normal;font-size:12px;font-weight:650;color:var(--secondary)}
.filter-bar label>input,.filter-bar label>select,.inline-filter-row label>input,.inline-filter-row label>select{flex:none}
.inline-filter-row{align-items:flex-end}
.inline-filter-row label{min-width:0}
.inline-filter-row label>input,.inline-filter-row label>select{width:100%;height:var(--admin-control-height)}
@media(max-width:700px){.inline-filter-row{align-items:stretch}.inline-filter-row label{flex-basis:auto}}
.filter-bar>.filter-disclosure{align-self:flex-end}
.filter-bar>.filter-clear{align-self:flex-end}
.filter-bar>.results-count{align-self:flex-end;min-height:var(--admin-control-height);display:flex;align-items:center;white-space:normal}
@media(max-width:700px){
  .filter-bar input,.filter-bar select{font-weight:400}
  .filter-bar .device-mobile-sort{display:flex;flex-direction:column;gap:6px}
  .filter-bar .device-mobile-sort select{width:100%;margin:0}
}
.provider-status{text-transform:capitalize}
/* Compact coverage lists keep names, counts and activity readable in the sidebar. */
.map-statistics-popularity .table-wrap{border:0;border-radius:0;overflow:visible}
.map-statistics-popularity .table-wrap .admin-table{display:block;width:100%;min-width:0;table-layout:fixed}
.map-statistics-popularity .table-wrap .admin-table thead{position:absolute;display:block;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.map-statistics-popularity .table-wrap .admin-table tbody{display:grid;gap:0;width:100%}
.map-statistics-popularity .table-wrap .admin-table tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:8px 0;background:none;border:0;border-bottom:1px solid var(--border);border-radius:0;min-width:0}
.map-statistics-popularity .table-wrap .admin-table tbody tr:last-child{border-bottom:0}
.map-statistics-popularity .table-wrap .admin-table td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;white-space:normal;overflow-wrap:anywhere;text-align:left!important;font-size:13px}
.map-statistics-popularity .table-wrap .admin-table td.popular-map-name{grid-column:1;grid-row:1}
.map-statistics-popularity .table-wrap .admin-table td.popular-map-count{grid-column:2;grid-row:1;align-self:start;text-align:right!important;white-space:nowrap}
.map-statistics-popularity .table-wrap .admin-table td[colspan]{grid-column:1/-1}
.map-statistics-popularity .table-wrap .admin-table td::before{display:none}
.map-statistics-popularity .table-wrap .admin-table td.popular-map-count::after{content:none}
.map-statistics-popularity .table-secondary,.map-statistics-popularity code{white-space:normal;overflow-wrap:anywhere;font-size:11px}
.map-statistics-page .popular-map-name-content{display:grid;min-width:0;gap:2px}
.map-statistics-page .popular-map-detail{display:block;min-width:0;color:var(--secondary);font-size:11px;font-weight:400;line-height:1.35;overflow-wrap:anywhere}
.map-statistics-popularity .table-wrap .popular-map-count-label{display:inline-flex;align-items:baseline;gap:3px;white-space:nowrap;font-weight:400}
.map-statistics-popularity .table-wrap .popular-map-count-label>strong{font-weight:750}
.map-statistics-popularity .table-wrap .region-map-link{position:relative;display:inline-flex;width:auto;max-width:100%;min-height:0;padding:0;align-items:flex-start;color:inherit;font-weight:400;line-height:1.35;text-align:left;text-decoration:none;white-space:normal;overflow-wrap:anywhere}
.map-statistics-popularity .table-wrap .region-map-link::after{content:'';position:absolute;inset:0;min-width:44px;min-height:44px}
.map-statistics-popularity .region-map-link:hover,.map-statistics-popularity .region-map-link:focus-visible{text-decoration:underline}
.map-statistics-world-map-card .section-heading{flex-wrap:wrap}
.map-statistics-world-map-card .map-statistics-world-map{padding:0;min-height:0}
.map-statistics-world-map-card .world-map-svg{height:auto;min-height:0;aspect-ratio:900 / 365}
.map-statistics-world-map-card .world-map-controls{position:absolute;z-index:3;top:8px;left:8px;padding:0;gap:6px}
.map-statistics-world-map-card .world-map-controls span{padding:4px 6px;border-radius:var(--admin-control-radius);background:var(--surface)}
@media(max-width:700px){.map-statistics-world-map-card .world-map-controls{position:static;padding:8px;gap:4px}.map-statistics-world-map-card .world-map-controls button{padding:6px 8px;white-space:nowrap}.map-statistics-world-map-card .world-map-controls span{padding:4px}}
.map-statistics-popularity .table-wrap th{white-space:normal;overflow-wrap:normal}
@media(max-width:700px){.world-map-controls button{min-width:44px;min-height:44px}}
@media(max-width:700px){
  .filter-clear{width:100%;min-height:44px}
  .system-health-row>.disclosure-body{padding:0 0 8px}
}
/* Mobile card spacing belongs to the containing layout, not both grid and card. */
@media(max-width:700px){
  .dashboard{--admin-mobile-card-gap:12px}
  main.overview-page{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--admin-mobile-card-gap)}
  .overview-page>.overview-heading{margin:0 0 4px}
  .overview-page>.overview-panel{margin:0}
  .overview-primary-grid>.overview-panel{margin:0}
  .overview-primary-grid,
  .admin-kpi-grid,.installation-kpis,.model-statistics,.diagnostic-model-metrics,
  .provider-metrics,.system-health-list,
  .provider-dashboard-grid,.model-information-columns{gap:var(--admin-mobile-card-gap)}
  .dashboard>.provider-card,.dashboard>.overview-panel,.dashboard>.model-page-section,
  .dashboard>.map-statistics-coverage-layout,.dashboard>.model-information-columns{margin-top:var(--admin-mobile-card-gap)}
  .overview-page>.overview-panel{margin-top:0}
  .provider-dashboard-grid>.provider-card{margin-top:0}
  .dashboard>.diagnostic-model-metrics,.dashboard>.provider-metrics,
  .dashboard>.admin-summary-strip{margin-bottom:var(--admin-mobile-card-gap)}
  .device-filter-bar{margin-bottom:var(--admin-mobile-card-gap)}
}
/* Information hierarchy: summaries first, complete evidence on demand. */
.identity-outcome{padding:16px;background:var(--off-white);border-radius:12px;margin:12px 0}
.identity-outcome h3{margin:0 0 8px;font-size:16px}.identity-outcome p{margin:4px 0}
.identity-candidate{border-top:1px solid var(--border);padding:8px 0}.identity-candidate>summary{min-height:40px;display:list-item;font-weight:600}
.identity-technical-evidence .identity-summary{font-size:13px}.identity-technical-evidence h4{font-size:14px;overflow-wrap:anywhere}
.identity-checks-table{font-size:13px}.identity-checks-table td{overflow-wrap:anywhere}
.diagnostic-id code{overflow-wrap:anywhere}
.identity-source-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.identity-source-form label{display:flex;flex-direction:column;gap:6px}.identity-source-form button{justify-self:start;grid-column:1/-1}.identity-source-form output{padding:10px 0;overflow-wrap:anywhere}
.overview-activity-item:has(>.download-history){display:block}
.identification-page{max-width:1200px}.identification-page h1{text-wrap:balance}.identification-page summary{cursor:pointer;min-height:44px;align-content:center}.identification-workspace{max-width:900px}.identification-workspace h2{margin-block:20px 12px;font-size:24px}.identification-workspace h3{margin:0 0 7px;font-size:16px;line-height:1.4}.identification-workspace h4{margin:0 0 8px;font-size:14px}.identification-workspace p{max-width:75ch;line-height:1.5}.identification-search{display:flex;align-items:flex-end;gap:12px;margin-block:20px}.identification-search label{display:grid;gap:8px;flex:1;min-width:0;font-weight:600}.identification-search input{width:100%;min-width:0}.identification-page :is(input,textarea)::placeholder{color:var(--secondary);opacity:1}.identification-choice{display:flex;justify-content:space-between;align-items:center;gap:20px;min-height:70px;padding:14px 4px;border-top:1px solid var(--border);text-decoration:none;color:inherit}.identification-choice-title{display:grid;gap:4px;min-width:0}.identification-choice-title>span{font-size:13px;color:var(--secondary)}.identification-choice:hover strong{text-decoration:underline}.identification-badges{display:flex;flex-wrap:wrap;gap:6px}.identification-page .identification-badge{display:inline-flex!important;align-items:center;gap:5px;max-width:100%;margin:0!important;padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:12px;font-weight:600;line-height:1.4}.identification-page .identification-badge>span{display:inline;margin:0;color:inherit}.identification-page .identification-approved{color:var(--status-success-text);background:var(--status-success-surface);border-color:var(--status-success-border)}.identification-page .identification-rejected{color:var(--status-error-text);background:var(--status-error-surface);border-color:var(--status-error-border)}.identification-page :is(.identification-pending,.identification-missing){color:var(--status-tested-text);background:var(--status-tested-surface);border-color:var(--status-tested-border)}.identification-workspace .identity-mappings{display:grid;gap:18px;margin-top:18px;padding:0}.identification-workspace .identity-mapping-source{display:grid;gap:18px;padding:0 0 20px;border-bottom:1px solid var(--border)}.identification-step{min-width:0}.identification-reported-name{display:block;font-size:16px;line-height:1.45}.identification-source-link{margin-top:7px}.identification-source-unavailable{color:var(--secondary);font-size:13px}.identification-match{display:grid;gap:4px}.identification-match>span{color:var(--secondary);font-size:13px}.identification-other-models ul{display:grid;gap:6px;margin:0;padding:0;list-style:none}.identification-other-models li{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:7px 0;border-top:1px solid var(--border)}.identification-other-models li>span{color:var(--secondary);font-size:12px}.identification-confirm{padding:16px;border-radius:12px;background:var(--surface-muted)}.identification-existing-decision{margin:0 0 12px;font-size:13px}.identification-workspace .identity-mapping-review{display:grid;grid-template-columns:1fr;gap:12px}.identification-workspace .identity-mapping-review label{display:grid;gap:6px;font-weight:600}.identification-workspace .identity-mapping-review textarea{width:100%;min-width:0;font:inherit}.identification-decision-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.identification-decision-actions button{min-height:44px}.identity-mapping-review .identification-decision-actions button.secondary-button{color:var(--interactive);background:var(--surface);border:1px solid var(--border)}.identity-mapping-review .identification-decision-actions button.secondary-button:hover{background:var(--surface-muted)}.identification-workspace .admin-action-status:empty{display:none}.identification-workspace .admin-action-status{margin:0;color:var(--graphite);font-size:13px}.identification-workspace .admin-action-status[data-error="true"]{color:var(--error-text)}.identification-technical{margin-top:0}.identification-technical .disclosure-body{display:grid;gap:16px}.identification-technical .disclosure-body>section{padding-top:16px;border-top:1px solid var(--border)}.identification-technical .model-information-list{margin:0}.identification-technical ul{margin:8px 0 0;padding-inline-start:20px}.identification-model-detail-link{margin-top:2px}.identification-empty{padding-block:20px}.identification-not-found{color:var(--error-text);background:var(--error-surface);padding:16px;border-radius:12px}.identification-page :is(a,button,input,textarea,select,summary):focus-visible{outline:2px solid var(--interactive);outline-offset:3px}.identification-page :is(a,p,strong,dd){overflow-wrap:anywhere}.identification-page .section-link{color:var(--graphite);text-decoration:underline;text-underline-offset:3px}
@media(max-width:760px){.identification-choice{align-items:flex-start;flex-direction:column;gap:10px}.identification-workspace .identity-mappings{gap:16px}.identification-other-models li{align-items:flex-start;flex-direction:column;gap:3px}.identification-confirm{padding:14px}.identification-decision-actions{display:grid;grid-template-columns:1fr}.identification-decision-actions button{width:100%}.identification-search{align-items:stretch;flex-direction:column}.identification-search button{align-self:flex-start}.identification-page :is(input,textarea){font-size:16px!important}.identification-workspace h2{font-size:22px}}

.download-history{margin:0;font-size:13px}.download-history>summary{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 16px;list-style:none;cursor:pointer;min-height:44px;align-content:center}.download-history>summary::-webkit-details-marker{display:none}.download-history>summary .overview-activity-label::before{content:'›';display:inline-block;width:14px;margin-right:4px;color:var(--interactive);transform-origin:5px center}.download-history[open]>summary .overview-activity-label::before{transform:rotate(90deg)}.download-history>summary>time{grid-column:2;grid-row:1 / span 2;align-self:center;color:var(--secondary);font-size:12px;white-space:nowrap}.overview-activity-item .download-history .download-context{grid-column:1;grid-row:2;display:block;margin-left:18px;color:var(--secondary);font-size:12px;font-weight:400;overflow-wrap:anywhere}.download-history>summary:focus-visible{outline:2px solid var(--interactive);outline-offset:3px;border-radius:4px}.download-history[open]>.download-timeline{margin-top:6px;margin-left:18px}.download-elapsed{font-variant-numeric:tabular-nums}@media(max-width:500px){.download-history>summary{gap:3px 8px}.download-history>summary>time{font-size:11px}}

.download-timeline{display:flex;flex-wrap:wrap;gap:8px 16px;list-style:none;padding:0;margin:0 0 4px;font-size:13px}
.download-timeline li{display:flex;align-items:center;flex-wrap:wrap;gap:4px}.download-timeline li+li::before{content:'→';color:var(--secondary);margin-right:8px}
.download-timeline .admin-icon,.download-timeline .download-phase-icon{width:14px;height:14px;flex:none}.download-timeline time{font-size:12px;font-variant-numeric:tabular-nums;position:static}
@media(max-width:700px){.identity-source-form{grid-template-columns:1fr}.identity-candidate>summary,.download-history summary{min-height:44px}}

@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
}

/* One compact geometry for plain and expandable map events. */
.map-activity-row,.map-activity-row:first-child{padding:8px 0;min-width:0}.map-activity-row>.map-activity-copy,.map-activity-row>time{grid-row:1}
.map-activity-row>.map-activity-copy,.map-activity-row .download-history>summary{min-height:44px;align-content:center;row-gap:3px;line-height:1.4}
.map-activity-row>.map-activity-copy{grid-template-columns:minmax(0,1fr)}
.map-activity-row .download-history>summary{padding:0;margin:0;column-gap:10px;font-weight:400}
.map-activity-row .overview-activity-label{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:750;line-height:1.4}
.map-activity-row .overview-activity-label .download-phase-icon{width:14px;height:14px;flex:0 0 14px}
.map-activity-row .download-history>summary .overview-activity-label::before{content:none}
.map-activity-row .download-history>summary .overview-activity-label::after{content:'›';display:inline-block;color:var(--secondary);margin-left:2px;line-height:1;transform-origin:center}
.map-activity-row .download-history[open]>summary .overview-activity-label::after{transform:rotate(90deg)}
.map-activity-row>.map-activity-copy>span:not(.overview-activity-label),.map-activity-row .download-history .download-context{margin:0 0 0 21px;font-size:12px;font-weight:400;line-height:1.4;color:var(--secondary)}
.map-activity-row .download-history[open]>.download-timeline{margin:6px 0 0 21px}
.map-activity-row>time,.map-activity-row .download-history>summary>time{font-size:12px;font-variant-numeric:tabular-nums}
.map-activity-info .overview-activity-label{color:var(--interactive)}
.map-activity-success .overview-activity-label{color:var(--success-text)}
.map-activity-error .overview-activity-label{color:var(--danger)}
.map-activity-warning .overview-activity-label{color:var(--status-tested-text)}
.map-activity-neutral .overview-activity-label{color:var(--secondary)}
@media(max-width:500px){.map-activity-row{grid-template-columns:minmax(0,1fr)}.map-activity-row>time{grid-column:1;grid-row:3;margin-left:21px}.map-activity-row .download-history>summary{grid-template-columns:minmax(0,1fr)}.map-activity-row .download-history>summary>time{grid-column:1;grid-row:3;margin-left:21px}.map-activity-row>.map-activity-copy{grid-row:1}}

/* Map statistics compact summary, popularity views, and table alignment. */
.map-statistics-kpi-panel{margin-top:18px;padding:16px 18px}
.map-statistics-kpi-groups{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}
.map-statistics-kpi-group{min-width:0}
.map-statistics-kpi-group h2{margin:0 0 10px;font-size:16px;line-height:1.25}
.map-statistics-kpi-values{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px}
.map-statistics-kpi-value{min-width:0;padding:0 4px}
.map-statistics-kpi-value.failed{grid-column:1/-1;padding-top:8px;border-top:1px solid color-mix(in srgb,var(--border) 78%,transparent)}
.map-statistics-kpi-value span{display:block;color:var(--secondary);font-size:12px;font-weight:650}
.map-statistics-kpi-value>strong{display:block;margin-top:4px;color:var(--graphite);font:700 24px/1.15 var(--font-brand);font-variant-numeric:tabular-nums}
.map-statistics-kpi-value.failed>strong,.map-statistics-kpi-secondary .map-statistics-kpi-value>strong{font-size:19px}
.map-statistics-kpi-secondary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-column:1/-1;gap:8px 16px;padding-top:8px;border-top:1px solid color-mix(in srgb,var(--border) 78%,transparent)}
.admin-table th.column-number,.admin-table td.column-number,.admin-table th.numeric,.admin-table td.numeric{text-align:right}
.admin-table th.column-status,.admin-table td.column-status{text-align:left}
.admin-table th.column-date,.admin-table td.column-date{text-align:right}
.admin-table .column-status .provider-status{margin-inline:0}
.popularity-search-label{display:block;margin:0 0 6px;color:var(--secondary);font-size:12px;font-weight:650}
.map-statistics-ranking>input{width:100%;min-width:0;margin:0 0 12px}
.map-statistics-ranking .popular-maps-table{min-width:0}
.map-statistics-ranking .popular-map-count{text-align:right!important}
.map-statistics-page>.admin-disclosure,.map-statistics-page>.map-events-card{margin-top:16px}
.map-statistics-trends{margin-top:16px}
@media(max-width:900px){.map-statistics-kpi-groups{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
@media(max-width:700px){.map-statistics-kpi-panel{padding:16px}.map-statistics-kpi-groups{grid-template-columns:1fr;gap:16px}.map-statistics-ranking>input{min-height:44px}}
@media(min-width:761px){
  .diagnostic-list-table :is(th,td).column-number,.diagnostic-list-table :is(th,td).column-date{text-align:right}
  .diagnostic-list-table :is(th,td).column-status{text-align:left}
}
@media(max-width:800px){
  .filter-bar>.results-count{width:auto;flex:1 1 180px;margin-left:0}
  .filter-bar>.filter-clear{width:auto;flex:0 0 auto}
}

/* Admin scrollbars are visually hidden without changing the scroll surface. */
.admin-shell :where(
  .table-wrap,
  .overview-chart-wrap,
  .identity-search-results,
  #admin-menu-panel,
  .admin-section-nav,
  .quick-filter-group,
  .diagnostic-detail-inner,
  .device-dialog-inner,
  .generated-url,
  .device-table-wrap,
  .provider-detail .provider-history-wrap,
  .map-statistics-popularity,
  .audit-technical-details code
){scrollbar-width:none;-ms-overflow-style:none}
.admin-shell :where(
  .table-wrap,
  .overview-chart-wrap,
  .identity-search-results,
  #admin-menu-panel,
  .admin-section-nav,
  .quick-filter-group,
  .diagnostic-detail-inner,
  .device-dialog-inner,
  .generated-url,
  .device-table-wrap,
  .provider-detail .provider-history-wrap,
  .map-statistics-popularity,
  .audit-technical-details code
)::-webkit-scrollbar{display:none;width:0;height:0}

/* Shared KPI and error-counter presentation across the operational views. */
.admin-kpi-panel{display:block;margin-top:0;margin-bottom:0}
.overview-page>.admin-kpi-panel{margin-top:16px}
.admin-kpi-panel .map-statistics-kpi-groups{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.admin-kpi-panel .map-statistics-kpi-values{gap:8px 16px}
.admin-kpi-panel .map-statistics-kpi-value{display:block;min-width:0}
.map-statistics-kpi-value.failed>.admin-error-counter{font-size:19px}
.overview-page>.heading-row+.overview-panel{margin-top:0}
.overview-page>.overview-panel{margin-top:16px}
.overview-attention-item{padding-block:6px}
.overview-primary-grid{gap:16px;margin-top:16px}
.overview-activity-panel{margin-top:16px}
.overview-activity-device{display:block;min-width:0;overflow-wrap:anywhere;color:var(--secondary);font-size:11px;text-decoration:none;white-space:normal}
.overview-activity-device:hover{text-decoration:underline;text-underline-offset:3px}
.download-history>summary>.overview-activity-device{grid-column:1/-1;margin-top:2px}
.map-activity-row>.overview-activity-device{grid-column:1;grid-row:3;margin-left:21px}.map-activity-row>time{grid-row:1/span 3}
@media(max-width:500px){.map-activity-row:has(>.overview-activity-device)>time{grid-row:4}}
.overview-chart-download-success{fill:var(--interactive);background:var(--interactive)}
.overview-chart-download-failed{fill:var(--danger);background:var(--danger)}
.overview-trend-chart polyline.overview-chart-line{fill:none}
.admin-kpi-panel .installation-kpi-groups{grid-template-columns:minmax(0,1fr)}
.admin-kpi-panel .provider-kpi-values{grid-template-columns:repeat(3,minmax(0,1fr))}
.admin-kpi-panel .installation-kpi-values{grid-template-columns:repeat(5,minmax(0,1fr))}
.admin-kpi-panel.model-statistics .model-kpi-groups{grid-template-columns:minmax(0,1fr)}
.admin-kpi-panel.model-statistics .model-activity-kpi-group{border-top:1px solid var(--border);padding-top:14px}
.admin-kpi-panel.model-statistics+.model-review-alert{margin-top:16px}
.diagnostic-actions-grid>form.diagnostic-action-form{display:flex;flex-direction:column}
.diagnostic-actions-grid>form.diagnostic-action-form>button[type="submit"],.diagnostic-actions-grid>form.identity-review-form>.identity-review-actions{margin-top:auto}
.diagnostic-actions-grid .admin-action-status:empty{display:none}

.admin-kpi-panel.model-statistics .timestamp-metric>strong{font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line)}
.dashboard>.heading-row{margin-bottom:20px}
.dashboard>.admin-summary-strip{margin-bottom:20px}
.system-health-page>#health-filters{margin-bottom:16px}
.system-health-page .system-health-healthy{margin-top:16px}
.system-health-page .heading-row+.filter-bar{margin-top:0}
.system-health-healthy>.disclosure-body{padding-top:12px}
.provider-table-wrap td.column-status .table-secondary{display:block;min-width:0;overflow-wrap:anywhere;white-space:normal}
.provider-detail .provider-action-bar{margin-bottom:12px}
.provider-detail .provider-state-grid{margin-top:4px}
.map-statistics-page>#map-statistics-metrics{margin-bottom:20px}
.map-statistics-page>.map-statistics-coverage-layout{margin-top:16px}
.installation-kpis+.evidence-section{margin-top:16px}
.device-summary-sync{font-size:var(--admin-type-helper-size)}
.admin-error-counter{color:var(--graphite)!important;font:inherit;font-variant-numeric:tabular-nums}
.admin-error-counter.is-positive{color:var(--danger)!important}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:0;min-height:0;padding:0;border:0;border-radius:0;color:inherit;font-weight:inherit;text-decoration:none}
.error-count:hover .admin-error-counter,.error-count:focus-visible .admin-error-counter{text-decoration:underline;text-underline-offset:3px}
.admin-table th.column-number>button,.admin-table th.column-number>.device-sort-button{justify-content:flex-end;text-align:end}
.admin-table th.column-status>button,.admin-table th.column-status>.device-sort-button{justify-content:center;text-align:center}
.admin-table th.column-date>button,.admin-table th.column-date>.device-sort-button{justify-content:flex-end;text-align:end}
.admin-table td.column-number,.admin-table th.column-number{font-variant-numeric:tabular-nums}
@media(min-width:761px){.evidence-table-wrap th.column-number,.evidence-table-wrap td.column-number,.evidence-table-wrap th.column-date,.evidence-table-wrap td.column-date{text-align:right!important}.evidence-table-wrap th.column-number>.device-sort-button,.evidence-table-wrap th.column-date>.device-sort-button{width:100%;justify-content:flex-end;text-align:end}.evidence-table-wrap th.column-status,.evidence-table-wrap td.column-status{text-align:left}.evidence-table-wrap th.column-status>.device-sort-button{justify-content:flex-start;text-align:start}.evidence-table-wrap .column-status .status-badge{margin-inline:0}.evidence-table-wrap td.column-date,.evidence-table-wrap td.column-date .admin-timestamp{white-space:nowrap}}
.device-table-wrap th.column-number>.device-sort-button,.device-sticky-header th.column-number>.device-sort-button{width:100%}
.device-table-wrap th.column-status>.device-sort-button,.device-sticky-header th.column-status>.device-sort-button{width:100%}
.device-table-wrap th.column-date>.device-sort-button,.device-sticky-header th.column-date>.device-sort-button{width:100%}
@media(max-width:900px){.admin-kpi-panel .installation-kpi-values{grid-template-columns:repeat(3,minmax(0,1fr))}.admin-kpi-panel.model-statistics .model-kpi-groups{grid-template-columns:1fr}.admin-kpi-panel.model-statistics .model-activity-kpi-group{border-top:1px solid var(--border);border-left:0;padding:16px 0 0}}
@media(max-width:700px){.admin-kpi-panel{padding:16px}.admin-kpi-panel .map-statistics-kpi-groups{grid-template-columns:1fr;gap:16px}.admin-kpi-panel .installation-kpi-values{grid-template-columns:repeat(2,minmax(0,1fr))}.admin-kpi-panel.model-statistics .model-activity-kpi-group{padding-top:12px}}
@media(max-width:420px){.admin-kpi-panel .installation-kpi-values{grid-template-columns:1fr}}

/* Identity Review is a compact fact summary, not a repeated evidence form. */
.identity-review-form{grid-column:auto}
.identity-picker-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.identity-picker-heading h4{margin:0}
.identity-reported-device{margin:0 0 4px;font-size:14px}
.identity-reported-also{margin:0 0 12px;color:var(--secondary);font-size:12px;overflow-wrap:anywhere}
.identity-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0}
.identity-fact{min-width:0;padding:10px 11px;border:1px solid var(--border);border-radius:10px;background:var(--surface)}
.identity-fact-heading{display:flex;align-items:center;gap:6px;color:var(--secondary);font-size:11px;font-weight:700}
.identity-fact-icon{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;font-size:12px;font-weight:800}
.identity-fact strong{display:block;margin-top:5px;overflow-wrap:anywhere;font-size:13px;line-height:1.35}
.identity-fact small{display:block;margin-top:5px;color:var(--secondary);font-size:10px}
.identity-fact-match{border-color:var(--status-success-border);background:var(--status-success-surface)}
.identity-fact-match .identity-fact-icon{background:var(--status-success-border);color:var(--status-success-text)}
.identity-fact-conflict{border-color:var(--status-error-border);background:var(--status-error-surface)}
.identity-fact-conflict .identity-fact-icon{background:var(--status-error-border);color:var(--status-error-text)}
.identity-fact-missing{border-color:var(--border);background:var(--surface-muted)}
.identity-fact-missing .identity-fact-icon{background:var(--surface);color:var(--secondary)}
.identity-selected-model{display:grid;gap:3px;margin-top:12px;padding:12px 14px;border-left:3px solid var(--interactive);background:var(--surface-muted)}
.identity-selected-model strong{overflow-wrap:anywhere}.identity-selected-model small{color:var(--secondary);font-size:11px}
.identity-picker{margin-top:10px}.identity-picker[hidden]{display:none}
.identity-search-results{display:grid;gap:4px;max-height:260px;margin-top:6px;overflow:auto;padding:4px;border:1px solid var(--border);border-radius:9px;background:var(--surface)}
.identity-picker-option{display:block;width:100%;min-height:38px;margin:0;padding:8px 10px;border:0;border-radius:6px;background:transparent;color:var(--graphite);font:inherit;font-size:12px;text-align:left;white-space:normal;overflow-wrap:anywhere}
.identity-picker-option:hover,.identity-picker-option:focus-visible{background:var(--surface-muted);outline:2px solid color-mix(in srgb,var(--interactive) 55%,transparent);outline-offset:-2px}
.identity-picker-empty{margin:8px;color:var(--secondary);font-size:12px}
.identity-review-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.identity-review-actions button[disabled]{opacity:.55;cursor:not-allowed}
.identity-conflict-warning{margin:10px 0;padding:9px 11px;border:1px solid var(--status-error-border);border-radius:8px;background:var(--status-error-surface);color:var(--status-error-text);font-size:12px;overflow-wrap:anywhere}
@media(max-width:700px){.identity-facts{grid-template-columns:repeat(2,minmax(0,1fr))}.identity-review-actions{display:grid;grid-template-columns:1fr}.identity-review-actions button{width:100%;min-height:44px}}
@media(max-width:430px){.identity-facts{grid-template-columns:1fr}}
"""


ADMIN_STYLES += """
.table-wrap td[colspan]{grid-column:1/-1;text-align:center!important;white-space:normal;padding:24px 14px}
.table-wrap td[colspan]::before{display:none!important}
.admin-disclosure:not(.filter-disclosure)>summary:hover{background:var(--surface-muted);text-decoration:none}
.admin-disclosure:not(.filter-disclosure)>.disclosure-body{margin:0;padding:0 14px 14px}
.model-information-columns>details{padding:0}
.model-information-columns>details>*:not(summary){margin:0 14px 14px}
.provider-card:has(>.admin-disclosure){padding:0}
.provider-card:has(>.admin-disclosure)>:not(details){margin:14px}
details.provider-card.admin-disclosure{padding:0}
details.provider-card.admin-disclosure>*:not(summary){margin:0 14px 14px}
.system-health-row[hidden]{display:none}
.model-administration>.administration-grid{padding:0 14px 14px}
.map-statistics-provider-table .admin-table{table-layout:fixed;width:100%;min-width:880px}
.map-statistics-provider-table .admin-table th{white-space:normal;overflow-wrap:normal}
.map-statistics-provider-table .admin-table th:first-child{width:15%}
.map-statistics-provider-table .admin-table th,.map-statistics-provider-table .admin-table td{padding-inline:7px}
.map-statistics-provider-table .admin-table td{white-space:normal;overflow-wrap:anywhere}
.map-statistics-provider-table .admin-table .column-date{width:142px;overflow-wrap:normal;white-space:nowrap}
.overview-composition-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-areas:'attention activity' 'downloads activity';align-items:start;gap:16px;margin-top:16px}
.overview-composition-grid>.overview-panel{min-width:0;margin:0}.overview-composition-grid>.overview-attention-panel{grid-area:attention}.overview-composition-grid>.overview-activity-panel{grid-area:activity}.overview-composition-grid>.overview-download-panel{grid-area:downloads}
.overview-heading+.overview-primary-grid{margin-top:0}
.metric-scope{color:var(--secondary);font-size:11px;font-weight:650;line-height:1.3;white-space:nowrap}
.metric-scope{margin-left:5px}
.installation-failed-value{color:var(--danger)!important}
.overview-activity-list{min-height:0;max-block-size:350px;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-inline-end:6px}
.map-activity-row>time{grid-row:1}
.map-activity-row:has(>.overview-activity-device)>time{grid-row:1/span 3}
@media(max-width:500px){.overview-activity-item{grid-template-columns:minmax(0,1fr)}.overview-activity-item>time,.map-activity-row:has(>.overview-activity-device)>time{grid-column:1;grid-row:auto;margin-left:21px}}
.model-evidence-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:16px}
.model-evidence-summary,.model-evidence-history{min-width:0}
.model-evidence-history>.model-page-section{margin-top:0}
.diagnostic-secondary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:16px;margin-top:16px}
.diagnostic-secondary-grid>.diagnostic-secondary-disclosure{min-width:0;margin:0}
@media(min-width:901px){
  .model-evidence-history .table-wrap:has(.mobile-record-table){border:0;background:transparent;overflow:visible;border-radius:0}
  .model-evidence-history table.mobile-record-table{display:block;min-width:0!important;width:100%;border:0;table-layout:auto}
  .model-evidence-history .mobile-record-table colgroup,.model-evidence-history .mobile-record-table thead{display:none}
  .model-evidence-history .mobile-record-table tbody{display:grid;width:100%;gap:12px}
  .model-evidence-history .mobile-record-table tbody tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;min-width:0}
  .model-evidence-history .mobile-record-table tbody td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;text-align:left!important;white-space:normal!important;overflow-wrap:anywhere;font-size:13px}
  .model-evidence-history .mobile-record-table tbody td::before{content:attr(data-label);display:block;margin-bottom:5px;color:var(--secondary);font-size:11px;line-height:1.35;font-weight:600}
  .model-evidence-history .mobile-record-table tbody td:first-child,.model-evidence-history .mobile-record-table tbody td:has(button){grid-column:1/-1}
  .model-evidence-history .mobile-record-table td button{width:100%;min-height:44px}
}
@media(max-width:900px){.overview-composition-grid{grid-template-columns:minmax(0,1fr);grid-template-areas:'attention' 'activity' 'downloads'}.model-evidence-grid{grid-template-columns:minmax(0,1fr)}.diagnostic-secondary-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:760px){
  .admin-section-nav{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%}
  .admin-nav-group{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%}
  .admin-section-nav a,.admin-nav>a,.admin-nav .link-button{display:flex;align-items:center;justify-content:flex-start;min-height:44px;width:100%;padding:10px;font-size:14px}
  .admin-section-nav>.admin-tools-menu{width:100%}
  .admin-section-nav details>summary{width:100%;min-height:44px;padding:8px 10px}
  .admin-tools-popover{position:static;min-width:0;margin-top:4px}
  .admin-nav{width:100%;display:flex;flex-direction:column;align-items:stretch;gap:4px;margin:8px 0 0;padding-top:8px;border-top:1px solid var(--border)}
  .admin-nav .timezone-control{width:100%}.timezone-control select{width:100%;max-width:none;font-size:16px}
  .admin-nav form{width:100%;margin:0}.admin-nav button{min-height:44px;width:100%;text-align:left}.admin-nav .admin-mobile-website{display:flex}
}
.disclosure-meta{color:var(--secondary);font-weight:400}
.provider-state-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.provider-state-grid>.provider-card{min-width:0}
@media(max-width:700px){.provider-state-grid{grid-template-columns:minmax(0,1fr)}.mobile-record-table td[colspan]{display:block!important;width:100%}}
"""

def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _success(message: str | None) -> str:
    return f"<p class='success'>{html.escape(message)}</p>" if message else ""


def _layout(title: str, content: str, *, sections: dict[str, Any] | None = None, revisions: dict[str, str] | None = None) -> bytes:
    if 'id="main-content"' in content or "id='main-content'" in content:
        revisions = revisions if revisions is not None else section_revisions(sections or {})
        revision = html.escape(json.dumps(revisions, sort_keys=True), quote=True)
        content = re.sub(r'(<main\b)', lambda match: match[0] + f' data-admin-revisions="{revision}"', content, count=1)
        content += f"<script>{_admin_freshness_script()}{_admin_mobile_script()}{_admin_filter_clear_script()}{_admin_disclosure_script()}</script>"
    content = content.replace(
        "<script>", f"<script nonce=\"{_ADMIN_NONCE_PLACEHOLDER}\">"
    )
    timezone_script = _admin_timezone_script()
    content = f"{content}<script>{timezone_script}</script>"
    content = content.replace(
        "<script>", f"<script nonce=\"{_ADMIN_NONCE_PLACEHOLDER}\">"
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>{ADMIN_STYLES}</style></head><body class="admin-shell">{content}</body></html>""".encode("utf-8")


def _admin_disclosure_script() -> str:
    return r"""(() => {
      const reveal = () => {
        let id;
        try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
        if (!id) return;
        const target = document.getElementById(id);
        if (!target) return;
        let node = target;
        while (node) { if (node.tagName === 'DETAILS') node.open = true; node = node.parentElement; }
        target.scrollIntoView({block:'start'});
      };
      window.addEventListener('hashchange', reveal);
      document.addEventListener('click', (event) => {
        const anchor = event.target.closest('a[href^="#"]');
        if (anchor && anchor.hash === location.hash) reveal();
      });
      reveal();
    })();"""


def _admin_mobile_script() -> str:
    return r"""(() => {
      const narrow = matchMedia('(max-width: 760px)');
      const header = document.querySelector('.admin-topbar');
      const toggle = document.querySelector('#admin-menu-toggle');
      const panel = document.querySelector('#admin-menu-panel');
      if (header && toggle && panel) {
        header.classList.add('admin-mobile-ready');
        const close = (focus = false) => {
          toggle.setAttribute('aria-expanded', 'false');
          panel.hidden = narrow.matches;
          if (focus) toggle.focus();
        };
        const adapt = () => { toggle.hidden = !narrow.matches; close(); };
        toggle.addEventListener('click', () => {
          const open = toggle.getAttribute('aria-expanded') !== 'true';
          toggle.setAttribute('aria-expanded', String(open)); panel.hidden = !open;
        });
        document.addEventListener('keydown', event => {
          if (event.key === 'Escape' && narrow.matches && !panel.hidden) close(true);
        });
        document.addEventListener('click', event => {
          if (narrow.matches && !header.contains(event.target)) close();
        });
        document.addEventListener('focusin', event => { if (narrow.matches && !header.contains(event.target)) close(); });
        panel.addEventListener('click', event => { if (event.target.closest('a')) close(); });
        narrow.addEventListener('change', adapt); adapt();
      }
      const forms = document.querySelectorAll('#evidence-filters, #device-filters');
      forms.forEach(form => {
        const labels = [...form.children].filter(e => e.tagName === 'LABEL' && !e.classList.contains('filter-search'));
        if (!labels.length) return;
        const extra = document.createElement('div'); extra.className = 'mobile-filter-options'; extra.id = form.id + '-extra';
        const button = document.createElement('button'); button.type = 'button'; button.className = 'mobile-filter-toggle secondary-button';
        button.textContent = 'Filters and sorting'; button.setAttribute('aria-controls', extra.id);
        form.insertBefore(button, labels[0]); form.insertBefore(extra, labels[0]); labels.forEach(label => extra.append(label));
        const adapt = () => { extra.hidden = narrow.matches; button.hidden = !narrow.matches; button.setAttribute('aria-expanded', 'false'); };
        button.addEventListener('click', () => { extra.hidden = !extra.hidden; button.setAttribute('aria-expanded', String(!extra.hidden)); });
        const update = () => {
          const active = [...extra.querySelectorAll('select')].filter(control => !control.id.includes('sort') && control.value !== 'all').length;
          button.textContent = active ? `Filters and sorting · ${active} active` : 'Filters and sorting';
        };
        form.addEventListener('change', update); update();
        narrow.addEventListener('change', adapt); adapt();
      });
      const labelTables = () => {
        document.querySelectorAll('main table').forEach(table => {
          if (table.closest('.device-sticky-header')) return;
          const headers = [...table.querySelectorAll('thead th')];
          if (!headers.length) return;
          table.classList.add('mobile-record-table'); table.setAttribute('role', 'table');
          table.querySelectorAll('tbody').forEach(body => body.setAttribute('role', 'rowgroup'));
          table.querySelectorAll('tbody tr').forEach(row => {
            if (!row.hasAttribute('role')) row.setAttribute('role', 'row');
            [...row.cells].forEach((cell, i) => {
              if (!cell.dataset.label) cell.dataset.label = cell.colSpan > 1 ? '' : (headers[i]?.getAttribute('aria-label') || headers[i]?.textContent || '').replace(/[↕↑↓]/g, '').trim();
              cell.setAttribute('role', 'cell');
            });
          });
        });
      };
      labelTables();
      const main = document.querySelector('main');
      if (main) new MutationObserver(labelTables).observe(main, {childList:true, subtree:true});
    })();"""


def _admin_filter_clear_script() -> str:
    return r"""(() => {
      document.querySelectorAll('[data-filter-clear]').forEach((button) => {
        button.addEventListener('click', () => {
          const form = button.closest('form');
          if (!form) return;
          form.dispatchEvent(new CustomEvent('terento-admin-clear-filters'));
          form.dispatchEvent(new CustomEvent('change'));
        });
      });
    })();"""


def _admin_freshness_script() -> str:
    return r"""(() => {
      if (!document.querySelector('[data-admin-revisions]') || document.querySelector('#admin-live-update')) return;
      const notice = document.createElement('div');
      notice.id = 'admin-live-update'; notice.className = 'admin-live-update';
      notice.setAttribute('role', 'status'); notice.hidden = true;
      const message = document.createElement('span');
      const refresh = document.createElement('button');
      refresh.type = 'button'; refresh.className = 'secondary-button'; refresh.textContent = 'Refresh';
      notice.append(message, refresh); document.querySelector('.admin-topbar')?.after(notice);
      let dirty = false, generation = 0, running = false, pending = null;
      const read = node => JSON.parse(node?.dataset.adminRevisions || '{}');
      const update = () => {
        if (!pending) { notice.hidden = true; return; }
        const shown = read(document.querySelector('[data-admin-revisions]'));
        notice.hidden = !Object.keys(pending).some(key => pending[key] !== shown[key]);
        message.textContent = 'New activity is available.';
      };
      document.addEventListener('input', event => {
        if (event.target.closest('form[method="post"]')) dirty = true;
      });
      document.addEventListener('change', event => {
        if (event.target.closest('form[method="post"]')) dirty = true;
      });
      refresh.addEventListener('click', () => {
        if (!dirty || window.confirm('Refresh and discard unsaved edits?')) window.location.reload();
      });
      window.addEventListener('terento-admin-content-changed', () => { generation++; pending = null; update(); });
      window.addEventListener('terento-admin-sections-rendered', event => {
        generation++;
        const current = document.querySelector('[data-admin-revisions]');
        current.dataset.adminRevisions = JSON.stringify({...read(current), ...event.detail});
        update();
      });
      window.addEventListener('popstate', () => { generation++; });
      const check = async () => {
        if (document.hidden || running) return;
        const current = document.querySelector('[data-admin-revisions]');
        if (!current || current.getAttribute('aria-busy') === 'true') return;
        running = true;
        const url = window.location.href, started = generation;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        const stale = () => document.hidden || generation !== started || window.location.href !== url || document.querySelector('[data-admin-revisions]') !== current;
        try {
          const response = await fetch(url, {credentials:'same-origin', cache:'no-store', signal:controller.signal});
          if (stale()) return;
          if ((response.redirected && new URL(response.url).pathname === '/admin/login') || response.status === 401 || response.status === 403) {
            message.textContent = 'Your session expired. Refresh to sign in.'; notice.hidden = false; return;
          }
          if (!response.ok) throw new Error('Unavailable');
          const next = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('[data-admin-revisions]');
          if (stale()) return;
          if (!next) throw new Error('Missing snapshot');
          pending = read(next); update();
        } catch (_) {
          if (!stale()) { message.textContent = 'Live check unavailable. Try Refresh.'; notice.hidden = false; }
        } finally { clearTimeout(timeout); running = false; }
      };
      setInterval(check, 60000);
      document.addEventListener('visibilitychange', check);
    })();"""


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

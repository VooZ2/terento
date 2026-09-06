from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
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
from .map_capability import classify_map_capable
from .admin_world_map import WORLD_MAP_COUNTRY_ALIASES, WORLD_MAP_SVG
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
    return calculate_compatibility_status(
        successful_install_count=int(row.get("successful_install_count") or 0),
        recognized_map_capable_evidence=(
            row.get("recognized_map_capable_evidence") is True
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


def _normalise_variant(value: Any) -> str:
    raw = str(value or "").strip()[:256]
    if not raw:
        return "—"
    normalized = re.sub(
        r"\b(\d{2,3})\s*mm\b",
        lambda match: f"{match.group(1)} mm",
        raw,
        flags=re.IGNORECASE,
    )
    display_names = {"amoled": "AMOLED", "solar": "Solar", "microled": "MicroLED"}
    normalized = re.sub(
        r"\b(AMOLED|Solar|MicroLED)\b",
        lambda match: display_names[match.group(1).lower()],
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = ", ".join(part.strip() for part in normalized.split(","))
    return " ".join(normalized.split())


def _identity_comparison_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "")).casefold()
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _identity_parts(row: dict[str, Any]) -> tuple[str, str, str]:
    model = str(row.get("model") or "—").strip()
    identity = str(row.get("compatibility_identity") or model).strip()
    variant = str(row.get("variant") or "").strip()
    case_size = row.get("case_size_mm")

    if "·" in identity:
        base, suffix = (part.strip() for part in identity.split("·", 1))
        if base:
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
    return model or "—", _normalise_variant(variant), identity


def _operation_key(result: dict[str, Any]) -> str:
    return str(
        result.get("operation_key")
        or result.get("operation_id")
        or result.get("event_id")
        or ""
    ).strip()


def _group_operations(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        key = _operation_key(event)
        if key:
            grouped.setdefault(key, []).append(event)
    for results in grouped.values():
        results.sort(key=lambda item: int(item.get("map_result_index") or 0))
    return grouped


def _identity_is_pending(results: list[dict[str, Any]]) -> bool:
    if not results:
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
        key = _operation_key(event)
        if identity and key:
            grouped.setdefault(identity, {}).setdefault(key, []).append(event)
    resolved_grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in resolved_events or []:
        identity = _identity_group_key(event)
        key = _operation_key(event)
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
    elif normalized in {"IDENTITY_PENDING", "UNRESOLVED", "PENDING"}:
        state, label = "IDENTITY_PENDING", "Identity pending"
    else:
        state, label = "OPEN", "Open"
    return f"<span class='diagnostic-state diagnostic-state-{state.lower()}'>{label}</span>"


def _github_issue_chip(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.fullmatch(r"#?(\d+)", raw)
    if match:
        issue_number = match.group(1)
        return f"<a class='diagnostic-chip github-issue' href='https://github.com/VooZ2/terento/issues/{issue_number}' target='_blank' rel='noreferrer'>Issue #{issue_number}</a>"
    return f"<span class='diagnostic-chip'>GitHub {html.escape(raw)}</span>"


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
        "SUCCEEDED": "Succeeded",
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


def _diagnostic_technical_details(result: dict[str, Any], result_number: int) -> str:
    fields: list[tuple[str, Any]] = []
    for label, key in (
        ("Raw MTP model", "raw_mtp_model"),
        ("Local identity", "identity_resolution_code"),
        ("Native code", "native_failure_code"),
        ("Transfer progress", "transfer_progress_bucket"),
        ("Map result", "map_result_index"),
        ("Selected maps", "selected_map_count"),
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
        f"<summary>Technical details · map result {result_number}</summary>"
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
    review = user.get("admin_review_summary") or {}
    installation_issues = int(review.get("installationIssues") or 0)
    identity_pending = int(review.get("identityPending") or 0)
    ready_to_publish = int(review.get("readyToPublish") or 0)
    review_total = int(review.get("total") or (
        installation_issues + identity_pending + ready_to_publish
    ))
    review_menu = f"""<details class="needs-review-menu">
        <summary aria-label="Needs review: {review_total}">Needs review <span class="needs-review-count">{review_total}</span></summary>
        <div class="needs-review-popover" role="group" aria-label="Review queue">
          <a href="/admin/installations?state=open"><span>Installation issues</span><strong>{installation_issues}</strong></a>
          <a href="/admin/installations?state=identity-pending"><span>Identity pending</span><strong>{identity_pending}</strong></a>
          <a href="/admin/devices?review=publication"><span>Ready to publish</span><strong>{ready_to_publish}</strong></a>
        </div>
      </details>""" if review_total else ""
    return f"""<header class="admin-topbar"><div class="admin-topbar-inner">
      <div class="admin-header-zone admin-header-left">{_admin_brand(show_badge=False)}<span class="admin-badge">Admin area</span><a class="admin-website-link" href="https://terento.app/" target="_blank" rel="noopener noreferrer" aria-label="Open Terento website in a new tab">Website <span aria-hidden="true">↗</span></a></div>
      <a class="admin-mobile-review" href="/admin#overview-attention-title" aria-label="Needs attention: {review_total}">Review <span class="needs-review-count">{review_total}</span></a>
      <button id="admin-menu-toggle" class="secondary-button" type="button" aria-controls="admin-menu-panel" aria-expanded="false" hidden>Menu</button>
      <div id="admin-menu-panel"><nav class="admin-section-nav" aria-label="Admin sections"><a{overview_class} href="/admin">Overview</a><a{system_health_class} href="/admin/system-health">System health</a><a{evidence_class} href="/admin/installations">Installations</a><a{devices_class} href="/admin/devices">Devices</a><a{providers_class} href="/admin/providers">Providers</a><a{map_statistics_class} href="/admin/map-statistics">Map statistics</a><a{campaign_class} href="/admin/campaign-links">Campaign links</a>{review_menu}</nav>
      <nav class="admin-nav" aria-label="Admin navigation"><label class="timezone-control"><span class="sr-only">Time zone</span><select id="admin-timezone" aria-label="Time zone" title="Time zone"><option value="browser">Automatic (browser)</option><option value="UTC">UTC</option><option value="Europe/Vilnius">Europe/Vilnius</option><option value="Europe/London">Europe/London</option><option value="Europe/Berlin">Europe/Berlin</option><option value="America/New_York">America/New_York</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="Asia/Tokyo">Asia/Tokyo</option></select></label><a class="admin-user" href="/admin/account" aria-label="Account settings for {username}">{username}</a>
      <form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><button class="link-button" type="submit">Sign out</button></form><a class="admin-mobile-website" href="https://terento.app/" target="_blank" rel="noopener noreferrer">Website ↗</a></nav></div>
    </div></header>"""


def setup_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Create admin account",
        """
        <main class="auth-card" aria-labelledby="auth-title">
          {brand}
          <p class="eyebrow">Admin</p>
          <h1 id="auth-title">Create the first admin account</h1>
          <p class="lede">This one-time setup requires the deployment secret.</p>
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
          <p class="eyebrow">Admin</p>
          <h1 id="auth-title">Sign in</h1>
          <p class="lede">Private installation activity and compatibility evidence for Terento.</p>
          {error}
          <form method="post" action="/admin/login">
            <label>Username<input name="username" autocomplete="username" required></label>
            <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
            <button type="submit">Sign in</button>
          </form>
        </main>
        """.format(error=_error(error), brand=_admin_brand()),
    )


def _overview_failure_reason_label(value: Any) -> str:
    return failure_reason_label(value)


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


def _overview_operation_label(operation: dict[str, Any]) -> tuple[str, str]:
    if operation.get("has_failed"):
        return "Install failed", "failed"
    if operation.get("has_not_started"):
        return "Install not started", "not-started"
    if operation.get("operation_succeeded"):
        return "Install succeeded", "succeeded"
    return "Install operation", "unknown"


def _compatibility_source_label(value: Any) -> str:
    source = str(value or "").strip()
    return {"custom": "Custom", "freizeitkarte": "Freizeitkarte", "opentopomap": "OpenTopoMap"}.get(source.casefold(), source)


def _overview_operation_context(operation: dict[str, Any]) -> str:
    model = str(operation.get("model") or operation.get("compatibility_identity") or "Unknown device").strip()
    variant = _normalise_variant(operation.get("variant"))
    provider = _compatibility_source_label(operation.get("provider"))
    parts = [model]
    if variant != "—" and variant not in model:
        parts.append(variant)
    if provider:
        parts.append(provider)
    return " · ".join(parts)


def _overview_compatibility_activity_row(operation: dict[str, Any]) -> str:
    label, state = _overview_operation_label(operation)
    if str(operation.get("provider") or "").strip().casefold() == "custom":
        label = {
            "succeeded": "Custom installation",
            "failed": "Custom installation failed",
            "not-started": "Custom installation not started",
        }.get(state, "Custom installation")
    href = _overview_operation_href(operation)
    return (
        f"<li class='overview-activity-item overview-activity-{state}'>"
        f"<a href='{html.escape(href, quote=True)}'><span class='overview-activity-label'>{html.escape(label)}</span>"
        f"<span>{html.escape(_overview_operation_context(operation))}</span></a>"
        f"{_timestamp_markup(operation.get('last_occurred_at'))}</li>"
    )


def _overview_operation_href(operation: dict[str, Any]) -> str:
    state = (
        "failed" if operation.get("has_failed")
        else "open" if operation.get("open_error") or operation.get("has_not_started")
        else None
    )
    device_id = str(operation.get("canonical_device_model_id") or "").strip()
    if device_id:
        return _device_detail_url(device_id, origin="installations", state=state, anchor="installations")
    return _diagnostics_url(operation, state=state)


def _overview_attention_item(operation: dict[str, Any]) -> str:
    label, state = _overview_operation_label(operation)
    href = _overview_operation_href(operation)
    reason = _overview_failure_reason_label(operation.get("error_category"))
    if operation.get('identity_pending') and not operation.get('open_error'):
        label, state, reason = 'Identity needs review', 'review', 'Confirm the exact device model'
        href = _diagnostics_url(operation, state='identity-pending')
    return (
        f"<li class='overview-attention-item overview-attention-{state}'>"
        f"<span class='overview-attention-dot' aria-hidden='true'>●</span>"
        f"<div><a href='{html.escape(href, quote=True)}'><strong>{html.escape(label)}</strong></a>"
        f"<span>{html.escape(_overview_operation_context(operation))}</span>"
        f"<small>{html.escape(reason)} · {_timestamp_markup(operation.get('last_occurred_at'))}</small></div>"
        f"<a class='overview-detail-link' href='{html.escape(href, quote=True)}'>Details&nbsp;→</a></li>"
    )


def _overview_provider_attention_item(provider: dict[str, Any]) -> str:
    provider_id = str(provider.get("id") or "").strip()
    name = str(provider.get("name") or provider_id or "Provider")
    health = str(provider.get("health") or "UNKNOWN").upper()
    href = f"/admin/providers/{quote(provider_id, safe='')}"
    return (
        f"<li class='overview-attention-item overview-attention-provider'>"
        f"<span class='overview-attention-dot' aria-hidden='true'>●</span>"
        f"<div><a href='{html.escape(href, quote=True)}'><strong>{html.escape(name)} health {html.escape(health.title())}</strong></a>"
        f"<span>Provider health requires review</span>"
        f"<small>{_timestamp_markup(provider.get('lastHealthCheck'))}</small></div>"
        f"<a class='overview-detail-link' href='{html.escape(href, quote=True)}'>Details&nbsp;→</a></li>"
    )


def _overview_failure_reasons(reasons: list[dict[str, Any]]) -> str:
    if not reasons:
        return "<p class='empty'>No normalized failure categories are available for this period.</p>"
    maximum = max(int(item.get("count") or 0) for item in reasons) or 1
    rows: list[str] = []
    for item in reasons:
        count = int(item.get("count") or 0)
        width = max(4, round(count / maximum * 100))
        label = _overview_failure_reason_label(item.get("reason"))
        rows.append(
            f"<li><span>{html.escape(label)}</span><strong>{count}</strong>"
            f"<span class='overview-bar' role='img' aria-label='{html.escape(label)}: {count}'><i style='width:{width}%'></i></span></li>"
        )
    return "<ul class='overview-reason-list'>" + "".join(rows) + "</ul>"


def _overview_model_activity_item(item: dict[str, Any]) -> str:
    model = str(item.get("model") or item.get("compatibility_identity") or "Unknown device").strip()
    variant = _normalise_variant(item.get("variant"))
    context = " · ".join(part for part in (model, variant if variant != "—" and variant not in model else "") if part)
    operation_count = int(item.get("operation_count") or 0)
    successful = int(item.get("successful_count") or 0)
    failed = int(item.get("failed_count") or 0)
    open_errors = int(item.get("open_error_count") or 0)
    status = "Needs review" if open_errors else ("Failures" if failed else "Active")
    status_class = "failed" if failed or open_errors else "succeeded"
    device_id = str(item.get("canonical_device_model_id") or "").strip()
    href = (
        _device_detail_url(device_id, origin="installations", state="open", anchor="installations")
        if device_id else _diagnostics_url(item)
    )
    result = f"{successful} successful · {failed} failed" if successful or failed else f"{operation_count} operation{'s' if operation_count != 1 else ''}"
    return (
        f"<li class='overview-model-item overview-model-{status_class}'>"
        f"<a href='{html.escape(href, quote=True)}'><strong>{html.escape(context)}</strong>"
        f"<span>{html.escape(result)} · {html.escape(status)}</span></a>"
        f"{_timestamp_markup(item.get('last_occurred_at'))}</li>"
    )


def _overview_model_activity(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p class='overview-empty-state'>No device/model activity in this period.</p>"
    return "<ul class='overview-model-list'>" + "".join(
        _overview_model_activity_item(item) for item in items
    ) + "</ul>"


def _overview_review_item(item: dict[str, Any]) -> str:
    model = str(item.get("model") or item.get("compatibility_identity") or "Unknown device").strip()
    variant = _normalise_variant(item.get("variant"))
    context = " · ".join(part for part in (model, variant if variant != "—" and variant not in model else "") if part)
    review_status = str(item.get("review_status") or "PENDING").upper()
    public_enabled = bool(item.get("public_statistics_enabled"))
    label = "Unpublished" if review_status == "APPROVED" and not public_enabled else "Review required"
    device_id = str(item.get("canonical_device_model_id") or "").strip()
    href = (
        _device_detail_url(device_id, origin="installations")
        if device_id else _diagnostics_url(item)
    )
    return (
        f"<li class='overview-review-item'><a href='{html.escape(href, quote=True)}'>"
        f"<strong>{html.escape(context)}</strong><span>{html.escape(label)}</span></a></li>"
    )


def _overview_review_required(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    return "<ul class='overview-review-list'>" + "".join(
        _overview_review_item(item) for item in items
    ) + "</ul>"


def _overview_review_attention_item(item: dict[str, Any]) -> str:
    model = str(item.get("model") or item.get("compatibility_identity") or "Unknown device").strip()
    variant = _normalise_variant(item.get("variant"))
    context = " · ".join(
        part for part in (model, variant if variant != "—" and variant not in model else "") if part
    )
    review_status = str(item.get("review_status") or "PENDING").upper()
    public_enabled = bool(item.get("public_statistics_enabled"))
    label = "Unpublished" if review_status == "APPROVED" and not public_enabled else "Review required"
    device_id = str(item.get("canonical_device_model_id") or "").strip()
    href = (
        _device_detail_url(device_id, origin="installations")
        if device_id else _diagnostics_url(item)
    )
    return (
        "<li class='overview-attention-item overview-attention-review'>"
        "<span class='overview-attention-dot' aria-hidden='true'>●</span>"
        f"<div><a href='{html.escape(href, quote=True)}'><strong>{html.escape(label)}</strong></a>"
        f"<span>{html.escape(context)}</span>"
        f"<small>{html.escape(review_status.title())} · {_timestamp_markup(item.get('last_evidence'))}</small></div>"
        f"<a class='overview-detail-link' href='{html.escape(href, quote=True)}'>Review&nbsp;→</a></li>"
    )


def _overview_map_event_label(event: dict[str, Any]) -> tuple[str, str]:
    labels = {
        "DOWNLOAD_STARTED": ("Download started", "started"),
        "DOWNLOAD_SUCCEEDED": ("Download completed", "succeeded"),
        "DOWNLOAD_FAILED": ("Download failed", "failed"),
        "INSTALL_SUCCEEDED": ("Install succeeded", "succeeded"),
        "INSTALL_FAILED": ("Install failed", "failed"),
    }
    return labels.get(str(event.get("event_type") or "").upper(), ("Map activity", "unknown"))


def _admin_event_outcome_label(value: Any) -> str:
    """Keep a non-terminal UNKNOWN outcome neutral in admin presentation."""
    normalized = str(value or "").strip().upper()
    if normalized == "UNKNOWN":
        return "—"
    return normalized.title() if normalized else "—"


_ADMIN_REGION_DISPLAY_NAMES = {
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
    "SE": "Sweden",
    "UA": "Ukraine",
}

_ADMIN_REGION_IDENTITY_ALIASES = {
    "AND": "ANDORRA",
    "ANDORRA": "ANDORRA",
    "PRINCIPALITYOFANDORRA": "ANDORRA",
    "LT": "LITHUANIA",
    "LTU": "LITHUANIA",
    "LITHUANIA": "LITHUANIA",
    "REPUBLICOFLITHUANIA": "LITHUANIA",
}


def _admin_region_identity(
    canonical_region_id: Any, country: Any = None, region: Any = None,
) -> str:
    """Return one cross-provider admin geography key from existing metadata."""
    canonical_token = re.sub(
        r"[^A-Za-z0-9]+", "", str(canonical_region_id or "")
    ).upper()
    if canonical_token:
        return _ADMIN_REGION_IDENTITY_ALIASES.get(
            canonical_token, canonical_token,
        )
    country_identity = re.sub(
        r"[^A-Za-z0-9]+", "", _admin_map_display_name(country)
    ).upper() if country else ""
    if country_identity and country_identity != "UNKNOWN":
        return _ADMIN_REGION_IDENTITY_ALIASES.get(
            country_identity, country_identity,
        )
    region_identity = re.sub(
        r"[^A-Za-z0-9]+", "", str(region or "")
    ).upper()
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


def _overview_map_event_context(event: dict[str, Any]) -> str:
    display_name = _admin_map_display_name(
        event.get("display_name")
        or event.get("map_package_name")
        or event.get("map_package_id")
        or event.get("region")
        or "Map",
    )
    region = _admin_map_display_name(event.get("region")) if event.get("region") else ""
    provider = str(event.get("provider_name") or event.get("provider_id") or "").strip()
    parts = [display_name]
    if region and region.casefold() != display_name.casefold():
        parts.append(region)
    if provider:
        parts.append(provider)
    return " · ".join(parts)


def _overview_map_event_href(event: dict[str, Any]) -> str:
    parameters = {
        "eventType": str(event.get("event_type") or ""),
        "provider": str(event.get("provider_id") or ""),
        "map": str(event.get("map_package_id") or ""),
        "region": str(event.get("region") or ""),
    }
    return "/admin/map-statistics?" + urlencode({key: value for key, value in parameters.items() if value})


def _overview_map_activity_row(event: dict[str, Any]) -> str:
    label, state = _overview_map_event_label(event)
    href = _overview_map_event_href(event)
    return (
        f"<li class='overview-activity-item overview-activity-{state}'>"
        f"<a href='{html.escape(href, quote=True)}'><span class='overview-activity-label'>{html.escape(label)}</span>"
        f"<span>{html.escape(_overview_map_event_context(event))}</span></a>"
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
        return parsed.strftime("%H:%M")
    if bucket == "month":
        return parsed.strftime("%b %Y")
    if bucket == "week":
        return "Week of " + parsed.strftime("%d %b")
    return parsed.strftime("%d %b")


def _overview_trend_chart(
    trend: list[dict[str, Any]], bucket: str, time_zone: str = "UTC",
) -> str:
    if not trend:
        return "<p class='overview-empty-state'>No map install operations in this period.</p>"
    values = [
        (max(0, int(item.get("success_count") or 0)), max(0, int(item.get("failed_count") or 0)), max(0, int(item.get("custom_count") or 0)))
        for item in trend
    ]
    maximum = max((sum(series) for series in values), default=1) or 1
    scale_maximum = max(maximum, 3)
    chart_width, chart_height = 720, 260
    left, top, bottom = 10, 10, 30
    plot_height = chart_height - top - bottom
    slot = chart_width / max(len(values), 1)
    bars: list[str] = []
    labels: list[str] = []
    for index, (counts, item) in enumerate(zip(values, trend)):
        center = (index + 0.5) * slot
        active = [(name, label, count) for name, label, count in zip(
            ("success", "failed", "custom"),
            ("Install succeeded", "Install failed", "Custom .img installed"), counts,
        ) if count > 0]
        bar_width = min(44, slot * 0.58)
        x = center - bar_width / 2
        total_height = plot_height * sum(counts) / scale_maximum
        y = top + plot_height
        clip_id = f"overview-bar-clip-{index}"
        bars.append(
            f"<defs><clipPath id='{clip_id}'><rect x='{x:.1f}' "
            f"y='{y - total_height:.1f}' width='{bar_width:.1f}' "
            f"height='{total_height:.1f}' rx='3'></rect></clipPath></defs>"
            f"<g clip-path='url(#{clip_id})'>"
        )
        for name, label, count in active:
            height = plot_height * count / scale_maximum
            y -= height
            title = f"{label}: {count} · {_overview_chart_bucket_label(item.get('bucket'), bucket, time_zone)}"
            bars.append(
                f"<rect class='overview-chart-{name}' x='{x:.1f}' y='{y:.1f}' "
                f"width='{bar_width:.1f}' height='{height:.1f}' tabindex='0' "
                f"role='img' aria-label='{html.escape(title, quote=True)}'>"
                f"<title>{html.escape(title)}</title></rect>"
            )
        bars.append("</g>")
        label_step = max(1, round((len(values) - 1) / 5))
        if len(values) <= 12 or index % label_step == 0 or index == len(values) - 1:
            labels.append(f"<text x='{center:.1f}' y='{chart_height - 8}' text-anchor='middle'>{html.escape(_overview_chart_bucket_label(item.get('bucket'), bucket, time_zone))}</text>")
    return (
        "<div class='overview-chart-wrap'>"
        f"<svg class='overview-trend-chart' viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='Map install operations over time'>"
        f"{''.join(bars)}{''.join(labels)}</svg>"
        "<div class='overview-chart-legend'><span><i class='overview-chart-success'></i>Succeeded</span><span><i class='overview-chart-failed'></i>Failed</span><span><i class='overview-chart-custom'></i>Custom .img</span></div><p class='overview-chart-note'>Custom .img is shown separately; it is not included in map-operation KPI totals.</p></div>"
    )


def _overview_period_script() -> str:
    return r"""(() => {
      let loadingKey = '';
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
        if (current) current.setAttribute('aria-busy', 'true');
        if (select) select.disabled = true;
        try {
          const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'text/html'}});
          if (!response.ok) throw new Error(`Overview refresh failed (${response.status})`);
          const documentNext = new DOMParser().parseFromString(await response.text(), 'text/html');
          const mainNext = documentNext.querySelector('#main-content');
          if (!mainNext) throw new Error('Overview content is unavailable.');
          current?.replaceWith(mainNext);
          window.dispatchEvent(new Event('terento-admin-content-changed'));
          if (push) window.history.pushState({period, timeZone}, '', url);
          else window.history.replaceState({period, timeZone}, '', url);
          window.TerentoAdminTime?.render();
          bind();
        } catch (_) {
          window.location.assign(url);
        } finally {
          loadingKey = '';
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
) -> bytes:
    data = overview.get("data") if isinstance(overview.get("data"), dict) else {}
    compatibility = overview.get("compatibility") if isinstance(overview.get("compatibility"), dict) else {}
    providers = list(overview.get("providers") or [])
    period = str(overview.get("period") or "24h")
    time_zone = str(overview.get("timeZone") or "UTC")
    period_labels = {"24h": "Last 24 hours", "7d": "Last 7 days", "30d": "Last 30 days", "all": "All time"}
    period_options = "".join(
        f"<option value='{value}'{' selected' if value == period else ''}>{label}</option>"
        for value, label in period_labels.items()
    )
    healthy = sum(1 for provider in providers if str(provider.get("health") or "").upper() == "HEALTHY")
    provider_count = len(providers)
    failed_installs = int(data.get("failedInstallCount") or 0)
    completed_installs = int(data.get("completedInstallCount") or 0)
    event_count = int(data.get("eventCount") or 0)
    open_errors = int(compatibility.get("allTimeOpenErrorCount", compatibility.get("openErrorCount")) or 0)
    recent = list(data.get("recentActivity") or [])
    has_map_data = bool(data.get("hasData")) if "hasData" in data else bool(event_count or recent)
    event_metric = lambda value: str(value) if has_map_data else "—"
    compatibility_has_data = bool(compatibility.get("hasData"))
    open_error_metric = lambda value: str(value) if "allTimeOpenErrorCount" in compatibility or compatibility_has_data else "—"
    attention_providers = [
        provider for provider in providers
        if str(provider.get("health") or "UNKNOWN").upper() not in {"HEALTHY", ""}
    ]
    attention_items = ""
    compatibility_attention = [
        item for item in compatibility.get("attention", compatibility.get("recentActivity", []))
        if item.get("open_error") or item.get("identity_pending")
    ]
    model_activity = list(compatibility.get("modelActivity") or [])
    review_required = list(compatibility.get("reviewRequired") or [])
    attention_items += "".join(_overview_attention_item(item) for item in compatibility_attention[:8])
    attention_items += "".join(
        _overview_review_attention_item(item) for item in review_required[:4]
    )
    attention_items += "".join(_overview_provider_attention_item(item) for item in attention_providers[:4])
    if isinstance(overview.get("system"), dict):
        health_cards, _, _ = _system_health_cards(overview["system"])
        attention_items += "".join(
            f"<li class='overview-attention-item overview-attention-review'><span aria-hidden='true'>!</span>"
            f"<div><a href='/admin/system-health'><strong>{html.escape(card['title'])} · {html.escape(card['status'].title())}</strong></a>"
            f"<small>{html.escape(card['reason'])}</small></div><a class='overview-detail-link' href='/admin/system-health'>Review&nbsp;→</a></li>"
            for card in health_cards if card["status"] != "HEALTHY"
        )
    if not attention_items:
        attention_content = "<p class='overview-empty-state'>No issues need attention</p>"
    else:
        attention_content = f"<ul class='overview-attention-list'>{attention_items}</ul>"
    recent_content = (
        "<p class='empty'>No map activity in this period.</p>"
        if not recent else
        "<ul class='overview-activity-list'>" + "".join(_overview_map_activity_row(item) for item in recent) + "</ul>"
    )
    success_rate = _format_rate(data.get("installSuccessRate")) if has_map_data else "—"
    compatibility_attempts = str(compatibility.get("writeStartedCount")) if compatibility_has_data else "—"
    compatibility_variants = str(compatibility.get("variantCount")) if compatibility_has_data else "—"
    compatibility_rate = _format_rate(compatibility.get("evidenceSuccessRate")) if compatibility_has_data else "—"
    map_statistics_href = "/admin/map-statistics"
    map_statistics_href += "?" + urlencode({"period": period})
    failure_href = map_statistics_href + ("&" if "?" in map_statistics_href else "?") + urlencode({"eventType": "INSTALL_FAILED"})
    attention_href = (
        "/admin/installations?state=open" if compatibility_attention else
        "/admin/devices" if review_required else
        "/admin/providers" if attention_providers else map_statistics_href
    )
    failure_reasons = list(compatibility.get("failureReasons") or [])
    compatibility_recent = list(compatibility.get("recentActivity") or [])
    compatibility_recent_content = (
        ""
        if not compatibility_recent else
        "<div class='overview-compatibility-activity' aria-label='Recent compatibility activity'><div class='section-heading'><div><p class='section-kicker'>Latest</p><h3>Recent compatibility activity</h3></div><a class='section-link' href='/admin/installations'>View all&nbsp;→</a></div><ul class='overview-activity-list'>" +
        "".join(_overview_compatibility_activity_row(item) for item in compatibility_recent) +
        "</ul></div>"
    )
    reasons_section = (
        f"<section class='overview-panel' aria-labelledby='overview-reasons-title'><div class='section-heading'><div><p class='section-kicker'>Compatibility evidence</p><h2 id='overview-reasons-title'>Failures by reason</h2></div><span class='overview-info' title='Compatibility evidence only.' aria-label='Compatibility evidence only.'>i</span></div>{_overview_failure_reasons(failure_reasons)}<p class='overview-chart-note'>Compatibility evidence only. Map-operation failure counts are shown above.</p></section>"
        if failure_reasons else ""
    )
    compatibility_summary = (
        f"<details class='overview-panel overview-compatibility-summary admin-disclosure' aria-labelledby='overview-compatibility-title'><summary id='overview-compatibility-title'>Compatibility evidence · details and activity</summary><div class='overview-compatibility-grid'><div><span>Write-started attempts</span><strong>{compatibility_attempts}</strong></div><div><span>Variants</span><strong>{compatibility_variants}</strong></div><div><span>Evidence success</span><strong>{compatibility_rate}</strong></div></div><p class='overview-chart-note'>Device compatibility evidence is not merged with map-operation telemetry.</p>{compatibility_recent_content}</details>"
        if compatibility_has_data else
        "<section class='overview-panel overview-compatibility-summary overview-compact-empty' aria-labelledby='overview-compatibility-title'><summary id='overview-compatibility-title'>Compatibility evidence · details and activity</summary><p class='overview-empty-state'>No compatibility evidence in this period.</p></section>"
    )
    review_section = (
        f"<div class='overview-review-block'><h3>New / review-required devices</h3>{_overview_review_required(review_required)}</div>"
        if review_required else ""
    )
    model_panel = (
        f"<section class='overview-panel overview-model-panel' aria-labelledby='overview-model-title'><div class='section-heading'><div><p class='section-kicker'>Compatibility evidence</p><h2 id='overview-model-title'>Device/model activity</h2></div></div><p class='overview-chart-note'>Compatibility evidence only · separate from map-operation telemetry.</p>{_overview_model_activity(model_activity)}{review_section}</section>"
        if model_activity or review_required else ""
    )
    primary_grid_class = "overview-primary-grid" if model_panel else "overview-primary-grid overview-primary-grid-single"
    secondary_grid_class = (
        "overview-secondary-grid"
        if reasons_section else
        "overview-secondary-grid overview-secondary-grid-single"
    )
    attention_section = (
        f"<section class='overview-panel overview-attention-panel' aria-labelledby='overview-attention-title'><div class='section-heading'><div><p class='section-kicker'>All unresolved · any date</p><h2 id='overview-attention-title'>Needs attention</h2></div><a class='section-link' href='{html.escape(attention_href, quote=True)}'>View all&nbsp;→</a></div>{attention_content}</section>"
        if attention_items else
        f"<section class='overview-panel overview-attention-panel overview-attention-empty' aria-labelledby='overview-attention-title'><div><p class='section-kicker'>All unresolved · any date</p><h2 id='overview-attention-title'>Needs attention</h2></div>{attention_content}<a class='section-link' href='{html.escape(attention_href, quote=True)}'>View all&nbsp;→</a></section>"
    )
    review = user.get("admin_review_summary") or {}
    attention_section += (
        "<nav class='attention-shortcuts' aria-label='All attention queues'>"
        f"<a href='/admin/installations?state=open'>Open errors <strong>{open_error_metric(open_errors)}</strong></a>"
        f"<a href='/admin/installations?state=identity-pending'>Identity review <strong>{int(review.get('identityPending') or 0)}</strong></a>"
        f"<a href='/admin/devices?review=publication'>Publication review <strong>{int(review.get('readyToPublish') or 0)}</strong></a>"
        "<a href='/admin/system-health'>System health</a></nav>"
    )
    provider_links = "".join(
        f"<a href='/admin/providers/{quote(str(provider.get('id') or ''), safe='')}'>{html.escape(str(provider.get('name') or provider.get('id') or 'Provider'))} <span>{html.escape(str(provider.get('health') or 'UNKNOWN').title())}</span></a>"
        for provider in providers
    )
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard overview-page' id='main-content'>
        <div class='heading-row overview-heading'><div><p class='eyebrow'>Operations</p><h1>Overview</h1><p class='lede'>Current Terento health and activity that needs attention.</p></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin'><label><span class='sr-only'>Time period</span><select id='overview-period' name='period'>{period_options}</select></label></form></div>
        <section class='overview-kpis' aria-label='Operational summary'>
          <a class='overview-kpi' href='{html.escape(map_statistics_href, quote=True)}'><span>Map install operations</span><strong>{event_metric(completed_installs + failed_installs)}</strong><small>{'Install actions in this period' if has_map_data else 'No map telemetry in this period'}</small></a>
          <a class='overview-kpi' href='{html.escape(map_statistics_href, quote=True)}'><span>Map operation success</span><strong>{success_rate}</strong><small>Successful install actions</small></a>
          <a class='overview-kpi overview-kpi-attention' href='{html.escape(failure_href, quote=True)}'><span>Failed map operations</span><strong>{event_metric(failed_installs)}</strong><small>{'Failed install actions in this period' if has_map_data else 'No map telemetry in this period'}</small></a>
          <a class='overview-kpi overview-kpi-attention' href='/admin/installations?state=open'><span>Open errors</span><strong>{open_error_metric(open_errors)}</strong><small>All unresolved compatibility errors</small></a>
          <a class='overview-kpi' href='/admin/providers'><span>Providers</span><strong>{healthy} / {provider_count}</strong><small>Healthy providers</small></a>
        </section>
        {attention_section}
        <div class='{primary_grid_class}'><section class='overview-panel overview-chart-panel' aria-labelledby='overview-trend-title'><div class='section-heading'><div><p class='section-kicker'>Map operations</p><h2 id='overview-trend-title'>Map install operations over time</h2></div></div>{_overview_trend_chart(list(data.get('trend') or []), str(data.get('bucket') or 'day'), time_zone)}</section>{model_panel}</div>
        <div class='{secondary_grid_class}'><section class='overview-panel' aria-labelledby='overview-activity-title'><div class='section-heading'><div><p class='section-kicker'>Latest</p><h2 id='overview-activity-title'>Recent map activity</h2></div><a class='section-link' href='{html.escape(map_statistics_href, quote=True)}'>View all&nbsp;→</a></div>{recent_content}</section>{reasons_section}</div>
        <section class='overview-panel overview-provider-panel' aria-labelledby='overview-provider-title'><div><p class='section-kicker'>Availability</p><h2 id='overview-provider-title'>Providers</h2></div><div class='overview-provider-summary'><strong>{healthy} / {provider_count} healthy</strong>{provider_links}</div><a class='section-link' href='/admin/providers'>Manage&nbsp;→</a></section>
        {compatibility_summary}
      </main>
      <script>{_overview_period_script()}</script>
    """
    return _layout("Overview", content)


def _health_status_badge(status: Any) -> str:
    normalized = str(status or "UNKNOWN").strip().upper()
    labels = {
        "HEALTHY": "Healthy", "WARNING": "Warning",
        "FAILED": "Failed", "UNKNOWN": "Unknown",
    }
    if normalized not in labels:
        normalized = "UNKNOWN"
    return f"<span class='system-health-badge system-health-{normalized.lower()}'>{labels[normalized]}</span>"


def _health_run_link(observation: dict[str, Any] | None) -> str:
    url = str((observation or {}).get("source_run_url") or "").strip()
    if not url.startswith("https://github.com/VooZ2/terento/actions/runs/"):
        return ""
    return f"<a class='section-link' href='{html.escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>GitHub Actions&nbsp;↗</a>"


def _health_attention(status: Any, reason: str, action: str) -> str:
    normalized = str(status or "UNKNOWN").upper()
    if normalized not in {"WARNING", "FAILED", "UNKNOWN"}:
        return ""
    return (
        f"<dl class='system-health-explanation'>"
        f"<div><dt>Reason</dt><dd>{html.escape(reason)}</dd></div>"
        f"<div><dt>Action</dt><dd>{html.escape(action)}</dd></div>"
        f"</dl>"
    )


def _system_health_card(
    title: str,
    status: Any,
    description: str,
    observation: dict[str, Any] | None = None,
    *,
    reason: str = "",
    action: str = "",
) -> dict[str, Any]:
    markup = (
        "<article class='system-health-card'>"
        f"<div class='section-heading'><h2>{html.escape(title)}</h2>{_health_status_badge(status)}</div>"
        f"<div class='system-health-description'>{description}</div>"
        f"{_health_attention(status, reason, action)}"
        f"{_health_run_link(observation)}</article>"
    )
    return {"title": title, "status": str(status or "UNKNOWN").upper(), "html": markup, "reason": reason}


def _system_health_cards(health: dict[str, Any]) -> tuple[list[dict[str, Any]], Any, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    providers = [
        provider for provider in health.get("providers") or []
        if str(provider.get("id") or "") in {"freizeitkarte", "opentopomap"}
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
            "API", health.get("api"), "<p>The authenticated page was served by the API.</p>",
            reason="The API health state could not be confirmed.",
            action="Reload the page, then inspect the catalog API deployment and service logs.",
        ),
        _system_health_card(
            "Database", health.get("database"), "<p>A live PostgreSQL snapshot was read for this page.</p>",
            reason="A live PostgreSQL health state could not be confirmed.",
            action="Inspect the database connection and migration state.",
        ),
    ]
    for provider in providers:
        state = provider_catalog_health(provider, now=now)
        description = (
            f"<p>Latest release <strong>{html.escape(str(provider.get('latestRelease') or '—'))}</strong>; "
            f"{int(provider.get('packageCount') or 0)} packages.</p>"
            f"<p>Last successful collection: {_timestamp_markup(provider.get('lastCollectionSuccess') or provider.get('lastCatalogSync'))}. "
            f"Last detected release change: {_timestamp_markup(provider.get('latestReleaseDetectedAt'))}.</p>"
        )
        cards.append(_system_health_card(
            f"{str(provider.get('name') or provider.get('id') or 'Provider')} catalog",
            state["status"], description, reason=state["reason"], action=state["action"],
        ))
    scheduler_action = "Inspect the catalog scheduler container and its next scheduled run."
    cards.extend([
        _system_health_card(
            "Catalog scheduler", scheduler_status,
            f"<p>Last completed: {_timestamp_markup((scheduler or {}).get('completed_at'))}. Next run: {_timestamp_markup((scheduler or {}).get('next_run_at'))}.</p>",
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
    card_markup = "".join(card['html'] for card in cards)
    attention_count = sum(card['status'] != 'HEALTHY' for card in cards)
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
        f"<tr><th scope='row'>{html.escape(suite_labels.get(str(name), str(name).replace('_', ' ').title()))}</th><td>{_health_status_badge('HEALTHY' if str(value).lower() in {'success', 'passed', 'healthy'} else 'FAILED' if str(value).lower() in {'failure', 'failed', 'cancelled', 'timed_out'} else 'UNKNOWN')}</td><td>{html.escape(str(value))}</td></tr>"
        for name, value in sorted(weekly_details.items())
        if name != "email" and not str(name).startswith("catalog_")
    ) or "<tr><td colspan='3'>No weekly suite details received yet.</td></tr>"
    content = f"""
      {_admin_header(user, csrf_token, active='system-health')}
      <main class='dashboard system-health-page' id='main-content'>
        <div class='heading-row'><div><p class='eyebrow'>Operations</p><h1>System health</h1><p class='lede'>Production state and retained GitHub evidence. Tests run in GitHub Actions, not in this admin panel.</p></div></div>
        <p class='admin-health-summary' role='status'>{str(attention_count) + ' checks need attention' if attention_count else 'All checks healthy'}. Problems appear first.</p><section class='system-health-grid' aria-label='System health summary'>{card_markup}</section>
        <details class='overview-panel admin-disclosure'><summary>Quality-gate results · weekly report</summary>{_health_run_link(weekly)}<div class='table-wrap'><table class='admin-table'><thead><tr><th scope='col'>Check</th><th scope='col'>Health</th><th scope='col'>Result</th></tr></thead><tbody>{detail_rows}</tbody></table></div></details>
      </main>
    """
    return _layout("System health", content)


def dashboard_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    public_stats_enabled: bool = False,
) -> bytes:
    latest = _latest_data_timestamp(rows)
    status_values = [status.value for status in CANONICAL_STATUS_ORDER]
    status_options = "".join(
        f"<option value='{status.lower()}'>{status.title()}</option>"
        for status in status_values
    )
    diagnostic_summary = _diagnostic_summary_by_identity(
        operations or [], resolved_operations or [],
    )
    def metric(row: dict[str, Any], summary_key: str, row_key: str) -> int:
        summary = diagnostic_summary.get(_identity_group_key(row), {})
        return int(summary[summary_key]) if summary_key in summary else int(row.get(row_key) or 0)

    attempts = sum(metric(row, "attempts", "attempted_install_count") for row in rows)
    successes = sum(metric(row, "successful", "successful_install_count") for row in rows)
    failures = sum(metric(row, "failed", "failed_install_count") for row in rows)
    open_errors = sum(
        int(summary.get("open_errors") or 0) for summary in diagnostic_summary.values()
    )
    historical_failures = max(0, failures - open_errors)
    success_rate = (successes / attempts * 100) if attempts else None
    table_rows = "".join(
        _statistics_row(
            row,
            diagnostic_summary.get(_identity_group_key(row), {}),
        )
        for row in rows
    )
    empty = "<p class='empty'>No installation evidence yet.</p>" if not rows else ""
    latest_copy = f"Updated {_timestamp_markup(latest)}" if latest else "No evidence received yet"
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class="dashboard" id="main-content">
        <div class="heading-row installation-heading"><div><p class="eyebrow">Compatibility</p><h1>Installations</h1><p class="lede">All-time compatibility evidence from Terento users.</p></div><p class="page-meta">{latest_copy}</p></div>
        <section class="admin-kpi-grid installation-kpis" aria-label="Installation summary">
          <article><span>Variants</span><strong>{len(rows)}</strong></article>
          <article><span>Write-started attempts</span><strong>{attempts}</strong></article>
          <article><span>Successful</span><strong>{successes}</strong></article>
          <article><span>Evidence success</span><strong>{_format_rate(success_rate)}</strong></article>
          <article><span>Open errors</span><strong>{open_errors}</strong></article>
        </section>
        <p class="historical-failure-note">Historical failures: {historical_failures} <span class="info-control info-control-inline" role="img" aria-label="Includes resolved historical failures. Open errors shows only unresolved problems." title="Includes resolved historical failures. Open errors shows only unresolved problems.">i</span></p>
        {empty}
        <section class="evidence-section" aria-label="Installation evidence table">
          <form class="filter-bar admin-filter-bar" id="evidence-filters" role="search">
            <div class="quick-filter-group" role="group" aria-label="Quick installation filters"><button type="button" class="quick-filter active" data-installation-filter="all" aria-pressed="true">All</button><button type="button" class="quick-filter" data-installation-filter="failed" aria-pressed="false">Failed</button><button type="button" class="quick-filter" data-installation-filter="open" aria-pressed="false">Open errors</button><button type="button" class="quick-filter" data-installation-filter="successful" aria-pressed="false">Successful</button><button type="button" class="quick-filter" data-installation-filter="identity-pending" aria-pressed="false">Identity review</button></div>
            <label class="filter-search"> <span class="sr-only">Search models</span><input id="evidence-search" type="search" placeholder="Search models" autocomplete="off"></label>
            <label><span class="sr-only">Filter by status</span><select id="evidence-status"><option value="all">All statuses</option>{status_options}</select></label>
            <label><span class="sr-only">Sort models</span><select id="evidence-sort"><option value="attempts">Most attempts</option><option value="errors">Most errors</option><option value="latest" selected>Latest activity</option><option value="model">Model name</option></select></label>
            <p class="results-count" id="results-count" aria-live="polite">{len(rows)} {"variant" if len(rows) == 1 else "variants"}</p>
          </form>
          <div class="table-wrap evidence-table-wrap"><table class="admin-table"><caption class="sr-only">Installations by exact device identity</caption><thead><tr><th scope="col">Model</th><th scope="col">Variant</th><th scope="col">Status</th><th scope="col">Attempts</th><th scope="col">Successful</th><th scope="col">Failed</th><th scope="col">Open errors</th><th scope="col">Last success</th></tr></thead><tbody id="evidence-rows">{table_rows}</tbody></table></div>
        </section>
      </main>
      <script>{_dashboard_script()}</script>
    """
    return _layout("Installations", content)


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
        "SUCCEEDED": "Succeeded",
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
        return f"<a href='{escaped}' target='_blank' rel='noopener noreferrer'>{text} <span aria-hidden='true'>↗</span></a>"
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
        return "<span class='provider-status provider-status-unknown' title='Not evaluated'>Not evaluated</span>"
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
    broken = max(
        int(provider.get("brokenUrlCount") or 0),
        int(provider.get("brokenPackageCount") or 0),
    )
    provider_href = html.escape(quote(provider_id, safe=""), quote=True)
    error = str(provider.get("lastHealthError") or "").strip()
    issue_count = max(broken, 1 if error else 0)
    issue_markup = (
        f"<span class='provider-issue-count' title='{html.escape(error or f'{issue_count} provider issue(s)', quote=True)}' aria-label='{html.escape(f'{issue_count} provider issue(s)', quote=True)}'>{issue_count}</span>"
        if issue_count else "0"
    )
    return (
        f"<tr data-provider-search='{html.escape(' '.join((provider_id, name, str(provider.get('adapterId') or ''), status, health)).casefold(), quote=True)}'>"
        f"<td><a class='provider-name-link' href='/admin/providers/{provider_href}'><strong>{html.escape(name)}</strong></a></td>"
        f"<td>{_provider_status_badge(status)}</td>"
        f"<td>{_provider_status_badge(health, kind='health')}</td>"
        f"<td class='numeric'>{int(provider.get('packageCount') or 0)}</td>"
        f"<td>{_timestamp_markup(provider.get('lastCatalogSync'))}</td>"
        f"<td>{_timestamp_markup(provider.get('lastHealthCheck') or provider.get('lastDownloadTest'))}</td>"
        f"<td class='numeric'>{issue_markup}</td>"
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
    packages = sum(int(provider.get("packageCount") or 0) for provider in provider_rows)
    issues = sum(
        max(
            int(provider.get("brokenUrlCount") or 0),
            int(provider.get("brokenPackageCount") or 0),
            1 if str(provider.get("lastHealthError") or "").strip() else 0,
        )
        for provider in provider_rows
    )
    content = f"""
      {_admin_header(user, csrf_token, active='providers')}
      <main class='dashboard' id='main-content'>
        <div class='heading-row'><div><p class='eyebrow'>Map operations</p><h1>Providers</h1><p class='lede'>Known provider adapters, catalog state, and the latest health evidence.</p></div></div>
        <section class='admin-summary-strip' aria-label='Provider summary'><p class='admin-summary-metrics'><strong>{len(provider_rows)} providers</strong><span> · {active} active · {healthy} healthy · {packages} packages · {issues} issues</span></p></section>
        {empty}
        <section class='provider-section' aria-label='Provider list'>
          <form class='filter-bar provider-filter-bar' id='provider-filters' role='search'><label class='filter-search'><span class='sr-only'>Search providers</span><input id='provider-search' type='search' placeholder='Search providers' autocomplete='off'></label><p class='results-count' id='provider-results-count' aria-live='polite'>{len(provider_rows)} providers</p></form>
          <div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Map provider status</caption><thead><tr><th scope='col'>Provider</th><th scope='col'>Activity</th><th scope='col'>Health</th><th scope='col'>Packages</th><th scope='col'>Catalog sync</th><th scope='col'>Last check</th><th scope='col'>Issues</th></tr></thead><tbody id='provider-rows'>{rows}</tbody></table></div>
        </section>
      </main>
      <script>window.terentoAdminCsrf = {_admin_json(csrf_token)};{_providers_list_script()}</script>
    """
    return _layout("Providers", content)


def _provider_package_row(package: dict[str, Any]) -> str:
    broken_count = int(package.get("broken_artifact_count") or 0)
    availability = str(package.get("availability") or "UNKNOWN")
    row_class = " provider-package-broken" if broken_count else ""
    broken_markup = _provider_status_badge("FAILED" if broken_count else availability)
    package_id = str(package.get("id") or "—")
    package_name = _admin_map_display_name(
        package.get("country"), package.get("name"), package.get("region"), package_id,
    )
    region = str(package.get("region") or "").strip()
    search = " ".join((package_id, package_name, region, str(package.get("release") or ""))).casefold()
    return (
        f"<tr class='{row_class.strip()}' data-package-search='{html.escape(search, quote=True)}' data-package-broken='{str(bool(broken_count)).lower()}'><td><span class='provider-package-name'>{html.escape(package_name)}</span><code class='provider-package-id'>{html.escape(package_id)}</code>{f'<small>{html.escape(region)}</small>' if region and region.casefold() != package_name.casefold() else ''}</td>"
        f"<td>{html.escape(str(package.get('release') or '—'))}</td><td class='numeric'>{int(package.get('artifact_count') or 0)}</td>"
        f"<td>{broken_markup}{f' <small>{broken_count} broken</small>' if broken_count else ''}</td></tr>"
    )


def _provider_source_row(source: dict[str, Any]) -> str:
    source_type = str(source.get("source_type") or "").upper()
    source_url = str(source.get("source_url") or "")
    source_label = _provider_source_label(source_url)
    search = " ".join((source_type, source_url)).casefold()
    broken = str(source.get("validation_status") or "").upper() in {"FAILED", "UNAVAILABLE"}
    return (
        f"<tr data-source-type='{html.escape(source_type, quote=True)}' data-source-search='{html.escape(search, quote=True)}' data-source-broken='{str(broken).lower()}'><td>{html.escape(_provider_source_type_label(source_type))}</td>"
        f"<td class='provider-url-cell' title='{html.escape(source_url, quote=True)}'>{_provider_url(source_url, label=source_label)}</td>"
        f"<td>{_provider_status_badge('ACTIVE' if source.get('enabled', True) else 'PAUSED')}</td>"
        f"<td>{_timestamp_markup(source.get('last_checked_at'))}</td></tr>"
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
        f"<span class='provider-component'>{html.escape(label)}: {_provider_check_badge(health.get(key))}</span>"
        for key, label in components
    )
    error = str(health.get("error_code") or health.get("error_detail") or "").strip()
    error_markup = (
        f"<span class='provider-error' title='{html.escape(error, quote=True)}'>{html.escape(error)}</span>"
        if error else "<span class='muted-value'>—</span>"
    )
    return (
        f"<tr><td>{_timestamp_markup(health.get('checked_at'))}</td><td>{_provider_status_badge(health.get('status'), kind='health')}</td>"
        f"<td><div class='provider-component-list'>{component_markup}</div></td><td>{html.escape(str(health.get('http_status') or '—'))}</td>"
        f"<td>{html.escape(str(health.get('artifact_count') or '—'))}</td><td>{html.escape(str(health.get('duration_ms') or '—'))} ms</td>"
        f"<td>{error_markup}</td></tr>"
    )


def _provider_run_row(run: dict[str, Any]) -> str:
    error = str(run.get("error_code") or run.get("error_detail") or "").strip()
    error_markup = html.escape(error) if error else "<span class='muted-value'>—</span>"
    return (
        f"<tr><td><code>{html.escape(str(run.get('id') or '—'))}</code></td><td>{_timestamp_markup(run.get('started_at'))}</td>"
        f"<td>{_timestamp_markup(run.get('finished_at'))}</td><td>{_provider_status_badge(run.get('status'))}</td>"
        f"<td class='numeric'>{int(run.get('package_count') or 0)}</td><td class='numeric'>{int(run.get('artifact_count') or 0)}</td>"
        f"<td>{error_markup}</td></tr>"
    )


def _provider_audit_row(audit: dict[str, Any]) -> str:
    details = audit.get("details")
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
        f"<td>{html.escape(str(audit.get('old_status') or '—'))}</td><td>{html.escape(str(audit.get('new_status') or '—'))}</td>"
        f"<td>{html.escape(str(audit.get('reason') or '—'))}</td><td>{_timestamp_markup(audit.get('occurred_at'))}</td>"
        f"<td><details class='audit-technical-details'><summary>Technical details</summary><code>{html.escape(technical_text if technical_text != '{}' else '—')}</code></details></td></tr>"
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
    broken_packages = sum(int(package.get("broken_artifact_count") or 0) for package in packages)
    package_count = int(provider.get("packageCount") or len(packages))
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
    rows_download_sources = "".join(_provider_source_row(source) for source in download_sources)
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
    source_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-source-table'><caption class='sr-only'>Provider-level original sources</caption><thead><tr><th scope='col'>Source</th><th scope='col'>Original link</th><th scope='col'>Status</th><th scope='col'>Last checked</th></tr></thead><tbody>{rows_sources}</tbody></table></div>" if provider_sources else ""
    download_source_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-source-table'><caption class='sr-only'>Download source URLs</caption><thead><tr><th scope='col'>Source</th><th scope='col'>Original link</th><th scope='col'>Status</th><th scope='col'>Last checked</th></tr></thead><tbody id='provider-download-source-rows'>{rows_download_sources}</tbody></table></div>" if download_sources else ""
    download_source_section = f"<section class='provider-card'><details class='admin-disclosure' id='provider-download-sources'><summary>Download source URLs · {len(download_sources)}</summary><div class='disclosure-body'><div class='inline-filter-row'><label><span class='sr-only'>Search source URLs</span><input id='provider-source-search' type='search' placeholder='Search source URLs' autocomplete='off'></label><label><span class='sr-only'>Source status</span><select id='provider-source-filter'><option value='all'>All sources</option><option value='broken'>Broken only</option></select></label><label><span class='sr-only'>Source page size</span><select id='provider-source-page-size'><option value='25'>25 per page</option><option value='50'>50 per page</option></select></label></div>{download_source_table}<div class='provider-pagination' id='provider-source-pagination' aria-live='polite'></div></div></details></section>" if download_sources else ""
    package_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-package-table'><caption class='sr-only'>Regions and packages</caption><thead><tr><th scope='col'>Region / package</th><th scope='col'>Release</th><th scope='col'>Artifacts</th><th scope='col'>State</th></tr></thead><tbody id='provider-package-rows'>{rows_packages}</tbody></table></div>" if packages else ""
    latest_health_table = f"<div class='table-wrap provider-table-wrap provider-history-wrap'><table class='admin-table'><caption class='sr-only'>Health check details</caption><thead><tr><th scope='col'>Checked</th><th scope='col'>Result</th><th scope='col'>Checks</th><th scope='col'>HTTP</th><th scope='col'>Artifacts</th><th scope='col'>Duration</th><th scope='col'>Error</th></tr></thead><tbody>{_provider_health_row(latest_health)}</tbody></table></div>" if latest_health else ""
    health_history_table = f"<div class='table-wrap provider-table-wrap provider-history-wrap'><table class='admin-table'><thead><tr><th scope='col'>Checked</th><th scope='col'>Result</th><th scope='col'>Checks</th><th scope='col'>HTTP</th><th scope='col'>Artifacts</th><th scope='col'>Duration</th><th scope='col'>Error</th></tr></thead><tbody>{rows_health}</tbody></table></div>" if previous_health else ""
    run_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-run-table'><thead><tr><th scope='col'>Run</th><th scope='col'>Started</th><th scope='col'>Finished</th><th scope='col'>Result</th><th scope='col'>Packages</th><th scope='col'>Artifacts</th><th scope='col'>Error</th></tr></thead><tbody>{rows_runs}</tbody></table></div>" if runs else ""
    audit_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Provider audit history</caption><thead><tr><th scope='col'>Action</th><th scope='col'>Old status</th><th scope='col'>New status</th><th scope='col'>Reason</th><th scope='col'>Timestamp</th><th scope='col'>Details</th></tr></thead><tbody>{rows_audits}</tbody></table></div>" if audits else ""
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
        f"<span>{int(latest_run.get('package_count') or 0)} packages · "
        f"{int(latest_run.get('artifact_count') or 0)} artifacts · "
        f"{_timestamp_markup(latest_run.get('finished_at') or latest_run.get('started_at'))}</span>"
        if latest_run else "<span class='muted-value'>No collection run recorded yet.</span>"
    )
    collection_section = (
        f"<section class='provider-card'><div class='section-heading'><div><p class='section-kicker'>Collection</p><h2>Last collection</h2></div></div><div class='provider-latest-summary'>{collection_summary}</div><details class='admin-disclosure' id='provider-collection-history'><summary>Collection history · {len(runs)} runs</summary><div class='disclosure-body'>{empty_runs}{run_table}</div></details></section>"
        if latest_run or runs else
        "<section class='provider-card provider-empty-disclosure'><details class='admin-disclosure' id='provider-collection-history'><summary>Collection · No runs yet</summary><div class='disclosure-body'><p class='empty'>No catalog collection runs recorded yet.</p></div></details></section>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='providers')}
      <main class='dashboard provider-detail' id='main-content'>
        <p class='back-link'><a href='/admin/providers'>← Back to providers</a></p>
        <div class='heading-row'><div><p class='eyebrow'>Provider detail</p><h1>{html.escape(name)}</h1></div><div class='provider-heading-status'>{_provider_status_badge(status)} {_provider_status_badge(health, kind='health')}</div></div>
        <section class='provider-action-bar' data-provider-id='{html.escape(provider_id, quote=True)}' aria-label='Provider actions'>
          {_provider_action_button(provider_id, 'check', 'Check now')}
          {_provider_action_button(provider_id, 'collect', 'Collect catalog', secondary=True)}
          {state_button}
          <details class='provider-action-overflow'><summary>More</summary><div>{_provider_action_button(provider_id, 'retire', 'Retire provider', secondary=True, disabled=status == 'RETIRED')}</div></details>
          {activation_note}
          <p class='admin-action-status' id='provider-action-status' aria-live='polite'></p>
        </section>
        <section class='provider-metrics' aria-label='Provider summary'><article><span>Packages</span><strong>{package_count}</strong></article><article><span>Broken</span><strong>{broken_packages}</strong></article><article><span>Last catalog sync</span><strong>{_timestamp_markup(provider.get('lastCatalogSync'))}</strong></article><article><span>Last health check</span><strong>{_timestamp_markup(provider.get('lastHealthCheck'))}</strong></article></section>
        {download_source_section}
        <section class='provider-card'><details class='admin-disclosure' id='provider-packages'><summary>Regions and packages · {len(packages)} packages · {broken_packages} broken</summary><div class='disclosure-body'><div class='inline-filter-row'><label><span class='sr-only'>Search packages</span><input id='provider-package-search' type='search' placeholder='Search packages' autocomplete='off'></label><label><span class='sr-only'>Package status</span><select id='provider-package-filter'><option value='all'>All packages</option><option value='broken'>Broken only</option></select></label><label><span class='sr-only'>Package page size</span><select id='provider-package-page-size'><option value='25'>25 per page</option><option value='50'>50 per page</option></select></label></div>{empty_packages}{package_table}<div class='provider-pagination' id='provider-package-pagination' aria-live='polite'></div></div></details></section>
        <section class='provider-card'><div class='section-heading'><div><p class='section-kicker'>Health</p><h2>Latest health check</h2></div></div><div class='provider-latest-summary'><div>{health_summary}</div><span>{health_transport}</span></div><details class='admin-disclosure' id='provider-health-details'><summary>View check details</summary><div class='disclosure-body'>{empty_health}{latest_health_table}</div></details><details class='admin-disclosure' id='provider-health-history'><summary>Health check history · {len(previous_health)} previous checks</summary><div class='disclosure-body'>{empty_previous_health}{health_history_table}</div></details></section>
        {collection_section}
        <details class='provider-card admin-disclosure'><summary>Provider metadata and attribution</summary><dl class='provider-information-list'><div><dt>Provider ID</dt><dd><code>{html.escape(provider_id)}</code></dd></div><div><dt>Adapter</dt><dd><code>{html.escape(str(provider.get('adapterId') or '—'))}</code></dd></div><div><dt>Website</dt><dd>{_provider_url(provider.get('website'))}</dd></div><div><dt>License</dt><dd>{html.escape(str(provider.get('license') or '—'))}</dd></div><div><dt>Attribution</dt><dd>{html.escape(str(provider.get('attribution') or '—'))}</dd></div><div><dt>License URL</dt><dd>{_provider_url(provider.get('licenseUrl'))}</dd></div></dl></details>
        <details class='provider-card admin-disclosure'><summary>Original links</summary>{empty_sources}{source_table}</details>
        <section class='provider-card'><details class='admin-disclosure' id='provider-history'><summary>Provider history · {len(audits)} events</summary><div class='disclosure-body'><p class='table-help'>Status changes and provider actions are retained.</p>{empty_audits}{audit_table}</div></details></section>
      </main>
      <script>window.terentoAdminCsrf = {_admin_json(csrf_token)};{_provider_detail_script()}</script>
    """
    return _layout(name, content)


def _map_statistics_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    has_event_data = bool(rows)

    def count(event_type: str, outcome: str | None = None) -> int:
        return sum(
            int(row.get("operation_count") or row.get("event_count") or 0)
            for row in rows
            if row.get("event_type") == event_type and (outcome is None or row.get("outcome") == outcome)
        )

    downloads = count("DOWNLOAD_SUCCEEDED", "SUCCEEDED")
    failed_downloads = count("DOWNLOAD_FAILED", "FAILED")
    download_attempts = downloads + failed_downloads
    installs = count("INSTALL_SUCCEEDED", "SUCCEEDED")
    failed_installs = count("INSTALL_FAILED", "FAILED")
    install_attempts = installs + failed_installs
    event_count = sum(
        int(row.get("event_count") or row.get("operation_count") or 0)
        for row in rows
    )
    return {
        "hasEventData": has_event_data,
        "eventGroupCount": len(rows),
        "eventCount": event_count if has_event_data else None,
        "completedDownloads": downloads if has_event_data else None,
        "failedDownloads": failed_downloads if has_event_data else None,
        "downloadAttempts": download_attempts if has_event_data else None,
        "downloadSuccessRate": (downloads / download_attempts * 100) if has_event_data and download_attempts else None,
        "completedInstalls": installs if has_event_data else None,
        "failedInstalls": failed_installs if has_event_data else None,
        "installAttempts": install_attempts if has_event_data else None,
        "installSuccessRate": (installs / install_attempts * 100) if has_event_data and install_attempts else None,
    }


def _map_statistics_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tr><td colspan='7' class='muted-value'>No map events in this period.</td></tr>"
    markup: list[str] = []
    for row in rows:
        region_name = _admin_map_display_name(
            row.get("region_display_name"), row.get("region"),
        )
        markup.append(
            f"<tr><td>{html.escape(str(row.get('provider_id') or '—'))}</td>"
            f"<td><code>{html.escape(str(row.get('map_package_id') or '—'))}</code></td>"
            f"<td>{html.escape(region_name)}</td><td>{html.escape(str(row.get('event_type') or '—'))}</td>"
            f"<td>{html.escape(_admin_event_outcome_label(row.get('outcome')))}</td><td class='numeric'>{int(row.get('operation_count') or row.get('event_count') or 0)}</td>"
            f"<td>{_timestamp_markup(row.get('last_occurred_at'))}</td></tr>"
        )
    return "".join(markup)


def map_statistics_page(
    statistics: dict[str, Any], providers: list[dict[str, Any]], user: dict[str, Any],
    csrf_token: str, *, selected_filters: dict[str, str] | None = None,
) -> bytes:
    rows = list(statistics.get("rows") or [])
    summary = _map_statistics_summary(rows)
    selected = selected_filters or {}
    has_event_data = bool(rows)
    selected_provider = str(selected.get("provider") or "").strip().lower()
    scoped_providers = [
        provider for provider in providers
        if not selected_provider
        or str(provider.get("id") or "").strip().lower() == selected_provider
    ]
    provider_issues = sum(
        max(
            int(provider.get("brokenUrlCount") or 0),
            int(provider.get("brokenPackageCount") or 0),
            1 if str(provider.get("lastHealthError") or "").strip() else 0,
        )
        for provider in scoped_providers
    )
    healthy_providers = sum(
        1 for provider in scoped_providers if str(provider.get("health") or "").upper() == "HEALTHY"
    )
    event_value = lambda key: "—" if summary.get(key) is None else str(summary[key])
    event_status = (
        f"{summary['eventGroupCount']} event group{'s' if summary['eventGroupCount'] != 1 else ''} · "
        f"{summary['eventCount']} event record{'s' if summary['eventCount'] != 1 else ''}"
        if has_event_data else "No event groups"
    )
    provider_options = "".join(
        f"<option value='{html.escape(str(provider.get('id') or ''), quote=True)}'>{html.escape(str(provider.get('name') or provider.get('id') or ''))}</option>"
        for provider in providers
    )
    detail_rows = list(statistics.get("detailRows") or rows[:25])
    detail_total = int(statistics.get("detailTotal") or len(rows))
    detail_page = int(statistics.get("detailPage") or 1)
    detail_page_size = int(statistics.get("detailPageSize") or 25)
    detail_pages = max(1, (detail_total + detail_page_size - 1) // detail_page_size)
    detail_start = min(detail_total, (detail_page - 1) * detail_page_size + 1) if detail_total else 0
    detail_end = min(detail_total, detail_page * detail_page_size)
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
    event_table = f"""<div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Map operation events</caption><thead><tr><th scope='col'>Provider</th><th scope='col'>Map</th><th scope='col'>Region</th><th scope='col'>Event</th><th scope='col'>Outcome</th><th scope='col'>Operations</th><th scope='col'>Last activity</th></tr></thead><tbody id='map-statistics-rows'>{_map_statistics_rows(detail_rows)}</tbody></table></div><div class='provider-pagination' id='map-statistics-event-pagination' aria-live='polite'><label>Rows <select id='map-statistics-event-page-size' aria-label='Rows per event page'><option value='25'{' selected' if detail_page_size == 25 else ''}>25</option><option value='50'{' selected' if detail_page_size == 50 else ''}>50</option></select></label><button type='button' data-event-page='previous' disabled>Previous</button><span>Showing {detail_start}–{detail_end} of {detail_total} · page {detail_page} of {detail_pages}</span><button type='button' data-event-page='next' {'disabled' if detail_page >= detail_pages else ''}>Next</button></div>"""
    content = f"""
      {_admin_header(user, csrf_token, active='map-statistics')}
      <main class='dashboard map-statistics-page' id='main-content'>
        <div class='heading-row'><div><p class='eyebrow'>Map operations</p><h1>Map statistics</h1><p class='lede'>Downloads, installs, and provider health.</p></div></div>
        <form class='filter-bar map-statistics-filter-bar' id='map-statistics-filters' role='search'><label><span class='sr-only'>Time range</span><select id='map-statistics-range'>{statistics_period_options}</select></label><label><span class='sr-only'>Provider</span><select id='map-statistics-provider'><option value=''>All providers</option>{provider_options}</select></label><details class='admin-disclosure filter-disclosure' id='map-statistics-more-filters'><summary>More filters</summary><div class='disclosure-body'><label><span class='sr-only'>Map ID</span><input id='map-statistics-map' type='search' placeholder='Map ID'></label><label><span class='sr-only'>Region</span><input id='map-statistics-region' type='search' placeholder='Region'></label><label><span class='sr-only'>Event type</span><select id='map-statistics-event'><option value=''>All events</option><option value='DOWNLOAD_SUCCEEDED'>Download succeeded</option><option value='DOWNLOAD_FAILED'>Download failed</option><option value='INSTALL_SUCCEEDED'>Install succeeded</option><option value='INSTALL_FAILED'>Install failed</option><option value='DOWNLOAD_STARTED'>Download started</option></select></label></div></details><p class='results-count' id='map-statistics-status' aria-live='polite'>{event_status}</p></form>
        <p class='table-help map-statistics-definition-note'>Counts map packages; one install can include multiple packages.</p>
        <section class='admin-kpi-grid map-statistics-kpis' id='map-statistics-metrics' aria-label='Map statistics summary'><article><span>Downloads</span><strong data-stat='completedDownloads'>{event_value('completedDownloads')}</strong></article><article><span>Download rate</span><strong data-stat='downloadSuccessRate'>{_format_rate(summary['downloadSuccessRate'])}</strong></article><article><span>Installs</span><strong data-stat='completedInstalls'>{event_value('completedInstalls')}</strong></article><article><span>Install rate</span><strong data-stat='installSuccessRate'>{_format_rate(summary['installSuccessRate'])}</strong></article></section>
        <section class='map-statistics-empty' id='map-statistics-empty' {'hidden' if has_event_data else ''} aria-live='polite'><h2>No map operation data yet</h2><p>Statistics will appear after opted-in map operations are received.</p></section>
        <section class='map-statistics-reliability' aria-label='Reliability summary'><div><span>Failed installs</span><strong data-stat='failedInstalls'>{event_value('failedInstalls')}</strong></div><div><span>Failed downloads</span><strong data-stat='failedDownloads'>{event_value('failedDownloads')}</strong></div><div><span>Provider issues</span><strong data-stat='providerIssues'>{provider_issues}</strong></div></section>
        <section class='map-statistics-provider-health' id='map-statistics-provider-health' aria-label='Provider health'><span>Provider health</span><strong data-stat='providerHealth'>{healthy_providers} / {len(scoped_providers)} healthy</strong><em data-stat='providerHealthIssues'> · {provider_issues} issues</em></section>
        <section class='provider-card map-statistics-provider-table' id='map-statistics-provider-table' {'hidden' if not has_event_data else ''}><div class='section-heading'><div><p class='section-kicker'>Popularity</p><h2>Provider activity</h2></div></div><div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Provider activity</caption><thead><tr><th scope='col'>Provider</th><th scope='col'>Downloads</th><th scope='col'>Installs</th><th scope='col'>Install rate</th><th scope='col'>Health</th></tr></thead><tbody id='provider-statistic-rows'></tbody></table></div></section>
        <section class='map-statistics-coverage-layout' id='map-statistics-coverage' {'hidden' if not has_event_data else ''} aria-label='Installation coverage'><section class='provider-card map-statistics-world-map-card' aria-labelledby='map-statistics-world-map-title'><div class='section-heading'><div><p class='section-kicker'>Coverage</p><h2 id='map-statistics-world-map-title'>Installs by country</h2></div><p class='table-help' id='map-statistics-world-map-status'>Completed installs</p></div><div class='map-statistics-world-map' id='map-statistics-world-map' role='group' aria-label='World map of installs by country'><div class='world-map-svg' id='world-map-svg'></div><div class='world-map-tooltip' id='world-map-tooltip' role='status' aria-live='polite' hidden></div></div><div class='world-map-legend' aria-label='Installation coverage legend'><span>0</span><i class='world-map-legend-gradient' aria-hidden='true'></i><span id='world-map-legend-max'>Most</span></div><p class='table-help world-map-note'>White means no installs. Hover a country for providers.</p></section><section class='provider-card map-statistics-popularity' id='map-statistics-popularity'><div class='section-heading'><div><p class='section-kicker'>Popularity</p><h2>Popular maps</h2></div></div><div class='popularity-subsection'><h3>Top 5</h3><div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Popular maps</caption><thead><tr><th scope='col'>Map</th><th scope='col'>Source</th><th scope='col'>Count</th><th scope='col'>Last</th></tr></thead><tbody id='map-rows'></tbody></table></div><details class='admin-disclosure popularity-all-maps-disclosure'><summary id='all-maps-summary'>All maps</summary></details></div><details class='admin-disclosure popularity-regions-disclosure'><summary>Regions</summary><div class='disclosure-body'><div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Top regions</caption><thead><tr><th scope='col'>Region</th><th scope='col'>Count</th><th scope='col'>Last</th></tr></thead><tbody id='top-region-rows'></tbody></table></div></div></details></section></section>
        <section class='provider-card map-events-card' {'hidden' if not has_event_data else ''}><details class='admin-disclosure' id='map-statistics-event-detail'><summary id='map-statistics-event-summary'>Event detail · {event_status}</summary><div class='disclosure-body' id='map-statistics-event-body'>{event_table}</div></details></section>
      </main>
      <script>window.terentoMapStatistics = {_admin_json(statistics)};window.terentoAdminProviders = {_admin_json(providers)};window.terentoMapStatisticsFilters = {_admin_json(selected)};window.terentoWorldMapSvg = {_admin_json(WORLD_MAP_SVG)};window.terentoWorldMapCountryAliases = {_admin_json(WORLD_MAP_COUNTRY_ALIASES)};{_map_statistics_script()}</script>
    """
    return _layout("Map statistics", content)


def _providers_list_script() -> str:
    return r"""(() => {
      const search = document.querySelector('#provider-search');
      const rows = [...document.querySelectorAll('#provider-rows tr[data-provider-search]')];
      const count = document.querySelector('#provider-results-count');
      const csrf = window.terentoAdminCsrf;
      const refresh = () => {
        const query = (search?.value || '').trim().toLocaleLowerCase();
        let visible = 0;
        rows.forEach((row) => { const show = !query || row.dataset.providerSearch.includes(query); row.hidden = !show; if (show) visible += 1; });
        if (count) count.textContent = `${visible} provider${visible === 1 ? '' : 's'}`;
      };
      search?.addEventListener('input', refresh);
      document.querySelectorAll('[data-provider-action="check"]').forEach((button) => {
        button.addEventListener('click', async () => {
          const id = button.dataset.providerId;
          button.disabled = true;
          try {
            const response = await fetch(`/admin/providers/${encodeURIComponent(id)}/check`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: '{}'});
            if (!response.ok) throw new Error(`Check failed (${response.status})`);
            window.location.reload();
          } catch (error) { button.disabled = false; window.alert(error.message || 'Provider check failed.'); }
        });
      });
      refresh();
    })();"""


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
      const csrf = window.terentoAdminCsrf;
      const initial = window.terentoMapStatistics || {rows: []};
      const providers = window.terentoAdminProviders || [];
      const filters = window.terentoMapStatisticsFilters || {};
      const range = document.querySelector('#map-statistics-range');
      const provider = document.querySelector('#map-statistics-provider');
      const map = document.querySelector('#map-statistics-map');
      const region = document.querySelector('#map-statistics-region');
      const event = document.querySelector('#map-statistics-event');
      const status = document.querySelector('#map-statistics-status');
      const moreFilters = document.querySelector('#map-statistics-more-filters');
      const emptyState = document.querySelector('#map-statistics-empty');
      const coverage = document.querySelector('#map-statistics-coverage');
      const popularity = document.querySelector('#map-statistics-popularity');
      const worldMap = document.querySelector('#map-statistics-world-map');
      const worldMapSvg = document.querySelector('#world-map-svg');
      const worldMapTooltip = document.querySelector('#world-map-tooltip');
      const worldMapStatus = document.querySelector('#map-statistics-world-map-status');
      const worldMapLegendMax = document.querySelector('#world-map-legend-max');
      const providerTable = document.querySelector('#map-statistics-provider-table');
      const mapRows = document.querySelector('#map-rows');
      const allMapsDisclosure = document.querySelector('.popularity-all-maps-disclosure');
      const allMapsSummary = allMapsDisclosure?.querySelector('summary');
      const providerHealth = document.querySelector('#map-statistics-provider-health');
      const eventDetail = document.querySelector('#map-statistics-event-detail');
      const eventSummary = document.querySelector('#map-statistics-event-summary');
      const eventPagination = document.querySelector('#map-statistics-event-pagination');
      const eventPageSize = document.querySelector('#map-statistics-event-page-size');
      let detailPage = 1;
      let currentPayload = initial;
      const formatRate = (value) => value === null || value === undefined ? '—' : `${Number(value).toFixed(Number(value) % 1 ? 1 : 0)}%`;
      const operations = (row) => Number(row.operation_count || row.event_count || 0);
      const count = (rows, eventType, outcome) => rows.filter((row) => row.event_type === eventType && (!outcome || row.outcome === outcome)).reduce((total, row) => total + operations(row), 0);
      const healthByProvider = Object.fromEntries(providers.map((item) => [item.id, item.health || 'UNKNOWN']));
      const providerName = Object.fromEntries(providers.map((item) => [item.id, item.name || item.id]));
      const providerIssueCount = (item) => Math.max(Number(item.brokenUrlCount || 0), Number(item.brokenPackageCount || 0), item.lastHealthError ? 1 : 0);
      const humanize = (value) => String(value || '—').replace(/[-_]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
      const outcomeLabel = (value) => String(value || '').toUpperCase() === 'UNKNOWN' ? '—' : humanize(value);
      const countryAliases = window.terentoWorldMapCountryAliases || {};
      const countryNames = {};
      Object.entries(countryAliases).forEach(([key, code]) => {
        if (key.length > 2 && !countryNames[code]) countryNames[code] = humanize(key);
      });
      const normalizeCountryToken = (value) => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9]+/g, '').toUpperCase();
      const countryCode = (row) => {
        const candidates = [row.region_country, row.canonical_region_id, row.region_identity, row.region, row.region_display_name];
        for (const candidate of candidates) {
          const token = normalizeCountryToken(candidate);
          if (!token) continue;
          const resolved = countryAliases[token] || (/^[A-Z]{2}$/.test(token) ? token.toLowerCase() : null);
          if (resolved) return resolved;
        }
        return null;
      };
      const countryCoverage = (installRows) => {
        const byCountry = {};
        installRows.forEach((row) => {
          const code = countryCode(row);
          if (!code) return;
          const providerId = row.provider_id || 'unknown';
          const countValue = operations(row);
          byCountry[code] ||= {code, count: 0, last: row.last_occurred_at, providers: {}};
          byCountry[code].count += countValue;
          if (String(row.last_occurred_at || '') > String(byCountry[code].last || '')) byCountry[code].last = row.last_occurred_at;
          byCountry[code].providers[providerId] ||= {id: providerId, count: 0};
          byCountry[code].providers[providerId].count += countValue;
        });
        return Object.values(byCountry);
      };
      const showWorldMapTooltip = (item, code) => {
        if (!worldMapTooltip) return;
        const label = item?.name || countryNames[code] || code.toUpperCase();
        const providersMarkup = item?.providers
          ? Object.values(item.providers).sort((a, b) => b.count - a.count || a.id.localeCompare(b.id)).map((providerItem) => `<div class="world-map-provider-line"><span>${escapeHtml(providerName[providerItem.id] || providerItem.id)}</span><strong>${providerItem.count}</strong></div>`).join('')
          : '';
        worldMapTooltip.innerHTML = `<strong>${escapeHtml(label)}</strong><span class="world-map-tooltip-total">${item?.count || 0} installs</span>${providersMarkup || '<span class="world-map-tooltip-empty">No installs</span>'}`;
        worldMapTooltip.hidden = false;
      };
      const renderWorldMap = (installRows) => {
        if (!worldMapSvg) return;
        const items = countryCoverage(installRows);
        const byCountry = Object.fromEntries(items.map((item) => [item.code, item]));
        const maximum = Math.max(0, ...items.map((item) => item.count));
        worldMapSvg.innerHTML = window.terentoWorldMapSvg || '';
        const regions = [...worldMapSvg.querySelectorAll('[id]')];
        regions.forEach((path) => {
          const code = String(path.getAttribute('id') || '').toLowerCase();
          if (!/^[a-z]{2}$/.test(code)) return;
          const item = byCountry[code];
          const intensity = maximum && item ? Math.pow(item.count / maximum, 0.58) : 0;
          const lightness = 97 - (intensity * 48);
          path.classList.add('world-map-country');
          path.style.fill = item && maximum ? `hsl(198 25% ${lightness}%)` : 'var(--surface)';
          path.setAttribute('tabindex', '0');
          path.setAttribute('role', 'button');
          path.setAttribute('aria-label', `${countryNames[code] || code.toUpperCase()}: ${item?.count || 0} installs`);
          path.addEventListener('mouseenter', () => showWorldMapTooltip(item, code));
          path.addEventListener('focus', () => showWorldMapTooltip(item, code));
          path.addEventListener('mouseleave', () => { if (worldMapTooltip) worldMapTooltip.hidden = true; });
          path.addEventListener('blur', () => { if (worldMapTooltip) worldMapTooltip.hidden = true; });
        });
        if (worldMapStatus) worldMapStatus.textContent = maximum ? `${items.length} countries · ${items.reduce((total, item) => total + item.count, 0)} installs` : 'No installs in this period';
        if (worldMapLegendMax) worldMapLegendMax.textContent = maximum ? String(maximum) : 'Most';
        if (worldMap) worldMap.dataset.countryCount = String(items.length);
      };
      const render = (payload) => {
        currentPayload = payload;
        const rows = payload.rows || [];
        const detailRows = payload.detailRows || rows;
        const hasEventData = rows.length > 0;
        const installRows = rows.filter((row) => row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED');
        const selectedProvider = String((payload.filters && payload.filters.provider) || provider?.value || '').trim().toLowerCase();
        const scopedProviders = selectedProvider ? providers.filter((item) => String(item.id || '').trim().toLowerCase() === selectedProvider) : providers;
        const eventRecords = rows.reduce((total, row) => total + Number(row.event_count || row.operation_count || 0), 0);
        const downloads = count(rows, 'DOWNLOAD_SUCCEEDED', 'SUCCEEDED');
        const failedDownloads = count(rows, 'DOWNLOAD_FAILED', 'FAILED');
        const installs = count(rows, 'INSTALL_SUCCEEDED', 'SUCCEEDED');
        const failedInstalls = count(rows, 'INSTALL_FAILED', 'FAILED');
        const set = (key, value) => { const node = document.querySelector(`[data-stat="${key}"]`); if (node) node.textContent = value; };
        set('completedDownloads', hasEventData ? downloads : '—'); set('failedDownloads', hasEventData ? failedDownloads : '—'); set('completedInstalls', hasEventData ? installs : '—'); set('failedInstalls', hasEventData ? failedInstalls : '—');
        set('downloadSuccessRate', hasEventData ? formatRate(downloads + failedDownloads ? downloads / (downloads + failedDownloads) * 100 : null) : '—');
        set('installSuccessRate', hasEventData ? formatRate(installs + failedInstalls ? installs / (installs + failedInstalls) * 100 : null) : '—');
        if (emptyState) emptyState.hidden = hasEventData;
        if (coverage) coverage.hidden = !hasEventData;
        if (popularity) popularity.hidden = !hasEventData;
        if (providerTable) providerTable.hidden = !hasEventData;
        if (eventDetail) eventDetail.closest('.map-events-card').hidden = !hasEventData;
        if (providerHealth) providerHealth.hidden = false;
        const healthyCount = scopedProviders.filter((item) => String(item.health || '').toUpperCase() === 'HEALTHY').length;
        const issueCount = scopedProviders.reduce((total, item) => total + providerIssueCount(item), 0);
        set('providerHealth', `${healthyCount} / ${scopedProviders.length} healthy`);
        set('providerHealthIssues', ` · ${issueCount} issues`);
        set('providerIssues', issueCount);
        const byProvider = Object.fromEntries(scopedProviders.map((item) => [item.id, {downloads: 0, installs: 0, failedInstalls: 0}]));
        rows.forEach((row) => { const id = row.provider_id || 'unknown'; byProvider[id] ||= {downloads: 0, installs: 0, failedInstalls: 0}; if (row.event_type === 'DOWNLOAD_SUCCEEDED' && row.outcome === 'SUCCEEDED') byProvider[id].downloads += operations(row); if (row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED') byProvider[id].installs += operations(row); if (row.event_type === 'INSTALL_FAILED' && row.outcome === 'FAILED') byProvider[id].failedInstalls += operations(row); });
        const providerRows = Object.entries(byProvider).sort((a, b) => b[1].downloads - a[1].downloads || a[0].localeCompare(b[0])).map(([id, item]) => `<tr><td>${escapeHtml(providerName[id] || id)}</td><td class="numeric">${item.downloads}</td><td class="numeric">${item.installs}</td><td>${formatRate(item.installs + item.failedInstalls ? item.installs / (item.installs + item.failedInstalls) * 100 : null)}</td><td>${badge(healthByProvider[id])}</td></tr>`).join('');
        document.querySelector('#provider-statistic-rows').innerHTML = providerRows || emptyRow(5);
        renderWorldMap(installRows);
        const byMap = {};
        installRows.forEach((row) => { const key = `${row.provider_id || 'unknown'}\u0000${row.map_package_id || 'unknown'}\u0000${row.region || '—'}`; byMap[key] ||= {map: row.map_package_id || '—', name: row.display_name || row.map_package_name || '', provider: row.provider_id || '', region: row.region || '—', regionIdentity: row.region_identity || row.canonical_region_id || row.region || 'UNKNOWN', regionName: row.region_display_name || humanize(row.region), count: 0, last: row.last_occurred_at}; byMap[key].count += operations(row); if (String(row.last_occurred_at || '') > String(byMap[key].last || '')) byMap[key].last = row.last_occurred_at; });
        const mapItems = Object.values(byMap).sort((a, b) => b.count - a.count || a.map.localeCompare(b.map));
        const showAllMaps = Boolean(allMapsDisclosure?.open);
        const mapRow = (item) => `<tr><td><strong>${escapeHtml(item.name || item.regionName || '—')}</strong><small class="table-secondary"><code>${escapeHtml(item.map)}</code> · ${escapeHtml(item.regionName || '—')}</small></td><td>${escapeHtml(providerName[item.provider] || item.provider || '—')}</td><td class="numeric">${item.count}</td><td>${formatTimestamp(item.last)}</td></tr>`;
        if (mapRows) mapRows.innerHTML = (showAllMaps ? mapItems : mapItems.slice(0, 5)).map(mapRow).join('') || emptyRow(4);
        if (allMapsSummary) allMapsSummary.textContent = showAllMaps ? 'Top 5' : 'All maps';
        const byRegion = {};
        Object.values(byMap).forEach((item) => { const key = item.regionIdentity || item.region; byRegion[key] ||= {region: key, display: item.regionName, count: 0, last: item.last}; byRegion[key].count += item.count; if (String(item.last || '') > String(byRegion[key].last || '')) byRegion[key].last = item.last; });
        const topRegions = Object.values(byRegion).sort((a, b) => b.count - a.count || a.region.localeCompare(b.region)).slice(0, 10).map((item) => `<tr><td>${escapeHtml(item.display || humanize(item.region))}</td><td class="numeric">${item.count}</td><td>${formatTimestamp(item.last)}</td></tr>`).join('');
        document.querySelector('#top-region-rows').innerHTML = topRegions || emptyRow(3);
        const detailMarkup = detailRows.map((row) => `<tr><td>${escapeHtml(row.provider_id || '—')}</td><td><code>${escapeHtml(row.map_package_id || '—')}</code></td><td>${escapeHtml(row.region_display_name || humanize(row.region))}</td><td>${escapeHtml(row.event_type || '—')}</td><td>${escapeHtml(outcomeLabel(row.outcome))}</td><td class="numeric">${operations(row)}</td><td>${formatTimestamp(row.last_occurred_at)}</td></tr>`).join('');
        document.querySelector('#map-statistics-rows').innerHTML = detailMarkup || emptyRow(7);
        const eventStatus = rows.length ? `${rows.length} event group${rows.length === 1 ? '' : 's'} · ${eventRecords} event record${eventRecords === 1 ? '' : 's'}` : 'No event groups';
        if (eventSummary) eventSummary.textContent = `Event detail · ${eventStatus}`;
        if (status) status.textContent = eventStatus;
        detailPage = Number(payload.detailPage || 1);
        const total = Number(payload.detailTotal || rows.length || 0);
        const size = Number(payload.detailPageSize || eventPageSize?.value || 25);
        if (eventPageSize && ['25', '50'].includes(String(size))) eventPageSize.value = String(size);
        if (eventPagination) {
          const pages = Math.max(1, Math.ceil(total / size));
          const start = total ? Math.min(total, (detailPage - 1) * size + 1) : 0;
          const end = Math.min(total, detailPage * size);
          eventPagination.querySelector('span').textContent = `Showing ${start}–${end} of ${total} · page ${detailPage} of ${pages}`;
          const previous = eventPagination.querySelector('[data-event-page="previous"]');
          const next = eventPagination.querySelector('[data-event-page="next"]');
          if (previous) previous.disabled = detailPage <= 1;
          if (next) next.disabled = detailPage >= pages;
        }
      };
      const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
      const formatTimestamp = (value) => {
        if (!value) return '—';
        if (typeof window.TerentoAdminTime?.format === 'function') return window.TerentoAdminTime.format(value);
        const normalizedValue = typeof value === 'string'
          ? value.trim().replace(/^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)$/, '$1T$2')
          : value;
        const date = new Date(normalizedValue);
        return Number.isNaN(date.getTime()) ? String(value) : date.toISOString().slice(0, 16).replace('T', ' ');
      };
      const badge = (value) => `<span class="provider-status provider-status-${String(value || 'UNKNOWN').toLowerCase()}">${escapeHtml(String(value || 'UNKNOWN').replace('_', ' '))}</span>`;
      const emptyRow = (columns) => `<tr><td colspan="${columns}" class="muted-value">No events in this period.</td></tr>`;
      const sync = async ({resetDetailPage = false} = {}) => {
        if (resetDetailPage) detailPage = 1;
        const parameters = new URLSearchParams();
        if (provider.value) parameters.set('provider', provider.value);
        if (map.value.trim()) parameters.set('map', map.value.trim());
        if (region.value.trim()) parameters.set('region', region.value.trim());
        if (event.value) parameters.set('eventType', event.value);
        parameters.set('period', range.value || 'all');
        if (filters.dateFrom && !filters.period && range.value === 'all') parameters.set('dateFrom', filters.dateFrom);
        parameters.set('detailPage', String(detailPage));
        parameters.set('detailPageSize', String(eventPageSize?.value || 25));
        if (status) status.textContent = 'Loading…';
        try { const response = await fetch(`/admin/map-statistics.json?${parameters}`, {credentials: 'same-origin', headers: {'Accept': 'application/json'}}); const payload = await response.json(); if (!response.ok) throw new Error(payload.error || 'Statistics unavailable'); render(payload); } catch (error) { if (status) status.textContent = error.message || 'Statistics unavailable'; }
      };
      if (allMapsDisclosure) allMapsDisclosure.addEventListener('toggle', () => render(currentPayload));
      const initialRange = ['24h', '7d', '30d', 'all'].includes(String(filters.period || '')) ? String(filters.period) : 'all'; range.value = initialRange; if (filters.provider) provider.value = filters.provider; if (filters.map) map.value = filters.map; if (filters.region) region.value = filters.region; if (filters.eventType) event.value = filters.eventType;
      if (moreFilters && (filters.map || filters.region || filters.eventType)) moreFilters.open = true;
      [range, provider, event].forEach((control) => control?.addEventListener('change', () => sync({resetDetailPage: true}))); [map, region].forEach((control) => { control?.addEventListener('change', () => sync({resetDetailPage: true})); control?.addEventListener('input', () => sync({resetDetailPage: true})); });
      eventPageSize?.addEventListener('change', () => sync({resetDetailPage: true}));
      eventPagination?.querySelector('[data-event-page="previous"]')?.addEventListener('click', () => { detailPage = Math.max(1, detailPage - 1); sync(); });
      eventPagination?.querySelector('[data-event-page="next"]')?.addEventListener('click', () => { detailPage += 1; sync(); });
      window.addEventListener('terento-admin-timezone-ready', () => render(currentPayload));
      window.addEventListener('terento-admin-timezone-change', () => render(currentPayload));
      render(initial);
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


def _identity_device_options(devices: list[dict[str, Any]] | None, current_id: Any = None) -> tuple[str, str]:
    current = str(current_id or "").strip()
    current_label = current or "No canonical device selected"
    options: list[str] = []
    for device in devices or []:
        device_id = str(device.get("device_id") or device.get("id") or "").strip()
        if not device_id:
            continue
        model = str(device.get("model") or "Garmin device").strip()
        variant = _normalise_variant(device.get("variant"))
        family = str(device.get("family_name") or device.get("familyName") or device.get("family") or "").strip()
        label_parts = [part for part in (model, variant if variant != "—" else "", family, device_id) if part]
        label = " · ".join(label_parts)
        if device_id == current:
            current_label = device_id
        options.append(
            f"<option value='{html.escape(label, quote=True)}' data-device-id='{html.escape(device_id, quote=True)}'></option>"
        )
    return "".join(options), current_label


def _operation_state(results: list[dict[str, Any]], *, resolved: bool) -> str:
    if resolved:
        return "resolved"
    if _operation_is_problematic(results) or _operation_issue(results):
        return "open"
    if _identity_is_pending(results):
        return "identity-pending"
    return "history"


def _operation_result(results: list[dict[str, Any]]) -> str:
    outcomes = {str(result.get("phase_outcome") or "").strip().upper() for result in results}
    if any(
        str(result.get("phase_outcome") or "").strip().upper() == "SUCCEEDED"
        and str(result.get("automatic_finishing_result") or "").strip().upper()
        not in {"", "VERIFIED"}
        for result in results
    ):
        return "INCOMPLETE"
    if "FAILED" in outcomes:
        return "FAILED"
    if "NOT_STARTED" in outcomes:
        return "NOT_STARTED"
    if outcomes and outcomes <= {"SUCCEEDED"}:
        return "SUCCEEDED"
    return next(iter(sorted(outcomes)), "UNKNOWN")


def _operation_write_started(results: list[dict[str, Any]]) -> bool:
    return any(result.get("write_started") is not False for result in results)


def _operation_counts_as_installation_attempt(results: list[dict[str, Any]]) -> bool:
    """Count persisted final results independently of device-write progress."""
    result = _operation_result(results)
    if result in {"FAILED", "SUCCEEDED", "INCOMPLETE", "BLOCKED"}:
        return True
    return _operation_write_started(results)


def _operation_text(results: list[dict[str, Any]], field: str, *, fallback: str = "—") -> str:
    values = []
    for result in results:
        value = str(result.get(field) or "").strip()
        if value and value not in values:
            values.append(value)
    return ", ".join(values) if values else fallback


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
        f"#{number} <span aria-hidden='true'>↗</span></a>"
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
            ("Native error", native_code),
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
    issue = _operation_issue(results)
    result_label = _operation_result(results)
    state = _operation_state(results, resolved=resolved)
    identity_pending = _identity_is_pending(results)
    return_to = return_to or _diagnostics_url({
        "compatibility_identity": identity,
        "canonical_device_model_id": canonical_device_model_id,
    })
    options, current_label = _identity_device_options(identity_devices, first.get("canonical_device_model_id"))
    search_id = f"identity-search-{dialog_id}"
    canonical_id = f"identity-canonical-{dialog_id}"
    action_id = f"identity-action-{dialog_id}"
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
    elif state == "open":
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
      <form method='post' action='/admin/diagnostics/identity' class='diagnostic-action-form identity-review-form admin-async-action'>
        <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
        <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
        <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
        <h4>Resolve identity</h4>
        <label>Action<select name='identity_action' id='{action_id}' data-identity-action><option value='ASSIGN'>Assign canonical Garmin device</option><option value='LEAVE_UNRESOLVED'>Leave unresolved</option><option value='NOT_IDENTIFIABLE'>Mark as not identifiable</option></select></label>
        <label data-canonical-device-wrap>Search Garmin device<input id='{search_id}' list='canonical-device-options-{dialog_id}' data-identity-search placeholder='Search model, family, variant, case size, or canonical ID' autocomplete='off'></label>
        <datalist id='canonical-device-options-{dialog_id}'>{options}</datalist>
        <input type='hidden' name='canonical_device_model_id' id='{canonical_id}' value='{html.escape(str(first.get('canonical_device_model_id') or ''), quote=True)}'>
        <p class='identity-selection' data-identity-selection>Canonical ID: <code>{html.escape(current_label)}</code></p>
        <label>Reason <span class='optional-label'>Optional</span><input name='identity_reason' placeholder='Exact model confirmed by operator'></label>
        <label>Review note <span class='optional-label'>Optional</span><textarea name='identity_note' rows='3'></textarea></label>
        <button type='submit'>Save identity review</button>
      </form>""" if identity_pending else ""
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
    issue_form = f"""
      <section class='diagnostic-action-form github-review github-review-collapsed' aria-labelledby='github-review-{dialog_id}'>
        <h4 id='github-review-{dialog_id}'>GitHub issue</h4>
        <p class='github-current'>{_github_issue_link(issue) if issue else '<span class="muted-value">No linked issue</span>'}</p>
        <p class='table-help'>Closed linked issues resolve this diagnostic after synchronization, normally within 15 minutes. Installation results stay in history.</p>
        <details class='github-issue-disclosure'><summary>{'Manage linked issue' if issue else 'Report an anomaly or link issue'}</summary><div class='github-issue-controls'>{issue_controls}</div></details>
      </section>"""
    review_state = ""
    if resolved:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('RESOLVED')}{resolution}</dd></div>"
    elif state == "open":
        identity_badge = f" {_diagnostic_state_badge('IDENTITY_PENDING')}" if identity_pending else ""
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('OPEN')}{identity_badge}</dd></div>"
    elif identity_pending:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('IDENTITY_PENDING')}</dd></div>"
    failure_summary = (
        f"<p class='diagnostic-failure-summary'><strong>Failure reason:</strong> {html.escape(_diagnostic_error_reason(results, resolved=resolved))}</p>"
        if result_label == "FAILED" else ""
    )
    technical_details = f"<details class='diagnostic-technical-details diagnostic-technical-all'><summary>Technical details</summary><p class='diagnostic-id'>Diagnostic ID: <code>{html.escape(operation_key)}</code></p><div class='technical-copy-actions'><button type='button' class='secondary-button' data-copy-diagnostic-id='{html.escape(operation_key, quote=True)}'>Copy diagnostic ID</button><button type='button' class='secondary-button' data-copy-technical-report data-report='{html.escape(issue_body, quote=True)}'>Copy technical report</button><span class='copy-status' data-copy-status role='status' aria-live='polite'></span></div>{technical}</details>"
    return f"""
      <dialog class='diagnostic-detail-dialog' id='{dialog_id}' aria-labelledby='{dialog_id}-title'>
        <div class='diagnostic-detail-inner'>
          <div class='device-dialog-header'><div><p class='section-kicker'>Diagnostic detail</p><h2 id='{dialog_id}-title'>{html.escape(model)}{f' · {html.escape(variant)}' if variant != '—' else ''}</h2></div><button class='dialog-close' type='button' data-close-dialog aria-label='Close diagnostic detail'>×</button></div>
          <dl class='diagnostic-detail-summary'>
            <div><dt>Device</dt><dd>{html.escape(model)}</dd></div>
            <div><dt>Variant</dt><dd>{html.escape(variant)}</dd></div>
            <div><dt>Date</dt><dd>{_timestamp_markup(first.get('occurred_at'))}</dd></div>
            <div><dt>Map / region</dt><dd>{html.escape(_operation_text(results, 'region'))}</dd></div>
            <div><dt>Result</dt><dd>{_diagnostic_result(result_label)}</dd></div>
            <div><dt>App version</dt><dd>{html.escape(_admin_app_version_label(first.get('release_label') or first.get('terento_version'), first.get('app_build')))}</dd></div>
            {review_state}
          </dl>
          {failure_summary}
          <div class='diagnostic-actions-grid'>{lifecycle_action}{identity_form}{issue_form}</div>
          {technical_details}
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


def device_detail_page(
    device: dict[str, Any], user: dict[str, Any], csrf_token: str, *,
    operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    identity_devices: list[dict[str, Any]] | None = None,
    origin: str = "devices",
    requested_state: str | None = None,
) -> bytes:
    device_id = str(device.get("id") or "").strip()
    model = str(device.get("model") or "Unknown Garmin model")
    variant = _normalise_variant(device.get("variant"))
    identity = " · ".join(part for part in (model, variant if variant != "—" else "") if part)

    def matches(event: dict[str, Any]) -> bool:
        return str(event.get("canonical_device_model_id") or "").strip() == device_id

    active_events = [event for event in (operations or []) if matches(event)]
    resolved_events = [event for event in (resolved_operations or []) if matches(event)]
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
        recognized_map_capable_evidence=device.get("mapCapable") is True,
    )
    status_value = status.value if status else ""
    last_activity = _timestamp_markup(stats.get("lastEvidenceAt")) if stats.get("lastEvidenceAt") else "—"
    publication = device.get("publicCompatibility") or {}
    map_label, map_kind = _admin_map_capability(device.get("mapCapable"))
    authorization_label, authorization_kind, _ = _admin_installation_authorization(
        device.get("supportStatus")
    )
    summary_badges = "".join((
        _admin_status_badge(f"Maps: {map_label}", f"map-{map_kind}"),
        _status_badge(status_value),
        _admin_status_badge(authorization_label, f"authorization-{authorization_kind}"),
        _admin_status_badge("Published", "publication-published") if publication.get("published") else "",
    ))
    image_url = (device.get("image") or {}).get("url")
    image = (
        f"<img class='model-page-image' src='{html.escape(str(image_url), quote=True)}' alt='' loading='eager'>"
        if image_url else ""
    )
    back_href = "/admin/installations" if origin == "installations" else "/admin/devices"
    back_label = "Back to Installations" if origin == "installations" else "Back to Devices"
    detail_url = _device_detail_url(device_id, origin=origin)
    public_link = (
        "<a class='secondary-button model-public-link' href='https://terento.app/compatibility/' target='_blank' rel='noreferrer'>View public page <span aria-hidden='true'>↗</span></a>"
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
        map_copy = html.escape(region or "Map not recorded")
        if map_release:
            map_copy += f"<small>{html.escape(map_release)}</small>"
        if result == "FAILED":
            error_state = _diagnostic_state_badge("RESOLVED" if resolved else "OPEN")
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
            f"<td>{_timestamp_markup(first.get('occurred_at'))}</td>"
            f"<td class='history-map'>{map_copy}</td>"
            f"<td>{_diagnostic_result(result)}</td>"
            f"<td class='history-error'>{error_markup}</td>"
            f"<td>{_github_issue_link(issue)}</td>"
            f"<td>{release_markup}</td>"
            f"<td><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='View installation details {index + 1}'>Details</button></td>"
            "</tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity, operation_key, results, resolved=resolved,
            csrf_token=csrf_token, identity_devices=identity_devices,
            canonical_device_model_id=device_id, return_to=detail_url + "#installations",
        ))
    history_rows = "".join(rows_markup) or "<tr><td colspan='7' class='empty'>No installation history for this device.</td></tr>"

    public_copy = (
        f"Published on terento.app/compatibility/ as {html.escape(status.value.title() if status else 'Unavailable')}."
        if publication.get("published") else
        "Not shown on the public compatibility page."
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
    device_info = _detail_rows([
        ("Model", model, False), ("Variant", variant, False),
        ("Family", device.get("familyName") or device.get("family"), False),
        ("Part number", device.get("partNumber"), False),
        ("Lifecycle", lifecycle, False),
        ("Map capability", _admin_status_badge(map_label, f"map-{map_kind}"), True),
        ("Catalog source", catalog_source, False),
        ("Last synced", _timestamp_markup(catalog.get("lastSeenAt")) if catalog.get("lastSeenAt") else None, True),
    ])
    all_events = active_events + resolved_events
    firmware = ", ".join(sorted({str(item.get("firmware_version")).strip() for item in all_events if item.get("firmware_version")}))
    raw_models = ", ".join(sorted({str(item.get("raw_mtp_model")).strip() for item in all_events if item.get("raw_mtp_model")}))
    transports = ", ".join(sorted({str(item.get("transport")).strip() for item in all_events if item.get("transport")}))
    technical_rows = _detail_rows([
        ("Catalog ID", device_id, False),
        ("USB identity", _usb_identity_details(device.get("usbIdentities")), False),
        ("Firmware", firmware, False),
        ("Raw MTP model", raw_models, False),
        ("Transport", transports, False),
    ])
    if not technical_rows:
        technical_rows = "<p class='diagnostic-technical-empty'>Detailed technical data is not available for this record.</p>"

    active_header = "evidence" if origin == "installations" else "devices"
    content = f"""
      {_admin_header(user, csrf_token, active=active_header)}
      <main class='dashboard model-detail-page' id='main-content'>
        <p class='back-link'><a href='{back_href}'>← {back_label}</a></p>
        <header class='model-page-header'>{image}<div class='model-page-heading'><p class='eyebrow'>Garmin device</p><h1>{html.escape(model)}{f' · <span>{html.escape(variant)}</span>' if variant != '—' else ''}</h1><div class='model-page-badges'>{summary_badges}</div></div>{public_link}</header>
        <section class='diagnostic-model-metrics model-statistics' aria-label='Model installation statistics'><article class='attempts-metric' aria-label='Attempts. Successful history plus failures received since the device counter baseline. Resolved failures are counted once.' title='Device snapshot totals information: successful history plus failures since the counter baseline; resolved failures count once. Installations uses write-started evidence.'><span>Attempts</span><strong>{attempts}</strong></article><article><span>Successful</span><strong>{successful}</strong></article><article><span>Failed</span><strong>{failed}</strong></article><article><span>Open errors</span><strong>{open_errors}</strong></article><article class='timestamp-metric'><span>Last activity</span><strong>{last_activity}</strong></article></section>
        {alert}
        <section class='diagnostics-detail-section model-page-section' id='installations' aria-labelledby='installation-history-title'>
          <div class='section-heading'><div><p class='section-kicker'>Operational history</p><h2 id='installation-history-title'>Installation history</h2></div><p class='table-help'>Failed results remain historical after their error is resolved.</p></div>
          <form class='filter-bar diagnostic-filter-bar' id='diagnostic-filters'><div class='quick-filter-group' role='group' aria-label='Quick history filters'><button type='button' class='quick-filter active' data-history-filter='all' aria-pressed='true'>All</button><button type='button' class='quick-filter' data-history-filter='failed' aria-pressed='false'>Failed</button><button type='button' class='quick-filter' data-history-filter='open' aria-pressed='false'>Open errors</button><button type='button' class='quick-filter' data-history-filter='succeeded' aria-pressed='false'>Succeeded</button></div><details class='admin-disclosure filter-disclosure history-more-filters'><summary>More filters</summary><div class='disclosure-body'><label><span class='sr-only'>Filter installation history</span><select id='diagnostic-state-filter'><option value='all'>All</option><option value='succeeded'>Successful</option><option value='failed'>Failed</option><option value='open'>Open errors</option><option value='resolved-errors'>Resolved errors</option></select></label></div></details></form>
          <p class='results-count' id='diagnostic-results-count' aria-live='polite'>{len(history)} records</p>
          <div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table model-history-table'><caption class='sr-only'>Installation history for this exact model and variant</caption><thead><tr><th scope='col'>Date</th><th scope='col'>Map</th><th scope='col'>Result</th><th scope='col'>Error</th><th scope='col'>GitHub issue</th><th scope='col'>App version</th><th scope='col'>Action</th></tr></thead><tbody id='diagnostic-rows'>{history_rows}</tbody></table></div>
          <div class='provider-pagination' id='diagnostic-history-pagination' aria-live='polite'><label>Rows <select id='diagnostic-history-page-size' aria-label='Rows per installation history page'><option value='25' selected>25</option><option value='50'>50</option></select></label><button type='button' data-history-page='previous' disabled>Previous</button><span>Showing {1 if history else 0}–{min(len(history), 25)} of {len(history)} · page 1 of {max(1, (len(history) + 24) // 25)}</span><button type='button' data-history-page='next' {'disabled' if len(history) <= 25 else ''}>Next</button></div>
        </section>
        <details class='model-page-section model-administration admin-disclosure' {'open' if device.get('supportStatus') == 'NOT_EVALUATED' or not publication.get('published') else ''}><summary id='administration-title'>Administration · authorization and publication</summary><div class='administration-grid'>
          <article><h3>Installation authorization</h3><form method='post' action='/admin/devices/authorization' class='admin-async-action' data-authorization-form data-current-authorization='{html.escape(str(device.get('supportStatus') or 'NOT_EVALUATED'), quote=True)}'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='device_id' value='{html.escape(device_id, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(detail_url, quote=True)}'><label>Status<select name='support_status'><option value='SUPPORTED'{' selected' if device.get('supportStatus') == 'SUPPORTED' else ''}>Approved</option><option value='UNSUPPORTED'{' selected' if device.get('supportStatus') == 'UNSUPPORTED' else ''}>Blocked</option><option value='NOT_EVALUATED'{' selected' if device.get('supportStatus') == 'NOT_EVALUATED' else ''}>Pending</option></select></label><label>Note <span class='optional-label'>Optional</span><textarea name='note' rows='2'></textarea></label><button type='submit'>Save authorization</button></form></article>
          <article><h3>Public compatibility</h3><p>{public_copy}</p>{public_form}</article>
        </div></details>
        <details class='model-page-section device-information-section admin-disclosure'><summary id='device-information-title'>Device information</summary><dl class='model-information-list'>{device_info}</dl></details>
        <details class='model-technical-details'><summary>Technical details</summary><dl class='model-information-list'>{technical_rows}</dl></details>
        {''.join(dialogs)}
      </main>
      <script>{_diagnostics_script()}</script>
    """
    return _layout(f"{model} {variant}", content)


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
    ]
    resolved_events = [
        event for event in (resolved_operations or [])
        if matches(event)
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
    attempts = int(model_row.get("attempted_install_count") or 0) if model_row else len(active_groups) + len(resolved_groups)
    successes = int(model_row.get("successful_install_count") or 0) if model_row else sum(
        1 for results in list(active_groups.values()) + list(resolved_groups.values())
        if _operation_result(results) == "SUCCEEDED"
    )
    errors = sum(1 for results in active_diagnostics.values() if _operation_is_problematic(results))
    status = _row_compatibility_status(model_row) if model_row else None
    filters = """<label><span class='sr-only'>Filter installation history</span><select id='diagnostic-state-filter'><option value='all' selected>All</option><option value='succeeded'>Succeeded</option><option value='failed'>Failed</option><option value='open'>Open</option><option value='resolved'>Resolved</option><option value='identity-pending'>Identity pending</option><option value='with-issue'>With issue</option></select></label>"""
    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results, resolved) in enumerate(diagnostic_groups):
        first = results[0]
        state = _operation_state(results, resolved=resolved)
        result = _operation_result(results)
        issue = _operation_issue(results)
        identity_pending = _identity_is_pending(results)
        review_badge = _diagnostic_state_badge(
            "RESOLVED" if resolved else ("OPEN" if state == "open" else ("IDENTITY_PENDING" if identity_pending else "NONE"))
        )
        if state == "open" and identity_pending:
            review_badge += " " + _diagnostic_state_badge("IDENTITY_PENDING")
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr data-diagnostic-state='{state}' data-review-open='{'true' if state == 'open' else 'false'}' data-review-resolved='{'true' if resolved else 'false'}' data-identity-pending='{'true' if identity_pending else 'false'}' data-diagnostic-result='{html.escape(result.lower(), quote=True)}' data-has-issue='{'true' if issue else 'false'}'>"
            f"<td>{_timestamp_markup(first.get('occurred_at'))}</td>"
            f"<td>{html.escape(_operation_text(results, 'region'))}</td>"
            f"<td>{_diagnostic_result(result)}</td>"
            f"<td>{html.escape(_operation_text(results, 'failure_stage'))}</td>"
            f"<td>{html.escape(_operation_text(results, 'failure_code'))}</td>"
            f"<td>{_github_issue_link(issue)}</td>"
            f"<td>{review_badge}</td>"
            f"<td><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='View installation details {index + 1}'>Details</button></td>"
            "</tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity, operation_key, results, resolved=resolved,
            csrf_token=csrf_token, identity_devices=identity_devices,
            canonical_device_model_id=canonical_device_model_id,
        ))
    rows_body = "".join(rows_markup) or "<tr><td colspan='8' class='empty'>No installation history for this model.</td></tr>"
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class='dashboard diagnostics-page' id='main-content'>
        <p class='back-link'><a href='/admin/installations'>← Installations</a></p>
        <div class='heading-row'><div><p class='eyebrow'>Diagnostics</p><h1>{html.escape(model)}{f' · {html.escape(variant)}' if variant != '—' else ''}</h1><p class='lede'>Exact model and variant diagnostic history.</p></div></div>
        <section class='diagnostic-model-metrics' aria-label='Model diagnostic summary'><article><span>Attempts</span><strong>{attempts}</strong></article><article><span>Successful</span><strong>{successes}</strong></article><article><span>Errors</span><strong>{errors}</strong></article><article><span>Compatibility status</span><strong>{_status_badge(status.value if status else '')}</strong></article></section>
        <section class='diagnostics-detail-section' aria-labelledby='diagnostic-list-title'>
          <div class='section-heading'><div><p class='section-kicker'>Evidence history</p><h2 id='diagnostic-list-title'>Installations</h2></div><p class='table-help'>Successful normal evidence remains historical evidence, not an open problem.</p></div>
          <form class='filter-bar diagnostic-filter-bar' id='diagnostic-filters'>{filters}</form>
          <p class='results-count' id='diagnostic-results-count' aria-live='polite'>{len(diagnostic_groups)} records</p>
          <div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table'><caption class='sr-only'>Installation and diagnostic records for exact model and variant</caption><thead><tr><th scope='col'>Date</th><th scope='col'>Region</th><th scope='col'>Result</th><th scope='col'>Stage</th><th scope='col'>Code</th><th scope='col'>Issue</th><th scope='col'>Review</th><th scope='col'>Action</th></tr></thead><tbody id='diagnostic-rows'>{rows_body}</tbody></table></div>
        </section>
        {''.join(dialogs)}
      </main>
      <script>{_diagnostics_script()}</script>
    """
    return _layout("Installation details", content)


def _admin_map_capability(value: Any) -> tuple[str, str]:
    if value is True:
        return "Yes", "yes"
    if value is False:
        return "No", "no"
    return "Unknown", "unknown"


def _admin_installation_authorization(value: Any) -> tuple[str, str, str]:
    status = str(value or "NOT_EVALUATED").upper()
    labels = {
        "SUPPORTED": ("Approved", "approved", "APPROVED"),
        "UNSUPPORTED": ("Blocked", "blocked", "BLOCKED"),
        "NOT_EVALUATED": ("Pending", "pending", "PENDING"),
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
        map_capable = (
            stored_map_capable if stored_map_capable is not None else classified_map_capable
        )
        evidence_status = calculate_compatibility_status(
            successful_install_count=successful,
            recognized_map_capable_evidence=map_capable is True,
        )
        authorization_label, _, authorization_code = _admin_installation_authorization(
            row.get("support_status")
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
        if asset_url:
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
            "variant": _normalise_variant(row.get("variant")),
            "caseSizeMm": row.get("case_size_mm"),
            "displayType": row.get("display_type"),
            "partNumber": row.get("part_number"),
            "productURL": row.get("product_url"),
            "active": bool(row.get("active", True)),
            "mapCapable": map_capable,
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
            "newThisSync": sync_count("records_added"),
        },
        "sync": {
            "id": sync.get("id") if sync else None,
            "status": sync.get("status") if sync else None,
            "startedAt": _timestamp_iso(sync.get("started_at")) or None if sync else None,
            "completedAt": _timestamp_iso(sync.get("finished_at")) or None if sync else None,
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
    model = str(device.get("model") or "Unknown Garmin model")
    variant = str(device.get("variant") or "—")
    family = str(device.get("familyName") or device.get("family") or "")
    map_label, map_kind = _admin_map_capability(device.get("mapCapable"))
    authorization_label, authorization_kind, _ = _admin_installation_authorization(
        device.get("supportStatus")
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
    return f"""<tr data-device-index='{index}' data-device-url='{html.escape(detail_url, quote=True)}' data-search='{html.escape(search, quote=True)}' data-model='{html.escape(model.lower(), quote=True)}' data-updated='{html.escape(str(catalog.get('updatedAt') or ''), quote=True)}' data-installs='{stats['attempts']}' data-evidence='{html.escape(str(stats.get('lastSuccessfulAt') or ''), quote=True)}' data-status='{html.escape(evidence_status.lower())}' tabindex='0' role='link' aria-label='Open {html.escape(model)}{f', {html.escape(variant)}' if variant != '—' else ''}'>
      <td><a class='device-model-button' href='{html.escape(detail_url, quote=True)}'>{image}<span class='device-model-copy'><strong>{html.escape(model)}</strong>{new_badge}</span></a></td>
      <td>{html.escape(variant)}</td>
      <td>{_admin_status_badge(map_label, f'map-{map_kind}')}</td>
      <td>{_admin_status_badge(authorization_label, f'authorization-{authorization_kind}')}</td>
      <td>{_status_badge(evidence_status)}</td>
      <td class='numeric'>{stats['attempts']}</td>
      <td class='numeric'>{stats['successful']}</td>
      <td>{last_success}</td>
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
    empty = "<p class='empty'>No Garmin device records are available.</p>" if not rows_html else ""
    payload_json = json.dumps({**payload, "csrfToken": csrf_token}, ensure_ascii=False).replace("<", "\\u003c")
    mobile_sort_options = "".join(
        f"<option value='{key}:{direction}'>{label} · {suffix}</option>"
        for key, label in [("model", "Model"), ("variant", "Variant"), ("maps", "Map capability"),
                           ("authorization", "Authorization"), ("status", "Compatibility"),
                           ("attempts", "Attempts"), ("success", "Successful"), ("evidence", "Last success")]
        for direction, suffix in [("ascending", "ascending"), ("descending", "descending")]
    )
    table_header = _device_table_header()
    table_columns = _device_table_columns()
    content = f"""
      {_admin_header(user, csrf_token, active="devices")}
      <main class="dashboard devices-page" id="main-content">
        <div class="heading-row"><div><p class="eyebrow">Catalog</p><h1>Devices</h1><p class="lede">Garmin device catalog, map capability, authorization, and compatibility evidence.</p></div></div>
        <section class="admin-summary-strip device-summary-strip" aria-label="Device catalog summary and sync">
          <p class="device-summary-metrics"><strong>{summary['models']} devices</strong><span> · {summary['mapCapable']} map-capable · {summary['approved']} approved · {summary['successful']} successful installs</span></p>
          <p class="device-summary-sync"><strong>Last sync</strong> {completed}<span> · {sync_line}</span>{f"<span> · {html.escape(str(sync_data['status'] or '').title())}</span>" if sync_data['status'] else ''}</p>
        </section>
        <section class="evidence-section" aria-labelledby="device-list-title">
          <div class="section-heading"><div><p class="section-kicker">Inventory</p><h2 id="device-list-title">Known devices</h2></div><p class="table-help">Times follow the selected time zone</p></div>
          <p class="sr-only">Compatibility status and installation counts remain backend-derived.</p>
          <form class="filter-bar admin-filter-bar device-filter-bar" id="device-filters" role="search">
            <label class="filter-search"><span class="sr-only">Search devices</span><input id="device-search" type="search" placeholder="Search devices" autocomplete="off"></label>
            <label><span class="sr-only">Filter by family</span><select id="device-family"><option value="all">All families</option>{family_options}</select></label>
            <label><span class="sr-only">Filter by map capability</span><select id="device-map"><option value="yes" selected>Maps: Yes</option><option value="no">Maps: No</option><option value="unknown">Maps: Unknown</option><option value="all">All maps</option></select></label>
            <label><span class="sr-only">Filter by installation authorization</span><select id="device-support"><option value="all">All authorizations</option><option value="SUPPORTED">Approved</option><option value="UNSUPPORTED">Blocked</option><option value="NOT_EVALUATED">Pending</option></select></label>
            <label><span class="sr-only">Filter by compatibility status</span><select id="device-status"><option value="all">All statuses</option><option value="TESTING">Testing</option><option value="TESTED">Tested</option><option value="SUPPORTED">Supported</option><option value="VERIFIED">Verified</option><option value="unavailable">Unavailable</option></select></label>
            <label class="device-mobile-sort"><span class="sr-only">Sort devices</span><select id="device-mobile-sort">{mobile_sort_options}</select></label>
            <p class="results-count" id="device-results-count" aria-live="polite">{summary['mapCapable']} results</p>
          </form>
          {empty}
          <div class="device-sticky-header" id="device-sticky-header"><div class="device-sticky-header-scroll"><table class="admin-table"><caption class="sr-only">Device catalog columns</caption>{table_columns}{table_header}</table></div></div>
          <div class="table-wrap device-table-wrap"><table class="admin-table"><caption class="sr-only">Device catalog and Terento installation evidence</caption>{table_columns}{table_header}<tbody id="device-rows">{rows_html}</tbody></table></div>
          <div class="device-pagination" id="device-pagination" hidden><button type="button" id="device-previous">Previous</button><span id="device-page-status"></span><button type="button" id="device-next">Next</button></div>
        </section>
      </main>
      <script>const terentoAdminDevices = {payload_json};{_devices_script()}</script>
    """
    return _layout("Devices", content)


def _device_table_header() -> str:
    return """<thead><tr><th scope="col" aria-sort="ascending"><button type="button" class="device-sort-button" data-device-sort="model" aria-label="Model">Model <span aria-hidden="true">↑</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="variant" aria-label="Variant">Variant <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="maps" aria-label="Map capability" title="Map capability">Maps <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="authorization" aria-label="Installation authorization" title="Installation authorization">Authorization <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="status" aria-label="Compatibility status" title="Compatibility status">Status <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="attempts" aria-label="Install attempts" title="Install attempts">Attempts <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="success" aria-label="Successful installations" title="Successful installations">Successful <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="evidence" aria-label="Last successful installation" title="Last successful installation">Last success <span aria-hidden="true">↕</span></button></th></tr></thead>"""


def _device_table_columns() -> str:
    return """<colgroup class="device-table-columns"><col class="device-column-model"><col class="device-column-variant"><col class="device-column-maps"><col class="device-column-authorization"><col class="device-column-status"><col class="device-column-attempts"><col class="device-column-successful"><col class="device-column-last-success"></colgroup>"""


def _campaign_info(control_id: str, title: str, body: str) -> str:
    info_id = f"{control_id}-info"
    return (
        f"<button class='info-control' type='button' aria-expanded='false' "
        f"aria-controls='{info_id}' aria-label='More information about {html.escape(title)}'>i</button>"
        f"<div class='info-popover' id='{info_id}' role='status' hidden><strong>{html.escape(title)}</strong>{body}</div>"
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
        <div class="heading-row"><div><p class="eyebrow">Campaigns</p><h1>Campaign links</h1><p class="lede">Create consistent tracking links for Terento campaigns.</p></div></div>
        <section class="campaign-card" aria-labelledby="campaign-builder-title">
          <div class="section-heading"><div><p class="section-kicker">Attribution</p><h2 id="campaign-builder-title">Campaign link builder</h2></div><p class="table-help">Links are generated locally in this browser.</p></div>
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
            <div class="section-heading"><div><p class="section-kicker">Output</p><h2 id="generated-link-title">Generated URL</h2></div></div>
            <p class="incomplete-state" id="incomplete-state" aria-live="polite">Complete the required fields to generate a link.</p>
            <div class="generated-url-row" id="generated-url-row" hidden><output id="generated-url" class="generated-url" aria-live="polite"></output><button id="copy-link" type="button" class="copy-button">Copy link</button><span id="copy-status" class="copy-status" role="status" aria-live="polite"></span></div>
          </section>
          <section class="attribution-preview" aria-labelledby="attribution-title">
            <div><p class="section-kicker">Analytics</p><h2 id="attribution-title">Umami attribution preview</h2><p class="table-help">This preview explains the attribution values; no Umami query parameter is added.</p></div>
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
        {_admin_header(user, csrf_token, active="")}
        <main class="auth-card account" id="main-content"><p class="eyebrow">Admin</p><h1>Account</h1>{notice}
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
) -> str:
    model, variant, identity = _identity_parts(row)
    summary = diagnostic_summary or {}
    attempted = int(summary["attempts"]) if "attempts" in summary else int(row.get("attempted_install_count") or 0)
    successful = int(summary["successful"]) if "successful" in summary else int(row.get("successful_install_count") or 0)
    failed = int(summary["failed"]) if "failed" in summary else int(row.get("failed_install_count") or 0)
    open_errors = int(summary.get("open_errors") or 0)
    status_value = _row_compatibility_status({**row, "successful_install_count": successful})
    status = status_value.value if status_value else ""
    search_text = " ".join((model, variant, str(row.get("family") or ""), identity)).strip()
    activity = max((_timestamp_iso(row.get(key)) for key in ("last_success", "last_failure", "last_evidence")), default="")
    diagnostics_url = _model_detail_url(row)
    pending_count = int(summary.get("identity_pending") or 0)
    model_cell = html.escape(model)
    if pending_count:
        model_cell += (
            f" <span class='identity-pending-indicator' aria-label='{pending_count} identity pending'>"
            "Identity pending</span>"
        )
    open_errors_markup = (
        f"<a class='error-count' href='{html.escape(_model_detail_url(row, state='open'), quote=True)}' aria-label='View {open_errors} open errors'>{open_errors}</a>"
        if open_errors else "0"
    )
    cells = (
        ("", model_cell),
        ("", html.escape(variant)),
        ("", _status_badge(status)),
        ("numeric", html.escape(str(attempted))),
        ("numeric", html.escape(str(successful))),
        ("numeric historical-number", html.escape(str(failed))),
        ("numeric", open_errors_markup),
        ("numeric", _timestamp_markup(row.get("last_success"))),
    )
    return (
        f"<tr class='evidence-model-row' data-search='{html.escape(search_text, quote=True)}' data-status='{html.escape(status.lower(), quote=True)}' data-activity='{html.escape(activity, quote=True)}' data-attempts='{attempted}' data-errors='{open_errors}' data-identity-pending='{int(summary.get('identity_pending') or 0)}' data-failed='{str(failed > 0).lower()}' data-successful='{str(successful > 0).lower()}' data-diagnostics-url='{html.escape(diagnostics_url, quote=True)}' tabindex='0' role='link' aria-label='Open {html.escape(model)}{f', {html.escape(variant)}' if variant != '—' else ''}'>"
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
      let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}'); } catch (_) { saved = {}; }
      const setSelect = (control, key, fallback) => {
        const requested = parameters.has(key) ? parameters.get(key) : saved[key];
        control.value = [...control.options].some((option) => option.value === requested) ? requested : fallback;
      };
      search.value = parameters.has('search') ? parameters.get('search') : (saved.search || '');
      setSelect(family, 'family', 'all');
      setSelect(map, 'maps', 'yes');
      setSelect(support, 'authorization', 'all');
      setSelect(status, 'status', 'all');
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
      const authorizationOrder = {NOT_EVALUATED: 0, UNSUPPORTED: 1, SUPPORTED: 2};
      const compareLastSuccess = __TERENTO_LAST_SUCCESS_COMPARATOR__;
      const sortValue = (device, key) => ({
        model: device.model,
        variant: device.variant,
        maps: mapOrder[mapValue(device)],
        authorization: authorizationOrder[device.supportStatus || 'NOT_EVALUATED'],
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
          const matchesAuthorization = support.value === 'all' || (device.supportStatus || 'NOT_EVALUATED') === support.value;
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
    return script.replace(
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
      if (!form || !search || !status || !sort || !body || !count || !quickFilters.length) return;
      const rows = [...body.querySelectorAll('tr')];
      const storageKey = 'terento.admin.installations.filters';
      const parameters = new URLSearchParams(window.location.search);
      let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}'); } catch (_) { saved = {}; }
      search.value = parameters.has('search') ? parameters.get('search') : (saved.search || '');
      const quickFilterValues = quickFilters.map((button) => button.dataset.installationFilter);
      let selectedQuickFilter = parameters.get('state') || saved.quick || 'all';
      if (!quickFilterValues.includes(selectedQuickFilter)) selectedQuickFilter = 'all';
      const restoreSelect = (control, key, fallback) => {
        const value = parameters.has(key) ? parameters.get(key) : saved[key];
        control.value = [...control.options].some((option) => option.value === value) ? value : fallback;
      };
      restoreSelect(status, 'status', 'all');
      restoreSelect(sort, 'sort', 'latest');
      const refresh = () => {
        const searchQuery = search.value.trim().toLocaleLowerCase();
        const selectedStatus = status.value;
        const visible = rows.filter((row) => {
          const matchesSearch = !searchQuery || row.dataset.search.toLocaleLowerCase().includes(searchQuery);
          const matchesStatus = selectedStatus === 'all' || row.dataset.status === selectedStatus;
          const matchesQuick = selectedQuickFilter === 'all'
            || (selectedQuickFilter === 'failed' && row.dataset.failed === 'true')
            || (selectedQuickFilter === 'open' && Number(row.dataset.errors || 0) > 0)
            || (selectedQuickFilter === 'successful' && row.dataset.successful === 'true')
            || (selectedQuickFilter === 'identity-pending' && Number(row.dataset.identityPending || 0) > 0);
          row.hidden = !(matchesSearch && matchesStatus && matchesQuick);
          return !row.hidden;
        });
        visible.sort((a, b) => {
          if (sort.value === 'latest') return (b.dataset.activity || '').localeCompare(a.dataset.activity || '');
          if (sort.value === 'errors') return Number(b.dataset.errors || 0) - Number(a.dataset.errors || 0);
          if (sort.value === 'model') return (a.dataset.search || '').localeCompare(b.dataset.search || '');
          return Number(b.dataset.attempts || 0) - Number(a.dataset.attempts || 0);
        });
        visible.forEach((row) => body.appendChild(row));
        count.textContent = `${visible.length} ${visible.length === 1 ? 'variant' : 'variants'}`;
        quickFilters.forEach((button) => {
          const active = button.dataset.installationFilter === selectedQuickFilter;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const state = {search: search.value, status: status.value, sort: sort.value, quick: selectedQuickFilter};
        try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* optional */ }
        const stateQuery = new URLSearchParams();
        if (search.value) stateQuery.set('search', search.value);
        if (selectedQuickFilter !== 'all') stateQuery.set('state', selectedQuickFilter);
        if (status.value !== 'all') stateQuery.set('status', status.value);
        if (sort.value !== 'latest') stateQuery.set('sort', sort.value);
        history.replaceState(null, '', stateQuery.size ? `${window.location.pathname}?${stateQuery}` : window.location.pathname);
      };
      form.addEventListener('submit', (event) => event.preventDefault());
      quickFilters.forEach((button) => button.addEventListener('click', () => {
        selectedQuickFilter = button.dataset.installationFilter || 'all';
        refresh();
      }));
      [search, status, sort].forEach((control) => control.addEventListener('input', refresh));
      rows.forEach((row) => {
        const open = () => { if (row.dataset.diagnosticsUrl) window.location.href = row.dataset.diagnosticsUrl; };
        row.addEventListener('click', (event) => {
          if (event.target.closest('a,button,input,select,textarea')) return;
          open();
        });
        row.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
        });
      });
      refresh();
    })();"""


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
        count.textContent = `${matching.length} ${label}`;
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
        if (summary) summary.textContent = `Showing ${start}–${end} of ${matching.length} · page ${page} of ${pages}`;
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
      document.querySelectorAll('form[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
        if (!window.confirm(form.dataset.confirm || 'Continue?')) event.preventDefault();
      }));
      document.querySelectorAll('[data-authorization-form]').forEach((form) => form.addEventListener('submit', (event) => {
        const current = form.dataset.currentAuthorization;
        const next = form.querySelector('select[name="support_status"]')?.value;
        if (current === 'SUPPORTED' && next !== 'SUPPORTED'
          && !window.confirm('Reduce installation authorization? This changes the operator decision but does not alter compatibility evidence or installation history.')) {
          event.preventDefault();
        }
      }));
      document.querySelectorAll('form.admin-async-action').forEach((form) => form.addEventListener('submit', async (event) => {
        if (event.defaultPrevented) return;
        event.preventDefault();
        if (form.dataset.submitting === 'true') return;
        const formData = new FormData(form);
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
          if (!response.ok) throw new Error(`Save failed (${response.status})`);
          if (response.redirected) {
            window.location.assign(response.url);
          } else {
            window.location.reload();
          }
        } catch (_) {
          controls.forEach((control) => {
            control.disabled = control.dataset.preSubmitDisabled === 'true';
            delete control.dataset.preSubmitDisabled;
          });
          if (submit) submit.textContent = originalLabel;
          status.textContent = 'Could not save. Check the values and try again.';
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
      filter?.addEventListener('input', () => { selectedFilter = filter.value; page = 1; refresh(); });
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
          const focusable = [...dialog.querySelectorAll('button,select,input,textarea,a')]
            .filter((element) => !element.disabled && element.offsetParent !== null);
          if (!focusable.length) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        dialog.querySelectorAll('[data-identity-action]').forEach((action) => {
          const form = action.closest('form');
          const wrap = form?.querySelector('[data-canonical-device-wrap]');
          const search = form?.querySelector('[data-identity-search]');
          const canonical = form?.querySelector('input[name="canonical_device_model_id"]');
          const selection = form?.querySelector('[data-identity-selection]');
          const sync = () => {
            const assign = action.value === 'ASSIGN';
            if (wrap) wrap.hidden = !assign;
            if (canonical) canonical.required = assign;
            if (search && canonical && selection) {
              const option = [...document.querySelectorAll(`#${search.getAttribute('list')} option`)].find((item) => item.value === search.value);
              if (option) canonical.value = option.dataset.deviceId || '';
              if (assign) selection.textContent = `Canonical ID: ${canonical.value || 'No device selected'}`;
            }
          };
          action.addEventListener('change', sync);
          search?.addEventListener('input', sync);
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
      const supportedTimeZones = typeof Intl.supportedValuesOf === 'function'
        ? Intl.supportedValuesOf('timeZone') : [];
      const timeZones = ['browser', 'UTC', browserTimeZone, ...commonTimeZones, ...supportedTimeZones]
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
:root{--admin-control-height:38px;--admin-control-radius:8px;--admin-control-padding-x:10px;--admin-control-font-size:13px;--admin-topbar-height:68px;--max-width:1440px}
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
.admin-action-dialog button:not(.secondary-button),.auth-card button:not(.link-button),.copy-button,.device-support-review button[type="submit"],.model-administration button[type="submit"]{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}
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
.needs-review-menu{position:relative}
.needs-review-menu summary{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:6px 8px;border:1px solid color-mix(in srgb,var(--stone) 45%,var(--border));border-radius:var(--admin-control-radius);background:color-mix(in srgb,var(--stone) 10%,var(--off-white));color:var(--graphite);cursor:pointer;list-style:none;font-weight:700}
.needs-review-menu summary::-webkit-details-marker{display:none}
.needs-review-menu summary:focus-visible{outline:3px solid var(--admin-focus-ring);outline-offset:2px}
.needs-review-count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--stone);color:var(--surface);font-size:10px;font-weight:800}
.needs-review-popover{position:absolute;z-index:20;top:calc(100% + 7px);right:0;width:230px;padding:7px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.16)}
.needs-review-popover a{display:flex!important;justify-content:space-between;gap:12px;width:100%;padding:8px 9px!important;color:var(--graphite)!important}
.needs-review-popover strong{font-variant-numeric:tabular-nums}
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
h1,h2{margin:0;font-family:var(--font-brand);letter-spacing:-.035em}
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
.table-wrap{max-height:none;overflow-x:auto;overflow-y:visible;background:var(--surface);border:1px solid var(--border);border-radius:14px}
table{border-collapse:collapse;width:100%;min-width:1060px}
th,td{padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);text-align:left;white-space:nowrap;vertical-align:middle}
thead th{background:var(--surface);box-shadow:0 1px 0 var(--border);color:var(--secondary);font-size:11px;font-weight:750;letter-spacing:.07em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:0}
tbody tr[hidden]{display:none}
td:nth-child(1){font-weight:650}
td:nth-child(4),td:nth-child(5),td:nth-child(6),td:nth-child(7){font-variant-numeric:tabular-nums}.numeric{font-variant-numeric:tabular-nums}
.muted-value{color:var(--secondary)}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:700}
.evidence-table-wrap table{min-width:760px}.evidence-model-row{cursor:pointer}.evidence-model-row:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}.evidence-model-row:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:-3px}.evidence-model-row td:nth-child(3),.evidence-model-row td:nth-child(4){font-variant-numeric:tabular-nums}.error-count{text-decoration:none}.identity-pending-indicator{display:inline-flex;align-items:center;margin-left:6px;padding:3px 6px;border:1px solid var(--border);border-radius:999px;color:var(--secondary);font-size:10px;font-weight:700;white-space:nowrap}.evidence-table-note{margin:10px 3px 0}.back-link{margin:0 0 20px;color:var(--interactive);font-size:13px;font-weight:700}.back-link a{text-underline-offset:3px}.diagnostic-model-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 30px}.diagnostic-model-metrics article{min-height:82px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.diagnostic-model-metrics span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.diagnostic-model-metrics strong{display:block;margin-top:4px;font-family:var(--font-brand);font-size:25px;line-height:1.15}.diagnostic-model-metrics .status-badge{margin-top:5px}.diagnostic-filter-bar{justify-content:flex-start}.diagnostic-list-wrap{max-height:min(70vh,720px)}.diagnostic-list-table{min-width:920px}.diagnostic-list-table th,.diagnostic-list-table td{white-space:normal;overflow-wrap:anywhere}.diagnostic-list-table td:first-child{white-space:nowrap}.diagnostic-list-table th:last-child,.diagnostic-list-table td:last-child{text-align:right}.diagnostic-list-table tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}.diagnostic-state{display:inline-flex;align-items:center;min-height:24px;padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-state-open{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}.diagnostic-state-resolved{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}.diagnostic-state-identity_pending{background:var(--surface-muted);color:var(--secondary)}.diagnostic-list-table .github-issue,.github-current .github-issue{color:var(--interactive);font-weight:700;white-space:nowrap}.diagnostic-detail-dialog{width:min(860px,calc(100% - 32px));max-height:min(900px,calc(100% - 32px));padding:0;border:0;border-radius:16px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}.diagnostic-detail-dialog::backdrop{background:rgba(34,42,43,.34)}.diagnostic-detail-inner{max-height:min(900px,calc(100vh - 32px));padding:24px;overflow:auto}.diagnostic-detail-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px;margin:0;border-top:1px solid var(--border)}.diagnostic-detail-summary div{display:grid;grid-template-columns:minmax(95px,.8fr) minmax(0,1.2fr);gap:12px;padding:9px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-detail-summary dt{color:var(--secondary);font-size:12px}.diagnostic-detail-summary dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.diagnostic-actions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:22px}.diagnostic-action-form{min-width:0;padding:14px;background:var(--surface-muted);border-radius:10px}.diagnostic-action-form h4{margin:0 0 10px;font-size:13px}.diagnostic-action-form label{display:block;margin:10px 0;color:var(--graphite);font-size:12px;font-weight:650}.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{display:block;width:100%;margin-top:5px;min-height:36px;padding:7px 9px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite);font-size:12px}.diagnostic-action-form textarea{resize:vertical}.diagnostic-action-form button{margin-top:6px}.identity-selection{margin:8px 0;color:var(--secondary);font-size:11px}.identity-selection code{color:var(--graphite);font-family:var(--font-mono);overflow-wrap:anywhere}.github-review{grid-column:1/-1}.github-current{margin:0 0 8px;font-size:13px}.github-actions{margin:0 0 4px}.github-link-form{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px}.github-link-form label{margin:0}.github-link-form button{white-space:nowrap}.github-remove-form{display:inline-block;margin:8px 0 0}.diagnostic-technical-all{margin-top:16px}.diagnostic-technical-all>summary{font-size:13px}
.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius)}
.github-issue-disclosure{margin-top:8px}.github-issue-disclosure>summary{width:max-content;cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750;text-underline-offset:3px}.github-issue-disclosure>summary:hover{text-decoration:underline}.github-issue-controls{margin-top:12px}
.diagnostic-id{font-size:11px!important;color:var(--secondary)!important}.diagnostic-id code{font-size:10px;color:var(--secondary)}.diagnostic-result{display:inline-flex;align-items:center;min-height:22px;padding:4px 7px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-result-succeeded{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}.diagnostic-result-failed{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}.diagnostic-result-not-started,.diagnostic-result-unknown{background:var(--surface-muted);color:var(--secondary)}.diagnostic-chip{display:inline-flex;align-items:center;min-height:21px;padding:3px 7px;border:1px solid var(--border);border-radius:999px;background:var(--surface-muted);color:var(--secondary);font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-chip.github-issue{color:var(--interactive)}.diagnostic-technical-details{margin:10px 0 0;padding:9px 11px;background:var(--surface-muted);border-radius:8px}.diagnostic-technical-details summary{cursor:pointer;color:var(--secondary);font-size:12px;font-weight:700}.diagnostic-technical-details dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px;margin:10px 0 0}.diagnostic-technical-details dl div{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-top:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-technical-details dt{color:var(--secondary);font-size:11px}.diagnostic-technical-details dd{margin:0;text-align:right;font:500 11px var(--font-mono);overflow-wrap:anywhere}
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
.provider-table-wrap table{min-width:980px}.provider-name-link{display:flex;flex-direction:column;gap:2px;text-decoration:none}.provider-name-link:hover strong{text-decoration:underline}.provider-name-link small{color:var(--secondary);font:500 11px var(--font-mono)}.provider-table-wrap code{font:500 11px var(--font-mono);overflow-wrap:anywhere}.provider-status{display:inline-flex;align-items:center;justify-content:center;min-height:25px;padding:5px 8px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;text-transform:uppercase;white-space:nowrap}.provider-status-active,.provider-status-healthy,.provider-status-succeeded{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}.provider-status-paused,.provider-status-unknown,.provider-status-running{background:var(--surface-muted);color:var(--secondary)}.provider-status-retired,.provider-status-down,.provider-status-failed{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}.provider-status-degraded{background:var(--status-tested-surface);border-color:var(--status-tested-border);color:var(--status-tested-text)}.provider-broken-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:750}.provider-error{display:block;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--danger);font-size:12px}.provider-table-wrap .numeric{text-align:right;font-variant-numeric:tabular-nums}.provider-action-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 20px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.provider-action-bar .admin-action-status{flex:1 1 180px;margin:0}.provider-activation-note{flex:1 1 100%;margin:2px 0 0;padding:9px 11px;border:1px solid var(--status-tested-border);border-radius:8px;background:var(--status-tested-surface);color:var(--status-tested-text);font-size:12px;line-height:1.45}.provider-heading-status{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.provider-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 24px}.provider-metrics article{min-width:0;min-height:84px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.provider-metrics article>span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.provider-metrics article>strong{display:block;margin-top:6px;font-family:var(--font-brand);font-size:20px;line-height:1.15}.provider-metrics article>strong .admin-timestamp{font-size:15px}.provider-card{margin-top:24px;padding:22px 24px;background:var(--surface);border:1px solid var(--border);border-radius:14px}.provider-card .section-heading{margin-bottom:16px}.provider-card .section-heading h2{font-size:20px}.provider-information-list{margin:0;border-top:1px solid var(--border)}.provider-information-list div{display:grid;grid-template-columns:minmax(150px,.45fr) minmax(0,1.55fr);gap:18px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.provider-information-list dt{color:var(--secondary);font-size:12px}.provider-information-list dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.provider-information-list a,.provider-url-cell a{color:var(--interactive);text-underline-offset:3px}.provider-package-broken{background:color-mix(in srgb,var(--error-surface) 35%,var(--surface))}.provider-package-broken small{display:block;margin-top:3px;color:var(--danger);font-size:10px}.provider-component-list{display:flex;gap:5px;flex-wrap:wrap}.provider-component{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.provider-component .provider-status{min-height:21px;padding:4px 6px;font-size:9px}.provider-history-wrap table{min-width:1240px}.provider-dashboard-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.provider-dashboard-grid .provider-card{min-width:0}.map-statistics-filter-bar label{flex:0 1 auto}.map-statistics-filter-bar input,.map-statistics-filter-bar select{min-width:130px}.map-statistics-filter-bar .results-count{flex:1 1 120px}.map-statistics-metrics{grid-template-columns:repeat(6,minmax(0,1fr));margin-top:18px}.map-statistics-metrics article>strong{font-size:24px}.map-statistics-metrics article>strong .admin-timestamp{font-size:20px}
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
.model-page-header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:20px;margin:0 0 24px}.model-page-image{width:96px;height:96px;object-fit:contain;border-radius:14px;background:var(--surface)}.model-page-heading h1 span{color:var(--secondary);font-size:.55em;font-weight:500;letter-spacing:-.01em}.model-page-badges{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:12px}.model-public-link{align-self:start;text-decoration:none}.model-statistics{grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:20px}.model-review-alert{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 26px;padding:12px 14px;border:1px solid color-mix(in srgb,var(--stone) 48%,var(--border));border-radius:10px;background:color-mix(in srgb,var(--stone) 9%,var(--surface));font-size:13px}.model-review-alert a{color:var(--interactive);font-weight:750;white-space:nowrap}.model-page-section{scroll-margin-top:calc(var(--admin-topbar-height) + 18px);margin-top:34px}.model-history-table{min-width:980px}.model-history-table th:nth-child(1){width:15%}.model-history-table th:nth-child(2){width:16%}.model-history-table th:nth-child(3){width:11%}.model-history-table th:nth-child(4){width:23%}.model-history-table th:nth-child(5){width:12%}.model-history-table th:nth-child(6){width:15%}.model-history-table th:nth-child(7){width:8%}.history-map small,.history-error small{display:block;margin-top:3px;color:var(--secondary);font-size:10px}.administration-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.administration-grid article{padding:18px;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.administration-grid h3{margin:0 0 12px;font:700 17px var(--font-brand)}.administration-grid p{color:var(--secondary);font-size:13px}.administration-grid form{display:grid;gap:10px}.administration-grid label{color:var(--secondary);font-size:12px;font-weight:650}.administration-grid label select,.administration-grid label textarea{display:block;width:100%;margin-top:5px}.model-information-list{margin:0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.model-information-list div{display:grid;grid-template-columns:minmax(170px,.7fr) minmax(0,1.3fr);gap:18px;padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.model-information-list div:last-child{border-bottom:0}.model-information-list dt{color:var(--secondary);font-size:12px}.model-information-list dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.model-technical-details{margin-top:18px;padding:14px;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.model-technical-details>summary{cursor:pointer;color:var(--interactive);font-weight:750}.model-technical-details .model-information-list{margin-top:12px}.github-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.github-issue-preview{margin:10px 0}.github-issue-preview>summary{cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750}.github-issue-preview input,.github-issue-preview textarea{font-family:var(--font-mono)!important}.technical-copy-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}.diagnostic-technical-empty{margin:10px 0;color:var(--secondary);font-size:12px}
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
.map-statistics-kpis{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:18px}.map-statistics-kpis article>strong{font-size:25px}.map-statistics-empty{margin:0 0 18px;padding:28px 24px;border:1px dashed var(--border);border-radius:14px;background:var(--surface);text-align:center}.map-statistics-empty h2{font-size:20px}.map-statistics-empty p{margin:8px 0 0;color:var(--secondary);font-size:13px}.map-statistics-reliability{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 24px}.map-statistics-reliability div{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--surface-muted)}.map-statistics-reliability span{color:var(--secondary);font-size:12px;font-weight:650}.map-statistics-reliability strong{font-family:var(--font-brand);font-size:19px;font-variant-numeric:tabular-nums}.map-statistics-provider-health{display:flex;align-items:center;gap:8px;margin:0 0 24px;color:var(--secondary);font-size:12px}.map-statistics-provider-health strong{color:var(--graphite);font-weight:750}.map-statistics-provider-health em{font-style:normal}.popularity-subsection+.popularity-subsection{margin-top:18px}.popularity-subsection h3{margin:0 0 9px;font:700 14px var(--font-brand);letter-spacing:-.01em}.map-events-card{margin-top:24px}
.admin-disclosure{margin:0}.admin-disclosure>summary{cursor:pointer;color:var(--interactive);font-size:13px;font-weight:750;list-style-position:inside;text-underline-offset:3px}.admin-disclosure>summary:hover{text-decoration:underline}.admin-disclosure>summary:focus-visible{outline:3px solid var(--admin-focus-ring);outline-offset:3px}.disclosure-body{margin-top:14px}.filter-disclosure{align-self:stretch;min-width:130px;position:relative}.filter-disclosure>summary{display:flex;align-items:center;justify-content:center;height:var(--admin-control-height);padding:8px 10px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-size:var(--admin-control-font-size);font-weight:650;list-style:none;text-decoration:none}.filter-disclosure>summary::-webkit-details-marker{display:none}.filter-disclosure .disclosure-body{display:flex;gap:8px;flex-wrap:wrap;position:absolute;z-index:5;margin-top:7px;padding:8px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.14)}.filter-disclosure .disclosure-body label{display:flex}.filter-disclosure .disclosure-body input,.filter-disclosure .disclosure-body select{min-width:140px}.inline-filter-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px}.inline-filter-row label{display:flex;flex:1 1 220px}.inline-filter-row select{flex:0 1 170px}.provider-pagination{display:flex;align-items:center;justify-content:center;gap:14px;min-height:34px;margin-top:12px;color:var(--secondary);font-size:12px;text-align:center}.provider-pagination button{min-height:34px;padding:7px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--interactive);font:700 12px var(--font-ui)}.provider-pagination button:hover:not(:disabled){border-color:var(--interactive);background:var(--success-bg)}.provider-pagination button:disabled{cursor:not-allowed;opacity:.45}.provider-latest-summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px;border-radius:10px;background:var(--surface-muted);color:var(--secondary);font-size:12px}.provider-latest-summary>div{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.provider-action-overflow{position:relative}.provider-action-overflow>summary{display:inline-flex;align-items:center;justify-content:center;min-height:var(--admin-control-height);padding:8px 12px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);cursor:pointer;font-size:13px;font-weight:700;list-style:none}.provider-action-overflow>summary::-webkit-details-marker{display:none}.provider-action-overflow>summary:hover{border-color:var(--interactive);color:var(--interactive)}.provider-action-overflow>div{position:absolute;z-index:4;right:0;top:calc(100% + 7px);min-width:180px;padding:7px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.14)}.provider-action-overflow button{width:100%}.provider-package-name{display:block;font-weight:700}.provider-package-id{display:block;margin-top:2px;color:var(--secondary)!important;font-size:10px!important}.provider-package-broken td:last-child{color:var(--danger)}.provider-issue-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:750}.audit-technical-details{margin-top:5px}.audit-technical-details summary{cursor:pointer;color:var(--interactive);font-size:11px;font-weight:700}.audit-technical-details code{display:block;margin-top:5px;max-width:300px;overflow:auto;white-space:pre-wrap;font:500 10px var(--font-mono);color:var(--secondary)}.provider-information-list dd{text-align:left}.provider-section .provider-table-wrap table{min-width:820px}.provider-detail .provider-table-wrap table{min-width:760px}.provider-detail .provider-history-wrap table{min-width:1240px}
@media(max-width:1100px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.admin-kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.map-statistics-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.map-statistics-reliability{grid-template-columns:repeat(3,minmax(0,1fr))}.provider-detail .provider-history-wrap{overflow-x:auto}}
@media(max-width:700px){.admin-kpi-grid,.map-statistics-kpis,.map-statistics-reliability{grid-template-columns:repeat(2,minmax(0,1fr))}.installation-heading{align-items:flex-start}.page-meta{white-space:normal}.provider-latest-summary{align-items:flex-start;flex-direction:column;gap:6px}.filter-disclosure .disclosure-body{position:static;margin-top:8px;box-shadow:none}.map-statistics-filter-bar .filter-disclosure{width:100%}.map-statistics-filter-bar .filter-disclosure>summary{justify-content:flex-start}}
@media(max-width:480px){.admin-kpi-grid,.map-statistics-kpis,.map-statistics-reliability,.admin-kpi-grid article{min-height:70px;padding:12px}.inline-filter-row{align-items:stretch;flex-direction:column}.inline-filter-row label,.inline-filter-row select{width:100%;flex-basis:auto}.provider-pagination{gap:8px;font-size:11px}.provider-pagination span{max-width:130px}.provider-action-overflow>div{position:static;margin-top:7px}.provider-action-overflow>summary{width:100%}}
@media(max-width:800px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.diagnostic-model-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.filter-bar .results-count{width:100%;margin:2px 4px 0}.public-status{align-items:flex-start;flex-direction:column}.public-status-value{width:100%;justify-content:space-between;flex-wrap:wrap}.status-guide-grid{grid-template-columns:1fr}.campaign-fields{grid-template-columns:1fr}.campaign-field-wide{grid-column:auto}.attribution-preview{grid-template-columns:1fr}.sync-summary{white-space:normal!important}.device-detail-grid{grid-template-columns:1fr}.device-support-review form{grid-template-columns:1fr}.diagnostic-detail-summary{grid-template-columns:1fr}.diagnostic-actions-grid{grid-template-columns:1fr}.github-review{grid-column:auto}}
@media(max-width:980px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-header-left,.admin-section-nav,.admin-nav{width:100%}.admin-section-nav{order:0;overflow:auto;justify-content:flex-start}.admin-section-nav a{white-space:nowrap}.admin-nav{justify-content:space-between;gap:10px;flex-wrap:wrap}.timezone-control{width:100%;justify-content:space-between}.timezone-control select{width:auto;flex:1}.dashboard{padding-top:28px}.diagnostic-model-metrics{gap:8px}.diagnostic-model-metrics article{padding:12px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}.campaign-card{padding:16px}.campaign-preset-row{align-items:stretch;flex-direction:column;gap:8px}.campaign-preset-row .campaign-label,.campaign-preset-row select{flex:none}.campaign-preset-row select{width:100%;height:var(--admin-control-height);margin-left:0}.generated-url-row{grid-template-columns:1fr}.copy-button{width:100%}.copy-status{min-height:18px}.device-dialog-inner,.diagnostic-detail-inner{padding:18px}.device-detail-grid dl div,.device-detail-secondary dl div{grid-template-columns:1fr;gap:2px}.device-detail-grid dd,.device-detail-secondary dd{text-align:left}.diagnostic-technical-details dl{grid-template-columns:1fr}.github-link-form{grid-template-columns:1fr}.github-link-form button{width:100%}}
@media(max-width:560px){.admin-section-nav{overflow:visible;flex-wrap:wrap}.needs-review-popover{left:0;right:auto}}
@media(max-width:800px){.admin-summary-strip{align-items:flex-start;flex-direction:column;gap:6px}.admin-summary-context,.device-summary-sync{text-align:left;white-space:normal}.device-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.device-detail-grid{grid-template-columns:1fr}.device-catalog-details dl div{grid-template-columns:1fr;gap:2px}.device-catalog-details dd{text-align:left}.device-detail-grid dd{text-align:left}.device-filter-bar .results-count{margin-left:0}.device-dialog-inner{padding:18px}}
@media(max-width:1100px){.device-sticky-header{display:block;position:sticky;top:calc(var(--admin-topbar-height) + var(--device-filter-height, 54px));z-index:21;overflow:hidden;border:1px solid var(--border);border-bottom:0;background:var(--surface)}.device-sticky-header-scroll{overflow:hidden}.device-sticky-header table,.device-table-wrap table{min-width:1050px}.device-sticky-header th{position:static}.device-table-wrap{overflow-x:auto;overflow-y:hidden}.device-table-wrap thead{display:none}.model-statistics{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:800px){.model-page-header{grid-template-columns:auto minmax(0,1fr)}.model-public-link{grid-column:1/-1;width:max-content}.model-statistics{grid-template-columns:repeat(2,minmax(0,1fr))}.administration-grid{grid-template-columns:1fr}.model-review-alert{align-items:flex-start;flex-direction:column}.model-information-list div{grid-template-columns:1fr;gap:3px}.model-information-list dd{text-align:left}}
@media(max-width:1100px){.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.map-statistics-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.provider-dashboard-grid{grid-template-columns:1fr}}
@media(max-width:900px){.map-statistics-coverage-layout{grid-template-columns:1fr}.map-statistics-world-map{min-height:0}.map-statistics-world-map-card .section-heading .table-help{text-align:left}}
@media(max-width:560px){.provider-card{padding:18px 16px}.provider-metrics,.map-statistics-metrics,.map-statistics-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.provider-metrics article{padding:12px}.provider-information-list div{grid-template-columns:1fr;gap:3px}.provider-information-list dd{text-align:left}.provider-action-bar{align-items:stretch;flex-direction:column}.provider-action-bar button,.button-link{width:100%}.provider-action-bar .admin-action-status{flex-basis:auto}.map-statistics-filter-bar label,.map-statistics-filter-bar input,.map-statistics-filter-bar select{width:100%;min-width:0}.map-statistics-filter-bar .results-count{width:100%;margin-left:4px}}
@media(max-height:760px){.device-dialog-inner{max-height:calc(100vh - 32px);overflow:auto}.device-dialog-header{position:sticky;top:-1px;z-index:2;padding-bottom:10px;background:var(--surface)}}
.overview-page{padding-top:30px}.overview-heading{align-items:flex-end;margin-bottom:20px}.overview-period-form{margin:0}.overview-period-form select{min-width:154px}.overview-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}.overview-kpi{display:flex;min-height:112px;flex-direction:column;justify-content:space-between;padding:15px 16px;border:1px solid var(--border);border-radius:12px;background:var(--surface);color:inherit;text-decoration:none;transition:border-color .15s ease,transform .15s ease}.overview-kpi:hover{border-color:color-mix(in srgb,var(--sky) 52%,var(--border));transform:translateY(-1px)}.overview-kpi span{color:var(--secondary);font-size:12px;font-weight:700}.overview-kpi strong{display:block;margin-top:8px;font-family:var(--font-brand);font-size:30px;line-height:1;font-variant-numeric:tabular-nums}.overview-kpi small{margin-top:8px;color:var(--secondary);font-size:11px;line-height:1.35}.overview-kpi-attention strong{color:var(--danger)}.overview-kpi-pending{background:var(--surface-muted)}.overview-kpi-pending strong{color:var(--secondary)}.overview-panel{margin-top:12px;padding:18px 20px;border:1px solid var(--border);border-radius:14px;background:var(--surface)}.overview-panel .section-heading{margin-bottom:10px}.overview-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}.overview-columns .overview-panel{min-width:0}.overview-empty-state{margin:0;padding:12px 0;color:var(--secondary);font-weight:650}.overview-attention-list,.overview-activity-list,.overview-reason-list{list-style:none;margin:0;padding:0}.overview-attention-item{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:10px;padding:10px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-attention-item:first-child{border-top:0;padding-top:3px}.overview-attention-dot{font-size:13px;line-height:1.5;color:var(--danger)}.overview-attention-provider .overview-attention-dot{color:var(--warning,var(--stone))}.overview-attention-item div{display:grid;gap:2px;min-width:0}.overview-attention-item a{color:var(--graphite);text-decoration:none}.overview-attention-item a:hover{text-decoration:underline;text-underline-offset:3px}.overview-attention-item strong{font-size:14px}.overview-attention-item span{color:var(--secondary);font-size:12px;overflow:hidden;text-overflow:ellipsis}.overview-attention-item small{color:var(--secondary);font-size:11px}.overview-detail-link,.section-link{color:var(--interactive);font-size:12px;font-weight:700;white-space:nowrap;text-decoration:none}.overview-detail-link:hover,.section-link:hover{text-decoration:underline;text-underline-offset:3px}.overview-activity-item{display:grid;grid-template-columns:126px minmax(0,1fr) max-content;align-items:center;gap:10px;padding:8px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-activity-item:first-child{border-top:0;padding-top:3px}.overview-activity-item time{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-activity-item a{display:grid;min-width:0;color:inherit;text-decoration:none}.overview-activity-item a:hover .overview-activity-label{text-decoration:underline;text-underline-offset:3px}.overview-activity-label{font-size:13px;font-weight:750}.overview-activity-item a span:not(.overview-activity-label){overflow:hidden;text-overflow:ellipsis;color:var(--secondary);font-size:12px;white-space:nowrap}.overview-activity-item a small{color:var(--danger);font-size:11px}.overview-activity-provider{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-activity-failed .overview-activity-label,.overview-activity-not-started .overview-activity-label{color:var(--danger)}.overview-reason-list{display:grid;gap:11px}.overview-reason-list li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;align-items:center}.overview-reason-list li>span:first-child{font-size:13px}.overview-reason-list strong{font-variant-numeric:tabular-nums}.overview-bar{grid-column:1/-1;height:7px;overflow:hidden;border-radius:999px;background:var(--surface-muted)}.overview-bar i{display:block;height:100%;border-radius:inherit;background:var(--interactive)}.overview-chart-note,.overview-semantic-note{margin:12px 0 0;color:var(--secondary);font-size:11px}.overview-provider-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.overview-provider-summary strong{margin-right:3px;font-variant-numeric:tabular-nums}.overview-provider-summary a{display:inline-flex;gap:5px;align-items:center;padding:5px 8px;border:1px solid var(--border);border-radius:999px;color:var(--graphite);font-size:12px;text-decoration:none}.overview-provider-summary a:hover{border-color:var(--sky);color:var(--interactive)}.overview-provider-summary a span{color:var(--secondary);font-size:11px}.overview-semantic-note{max-width:780px;margin-top:14px}.admin-section-nav{flex-wrap:wrap}
.quick-filter-group{display:flex;align-items:center;gap:4px;flex:0 0 auto;flex-wrap:wrap}.quick-filter{min-height:var(--admin-control-height);padding:8px 10px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:transparent;color:var(--secondary);font-weight:650}.quick-filter:hover{border-color:var(--border);color:var(--interactive)}.quick-filter.active{border-color:color-mix(in srgb,var(--sky) 45%,var(--border));background:var(--surface);color:var(--interactive);box-shadow:0 1px 1px rgba(34,42,43,.05)}
.map-statistics-coverage-layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:12px;margin-top:20px}.map-statistics-coverage-layout>.provider-card{min-width:0;margin-top:0}.map-statistics-popularity{grid-template-columns:minmax(0,1fr)}.map-statistics-popularity .provider-card{margin-top:0}.table-secondary{display:block;margin-top:3px;color:var(--secondary);font-size:11px;font-weight:500}.map-statistics-popularity table th:nth-child(1){width:40%}.map-statistics-popularity table th:nth-child(2){width:26%}.map-statistics-popularity table th:nth-child(3){width:14%}.map-statistics-popularity table th:nth-child(4){width:20%}
.map-statistics-world-map{position:relative;min-height:300px;padding:8px 0 0;overflow:hidden;border:1px solid var(--border);border-radius:10px;background:var(--surface-muted)}.world-map-svg{width:100%;padding:0 8px}.world-map-svg svg{display:block;width:100%;height:auto;overflow:visible}.world-map-country{stroke:color-mix(in srgb,var(--interactive) 42%,var(--border));stroke-width:.65;vector-effect:non-scaling-stroke;cursor:help;outline:none;transition:filter .12s ease,stroke-width .12s ease}.world-map-country:hover,.world-map-country:focus{filter:brightness(.86);stroke:var(--interactive);stroke-width:1.5}.world-map-tooltip{position:absolute;z-index:2;top:12px;right:12px;min-width:170px;max-width:240px;padding:10px 12px;border:1px solid color-mix(in srgb,var(--interactive) 28%,var(--border));border-radius:9px;background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 8px 24px rgba(34,42,43,.14);font-size:12px;pointer-events:none}.world-map-tooltip strong,.world-map-tooltip-total,.world-map-tooltip-empty{display:block}.world-map-tooltip-total{margin-top:2px;color:var(--secondary)}.world-map-tooltip-empty{margin-top:5px;color:var(--secondary);font-style:italic}.world-map-provider-line{display:flex;justify-content:space-between;gap:16px;margin-top:7px;padding-top:6px;border-top:1px solid var(--border)}.world-map-provider-line+ .world-map-provider-line{margin-top:5px;padding-top:5px}.world-map-provider-line span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.world-map-provider-line strong{font-variant-numeric:tabular-nums}.world-map-legend{display:flex;align-items:center;gap:8px;margin:8px 2px 0;color:var(--secondary);font-size:11px;font-variant-numeric:tabular-nums}.world-map-legend-gradient{display:block;flex:1;height:8px;border-radius:99px;background:linear-gradient(90deg,var(--surface),hsl(198 25% 49%));border:1px solid var(--border)}.world-map-note{margin:8px 2px 0}.map-statistics-world-map-card .section-heading{align-items:flex-start}.map-statistics-world-map-card .section-heading .table-help{padding-top:3px;text-align:right}
.overview-columns{grid-template-columns:minmax(0,2fr) minmax(280px,1fr)}.overview-chart-wrap{overflow-x:auto}.overview-trend-chart{display:block;width:100%;min-width:520px;height:auto;min-height:180px}.overview-trend-chart text{fill:var(--secondary);font:500 11px var(--font-ui)}.overview-chart-success{fill:var(--interactive);background:var(--interactive)}.overview-chart-failed{fill:var(--danger);background:var(--danger)}.overview-chart-custom{fill:var(--status-success-text);background:var(--status-success-text)}.overview-chart-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:7px;color:var(--secondary);font-size:11px}.overview-chart-note{font-size:12px;color:var(--secondary);margin:10px 0 0}.overview-chart-legend span{display:inline-flex;align-items:center;gap:5px}.overview-chart-legend i{display:inline-block;width:9px;height:9px;border-radius:2px}.overview-info{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border:1px solid var(--border);border-radius:50%;color:var(--secondary);font-size:11px;font-weight:750;cursor:help}.overview-compatibility-summary{margin-top:12px}.overview-compatibility-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.overview-compatibility-grid div{padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--surface-muted)}.overview-compatibility-grid span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.overview-compatibility-grid strong{display:block;margin-top:5px;font:700 20px var(--font-brand);font-variant-numeric:tabular-nums}.provider-metrics{grid-template-columns:repeat(4,minmax(0,1fr))}.map-statistics-provider-table{display:block}.provider-empty-disclosure{padding:16px 20px}.provider-empty-disclosure>details>summary{list-style:none}.provider-empty-disclosure>details>summary::-webkit-details-marker{display:none}.diagnostic-failure-summary{margin:14px 0 0;padding:11px 13px;border-left:3px solid var(--danger);border-radius:6px;background:var(--error-surface);color:var(--danger);font-size:13px}.diagnostic-failure-summary strong{font-weight:750}.model-statistics article>.info-control{display:inline-flex;margin-top:6px;vertical-align:middle}.history-more-filters{min-width:130px}.history-more-filters .disclosure-body{min-width:170px}.map-statistics-popularity .popularity-all-maps-disclosure{margin-top:12px}.map-statistics-popularity .popularity-regions-disclosure{margin-top:12px}
@media(max-width:1100px){.overview-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:760px){.overview-heading{align-items:flex-start;flex-direction:column;gap:12px}.overview-period-form,.overview-period-form select{width:100%}.overview-columns{grid-template-columns:1fr}.overview-kpi strong{font-size:26px}.overview-activity-item{grid-template-columns:1fr max-content;gap:3px 8px}.overview-activity-item time{grid-column:1/-1}.overview-activity-provider{grid-column:2;grid-row:2}.overview-activity-item a{grid-column:1;grid-row:2}}
@media(max-width:560px){.overview-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.overview-panel{padding:16px}.overview-attention-item{grid-template-columns:auto minmax(0,1fr)}.overview-detail-link{grid-column:2}.overview-kpi{min-height:100px;padding:13px}.overview-kpi strong{font-size:24px}}
@media(max-width:400px){.overview-kpis{grid-template-columns:1fr}}
@media(max-width:700px){.overview-compatibility-grid{grid-template-columns:1fr}.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:480px){.overview-compatibility-grid{grid-template-columns:1fr}}
.overview-primary-grid,.overview-secondary-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,1fr);gap:12px}.overview-primary-grid .overview-panel,.overview-secondary-grid .overview-panel{min-width:0}.overview-model-list,.overview-review-list{list-style:none;margin:0;padding:0}.overview-model-item,.overview-review-item{display:grid;grid-template-columns:minmax(0,1fr) max-content;gap:8px;align-items:start;padding:9px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-model-item:first-child,.overview-review-item:first-child{border-top:0;padding-top:3px}.overview-model-item a,.overview-review-item a{display:grid;min-width:0;color:inherit;text-decoration:none}.overview-model-item a:hover strong,.overview-review-item a:hover strong{text-decoration:underline;text-underline-offset:3px}.overview-model-item strong,.overview-review-item strong{font-size:13px;overflow:hidden;text-overflow:ellipsis}.overview-model-item a span,.overview-review-item a span{color:var(--secondary);font-size:11px}.overview-model-item time{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-model-failed strong{color:var(--danger)}.overview-review-block{margin-top:14px;padding-top:12px;border-top:1px solid var(--border)}.overview-review-block h3{margin:0 0 5px;color:var(--secondary);font-size:12px}.overview-activity-item{grid-template-columns:minmax(0,1fr) max-content}.overview-activity-item time{grid-column:2;grid-row:1 / span 2}.overview-activity-item .overview-activity-label{grid-column:1}.overview-activity-item a span:not(.overview-activity-label){grid-column:1}.overview-compact-empty{padding-bottom:14px}.inline-filter-row{justify-content:flex-start}.inline-filter-row label{flex:0 1 260px}.inline-filter-row select{flex:0 0 170px}
.system-health-page{padding-top:30px}.system-health-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.system-health-card{min-height:150px;padding:18px;border:1px solid var(--border);border-radius:14px;background:var(--surface)}.system-health-card .section-heading{align-items:center;margin-bottom:14px}.system-health-card h2{font-size:16px}.system-health-description p{margin:0 0 10px;color:var(--secondary);font-size:12px;line-height:1.55}.system-health-explanation{margin:12px 0;font-size:11px}.system-health-explanation div{display:grid;grid-template-columns:48px 1fr;gap:7px;padding:5px 0;border-top:1px solid var(--border)}.system-health-explanation dt{font-weight:750;color:var(--graphite)}.system-health-explanation dd{margin:0;color:var(--secondary)}.system-health-badge{display:inline-flex;padding:4px 8px;border:1px solid;border-radius:999px;font-size:11px;font-weight:750}.system-health-healthy{border-color:var(--status-success-border);background:var(--status-success-surface);color:var(--status-success-text)}.system-health-warning{border-color:var(--status-tested-border);background:var(--status-tested-surface);color:var(--status-tested-text)}.system-health-failed{border-color:var(--status-error-border);background:var(--status-error-surface);color:var(--status-error-text)}.system-health-unknown{border-color:var(--status-neutral-border);background:var(--status-neutral-surface);color:var(--status-neutral-text)}
@media(max-width:1100px){.system-health-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.system-health-grid{grid-template-columns:1fr}.system-health-card{min-height:0}}
.model-statistics .attempts-metric>span{display:inline-flex;align-items:center;gap:6px}.model-statistics .attempts-metric>span:after{content:'i';display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border:1px solid var(--border);border-radius:50%;color:var(--interactive);font-size:11px;font-weight:750;line-height:1}
@media(max-width:900px){.overview-primary-grid,.overview-secondary-grid{grid-template-columns:1fr}}
@media(max-width:760px){.overview-activity-item{grid-template-columns:1fr max-content}.overview-activity-item time{grid-column:2;grid-row:1 / span 2}.overview-activity-item a{grid-column:1;grid-row:1 / span 2}.overview-activity-item a span:not(.overview-activity-label){white-space:normal}}
@media(max-width:480px){.inline-filter-row label,.inline-filter-row select{flex-basis:auto}}
.overview-primary-grid-single{grid-template-columns:minmax(0,1fr)}
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
.table-help,.results-count,.page-meta,.overview-chart-note,.overview-semantic-note,.historical-failure-note,.review-help{font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
button,input,select,textarea{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}
.filter-bar input,.filter-bar select,.filter-disclosure>summary,.quick-filter,.provider-action-overflow>summary,.secondary-button,.button-link,.copy-button,.provider-pagination button,.device-pagination button,.admin-action-dialog button:not(.link-button),.auth-card button:not(.link-button),.device-support-review button[type="submit"],.model-administration button[type="submit"]{font-size:var(--admin-type-button-size);line-height:var(--admin-type-button-line)}
.admin-section-nav,.admin-nav,.admin-section-nav a,.admin-nav a,.link-button{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}

.overview-kpi span,.admin-kpi-grid article>span,.provider-metrics article>span,.map-statistics-metrics article>span,.diagnostic-model-metrics article>span,.overview-compatibility-grid span{font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line)}
.overview-kpi strong,.admin-kpi-grid article>strong,.provider-metrics article>strong,.map-statistics-metrics article>strong,.diagnostic-model-metrics article>strong,.model-statistics article>strong{font-size:var(--admin-type-kpi-value-size);line-height:var(--admin-type-kpi-value-line)}
.overview-kpi small{font-size:var(--admin-type-support-size);line-height:var(--admin-type-support-line)}
.overview-compatibility-grid strong{font-size:20px;line-height:22px}
.overview-period-form{margin:0;padding:6px}
.overview-period-form label{display:flex}
.overview-period-form select{height:var(--admin-control-height);min-height:var(--admin-control-height);min-width:154px;padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius);font:600 var(--admin-control-font-size)/1.2 var(--font-ui)}
.overview-chart-panel{padding-top:16px;padding-bottom:16px}
.overview-chart-panel .section-heading{margin-bottom:6px}
.overview-chart-wrap{max-width:780px;margin:0 auto}
.overview-trend-chart{display:block;width:100%;height:260px;max-width:760px;min-height:0;margin:0 auto}
.overview-attention-empty{display:grid;grid-template-columns:minmax(0,auto) minmax(180px,1fr) auto;align-items:center;gap:18px;min-height:76px;padding:12px 16px}
.overview-attention-empty h2,.overview-provider-panel h2{font-family:var(--font-ui);font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line);letter-spacing:0}
.overview-attention-empty .section-kicker,.overview-provider-panel .section-kicker{margin-bottom:1px}
.overview-attention-empty .overview-empty-state{padding:0;font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line);font-weight:500}
.overview-provider-panel{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:18px;min-height:76px;padding:12px 16px}
.overview-provider-panel .overview-provider-summary{justify-content:flex-start}
.device-information-section .model-information-list{max-width:780px}
.device-information-section .model-information-list div{grid-template-columns:150px minmax(0,1fr);gap:16px}
.device-information-section .model-information-list dd{text-align:left}
.diagnostic-detail-dialog{width:min(880px,calc(100% - 32px));max-height:min(82vh,760px)}
.diagnostic-detail-inner{max-height:min(82vh,760px)}
.github-review-collapsed{padding:12px 14px}
.github-review-collapsed .github-current{margin-bottom:4px}
.overview-secondary-grid-single{grid-template-columns:minmax(0,1fr)}
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
.needs-review-count{font-size:var(--admin-type-badge-size);line-height:var(--admin-type-badge-line)}
.admin-disclosure>summary,.provider-action-overflow>summary{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}
.admin-action-dialog h4,.administration-grid h3,.popularity-subsection h3{font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line)}

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
.provider-action-overflow>summary{min-height:var(--admin-control-height);padding:8px 12px}
.provider-action-bar{gap:7px}
.disclosure-body{margin-top:12px}

@media(max-width:760px){
  .provider-card{padding:16px}
  .campaign-card{padding:18px}
  .table-help,.results-count,.page-meta{line-height:16px}
  .overview-compact-empty{align-items:flex-start;flex-direction:column;gap:4px}
  .overview-attention-empty,.overview-provider-panel{grid-template-columns:1fr;align-items:flex-start;gap:7px}
  .overview-provider-panel .overview-provider-summary{gap:7px}
  .device-information-section .model-information-list div{grid-template-columns:1fr;gap:2px}
}

/* Admin audit: one UI type family, visible actions, responsive navigation. */
h1,h2,h3,h4,.administration-grid h3,.overview-kpi strong,.admin-kpi-grid article>strong,.provider-metrics article>strong,.map-statistics-metrics article>strong,.diagnostic-model-metrics article>strong,.overview-compatibility-grid strong{font-family:var(--font-ui);letter-spacing:-.015em}
:root{--admin-type-page-title-size:clamp(28px,3vw,36px);--admin-type-page-title-line:1.2;--admin-type-section-title-size:20px;--admin-type-section-title-line:26px}
.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:8px 16px;padding:10px 0}
.admin-section-nav{flex:1 1 100%;order:3;min-width:0;justify-content:flex-start}
.admin-nav{margin-left:auto;flex:0 1 auto;min-width:0}
.admin-header-left{flex:0 0 auto}
.needs-review-count{background:var(--status-tested-surface);color:var(--status-tested-text);border:1px solid var(--status-tested-border)}
.diagnostic-action-form button[type='submit']{min-height:var(--admin-control-height);padding:8px 12px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:600}
.diagnostic-action-form button[type='submit']:hover{background:var(--interactive-hover)}
.diagnostic-action-form button.secondary-button,.model-administration button.secondary-button{background:var(--surface);color:var(--interactive);border:1px solid var(--border)}
.timestamp-metric strong{font-size:var(--admin-type-subsection-size)!important;line-height:var(--admin-type-subsection-line)!important}
.overview-secondary-grid{align-items:start}.overview-primary-grid{align-items:stretch}
.overview-compatibility-summary>summary,.model-administration>summary,.device-information-section>summary{margin-bottom:12px}
.model-administration,.device-information-section{padding:16px;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
.attention-shortcuts{display:flex;flex-wrap:wrap;gap:8px 18px;margin:12px 0 20px;font-size:13px}
.attention-shortcuts a{color:var(--interactive);text-underline-offset:3px}
.attention-shortcuts strong{margin-left:4px}
.admin-live-update{position:sticky;top:var(--admin-topbar-height);z-index:29;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 24px;background:var(--selected-tint,var(--surface));border-bottom:1px solid var(--border);font-size:14px}
.admin-live-update[hidden]{display:none}
@media(max-width:800px){.admin-section-nav{flex-basis:100%;order:3}.admin-nav{margin-left:auto}.admin-live-update{padding:10px 16px}}
@media(max-width:560px){.admin-header-left{width:auto}.admin-nav{width:100%;justify-content:space-between}.admin-section-nav{overflow:visible}}
/* Phone layouts share the same controls and data as desktop. */
#admin-menu-panel,.mobile-filter-options{display:contents}
.admin-mobile-review,.admin-nav .admin-mobile-website,.filter-bar .device-mobile-sort{display:none}
@media(max-width:700px){
  :root{--admin-control-height:44px;--admin-control-font-size:16px;--admin-topbar-height:64px}
  .admin-topbar-inner{min-height:64px;flex-direction:row;align-items:center;flex-wrap:nowrap;gap:8px;padding:8px 0}
  .admin-header-left{width:auto;min-width:0;flex:1 1 auto}
  .admin-header-left>.admin-badge,.admin-header-left>.admin-website-link{display:none}
  .admin-brand{gap:6px;font-size:19px}.admin-brand img{width:22px;height:26px}
  .admin-mobile-review{display:flex;align-items:center;justify-content:center;gap:5px;min-height:44px;padding:6px;color:var(--interactive);text-decoration:none;font-size:13px;font-weight:650}
  #admin-menu-toggle{flex:0 0 auto;min-height:44px;padding:8px 12px}
  #admin-menu-panel{display:block;position:absolute;top:100%;left:0;right:0;max-height:calc(100dvh - 64px);overflow-y:auto;overscroll-behavior:contain;padding:12px 16px 20px;background:var(--surface);border-bottom:1px solid var(--border);box-shadow:0 8px 16px color-mix(in srgb,var(--graphite) 12%,transparent)}
  .admin-topbar:not(.admin-mobile-ready) .admin-topbar-inner{flex-wrap:wrap}
  .admin-topbar:not(.admin-mobile-ready) #admin-menu-panel{position:static;max-height:none;flex-basis:100%}
  .admin-section-nav{display:grid;grid-template-columns:1fr 1fr;gap:6px;width:100%}
  .admin-section-nav>a,.admin-nav>a{display:flex;align-items:center;min-height:44px;padding:10px;font-size:14px}
  .admin-section-nav>.needs-review-menu{grid-column:1/-1}
  .needs-review-menu summary{min-height:44px}.needs-review-popover{position:static;width:auto;min-width:0;box-shadow:none;margin-top:8px}
  .needs-review-popover a{min-height:44px}
  .admin-nav{width:100%;display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0 0;padding-top:12px;border-top:1px solid var(--border)}
  .admin-nav .timezone-control{grid-column:1/-1;width:100%}.timezone-control select{width:100%;max-width:none;font-size:16px}
  .admin-nav form{margin:0}.admin-nav button{min-height:44px;width:100%}.admin-nav .admin-mobile-website{display:flex}
  main.dashboard{width:100%;max-width:100%;margin:0;padding:20px 16px 32px}.heading-row{margin-bottom:16px}.eyebrow{margin-bottom:6px}
  .lede{font-size:14px;line-height:1.5}.overview-heading{gap:10px}.overview-period-form{padding:0;border:0;background:none}
  .overview-attention-panel{margin-top:0}.overview-attention-item{gap:6px 10px;padding:12px 0}.overview-detail-link{min-height:36px;display:inline-flex;align-items:center}
  .overview-attention-item span,.overview-activity-item a span:not(.overview-activity-label){white-space:normal;overflow:visible;overflow-wrap:anywhere}
  .attention-shortcuts{display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;margin:8px 0 16px}
  .attention-shortcuts a{display:flex;align-items:center;min-height:44px;gap:4px;font-size:12px}
  .overview-kpis,.installation-kpis,.model-statistics,.diagnostic-model-metrics,.provider-metrics,.map-statistics-metrics,.map-statistics-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .overview-kpi{min-height:104px;padding:12px}.overview-kpi strong{font-size:26px;margin-top:5px}.overview-kpi:last-child:nth-child(odd){grid-column:1/-1;min-height:82px}
  .admin-kpi-grid article{min-width:0;padding:12px;min-height:80px}.installation-kpis article:last-child{grid-column:1/-1}
  .installation-kpis{margin-bottom:12px}.historical-failure-note{margin-bottom:16px}
  .admin-filter-bar,.filter-bar{min-width:0;max-width:100%;gap:8px}.admin-filter-bar{align-items:stretch}
  .filter-bar label,.filter-search{min-width:0!important;max-width:100%;flex:1 1 100%}
  input:not([type='checkbox']):not([type='radio']),select,textarea{font-size:16px!important;max-width:100%;min-width:0;min-height:44px}
  .quick-filter-group{min-width:0;max-width:100%;display:flex;flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;flex-basis:100%;gap:5px;padding-bottom:3px}
  .quick-filter{flex:0 0 auto;min-height:44px;font-size:13px}
  .mobile-filter-options{display:grid;grid-template-columns:1fr;gap:8px;width:100%}
  .mobile-filter-toggle{width:100%;text-align:left}.filter-bar .device-mobile-sort{display:block}
  .device-filter-bar{position:static}.device-sticky-header{display:none!important}
  .table-wrap{min-width:0;max-width:100%}.diagnostic-list-wrap{max-height:none}
  .table-wrap:has(.mobile-record-table){border:0;background:transparent;overflow:visible;border-radius:0}
  table.mobile-record-table{display:block;min-width:0!important;width:100%;border:0;table-layout:auto}
  .mobile-record-table colgroup{display:none}
  .mobile-record-table thead{position:absolute!important;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
  .mobile-record-table tbody{display:grid;width:100%;gap:12px}
  .mobile-record-table tbody tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;min-width:0}
  .mobile-record-table tbody td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;text-align:left!important;white-space:normal!important;overflow-wrap:anywhere;font-size:13px}
  .mobile-record-table td a{min-height:44px;display:inline-flex;align-items:center}
  .mobile-record-table td .provider-name-link{align-items:flex-start}
  .mobile-record-table td[data-label='']::before{display:none}
  #overview-attention-title{scroll-margin-top:80px}
  .mobile-record-table tbody td::before{content:attr(data-label);display:block;margin-bottom:5px;font-size:11px;line-height:1.35;font-weight:600;color:var(--secondary)}
  .mobile-record-table tbody td:first-child{grid-column:1/-1;font-weight:650}
  .mobile-record-table tbody td:has(button){grid-column:1/-1}.mobile-record-table td button{min-height:44px;width:100%}
  .device-model-button{min-height:44px}.device-thumb{width:40px;height:48px}.device-model-copy{min-width:0}.device-model-copy strong{white-space:normal}
  .model-page-header{gap:12px;grid-template-columns:auto minmax(0,1fr)}.model-page-image{width:64px;height:64px}.model-page-heading h1{font-size:24px}
  .model-review-alert{gap:8px;align-items:flex-start}.model-review-alert a{min-height:44px;display:flex;align-items:center}
  .provider-action-bar{display:grid;grid-template-columns:1fr 1fr}.provider-action-bar button{width:100%;min-height:44px}.provider-action-overflow{width:100%}.provider-action-bar>p{grid-column:1/-1}
  .provider-pagination,.device-pagination{display:flex;flex-wrap:wrap;gap:8px}.provider-pagination button,.device-pagination button{min-height:44px}.provider-pagination>span{flex:1 1 100%;order:3}
  .system-health-card{min-height:0;padding:16px}.system-health-card .section-heading{display:flex;flex-direction:row;justify-content:space-between;text-align:left;align-items:center}.system-health-card .system-health-description{text-align:left}
  details>summary{min-height:44px;align-content:center;line-height:1.45}summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
  .diagnostic-detail-dialog{width:calc(100% - 16px);max-width:none;max-height:calc(100dvh - 16px);margin:auto;border-radius:12px}
  .diagnostic-detail-inner{padding:16px;max-height:calc(100dvh - 16px);overflow:auto;overscroll-behavior:contain}
  .diagnostic-detail-inner>.device-dialog-header{position:sticky;top:-16px;z-index:2;background:var(--surface);padding:12px 0;flex-direction:row;align-items:flex-start;gap:10px}
  .diagnostic-detail-inner .dialog-close{width:44px;min-width:44px;height:44px}
  .diagnostic-detail-summary,.diagnostic-actions-grid,.administration-grid{grid-template-columns:1fr}.diagnostic-detail-summary div{grid-template-columns:minmax(80px,.7fr) minmax(0,1fr)}
  .diagnostic-action-form button{min-height:44px}.diagnostic-detail-summary dd{text-align:right}
  .auth-card{margin:24px 16px;max-width:calc(100% - 32px);padding:20px}.auth-card button{min-height:44px}
  .campaign-card{padding:16px}.campaign-grid{gap:16px}.campaign-field input,.campaign-field select{font-size:16px}
  .admin-live-update{top:64px;gap:8px;padding:10px 16px;font-size:13px}.admin-live-update button{min-height:44px}
}

/* Full labels and values remain readable at every admin width. */
.overview-attention-item span,.overview-activity-item a span:not(.overview-activity-label),.overview-model-item strong,.overview-review-item strong,.device-model-copy strong,.provider-error{white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;max-width:none}
.overview-panel,.system-health-card,.provider-card,.campaign-card,.admin-kpi-grid article,.overview-kpi,.provider-metrics article{min-width:0;overflow-wrap:anywhere}
.section-heading>div,.heading-row>div,.provider-latest-summary>div,.device-model-copy{min-width:0}
.generated-url{white-space:pre-wrap;overflow-wrap:anywhere;overflow:visible;word-break:normal}
.diagnostic-technical-details pre,.model-technical-details pre,.device-dialog pre,.diagnostic-detail-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}
.diagnostic-list-wrap{max-height:none}
@media(min-width:701px){
  .table-wrap table,.device-sticky-header table{min-width:0!important;width:100%;table-layout:fixed}
  .table-wrap th,.table-wrap td,.device-sticky-header th{min-width:0;white-space:normal!important;overflow-wrap:anywhere}
  .table-wrap .admin-timestamp,.device-sticky-header .admin-timestamp{white-space:normal}
  .model-history-table th:nth-child(4){width:20%}.model-history-table th:nth-child(7){width:11%}
  .device-table-wrap th button,.device-sticky-header th button{min-width:0;width:100%;white-space:normal;text-align:left;justify-content:flex-start}
  .provider-history-wrap th:nth-child(1){width:14%}.provider-history-wrap th:nth-child(2){width:10%}
  .provider-history-wrap th:nth-child(3){width:26%}.provider-history-wrap th:nth-child(4){width:6%}
  .provider-history-wrap th:nth-child(5){width:10%}.provider-history-wrap th:nth-child(6){width:10%}
  .provider-history-wrap th:nth-child(7){width:24%}
  .provider-source-table th:nth-child(1){width:14%}.provider-source-table th:nth-child(2){width:50%}.provider-source-table th:nth-child(3){width:12%}.provider-source-table th:nth-child(4){width:24%}
  .provider-package-table th:nth-child(1){width:55%}.provider-package-table th:nth-child(2){width:20%}.provider-package-table th:nth-child(3){width:10%}.provider-package-table th:nth-child(4){width:15%}
  .provider-run-table th:nth-child(1){width:6%}.provider-run-table th:nth-child(2),.provider-run-table th:nth-child(3){width:16%}.provider-run-table th:nth-child(4){width:12%}.provider-run-table th:nth-child(5),.provider-run-table th:nth-child(6){width:10%}.provider-run-table th:nth-child(7){width:30%}
  .provider-component{white-space:normal;flex-wrap:wrap}.provider-component-list{min-width:0}
  .provider-component .provider-status{white-space:normal;line-height:1.3}
  .overview-trend-chart{min-width:0}
  .diagnostic-detail-dialog,.device-dialog{max-height:calc(100dvh - 48px);overflow:hidden}
  .diagnostic-detail-inner,.device-dialog-inner{max-height:calc(100dvh - 48px);overflow-y:auto;overscroll-behavior:contain}
  .diagnostic-detail-inner>.device-dialog-header,.device-dialog-inner>.device-dialog-header{position:sticky;top:-24px;z-index:2;background:var(--surface);padding:12px 0}
}

"""


def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _layout(title: str, content: str) -> bytes:
    if 'id="main-content"' in content or "id='main-content'" in content:
        # Rendering time is not new activity. Device/provider payloads include it.
        stable_content = re.sub(r'("generatedAt"\s*:\s*)"[^"]*"', r'\1""', content)
        revision = hashlib.sha256(stable_content.encode()).hexdigest()
        content = re.sub(r'(<main\b)', rf'\1 data-admin-revision="{revision}"', content, count=1)
        content += f"<script>{_admin_freshness_script()}{_admin_mobile_script()}</script>"
    content = content.replace(
        "<script>", f"<script nonce=\"{_ADMIN_NONCE_PLACEHOLDER}\">"
    )
    timezone_script = _admin_timezone_script()
    content = f"{content}<script>{timezone_script}</script>"
    content = content.replace(
        "<script>", f"<script nonce=\"{_ADMIN_NONCE_PLACEHOLDER}\">"
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>{ADMIN_STYLES}</style></head><body>{content}</body></html>""".encode("utf-8")


def _admin_mobile_script() -> str:
    return r"""(() => {
      const narrow = matchMedia('(max-width: 700px)');
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
        document.querySelector('.admin-mobile-review')?.addEventListener('click', () => close());
        panel.addEventListener('click', event => { if (event.target.closest('a')) close(); });
        narrow.addEventListener('change', adapt); adapt();
      }
      const arrange = () => {
        const kpis = document.querySelector('.overview-kpis');
        const attention = document.querySelector('.overview-attention-panel');
        const shortcuts = document.querySelector('.attention-shortcuts');
        if (kpis && attention && shortcuts) {
          if (narrow.matches) kpis.before(attention, shortcuts); else kpis.after(attention, shortcuts);
        }
      };
      narrow.addEventListener('change', arrange);
      window.addEventListener('terento-admin-content-changed', arrange); arrange();
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
              cell.dataset.label = cell.colSpan > 1 ? '' : (headers[i]?.getAttribute('aria-label') || headers[i]?.textContent || '').replace(/[↕↑↓]/g, '').trim();
              cell.setAttribute('role', 'cell');
            });
          });
        });
      };
      labelTables();
      const main = document.querySelector('main');
      if (main) new MutationObserver(labelTables).observe(main, {childList:true, subtree:true});
    })();"""


def _admin_freshness_script() -> str:
    return r"""(() => {
      const main = document.querySelector('[data-admin-revision]');
      if (!main || document.querySelector('#admin-live-update')) return;
      const notice = document.createElement('div');
      notice.id = 'admin-live-update'; notice.className = 'admin-live-update';
      notice.setAttribute('role', 'status'); notice.hidden = true;
      const message = document.createElement('span');
      const refresh = document.createElement('button');
      refresh.type = 'button'; refresh.className = 'secondary-button'; refresh.textContent = 'Refresh';
      notice.append(message, refresh); document.querySelector('.admin-topbar')?.after(notice);
      let dirty = false;
      document.addEventListener('input', event => {
        if (event.target.closest('form[method="post"]')) dirty = true;
      });
      refresh.addEventListener('click', () => {
        if (!dirty || window.confirm('Refresh and discard unsaved edits?')) window.location.reload();
      });
      let running = false;
      const check = async () => {
        if (document.hidden || running) return;
        const current = document.querySelector('[data-admin-revision]');
        if (!current || current.getAttribute('aria-busy') === 'true') return;
        running = true;
        const url = window.location.href;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
          const response = await fetch(url, {credentials:'same-origin', cache:'no-store', signal:controller.signal});
          if (response.redirected && new URL(response.url).pathname === '/admin/login') {
            message.textContent = 'Your session expired. Refresh to sign in.'; notice.hidden = false; return;
          }
          if (!response.ok) throw new Error('Unavailable');
          const next = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('[data-admin-revision]');
          if (window.location.href !== url || document.querySelector('[data-admin-revision]') !== current) return;
          if (!next) throw new Error('Missing snapshot');
          notice.hidden = next.dataset.adminRevision === current.dataset.adminRevision;
          message.textContent = 'New activity or status changes are available.';
        } catch (_) {
          message.textContent = 'Live check unavailable. This page may be out of date.'; notice.hidden = false;
        } finally { clearTimeout(timeout); running = false; }
      };
      setInterval(check, 60000);
      document.addEventListener('visibilitychange', check);
    })();"""


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

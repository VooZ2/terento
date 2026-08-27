from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from .campaign_links import CAMPAIGN_SUGGESTIONS, MEDIUM_OPTIONS, SOURCE_OPTIONS
from .asset_attribution import generic_fallback_image
from .compatibility_status import (
    CANONICAL_STATUS_ORDER,
    STATUS_PUBLIC_COPY,
    CompatibilityStatus,
    calculate_compatibility_status,
)
from .device_catalog import _official_source_image_url
from .map_capability import classify_map_capable


PASSWORD_MIN_LENGTH = 14
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,64}")
PBKDF2_ITERATIONS = 600_000


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
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
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
    raw = str(value or "").strip()
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
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
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


def _diagnostics_url(value: dict[str, Any], *, state: str | None = None) -> str:
    identity = str(value.get("compatibility_identity") or value.get("model") or "Unknown").strip()
    parameters = {"identity": identity}
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        parameters["canonical_device_id"] = canonical_id
    if state:
        parameters["state"] = state
    return "/admin/diagnostics?" + urlencode(parameters)


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


def _diagnostic_summary_by_identity(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_identity: dict[str, dict[str, int]] = {}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in events:
        identity = _identity_group_key(event)
        key = _operation_key(event)
        if identity and key:
            grouped.setdefault(identity, {}).setdefault(key, []).append(event)
    for identity, operations in grouped.items():
        errors = sum(1 for results in operations.values() if _operation_is_problematic(results))
        pending = sum(1 for results in operations.values() if _identity_is_pending(results))
        by_identity[identity] = {"errors": errors, "identity_pending": pending}
    return by_identity


def _normalise_github_issue_reference(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    match = re.fullmatch(r"#?(\d{1,10})", raw)
    if not match:
        raise ValueError("GitHub issue must be a Terento issue number such as #32")
    return f"#{int(match.group(1))}"


def _error_cell(row: dict[str, Any], diagnostic_summary: dict[str, int] | None = None) -> str:
    summary = diagnostic_summary or {}
    count = (
        int(row.get("failed_install_count") or 0)
        if "failed_install_count" in row
        else int(summary.get("errors") or 0)
    )
    identity = str(row.get("compatibility_identity") or row.get("model") or "unknown")
    target = _diagnostics_url(row, state="all")
    if count:
        return (
            f"<a class='error-count' href='{html.escape(target, quote=True)}' "
            f"aria-label='View {count} failed installations for {html.escape(identity)}'>"
            f"{count} error{'s' if count != 1 else ''}</a>"
        )
    return "<span class='muted-value'>—</span>"


def _diagnostics_id(identity: str) -> str:
    return "diagnostics-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


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


def _github_issue_markup(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.fullmatch(r"#?(\d+)", raw)
    if not match:
        return f" · GitHub {html.escape(raw)}"
    issue_number = match.group(1)
    return f" · <a class='github-issue' href='https://github.com/VooZ2/terento/issues/{issue_number}' target='_blank' rel='noreferrer'>Issue #{issue_number}</a>"


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


def _diagnostic_code(result: dict[str, Any]) -> str:
    code = str(result.get("failure_code") or "").strip()
    native = str(result.get("native_failure_code") or "").strip()
    if not code and not native:
        return "<span class='muted-value'>—</span>"
    primary = html.escape(code or "—")
    native_markup = (
        f"<small class='diagnostic-native-code'>Native: {html.escape(native)}</small>"
        if native else ""
    )
    return f"<span class='diagnostic-code-value'>{primary}{native_markup}</span>"


def _diagnostic_cleanup(result: dict[str, Any]) -> str:
    attempted = _diagnostic_boolean(result.get("cleanup_attempted"))
    if attempted == "No" or attempted.startswith("<span"):
        return "Not attempted"
    return "Yes" if _diagnostic_boolean(result.get("cleanup_succeeded")) == "Yes" else "No"


def _diagnostic_summary_rows(results: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for result in sorted(results, key=lambda item: int(item.get("map_result_index") or 0)):
        rows.append(
            "<tr>"
            f"<td>{_diagnostic_value(result.get('region'))}</td>"
            f"<td>{_diagnostic_result(result.get('phase_outcome'))}</td>"
            f"<td>{_diagnostic_value(result.get('failure_stage'))}</td>"
            f"<td>{_diagnostic_code(result)}</td>"
            f"<td>{_diagnostic_boolean(result.get('write_started'))}</td>"
            f"<td>{_diagnostic_cleanup(result)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _diagnostic_technical_details(result: dict[str, Any], result_number: int) -> str:
    fields = (
        ("Raw MTP model", result.get("raw_mtp_model")),
        ("Local identity", result.get("identity_resolution_code")),
        ("Native code", result.get("native_failure_code")),
        ("Object created", _diagnostic_boolean(result.get("remote_object_created"))),
        ("Transfer progress", result.get("transfer_progress_bucket")),
        ("Map result", result.get("map_result_index")),
        ("Selected maps", result.get("selected_map_count")),
        ("Cleanup attempted", _diagnostic_boolean(result.get("cleanup_attempted"))),
        ("Cleanup succeeded", _diagnostic_boolean(result.get("cleanup_succeeded"))),
        ("Error category", result.get("error_category")),
        ("Transport", result.get("transport")),
    )
    rows = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{value if isinstance(value, str) and value.startswith('<span') else _diagnostic_value(value)}</dd></div>"
        for label, value in fields
    )
    return (
        f"<details class='diagnostic-technical-details'>"
        f"<summary>Technical details · map result {result_number}</summary>"
        f"<dl>{rows}</dl></details>"
    )


def _diagnostic_group_summary(identity: str, operations: dict[str, list[dict[str, Any]]]) -> str:
    parts = [part.strip() for part in identity.split("·") if part.strip()]
    title_parts: list[str] = []
    chips: list[str] = []
    for part in parts:
        lowered = part.casefold()
        if lowered in {"identity pending", "identity unresolved", "identity not identifiable"}:
            chips.append(f"<span class='diagnostic-chip'>{html.escape(part)}</span>")
            continue
        if re.fullmatch(r"(?:issue\s*)?#?\d+", part, flags=re.IGNORECASE):
            chips.append(_github_issue_chip(part.removeprefix("issue ").strip()))
            continue
        title_parts.append(part)
    if not title_parts:
        title_parts = [identity]
    elif len(title_parts) == 1:
        size_match = re.fullmatch(r"(.+?)\s+(\d{2,3}\s*mm)", title_parts[0], flags=re.IGNORECASE)
        if size_match:
            title_parts = [
                size_match.group(1).strip(),
                re.sub(r"(\d{2,3})\s*mm", r"\1 mm", size_match.group(2), flags=re.IGNORECASE),
            ]
    issue = next(
        (
            event.get("linked_github_issue")
            for result_group in operations.values()
            for event in result_group
            if event.get("linked_github_issue")
        ),
        None,
    )
    if issue and not any("github.com/VooZ2/terento/issues/" in chip for chip in chips):
        chips.append(_github_issue_chip(issue))
    count = len(operations)
    chips.append(
        f"<span class='diagnostic-chip'>{count} diagnostic{'s' if count != 1 else ''}</span>"
    )
    return (
        f"<span class='diagnostic-group-title'>{html.escape(' · '.join(title_parts))}</span>"
        f"<span class='diagnostic-group-meta'>{''.join(chips)}</span>"
        "<span class='diagnostic-summary-action'>View details</span>"
    )


def _admin_brand() -> str:
    return """<a class="admin-brand" href="/admin" aria-label="Terento admin home">
      <img src="https://terento.app/assets/logo-sky.svg" alt="" width="25" height="29">
      <span>Terento</span><span class="admin-badge">Admin</span>
    </a>"""


def _admin_header(user: dict[str, Any], csrf_token: str, *, active: str = "evidence") -> str:
    username = html.escape(str(user.get("username") or ""))
    evidence_class = " class='active'" if active == "evidence" else ""
    campaign_class = " class='active'" if active == "campaigns" else ""
    devices_class = " class='active'" if active == "devices" else ""
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
          <a href="/admin"><span>Installation issues</span><strong>{installation_issues}</strong></a>
          <a href="/admin"><span>Identity pending</span><strong>{identity_pending}</strong></a>
          <a href="/admin/devices"><span>Ready to publish</span><strong>{ready_to_publish}</strong></a>
        </div>
      </details>""" if review_total else ""
    return f"""<header class="admin-topbar"><div class="admin-topbar-inner">
      <div class="admin-header-zone admin-header-left">{_admin_brand()}</div>
      <nav class="admin-section-nav" aria-label="Admin sections"><a{evidence_class} href="/admin">Installations</a><a{devices_class} href="/admin/devices">Devices</a><a{campaign_class} href="/admin/campaign-links">Campaign links</a>{review_menu}</nav>
      <nav class="admin-nav" aria-label="Admin navigation"><label class="timezone-control"><span class="sr-only">Time zone</span><select id="admin-timezone" aria-label="Time zone" title="Time zone"><option value="browser">Automatic (browser)</option><option value="UTC">UTC</option><option value="Europe/Vilnius">Europe/Vilnius</option><option value="Europe/London">Europe/London</option><option value="Europe/Berlin">Europe/Berlin</option><option value="America/New_York">America/New_York</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="Asia/Tokyo">Asia/Tokyo</option></select></label><a class="admin-website-link" href="https://terento.app/" target="_blank" rel="noopener noreferrer" aria-label="Open Terento website in a new tab">Website <span aria-hidden="true">↗</span></a><span class="admin-user" aria-label="Signed in as {username}">{username}</span>
      <form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><button class="link-button" type="submit">Sign out</button></form></nav>
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


def dashboard_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    public_stats_enabled: bool = False,
) -> bytes:
    attempts = sum(int(row.get("attempted_install_count") or 0) for row in rows)
    successes = sum(int(row.get("successful_install_count") or 0) for row in rows)
    latest = _latest_data_timestamp(rows)
    status_values = [status.value for status in CANONICAL_STATUS_ORDER]
    status_options = "".join(
        f"<option value='{status.lower()}'>{status.title()}</option>"
        for status in status_values
    )
    diagnostic_summary = _diagnostic_summary_by_identity(operations or [])
    errors = sum(int(row.get("failed_install_count") or 0) for row in rows)
    table_rows = "".join(
        _statistics_row(row, diagnostic_summary.get(_identity_group_key(row), {}))
        for row in rows
    )
    empty = "<p class='empty'>No installation evidence yet.</p>" if not rows else ""
    latest_copy = f"<strong>Updated</strong> {_timestamp_markup(latest)}" if latest else "No evidence received yet"
    content = f"""
      {_admin_header(user, csrf_token)}
      <main class="dashboard" id="main-content">
        <div class="heading-row"><div><p class="eyebrow">Evidence</p><h1>Installations</h1><p class="lede">Installation activity and compatibility evidence from Terento users.</p></div></div>
        <section class="admin-summary-strip installation-summary-strip" aria-label="Evidence summary and latest update">
          <p class="admin-summary-metrics"><strong>{len(rows)} {'model' if len(rows) == 1 else 'models'}</strong><span> · {attempts} {'attempt' if attempts == 1 else 'attempts'} · {successes} successful · {errors} {'error' if errors == 1 else 'errors'}</span></p>
          <p class="admin-summary-context">{latest_copy}</p>
        </section>{empty}
        <section class="evidence-section" aria-label="Installation evidence table">
          <form class="filter-bar admin-filter-bar" id="evidence-filters" role="search">
            <label class="filter-search"> <span class="sr-only">Search models</span><input id="evidence-search" type="search" placeholder="Search models" autocomplete="off"></label>
            <label><span class="sr-only">Filter by status</span><select id="evidence-status"><option value="all">All statuses</option>{status_options}</select></label>
            <label><span class="sr-only">Sort models</span><select id="evidence-sort"><option value="attempts">Most attempts</option><option value="errors">Most errors</option><option value="latest">Latest activity</option><option value="model">Model name</option></select></label>
            <p class="results-count" id="results-count" aria-live="polite">{len(rows)} {"model" if len(rows) == 1 else "models"}</p>
          </form>
          <div class="table-wrap evidence-table-wrap"><table class="admin-table"><caption class="sr-only">Installations by exact device identity</caption><thead><tr><th scope="col">Model</th><th scope="col">Variant</th><th scope="col">Attempts</th><th scope="col">Success</th><th scope="col">Errors</th><th scope="col">Status</th><th scope="col">Last success</th></tr></thead><tbody id="evidence-rows">{table_rows}</tbody></table></div>
          <p class="table-help evidence-table-note">Attempts, successes, and errors include all retained installation operations. The Needs review queue contains only unresolved problems.</p>
        </section>
      </main>
      <script>{_dashboard_script()}</script>
    """
    return _layout("Installations", content)


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
        f"#{number} · Open</a>"
    )


def _sanitised_issue_value(value: Any) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "—")).strip()[:160]


def _github_create_issue_url(identity: str, results: list[dict[str, Any]]) -> str:
    model, variant = _display_identity(identity)
    first = results[0] if results else {}
    title = f"Terento installation diagnostic: {_sanitised_issue_value(model)}"
    if variant != "—":
        title += f" · {_sanitised_issue_value(variant)}"
    body = "\n".join(
        (
            "Terento installation diagnostic",
            "",
            f"Device: {_sanitised_issue_value(model)}",
            f"Variant: {_sanitised_issue_value(variant)}",
            f"Result: {_sanitised_issue_value(_operation_result(results))}",
            f"Stage: {_sanitised_issue_value(_operation_text(results, 'failure_stage'))}",
            f"Code: {_sanitised_issue_value(_operation_text(results, 'failure_code'))}",
            f"Diagnostic reference: {_sanitised_issue_value(_operation_key(first))}",
            "",
            "Please add reproduction context without including personal data, Garmin unit identifiers, or local file paths.",
        )
    )
    return "https://github.com/VooZ2/terento/issues/new?" + urlencode({"title": title, "body": body})


def _diagnostic_detail_dialog(
    identity: str,
    operation_key: str,
    results: list[dict[str, Any]],
    *,
    resolved: bool,
    csrf_token: str,
    identity_devices: list[dict[str, Any]] | None,
    canonical_device_model_id: str | None = None,
) -> str:
    first = results[0]
    dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
    model, variant = _display_identity(identity)
    issue = _operation_issue(results)
    result_label = _operation_result(results)
    state = _operation_state(results, resolved=resolved)
    identity_pending = _identity_is_pending(results)
    return_to = _diagnostics_url({
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
          <form method='post' action='/admin/diagnostics/reopen' class='diagnostic-action-form'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
            <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
            <button type='submit' class='secondary-button'>Reopen diagnostic</button>
          </form>"""
    elif state == "open":
        lifecycle_action = f"""
          <form method='post' action='/admin/diagnostics/resolve' class='diagnostic-action-form'>
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
      <form method='post' action='/admin/diagnostics/identity' class='diagnostic-action-form identity-review-form'>
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
    issue_controls = f"""
        <div class='github-actions'><a class='secondary-button' href='{html.escape(_github_create_issue_url(identity, results), quote=True)}' target='_blank' rel='noreferrer'>Create GitHub issue</a></div>
        <form method='post' action='/admin/diagnostics/issue' class='github-link-form'>
          <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
          <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
          <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
          <label>{'Change' if issue else 'Link'} issue <span class='optional-label'>e.g. #32</span><input name='linked_github_issue' placeholder='#32' inputmode='numeric' pattern='#?[0-9]{{1,10}}'></label>
          <button type='submit' class='secondary-button'>{'Change linked issue' if issue else 'Link issue'}</button>
        </form>
        {f"<form method='post' action='/admin/diagnostics/issue' class='github-remove-form'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'><input type='hidden' name='linked_github_issue' value=''><button type='submit' class='secondary-button'>Remove link</button></form>" if issue else ''}"""
    collapse_issue_form = result_label == "SUCCEEDED" and state == "history" and not issue
    if collapse_issue_form:
        issue_form = f"""
          <section class='diagnostic-action-form github-review github-review-collapsed' aria-labelledby='github-review-{dialog_id}'>
            <h4 id='github-review-{dialog_id}'>GitHub issue</h4>
            <p class='github-current'><span class="muted-value">No linked issue</span></p>
            <details class='github-issue-disclosure'><summary>Link or create issue</summary><div class='github-issue-controls'>{issue_controls}</div></details>
          </section>"""
    else:
        issue_form = f"""
          <section class='diagnostic-action-form github-review' aria-labelledby='github-review-{dialog_id}'>
            <h4 id='github-review-{dialog_id}'>GitHub issue</h4>
            <p class='github-current'>{_github_issue_link(issue) if issue else '<span class="muted-value">No linked issue</span>'}</p>
            {issue_controls}
          </section>"""
    review_state = ""
    if resolved:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('RESOLVED')}{resolution}</dd></div>"
    elif state == "open":
        identity_badge = f" {_diagnostic_state_badge('IDENTITY_PENDING')}" if identity_pending else ""
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('OPEN')}{identity_badge}</dd></div>"
    elif identity_pending:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('IDENTITY_PENDING')}</dd></div>"
    technical_details = f"<details class='diagnostic-technical-details diagnostic-technical-all'><summary>Technical details</summary><p class='diagnostic-id'>Diagnostic ID: <code>{html.escape(operation_key)}</code></p>{technical}</details>"
    return f"""
      <dialog class='diagnostic-detail-dialog' id='{dialog_id}' aria-labelledby='{dialog_id}-title'>
        <div class='diagnostic-detail-inner'>
          <div class='device-dialog-header'><div><p class='section-kicker'>Diagnostic detail</p><h2 id='{dialog_id}-title'>{html.escape(model)}{f' · {html.escape(variant)}' if variant != '—' else ''}</h2></div><button class='dialog-close' type='button' data-close-dialog aria-label='Close diagnostic detail'>×</button></div>
          <dl class='diagnostic-detail-summary'>
            <div><dt>Device</dt><dd>{html.escape(model)}</dd></div>
            <div><dt>Variant</dt><dd>{html.escape(variant)}</dd></div>
            <div><dt>Date</dt><dd>{_timestamp_markup(first.get('occurred_at'))}</dd></div>
            <div><dt>Region</dt><dd>{html.escape(_operation_text(results, 'region'))}</dd></div>
            <div><dt>Result</dt><dd>{_diagnostic_result(result_label)}</dd></div>
            <div><dt>App version</dt><dd>{html.escape(str(first.get('release_label') or first.get('terento_version') or '—'))}{f" (build {html.escape(str(first.get('app_build')))})" if first.get('app_build') else ''}</dd></div>
            {review_state}
            <div><dt>Linked issue</dt><dd>{_github_issue_link(issue)}</dd></div>
          </dl>
          <div class='diagnostic-actions-grid'>{lifecycle_action}{identity_form}{issue_form}</div>
          {technical_details}
        </div>
      </dialog>"""


def diagnostics_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, identity: str,
    operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    identity_devices: list[dict[str, Any]] | None = None,
    canonical_device_model_id: str | None = None,
) -> bytes:
    identity = identity.strip()
    canonical_device_model_id = str(canonical_device_model_id or "").strip() or None

    def matches(value: dict[str, Any]) -> bool:
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
    diagnostic_groups = [(key, results, False) for key, results in active_groups.items()]
    diagnostic_groups.extend((key, results, True) for key, results in resolved_groups.items())
    diagnostic_groups.sort(key=lambda item: _timestamp_iso(item[1][0].get("occurred_at")), reverse=True)
    model, variant = _display_identity(identity, model_row)
    attempts = int(model_row.get("attempted_install_count") or 0) if model_row else len(active_groups) + len(resolved_groups)
    successes = int(model_row.get("successful_install_count") or 0) if model_row else sum(
        1 for results in list(active_groups.values()) + list(resolved_groups.values())
        if _operation_result(results) == "SUCCEEDED"
    )
    errors = int(model_row.get("failed_install_count") or 0) if model_row else sum(
        1
        for results in list(active_groups.values()) + list(resolved_groups.values())
        if _operation_is_problematic(results)
    )
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
      {_admin_header(user, csrf_token)}
      <main class='dashboard diagnostics-page' id='main-content'>
        <p class='back-link'><a href='/admin'>← Installations</a></p>
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


def _diagnostic_details(rows: list[dict[str, Any]], events: list[dict[str, Any]], csrf_token: str) -> str:
    identities = {
        str(row.get("compatibility_identity") or row.get("model") or "Unknown")
        for row in rows
    }
    return _render_diagnostic_details(
        events,
        identities=identities,
        heading="Diagnostics",
        summary_prefix="",
        csrf_token=csrf_token,
    )


def _resolved_diagnostic_details(events: list[dict[str, Any]], csrf_token: str) -> str:
    return _render_diagnostic_details(
        events,
        identities=None,
        heading="Resolved / historical diagnostics",
        summary_prefix="",
        note="These records are retained for diagnosis and remain included in compatibility counts and rates.",
        csrf_token=csrf_token,
    )


def _render_diagnostic_details(
    events: list[dict[str, Any]],
    *,
    identities: set[str] | None,
    heading: str,
    summary_prefix: str,
    note: str | None = None,
    csrf_token: str = "",
) -> str:
    by_identity: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in events:
        identity = str(event.get("compatibility_identity") or event.get("model") or "Unknown")
        if identities is not None and identity not in identities:
            continue
        operation = str(event.get("operation_key") or event.get("operation_id") or event.get("event_id"))
        by_identity.setdefault(identity, {}).setdefault(operation, []).append(event)
    sections: list[str] = []
    identities_to_render = identities if identities is not None else set(by_identity)
    for identity in sorted(identities_to_render):
        operations = by_identity.get(identity, {})
        if not operations:
            continue
        operation_cards: list[str] = []
        details_id = _diagnostics_id(identity)
        if heading == "Resolved / historical diagnostics":
            details_id = "resolved-" + details_id
        for operation_key, results in operations.items():
            first = results[0]
            summary_rows = _diagnostic_summary_rows(results)
            technical_details = "".join(
                _diagnostic_technical_details(result, index)
                for index, result in enumerate(
                    sorted(results, key=lambda item: int(item.get("map_result_index") or 0)),
                    start=1,
                )
            )
            release = first.get("release_label") or first.get("terento_version") or "legacy"
            build = first.get("app_build") or "legacy"
            resolution = ""
            if str(first.get("diagnostic_status") or "").upper() == "RESOLVED":
                resolution = " · " + html.escape(
                    str(first.get("resolution_reason") or first.get("resolution_code") or "Resolved")
                )
                if first.get("resolution_note"):
                    resolution += " · " + html.escape(str(first["resolution_note"]))
                if first.get("resolved_at"):
                    resolution += " · resolved " + _timestamp_markup(first.get("resolved_at"))
                if first.get("resolved_by_username"):
                    resolution += " · by " + html.escape(str(first["resolved_by_username"]))
            diagnostic_status = str(first.get("diagnostic_status") or "ACTIVE").upper()
            lifecycle = _diagnostic_state_badge(diagnostic_status)
            identity_state = str(first.get("identity_resolution_state") or "UNRESOLVED").upper()
            if diagnostic_status == "RESOLVED":
                action = f"""<form method='post' action='/admin/diagnostics/reopen' class='diagnostic-inline-form'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='operation_key' value='{html.escape(str(operation_key), quote=True)}'><button type='submit' class='secondary-button'>Reopen</button></form>"""
            else:
                action = f"""<button type='button' class='secondary-button' data-resolve-operation='{html.escape(str(operation_key), quote=True)}'>Resolve</button>"""
            identity_action = f"""<button type='button' class='secondary-button' data-identity-operation='{html.escape(str(operation_key), quote=True)}'>Resolve identity</button>"""
            operation_cards.append(f"""
              <article class='diagnostic-operation'>
                <div class='diagnostic-operation-heading'><div><h4>Diagnostic record</h4><p>{_timestamp_markup(first.get('occurred_at'))} · {html.escape(str(release))} (build {html.escape(str(build))}) · Write: {_diagnostic_boolean(first.get('write_started'))} · {len(results)} map result{'s' if len(results) != 1 else ''}</p><p class='diagnostic-id'>Diagnostic ID: <code>{html.escape(str(operation_key))}</code></p></div><div class='diagnostic-actions'>{lifecycle}{action}{identity_action}</div></div>
                <p class='diagnostic-meta'>Identity: {html.escape(identity_state.title().replace('_', ' '))}{resolution}</p>
                <div class='table-wrap diagnostic-summary-wrap'><table class='diagnostic-summary-table'><caption class='sr-only'>Diagnostic summary</caption><thead><tr><th scope='col'>Region</th><th scope='col'>Result</th><th scope='col'>Stage</th><th scope='col'>Code</th><th scope='col'>Write</th><th scope='col'>Cleanup</th></tr></thead><tbody>{summary_rows}</tbody></table></div>
                {technical_details}
              </article>""")
        sections.append(f"""
          <details class='diagnostic-details' id='{details_id}'>
            <summary>{_diagnostic_group_summary(summary_prefix + identity, operations)}</summary>
            {''.join(operation_cards)}
          </details>""")
    if not sections:
        return ""
    note_markup = f"<p class='table-help'>{html.escape(note)}</p>" if note else ""
    section_class = (
        "diagnostics-list resolved-diagnostics"
        if heading == "Resolved / historical diagnostics"
        else "diagnostics-list"
    )
    return (
        f"<section class='{section_class}' aria-label='{html.escape(heading)}'>"
        f"<h3>{html.escape(heading)}</h3>{note_markup}"
        + "".join(sections)
        + "</section>"
    )


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
    last_evidence = _timestamp_markup(stats.get("lastEvidenceAt")) if stats.get("lastEvidenceAt") else "—"
    return f"""<tr data-device-index='{index}' data-search='{html.escape(search, quote=True)}' data-model='{html.escape(model.lower(), quote=True)}' data-updated='{html.escape(str(catalog.get('updatedAt') or ''), quote=True)}' data-installs='{stats['attempts']}' data-evidence='{html.escape(str(stats.get('lastEvidenceAt') or ''), quote=True)}' data-status='{html.escape(evidence_status.lower())}' tabindex='0' aria-label='Open details for {html.escape(model)}{f', {html.escape(variant)}' if variant != '—' else ''}'>
      <td><button class='device-model-button' type='button' data-device-index='{index}'>{image}<span class='device-model-copy'><strong>{html.escape(model)}</strong>{new_badge}</span></button></td>
      <td>{html.escape(variant)}</td>
      <td>{_admin_status_badge(map_label, f'map-{map_kind}')}</td>
      <td>{_admin_status_badge(authorization_label, f'authorization-{authorization_kind}')}</td>
      <td>{_status_badge(evidence_status)}</td>
      <td class='numeric'>{stats['attempts']}</td>
      <td class='numeric'>{stats['successful']}</td>
      <td>{last_evidence}</td>
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
        f"{sync_data['recordsAdded']} new · {sync_data['recordsUpdated']} updated"
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
    content = f"""
      {_admin_header(user, csrf_token, active="devices")}
      <main class="dashboard devices-page" id="main-content">
        <div class="heading-row"><div><p class="eyebrow">Catalog</p><h1>Devices</h1><p class="lede">Garmin device catalog, map capability, authorization, and compatibility evidence.</p></div></div>
        <section class="admin-summary-strip device-summary-strip" aria-label="Device catalog summary and sync">
          <p class="device-summary-metrics"><strong>{summary['models']} models</strong><span> · {summary['mapCapable']} map-capable · {summary['approved']} approved · {summary['successful']} successful installs</span></p>
          <p class="device-summary-sync"><strong>Last sync</strong> {completed}<span> · {html.escape(sync_line)}</span>{f"<span> · {html.escape(str(sync_data['status'] or '').title())}</span>" if sync_data['status'] else ''}</p>
        </section>
        <section class="evidence-section" aria-labelledby="device-list-title">
          <div class="section-heading"><div><p class="section-kicker">Inventory</p><h2 id="device-list-title">Known models</h2></div><p class="table-help">Times follow the selected time zone</p></div>
          <p class="sr-only">Compatibility status and installation counts remain backend-derived.</p>
          <form class="filter-bar admin-filter-bar device-filter-bar" id="device-filters" role="search">
            <label class="filter-search"><span class="sr-only">Search devices</span><input id="device-search" type="search" placeholder="Search devices" autocomplete="off"></label>
            <label><span class="sr-only">Filter by family</span><select id="device-family"><option value="all">All families</option>{family_options}</select></label>
            <label><span class="sr-only">Filter by map capability</span><select id="device-map"><option value="all">All maps</option><option value="yes">Maps: Yes</option><option value="no">Maps: No</option><option value="unknown">Maps: Unknown</option></select></label>
            <label><span class="sr-only">Filter by installation authorization</span><select id="device-support"><option value="all">All authorizations</option><option value="SUPPORTED">Approved</option><option value="UNSUPPORTED">Blocked</option><option value="NOT_EVALUATED">Pending</option></select></label>
            <label><span class="sr-only">Filter by compatibility status</span><select id="device-status"><option value="all">All statuses</option><option value="TESTING">Testing</option><option value="TESTED">Tested</option><option value="SUPPORTED">Supported</option><option value="VERIFIED">Verified</option><option value="unavailable">Unavailable</option></select></label>
            <p class="results-count" id="device-results-count" aria-live="polite">{len(payload['devices'])} {'model' if len(payload['devices']) == 1 else 'models'}</p>
          </form>
          {empty}
          <div class="table-wrap device-table-wrap"><table class="admin-table"><caption class="sr-only">Device catalog and Terento installation evidence</caption><thead><tr><th scope="col" aria-sort="ascending"><button type="button" class="device-sort-button" data-device-sort="model" aria-label="Model">Model <span aria-hidden="true">↑</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="variant" aria-label="Variant">Variant <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="maps" aria-label="Map capability" title="Map capability">Maps <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="authorization" aria-label="Installation authorization" title="Installation authorization">Authorization <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="status" aria-label="Compatibility status" title="Compatibility status">Status <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="attempts" aria-label="Install attempts" title="Install attempts">Attempts <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="success" aria-label="Successful installations" title="Successful installations">Success <span aria-hidden="true">↕</span></button></th><th scope="col" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="evidence" aria-label="Last evidence" title="Last evidence">Last evidence <span aria-hidden="true">↕</span></button></th></tr></thead><tbody id="device-rows">{rows_html}</tbody></table></div>
          <div class="device-pagination" id="device-pagination" hidden><button type="button" id="device-previous">Previous</button><span id="device-page-status"></span><button type="button" id="device-next">Next</button></div>
        </section>
      </main>
      <dialog class="device-dialog" id="device-dialog" aria-labelledby="device-dialog-title"><div class="device-dialog-inner"><div class="device-dialog-header"><div><p class="section-kicker">Garmin device record</p><h2 id="device-dialog-title">Device details</h2></div><button class="dialog-close" type="button" id="device-dialog-close" aria-label="Close device details">×</button></div><div id="device-dialog-body"></div></div></dialog>
      <script>const terentoAdminDevices = {payload_json};{_devices_script()}</script>
    """
    return _layout("Devices", content)


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


def _statistics_row(row: dict[str, Any], diagnostic_summary: dict[str, int] | None = None) -> str:
    model, variant, identity = _identity_parts(row)
    status_value = _row_compatibility_status(row)
    status = status_value.value if status_value else ""
    search_text = " ".join((model, variant, str(row.get("family") or ""), identity)).strip()
    activity = max((_timestamp_iso(row.get(key)) for key in ("last_success", "last_failure", "last_evidence")), default="")
    diagnostics_url = _diagnostics_url(row)
    error_count = (
        int(row.get("failed_install_count") or 0)
        if "failed_install_count" in row
        else int((diagnostic_summary or {}).get("errors") or 0)
    )
    pending_count = int((diagnostic_summary or {}).get("identity_pending") or 0)
    model_cell = html.escape(model)
    if pending_count:
        model_cell += (
            f" <span class='identity-pending-indicator' aria-label='{pending_count} identity pending'>"
            "Identity pending</span>"
        )
    cells = (
        model_cell, html.escape(variant),
        html.escape(str(row.get("attempted_install_count", 0))), html.escape(str(row.get("successful_install_count", 0))),
        _error_cell(row, diagnostic_summary), _status_badge(status), _timestamp_markup(row.get("last_success")),
    )
    return (
        f"<tr class='evidence-model-row' data-search='{html.escape(search_text, quote=True)}' data-status='{html.escape(status.lower(), quote=True)}' data-activity='{html.escape(activity, quote=True)}' data-attempts='{int(row.get('attempted_install_count') or 0)}' data-errors='{error_count}' data-diagnostics-url='{html.escape(diagnostics_url, quote=True)}' tabindex='0' role='link' aria-label='Review diagnostics for {html.escape(model)}{f', {html.escape(variant)}' if variant != '—' else ''}'>"
        + "".join(f"<td>{cell}</td>" for cell in cells)
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


def _devices_script() -> str:
    return r"""(() => {
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
      const dialog = document.querySelector('#device-dialog');
      const dialogTitle = document.querySelector('#device-dialog-title');
      const dialogBody = document.querySelector('#device-dialog-body');
      const close = document.querySelector('#device-dialog-close');
      if (!body || !form || !search || !family || !map || !support || !status || !count || !dialog) return;

      const pageSize = 50;
      let page = 0;
      let sortKey = 'model';
      let sortDirection = 'ascending';
      let lastFocused = null;
      const escapeHtml = (value) => String(value ?? '—')
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
      const display = (value) => value === null || value === undefined || value === '' ? '—' : value;
      const utcDate = (value) => value ? new Date(value).toISOString().slice(0, 16).replace('T', ' ') : '—';
      const date = (value) => value ? `<time class="admin-timestamp" data-admin-timestamp="${escapeHtml(value)}">${escapeHtml(window.TerentoAdminTime ? window.TerentoAdminTime.format(value) : utcDate(value))}</time>` : '—';
      const mapValue = (device) => device.mapCapable === true ? 'yes' : device.mapCapable === false ? 'no' : 'unknown';
      const authorizationLabel = (value) => ({APPROVED: 'Approved', BLOCKED: 'Blocked', PENDING: 'Pending'})[value] || 'Pending';
      const evidenceLabel = (value) => ({TESTING: 'Testing', TESTED: 'Tested', SUPPORTED: 'Supported', VERIFIED: 'Verified'})[value] || 'Unavailable';
      const statusBadge = (value) => value ? `<span class="status-badge status-${String(value).toLowerCase()}">${escapeHtml(evidenceLabel(value))}</span>` : '<span class="status-badge status-unavailable">Unavailable</span>';
      const mapBadge = (label, value) => `<span class="admin-state admin-state-map-${value}">${escapeHtml(label)}</span>`;
      const authorizationBadge = (value) => `<span class="admin-state admin-state-authorization-${String(value || 'PENDING').toLowerCase()}">${escapeHtml(authorizationLabel(value))}</span>`;
      const publicationBadge = (publication) => publication?.published
        ? '<span class="admin-state admin-state-publication-published">Published</span>'
        : publication?.eligible
          ? '<span class="admin-state admin-state-publication-pending">Approval required</span>'
          : '<span class="admin-state admin-state-publication-unavailable">Not eligible</span>';
      const deviceSearch = (device) => [device.id, device.model, device.canonicalModel, device.family, device.familyName, device.variant, device.caseSizeMm, device.partNumber, device.displayType].filter(Boolean).join(' ').toLocaleLowerCase();
      const textCompare = (a, b) => String(a || '').localeCompare(String(b || ''), undefined, {sensitivity: 'base', numeric: true});
      const statusOrder = {unavailable: 0, TESTING: 1, TESTED: 2, SUPPORTED: 3, VERIFIED: 4};
      const mapOrder = {unknown: 0, no: 1, yes: 2};
      const authorizationOrder = {NOT_EVALUATED: 0, UNSUPPORTED: 1, SUPPORTED: 2};
      const sortValue = (device, key) => ({
        model: device.model,
        variant: device.variant,
        maps: mapOrder[mapValue(device)],
        authorization: authorizationOrder[device.supportStatus || 'NOT_EVALUATED'],
        status: statusOrder[device.evidenceStatus || 'unavailable'],
        attempts: Number(device.installationStats.attempts || 0),
        success: Number(device.installationStats.successful || 0),
        evidence: device.installationStats.lastEvidenceAt ? Date.parse(device.installationStats.lastEvidenceAt) : null,
      })[key];
      const compareDevices = (a, b) => {
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
      const matching = () => {
        const query = search.value.trim().toLocaleLowerCase();
        return devices.filter((device) => {
          const matchesSearch = !query || deviceSearch(device).includes(query);
          const matchesFamily = family.value === 'all' || family.value === (device.familyName || device.family);
          const matchesMap = map.value === 'all' || mapValue(device) === map.value;
          const matchesAuthorization = support.value === 'all' || (device.supportStatus || 'NOT_EVALUATED') === support.value;
          const matchesStatus = status.value === 'all' || (device.evidenceStatus || 'unavailable') === status.value;
          return matchesSearch && matchesFamily && matchesMap && matchesAuthorization && matchesStatus;
        }).sort(compareDevices);
      };
      const usbIdentity = (identities) => {
        const known = (identities || []).filter((identity) => identity.vendorId !== null && identity.vendorId !== undefined && identity.productId !== null && identity.productId !== undefined);
        if (!known.length) return '<span class="muted-value" title="No exact USB identity is currently recorded for this catalog profile.">Not known</span>';
        const value = (number) => number === null || number === undefined || number === '' || !Number.isFinite(Number(number)) ? 'Not known' : `0x${Number(number).toString(16).padStart(4, '0').toUpperCase()}`;
        return known.map((identity) => `<span title="USB identity observed for this exact catalog profile. Decimal: ${escapeHtml(identity.vendorId)} · ${escapeHtml(identity.productId)}">VID ${value(identity.vendorId)} · PID ${value(identity.productId)}</span>`).join(', ');
      };
      const openDevice = (device) => {
        if (!device) return;
        lastFocused = document.activeElement;
        const stats = device.installationStats;
        const catalog = device.catalog;
        const publication = device.publicCompatibility || {};
        const mapLabel = device.mapCapable === true ? 'Yes' : device.mapCapable === false ? 'No' : 'Unknown';
        const image = device.image || {};
        const imageSourceLabel = image.origin === 'controlled' ? 'Terento · approved asset' : image.origin === 'garmin-source' ? 'Garmin · exact model' : image.origin === 'fallback' ? 'Terento · neutral fallback' : 'Not available';
        const imageMatchLabel = image.origin === 'controlled' ? 'Approved Terento asset' : image.origin === 'garmin-source' ? 'Official product media' : image.origin === 'fallback' ? 'Generic fallback' : 'No image';
        const imageSourceUrl = device.sourceAsset?.url || image.url || '';
        const imageMarkup = image.url ? `<img class="device-detail-image" src="${escapeHtml(image.url)}" alt="">` : '';
        const canonicalRow = device.canonicalModel && device.canonicalModel.toLocaleLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '') !== device.model.toLocaleLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '') ? `<div><dt>Canonical model</dt><dd>${escapeHtml(device.canonicalModel)}</dd></div>` : '';
        dialogTitle.innerHTML = `<span>${escapeHtml(device.model)}</span><span class="modal-subtitle">${escapeHtml(device.variant)}</span>${statusBadge(device.evidenceStatus)}`;
        dialogBody.innerHTML = `
          <div class="device-modal-hero">${imageMarkup}</div>
          <div class="device-detail-grid">
            <section><p class="detail-kicker">Identity</p><dl>
              <div><dt>Model</dt><dd>${escapeHtml(device.model)}</dd></div>${canonicalRow}
              <div><dt>Variant</dt><dd>${escapeHtml(device.variant)}</dd></div>
              <div><dt>Family</dt><dd>${escapeHtml(device.familyName || device.family)}</dd></div>
              <div><dt>Part number</dt><dd>${escapeHtml(device.partNumber)}</dd></div>
              <div><dt>Catalog ID</dt><dd class="technical-value device-catalog-id">${escapeHtml(device.id)}</dd></div>
            </dl></section>
            <section><p class="detail-kicker">Capability &amp; authorization</p><dl>
              <div><dt>Map capability</dt><dd>${mapBadge(mapLabel, mapValue(device))}</dd></div>
              <div><dt>Installation authorization</dt><dd>${authorizationBadge(device.installationAuthorization)}</dd></div>
              <div><dt>USB identity <button class="info-control info-control-inline" type="button" title="VID/PID is shown only when it was recorded from this exact catalog profile. No value is inferred." aria-label="USB identity information">i</button></dt><dd class="technical-value">${usbIdentity(device.usbIdentities)}</dd></div>
            </dl></section>
            <section><p class="detail-kicker">Compatibility evidence</p><dl>
              <div><dt>Compatibility status</dt><dd class="detail-status-value">${escapeHtml(evidenceLabel(device.evidenceStatus))}</dd></div>
              <div><dt>Public listing</dt><dd>${publicationBadge(publication)}</dd></div>
              <div><dt>Attempts</dt><dd>${stats.attempts}</dd></div>
              <div><dt>Successful</dt><dd>${stats.successful}</dd></div>
              <div><dt>Failed</dt><dd>${stats.failed}</dd></div>
              <div><dt>Rate</dt><dd>${stats.successRate === null ? '—' : `${stats.successRate}%`}</dd></div>
              <div><dt>First success</dt><dd>${date(stats.firstSuccessfulAt)}</dd></div>
              <div><dt>Last evidence</dt><dd>${date(stats.lastEvidenceAt)}</dd></div>
            </dl></section>
          </div>
          <section class="device-support-review" aria-labelledby="device-support-review-title">
            <p class="detail-kicker" id="device-support-review-title">Installation authorization</p>
            <div class="authorization-current" data-authorization-current><span>Current</span><span class="authorization-current-value">${authorizationBadge(device.installationAuthorization)}</span><button type="button" class="secondary-button" data-authorization-change>Change</button></div>
            <form method="post" action="/admin/devices/authorization" data-authorization-form hidden>
              <input type="hidden" name="csrf_token" value="${escapeHtml(terentoAdminDevices.csrfToken)}">
              <input type="hidden" name="device_id" value="${escapeHtml(device.id)}">
              <label for="authorization-${escapeHtml(device.id)}">Change to<select id="authorization-${escapeHtml(device.id)}" name="support_status">
                <option value="SUPPORTED"${device.supportStatus === 'SUPPORTED' ? ' selected' : ''}>Approved</option>
                <option value="UNSUPPORTED"${device.supportStatus === 'UNSUPPORTED' ? ' selected' : ''}>Blocked</option>
                <option value="NOT_EVALUATED"${device.supportStatus === 'NOT_EVALUATED' ? ' selected' : ''}>Pending</option>
              </select></label>
              <label>Note <span class="optional-label">Optional</span><textarea name="note" rows="2" placeholder="Why this authorization changed"></textarea></label>
              <div class="dialog-actions"><button type="button" class="secondary-button" data-authorization-cancel>Cancel</button><button type="submit" disabled>Save</button></div>
            </form>
          </section>
          <section class="device-public-review" aria-labelledby="device-public-review-title">
            <p class="detail-kicker" id="device-public-review-title">Public compatibility</p>
            <div class="authorization-current"><span>Current</span><span class="authorization-current-value">${publicationBadge(publication)}</span></div>
            <p class="review-help">${publication.published
              ? `Visible on terento.app/compatibility/ with the evidence status ${escapeHtml(evidenceLabel(device.evidenceStatus))}.`
              : publication.eligible
                ? `Evidence is ready. Operator approval is required before this exact model is listed publicly.`
                : `Exact recognized map-capable evidence is required before publication.`}</p>
            ${publication.eligible ? `<form method="post" action="/admin/devices/public-compatibility">
              <input type="hidden" name="csrf_token" value="${escapeHtml(terentoAdminDevices.csrfToken)}">
              <input type="hidden" name="device_id" value="${escapeHtml(device.id)}">
              <input type="hidden" name="publication_action" value="${publication.published ? 'UNPUBLISH' : 'PUBLISH'}">
              <label>Note <span class="optional-label">Optional</span><textarea name="note" rows="2" placeholder="Why this public review changed"></textarea></label>
              <div class="dialog-actions"><button type="submit" class="${publication.published ? 'secondary-button' : ''}">${publication.published ? 'Remove from public compatibility' : 'Approve and publish'}</button></div>
            </form>` : ''}
          </section>
          <details class="device-catalog-details"><summary>Catalog details</summary><dl>
            <div><dt>Active</dt><dd>${device.active ? 'Yes' : 'No'}</dd></div>
            <div><dt>First seen</dt><dd>${date(catalog.firstSeenAt)}</dd></div>
            <div><dt>Created</dt><dd>${date(catalog.createdAt)}</dd></div>
            <div><dt>Updated</dt><dd>${date(catalog.updatedAt)}</dd></div>
            <div><dt>Last seen</dt><dd>${date(catalog.lastSeenAt)}</dd></div>
            <div><dt>New in latest sync</dt><dd>${catalog.newInLatestSync ? 'Yes' : 'No'}</dd></div>
            <div><dt>Image provenance</dt><dd>Catalog metadata only</dd></div>
            <div><dt>Image source</dt><dd title="${escapeHtml(imageSourceUrl)}">${escapeHtml(imageSourceLabel)}</dd></div>
            <div><dt>Match</dt><dd>${escapeHtml(imageMatchLabel)}</dd></div>
          </dl>${device.productURL ? `<p class="device-product-link"><a href="${escapeHtml(device.productURL)}" target="_blank" rel="noreferrer">Open Garmin product page</a></p>` : ''}</details>
        `;
        const authorizationForm = dialog.querySelector('[data-authorization-form]');
        const authorizationChange = dialog.querySelector('[data-authorization-change]');
        const authorizationCancel = dialog.querySelector('[data-authorization-cancel]');
        const authorizationSelect = authorizationForm?.querySelector('select');
        const authorizationSave = authorizationForm?.querySelector('button[type="submit"]');
        const initialAuthorization = authorizationSelect?.value;
        const syncAuthorizationForm = () => {
          if (authorizationSave) authorizationSave.disabled = !authorizationSelect || authorizationSelect.value === initialAuthorization;
        };
        authorizationChange?.addEventListener('click', () => {
          if (!authorizationForm) return;
          authorizationForm.hidden = false;
          authorizationChange.hidden = true;
          authorizationSelect?.focus();
          syncAuthorizationForm();
        });
        authorizationSelect?.addEventListener('change', syncAuthorizationForm);
        authorizationCancel?.addEventListener('click', () => {
          if (!authorizationForm) return;
          authorizationSelect.value = initialAuthorization;
          const note = authorizationForm.querySelector('textarea');
          if (note) note.value = '';
          authorizationForm.hidden = true;
          authorizationChange.hidden = false;
          syncAuthorizationForm();
          authorizationChange.focus();
        });
        syncAuthorizationForm();
        if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
        dialog.querySelector('[data-authorization-change]')?.focus();
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
        count.textContent = visible.length === devices.length ? `${visible.length} ${visible.length === 1 ? 'model' : 'models'}` : `${visible.length} of ${devices.length} models`;
        pagination.hidden = visible.length <= pageSize;
        pageStatus.textContent = `Page ${page + 1} of ${totalPages}`;
        previous.disabled = page === 0;
        next.disabled = page >= totalPages - 1;
      };
      const reset = () => { page = 0; refresh(); };
      form.addEventListener('submit', (event) => event.preventDefault());
      [search, family, map, support, status].forEach((control) => control.addEventListener(control === search ? 'input' : 'change', reset));
      sortButtons.forEach((button) => button.addEventListener('click', () => {
        const key = button.dataset.deviceSort;
        if (sortKey === key) sortDirection = sortDirection === 'ascending' ? 'descending' : 'ascending';
        else { sortKey = key; sortDirection = 'ascending'; }
        updateSortHeaders();
        reset();
      }));
      previous.addEventListener('click', () => { page -= 1; refresh(); });
      next.addEventListener('click', () => { page += 1; refresh(); });
      body.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-device-index]');
        const row = event.target.closest('tr[data-device-index]');
        if (button || !row) return;
        openDevice(devices[Number(row.dataset.deviceIndex)]);
      });
      body.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const row = event.target.closest('tr[data-device-index]');
        if (!row || event.target.closest('button')) return;
        event.preventDefault();
        openDevice(devices[Number(row.dataset.deviceIndex)]);
      });
      body.querySelectorAll('button[data-device-index]').forEach((button) => button.addEventListener('click', () => openDevice(devices[Number(button.dataset.deviceIndex)])));
      const closeDialog = () => { dialog.close(); lastFocused?.focus(); };
      close.addEventListener('click', closeDialog);
      dialog.addEventListener('cancel', () => window.setTimeout(() => lastFocused?.focus(), 0));
      dialog.addEventListener('click', (event) => { if (event.target === dialog) closeDialog(); });
      dialog.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const focusable = [...dialog.querySelectorAll('button,select,input,textarea,a')].filter((element) => !element.disabled && element.offsetParent !== null);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      });
      updateSortHeaders();
      refresh();
    })();"""


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
      const body = document.querySelector('#evidence-rows');
      const count = document.querySelector('#results-count');
      if (!form || !search || !status || !sort || !body || !count) return;
      const rows = [...body.querySelectorAll('tr')];
      const refresh = () => {
        const query = search.value.trim().toLocaleLowerCase();
        const selectedStatus = status.value;
        const visible = rows.filter((row) => {
          const matchesSearch = !query || row.dataset.search.toLocaleLowerCase().includes(query);
          const matchesStatus = selectedStatus === 'all' || row.dataset.status === selectedStatus;
          row.hidden = !(matchesSearch && matchesStatus);
          return !row.hidden;
        });
        visible.sort((a, b) => {
          if (sort.value === 'latest') return (b.dataset.activity || '').localeCompare(a.dataset.activity || '');
          if (sort.value === 'errors') return Number(b.dataset.errors || 0) - Number(a.dataset.errors || 0);
          if (sort.value === 'model') return (a.dataset.search || '').localeCompare(b.dataset.search || '');
          return Number(b.dataset.attempts || 0) - Number(a.dataset.attempts || 0);
        });
        visible.forEach((row) => body.appendChild(row));
        const label = visible.length === 1 ? 'model' : 'models';
        count.textContent = visible.length === rows.length ? `${visible.length} ${label}` : `${visible.length} of ${rows.length} ${label}`;
      };
      form.addEventListener('submit', (event) => event.preventDefault());
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


def _diagnostics_script() -> str:
    return """(() => {
      const filter = document.querySelector('#diagnostic-state-filter');
      const body = document.querySelector('#diagnostic-rows');
      const count = document.querySelector('#diagnostic-results-count');
      if (!filter || !body || !count) return;
      const rows = [...body.querySelectorAll('tr[data-diagnostic-state]')];
      const dialogs = [...document.querySelectorAll('.diagnostic-detail-dialog')];
      let lastFocused = null;
      const requestedFilter = new URLSearchParams(window.location.search).get('state');
      if (requestedFilter && [...filter.options].some((option) => option.value === requestedFilter)) filter.value = requestedFilter;
      const refresh = () => {
          const selected = filter.value;
          const visible = rows.filter((row) => {
            const matches = selected === 'all'
            || (selected === 'succeeded' && row.dataset.diagnosticResult === 'succeeded')
            || (selected === 'open' && row.dataset.reviewOpen === 'true')
            || (selected === 'resolved' && row.dataset.reviewResolved === 'true')
            || (selected === 'identity-pending' && row.dataset.identityPending === 'true')
            || (selected === 'failed' && row.dataset.diagnosticResult === 'failed')
            || (selected === 'with-issue' && row.dataset.hasIssue === 'true');
          row.hidden = !matches;
          return matches;
        });
        const label = visible.length === 1 ? 'record' : 'records';
        count.textContent = `${visible.length} ${label}`;
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
      filter.addEventListener('input', refresh);
      document.querySelectorAll('.diagnostic-review').forEach((button) => button.addEventListener('click', () => open(document.getElementById(button.dataset.dialogId), button)));
      document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => close(button.closest('dialog'))));
      dialogs.forEach((dialog) => {
        dialog.addEventListener('click', (event) => { if (event.target === dialog) close(dialog); });
        dialog.addEventListener('cancel', () => window.setTimeout(() => lastFocused?.focus(), 0));
        dialog.addEventListener('keydown', (event) => {
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
        const date = new Date(value);
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
    })();"""


ADMIN_STYLES = """
@font-face{font-family:"Instrument Sans";src:url("https://terento.app/assets/fonts/instrument-sans.woff2") format("woff2");font-weight:400 700;font-display:swap}
@font-face{font-family:"Inter";src:url("https://terento.app/assets/fonts/inter-variable.woff2") format("woff2");font-weight:100 900;font-display:swap}
:root{--off-white:#F7F3EC;--graphite:#222A2B;--sky:#7898A8;--lichen:#9AA58B;--stone:#B39A78;--interactive:#577787;--interactive-hover:#4F6E7E;--secondary:#6D706F;--surface:#FFFFFF;--surface-muted:#F1EEE7;--border:#D7DDDA;--danger:#9A493D;--success-bg:#E8F0E5;--admin-control-height:38px;--admin-control-radius:8px;--admin-control-padding-x:10px;--admin-control-font-size:13px;--admin-placeholder:#858B89;--admin-focus-ring:3px solid color-mix(in srgb,var(--sky) 58%,white);--admin-topbar-height:68px;--max-width:1440px}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{min-width:0}
body{margin:0;min-width:0;background:var(--off-white);color:var(--graphite);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
button,input,select,textarea{font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:var(--admin-control-font-size);line-height:1.3}
input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]),select,textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-weight:500}
select{padding-right:28px;color-scheme:light}
textarea{min-height:78px;resize:vertical}
input::placeholder,textarea::placeholder{color:var(--admin-placeholder);opacity:1;font-weight:400}
input:disabled,select:disabled,textarea:disabled,button:disabled{cursor:not-allowed;background:var(--surface-muted);border-color:color-mix(in srgb,var(--border) 78%,var(--surface-muted));color:var(--secondary);opacity:1}
button{cursor:pointer}
.admin-action-dialog button:not(.secondary-button),.auth-card button:not(.link-button),.copy-button,.device-support-review button[type="submit"]{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:#fff;font-weight:700}
.admin-action-dialog button:not(.secondary-button):hover,.auth-card button:not(.link-button):hover,.copy-button:hover,.device-support-review button[type="submit"]:hover{background:var(--interactive-hover)}
.admin-topbar{position:sticky;top:0;z-index:30;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);background:var(--off-white);box-shadow:0 1px 0 rgba(34,42,43,.04)}
.admin-topbar-inner{width:min(calc(100% - 48px),var(--max-width));min-height:68px;margin:0 auto;display:grid;grid-template-columns:minmax(180px,1fr) max-content minmax(385px,1fr);align-items:center;gap:16px}
.admin-header-zone{min-width:0}
.admin-header-left{display:flex;align-items:center;justify-self:start}
.admin-brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--graphite);font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;font-size:20px;font-weight:700;letter-spacing:-.02em}
.admin-brand img{width:25px;height:29px;object-fit:contain}
.admin-badge{display:inline-flex;align-items:center;min-height:22px;padding:3px 8px;border:1px solid color-mix(in srgb,var(--sky) 48%,var(--border));border-radius:999px;color:var(--interactive);font-family:"Inter",sans-serif;font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.admin-section-nav{display:flex;align-items:center;justify-content:center;gap:4px;justify-self:center;color:var(--secondary);font-size:13px;font-weight:650}
.admin-section-nav a,.admin-nav a,.link-button{display:inline-flex;align-items:center;min-height:32px;padding:6px 8px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:none;text-decoration:none;color:var(--secondary);font-weight:650;transition:background-color .15s ease,border-color .15s ease,color .15s ease}
.admin-section-nav a:hover,.admin-nav a:hover,.link-button:hover,.admin-section-nav a:active,.admin-nav a:active,.link-button:active{background:color-mix(in srgb,var(--sky) 12%,transparent);color:var(--interactive)}
.admin-section-nav a.active{background:color-mix(in srgb,var(--sky) 13%,var(--off-white));border-color:color-mix(in srgb,var(--sky) 28%,var(--border));color:var(--interactive);box-shadow:none}
.needs-review-menu{position:relative}
.needs-review-menu summary{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:6px 8px;border:1px solid color-mix(in srgb,var(--stone) 45%,var(--border));border-radius:var(--admin-control-radius);background:color-mix(in srgb,var(--stone) 10%,var(--off-white));color:var(--graphite);cursor:pointer;list-style:none;font-weight:700}
.needs-review-menu summary::-webkit-details-marker{display:none}
.needs-review-menu summary:focus-visible{outline:3px solid var(--admin-focus-ring);outline-offset:2px}
.needs-review-count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--stone);color:white;font-size:10px;font-weight:800}
.needs-review-popover{position:absolute;z-index:20;top:calc(100% + 7px);right:0;width:230px;padding:7px;border:1px solid var(--border);border-radius:10px;background:var(--surface);box-shadow:0 14px 34px rgba(34,42,43,.16)}
.needs-review-popover a{display:flex!important;justify-content:space-between;gap:12px;width:100%;padding:8px 9px!important;color:var(--graphite)!important}
.needs-review-popover strong{font-variant-numeric:tabular-nums}
.admin-nav{display:flex;align-items:center;justify-self:end;min-width:0;gap:8px;color:var(--secondary);font-size:13px;white-space:nowrap}
.admin-nav form{display:flex;align-items:center;margin:0}
.admin-user{padding:6px 0;color:var(--graphite);font-weight:650;white-space:nowrap}
.timezone-control{display:flex;align-items:center;gap:7px;color:var(--secondary);font-size:11px;font-weight:650;white-space:nowrap}
.timezone-control select{width:clamp(150px,17vw,205px);min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-size:var(--admin-control-font-size)}
.admin-website-link{white-space:nowrap}
.dashboard{width:min(calc(100% - 48px),var(--max-width));margin:0 auto;padding:40px 0 64px}
.heading-row{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;margin-bottom:28px}
.eyebrow,.section-kicker{margin:0 0 8px;color:var(--interactive);font-size:12px;font-weight:750;letter-spacing:.14em;text-transform:uppercase}
h1,h2{margin:0;font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;letter-spacing:-.035em}
h1{font-size:clamp(32px,3.5vw,44px);line-height:1.06}
h2{font-size:22px;line-height:1.15}
.lede{max-width:680px;margin:12px 0 0;color:var(--secondary);font-size:16px}
.evidence-section{margin-top:2px}
.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:14px}
.section-heading .section-kicker{margin-bottom:5px}
.table-help,.results-count{margin:0;color:var(--secondary);font-size:12px}
.filter-bar{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap;margin:0 0 10px;padding:8px;background:var(--surface-muted);border:1px solid var(--border);border-radius:12px}
.filter-bar label{display:flex;align-items:stretch;margin:0}
.filter-bar input,.filter-bar select{height:var(--admin-control-height);min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius);font:600 var(--admin-control-font-size)/1.2 "Instrument Sans","Helvetica Neue",Arial,sans-serif}
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
td:nth-child(4),td:nth-child(5),td:nth-child(6),td:nth-child(7){font-variant-numeric:tabular-nums}
.muted-value{color:var(--secondary)}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:700}
.evidence-table-wrap table{min-width:760px}.evidence-model-row{cursor:pointer}.evidence-model-row:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}.evidence-model-row:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:-3px}.evidence-model-row td:nth-child(3),.evidence-model-row td:nth-child(4){font-variant-numeric:tabular-nums}.error-count{text-decoration:none}.identity-pending-indicator{display:inline-flex;align-items:center;margin-left:6px;padding:3px 6px;border:1px solid var(--border);border-radius:999px;color:var(--secondary);font-size:10px;font-weight:700;white-space:nowrap}.evidence-table-note{margin:10px 3px 0}.back-link{margin:0 0 20px;color:var(--interactive);font-size:13px;font-weight:700}.back-link a{text-underline-offset:3px}.diagnostic-model-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 30px}.diagnostic-model-metrics article{min-height:82px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.diagnostic-model-metrics span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.diagnostic-model-metrics strong{display:block;margin-top:4px;font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;font-size:25px;line-height:1.15}.diagnostic-model-metrics .status-badge{margin-top:5px}.diagnostic-filter-bar{justify-content:flex-start}.diagnostic-list-wrap{max-height:min(70vh,720px)}.diagnostic-list-table{min-width:920px}.diagnostic-list-table th,.diagnostic-list-table td{white-space:normal;overflow-wrap:anywhere}.diagnostic-list-table td:first-child{white-space:nowrap}.diagnostic-list-table th:last-child,.diagnostic-list-table td:last-child{text-align:right}.diagnostic-list-table tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}.diagnostic-state{display:inline-flex;align-items:center;min-height:24px;padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-state-open{background:#F0E9E5;border-color:#D6BDB2;color:#7A493D}.diagnostic-state-resolved{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}.diagnostic-state-identity_pending{background:var(--surface-muted);color:var(--secondary)}.diagnostic-list-table .github-issue,.github-current .github-issue{color:var(--interactive);font-weight:700;white-space:nowrap}.diagnostic-detail-dialog{width:min(860px,calc(100% - 32px));max-height:min(900px,calc(100% - 32px));padding:0;border:0;border-radius:16px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}.diagnostic-detail-dialog::backdrop{background:rgba(34,42,43,.34)}.diagnostic-detail-inner{max-height:min(900px,calc(100vh - 32px));padding:24px;overflow:auto}.diagnostic-detail-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px;margin:0;border-top:1px solid var(--border)}.diagnostic-detail-summary div{display:grid;grid-template-columns:minmax(95px,.8fr) minmax(0,1.2fr);gap:12px;padding:9px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-detail-summary dt{color:var(--secondary);font-size:12px}.diagnostic-detail-summary dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.diagnostic-actions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:22px}.diagnostic-action-form{min-width:0;padding:14px;background:var(--surface-muted);border-radius:10px}.diagnostic-action-form h4{margin:0 0 10px;font-size:13px}.diagnostic-action-form label{display:block;margin:10px 0;color:var(--graphite);font-size:12px;font-weight:650}.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{display:block;width:100%;margin-top:5px;min-height:36px;padding:7px 9px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite);font-size:12px}.diagnostic-action-form textarea{resize:vertical}.diagnostic-action-form button{margin-top:6px}.identity-selection{margin:8px 0;color:var(--secondary);font-size:11px}.identity-selection code{color:var(--graphite);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.github-review{grid-column:1/-1}.github-current{margin:0 0 8px;font-size:13px}.github-actions{margin:0 0 4px}.github-link-form{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px}.github-link-form label{margin:0}.github-link-form button{white-space:nowrap}.github-remove-form{display:inline-block;margin:8px 0 0}.diagnostic-technical-all{margin-top:16px}.diagnostic-technical-all>summary{font-size:13px}
.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius)}
.github-issue-disclosure{margin-top:8px}.github-issue-disclosure>summary{width:max-content;cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750;text-underline-offset:3px}.github-issue-disclosure>summary:hover{text-decoration:underline}.github-issue-controls{margin-top:12px}
.diagnostic-operation table{min-width:0}.diagnostic-id{font-size:11px!important;color:var(--secondary)!important}.diagnostic-id code{font-size:10px;color:var(--secondary)}.diagnostic-summary-table{min-width:0!important;table-layout:fixed}.diagnostic-summary-table th,.diagnostic-summary-table td{white-space:normal;overflow-wrap:anywhere}.diagnostic-summary-table th:nth-child(1){width:18%}.diagnostic-summary-table th:nth-child(2){width:18%}.diagnostic-summary-table th:nth-child(3){width:18%}.diagnostic-summary-table th:nth-child(4){width:20%}.diagnostic-summary-table th:nth-child(5){width:12%}.diagnostic-summary-table th:nth-child(6){width:14%}.diagnostic-code-value{display:inline-flex;flex-direction:column;gap:2px;overflow-wrap:anywhere}.diagnostic-native-code{color:var(--secondary);font-size:10px;font-weight:500}.diagnostic-result{display:inline-flex;align-items:center;min-height:22px;padding:4px 7px;border:1px solid var(--border);border-radius:999px;font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-result-succeeded{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}.diagnostic-result-failed{background:#F0E9E5;border-color:#D6BDB2;color:#7A493D}.diagnostic-result-not-started,.diagnostic-result-unknown{background:var(--surface-muted);color:var(--secondary)}.diagnostic-group-title{font-weight:700}.diagnostic-group-meta{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap;margin-left:8px}.diagnostic-chip{display:inline-flex;align-items:center;min-height:21px;padding:3px 7px;border:1px solid var(--border);border-radius:999px;background:var(--surface-muted);color:var(--secondary);font-size:10px;font-weight:750;line-height:1;white-space:nowrap}.diagnostic-chip.github-issue{color:var(--interactive)}.diagnostic-summary-action{float:right;color:var(--secondary);font-size:11px;font-weight:600}.diagnostic-technical-details{margin:10px 0 0;padding:9px 11px;background:var(--surface-muted);border-radius:8px}.diagnostic-technical-details summary{cursor:pointer;color:var(--secondary);font-size:12px;font-weight:700}.diagnostic-technical-details dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px;margin:10px 0 0}.diagnostic-technical-details dl div{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-top:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-technical-details dt{color:var(--secondary);font-size:11px}.diagnostic-technical-details dd{margin:0;text-align:right;font:500 11px ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
.status-badge{display:inline-flex;align-items:center;justify-content:center;min-width:74px;min-height:28px;padding:6px 10px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;letter-spacing:.03em;line-height:1;text-transform:uppercase}
.status-tested{background:#EDE8DF;border-color:#CFC2AE;color:#5B5144}
.status-supported{background:#E3EDF0;border-color:#ABC3CD;color:#375E6D}
.status-verified{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}
.status-testing{background:#F0F1ED;border-color:#D8DDD8;color:#60706C}
.status-enabled{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}
.status-disabled{background:#F0F1ED;border-color:#D8DDD8;color:#60706C}
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
.error{background:#FBEAE6;color:#81372D}
.success{background:var(--success-bg);color:#365B3B}
.account{margin-top:48px}
.campaign-card{padding:24px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.campaign-card>.section-heading{margin-bottom:22px}
.campaign-preset-row{display:flex;align-items:center;gap:12px;margin-bottom:20px;padding:8px;background:var(--surface-muted);border:1px solid var(--border);border-radius:12px}
.campaign-preset-row .campaign-label{margin:0;white-space:nowrap}
.campaign-preset-row select{width:min(360px,100%);margin-left:auto}
.campaign-field input,.campaign-field select,.campaign-preset-row select{height:var(--admin-control-height);min-height:var(--admin-control-height);box-sizing:border-box;padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:var(--admin-control-font-size);font-weight:500;line-height:1.3}
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
.info-popover code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:var(--graphite)}
.custom-input{margin-top:9px;padding:10px;background:var(--surface-muted);border-radius:8px}
.custom-input label{display:block;margin:0 0 6px;color:var(--secondary);font-size:11px;font-weight:650}
.custom-input input{min-height:38px}
.campaign-result{margin-top:26px;padding-top:21px;border-top:1px solid var(--border)}
.incomplete-state{margin:0;padding:12px 14px;background:var(--surface-muted);border:1px dashed var(--border);border-radius:8px;color:var(--secondary);font-size:13px}
.generated-url-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px}
.generated-url{display:block;min-width:0;padding:12px 13px;overflow:auto;border:1px solid var(--border);border-radius:8px;background:var(--surface-muted);color:var(--graphite);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;white-space:nowrap}
.copy-button{min-height:42px;padding:9px 15px;border:0;border-radius:8px;background:var(--interactive);color:white;font-weight:700}
.copy-button:hover{background:var(--interactive-hover)}
.copy-button:disabled{cursor:not-allowed;opacity:.45}
.copy-status{min-width:54px;color:var(--interactive);font-size:12px;font-weight:700}
.attribution-preview{display:grid;grid-template-columns:minmax(220px,.65fr) minmax(0,1.35fr);gap:24px;margin-top:26px;padding-top:21px;border-top:1px solid var(--border)}
.attribution-preview h2{font-size:20px}
.attribution-preview .table-help{margin-top:8px;max-width:420px}
.preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:0}
.preview-grid div{padding:10px 12px;background:var(--surface-muted);border-radius:8px}
.preview-grid dt{color:var(--secondary);font-size:11px;font-weight:650}
.preview-grid dd{margin:2px 0 0;overflow-wrap:anywhere;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.admin-summary-strip{display:flex;align-items:center;justify-content:space-between;gap:24px;margin:0 0 28px;padding:13px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;color:var(--secondary);font-size:13px}
.admin-summary-strip p{margin:0;min-width:0}
.admin-summary-metrics strong,.admin-summary-context strong,.device-summary-metrics strong,.device-summary-sync strong{color:var(--graphite);font-weight:750}
.admin-summary-context,.device-summary-sync{text-align:right;white-space:nowrap}
.device-filter-bar{position:sticky;top:calc(var(--admin-topbar-height) + 8px);z-index:20;align-items:stretch;margin-bottom:10px;background:var(--surface-muted);box-shadow:0 2px 0 rgba(34,42,43,.05)}
.device-table-wrap{overflow:visible}
.device-table-wrap table{min-width:0;table-layout:fixed}
.device-table-wrap th:nth-child(1){width:20%}.device-table-wrap th:nth-child(2){width:18%}.device-table-wrap th:nth-child(3){width:9%}.device-table-wrap th:nth-child(4){width:14%}.device-table-wrap th:nth-child(5){width:11%}.device-table-wrap th:nth-child(6){width:9%}.device-table-wrap th:nth-child(7){width:8%}.device-table-wrap th:nth-child(8){width:11%}
.device-table-wrap thead{position:static}
.device-table-wrap thead th{position:sticky;top:calc(var(--admin-topbar-height) + var(--device-filter-height, 54px) + 18px);z-index:10}
.device-table-wrap th,.device-table-wrap td{white-space:normal;overflow-wrap:anywhere}
.device-sort-button{display:inline-flex;align-items:center;gap:5px;width:auto;min-height:0;margin:0;padding:0;border:0;background:transparent;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;white-space:nowrap;cursor:pointer}
.device-sort-button:hover{color:var(--graphite)}.device-sort-button:focus-visible{outline:2px solid var(--interactive);outline-offset:1px}
.device-sort-button span{min-width:10px;color:var(--secondary);font-size:12px;opacity:.2;transition:color .15s ease,opacity .15s ease}.device-sort-button:hover span,.device-sort-button:focus-visible span{opacity:.6}.device-table-wrap th[aria-sort="ascending"] .device-sort-button,.device-table-wrap th[aria-sort="descending"] .device-sort-button{color:var(--graphite);font-weight:800}.device-table-wrap th[aria-sort="ascending"] .device-sort-button span,.device-table-wrap th[aria-sort="descending"] .device-sort-button span{color:var(--interactive);opacity:1}
.device-table-wrap td:nth-child(3),.device-table-wrap td:nth-child(4),.device-table-wrap td:nth-child(5),.device-table-wrap td:nth-child(6),.device-table-wrap td:nth-child(7),.device-table-wrap td:nth-child(8){white-space:nowrap}
.device-table-wrap tbody td{padding-top:6px;padding-bottom:6px}
.device-table-wrap tbody tr{cursor:pointer}
.device-table-wrap tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}
.device-table-wrap tbody tr:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:-3px}
.device-model-button{display:flex;align-items:center;gap:10px;width:100%;padding:0;border:0;background:none;color:inherit;text-align:left}
.device-model-button strong{display:block;font-weight:700}
.device-model-copy{display:flex;align-items:center;gap:8px;min-width:0}
.device-model-copy strong{min-width:0;overflow-wrap:anywhere}
.device-thumb{display:block;width:38px;height:38px;flex:0 0 38px;object-fit:contain;border-radius:8px;background:var(--surface-muted)}
.device-detail-image{display:block;width:120px;height:120px;object-fit:contain;border-radius:16px;background:var(--surface-muted);margin:0 0 16px}
.device-thumb-placeholder{position:relative;border:1px solid var(--border)}
.device-thumb-placeholder:before{content:"";position:absolute;left:10px;top:8px;width:16px;height:21px;border:2px solid var(--sky);border-radius:5px}
.device-thumb-placeholder:after{content:"";position:absolute;left:15px;top:13px;width:6px;height:2px;border-radius:2px;background:var(--sky);box-shadow:0 8px 0 var(--sky)}
.new-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--lichen) 65%,var(--border));border-radius:999px;background:#EEF2E9;color:#52624C;font-size:10px;font-weight:750;letter-spacing:.06em;text-transform:uppercase}
.admin-state{display:inline-flex;align-items:center;min-height:26px;padding:5px 9px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;line-height:1;white-space:nowrap}
.admin-state-map-yes,.admin-state-authorization-approved,.admin-state-publication-published{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}
.admin-state-map-no,.admin-state-authorization-blocked{background:#F0E9E5;border-color:#D6BDB2;color:#7A493D}
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
.modal-subtitle{color:var(--secondary);font:500 14px "Inter",sans-serif;letter-spacing:0}
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
.technical-value{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px!important}
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
.secondary-button{min-height:32px;padding:6px 10px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--interactive);font-size:12px;font-weight:700}
.secondary-button:hover{border-color:var(--interactive);background:var(--success-bg)}
.admin-action-dialog{width:min(520px,calc(100% - 32px));padding:22px;border:0;border-radius:14px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}
.admin-action-dialog::backdrop{background:rgba(34,42,43,.34)}
.admin-action-dialog form>label{display:block;margin:13px 0;color:var(--graphite);font-size:13px;font-weight:650}
.admin-action-dialog textarea{resize:vertical}
.dialog-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:800px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.diagnostic-model-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.filter-bar .results-count{width:100%;margin:2px 4px 0}.public-status{align-items:flex-start;flex-direction:column}.public-status-value{width:100%;justify-content:space-between;flex-wrap:wrap}.status-guide-grid{grid-template-columns:1fr}.campaign-fields{grid-template-columns:1fr}.campaign-field-wide{grid-column:auto}.attribution-preview{grid-template-columns:1fr}.sync-summary{white-space:normal!important}.device-detail-grid{grid-template-columns:1fr}.device-support-review form{grid-template-columns:1fr}.diagnostic-operation-heading{flex-direction:column}.diagnostic-actions{justify-content:flex-start}.diagnostic-detail-summary{grid-template-columns:1fr}.diagnostic-actions-grid{grid-template-columns:1fr}.github-review{grid-column:auto}}
@media(max-width:980px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-header-left,.admin-section-nav,.admin-nav{width:100%}.admin-section-nav{order:0;overflow:auto;justify-content:flex-start}.admin-section-nav a{white-space:nowrap}.admin-nav{justify-content:space-between;gap:10px;flex-wrap:wrap}.timezone-control{width:100%;justify-content:space-between}.timezone-control select{width:auto;flex:1}.dashboard{padding-top:28px}.diagnostic-model-metrics{gap:8px}.diagnostic-model-metrics article{padding:12px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}.campaign-card{padding:16px}.campaign-preset-row{align-items:stretch;flex-direction:column;gap:8px}.campaign-preset-row .campaign-label,.campaign-preset-row select{flex:none}.campaign-preset-row select{width:100%;height:var(--admin-control-height);margin-left:0}.generated-url-row{grid-template-columns:1fr}.copy-button{width:100%}.copy-status{min-height:18px}.device-dialog-inner,.diagnostic-detail-inner{padding:18px}.device-detail-grid dl div,.device-detail-secondary dl div{grid-template-columns:1fr;gap:2px}.device-detail-grid dd,.device-detail-secondary dd{text-align:left}.diagnostic-technical-details dl{grid-template-columns:1fr}.diagnostic-summary-action{float:none;display:block;margin-top:6px}.github-link-form{grid-template-columns:1fr}.github-link-form button{width:100%}}
@media(max-width:560px){.admin-section-nav{overflow:visible;flex-wrap:wrap}.needs-review-popover{left:0;right:auto}}
@media(max-width:800px){.admin-summary-strip{align-items:flex-start;flex-direction:column;gap:6px}.admin-summary-context,.device-summary-sync{text-align:left;white-space:normal}.device-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.device-detail-grid{grid-template-columns:1fr}.device-catalog-details dl div{grid-template-columns:1fr;gap:2px}.device-catalog-details dd{text-align:left}.device-detail-grid dd{text-align:left}.device-filter-bar .results-count{margin-left:0}.device-dialog-inner{padding:18px}}
@media(max-width:1100px){.device-table-wrap{overflow-x:auto;overflow-y:visible}.device-table-wrap table{min-width:1050px}.device-table-wrap thead th{top:0}}
@media(max-height:760px){.device-dialog-inner{max-height:calc(100vh - 32px);overflow:auto}.device-dialog-header{position:sticky;top:-1px;z-index:2;padding-bottom:10px;background:var(--surface)}}
"""


def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _layout(title: str, content: str) -> bytes:
    nonce = secrets.token_urlsafe(18)
    content = content.replace("<script>", f"<script nonce=\"{nonce}\">")
    timezone_script = _admin_timezone_script()
    content = f"{content}<script>{timezone_script}</script>"
    content = content.replace("<script>", f"<script nonce=\"{nonce}\">")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>{ADMIN_STYLES}</style></head><body>{content}</body></html>""".encode("utf-8")


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

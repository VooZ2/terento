from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from .campaign_links import CAMPAIGN_SUGGESTIONS, MEDIUM_OPTIONS, SOURCE_OPTIONS
from .asset_attribution import generic_fallback_image
from .compatibility_status import (
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
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        return f"{parsed.day:02d} {months[parsed.month - 1]} {parsed.year}, {parsed.hour:02d}:{parsed.minute:02d} UTC"
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
        for key in ("last_success", "last_failure")
    ]
    parsed = [value for value in values if value is not None]
    return max(parsed) if parsed else None


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
    size_match = re.search(r"\b(\d{2,3})\s*mm\b", raw, flags=re.IGNORECASE)
    display_tokens = [token for token in ("AMOLED", "Solar", "MicroLED") if re.search(rf"\b{token}\b", raw, flags=re.IGNORECASE)]
    parts: list[str] = []
    if size_match:
        parts.append(f"{size_match.group(1)} mm")
    if display_tokens:
        parts.extend(display_tokens)
    if parts:
        return ", ".join(dict.fromkeys(parts))
    return raw


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


def _error_cell(row: dict[str, Any]) -> str:
    errors = row.get("error_categories") or {}
    if not isinstance(errors, dict) or not errors:
        return "<span class='muted-value'>—</span>"
    count = sum(int(value) for value in errors.values() if str(value).isdigit())
    detail = ", ".join(f"{html.escape(str(key))}: {html.escape(str(value))}" for key, value in sorted(errors.items()))
    target = _diagnostics_id(str(row.get("compatibility_identity") or row.get("model") or "unknown"))
    return f"<a class='error-count' href='#{target}' title='{detail}' aria-label='View {count} errors'>{count}</a>"


def _diagnostics_id(identity: str) -> str:
    return "diagnostics-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _admin_brand() -> str:
    return """<a class="admin-brand" href="https://terento.app/" aria-label="Terento home">
      <img src="https://terento.app/assets/logo-sky.svg" alt="" width="25" height="29">
      <span>Terento</span><span class="admin-badge">Admin</span>
    </a>"""


def _admin_header(user: dict[str, Any], csrf_token: str, *, active: str = "evidence") -> str:
    username = html.escape(str(user.get("username") or ""))
    evidence_class = " class='active'" if active == "evidence" else ""
    campaign_class = " class='active'" if active == "campaigns" else ""
    devices_class = " class='active'" if active == "devices" else ""
    return f"""<header class="admin-topbar"><div class="admin-topbar-inner">{_admin_brand()}
      <nav class="admin-section-nav" aria-label="Admin sections"><a{evidence_class} href="/admin">Installation evidence</a><a{devices_class} href="/admin/devices">Garmin devices</a><a{campaign_class} href="/admin/campaign-links">Campaign links</a></nav>
      <nav class="admin-nav" aria-label="Admin navigation"><label class="timezone-control"><span>Time zone</span><select id="admin-timezone" aria-label="Time zone"><option value="browser">Automatic (browser)</option><option value="UTC">UTC</option><option value="Europe/Vilnius">Europe/Vilnius</option><option value="Europe/London">Europe/London</option><option value="Europe/Berlin">Europe/Berlin</option><option value="America/New_York">America/New_York</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="Asia/Tokyo">Asia/Tokyo</option></select></label><a href="/admin/account">Account</a><span class="admin-user">{username}</span>
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
          <p class="lede">Private installation evidence for Terento.</p>
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
    failures = sum(int(row.get("failed_install_count") or 0) for row in rows)
    latest = _latest_data_timestamp(rows)
    published = sum(
        1 for row in rows
        if row.get("public_statistics_enabled") is True
        and str(row.get("review_status") or "").upper() == "APPROVED"
        and str(row.get("calculated_status") or "").upper() in {"TESTING", "TESTED", "SUPPORTED", "VERIFIED"}
    ) if public_stats_enabled else 0
    status_values = ["TESTING", "TESTED", "SUPPORTED", "VERIFIED"]
    status_options = "".join(
        f"<option value='{status.lower()}'>{status.title()}</option>"
        for status in status_values
    )
    cards = "".join(
        f"<article class='metric'><span>{label}</span><strong>{value}</strong></article>"
        for label, value in (("Models", len(rows)), ("Write attempts", attempts), ("Successful operations", successes), ("Failed operations", failures))
    )
    table_rows = "".join(_statistics_row(row) for row in rows)
    has_resolved_operations = bool(resolved_operations)
    empty = (
        "<p class='empty'>No current installation evidence reports yet. Resolved historical reports are shown below.</p>"
        if not rows and has_resolved_operations
        else ("<p class='empty'>No installation evidence reports yet.</p>" if not rows else "")
    )
    latest_copy = f"Updated {_timestamp_markup(latest)}" if latest else (
        "No current reports received yet" if has_resolved_operations else "No reports received yet"
    )
    diagnostic_details = _diagnostic_details(rows, operations or [])
    resolved_diagnostic_details = _resolved_diagnostic_details(resolved_operations or [])
    content = f"""
      {_admin_header(user, csrf_token)}
      <main class="dashboard" id="main-content">
        <div class="heading-row"><div><p class="eyebrow">Admin</p><h1>Installation evidence</h1><p class="lede">Compatibility reports received from Terento installations.</p></div><p class="updated-at">{latest_copy}</p></div>
        <section class="metrics" aria-label="Evidence summary">{cards}</section>{empty}
        <section class="evidence-section" aria-labelledby="evidence-title">
          <div class="section-heading"><div><p class="section-kicker">Evidence</p><h2 id="evidence-title">Installation reports</h2></div><p class="table-help">Times follow the selected time zone</p></div>
          <form class="filter-bar" id="evidence-filters" role="search">
            <label class="filter-search"> <span class="sr-only">Search models</span><input id="evidence-search" type="search" placeholder="Search models" autocomplete="off"></label>
            <label><span class="sr-only">Filter by status</span><select id="evidence-status"><option value="all">All statuses</option>{status_options}</select></label>
            <label><span class="sr-only">Sort reports</span><select id="evidence-sort"><option value="reports">Most reports</option><option value="latest">Latest activity</option></select></label>
          </form>
          <p class="results-count" id="results-count" aria-live="polite">{len(rows)} {"model" if len(rows) == 1 else "models"}</p>
          <div class="table-wrap"><table><caption class="sr-only">Installation evidence by exact device identity</caption><thead><tr><th scope="col">Model</th><th scope="col">Variant</th><th scope="col">Firmware</th><th scope="col">Write attempts</th><th scope="col">Successful operations</th><th scope="col">Failed operations</th><th scope="col">Success rate</th><th scope="col">Status</th><th scope="col">Last success</th><th scope="col">Errors</th></tr></thead><tbody id="evidence-rows">{table_rows}</tbody></table></div>
          <p class="table-help">Compatibility rates count distinct active write-started operations. Resolved historical failures are excluded from current compatibility counts or rates and shown separately below.</p>
          {diagnostic_details}
          {resolved_diagnostic_details}
        </section>
        <section class="status-guide" aria-labelledby="status-guide-title"><div class="section-heading"><div><p class="section-kicker">Canonical rules</p><h2 id="status-guide-title">Compatibility statuses</h2></div><p class="table-help">Exact model and variant; successful shared installations only</p></div><div class="status-guide-grid">{''.join(f"<div class='status-guide-row'>{_status_badge(status)}<span>{html.escape(STATUS_PUBLIC_COPY[CompatibilityStatus(status)])}</span></div>" for status in status_values)}</div></section>
        <section class="public-status" aria-labelledby="public-status-title"><div><p class="section-kicker">Publication</p><h2 id="public-status-title">Public compatibility</h2></div><div class="public-status-value"><span class="status-badge status-{('enabled' if public_stats_enabled else 'disabled')}">{'Enabled' if public_stats_enabled else 'Disabled'}</span><span>{published} {'model' if published == 1 else 'models'} published</span></div></section>
      </main>
      <script>{_dashboard_script()}</script>
    """
    return _layout("Installation evidence", content)


def _diagnostic_details(rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    identities = {
        str(row.get("compatibility_identity") or row.get("model") or "Unknown")
        for row in rows
    }
    return _render_diagnostic_details(
        events,
        identities=identities,
        heading="Operation diagnostics",
        summary_prefix="",
    )


def _resolved_diagnostic_details(events: list[dict[str, Any]]) -> str:
    return _render_diagnostic_details(
        events,
        identities=None,
        heading="Resolved / historical diagnostics",
        summary_prefix="Resolved / historical · ",
        note="These records are retained for diagnosis but do not affect current compatibility counts or rates.",
    )


def _render_diagnostic_details(
    events: list[dict[str, Any]],
    *,
    identities: set[str] | None,
    heading: str,
    summary_prefix: str,
    note: str | None = None,
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
        if summary_prefix:
            details_id = "resolved-" + details_id
        for operation_key, results in operations.items():
            first = results[0]
            map_rows = "".join(
                "<tr>" + "".join(f"<td>{html.escape(str(value if value not in (None, '') else '—'))}</td>" for value in (
                    result.get("region"), result.get("raw_mtp_model"), result.get("identity_resolution_code"),
                    result.get("phase_outcome"), result.get("failure_stage"),
                    result.get("failure_code"), result.get("native_failure_code"),
                    str(bool(result.get("write_started"))).lower(),
                    str(bool(result.get("remote_object_created"))).lower(),
                    ("not attempted" if not result.get("cleanup_attempted") else
                     ("succeeded" if result.get("cleanup_succeeded") else "failed")),
                    result.get("transfer_progress_bucket"),
                )) + "</tr>"
                for result in sorted(results, key=lambda item: int(item.get("map_result_index") or 0))
            )
            release = first.get("release_label") or first.get("terento_version") or "legacy"
            build = first.get("app_build") or "legacy"
            resolution = ""
            if str(first.get("diagnostic_status") or "").upper() == "RESOLVED":
                resolution = " · " + html.escape(
                    str(first.get("resolution_note") or "Marked resolved")
                )
            operation_cards.append(f"""
              <article class='diagnostic-operation'>
                <h4>{html.escape(str(operation_key))}</h4>
                <p>{_timestamp_markup(first.get('occurred_at'))} · {html.escape(str(release))} (build {html.escape(str(build))}) · write started: {str(bool(first.get('write_started'))).lower()}{resolution}</p>
                <div class='table-wrap'><table><thead><tr><th>Region</th><th>Raw MTP model</th><th>Local identity</th><th>Result</th><th>Stage</th><th>Code</th><th>Native code</th><th>Write</th><th>Object created</th><th>Cleanup</th><th>Progress</th></tr></thead><tbody>{map_rows}</tbody></table></div>
              </article>""")
        sections.append(f"""
          <details class='diagnostic-details' id='{details_id}'>
            <summary>{html.escape(summary_prefix + identity)} · {len(operations)} operation{'s' if len(operations) != 1 else ''}</summary>
            {''.join(operation_cards)}
          </details>""")
    if not sections:
        return ""
    note_markup = f"<p class='table-help'>{html.escape(note)}</p>" if note else ""
    section_class = "diagnostics-list resolved-diagnostics" if summary_prefix else "diagnostics-list"
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


def _admin_support_status(value: Any) -> tuple[str, str]:
    status = str(value or "NOT_EVALUATED").upper()
    labels = {
        "SUPPORTED": ("Supported", "supported"),
        "UNSUPPORTED": ("Unsupported", "unsupported"),
        "NOT_EVALUATED": ("Not evaluated", "not-evaluated"),
    }
    return labels.get(status, ("Not evaluated", "not-evaluated"))


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
            recognized_map_capable_evidence=map_capable is not False,
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
            "variant": row.get("variant"),
            "caseSizeMm": row.get("case_size_mm"),
            "displayType": row.get("display_type"),
            "partNumber": row.get("part_number"),
            "productURL": row.get("product_url"),
            "active": bool(row.get("active", True)),
            "mapCapable": map_capable,
            "supportStatus": str(row.get("support_status") or "NOT_EVALUATED").upper(),
            "evidenceStatus": evidence_status.value if evidence_status else None,
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
            "supported": sum(device["supportStatus"] == "SUPPORTED" for device in devices),
            "tested": sum(device["installationStats"]["successful"] > 0 for device in devices),
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
    support_label, support_kind = _admin_support_status(device.get("supportStatus"))
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
    last_tested = _timestamp_markup(stats.get("lastSuccessfulAt")) if stats.get("lastSuccessfulAt") else "—"
    return f"""<tr data-device-index='{index}' data-search='{html.escape(search, quote=True)}' data-model='{html.escape(model.lower(), quote=True)}' data-updated='{html.escape(str(catalog.get('updatedAt') or ''), quote=True)}' data-installs='{stats['attempts']}' data-tested='{str(stats['successful'] > 0).lower()}' tabindex='0'>
      <td><button class='device-model-button' type='button' data-device-index='{index}'>{image}<span class='device-model-copy'><strong>{html.escape(model)}</strong>{new_badge}</span></button></td>
      <td>{html.escape(variant)}</td>
      <td>{_admin_status_badge(map_label, f'map-{map_kind}')}</td>
      <td>{_admin_status_badge(support_label, f'support-{support_kind}')}</td>
      <td>{_status_badge(evidence_status) if evidence_status else _admin_status_badge('Unavailable', 'unavailable')}</td>
      <td class='numeric'>{stats['attempts']}</td>
      <td class='numeric'>{stats['successful']}</td>
      <td>{last_tested}</td>
    </tr>"""


def devices_page(
    rows: list[dict[str, Any]], sync: dict[str, Any] | None,
    user: dict[str, Any], csrf_token: str,
) -> bytes:
    payload = _admin_device_payload(rows, sync)
    summary = payload["summary"]
    rate = _format_rate(summary["successRate"])
    sync_data = payload["sync"]
    completed = _timestamp_markup(sync_data["completedAt"]) if sync_data["completedAt"] else "No successful sync recorded"
    sync_line = (
        f"Last sync: {sync_data['recordsAdded']} new · {sync_data['recordsUpdated']} updated"
        if sync_data["id"] is not None and sync_data["recordsAdded"] is not None
        else ("Last sync: counts unavailable for this historical run" if sync_data["id"] is not None else "Last sync: —")
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
        <div class="heading-row"><div><p class="eyebrow">Admin · Garmin</p><h1>Garmin devices</h1><p class="lede">Catalogue health, map capability, Support decision, and real Terento installation evidence.</p></div><p class="updated-at">Catalogue completed {completed}</p></div>
        <section class="metrics device-metrics" aria-label="Garmin device catalogue summary">
          <article class='metric'><span>Models</span><strong>{summary['models']}</strong></article>
          <article class='metric'><span>Map-capable</span><strong>{summary['mapCapable']}</strong></article>
          <article class='metric'><span>Supported</span><strong>{summary['supported']}</strong></article>
          <article class='metric'><span>Tested</span><strong>{summary['tested']}</strong></article>
          <article class='metric'><span>Install attempts</span><strong>{summary['installAttempts']}</strong></article>
          <article class='metric'><span>Successful installs</span><strong>{summary['successfulInstalls']}</strong></article>
          <article class='metric'><span>Success rate</span><strong>{html.escape(rate)}</strong></article>
          <article class='metric'><span>New this sync</span><strong>{summary['newThisSync'] if summary['newThisSync'] is not None else '—'}</strong></article>
        </section>
        <section class="catalog-sync" aria-labelledby="catalog-sync-title"><div><p class="section-kicker">Catalogue</p><h2 id="catalog-sync-title">Garmin device catalog</h2><p>Last updated {completed}</p></div><p class="sync-summary">{html.escape(sync_line)}</p></section>
        <section class="evidence-section" aria-labelledby="device-list-title">
          <div class="section-heading"><div><p class="section-kicker">Inventory</p><h2 id="device-list-title">Known Garmin models</h2></div><p class="table-help">Times follow the selected time zone</p></div>
          <form class="filter-bar device-filter-bar" id="device-filters" role="search">
            <label class="filter-search"><span class="sr-only">Search Garmin devices</span><input id="device-search" type="search" placeholder="Search model, family, variant, case size or part number" autocomplete="off"></label>
            <label><span class="sr-only">Filter by family</span><select id="device-family"><option value="all">All families</option>{family_options}</select></label>
            <label><span class="sr-only">Filter by map capability</span><select id="device-map"><option value="all">All map capability</option><option value="yes">Map-capable: Yes</option><option value="no">Map-capable: No</option><option value="unknown">Map-capable: Unknown</option></select></label>
            <label><span class="sr-only">Filter by Support decision</span><select id="device-support"><option value="all">All Support decisions</option><option value="SUPPORTED">Supported</option><option value="UNSUPPORTED">Unsupported</option><option value="NOT_EVALUATED">Not evaluated</option></select></label>
            <label><span class="sr-only">Filter by testing</span><select id="device-tested"><option value="all">All tested states</option><option value="yes">Tested: Yes</option><option value="no">Tested: No</option></select></label>
            <label><span class="sr-only">Sort Garmin devices</span><select id="device-sort"><option value="model">Model name</option><option value="newest">Newest in database</option><option value="updated">Recently updated</option><option value="installs">Most installs</option><option value="tested">Last tested</option></select></label>
          </form>
          <p class="results-count" id="device-results-count" aria-live="polite">{len(payload['devices'])} {'model' if len(payload['devices']) == 1 else 'models'}</p>
          {empty}
          <div class="table-wrap device-table-wrap"><table><caption class="sr-only">Garmin device catalogue and Terento installation evidence</caption><thead><tr><th scope="col">Model</th><th scope="col">Variant</th><th scope="col">Map-capable</th><th scope="col">Support decision</th><th scope="col">Evidence status</th><th scope="col">Installs</th><th scope="col">Success</th><th scope="col">Last tested</th></tr></thead><tbody id="device-rows">{rows_html}</tbody></table></div>
          <div class="device-pagination" id="device-pagination" hidden><button type="button" id="device-previous">Previous</button><span id="device-page-status"></span><button type="button" id="device-next">Next</button></div>
        </section>
      </main>
      <dialog class="device-dialog" id="device-dialog" aria-labelledby="device-dialog-title"><div class="device-dialog-inner"><div class="device-dialog-header"><div><p class="section-kicker">Garmin device record</p><h2 id="device-dialog-title">Device details</h2></div><button class="dialog-close" type="button" id="device-dialog-close" aria-label="Close device details">×</button></div><div id="device-dialog-body"></div></div></dialog>
      <script>const terentoAdminDevices = {payload_json};{_devices_script()}</script>
    """
    return _layout("Garmin devices", content)


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
        <div class="heading-row"><div><p class="eyebrow">Admin</p><h1>Campaign links</h1><p class="lede">Create consistent tracking links for Terento campaigns.</p></div></div>
        <section class="campaign-card" aria-labelledby="campaign-builder-title">
          <div class="section-heading"><div><p class="section-kicker">Attribution</p><h2 id="campaign-builder-title">Campaign link builder</h2></div><p class="table-help">Links are generated locally in this browser.</p></div>
          <div class="campaign-preset-row">
            <label class="campaign-label" for="campaign-preset">Preset { _campaign_info("campaign-preset", "Preset", "<p>Choose a common campaign setup, then edit any field before copying.</p><p><strong>Recommendation:</strong> use the Reddit preset for a community post.</p>") }</label>
            <select id="campaign-preset"><option value="reddit-community">Reddit community post</option><option value="" selected>Custom</option></select>
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
                <label class="campaign-label" for="term">Term <span class="optional-label">Optional</span> { _campaign_info("term", "Term", "<p>Optional keyword or audience label for paid or partner campaigns.</p><p><strong>Recommendation:</strong> leave blank unless you need this extra breakdown.</p><p><strong>Example:</strong> <code>47mm</code></p>") }</label>
                <input id="term" type="text" placeholder="47mm" autocomplete="off">
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


def _statistics_row(row: dict[str, Any]) -> str:
    model, variant, identity = _identity_parts(row)
    status = str(row.get("calculated_status") or "").upper()
    search_text = " ".join((model, variant, str(row.get("family") or ""), identity)).strip()
    activity = max((_timestamp_iso(row.get(key)) for key in ("last_success", "last_failure")), default="")
    cells = (
        html.escape(model), html.escape(variant), html.escape(str(row.get("firmware_versions") or "—")),
        html.escape(str(row.get("attempted_install_count", 0))), html.escape(str(row.get("successful_install_count", 0))),
        html.escape(str(row.get("failed_install_count", 0))), html.escape(_format_rate(row.get("success_rate"))),
        _status_badge(status), _timestamp_markup(row.get("last_success")), _error_cell(row),
    )
    return (
        f"<tr data-search='{html.escape(search_text)}' data-status='{html.escape(status.lower())}' data-activity='{html.escape(activity)}' data-reports='{int(row.get('attempted_install_count') or 0)}'>"
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
      const tested = document.querySelector('#device-tested');
      const sort = document.querySelector('#device-sort');
      const count = document.querySelector('#device-results-count');
      const pagination = document.querySelector('#device-pagination');
      const previous = document.querySelector('#device-previous');
      const next = document.querySelector('#device-next');
      const pageStatus = document.querySelector('#device-page-status');
      const dialog = document.querySelector('#device-dialog');
      const dialogTitle = document.querySelector('#device-dialog-title');
      const dialogBody = document.querySelector('#device-dialog-body');
      const close = document.querySelector('#device-dialog-close');
      if (!body || !form || !search || !family || !map || !support || !tested || !sort || !count || !dialog) return;

      const pageSize = 50;
      let page = 0;
      const escapeHtml = (value) => String(value ?? '—')
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
      const display = (value) => value === null || value === undefined || value === '' ? '—' : value;
      const utcDate = (value) => value ? new Intl.DateTimeFormat('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short'
      }).format(new Date(value)) : '—';
      const date = (value) => value ? `<time class="admin-timestamp" data-admin-timestamp="${escapeHtml(value)}">${escapeHtml(window.TerentoAdminTime ? window.TerentoAdminTime.format(value) : utcDate(value))}</time>` : '—';
      const mapValue = (device) => device.mapCapable === true ? 'yes' : device.mapCapable === false ? 'no' : 'unknown';
      const supportLabel = (value) => ({SUPPORTED: 'Supported', UNSUPPORTED: 'Unsupported', NOT_EVALUATED: 'Not evaluated'})[value] || 'Not evaluated';
      const evidenceLabel = (value) => ({TESTING: 'Testing', TESTED: 'Tested', SUPPORTED: 'Supported', VERIFIED: 'Verified'})[value] || 'Unavailable';
      const deviceSearch = (device) => [device.model, device.canonicalModel, device.family, device.familyName, device.variant, device.caseSizeMm, device.partNumber, device.displayType].filter(Boolean).join(' ').toLocaleLowerCase();
      const matching = () => {
        const query = search.value.trim().toLocaleLowerCase();
        return devices.filter((device) => {
          const matchesSearch = !query || deviceSearch(device).includes(query);
          const matchesFamily = family.value === 'all' || family.value === (device.familyName || device.family);
          const matchesMap = map.value === 'all' || mapValue(device) === map.value;
          const matchesSupport = support.value === 'all' || (device.supportStatus || 'NOT_EVALUATED') === support.value;
          const matchesTested = tested.value === 'all' || (device.installationStats.successful > 0 ? 'yes' : 'no') === tested.value;
          return matchesSearch && matchesFamily && matchesMap && matchesSupport && matchesTested;
        }).sort((a, b) => {
          if (sort.value === 'newest') return String(b.catalog.firstSeenAt || '').localeCompare(String(a.catalog.firstSeenAt || ''));
          if (sort.value === 'updated') return String(b.catalog.updatedAt || '').localeCompare(String(a.catalog.updatedAt || ''));
          if (sort.value === 'installs') return (b.installationStats.attempts || 0) - (a.installationStats.attempts || 0);
          if (sort.value === 'tested') return String(b.installationStats.lastSuccessfulAt || '').localeCompare(String(a.installationStats.lastSuccessfulAt || ''));
          return String(a.model || '').localeCompare(String(b.model || ''), undefined, {sensitivity: 'base', numeric: true})
            || String(a.variant || '').localeCompare(String(b.variant || ''), undefined, {sensitivity: 'base', numeric: true});
        });
      };
      const openDevice = (device) => {
        if (!device) return;
        dialogTitle.textContent = display(device.model);
        const stats = device.installationStats;
        const catalog = device.catalog;
        const mapLabel = device.mapCapable === true ? 'Yes' : device.mapCapable === false ? 'No' : 'Unknown';
        const image = device.image || {};
        const assetLabel = image.origin === 'controlled' ? 'Controlled Terento asset' : image.origin === 'garmin-source' ? 'Garmin source image (model match)' : image.origin === 'fallback' ? 'Generic Terento fallback' : 'Missing';
        const imageMarkup = image.url ? `<img class="device-detail-image" src="${escapeHtml(image.url)}" alt="">` : '';
        const usb = (device.usbIdentities || []).map((identity) => `VID ${identity.vendorId} · PID ${identity.productId}`).join(', ') || '—';
        dialogBody.innerHTML = `
          ${imageMarkup}
          <div class="device-detail-grid">
            <section><p class="detail-kicker">Identity</p><dl>
              <div><dt>Model</dt><dd>${escapeHtml(device.model)}</dd></div>
              <div><dt>Canonical model</dt><dd>${escapeHtml(device.canonicalModel)}</dd></div>
              <div><dt>Family</dt><dd>${escapeHtml(device.familyName || device.family)}</dd></div>
              <div><dt>Variant</dt><dd>${escapeHtml(device.variant)}</dd></div>
              <div><dt>Case size</dt><dd>${escapeHtml(device.caseSizeMm ? `${device.caseSizeMm} mm` : null)}</dd></div>
              <div><dt>Display</dt><dd>${escapeHtml(device.displayType)}</dd></div>
              <div><dt>Part number</dt><dd>${escapeHtml(device.partNumber)}</dd></div>
              <div><dt>Record ID</dt><dd class="technical-value">${escapeHtml(device.id)}</dd></div>
            </dl></section>
            <section><p class="detail-kicker">Compatibility</p><dl>
              <div><dt>Map-capable</dt><dd>${escapeHtml(mapLabel)}</dd></div>
              <div><dt>Support decision</dt><dd>${escapeHtml(supportLabel(device.supportStatus))}</dd></div>
              <div><dt>Evidence status</dt><dd>${escapeHtml(evidenceLabel(device.evidenceStatus))}</dd></div>
              <div><dt>Active</dt><dd>${device.active ? 'Yes' : 'No'}</dd></div>
              <div><dt>USB identities</dt><dd class="technical-value">${escapeHtml(usb)}</dd></div>
            </dl></section>
            <section><p class="detail-kicker">Installation evidence</p><dl>
              <div><dt>Attempts</dt><dd>${stats.attempts}</dd></div>
              <div><dt>Successful</dt><dd>${stats.successful}</dd></div>
              <div><dt>Failed</dt><dd>${stats.failed}</dd></div>
              <div><dt>Success rate</dt><dd>${stats.successRate === null ? '—' : `${stats.successRate}%`}</dd></div>
              <div><dt>First successful install</dt><dd>${date(stats.firstSuccessfulAt)}</dd></div>
              <div><dt>Last tested</dt><dd>${date(stats.lastSuccessfulAt)}</dd></div>
              <div><dt>Last evidence</dt><dd>${date(stats.lastEvidenceAt)}</dd></div>
            </dl></section>
            <section><p class="detail-kicker">Catalogue</p><dl>
              <div><dt>First seen in Terento</dt><dd>${date(catalog.firstSeenAt)}</dd></div>
              <div><dt>Record created</dt><dd>${date(catalog.createdAt)}</dd></div>
              <div><dt>Record updated</dt><dd>${date(catalog.updatedAt)}</dd></div>
              <div><dt>Last seen</dt><dd>${date(catalog.lastSeenAt)}</dd></div>
              <div><dt>New in latest sync</dt><dd>${catalog.newInLatestSync ? 'Yes' : 'No'}</dd></div>
              <div><dt>Image</dt><dd>${escapeHtml(assetLabel)}</dd></div>
              <div><dt>Match source</dt><dd>${escapeHtml(image.origin === 'controlled' ? 'Approved catalog asset' : image.origin === 'garmin-source' ? 'Official Garmin product media URL for this exact catalog row' : image.origin === 'fallback' ? 'Neutral Terento fallback; no model-specific image available' : 'No image URL stored for this row')}</dd></div>
            </dl></section>
          </div>
          <section class="device-support-review" aria-labelledby="device-support-review-title">
            <p class="detail-kicker" id="device-support-review-title">Operator review</p>
            <p class="table-help">This changes the Support decision only. It does not change Evidence status or installation counts.</p>
            <form method="post" action="/admin/devices/support">
              <input type="hidden" name="csrf_token" value="${escapeHtml(terentoAdminDevices.csrfToken)}">
              <input type="hidden" name="device_id" value="${escapeHtml(device.id)}">
              <label for="support-decision-${escapeHtml(device.id)}">Support decision</label>
              <select id="support-decision-${escapeHtml(device.id)}" name="support_status">
                <option value="SUPPORTED"${device.supportStatus === 'SUPPORTED' ? ' selected' : ''}>Supported</option>
                <option value="UNSUPPORTED"${device.supportStatus === 'UNSUPPORTED' ? ' selected' : ''}>Unsupported</option>
                <option value="NOT_EVALUATED"${device.supportStatus === 'NOT_EVALUATED' ? ' selected' : ''}>Not evaluated</option>
              </select>
              <button type="submit">Save support decision</button>
            </form>
          </section>
          ${device.productURL ? `<p class="device-product-link"><a href="${escapeHtml(device.productURL)}" target="_blank" rel="noreferrer">Open Garmin product page</a></p>` : ''}
        `;
        if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
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
      [search, family, map, support, tested, sort].forEach((control) => control.addEventListener(control === search ? 'input' : 'change', reset));
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
        if (!row) return;
        event.preventDefault();
        openDevice(devices[Number(row.dataset.deviceIndex)]);
      });
      body.querySelectorAll('button[data-device-index]').forEach((button) => button.addEventListener('click', () => openDevice(devices[Number(button.dataset.deviceIndex)])));
      close.addEventListener('click', () => dialog.close());
      dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
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
      const refresh = () => {
        updateCustomVisibility();
        const result = buildUrl();
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
        visible.sort((a, b) => sort.value === 'latest'
          ? (b.dataset.activity || '').localeCompare(a.dataset.activity || '')
          : Number(b.dataset.reports || 0) - Number(a.dataset.reports || 0));
        visible.forEach((row) => body.appendChild(row));
        const label = visible.length === 1 ? 'model' : 'models';
        count.textContent = visible.length === rows.length ? `${visible.length} ${label}` : `${visible.length} of ${rows.length} ${label}`;
      };
      form.addEventListener('submit', (event) => event.preventDefault());
      [search, status, sort].forEach((control) => control.addEventListener('input', refresh));
      document.querySelectorAll('a.error-count[href^="#diagnostics-"]').forEach((link) => {
        link.addEventListener('click', () => {
          const target = document.querySelector(link.getAttribute('href'));
          if (target instanceof HTMLDetailsElement) target.open = true;
        });
      });
      refresh();
    })();"""


def _admin_timezone_script() -> str:
    return r"""(() => {
      const select = document.querySelector('#admin-timezone');
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
          return new Intl.DateTimeFormat('en-GB', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit', timeZone: activeTimeZone(), timeZoneName: 'short'
          }).format(date);
        } catch (_) {
          return date.toISOString();
        }
      };
      const render = () => {
        const zone = activeTimeZone();
        document.querySelectorAll('[data-admin-timestamp]').forEach((element) => {
          element.textContent = format(element.dataset.adminTimestamp);
          element.title = `${element.textContent} · ${zone}`;
        });
        select.title = zone;
        select.setAttribute('aria-label', `Time zone: ${select.value === 'browser' ? `Automatic (${browserTimeZone})` : select.value}`);
      };
      select.replaceChildren(...timeZones.map((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value === 'browser' ? `Automatic (browser) · ${browserTimeZone}` : value;
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
:root{--off-white:#F7F3EC;--graphite:#222A2B;--sky:#7898A8;--lichen:#9AA58B;--stone:#B39A78;--interactive:#577787;--interactive-hover:#4F6E7E;--secondary:#6D706F;--surface:#FFFFFF;--surface-muted:#F1EEE7;--border:#D7DDDA;--danger:#9A493D;--success-bg:#E8F0E5;--max-width:1440px}
*{box-sizing:border-box}
html{min-width:0}
body{margin:0;min-width:0;background:var(--off-white);color:var(--graphite);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:3px}
button,input,select{font:inherit}
button{cursor:pointer}
.admin-topbar{border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);background:color-mix(in srgb,var(--off-white) 92%,white)}
.admin-topbar-inner{width:min(calc(100% - 48px),var(--max-width));min-height:68px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:24px}
.admin-brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--graphite);font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;font-size:20px;font-weight:700;letter-spacing:-.02em}
.admin-brand img{width:25px;height:29px;object-fit:contain}
.admin-badge{display:inline-flex;align-items:center;min-height:22px;padding:3px 8px;border:1px solid color-mix(in srgb,var(--sky) 48%,var(--border));border-radius:999px;color:var(--interactive);font-family:"Inter",sans-serif;font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.admin-section-nav{display:flex;align-items:center;gap:4px;margin-left:auto;color:var(--secondary);font-size:13px;font-weight:650}
.admin-section-nav a{padding:7px 10px;border-radius:8px;text-decoration:none}
.admin-section-nav a:hover,.admin-section-nav a.active{background:var(--surface);color:var(--interactive)}
.admin-nav{display:flex;align-items:center;gap:18px;color:var(--secondary);font-size:13px}
.admin-nav a{text-decoration:none}
.admin-nav a:hover{color:var(--interactive)}
.admin-user{color:var(--graphite);font-weight:650}
.timezone-control{display:flex;align-items:center;gap:7px;color:var(--secondary);font-size:11px;font-weight:650;white-space:nowrap}
.timezone-control select{max-width:205px;min-height:32px;padding:5px 8px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite);font-size:11px}
.admin-nav form{margin:0}
.link-button{padding:0;border:0;background:none;color:var(--interactive);font-weight:650;text-decoration:underline;text-underline-offset:3px}
.dashboard{width:min(calc(100% - 48px),var(--max-width));margin:0 auto;padding:40px 0 64px}
.heading-row{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;margin-bottom:28px}
.eyebrow,.section-kicker{margin:0 0 8px;color:var(--interactive);font-size:12px;font-weight:750;letter-spacing:.14em;text-transform:uppercase}
h1,h2{margin:0;font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;letter-spacing:-.035em}
h1{font-size:clamp(34px,4.2vw,52px);line-height:1.04}
h2{font-size:22px;line-height:1.15}
.lede{max-width:680px;margin:12px 0 0;color:var(--secondary);font-size:16px}
.updated-at{margin:0 0 5px;color:var(--secondary);font-size:13px;white-space:nowrap}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:34px}
.metric{min-height:104px;padding:18px 20px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.metric span{display:block;color:var(--secondary);font-size:13px;font-weight:600}
.metric strong{display:block;margin-top:5px;font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;font-size:30px;line-height:1.1;letter-spacing:-.025em}
.evidence-section{margin-top:2px}
.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:14px}
.section-heading .section-kicker{margin-bottom:5px}
.table-help,.results-count{margin:0;color:var(--secondary);font-size:12px}
.filter-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 9px;padding:8px;background:var(--surface-muted);border:1px solid var(--border);border-radius:12px}
.filter-bar label{margin:0}
.filter-bar input,.filter-bar select{min-height:38px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite);padding:8px 11px;font-size:13px}
.filter-bar input{width:min(360px,42vw)}
.filter-bar select{min-width:150px}
.filter-bar input::placeholder{color:var(--secondary)}
.results-count{margin:0 0 8px 3px}
.table-wrap{overflow:auto;background:var(--surface);border:1px solid var(--border);border-radius:14px}
table{border-collapse:collapse;width:100%;min-width:1060px}
th,td{padding:12px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);text-align:left;white-space:nowrap;vertical-align:middle}
th{color:var(--secondary);font-size:11px;font-weight:750;letter-spacing:.07em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:0}
tbody tr[hidden]{display:none}
td:nth-child(1){font-weight:650}
td:nth-child(4),td:nth-child(5),td:nth-child(6),td:nth-child(7){font-variant-numeric:tabular-nums}
.muted-value{color:var(--secondary)}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:700}
.diagnostics-list{margin-top:24px}.diagnostics-list h3{margin-bottom:12px}.diagnostic-details{margin:8px 0;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;scroll-margin-top:20px}.diagnostic-details summary{cursor:pointer;font-weight:700}.diagnostic-operation{margin-top:16px}.diagnostic-operation h4{margin:0;font:650 13px ui-monospace,SFMono-Regular,Menlo,monospace}.diagnostic-operation p{margin:5px 0 9px;color:var(--secondary);font-size:12px}.diagnostic-operation table{min-width:920px}.resolved-diagnostics{padding-top:18px;border-top:1px solid var(--border)}.resolved-diagnostics .diagnostic-details{background:var(--background)}
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
.auth-card input{display:block;width:100%;margin-top:7px;padding:11px 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite)}
.auth-card button:not(.link-button){margin-top:8px;padding:11px 16px;border:0;border-radius:8px;background:var(--interactive);color:white;font-weight:700}
.auth-card button:not(.link-button):hover{background:var(--interactive-hover)}
.error,.success{margin:16px 0;padding:11px 13px;border-radius:8px;font-size:13px}
.error{background:#FBEAE6;color:#81372D}
.success{background:var(--success-bg);color:#365B3B}
.account{margin-top:48px}
.campaign-card{padding:24px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.campaign-card>.section-heading{margin-bottom:22px}
.campaign-preset-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,360px);align-items:center;gap:16px;margin-bottom:20px;padding:13px 14px;background:var(--surface-muted);border:1px solid var(--border);border-radius:10px}
.campaign-preset-row select,.campaign-field input,.campaign-field select{width:100%;min-height:42px;padding:9px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--graphite)}
.campaign-form{margin:0}
.campaign-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 16px}
.campaign-field{min-width:0}
.campaign-field-wide{grid-column:1/-1}
.campaign-label{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:0 0 7px;color:var(--graphite);font-size:13px;font-weight:700}
.required-label,.optional-label{color:var(--secondary);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.required-label{color:var(--danger)}
.info-control{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;padding:0;border:1px solid var(--border);border-radius:50%;background:var(--surface);color:var(--interactive);font-size:12px;font-weight:750;line-height:1}
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
.devices-page .device-metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:18px}
.catalog-sync{display:flex;align-items:center;justify-content:space-between;gap:24px;margin:0 0 28px;padding:16px 20px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.catalog-sync h2{font-size:20px}
.catalog-sync p{margin:5px 0 0;color:var(--secondary);font-size:13px}
.catalog-sync .section-kicker{margin:0 0 4px}
.sync-summary{font-weight:700!important;color:var(--interactive)!important;white-space:nowrap}
.device-filter-bar{align-items:stretch}
.device-filter-bar .filter-search{flex:1 1 310px}
.device-filter-bar input{width:100%}
.device-table-wrap table{min-width:900px}
.device-table-wrap tbody tr{cursor:pointer}
.device-table-wrap tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,white)}
.device-table-wrap tbody tr:focus-visible{outline:3px solid color-mix(in srgb,var(--sky) 58%,white);outline-offset:-3px}
.device-model-button{display:flex;align-items:center;gap:10px;width:100%;padding:0;border:0;background:none;color:inherit;text-align:left}
.device-model-button strong{display:block;font-weight:700}
.device-model-copy{display:flex;align-items:center;gap:8px}
.device-thumb{display:block;width:38px;height:38px;flex:0 0 38px;object-fit:contain;border-radius:8px;background:var(--surface-muted)}
.device-detail-image{display:block;width:120px;height:120px;object-fit:contain;border-radius:16px;background:var(--surface-muted);margin:0 0 16px}
.device-thumb-placeholder{position:relative;border:1px solid var(--border)}
.device-thumb-placeholder:before{content:"";position:absolute;left:10px;top:8px;width:16px;height:21px;border:2px solid var(--sky);border-radius:5px}
.device-thumb-placeholder:after{content:"";position:absolute;left:15px;top:13px;width:6px;height:2px;border-radius:2px;background:var(--sky);box-shadow:0 8px 0 var(--sky)}
.new-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--lichen) 65%,var(--border));border-radius:999px;background:#EEF2E9;color:#52624C;font-size:10px;font-weight:750;letter-spacing:.06em;text-transform:uppercase}
.admin-state{display:inline-flex;align-items:center;min-height:26px;padding:5px 9px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;line-height:1;white-space:nowrap}
.admin-state-map-yes,.admin-state-support-supported{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}
.admin-state-map-no,.admin-state-support-unsupported{background:#F0E9E5;border-color:#D6BDB2;color:#7A493D}
.admin-state-map-unknown,.admin-state-support-not-evaluated{background:var(--surface-muted);border-color:var(--border);color:var(--secondary)}
.numeric{font-variant-numeric:tabular-nums}
.device-pagination{display:flex;align-items:center;justify-content:center;gap:16px;margin:14px 0 0;color:var(--secondary);font-size:13px}
.device-pagination button,.dialog-close{min-height:34px;padding:7px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--interactive);font-weight:700}
.device-pagination button:hover,.dialog-close:hover{border-color:var(--interactive);background:var(--success-bg)}
.device-pagination button:disabled{cursor:not-allowed;opacity:.45}
.device-dialog{width:min(860px,calc(100% - 32px));max-height:min(820px,calc(100% - 32px));padding:0;border:0;border-radius:16px;background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px rgba(34,42,43,.24)}
.device-dialog::backdrop{background:rgba(34,42,43,.34)}
.device-dialog-inner{padding:24px}
.device-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:22px}
.device-dialog-header h2{font-size:28px}
.dialog-close{width:34px;padding:0;font-size:23px;line-height:1}
.device-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px 26px}
.device-detail-grid section{min-width:0;padding-top:2px}
.detail-kicker{margin:0 0 8px;color:var(--interactive);font-size:11px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}
.device-detail-grid dl{margin:0;border-top:1px solid var(--border)}
.device-detail-grid dl div{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr);gap:12px;padding:8px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 70%,transparent)}
.device-detail-grid dt{color:var(--secondary);font-size:12px}
.device-detail-grid dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}
.technical-value{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px!important}
.device-product-link{margin:22px 0 0;padding-top:16px;border-top:1px solid var(--border);font-size:13px;font-weight:700}
.device-product-link a{color:var(--interactive);text-underline-offset:3px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:800px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.admin-section-nav{margin-left:0}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.updated-at{margin:0}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.devices-page .device-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar input{width:min(100%,360px)}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.public-status{align-items:flex-start;flex-direction:column}.public-status-value{width:100%;justify-content:space-between}.status-guide-grid{grid-template-columns:1fr}.campaign-fields{grid-template-columns:1fr}.campaign-field-wide{grid-column:auto}.attribution-preview{grid-template-columns:1fr}.catalog-sync{align-items:flex-start;flex-direction:column;gap:4px}.sync-summary{white-space:normal!important}.device-detail-grid{grid-template-columns:1fr}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-section-nav{width:100%;overflow:auto}.admin-section-nav a{white-space:nowrap}.admin-nav{width:100%;justify-content:space-between;gap:10px;flex-wrap:wrap}.timezone-control{width:100%;justify-content:space-between}.timezone-control select{max-width:none;flex:1}.dashboard{padding-top:28px}.metrics{gap:8px}.metric{min-height:92px;padding:14px}.metric strong{font-size:26px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}.campaign-card{padding:16px}.campaign-preset-row{grid-template-columns:1fr;gap:8px}.generated-url-row{grid-template-columns:1fr}.copy-button{width:100%}.copy-status{min-height:18px}.device-dialog-inner{padding:18px}.device-detail-grid dl div{grid-template-columns:1fr;gap:2px}.device-detail-grid dd{text-align:left}}
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

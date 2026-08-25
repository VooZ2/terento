from __future__ import annotations

import base64
import hashlib
import hmac
import html
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from .campaign_links import CAMPAIGN_SUGGESTIONS, MEDIUM_OPTIONS, SOURCE_OPTIONS
from .compatibility_status import STATUS_PUBLIC_COPY, CompatibilityStatus


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
    return f"<span class='error-count' title='{detail}' aria-label='{count} errors'>{count}</span>"


def _admin_brand() -> str:
    return """<a class="admin-brand" href="https://terento.app/" aria-label="Terento home">
      <img src="https://terento.app/assets/logo-sky.svg" alt="" width="25" height="29">
      <span>Terento</span><span class="admin-badge">Admin</span>
    </a>"""


def _admin_header(user: dict[str, Any], csrf_token: str, *, active: str = "evidence") -> str:
    username = html.escape(str(user.get("username") or ""))
    evidence_class = " class='active'" if active == "evidence" else ""
    campaign_class = " class='active'" if active == "campaigns" else ""
    return f"""<header class="admin-topbar"><div class="admin-topbar-inner">{_admin_brand()}
      <nav class="admin-section-nav" aria-label="Admin sections"><a{evidence_class} href="/admin">Installation evidence</a><a{campaign_class} href="/admin/campaign-links">Campaign links</a></nav>
      <nav class="admin-nav" aria-label="Admin navigation"><a href="/admin/account">Account</a><span class="admin-user">{username}</span>
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
    *, public_stats_enabled: bool = False,
) -> bytes:
    attempts = sum(int(row.get("attempted_install_count") or 0) for row in rows)
    successes = sum(int(row.get("successful_install_count") or 0) for row in rows)
    failures = sum(int(row.get("failed_install_count") or 0) for row in rows)
    latest = _latest_data_timestamp(rows)
    published = sum(
        1 for row in rows
        if row.get("public_statistics_enabled") is True
        and str(row.get("review_status") or "").upper() == "APPROVED"
        and str(row.get("calculated_status") or "").upper() in {"TESTED", "SUPPORTED", "VERIFIED"}
    ) if public_stats_enabled else 0
    status_values = ["TESTING", "TESTED", "SUPPORTED", "VERIFIED"]
    status_options = "".join(
        f"<option value='{status.lower()}'>{status.title()}</option>"
        for status in status_values
    )
    cards = "".join(
        f"<article class='metric'><span>{label}</span><strong>{value}</strong></article>"
        for label, value in (("Models", len(rows)), ("Reports", attempts), ("Successful", successes), ("Failed", failures))
    )
    table_rows = "".join(_statistics_row(row) for row in rows)
    empty = "<p class='empty'>No installation evidence reports yet.</p>" if not rows else ""
    latest_copy = f"Updated {format_timestamp(latest)}" if latest else "No reports received yet"
    content = f"""
      {_admin_header(user, csrf_token)}
      <main class="dashboard" id="main-content">
        <div class="heading-row"><div><p class="eyebrow">Admin</p><h1>Installation evidence</h1><p class="lede">Compatibility reports received from Terento installations.</p></div><p class="updated-at">{html.escape(latest_copy)}</p></div>
        <section class="metrics" aria-label="Evidence summary">{cards}</section>{empty}
        <section class="evidence-section" aria-labelledby="evidence-title">
          <div class="section-heading"><div><p class="section-kicker">Evidence</p><h2 id="evidence-title">Installation reports</h2></div><p class="table-help">Times shown in UTC</p></div>
          <form class="filter-bar" id="evidence-filters" role="search">
            <label class="filter-search"> <span class="sr-only">Search models</span><input id="evidence-search" type="search" placeholder="Search models" autocomplete="off"></label>
            <label><span class="sr-only">Filter by status</span><select id="evidence-status"><option value="all">All statuses</option>{status_options}</select></label>
            <label><span class="sr-only">Sort reports</span><select id="evidence-sort"><option value="reports">Most reports</option><option value="latest">Latest activity</option></select></label>
          </form>
          <p class="results-count" id="results-count" aria-live="polite">{len(rows)} {"report" if len(rows) == 1 else "reports"}</p>
          <div class="table-wrap"><table><caption class="sr-only">Installation evidence reports by exact device identity</caption><thead><tr><th scope="col">Model</th><th scope="col">Variant</th><th scope="col">Firmware</th><th scope="col">Reports</th><th scope="col">Successful</th><th scope="col">Failed</th><th scope="col">Success rate</th><th scope="col">Status</th><th scope="col">Last success</th><th scope="col">Errors</th></tr></thead><tbody id="evidence-rows">{table_rows}</tbody></table></div>
        </section>
        <section class="public-status" aria-labelledby="public-status-title"><div><p class="section-kicker">Publication</p><h2 id="public-status-title">Public compatibility</h2></div><div class="public-status-value"><span class="status-badge status-{('enabled' if public_stats_enabled else 'disabled')}">{'Enabled' if public_stats_enabled else 'Disabled'}</span><span>{published} {'model' if published == 1 else 'models'} published</span></div></section>
      </main>
      <script>{_dashboard_script()}</script>
    """
    return _layout("Installation evidence", content)


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
    status = str(row.get("calculated_status") or "UNKNOWN").upper()
    search_text = " ".join((model, variant, str(row.get("family") or ""), identity)).strip()
    activity = max((_timestamp_iso(row.get(key)) for key in ("last_success", "last_failure")), default="")
    cells = (
        html.escape(model), html.escape(variant), html.escape(str(row.get("firmware_versions") or "—")),
        html.escape(str(row.get("attempted_install_count", 0))), html.escape(str(row.get("successful_install_count", 0))),
        html.escape(str(row.get("failed_install_count", 0))), html.escape(_format_rate(row.get("success_rate"))),
        _status_badge(status), html.escape(format_timestamp(row.get("last_success"))), _error_cell(row),
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
        status = CompatibilityStatus.UNKNOWN
    label = status.value.title()
    return (
        f"<span class='status-badge status-{status.value.lower()}' role='img' "
        f"aria-label='{html.escape(label)}: {html.escape(STATUS_PUBLIC_COPY[status])}'>"
        f"{html.escape(label)}</span>"
    )


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
        const label = visible.length === 1 ? 'report' : 'reports';
        count.textContent = visible.length === rows.length ? `${visible.length} ${label}` : `${visible.length} of ${rows.length} ${label}`;
      };
      form.addEventListener('submit', (event) => event.preventDefault());
      [search, status, sort].forEach((control) => control.addEventListener('input', refresh));
      refresh();
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
.status-badge{display:inline-flex;align-items:center;justify-content:center;min-width:74px;min-height:28px;padding:6px 10px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;letter-spacing:.03em;line-height:1;text-transform:uppercase}
.status-tested{background:#EDE8DF;border-color:#CFC2AE;color:#5B5144}
.status-supported{background:#E3EDF0;border-color:#ABC3CD;color:#375E6D}
.status-verified{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}
.status-testing,.status-unknown{background:#F0F1ED;border-color:#D8DDD8;color:#60706C}
.status-enabled{background:#E7EEE2;border-color:#B4C6A7;color:#4B6142}
.status-disabled{background:#F0F1ED;border-color:#D8DDD8;color:#60706C}
.public-status{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-top:28px;padding:18px 20px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.public-status .section-kicker{margin-bottom:5px}
.public-status-value{display:flex;align-items:center;gap:12px;color:var(--secondary);font-size:13px;font-weight:600}
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
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:800px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.admin-section-nav{margin-left:0}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.updated-at{margin:0}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar input{width:min(100%,360px)}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.public-status{align-items:flex-start;flex-direction:column}.public-status-value{width:100%;justify-content:space-between}.campaign-fields{grid-template-columns:1fr}.campaign-field-wide{grid-column:auto}.attribution-preview{grid-template-columns:1fr}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-section-nav{width:100%;overflow:auto}.admin-section-nav a{white-space:nowrap}.admin-nav{width:100%;justify-content:space-between;gap:10px}.dashboard{padding-top:28px}.metrics{gap:8px}.metric{min-height:92px;padding:14px}.metric strong{font-size:26px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}.campaign-card{padding:16px}.campaign-preset-row{grid-template-columns:1fr;gap:8px}.generated-url-row{grid-template-columns:1fr}.copy-button{width:100%}.copy-status{min-height:18px}}
"""


def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _layout(title: str, content: str) -> bytes:
    nonce = secrets.token_urlsafe(18)
    content = content.replace("<script>", f"<script nonce=\"{nonce}\">")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>{ADMIN_STYLES}</style></head><body>{content}</body></html>""".encode("utf-8")


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

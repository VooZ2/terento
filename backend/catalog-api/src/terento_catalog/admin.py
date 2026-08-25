from __future__ import annotations

import base64
import hashlib
import hmac
import html
import re
import secrets
from datetime import datetime, timezone
from typing import Any

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


def _admin_header(user: dict[str, Any], csrf_token: str) -> str:
    username = html.escape(str(user.get("username") or ""))
    return f"""<header class="admin-topbar"><div class="admin-topbar-inner">{_admin_brand()}
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


def account_page(user: dict[str, Any], csrf_token: str, *, error: str | None = None, success: str | None = None) -> bytes:
    notice = _error(error) if error else (f"<p class='success'>{html.escape(success or '')}</p>" if success else "")
    return _layout(
        "Account",
        f"""
        {_admin_header(user, csrf_token)}
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
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:800px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.updated-at{margin:0}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar input{width:min(100%,360px)}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.public-status{align-items:flex-start;flex-direction:column}.public-status-value{width:100%;justify-content:space-between}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-nav{width:100%;justify-content:space-between;gap:10px}.dashboard{padding-top:28px}.metrics{gap:8px}.metric{min-height:92px;padding:14px}.metric strong{font-size:26px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}}
"""


def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _layout(title: str, content: str) -> bytes:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>{ADMIN_STYLES}</style></head><body>{content}</body></html>""".encode("utf-8")


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import re
import secrets
from datetime import datetime, timezone
from typing import Any


PASSWORD_MIN_LENGTH = 14
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,64}")
PBKDF2_ITERATIONS = 600_000


class AdminValidationError(ValueError):
    pass


def validate_username(value: str) -> str:
    username = value.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AdminValidationError("Naudotojo vardą turi sudaryti 3–64 raidės, skaičiai arba . _ - ženklai.")
    return username


def validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH or len(value) > 256:
        raise AdminValidationError(f"Slaptažodį turi sudaryti {PASSWORD_MIN_LENGTH}–256 ženklai.")
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
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return str(value)


def setup_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Sukurti administratorių",
        """
        <main class="auth-card">
          <a class="wordmark" href="/">Terento</a>
          <p class="eyebrow">Administravimas</p>
          <h1>Sukurkite pirmą administratorių</h1>
          <p class="lede">Šis veiksmas galimas tik vieną kartą ir reikalauja diegimo paslapties.</p>
          {error}
          <form method="post" action="/admin/setup">
            <label>Naudotojo vardas<input name="username" autocomplete="username" required minlength="3" maxlength="64"></label>
            <label>Slaptažodis<input type="password" name="password" autocomplete="new-password" required minlength="14"></label>
            <label>Pakartokite slaptažodį<input type="password" name="password_confirmation" autocomplete="new-password" required minlength="14"></label>
            <label>Diegimo paslaptis<input type="password" name="bootstrap_secret" autocomplete="one-time-code" required></label>
            <button type="submit">Sukurti administratorių</button>
          </form>
        </main>
        """.format(error=_error(error)),
    )


def login_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Prisijungti",
        """
        <main class="auth-card">
          <a class="wordmark" href="/">Terento</a>
          <p class="eyebrow">Administravimas</p>
          <h1>Prisijungti</h1>
          <p class="lede">Privati diegimų statistika ir suderinamumo įrodymai.</p>
          {error}
          <form method="post" action="/admin/login">
            <label>Naudotojo vardas<input name="username" autocomplete="username" required></label>
            <label>Slaptažodis<input type="password" name="password" autocomplete="current-password" required></label>
            <button type="submit">Prisijungti</button>
          </form>
        </main>
        """.format(error=_error(error)),
    )


def dashboard_page(rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str) -> bytes:
    attempts = sum(int(row.get("attempted_install_count") or 0) for row in rows)
    successes = sum(int(row.get("successful_install_count") or 0) for row in rows)
    failures = sum(int(row.get("failed_install_count") or 0) for row in rows)
    cards = "".join(
        f"<article class='metric'><span>{label}</span><strong>{value}</strong></article>"
        for label, value in (("Modeliai", len(rows)), ("Bandymai", attempts), ("Sėkmingos", successes), ("Nepavykusios", failures))
    )
    table_rows = "".join(_statistics_row(row) for row in rows)
    empty = "<p class='empty'>Dar nėra savanoriškai pateiktų diegimo įvykių.</p>" if not rows else ""
    content = f"""
      <header class="topbar"><a class="wordmark" href="/">Terento</a><nav><a href="/admin/account">Prisijungimo nustatymai</a><form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><button class="link-button">Atsijungti</button></form></nav></header>
      <main class="dashboard">
        <p class="eyebrow">Administravimas</p><h1>Diegimų statistika</h1>
        <p class="lede">Anoniminiai, tik naudotojui sutikus atsiųsti diegimo rezultatai. Prisijungta kaip <strong>{html.escape(str(user['username']))}</strong>.</p>
        <section class="metrics">{cards}</section>{empty}
        <div class="table-wrap"><table><thead><tr><th>Modelis</th><th>Programinė įranga</th><th>Bandymai</th><th>Sėkmingos</th><th>Nepavykusios</th><th>Sėkmė</th><th>Būsena</th><th>Paskutinė sėkmė</th><th>Klaidos</th></tr></thead><tbody>{table_rows}</tbody></table></div>
        <section class="note"><h2>Vieša statistika paruošta, bet išjungta</h2><p>API gali grąžinti TOP modelius tik tada, kai įjungtas serverio leidimas ir konkretus modelis atskirai patvirtintas publikavimui. Neapdoroti įvykiai viešai neatiduodami.</p></section>
      </main>
    """
    return _layout("Diegimų statistika", content)


def account_page(user: dict[str, Any], csrf_token: str, *, error: str | None = None, success: str | None = None) -> bytes:
    notice = _error(error) if error else (f"<p class='success'>{html.escape(success or '')}</p>" if success else "")
    return _layout(
        "Prisijungimo nustatymai",
        f"""
        <header class="topbar"><a class="wordmark" href="/">Terento</a><nav><a href="/admin">Statistika</a></nav></header>
        <main class="auth-card account"><p class="eyebrow">Administravimas</p><h1>Prisijungimo nustatymai</h1>{notice}
          <form method="post" action="/admin/account">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
            <label>Naudotojo vardas<input name="username" value="{html.escape(str(user['username']))}" autocomplete="username" required></label>
            <label>Dabartinis slaptažodis<input type="password" name="current_password" autocomplete="current-password" required></label>
            <label>Naujas slaptažodis <small>(palikite tuščią, jei nekeičiate)</small><input type="password" name="new_password" autocomplete="new-password" minlength="14"></label>
            <label>Pakartokite naują slaptažodį<input type="password" name="new_password_confirmation" autocomplete="new-password" minlength="14"></label>
            <button type="submit">Išsaugoti</button>
          </form>
        </main>
        """,
    )


def _statistics_row(row: dict[str, Any]) -> str:
    errors = row.get("error_categories") or {}
    if isinstance(errors, dict):
        errors_text = ", ".join(f"{key}: {value}" for key, value in sorted(errors.items())) or "—"
    else:
        errors_text = str(errors)
    rate = row.get("success_rate")
    rate_text = f"{rate}%" if rate is not None else "—"
    values = (
        row.get("model"), row.get("firmware_versions") or "—", row.get("attempted_install_count", 0),
        row.get("successful_install_count", 0), row.get("failed_install_count", 0), rate_text,
        row.get("calculated_status") or "UNKNOWN", format_timestamp(row.get("last_success")), errors_text,
    )
    return "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in values) + "</tr>"


def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _layout(title: str, content: str) -> bytes:
    return f"""<!doctype html><html lang="lt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>
    :root{{--ink:#18322d;--muted:#60706c;--paper:#f5f4ee;--card:#fff;--line:#d8ddd8;--accent:#d66b3d;--green:#275f52}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,sans-serif}}a{{color:var(--green)}}.wordmark{{font:bold 24px Georgia,serif;color:var(--ink);text-decoration:none}}.topbar{{height:72px;padding:0 clamp(20px,5vw,72px);display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}}nav{{display:flex;align-items:center;gap:22px}}nav form{{margin:0}}.dashboard{{max-width:1440px;margin:0 auto;padding:56px clamp(20px,5vw,72px)}}.auth-card{{width:min(480px,calc(100% - 32px));margin:8vh auto;background:var(--card);padding:clamp(26px,5vw,48px);border:1px solid var(--line);border-radius:20px;box-shadow:0 18px 60px #18322d12}}.account{{margin-top:56px}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:12px;font-weight:700;color:var(--accent);margin:28px 0 8px}}h1{{font:clamp(34px,5vw,58px)/1.02 Georgia,serif;margin:0 0 16px}}h2{{font:26px/1.2 Georgia,serif}}.lede{{color:var(--muted);max-width:760px}}label{{display:block;font-weight:650;margin:20px 0}}label small{{font-weight:400;color:var(--muted)}}input{{display:block;width:100%;margin-top:7px;padding:12px 14px;border:1px solid #aeb9b4;border-radius:9px;font:inherit;background:white}}button{{border:0;border-radius:99px;padding:12px 20px;background:var(--green);color:white;font:inherit;font-weight:700;cursor:pointer}}.link-button{{padding:0;background:none;color:var(--green);text-decoration:underline}}.error,.success{{padding:12px 14px;border-radius:8px}}.error{{background:#fee9e5;color:#8a2f20}}.success{{background:#e4f2eb;color:#205644}}.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:32px 0}}.metric{{background:white;border:1px solid var(--line);border-radius:14px;padding:20px}}.metric span{{color:var(--muted);display:block}}.metric strong{{font:36px/1.2 Georgia,serif}}.table-wrap{{overflow:auto;background:white;border:1px solid var(--line);border-radius:14px}}table{{border-collapse:collapse;width:100%;min-width:960px}}th,td{{padding:13px 15px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}th{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.note{{max-width:760px;margin-top:28px;padding:20px 24px;border-left:4px solid var(--accent);background:#fff9f3}}.empty{{padding:24px;background:white;border:1px solid var(--line);border-radius:14px}}@media(max-width:760px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.topbar{{height:auto;padding-top:18px;padding-bottom:18px;align-items:flex-start}}nav{{align-items:flex-end;flex-direction:column;gap:6px}}}}
    </style></head><body>{content}</body></html>""".encode("utf-8")


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

"""Admin Web installer page (contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).

Plain words for people, with the stored codes next to them so a failure can be
traced to its cause. Read-only; a separate population from app statistics.
"""

from __future__ import annotations

import html
import json
from typing import Any

from .admin import (
    _ADMIN_NONCE_PLACEHOLDER,
    _PROVIDER_LABELS,
    _admin_header,
    _empty_state,
    _layout,
    _metric_row,
    _metric_tile,
    _overview_period_script,
    _section_card,
    _status_pill,
    _timestamp_markup,
    _unavailable_card,
)
from .statistics_periods import ADMIN_PERIOD_LABELS, ADMIN_PERIODS

WORDS = {
    # Connection outcomes
    "NO_WATCH_CHOSEN": "No watch was chosen in Chrome",
    "CHOOSER_TIMEOUT": "Chrome did not show the watch in time",
    "STARTUP_ENTRY": "The watch's startup entry was chosen instead of the watch",
    "MODEL_NOT_ENABLED": "This watch model is not enabled for installs",
    "POLICY_UNAVAILABLE": "The list of supported watches could not be loaded",
    "OTHER_TAB": "Another tab was already using the watch",
    "TIMEOUT": "The watch did not answer in time",
    "CONNECTION_LOST": "The connection to the watch ended",
    "FAILED": "Other connection error",
    # Map and removal reasons
    "CANCELLED": "Cancelled by the person",
    "WATCH_FULL": "Not enough space on the watch",
    "CHECK_MISMATCH": "The check on the watch did not match",
    "CATALOG_CHANGED": "The map list changed during the install",
    "COMPUTER_FULL": "Not enough space on the computer",
    "EARLIER_CHANGE": "An earlier change on the watch was not finished",
    "SERVER_BUSY": "The server was busy",
    "PREPARE_FAILED": "The server could not prepare the map",
    "BAD_FILE": "The downloaded file was wrong",
    "DOWNLOAD_STOPPED": "The download stopped",
    "OTHER": "Other",
    # Steps
    "PREPARE": "Preparing", "DOWNLOAD": "Downloading", "WRITE": "Writing to the watch", "VERIFY": "Checking on the watch",
    # Server reasons
    "NOT_REVIEWED": "Provider not enabled for the web installer",
    "COMPUTER_LIMIT": "Too many maps at once from one computer",
    "POLICY_WITHHELD": "Map not allowed by the catalog rules",
    "NO_ARTIFACT": "No usable map file in the catalog",
    "SOURCE_NOT_ALLOWED": "Provider address not allowed",
    "PROVIDER_HTTP_ERROR": "Provider returned an error",
    "PROVIDER_UNREACHABLE": "Provider could not be reached",
    "PROVIDER_CHANGED": "Provider file differs from the catalog",
    "BAD_ARCHIVE": "Provider file failed the safety checks",
    "SIZE_LIMIT": "Map is larger than the server allows",
    "DISK_FULL": "Not enough space on the server",
    "SERVICE_RESTARTED": "The server restarted during the job",
}
OUTCOMES = {
    "SUCCEEDED": ("success", "Succeeded"), "FAILED": ("danger", "Failed"), "CANCELLED": ("neutral", "Cancelled"),
    "DELIVERED": ("success", "Sent"), "NOT_DOWNLOADED": ("warning", "Not downloaded"),
    "EXPIRED": ("neutral", "Not collected"), "REFUSED": ("warning", "Refused"), "INTERRUPTED": ("warning", "Interrupted"),
}


def _text(value: Any) -> str:
    return "—" if value in (None, "") else html.escape(str(value))


def _code(*values: Any) -> str:
    codes = " · ".join(str(v) for v in values if v not in (None, ""))
    return f"<code class='web-installer-code'>{html.escape(codes)}</code>" if codes else ""


def _words(code: Any) -> str:
    return _text(WORDS.get(code, code))


def _provider(value: Any) -> str:
    return _text(_PROVIDER_LABELS.get(value, value))


def _bytes(value: Any) -> str:
    if value is None:
        return "—"
    for unit, size in (("GB", 1e9), ("MB", 1e6)):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{round(value / 1e3)} kB"


def _duration(seconds: Any) -> str:
    if seconds is None:
        return "—"
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min" + (f" {seconds % 60} s" if seconds % 60 else "")
    return f"{seconds // 3600} h" + (f" {seconds // 60 % 60} min" if seconds // 60 % 60 else "")


def _outcome(value: str) -> str:
    kind, label = OUTCOMES.get(value, ("neutral", value))
    return _status_pill(kind, label, value=value)


def _table(caption: str, headers: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return _empty_state("empty", empty)
    head = "".join(
        f"<th scope='col'{' class=' + chr(39) + 'column-number' + chr(39) if h.startswith('#') else ''}>{html.escape(h.lstrip('#'))}</th>"
        for h in headers
    )
    body = "".join("<tr>" + "".join(row) + "</tr>" for row in rows)
    return (
        f"<div class='table-wrap'><table class='admin-table web-installer-table'><caption class='sr-only'>{html.escape(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _td(content: str) -> str:
    return f"<td>{content}</td>"


def _num(value: Any) -> str:
    return f"<td class='column-number'>{_text(value)}</td>"


def _watch_sections(watch: dict[str, Any], period: str) -> str:
    tiles = _metric_row([
        _metric_tile("Watch connected", watch["connectedSessions"], scope=period),
        _metric_tile("Maps installed", watch["installed"], scope=period),
        _metric_tile("Maps updated", watch["updated"], scope=period),
        _metric_tile("Failed", watch["failed"], scope=period, failure=True),
        _metric_tile("Writing", _duration(watch["medianWriteS"]), fmt="text", scope=period,
                     state=None if watch["medianWriteS"] is not None else "unknown",
                     secondary=f"then {html.escape(_duration(watch['medianVerifyS']))} checking"),
    ], label="On the watch")
    models = _table("Watch models", ["Model", "System", "Firmware", "#Connected", "#Installed", "#Updated", "#Failed", "Last seen"], [[
        _td(_text(m["model"] or "Not read")), _td(_text(m["system"])), _td(_text(", ".join(m["firmware"]))),
        _num(m["sessions"]), _num(m["installed"]), _num(m["updated"]), _num(m["failed"]), _td(_timestamp_markup(m["last"])),
    ] for m in watch["models"]], "No watch was connected in this period.")
    systems = _table("Systems and browsers", ["System", "Browser", "#Visits", "#Could not use"], [[
        _td(_text(s["system"])), _td(_text(s["browser"])), _num(s["visits"]), _num(s["blocked"]),
    ] for s in watch["systems"]], "No visits in this period.")
    connect = _table("Connection problems", ["Problem", "System", "#Count", "Last"], [[
        _td(_words(p["outcome"]) + _code(p["outcome"], p["error_name"])), _td(_text(p["os_family"])),
        _num(p["count"]), _td(_timestamp_markup(p["last"])),
    ] for p in watch["connectProblems"]], "No connection problems in this period.")
    detail = lambda p: [f"HTTP {p['http_status']}" if p["http_status"] else None,
                        f"MTP 0x{p['mtp_response']:04X}" if p["mtp_response"] else None]
    problems = _table("Install and removal problems", ["Action", "Step", "Problem", "Watch models", "#Count", "#After writing started", "Last"], [[
        _td("Remove" if p["stage"] == "REMOVE" else "Install or update"), _td(_words(p["failure_stage"])),
        _td(_words(p["reason"]) + _code(p["failure_stage"], p["reason"], p["error_name"], *detail(p))),
        _td(_text(", ".join(p["models"]))), _num(p["count"]), _num(p["writeStarted"]), _td(_timestamp_markup(p["last"])),
    ] for p in watch["mapProblems"]], "No failed installs or removals in this period.")
    recent = _table("Recent results on watches", ["Time", "Watch", "System", "Action", "Map", "Result", "#Writing", "#Checking"], [[
        _td(_timestamp_markup(r["occurred_at"])),
        _td(_text(r.get("model")) + (_code("firmware " + r["firmware"]) if r.get("firmware") else "")),
        _td(_text(" ".join(str(v) for v in (r.get("os_family"), r.get("os_major")) if v is not None))),
        _td("Remove" if r["stage"] == "REMOVE" else "Update" if r.get("operation") == "update" else "Install"),
        _td(_text(r.get("package_id")) + _code(r.get("provider"))),
        _td(_outcome(r["outcome"]) + ("" if r["outcome"] == "SUCCEEDED" else
            "<span class='web-installer-why'>" + _words(r.get("reason")) + "</span>"
            + _code(r.get("failure_stage"), r.get("reason"), r.get("error_name")))),
        _num(_duration(r.get("write_s")) if r.get("write_s") is not None else None),
        _num(_duration(r.get("verify_s")) if r.get("verify_s") is not None else None),
    ] for r in watch["recent"]], "No results in this period.")
    return (
        "<h2 class='web-installer-part'>On the watch</h2>" + tiles
        + _section_card("Watch models", models, card_id="web-installer-models")
        + "<div class='web-installer-grid'>"
        + _section_card("Systems and browsers", systems, card_id="web-installer-systems")
        + _section_card("Connection problems", connect, card_id="web-installer-connect")
        + "</div>"
        + _section_card("Install and removal problems", problems, card_id="web-installer-problems")
        + _section_card("Recent results on watches", recent, card_id="web-installer-recent")
    )


def _server_sections(server: dict[str, Any], period: str) -> str:
    tiles = _metric_row([
        _metric_tile("Requests", server["requests"], scope=period),
        _metric_tile("Sent", server["delivered"], scope=period, secondary=html.escape(_bytes(server["servedBytes"]))),
        _metric_tile("Failed", server["failed"], scope=period, failure=True),
        _metric_tile("Preparing", _duration(server["medianReadyS"]), fmt="text", scope=period,
                     state=None if server["medianReadyS"] is not None else "unknown", secondary="median"),
        _metric_tile("Sending", _duration(server["medianSendS"]), fmt="text", scope=period,
                     state=None if server["medianSendS"] is not None else "unknown", secondary="median"),
    ], label="On the server")
    providers = _table("Providers", ["Provider", "#Requests", "#Sent", "#Failed", "#Data sent"], [[
        _td(_provider(p["provider"])), _num(p["requests"]), _num(p["delivered"]), _num(p["failed"]), _num(_bytes(p["servedBytes"])),
    ] for p in server["providers"]], "No requests in this period.")
    problems = _table("Problems", ["Result", "Why", "Provider", "#Count", "Last"], [[
        _td(_outcome(p["outcome"])),
        _td(_words(p["reason"]) + _code(p["reason"], f"HTTP {p['providerHttpStatus']}" if p["providerHttpStatus"] else None)),
        _td(_provider(p["provider"])), _num(p["count"]), _td(_timestamp_markup(p["last"])),
    ] for p in server["problems"]], "No server problems in this period.")
    recent = _table("Recent requests", ["Requested", "Map", "Provider", "Release", "#Size", "Result", "#Preparing", "#Sending"], [[
        _td(_timestamp_markup(j["requested_at"])), _td(_text(j.get("region") or j["package_id"]) + _code(j["package_id"])),
        _td(_provider(j["provider"])), _td(_text(j.get("release"))), _num(_bytes(j.get("size_bytes"))),
        _td(_outcome(j["outcome"]) + (
            "<span class='web-installer-why'>" + _words(j["reason"]) + "</span>"
            + _code(j["reason"], f"HTTP {j['provider_http_status']}" if j.get("provider_http_status") else None)
            if j.get("reason") else "")),
        _num(_duration((j["ready_at"] - j["requested_at"]).total_seconds()) if j.get("ready_at") else None),
        _num(_duration((j["finished_at"] - j["ready_at"]).total_seconds())
             if j.get("ready_at") and j["outcome"] == "DELIVERED" else None),
    ] for j in server["recent"]], "No requests in this period.")
    return (
        "<h2 class='web-installer-part'>On the server</h2>" + tiles
        + "<div class='web-installer-grid'>"
        + _section_card("Providers", providers, card_id="web-installer-providers")
        + _section_card("Problems", problems, card_id="web-installer-server-problems")
        + "</div>"
        + _section_card("Recent requests", recent, card_id="web-installer-requests")
    )


def web_installer_page(data: dict[str, Any] | None, user: dict[str, Any], csrf_token: str, *, period: str) -> bytes:
    if period not in ADMIN_PERIODS:
        period = "7d"
    options = "".join(
        f"<option value='{value}'{' selected' if value == period else ''}>{ADMIN_PERIOD_LABELS[value]}</option>"
        for value in ADMIN_PERIODS
    )
    if not isinstance(data, dict) or "watch" not in data:
        body = _unavailable_card("Web installer", "web-installer-unavailable", retry_href=f"/admin/web-installer?period={period}")
        tests = ""
    else:
        body = _watch_sections(data["watch"], period) + _server_sections(data["server"], period)
        test = data.get("testRecords") or {}
        tests = (
            f"<p class='web-installer-tests muted-value'>Test records: {int(test.get('count') or 0):,}"
            + (f" · last {_timestamp_markup(test['last'])}" if test.get("last") else "") + "</p>"
        )
    content = f"""
      {_admin_header(user, csrf_token, active='web-installer')}
      <main class='dashboard overview-page web-installer-page' id='main-content'>
        <div class='heading-row overview-heading'><div><h1>Web installer</h1></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin/web-installer'><label><span class='sr-only'>Time period</span><select id='overview-period' data-admin-dropdown name='period'>{options}</select></label></form></div>
        {body}
        {tests}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_overview_period_script()}</script>
    """
    # Rows hold UUIDs and datetimes; the revision only needs their text.
    revision = None if not isinstance(data, dict) else json.loads(json.dumps(
        {key: data.get(key) for key in ("watch", "server", "testRecords")}, default=str))
    return _layout("Web installer", content, sections={"webInstaller": revision})

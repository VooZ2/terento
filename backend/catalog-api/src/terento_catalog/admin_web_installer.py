"""Admin Web installer page (contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).

Plain words for people, with the stored codes next to them so a failure can be
traced to its cause. Read-only; a separate population from app statistics.
"""

from __future__ import annotations

import html
from typing import Any

from .admin import (
    _ADMIN_NONCE_PLACEHOLDER,
    _PROVIDER_LABELS,
    _admin_header,
    _admin_icon,
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
from .web_installer import joined

WORDS = {
    # Connection outcomes
    "NO_WATCH_CHOSEN": "No watch selected",
    "CHOOSER_TIMEOUT": "The browser did not show the watch in time",
    "STARTUP_ENTRY": "The watch's startup entry was chosen instead of the watch",
    "MODEL_NOT_ENABLED": "This watch model is not enabled for installs",
    "POLICY_UNAVAILABLE": "The list of supported watches could not be loaded",
    "OTHER_TAB": "Another tab was already using the watch",
    "TIMEOUT": "The watch did not answer in time",
    "CONNECTION_LOST": "The connection to the watch ended",
    "OPEN_ACCESS_DENIED": "USB access denied",
    "INTERFACE_CLAIM_FAILED": "USB interface unavailable",
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
    "DOWNLOAD_BLOCKED": "The network blocked the download",
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
# What the installer page let this system and browser do (GATE outcome).
SUPPORT = {
    "SUPPORTED": ("success", "Supported"), "TESTING": ("progress", "Testing"),
    "BLOCKED_BROWSER": ("danger", "Browser not supported"), "BLOCKED_SYSTEM": ("danger", "System not supported"),
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
    number = " class='column-number'"
    head = "".join(f"<th scope='col'{number if h.startswith('#') else ''}>{html.escape(h.lstrip('#'))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(row) + "</tr>" for row in rows)
    return (
        f"<div class='table-wrap'><table class='admin-table web-installer-table'><caption class='sr-only'>{html.escape(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _browser(value: Any) -> str:
    """Browser name with its Font Awesome logo; the name stays as text."""
    if not value:
        return _text(value)
    family = str(value).split()[0].lower()
    known = family in ("chrome", "edge", "opera", "brave", "firefox", "safari")
    return f"<span class='web-installer-browser'>{_admin_icon('browser-' + (family if known else 'other'))}{_text(value)}</span>"


def _support(support: str) -> str:
    """Icon and short text, readable without hover (owner 2026-10-12)."""
    kind, label = SUPPORT[support]
    return f"<span class='web-installer-support'>{_status_pill(kind, label, value=support)}</span>"


def _td(content: str) -> str:
    return f"<td>{content}</td>"


def _num(value: Any) -> str:
    return f"<td class='column-number'>{_text(value)}</td>"


def _switch(card: str, label: str, panels: list[tuple[str, str, str]], default: str | None = None) -> str:
    """Buttons that show one of ``panels`` (name, button label, body); the
    choice survives period reloads (``_grouped_card_script``)."""
    default = default or panels[0][0]
    buttons = "".join(
        f"<button type='button' class='quick-filter{' active' if name == default else ''}' data-group-switch='{name}' "
        f"aria-pressed='{str(name == default).lower()}'>{title}</button>" for name, title, _ in panels)
    bodies = "".join(f"<div data-group-panel='{name}'{'' if name == default else ' hidden'}>{body}</div>" for name, _, body in panels)
    return (
        f"<div data-group-card='{card}' data-group-default='{default}'><div class='filter-bar web-installer-card-filter'>"
        f"<div class='quick-filter-group' role='group' aria-label='{label}'>{buttons}</div></div>{bodies}</div>"
    )


def _counted(label: str, count: int) -> str:
    return f"{label} <span class='web-installer-count'>{count:,}</span>"


def _records(caption: str, items: list[tuple[str, str, list[tuple[str, str]], list[tuple[str, str]]]], empty: str) -> str:
    """Rows whose results show at once and whose other fields open below:
    (title, subtitle, [(label, value)] shown, [(label, value)] opened)."""
    if not items:
        return _empty_state("empty", empty)
    rows = "".join(
        f"<details class='web-installer-record'><summary>{_admin_icon('chevron-down')}"
        f"<span class='web-installer-record-title'><strong>{title}</strong>{f'<span>{subtitle}</span>' if subtitle else ''}</span>"
        "<span class='web-installer-record-stats'>" + "".join(f"<span><small>{name}</small>{value}</span>" for name, value in stats)
        + "</span></summary><dl class='web-installer-record-details'>"
        + "".join(f"<div><dt>{name}</dt><dd>{value}</dd></div>" for name, value in details) + "</dl></details>"
        for title, subtitle, stats, details in items)
    return f"<div class='web-installer-records' role='group' aria-label='{html.escape(caption, quote=True)}'>{rows}</div>"


def _stat(value: Any, failure: bool = False) -> str:
    return f"<strong{' class=' + chr(39) + 'web-installer-failed' + chr(39) if failure and value else ''}>{_text(value)}</strong>"


def _wide_narrow(wide: str, narrow: str) -> str:
    """A table on wide screens; records on phones, so results never scroll sideways."""
    return f"<div class='web-installer-wide'>{wide}</div><div class='web-installer-narrow'>{narrow}</div>"


def _grouped_card(card: str, caption: str, columns: list[tuple[str, str]], panels: list[tuple[str, str, list[tuple[Any, ...]]]]) -> str:
    """A Group by switch over tables with one row per group and its totals;
    the group's own rows open below it. They sit in one spanning cell, so the
    shared column sort keeps them with their group row.

    ``columns`` follow the label column: (header, col class). Each panel is
    (name, label, groups); a group is (key, label, label extra, total cells,
    rows of cells including their first cell)."""
    cols = "<colgroup><col>" + "".join(f"<col class='{c}'>" for _, c in columns) + "</colgroup>"
    tables = []
    for name, label, groups in panels:
        head = f"<th scope='col'>{label}</th>" + "".join(
            f"<th scope='col' class='{'column-number ' if h.startswith('#') else ''}{c}-cell'>{html.escape(h.lstrip('#'))}</th>" for h, c in columns)
        rows = []
        for index, (key, title, extra, totals, children) in enumerate(groups):
            row_id = f"{card}-{name}-{index}"
            inner = "".join("<tr>" + "".join(child) + "</tr>" for child in children)
            rows.append(
                f"<tr data-group-key='{html.escape(str(key), quote=True)}'><td><button type='button' class='web-installer-group-toggle' "
                f"data-group-toggle aria-expanded='false' aria-controls='{row_id}'>{_admin_icon('chevron-down')}{title}</button>{extra}</td>"
                + "".join(totals) + "</tr>"
                f"<tr class='web-installer-group-rows' id='{row_id}' hidden><td colspan='{len(columns) + 1}'>"
                f"<table class='admin-table web-installer-table web-installer-grouped-table'>{cols}<tbody>{inner}</tbody></table></td></tr>")
        tables.append((name, label,
            f"<div class='table-wrap'><table class='admin-table web-installer-table web-installer-grouped-table' data-own-mobile-layout>"
            f"<caption class='sr-only'>{html.escape(caption)} by {label.lower()}</caption>{cols}"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"))
    return _switch(card, "Group by", tables)


def _cell(content: str, column: str) -> str:
    return f"<td class='{column}-cell'>{content}</td>"


def _count(value: Any, column: str) -> str:
    return f"<td class='column-number {column}-cell'>{_text(value)}</td>"


def _systems(systems: list[dict[str, Any]]) -> str:
    """Systems and browsers by system family or by browser family."""
    if not systems:
        return _empty_state("empty", "No visits in this period.")
    columns = [("#Visits", "web-installer-col-visits"), ("#Could not use", "web-installer-col-blocked")]
    panels = []
    for name, label, key in (("system", "System", "os_family"), ("browser", "Browser", "browser_family")):
        families: dict[Any, list[dict[str, Any]]] = {}
        for item in systems:
            families.setdefault(item.get(key), []).append(item)
        groups = []
        for family, items in sorted(families.items(), key=lambda g: (-sum(i["visits"] for i in g[1]), g[0] or "~")):
            browser = lambda i: _browser(i["browser"]) + _support(i["support"])
            version = lambda i: "<span class='web-installer-version'>" + (
                f"<span>{_text(i['system'])}</span>" + browser(i) if name == "system" else browser(i) + f"<span>{_text(i['system'])}</span>") + "</span>"
            groups.append((family, _browser(family) if name == "browser" else _text(family), "",
                           [_count(sum(i["visits"] for i in items), columns[0][1]), _count(sum(i["blocked"] for i in items), columns[1][1])],
                           [[_td(version(i)), _count(i["visits"], columns[0][1]), _count(i["blocked"], columns[1][1])] for i in items]))
        panels.append((name, label, groups))
    return _grouped_card("web-installer-systems-groups", "Systems and browsers", columns, panels)


def _connect(problems: list[dict[str, Any]], groups: dict[str, list[dict[str, Any]]]) -> str:
    """Connection problems by problem, system or browser. A group's Visits are
    its own distinct sessions, not the sum of its rows."""
    if not problems:
        return _empty_state("empty", "No connection problems in this period.")
    columns = [("Watch models", "web-installer-col-models"), ("#Visits", "web-installer-col-visits"),
               ("#Count", "web-installer-col-count"), ("Last", "web-installer-col-last")]
    # Watch models and Last move under the label on phones.
    phone = lambda p: "<span class='web-installer-phone-line'>" + " · ".join(
        [html.escape(", ".join(p["models"]))] * bool(p["models"]) + [_timestamp_markup(p["last"])]) + "</span>"
    cells = lambda p: [_cell(_text(", ".join(p["models"])), columns[0][1]), _count(p["sessions"], columns[1][1]),
                       _count(p["count"], columns[2][1]), _cell(_timestamp_markup(p["last"]), columns[3][1])]
    dims = lambda *parts: "<span class='web-installer-version'>" + "".join(parts) + "</span>"
    panels = []
    for name, label, key in (("problem", "Problem", "outcome"), ("system", "System", "os_family"), ("browser", "Browser", "browser_family")):
        rows = []
        for group in groups[name]:
            members = [p for p in problems if p.get(key) == group.get(key)]
            if name == "problem":
                title, extra = _words(group[key]), _code(group[key])
                first = lambda p: dims(f"<span>{_text(p['os_family'])}</span>", _browser(p["browser_family"])) + _code(p["error_name"], *_detail(p))
            else:
                title, extra = (_browser(group[key]) if name == "browser" else _text(group[key])), ""
                other = (lambda p: _browser(p["browser_family"])) if name == "system" else (lambda p: f"<span>{_text(p['os_family'])}</span>")
                first = lambda p, other=other: _words(p["outcome"]) + dims(other(p)) + _code(p["outcome"], p["error_name"], *_detail(p))
            rows.append((group.get(key), title, extra + phone(group), cells(group),
                         [[_td(first(p) + phone(p))] + cells(p) for p in members]))
        panels.append((name, label, rows))
    return _grouped_card("web-installer-connect-groups", "Connection problems", columns, panels)


def _grouped_card_script() -> str:
    """Group by switches and group rows; both survive live refreshes."""
    return r"""(() => {
      const chosen = new Map();
      const open = new Set();
      const keyOf = (button) => {
        const row = button.closest('tr');
        return row.closest('[data-group-card]').dataset.groupCard + ':' + row.closest('[data-group-panel]').dataset.groupPanel + ':' + row.dataset.groupKey;
      };
      const apply = () => {
        document.querySelectorAll('[data-group-card]').forEach((card) => {
          const own = (selector) => [...card.querySelectorAll(selector)].filter((node) => node.closest('[data-group-card]') === card);
          // A choice the new period no longer has (Other) falls back to the default.
          const picked = chosen.get(card.dataset.groupCard);
          const name = own('[data-group-switch]').some((button) => button.dataset.groupSwitch === picked) ? picked : card.dataset.groupDefault;
          own('[data-group-switch]').forEach((button) => {
            const on = button.dataset.groupSwitch === name;
            button.classList.toggle('active', on);
            button.setAttribute('aria-pressed', String(on));
          });
          own('[data-group-panel]').forEach((panel) => { panel.hidden = panel.dataset.groupPanel !== name; });
        });
        document.querySelectorAll('[data-group-toggle]').forEach((button) => {
          const expanded = open.has(keyOf(button));
          button.setAttribute('aria-expanded', String(expanded));
          const rows = document.getElementById(button.getAttribute('aria-controls'));
          if (rows) rows.hidden = !expanded;
        });
      };
      document.addEventListener('click', (event) => {
        const pick = event.target.closest('[data-group-switch]');
        if (pick) { chosen.set(pick.closest('[data-group-card]').dataset.groupCard, pick.dataset.groupSwitch); apply(); return; }
        const toggle = event.target.closest('[data-group-toggle]');
        if (!toggle) return;
        const key = keyOf(toggle);
        if (!open.delete(key)) open.add(key);
        apply();
      });
      window.addEventListener('terento-admin-content-changed', apply);
    })();"""


# Problem steps in install order; a removal is its own step whatever step it
# failed at, and a missing or unknown step stays visible as Other.
STEPS = {"PREPARE": "Preparing", "DOWNLOAD": "Downloading", "WRITE": "Writing", "VERIFY": "Checking", "REMOVE": "Removal"}


def _step(problem: dict[str, Any]) -> str:
    if problem["stage"] == "REMOVE":
        return "REMOVE"
    return problem["failure_stage"] if problem.get("failure_stage") in STEPS else "OTHER"


def _detail(row: dict[str, Any]) -> list[str | None]:
    return [f"HTTP {row['http_status']}" if row.get("http_status") else None,
            f"MTP 0x{row['mtp_response']:04X}" if row.get("mtp_response") else None]


def _median_tile(label: str, seconds: Any) -> str:
    return _metric_tile(label, _duration(seconds), fmt="text", state=None if seconds is not None else "unknown")


def _summary(watch: dict[str, Any]) -> str:
    tiles = _metric_row([
        _metric_tile("Maps installed", watch["installed"]),
        _metric_tile("Maps updated", watch["updated"]),
        _metric_tile("Failed after write start", watch["failed"], failure=True),
        _metric_tile("Connected visits", watch["connectedSessions"]),
        _median_tile("Writing · median", watch["medianWriteS"]),
        _median_tile("Checking · median", watch["medianVerifyS"]),
    ], label="Results on watches")
    return f"<section class='admin-card admin-kpi-panel web-installer-kpis' aria-label='Results on watches'>{tiles}</section>"


def _problems(watch: dict[str, Any]) -> str:
    """Problem records per step: attempts, not visits, and not a funnel."""
    connect = watch["connectProblems"]
    steps: dict[str, list[dict[str, Any]]] = {}
    for problem in watch["mapProblems"]:
        steps.setdefault(_step(problem), []).append(problem)
    panels = [("connect", "Connection", sum(p["count"] for p in connect), _connect(connect, watch["connectGroups"]))]
    for key, label in (*STEPS.items(), ("OTHER", "Other")):
        rows = steps.get(key, [])
        if key == "OTHER" and not rows:
            continue
        panels.append((key, label, sum(p["count"] for p in rows), _records(f"{label} problems", [(
            _words(p["reason"]), _text(", ".join(p["models"])),
            [("Count", _stat(p["count"])), ("After writing started", _stat(p["writeStarted"]))],
            [("Action", "Remove" if p["stage"] == "REMOVE" else "Install or update"), ("Step", _words(p["failure_stage"])),
             ("Last", _timestamp_markup(p["last"])), ("Codes", _code(p["failure_stage"], p["reason"], p["error_name"], *_detail(p)) or "—")],
        ) for p in rows], "No problems at this step in this period.")))
    default = next((key for key, _, count, _ in panels if count), "connect")
    return _section_card("Problems", _switch("web-installer-problem-steps", "Problem step", [
        (key, _counted(label, count), body) for key, label, count, body in panels], default), card_id="web-installer-problems")


def _watches(watch: dict[str, Any]) -> str:
    empty = "No watch was connected in this period."
    table = _table("Watch models", ["Model", "System", "Firmware", "#Connected", "#Installed", "#Updated", "#Failed", "Last seen"], [[
        _td(_text(m["model"] or "Not read")), _td(_text(m["system"])), _td(_text(", ".join(m["firmware"]))),
        _num(m["sessions"]), _num(m["installed"]), _num(m["updated"]), _num(m["failed"]), _td(_timestamp_markup(m["last"])),
    ] for m in watch["models"]], empty)
    records = _records("Watch models", [(
        _text(m["model"] or "Not read"), _text(m["system"]),
        [("Installed", _stat(m["installed"])), ("Updated", _stat(m["updated"])), ("Failed", _stat(m["failed"], failure=True))],
        [("Firmware", _text(", ".join(m["firmware"]))), ("Connected", _text(m["sessions"])), ("Last seen", _timestamp_markup(m["last"]))],
    ) for m in watch["models"]], empty)
    return _section_card("Watches and systems", _switch("web-installer-watch-views", "Watches and systems", [
        ("models", "Watch models", _wide_narrow(table, records)),
        ("systems", "Systems and browsers", _systems(watch["systems"])),
    ]), card_id="web-installer-watches")


def _server(server: dict[str, Any]) -> str:
    delivered = server["delivered"]
    tiles = _metric_row([
        _metric_tile("Requests", server["requests"]),
        _metric_tile("Sent", delivered, secondary=html.escape(_bytes(server["servedBytes"]))),
        _metric_tile("Through Cloudflare", server["viaFallback"],
                     secondary=f"{round(100 * server['viaFallback'] / delivered)}% of sent" if delivered else ""),
        _metric_tile("Failed", server["failed"], failure=True),
        _median_tile("Preparing · median", server["medianReadyS"]),
        _median_tile("Sending · median", server["medianSendS"]),
    ], label="Server results")
    http = lambda status: f"HTTP {status}" if status else None
    problems = _records("Server problems", [(
        _words(p["reason"]), _provider(p["provider"]), [("Count", _stat(p["count"]))],
        [("Result", _outcome(p["outcome"])), ("Last", _timestamp_markup(p["last"])),
         ("Codes", _code(p["reason"], http(p["providerHttpStatus"])) or "—")],
    ) for p in server["problems"]], "No server problems in this period.")
    empty = "No requests in this period."
    providers = _wide_narrow(_table("Providers", ["Provider", "#Requests", "#Sent", "#Failed", "#Data sent"], [[
        _td(_provider(p["provider"])), _num(p["requests"]), _num(p["delivered"]), _num(p["failed"]), _num(_bytes(p["servedBytes"])),
    ] for p in server["providers"]], empty), _records("Providers", [(
        _provider(p["provider"]), "",
        [("Requests", _stat(p["requests"])), ("Sent", _stat(p["delivered"])), ("Failed", _stat(p["failed"], failure=True))],
        [("Data sent", _text(_bytes(p["servedBytes"])))],
    ) for p in server["providers"]], empty))
    preparing = lambda j: _duration((j["ready_at"] - j["requested_at"]).total_seconds()) if j.get("ready_at") else None
    sending = lambda j: (_duration((j["finished_at"] - j["ready_at"]).total_seconds())
                         if j.get("ready_at") and j["outcome"] == "DELIVERED" else None)
    why = lambda j: ("<span class='web-installer-why'>" + _words(j["reason"]) + "</span>"
                     + _code(j["reason"], http(j.get("provider_http_status"))) if j.get("reason") else "")
    requests = _wide_narrow(_table("Recent requests", ["Requested", "Map", "Provider", "Release", "#Size", "Result", "#Preparing", "#Sending"], [[
        _td(_timestamp_markup(j["requested_at"])), _td(_text(j.get("region") or j["package_id"]) + _code(j["package_id"])),
        _td(_provider(j["provider"])), _td(_text(j.get("release"))), _num(_bytes(j.get("size_bytes"))),
        _td(_outcome(j["outcome"]) + why(j)), _num(preparing(j)), _num(sending(j)),
    ] for j in server["recent"]], empty), _records("Recent requests", [(
        _text(j.get("region") or j["package_id"]), _provider(j["provider"]) + " · " + _timestamp_markup(j["requested_at"]),
        [("Result", _outcome(j["outcome"]))],
        [("Package", _code(j["package_id"])), ("Release", _text(j.get("release"))), ("Size", _text(_bytes(j.get("size_bytes")))),
         ("Why", why(j) or "—"), ("Preparing", _text(preparing(j))), ("Sending", _text(sending(j)))],
    ) for j in server["recent"]], empty))
    return _section_card("Server", tiles + _switch("web-installer-server-views", "Server", [
        ("problems", _counted("Problems", sum(p["count"] for p in server["problems"])), problems),
        ("providers", "Providers", providers),
        ("requests", _counted("Recent requests", len(server["recent"])), requests),
    ]), card_id="web-installer-server", css="admin-kpi-panel web-installer-server")


def _history(recent: list[dict[str, Any]]) -> str:
    """Every listed map result and removal, also those that stopped before writing."""
    action = lambda r: "Remove" if r["stage"] == "REMOVE" else "Update" if r.get("operation") == "update" else "Install"
    package = lambda r: _text(r.get("package_id")) + _code(r.get("provider")) if r.get("package_id") else _provider(r.get("provider"))
    why = lambda r: ("" if r["outcome"] == "SUCCEEDED" else "<span class='web-installer-why'>" + _words(r.get("reason")) + "</span>"
                     + _code(r.get("failure_stage"), r.get("reason"), r.get("error_name"), *_detail(r)))
    seconds = lambda value: _duration(value) if value is not None else None
    table = _table("Recent results on watches", ["Time", "Watch", "System", "Action", "Map", "Result", "#Writing", "#Checking"], [[
        _td(_timestamp_markup(r["occurred_at"])),
        _td(_text(r.get("model")) + (_code("firmware " + r["firmware"]) if r.get("firmware") else "")),
        _td(_text(joined(r.get("os_family"), r.get("os_major")))), _td(action(r)), _td(package(r)),
        _td(_outcome(r["outcome"]) + why(r)), _num(seconds(r.get("write_s"))), _num(seconds(r.get("verify_s"))),
    ] for r in recent], "No results in this period.")
    records = _records("Recent results on watches", [(
        _text(r.get("model")), action(r) + " · " + _text(r.get("package_id") or _PROVIDER_LABELS.get(r.get("provider"), r.get("provider")))
        + " · " + _timestamp_markup(r["occurred_at"]),
        [("Result", _outcome(r["outcome"]))],
        [("Firmware", _text(r.get("firmware"))), ("System", _text(joined(r.get("os_family"), r.get("os_major")))), ("Map", package(r)),
         ("Why", why(r) or "—"), ("Writing", _text(seconds(r.get("write_s")))), ("Checking", _text(seconds(r.get("verify_s"))))],
    ) for r in recent], "No results in this period.")
    return (
        "<section class='admin-card web-installer-history' id='web-installer-recent' aria-labelledby='web-installer-recent-title'>"
        f"<details><summary><h2 id='web-installer-recent-title'>{_counted('Recent results on watches', len(recent))}</h2>"
        f"{_admin_icon('chevron-down')}</summary>{_wide_narrow(table, records)}</details></section>"
    )


def web_installer_page(data: dict[str, Any] | None, user: dict[str, Any], csrf_token: str, *, period: str, time_zone: str = "UTC") -> bytes:
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
        watch = data["watch"]
        body = _summary(watch) + _problems(watch) + _watches(watch) + _server(data["server"]) + _history(watch["recent"])
        test = data.get("testRecords") or {}
        tests = (
            f"<p class='web-installer-tests muted-value'>Test records: {int(test.get('count') or 0):,}"
            + (f" · last {_timestamp_markup(test['last'])}" if test.get("last") else "") + "</p>"
        )
    content = f"""
      {_admin_header(user, csrf_token, active='web-installer')}
      <main class='dashboard overview-page web-installer-page' id='main-content'>
        <div class='heading-row overview-heading'><div><h1>Web installer</h1></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin/web-installer' data-time-zone='{html.escape(time_zone, quote=True)}'><span class='web-installer-source'>{_admin_icon('source-web')}Web</span><label><span class='sr-only'>Time period</span><select id='overview-period' data-admin-dropdown name='period'>{options}</select></label></form></div>
        {body}
        {tests}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_overview_period_script()}{_grouped_card_script()}</script>
    """
    revision = None if not isinstance(data, dict) else {key: data.get(key) for key in ("watch", "server", "testRecords")}
    return _layout("Web installer", content, sections={"webInstaller": revision})

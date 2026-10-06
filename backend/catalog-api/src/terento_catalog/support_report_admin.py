"""Admin pages for user-sent support reports (contracts/SUPPORT_REPORT_CONTRACT.md).

Rendered with the shared Admin component kit (docs/admin-behavior-contract.md,
"Shared component kit"); this module never changes report content, statistics
or diagnostics.
"""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote, urlencode

from .admin import (
    _ADMIN_NONCE_PLACEHOLDER,
    _admin_app_version_label,
    _admin_header,
    _admin_icon,
    _diagnostics_script,
    _empty_state,
    _layout,
    _metric_row,
    _metric_tile,
    _model_detail_url,
    _optional_nonnegative_int,
    _section_card,
    _status_pill,
    _timestamp_markup,
    _unavailable_card,
)

SUPPORT_REPORT_PAGE_SIZE = 50
CATEGORY_LABELS = {
    "INSTALL_FAILED": "Install failed",
    "UPDATE_FAILED": "Update failed",
    "REMOVE_FAILED": "Removal failed",
    "CONNECTION": "Connection",
    "OTHER": "Other",
}
OPERATION_LABELS = {"INSTALLATION": "Map installation", "UPDATE": "Map update", "REMOVAL": "Map removal"}
ACTION_NOTICES = {
    "handled": "Report marked handled.",
    "reopened": "Report reopened.",
    "linked": "GitHub issue linked.",
    "unlinked": "GitHub issue unlinked.",
}
AUDIT_LABELS = {
    "HANDLED": "Marked handled",
    "REOPENED": "Reopened",
    "ISSUE_LINKED": "Issue linked",
    "ISSUE_UNLINKED": "Issue unlinked",
}


def _e(value: Any) -> str:
    return html.escape(str(value))


def support_status_pill(status: Any) -> str:
    if str(status or "").upper() == "HANDLED":
        return _status_pill("success", "Handled", value="HANDLED")
    return _status_pill("warning", "Open", value="OPEN")


def support_report_url(reference: Any, **query: str) -> str:
    url = "/admin/support-reports/" + quote(str(reference or ""), safe="")
    return url + ("?" + urlencode(query) if query else "")


def _issue_link(value: Any) -> str:
    issue = str(value or "").strip()
    if not issue.startswith("#") or not issue[1:].isdigit():
        return "—"
    return (
        f"<a href='https://github.com/VooZ2/terento/issues/{issue[1:]}' target='_blank' rel='noopener noreferrer'>"
        f"{_e(issue)} {_admin_icon('external')}</a>"
    )


def _model_label(row: dict[str, Any]) -> str:
    parts = [str(row.get(key) or "").strip() for key in ("device_model", "device_variant")]
    return " · ".join(part for part in parts if part) or "—"


def support_report_row(row: dict[str, Any]) -> str:
    """One list row: identity first, dates and status trailing."""
    reference = str(row.get("reference") or "")
    summary = str(row.get("title") or "").strip() or CATEGORY_LABELS.get(str(row.get("category")), "Other")
    description = " <span class='support-report-has-message'>· Description</span>" if row.get("has_user_message") else ""
    return (
        f"<tr data-status='{_e(row.get('status') or 'OPEN')}'>"
        f"<td><a href='{_e(support_report_url(reference))}'><code>{_e(reference)}</code></a></td>"
        f"<td>{_e(CATEGORY_LABELS.get(str(row.get('category')), 'Other'))}</td>"
        f"<td class='support-report-summary'>{_e(summary)}{description}</td>"
        f"<td>{_e(_model_label(row))}</td>"
        f"<td>{_e(_admin_app_version_label(row.get('release_label'), row.get('app_build')))}</td>"
        f"<td class='column-date'>{_timestamp_markup(row.get('received_at'))}</td>"
        f"<td class='column-status'>{support_status_pill(row.get('status'))}</td></tr>"
    )


def support_report_table(rows: list[dict[str, Any]], *, caption: str) -> str:
    return (
        "<div class='table-wrap'><table class='admin-table support-report-table'>"
        f"<caption class='sr-only'>{_e(caption)}</caption><thead><tr>"
        "<th scope='col'>Reference</th><th scope='col'>Category</th><th scope='col'>Report</th>"
        "<th scope='col'>Model</th><th scope='col'>App version</th>"
        "<th scope='col' class='column-date'>Received</th><th scope='col' class='column-status'>Status</th>"
        f"</tr></thead><tbody>{''.join(support_report_row(row) for row in rows)}</tbody></table></div>"
    )


def support_reports_page(
    payload: dict[str, Any] | None, user: dict[str, Any], csrf_token: str, *, status: str = "OPEN",
) -> bytes:
    """Support reports from public builds: Open/Handled filter, 50 per page."""
    status = "HANDLED" if status == "HANDLED" else "OPEN"
    if payload is None or payload.get("available") is False:
        body = _unavailable_card("Reports", "support-report-list", retry_href="")
    else:
        open_count = _optional_nonnegative_int(payload.get("openCount")) or 0
        handled_count = _optional_nonnegative_int(payload.get("handledCount")) or 0
        total = _optional_nonnegative_int(payload.get("filteredTotal")) or 0
        offset = _optional_nonnegative_int(payload.get("offset")) or 0
        limit = _optional_nonnegative_int(payload.get("limit")) or SUPPORT_REPORT_PAGE_SIZE
        rows = list(payload.get("rows") or [])
        query_status = status.lower()
        chips = "".join(
            f"<a class='quick-filter{' active' if value == status else ''}' href='/admin/support-reports?status={value.lower()}'"
            f"{' aria-current=' + chr(39) + 'page' + chr(39) if value == status else ''}>{label} · {count:,}</a>"
            for value, label, count in (("OPEN", "Open", open_count), ("HANDLED", "Handled", handled_count))
        )
        pagination = ""
        if total > limit:
            previous = (
                f"<a class='secondary-button' href='{_e('/admin/support-reports?' + urlencode({'status': query_status, 'offset': max(0, offset - limit)}))}'>Previous</a>"
                if offset else ""
            )
            following = (
                f"<a class='secondary-button' href='{_e('/admin/support-reports?' + urlencode({'status': query_status, 'offset': offset + limit}))}'>Next</a>"
                if offset + limit < total else ""
            )
            pagination = (
                "<div class='provider-pagination' aria-label='Support report pages'>"
                f"{previous}<span>{offset + 1}–{min(total, offset + limit)} of {total:,}</span>{following}</div>"
            )
        if rows:
            listing = support_report_table(rows, caption=f"{status.title()} support reports, newest first") + pagination
        elif offset:
            listing = _empty_state("filtered", "No reports on this page.", action=(f"/admin/support-reports?status={query_status}", "First page"))
        else:
            listing = _empty_state("empty", "No open reports." if status == "OPEN" else "No handled reports.")
        body = _metric_row([
            _metric_tile("Open", open_count, scope="now", failure=False),
            _metric_tile("Handled", handled_count, scope="all"),
            _metric_tile("Reports", open_count + handled_count, scope="all"),
        ], label="Support report summary") + _section_card(
            "Reports",
            f"<div class='quick-filter-group support-report-filters' role='group' aria-label='Report status'>{chips}</div>{listing}",
            card_id="support-report-list",
        )
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard support-reports-page' id='main-content'>
        <p class='back-link'><a href='/admin'>{_admin_icon('arrow-left')} Dashboard</a></p>
        <div class='heading-row'><div><h1>Support reports</h1></div></div>
        {body}
      </main>
    """
    return _layout("Support reports", content, sections={"supportReports": payload})


def _facts(items: list[tuple[str, str]]) -> str:
    """``label`` → already-escaped markup; unknown values render as ``—``."""
    return "<dl class='diagnostic-detail-summary support-report-facts'>" + "".join(
        f"<div><dt>{_e(label)}</dt><dd>{value if value not in ('', None) else '—'}</dd></div>"
        for label, value in items
    ) + "</dl>"


def _text(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return _e(text) if text else "—"


def _flag(value: Any) -> str:
    return "Yes" if value is True else "No" if value is False else "—"


def _technical_details(detail: dict[str, Any], report: dict[str, Any]) -> str:
    verification = report.get("verification") if isinstance(report.get("verification"), dict) else {}
    lines: list[tuple[str, str]] = [
        ("Report ID", f"<code>{_e(detail.get('id'))}</code>"),
        ("Operation ID", f"<code>{_e(detail.get('operation_id'))}</code>" if detail.get("operation_id") else "—"),
        ("Failure stages", _text(", ".join(report.get("failureStages") or []))),
        ("Error category", _text(report.get("errorCategory"))),
        ("Write started", _flag(report.get("writeStarted"))),
        ("Object created", _flag(report.get("objectCreated"))),
        ("Cleanup attempted", _flag(report.get("cleanupAttempted"))),
        ("Cleanup succeeded", _flag(report.get("cleanupSucceeded"))),
        ("Transfer progress", f"{int(report['transferProgressPercent'])}%" if isinstance(report.get("transferProgressPercent"), int) else "—"),
        ("Raw USB model", _text((report.get("device") or {}).get("mtpModel"))),
        ("Family", _text((report.get("device") or {}).get("family"))),
    ]
    lines += [(key, _text(value)) for key, value in verification.items()]
    for context_key, label in (("failureContext", "Failure context"), ("originalFailureContext", "Original failure context")):
        context = report.get(context_key)
        if isinstance(context, dict):
            flat = {key: value for key, value in context.items() if key != "protection"}
            flat.update({f"protection.{key}": value for key, value in (context.get("protection") or {}).items()})
            lines.append((label, "<br>".join(f"{_e(key)}: {_e(value)}" for key, value in flat.items())))
    facts = report.get("lifecycleFacts") or []
    trace = report.get("finishingTrace") or []
    extra = ""
    if facts:
        extra += "<h3>Lifecycle facts</h3><ul class='support-report-list'>" + "".join(f"<li>{_e(item)}</li>" for item in facts) + "</ul>"
    if trace:
        extra += "<h3>Finishing diagnostics</h3><pre class='support-report-trace'><code>" + _e("\n".join(trace)) + "</code></pre>"
    return (
        "<details class='admin-disclosure support-report-technical'><summary>Technical details</summary>"
        f"<div class='disclosure-body'>{_facts(lines)}{extra}</div></details>"
    )


def _diagnostics_card(detail: dict[str, Any]) -> str:
    if detail.get("is_local_test"):
        body = _empty_state("empty", "Local test report: diagnostics are not linked.")
    elif not detail.get("operation_id"):
        body = _empty_state("empty", "No operation ID was sent with this report.")
    else:
        links: list[str] = []
        for row in detail.get("installationDiagnostics") or []:
            identity = str(row.get("compatibility_identity") or row.get("model") or "Unknown model")
            count = _optional_nonnegative_int(row.get("result_count")) or 0
            links.append(
                f"<li><a href='{_e(_model_detail_url(row))}'>Installation report · {_e(identity)}</a>"
                f" <span class='support-report-meta'>{count} map result{'s' if count != 1 else ''} · {_timestamp_markup(row.get('last_occurred_at'))}</span></li>"
            )
        for row in detail.get("updateDiagnostics") or []:
            href = "/admin/update-diagnostics?" + urlencode({"diagnosticId": str(row.get("event_id"))})
            label = " / ".join(str(row.get(key)) for key in ("provider", "region") if row.get(key))
            links.append(
                f"<li><a href='{_e(href)}'>Update report · {_e(label or 'Map update')}</a>"
                f" <span class='support-report-meta'>{_e(str(row.get('outcome') or '').title())} · {_timestamp_markup(row.get('occurred_at'))}</span></li>"
            )
        body = (
            "<ul class='support-report-links'>" + "".join(links) + "</ul>" if links
            else _empty_state("empty", "No installation or update report with this operation ID was received.")
        )
    return _section_card("Diagnostics", body, card_id="support-report-diagnostics")


def _actions_card(detail: dict[str, Any], csrf_token: str) -> str:
    reference = _e(detail.get("reference"))
    hidden = (
        f"<input type='hidden' name='csrf_token' value='{_e(csrf_token)}'>"
        f"<input type='hidden' name='reference' value='{reference}'>"
    )
    handled = str(detail.get("status") or "").upper() == "HANDLED"
    status_form = (
        f"<form method='post' action='/admin/support-reports/{'reopen' if handled else 'handle'}' class='support-report-form'>{hidden}"
        "<label>Note <span class='support-report-optional'>(optional)</span>"
        f"<textarea name='note' maxlength='2000' rows='2'>{_e(detail.get('note') or '')}</textarea></label>"
        f"<button type='submit' class='{'secondary-button' if handled else 'support-report-primary'}'>{'Reopen' if handled else 'Mark handled'}</button></form>"
    )
    issue_form = (
        f"<form method='post' action='/admin/support-reports/issue' class='support-report-form'>{hidden}"
        "<label>GitHub issue"
        f"<input name='linked_github_issue' value='{_e(detail.get('linked_github_issue') or '')}' placeholder='#123' "
        "pattern='#?[0-9]{1,10}' inputmode='numeric' autocomplete='off' spellcheck='false'></label>"
        "<button type='submit' class='secondary-button'>Save issue</button></form>"
    )
    return _section_card("Actions", status_form + issue_form, card_id="support-report-actions")


def _history_card(detail: dict[str, Any]) -> str:
    audit = list(detail.get("audit") or [])
    if not audit:
        body = _empty_state("empty", "No changes yet.")
    else:
        body = "<ul class='support-report-history'>" + "".join(
            f"<li><strong>{_e(AUDIT_LABELS.get(str(item.get('action')), item.get('action')))}</strong>"
            + (f" {_e(item.get('new_github_issue') or item.get('previous_github_issue') or '')}" if str(item.get('action', '')).startswith('ISSUE') else "")
            + f" · {_e(item.get('changed_by_username') or '—')} · {_timestamp_markup(item.get('changed_at'))}"
            + (f"<p>{_e(item.get('note'))}</p>" if item.get("note") else "")
            + "</li>"
            for item in audit
        ) + "</ul>"
    return _section_card("History", body, card_id="support-report-history")


def support_report_detail_page(
    detail: dict[str, Any], user: dict[str, Any], csrf_token: str, *, action: str = "",
) -> bytes:
    report = detail.get("report") if isinstance(detail.get("report"), dict) else {}
    device = report.get("device") if isinstance(report.get("device"), dict) else {}
    maps = [item for item in report.get("maps") or [] if isinstance(item, dict)]
    is_local = bool(detail.get("is_local_test"))
    reference = str(detail.get("reference") or "")
    pills = support_status_pill(detail.get("status")) + (" " + _status_pill("info", "Local test") if is_local else "")
    map_lines = "<br>".join(
        _e(" / ".join(str(item.get(key)) for key in ("provider", "region") if item.get(key)))
        + (f" · {_e(item['release'])}" if item.get("release") else "")
        for item in maps
    )
    handled = ""
    if detail.get("handled_at"):
        handled = _timestamp_markup(detail.get("handled_at")) + (
            f" · {_e(detail.get('handled_by_username'))}" if detail.get("handled_by_username") else ""
        )
    summary = _facts([
        ("Status", pills),
        ("Category", _e(CATEGORY_LABELS.get(str(detail.get("category")), "Other"))),
        ("Received", _timestamp_markup(detail.get("received_at"))),
        ("Sent from app", _timestamp_markup(detail.get("created_at"))),
        ("Model", _text(device.get("model"))),
        ("Variant", _text(device.get("variant"))),
        ("Firmware", _text(device.get("firmware"))),
        ("Operation", _e(OPERATION_LABELS.get(str(report.get("operation")), "—"))),
        ("Map", map_lines or "—"),
        ("Stage", _text(report.get("stage"))),
        ("Error code", _text(", ".join(report.get("errorCodes") or []))),
        ("App version", _e(_admin_app_version_label(detail.get("release_label"), detail.get("app_build")))),
        ("macOS", _text(report.get("macOSVersion"))),
        ("GitHub issue", _issue_link(detail.get("linked_github_issue"))),
        ("Handled", handled or "—"),
    ])
    problem = (
        (f"<p class='support-report-title'><strong>{_e(report['title'])}</strong></p>" if report.get("title") else "")
        + (f"<p>{_e(report['message'])}</p>" if report.get("message") else "")
    ) or _empty_state("empty", "No failure message was included.")
    message = detail.get("user_message")
    description = (
        f"<p class='support-report-message'>{_e(message)}</p>" if message
        else _empty_state("empty", "The user did not add a description.")
    )
    notice = (
        f"<div class='overview-review-notice' role='status'>{_e(ACTION_NOTICES[action])}</div>"
        if action in ACTION_NOTICES else ""
    )
    back = (
        f"<a href='/admin/test-data'>{_admin_icon('arrow-left')} Test data</a>" if is_local
        else f"<a href='/admin/support-reports'>{_admin_icon('arrow-left')} Support reports</a>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='test-data' if is_local else 'overview')}
      <main class='dashboard support-report-page' id='main-content'>
        <p class='back-link'>{back}</p>
        <div class='heading-row'><div><h1><code>{_e(reference)}</code></h1></div></div>
        {notice}
        <div class='support-report-grid'>
          <div class='support-report-main'>
            {_section_card('Summary', summary, card_id='support-report-summary')}
            {_section_card('Problem', problem, card_id='support-report-problem')}
            {_section_card('Description', description, card_id='support-report-description')}
            {_section_card('Details', _technical_details(detail, report), card_id='support-report-details')}
          </div>
          <div class='support-report-side'>
            {_actions_card(detail, csrf_token)}
            {_diagnostics_card(detail)}
            {_history_card(detail)}
          </div>
        </div>
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_diagnostics_script()}</script>
    """
    return _layout(f"Support report {reference}", content, sections={"supportReport": {
        "reference": reference, "status": detail.get("status"), "issue": detail.get("linked_github_issue"),
    }})


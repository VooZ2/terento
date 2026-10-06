"""Admin-only update diagnostics, separate from installation compatibility evidence."""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

# Messages are authored locally. Raw diagnostic text and arbitrary payload fields
# are deliberately never rendered or copied into the admin page.
_REASONS = {
    'UPDATE_FAILED_ACQUISITION': ('The replacement could not be downloaded or prepared.', 'Check the provider package, then retry the update in Terento.'),
    'UPDATE_FAILED_SOURCE_VALIDATION': ('The replacement failed source validation.', 'Recheck the provider package before retrying.'),
    'UPDATE_BLOCKED_INSUFFICIENT_SPACE': ('There is not enough room for a safe update.', 'Review device storage in Terento. Keep the working map until enough space is available.'),
    'UPDATE_FAILED_DEVICE_DISCONNECTED': ('The device disconnected.', 'Reconnect the device and inspect its map status in Terento before retrying.'),
    'UPDATE_FAILED_WRITE': ('The replacement could not be written.', 'Reconnect the device and review Terento diagnostics before retrying.'),
    'UPDATE_FAILED_COMMIT': ('The update could not finish replacing the previous map.', 'Inspect the installed maps in Terento before retrying; do not delete files manually.'),
    'UPDATE_FAILED_MANIFEST_RECONCILIATION': ('Local ownership records could not be reconciled.', 'Review the device and local diagnostics in Terento before another update.'),
    'UPDATE_FAILED_CLEANUP': ('Cleanup did not complete.', 'Review Terento diagnostics and device state; do not remove unknown files.'),
    'UPDATE_BLOCKED_NOT_MANAGED': ('The current map is not managed by Terento.', 'Use the installed-map actions in Terento; automatic replacement requires recorded ownership.'),
    'UPDATE_BLOCKED_NO_UPDATE': ('No newer release is available.', 'Refresh the catalog and inspect the installed version.'),
    'UPDATE_BLOCKED_NEWER_INSTALLED': ('A newer version is already installed.', 'Keep the installed version and review provider release metadata.'),
    'UPDATE_BLOCKED_CONFIRMATION_REQUIRED': ('Confirmation is required.', 'Confirm the update in Terento.'),
    'UPDATE_BLOCKED_TRANSACTION_ALREADY_RUNNING': ('Another device operation is running.', 'Wait for the current operation to finish.'),
    'UPDATE_BLOCKED_TERENTO_DEVICE_SCOPE': ('Device authorization did not permit this update.', 'Review the device authorization result in Terento.'),
    'UPDATE_BLOCKED_UNSUPPORTED_DEVICE': ('The device is not supported for this operation.', 'Review the device model and capability assessment in Terento.'),
}
for _code in ('REMOTE_MISSING', 'SIZE_MISMATCH', 'HASH_MISMATCH', 'METADATA_MISMATCH', 'POST_VERIFY'):
    _REASONS['UPDATE_FAILED_' + _code] = (
        'The replacement did not pass device verification.',
        'Reconnect the device and inspect Terento diagnostics before retrying. Do not remove the working map manually.',
    )
for _code in ('UNKNOWN_STATE', 'AMBIGUOUS_MAP_IDENTITY', 'CURRENT_OBJECT_CHANGED', 'UNKNOWN_TARGET'):
    _REASONS['UPDATE_BLOCKED_' + _code] = (
        'Terento could not establish a safe update target.',
        'Reconnect and rescan the device in Terento. Review diagnostics if the same condition persists.',
    )


def _uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _update_detail_context(connection, row):
    if row is None:
        return None
    row = dict(row)
    if row.get('canonical_device_model_id'):
        row['device'] = connection.execute(
            'SELECT id,model,variant,case_size_mm,screen_technology FROM device_model WHERE id=%s',
            (row['canonical_device_model_id'],)).fetchone()
    else:
        row['device'] = None
    row['audit'] = list(connection.execute(
        'SELECT action,previous_state,next_state,changed_by,changed_at FROM map_update_diagnostic_audit WHERE event_id=%s ORDER BY id DESC',
        (row['event_id'],)).fetchall())
    return row


def load_update_diagnostics(db: Any, *, event_id: str = '', diagnostic_id: str = '',
                            outcome: str = '', offset: int = 0, device_id: str = '',
                            lifecycle: str = '') -> dict[str, Any]:
    """Read exact report/model scope; caller enforces admin authentication."""
    if (offset < 0 or outcome not in {'', 'failed', 'not_started', 'succeeded'} or (event_id and diagnostic_id)
            or lifecycle not in {'', 'ACTIVE', 'RESOLVED'} or len(device_id) > 160
            or ((event_id or diagnostic_id) and (device_id or outcome or lifecycle or offset))):
        raise ValueError('invalid_update_filter')
    if (event_id and not _uuid(event_id)) or (diagnostic_id and not _uuid(diagnostic_id)):
        raise ValueError('invalid_update_identifier')
    data: dict[str, Any] = {'rows': [], 'detail': None, 'event': None, 'status': '',
                            'outcome': outcome, 'offset': offset, 'device_id':device_id,
                            'device':None,'lifecycle':lifecycle, 'has_more':False}
    with db.connection() as connection:
        if device_id:
            data['device'] = connection.execute(
                'SELECT id,model,variant,case_size_mm,screen_technology FROM device_model WHERE id=%s', (device_id,)).fetchone()
            if not data['device']:
                raise ValueError('unknown_device')
        if event_id:
            event = connection.execute('''SELECT event_id, operation_id, provider_id, region,
                       event_type, outcome, occurred_at, app_build, release_label
                FROM map_download_event WHERE event_id = %s AND is_local_test IS FALSE
                  AND event_type IN ('MAP_UPDATE_SUCCEEDED', 'MAP_UPDATE_FAILED')''',
                (_uuid(event_id),)).fetchone()
            data['event'] = event
            if not event:
                return {**data, 'status': 'Event not found.'}
            matches = connection.execute('''SELECT * FROM map_update_diagnostic
                WHERE is_local_test IS FALSE AND operation_id = %s AND provider = %s AND lower(region) = lower(%s)
                ORDER BY occurred_at DESC, event_id LIMIT 2''',
                (event['operation_id'], event['provider_id'], event['region'])).fetchall()
            if len(matches) == 1 and matches[0].get('outcome') == event.get('outcome'):
                data['detail'] = _update_detail_context(connection, matches[0])
            elif len(matches) == 1:
                data['status'] = 'The diagnostic outcome does not match this event. No diagnostic was selected.'
            elif matches:
                data['status'] = 'More than one diagnostic matches this operation. No diagnostic was selected.'
            else:
                data['status'] = 'Failure details were not received. Historical events may have no diagnostics, or diagnostic sharing may have been disabled. Request the local Terento diagnostic report for investigation.'
            return data
        if diagnostic_id:
            row = connection.execute('SELECT * FROM map_update_diagnostic WHERE event_id = %s AND is_local_test IS FALSE',
                                     (_uuid(diagnostic_id),)).fetchone()
            data['detail'] = _update_detail_context(connection, row)
            if not data['detail']:
                data['status'] = 'Diagnostic not found.'
            return data
        data['rows'] = connection.execute('''SELECT d.*, m.model AS canonical_device_model_name,m.variant AS canonical_device_variant
                FROM map_update_diagnostic d LEFT JOIN device_model m ON m.id=d.canonical_device_model_id
                WHERE d.is_local_test IS FALSE AND (%s = '' OR d.outcome = %s)
                  AND (%s = '' OR d.canonical_device_model_id = %s)
                  AND (%s = '' OR d.diagnostic_status = %s)
                ORDER BY d.occurred_at DESC, d.event_id LIMIT 51 OFFSET %s''',
                (outcome.upper(),outcome.upper(),device_id,device_id,lifecycle,lifecycle,offset)).fetchall()
        # Report totals for the list scope (raw report rows, the update report
        # stream), independent of the outcome filter and pagination (ADM-09).
        try:
            totals = connection.execute('''SELECT count(*) AS total,
                    count(*) FILTER (WHERE d.outcome = 'SUCCEEDED') AS succeeded,
                    count(*) FILTER (WHERE d.outcome = 'FAILED') AS failed,
                    count(*) FILTER (WHERE d.outcome = 'NOT_STARTED') AS not_started,
                    count(*) FILTER (WHERE d.outcome = 'FAILED' AND d.diagnostic_status = 'ACTIVE') AS open_failed
                FROM map_update_diagnostic d
                WHERE d.is_local_test IS FALSE
                  AND (%s = '' OR d.canonical_device_model_id = %s)
                  AND (%s = '' OR d.diagnostic_status = %s)''',
                (device_id, device_id, lifecycle, lifecycle)).fetchone()
            data['totals'] = dict(totals) if isinstance(totals, dict) else None
        except Exception:
            data['totals'] = None
    data['has_more'] = len(data['rows']) > 50
    data['rows'] = data['rows'][:50]
    if device_id:
        data['summary'] = db.update_model_statistics().get(device_id, {
            'successfulUpdateCount':0,'failedUpdateCount':0,'attemptedUpdateCount':0,'notStartedCount':0,'ambiguousUpdateCount':0})
    return data


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else 'Unknown'))


def _fact(value: Any) -> str:
    return 'Yes' if value is True else 'No' if value is False else 'Unknown'


def _preservation_fact(value: Any, outcome: str | None) -> str:
    if value is True:
        return 'Yes'
    if value is False:
        return 'Replaced successfully' if outcome == 'SUCCEEDED' else 'Not confirmed — inspect device'
    return 'Unknown'


def _update_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    """Only an assessed catalog identity grants a link to an exact model."""
    from .admin import _device_detail_url, _identity_parts
    device = row.get('device') or {}
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    if row.get('canonical_device_model_id'):
        if device:
            model, variant, _ = _identity_parts(device)
        else:
            model = str(row.get('canonical_device_model_name') or 'Catalog model')
            variant = str(row.get('canonical_device_variant') or 'Unknown')
        link = _device_detail_url(row['canonical_device_model_id'], anchor='updates')
        return f"<a href='{html.escape(link, quote=True)}'>{_escape(model)}</a>", variant, model
    model = payload.get('model') or 'Unknown model'
    return f"{_escape(model)} <span class='muted-value'>(reported; exact identity unassigned)</span>", str(payload.get('variant') or 'Unknown'), str(model)


def _update_reason(row: dict[str, Any]) -> tuple[str, str]:
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    if row.get('outcome') == 'SUCCEEDED':
        return 'The update succeeded.', 'No failure action is required.'
    reason = _REASONS.get(payload.get('failureCode'), (
        'No recognized failure reason was recorded.',
        'Review the local Terento diagnostic report. Do not infer the cause from the statistics alone.'))
    if payload.get('failureCode') == 'UPDATE_FAILED_ACQUISITION':
        return {
            'download': ('The replacement could not be downloaded.', 'Check the provider package and the Mac connection, then retry in Terento.'),
            'extract': ('The replacement could not be extracted.', 'Check available local storage and the provider package; review the local diagnostic report before retrying.'),
            'source-validation': ('The replacement failed source validation.', 'Recheck the provider package before retrying.'),
            'preflight': ('Replacement preparation was blocked.', 'Review the local Terento diagnostic report before retrying.'),
        }.get(payload.get('failureStage'), reason)
    return reason


def _update_technical_fields(row: dict[str, Any]) -> list[tuple[str, Any]]:
    from .admin import _failure_context_fields
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    fields = [(label, payload.get(key)) for label, key in (
        ('Failure stage', 'failureStage'), ('Failure code', 'failureCode'),
        ('Automatic finishing result', 'automaticFinishingResult'),
        ('Transfer progress', 'transferProgressBucket'), ('Transport', 'transport'),
        ('Firmware', 'firmwareVersion'))]
    for key, label in (('failureContext', 'Failure'), ('originalFailureContext', 'Original failure')):
        if payload.get(key) is None:
            fields.append((label + ' context', 'Unavailable'))
        else:
            fields.extend((label + ' ' + name.lower(), value)
                for name, value in _failure_context_fields({'context': payload[key]}, 'context', technical=True))
    return fields


def _update_issue_report(row: dict[str, Any]) -> tuple[str, str]:
    from .admin import _markdown_issue_value, _sanitised_issue_value
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    _, variant, model = _update_identity(row)
    reason, action = _update_reason(row)
    title = _sanitised_issue_value(
        f"[Map update anomaly] {model}" if row.get('outcome') == 'SUCCEEDED' else
        f"[Map update] {model} — {payload.get('failureCode') or row.get('outcome') or 'Unknown result'}", max_length=180)
    sections = [
        ('Summary', [('Operation', 'Map update'), ('Model', model), ('Variant', variant),
            ('Identity', 'Catalog assessed' if row.get('canonical_device_model_id') else 'Unassigned; reported model only'),
            ('Result', row.get('outcome')), ('Date', row.get('occurred_at')),
            ('Map', row.get('provider')), ('Region', row.get('region')),
            ('Map version', payload.get('mapRelease')), ('App version', payload.get('terentoVersion')), ('Build', payload.get('appBuild'))]),
        ('What happened', [('Reason', reason), ('Stage', payload.get('failureStage')), ('Failure code', payload.get('failureCode'))]),
        ('Next action', [('Action', action)]),
        ('Safety facts', [('Write started', _fact(payload.get('writeStarted'))),
            ('Cleanup attempted', _fact(payload.get('cleanupAttempted'))), ('Cleanup succeeded', _fact(payload.get('cleanupSucceeded'))),
            ('Previous map confirmed preserved', _preservation_fact(payload.get('oldMapPreserved'), row.get('outcome')))]),
        ('Technical details', _update_technical_fields(row)),
        ('Reference', [('Diagnostic ID', row.get('event_id')), ('Operation ID', row.get('operation_id'))]),
    ]
    body = '\n\n'.join('## ' + heading + '\n\n' + '\n'.join(
        f'- {label}: {_markdown_issue_value(value) or "Unknown"}' for label, value in fields)
        for heading, fields in sections)
    return title, body


def _update_review_controls(row: dict[str, Any], csrf_token: str, return_to: str) -> str:
    from .admin import (DIAGNOSTIC_DISCLOSURE_CLASS, _diagnostic_review_administration, _github_issue_controls,
                        _github_issue_link, _normalise_github_issue_reference, _timestamp_markup)
    try:
        issue = _normalise_github_issue_reference(row.get('linked_github_issue'))
    except ValueError:
        issue = None
    identifier = str(row['event_id'])
    hidden = f"<input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='diagnostic_id' value='{html.escape(identifier, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>"
    resolved = row.get('diagnostic_status') == 'RESOLVED'
    lifecycle = ''
    resolution_detail = ''
    if resolved:
        resolution_rows = ''.join(f'<div><dt>{label}</dt><dd>{_escape(value)}</dd></div>' for label, value in (
            ('Resolution reason', row.get('resolution_code') or row.get('resolution_reason')),
            ('Resolution note', row.get('resolution_note'))) if value)
        if row.get('resolved_at'):
            resolution_rows += f"<div><dt>Resolved at</dt><dd>{_timestamp_markup(row['resolved_at'])}</dd></div>"
        resolution_detail = f"<dl class='diagnostic-detail-summary'>{resolution_rows}</dl>"
    if resolved:
        lifecycle = f"<form method='post' action='/admin/update-diagnostics/reopen' class='diagnostic-action-form admin-async-action'>{hidden}<h4>Review state</h4><p>Resolved. The original update result remains in history.</p>{resolution_detail}<button type='submit' class='secondary-button'>Reopen diagnostic</button></form>"
    elif row.get('outcome') != 'SUCCEEDED':
        lifecycle = f"<form method='post' action='/admin/update-diagnostics/resolve' class='diagnostic-action-form admin-async-action' data-confirm='Resolve this diagnostic? The original update result remains in history and statistics.'>{hidden}<h4>Resolve diagnostic</h4><label>Reason<select name='resolution_reason' required><option value='FIXED'>Fixed</option><option value='HISTORICAL_SUPERSEDED'>Historical / superseded</option><option value='DUPLICATE'>Duplicate</option><option value='NOT_TERENTO_ISSUE'>Not a Terento issue</option><option value='OTHER'>Other</option></select></label><label>Resolution note <span class='optional-label'>Optional</span><textarea name='resolution_note' rows='3'></textarea></label><button type='submit'>Resolve diagnostic</button></form>"
    workflow = ''
    if issue and not resolved:
        state = row.get('diagnostic_workflow_status')
        workflow = f"<form method='post' action='/admin/update-diagnostics/workflow' class='diagnostic-action-form admin-async-action'>{hidden}<h4>GitHub issue workflow</h4><label>Status<select name='diagnostic_workflow_status'><option value='IN_PROGRESS'{' selected' if state != 'UNDER_REVIEW' else ''}>In progress</option><option value='UNDER_REVIEW'{' selected' if state == 'UNDER_REVIEW' else ''}>Under review</option></select></label><button type='submit' class='secondary-button'>Save workflow status</button></form>"
    title, body = _update_issue_report(row)
    controls = _github_issue_controls(title, body, issue=issue, csrf_token=csrf_token,
        identifier=identifier, return_to=return_to, action='/admin/update-diagnostics/issue', identifier_name='diagnostic_id')
    issue_form = f"<section class='diagnostic-section diagnostic-issue-section github-review'><h3>GitHub issue</h3><p class='github-current'>{_github_issue_link(issue) if issue else 'No linked issue'}</p><p class='table-help'>Review the report before sharing. A closed linked issue resolves this diagnostic after synchronization; the update result remains in history.</p><div class='github-issue-controls'>{controls}</div></section>"
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    technical_fields = [('Diagnostic ID', identifier), ('Operation ID', row.get('operation_id'))] + _update_technical_fields(row)
    technical = ''.join(f'<div><dt>{_escape(label)}</dt><dd>{_escape(value)}</dd></div>' for label, value in technical_fields)
    technical_form = f"<details class='{DIAGNOSTIC_DISCLOSURE_CLASS} diagnostic-technical-section'><summary>Technical details</summary><div class='disclosure-body'><div class='technical-copy-actions'><button type='button' class='secondary-button' data-copy-diagnostic-id='{html.escape(identifier, quote=True)}'>Copy diagnostic ID</button><button type='button' class='secondary-button' data-copy-technical-report data-report='{html.escape(body, quote=True)}'>Copy technical report</button><span class='copy-status' data-copy-status role='status' aria-live='polite'></span></div><dl class='diagnostic-detail-summary'>{technical}</dl></div></details>"
    administration = _diagnostic_review_administration(f"{lifecycle}{workflow}")
    return f"{issue_form}<div class='diagnostic-disclosure-stack'>{administration}{technical_form}</div>"


def update_summary_markup(summary: dict[str, Any], device_id: str) -> str:
    """Update reports for one model: diagnostic stream, all time. Styled like
    the Installs card beside it, with plain (unlinked) counts (owner decision
    2026-10-06); the update history below filters by outcome."""
    from .admin import _metric_row, _metric_tile

    def count(field: str, label: str, *, failure: bool = False) -> str:
        return _metric_tile(label, int(summary.get(field) or 0), failure=failure, data_stat=field)

    values = _metric_row([
        count('successfulUpdateCount', 'Successful'),
        count('failedUpdateCount', 'Failed', failure=True),
        count('notStartedCount', 'Blocked before writing'),
    ], label='Update reports for this model')
    conflicts = int(summary.get('ambiguousUpdateCount') or 0)
    note = f"<p class='table-help'>{conflicts} conflicting reported results excluded from attempt totals. Inspect update history.</p>" if conflicts else ''
    return (
        "<section class='admin-card admin-kpi-panel diagnostic-model-metrics model-statistics model-update-statistics' aria-labelledby='model-update-kpis-title'>"
        f"<header class='admin-card-head'><h2 id='model-update-kpis-title'>Updates</h2></header>"
        f"{values}{note}</section>"
    )


def update_history_markup(data: dict[str, Any], *, base_url: str = '/admin/update-diagnostics', embedded: bool = False) -> str:
    from .admin import _timestamp_markup, _diagnostic_result, _github_issue_link, _admin_app_version_label
    selected = data.get('outcome', '')
    def url(**values: Any) -> str:
        parameters = {'deviceId': data.get('device_id', ''), 'outcome': selected, 'lifecycle': data.get('lifecycle', '')}
        parameters.update(values)
        if embedded:
            parameters = {'updateOutcome': parameters['outcome'], 'updateOffset': parameters.get('offset', 0)}
        return base_url + ('&' if '?' in base_url else '?') + urlencode({k: v for k, v in parameters.items() if v != ''}) + ('#updates' if embedded else '')
    from .admin import _operation_map_label, _scope_chip
    if embedded:
        return _embedded_update_history_markup(data, url)
    title = 'Reports'
    result = (
        f"<section class='model-page-section admin-card' id='updates' aria-labelledby='update-history-title'><header class='admin-card-head'><h2 id='update-history-title'>{title}</h2>"
        f"{_scope_chip('all')}</header>"
    )
    result += "<div class='filter-bar diagnostic-filter-bar'><nav class='quick-filter-group' aria-label='Filter update reports'>"
    for value, label in _UPDATE_OUTCOME_FILTERS:
        active = selected == value
        result += f"<a class='quick-filter{' active' if active else ''}' href='{html.escape(url(outcome=value, offset=0), quote=True)}'{' aria-current="true"' if active else ''}>{label}</a>"
    result += "</nav></div><div class='table-wrap'><table class='diagnostic-list-table mobile-record-table'><caption class='sr-only'>Reported map update results</caption><thead><tr><th scope='col'>Date</th><th scope='col'>Map</th><th scope='col'>Result</th><th scope='col'>GitHub issue</th><th scope='col'>App version</th><th scope='col'>Action</th></tr></thead><tbody>"
    for row in data.get('rows', []):
        payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
        link = '/admin/update-diagnostics?' + urlencode({'diagnosticId': str(row['event_id'])})
        result += f"<tr><td data-label='Date'>{_timestamp_markup(row.get('occurred_at'))}</td><td data-label='Map'>{_escape(_operation_map_label([row]))}</td><td data-label='Result'>{_diagnostic_result(row.get('outcome'))}</td><td data-label='GitHub issue'>{_github_issue_link(row.get('linked_github_issue'))}</td><td data-label='App version'>{_escape(_admin_app_version_label(payload.get('terentoVersion'), payload.get('appBuild')))}</td><td data-label='Action'><a href='{html.escape(link, quote=True)}'>Inspect update</a></td></tr>"
    if not data.get('rows'):
        result += "<tr><td colspan='6'>No update reports match this filter. Reports appear when diagnostic sharing is enabled.</td></tr>"
    result += '</tbody></table></div><nav class="provider-pagination" aria-label="Update history pages">'
    if data.get('offset', 0):
        result += f"<a class='secondary-button' href='{html.escape(url(offset=max(0, data['offset'] - 50)), quote=True)}'>Previous updates</a>"
    if data.get('has_more'):
        result += f"<a class='secondary-button' href='{html.escape(url(offset=data.get('offset', 0) + 50), quote=True)}'>Next updates</a>"
    return result + '</nav></section>'


# Same order and labels as the Installation history quick filters (owner decision 2026-10-06).
_UPDATE_OUTCOME_FILTERS = (('', 'All'), ('failed', 'Failed'), ('not_started', 'Blocked'), ('succeeded', 'Successful'))


def _embedded_update_history_markup(data: dict[str, Any], url: Any) -> str:
    """Device-detail Update history, laid out like Installation history.

    The heading sits outside the card, the filters reuse the quick-filter bar and
    the table reuses the diagnostic list / mobile record table. Filtering and
    paging stay server-side (``updateOutcome`` / ``updateOffset``), so the
    filters are links marked with ``aria-current``.
    """
    from .admin import (_timestamp_markup, _diagnostic_result, _github_issue_link,
                        _admin_app_version_label, _operation_map_label)
    selected = data.get('outcome', '')
    rows = data.get('rows') or []
    offset = data.get('offset', 0) or 0
    heading = "<h2 id='update-history-title'>Update history</h2>"
    if not rows and not selected and not offset:
        return ("<section class='diagnostics-detail-section model-page-section compact-empty-state' id='updates' "
                f"aria-labelledby='update-history-title'>{heading}<p class='empty'>No update history for this device.</p></section>")
    filters = ''
    for value, label in _UPDATE_OUTCOME_FILTERS:
        active = selected == value
        current = " aria-current='page'" if active else ''
        filters += (f"<a class='quick-filter{' active' if active else ''}' "
                    f"href='{html.escape(url(outcome=value, offset=0), quote=True)}'{current}>{label}</a>")
    result = (
        "<section class='diagnostics-detail-section model-page-section' id='updates' aria-labelledby='update-history-title'>"
        f"<div class='section-heading'><div>{heading}</div></div>"
        "<nav class='filter-bar diagnostic-filter-bar update-history-filters' aria-label='Filter update history'>"
        f"<div class='quick-filter-group'>{filters}</div>"
        + (f"<a class='secondary-button filter-clear' href='{html.escape(url(outcome='', offset=0), quote=True)}' "
           "aria-label='Clear update history filters'>Clear</a>" if selected else '')
        + "</nav>"
    )
    if rows:
        result += (
            "<div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table update-history-table mobile-record-table'>"
            "<caption class='sr-only'>Reported map update results for this exact model and variant</caption><thead><tr>"
            "<th scope='col' class='column-date'>Date</th><th scope='col'>Map</th><th scope='col' class='column-status'>Result</th>"
            "<th scope='col'>GitHub issue</th><th scope='col'>App version</th><th scope='col' class='column-status'>Action</th>"
            "</tr></thead><tbody>"
        )
        for index, row in enumerate(rows):
            payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
            link = '/admin/update-diagnostics?' + urlencode({'diagnosticId': str(row['event_id'])})
            release = _admin_app_version_label(payload.get('terentoVersion'), payload.get('appBuild'))
            release_markup = _escape(release) if release != '—' else "<span class='muted-value'>—</span>"
            result += (
                f"<tr><td class='column-date' data-label='Date'>{_timestamp_markup(row.get('occurred_at'))}</td>"
                f"<td class='history-map' data-label='Map'>{_escape(_operation_map_label([row]))}</td>"
                f"<td class='column-status' data-label='Result'>{_diagnostic_result(row.get('outcome'))}</td>"
                f"<td data-label='GitHub issue'>{_github_issue_link(row.get('linked_github_issue'))}</td>"
                f"<td data-label='App version'>{release_markup}</td>"
                "<td class='column-status' data-label='Action'><a class='secondary-button update-history-inspect' "
                f"href='{html.escape(link, quote=True)}' aria-label='Inspect update {offset + index + 1}'>Inspect</a></td></tr>"
            )
        result += '</tbody></table></div>'
    else:
        result += "<p class='results-count'>No update reports match this filter.</p>"
    pages = ''
    if offset:
        pages += f"<a class='secondary-button' href='{html.escape(url(offset=max(0, offset - 50)), quote=True)}'>Previous updates</a>"
    if data.get('has_more'):
        pages += f"<a class='secondary-button' href='{html.escape(url(offset=offset + 50), quote=True)}'>Next updates</a>"
    if pages:
        result += f"<nav class='provider-pagination' aria-label='Update history pages'>{pages}</nav>"
    return result + '</section>'


def _update_totals_markup(totals: dict[str, Any] | None) -> str:
    """Report tiles for the list scope; the stream is update reports, not Maps updates."""
    from .admin import _metric_row, _metric_tile
    state = None if totals is not None else 'unavailable'
    totals = totals or {}

    def tile(label: str, key: str, *, failure: bool = False, href: str | None = None) -> str:
        return _metric_tile(label, totals.get(key), scope='all', state=state, failure=failure,
                            href=href, data_stat=key)

    return _metric_row([
        tile('Reports', 'total'),
        tile('Successful', 'succeeded'),
        tile('Failed', 'failed', failure=True),
        tile('Blocked', 'not_started'),
        tile('Open', 'open_failed', failure=True, href='/admin/update-diagnostics?outcome=failed&lifecycle=ACTIVE'),
    ], label='Update report totals')


def update_diagnostics_page(data: dict[str, Any], user: dict[str, Any], csrf_token: str) -> bytes:
    from .admin import _admin_header, _admin_icon, _layout, _timestamp_markup, _diagnostic_result, _diagnostics_script, _admin_app_version_label, _operation_map_label, _diagnostic_state_badge, _diagnostic_heading, _diagnostic_outcome_sections
    content = _admin_header(user, csrf_token, active='update-diagnostics')
    content += (
        "<main id='main-content' class='dashboard provider-detail update-diagnostics-page'>"
        "<div class='heading-row'><h1>Update reports</h1>"
        "<a class='section-link' href='/admin/update-diagnostics'>All update reports</a></div>"
    )
    if data.get('status'):
        content += f"<section class='provider-card admin-card'><h2>Report status</h2><p>{_escape(data['status'])}</p></section>"
    detail = data.get('detail')
    event = data.get('event')
    if detail or event:
        row = detail or event
        payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
        model, variant, _ = _update_identity(row)
        content += f"<section class='provider-card'><h2>{_diagnostic_heading(row.get('outcome'), update=True)}</h2><dl class='diagnostic-detail-summary'>"
        fields = [('Operation', 'Map update'), ('Device', model), ('Variant', _escape(variant)),
            ('Date', _timestamp_markup(row.get('occurred_at'))),
            ('Map / region', _escape(_operation_map_label([row]))),
            ('Result', _diagnostic_result(row.get('outcome'))),
            ('App version', _escape(_admin_app_version_label(payload.get('terentoVersion') or row.get('release_label'), payload.get('appBuild') or row.get('app_build'))))]
        if detail:
            review_state = 'RESOLVED' if row.get('diagnostic_status') == 'RESOLVED' else row.get('diagnostic_workflow_status') or 'OPEN'
            fields.append(('Review state', _diagnostic_state_badge(review_state)))
        content += ''.join(f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in fields) + '</dl>'
        if detail:
            reason, action = _update_reason(row)
            safety = ''.join(f'<div><dt>{label}</dt><dd>{_escape(value)}</dd></div>' for label, value in (
                ('Write started', _fact(payload.get('writeStarted'))), ('Cleanup attempted', _fact(payload.get('cleanupAttempted'))),
                ('Cleanup succeeded', _fact(payload.get('cleanupSucceeded'))),
                ('Previous map confirmed preserved', _preservation_fact(payload.get('oldMapPreserved'), row.get('outcome')))))
            content += _diagnostic_outcome_sections(_escape(reason), _escape(action), safety)
            provider = row.get('provider')
            if payload.get('failureCode') in {'UPDATE_FAILED_ACQUISITION', 'UPDATE_FAILED_SOURCE_VALIDATION'} and payload.get('failureStage') != 'preflight' and provider in {'freizeitkarte', 'opentopomap', 'maprando', 'bbbike'}:
                content += f"<p><a class='secondary-button' href='/admin/providers/{provider}'>Review provider packages</a></p>"
            if _uuid(row.get('event_id')):
                content += _update_review_controls(row, csrf_token, '/admin/update-diagnostics?' + urlencode({'diagnosticId': str(row['event_id'])}))
        content += '</section>'
    else:
        device = data.get('device')
        if device:
            from .admin import _identity_parts, _device_detail_url
            model, variant, _ = _identity_parts(device)
            content += f"<p><a href='{html.escape(_device_detail_url(data['device_id']), quote=True)}'>{_escape(model)} · {_escape(variant)}</a></p>"
        if data.get('device_id'):
            content += update_summary_markup(data.get('summary') or {}, data['device_id'])
        else:
            content += _update_totals_markup(data.get('totals'))
        content += update_history_markup(data)
    from .admin import _script_tag
    return _layout('Update reports', content + '</main>' + _script_tag(_diagnostics_script()))

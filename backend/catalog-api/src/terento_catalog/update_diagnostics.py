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


def load_update_diagnostics(db: Any, *, event_id: str = '', diagnostic_id: str = '',
                            outcome: str = '', offset: int = 0) -> dict[str, Any]:
    """Read through the existing Database connection; caller enforces admin auth."""
    if offset < 0 or outcome not in {'', 'failed', 'not_started'} or (event_id and diagnostic_id):
        raise ValueError('invalid_update_filter')
    if (event_id and not _uuid(event_id)) or (diagnostic_id and not _uuid(diagnostic_id)):
        raise ValueError('invalid_update_identifier')
    data: dict[str, Any] = {'rows': [], 'detail': None, 'event': None, 'status': '',
                            'outcome': outcome if outcome in {'failed', 'not_started'} else '',
                            'offset': max(0, offset)}
    with db.connection() as connection:
        if event_id:
            identifier = _uuid(event_id)
            if identifier is None:
                return {**data, 'status': 'Event not found.'}
            event = connection.execute('''SELECT event_id, operation_id, provider_id, region,
                       event_type, outcome, occurred_at, app_build, release_label
                FROM map_download_event WHERE event_id = %s AND is_local_test IS FALSE
                  AND event_type IN ('MAP_UPDATE_SUCCEEDED', 'MAP_UPDATE_FAILED')''',
                (identifier,)).fetchone()
            data['event'] = event
            if not event:
                return {**data, 'status': 'Event not found.'}
            # Native evidence keeps canonical region case; map-use intake stores
            # lowercase. Match that deterministic casing difference only.
            matches = connection.execute('''SELECT * FROM map_update_diagnostic
                WHERE is_local_test IS FALSE AND operation_id = %s AND provider = %s AND lower(region) = lower(%s)
                ORDER BY occurred_at DESC, event_id LIMIT 2''',
                (event['operation_id'], event['provider_id'], event['region'])).fetchall()
            if len(matches) == 1 and matches[0].get('outcome') == event.get('outcome'):
                data['detail'] = matches[0]
            elif len(matches) == 1:
                data['status'] = 'The diagnostic outcome does not match this event. No diagnostic was selected.'
            elif matches:
                data['status'] = 'More than one diagnostic matches this operation. No diagnostic was selected.'
            else:
                data['status'] = 'Failure details were not received. Historical events may have no diagnostics, or diagnostic sharing may have been disabled. Request the local Terento diagnostic report for investigation.'
            return data
        if diagnostic_id:
            identifier = _uuid(diagnostic_id)
            if identifier:
                data['detail'] = connection.execute(
                    'SELECT * FROM map_update_diagnostic WHERE event_id = %s AND is_local_test IS FALSE', (identifier,)).fetchone()
            if not data['detail']:
                data['status'] = 'Diagnostic not found.'
            return data
        data['rows'] = connection.execute('''SELECT event_id, provider, region, outcome,
                    occurred_at, payload FROM map_update_diagnostic
                WHERE is_local_test IS FALSE AND (%s = '' OR outcome = %s)
                ORDER BY occurred_at DESC, event_id LIMIT 51 OFFSET %s''',
                (data['outcome'].upper(), data['outcome'].upper(), data['offset'])).fetchall()
    data['has_more'] = len(data['rows']) > 50
    data['rows'] = data['rows'][:50]
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


def update_diagnostics_page(data: dict[str, Any], user: dict[str, Any], csrf_token: str) -> bytes:
    from .admin import _admin_header, _layout, _timestamp_markup

    content = _admin_header(user, csrf_token, active='map-statistics')
    content += "<main id='main-content' class='dashboard provider-detail'><div class='heading-row'><h1>Update diagnostics</h1></div><p>Update reports are separate from installation results and compatibility evidence.</p>"
    content += "<nav class='provider-problem-actions' aria-label='Update report navigation'><a class='secondary-button' href='/admin/update-diagnostics'>All update reports</a><a class='secondary-button' href='/admin/map-statistics'>Map statistics</a></nav>"
    if data.get('status'):
        content += f"<section class='provider-card'><h2>Diagnostic availability</h2><p>{_escape(data['status'])}</p></section>"
    detail = data.get('detail')
    event = data.get('event')
    if detail or event:
        row = detail or event
        payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
        code = payload.get('failureCode')
        reason, action = _REASONS.get(code, ('No recognized failure reason was recorded.', 'Review the local Terento diagnostic report. Do not infer the cause from the statistics alone.'))
        if code == 'UPDATE_FAILED_ACQUISITION':
            reason, action = {
                'download': ('The replacement could not be downloaded.', 'Check the provider package and the Mac connection, then retry in Terento.'),
                'extract': ('The replacement could not be extracted.', 'Check available local storage and the provider package; review the local diagnostic report before retrying.'),
                'source-validation': ('The replacement failed source validation.', 'Recheck the provider package before retrying.'),
                'preflight': ('Replacement preparation was blocked.', 'Review the local Terento diagnostic report before retrying.'),
            }.get(payload.get('failureStage'), (reason, action))
        content += f"<section class='provider-card'><h2>{_escape(row.get('region'))} · {_escape(row.get('provider') or row.get('provider_id'))}</h2>"
        content += f"<p>{_timestamp_markup(row.get('occurred_at'))} · {_escape(row.get('outcome'))}</p>"
        if detail:
            if row.get('outcome') == 'SUCCEEDED':
                reason, action = 'The update succeeded.', 'No failure action is required.'
            content += f"<h3>What happened</h3><p>{_escape(reason)}</p><h3>Next action</h3><p>{_escape(action)}</p><dl class='provider-information-list' style='overflow-wrap:anywhere'>"
            for label, value in (
                ('Stage', payload.get('failureStage')), ('Failure code', code),
                ('Write started', _fact(payload.get('writeStarted'))),
                ('Cleanup attempted', _fact(payload.get('cleanupAttempted'))),
                ('Cleanup succeeded', _fact(payload.get('cleanupSucceeded'))),
                ('Previous map confirmed preserved', _preservation_fact(payload.get('oldMapPreserved'), row.get('outcome'))),
                ('App version', payload.get('terentoVersion')), ('App build', payload.get('appBuild')),
            ):
                content += f'<div><dt>{label}</dt><dd>{_escape(value)}</dd></div>'
            content += '</dl>'
            provider = row.get('provider')
            if code in {'UPDATE_FAILED_ACQUISITION', 'UPDATE_FAILED_SOURCE_VALIDATION'} and payload.get('failureStage') != 'preflight' and provider in {'freizeitkarte', 'opentopomap', 'maprando', 'bbbike'}:
                content += f"<p><a class='secondary-button' href='/admin/providers/{provider}'>Review provider packages</a></p>"
        else:
            content += f"<p>App build: {_escape(row.get('app_build'))} · Release: {_escape(row.get('release_label'))}</p>"
        content += '</section>'
    else:
        selected = data.get('outcome', '')
        content += "<section class='provider-card'><form method='get' class='filter-bar'><label for='update-outcome'>Outcome</label> <select id='update-outcome' name='outcome'>"
        for value, label in (('', 'All outcomes'), ('failed', 'Failed'), ('not_started', 'Not started')):
            content += f"<option value='{value}'{' selected' if value == selected else ''}>{label}</option>"
        content += "</select> <button type='submit' class='secondary-button'>Filter reports</button></form><div class='table-wrap' style='overflow-x:auto'><table><thead><tr><th>Map</th><th>Outcome</th><th>Time</th><th>Action</th></tr></thead><tbody>"
        for row in data.get('rows', []):
            link = '/admin/update-diagnostics?' + urlencode({'diagnosticId': str(row['event_id'])})
            content += f"<tr><td>{_escape(row.get('region'))} · {_escape(row.get('provider'))}</td><td>{_escape(row.get('outcome'))}</td><td>{_timestamp_markup(row.get('occurred_at'))}</td><td><a href='{html.escape(link, quote=True)}'>View report</a></td></tr>"
        if not data.get('rows'):
            content += '<tr><td colspan="4">No update diagnostics received for this filter.</td></tr>'
        content += '</tbody></table></div>'
        if data.get('offset', 0):
            content += '<a href="?' + html.escape(urlencode({'outcome': selected, 'offset': max(0, data['offset'] - 50)}), quote=True) + '">Previous reports</a> '
        if data.get('has_more'):
            content += '<a href="?' + html.escape(urlencode({'outcome': selected, 'offset': data.get('offset', 0) + 50}), quote=True) + '">Next reports</a>'
        content += '</section>'
    return _layout('Update diagnostics', content + '</main>')

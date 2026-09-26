"""Meaningful private-view revisions; rendering, transport and heartbeat data are excluded."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Any

# Source event and decision times deliberately remain. These are observation-only clocks.
_OBSERVATION_FIELDS = {
    'generatedAt', 'checked_at', 'checkedAt', 'lastHealthCheck', 'lastDownloadTest',
    'heartbeat_at', 'heartbeatAt', 'last_heartbeat_at', 'csrf_token', 'csrfToken',
    'requestId', 'nonce', 'lastObservedAt', 'lastSuccessfulObservedAt',
}
_CHECK_CONTEXTS = {'healthHistory', 'health', 'observations', 'weekly', 'scheduler', 'issueSync', 'githubSync'}


def _canonical(value: Any, context: str = '') -> Any:
    if isinstance(value, dict):
        if context == 'downloads':
            # A successful poll with unchanged counters is an observation, not new work.
            # Keep increases and discontinuities (including their interval) meaningful.
            trend = []
            for row in value.get('trend', []):
                if row.get('state') == 'observed_zero':
                    continue
                point = {k: v for k, v in row.items() if k not in {'observed_at', 'previous_observed_at'}}
                if point.get('state') == 'baseline':
                    point.pop('bucket', None)
                elif isinstance(point.get('bucket'), datetime):
                    point['bucket'] = point['bucket'].replace(minute=0, second=0, microsecond=0)
                elif isinstance(point.get('bucket'), str):
                    point['bucket'] = point['bucket'][:13]
                trend.append(point)
            value = {**value, 'trend': trend}
        if context == 'scheduler' and value.get('status') in {'RUNNING', 'WAITING', 'HEALTHY'}:
            value = {**value, 'status': 'HEALTHY'}
        ignored = set(_OBSERVATION_FIELDS)
        if context in _CHECK_CONTEXTS:
            ignored |= {'id', 'observed_at', 'started_at', 'completed_at', 'next_run_at',
                        'duration_ms', 'workflow_run_id', 'workflow_run_url', 'received_at',
                        'observation_id', 'source_run_id', 'source_run_url', 'updated_at'}
        if value.get('acquisition_id') or (value.get('operation_id') and value.get('map_result_index') is not None):
            ignored |= {'event_id', 'received_at'}
        return {str(k): _canonical(v, str(k)) for k, v in sorted(value.items()) if k not in ignored}
    if isinstance(value, (list, tuple)):
        # Lists describe populations. Reordering or delivery of the same fact is not new work.
        unique = {json.dumps(_canonical(item, context), sort_keys=True, separators=(',', ':')) for item in value}
        return [json.loads(item) for item in sorted(unique)]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def section_revisions(sections: dict[str, Any]) -> dict[str, str]:
    return {key: hashlib.sha256(json.dumps(_canonical(value, key), sort_keys=True,
                separators=(',', ':')).encode()).hexdigest() for key, value in sections.items()}


def statistics_revisions(payload: dict[str, Any]) -> dict[str, str]:
    return section_revisions({
        'statistics': {key: payload.get(key) for key in ('rows', 'summary', 'allTimeSummary', 'linkage')},
        'eventDetail': {key: payload.get(key) for key in ('detailRows', 'detailTotal', 'detailPage', 'detailPageSize')},
    })

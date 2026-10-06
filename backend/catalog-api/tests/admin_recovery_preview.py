"""Generate synthetic admin recovery fixtures; no DB, telemetry or device access.

PYTHONPATH=src python3.13 tests/admin_recovery_preview.py /tmp/admin-recovery
Serve that directory locally, then run admin_recovery_browser.cjs.
"""
from pathlib import Path
from terento_catalog.admin import overview_page, provider_detail_page
from terento_catalog.update_diagnostics import update_diagnostics_page

HISTORICAL = '11111111-1111-4111-8111-111111111111'
CURRENT = '22222222-2222-4222-8222-222222222222'
DIAGNOSTIC = '33333333-3333-4333-8333-333333333333'
NOW = '2026-10-02T18:02:00Z'


def build(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    user = {'username': 'Recovery preview'}
    packages = []
    for region, title in [('idaho', 'Idaho — United States'), ('nordeste', 'Nordeste — Brazil')]:
        for style in ['bbbike', 'ontrail']:
            packages.append({'id': f'{region}-{style}', 'name': title, 'region': region,
                'release': '2026-09-30', 'availability': 'UNAVAILABLE', 'artifact_count': 1,
                'broken_artifact_count': 1, 'artifacts': [{'kind': 'main', 'validation_status': 'UNAVAILABLE',
                'source_url': f'https://data.bbbike.org/osm/garmin/region/{region}/{style}.zip',
                'last_check': {'code': 'validation_failed', 'message': 'README date could not be validated.',
                    'nextAction': 'Review source metadata and recheck this package.', 'checkedAt': NOW}}]})
    provider = {'id': 'bbbike', 'name': 'BBBike', 'status': 'ACTIVE', 'maps': packages,
        'sources': [], 'healthStatus': 'HEALTHY', 'affectedPackageCount': 4,
        'brokenArtifactCount': 4, 'problematicSourceCount': 4}
    events = [{'event_id': event_id, 'event_type': 'MAP_UPDATE_FAILED', 'outcome': 'FAILED',
        'provider_id': 'bbbike', 'region': 'fra', 'display_name': label, 'occurred_at': NOW}
        for event_id, label in [(HISTORICAL, 'Historical France update'), (CURRENT, 'Current France update')]]
    trend = [{'bucket': f'2026-09-{day:02d}T00:00:00Z', 'success_count': 3,
        'failed_count': 1, 'map_update_count': 3, 'map_update_success_count': 2,
        'map_update_failed_count': 1} for day in [1, 8, 15, 22, 29]]
    overview = {'period': 'all', 'data': {'hasData': True, 'recentActivity': events,
        'completedInstallCount': 15, 'failedInstallCount': 5, 'mapUpdateCount': 15,
        'allTimeSuccessCount': 15, 'allTimeFailedCount': 5, 'allTimeInstallSuccessRate': 75,
        'trend': trend, 'bucket': 'week'}, 'providers': []}
    detail = {'event_id': DIAGNOSTIC, 'region': 'FRA', 'provider': 'bbbike', 'outcome': 'FAILED',
        'occurred_at': NOW, 'payload': {'failureCode': 'UPDATE_FAILED_COMMIT',
        'failureStage': 'cleanup', 'writeStarted': True, 'oldMapPreserved': False,
        'terentoVersion': 'Preview', 'appBuild': 'fixture'}}
    source_detail = {**detail, 'outcome': 'NOT_STARTED', 'payload': {**detail['payload'],
        'failureCode': 'UPDATE_FAILED_SOURCE_VALIDATION', 'failureStage': 'source-validation',
        'writeStarted': False, 'oldMapPreserved': True}}
    missing = {'event': {'region': 'fra', 'provider_id': 'bbbike', 'outcome': 'FAILED',
        'occurred_at': NOW}, 'status': 'Failure details were not received. Request the local Terento diagnostic report for investigation.'}
    pages = {'provider': provider_detail_page({'provider': provider}, [], [], user, 'fixture'),
        'chart': overview_page(overview, user, 'fixture'),
        'updates': update_diagnostics_page({'rows': [detail], 'totals': {'total': 52, 'succeeded': 44, 'failed': 5, 'not_started': 3, 'open_failed': 2}}, user, 'fixture'),
        'update-detail': update_diagnostics_page({'detail': detail}, user, 'fixture'),
        'update-missing': update_diagnostics_page(missing, user, 'fixture'),
        'update-source': update_diagnostics_page({'detail': source_detail}, user, 'fixture')}
    for name, body in pages.items():
        (root / (name + '.html')).write_bytes(body)
    return pages


if __name__ == '__main__':
    import sys
    build(sys.argv[1])

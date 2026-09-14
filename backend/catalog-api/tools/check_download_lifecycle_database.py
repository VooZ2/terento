"""Exercise component identity and terminal deduplication on disposable CI only."""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from uuid import uuid4


def check_download_lifecycle_database(database):
    assert urlparse(database.dsn).path == '/terento_ci'
    now = datetime.now(timezone.utc)
    operation = str(uuid4())
    main, contours = str(uuid4()), str(uuid4())

    def event(acquisition, component, event_type, offset):
        return dict(id=str(uuid4()), operationId=operation, providerId='opentopomap',
                    mapId='opentopomap-andorra', region='ANDORRA', appBuild='30',
                    releaseLabel='1.0.0-beta.12', acquisitionId=acquisition,
                    componentKind=component, eventType=event_type,
                    outcome='SUCCEEDED' if event_type == 'DOWNLOAD_SUCCEEDED' else 'UNKNOWN',
                    timestamp=now + timedelta(seconds=offset))

    # Delivery order differs from occurrence order. Terminal remains authoritative.
    terminal = event(main, 'main', 'DOWNLOAD_SUCCEEDED', 2)
    assert database.insert_map_event(terminal)
    assert not database.insert_map_event(terminal)
    for acquisition, kind in ((main, 'main'), (contours, 'contours')):
        assert database.insert_map_event(event(acquisition, kind, 'DOWNLOAD_STARTED', 0))
        assert database.insert_map_event(event(acquisition, kind, 'DOWNLOAD_PROCESSING', 1))
    assert not database.insert_map_event(event(main, 'main', 'DOWNLOAD_INTERRUPTED', 3))
    assert database.insert_map_event(event(contours, 'contours', 'DOWNLOAD_INTERRUPTED', 3))
    snapshot = database.admin_overview_map_snapshot(now - timedelta(seconds=1), recent_limit=100)
    recent = [r for r in snapshot['recentActivity'] if r.get('operation_id') == operation]
    assert len(recent) == 2, recent
    assert {(r['component_kind'], r['event_type']) for r in recent} == {
        ('main', 'DOWNLOAD_SUCCEEDED'), ('contours', 'DOWNLOAD_INTERRUPTED')}, recent
    assert all(len(r['lifecycle']) == 3 for r in recent), recent
    legacy = event(None, None, 'DOWNLOAD_STARTED', 4)
    legacy['operationId'] = str(uuid4())
    assert database.insert_map_event(legacy)
    legacy['id'] = str(uuid4())
    assert not database.insert_map_event(legacy)
    print('PASS: main/contour event isolation, terminal-first delivery, phase history and legacy deduplication')

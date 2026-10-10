"""Synthetic Activity identity fixture: no DB, telemetry or device operations."""
from pathlib import Path
from terento_catalog.admin import ADMIN_STYLES, ADMIN_STYLESHEET_PATH, overview_page


def build(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    events = []
    kinds = ['INSTALL_SUCCEEDED', 'INSTALL_FAILED', 'INSTALL_SUCCEEDED',
             'MAP_UPDATE_SUCCEEDED', 'MAP_UPDATE_FAILED', 'MAP_UPDATE_FAILED']
    for index, kind in enumerate(kinds):
        custom = index == 2
        events.append({'event_id': f'00000000-0000-4000-8000-{index+1:012d}',
            'event_type': kind, 'provider_id': 'custom' if custom else 'bbbike',
            'provider_name': 'Should never show custom provider' if custom else 'BBBike',
            'region': 'custom' if custom else 'LT', 'display_name': 'Lithuania',
            'occurred_at': f'2026-10-02T18:{index:02d}:00Z', 'model': 'Unverified device name' if index == 5 else 'fēnix 8',
            'variant': '47 mm, AMOLED', 'canonical_device_model_id': None if index == 5 else 'fenix-8-47-amoled'})
    events.append({'event_id': '00000000-0000-4000-8000-000000000007', 'event_type': 'DOWNLOAD_SUCCEEDED',
        'provider_id': 'bbbike', 'provider_name': 'BBBike', 'region': 'LT', 'display_name': 'Lithuania',
        'occurred_at': '2026-10-02T18:10:00Z', 'lifecycle': [
            {'type': 'DOWNLOAD_STARTED', 'at': '2026-10-02T18:07:00Z'},
            {'type': 'DOWNLOAD_PROCESSING', 'at': '2026-10-02T18:08:00Z'},
            {'type': 'DOWNLOAD_SUCCEEDED', 'at': '2026-10-02T18:10:00Z'}]})
    page = overview_page({'period': '24h', 'timeZone': 'UTC',
        'data': {'hasData': True, 'recentActivity': events}, 'providers': []},
        {'username': 'Activity preview'}, 'fixture')
    (root / 'activity.html').write_bytes(page)
    # Signed-in pages link the content-versioned Admin stylesheet.
    (root / ADMIN_STYLESHEET_PATH.lstrip('/')).parent.mkdir(parents=True, exist_ok=True)
    (root / ADMIN_STYLESHEET_PATH.lstrip('/')).write_text(ADMIN_STYLES, encoding='utf-8')


if __name__ == '__main__':
    import sys
    build(sys.argv[1])

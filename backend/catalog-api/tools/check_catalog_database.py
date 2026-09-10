"""Exercise the changed catalog transaction and read models on the disposable CI DB."""
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import urlparse
from terento_catalog.catalog import build_catalog
from terento_catalog.config import Settings
from terento_catalog.db import Database
from terento_catalog.provider_catalog import CatalogArtifact, CatalogPackage, ProviderSnapshot, OPENTOPO_MAP

settings = Settings.from_env()
assert urlparse(settings.database_url).path == '/terento_ci', 'Requires disposable terento_ci database'
database = Database(settings.database_url)
now = datetime.now(timezone.utc)
main = CatalogArtifact('opentopomap-andorra-main', 'main', 'https://garmin.opentopomap.org/europe/andorra/otm-andorra.zip', 100, 200, None, 'application/zip', True, 'VALIDATED')
contour = replace(main, id='opentopomap-andorra-contours', kind='contours', source_url='https://garmin.opentopomap.org/europe/andorra/otm-andorra-contours.zip', required=False, size_bytes=30, install_size_bytes=40, source_proof={'sourceIdentity':'opentopomap:andorra:contours','revision':'a'*64})
package = CatalogPackage('opentopomap-andorra','opentopomap','andorra','ANDORRA','OpenTopoMap Andorra','ANDORRA','Andorra','2026-05','2026-05','2026-05',now,now,'AVAILABLE',('AD',),'country',(),('main','contours'),(main,contour))
for release in ('2026-05','2026-06'):
    database.upsert_provider_snapshot(ProviderSnapshot(OPENTOPO_MAP,(replace(package,release=release),),now))
rows, updated = database.catalog_snapshot()
public = build_catalog(rows,updated,contour_mode='public')
item = next(p for p in public['providers'] if p['id']=='opentopomap')['maps'][0]
assert item['sourceURL'] == main.source_url and item['downloadSizeBytes'] == 100
assert len(item['artifacts']) == 2 and item['artifacts'][1]['sourceProof'] == contour.source_proof
assert database.admin_overview_map_snapshot(now, time_zone='Europe/Vilnius') is not None
assert database.provider_detail('opentopomap') is not None
assert [row['source_url'] for row in database.provider_download_urls('opentopomap')] == [main.source_url]
print('PASS: PostgreSQL snapshot update, source proof, main compatibility fields and Overview SQL')

# Synthetic results only in the explicitly guarded disposable CI database.
# Reproduce the retained mixed custom + catalog session without production data.
from uuid import uuid4
from datetime import timedelta
operation_id = uuid4()
with database.connection() as connection:
    device = connection.execute('SELECT id FROM device_model ORDER BY id LIMIT 1').fetchone()['id']
    for index, provider in enumerate(('custom', 'opentopomap')):
        connection.execute('''
            INSERT INTO compatibility_evidence_event
                (event_id, operation_id, map_result_index, selected_map_count,
                 occurred_at, model, compatibility_identity, canonical_device_model_id,
                 usb_vendor_id, usb_product_id, transport, provider, region,
                 map_release, terento_version, macos_version, phase_outcome,
                 automatic_finishing_result, write_started)
            VALUES (%s,%s,%s,2,%s,'CI watch','CI watch',%s,2334,1,'MTP',%s,%s,
                    '2026-05','1.0.0','26','SUCCEEDED','VERIFIED',true)
        ''', (uuid4(), operation_id, index, now, device, provider,
              'custom' if provider == 'custom' else 'ANDORRA'))
    connection.execute('''
        INSERT INTO map_download_event
            (event_id,operation_id,provider_id,map_package_id,region,event_type,outcome,occurred_at)
        VALUES (%s,%s,'opentopomap','opentopomap-andorra','ANDORRA',
                'INSTALL_SUCCEEDED','SUCCEEDED',%s)
    ''', (uuid4(), operation_id, now))
since = now - timedelta(seconds=1)
overview = database.admin_overview_map_snapshot(since, time_zone='Europe/Vilnius')
assert overview['completedInstallCount'] == 2, overview
assert sum(row['success_count'] for row in overview['trend']) == 1
assert sum(row['custom_count'] for row in overview['trend']) == 1
assert database.admin_overview_snapshot(since)['successfulInstallCount'] == 2
statistics = database.map_statistics({})
assert sum(row['operation_count'] for row in statistics if row['event_type'] == 'INSTALL_SUCCEEDED') == 1
devices, _ = database.admin_device_snapshot()
watch = next(row for row in devices if row['device_id'] == device)
assert watch['attempted_install_count'] == 2 and watch['successful_install_count'] == 2, watch
assert watch['compatibility_successful_install_count'] == 2, watch
print('PASS: mixed session = two shared compatibility successes, one catalog success, one custom chart result')

with database.connection() as connection:
    connection.execute("UPDATE compatibility_evidence_event SET phase_outcome='FAILED', automatic_finishing_result='FAILED' WHERE operation_id=%s AND provider='custom'", (operation_id,))
overview = database.admin_overview_map_snapshot(since)
assert (overview['completedInstallCount'], overview['failedInstallCount']) == (1, 1)
assert sum(row['failed_count'] for row in overview['trend']) == 1
assert sum(row['custom_count'] for row in overview['trend']) == 0
devices, _ = database.admin_device_snapshot()
watch = next(row for row in devices if row['device_id'] == device)
assert (watch['attempted_install_count'], watch['successful_install_count'], watch['failed_install_count']) == (2, 1, 1)
with database.connection() as connection:
    connection.execute("UPDATE compatibility_evidence_event SET is_local_test=true WHERE operation_id=%s AND provider='custom'", (operation_id,))
    connection.execute("UPDATE map_download_event SET is_local_test=true WHERE operation_id=%s", (operation_id,))
    connection.execute("UPDATE compatibility_evidence_event SET selected_map_count=3 WHERE operation_id=%s", (operation_id,))
overview = database.admin_overview_map_snapshot(since)
assert (overview['completedInstallCount'], overview['failedInstallCount']) == (1, 0)
statistics = database.map_statistics({})
assert sum(row['operation_count'] for row in statistics if row['event_type'] == 'INSTALL_SUCCEEDED') == 1
print('PASS: partial failure, local exclusion and missing sibling retain independent result counts')
with database.connection() as connection:
    connection.execute("UPDATE compatibility_evidence_event SET phase_outcome='FAILED', automatic_finishing_result='FAILED' WHERE operation_id=%s AND provider='opentopomap'", (operation_id,))
statistics = database.map_statistics({'eventType': 'INSTALL_FAILED'})
assert sum(row['operation_count'] for row in statistics) == 1, statistics
assert database.map_statistics({'eventType': 'INSTALL_SUCCEEDED'}) == []
print('PASS: catalog failure fallback respects outcome filters')

# Future results arrive individually; neither selected_map_count nor the UI's
# bounded diagnostic history may cap the public/admin counters.
future_session = uuid4()
with database.connection() as connection:
    connection.execute("INSERT INTO compatibility_model_review (model,identity_key,review_status,public_statistics_enabled) VALUES ('CI watch','CI watch','APPROVED',true)")
for successes in range(1, 6):
    event_id = uuid4()
    with database.connection() as connection:
        for delivery in range(2):
            connection.execute('''
                INSERT INTO compatibility_evidence_event
                    (event_id,operation_id,map_result_index,selected_map_count,
                     occurred_at,model,compatibility_identity,canonical_device_model_id,
                     usb_vendor_id,usb_product_id,transport,provider,region,map_release,
                     terento_version,macos_version,phase_outcome,automatic_finishing_result,write_started)
                VALUES (%s,%s,%s,5,%s,'CI watch','CI watch',%s,2334,1,'MTP',
                        'custom','custom','custom','1.0.0','26','SUCCEEDED','VERIFIED',true)
                ON CONFLICT (event_id) DO NOTHING
            ''', (event_id, future_session, successes - 1, now, device))
    public = next(row for row in database.public_compatibility_statistics(100) if row['canonical_device_model_id'] == device)
    admin = next(row for row in database.compatibility_statistics() if row['canonical_device_model_id'] == device)
    devices, _ = database.admin_device_snapshot()
    watch = next(row for row in devices if row['device_id'] == device)
    for row in (public, admin, watch):
        assert row['successful_install_count'] == successes, row
        assert row['attempted_install_count'] == successes + 1, row
        assert row['failed_install_count'] == 1, row
    assert public['calculated_status'] == ('TESTED' if successes < 3 else 'SUPPORTED' if successes < 5 else 'VERIFIED'), public
print('PASS: future per-map results promote all models at 3/5; public/admin/watch parity and replay idempotency')
with database.connection() as connection:
    connection.execute("UPDATE compatibility_evidence_event SET automatic_finishing_result='NOT_REACHED' WHERE event_id=%s", (event_id,))
public = next(row for row in database.public_compatibility_statistics(100) if row['canonical_device_model_id'] == device)
assert public['successful_install_count'] == 4 and public['calculated_status'] == 'SUPPORTED', public
from terento_catalog.migrate import apply_migrations
assert apply_migrations(database) == []
print('PASS: unverified success cannot promote compatibility; migration replay is idempotent')

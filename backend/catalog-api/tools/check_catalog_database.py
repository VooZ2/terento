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

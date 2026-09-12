"""Real PostgreSQL contract check on the explicitly disposable terento_ci DB.

Inputs are recorded provider metadata. Events are synthetic test events and
must never be sent to production or represented as hardware evidence.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from terento_catalog.config import Settings
from terento_catalog.db import Database
from terento_catalog.http_api import CatalogService
from terento_catalog.provider_catalog import BBBIKE, CatalogArtifact, CatalogPackage, ProviderSnapshot

settings=Settings.from_env()
assert urlparse(settings.database_url).path=='/terento_ci', 'Requires disposable terento_ci database'
database=Database(settings.database_url);service=CatalogService(database)
root=Path(__file__).resolve().parents[3]
fixture=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/bbbike/representative-catalog.json').read_text())
now=datetime.now(timezone.utc)
packages=[]
for p in fixture['providers'][0]['maps']:
    a=p['artifacts'][0];proof=a['sourceProof'];created=datetime.fromisoformat(proof['generatedAt'])
    packages.append(CatalogPackage(id=p['id'],provider_id='bbbike',provider_region_id=p['providerRegionId'],canonical_region_id=p['canonicalRegionId'],name=p['name'],region=p['region'],country=p['country'],release=p['release'],release_id=proof['revision'],version_label=p['release'],generated_at=created,source_updated_at=created,availability='AVAILABLE',country_codes=tuple(p['countryCodes']),region_kind=p['regionKind'],tags=(),capabilities=('main',),map_type=p['mapType'],geographic_region_id=p['geographicRegionId'],artifacts=(CatalogArtifact(id=a['id'],kind='main',source_url=a['sourceUrl'],size_bytes=a['downloadSizeBytes'],install_size_bytes=a['installSizeBytes'],checksum_sha256=None,content_type='application/zip',required=True,validation_status='VALIDATED',install_payload_path=proof['payloadPath'],source_updated_at=created,source_proof=proof),)))
database.upsert_provider_snapshot(ProviderSnapshot(BBBIKE,tuple(packages),now))
# Upsert is idempotent, including new geography columns and PAUSED default.
database.upsert_provider_snapshot(ProviderSnapshot(BBBIKE,tuple(packages),now))
for method,expected in ((service.catalog_response,False),(service.catalog_v3_response,False),(service.catalog_v4_response,True)):
    providers=json.loads(method()[0])['providers']
    assert any(p['id']=='bbbike' for p in providers)==expected
provider=next(p for p in json.loads(service.catalog_v4_response()[0])['providers'] if p['id']=='bbbike')
assert provider['status']=='PAUSED' and len(provider['maps'])==6
lithuania=[p for p in packages if p.geographic_region_id=='LITHUANIA']
event_base=json.loads((root/'contracts/fixtures/map-event.valid.json').read_text())
evidence_base=json.loads((root/'contracts/fixtures/compatibility-event.valid.json').read_text())
for p in lithuania:
    operation=str(uuid4())
    event={**event_base,'id':str(uuid4()),'operationId':operation,'timestamp':now.isoformat(),'providerId':'bbbike','mapId':p.id,'region':p.region,'releaseLabel':'1.0.0-beta.12-local'}
    assert service.receive_map_event(json.dumps(event).encode())[1]
    assert not service.receive_map_event(json.dumps(event).encode())[1]
    evidence={**evidence_base,'id':str(uuid4()),'operationId':operation,'timestamp':now.isoformat(),'provider':'bbbike','region':p.region,'releaseLabel':'1.0.0-beta.12-local'}
    assert service.receive_compatibility_event(json.dumps(evidence).encode())
with database.connection() as connection:
    rows=connection.execute("SELECT e.map_package_id,e.is_local_test,p.geographic_region_id,p.map_type FROM map_download_event e JOIN map_package p ON p.id=e.map_package_id WHERE e.provider_id='bbbike'").fetchall()
    assert len(rows)==2 and all(r['is_local_test'] and r['geographic_region_id']=='LITHUANIA' for r in rows)
assert not database.map_statistics({'provider':'bbbike'}), 'Local events leaked into production statistics'
# Production classification is tested only inside this disposable database.
for p in lithuania:
    event={**event_base,'id':str(uuid4()),'operationId':str(uuid4()),'timestamp':now.isoformat(),'providerId':'bbbike','mapId':p.id,'region':p.region,'releaseLabel':'1.0.0-beta.12'}
    assert service.receive_map_event(json.dumps(event).encode())[1]
rows=database.map_statistics({'provider':'bbbike'})
assert len(rows)==2 and {r['map_type'] for r in rows}=={'bbbike-latin1','ontrail-latin1'}
assert all(r['canonical_region_id']=='LITHUANIA' and r['region_country']=='LT' and r['operation_count']==1 for r in rows)
service_rows=service.map_statistics({'provider':'bbbike'})
assert service_rows, 'Admin projection failed'
# A diagnostics-only exact variant resolves its own type; untyped region never guesses.
for region in (lithuania[1].region,'LITHUANIA'):
    evidence={**evidence_base,'id':str(uuid4()),'operationId':str(uuid4()),'timestamp':now.isoformat(),'provider':'bbbike','region':region,'releaseLabel':'1.0.0-beta.12'}
    assert service.receive_compatibility_event(json.dumps(evidence).encode())
rows=database.map_statistics({'provider':'bbbike'})
untyped=next(r for r in rows if r['region']=='LITHUANIA')
assert untyped['map_package_id'] is None and untyped['map_type'] is None
assert untyped['canonical_region_id']=='LITHUANIA' and untyped['region_country']=='LT'
print('PASS: BBBike PostgreSQL migrations, idempotent actual metadata seed, closed catalog projections, both local telemetry streams, geographic/type statistics, ambiguous fallback')

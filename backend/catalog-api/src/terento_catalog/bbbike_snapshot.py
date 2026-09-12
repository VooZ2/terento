"""Validate/import an inspected BBBike metadata snapshot without activation."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from .bbbike import ARTIFACT_ROOT, EXAMPLE_ROOT, EXAMPLE_REGIONS, MAP_TYPES, region_path, source_url
from .bbbike_geography import geography
from .provider_catalog import BBBIKE, CatalogArtifact, CatalogPackage, ProviderCollectionError, ProviderSnapshot


def load_snapshot(path: Path) -> ProviderSnapshot:
    if path.stat().st_size>16*1024*1024:
        raise ProviderCollectionError('BBBike metadata snapshot exceeds bound')
    data=json.loads(path.read_text())
    if data['definition']['id']!='bbbike':
        raise ProviderCollectionError('Snapshot is not BBBike')
    packages=[]; seen=set()
    for item in data['packages']:
        source=region_path(item['provider_region_id']); map_type=item['map_type']
        if map_type not in MAP_TYPES: raise ProviderCollectionError('Unreviewed BBBike type')
        token=source.replace('/','-')+'-'+map_type
        identity=token.upper();normalized=re.sub('[^A-Z0-9]','',identity)
        if normalized in seen or len(identity)>140:raise ProviderCollectionError('Duplicate/oversized BBBike identity')
        seen.add(normalized)
        if (item['id']!='bbbike-'+token or item['provider_id']!='bbbike'
                or item['region']!=identity or item['canonical_region_id']!=identity):
            raise ProviderCollectionError('BBBike snapshot lifecycle identity mismatch')
        name,geo,codes,kind=geography(source)
        if (item['name'],item['geographic_region_id'],tuple(item['country_codes']),item['region_kind'])!=(name,geo,codes,kind):
            raise ProviderCollectionError('BBBike snapshot geography differs from reviewed mapper')
        if len(item['artifacts'])!=1:raise ProviderCollectionError('BBBike requires exactly one main artifact')
        a=dict(item['artifacts'][0]);proof=a.get('source_proof')
        expected=f'{ARTIFACT_ROOT}{source}/{source.split("/")[-1]}.osm.garmin-{map_type}.zip'
        disabled=item['availability']=='UNAVAILABLE'
        example=f'{EXAMPLE_ROOT}{source}/{source.split("/")[-1]}.osm.garmin-{map_type}.zip'
        if a['source_url']!=expected and not (source in EXAMPLE_REGIONS and a['source_url']==example):
            raise ProviderCollectionError('BBBike snapshot source URL is not reviewed')
        if a['id']!=item['id']+'-main' or a['kind']!='main' or not a['required']:
            raise ProviderCollectionError('BBBike snapshot artifact identity mismatch')
        if disabled:
            if a['validation_status']!='UNAVAILABLE' or proof or a['install_size_bytes'] is not None:
                raise ProviderCollectionError('Unavailable BBBike artifact has usable validation')
        else:
            if item['availability']!='AVAILABLE' or a['validation_status']!='VALIDATED' or not proof:
                raise ProviderCollectionError('BBBike snapshot lacks validated source evidence')
            source_url(a['source_url'],artifact=True)
            payload=f'{source.split("/")[-1]}-garmin-{map_type}/gmapsupp.img'
            if (a['size_bytes']<=0 or not a['install_size_bytes'] or a['install_size_bytes']<512
                    or proof.get('payloadPath')!=payload or a.get('install_payload_path')!=payload
                    or not isinstance(proof.get('etag'),str) or not proof['etag'] or proof['etag'].startswith('W/')
                    or not proof.get('lastModified')):
                raise ProviderCollectionError('BBBike source bounds/path/HTTP identity missing')
            if not proof.get('headerIdentityValidated'):
                raise ProviderCollectionError('BBBike snapshot lacks exact IMG title evidence')
            if (proof['sourceURL']!=a['source_url'] or proof['sourceIdentity']!=f'bbbike:{source}:{map_type}'
                    or proof['mapType']!=map_type or proof['sourceRegion']!=source
                    or proof['downloadSizeBytes']!=a['size_bytes'] or proof['installSizeBytes']!=a['install_size_bytes']
                    or not re.fullmatch('[a-f0-9]{32}',proof['payloadMD5'])):
                raise ProviderCollectionError('BBBike snapshot source proof mismatch')
            revision=hashlib.sha256(json.dumps({k:v for k,v in proof.items() if k!='revision'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if proof['revision']!=revision:raise ProviderCollectionError('BBBike source proof revision mismatch')
            if item['release']!=datetime.fromisoformat(proof['generatedAt']).date().isoformat():
                raise ProviderCollectionError('BBBike release differs from README creation date')
        for field in ('source_updated_at',):
            a[field]=datetime.fromisoformat(a[field]) if a.get(field) else None
        item=dict(item); item['artifacts']=(CatalogArtifact(**a),)
        for field in ('country_codes','tags','capabilities'):item[field]=tuple(item[field])
        for field in ('generated_at','source_updated_at'):
            item[field]=datetime.fromisoformat(item[field]) if item.get(field) else None
        packages.append(CatalogPackage(**item))
    if not packages:raise ProviderCollectionError('BBBike metadata snapshot is empty')
    return ProviderSnapshot(BBBIKE,tuple(packages),datetime.fromisoformat(data['collected_at']))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('--apply',action='store_true',help='Persist metadata to configured database, retaining PAUSED state')
    parser.add_argument('--expected-packages',type=int)
    args=parser.parse_args();snapshot=load_snapshot(args.snapshot)
    if args.expected_packages is not None and len(snapshot.packages)!=args.expected_packages:
        raise ProviderCollectionError('BBBike snapshot count differs from reviewed expected count')
    if args.apply:
        from .config import Settings
        from .db import Database
        from .collect import snapshot_release_evidence
        database=Database(Settings.from_env().database_url)
        with database.connection() as connection:
            state=connection.execute("SELECT status FROM map_provider WHERE id='bbbike'").fetchone()
            if state and state['status']!='PAUSED':
                raise ProviderCollectionError('BBBike metadata candidate import requires PAUSED provider')
        database.ensure_provider_definition(BBBIKE)
        run=database.begin_catalog_collection('bbbike')
        database.upsert_provider_snapshot(snapshot)
        release,fingerprint=snapshot_release_evidence(snapshot)
        database.finish_catalog_collection(run,status='SUCCEEDED',package_count=len(snapshot.packages),
            artifact_count=len(snapshot.packages),latest_release=release,catalog_fingerprint=fingerprint)
    print(json.dumps({'provider':'bbbike','status':'PAUSED','packages':len(snapshot.packages),
        'available':sum(p.availability=='AVAILABLE' for p in snapshot.packages),'applied':args.apply}))

if __name__=='__main__':main()

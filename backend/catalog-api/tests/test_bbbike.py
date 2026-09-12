"""BBBike protocol tests; synthetic ZIPs are adversarial fixtures, not hardware evidence."""
import io
import json
from pathlib import Path
import stat
import unittest
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from terento_catalog.bbbike import (ARTIFACT_ROOT, ROOT, BBBikeProviderAdapter, BBBikeMeasurement,
    MAP_TYPES, directory_contents, inspect_bbbike, region_path, source_url)
from terento_catalog.bbbike_geography import geography
from terento_catalog.collectors.freizeitkarte.range_zip import RangeResponse
from terento_catalog.http_api import CatalogService
from terento_catalog.provider_catalog import BBBIKE, ProviderCollectionError

PATH='europe/andorra'
TYPE='bbbike-latin1'
URL=ARTIFACT_ROOT+PATH+'/andorra.osm.garmin-'+TYPE+'.zip'
PREFIX='andorra-garmin-bbbike-latin1/'
README='This Garmin map was created on: Wed  9 Sep 00:15:05 UTC 2026\nGarmin map style: bbbike (latin1)\nName of area: europe/andorra\n'

class MemoryFetcher:
    def __init__(self, *, readme=README, extra=None, encrypted=False):
        img=bytearray(2048); img[16:22]=b'DSKIMG'; img[65:71]=b'GARMIN'
        title=b'europe/andorra bbbike/latin1 BBBike.org 09-Sep-2026'[:50].ljust(50,b' ')
        img[0x49:0x5D]=title[:20]; img[0x65:0x83]=title[20:]
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr(PREFIX+'gmapsupp.img',img)
            z.writestr(PREFIX+'README.txt',readme)
            z.writestr(PREFIX+'CHECKSUM.txt','a'*32+'  gmapsupp.img\n')
            if extra: z.writestr(*extra)
        self.body=buffer.getvalue(); self.bytes_read=0
    def metadata(self,url): return len(self.body),'"stable"','Wed, 09 Sep 2026 00:15:08 GMT'
    def fetch_range(self,url,start,end):
        body=self.body[start:end+1]; self.bytes_read+=len(body)
        return RangeResponse(206,start,end,len(self.body),body,url)

class BBBikeTests(unittest.TestCase):
    def test_reviewed_url_boundaries(self):
        self.assertEqual(source_url(URL,artifact=True),URL)
        for bad in (URL.replace('https:','http:'), URL+'?x=1',URL.replace('andorra.osm','france.osm'),
                    URL.replace('latin1','utf8'), URL.replace('/europe/andorra/','/russia/andorra/'),
                    URL.replace('/region/','/'), URL.replace('data.bbbike.org','data.bbbike.org.evil.test')):
            with self.subTest(url=bad),self.assertRaises(ProviderCollectionError):source_url(bad,artifact=True)
        for bad in ('russia','europe/russia','europe/../andorra','europe%2fandorra'):
            with self.assertRaises(ProviderCollectionError):region_path(bad)

    def test_traversal_subregion_links_and_russia_before_request(self):
        children,artifacts=directory_contents('<a href="europe/">Europe</a><a href="russia/">Russia</a><a href="../">Parent</a>',ROOT)
        self.assertEqual(children,[ROOT+'europe/'])
        children,_=directory_contents('<a class="sub_region_link" href="baden-wuerttemberg">Subregion</a><a href="../../russia/">Russia</a>',ROOT+'europe/germany/')
        self.assertEqual(children,[ROOT+'europe/germany/baden-wuerttemberg/'])
        _,artifacts=directory_contents(f'<a href="{URL}">BBBike</a><a href="{URL.replace("latin1","utf8")}">UTF8</a>',ROOT+PATH+'/')
        self.assertEqual(artifacts,{TYPE:URL})

    def test_readme_zip_and_bounded_header_identity(self):
        fetcher=MemoryFetcher()
        result=inspect_bbbike(URL,PATH,TYPE,fetcher=fetcher)
        self.assertEqual(result.generated_at,datetime(2026,9,9,0,15,5,tzinfo=timezone.utc))
        self.assertEqual(result.install_size_bytes,2048)
        self.assertEqual(result.source_proof['payloadMD5'],'a'*32)
        self.assertEqual(result.source_proof['sourceIdentity'],'bbbike:europe/andorra:bbbike-latin1')
        self.assertLess(fetcher.bytes_read,8*1024*1024)
        for readme in (README.replace('bbbike (latin1)','ontrail (latin1)'),README.replace('europe/andorra','europe/france'),README+'Name of area: europe/andorra\n'):
            with self.assertRaises(ProviderCollectionError):inspect_bbbike(URL,PATH,TYPE,fetcher=MemoryFetcher(readme=readme))
        symlink=zipfile.ZipInfo(PREFIX+'link'); symlink.create_system=3;symlink.external_attr=(stat.S_IFLNK|0o777)<<16
        for extra in ((PREFIX+'../escape','x'),(PREFIX+'second.img','x'),(symlink,'gmapsupp.img')):
            with self.assertRaises(ProviderCollectionError):inspect_bbbike(URL,PATH,TYPE,fetcher=MemoryFetcher(extra=extra))

    def test_changed_source_rejected(self):
        fetcher=MemoryFetcher(); before=fetcher.metadata(URL)
        with patch.object(fetcher,'metadata',side_effect=[before,(before[0],'"changed"',before[2])]):
            with self.assertRaises(ProviderCollectionError):inspect_bbbike(URL,PATH,TYPE,fetcher=fetcher)

    def test_both_types_one_provider_distinct_lifecycle_shared_geography(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/bbbike/representative-catalog.json').read_text())
        provider=fixture['providers'][0]
        self.assertEqual(provider['id'],'bbbike'); self.assertEqual(provider['status'],'PAUSED')
        packages=provider['maps'];self.assertEqual(len(packages),6)
        self.assertEqual({p['mapType'] for p in packages},set(MAP_TYPES))
        lithuania=[p for p in packages if p['geographicRegionId']=='LITHUANIA']
        self.assertEqual(len(lithuania),2)
        self.assertEqual({p['name'] for p in lithuania},{'Lithuania'})
        self.assertEqual(len({p['canonicalRegionId'] for p in lithuania}),2)
        self.assertTrue(all(p['countryCodes']==['LT'] for p in lithuania))
        for p in packages:
            proof=p['artifacts'][0]['sourceProof']
            self.assertEqual(proof['mapType'],p['mapType'])
            self.assertEqual(proof['sourceRegion'],p['providerRegionId'])
            self.assertEqual(proof['installSizeBytes'],p['installSizeBytes'])
            self.assertRegex(proof['payloadMD5'],r'^[a-f0-9]{32}$')

    def test_all_released_provider_projections_closed(self):
        now=datetime.now(timezone.utc)
        rows=[dict(provider_id=p,provider_name=p,provider_website='https://example.test',provider_attribution='',provider_license_url='https://example.test/license',provider_license_information='',version_year=None) for p in ('freizeitkarte','opentopomap','maprando','bbbike','unreviewed')]
        service=CatalogService(SimpleNamespace(catalog_snapshot=lambda:(rows,now)))
        for method,expected in ((service.catalog_response,{'freizeitkarte','opentopomap'}),(service.catalog_v3_response,{'freizeitkarte','opentopomap','maprando'}),(service.catalog_v4_response,{'freizeitkarte','opentopomap','maprando','bbbike'})):
            data=json.loads(method()[0]);self.assertEqual({p['id'] for p in data['providers']},expected)

    def test_exact_example_aliases_are_not_a_namespace_allowlist(self):
        for path in ('asia/cambodia','asia/jordan','europe/luxembourg'):
            for kind in MAP_TYPES:
                url=f'https://data.bbbike.org/osm/garmin/example/{path}/{path.split("/")[-1]}.osm.garmin-{kind}.zip'
                self.assertEqual(source_url(url,artifact=True),url)
        with self.assertRaises(ProviderCollectionError):
            source_url(URL.replace('/region/','/example/'),artifact=True)

    def test_proof_cache_reuses_only_exact_validated_http_identity(self):
        measured=inspect_bbbike(URL,PATH,TYPE,fetcher=MemoryFetcher())
        fetcher=MemoryFetcher()
        fetcher.inspect=lambda *_:self.fail('Unchanged validated source was inspected again')
        adapter=BBBikeProviderAdapter(fetcher=fetcher)
        adapter.set_previous_rows([{'provider_id':'bbbike','artifact_source_url':URL,
            'artifact_validation_status':'VALIDATED','artifact_source_proof':measured.source_proof}])
        reused,error=adapter._measure((PATH,TYPE,URL))
        self.assertIsNone(error);self.assertEqual(reused.source_proof,measured.source_proof)
        with patch.object(fetcher,'metadata',return_value=(1,'"changed"','changed')):
            fetcher.inspect=lambda *_:measured
            fresh,error=adapter._measure((PATH,TYPE,URL))
            self.assertIsNone(error);self.assertEqual(fresh,measured)

    def test_one_broken_source_keeps_known_release_unavailable(self):
        class Broken:
            def inspect(self,*_):raise ValueError('invalid IMG identity')
        adapter=BBBikeProviderAdapter(fetcher=Broken())
        adapter.source_dates[URL]=datetime(2026,9,9,tzinfo=timezone.utc)
        adapter.discover=lambda:{PATH:{TYPE:URL}}
        snapshot=adapter.collect();self.assertEqual(len(snapshot.packages),1)
        package=snapshot.packages[0]
        self.assertEqual(package.availability,'UNAVAILABLE')
        self.assertEqual(package.release,'2026-09-09')
        self.assertEqual(package.artifacts[0].validation_status,'UNAVAILABLE')
        self.assertIsNone(package.artifacts[0].source_proof)
        self.assertIsNone(package.artifacts[0].install_size_bytes)

    def test_reviewed_geography_retains_unknown_future_scope(self):
        self.assertEqual(geography('europe/lithuania'),('Lithuania','LITHUANIA',('LT',),'country'))
        self.assertEqual(geography('north-america/us/alabama')[2],('US',))
        self.assertEqual(geography('asia/indonesia/java')[2],('ID',))
        self.assertEqual(geography('new-continent/new-region')[2],())

if __name__=='__main__':unittest.main()

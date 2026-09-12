"""Ready BBBike Garmin latin1 regions; bounded original-source metadata only.

One provider, two independent map types. No city extract service, Russia tree,
other Garmin style, binary mirroring, or archive script execution.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
from urllib.parse import urljoin, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError
from threading import Event
import zipfile

from .collectors.freizeitkarte.range_zip import RangeResponse
from .provider_catalog import BBBIKE, CatalogArtifact, CatalogPackage, ProviderCollectionError, ProviderSnapshot

ROOT = "https://data.bbbike.org/osm/region/"
ARTIFACT_ROOT = "https://data.bbbike.org/osm/garmin/region/"
EXAMPLE_ROOT = "https://data.bbbike.org/osm/garmin/example/"
EXAMPLE_REGIONS = frozenset({"asia/cambodia", "asia/jordan", "europe/luxembourg"})
MAP_TYPES = ("bbbike-latin1", "ontrail-latin1")
MAX_INDEX_BYTES = 1024 * 1024
MAX_DIRECTORIES = 4096
MAX_DEPTH = 8
MAX_METADATA_BYTES = 8 * 1024 * 1024


def region_path(value: str) -> str:
    if (not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9-]+)*", value)
            or len(value) > 140 or len(value.split('/')) > MAX_DEPTH
            or 'russia' in value.split('/')):
        raise ProviderCollectionError("BBBike region outside reviewed scope")
    return value


def source_url(value: str, *, artifact: bool = False) -> str:
    root = ARTIFACT_ROOT if artifact else ROOT
    example = artifact and value.startswith(EXAMPLE_ROOT)
    if example:
        root = EXAMPLE_ROOT
    if not value.startswith(root):
        raise ProviderCollectionError("BBBike source outside reviewed HTTPS path")
    parsed = urlparse(value)
    if parsed.query or parsed.fragment or parsed.username or parsed.port:
        raise ProviderCollectionError("BBBike source has unreviewed URL components")
    suffix = value[len(root):]
    if artifact:
        match = re.fullmatch(r"(.+)/([^/]+)\.osm\.garmin-(bbbike-latin1|ontrail-latin1)\.zip", suffix)
        if not match or match[1].split('/')[-1] != match[2]:
            raise ProviderCollectionError("BBBike source filename does not match region/style")
        region_path(match[1])
        if example and match[1] not in EXAMPLE_REGIONS:
            raise ProviderCollectionError("BBBike example source has no reviewed region alias")
    elif suffix:
        if not suffix.endswith('/'):
            raise ProviderCollectionError("BBBike directory must end with slash")
        region_path(suffix[:-1])
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderCollectionError("BBBike source redirect is not reviewed")


class BBBikeFetcher:
    def __init__(self):
        self.opener = build_opener(_NoRedirect())
        self.rate_limited = Event()

    def _open(self, url, *, method='GET', headers=None):
        source_url(url, artifact=url.startswith((ARTIFACT_ROOT, EXAMPLE_ROOT)))
        if self.rate_limited.is_set():
            raise ProviderCollectionError('BBBike source rate limited; collection makes no further requests')
        try:
            return self.opener.open(Request(url, method=method, headers={
                'User-Agent': 'TerentoCatalog/0.1 (+https://terento.app)', **(headers or {})}), timeout=30)
        except HTTPError as error:
            if error.code == 429:
                self.rate_limited.set()
            raise

    def fetch_text(self, url):
        source_url(url)
        with self._open(url) as response:
            if response.status != 200 or response.geturl() != url:
                raise ProviderCollectionError('BBBike directory changed source')
            body = response.read(MAX_INDEX_BYTES + 1)
        if len(body) > MAX_INDEX_BYTES:
            raise ProviderCollectionError('BBBike index exceeded metadata bound')
        return body.decode('utf-8', errors='strict')

    def metadata(self, url):
        source_url(url, artifact=True)
        with self._open(url, method='HEAD') as response:
            size = int(response.headers.get('Content-Length', '0'))
            etag, modified = response.headers.get('ETag'), response.headers.get('Last-Modified')
            if response.status != 200 or response.geturl() != url or size <= 0 or not etag or etag.startswith('W/') or not modified:
                raise ProviderCollectionError('BBBike source lacks stable HTTP metadata')
            return size, etag, modified

    def fetch_range(self, url, start, end):
        if start < 0 or end < start or end-start+1 > MAX_METADATA_BYTES:
            raise ProviderCollectionError('Invalid BBBike metadata range')
        with self._open(url, headers={'Range': f'bytes={start}-{end}'}) as response:
            if response.status != 206 or response.geturl() != url:
                raise ProviderCollectionError('BBBike metadata requires exact HTTP206')
            match = re.fullmatch(r'bytes ([0-9]+)-([0-9]+)/([0-9]+)', response.headers.get('Content-Range', ''))
            if not match or int(match[1]) != start or int(match[2]) != end or int(match[3]) <= end:
                raise ProviderCollectionError('BBBike source returned invalid Content-Range')
            body = response.read(end-start+2)
            if len(body) != end-start+1:
                raise ProviderCollectionError('BBBike source returned incomplete range')
            return RangeResponse(206, start, end, int(match[3]), body, url)

    def inspect(self, url, path, map_type):
        return inspect_bbbike(url, path, map_type, fetcher=self)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append((attrs['href'], attrs.get('class', '').split(), attrs.get('title','')))


def directory_contents(html, url):
    """Only immediate child directories and explicit subregion links are traversed."""
    source_url(url)
    parser=_Links(); parser.feed(html)
    directories, artifacts = set(), {}
    current = url[len(ROOT):].rstrip('/')
    for href, classes, _ in parser.links:
        if href.endswith('/') or 'sub_region_link' in classes:
            candidate=urljoin(url, href.rstrip('/')+'/')
            if not candidate.startswith(url) or candidate == url:
                continue
            relative=candidate[len(url):].rstrip('/')
            if '/' in relative:
                continue
            try: source_url(candidate)
            except ProviderCollectionError: continue
            directories.add(candidate)
        candidate=urljoin(url, href)
        if current in EXAMPLE_REGIONS:
            for map_type in MAP_TYPES:
                if candidate == f'{EXAMPLE_ROOT}{current}/{current.split("/")[-1]}.osm.garmin-{map_type}.zip':
                    artifacts[map_type]=candidate  # Six exact aliases reviewed against ready-region footprints.
        if candidate.startswith(ARTIFACT_ROOT):
            try: source_url(candidate, artifact=True)
            except ProviderCollectionError: continue
            for map_type in MAP_TYPES:
                if current and candidate == f'{ARTIFACT_ROOT}{current}/{current.split("/")[-1]}.osm.garmin-{map_type}.zip':
                    artifacts[map_type]=candidate
    return sorted(directories), artifacts


class _RemoteZip(io.RawIOBase):
    def __init__(self, url, size, fetcher):
        self.url, self.size, self.fetcher = url, size, fetcher
        self.position=0; self.remaining=MAX_METADATA_BYTES
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        position=offset+(self.position if whence==1 else self.size if whence==2 else 0)
        if not 0 <= position <= self.size: raise ProviderCollectionError('ZIP seek outside archive')
        self.position=position; return position
    def read(self, size=-1):
        size=min(self.size-self.position, size if size>=0 else self.size)
        if size>self.remaining: raise ProviderCollectionError('BBBike metadata budget exceeded')
        if not size: return b''
        response=self.fetcher.fetch_range(self.url,self.position,self.position+size-1)
        if response.url!=self.url or response.total_size!=self.size or len(response.body)!=size:
            raise ProviderCollectionError('BBBike source changed during inspection')
        self.position+=size; self.remaining-=size
        return response.body


@dataclass(frozen=True)
class BBBikeMeasurement:
    download_size_bytes: int
    install_size_bytes: int | None
    payload_path: str
    generated_at: datetime
    source_proof: dict | None


def inspect_bbbike(url, path, map_type, *, fetcher=None):
    source_url(url, artifact=True); region_path(path)
    allowed_sources={f'{ARTIFACT_ROOT}{path}/{path.split("/")[-1]}.osm.garmin-{map_type}.zip'}
    if path in EXAMPLE_REGIONS:
        allowed_sources.add(f'{EXAMPLE_ROOT}{path}/{path.split("/")[-1]}.osm.garmin-{map_type}.zip')
    if map_type not in MAP_TYPES or url not in allowed_sources:
        raise ProviderCollectionError('BBBike source identity mismatch')
    fetcher=fetcher or BBBikeFetcher()
    before=fetcher.metadata(url)
    prefix=f'{path.split("/")[-1]}-garmin-{map_type}/'
    expected=prefix+'gmapsupp.img'
    with zipfile.ZipFile(_RemoteZip(url,before[0],fetcher)) as archive:
        entries=archive.infolist()
        if any(i.flag_bits & 1 or (i.create_system == 3 and stat.S_IFMT(i.external_attr >> 16) not in {0, stat.S_IFREG, stat.S_IFDIR}) for i in entries):
            raise ProviderCollectionError('BBBike ZIP contains encrypted or nonregular entries')
        names=[i.filename for i in entries]
        if len(names)!=len(set(names)) or any(n.startswith('/') or '\\' in n or '..' in PurePosixPath(n).parts or not n.startswith(prefix) for n in names):
            raise ProviderCollectionError('BBBike ZIP contains unsafe or duplicate entries')
        images=[i for i in archive.infolist() if i.filename.lower().endswith('.img')]
        if len(images)!=1 or images[0].filename!=expected or images[0].file_size<512:
            raise ProviderCollectionError('BBBike ZIP lacks exact single IMG')
        def metadata_text(name):
            info=archive.getinfo(prefix+name)
            if info.file_size>32768 or info.flag_bits&1:
                raise ProviderCollectionError('BBBike README/checksum is oversized or encrypted')
            return archive.read(info).decode('utf-8',errors='strict')
        readme=metadata_text('README.txt')
        for field in ('Garmin map style:', 'Name of area:', 'This Garmin map was created on:'):
            if sum(line.startswith(field) for line in readme.splitlines()) != 1:
                raise ProviderCollectionError('BBBike README identity fields missing or duplicated')
        style=map_type.removesuffix('-latin1')
        if not re.search(r'^Garmin map style:\s*'+re.escape(style)+r' \(latin1\)\s*$',readme,re.M) or not re.search(r'^Name of area:\s*'+re.escape(path)+r'\s*$',readme,re.M):
            raise ProviderCollectionError('BBBike README region/style differs from source')
        date=re.search(r'^This Garmin map was created on:\s*(.+)$',readme,re.M)
        if not date: raise ProviderCollectionError('BBBike README creation date missing')
        generated=datetime.strptime(' '.join(date[1].split()),'%a %d %b %H:%M:%S UTC %Y').replace(tzinfo=timezone.utc)
        checksum=re.fullmatch(r'\s*([0-9a-fA-F]{32})\s+\*?gmapsupp\.img\s*',metadata_text('CHECKSUM.txt'))
        if not checksum: raise ProviderCollectionError('BBBike payload checksum identity missing')
        with archive.open(images[0]) as image: header=image.read(512)
        if len(header)!=512 or header[0]!=0 or header[16:22]!=b'DSKIMG' or header[65:71]!=b'GARMIN':
            raise ProviderCollectionError('BBBike payload lacks unencrypted Garmin IMG header')
        description=(header[0x49:0x5D]+header[0x65:0x83]).decode('latin-1').rstrip(' \x00')
        expected_description=f'{path} {style}/latin1 BBBike.org {generated.strftime("%d-%b-%Y")}'
        if len(description)<20 or not expected_description.startswith(description):
            raise ProviderCollectionError('BBBike IMG description does not match reviewed README identity')
        install_size=images[0].file_size
    if fetcher.metadata(url)!=before: raise ProviderCollectionError('BBBike source changed during metadata inspection')
    proof={'sourceURL':url,'etag':before[1],'lastModified':before[2],
           'downloadSizeBytes':before[0],'installSizeBytes':install_size,'payloadPath':expected,
           'sourceIdentity':f'bbbike:{path}:{map_type}','mapType':map_type,'sourceRegion':path,
           'payloadMD5':checksum[1].lower(),'generatedAt':generated.isoformat(), 'headerIdentityValidated':True}
    proof['revision']=hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return BBBikeMeasurement(before[0],install_size,expected,generated,proof)


class BBBikeProviderAdapter:
    definition=BBBIKE
    def __init__(self, *, fetcher=None):
        self.fetcher=fetcher or BBBikeFetcher()
        self.previous_rows={}; self.source_dates={}
    def set_previous_rows(self, rows):
        self.previous_rows={row['artifact_source_url']:row for row in rows
            if row.get('provider_id')=='bbbike' and row.get('artifact_source_url')}
    def _measure(self, item):
        path,map_type,url=item
        previous=self.previous_rows.get(url,{})
        proof=previous.get('artifact_source_proof') or {}
        try:
            if previous.get('artifact_validation_status')=='VALIDATED' and proof.get('headerIdentityValidated') is True:
                metadata=self.fetcher.metadata(url)
                if (metadata==(proof.get('downloadSizeBytes'),proof.get('etag'),proof.get('lastModified'))
                        and proof.get('sourceIdentity')==f'bbbike:{path}:{map_type}'):
                    return BBBikeMeasurement(metadata[0],proof['installSizeBytes'],proof['payloadPath'],
                        datetime.fromisoformat(proof['generatedAt']),proof),None
            return self.fetcher.inspect(url,path,map_type),None
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            # One broken source must not erase every other valid package. Retain
            # the known source metadata as unavailable; never claim fresh validation.
            date=self.source_dates.get(url) or previous.get('package_source_updated_at')
            if isinstance(date,str): date=datetime.fromisoformat(date)
            size=previous.get('artifact_size_bytes') or 0
            if not date:
                return None,str(error)
            return BBBikeMeasurement(size,None,f'{path.split("/")[-1]}-garmin-{map_type}/gmapsupp.img',date,None),str(error)
    def discover(self):
        pending=[ROOT]; visited=set(); found={}
        while pending:
            url=pending.pop(0)
            if url in visited: continue
            visited.add(url)
            if len(visited)>MAX_DIRECTORIES: raise ProviderCollectionError('BBBike directory limit exceeded')
            html=self.fetcher.fetch_text(url)
            children, artifacts=directory_contents(html,url)
            parser=_Links(); parser.feed(html)
            for href,_,title in parser.links:
                target=urljoin(url,href)
                if target in artifacts.values() and title.startswith('last update:'):
                    try:
                        self.source_dates[target]=datetime.strptime(' '.join(title.removeprefix('last update:').split()),'%a %b %d %H:%M:%S %Y UTC').replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
            pending.extend(children)
            if artifacts: found[url[len(ROOT):].rstrip('/')]=artifacts
        if not found: raise ProviderCollectionError('BBBike ready region catalog is empty')
        return found
    def collect(self):
        from .bbbike_geography import geography
        packages=[]; identities=set()
        discovered=self.discover()
        items=[(path,t,url) for path,artifacts in sorted(discovered.items()) for t,url in sorted(artifacts.items())]
        # Four bounded metadata readers; source 429 is not retried or bypassed.
        with ThreadPoolExecutor(max_workers=4) as pool:
            measured=dict(zip(items,pool.map(self._measure,items)))
        for path, artifacts in sorted(discovered.items()):
            name, geographic, codes, kind=geography(path)
            for map_type,url in sorted(artifacts.items()):
                token=path.replace('/','-')+'-'+map_type
                identity=token.upper(); package_id='bbbike-'+token
                normalized=re.sub('[^A-Z0-9]','',identity)
                if normalized in identities or len(identity)>140:
                    raise ProviderCollectionError('BBBike lifecycle identity collision/length')
                identities.add(normalized)
                measurement,error=measured[(path,map_type,url)]
                if measurement is None:
                    continue  # No trustworthy release metadata: not a validated catalog member.
                released=measurement.generated_at.date().isoformat()
                packages.append(CatalogPackage(
                    id=package_id,provider_id='bbbike',provider_region_id=path,
                    canonical_region_id=identity,name=name,region=identity,
                    country=codes[0] if len(codes)==1 else None,release=released,release_id=(measurement.source_proof or {}).get('revision'),
                    version_label=released,generated_at=measurement.generated_at,source_updated_at=measurement.generated_at,
                    availability='UNAVAILABLE' if error else 'AVAILABLE',country_codes=codes,region_kind=kind,tags=(map_type,),capabilities=('main',),
                    map_type=map_type,geographic_region_id=geographic,
                    artifacts=(CatalogArtifact(id=package_id+'-main',kind='main',source_url=url,
                        size_bytes=measurement.download_size_bytes,install_size_bytes=measurement.install_size_bytes,
                        checksum_sha256=None,content_type='application/zip',required=True,validation_status='UNAVAILABLE' if error else 'VALIDATED',
                        install_payload_path=measurement.payload_path,source_updated_at=measurement.generated_at,
                        source_proof=measurement.source_proof),)))
        return ProviderSnapshot(self.definition,tuple(packages),datetime.now(timezone.utc))

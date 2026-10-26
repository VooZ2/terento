"""OSMapaPL protocol tests; synthetic ZIPs are adversarial fixtures, not hardware evidence."""
import io
import json
import random
import re
import unittest
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

from terento_catalog.catalog import build_catalog
from terento_catalog.collectors.freizeitkarte.range_zip import RangeResponse
from terento_catalog.http_api import CatalogService
from terento_catalog.osmapa import (FAMILY_IDS, PRODUCTS, ROOT, OSMapaFetcher, OSMapaProviderAdapter,
    conflict_group, discover, header_identity, inspect_osmapa, source_url)
from terento_catalog.provider_catalog import KNOWN_PROVIDER_DEFINITIONS, OSMAPA, ProviderCollectionError

DATE = '20261024'
STYLES = ('PODSTAWOWA', 'OGONKI', 'LIGHT', 'WARSTWICE')


def url(coverage='pl', style='OGONKI', date=DATE):
    return f'{PRODUCTS}OSMapaPL{"ext" if coverage == "plext" else ""}-{style}-{date}V2.03_IMG.zip'


def index(date=DATE, extra=''):
    links = [url(c, s, date) for c in ('pl', 'plext') for s in (*STYLES, 'SZLAKI')]
    links += [u.replace('_IMG.zip', '.exe') for u in links]
    return ''.join(f'<a href="{u[len(ROOT) - 1:]}">x</a>' for u in links) + extra


def img(title, *, date=(2026, 10, 24), fid=5, mdr=True, size=200_000):
    data = bytearray(random.Random(title).randbytes(size))
    data[:0x1000] = bytes(0x1000)
    data[0x10:0x16], data[0x41:0x47] = b'DSKIMG', b'GARMIN'
    data[0x39:0x3B] = date[0].to_bytes(2, 'little'); data[0x3B], data[0x3C] = date[1], date[2]
    raw = title.encode('latin-1')
    data[0x49:0x5D] = raw[:20].ljust(20, b' '); data[0x65:0x83] = raw[20:].ljust(30, b' ')
    data[0x400] = 1; data[0x401:0x40C] = b' ' * 11
    data[0x600] = 1; data[0x601:0x60C] = b'MAKEGMAPMPS'
    if mdr:
        data[0x800] = 1; data[0x801:0x80C] = f'{fid:08d}MDR'.encode()
    return bytes(data)


def archive(payload, *, name='gmapsupp.img', extra=None, method=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', method) as z:
        z.writestr(name, payload)
        if extra:
            z.writestr(*extra)
    return buffer.getvalue()


def fixture(source):
    coverage, style, _, _ = source_url(source)
    title = f'OSMapaPL{"ext" if coverage == "plext" else ""}-{style.upper()}'
    return archive(img(title, fid=FAMILY_IDS[style]))


class MemoryFetcher:
    def __init__(self, bodies=None, *, html=None, etags=None, status=206, errors=None, short_head=False):
        self.bodies = bodies or {}
        self.html = html if html is not None else index()
        self.etags = etags or {}
        self.status = status
        self.errors = errors or {}
        self.short_head = short_head
        self.requests = []; self.bytes_read = 0

    def fetch_index(self):
        self.requests.append(('GET', ROOT, None))
        return self.html

    def fetch_range(self, source, header):
        self.requests.append(('GET', source, header))
        if source in self.errors:
            raise self.errors[source]
        body = self.bodies.get(source) or fixture(source)
        total = len(body)
        match = re.fullmatch(r'bytes=(?:-([0-9]+)|([0-9]+)-([0-9]+))', header)
        if match[1]:
            start, end = max(0, total - int(match[1])), total - 1
        else:
            start, end = int(match[2]), min(int(match[3]), total - 1)
            if self.short_head:
                end = start + 8191  # Enough for the IMG header, shorter than requested.
        if self.status != 206:
            raise ProviderCollectionError('OSMapaPL metadata requires exact HTTP206')
        chunk = body[start:end + 1]; self.bytes_read += len(chunk)
        etag = self.etags.get((source, 'tail' if match[1] else 'head'), '"stable"')
        return RangeResponse(206, start, end, total, chunk, source), etag, 'Sat, 24 Oct 2026 19:31:35 GMT'

    def inspect(self, source, coverage, style):
        return inspect_osmapa(source, coverage, style, fetcher=self)


class OSMapaTests(unittest.TestCase):
    def test_reviewed_url_boundaries(self):
        self.assertEqual(source_url(url('plext', 'WARSTWICE'))[:2], ('plext', 'warstwice'))
        for bad in (url().replace('https:', 'http:'), url() + '?x=1', url() + '#x',
                    url().replace('las.org.pl', 'las.org.pl.evil.test'), url('pl', 'SZLAKI'),
                    url().replace('/products/', '/products/old/'), url().replace('_IMG.zip', '.exe'),
                    url(date='20261399'), url().replace('OSMapaPL-', 'OSMapaPLx-'),
                    PRODUCTS + '../products/' + url()[len(PRODUCTS):]):
            with self.subTest(url=bad), self.assertRaises(ProviderCollectionError):
                source_url(bad)

    def test_discovery_takes_newest_of_each_of_eight_and_ignores_out_of_scope(self):
        found = discover(index(extra=f'<a href="{url(date="20261004")}">old</a><a href="https://evil.test/{url()[len(ROOT):]}">x</a>'))
        self.assertEqual(len(found), 8)
        self.assertTrue(all(DATE in source for source in found.values()))
        self.assertNotIn(('pl', 'szlaki'), found)
        with self.assertRaises(ProviderCollectionError):
            discover(index().replace(url('plext', 'LIGHT')[len(ROOT) - 1:], '/products/nothing.zip'))
        with self.assertRaises(ProviderCollectionError):
            discover(index(extra=f'<a href="{url().replace("V2.03", "V2.04")}">same day</a>'))

    def test_collect_publishes_eight_paused_packages_with_bounded_requests(self):
        fetcher = MemoryFetcher()
        snapshot = OSMapaProviderAdapter(fetcher=fetcher).collect()
        self.assertEqual(snapshot.definition.default_status, 'PAUSED')
        self.assertEqual(sorted(p.id for p in snapshot.packages),
            sorted(f'osmapa-{c}-{s.lower()}' for c in ('pl', 'plext') for s in STYLES))
        # One index GET, then exactly two ranged GETs per package; no HEAD, no full download.
        self.assertEqual(len(fetcher.requests), 17)
        self.assertTrue(all(method == 'GET' for method, _, _ in fetcher.requests))
        self.assertLessEqual(fetcher.bytes_read, 16 * 64 * 1024)
        for package in snapshot.packages:
            coverage, style = package.provider_region_id.split('-')
            proof = package.artifacts[0].source_proof
            self.assertEqual(package.availability, 'AVAILABLE')
            self.assertEqual((package.map_type, package.country, package.country_codes), (style, 'PL', ('PL',)))
            self.assertEqual(package.release, '2026-10-24')
            self.assertEqual(package.version_label, '2026-10-24 V2.03')
            self.assertEqual(package.geographic_region_id, 'POLAND' if coverage == 'pl' else 'POLAND-WITH-BORDER-AREAS')
            self.assertEqual(proof['familyId'], FAMILY_IDS[style])
            self.assertEqual(proof['sourceIdentity'], f'osmapa:{coverage}:{style}')
            self.assertRegex(proof['crc32'], r'^[0-9a-f]{8}$')
            self.assertEqual(proof['installSizeBytes'], package.artifacts[0].install_size_bytes)
            self.assertEqual(package.release_id, proof['revision'])
        names = {p.id: p.name for p in snapshot.packages}
        self.assertEqual(names['osmapa-plext-ogonki'], 'Poland with border areas')
        self.assertEqual(names['osmapa-pl-warstwice'], 'Poland contour lines')

    def test_long_titles_are_stitched_from_both_header_fields(self):
        title, created, hints = header_identity(img('OSMapaPLext-PODSTAWOWA', fid=4)[:4096])
        self.assertEqual((title, created, hints), ('OSMapaPLext-PODSTAWOWA', datetime(2026, 10, 24, tzinfo=timezone.utc), {4}))
        self.assertEqual(header_identity(img('OSMapaPLext-WARSTWICE', fid=12)[:4096])[0], 'OSMapaPLext-WARSTWICE')

    def test_identity_and_archive_mismatches_are_rejected(self):
        source = url('plext', 'PODSTAWOWA')
        cases = {
            'truncated title': archive(img('OSMapaPLext-PODSTAWO', fid=4)),
            'other coverage title': archive(img('OSMapaPL-PODSTAWOWA', fid=4)),
            'other date': archive(img('OSMapaPLext-PODSTAWOWA', date=(2026, 10, 4), fid=4)),
            'invalid date': archive(img('OSMapaPLext-PODSTAWOWA', date=(2026, 13, 4), fid=4)),
            'other FID': archive(img('OSMapaPLext-PODSTAWOWA', fid=5)),
            'missing MDR hint': archive(img('OSMapaPLext-PODSTAWOWA', fid=4, mdr=False)),
            'two entries': archive(img('OSMapaPLext-PODSTAWOWA', fid=4), extra=('README.txt', 'x')),
            'wrong name': archive(img('OSMapaPLext-PODSTAWOWA', fid=4), name='OSMapaPL/gmapsupp.img'),
            'stored entry': archive(img('OSMapaPLext-PODSTAWOWA', fid=4), method=zipfile.ZIP_STORED),
            'not IMG': archive(b'\x00' * 200_000),
        }
        self.assertTrue(inspect_osmapa(source, 'plext', 'podstawowa', fetcher=MemoryFetcher()).source_proof)
        for label, body in cases.items():
            with self.subTest(label), self.assertRaises(ProviderCollectionError):
                inspect_osmapa(source, 'plext', 'podstawowa', fetcher=MemoryFetcher({source: body}))
        with self.assertRaises(ProviderCollectionError):
            inspect_osmapa(source, 'pl', 'podstawowa', fetcher=MemoryFetcher())
        with self.assertRaises(ProviderCollectionError):
            inspect_osmapa(source, 'plext', 'podstawowa', fetcher=MemoryFetcher(short_head=True))
        changed = MemoryFetcher(etags={(source, 'head'): '"changed"'})
        with self.assertRaises(ProviderCollectionError):
            inspect_osmapa(source, 'plext', 'podstawowa', fetcher=changed)

    def test_encrypted_entry_is_rejected(self):
        source = url()
        body = bytearray(fixture(source))
        central = body.rfind(b'PK\x01\x02'); body[central + 8] |= 1
        with self.assertRaises(ProviderCollectionError):
            inspect_osmapa(source, 'pl', 'ogonki', fetcher=MemoryFetcher({source: bytes(body)}))

    def test_source_gate_closes_on_403_429_5xx_and_keeps_previous_snapshot(self):
        for code in (403, 429, 503):
            errors = {url('plext', 'LIGHT'): HTTPError(url('plext', 'LIGHT'), code, 'x', {}, None)}
            with self.subTest(code=code), self.assertRaises(ProviderCollectionError):
                OSMapaProviderAdapter(fetcher=MemoryFetcher(errors=errors)).collect()

        class IndexDown(MemoryFetcher):
            def fetch_index(self):
                raise HTTPError(ROOT, 403, 'Forbidden', {}, None)
        with self.assertRaises(ProviderCollectionError):
            OSMapaProviderAdapter(fetcher=IndexDown()).collect()

    def test_one_invalid_package_stays_out_or_unavailable_without_proof(self):
        broken = url('pl', 'LIGHT')
        bodies = {broken: archive(img('OSMapaPL-LIGHT', fid=4))}
        snapshot = OSMapaProviderAdapter(fetcher=MemoryFetcher(bodies)).collect()
        self.assertEqual(len(snapshot.packages), 7)
        self.assertNotIn('osmapa-pl-light', {p.id for p in snapshot.packages})
        adapter = OSMapaProviderAdapter(fetcher=MemoryFetcher(bodies))
        adapter.set_previous_rows([{'provider_id': 'osmapa', 'package_id': 'osmapa-pl-light',
            'artifact_source_url': url('pl', 'LIGHT', '20261004'), 'artifact_size_bytes': 400_000_000,
            'package_source_updated_at': datetime(2026, 10, 4, tzinfo=timezone.utc)}])
        package = next(p for p in adapter.collect().packages if p.id == 'osmapa-pl-light')
        self.assertEqual((package.availability, package.release), ('UNAVAILABLE', '2026-10-04'))
        self.assertEqual(package.artifacts[0].validation_status, 'UNAVAILABLE')
        self.assertIsNone(package.artifacts[0].source_proof)
        self.assertIsNone(package.artifacts[0].install_size_bytes)
        missing = MemoryFetcher(errors={broken: HTTPError(broken, 404, 'Not Found', {}, None)})
        self.assertEqual(len(OSMapaProviderAdapter(fetcher=missing).collect().packages), 7)

    def test_fetcher_requires_exact_206_and_never_follows_redirects(self):
        class Response:
            def __init__(self, status, headers, body=b'x' * 16, location=None):
                self.status, self.headers, self.body, self.location = status, headers, body, location
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def geturl(self): return self.location or url()
            def read(self, _): return self.body
        headers = {'Content-Range': 'bytes 0-15/1000', 'ETag': '"a"', 'Last-Modified': 'x'}
        fetcher = OSMapaFetcher()
        for response in (Response(200, headers), Response(206, {**headers, 'ETag': 'W/"a"'}),
                         Response(206, {**headers, 'Content-Range': 'bytes 0-31/1000'}),
                         Response(206, {**headers, 'Content-Range': 'bytes 0-7/1000'}, body=b'x' * 8),
                         Response(206, {**headers, 'Content-Range': 'bytes 1-16/1000'}),
                         Response(206, headers, location=url('plext'))):
            fetcher.opener = SimpleNamespace(open=lambda *_args, response=response, **_kw: response)
            with self.assertRaises(ProviderCollectionError):
                fetcher.fetch_range(url(), 'bytes=0-15')
        fetcher.opener = SimpleNamespace(open=lambda *_a, **_k: Response(206, headers))
        self.assertEqual(fetcher.fetch_range(url(), 'bytes=0-15')[0].total_size, 1000)
        tail = {**headers, 'Content-Range': 'bytes 984-999/1000'}
        fetcher.opener = SimpleNamespace(open=lambda *_a, **_k: Response(206, tail))
        self.assertEqual(fetcher.fetch_range(url(), 'bytes=-16')[0].start, 984)
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range(url(), 'bytes=-32')
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range(url(), 'bytes=0-')
        from terento_catalog.osmapa import _NoRedirect
        with self.assertRaises(ProviderCollectionError):
            _NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'https://evil.test/')
        calls = []
        def reset_once(*_a, **_k):
            calls.append(1)
            if len(calls) == 1:
                raise URLError(ConnectionResetError())
            return Response(206, headers)
        fetcher.opener = SimpleNamespace(open=reset_once)
        fetcher.fetch_range(url(), 'bytes=0-15')
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range('https://example.test/x.zip', 'bytes=0-15')

    def test_only_v5_projection_contains_osmapa(self):
        now = datetime.now(timezone.utc)
        rows = [dict(provider_id=p, provider_name=p, provider_website='https://example.test', provider_attribution='',
                     provider_license_url='https://example.test/license', provider_license_information='', version_year=None)
                for p in ('freizeitkarte', 'opentopomap', 'maprando', 'bbbike', 'osmapa', 'unreviewed')]
        service = CatalogService(SimpleNamespace(catalog_snapshot=lambda: (rows, now)))
        expected = {'freizeitkarte', 'opentopomap', 'maprando', 'bbbike'}
        for method, providers in ((service.catalog_response, {'freizeitkarte', 'opentopomap'}),
                                  (service.catalog_v3_response, {'freizeitkarte', 'opentopomap', 'maprando'}),
                                  (service.catalog_v4_response, expected),
                                  (service.catalog_v5_response, expected | {'osmapa'})):
            self.assertEqual({p['id'] for p in json.loads(method()[0])['providers']}, providers)
        self.assertIs(KNOWN_PROVIDER_DEFINITIONS['osmapa'], OSMAPA)

    def test_closed_projection_timestamp_ignores_providers_outside_it(self):
        global_change = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)
        changed = {'freizeitkarte': datetime(2026, 9, 1, tzinfo=timezone.utc),
                   'opentopomap': datetime(2026, 9, 2, tzinfo=timezone.utc),
                   'maprando': datetime(2026, 9, 3, tzinfo=timezone.utc),
                   'bbbike': datetime(2026, 10, 1, tzinfo=timezone.utc), 'osmapa': global_change}
        rows = [dict(provider_id=p, provider_name=p, provider_website='https://example.test', provider_attribution='',
                     provider_license_url='https://example.test/license', provider_license_information='',
                     version_year=None, provider_changed_at=at) for p, at in changed.items()]
        service = CatalogService(SimpleNamespace(catalog_snapshot=lambda: (rows, global_change)))
        for method, expected in ((service.catalog_response, '2026-09-02'), (service.catalog_v3_response, '2026-09-03'),
                                 (service.catalog_v4_response, '2026-10-01'), (service.catalog_v5_response, '2026-10-26')):
            body, _, last_modified = method()
            self.assertEqual(json.loads(body)['updatedAt'][:10], expected)
            self.assertEqual(last_modified.date().isoformat(), expected)

    def test_paused_package_is_published_blocked_with_type_geography_and_conflict_group(self):
        snapshot = OSMapaProviderAdapter(fetcher=MemoryFetcher()).collect()
        package = next(p for p in snapshot.packages if p.id == 'osmapa-plext-ogonki')
        artifact = package.artifacts[0]
        row = dict(provider_id='osmapa', provider_name='OSMapaPL', provider_status='PAUSED',
            provider_website=OSMAPA.website, provider_attribution=OSMAPA.attribution,
            provider_license_url=OSMAPA.license_url, provider_license_information=OSMAPA.license,
            package_id=package.id, provider_region_id=package.provider_region_id,
            canonical_region_id=package.canonical_region_id, package_name=package.name,
            package_region=package.region, package_country=package.country, release=package.release,
            release_id=package.release_id, version_label=package.version_label,
            generated_at=package.generated_at, package_source_updated_at=package.source_updated_at,
            availability=package.availability, country_codes=list(package.country_codes),
            region_kind=package.region_kind, tags=list(package.tags), capabilities=['main'],
            map_type=package.map_type, geographic_region_id=package.geographic_region_id,
            artifact_id=artifact.id, artifact_kind='main', artifact_required=True,
            artifact_source_url=artifact.source_url, artifact_size_bytes=artifact.size_bytes,
            artifact_install_size_bytes=artifact.install_size_bytes, artifact_content_type=artifact.content_type,
            artifact_validation_status='VALIDATED', artifact_source_proof=artifact.source_proof,
            artifact_install_payload_path='gmapsupp.img', artifact_source_updated_at=artifact.source_updated_at)
        catalog = build_catalog([row], datetime.now(timezone.utc))
        provider = catalog['providers'][0]
        self.assertEqual((provider['status'], provider['downloadBlockReason']), ('PAUSED', 'PROVIDER_PAUSED'))
        published = provider['maps'][0]
        self.assertEqual(published['version'], {'year': 2026, 'month': 10, 'day': 24})
        self.assertEqual((published['mapType'], published['geographicRegionId'], published['conflictGroup']),
                         ('ogonki', 'POLAND-WITH-BORDER-AREAS', 'osmapa-ogonki'))
        self.assertEqual(published['artifacts'][0]['sourceProof']['familyId'], 5)
        self.assertEqual(conflict_group('warstwice'), 'osmapa-warstwice')


if __name__ == '__main__':
    unittest.main()

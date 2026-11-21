"""Lucky Maps protocol tests; synthetic IMG headers are adversarial fixtures, not hardware evidence."""
import json
import re
import struct
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

from native_catalog_acceptance import catalog_rejections
from terento_catalog.catalog import build_catalog
from terento_catalog.http_api import CatalogService
from terento_catalog.luckymaps import (HEADER_BYTES, INDEX_URL, MAPS_ROOT, LuckyMapsFetcher,
    LuckyMapsProviderAdapter, RangeBody, SourceRef, header_facts, inspect_luckymaps, mps_identity,
    package_id, parse_index, source_url)
from terento_catalog.map_preview.acquire import reviewed_url
from terento_catalog.provider_catalog import KNOWN_PROVIDER_DEFINITIONS, LUCKYMAPS, ProviderCollectionError

FIXTURES = Path(__file__).parent / "fixtures" / "luckymaps"
MPS_BLOCK = 20


def mps(family, area, *, publisher=b"luckymaps.ch", families=None):
    body = b""
    for number, fam in enumerate(families or [family]):
        strings = b"series name\x00" + area.encode() + b"\x00" + publisher + b"\x00"
        record = struct.pack("<HHI", 1, fam, fam * 1000 + number) + strings + b"\x00\x00\x00\x00"
        body += b"L" + struct.pack("<H", len(record)) + record
    family_record = struct.pack("<HH", 1, family) + publisher + b"\x00"
    body += b"F" + struct.pack("<H", len(family_record)) + family_record
    version = b"OSM map set\x00\x00"
    body += b"V" + struct.pack("<H", len(version)) + version
    return body


def img(title, *, family=55001, date=(2026, 10, 4), contour=False, size=200_000, mps_body=None, mdr=None):
    data = bytearray(size)
    data[0x10:0x16], data[0x41:0x47] = b"DSKIMG", b"GARMIN"
    data[0x39:0x3B] = date[0].to_bytes(2, "little"); data[0x3B], data[0x3C] = date[1], date[2]
    data[0x61], data[0x62] = 9, 0  # 512-byte blocks
    raw = title.encode("latin-1")
    data[0x49:0x5D] = raw[:20].ljust(20, b" "); data[0x65:0x83] = raw[20:].ljust(30, b" ")
    mps_bytes = mps_body if mps_body is not None else mps(family, title)
    data[0x400] = 1; data[0x401:0x40C] = b" " * 11
    entry = 0x600
    data[entry] = 1; data[entry + 1:entry + 12] = b"MAKEGMAPMPS"
    data[entry + 0x0C:entry + 0x10] = struct.pack("<I", len(mps_bytes))
    data[entry + 0x20:entry + 0x22] = struct.pack("<H", MPS_BLOCK)
    if not contour:
        for name in (mdr if mdr is not None else [family]):
            entry += 0x200
            data[entry] = 1; data[entry + 1:entry + 12] = f"{name:08d}MDR".encode()
    data[MPS_BLOCK * 512:MPS_BLOCK * 512 + len(mps_bytes)] = mps_bytes
    return bytes(data)


def index(regions=None, **extra):
    regions = regions or [("Andorra", "andorra", True), ("Lithuania", "lithuania", True), ("USA West", "US-West", False)]
    children = [{"name": name, "map": f"{stem}.img", "poly": f"{stem}.poly",
                 **({"contour": f"{stem}-ct.img"} if contour else {})} for name, stem, contour in regions]
    return json.dumps([{"name": "Europe", "update": "October 2026", "children": children, **extra}])


FAMILIES = {"andorra": 55001, "lithuania": 55029, "US-West": 58072,
            "andorra-ct": 25001, "lithuania-ct": 25029}


def fixture(url):
    _, stem = source_url(url)
    contour = stem.endswith("-ct")
    return img(stem, family=FAMILIES.get(stem, 55100), contour=contour,
               date=(2024, 3, 2) if contour else (2026, 10, 4))


class MemoryFetcher:
    def __init__(self, bodies=None, *, body=None, errors=None, etags=None):
        self.bodies = bodies or {}
        self.index = body if body is not None else index()
        self.errors = errors or {}
        self.etags = etags or {}
        self.requests = []

    def fetch_index(self):
        self.requests.append(("GET", INDEX_URL, None))
        return self.index

    def fetch_range(self, url, start, end):
        self.requests.append(("GET", url, (start, end)))
        if url in self.errors:
            raise self.errors[url]
        body = self.bodies.get(url) or fixture(url)
        chunk = body[start:end + 1]
        etag = self.etags.get((url, start), self.etags.get(url, '"stable"'))
        return RangeBody(start, start + len(chunk) - 1, len(body), chunk, etag, "Sun, 04 Oct 2026 08:00:38 GMT")


def catalog_rows(packages, status="PAUSED"):
    rows = []
    for package in packages:
        for artifact in package.artifacts:
            rows.append(dict(
                provider_id="luckymaps", provider_name="Lucky Maps", provider_status=status,
                provider_website=LUCKYMAPS.website, provider_attribution=LUCKYMAPS.attribution,
                provider_license_url=LUCKYMAPS.license_url, provider_license_information=LUCKYMAPS.license,
                package_id=package.id, provider_region_id=package.provider_region_id,
                canonical_region_id=package.canonical_region_id, package_name=package.name,
                package_region=package.region, package_country=package.country, release=package.release,
                release_id=package.release_id, version_label=package.version_label,
                generated_at=package.generated_at, package_source_updated_at=package.source_updated_at,
                availability=package.availability, country_codes=list(package.country_codes),
                region_kind=package.region_kind, tags=list(package.tags), capabilities=list(package.capabilities),
                map_type=None, geographic_region_id=None,
                artifact_id=artifact.id, artifact_kind=artifact.kind, artifact_required=artifact.required,
                artifact_source_url=artifact.source_url, artifact_size_bytes=artifact.size_bytes,
                artifact_install_size_bytes=artifact.install_size_bytes,
                artifact_checksum_sha256=artifact.checksum_sha256, artifact_content_type=artifact.content_type,
                artifact_validation_status=artifact.validation_status, artifact_source_proof=artifact.source_proof,
                artifact_install_payload_path=None, artifact_source_updated_at=artifact.source_updated_at))
    return rows


class LuckyMapsTests(unittest.TestCase):
    def test_reviewed_url_boundaries(self):
        self.assertEqual(source_url(MAPS_ROOT + "andorra.img")[1], "andorra")
        self.assertEqual(source_url(MAPS_ROOT + "2027-01/US-West.img")[1], "US-West")
        for bad in (MAPS_ROOT.replace("https:", "http:") + "andorra.img", MAPS_ROOT + "andorra.img?x=1",
                    MAPS_ROOT + "andorra.img#x", "https://luckymaps.ch.evil.test/assets/maps/andorra.img",
                    "https://luckymaps.ch:8443/assets/maps/andorra.img", "https://luckymaps.ch/assets/andorra.img",
                    MAPS_ROOT + "../maps/andorra.img", MAPS_ROOT + "andorra.poly", MAPS_ROOT + "andorra.img.zip",
                    MAPS_ROOT + "a%2Fb.img", MAPS_ROOT + "a/b/c/d/andorra.img", MAPS_ROOT + ".hidden.img",
                    "https://user@luckymaps.ch/assets/maps/andorra.img"):
            with self.subTest(url=bad), self.assertRaises(ProviderCollectionError):
                source_url(bad)

    def test_live_index_shape_parses_every_region(self):
        entries, skipped = parse_index((FIXTURES / "maps-2026-10-04.json").read_text())
        self.assertEqual((len(entries), skipped), (263, []))
        by_stem = {entry.stem: entry for entry in entries}
        self.assertEqual(by_stem["andorra"].contour.url, MAPS_ROOT + "andorra-ct.img")
        self.assertIsNone(by_stem["US-West"].contour)
        self.assertEqual(package_id("SouthDE_AT_FL"), "luckymaps-southde-at-fl")
        self.assertEqual(len({package_id(entry.stem) for entry in entries}), 263)

    def test_future_index_with_checksums_and_versioned_folders(self):
        entries, skipped = parse_index((FIXTURES / "maps-future-sha256.json").read_text())
        self.assertEqual(skipped, [])
        andorra = next(entry for entry in entries if entry.stem == "andorra")
        self.assertEqual(andorra.main.url, MAPS_ROOT + "2027-01/andorra.img")
        self.assertEqual(andorra.main.sha256, "a" * 64)
        self.assertEqual(andorra.main.size_bytes, 200_000)
        self.assertEqual(andorra.contour.url, MAPS_ROOT + "2024-03/andorra-ct.img")
        flat, _ = parse_index(json.dumps([{"group": "Europe", "updated": "2027-01", "name": "Andorra",
                                           "map": {"url": "https://luckymaps.ch/assets/maps/andorra.img"}}]))
        self.assertEqual((flat[0].stem, flat[0].group), ("andorra", "Europe"))

    def test_bad_entries_are_left_out_without_hiding_others(self):
        body = json.dumps([{"name": "Europe", "children": [
            {"name": "Andorra", "map": "andorra.img", "contour": "andorra-ct.img"},
            {"name": "Evil", "map": "https://evil.test/assets/maps/x.img"},
            {"name": "Bad hash", "map": {"url": "x.img", "sha256": "nothex"}},
            {"name": "Bad size", "map": {"url": "y.img", "size": True}},
            {"name": "No map", "contour": "z-ct.img"},
            {"name": "Mismatched contour", "map": "lithuania.img", "contour": "latvia-ct.img"},
            {"name": "Dup A", "map": "dup.img"}, {"name": "Dup B", "map": "2027/dup.img"},
        ]}])
        entries, skipped = parse_index(body)
        self.assertEqual([entry.stem for entry in entries], ["andorra", "lithuania"])
        self.assertIsNone(entries[1].contour)
        self.assertEqual(len(skipped), 6)
        for broken in ("not json", "{}", json.dumps([{"name": "x", "children": []}])):
            with self.subTest(broken), self.assertRaises(ProviderCollectionError):
                parse_index(broken)

    def test_collect_publishes_paused_packages_with_optional_contours_and_bounded_requests(self):
        fetcher = MemoryFetcher()
        snapshot = LuckyMapsProviderAdapter(fetcher=fetcher).collect()
        self.assertEqual(snapshot.definition.default_status, "PAUSED")
        self.assertEqual(sorted(p.id for p in snapshot.packages),
                         ["luckymaps-andorra", "luckymaps-lithuania", "luckymaps-us-west"])
        # Index, then one header and one MPS range per file (5 files); no full download.
        self.assertEqual(len(fetcher.requests), 1 + 2 * 5)
        self.assertTrue(all(end - start < 64 * 1024 for _, _, span in fetcher.requests[1:] for start, end in [span]))
        andorra = next(p for p in snapshot.packages if p.id == "luckymaps-andorra")
        self.assertEqual((andorra.release, andorra.country_codes, andorra.region_kind, andorra.name),
                         ("2026-10-04", ("AD",), "country", "Andorra"))
        self.assertEqual(andorra.capabilities, ("main", "contours"))
        main, contour = andorra.artifacts
        self.assertEqual((main.kind, main.required, contour.kind, contour.required), ("main", True, "contours", False))
        self.assertEqual(main.source_proof["familyId"], 55001)
        self.assertEqual(main.source_proof["sourceIdentity"], "luckymaps:andorra:main")
        self.assertEqual(contour.source_proof["sourceIdentity"], "luckymaps:andorra-ct:contours")
        self.assertEqual(contour.source_proof["createdAt"], "2024-03-02")
        self.assertIsNone(main.checksum_sha256)
        west = next(p for p in snapshot.packages if p.id == "luckymaps-us-west")
        self.assertEqual((west.capabilities, west.country_codes, west.region_kind), (("main",), ("US",), "subregion"))

    def test_unchanged_files_reuse_the_stored_proof_with_one_request_each(self):
        first = LuckyMapsProviderAdapter(fetcher=MemoryFetcher()).collect()
        adapter = LuckyMapsProviderAdapter(fetcher=MemoryFetcher())
        adapter.set_previous_rows(catalog_rows(first.packages))
        fetcher = adapter.fetcher
        second = adapter.collect()
        self.assertEqual(len(fetcher.requests), 1 + 5)
        self.assertEqual([[a.source_proof for a in p.artifacts] for p in first.packages],
                         [[a.source_proof for a in p.artifacts] for p in second.packages])
        changed = MemoryFetcher(etags={MAPS_ROOT + "andorra.img": '"new"'})
        adapter = LuckyMapsProviderAdapter(fetcher=changed)
        adapter.set_previous_rows(catalog_rows(first.packages))
        adapter.collect()
        self.assertEqual(len(changed.requests), 1 + 5 + 1)

    def test_identity_mismatches_are_rejected(self):
        ref = SourceRef(MAPS_ROOT + "andorra.img", "andorra")
        cases = {
            "other title": img("andorr"),
            "invalid date": img("andorra", date=(2026, 13, 1)),
            "other publisher": img("andorra", mps_body=mps(55001, "andorra", publisher=b"example.org")),
            "MPS area": img("andorra", mps_body=mps(55001, "lithuania")),
            "two families in MPS": img("andorra", mps_body=mps(55001, "andorra", families=[55001, 55002])),
            "MDR differs from MPS": img("andorra", mdr=[55002]),
            "no MDR": img("andorra", mdr=[]),
            "two MDR": img("andorra", mdr=[55001, 55002]),
            "not IMG": b"\x00" * 200_000,
            "too short": img("andorra")[:2048],
        }
        self.assertTrue(inspect_luckymaps(ref, "main", fetcher=MemoryFetcher()).source_proof)
        for label, body in cases.items():
            with self.subTest(label), self.assertRaises(ProviderCollectionError):
                inspect_luckymaps(ref, "main", fetcher=MemoryFetcher({ref.url: body}))
        with self.assertRaises(ProviderCollectionError):  # contour with a map index
            inspect_luckymaps(SourceRef(MAPS_ROOT + "andorra-ct.img", "andorra-ct"), "contours",
                              fetcher=MemoryFetcher({MAPS_ROOT + "andorra-ct.img": img("andorra-ct", family=25001)}))
        with self.assertRaises(ProviderCollectionError):  # index size differs from served file
            inspect_luckymaps(SourceRef(ref.url, "andorra", 123), "main", fetcher=MemoryFetcher())
        moving = MemoryFetcher(etags={(ref.url, MPS_BLOCK * 512): '"changed"'})
        with self.assertRaises(ProviderCollectionError):
            inspect_luckymaps(ref, "main", fetcher=moving)

    def test_oversized_missing_and_invalid_files_stay_out_or_unavailable(self):
        class Big(MemoryFetcher):
            def fetch_range(self, url, start, end):
                result = super().fetch_range(url, start, end)
                if url.endswith("/lithuania.img"):
                    return RangeBody(result.start, result.end, 4 * 1024**3, result.body, result.etag, result.last_modified)
                return result
        missing = HTTPError(MAPS_ROOT + "US-West.img", 404, "Not Found", {}, None)
        fetcher = Big(errors={MAPS_ROOT + "US-West.img": missing,
                              MAPS_ROOT + "andorra-ct.img": HTTPError(MAPS_ROOT + "andorra-ct.img", 404, "x", {}, None)})
        snapshot = LuckyMapsProviderAdapter(fetcher=fetcher).collect()
        self.assertEqual([p.id for p in snapshot.packages], ["luckymaps-andorra"])
        self.assertEqual(snapshot.packages[0].capabilities, ("main",))
        adapter = LuckyMapsProviderAdapter(fetcher=MemoryFetcher(errors={MAPS_ROOT + "US-West.img": missing}))
        adapter.set_previous_rows([{"provider_id": "luckymaps", "package_id": "luckymaps-us-west",
            "artifact_kind": "main", "artifact_size_bytes": 900_000_000,
            "package_source_updated_at": datetime(2026, 5, 20, tzinfo=timezone.utc)}])
        west = next(p for p in adapter.collect().packages if p.id == "luckymaps-us-west")
        self.assertEqual((west.availability, west.release), ("UNAVAILABLE", "2026-05-20"))
        self.assertEqual(len(west.artifacts), 1)
        self.assertIsNone(west.artifacts[0].source_proof)
        self.assertIsNone(west.artifacts[0].install_size_bytes)

    def test_shared_contour_family_ids_offer_neither_contour(self):
        bodies = {MAPS_ROOT + "lithuania-ct.img": img("lithuania-ct", family=25001, contour=True, date=(2024, 3, 2))}
        snapshot = LuckyMapsProviderAdapter(fetcher=MemoryFetcher(bodies)).collect()
        self.assertTrue(all(p.capabilities == ("main",) for p in snapshot.packages))
        shared_main = {MAPS_ROOT + "lithuania.img": img("lithuania", family=55001)}
        snapshot = LuckyMapsProviderAdapter(fetcher=MemoryFetcher(shared_main)).collect()
        self.assertEqual([p.id for p in snapshot.packages], ["luckymaps-us-west"])

    def test_author_checksums_are_published_and_bound_to_the_proof(self):
        body = json.dumps([{"name": "Europe", "children": [{"name": "Andorra",
            "map": {"url": "andorra.img", "size": 200_000, "sha256": "B" * 64},
            "contour": {"url": "andorra-ct.img", "sha256": "c" * 64}}]}])
        package = LuckyMapsProviderAdapter(fetcher=MemoryFetcher(body=body)).collect().packages[0]
        main, contour = package.artifacts
        self.assertEqual((main.checksum_sha256, main.source_proof["sha256"]), ("b" * 64, "b" * 64))
        self.assertEqual(contour.checksum_sha256, "c" * 64)
        catalog = build_catalog(catalog_rows([package]), datetime.now(timezone.utc))
        self.assertEqual(catalog_rejections(catalog), [])

    def test_source_gate_closes_on_403_429_5xx(self):
        for code in (403, 429, 503):
            errors = {MAPS_ROOT + "lithuania.img": HTTPError(MAPS_ROOT + "lithuania.img", code, "x", {}, None)}
            with self.subTest(code=code), self.assertRaises(ProviderCollectionError):
                LuckyMapsProviderAdapter(fetcher=MemoryFetcher(errors=errors)).collect()

        class IndexDown(MemoryFetcher):
            def fetch_index(self):
                raise HTTPError(INDEX_URL, 503, "Unavailable", {}, None)
        with self.assertRaises(ProviderCollectionError):
            LuckyMapsProviderAdapter(fetcher=IndexDown()).collect()

    def test_fetcher_requires_exact_206_and_never_follows_redirects(self):
        class Response:
            def __init__(self, status, headers, body=b"x" * 16, location=None):
                self.status, self.headers, self.body, self.location = status, headers, body, location
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def geturl(self): return self.location or MAPS_ROOT + "andorra.img"
            def read(self, _): return self.body
        url = MAPS_ROOT + "andorra.img"
        headers = {"Content-Range": "bytes 0-15/1000", "ETag": '"a"', "Last-Modified": "x"}
        fetcher = LuckyMapsFetcher()
        for response in (Response(200, headers), Response(206, {**headers, "ETag": 'W/"a"'}),
                         Response(206, {**headers, "Content-Range": "bytes 1-16/1000"}),
                         Response(206, {**headers, "Content-Range": "bytes 0-15/1000"}, body=b"x" * 8),
                         Response(206, {k: v for k, v in headers.items() if k != "Last-Modified"}),
                         Response(206, headers, location=MAPS_ROOT + "lithuania.img")):
            fetcher.opener = SimpleNamespace(open=lambda *_a, response=response, **_k: response)
            with self.assertRaises(ProviderCollectionError):
                fetcher.fetch_range(url, 0, 15)
        fetcher.opener = SimpleNamespace(open=lambda *_a, **_k: Response(206, headers))
        self.assertEqual(fetcher.fetch_range(url, 0, 15).total, 1000)
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range(url, 0, 128 * 1024)
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range("https://example.test/x.img", 0, 15)
        from terento_catalog.luckymaps import _NoRedirect
        with self.assertRaises(ProviderCollectionError):
            _NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.test/")

    def test_only_v6_projection_contains_luckymaps(self):
        now = datetime.now(timezone.utc)
        rows = [dict(provider_id=p, provider_name=p, provider_website="https://example.test", provider_attribution="",
                     provider_license_url="https://example.test/license", provider_license_information="", version_year=None)
                for p in ("freizeitkarte", "opentopomap", "maprando", "bbbike", "osmapa", "luckymaps", "unreviewed")]
        service = CatalogService(SimpleNamespace(catalog_snapshot=lambda: (rows, now)))
        v5 = {"freizeitkarte", "opentopomap", "maprando", "bbbike", "osmapa"}
        self.assertEqual({p["id"] for p in json.loads(service.catalog_v5_response()[0])["providers"]}, v5)
        self.assertEqual({p["id"] for p in json.loads(service.catalog_v6_response()[0])["providers"]}, v5 | {"luckymaps"})
        self.assertIs(KNOWN_PROVIDER_DEFINITIONS["luckymaps"], LUCKYMAPS)

    def test_never_activated_provider_is_hidden_unless_previewed(self):
        from terento_catalog.http_api import _catalog_preview
        now = datetime.now(timezone.utc)
        snapshot = LuckyMapsProviderAdapter(fetcher=MemoryFetcher()).collect()
        lucky = [dict(row, provider_first_activated_at=None) for row in catalog_rows(snapshot.packages)]
        fzk = dict(provider_id="freizeitkarte", provider_name="Freizeitkarte", provider_status="PAUSED",
                   provider_first_activated_at=now, provider_website="https://example.test",
                   provider_attribution="", provider_license_url="https://example.test/l",
                   provider_license_information="", version_year=None)
        rows = [fzk, *lucky]
        service = CatalogService(SimpleNamespace(catalog_snapshot=lambda: (rows, now)))
        ids = lambda body: {p["id"] for p in json.loads(body[0])["providers"]}
        # A paused provider that was published before stays visible as today.
        self.assertEqual(ids(service.catalog_v6_response()), {"freizeitkarte"})
        self.assertEqual(ids(service.catalog_v6_response(frozenset({"luckymaps"}))), {"freizeitkarte", "luckymaps"})
        self.assertEqual(ids(service.catalog_v5_response()), {"freizeitkarte"})
        for row in lucky:
            row["provider_first_activated_at"] = now
        self.assertEqual(ids(service.catalog_v6_response()), {"freizeitkarte", "luckymaps"})
        self.assertEqual(_catalog_preview("preview=LuckyMaps,unreviewed&preview=osmapa"), frozenset({"luckymaps"}))
        self.assertEqual(_catalog_preview(""), frozenset())

    def test_first_activation_is_recorded_and_read(self):
        root = Path(__file__).resolve().parents[1] / "src" / "terento_catalog"
        db = (root / "db.py").read_text()
        migration = (root / "migrations" / "097_luckymaps_provider.sql").read_text()
        self.assertIn("p.first_activated_at AS provider_first_activated_at", db)
        self.assertIn("CASE WHEN %s = 'ACTIVE' THEN now() END", db)
        self.assertIn("ADD COLUMN IF NOT EXISTS first_activated_at", migration)
        self.assertLess(migration.index("SET first_activated_at = created_at"), migration.index("INSERT INTO map_provider"))

    def test_published_packages_pass_the_native_acceptance_mirror(self):
        snapshot = LuckyMapsProviderAdapter(fetcher=MemoryFetcher()).collect()
        catalog = build_catalog(catalog_rows(snapshot.packages), datetime.now(timezone.utc))
        provider = catalog["providers"][0]
        self.assertEqual((provider["status"], provider["downloadBlockReason"]), ("PAUSED", "PROVIDER_PAUSED"))
        andorra = next(m for m in provider["maps"] if m["id"] == "luckymaps-andorra")
        self.assertEqual(andorra["version"], {"year": 2026, "month": 10, "day": 4})
        contour = next(a for a in andorra["artifacts"] if a["kind"] == "contours")
        self.assertEqual((contour["required"], contour["version"]), (False, {"year": 2024, "month": 3}))
        self.assertEqual(catalog_rejections(catalog), [])
        tampering = {
            "familyId": lambda m, p: p.update(familyId=0),
            "imgTitle": lambda m, p: p.update(imgTitle="lithuania"),
            "weak etag": lambda m, p: p.update(etag='W/"x"'),
            "createdAt": lambda m, p: p.update(createdAt="2026-10-03"),
            "publisher": lambda m, p: p.update(publisher="example.org"),
            "identity": lambda m, p: p.update(sourceIdentity="luckymaps:andorra:contours"),
            "sha mismatch": lambda m, p: p.update(sha256="a" * 64),
            "header flag 1": lambda m, p: p.update(headerIdentityValidated=1),
            "size true": lambda m, p: p.update(downloadSizeBytes=True),
            "id": lambda m, p: m.update(id="luckymaps-other"),
            "url host": lambda m, p: m["artifacts"][0].update(sourceURL="https://evil.test/assets/maps/andorra.img"),
        }
        for label, edit in tampering.items():
            with self.subTest(label):
                broken = json.loads(json.dumps(catalog))
                package = next(m for m in broken["providers"][0]["maps"] if m["id"] == "luckymaps-andorra")
                edit(package, package["artifacts"][0]["sourceProof"])
                self.assertTrue(any(r.startswith(("luckymaps-andorra:", "luckymaps-other:")) for r in catalog_rejections(broken)), label)
        broken = json.loads(json.dumps(catalog))
        package = next(m for m in broken["providers"][0]["maps"] if m["id"] == "luckymaps-andorra")
        package["artifacts"][1]["sourceProof"]["imgTitle"] = "andorra"
        self.assertTrue(catalog_rejections(broken))

    def test_preview_accepts_only_reviewed_lucky_maps_paths(self):
        self.assertEqual(reviewed_url("luckymaps", MAPS_ROOT + "andorra.img"), MAPS_ROOT + "andorra.img")
        self.assertEqual(reviewed_url("luckymaps", MAPS_ROOT + "andorra-ct.img"), MAPS_ROOT + "andorra-ct.img")
        for bad in ("https://luckymaps.ch/assets/maps.json", MAPS_ROOT + "andorra.poly", "https://evil.test/assets/maps/a.img"):
            with self.subTest(bad), self.assertRaises(Exception):
                reviewed_url("luckymaps", bad)

    def test_header_and_mps_parsers_on_measured_live_prefix(self):
        # First 4 KiB of luckymaps.ch andorra.img (2026-10-04) and its MPS, measured 2026-11-21.
        header = (FIXTURES / "andorra-header.bin").read_bytes()
        facts = header_facts(header)
        self.assertEqual((facts.title, facts.created.date().isoformat(), set(facts.mdr_family_ids)),
                         ("andorra", "2026-10-03", {55001}))
        self.assertEqual(mps_identity((FIXTURES / "andorra-mps.bin").read_bytes()), (55001, frozenset({"andorra"})))
        contour = header_facts((FIXTURES / "andorra-ct-header.bin").read_bytes())
        self.assertEqual((contour.title, contour.mdr_family_ids), ("andorra-ct", frozenset()))
        self.assertEqual(mps_identity((FIXTURES / "andorra-ct-mps.bin").read_bytes())[0], 25001)
        self.assertEqual(len(header), HEADER_BYTES)
        self.assertTrue(re.fullmatch(r"[0-9]+", str(facts.block_size)))


if __name__ == "__main__":
    unittest.main()

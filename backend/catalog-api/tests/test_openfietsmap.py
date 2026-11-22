"""OpenFietsMap protocol tests; synthetic ZIPs are adversarial fixtures, not hardware evidence."""
import io
import json
import random
import re
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

from native_catalog_acceptance import catalog_rejections
from terento_catalog.catalog import build_catalog
from terento_catalog.collectors.freizeitkarte.range_zip import RangeResponse
from terento_catalog.http_api import CatalogService
from terento_catalog.openfietsmap import (FIXED_AREAS, ROOT, OpenFietsMapFetcher, OpenFietsMapProviderAdapter,
    discover_europe, discover_fixed, europe_family_id, inspect_openfietsmap, newest_europe_year,
    source_for_url, source_identity)
from terento_catalog.provider_catalog import (KNOWN_PROVIDER_DEFINITIONS, OPENFIETSMAP, ProviderCollectionError,
    acquisition_withheld)

AREAS = {area.key: area for area in FIXED_AREAS}
DATES = {"benelux": "21-11-2026", "benelux-light": "21-11-2026", "benelux-hiking": "21-11-2026",
         "germany": "07-11-2026", "alps": "31-07-2026", "atlantic": "21-09-2026",
         "baleares": "10-01-2026", "iceland": "10-01-2026"}
FILES = {"benelux": "OpenFietsMap.zip", "benelux-light": "OpenFietsMap_light.zip", "benelux-hiking": "gmapsupp.zip",
         "germany": "OFM_DE({d}_gps).zip", "alps": "OFM_Alps({d}_gps).zip", "atlantic": "OFM_Atlantic({d}_gps).zip",
         "baleares": "OFM_Baleares({d}_gps).zip", "iceland": "OFM_Iceland({d}_gps).zip"}
TITLES = {"benelux": "OFM_BNL({d})", "benelux-light": "OFM_light({d})", "benelux-hiking": "OFM_hike({d})",
          "germany": "OFM_DE({d})", "alps": "OFM_Alps({d})", "atlantic": "OFM_Atlantic",
          "baleares": "OFM_Baleares", "iceland": "OFM_Island"}
EUROPE = ("GB", "N", "W", "C", "SW", "SE", "E")


def fixed_url(key, date=None):
    return ROOT + AREAS[key].folder + FILES[key].format(d=date or DATES[key])


def europe_url(area, year=2026, folder="0310"):
    return f"{ROOT}EU_{year}/{folder}/GPS/OFM(EU{year}_{area}_GPS).zip"


def folder_index(key, extra=""):
    name = FILES[key].format(d=DATES[key])
    links = [name, name.replace("_gps", "_pc"), name.replace("_gps", "_gmap"), "readme.html", "?C=N;O=D"]
    return "".join(f'<a href="{link}">{link}</a>' for link in links) + extra


def root_index(years=(2026,)):
    return "".join(f'<a href="EU_{y}/">EU_{y}/</a>' for y in years) + '<a href="Alps/">Alps/</a><a href="/">up</a>'


def europe_page(year=2026, folder="0310", skip=None):
    popups = []
    for area in EUROPE:
        if area == skip:
            continue
        popups.append(f"""bindPopup('OFM(EU{year}_{area})<p><a href="{folder}/GPS/OFM(EU{year}_{area}_GPS).zip">GPS</a></p>"""
                      f"""<p><a href="{folder}/gmap/regions/OFM(EU{year}_{area}_gmap).zip">gmap</a></p>');""")
    return '<html><script>' + "\n".join(popups) + '</script></html>'


def img(title, *, created=(2026, 11, 21), fid=10010, size=120_000):
    data = bytearray(random.Random(title).randbytes(size))
    data[:0x1000] = bytes(0x1000)
    data[0x10:0x16], data[0x41:0x47] = b"DSKIMG", b"GARMIN"
    data[0x39:0x3B] = created[0].to_bytes(2, "little"); data[0x3B], data[0x3C] = created[1], created[2]
    raw = title.encode("latin-1")
    data[0x49:0x5D] = raw[:20].ljust(20, b" "); data[0x65:0x83] = raw[20:].ljust(30, b" ")
    data[0x400] = 1; data[0x401:0x40C] = b" " * 11
    data[0x600] = 1; data[0x601:0x60C] = b"MAKEGMAPMPS"
    data[0x800] = 1; data[0x801:0x80C] = f"{fid:08d}MDR".encode()
    return bytes(data)


def archive(payload, name, *, folder=None, extra=(), method=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", method) as z:
        if folder:
            z.writestr(zipfile.ZipInfo(folder), b"")
        z.writestr(name, payload)
        for item in extra:
            z.writestr(*item)
    return buffer.getvalue()


def _date_tuple(text):
    day, month, year = text.split("-")
    return int(year), int(month), int(day)


def fixture(url):
    key, payload, fid, dated, year = source_identity(url)
    if year is not None:
        area = key.removeprefix("europe-").upper()
        created = (year, 3, 11 if area in ("SW", "SE", "E") else 10)
        return archive(img(f"OFM(EU{year}_{area})", created=created, fid=fid), payload, folder="garmin/",
                       extra=(("leesme.txt", "x"), ("readme.txt", "x")))
    date = DATES[key]
    title = TITLES[key].format(d=date)
    body = img(title, created=_date_tuple(date), fid=fid)
    if "/" in payload:
        return archive(body, payload, folder=payload.split("/")[0] + "/", extra=(("readme(gps_version).txt", "x"),))
    return archive(body, payload, extra=(("leesmij.html", "x"), ("readme.html", "x"), ("setup.exe", b"MZ" * 64)))


class MemoryFetcher:
    def __init__(self, bodies=None, *, indexes=None, etags=None, errors=None):
        self.bodies = bodies or {}
        self.indexes = {ROOT: root_index(), f"{ROOT}EU_2026/map.html": europe_page(),
                        **{ROOT + area.folder: folder_index(area.key) for area in FIXED_AREAS}, **(indexes or {})}
        self.etags = etags or {}
        self.errors = errors or {}
        self.requests = []; self.bytes_read = 0

    def fetch_index(self, url):
        self.requests.append(("GET", url, None))
        if url in self.errors:
            raise self.errors[url]
        return self.indexes[url]

    def fetch_range(self, url, header):
        self.requests.append(("GET", url, header))
        if url in self.errors:
            raise self.errors[url]
        body = self.bodies.get(url) or fixture(url)
        total = len(body)
        match = re.fullmatch(r"bytes=(?:-([0-9]+)|([0-9]+)-([0-9]+))", header)
        if match[1]:
            start, end = max(0, total - int(match[1])), total - 1
        else:
            start, end = int(match[2]), min(int(match[3]), total - 1)
        chunk = body[start:end + 1]; self.bytes_read += len(chunk)
        etag = self.etags.get((url, "tail" if match[1] else "head"), '"stable"')
        return RangeResponse(206, start, end, total, chunk, url), etag, "Sat, 21 Nov 2026 00:46:41 GMT"

    def inspect(self, source):
        return inspect_openfietsmap(source, fetcher=self)


def catalog_row(package, status="VALIDATED"):
    artifact = package.artifacts[0]
    return dict(provider_id="openfietsmap", provider_name="OpenFietsMap", provider_status="PAUSED",
        provider_website=OPENFIETSMAP.website, provider_attribution=OPENFIETSMAP.attribution,
        provider_license_url=OPENFIETSMAP.license_url, provider_license_information=OPENFIETSMAP.license,
        package_id=package.id, provider_region_id=package.provider_region_id,
        canonical_region_id=package.canonical_region_id, package_name=package.name,
        package_region=package.region, package_country=package.country, release=package.release,
        release_id=package.release_id, version_label=package.version_label,
        generated_at=package.generated_at, package_source_updated_at=package.source_updated_at,
        availability=package.availability, country_codes=list(package.country_codes),
        region_kind=package.region_kind, tags=list(package.tags), capabilities=["main"],
        map_type=package.map_type, geographic_region_id=package.geographic_region_id,
        artifact_id=artifact.id, artifact_kind="main", artifact_required=True,
        artifact_source_url=artifact.source_url, artifact_size_bytes=artifact.size_bytes,
        artifact_install_size_bytes=artifact.install_size_bytes, artifact_content_type=artifact.content_type,
        artifact_validation_status=status, artifact_source_proof=artifact.source_proof,
        artifact_install_payload_path=artifact.install_payload_path if artifact.source_proof else None,
        artifact_source_updated_at=artifact.source_updated_at)


class OpenFietsMapTests(unittest.TestCase):
    def test_reviewed_url_boundaries(self):
        self.assertEqual(source_identity(fixed_url("germany"))[:3], ("germany", "Garmin/gmapsupp.img", 4900))
        self.assertEqual(source_identity(fixed_url("benelux"))[:4], ("benelux", "gmapsupp.img", 10010, None))
        self.assertEqual(source_identity(europe_url("E"))[:3], ("europe-e", "garmin/gmapsupp.img", 20267))
        self.assertEqual(europe_family_id(2024, "GB"), 20241)
        for bad in (fixed_url("germany").replace("https:", "http:"), fixed_url("germany") + "?x=1",
                    fixed_url("germany") + "#x", fixed_url("alps").replace("_gps", "_gmap"),
                    fixed_url("alps").replace("_gps", "_pc"), fixed_url("germany", "31-02-2026"),
                    fixed_url("benelux").replace("OpenFietsMap.zip", "OpenFietsMap(gmap).zip"),
                    fixed_url("benelux-hiking").replace("gmapsupp.zip", "OFM_hike.zip"),
                    fixed_url("germany").replace("(", "%28").replace(")", "%29"),
                    europe_url("GB").replace("EU_2026/", "EU_2025/"), europe_url("GB", folder="1399"),
                    europe_url("GB").replace("/GPS/", "/gmap/"), europe_url("X"),
                    "https://ftp.nluug.nl/maps/openfietsmap/germany/OFM_DE(07-11-2026_gps).zip",
                    fixed_url("germany").replace("openstreetmap.org", "openstreetmap.org.evil.test"),
                    ROOT + "../openfietsmap/" + AREAS["germany"].folder + FILES["germany"].format(d=DATES["germany"])):
            with self.subTest(url=bad), self.assertRaises(ProviderCollectionError):
                source_identity(bad)

    def test_discovery_takes_newest_dated_file_and_seven_europe_areas(self):
        older = '<a href="OFM_DE(01-05-2021_gps).zip">old</a><a href="https://evil.test/OFM_DE(08-11-2026_gps).zip">x</a>'
        self.assertEqual(discover_fixed(AREAS["germany"], folder_index("germany", older)).url, fixed_url("germany"))
        with self.assertRaises(ProviderCollectionError):
            discover_fixed(AREAS["germany"], '<a href="OFM_DE(07-11-2026_gmap).zip">x</a>')
        with self.assertRaises(ProviderCollectionError):
            discover_fixed(AREAS["germany"], folder_index("germany", '<a href="OFM_DE(31-13-2026_gps).zip">bad</a>'))
        self.assertEqual(newest_europe_year(root_index((2024, 2026, 2025))), 2026)
        with self.assertRaises(ProviderCollectionError):
            newest_europe_year('<a href="Alps/">x</a>')
        europe = discover_europe(2026, europe_page())
        self.assertEqual([s.key for s in europe], [f"europe-{a.lower()}" for a in EUROPE])
        self.assertEqual([s.family_id for s in europe], list(range(20261, 20268)))
        for page in (europe_page(skip="SW"), europe_page() + europe_page(folder="0311"),
                     europe_page().replace("EU2026_GB_GPS).zip", "EU2025_GB_GPS).zip")):
            with self.subTest(page=page[-80:]), self.assertRaises(ProviderCollectionError):
                discover_europe(2026, page)

    def test_collect_publishes_fifteen_paused_packages_with_bounded_requests(self):
        fetcher = MemoryFetcher()
        snapshot = OpenFietsMapProviderAdapter(fetcher=fetcher).collect()
        self.assertEqual(snapshot.definition.default_status, "PAUSED")
        self.assertEqual(len(snapshot.packages), 15)
        # Eight folder listings, the root listing and one Europe page, then two
        # ranged GETs per package; no HEAD, no full download.
        self.assertEqual(len(fetcher.requests), 10 + 30)
        self.assertTrue(all(method == "GET" for method, _, _ in fetcher.requests))
        self.assertLessEqual(fetcher.bytes_read, 30 * 64 * 1024)
        packages = {p.id: p for p in snapshot.packages}
        for package in snapshot.packages:
            proof = package.artifacts[0].source_proof
            self.assertEqual(package.availability, "AVAILABLE")
            self.assertEqual(proof["sourceIdentity"], "openfietsmap:" + package.provider_region_id)
            self.assertEqual(proof["installSizeBytes"], package.artifacts[0].install_size_bytes)
            self.assertEqual(package.artifacts[0].install_payload_path, proof["payloadPath"])
            self.assertRegex(proof["crc32"], r"^[0-9a-f]{8}$")
            self.assertEqual(package.release_id, proof["revision"])
            self.assertNotIn("RU", package.country_codes)
            self.assertFalse(acquisition_withheld("openfietsmap", package.provider_region_id,
                                                  package.country_codes, package.region, package.availability))
        self.assertEqual(packages["openfietsmap-germany"].release, "2026-11-07")
        self.assertEqual(packages["openfietsmap-iceland"].artifacts[0].source_proof["imgTitle"], "OFM_Island")
        self.assertEqual(packages["openfietsmap-europe-se"].release, "2026-03-11")
        self.assertEqual(packages["openfietsmap-europe-n"].artifacts[0].source_proof["familyId"], 20262)
        self.assertEqual({p.map_type for p in snapshot.packages}, {"ofm-full", "ofm-light", "ofm-hiking"})
        self.assertEqual(packages["openfietsmap-benelux-hiking"].map_type, "ofm-hiking")
        self.assertEqual(packages["openfietsmap-germany"].country, "DE")
        self.assertIsNone(packages["openfietsmap-alps"].country)

    def test_identity_date_and_archive_mismatches_are_rejected(self):
        g = fixed_url("germany"); e = europe_url("C"); b = fixed_url("benelux")
        cases = {
            "family id": (g, archive(img("OFM_DE(07-11-2026)", created=(2026, 11, 7), fid=4143), "Garmin/gmapsupp.img")),
            "title": (g, archive(img("OFM_Alps(07-11-2026)", created=(2026, 11, 7), fid=4900), "Garmin/gmapsupp.img")),
            "title date": (g, archive(img("OFM_DE(06-11-2026)", created=(2026, 11, 7), fid=4900), "Garmin/gmapsupp.img")),
            "created date": (g, archive(img("OFM_DE(07-11-2026)", created=(2026, 11, 6), fid=4900), "Garmin/gmapsupp.img")),
            "stable title date": (b, archive(img("OFM_BNL(20-11-2026)", fid=10010), "gmapsupp.img")),
            "europe year fid": (e, archive(img("OFM(EU2026_C)", created=(2026, 3, 10), fid=20254), "garmin/gmapsupp.img", folder="garmin/")),
            "europe late": (e, archive(img("OFM(EU2026_C)", created=(2026, 3, 20), fid=20264), "garmin/gmapsupp.img", folder="garmin/")),
            "europe early": (e, archive(img("OFM(EU2026_C)", created=(2026, 3, 9), fid=20264), "garmin/gmapsupp.img", folder="garmin/")),
            "payload path": (g, archive(img("OFM_DE(07-11-2026)", created=(2026, 11, 7), fid=4900), "gmapsupp.img")),
            "second img": (g, archive(img("OFM_DE(07-11-2026)", created=(2026, 11, 7), fid=4900), "Garmin/gmapsupp.img",
                                      extra=(("Garmin/other.img", b"x"),))),
            "unreviewed side file": (g, archive(img("OFM_DE(07-11-2026)", created=(2026, 11, 7), fid=4900),
                                                "Garmin/gmapsupp.img", extra=(("install.sh", b"x"),))),
            "stored": (g, archive(img("OFM_DE(07-11-2026)", created=(2026, 11, 7), fid=4900), "Garmin/gmapsupp.img",
                                  method=zipfile.ZIP_STORED)),
            "not img": (g, archive(b"\x00" * 8192, "Garmin/gmapsupp.img")),
        }
        for label, (url, body) in cases.items():
            with self.subTest(label), self.assertRaises(ProviderCollectionError):
                inspect_openfietsmap(source_for_url(url), fetcher=MemoryFetcher({url: body}))
        changed = MemoryFetcher(etags={(g, "head"): '"other"'})
        with self.assertRaises(ProviderCollectionError):
            inspect_openfietsmap(source_for_url(g), fetcher=changed)

    def test_encrypted_entry_is_rejected(self):
        body = bytearray(fixture(fixed_url("benelux")))
        central = body.rfind(b"PK\x01\x02", 0, body.rfind(b"PK\x01\x02", 0, body.rfind(b"PK\x01\x02")))
        body[central + 8] |= 1
        with self.assertRaises(ProviderCollectionError):
            inspect_openfietsmap(source_for_url(fixed_url("benelux")),
                                 fetcher=MemoryFetcher({fixed_url("benelux"): bytes(body)}))

    def test_source_gate_closes_on_403_429_5xx(self):
        g = fixed_url("germany")
        for code in (403, 429, 503):
            with self.subTest(code=code), self.assertRaises(ProviderCollectionError):
                OpenFietsMapProviderAdapter(fetcher=MemoryFetcher(errors={g: HTTPError(g, code, "x", {}, None)})).collect()
        index = ROOT + "Alps/"
        with self.assertRaises(ProviderCollectionError):
            OpenFietsMapProviderAdapter(fetcher=MemoryFetcher(errors={index: HTTPError(index, 404, "x", {}, None)})).collect()

    def test_one_invalid_package_stays_out_or_unavailable_without_proof(self):
        broken = fixed_url("alps")
        bodies = {broken: archive(img("OFM_Alps(31-07-2026)", created=(2026, 7, 31), fid=4900), "Garmin/gmapsupp.img")}
        snapshot = OpenFietsMapProviderAdapter(fetcher=MemoryFetcher(bodies)).collect()
        self.assertEqual(len(snapshot.packages), 14)
        adapter = OpenFietsMapProviderAdapter(fetcher=MemoryFetcher(bodies))
        adapter.set_previous_rows([{"provider_id": "openfietsmap", "package_id": "openfietsmap-alps",
            "artifact_size_bytes": 2_900_000_000, "package_source_updated_at": datetime(2026, 3, 4, tzinfo=timezone.utc)}])
        package = next(p for p in adapter.collect().packages if p.id == "openfietsmap-alps")
        self.assertEqual((package.availability, package.release), ("UNAVAILABLE", "2026-03-04"))
        self.assertIsNone(package.artifacts[0].source_proof)
        missing = MemoryFetcher(errors={broken: HTTPError(broken, 404, "Not Found", {}, None)})
        self.assertEqual(len(OpenFietsMapProviderAdapter(fetcher=missing).collect().packages), 14)

    def test_fetcher_refuses_unreviewed_urls_and_redirects(self):
        fetcher = OpenFietsMapFetcher()
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_index(ROOT + "OSM_Combiner/")
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range("https://ftp.nluug.nl/maps/openfietsmap/Alps/x.zip", "bytes=-10")
        with self.assertRaises(ProviderCollectionError):
            fetcher.fetch_range(fixed_url("alps"), "bytes=0-")

    def test_only_v6_projection_contains_openfietsmap(self):
        now = datetime.now(timezone.utc)
        rows = [dict(provider_id=p, provider_name=p, provider_website="https://example.test", provider_attribution="",
                     provider_license_url="https://example.test/license", provider_license_information="", version_year=None)
                for p in ("freizeitkarte", "opentopomap", "maprando", "bbbike", "osmapa", "openfietsmap")]
        service = CatalogService(SimpleNamespace(catalog_snapshot=lambda: (rows, now)))
        for method in (service.catalog_response, service.catalog_v3_response, service.catalog_v4_response,
                       service.catalog_v5_response):
            self.assertNotIn("openfietsmap", {p["id"] for p in json.loads(method()[0])["providers"]})
        self.assertIn("openfietsmap", {p["id"] for p in json.loads(service.catalog_v6_response()[0])["providers"]})
        self.assertIs(KNOWN_PROVIDER_DEFINITIONS["openfietsmap"], OPENFIETSMAP)

    def test_never_activated_openfietsmap_is_hidden_unless_previewed(self):
        from terento_catalog.http_api import _catalog_preview
        now = datetime.now(timezone.utc)
        snapshot = OpenFietsMapProviderAdapter(fetcher=MemoryFetcher()).collect()
        rows = [dict(catalog_row(p), provider_first_activated_at=None) for p in snapshot.packages]
        service = CatalogService(SimpleNamespace(catalog_snapshot=lambda: (rows, now)))
        ids = lambda body: {p["id"] for p in json.loads(body[0])["providers"]}
        # Migration 098 inserts the provider PAUSED with first_activated_at NULL:
        # users see nothing, a Debug build sees it with ?preview=openfietsmap.
        self.assertEqual(ids(service.catalog_v6_response()), set())
        preview = _catalog_preview("preview=openfietsmap")
        self.assertEqual(preview, frozenset({"openfietsmap"}))
        body = json.loads(service.catalog_v6_response(preview)[0])
        self.assertEqual(ids((json.dumps(body),)), {"openfietsmap"})
        self.assertEqual(len(body["providers"][0]["maps"]), 15)
        migration = (Path(__file__).resolve().parents[1] / "src" / "terento_catalog" / "migrations"
                     / "098_openfietsmap_provider.sql").read_text()
        self.assertNotIn("first_activated_at", migration)
        for row in rows:
            row["provider_first_activated_at"] = now
        self.assertEqual(ids(service.catalog_v6_response()), {"openfietsmap"})

    def test_paused_packages_pass_the_native_acceptance_mirror(self):
        snapshot = OpenFietsMapProviderAdapter(fetcher=MemoryFetcher()).collect()
        catalog = build_catalog([catalog_row(p) for p in snapshot.packages], datetime.now(timezone.utc))
        provider = catalog["providers"][0]
        self.assertEqual((provider["status"], provider["downloadBlockReason"]), ("PAUSED", "PROVIDER_PAUSED"))
        self.assertEqual(len(provider["maps"]), 15)
        germany = next(m for m in provider["maps"] if m["id"] == "openfietsmap-germany")
        self.assertEqual(germany["version"], {"year": 2026, "month": 11, "day": 7})
        self.assertEqual((germany["mapType"], germany["geographicRegionId"]), ("ofm-full", "GERMANY"))
        self.assertNotIn("conflictGroup", germany)
        self.assertEqual(catalog_rejections(catalog), [])

        tampering = {
            "familyId": lambda m, p: p.update(familyId=4143),
            "imgTitle": lambda m, p: p.update(imgTitle="OFM_DE(08-11-2026)"),
            "weak etag": lambda m, p: p.update(etag='W/"x"'),
            "crc32": lambda m, p: p.update(crc32="ZZZZZZZZ"),
            "url date": lambda m, p: p.update(sourceURL=fixed_url("germany", "08-11-2026")),
            "url area": lambda m, p: p.update(sourceURL=fixed_url("alps")),
            "payload": lambda m, p: p.update(payloadPath="gmapsupp.img"),
            "mapType": lambda m, p: m.update(mapType="ofm-light"),
            "region": lambda m, p: m.update(providerRegionId="netherlands"),
            "russia": lambda m, p: m.update(countryCodes=["DE", "RU"]),
            "size true": lambda m, p: (p.update(downloadSizeBytes=True), m.update(downloadSizeBytes=True)),
            "header flag 1": lambda m, p: p.update(headerIdentityValidated=1),
            "missing field": lambda m, p: p.pop("area"),
            "two artifacts": lambda m, p: m["artifacts"].append(dict(m["artifacts"][0], id="x", kind="contours")),
        }
        for label, edit in tampering.items():
            with self.subTest(label):
                broken = json.loads(json.dumps(catalog))
                package = next(m for m in broken["providers"][0]["maps"] if m["id"] == "openfietsmap-germany")
                edit(package, package["artifacts"][0]["sourceProof"])
                self.assertTrue(any(r.startswith("openfietsmap-germany:") for r in catalog_rejections(broken)), label)

        adapter = OpenFietsMapProviderAdapter(fetcher=MemoryFetcher(
            {fixed_url("alps"): archive(img("OFM_Alps(31-07-2026)", created=(2026, 7, 31), fid=1), "Garmin/gmapsupp.img")}))
        adapter.set_previous_rows([{"provider_id": "openfietsmap", "package_id": "openfietsmap-alps",
            "artifact_size_bytes": 2_900_000_000, "package_source_updated_at": datetime(2026, 3, 4, tzinfo=timezone.utc)}])
        unavailable = build_catalog([catalog_row(p, p.artifacts[0].validation_status) for p in adapter.collect().packages],
                                    datetime.now(timezone.utc))
        self.assertEqual(catalog_rejections(unavailable), [])
        alps = next(m for m in unavailable["providers"][0]["maps"] if m["id"] == "openfietsmap-alps")
        self.assertNotIn("sourceProof", alps["artifacts"][0])


if __name__ == "__main__":
    unittest.main()

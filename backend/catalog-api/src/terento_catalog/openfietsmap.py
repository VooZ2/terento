"""OpenFietsMap Garmin IMG packages; bounded original-source metadata only.

OpenFietsMap (openfietsmap.nl, by Minko) is a routable cycling map compiled
by its author for Europe. The reviewed scope is the GPS (``gmapsupp.img``)
download of fifteen packages: Benelux full, light and hiking layer, Germany,
the Alps, Azores/Madeira/Canary Islands, the Balearic Islands, Iceland and
Europe in seven areas. BaseCamp/MapSource editions (``_pc``/``_gmap``),
OsmAnd files, older releases and binary mirroring are out of scope.

The author gave written permission on 2026-11-21 for Terento to list the
maps. Files stay on the author's server (hosted by OpenStreetMap.org); the
stale 2024 copy on ftp.nluug.nl is never used. Per collection the adapter
reads the folder listings plus one Europe area page and makes two ranged GETs
per package (ZIP tail and head); it never downloads a full archive.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import json
import re
import struct
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib

from .collectors.freizeitkarte.range_zip import RangeResponse
from .provider_catalog import (OPENFIETSMAP, CatalogArtifact, CatalogPackage,
                               ProviderCollectionError, ProviderSnapshot)

ROOT = "https://ligfietser.dev.openstreetmap.org/openfietsmap/"
PROBE_BYTES = 64 * 1024
MAX_INDEX_BYTES = 1024 * 1024
MAX_IMG_BYTES = 4 * 1024**3 - 1
MAX_SIDE_FILE_BYTES = 64 * 1024 * 1024
HEADER_BYTES = 4096
DATE = r"([0-9]{2}-[0-9]{2}-20[0-9]{2})"

# Europe areas in the author's order; the Garmin family ID of an area is
# year * 10 + position (measured on the 2024 and 2026 releases, e.g. 20261 GB,
# 20267 E). Every year has new folders and new family IDs.
EUROPE_AREAS = ("GB", "N", "W", "C", "SW", "SE", "E")


@dataclass(frozen=True)
class Area:
    key: str
    folder: str
    filename: re.Pattern
    payload: str
    family_id: int | None
    title: re.Pattern
    name: str
    country_codes: tuple[str, ...]
    region_kind: str
    map_type: str = "ofm-full"


def _fixed(key, folder, filename, payload, family_id, title, name, codes, kind, map_type="ofm-full"):
    return Area(key, folder, re.compile(filename), payload, family_id, re.compile(title), name,
                codes, kind, map_type)


# Measured 2026-11-21 on every published GPS file: payload path, family ID and
# IMG title. A dated title must carry the IMG creation date; the island
# packages have undated titles and carry the date only in the filename.
FIXED_AREAS = (
    _fixed("benelux", "benelux/full/", r"OpenFietsMap\.zip", "gmapsupp.img", 10010,
           rf"OFM_BNL\({DATE}\)", "Benelux", ("BE", "LU", "NL"), "multiCountry"),
    _fixed("benelux-light", "benelux/light/", r"OpenFietsMap_light\.zip", "gmapsupp.img", 20010,
           rf"OFM_light\({DATE}\)", "Benelux Light", ("BE", "LU", "NL"), "multiCountry", "ofm-light"),
    _fixed("benelux-hiking", "benelux/hike/", r"gmapsupp\.zip", "gmapsupp.img", 50010,
           rf"OFM_hike\({DATE}\)", "Benelux hiking routes", ("BE", "LU", "NL"), "multiCountry",
           "ofm-hiking"),
    _fixed("germany", "germany/", rf"OFM_DE\({DATE}_gps\)\.zip", "Garmin/gmapsupp.img", 4900,
           rf"OFM_DE\({DATE}\)", "Germany", ("DE",), "country"),
    _fixed("alps", "Alps/", rf"OFM_Alps\({DATE}_gps\)\.zip", "Garmin/gmapsupp.img", 4143,
           rf"OFM_Alps\({DATE}\)", "Alps", ("AT", "CH", "DE", "FR", "HR", "IT", "LI", "SI"),
           "multiCountry"),
    _fixed("atlantic", "Atlantic/", rf"OFM_Atlantic\({DATE}_gps\)\.zip", "garmin/gmapsupp.img", 34351,
           r"OFM_Atlantic", "Azores, Madeira and Canary Islands", ("ES", "PT"), "multiCountry"),
    _fixed("baleares", "Baleares/", rf"OFM_Baleares\({DATE}_gps\)\.zip", "garmin/gmapsupp.img", 34971,
           r"OFM_Baleares", "Balearic Islands", ("ES",), "subregion"),
    _fixed("iceland", "Iceland/", rf"OFM_Iceland\({DATE}_gps\)\.zip", "garmin/gmapsupp.img", 35400,
           r"OFM_Island", "Iceland", ("IS",), "country"),
)
# Stable filenames carry no date; their release date is the IMG title date.
UNDATED_FILENAMES = {"benelux", "benelux-light", "benelux-hiking"}

# Country codes name the countries each Europe area is published for. The
# author's areas are rectangles: EU_E reaches Kaliningrad and EU_N the
# St Petersburg, Pskov and Vyborg area (owner decisions 2026-11-21: listed).
# RU is deliberately not a package country, so these areas stay listed.
EUROPE = {
    "GB": ("Great Britain and Ireland", ("GB", "IE", "IM")),
    "N": ("Scandinavia and the Baltic states", ("DK", "EE", "FI", "LT", "LV", "NO", "SE")),
    "W": ("Benelux and northern France", ("BE", "FR", "LU", "NL")),
    "C": ("Central Europe", ("AT", "CH", "CZ", "DE", "DK", "LI", "PL")),
    "SW": ("Southern France, Spain and Portugal", ("AD", "CH", "ES", "FR", "GI", "MC", "PT")),
    "SE": ("Italy and the western Balkans", ("BA", "HR", "IT", "ME", "MT", "SI", "SM", "VA")),
    "E": ("Eastern Europe", ("AL", "BG", "BY", "GR", "HU", "LT", "MD", "MK", "PL", "RO", "RS", "SK", "TR", "UA", "XK")),
}
EUROPE_MAP = re.compile(r"EU_(20[0-9]{2})/")
EUROPE_FILE = re.compile(r"([0-9]{4})/GPS/OFM\(EU(20[0-9]{2})_(GB|N|W|C|SW|SE|E)_GPS\)\.zip")
# Side files that may share an archive with the map; anything else rejects it.
SIDE_FILES = re.compile(r"(?:(?:readme|leesmij|leesme)(?:\(gps_version\))?\.(?:html|txt)|setup\.exe)", re.I)


def package_id(key: str) -> str:
    return f"openfietsmap-{key}"


def europe_key(area: str) -> str:
    return f"europe-{area.lower()}"


def europe_family_id(year: int, area: str) -> int:
    return year * 10 + EUROPE_AREAS.index(area) + 1


def _day(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%d-%m-%Y").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ProviderCollectionError("OpenFietsMap date is invalid") from error


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    payload: str
    family_id: int
    title: re.Pattern
    name: str
    country_codes: tuple[str, ...]
    region_kind: str
    map_type: str
    # Filename date (dated packages) or Europe folder date; None for stable names.
    dated: datetime | None
    europe_year: int | None = None


def source_identity(url: str):
    """Return (key, payload, family ID, filename date, Europe year) for a reviewed URL."""
    if not url.startswith(ROOT):
        raise ProviderCollectionError("OpenFietsMap source outside reviewed HTTPS path")
    parsed = urlparse(url)
    if parsed.query or parsed.fragment or parsed.username or parsed.port or parsed.params:
        raise ProviderCollectionError("OpenFietsMap source has unreviewed URL components")
    path = url[len(ROOT):]
    if "%" in path:
        raise ProviderCollectionError("OpenFietsMap source has unreviewed encoding")
    for area in FIXED_AREAS:
        if path.startswith(area.folder):
            match = area.filename.fullmatch(path[len(area.folder):])
            if match:
                dated = _day(match[1]) if match.groups() else None
                return area.key, area.payload, area.family_id, dated, None
    match = re.fullmatch(r"EU_(20[0-9]{2})/" + EUROPE_FILE.pattern, path)
    if match and match[1] == match[3]:
        year = int(match[1])
        try:
            folder = datetime(year, int(match[2][:2]), int(match[2][2:]), tzinfo=timezone.utc)
        except ValueError as error:
            raise ProviderCollectionError("OpenFietsMap Europe folder date is invalid") from error
        return europe_key(match[4]), "garmin/gmapsupp.img", europe_family_id(year, match[4]), folder, year
    raise ProviderCollectionError("OpenFietsMap source filename is not reviewed")


def source_for_url(url: str) -> Source:
    """The reviewed package for one source URL (collection, rechecks and health)."""
    key, payload, family_id, dated, year = source_identity(url)
    if year is not None:
        area = key.removeprefix("europe-").upper()
        name, codes = EUROPE[area]
        return Source(key, url, payload, family_id, re.compile(re.escape(f"OFM(EU{year}_{area})")),
                      f"Europe: {name}", codes, "multiCountry", "ofm-full", dated, year)
    area = next(item for item in FIXED_AREAS if item.key == key)
    return Source(key, url, payload, family_id, area.title, area.name, area.country_codes,
                  area.region_kind, area.map_type, dated)


class _SourceGateClosed(ProviderCollectionError):
    """HTTP 403/429/5xx: the whole collection stops and keeps the previous snapshot."""


def _gate_closing(error):
    return error.code in (403, 429) or error.code >= 500


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderCollectionError("OpenFietsMap source redirect is not reviewed")


def _index_url(url: str) -> bool:
    if url == ROOT:
        return True
    path = url[len(ROOT):] if url.startswith(ROOT) else None
    return path is not None and (any(path == area.folder for area in FIXED_AREAS)
                                 or re.fullmatch(r"EU_20[0-9]{2}/map\.html", path) is not None)


def _decode(body: bytes) -> str:
    # The author's hand-written listings are partly UTF-16 with a BOM.
    if body[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return body.decode("utf-16", errors="strict")
    return body.decode("utf-8", errors="strict")


class OpenFietsMapFetcher:
    def __init__(self):
        self.opener = build_opener(_NoRedirect())
        self.rate_limited = Event()

    def _open(self, url, headers=None):
        if not _index_url(url):
            source_identity(url)
        if self.rate_limited.is_set():
            raise _SourceGateClosed("OpenFietsMap source rate limited; collection makes no further requests")
        request = Request(url, headers={"User-Agent": "TerentoCatalog/0.1 (+https://terento.app)", **(headers or {})})
        for attempt in (0, 1):
            try:
                return self.opener.open(request, timeout=30)
            except HTTPError as error:
                if error.code == 429:
                    self.rate_limited.set()
                raise
            except (URLError, ConnectionError):
                # One retry for a transport reset; never for an HTTP status.
                if attempt:
                    raise

    def fetch_index(self, url):
        if not _index_url(url):
            raise ProviderCollectionError("OpenFietsMap index is not reviewed")
        with self._open(url) as response:
            if response.status != 200 or response.geturl() != url:
                raise ProviderCollectionError("OpenFietsMap index changed source")
            body = response.read(MAX_INDEX_BYTES + 1)
        if len(body) > MAX_INDEX_BYTES:
            raise ProviderCollectionError("OpenFietsMap index exceeded metadata bound")
        try:
            return _decode(body)
        except UnicodeDecodeError as error:
            raise ProviderCollectionError("OpenFietsMap index is not text") from error

    def fetch_range(self, url, header):
        requested = re.fullmatch(r"bytes=(?:-([0-9]+)|([0-9]+)-([0-9]+))", header)
        if not requested:
            raise ProviderCollectionError("OpenFietsMap range request is not reviewed")
        with self._open(url, {"Range": header}) as response:
            if response.status != 206 or response.geturl() != url:
                raise ProviderCollectionError("OpenFietsMap metadata requires exact HTTP206")
            match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", response.headers.get("Content-Range", ""))
            etag, modified = response.headers.get("ETag"), response.headers.get("Last-Modified")
            if not match or not etag or etag.startswith("W/") or not modified:
                raise ProviderCollectionError("OpenFietsMap source lacks stable range metadata")
            start, end, total = int(match[1]), int(match[2]), int(match[3])
            body = response.read(PROBE_BYTES + 1)
        if requested[1]:
            exact = (start, end) == (max(0, total - int(requested[1])), total - 1)
        else:
            exact = (start, end) == (int(requested[2]), min(int(requested[3]), total - 1))
        if (not exact or end < start or total <= end or end - start + 1 > PROBE_BYTES
                or len(body) != end - start + 1):
            raise ProviderCollectionError("OpenFietsMap source returned invalid Content-Range")
        return RangeResponse(206, start, end, total, body, url), etag, modified

    def inspect(self, source):
        return inspect_openfietsmap(source, fetcher=self)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(href)


def _links(html):
    parser = _Links(); parser.feed(html)
    return parser.links


def _quote(path: str) -> str:
    # The server publishes parentheses literally; keep the URL canonical.
    return ROOT + path


def discover_fixed(area: Area, html: str) -> Source:
    """Exactly one newest GPS file per fixed area."""
    found = {}
    for href in _links(html):
        name = unquote(href)
        if "/" in name or name.startswith("?"):
            continue
        match = area.filename.fullmatch(name)
        if not match:
            continue  # BaseCamp editions, readmes and unrelated links are out of scope.
        dated = _day(match[1]) if match.groups() else None
        found.setdefault(dated, set()).add(name)
    if not found:
        raise ProviderCollectionError(f"OpenFietsMap index lacks {package_id(area.key)}")
    if None in found and len(found) > 1:
        raise ProviderCollectionError(f"OpenFietsMap index has ambiguous {package_id(area.key)}")
    newest = max(found, key=lambda value: value or datetime.min.replace(tzinfo=timezone.utc))
    if len(found[newest]) != 1:
        raise ProviderCollectionError(f"OpenFietsMap index has ambiguous {package_id(area.key)}")
    return source_for_url(_quote(area.folder + next(iter(found[newest]))))


def newest_europe_year(root_html: str) -> int:
    years = {int(match[1]) for href in _links(root_html) if (match := EUROPE_MAP.fullmatch(href))}
    if not years:
        raise ProviderCollectionError("OpenFietsMap root index lacks a Europe release")
    return max(years)


def discover_europe(year: int, html: str) -> list[Source]:
    """All seven areas of one Europe release, from the author's area map page."""
    found = {}
    # The links sit in the Leaflet popups' JavaScript strings, not in <a> tags.
    for href in re.findall(r'href="([^"<>]+)"', html):
        match = EUROPE_FILE.fullmatch(href)
        if not match:
            continue  # gmap (BaseCamp) editions and other links.
        if int(match[2]) != year:
            raise ProviderCollectionError("OpenFietsMap Europe page links another year")
        found.setdefault(match[3], set()).add(match[1] + "/GPS/" + f"OFM(EU{year}_{match[3]}_GPS).zip")
    sources = []
    for area in EUROPE_AREAS:
        paths = found.get(area)
        if not paths:
            raise ProviderCollectionError(f"OpenFietsMap Europe {year} lacks area {area}")
        if len(paths) != 1:
            raise ProviderCollectionError(f"OpenFietsMap Europe {year} has ambiguous area {area}")
        sources.append(source_for_url(_quote(f"EU_{year}/" + next(iter(paths)))))
    return sources


@dataclass(frozen=True)
class OpenFietsMapMeasurement:
    download_size_bytes: int
    install_size_bytes: int | None
    payload_path: str
    generated_at: datetime
    source_proof: dict | None


def _central_entries(tail, tail_start, total):
    """Parse the classic (non-ZIP64) central directory from the archive tail."""
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) - position < 22:
        raise ProviderCollectionError("OpenFietsMap ZIP end record is not in the bounded tail")
    disk, cd_disk, disk_entries, entries, cd_size, cd_offset, comment = struct.unpack(
        "<HHHHIIH", tail[position+4:position+22])
    if (disk or cd_disk or disk_entries != entries or not 1 <= entries <= 8
            or position + 22 + comment != len(tail)
            or tail_start + position != cd_offset + cd_size or cd_offset < tail_start):
        raise ProviderCollectionError("OpenFietsMap ZIP central directory is not bounded")
    record = tail[cd_offset - tail_start:position]
    result, cursor = [], 0
    for _ in range(entries):
        if len(record) - cursor < 46 or record[cursor:cursor+4] != b"PK\x01\x02":
            raise ProviderCollectionError("OpenFietsMap ZIP central directory is invalid")
        (flags, method, crc, compressed, size, name_length, extra_length, comment_length,
         _, _, attributes, local_offset) = struct.unpack("<8xHH4xIIIHHHHHII", record[cursor:cursor+46])
        name = record[cursor+46:cursor+46+name_length]
        result.append((name, flags, method, crc, compressed, size, attributes, local_offset))
        cursor += 46 + name_length + extra_length + comment_length
    if cursor != len(record):
        raise ProviderCollectionError("OpenFietsMap ZIP central directory has trailing data")
    return result, cd_offset


def _payload_entry(entries, payload, total, cd_offset):
    """Exactly one unencrypted deflated payload; only reviewed side files beside it."""
    payload_entry, folder = None, payload.rsplit("/", 1)[0] + "/" if "/" in payload else ""
    for name, flags, method, crc, compressed, size, attributes, local_offset in entries:
        try:
            text = name.decode("ascii")
        except UnicodeDecodeError as error:
            raise ProviderCollectionError("OpenFietsMap ZIP entry name is not ASCII") from error
        unix_type = (attributes >> 16) & 0o170000
        if text.startswith("/") or "\\" in text or ".." in text.split("/") or flags & 1:
            raise ProviderCollectionError("OpenFietsMap ZIP entry is not reviewed")
        if text == payload:
            if (payload_entry or method != 8 or unix_type not in (0, 0o100000) or compressed >= total
                    or not HEADER_BYTES <= size <= MAX_IMG_BYTES or local_offset >= cd_offset):
                raise ProviderCollectionError("OpenFietsMap ZIP lacks one deflated gmapsupp.img")
            payload_entry = (crc, compressed, size, local_offset)
        elif folder and text == folder:
            if size or compressed:
                raise ProviderCollectionError("OpenFietsMap ZIP folder entry has data")
        elif SIDE_FILES.fullmatch(text) and "/" not in text:
            if size > MAX_SIDE_FILE_BYTES or text.lower().endswith(".img"):
                raise ProviderCollectionError("OpenFietsMap ZIP side file is not reviewed")
        else:
            raise ProviderCollectionError("OpenFietsMap ZIP contains an unreviewed entry")
    if not payload_entry:
        raise ProviderCollectionError("OpenFietsMap ZIP lacks the reviewed gmapsupp.img")
    return payload_entry


def _img_header(head, payload, compressed, local_offset, cd_offset):
    start = local_offset
    if head[start:start+4] != b"PK\x03\x04":
        raise ProviderCollectionError("OpenFietsMap ZIP local header is invalid")
    flags, method = struct.unpack("<HH", head[start+6:start+10])
    name_length, extra_length = struct.unpack("<HH", head[start+26:start+30])
    data_start = start + 30 + name_length + extra_length
    if (head[start+30:start+30+name_length] != payload.encode() or flags & 1 or method != 8
            or data_start + compressed > cd_offset or data_start >= len(head)):
        raise ProviderCollectionError("OpenFietsMap ZIP local header differs from central directory")
    try:
        header = zlib.decompressobj(-15).decompress(head[data_start:], HEADER_BYTES)
    except zlib.error as error:
        raise ProviderCollectionError("OpenFietsMap IMG prefix does not inflate") from error
    if len(header) != HEADER_BYTES:
        raise ProviderCollectionError("OpenFietsMap IMG prefix is shorter than the reviewed header")
    return header


def header_identity(header):
    """Return (title, creation date, MDR family ID hints) from the first 4 KiB of the IMG."""
    if header[0] != 0 or header[0x10:0x16] != b"DSKIMG" or header[0x41:0x47] != b"GARMIN":
        raise ProviderCollectionError("OpenFietsMap payload lacks unencrypted Garmin IMG header")
    first = header[0x49:0x5D].decode("latin-1")
    continuation = header[0x65:0x83].decode("latin-1").rstrip(" \x00")
    title = first.rstrip(" \x00")
    if len(title) == 20:
        title += continuation
    elif continuation:
        raise ProviderCollectionError("OpenFietsMap IMG description is not one reviewed title")
    year, month, day = struct.unpack("<H", header[0x39:0x3B])[0], header[0x3B], header[0x3C]
    try:
        created = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError as error:
        raise ProviderCollectionError("OpenFietsMap IMG creation date is invalid") from error
    hints = set()
    for offset in range(0x400, HEADER_BYTES, 0x200):
        entry = header[offset:offset+12]
        if entry[0] == 1 and entry[9:12] == b"MDR":
            name = entry[1:9].decode("latin-1")
            if not name.isdigit():
                raise ProviderCollectionError("OpenFietsMap IMG index name is not a Garmin family ID")
            hints.add(int(name))
    return title, created, hints


def _release_date(source: Source, title_match, created: datetime) -> datetime:
    """The IMG creation date, cross-checked with the date the source publishes."""
    if source.europe_year is not None:
        # The author builds the seven areas over two days (2026: 10 and 11 March).
        if not source.dated <= created <= source.dated + timedelta(days=3):
            raise ProviderCollectionError("OpenFietsMap Europe IMG date differs from its release folder")
        return created
    published = source.dated
    if title_match.groups():
        title_date = _day(title_match[1])
        if published is not None and title_date != published:
            raise ProviderCollectionError("OpenFietsMap IMG title date differs from its filename")
        published = title_date
    if published is None or created != published:
        raise ProviderCollectionError("OpenFietsMap IMG creation date differs from the published date")
    return created


def inspect_openfietsmap(source: Source, *, fetcher=None):
    key, payload, family_id, dated, year = source_identity(source.url)
    if (key, payload, family_id, dated, year) != (source.key, source.payload, source.family_id,
                                                  source.dated, source.europe_year):
        raise ProviderCollectionError("OpenFietsMap source identity mismatch")
    fetcher = fetcher or OpenFietsMapFetcher()
    tail, tail_etag, tail_modified = fetcher.fetch_range(source.url, f"bytes=-{PROBE_BYTES}")
    total = tail.total_size
    if tail.end != total - 1 or tail.start != max(0, total - PROBE_BYTES):
        raise ProviderCollectionError("OpenFietsMap tail range is not the archive end")
    entries, cd_offset = _central_entries(tail.body, tail.start, total)
    crc, compressed, size, local_offset = _payload_entry(entries, payload, total, cd_offset)
    head, head_etag, head_modified = fetcher.fetch_range(source.url, f"bytes=0-{min(PROBE_BYTES, total) - 1}")
    if ((head.start, head.end) != (0, min(PROBE_BYTES, total) - 1) or head.total_size != total
            or (head_etag, head_modified) != (tail_etag, tail_modified)):
        raise ProviderCollectionError("OpenFietsMap source changed during inspection")
    header = _img_header(head.body, payload, compressed, local_offset, cd_offset)
    title, created, hints = header_identity(header)
    title_match = source.title.fullmatch(title)
    if not title_match or hints != {family_id}:
        raise ProviderCollectionError("OpenFietsMap IMG identity differs from the reviewed package")
    released = _release_date(source, title_match, created)
    proof = {"sourceURL": source.url, "etag": tail_etag, "lastModified": tail_modified,
             "downloadSizeBytes": total, "installSizeBytes": size, "payloadPath": payload,
             "crc32": f"{crc:08x}", "sourceIdentity": f"openfietsmap:{key}",
             "area": key, "mapType": source.map_type, "familyId": family_id, "imgTitle": title,
             "generatedAt": released.isoformat(), "headerIdentityValidated": True}
    proof["revision"] = hashlib.sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return OpenFietsMapMeasurement(total, size, payload, released, proof)


class OpenFietsMapProviderAdapter:
    definition = OPENFIETSMAP

    def __init__(self, *, fetcher=None):
        self.fetcher = fetcher or OpenFietsMapFetcher()
        self.previous_rows = {}

    def set_previous_rows(self, rows):
        self.previous_rows = {row["package_id"]: row for row in rows
            if row.get("provider_id") == "openfietsmap" and row.get("package_id")}

    def _index(self, url):
        try:
            return self.fetcher.fetch_index(url)
        except HTTPError as error:
            raise _SourceGateClosed(f"OpenFietsMap index returned HTTP {error.code}") from error

    def discover(self):
        sources = [discover_fixed(area, self._index(ROOT + area.folder)) for area in FIXED_AREAS]
        year = newest_europe_year(self._index(ROOT))
        sources += discover_europe(year, self._index(f"{ROOT}EU_{year}/map.html"))
        return sources

    def _measure(self, source):
        try:
            return self.fetcher.inspect(source), None
        except _SourceGateClosed:
            raise
        except HTTPError as error:
            if _gate_closing(error):
                raise _SourceGateClosed(f"OpenFietsMap source returned HTTP {error.code}") from error
            return self._unavailable(source, error)
        except (OSError, ValueError, KeyError, ProviderCollectionError) as error:
            return self._unavailable(source, error)

    def _unavailable(self, source, error):
        # A file that fails validation is never offered; a known package stays
        # listed as unavailable with its previous size and no fresh proof.
        previous = self.previous_rows.get(package_id(source.key), {})
        date = previous.get("package_source_updated_at")
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        if not date:
            return None, error
        return OpenFietsMapMeasurement(previous.get("artifact_size_bytes") or 0, None, source.payload, date, None), error

    def collect(self):
        from .provider_rechecks import check_failure
        packages = []
        for source in self.discover():
            measurement, error = self._measure(source)
            if measurement is None:
                continue  # No trustworthy release metadata: not a catalog member.
            pid = package_id(source.key)
            identity = source.key.upper()
            released = measurement.generated_at.date().isoformat()
            packages.append(CatalogPackage(
                id=pid, provider_id="openfietsmap", provider_region_id=source.key,
                canonical_region_id=identity, name=source.name, region=identity,
                country=source.country_codes[0] if len(source.country_codes) == 1 else None,
                release=released, release_id=(measurement.source_proof or {}).get("revision"),
                version_label=released, generated_at=measurement.generated_at,
                source_updated_at=measurement.generated_at,
                availability="UNAVAILABLE" if error else "AVAILABLE", country_codes=source.country_codes,
                region_kind=source.region_kind, tags=(source.map_type,), capabilities=("main",),
                map_type=source.map_type, geographic_region_id=identity,
                artifacts=(CatalogArtifact(id=pid + "-main", kind="main", source_url=source.url,
                    size_bytes=measurement.download_size_bytes, install_size_bytes=measurement.install_size_bytes,
                    checksum_sha256=None, content_type="application/zip", required=True,
                    validation_status="UNAVAILABLE" if error else "VALIDATED",
                    install_payload_path=measurement.payload_path, source_updated_at=measurement.generated_at,
                    source_proof=measurement.source_proof,
                    last_check=(check_failure(error) if error else {"status": "VALIDATED", "message": "Source validation passed.",
                        "checkedAt": datetime.now(timezone.utc).isoformat()})),)))
        return ProviderSnapshot(self.definition, tuple(packages), datetime.now(timezone.utc))

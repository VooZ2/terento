"""OSMapaPL Garmin IMG packages; bounded original-source metadata only.

One provider, four reviewed styles (three main styles and WARSTWICE contour
lines as a standalone package), each for Poland and Poland with border areas.
SZLAKI, BaseCamp installers, older releases and binary mirroring are out of
scope. Per package the collector makes two ranged GETs (ZIP tail and head);
it never downloads a full archive and never reads the MPS subfile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
import re
import struct
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib

from .collectors.freizeitkarte.range_zip import RangeResponse
from .provider_catalog import OSMAPA, CatalogArtifact, CatalogPackage, ProviderCollectionError, ProviderSnapshot

ROOT = "https://osmapa-garmin.las.org.pl/"
PRODUCTS = ROOT + "products/"
COVERAGES = {"pl": "OSMapaPL", "plext": "OSMapaPLext"}
STYLES = ("podstawowa", "ogonki", "light", "warstwice")
# FID is a function of the style only (measured on every published file);
# PL and PLext of one style share FID and tile IDs and cannot coexist.
FAMILY_IDS = {"podstawowa": 4, "ogonki": 5, "light": 6, "warstwice": 12}
NAMES = {"pl": "Poland", "plext": "Poland with border areas"}
GEOGRAPHY = {"pl": "POLAND", "plext": "POLAND-WITH-BORDER-AREAS"}
FILENAME = re.compile(r"(OSMapaPL(?:ext)?)-(PODSTAWOWA|OGONKI|LIGHT|WARSTWICE)-(20[0-9]{6})V([0-9]+\.[0-9]+)_IMG\.zip")
PAYLOAD = "gmapsupp.img"
PROBE_BYTES = 64 * 1024
MAX_INDEX_BYTES = 1024 * 1024
MAX_IMG_BYTES = 4 * 1024**3 - 1
HEADER_BYTES = 4096


def source_url(value: str):
    """Return (coverage, style, date, version) for one reviewed source URL."""
    if not value.startswith(PRODUCTS):
        raise ProviderCollectionError("OSMapaPL source outside reviewed HTTPS path")
    parsed = urlparse(value)
    if parsed.query or parsed.fragment or parsed.username or parsed.port or parsed.params:
        raise ProviderCollectionError("OSMapaPL source has unreviewed URL components")
    match = FILENAME.fullmatch(value[len(PRODUCTS):])
    if not match:
        raise ProviderCollectionError("OSMapaPL source filename is not reviewed")
    coverage = "plext" if match[1] == "OSMapaPLext" else "pl"
    try:
        date = datetime.strptime(match[3], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ProviderCollectionError("OSMapaPL source filename date is invalid") from error
    return coverage, match[2].lower(), date, match[4]


def package_id(coverage: str, style: str) -> str:
    return f"osmapa-{coverage}-{style}"


def conflict_group(style: str) -> str:
    """Same-style packages share FID and tiles: one per watch, never deleted automatically."""
    return f"osmapa-{style}"


class _SourceGateClosed(ProviderCollectionError):
    """HTTP 403/429/5xx: the whole collection stops and keeps the previous snapshot."""


def _gate_closing(error):
    return error.code in (403, 429) or error.code >= 500


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderCollectionError("OSMapaPL source redirect is not reviewed")


class OSMapaFetcher:
    def __init__(self):
        self.opener = build_opener(_NoRedirect())
        self.rate_limited = Event()

    def _open(self, url, headers=None):
        if url != ROOT:
            source_url(url)
        if self.rate_limited.is_set():
            raise _SourceGateClosed("OSMapaPL source rate limited; collection makes no further requests")
        request = Request(url, headers={"User-Agent": "TerentoCatalog/0.1 (+https://terento.app)", **(headers or {})})
        for attempt in (0, 1):
            try:
                return self.opener.open(request, timeout=30)
            except HTTPError as error:
                if error.code == 429:
                    self.rate_limited.set()
                raise
            except (URLError, ConnectionError):
                # One retry for a transport reset; never for HTTP status. urllib wraps
                # send errors in URLError, but a connection dropped before the
                # response (http.client.RemoteDisconnected, seen 2026-10-31) is raw.
                if attempt:
                    raise

    def fetch_index(self):
        with self._open(ROOT) as response:
            if response.status != 200 or response.geturl() != ROOT:
                raise ProviderCollectionError("OSMapaPL index changed source")
            body = response.read(MAX_INDEX_BYTES + 1)
        if len(body) > MAX_INDEX_BYTES:
            raise ProviderCollectionError("OSMapaPL index exceeded metadata bound")
        return body.decode("utf-8", errors="strict")

    def fetch_range(self, url, header):
        requested = re.fullmatch(r"bytes=(?:-([0-9]+)|([0-9]+)-([0-9]+))", header)
        if not requested:
            raise ProviderCollectionError("OSMapaPL range request is not reviewed")
        with self._open(url, {"Range": header}) as response:
            if response.status != 206 or response.geturl() != url:
                raise ProviderCollectionError("OSMapaPL metadata requires exact HTTP206")
            match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", response.headers.get("Content-Range", ""))
            etag, modified = response.headers.get("ETag"), response.headers.get("Last-Modified")
            if not match or not etag or etag.startswith("W/") or not modified:
                raise ProviderCollectionError("OSMapaPL source lacks stable range metadata")
            start, end, total = int(match[1]), int(match[2]), int(match[3])
            body = response.read(PROBE_BYTES + 1)
        if requested[1]:
            exact = (start, end) == (max(0, total - int(requested[1])), total - 1)
        else:
            exact = (start, end) == (int(requested[2]), min(int(requested[3]), total - 1))
        if (not exact or end < start or total <= end or end - start + 1 > PROBE_BYTES
                or len(body) != end - start + 1):
            raise ProviderCollectionError("OSMapaPL source returned invalid Content-Range")
        return RangeResponse(206, start, end, total, body, url), etag, modified

    def inspect(self, url, coverage, style):
        return inspect_osmapa(url, coverage, style, fetcher=self)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(href)


def discover(html):
    """Exactly one newest source per (coverage, style); all eight must be present."""
    parser = _Links(); parser.feed(html)
    found = {}
    for href in parser.links:
        url = urljoin(ROOT, href)
        if not url.startswith(PRODUCTS):
            continue
        try:
            coverage, style, date, _ = source_url(url)
        except ProviderCollectionError:
            continue  # SZLAKI, BaseCamp installers and unrelated links are out of scope.
        found.setdefault((coverage, style), {}).setdefault(date, set()).add(url)
    result = {}
    for coverage in COVERAGES:
        for style in STYLES:
            dates = found.get((coverage, style))
            if not dates:
                raise ProviderCollectionError(f"OSMapaPL index lacks {package_id(coverage, style)}")
            newest = max(dates)
            if len(dates[newest]) != 1:
                raise ProviderCollectionError(f"OSMapaPL index has ambiguous {package_id(coverage, style)}")
            result[(coverage, style)] = next(iter(dates[newest]))
    return result


@dataclass(frozen=True)
class OSMapaMeasurement:
    download_size_bytes: int
    install_size_bytes: int | None
    payload_path: str
    generated_at: datetime
    source_proof: dict | None


def _central_entry(tail, tail_start, total):
    """Parse the only central-directory entry from the archive tail."""
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) - position < 22:
        raise ProviderCollectionError("OSMapaPL ZIP end record is not in the bounded tail")
    disk, cd_disk, disk_entries, entries, cd_size, cd_offset, comment = struct.unpack("<HHHHIIH", tail[position+4:position+22])
    if (disk or cd_disk or disk_entries != 1 or entries != 1 or position + 22 + comment != len(tail)
            or tail_start + position != cd_offset + cd_size or cd_offset < tail_start):
        raise ProviderCollectionError("OSMapaPL ZIP must contain exactly one bounded entry")
    record = tail[cd_offset - tail_start:position]
    if len(record) < 46 or record[:4] != b"PK\x01\x02":
        raise ProviderCollectionError("OSMapaPL ZIP central directory is invalid")
    (flags, method, crc, compressed, size, name_length, extra_length, comment_length,
     _, _, attributes, local_offset) = struct.unpack("<8xHH4xIIIHHHHHII", record[:46])
    name = record[46:46+name_length]
    if 46 + name_length + extra_length + comment_length != len(record):
        raise ProviderCollectionError("OSMapaPL ZIP central directory has trailing data")
    unix_type = (attributes >> 16) & 0o170000
    if (name != PAYLOAD.encode() or flags & 1 or method != 8 or local_offset != 0
            or unix_type not in (0, 0o100000) or compressed >= total or not HEADER_BYTES <= size <= MAX_IMG_BYTES):
        raise ProviderCollectionError("OSMapaPL ZIP lacks one unencrypted deflated gmapsupp.img")
    return crc, compressed, size, cd_offset


def _img_header(head, compressed, cd_offset):
    if head[:4] != b"PK\x03\x04":
        raise ProviderCollectionError("OSMapaPL ZIP local header is invalid")
    flags, method = struct.unpack("<HH", head[6:10])
    name_length, extra_length = struct.unpack("<HH", head[26:30])
    data_start = 30 + name_length + extra_length
    if (head[30:30+name_length] != PAYLOAD.encode() or flags & 1 or method != 8
            or data_start + compressed > cd_offset or data_start >= len(head)):
        raise ProviderCollectionError("OSMapaPL ZIP local header differs from central directory")
    try:
        header = zlib.decompressobj(-15).decompress(head[data_start:], HEADER_BYTES)
    except zlib.error as error:
        raise ProviderCollectionError("OSMapaPL IMG prefix does not inflate") from error
    if len(header) != HEADER_BYTES:
        raise ProviderCollectionError("OSMapaPL IMG prefix is shorter than the reviewed header")
    return header


def header_identity(header):
    """Return (title, creation date, MDR FID hints) from the first 4 KiB of the IMG."""
    if header[0] != 0 or header[0x10:0x16] != b"DSKIMG" or header[0x41:0x47] != b"GARMIN":
        raise ProviderCollectionError("OSMapaPL payload lacks unencrypted Garmin IMG header")
    first = header[0x49:0x5D].decode("latin-1")
    continuation = header[0x65:0x83].decode("latin-1").rstrip(" \x00")
    title = first.rstrip(" \x00")
    if len(title) == 20:
        title += continuation  # Long descriptions continue at 0x65 (e.g. PODSTAWO + WA).
    elif continuation:
        raise ProviderCollectionError("OSMapaPL IMG description is not one reviewed title")
    year, month, day = struct.unpack("<H", header[0x39:0x3B])[0], header[0x3B], header[0x3C]
    try:
        created = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError as error:
        raise ProviderCollectionError("OSMapaPL IMG creation date is invalid") from error
    hints = set()
    for offset in range(0x400, HEADER_BYTES, 0x200):
        entry = header[offset:offset+12]
        if entry[0] == 1 and entry[9:12] == b"MDR":
            name = entry[1:9].decode("latin-1")
            if not name.isdigit():
                raise ProviderCollectionError("OSMapaPL IMG index name is not a Garmin family ID")
            hints.add(int(name))
    return title, created, hints


def inspect_osmapa(url, coverage, style, *, fetcher=None):
    actual_coverage, actual_style, date, version = source_url(url)
    if (actual_coverage, actual_style) != (coverage, style):
        raise ProviderCollectionError("OSMapaPL source identity mismatch")
    fetcher = fetcher or OSMapaFetcher()
    tail, tail_etag, tail_modified = fetcher.fetch_range(url, f"bytes=-{PROBE_BYTES}")
    total = tail.total_size
    if tail.end != total - 1 or tail.start != max(0, total - PROBE_BYTES):
        raise ProviderCollectionError("OSMapaPL tail range is not the archive end")
    crc, compressed, size, cd_offset = _central_entry(tail.body, tail.start, total)
    head, head_etag, head_modified = fetcher.fetch_range(url, f"bytes=0-{min(PROBE_BYTES, total) - 1}")
    if ((head.start, head.end) != (0, min(PROBE_BYTES, total) - 1) or head.total_size != total
            or (head_etag, head_modified) != (tail_etag, tail_modified)):
        raise ProviderCollectionError("OSMapaPL source changed during inspection")
    header = _img_header(head.body, compressed, cd_offset)
    title, created, hints = header_identity(header)
    expected_title = f"{COVERAGES[coverage]}-{style.upper()}"
    if title != expected_title or created != date or hints != {FAMILY_IDS[style]}:
        raise ProviderCollectionError("OSMapaPL IMG identity differs from reviewed filename")
    proof = {"sourceURL": url, "etag": tail_etag, "lastModified": tail_modified,
             "downloadSizeBytes": total, "installSizeBytes": size, "payloadPath": PAYLOAD,
             "crc32": f"{crc:08x}", "sourceIdentity": f"osmapa:{coverage}:{style}",
             "coverage": coverage, "mapType": style, "familyId": FAMILY_IDS[style],
             "imgTitle": title, "sourceVersion": version, "generatedAt": date.isoformat(),
             "headerIdentityValidated": True}
    proof["revision"] = hashlib.sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return OSMapaMeasurement(total, size, PAYLOAD, date, proof)


class OSMapaProviderAdapter:
    definition = OSMAPA

    def __init__(self, *, fetcher=None):
        self.fetcher = fetcher or OSMapaFetcher()
        self.previous_rows = {}

    def set_previous_rows(self, rows):
        self.previous_rows = {row["package_id"]: row for row in rows
            if row.get("provider_id") == "osmapa" and row.get("package_id")}

    def _measure(self, coverage, style, url):
        try:
            return self.fetcher.inspect(url, coverage, style), None
        except _SourceGateClosed:
            raise
        except HTTPError as error:
            if _gate_closing(error):
                raise _SourceGateClosed(f"OSMapaPL source returned HTTP {error.code}") from error
            return self._unavailable(coverage, style, error)
        except (OSError, ValueError, KeyError, ProviderCollectionError) as error:
            return self._unavailable(coverage, style, error)

    def _unavailable(self, coverage, style, error):
        # A file that fails validation is never offered; a known package stays
        # listed as unavailable with its previous size and no fresh proof.
        previous = self.previous_rows.get(package_id(coverage, style), {})
        date = previous.get("package_source_updated_at")
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        if not date:
            return None, error
        return OSMapaMeasurement(previous.get("artifact_size_bytes") or 0, None, PAYLOAD, date, None), error

    def collect(self):
        from .provider_rechecks import check_failure
        try:
            html = self.fetcher.fetch_index()
        except HTTPError as error:
            raise _SourceGateClosed(f"OSMapaPL index returned HTTP {error.code}") from error
        sources = discover(html)
        packages = []
        for (coverage, style), url in sorted(sources.items()):
            measurement, error = self._measure(coverage, style, url)
            if measurement is None:
                continue  # No trustworthy release metadata: not a catalog member.
            identity = f"{coverage}-{style}".upper()
            pid = package_id(coverage, style)
            released = measurement.generated_at.date().isoformat()
            _, _, _, version = source_url(url)
            name = NAMES[coverage] + (" contour lines" if style == "warstwice" else "")
            packages.append(CatalogPackage(
                id=pid, provider_id="osmapa", provider_region_id=f"{coverage}-{style}",
                canonical_region_id=identity, name=name, region=identity, country="PL",
                release=released, release_id=(measurement.source_proof or {}).get("revision"),
                version_label=f"{released} V{version}", generated_at=measurement.generated_at,
                source_updated_at=measurement.generated_at,
                availability="UNAVAILABLE" if error else "AVAILABLE", country_codes=("PL",),
                region_kind="country", tags=(style,), capabilities=("main",),
                map_type=style, geographic_region_id=GEOGRAPHY[coverage],
                artifacts=(CatalogArtifact(id=pid + "-main", kind="main", source_url=url,
                    size_bytes=measurement.download_size_bytes, install_size_bytes=measurement.install_size_bytes,
                    checksum_sha256=None, content_type="application/zip", required=True,
                    validation_status="UNAVAILABLE" if error else "VALIDATED",
                    install_payload_path=measurement.payload_path, source_updated_at=measurement.generated_at,
                    source_proof=measurement.source_proof,
                    last_check=(check_failure(error) if error else {"status": "VALIDATED", "message": "Source validation passed.",
                        "checkedAt": datetime.now(timezone.utc).isoformat()})),)))
        return ProviderSnapshot(self.definition, tuple(packages), datetime.now(timezone.utc))

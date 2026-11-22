"""Lucky Maps (luckymaps.ch) Garmin IMG packages; bounded original-source metadata only.

The author publishes one JSON index (``/assets/maps.json``) that lists every
region with a main map and, for most regions, a separate contour-line IMG.
Both are raw Garmin IMG files served from ``/assets/maps/``. The collector
reads that index, then one 4 KiB ranged GET per file (IMG header and FAT).
Only when a file's ETag/Last-Modified/size changed since the stored proof does
it make one more bounded ranged GET for the MPS product subfile, which names
the Garmin family ID and the ``luckymaps.ch`` publisher. It never downloads a
complete map and never stores or serves provider binaries.

The index format is read tolerantly: the 2026-10 form (``map``/``contour`` as
file names) and a later form in which ``map``/``contour`` are objects with
``url``, ``size`` and ``sha256`` (the author agreed on 2026-11-18 to add
SHA-256 per file and versioned folders). A SHA-256 is published only when the
author supplies one; Terento never computes it from a full download here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import struct
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .luckymaps_geography import REGION_GEOGRAPHY
from .provider_catalog import (LUCKYMAPS, CatalogArtifact, CatalogPackage, ProviderCollectionError,
    ProviderSnapshot)

LOGGER = logging.getLogger(__name__)

ORIGIN = "https://luckymaps.ch"
HOST = "luckymaps.ch"
INDEX_URL = ORIGIN + "/assets/maps.json"
MAPS_ROOT = ORIGIN + "/assets/maps/"
PUBLISHER = "luckymaps.ch"
MAX_INDEX_BYTES = 1024 * 1024
HEADER_BYTES = 4096
MAX_MPS_BYTES = 64 * 1024
# FAT32 limit on Garmin watches: larger IMGs are never offered.
MAX_IMG_BYTES = 4 * 1024**3 - 1
USER_AGENT = "TerentoCatalog/0.1 (+https://terento.app)"
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
# Versioned folders below /assets/maps/ are allowed (author's 2026-11-18 offer),
# but the tree stays shallow and every segment is a plain name.
MAX_FOLDER_DEPTH = 3


@dataclass(frozen=True)
class SourceRef:
    url: str
    stem: str
    size_bytes: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class IndexEntry:
    stem: str
    name: str
    group: str | None
    group_update: str | None
    main: SourceRef
    contour: SourceRef | None


def source_url(value: str) -> tuple[str, str]:
    """Return (canonical URL, file stem) for one reviewed Lucky Maps IMG URL."""
    if not isinstance(value, str) or not value.startswith(MAPS_ROOT):
        raise ProviderCollectionError("Lucky Maps source outside reviewed HTTPS path")
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname != HOST or parsed.netloc != HOST
            or parsed.query or parsed.fragment or parsed.params):
        raise ProviderCollectionError("Lucky Maps source has unreviewed URL components")
    relative = parsed.path[len("/assets/maps/"):]
    if unquote(relative) != relative:
        raise ProviderCollectionError("Lucky Maps source path must not be percent-encoded")
    parts = relative.split("/")
    if len(parts) - 1 > MAX_FOLDER_DEPTH or not all(_SEGMENT.fullmatch(part) for part in parts):
        raise ProviderCollectionError("Lucky Maps source path is not reviewed")
    filename = parts[-1]
    if not filename.endswith(".img") or not _STEM.fullmatch(filename[:-4]):
        raise ProviderCollectionError("Lucky Maps source filename is not a reviewed IMG name")
    return value, filename[:-4]


def package_id(stem: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not slug:
        raise ProviderCollectionError("Lucky Maps region has no stable identity")
    return "luckymaps-" + slug


def canonical_region(stem: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", stem.upper()).strip("-")


def policy_codes(stem: str) -> tuple[tuple[str, ...], str | None]:
    """Product policy identity from the stem alone; not a membership rule."""
    key = stem.lower()
    if "crimea" in key or "krym" in key:
        return ("UA",), "CRIMEA"
    if key == "russia" or key.startswith(("russia-", "russia_")) or "-russia" in key:
        return ("RU",), None
    return (), None


def display_geography(stem: str, index_name: str) -> tuple[str, tuple[str, ...], str]:
    reviewed = REGION_GEOGRAPHY.get(stem.lower())
    if reviewed:
        return reviewed
    # A new region keeps the author's name and unknown geography.
    name = " ".join(index_name.split()) or stem
    return name[:120], (), "subregion"


def _reference(value: Any, *, kind: str) -> SourceRef | None:
    """One ``map``/``contour`` value: a file name or an object with url/size/sha256."""
    if value is None or value == "":
        return None
    size = sha = None
    if isinstance(value, str):
        location = value
    elif isinstance(value, dict):
        location = value.get("url") or value.get("file") or value.get("path")
        size = value.get("size", value.get("sizeBytes"))
        sha = value.get("sha256", value.get("sha-256"))
        if not isinstance(location, str):
            raise ProviderCollectionError(f"Lucky Maps {kind} entry has no file location")
    else:
        raise ProviderCollectionError(f"Lucky Maps {kind} entry has an unreviewed shape")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size <= 0):
        raise ProviderCollectionError(f"Lucky Maps {kind} size is not a positive integer")
    if sha is not None:
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ProviderCollectionError(f"Lucky Maps {kind} SHA-256 is malformed")
        sha = sha.lower()
    if location.startswith(("https://", "http://", "//")):
        absolute = location
    elif location.startswith("/"):
        absolute = ORIGIN + location
    else:
        absolute = urljoin(MAPS_ROOT, location)
    url, stem = source_url(absolute)
    return SourceRef(url, stem, size, sha)


def _children(document: Any):
    """Yield (group, group update, child) from the nested or a flat index form."""
    groups = document.get("groups") if isinstance(document, dict) else document
    if not isinstance(groups, list):
        raise ProviderCollectionError("Lucky Maps index is not a list of groups")
    for group in groups:
        if not isinstance(group, dict):
            raise ProviderCollectionError("Lucky Maps index group has an unreviewed shape")
        children = group.get("children", group.get("maps", group.get("regions")))
        if children is None and "map" in group:
            # Flat form: each item is one region and names its own group.
            yield group.get("group"), group.get("updated", group.get("update")), group
            continue
        if not isinstance(children, list):
            raise ProviderCollectionError("Lucky Maps index group has no region list")
        for child in children:
            yield group.get("name"), group.get("updated", group.get("update")), child


def parse_index(body: str) -> tuple[list[IndexEntry], list[str]]:
    """Return reviewed entries and the reasons for every entry left out.

    One malformed region never hides the others; an index that is not JSON or
    has no usable region at all is a collection failure.
    """
    try:
        document = json.loads(body)
    except json.JSONDecodeError as error:
        raise ProviderCollectionError("Lucky Maps index is not JSON") from error
    entries, skipped, seen = [], [], {}
    for group, update, child in _children(document):
        try:
            if not isinstance(child, dict):
                raise ProviderCollectionError("Lucky Maps region has an unreviewed shape")
            name = child.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ProviderCollectionError("Lucky Maps region has no name")
            main = _reference(child.get("map"), kind="map")
            if main is None:
                raise ProviderCollectionError("Lucky Maps region has no map file")
            contour = _reference(child.get("contour"), kind="contour")
            if contour is not None and contour.stem != main.stem + "-ct":
                LOGGER.warning("Lucky Maps contour %s does not pair with %s; contour left out", contour.stem, main.stem)
                skipped.append(f"{main.stem}: contour name does not pair")
                contour = None
            pid = package_id(main.stem)
        except ProviderCollectionError as error:
            skipped.append(str(error))
            continue
        if pid in seen:
            # Two index rows claiming one identity are ambiguous: neither is offered.
            skipped.append(f"{main.stem}: duplicate region identity")
            seen[pid] = None
            continue
        seen[pid] = len(entries)
        entries.append(IndexEntry(main.stem, name.strip(), group if isinstance(group, str) else None,
                                  update if isinstance(update, str) else None, main, contour))
    duplicates = {pid for pid, position in seen.items() if position is None}
    entries = [entry for entry in entries if package_id(entry.stem) not in duplicates]
    if not entries:
        raise ProviderCollectionError("Lucky Maps index contains no usable region")
    return entries, skipped


class _SourceGateClosed(ProviderCollectionError):
    """HTTP 403/429/5xx: the whole collection stops and keeps the previous snapshot."""


def _gate_closing(error: HTTPError) -> bool:
    return error.code in (403, 429) or error.code >= 500


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderCollectionError("Lucky Maps source redirect is not reviewed")


@dataclass(frozen=True)
class RangeBody:
    start: int
    end: int
    total: int
    body: bytes
    etag: str
    last_modified: str


class LuckyMapsFetcher:
    def __init__(self):
        self.opener = build_opener(_NoRedirect())
        self.rate_limited = Event()

    def _open(self, url, headers=None):
        if url != INDEX_URL:
            source_url(url)
        if self.rate_limited.is_set():
            raise _SourceGateClosed("Lucky Maps source rate limited; collection makes no further requests")
        request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
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

    def fetch_index(self) -> str:
        with self._open(INDEX_URL) as response:
            if response.status != 200 or response.geturl() != INDEX_URL:
                raise ProviderCollectionError("Lucky Maps index changed source")
            body = response.read(MAX_INDEX_BYTES + 1)
        if len(body) > MAX_INDEX_BYTES:
            raise ProviderCollectionError("Lucky Maps index exceeded metadata bound")
        try:
            return body.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ProviderCollectionError("Lucky Maps index is not UTF-8") from error

    def fetch_range(self, url: str, start: int, end: int) -> RangeBody:
        if start < 0 or end < start or end - start + 1 > MAX_MPS_BYTES:
            raise ProviderCollectionError("Lucky Maps range request is not reviewed")
        with self._open(url, {"Range": f"bytes={start}-{end}"}) as response:
            if response.status != 206 or response.geturl() != url:
                raise ProviderCollectionError("Lucky Maps metadata requires exact HTTP206")
            match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", response.headers.get("Content-Range", ""))
            etag, modified = response.headers.get("ETag"), response.headers.get("Last-Modified")
            if not match or not etag or etag.startswith("W/") or not modified:
                raise ProviderCollectionError("Lucky Maps source lacks stable range metadata")
            got_start, got_end, total = int(match[1]), int(match[2]), int(match[3])
            body = response.read(end - start + 2)
        if (got_start != start or got_end != min(end, total - 1) or total <= got_end
                or len(body) != got_end - got_start + 1):
            raise ProviderCollectionError("Lucky Maps source returned invalid Content-Range")
        return RangeBody(got_start, got_end, total, body, etag, modified)


@dataclass(frozen=True)
class HeaderFacts:
    title: str
    created: datetime
    block_size: int
    mdr_family_ids: frozenset[int]
    mps_block: int | None
    mps_size: int | None


def header_facts(header: bytes) -> HeaderFacts:
    """Fixed IMG header plus the first FAT entries (first 4 KiB only)."""
    if (len(header) < HEADER_BYTES or header[0] != 0 or header[0x10:0x16] != b"DSKIMG"
            or header[0x41:0x47] != b"GARMIN"):
        raise ProviderCollectionError("Lucky Maps payload lacks unencrypted Garmin IMG header")
    first = header[0x49:0x5D].decode("latin-1")
    continuation = header[0x65:0x83].decode("latin-1").rstrip(" \x00")
    title = first.rstrip(" \x00")
    if len(title) == 20:
        title += continuation
    elif continuation:
        raise ProviderCollectionError("Lucky Maps IMG description is not one reviewed title")
    year, month, day = struct.unpack("<H", header[0x39:0x3B])[0], header[0x3B], header[0x3C]
    try:
        created = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError as error:
        raise ProviderCollectionError("Lucky Maps IMG creation date is invalid") from error
    exponent = header[0x61] + header[0x62]
    if not 9 <= exponent <= 16:
        raise ProviderCollectionError("Lucky Maps IMG block size is not reviewed")
    families, mps_block, mps_size = set(), None, None
    for offset in range(0x400, HEADER_BYTES, 0x200):
        entry = header[offset:offset + 0x200]
        if entry[0] != 1:
            continue
        name, ext = entry[1:9].decode("latin-1"), entry[9:12]
        part = struct.unpack("<H", entry[0x10:0x12])[0]
        if ext == b"MDR":
            if not name.isdigit():
                raise ProviderCollectionError("Lucky Maps IMG index name is not a Garmin family ID")
            families.add(int(name))
        elif ext == b"MPS" and part == 0:
            if mps_block is not None:
                raise ProviderCollectionError("Lucky Maps IMG has more than one MPS subfile")
            mps_size = struct.unpack("<I", entry[0x0C:0x10])[0]
            mps_block = struct.unpack("<H", entry[0x20:0x22])[0]
    return HeaderFacts(title, created, 1 << exponent, frozenset(families), mps_block, mps_size)


def mps_identity(body: bytes) -> tuple[int, frozenset[str]]:
    """Return (family ID, area names) from an MPS product subfile.

    Every map (L) and family (F) record must name one family ID, and the
    family record must name the ``luckymaps.ch`` publisher.
    """
    families, areas, publisher_ok, position = set(), set(), False, 0
    while position + 3 <= len(body) and body[position]:
        kind = body[position]
        length = struct.unpack("<H", body[position + 1:position + 3])[0]
        record = body[position + 3:position + 3 + length]
        if len(record) != length:
            raise ProviderCollectionError("Lucky Maps MPS record is truncated")
        if kind == 0x4C:  # L: product, family, map number, then NUL-terminated strings
            if length < 8:
                raise ProviderCollectionError("Lucky Maps MPS map record is invalid")
            families.add(struct.unpack("<H", record[2:4])[0])
            strings = record[8:].split(b"\x00")
            if len(strings) < 3 or strings[2] != PUBLISHER.encode():
                raise ProviderCollectionError("Lucky Maps MPS map record lacks the publisher")
            areas.add(strings[1].decode("latin-1"))
        elif kind == 0x46:  # F: product, family, family name
            if length < 5:
                raise ProviderCollectionError("Lucky Maps MPS family record is invalid")
            families.add(struct.unpack("<H", record[2:4])[0])
            publisher_ok = publisher_ok or record[4:].split(b"\x00")[0] == PUBLISHER.encode()
        position += 3 + length
    if len(families) != 1 or not areas or not publisher_ok:
        raise ProviderCollectionError("Lucky Maps MPS does not name one luckymaps.ch family")
    return next(iter(families)), frozenset(areas)


@dataclass(frozen=True)
class Measurement:
    size_bytes: int
    created: datetime
    source_proof: dict | None


def _reusable(previous: dict | None, ref: SourceRef, probe: RangeBody) -> dict | None:
    if not previous:
        return None
    same = (previous.get("sourceURL") == ref.url and previous.get("etag") == probe.etag
            and previous.get("lastModified") == probe.last_modified
            and previous.get("downloadSizeBytes") == probe.total
            and isinstance(previous.get("familyId"), int) and previous.get("headerIdentityValidated") is True)
    return previous if same else None


def inspect_luckymaps(ref: SourceRef, kind: str, *, fetcher=None, previous_proof: dict | None = None) -> Measurement:
    """Bounded identity check of one main or contour IMG."""
    if kind not in ("main", "contours"):
        raise ProviderCollectionError("Lucky Maps artifact kind is not reviewed")
    url, stem = source_url(ref.url)
    fetcher = fetcher or LuckyMapsFetcher()
    probe = fetcher.fetch_range(url, 0, HEADER_BYTES - 1)
    if probe.total < HEADER_BYTES or len(probe.body) != HEADER_BYTES:
        raise ProviderCollectionError("Lucky Maps IMG is shorter than the reviewed header")
    if probe.total > MAX_IMG_BYTES:
        raise ProviderCollectionError("Lucky Maps IMG exceeds the 4 GiB watch file limit")
    if ref.size_bytes is not None and ref.size_bytes != probe.total:
        raise ProviderCollectionError("Lucky Maps index size differs from the served file")
    facts = header_facts(probe.body)
    if facts.title != stem:
        raise ProviderCollectionError("Lucky Maps IMG title differs from its file name")
    if kind == "main" and len(facts.mdr_family_ids) != 1:
        raise ProviderCollectionError("Lucky Maps map IMG must name exactly one family ID")
    if kind == "contours" and facts.mdr_family_ids:
        raise ProviderCollectionError("Lucky Maps contour IMG unexpectedly carries a map index")
    reused = _reusable(previous_proof, ref, probe)
    if reused:
        family = reused["familyId"]
    else:
        if facts.mps_block is None or not facts.mps_size or facts.mps_size > MAX_MPS_BYTES:
            raise ProviderCollectionError("Lucky Maps IMG lacks a bounded MPS subfile")
        start = facts.mps_block * facts.block_size
        if start + facts.mps_size > probe.total:
            raise ProviderCollectionError("Lucky Maps MPS lies outside the file")
        mps = fetcher.fetch_range(url, start, start + facts.mps_size - 1)
        if (mps.etag, mps.last_modified, mps.total) != (probe.etag, probe.last_modified, probe.total):
            raise ProviderCollectionError("Lucky Maps source changed during inspection")
        family, areas = mps_identity(mps.body)
        if areas != {stem}:
            raise ProviderCollectionError("Lucky Maps MPS area name differs from its file name")
    if kind == "main" and facts.mdr_family_ids != {family}:
        raise ProviderCollectionError("Lucky Maps map index and MPS name different family IDs")
    proof = {"sourceURL": url, "etag": probe.etag, "lastModified": probe.last_modified,
             "downloadSizeBytes": probe.total, "installSizeBytes": probe.total,
             "sourceIdentity": f"luckymaps:{stem}:{kind}", "familyId": family, "imgTitle": stem,
             "createdAt": facts.created.date().isoformat(), "publisher": PUBLISHER,
             "sha256": ref.sha256, "headerIdentityValidated": True}
    proof["revision"] = hashlib.sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Measurement(probe.total, facts.created, proof)


class LuckyMapsProviderAdapter:
    definition = LUCKYMAPS

    def __init__(self, *, fetcher=None):
        self.fetcher = fetcher or LuckyMapsFetcher()
        self.previous_rows: dict[str, dict] = {}
        self.previous_proofs: dict[str, dict] = {}
        self.skipped: list[str] = []

    def set_previous_rows(self, rows):
        self.previous_rows = {row["package_id"]: row for row in rows
            if row.get("provider_id") == "luckymaps" and row.get("package_id")
            and str(row.get("artifact_kind") or "main") == "main"}
        for row in rows:
            proof = row.get("artifact_source_proof")
            if row.get("provider_id") == "luckymaps" and row.get("artifact_id") and isinstance(proof, dict):
                self.previous_proofs[row["artifact_id"]] = proof

    def _measure(self, ref, kind, artifact_id):
        try:
            return inspect_luckymaps(ref, kind, fetcher=self.fetcher,
                                     previous_proof=self.previous_proofs.get(artifact_id)), None
        except _SourceGateClosed:
            raise
        except HTTPError as error:
            if _gate_closing(error):
                raise _SourceGateClosed(f"Lucky Maps source returned HTTP {error.code}") from error
            return None, error
        except (OSError, ValueError, KeyError, ProviderCollectionError) as error:
            return None, error

    def _unavailable_main(self, pid):
        # A file that fails validation is never offered; a known package stays
        # listed as unavailable with its previous size and no fresh proof.
        previous = self.previous_rows.get(pid, {})
        date = previous.get("package_source_updated_at")
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        if not date:
            return None
        return Measurement(previous.get("artifact_size_bytes") or 0, date, None)

    def collect(self) -> ProviderSnapshot:
        from .provider_rechecks import check_failure
        try:
            body = self.fetcher.fetch_index()
        except HTTPError as error:
            raise _SourceGateClosed(f"Lucky Maps index returned HTTP {error.code}") from error
        entries, self.skipped = parse_index(body)
        measured = []
        for entry in entries:
            pid = package_id(entry.stem)
            main, error = self._measure(entry.main, "main", pid + "-main")
            if error is not None:
                LOGGER.info("Lucky Maps %s main not validated: %s", entry.stem, error)
                main = self._unavailable_main(pid)
                if main is None:
                    continue  # Never seen valid: not a catalog member.
            contour = contour_error = None
            if entry.contour is not None and error is None:
                contour, contour_error = self._measure(entry.contour, "contours", pid + "-contours")
                if contour_error is not None:
                    LOGGER.info("Lucky Maps %s contour not offered: %s", entry.stem, contour_error)
            measured.append((entry, pid, main, error, contour))
        # Two contour files with one family ID cannot both live on a watch;
        # neither is offered until the author gives them distinct IDs.
        contour_families: dict[int, int] = {}
        for _, _, _, _, contour in measured:
            if contour is not None:
                family = contour.source_proof["familyId"]
                contour_families[family] = contour_families.get(family, 0) + 1
        main_families: dict[int, int] = {}
        for _, _, main, error, _ in measured:
            if error is None:
                family = main.source_proof["familyId"]
                main_families[family] = main_families.get(family, 0) + 1
        packages = []
        now = datetime.now(timezone.utc)
        for entry, pid, main, error, contour in measured:
            if error is None and main_families[main.source_proof["familyId"]] > 1:
                error = ProviderCollectionError("Lucky Maps map family ID is shared with another region")
                main = self._unavailable_main(pid)
                contour = None
                if main is None:
                    continue
            if contour is not None and contour_families[contour.source_proof["familyId"]] > 1:
                self.skipped.append(f"{entry.stem}: contour family ID {contour.source_proof['familyId']} is shared")
                contour = None
            name, codes, kind = display_geography(entry.stem, entry.name)
            policy, locality = policy_codes(entry.stem)
            if policy:
                codes = policy
            region = canonical_region(entry.stem)
            released = main.created.date().isoformat()
            available = error is None
            artifacts = [CatalogArtifact(
                id=pid + "-main", kind="main", source_url=entry.main.url,
                size_bytes=main.size_bytes, install_size_bytes=main.size_bytes if available else None,
                checksum_sha256=entry.main.sha256 if available else None,
                content_type="application/octet-stream", required=True,
                validation_status="VALIDATED" if available else "UNAVAILABLE",
                source_updated_at=main.created, source_proof=main.source_proof,
                last_check=(check_failure(error) if error else {"status": "VALIDATED",
                    "message": "Source validation passed.", "checkedAt": now.isoformat()}))]
            if contour is not None:
                artifacts.append(CatalogArtifact(
                    id=pid + "-contours", kind="contours", source_url=entry.contour.url,
                    size_bytes=contour.size_bytes, install_size_bytes=contour.size_bytes,
                    checksum_sha256=entry.contour.sha256, content_type="application/octet-stream",
                    required=False, validation_status="VALIDATED", source_updated_at=contour.created,
                    source_proof=contour.source_proof,
                    last_check={"status": "VALIDATED", "message": "Source validation passed.",
                                "checkedAt": now.isoformat()}))
            packages.append(CatalogPackage(
                id=pid, provider_id="luckymaps", provider_region_id=entry.stem,
                canonical_region_id=region, name=name, region=locality or region,
                country=codes[0] if len(codes) == 1 else None, release=released,
                release_id=(main.source_proof or {}).get("revision"), version_label=released,
                generated_at=main.created, source_updated_at=main.created,
                availability="AVAILABLE" if available else "UNAVAILABLE", country_codes=codes,
                region_kind=kind, tags=tuple(t for t in (entry.group,) if t),
                capabilities=("main", "contours") if contour is not None else ("main",),
                artifacts=tuple(artifacts)))
        if self.skipped:
            LOGGER.warning("Lucky Maps index entries left out: %s", "; ".join(self.skipped[:20]))
        return ProviderSnapshot(self.definition, tuple(packages), now)

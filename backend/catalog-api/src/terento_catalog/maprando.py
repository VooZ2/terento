"""Original-source MapRando directory metadata and bounded IMG inspection.

No binary is downloaded or stored: source inspection reads the 512-byte Garmin
header only. Source/legal/device gates remain separate from catalog discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import logging
import unicodedata
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from .collectors.freizeitkarte.range_zip import HTTPRangeFetcher
from .maprando_geography import REGION_GEOGRAPHY, maprando_display_name
from .provider_catalog import (MAPRANDO, CatalogArtifact, CatalogPackage,
    ProviderCollectionError, ProviderSnapshot, _AnchorParser)

MAX_INDEX_BYTES = 1024 * 1024


def region_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        raise ProviderCollectionError("MapRando region has no stable identity")
    return slug


def _source_url(url: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc != "ravenfeld.fr"
            or not parsed.path.startswith("/MapRando/") or parsed.query or parsed.fragment
            or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))):
        raise ProviderCollectionError("MapRando source outside reviewed origin/path")
    return parsed._replace(path=quote(unquote(parsed.path), safe="/" )).geturl()


@dataclass(frozen=True)
class ImageMeasurement:
    size_bytes: int
    identity_validated: bool = True


class MapRandoFetcher:
    def fetch_text(self, url: str) -> str:
        url = _source_url(url)
        with urlopen(Request(url, headers={"User-Agent": HTTPRangeFetcher.user_agent}), timeout=30) as response:
            if _source_url(response.geturl()) != url:
                raise ProviderCollectionError("MapRando directory redirect changed source")
            body = response.read(MAX_INDEX_BYTES + 1)
        if len(body) > MAX_INDEX_BYTES:
            raise ProviderCollectionError("MapRando index exceeded metadata limit")
        return body.decode("utf-8", errors="strict")

    def measure_img(self, url: str) -> ImageMeasurement:
        return inspect_maprando_img(url)


def inspect_maprando_img(url: str) -> ImageMeasurement:
    url = _source_url(url)
    response = HTTPRangeFetcher(timeout_seconds=30, max_response_bytes=512).fetch_range(url, 0, 511)
    if (len(response.body) != 512 or response.total_size < 512
            or response.body[0] != 0 or response.body[16:22] != b"DSKIMG"
            or response.body[65:71] != b"GARMIN"):
        raise ProviderCollectionError("MapRando source has no unencrypted Garmin IMG header")
    description_bytes = response.body[0x49:0x5D] + response.body[0x65:0x83]
    try:
        description = description_bytes.decode("utf-8")
    except UnicodeDecodeError:
        description = description_bytes.decode("latin-1")
    description = description.strip(" \t\r\n\x00")
    header = re.fullmatch(r"MapRando (.+) ([0-9]{2}\.[0-9]{2}\.20[0-9]{2})", description)
    filename = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    expected = re.fullmatch(r"MapRando_(.+)_(20[0-9]{2}_[0-9]{2}_[0-9]{2})\.img", filename)
    valid = False
    if header and expected:
        try:
            valid = (region_slug(header.group(1)) == region_slug(expected.group(1))
                     and datetime.strptime(header.group(2), "%d.%m.%Y") == datetime.strptime(expected.group(2), "%Y_%m_%d"))
        except ValueError:
            pass
    if not valid:
        logging.getLogger(__name__).warning("MapRando source identity unavailable: %s (fixed IMG title/date differs or is truncated)", filename)
    return ImageMeasurement(response.total_size, valid)


def directory_links(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    base_path = urlparse(base_url).path
    result = []
    for href, _ in parser.links:
        candidate = urljoin(base_url, href)
        try:
            candidate = _source_url(candidate)
        except ProviderCollectionError:
            continue
        path = urlparse(candidate).path
        relative = unquote(path[len(base_path):]) if path.startswith(base_path) else ""
        if relative and relative.endswith("/") and "/" not in relative[:-1]:
            result.append((relative[:-1], candidate))
    return sorted(set(result))


def image_links(html: str, directory_url: str, region: str) -> list[tuple[datetime, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    results = []
    for href, _ in parser.links:
        try:
            url = _source_url(urljoin(directory_url, href))
        except ProviderCollectionError:
            continue
        if url.rsplit("/", 1)[0] + "/" != directory_url:
            continue
        filename = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        match = re.fullmatch(r"MapRando_(.+)_(20[0-9]{2})_([0-9]{2})_([0-9]{2})\.img", filename)
        if not match:
            continue
        if region_slug(match.group(1)) != region_slug(region):
            raise ProviderCollectionError("MapRando filename region differs from directory")
        try:
            released = datetime(*map(int, match.groups()[1:]), tzinfo=timezone.utc)
        except ValueError as exc:
            raise ProviderCollectionError("MapRando filename date is invalid") from exc
        results.append((released, url))
    return sorted(set(results))


def policy_identity(slug: str) -> tuple[str, tuple[str, ...]]:
    # Geographic identity only; this is not a catalog membership allowlist.
    if slug in {"crimee", "crimea"}:
        return "CRIMEA", ("UA",)
    if slug in {"russie", "russia"} or slug.startswith(("russie-", "russia-")):
        return re.sub(r"[^A-Z0-9]", "", slug.upper()), ("RU",)
    return re.sub(r"[^A-Z0-9]", "", slug.upper()), ()


class MapRandoProviderAdapter:
    definition = MAPRANDO

    def __init__(self, *, fetcher: MapRandoFetcher | None = None) -> None:
        self.fetcher = fetcher or MapRandoFetcher()

    def collect(self) -> ProviderSnapshot:
        directories = directory_links(self.fetcher.fetch_text(self.definition.catalog_url), self.definition.catalog_url)
        if not directories:
            raise ProviderCollectionError("MapRando catalog contains no region directories")
        packages = []
        seen = set()
        for region, directory_url in directories:
            slug = region_slug(region)
            if slug in seen:
                raise ProviderCollectionError("MapRando normalized region identity collision")
            seen.add(slug)
            links = image_links(self.fetcher.fetch_text(directory_url), directory_url, region)
            if not links:
                # Direct-download catalog excludes BaseCamp-only directories.
                continue
            released, source_url = links[-1]
            if sum(date == released for date, _ in links) != 1:
                raise ProviderCollectionError("MapRando latest release is ambiguous")
            measurement = self.fetcher.measure_img(source_url)
            identity, policy_codes = policy_identity(slug)
            codes, region_kind = REGION_GEOGRAPHY.get(slug, (policy_codes, "subregion"))
            package_id = "maprando-" + slug
            release = released.date().isoformat()
            packages.append(CatalogPackage(
                id=package_id, provider_id="maprando", provider_region_id=slug,
                canonical_region_id=identity, name=maprando_display_name(slug, region),
                region=identity, country=codes[0] if len(codes) == 1 else None,
                release=release, release_id=release,
                version_label=release, generated_at=released, source_updated_at=released,
                availability="AVAILABLE" if measurement.identity_validated else "UNAVAILABLE",
                country_codes=codes, region_kind=region_kind,
                tags=(), capabilities=("main",), artifacts=(CatalogArtifact(
                    id=package_id + "-main", kind="main", source_url=source_url,
                    size_bytes=measurement.size_bytes, install_size_bytes=measurement.size_bytes,
                    checksum_sha256=None, content_type="application/octet-stream", required=True,
                    validation_status="VALIDATED" if measurement.identity_validated else "UNAVAILABLE",
                    source_updated_at=released,
                ),),
            ))
        if not packages:
            raise ProviderCollectionError("MapRando catalog contains no validated direct IMG packages")
        return ProviderSnapshot(self.definition, tuple(packages), datetime.now(timezone.utc))

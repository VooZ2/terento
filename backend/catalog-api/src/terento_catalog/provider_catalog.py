"""Provider-neutral catalog records and the reviewed provider adapters.

Adapters are deliberately small. They discover metadata and original source
URLs only; they never proxy or persist provider map binaries.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import re
import time
from typing import Any, Protocol
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from .collectors.freizeitkarte.collector import FreizeitkarteCollector
from .collectors.freizeitkarte.range_zip import HTTPRangeFetcher, ZipRangeInspector


class ProviderCollectionError(RuntimeError):
    """A provider source could not be converted into a safe catalog snapshot."""


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    adapter_id: str
    website: str
    catalog_url: str
    license: str
    attribution: str
    license_url: str
    default_status: str = "ACTIVE"


@dataclass(frozen=True)
class CatalogArtifact:
    id: str
    kind: str
    source_url: str
    size_bytes: int
    install_size_bytes: int | None
    checksum_sha256: str | None
    content_type: str | None
    required: bool
    validation_status: str
    install_payload_path: str | None = None
    source_updated_at: datetime | None = None


@dataclass(frozen=True)
class CatalogPackage:
    id: str
    provider_id: str
    provider_region_id: str
    canonical_region_id: str
    name: str
    region: str
    country: str | None
    release: str
    release_id: str | None
    version_label: str | None
    generated_at: datetime | None
    source_updated_at: datetime | None
    availability: str
    country_codes: tuple[str, ...]
    region_kind: str
    tags: tuple[str, ...]
    capabilities: tuple[str, ...]
    artifacts: tuple[CatalogArtifact, ...]


@dataclass(frozen=True)
class ProviderSnapshot:
    definition: ProviderDefinition
    packages: tuple[CatalogPackage, ...]
    collected_at: datetime


class ProviderAdapter(Protocol):
    definition: ProviderDefinition

    def collect(self) -> ProviderSnapshot:
        """Collect metadata without downloading a provider binary."""


FREIZEITKARTE = ProviderDefinition(
    id="freizeitkarte",
    name="Freizeitkarte",
    adapter_id="freizeitkarte",
    website="https://www.freizeitkarte-osm.de/garmin/en/index.html",
    catalog_url="https://www.freizeitkarte-osm.de/garmin/en/release.html",
    license=(
        "Map data © OpenStreetMap contributors (ODbL); produced map © FZK "
        "project. Contour-line sources vary by region."
    ),
    attribution="Map data © OpenStreetMap contributors; produced map © FZK project",
    license_url="https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
)

OPENTOPO_MAP = ProviderDefinition(
    id="opentopomap",
    name="OpenTopoMap",
    adapter_id="opentopomap",
    website="https://opentopomap.org/",
    catalog_url="https://garmin.opentopomap.org/",
    license="Map data © OpenStreetMap contributors (ODbL); map rendering © OpenTopoMap.",
    attribution="Map data © OpenStreetMap contributors; map rendering © OpenTopoMap",
    license_url="https://opentopomap.org/about",
    # The repository records the OpenTopoMap source gate as PARTIAL. Keep the
    # known adapter visible but fail closed until an operator activates it.
    default_status="PAUSED",
)

KNOWN_PROVIDER_DEFINITIONS: dict[str, ProviderDefinition] = {
    item.id: item for item in (FREIZEITKARTE, OPENTOPO_MAP)
}

# Beta.8 exposes only OpenTopoMap's ready-to-install Garmin main archives.
# Optional contours remain outside the collection gate until their own
# validation contract is accepted.
OPENTOPO_MAP_BETA8_MAIN_PACKAGE_COUNT = 177

# The beta.8 product policy needs a canonical identity for explicit OTM
# russia packages. Other OTM regions may continue without country codes until
# a reviewed complete geographic mapping is available.
OPENTOPO_MAP_POLICY_COUNTRY_CODES: dict[str, tuple[str, ...]] = {
    "russia-asian-part": ("RU",),
    "russia-european-part": ("RU",),
}


class FreizeitkarteProviderAdapter:
    definition = FREIZEITKARTE

    def __init__(self, collector: FreizeitkarteCollector | None = None) -> None:
        self.collector = collector or FreizeitkarteCollector()

    def collect(self) -> ProviderSnapshot:
        records = self.collector.collect()
        return snapshot_from_freizeitkarte_records(records, self.definition)


def snapshot_from_freizeitkarte_records(
    records: list[Any], definition: ProviderDefinition = FREIZEITKARTE
) -> ProviderSnapshot:
    """Convert the legacy FZK collector output without fetching twice."""

    packages: list[CatalogPackage] = []
    for record in records:
        release = f"{record.version.year:04d}-{record.version.month:02d}"
        download_size = record.download_size_bytes or record.file_size_bytes
        if not download_size or download_size < 0:
            raise ProviderCollectionError(
                f"Freizeitkarte package {record.map.id} has no source size"
            )
        packages.append(
            CatalogPackage(
                id=record.map.id,
                provider_id=definition.id,
                provider_region_id=record.map.identifier,
                canonical_region_id=record.map.region,
                name=record.map.name,
                region=record.map.region,
                country=record.map.country,
                release=release,
                release_id=record.raw_version,
                version_label=record.raw_version,
                generated_at=None,
                source_updated_at=_as_utc(record.release_date),
                availability="AVAILABLE",
                country_codes=(record.map.region,),
                region_kind="country",
                tags=(),
                capabilities=("main",),
                artifacts=(
                    CatalogArtifact(
                        id=f"{record.map.id}-main",
                        kind="main",
                        source_url=record.source_url,
                        size_bytes=download_size,
                        install_size_bytes=record.install_size_bytes,
                        checksum_sha256=record.checksum_sha256,
                        content_type="application/zip",
                        required=True,
                        validation_status=(
                            "VALIDATED"
                            if record.install_size_bytes is not None
                            else "NOT_VALIDATED"
                        ),
                        install_payload_path=record.install_payload_path,
                        source_updated_at=_as_utc(record.release_date),
                    ),
                ),
            )
        )
    return ProviderSnapshot(
        definition=definition,
        packages=tuple(sorted(packages, key=lambda item: item.id)),
        collected_at=datetime.now(timezone.utc),
    )


class OpenTopoMapFetcher:
    user_agent = "TerentoCatalog/0.1 (+https://terento.app)"

    def fetch_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    def head_size(self, url: str) -> int | None:
        return HTTPRangeFetcher(timeout_seconds=30).head_size(url)

    def measure_zip(self, url: str) -> Any:
        fetcher = HTTPRangeFetcher(timeout_seconds=30)
        return ZipRangeInspector(fetcher).inspect(url, expected_payload_path=None)


class OpenTopoMapProviderAdapter:
    definition = OPENTOPO_MAP

    def __init__(
        self,
        *,
        fetcher: OpenTopoMapFetcher | None = None,
        catalog_url: str | None = None,
        expected_main_package_count: int = OPENTOPO_MAP_BETA8_MAIN_PACKAGE_COUNT,
        max_workers: int = 4,
        measurement_attempts: int = 2,
    ) -> None:
        self.fetcher = fetcher or OpenTopoMapFetcher()
        self.catalog_url = catalog_url or self.definition.catalog_url
        self.expected_main_package_count = expected_main_package_count
        self.max_workers = max(1, min(max_workers, 4))
        self.measurement_attempts = max(1, min(measurement_attempts, 3))

    def collect(self) -> ProviderSnapshot:
        html = self.fetcher.fetch_text(self.catalog_url)
        links = [
            link
            for link in parse_opentopomap_catalog(html, self.catalog_url)
            if link.kind == "main"
        ]
        if len(links) != self.expected_main_package_count:
            raise ProviderCollectionError(
                "OpenTopoMap main catalog count changed: "
                f"expected {self.expected_main_package_count}, found {len(links)}"
            )
        packages_by_region: dict[str, dict[str, Any]] = {}
        measurements = self._measure_links(links)
        for link in links:
            package = packages_by_region.setdefault(
                link.region,
                {
                    "name": link.country_name,
                    "provider_region_id": link.provider_region_id,
                    "artifacts": {},
                },
            )
            if link.kind in package["artifacts"]:
                raise ProviderCollectionError(
                    f"OpenTopoMap has duplicate {link.kind} artifact for {link.region}"
                )
            measurement = measurements[link.source_url]
            if measurement.download_size_bytes <= 0:
                raise ProviderCollectionError(
                    f"OpenTopoMap artifact {link.source_url} has invalid size"
                )
            package["artifacts"][link.kind] = CatalogArtifact(
                id=f"opentopomap-{link.provider_region_id}-{link.kind}",
                kind=link.kind,
                source_url=link.source_url,
                size_bytes=measurement.download_size_bytes,
                install_size_bytes=measurement.install_size_bytes,
                checksum_sha256=None,
                content_type="application/zip",
                required=link.kind == "main",
                validation_status=(
                    "VALIDATED"
                    if measurement.install_size_bytes is not None
                    else "NOT_VALIDATED"
                ),
                install_payload_path=measurement.payload_path,
                source_updated_at=link.source_updated_at,
            )

        if not packages_by_region:
            raise ProviderCollectionError("OpenTopoMap catalog has no Garmin ZIP artifacts")

        fallback_release = _release_label(html)
        packages = []
        for region, value in sorted(packages_by_region.items()):
            artifacts = (value["artifacts"]["main"],)
            source_updated_at = next(
                (
                    artifact.source_updated_at
                    for artifact in artifacts
                    if artifact.source_updated_at is not None
                ),
                None,
            )
            release = (
                f"{source_updated_at.year:04d}-{source_updated_at.month:02d}"
                if source_updated_at is not None
                else fallback_release
            )
            packages.append(
                CatalogPackage(
                    id=f"opentopomap-{value['provider_region_id']}",
                    provider_id=self.definition.id,
                    provider_region_id=value["provider_region_id"],
                    canonical_region_id=region,
                    name=f"OpenTopoMap {value['name']}",
                    region=region,
                    country=value["name"],
                    release=release,
                    release_id=release if release != "unknown" else None,
                    version_label=release if release != "unknown" else None,
                    generated_at=source_updated_at,
                    source_updated_at=source_updated_at,
                    availability="AVAILABLE",
                    country_codes=OPENTOPO_MAP_POLICY_COUNTRY_CODES.get(
                        value["provider_region_id"], ()
                    ),
                    region_kind="multiCountry",
                    tags=(),
                    capabilities=tuple(artifact.kind for artifact in artifacts),
                    artifacts=artifacts,
                )
            )
        return ProviderSnapshot(
            definition=self.definition,
            packages=tuple(packages),
            collected_at=datetime.now(timezone.utc),
        )

    def _measure_links(self, links: list[OpenTopoMapLink]) -> dict[str, Any]:
        unique_urls = tuple(dict.fromkeys(link.source_url for link in links))
        measurements: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            pending = {
                executor.submit(self._measure_with_retry, url): url
                for url in unique_urls
            }
            for future in as_completed(pending):
                url = pending[future]
                try:
                    measurements[url] = future.result()
                except Exception as exc:
                    raise ProviderCollectionError(
                        f"OpenTopoMap artifact inspection failed for {url}: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
        return measurements

    def _measure_with_retry(self, url: str) -> Any:
        failure: Exception | None = None
        for attempt in range(self.measurement_attempts):
            try:
                return self.fetcher.measure_zip(url)
            except Exception as exc:  # provider/network failure is retried narrowly
                failure = exc
                if attempt + 1 < self.measurement_attempts:
                    time.sleep(0.25 * (attempt + 1))
        assert failure is not None
        raise failure


@dataclass(frozen=True)
class OpenTopoMapLink:
    region: str
    country_name: str
    provider_region_id: str
    kind: str
    source_url: str
    source_updated_at: datetime | None


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


class _OpenTopoMapRowParser(HTMLParser):
    """Extract the provider's country rows without executing page scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[list[str], list[tuple[str, str]]]] = []
        self._in_country_row = False
        self._cell_depth = 0
        self._cell_text: list[str] = []
        self._cells: list[str] = []
        self._links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        attributes = dict(attrs)
        if normalized == "tr":
            classes = set((attributes.get("class") or "").split())
            self._in_country_row = "country" in classes
            if self._in_country_row:
                self._cells = []
                self._links = []
        elif self._in_country_row and normalized == "td":
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._cell_text = []
        elif self._in_country_row and normalized == "a":
            self._href = attributes.get("href")
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._in_country_row and self._cell_depth:
            self._cell_text.append(data)
        if self._in_country_row and self._href is not None:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if self._in_country_row and normalized == "a" and self._href is not None:
            self._links.append((self._href, " ".join(self._link_text).strip()))
            self._href = None
            self._link_text = []
        elif self._in_country_row and normalized == "td" and self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(" ".join(" ".join(self._cell_text).split()))
                self._cell_text = []
        elif normalized == "tr" and self._in_country_row:
            self.rows.append((self._cells, self._links))
            self._in_country_row = False


def parse_opentopomap_catalog(html: str, base_url: str) -> list[OpenTopoMapLink]:
    row_parser = _OpenTopoMapRowParser()
    row_parser.feed(html)
    if row_parser.rows:
        return _reconcile_opentopomap_links(
            _parse_opentopomap_rows(row_parser.rows, base_url)
        )

    # Narrow fallback for fixtures or a provider page that temporarily loses
    # its table wrapper. Official identity still comes from the filename.
    parser = _AnchorParser()
    parser.feed(html)
    results: list[OpenTopoMapLink] = []
    for href, anchor_text in parser.links:
        link = _opentopomap_link(href, anchor_text, None, None, base_url)
        if link is not None:
            results.append(link)
    if not results:
        raise ProviderCollectionError("OpenTopoMap catalog has no recognized country ZIP links")
    return _reconcile_opentopomap_links(results)


def _parse_opentopomap_rows(
    rows: list[tuple[list[str], list[tuple[str, str]]]], base_url: str
) -> list[OpenTopoMapLink]:
    results: list[OpenTopoMapLink] = []
    for cells, links in rows:
        country_name = cells[0].strip() if cells else None
        generated_at = _parse_opentopomap_generated_at(cells[-1] if cells else None)
        for href, anchor_text in links:
            link = _opentopomap_link(
                href, anchor_text, country_name, generated_at, base_url
            )
            if link is not None:
                results.append(link)
    if not results:
        raise ProviderCollectionError("OpenTopoMap catalog has no recognized country ZIP links")
    return results


def _reconcile_opentopomap_links(
    links: list[OpenTopoMapLink],
) -> list[OpenTopoMapLink]:
    """Apply explicit provider package relationships visible in the catalog."""

    main_regions = {
        link.provider_region_id for link in links if link.kind == "main"
    }
    reconciled: list[OpenTopoMapLink] = []
    for link in links:
        if link.kind == "contours" and link.provider_region_id == "canada":
            targets = [
                region for region in ("canada-east", "canada-west")
                if region in main_regions
            ]
            if targets:
                for target in targets:
                    reconciled.append(
                        OpenTopoMapLink(
                            region=re.sub(r"[^A-Z0-9]+", "", target.upper()),
                            country_name=_display_name_from_slug(target),
                            provider_region_id=target,
                            kind=link.kind,
                            source_url=link.source_url,
                            source_updated_at=link.source_updated_at,
                        )
                    )
                continue
        reconciled.append(link)
    return reconciled


def _opentopomap_link(
    href: str,
    anchor_text: str,
    country_name: str | None,
    generated_at: datetime | None,
    base_url: str,
) -> OpenTopoMapLink | None:
    source_url = urljoin(base_url, href)
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if not _allowed_opentopomap_host(parsed.hostname):
        return None
    filename = unquote(parsed.path.rsplit("/", 1)[-1])
    filename_match = re.fullmatch(r"(?i)otm-([a-z0-9]+(?:-[a-z0-9]+)*)\.zip", filename)
    if filename_match is None:
        return None
    stem = filename_match.group(1).lower()
    if stem.endswith("-basecamp"):
        return None
    kind = "contours" if stem.endswith("-contours") else "main"
    provider_region_id = stem.removesuffix("-contours")
    normalized_name = (country_name or "").strip()
    if not normalized_name or normalized_name.casefold() in {"garmin", "garmin contours"}:
        normalized_name = _display_name_from_slug(provider_region_id)
    region = re.sub(r"[^A-Z0-9]+", "", provider_region_id.upper())
    if not region:
        return None
    return OpenTopoMapLink(
        region=region,
        country_name=normalized_name,
        provider_region_id=provider_region_id,
        kind=kind,
        source_url=source_url,
        source_updated_at=generated_at,
    )


def _display_name_from_slug(slug: str) -> str:
    words = []
    for word in slug.split("-"):
        words.append(word.upper() if word in {"uk", "us", "usa"} else word.capitalize())
    return "-".join(words)


def _parse_opentopomap_generated_at(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.search(
        r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"
        r"(?:\s+([01]\d|2[0-3]):([0-5]\d):([0-5]\d))?\b",
        value,
    )
    if match is None:
        return None
    hour, minute, second = (int(item or 0) for item in match.groups()[3:])
    return datetime(
        int(match.group(1)), int(match.group(2)), int(match.group(3)),
        hour, minute, second, tzinfo=timezone.utc,
    )


def _release_label(html: str) -> str:
    match = re.search(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.](0?[1-9]|[12]\d|3[01]))?\b", html)
    if not match:
        return "unknown"
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"


def _allowed_opentopomap_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return normalized == "opentopomap.org" or normalized.endswith(".opentopomap.org")


def _as_utc(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

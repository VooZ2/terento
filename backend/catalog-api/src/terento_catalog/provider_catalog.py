"""Provider-neutral catalog records and the reviewed provider adapters.

Adapters are deliberately small. They discover metadata and original source
URLs only; they never proxy or persist provider map binaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import re
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
    ) -> None:
        self.fetcher = fetcher or OpenTopoMapFetcher()
        self.catalog_url = catalog_url or self.definition.catalog_url

    def collect(self) -> ProviderSnapshot:
        html = self.fetcher.fetch_text(self.catalog_url)
        links = parse_opentopomap_catalog(html, self.catalog_url)
        packages_by_region: dict[str, dict[str, Any]] = {}
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
            measurement = self.fetcher.measure_zip(link.source_url)
            if measurement.download_size_bytes <= 0:
                raise ProviderCollectionError(
                    f"OpenTopoMap artifact {link.source_url} has invalid size"
                )
            package["artifacts"][link.kind] = CatalogArtifact(
                id=f"opentopomap-{link.region.lower()}-{link.kind}",
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
            )

        if not packages_by_region:
            raise ProviderCollectionError("OpenTopoMap catalog has no Garmin ZIP artifacts")

        release = _release_label(html)
        packages = []
        for region, value in sorted(packages_by_region.items()):
            artifacts = tuple(
                value["artifacts"][kind]
                for kind in ("main", "contours")
                if kind in value["artifacts"]
            )
            packages.append(
                CatalogPackage(
                    id=f"opentopomap-{region.lower()}",
                    provider_id=self.definition.id,
                    provider_region_id=value["provider_region_id"],
                    canonical_region_id=region,
                    name=f"OpenTopoMap {value['name']}",
                    region=region,
                    country=value["name"],
                    release=release,
                    release_id=release if release != "unknown" else None,
                    version_label=release if release != "unknown" else None,
                    generated_at=None,
                    source_updated_at=None,
                    availability="AVAILABLE",
                    country_codes=(region,),
                    region_kind="country",
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


@dataclass(frozen=True)
class OpenTopoMapLink:
    region: str
    country_name: str
    provider_region_id: str
    kind: str
    source_url: str


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


COUNTRY_CODES: dict[str, str] = {
    "albania": "AL",
    "austria": "AT",
    "belgium": "BE",
    "bulgaria": "BG",
    "croatia": "HR",
    "czech": "CZ",
    "czechia": "CZ",
    "denmark": "DK",
    "estonia": "EE",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "hungary": "HU",
    "ireland": "IE",
    "italy": "IT",
    "latvia": "LV",
    "lithuania": "LT",
    "luxembourg": "LU",
    "netherlands": "NL",
    "norway": "NO",
    "poland": "PL",
    "portugal": "PT",
    "romania": "RO",
    "slovakia": "SK",
    "slovenia": "SI",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "ukraine": "UA",
    "united kingdom": "GB",
}


def parse_opentopomap_catalog(html: str, base_url: str) -> list[OpenTopoMapLink]:
    parser = _AnchorParser()
    parser.feed(html)
    results: list[OpenTopoMapLink] = []
    for href, anchor_text in parser.links:
        source_url = urljoin(base_url, href)
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        if not _allowed_opentopomap_host(parsed.hostname):
            continue
        filename = unquote(parsed.path.rsplit("/", 1)[-1])
        if not filename.lower().endswith(".zip"):
            continue
        combined = f"{filename} {anchor_text}".lower()
        kind = "contours" if "contour" in combined else "main"
        region, country_name = _infer_country(filename, anchor_text)
        if region is None:
            continue
        stem = re.sub(r"(?i)\.zip$", "", filename)
        stem = re.sub(r"(?i)(?:[-_]?(?:contours?|garmin|maps?))+$", "", stem)
        provider_region_id = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-")
        if not provider_region_id:
            provider_region_id = region
        results.append(
            OpenTopoMapLink(
                region=region,
                country_name=country_name,
                provider_region_id=provider_region_id,
                kind=kind,
                source_url=source_url,
            )
        )
    if not results:
        raise ProviderCollectionError("OpenTopoMap catalog has no recognized country ZIP links")
    return results


def _infer_country(filename: str, anchor_text: str) -> tuple[str | None, str]:
    combined = f"{filename} {anchor_text}".lower().replace("_", " ").replace("-", " ")
    for name, code in sorted(COUNTRY_CODES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(name)}\b", combined):
            return code, name.title()
    for token in re.findall(r"\b[A-Za-z]{2,3}\b", combined):
        upper = token.upper()
        if upper in set(COUNTRY_CODES.values()):
            return upper, upper
    return None, "Unknown"


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

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from ...models import CollectedMap, MapMetadata, ProviderMetadata
from .parser import parse_region_downloads, parse_release_page
from .range_zip import (
    HTTPRangeFetcher,
    RangeResponse,
    ZipPayloadMeasurement,
    ZipRangeError,
    ZipRangeInspector,
)

LOGGER = logging.getLogger(__name__)


class Fetcher:
    user_agent = "TerentoCatalog/0.1 (+https://terento.app)"

    def fetch_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")

    def head_size(self, url: str) -> int | None:
        request = Request(
            url,
            method="HEAD",
            headers={"User-Agent": self.user_agent},
        )
        try:
            with urlopen(request, timeout=20) as response:
                value = response.headers.get("Content-Length")
        except OSError as exc:
            LOGGER.warning("Freizeitkarte HEAD failed; size remains unknown: %s", exc)
            return None
        if value is None:
            return None
        try:
            size = int(value)
        except ValueError:
            return None
        return size if size >= 0 else None

    def fetch_range(self, url: str, start: int, end: int) -> RangeResponse:
        return HTTPRangeFetcher().fetch_range(url, start, end)

    def measure_zip(self, url: str) -> ZipPayloadMeasurement:
        return ZipRangeInspector(self).inspect(url, expected_payload_path="gmapsupp.img")


@dataclass(frozen=True)
class FreizeitkarteCollector:
    fetcher: Fetcher | None = None
    release_url: str = "https://www.freizeitkarte-osm.de/garmin/en/release.html"
    map_page_urls: tuple[str, ...] = (
        "https://www.freizeitkarte-osm.de/garmin/en/nordeuropa.html",
        "https://www.freizeitkarte-osm.de/garmin/en/osteuropa.html",
        "https://www.freizeitkarte-osm.de/garmin/en/suedosteuropa.html",
        "https://www.freizeitkarte-osm.de/garmin/en/suedeuropa.html",
        "https://www.freizeitkarte-osm.de/garmin/en/westeuropa.html",
        "https://www.freizeitkarte-osm.de/garmin/en/mitteleuropa.html",
        "https://www.freizeitkarte-osm.de/garmin/en/sonstigelaender.html",
    )
    map_base_url: str = "https://www.freizeitkarte-osm.de/garmin/en/"

    def collect(self) -> list[CollectedMap]:
        fetcher = self.fetcher or Fetcher()
        release = parse_release_page(fetcher.fetch_text(self.release_url))

        provider = ProviderMetadata(
            id="freizeitkarte",
            name="Freizeitkarte",
            website="https://www.freizeitkarte-osm.de/garmin/en/index.html",
            license_information=(
                "Map data © OpenStreetMap contributors (ODbL); produced map © FZK "
                "project. Contour-line sources vary by region."
            ),
            attribution=(
                "Map data © OpenStreetMap contributors; produced map © FZK project"
            ),
            license_url="https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
        )
        downloads = []
        for map_page_url in self.map_page_urls:
            page_downloads = parse_region_downloads(
                fetcher.fetch_text(map_page_url),
                base_url=self.map_base_url,
            )
            downloads.extend(page_downloads)

        records: list[CollectedMap] = []
        seen_map_ids: set[str] = set()
        for download in downloads:
            map_id = _map_id(download.identifier)
            if map_id in seen_map_ids:
                raise RuntimeError(
                    f"Freizeitkarte source produced duplicate map identifier: {download.identifier}"
                )
            seen_map_ids.add(map_id)
            measurement = _measure_download(fetcher, download.source_url)
            download_size = measurement.download_size_bytes or None
            records.append(
                CollectedMap(
                    provider=provider,
                    map=MapMetadata(
                        id=map_id,
                        provider_id=provider.id,
                        name=download.name,
                        region=download.region,
                        country=download.name,
                        identifier=download.identifier,
                    ),
                    version=release.version,
                    raw_version=release.raw_version,
                    file_size_bytes=download_size,
                    source_url=download.source_url,
                    release_date=release.release_date,
                    download_size_bytes=download_size,
                    install_size_bytes=measurement.install_size_bytes,
                    install_payload_path=measurement.payload_path,
                    size_measurement_method=measurement.method,
                    size_measured_at=(
                        datetime.now(timezone.utc)
                        if download_size is not None
                        else None
                    ),
                    size_measurement_warning=measurement.warning,
                )
            )
        if not records:
            raise RuntimeError("Freizeitkarte collector returned no map packages")
        LOGGER.info(
            "Freizeitkarte release %s: collected %d map packages",
            release.raw_version,
            len(records),
        )
        return records


def _measure_download(fetcher: Fetcher, url: str) -> ZipPayloadMeasurement:
    """Measure package and IMG sizes without downloading the package body."""

    measure_zip = getattr(fetcher, "measure_zip", None)
    if callable(measure_zip):
        try:
            return measure_zip(url)
        except ZipRangeError as exc:
            # A provider-side ZIP/Range problem must not erase a previously
            # known-good value during the database upsert. Keep a HEAD size
            # when available and leave install size unknown.
            LOGGER.warning("Freizeitkarte ZIP size inspection failed for %s: %s", url, exc)
            return ZipPayloadMeasurement(
                download_size_bytes=fetcher.head_size(url) or 0,
                install_size_bytes=None,
                payload_path=None,
                method="head-content-length-fallback",
                warning=str(exc),
            )

    # Small test doubles and older integrations may only expose HEAD. Keeping
    # this fallback preserves the metadata collector's non-downloading API.
    return ZipPayloadMeasurement(
        download_size_bytes=fetcher.head_size(url) or 0,
        install_size_bytes=None,
        payload_path=None,
        method="head-content-length",
        warning="ZIP central-directory inspection is unavailable",
    )


def _map_id(identifier: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "-"
        for character in identifier
    ).strip("-")
    return f"freizeitkarte-{slug}"

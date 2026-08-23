from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html import unescape
from urllib.parse import urljoin, urlparse

from ...models import NormalizedVersion


@dataclass(frozen=True)
class ReleaseMetadata:
    raw_version: str
    version: NormalizedVersion
    release_date: date | None


@dataclass(frozen=True)
class RegionDownload:
    region: str
    name: str
    identifier: str
    source_url: str


class ProviderPageParseError(ValueError):
    pass


def parse_release_page(html: str) -> ReleaseMetadata:
    text = _plain_text(html)

    release_match = re.search(
        r'(?i)maps?\s+["“]?([0-9]{1,2}/[0-9]{4})["”]?', text
    )
    data_match = re.search(
        r"(?i)(?:OSM|OpenStreetMap)\s+data\s+of\s+(\d{4})/(\d{1,2})/(\d{1,2})",
        text,
    )
    legacy_match = re.search(
        r"(?i)\bRelease\s+[\"“]?([0-9]{2})[./-](0?[1-9]|1[0-2])[\"”]?\b",
        text,
    )

    release_date: date | None = None
    if data_match:
        try:
            release_date = date(
                int(data_match.group(1)),
                int(data_match.group(2)),
                int(data_match.group(3)),
            )
        except ValueError as exc:
            raise ProviderPageParseError("invalid Freizeitkarte data date") from exc

    if release_match and release_date:
        raw_version = release_match.group(1)
        version = NormalizedVersion(release_date.year, release_date.month)
        return ReleaseMetadata(raw_version, version, release_date)

    if legacy_match:
        raw_version = f"Release {legacy_match.group(1)}.{legacy_match.group(2)}"
        version = NormalizedVersion(
            2000 + int(legacy_match.group(1)),
            int(legacy_match.group(2)),
        )
        return ReleaseMetadata(raw_version, version, release_date)

    raise ProviderPageParseError(
        "Freizeitkarte release page has no supported release and source-date signal"
    )


def parse_region_download(
    html: str,
    *,
    region_code: str,
    base_url: str,
) -> str:
    for download in parse_region_downloads(html, base_url=base_url):
        if download.region == region_code:
            return download.source_url
    raise ProviderPageParseError(f"Freizeitkarte region section not found: {region_code}")


def parse_region_downloads(html: str, *, base_url: str) -> list[RegionDownload]:
    """Parse one official Garmin regional page into one preferred package per map.

    Freizeitkarte publishes several language variants for some regions. Terento
    prefers the English package and falls back to the first published variant
    when an English package does not exist. The archive is never downloaded by
    this parser.
    """

    section_pattern = re.compile(
        r'<h3[^>]*>\s*<a[^>]*id=["\'](?P<region>[^"\']+)["\'][^>]*>'
        r"(?P<title>.*?)</a>\s*</h3>(?P<section>.*?)(?=<h3\b|</body>|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    results: list[RegionDownload] = []
    for section_match in section_pattern.finditer(html):
        links: list[tuple[str, str, str]] = []
        for link_match in re.finditer(
            r'<a[^>]+href=["\']([^"\']*gmapsupp\.img\.zip)["\']',
            section_match.group("section"),
            re.IGNORECASE,
        ):
            source_url = urljoin(base_url, unescape(link_match.group(1)))
            parsed = urlparse(source_url)
            filename = parsed.path.rsplit("/", 1)[-1]
            filename_match = re.fullmatch(
                r"(?P<identifier>.+)_(?P<language>[a-z]{2})_gmapsupp\.img\.zip",
                filename,
                re.IGNORECASE,
            )
            if filename_match is None:
                continue
            links.append(
                (
                    filename_match.group("language").lower(),
                    filename_match.group("identifier"),
                    source_url,
                )
            )

        if not links:
            continue

        _, identifier, source_url = next(
            (item for item in links if item[0] == "en"),
            links[0],
        )
        results.append(
            RegionDownload(
                region=section_match.group("region").strip(),
                name=_region_name(section_match.group("title"), identifier),
                identifier=identifier,
                source_url=source_url,
            )
        )
    if not results:
        raise ProviderPageParseError("Freizeitkarte page has no Garmin map packages")
    return results


def _region_name(title_html: str, identifier: str) -> str:
    title = _plain_text(title_html).rstrip(":").strip()
    title = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    return title or identifier


def _plain_text(html: str) -> str:
    without_scripts = re.sub(
        r"(?is)<(script|style).*?</\1>", " ", html
    )
    text = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return " ".join(unescape(text).split())

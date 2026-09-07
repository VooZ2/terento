"""Fail-closed OpenTopoMap contour source audit.

The audit is intentionally separate from the public collector. It may inspect
every contour link and record shadow health, but it never changes the public
catalog mode and never stores provider binaries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import tempfile
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

from .collectors.freizeitkarte.range_zip import ZipRangeError
from .provider_catalog import (
    OPENTOPO_MAP_BETA8_MAIN_PACKAGE_COUNT,
    OPENTOPO_MAP,
    OpenTopoMapFetcher,
    OpenTopoMapLink,
    parse_opentopomap_catalog,
)


@dataclass(frozen=True)
class ContourPayloadCheck:
    region: str
    source_url: str
    payload_path: str | None
    download_size_bytes: int | None
    install_size_bytes: int | None
    status: str
    reason: str | None = None
    header_identity: str | None = None


@dataclass(frozen=True)
class OpenTopoMapContourAuditReport:
    schema_version: int
    source_url: str
    main_package_count: int
    expected_main_package_count: int
    unique_contour_source_count: int
    package_to_contour_attachment_count: int
    validated_contours: int
    missing_contours: int
    unavailable_contours: int
    rejected_contours: int
    shared_contour_sources: int
    unknown_install_sizes: int
    duplicate_identities: int
    payload_path_patterns: tuple[str, ...]
    minimum_install_size_bytes: int | None
    maximum_install_size_bytes: int | None
    sample_region: str | None
    sample_status: str
    sample_reason: str | None
    contours: tuple[ContourPayloadCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_opentopomap_contours(
    *,
    fetcher: OpenTopoMapFetcher | None = None,
    expected_main_package_count: int = OPENTOPO_MAP_BETA8_MAIN_PACKAGE_COUNT,
    sample_region: str | None = None,
    max_workers: int = 8,
) -> OpenTopoMapContourAuditReport:
    fetcher = fetcher or OpenTopoMapFetcher()
    html = fetcher.fetch_text(OPENTOPO_MAP.catalog_url)
    links = parse_opentopomap_catalog(html, OPENTOPO_MAP.catalog_url)
    main_links = [link for link in links if link.kind == "main"]
    contour_links = [link for link in links if link.kind == "contours"]

    if len(main_links) != expected_main_package_count:
        raise RuntimeError(
            "OpenTopoMap main catalog count changed: "
            f"expected {expected_main_package_count}, found {len(main_links)}"
        )

    duplicate_identities = len(contour_links) - len({
        (link.provider_region_id, link.source_url) for link in contour_links
    })
    source_counts: dict[str, int] = {}
    for link in contour_links:
        source_counts[link.source_url] = source_counts.get(link.source_url, 0) + 1

    def inspect(link: OpenTopoMapLink) -> ContourPayloadCheck:
        try:
            measurement = fetcher.measure_zip(link.source_url)
            install_size = measurement.install_size_bytes
            status = "VALIDATED" if install_size is not None and install_size > 0 else "UNKNOWN_SIZE"
            return ContourPayloadCheck(
                region=link.provider_region_id,
                source_url=link.source_url,
                payload_path=measurement.payload_path,
                download_size_bytes=measurement.download_size_bytes,
                install_size_bytes=install_size,
                status=status,
                reason=None if status == "VALIDATED" else "exact install size unavailable",
            )
        except (OSError, ValueError, ZipRangeError) as exc:
            return ContourPayloadCheck(
                region=link.provider_region_id,
                source_url=link.source_url,
                payload_path=None,
                download_size_bytes=None,
                install_size_bytes=None,
                status="UNAVAILABLE",
                reason=f"{type(exc).__name__}: {exc}",
            )

    checks_by_url: dict[str, ContourPayloadCheck] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 16))) as executor:
        pending = {
            executor.submit(inspect, link): link.source_url
            for link in contour_links
        }
        for future in as_completed(pending):
            check = future.result()
            checks_by_url.setdefault(check.source_url, check)
    checks = [
        checks_by_url[link.source_url]
        for link in contour_links
        if link.source_url in checks_by_url
    ]

    sample_check = _sample_contour_payload(contour_links, sample_region)
    sizes = [item.install_size_bytes for item in checks if item.install_size_bytes]
    payload_paths = tuple(sorted({item.payload_path for item in checks if item.payload_path}))
    return OpenTopoMapContourAuditReport(
        schema_version=1,
        source_url=OPENTOPO_MAP.catalog_url,
        main_package_count=len(main_links),
        expected_main_package_count=expected_main_package_count,
        unique_contour_source_count=len(source_counts),
        package_to_contour_attachment_count=len(contour_links),
        validated_contours=sum(item.status == "VALIDATED" for item in checks),
        missing_contours=len(main_links) - len({item.region for item in contour_links}),
        unavailable_contours=sum(item.status == "UNAVAILABLE" for item in checks),
        rejected_contours=sum(item.status == "REJECTED" for item in checks),
        shared_contour_sources=sum(count > 1 for count in source_counts.values()),
        unknown_install_sizes=sum(item.status == "UNKNOWN_SIZE" for item in checks),
        duplicate_identities=max(0, duplicate_identities),
        payload_path_patterns=payload_paths,
        minimum_install_size_bytes=min(sizes) if sizes else None,
        maximum_install_size_bytes=max(sizes) if sizes else None,
        sample_region=sample_region,
        sample_status=sample_check[0],
        sample_reason=sample_check[1],
        contours=tuple(checks),
    )


def _sample_contour_payload(
    links: list[OpenTopoMapLink],
    requested_region: str | None,
) -> tuple[str, str | None]:
    if not requested_region:
        return "NOT_REQUESTED", None
    normalized = requested_region.strip().casefold()
    link = next(
        (item for item in links if item.provider_region_id.casefold() == normalized),
        None,
    )
    if link is None:
        return "REJECTED", "requested sample region has no contour source"

    parsed = urlparse(link.source_url)
    if parsed.scheme != "https" or parsed.hostname != "garmin.opentopomap.org":
        return "REJECTED", "sample source is outside the reviewed OpenTopoMap host"

    try:
        request = Request(
            link.source_url,
            headers={"User-Agent": OpenTopoMapFetcher.user_agent},
        )
        with urlopen(request, timeout=60) as response:
            final_url = response.geturl()
            if urlparse(final_url).hostname != parsed.hostname:
                return "REJECTED", "sample download redirected to another host"
            with tempfile.TemporaryDirectory(prefix="terento-otm-contour-sample-") as directory:
                archive = Path(directory) / "sample.zip"
                with archive.open("wb") as output:
                    total = 0
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > 512 * 1024 * 1024:
                            return "REJECTED", "sample archive exceeded bounded audit size"
                        output.write(chunk)
                with zipfile.ZipFile(archive) as package:
                    names = [
                        name for name in package.namelist()
                        if not name.endswith("/") and name.casefold().endswith(".img")
                    ]
                    if len(names) != 1:
                        return "REJECTED", "sample contour ZIP does not have one IMG payload"
                    payload = package.open(names[0])
                    header = payload.read(4096)
                    if header[0x10:0x16] != b"DSKIMG" or header[0x41:0x47] != b"GARMIN":
                        return "REJECTED", "sample payload is not a Garmin IMG"
                    printable = "".join(
                        chr(byte) if 32 <= byte <= 126 else " "
                        for byte in header
                    ).casefold()
                    normalized_header = "".join(
                        character for character in printable if character.isalnum()
                    )
                    normalized_region = "".join(
                        character
                        for character in link.provider_region_id.casefold()
                        if character.isalnum()
                    )
                    if "opentopomap" not in normalized_header:
                        return "REJECTED", "sample IMG does not identify OpenTopoMap"
                    if normalized_region not in normalized_header:
                        return "REJECTED", "sample IMG does not identify the selected region"
                    return "VALIDATED", f"OpenTopoMap:{link.provider_region_id}:{names[0]}"
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        return "UNAVAILABLE", f"{type(exc).__name__}: {exc}"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Audit OpenTopoMap contour metadata")
    parser.add_argument("--sample-region", default="andorra")
    parser.add_argument("--expected-main-count", type=int, default=OPENTOPO_MAP_BETA8_MAIN_PACKAGE_COUNT)
    args = parser.parse_args()
    report = audit_opentopomap_contours(
        expected_main_package_count=args.expected_main_count,
        sample_region=args.sample_region,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()


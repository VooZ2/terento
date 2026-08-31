"""Bounded, metadata-only provider health checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Iterable, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .collectors.freizeitkarte.range_zip import HTTPRangeFetcher, ZipRangeError, ZipRangeInspector
from .provider_catalog import ProviderDefinition


MAX_TEXT_BYTES = 128 * 1024
MAX_DOWNLOAD_CHECKS = 8


@dataclass(frozen=True)
class HTTPProbeResult:
    status_code: int
    final_url: str
    content_type: str | None
    body_prefix: bytes = b""
    body: bytes = b""


class ProviderProbe(Protocol):
    def inspect(self, url: str, *, read_body: bool = False) -> HTTPProbeResult: ...

    def inspect_magic(self, url: str) -> bytes: ...

    def inspect_zip(self, url: str): ...


class DefaultProviderProbe:
    user_agent = "TerentoCatalog/0.1 (+https://terento.app)"

    def inspect(self, url: str, *, read_body: bool = False) -> HTTPProbeResult:
        request = Request(
            url,
            method="GET" if read_body else "HEAD",
            headers={"User-Agent": self.user_agent},
        )
        with urlopen(request, timeout=15) as response:
            body = response.read(MAX_TEXT_BYTES + 1) if read_body else b""
            if len(body) > MAX_TEXT_BYTES:
                body = body[:MAX_TEXT_BYTES]
            return HTTPProbeResult(
                status_code=int(getattr(response, "status", 200)),
                final_url=response.geturl(),
                content_type=response.headers.get("Content-Type"),
                body_prefix=body[:16],
                body=body,
            )

    def inspect_zip(self, url: str):
        return ZipRangeInspector(HTTPRangeFetcher(timeout_seconds=15)).inspect(
            url, expected_payload_path=None
        )

    def inspect_magic(self, url: str) -> bytes:
        return HTTPRangeFetcher(timeout_seconds=15).fetch_range(url, 0, 3).body


@dataclass(frozen=True)
class ProviderHealthResult:
    provider_id: str
    status: str
    website_status: str
    catalog_status: str
    redirect_status: str
    download_status: str
    mime_status: str
    magic_status: str
    zip_status: str
    img_status: str
    last_update_status: str
    http_status: int | None
    final_url: str | None
    content_type: str | None
    artifact_count: int
    source_updated_at: str | None
    error_code: str | None
    error_detail: str | None
    duration_ms: int

    def as_database_values(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "website_status": self.website_status,
            "catalog_status": self.catalog_status,
            "redirect_status": self.redirect_status,
            "download_status": self.download_status,
            "mime_status": self.mime_status,
            "magic_status": self.magic_status,
            "zip_status": self.zip_status,
            "img_status": self.img_status,
            "last_update_status": self.last_update_status,
            "http_status": self.http_status,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "artifact_count": self.artifact_count,
            "source_updated_at": self.source_updated_at,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "duration_ms": self.duration_ms,
        }


def check_provider(
    definition: ProviderDefinition,
    *,
    download_urls: Iterable[str] = (),
    source_updated_at: str | None = None,
    probe: ProviderProbe | None = None,
) -> ProviderHealthResult:
    """Run a bounded provider/source check without downloading map archives."""

    started = time.monotonic()
    probe = probe or DefaultProviderProbe()
    errors: list[str] = []
    website_status, catalog_status = "UNKNOWN", "UNKNOWN"
    redirect_status, download_status = "UNKNOWN", "UNKNOWN"
    mime_status, magic_status, zip_status, img_status = (
        "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"
    )
    http_status: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    checked_downloads = 0

    website = _safe_inspect(probe, definition.website, read_body=False)
    if website is None:
        website_status = "DOWN"
        errors.append("website_unreachable")
    else:
        http_status = website.status_code
        final_url = website.final_url
        website_status = "HEALTHY" if 200 <= website.status_code < 400 else "DOWN"
        redirect_status = "HEALTHY" if _same_host(definition.website, website.final_url) else "DOWN"
        if redirect_status == "DOWN":
            errors.append("website_redirect_host")

    catalog = _safe_inspect(probe, definition.catalog_url, read_body=True)
    if catalog is None:
        catalog_status = "DOWN"
        errors.append("catalog_unreachable")
    else:
        catalog_status = "HEALTHY" if 200 <= catalog.status_code < 400 else "DOWN"
        if not _same_host(definition.catalog_url, catalog.final_url):
            redirect_status = "DOWN"
            errors.append("catalog_redirect_host")
        if catalog.status_code < 200 or catalog.status_code >= 400:
            errors.append("catalog_http")
        elif not catalog.body:
            catalog_status = "DEGRADED"
            errors.append("catalog_body_empty")

    for url in list(download_urls)[:MAX_DOWNLOAD_CHECKS]:
        checked_downloads += 1
        artifact = _safe_inspect(probe, url, read_body=False)
        if artifact is None:
            errors.append("download_unreachable")
            continue
        final_url = artifact.final_url
        http_status = artifact.status_code
        content_type = artifact.content_type
        if not _same_host(url, artifact.final_url):
            redirect_status = "DOWN"
            errors.append("download_redirect_host")
        if 200 <= artifact.status_code < 400:
            download_status = "HEALTHY"
        else:
            download_status = "DOWN"
            errors.append("download_http")
        if artifact.content_type and "zip" in artifact.content_type.lower():
            mime_status = "HEALTHY"
        else:
            mime_status = "DEGRADED"
            errors.append("download_mime")
        try:
            inspect_magic = getattr(probe, "inspect_magic", None)
            prefix = (
                inspect_magic(url)
                if callable(inspect_magic)
                else artifact.body_prefix
            )
            if prefix[:4] in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"}:
                magic_status = "HEALTHY"
            else:
                magic_status = "DEGRADED"
                errors.append("download_magic")
        except (OSError, ValueError, ZipRangeError):
            magic_status = "UNKNOWN"
            errors.append("magic_check")
        try:
            measurement = probe.inspect_zip(url)
            zip_status = "HEALTHY"
            img_status = "HEALTHY" if measurement.install_size_bytes else "DEGRADED"
            if not measurement.install_size_bytes:
                errors.append("img_missing")
        except (OSError, ValueError, ZipRangeError) as exc:
            zip_status = "DEGRADED"
            img_status = "UNKNOWN"
            errors.append(f"zip_check:{type(exc).__name__}")

    if checked_downloads == 0:
        download_status = "UNKNOWN"
        mime_status = "UNKNOWN"
        magic_status = "UNKNOWN"
        zip_status = "UNKNOWN"
        img_status = "UNKNOWN"
    elif download_status == "UNKNOWN":
        download_status = "DOWN"

    last_update_status = _last_update_status(source_updated_at)
    availability_statuses = {
        website_status,
        catalog_status,
        redirect_status,
    }
    if checked_downloads:
        availability_statuses.update(
            {download_status, mime_status, magic_status, zip_status, img_status}
        )
    if "DOWN" in availability_statuses:
        status = "DOWN"
    elif "DEGRADED" in availability_statuses or last_update_status == "DEGRADED":
        status = "DEGRADED"
    elif "UNKNOWN" in availability_statuses:
        status = "UNKNOWN"
    else:
        status = "HEALTHY"

    return ProviderHealthResult(
        provider_id=definition.id,
        status=status,
        website_status=website_status,
        catalog_status=catalog_status,
        redirect_status=redirect_status,
        download_status=download_status,
        mime_status=mime_status,
        magic_status=magic_status,
        zip_status=zip_status,
        img_status=img_status,
        last_update_status=last_update_status,
        http_status=http_status,
        final_url=final_url,
        content_type=content_type,
        artifact_count=checked_downloads,
        source_updated_at=source_updated_at,
        error_code=errors[0] if errors else None,
        error_detail=", ".join(errors[:8]) if errors else None,
        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
    )


def _safe_inspect(
    probe: ProviderProbe, url: str, *, read_body: bool
) -> HTTPProbeResult | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        result = probe.inspect(url, read_body=read_body)
        final = urlparse(result.final_url)
        if final.scheme != "https" or not final.hostname:
            return None
        return result
    except (OSError, ValueError):
        return None


def _same_host(original: str, final: str) -> bool:
    return urlparse(original).hostname == urlparse(final).hostname


def _last_update_status(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "UNKNOWN"
    if parsed.tzinfo is None:
        return "UNKNOWN"
    age_days = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 86_400
    if age_days < -1:
        return "DEGRADED"
    if age_days > 180:
        return "DEGRADED"
    return "HEALTHY"

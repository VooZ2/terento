"""Bounded, metadata-only provider health checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from email.utils import parsedate_to_datetime
from itertools import islice
from urllib.error import HTTPError
from typing import Iterable, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .collectors.freizeitkarte.range_zip import HTTPRangeFetcher, ZipRangeError, ZipRangeInspector
from .provider_catalog import ProviderDefinition, ProviderCollectionError


MAX_TEXT_BYTES = 128 * 1024
MAX_DOWNLOAD_CHECKS = 8


@dataclass(frozen=True)
class HTTPProbeResult:
    status_code: int
    final_url: str
    content_type: str | None
    body_prefix: bytes = b""
    body: bytes = b""
    retry_after: str | None = None


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
                retry_after=response.headers.get("Retry-After"),
            )

    def inspect_zip(self, url: str):
        if url.startswith(("https://data.bbbike.org/osm/garmin/region/", "https://data.bbbike.org/osm/garmin/example/")):
            from .bbbike import ARTIFACT_ROOT, EXAMPLE_ROOT, inspect_bbbike
            suffix = url[len(EXAMPLE_ROOT if url.startswith(EXAMPLE_ROOT) else ARTIFACT_ROOT):]
            path = suffix.rsplit("/", 1)[0]
            map_type = suffix.rsplit(".osm.garmin-", 1)[-1].removesuffix(".zip")
            return inspect_bbbike(url, path, map_type)
        return ZipRangeInspector(HTTPRangeFetcher(timeout_seconds=15)).inspect(
            url, expected_payload_path=None
        )

    def inspect_img(self, url: str):
        from .maprando import inspect_maprando_img
        return inspect_maprando_img(url)

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
    retry_after_seconds: int | None = None

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
            "retry_after_seconds": self.retry_after_seconds,
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

    catalog = None if website is not None and website.status_code == 429 else _safe_inspect(probe, definition.catalog_url, read_body=True)
    if catalog is None:
        if website is not None and website.status_code == 429:
            errors.append("catalog_not_evaluated:rate_limited")
        else:
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

    sample_statuses: list[str] = []
    details: dict[str, list[str]] = {key: [] for key in ("mime", "magic", "zip", "img")}
    rate_limited = next((response for response in (website, catalog)
                         if response is not None and response.status_code == 429), None)
    retry_after_seconds = _retry_after_seconds(rate_limited.retry_after) if rate_limited else None
    if rate_limited:
        errors.append("rate_limited:remaining_checks_not_evaluated")

    for url in (() if rate_limited else islice(download_urls, MAX_DOWNLOAD_CHECKS)):
        checked_downloads += 1
        artifact = _safe_inspect(probe, url, read_body=False)
        if artifact is None:
            sample_statuses.append("DOWN")
            errors.append("download_unreachable:validation_not_evaluated")
            for values in details.values():
                values.append("UNKNOWN")
            continue
        final_url = artifact.final_url
        http_status = artifact.status_code
        content_type = artifact.content_type
        if artifact.status_code == 429:
            sample_statuses.append("DEGRADED")
            retry_after_seconds = _retry_after_seconds(artifact.retry_after)
            errors.append("rate_limited:remaining_checks_not_evaluated")
            break
        if not 200 <= artifact.status_code < 400:
            sample_statuses.append("DOWN" if artifact.status_code >= 500 else "DEGRADED")
            errors.append(f"download_http_{artifact.status_code}:validation_not_evaluated")
            for values in details.values():
                values.append("UNKNOWN")
            continue
        sample = {key: "UNKNOWN" for key in details}
        safe_redirect = _same_host(url, artifact.final_url)
        if not safe_redirect:
            redirect_status = "DOWN"
            errors.append("download_redirect_host")
            sample_statuses.append("DEGRADED")
            for values in details.values():
                values.append("UNKNOWN")
            continue
        raw_img = definition.id == "maprando" and urlparse(url).path.lower().endswith(".img")
        if artifact.content_type and ("zip" in artifact.content_type.lower() or (raw_img and artifact.content_type.split(";", 1)[0].lower() in {"application/octet-stream", "application/x-garmin-img"})):
            sample["mime"] = "HEALTHY"
        else:
            sample["mime"] = "DEGRADED"
            errors.append("download_mime")
        try:
            if raw_img:
                sample["zip"] = "NOT_APPLICABLE"
                inspect_img = getattr(probe, "inspect_img", None)
                if inspect_img is None or not inspect_img(url).identity_validated:
                    raise ValueError("IMG identity unavailable")
                sample["magic"] = sample["img"] = "HEALTHY"
            else:
                inspect_magic = getattr(probe, "inspect_magic", None)
                prefix = inspect_magic(url) if callable(inspect_magic) else artifact.body_prefix
                sample["magic"] = "HEALTHY" if prefix[:4] in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"} else "DEGRADED"
                if sample["magic"] == "DEGRADED":
                    errors.append("download_magic")
                measurement = probe.inspect_zip(url)
                sample["zip"] = "HEALTHY"
                sample["img"] = "HEALTHY" if measurement.install_size_bytes else "DEGRADED"
                if sample["img"] == "DEGRADED":
                    errors.append("img_missing")
        except HTTPError as exc:
            if exc.code == 429:
                retry_after_seconds = _retry_after_seconds(exc.headers.get("Retry-After") if exc.headers else None)
                errors.append("rate_limited:remaining_checks_not_evaluated")
            else:
                errors.append(f"package_http_{exc.code}")
            sample["img"] = "DEGRADED"
        except (OSError, ValueError, ZipRangeError, ProviderCollectionError) as exc:
            errors.append(f"package_check:{type(exc).__name__}")
            sample["img"] = "DEGRADED"
        sample_statuses.append("HEALTHY" if all(value in {"HEALTHY", "NOT_APPLICABLE"} for value in sample.values()) else "DEGRADED")
        for key, values in details.items():
            values.append(sample[key])
        if retry_after_seconds is not None:
            break

    download_status = "DEGRADED" if rate_limited else _aggregate(sample_statuses)
    mime_status, magic_status, zip_status, img_status = (_aggregate(details[key]) for key in details)
    if not checked_downloads and not rate_limited:
        errors.append("download_not_evaluated:no_samples")

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
        retry_after_seconds=retry_after_seconds,
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
    except HTTPError as exc:
        return HTTPProbeResult(exc.code, exc.geturl(), exc.headers.get("Content-Type") if exc.headers else None, retry_after=exc.headers.get("Retry-After") if exc.headers else None)
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


def _aggregate(statuses: list[str]) -> str:
    if not statuses:
        return "UNKNOWN"
    unique = set(statuses)
    if len(unique) == 1:
        return statuses[0]
    if unique <= {"HEALTHY", "NOT_APPLICABLE"}:
        return "HEALTHY"
    return "DEGRADED"


def _retry_after_seconds(value: str | None) -> int:
    """Respect server cooldown; use an hour when the header is absent/invalid."""
    if value:
        try:
            return max(60, min(604800, int(value)))
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                return max(60, min(604800, int((date - datetime.now(timezone.utc)).total_seconds())))
            except (TypeError, ValueError, OverflowError):
                pass
    return 3600

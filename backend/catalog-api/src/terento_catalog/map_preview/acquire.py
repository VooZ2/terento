"""Temporary, polite download of a provider map for preview rendering only.

Only reviewed provider hosts and path shapes are accepted, redirects are
refused, the transfer and extraction are size-capped, and every file lives
in a per-job work directory that the caller deletes in ``finally``. Nothing
here is served; the source map is removed as soon as its tiles are drawn.
"""
from __future__ import annotations

import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.parse import unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

USER_AGENT = "TerentoCatalog/0.1 (+https://terento.app)"
CHUNK = 1024 * 1024

ALLOWED_SOURCES: dict[str, tuple[set[str], re.Pattern[str]]] = {
    "freizeitkarte": (
        {"download.freizeitkarte-osm.de", "freizeitkarte-osm.de"},
        re.compile(r"/garmin/[^/]+/[^/]+_gmapsupp\.img\.zip"),
    ),
    "opentopomap": (
        {"garmin.opentopomap.org"},
        re.compile(r"/[a-z-]+/[a-z0-9-]+/otm-[a-z0-9-]+\.zip"),
    ),
    "maprando": (
        {"ravenfeld.fr"},
        re.compile(r"/MapRando/[^/]+/MapRando_[^/]+\.img"),
    ),
    "bbbike": (
        {"data.bbbike.org"},
        re.compile(r"/osm/garmin/region/[a-z0-9/_-]+\.osm\.garmin-(?:bbbike|ontrail)-latin1\.zip"),
    ),
}


class AcquisitionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retry_not_before: datetime | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_not_before = retry_not_before


@dataclass(frozen=True)
class Limits:
    max_source_bytes: int
    min_free_bytes: int


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        raise AcquisitionError("redirect_refused", "Source redirect requires review")


def reviewed_url(provider_id: str, url: str) -> str:
    rule = ALLOWED_SOURCES.get(provider_id)
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if (
        rule is None
        or parsed.scheme != "https"
        or parsed.hostname not in rule[0]
        or parsed.username or parsed.password or parsed.port
        or parsed.query or parsed.fragment
        or any(part in {".", ".."} for part in path.split("/"))
        or not rule[1].fullmatch(path)
    ):
        raise AcquisitionError("unreviewed_source", "Source URL is outside the reviewed provider paths")
    return url


def ensure_free_space(directory: Path, needed: int, limits: Limits) -> None:
    free = shutil.disk_usage(directory).free
    if free - needed < limits.min_free_bytes:
        raise AcquisitionError(
            "disk_space",
            f"Not enough free disk space: {free} bytes free, {needed} needed, "
            f"{limits.min_free_bytes} must stay free",
        )


def download(
    provider_id: str,
    url: str,
    destination: Path,
    *,
    expected_bytes: int,
    limits: Limits,
    opener=None,
    timeout_seconds: int = 60,
) -> Path:
    reviewed_url(provider_id, url)
    cap = min(limits.max_source_bytes, max(expected_bytes, 1) * 2 + CHUNK)
    if expected_bytes > limits.max_source_bytes:
        raise AcquisitionError("too_large", f"Source is {expected_bytes} bytes; limit is {limits.max_source_bytes}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ensure_free_space(destination.parent, cap, limits)
    opener = opener or build_opener(_NoRedirect())
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    written = 0
    try:
        with opener.open(request, timeout=timeout_seconds) as response, destination.open("wb") as handle:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > cap:
                    raise AcquisitionError("too_large", f"Source exceeded {cap} bytes")
                handle.write(chunk)
    except HTTPError as error:
        destination.unlink(missing_ok=True)
        if error.code == 429:
            raise AcquisitionError(
                "rate_limited", "Provider rate limit reached",
                retry_not_before=_retry_after(error.headers.get("Retry-After") if error.headers else None),
            ) from error
        raise AcquisitionError("http_error", f"Provider returned HTTP {error.code}") from error
    except AcquisitionError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise AcquisitionError("network_error", f"Source could not be downloaded: {error}") from error
    if written == 0:
        destination.unlink(missing_ok=True)
        raise AcquisitionError("empty_source", "Source was empty")
    return destination


def extract_img(archive: Path, work_dir: Path, limits: Limits) -> Path:
    """Return the Garmin IMG inside ``archive`` (or ``archive`` itself)."""
    if archive.suffix.lower() == ".img":
        return archive
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [
                info for info in bundle.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".img")
            ]
            if not members:
                raise AcquisitionError("no_img", "Archive contains no Garmin IMG")
            preferred = [info for info in members if PurePosixPath(info.filename).name.lower() == "gmapsupp.img"]
            member = (preferred or sorted(members, key=lambda info: info.file_size, reverse=True))[0]
            if member.file_size > limits.max_source_bytes:
                raise AcquisitionError("too_large", "Archived map exceeds the size limit")
            ensure_free_space(work_dir, member.file_size, limits)
            target = work_dir / "map.img"
            written = 0
            with bundle.open(member) as source, target.open("wb") as handle:
                while True:
                    chunk = source.read(CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > member.file_size or written > limits.max_source_bytes:
                        raise AcquisitionError("too_large", "Archived map is larger than declared")
                    handle.write(chunk)
    except zipfile.BadZipFile as error:
        raise AcquisitionError("bad_archive", "Source is not a valid ZIP archive") from error
    finally:
        archive.unlink(missing_ok=True)
    return target


def _retry_after(value: str | None) -> datetime:
    now = datetime.now(timezone.utc)
    until = now + timedelta(minutes=15)
    if value:
        try:
            if value.strip().isdigit():
                until = now + timedelta(seconds=int(value.strip()))
            else:
                parsed = parsedate_to_datetime(value)
                until = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass
    return max(until, now + timedelta(minutes=5))


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():  # pragma: no cover - filesystem permission failure
        for root, _dirs, files in os.walk(path):
            for name in files:
                Path(root, name).unlink(missing_ok=True)

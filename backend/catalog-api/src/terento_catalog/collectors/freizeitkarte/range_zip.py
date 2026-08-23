from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen


EOCD_SIGNATURE = b"PK\x05\x06"
ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
CENTRAL_DIRECTORY_SIGNATURE = b"PK\x01\x02"
ZIP64_EXTRA_FIELD = 0x0001
DEFAULT_TAIL_BYTES = 22 + 65535
MAX_TAIL_BYTES = 4 * 1024 * 1024
MAX_CENTRAL_DIRECTORY_BYTES = 64 * 1024 * 1024
MAX_ZIP64_RECORD_BYTES = 1024 * 1024


class ZipRangeError(ValueError):
    pass


class RangeNotSupported(ZipRangeError):
    pass


class InvalidRangeResponse(ZipRangeError):
    pass


class RangeFetcher(Protocol):
    def head_size(self, url: str) -> int | None: ...

    def fetch_range(self, url: str, start: int, end: int) -> "RangeResponse": ...


@dataclass(frozen=True)
class RangeResponse:
    status_code: int
    start: int
    end: int
    total_size: int
    body: bytes
    url: str


class HTTPRangeFetcher:
    """Bounded HTTP HEAD/Range access for provider metadata inspection."""

    user_agent = "TerentoCatalog/0.1 (+https://terento.app)"

    def __init__(self, *, timeout_seconds: int = 30, max_response_bytes: int = MAX_CENTRAL_DIRECTORY_BYTES) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def head_size(self, url: str) -> int | None:
        request = Request(url, method="HEAD", headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                self._validate_redirect(url, response.geturl())
                if getattr(response, "status", 200) != 200:
                    return None
                value = response.headers.get("Content-Length")
        except OSError:
            return None
        try:
            size = int(value) if value is not None else -1
        except ValueError:
            return None
        return size if size >= 0 else None

    def fetch_range(self, url: str, start: int, end: int) -> RangeResponse:
        if start < 0 or end < start:
            raise ValueError("invalid byte range")
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Range": f"bytes={start}-{end}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                self._validate_redirect(url, final_url)
                status = getattr(response, "status", 200)
                if status == 200:
                    raise RangeNotSupported("provider returned 200 to a Range request")
                if status != 206:
                    raise InvalidRangeResponse(f"provider returned HTTP {status}")
                content_range = response.headers.get("Content-Range", "")
                actual_start, actual_end, total = _parse_content_range(content_range)
                if actual_start != start or actual_end > end:
                    raise InvalidRangeResponse(
                        f"provider returned bytes {actual_start}-{actual_end}, expected a range within {start}-{end}"
                    )
                if total <= actual_end:
                    raise InvalidRangeResponse("Content-Range total is smaller than requested end")
                content_length = response.headers.get("Content-Length")
                actual_length = actual_end - actual_start + 1
                if content_length is not None and int(content_length) != actual_length:
                    raise InvalidRangeResponse("Content-Length does not match Content-Range")
                body = response.read(min(actual_length, self.max_response_bytes) + 1)
        except RangeNotSupported:
            raise
        except InvalidRangeResponse:
            raise
        except (OSError, ValueError) as exc:
            raise InvalidRangeResponse("provider Range request failed") from exc

        if len(body) != (actual_end - actual_start + 1):
            raise InvalidRangeResponse("provider returned an incomplete byte range")
        return RangeResponse(status, start, start + len(body) - 1, total, body, final_url)

    @staticmethod
    def _validate_redirect(original_url: str, final_url: str) -> None:
        original_host = urlparse(original_url).hostname
        final_host = urlparse(final_url).hostname
        if not original_host or final_host != original_host:
            raise InvalidRangeResponse("provider redirect changed the download host")


@dataclass(frozen=True)
class ZipEntry:
    name: str
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int
    is_directory: bool = False


@dataclass(frozen=True)
class ZipPayloadMeasurement:
    download_size_bytes: int
    install_size_bytes: int | None
    payload_path: str | None
    method: str
    warning: str | None = None


class ZipRangeInspector:
    def __init__(
        self,
        fetcher: RangeFetcher,
        *,
        initial_tail_bytes: int = DEFAULT_TAIL_BYTES,
        max_tail_bytes: int = MAX_TAIL_BYTES,
        max_central_directory_bytes: int = MAX_CENTRAL_DIRECTORY_BYTES,
    ) -> None:
        self.fetcher = fetcher
        self.initial_tail_bytes = max(22, initial_tail_bytes)
        self.max_tail_bytes = max(self.initial_tail_bytes, max_tail_bytes)
        self.max_central_directory_bytes = max_central_directory_bytes

    def inspect(
        self,
        url: str,
        *,
        expected_payload_path: str | None = "gmapsupp.img",
    ) -> ZipPayloadMeasurement:
        head_size = self.fetcher.head_size(url)
        tail, total_size = self._tail(url, head_size)
        eocd_offset = _find_complete_eocd(tail)
        if eocd_offset is None:
            raise ZipRangeError("ZIP End of Central Directory was not found")

        eocd_values = struct.unpack_from("<4s4H2LH", tail, eocd_offset)
        _, disk_number, central_disk, entries_on_disk, entries_total, central_size, central_offset, comment_length = eocd_values
        if eocd_offset + 22 + comment_length > len(tail):
            raise ZipRangeError("ZIP comment is incomplete")
        if disk_number != 0 or central_disk != 0 or entries_on_disk != entries_total:
            raise ZipRangeError("multi-disk ZIP archives are not supported")

        if (
            entries_total == 0xFFFF
            or central_size == 0xFFFFFFFF
            or central_offset == 0xFFFFFFFF
        ):
            entries_total, central_size, central_offset = self._zip64_values(
                url,
                tail,
                eocd_offset,
            )

        if central_size <= 0 or central_size > self.max_central_directory_bytes:
            raise ZipRangeError("ZIP central directory size is invalid or too large")
        if central_offset < 0 or central_offset + central_size > total_size:
            raise ZipRangeError("ZIP central directory is outside the archive")

        central_response = self.fetcher.fetch_range(
            url,
            central_offset,
            central_offset + central_size - 1,
        )
        if central_response.total_size != total_size:
            raise InvalidRangeResponse("central-directory Range total differs from archive size")
        if central_response.start != central_offset or central_response.end != central_offset + central_size - 1:
            raise InvalidRangeResponse("central-directory Range is incomplete")
        entries = _parse_central_directory(central_response.body, entries_total)
        payload = _select_payload(entries, expected_payload_path)
        if payload.uncompressed_size <= 0:
            raise ZipRangeError("selected ZIP payload is empty")
        return ZipPayloadMeasurement(
            download_size_bytes=total_size,
            install_size_bytes=payload.uncompressed_size,
            payload_path=payload.name,
            method="zip-central-directory-range",
        )

    def _tail(
        self,
        url: str,
        head_size: int | None,
    ) -> tuple[bytes, int]:
        requested_size = self.initial_tail_bytes
        while requested_size <= self.max_tail_bytes:
            if head_size is None:
                response = self.fetcher.fetch_range(url, 0, requested_size - 1)
                total_size = response.total_size
            else:
                total_size = head_size
                if total_size <= 0:
                    raise ZipRangeError("archive size is invalid")
                start = max(0, total_size - requested_size)
                response = self.fetcher.fetch_range(url, start, total_size - 1)
                if response.total_size != total_size:
                    raise InvalidRangeResponse("Range total differs from validated HEAD size")

            tail_offset = response.start
            eocd_offset = _find_complete_eocd(response.body)
            if eocd_offset is not None:
                return response.body, total_size
            if requested_size == self.max_tail_bytes or tail_offset == 0:
                break
            requested_size = min(self.max_tail_bytes, requested_size * 2)
        raise ZipRangeError("ZIP End of Central Directory was not found in bounded tail ranges")

    def _zip64_values(
        self,
        url: str,
        tail: bytes,
        eocd_offset: int,
    ) -> tuple[int, int, int]:
        locator_offset = tail.rfind(ZIP64_LOCATOR_SIGNATURE, 0, eocd_offset)
        if locator_offset < 0 or locator_offset + 20 > len(tail):
            raise ZipRangeError("ZIP64 locator is missing")
        _, disk, zip64_offset, disk_count = struct.unpack_from("<4sLQL", tail, locator_offset)
        if disk != 0 or disk_count != 1:
            raise ZipRangeError("multi-disk ZIP64 archives are not supported")
        record_head = self.fetcher.fetch_range(url, zip64_offset, zip64_offset + 55)
        if record_head.body[:4] != ZIP64_EOCD_SIGNATURE:
            raise ZipRangeError("ZIP64 End of Central Directory signature is invalid")
        record_size = struct.unpack_from("<Q", record_head.body, 4)[0]
        if record_size < 44 or record_size > MAX_ZIP64_RECORD_BYTES:
            raise ZipRangeError("ZIP64 End of Central Directory size is invalid")
        record = record_head.body
        if len(record) < record_size + 12:
            record = self.fetcher.fetch_range(
                url,
                zip64_offset,
                zip64_offset + record_size + 11,
            ).body
        values = struct.unpack_from("<4sQ2H2L4Q", record, 0)
        _, _, _, _, disk_number, central_disk, entries_on_disk, entries_total, central_size, central_offset = values
        if disk_number != 0 or central_disk != 0 or entries_on_disk != entries_total:
            raise ZipRangeError("multi-disk ZIP64 archives are not supported")
        return entries_total, central_size, central_offset


def _find_complete_eocd(data: bytes) -> int | None:
    offset = data.rfind(EOCD_SIGNATURE)
    if offset < 0 or offset + 22 > len(data):
        return None
    comment_length = struct.unpack_from("<H", data, offset + 20)[0]
    if offset + 22 + comment_length > len(data):
        return None
    return offset


def _parse_content_range(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", value.strip())
    if match is None:
        raise InvalidRangeResponse("Content-Range is invalid")
    start, end, total = (int(part) for part in match.groups())
    if start < 0 or end < start or total <= end:
        raise InvalidRangeResponse("Content-Range values are invalid")
    return start, end, total


def _parse_central_directory(data: bytes, expected_entries: int) -> list[ZipEntry]:
    entries: list[ZipEntry] = []
    offset = 0
    fixed_size = 46
    while offset < len(data):
        if offset + fixed_size > len(data):
            raise ZipRangeError("ZIP central-directory header is truncated")
        values = struct.unpack_from("<4s6H3L5H2L", data, offset)
        if values[0] != CENTRAL_DIRECTORY_SIGNATURE:
            raise ZipRangeError("ZIP central-directory signature is invalid")
        _, _, _, flags, _, _, _, _, compressed_size, uncompressed_size, name_length, extra_length, comment_length, disk_start, _, _, local_offset = values
        end = offset + fixed_size + name_length + extra_length + comment_length
        if end > len(data):
            raise ZipRangeError("ZIP central-directory entry is truncated")
        name_bytes = data[offset + fixed_size : offset + fixed_size + name_length]
        try:
            name = name_bytes.decode("utf-8" if flags & 0x800 else "cp437")
        except UnicodeDecodeError as exc:
            raise ZipRangeError("ZIP entry name encoding is invalid") from exc
        name = _safe_entry_name(name)
        extra = data[offset + fixed_size + name_length : offset + fixed_size + name_length + extra_length]
        compressed_size, uncompressed_size, local_offset = _zip64_entry_values(
            extra,
            compressed_size,
            uncompressed_size,
            local_offset,
        )
        if disk_start != 0:
            raise ZipRangeError("multi-disk ZIP entry is not supported")
        entries.append(
            ZipEntry(
                name=name,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                local_header_offset=local_offset,
                is_directory=name.endswith("/"),
            )
        )
        offset = end
    if offset != len(data) or len(entries) != expected_entries:
        raise ZipRangeError("ZIP central-directory entry count is inconsistent")
    return entries


def _zip64_entry_values(
    extra: bytes,
    compressed_size: int,
    uncompressed_size: int,
    local_offset: int,
) -> tuple[int, int, int]:
    if not (
        compressed_size == 0xFFFFFFFF
        or uncompressed_size == 0xFFFFFFFF
        or local_offset == 0xFFFFFFFF
    ):
        return compressed_size, uncompressed_size, local_offset
    position = 0
    values: list[int] = []
    while position + 4 <= len(extra):
        field_id, field_size = struct.unpack_from("<HH", extra, position)
        position += 4
        field_end = position + field_size
        if field_end > len(extra):
            raise ZipRangeError("ZIP extra field is truncated")
        if field_id == ZIP64_EXTRA_FIELD:
            field = extra[position:field_end]
            field_position = 0
            for value in (uncompressed_size, compressed_size, local_offset):
                if value == 0xFFFFFFFF:
                    if field_position + 8 > len(field):
                        raise ZipRangeError("ZIP64 entry extra field is incomplete")
                    values.append(struct.unpack_from("<Q", field, field_position)[0])
                    field_position += 8
            break
        position = field_end
    value_iter = iter(values)
    try:
        if uncompressed_size == 0xFFFFFFFF:
            uncompressed_size = next(value_iter)
        if compressed_size == 0xFFFFFFFF:
            compressed_size = next(value_iter)
        if local_offset == 0xFFFFFFFF:
            local_offset = next(value_iter)
    except StopIteration as exc:
        raise ZipRangeError("ZIP64 entry extra field is incomplete") from exc
    return compressed_size, uncompressed_size, local_offset


def _safe_entry_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise ZipRangeError("ZIP entry path is unsafe")
    path = PurePosixPath(name)
    if any(part in ("", ".", "..") for part in path.parts):
        raise ZipRangeError("ZIP entry path contains unsafe traversal")
    return str(path)


def _select_payload(entries: list[ZipEntry], expected_path: str | None) -> ZipEntry:
    files = [entry for entry in entries if not entry.is_directory]
    if expected_path:
        expected = _safe_entry_name(expected_path).lower()
        matches = [
            entry
            for entry in files
            if entry.name.lower() == expected
            or ("/" not in expected and PurePosixPath(entry.name).name.lower() == expected)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ZipRangeError("expected ZIP payload path is ambiguous")

    candidates = [entry for entry in files if entry.name.lower().endswith(".img")]
    if len(candidates) == 1:
        return candidates[0]
    raise ZipRangeError("ZIP payload IMG entry is missing or ambiguous")


def validate_extracted_payload_size(measurement: ZipPayloadMeasurement, actual_size: int) -> None:
    if actual_size < 0 or measurement.install_size_bytes != actual_size:
        raise ZipRangeError(
            "extracted payload size does not match ZIP central-directory metadata"
        )

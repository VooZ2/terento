from __future__ import annotations

import hashlib
import os
import re
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PUBLIC_ASSET_PATH_PREFIX = "/assets/devices/"
PUBLIC_ASSET_URL_PREFIX = "https://api.terento.app/assets/devices/"
MAX_ASSET_BYTES = 8 * 1024 * 1024
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class AssetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class StoredAsset:
    storage_key: str
    url: str | None
    sha256: str
    width: int
    height: int
    size_bytes: int
    mime_type: str = "image/webp"


class AssetStorage:
    """Filesystem-backed public asset store with path-traversal protection."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def store_webp(self, data: bytes, storage_key: str) -> StoredAsset:
        return self._store(data, storage_key, self.root, public=True)

    def stage_webp(self, data: bytes, storage_key: str) -> StoredAsset:
        """Store a candidate outside the public asset tree."""
        return self._store(data, storage_key, self.root / ".review", public=False)

    def publish_staged(self, storage_key: str) -> StoredAsset:
        key = validate_storage_key(storage_key)
        staged = (self.root / ".review" / key).resolve()
        review_root = (self.root / ".review").resolve()
        try:
            staged.relative_to(review_root)
        except ValueError as exc:
            raise AssetValidationError(
                "staged asset path is outside review storage"
            ) from exc
        if not staged.is_file():
            raise AssetValidationError("staged asset does not exist")
        data = staged.read_bytes()
        stored = self._store(data, key, self.root, public=True)
        staged.unlink()
        return stored

    def _store(
        self, data: bytes, storage_key: str, destination_root: Path, *, public: bool
    ) -> StoredAsset:
        width, height = validate_webp(data)
        key = validate_storage_key(storage_key)
        destination = destination_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".upload-", delete=False
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o644)
            os.replace(temporary_name, destination)
        finally:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

        return StoredAsset(
            storage_key=key,
            url=public_asset_url(key) if public else None,
            sha256=hashlib.sha256(data).hexdigest(),
            width=width,
            height=height,
            size_bytes=len(data),
        )

    def read_public_path(self, request_path: str) -> tuple[bytes, str, str] | None:
        if not request_path.startswith(PUBLIC_ASSET_PATH_PREFIX):
            return None
        key = "devices/" + request_path.removeprefix(PUBLIC_ASSET_PATH_PREFIX)
        try:
            key = validate_storage_key(key)
        except AssetValidationError:
            return None

        asset_path = (self.root / key).resolve()
        root = self.root.resolve()
        try:
            asset_path.relative_to(root)
        except ValueError:
            return None
        if not asset_path.is_file():
            return None
        data = asset_path.read_bytes()
        validate_webp(data)
        return data, hashlib.sha256(data).hexdigest(), "image/webp"


def validate_storage_key(storage_key: str) -> str:
    if not isinstance(storage_key, str) or not storage_key:
        raise AssetValidationError("asset storage key is required")
    path = PurePosixPath(storage_key)
    if path.is_absolute() or len(path.parts) < 3 or path.parts[0] != "devices":
        raise AssetValidationError("asset storage key must be under devices/")
    if path.suffix.lower() != ".webp":
        raise AssetValidationError("runtime assets must use the WebP format")
    if any(not _SAFE_SEGMENT.fullmatch(part) for part in path.parts):
        raise AssetValidationError("asset storage key contains an unsafe path segment")
    return path.as_posix()


def public_asset_url(storage_key: str) -> str:
    return PUBLIC_ASSET_URL_PREFIX + validate_storage_key(storage_key).removeprefix(
        "devices/"
    )


def validate_webp(data: bytes) -> tuple[int, int]:
    if not isinstance(data, bytes) or len(data) < 30:
        raise AssetValidationError("asset is too small to be a WebP image")
    if len(data) > MAX_ASSET_BYTES:
        raise AssetValidationError("asset exceeds the maximum runtime size")
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise AssetValidationError("asset must be a RIFF WebP image")
    riff_size = struct.unpack_from("<I", data, 4)[0]
    if riff_size + 8 > len(data):
        raise AssetValidationError("WebP container is truncated")

    offset = 12
    width: int | None = None
    height: int | None = None
    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        payload_start = offset + 8
        payload_end = payload_start + chunk_size
        if payload_end > len(data):
            raise AssetValidationError("WebP chunk is truncated")
        payload = data[payload_start:payload_end]
        if chunk_type == b"VP8X" and len(payload) >= 10:
            width = 1 + int.from_bytes(payload[4:7], "little")
            height = 1 + int.from_bytes(payload[7:10], "little")
            break
        if chunk_type == b"VP8 " and len(payload) >= 18:
            if payload[6:10] == b"\x9d\x01\x2a":
                width = struct.unpack_from("<H", payload, 10)[0] & 0x3FFF
                height = struct.unpack_from("<H", payload, 12)[0] & 0x3FFF
                break
        if chunk_type == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F:
            bits = int.from_bytes(payload[1:5], "little")
            width = 1 + (bits & 0x3FFF)
            height = 1 + ((bits >> 14) & 0x3FFF)
            break
        offset = payload_end + (chunk_size & 1)

    if width is None or height is None or not (
        1 <= width <= 16384 and 1 <= height <= 16384
    ):
        raise AssetValidationError("WebP dimensions could not be validated")
    return width, height

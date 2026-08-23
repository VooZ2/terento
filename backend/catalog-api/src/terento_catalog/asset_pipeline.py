from __future__ import annotations

import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .asset_storage import AssetStorage, StoredAsset


MAX_SOURCE_BYTES = 32 * 1024 * 1024


class AssetAcquisitionError(ValueError):
    pass


class AssetPipeline:
    """Prepare reviewed assets without making them public automatically."""

    def __init__(self, storage: AssetStorage) -> None:
        self.storage = storage

    def prepare(self, source: str, storage_key: str) -> StoredAsset:
        data = self._read_source(source)
        # Runtime assets are deliberately normalized to validated WebP before
        # they enter review storage. Conversion tools are kept outside the API
        # process so a collector cannot publish an unreviewed source image.
        return self.storage.stage_webp(data, storage_key)

    def approve(self, storage_key: str) -> StoredAsset:
        return self.storage.publish_staged(storage_key)

    def _read_source(self, source: str) -> bytes:
        path = Path(source).expanduser()
        if path.is_file():
            data = path.read_bytes()
            if len(data) > MAX_SOURCE_BYTES:
                raise AssetAcquisitionError("source image exceeds the maximum size")
            return data

        parsed = urlparse(source)
        if parsed.scheme != "https" or not parsed.netloc:
            raise AssetAcquisitionError(
                "asset source must be a local file or HTTPS URL"
            )
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "TerentoAssetCollector/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = urlparse(response.geturl())
            if final_url.scheme != "https":
                raise AssetAcquisitionError("asset redirect left HTTPS")
            advertised = response.headers.get("Content-Length")
            if advertised and int(advertised) > MAX_SOURCE_BYTES:
                raise AssetAcquisitionError("source image exceeds the maximum size")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise AssetAcquisitionError("source image exceeds the maximum size")
                chunks.append(chunk)
        return b"".join(chunks)

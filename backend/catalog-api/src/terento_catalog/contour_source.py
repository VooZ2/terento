"""Bounded, metadata-only inspection of official OpenTopoMap contour ZIPs."""
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
import io
import hashlib
import json
import re
import zipfile
from urllib.request import Request, urlopen

from .collectors.freizeitkarte.range_zip import HTTPRangeFetcher


@dataclass(frozen=True)
class ContourMeasurement:
    download_size_bytes: int
    install_size_bytes: int
    payload_path: str
    source_updated_at: datetime | None
    source_proof: dict


class _RemoteZip(io.RawIOBase):
    def __init__(self, url, size, fetcher):
        self.url, self.size, self.fetcher = url, size, fetcher
        self.position = 0
        self.remaining = 8 * 1024 * 1024

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset + (self.position if whence == 1 else self.size if whence == 2 else 0)
        if position < 0 or position > self.size:
            raise ValueError('ZIP seek outside archive')
        self.position = position
        return position

    def read(self, size=-1):
        size = min(self.size - self.position, size if size >= 0 else self.size)
        if size > self.remaining or size > 4 * 1024 * 1024:
            raise ValueError('Contour metadata inspection byte limit exceeded')
        if not size:
            return b''
        response = self.fetcher.fetch_range(self.url, self.position, self.position + size - 1)
        if response.url != self.url or response.total_size != self.size or len(response.body) != size:
            raise ValueError('Contour source changed during inspection')
        self.remaining -= size
        self.position += size
        return response.body


def _metadata(url):
    with urlopen(Request(url, method='HEAD', headers={'User-Agent': HTTPRangeFetcher.user_agent}), timeout=30) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Contour source must remain at its official URL')
        return (int(response.headers.get('Content-Length', '0')),
                response.headers.get('ETag'), response.headers.get('Last-Modified'))


def inspect_contour(url):
    match = re.fullmatch(r'https://garmin\.opentopomap\.org/[a-z-]+/([a-z0-9-]+)/otm-\1-contours\.zip', url)
    if not match:
        raise ValueError('Not an exact official contour source path')
    region = match.group(1)
    before = _metadata(url)
    if before[0] <= 0 or not before[1] or before[1].startswith('W/') or not before[2]:
        raise ValueError('Contour source lacks stable HTTP metadata')
    expected = f'otm-{region}-contours.img'
    with zipfile.ZipFile(_RemoteZip(url, before[0], HTTPRangeFetcher())) as archive:
        images = [item for item in archive.infolist() if item.filename.lower().endswith('.img')]
        if len(images) != 1 or images[0].filename != expected or images[0].file_size <= 4096:
            raise ValueError('Contour ZIP does not contain the exact expected IMG')
        with archive.open(images[0]) as payload:
            header = payload.read(4096)
        if header[0x10:0x16] != b'DSKIMG' or header[0x41:0x47] != b'GARMIN':
            raise ValueError('Contour payload is not a Garmin IMG')
        identity = ''.join(chr(b).lower() for b in header if 48 <= b <= 57 or 65 <= b <= 90 or 97 <= b <= 122)
        if 'opentopomap' not in identity or region.replace('-', '') not in identity:
            raise ValueError('Contour header does not match provider and region')
        install_size = images[0].file_size
    if _metadata(url) != before:
        raise ValueError('Contour HTTP metadata changed during inspection')
    proof = {"sourceURL": url, "etag": before[1], "lastModified": before[2],
             "downloadSizeBytes": before[0], "installSizeBytes": install_size,
             "payloadPath": expected}
    proof["revision"] = hashlib.sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    proof["sourceIdentity"] = f"opentopomap:{region}:contours"
    return ContourMeasurement(before[0], install_size, expected, parsedate_to_datetime(before[2]), proof)

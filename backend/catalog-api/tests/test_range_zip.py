from __future__ import annotations

import io
import struct
import unittest
import zipfile

from terento_catalog.collectors.freizeitkarte.collector import FreizeitkarteCollector
from terento_catalog.collectors.freizeitkarte.range_zip import (
    RangeNotSupported,
    RangeResponse,
    ZipRangeError,
    ZipRangeInspector,
    validate_extracted_payload_size,
)


def make_zip(*, entries: dict[str, bytes], comment: bytes = b"") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = comment
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def make_zip64_archive() -> bytes:
    original = make_zip(entries={"gmapsupp.img": b"garmin-payload"})
    eocd_offset = original.rfind(b"PK\x05\x06")
    _, _, _, _, entries, central_size, central_offset, _ = struct.unpack_from(
        "<4s4H2LH", original, eocd_offset
    )
    del entries
    zip64_offset = eocd_offset
    zip64_record = struct.pack(
        "<4sQ2H2L4Q",
        b"PK\x06\x06",
        44,
        45,
        45,
        0,
        0,
        1,
        1,
        central_size,
        central_offset,
    )
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, zip64_offset, 1)
    classic_eocd = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    return original[:eocd_offset] + zip64_record + locator + classic_eocd


class MemoryRangeFetcher:
    def __init__(self, payload: bytes, *, head: bool = True) -> None:
        self.payload = payload
        self.head = head
        self.calls: list[tuple[int, int]] = []

    def head_size(self, url: str) -> int | None:
        return len(self.payload) if self.head else None

    def fetch_range(self, url: str, start: int, end: int) -> RangeResponse:
        self.calls.append((start, end))
        actual_end = min(end, len(self.payload) - 1)
        if start > actual_end:
            raise AssertionError("range starts after archive")
        return RangeResponse(
            status_code=206,
            start=start,
            end=actual_end,
            total_size=len(self.payload),
            body=self.payload[start : actual_end + 1],
            url=url,
        )


class RangeZipTests(unittest.TestCase):
    def test_measures_final_img_from_central_directory_without_full_download(self) -> None:
        archive = make_zip(
            entries={"README.txt": b"metadata", "maps/gmapsupp.img": b"x" * 37}
        )
        fetcher = MemoryRangeFetcher(archive)
        measurement = ZipRangeInspector(fetcher).inspect(
            "https://download.example/map.zip"
        )

        self.assertEqual(measurement.download_size_bytes, len(archive))
        self.assertEqual(measurement.install_size_bytes, 37)
        self.assertEqual(measurement.payload_path, "maps/gmapsupp.img")
        self.assertEqual(measurement.method, "zip-central-directory-range")
        self.assertTrue(all(end < len(archive) for _, end in fetcher.calls))

    def test_expands_tail_for_long_zip_comment(self) -> None:
        archive = make_zip(entries={"gmapsupp.img": b"x" * 11}, comment=b"c" * 65_535)
        fetcher = MemoryRangeFetcher(archive)
        measurement = ZipRangeInspector(
            fetcher,
            initial_tail_bytes=32,
            max_tail_bytes=256 * 1024,
        ).inspect("https://download.example/map.zip")

        self.assertEqual(measurement.install_size_bytes, 11)
        self.assertGreater(len(fetcher.calls), 1)

    def test_supports_zip64_eocd(self) -> None:
        archive = make_zip64_archive()
        measurement = ZipRangeInspector(MemoryRangeFetcher(archive)).inspect(
            "https://download.example/map.zip"
        )
        self.assertEqual(measurement.install_size_bytes, len(b"garmin-payload"))

    def test_rejects_ambiguous_img_payload(self) -> None:
        archive = make_zip(
            entries={"one.img": b"1", "two.img": b"2"}
        )
        with self.assertRaises(ZipRangeError):
            ZipRangeInspector(MemoryRangeFetcher(archive)).inspect(
                "https://download.example/map.zip"
            )

    def test_rejects_unsafe_entry_path(self) -> None:
        archive = make_zip(entries={"../gmapsupp.img": b"payload"})
        with self.assertRaises(ZipRangeError):
            ZipRangeInspector(MemoryRangeFetcher(archive)).inspect(
                "https://download.example/map.zip"
            )

    def test_rejects_malformed_central_directory(self) -> None:
        archive = bytearray(make_zip(entries={"gmapsupp.img": b"payload"}))
        eocd_offset = archive.rfind(b"PK\x05\x06")
        central_offset = struct.unpack_from("<L", archive, eocd_offset + 16)[0]
        archive[central_offset : central_offset + 4] = b"NOPE"
        with self.assertRaises(ZipRangeError):
            ZipRangeInspector(MemoryRangeFetcher(bytes(archive))).inspect(
                "https://download.example/map.zip"
            )

    def test_unknown_head_still_uses_range_total(self) -> None:
        archive = make_zip(entries={"gmapsupp.img": b"payload"})
        fetcher = MemoryRangeFetcher(archive, head=False)
        measurement = ZipRangeInspector(fetcher).inspect("https://download.example/map.zip")
        self.assertEqual(measurement.download_size_bytes, len(archive))

    def test_extracted_size_must_match_metadata(self) -> None:
        archive = make_zip(entries={"gmapsupp.img": b"payload"})
        measurement = ZipRangeInspector(MemoryRangeFetcher(archive)).inspect(
            "https://download.example/map.zip"
        )
        validate_extracted_payload_size(measurement, len(b"payload"))
        with self.assertRaises(ZipRangeError):
            validate_extracted_payload_size(measurement, 3)

    def test_collector_keeps_download_size_when_range_is_unavailable(self) -> None:
        class Fetcher:
            release_html = '<p>The Freizeitkarte maps "2/2026" are based on OpenStreetMap data of 2026/05/03.</p>'
            map_html = '<h3><a id="DEU">Germany (DEU+):</a></h3><a href="https://download.example/DEU_en_gmapsupp.img.zip">gmapsupp</a>'

            def fetch_text(self, url: str) -> str:
                return self.release_html if "release" in url else self.map_html

            def head_size(self, url: str) -> int:
                return 123

            def measure_zip(self, url: str):
                raise RangeNotSupported("Range is not supported")

        record = FreizeitkarteCollector(
            fetcher=Fetcher(),
            map_page_urls=("https://www.freizeitkarte-osm.de/garmin/en/maps.html",),
        ).collect()[0]
        self.assertEqual(record.download_size_bytes, 123)
        self.assertIsNone(record.install_size_bytes)
        self.assertIn("Range is not supported", record.size_measurement_warning or "")


if __name__ == "__main__":
    unittest.main()

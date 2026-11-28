"""Writes synthetic T-MZ Japan OSM IMG/ZIP fixtures; no real map data is stored.

Each IMG mirrors the layout measured on tmz.skr.jp's published files:
- title at 0x49/0x65: '"Japan OSM"' (with contours) or 'OSM Japan' (standard)
- build date at 0x39
- FAT records: MAKEGMAP.MPS at 0x600, 00000042.MDR at 0x800, 00000TMZ.TYP at 0x1000/0x1800
Each ZIP mirrors the published 3-entry archive: gmapsupp.img, gmapsupp_search.img,
and osmmap_license.txt.
"""
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path


def img(title, date, fid=42, typ_name="00000TMZ", typ_offset=0x1000, size=65536):
    data = bytearray(size)
    data[0x10:0x16], data[0x41:0x47] = b"DSKIMG", b"GARMIN"
    data[0x39:0x3B] = struct.pack("<H", date[0])
    data[0x3B], data[0x3C] = date[1], date[2]
    raw = title.encode("ascii")
    data[0x49:0x5D] = raw[:20].ljust(20, b" ")
    data[0x65:0x83] = raw[20:].ljust(30, b" ")
    data[0x61], data[0x62] = 9, 0
    data[0x400] = 1
    data[0x401:0x40C] = b" " * 11
    data[0x600] = 1
    data[0x601:0x60C] = b"MAKEGMAPMPS"
    data[0x800] = 1
    data[0x801:0x80C] = f"{fid:08d}MDR".encode()
    if typ_name:
        data[typ_offset] = 1
        data[typ_offset + 1:typ_offset + 12] = f"{typ_name:8s}TYP".encode()
    return bytes(data)


def search_img(size=8192):
    data = bytearray(size)
    data[0x10:0x16], data[0x41:0x47] = b"DSKIMG", b"GARMIN"
    data[0x39:0x3B] = struct.pack("<H", 2026)
    data[0x3B], data[0x3C] = 11, 21
    data[0x49:0x5D] = b"Japan Search".ljust(20, b" ")
    return bytes(data)


CONTOURS = img('"Japan OSM"', (2026, 11, 21), 42, "00000TMZ", 0x1000)
STANDARD = img("OSM Japan", (2026, 11, 21), 42, "00000TMZ", 0x1800)
SEARCH = search_img()
LICENSE = (
    b"Map data (c) OpenStreetMap contributors\n"
    b"Map data licenced under Open Data Commons Open Database License (ODbL)\n"
)


def archive(path, entries):
    with zipfile.ZipFile(path, "w") as target:
        for name, data, method in entries:
            info = zipfile.ZipInfo(name, (2026, 11, 21, 3, 47, 18))
            info.compress_type = method
            target.writestr(info, data)


def tmz_entries(payload=CONTOURS, name="gmapsupp.img", extra=(), method=zipfile.ZIP_DEFLATED):
    return [
        (name, payload, method),
        ("gmapsupp_search.img", SEARCH, zipfile.ZIP_DEFLATED),
        ("osmmap_license.txt", LICENSE, zipfile.ZIP_DEFLATED),
        *extra,
    ]


def main(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    variants = {
        "gmapsupp_261119cntr.zip": tmz_entries(CONTOURS),
        "gmapsupp_261119.zip": tmz_entries(STANDARD),
        "bad-extra-img.zip": tmz_entries(CONTOURS, extra=[("extra.img", CONTOURS, zipfile.ZIP_DEFLATED)]),
        "bad-side-file.zip": tmz_entries(CONTOURS, extra=[("run.sh", b"#!/bin/sh\n", zipfile.ZIP_DEFLATED)]),
        "bad-stored.zip": tmz_entries(CONTOURS, method=zipfile.ZIP_STORED),
        "bad-path.zip": tmz_entries(CONTOURS, name="garmin/gmapsupp.img"),
        "bad-family.zip": tmz_entries(img('"Japan OSM"', (2026, 11, 21), 99, "00000TMZ")),
        "bad-typ.zip": tmz_entries(img('"Japan OSM"', (2026, 11, 21), 42, None)),
        "bad-title.zip": tmz_entries(img("Other Map", (2026, 11, 21), 42, "00000TMZ")),
        "bad-date.zip": tmz_entries(img('"Japan OSM"', (2026, 11, 18), 42, "00000TMZ")),
    }
    meta = {}
    for name, entries in variants.items():
        archive(target / name, entries)
        image = next(data for entry, data, _ in entries if entry.endswith("gmapsupp.img"))
        meta[name] = {
            "downloadSizeBytes": (target / name).stat().st_size,
            "installSizeBytes": len(image),
            "crc32": f"{zlib.crc32(image):08x}",
        }
        if name in ("gmapsupp_261119cntr.zip", "gmapsupp_261119.zip"):
            (target / (name[:-4] + ".img")).write_bytes(image)
    (target / "meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])

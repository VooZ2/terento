"""Writes synthetic OpenFietsMap IMG/ZIP fixtures; no map data is stored in the repo.

Each IMG mirrors the layout measured on the author's files (2026-11-21): the
title stitched at 0x49/0x65, the build date at 0x39 and one <FID>.MDR FAT
record from 0x400. Each ZIP mirrors one published archive: Benelux has the map
at the root beside two readme pages and a Windows installer; the Europe areas
put it in a garmin/ folder beside two readme texts. meta.json gives the
download size, IMG size and CRC-32 a catalog proof would carry. Variants change
one fact each.
"""
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path


def img(title, date, fid, size=65536):
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
    data[0x601:0x60C] = f"{fid:08d}MDR".encode()
    return bytes(data)


BENELUX = img("OFM_BNL(21-11-2026)", (2026, 11, 21), 10010)
EUROPE_C = img("OFM(EU2026_C)", (2026, 3, 10), 20264)


def archive(path, entries):
    with zipfile.ZipFile(path, "w") as target:
        for name, data, method in entries:
            if name.endswith("/"):
                info = zipfile.ZipInfo(name, (2026, 3, 10, 0, 0, 0))
                target.writestr(info, b"")
            else:
                info = zipfile.ZipInfo(name, (2026, 3, 10, 0, 0, 0))
                info.compress_type = method
                target.writestr(info, data)


def benelux(payload=BENELUX, name="gmapsupp.img", extra=(), method=zipfile.ZIP_DEFLATED):
    return [(name, payload, method), ("leesmij.html", b"<html>leesmij</html>", zipfile.ZIP_DEFLATED),
            ("readme.html", b"<html>readme</html>", zipfile.ZIP_DEFLATED),
            ("setup.exe", b"MZ" + bytes(510), zipfile.ZIP_DEFLATED), *extra]


def main(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    variants = {
        "OpenFietsMap.zip": (benelux(), BENELUX),
        "OFM(EU2026_C_GPS).zip": ([("garmin/", b"", None), ("garmin/gmapsupp.img", EUROPE_C, zipfile.ZIP_DEFLATED),
                                    ("leesme.txt", b"leesme", zipfile.ZIP_DEFLATED),
                                    ("readme.txt", b"readme", zipfile.ZIP_DEFLATED)], EUROPE_C),
        "bad-second-img.zip": (benelux(extra=[("old.img", BENELUX, zipfile.ZIP_DEFLATED)]), BENELUX),
        "bad-side-file.zip": (benelux(extra=[("run.bat", b"echo", zipfile.ZIP_DEFLATED)]), BENELUX),
        "bad-stored.zip": (benelux(method=zipfile.ZIP_STORED), BENELUX),
        "bad-path.zip": (benelux(name="garmin/gmapsupp.img"), BENELUX),
        "bad-family.zip": (benelux(img("OFM_BNL(21-11-2026)", (2026, 11, 21), 10011)), None),
        "bad-title.zip": (benelux(img("OFM_BNL(22-11-2026)", (2026, 11, 21), 10010)), None),
        "bad-date.zip": (benelux(img("OFM_BNL(21-11-2026)", (2026, 11, 22), 10010)), None),
    }
    meta = {}
    for name, (entries, payload) in variants.items():
        archive(target / name, entries)
        image = next(data for entry, data, _ in entries if entry.endswith(".img") and entry != "old.img")
        meta[name] = {"downloadSizeBytes": (target / name).stat().st_size, "installSizeBytes": len(image),
                      "crc32": f"{zlib.crc32(image):08x}"}
        if name in ("OpenFietsMap.zip", "OFM(EU2026_C_GPS).zip"):
            (target / (name[:-4] + ".img")).write_bytes(image)
    (target / "meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])

"""Writes Lucky Maps IMG fixtures from the measured Andorra header and MPS bytes.

The 4 KiB headers and MPS product files are the real luckymaps.ch bytes
(2026-11-21); every other block is zero, so no map data is stored in the repo.
Variants change one identity fact each.
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).parent


def build(header, mps, size):
    data = bytearray(size)
    data[:len(header)] = header
    exponent = header[0x61] + header[0x62]
    block = 1 << exponent
    for offset in range(0x400, 4096, 0x200):
        if header[offset] == 1 and header[offset + 1:offset + 12] == b"MAKEGMAPMPS":
            start = struct.unpack("<H", header[offset + 0x20:offset + 0x22])[0] * block
            assert struct.unpack("<I", header[offset + 0x0C:offset + 0x10])[0] == len(mps)
            data[start:start + len(mps)] = mps
            return data
    raise SystemExit("no MPS entry")


def main(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    main_header = (HERE / "andorra-header.bin").read_bytes()
    main_mps = (HERE / "andorra-mps.bin").read_bytes()
    ct_header = (HERE / "andorra-ct-header.bin").read_bytes()
    ct_mps = (HERE / "andorra-ct-mps.bin").read_bytes()
    variants = {
        "andorra": (main_header, main_mps),
        "andorra-ct": (ct_header, ct_mps),
        "bad-publisher": (main_header, main_mps.replace(b"luckymaps.ch", b"luckymaps.cz")),
        "bad-area": (main_header, main_mps.replace(b"andorra\0", b"andorrb\0")),
        "bad-mps-family": (main_header, main_mps.replace(struct.pack("<H", 55001), struct.pack("<H", 55002))),
        "bad-title": (main_header[:0x49] + b"andorrb" + main_header[0x50:], main_mps),
        "bad-date": (main_header[:0x3C] + bytes([4]) + main_header[0x3D:], main_mps),
        "ct-as-main": (ct_header, ct_mps),
    }
    for name, (header, mps) in variants.items():
        size = 49152 if header is main_header or name.startswith("bad-") else 8192
        (target / f"{name}.img").write_bytes(build(header, mps, size))


if __name__ == "__main__":
    main(sys.argv[1])

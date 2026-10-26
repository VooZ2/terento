"""Writes synthetic OSMapaPL IMG/ZIP fixtures; no map data is stored in the repo.

Each IMG mirrors the measured mkgmap layout: stitched title at 0x49/0x65,
creation date at 0x39, FAT from 0x400 (reserved entry, MAKEGMAP.MPS,
<FID>.MDR) and an MPS product file with L and F records.
"""
import struct
import sys
import zipfile
from pathlib import Path


def img(title, date=(2026, 10, 24), fid=5, mdr_fid=None, mps_fid=None, size=65536):
    data = bytearray(size)
    data[0x10:0x16], data[0x41:0x47] = b'DSKIMG', b'GARMIN'
    data[0x39:0x3B] = date[0].to_bytes(2, 'little')
    data[0x3B], data[0x3C] = date[1], date[2]
    raw = title.encode('latin-1')
    data[0x49:0x5D] = raw[:20].ljust(20, b' ')
    data[0x65:0x83] = raw[20:].ljust(30, b' ')
    data[0x61], data[0x62] = 9, 0  # 512-byte blocks
    mps_fid = fid if mps_fid is None else mps_fid
    name = title.encode('latin-1') + b'\0'
    mps = (b'L' + struct.pack('<H', 8 + 2 * len(name) + 9) + struct.pack('<HHI', mps_fid, mps_fid, 66012001)
           + name + name + b'Area 1\0\0\0'
           + b'F' + struct.pack('<H', 4 + len(name)) + struct.pack('<HH', mps_fid, mps_fid) + name
           + b'V' + struct.pack('<H', 13) + b'OSM map set\0\0')
    data[0x400] = 1
    data[0x401:0x40C] = b' ' * 11
    data[0x600] = 1
    data[0x601:0x60C] = b'MAKEGMAPMPS'
    data[0x60C:0x610] = struct.pack('<I', len(mps))
    data[0x620:0x620 + 480] = b'\xff' * 480
    data[0x620:0x622] = struct.pack('<H', 16)
    data[16 * 512:16 * 512 + len(mps)] = mps
    if mdr_fid is not False:
        data[0x800] = 1
        data[0x801:0x80C] = f'{fid if mdr_fid is None else mdr_fid:08d}MDR'.encode()
    return bytes(data)


def write(directory, stem, payload, entries=None, method=zipfile.ZIP_DEFLATED):
    (directory / f'{stem}.img').write_bytes(payload)
    with zipfile.ZipFile(directory / f'{stem}.zip', 'w', method) as archive:
        for name, body in entries or [('gmapsupp.img', payload)]:
            archive.writestr(name, body)


def main(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    styles = {'PODSTAWOWA': 4, 'OGONKI': 5, 'LIGHT': 6, 'WARSTWICE': 12}
    for coverage, prefix in (('pl', 'OSMapaPL'), ('plext', 'OSMapaPLext')):
        for style, fid in styles.items():
            write(directory, f'{coverage}-{style.lower()}', img(f'{prefix}-{style}', fid=fid))
    good = img('OSMapaPL-OGONKI', fid=5)
    write(directory, 'bad-mps', img('OSMapaPL-OGONKI', fid=5, mps_fid=4))
    write(directory, 'bad-mdr', img('OSMapaPL-OGONKI', fid=5, mdr_fid=4))
    write(directory, 'bad-date', img('OSMapaPL-OGONKI', fid=5, date=(2026, 10, 23)))
    write(directory, 'bad-title', img('OSMapaPLext-OGONKI', fid=5))
    write(directory, 'two-entries', good, entries=[('gmapsupp.img', good), ('README.txt', b'x')])
    write(directory, 'stored', good, method=zipfile.ZIP_STORED)
    write(directory, 'renamed', good, entries=[('map.img', good)])


if __name__ == '__main__':
    main(sys.argv[1])

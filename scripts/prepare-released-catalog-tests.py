#!/usr/bin/env python3
"""Adapt the known historical date fixture, never the pinned client's runtime code."""
from pathlib import Path
import sys

TEST_PATH = Path("app/TerentoCore/Tests/TerentoPoCTests/Stage1ProviderNeutralTests.swift")
REPLACEMENTS = (
    ("makeFreizeitkarteIMG(token: package.providerRegionId)",
     "makeFreizeitkarteIMG(token: package.providerRegionId, version: package.version)", 1),
    ("makeFreizeitkarteIMG(token: String) -> [UInt8]",
     "makeFreizeitkarteIMG(token: String, version: MapVersion) -> [UInt8]", 1),
    ('Release 26.05', 'Release \\(String(format: "%02d.%02d", version.year % 100, version.month))', 2),
)


def prepare(root: Path) -> None:
    path = root / TEST_PATH
    source = path.read_text()
    if all(source.count(old) == 0 and source.count(new) >= count
           for old, new, count in REPLACEMENTS):
        return
    # Refuse partial/unknown test layouts instead of silently weakening a gate.
    if not all(source.count(old) == count and source.count(new) == 0
               for old, new, count in REPLACEMENTS):
        raise ValueError("Unrecognized released-client date fixture; review the pinned test source")
    for old, new, _ in REPLACEMENTS:
        source = source.replace(old, new)
    path.write_text(source)


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))

#!/usr/bin/env python3
"""Review the map style preview areas against install statistics and coverage.

Offline and read-only. Inputs are files the operator already has:

* ``contracts/map-preview-areas.json`` (default) – the curated area list;
* ``--catalog`` – a saved public catalog, e.g. ``/maps/catalog-v4.json``;
* ``--statistics`` – optional saved Admin ``/admin/map-statistics.json``
  (period ``all``); only successful main-map installs are counted, matching
  the Admin "Top countries" population.

The report lists, per area, how many preview styles have a candidate map
package, flags areas below the coverage rule (three styles in Europe, two
elsewhere), and ranks countries with installs but no preview area. It never
edits the area list; changes stay a reviewed edit of the contract file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AREAS = ROOT / "contracts/map-preview-areas.json"

# style id -> (provider id, map type or None)
STYLES = {
    "freizeitkarte": ("freizeitkarte", None),
    "opentopomap": ("opentopomap", None),
    "maprando": ("maprando", None),
    "bbbike": ("bbbike", "bbbike-latin1"),
    "bbbike-ontrail": ("bbbike", "ontrail-latin1"),
}
# Freizeitkarte catalog rows may not carry country codes; its published
# coverage is Europe plus Türkiye.
FREIZEITKARTE_EXTRA = {"TR"}


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def catalog_coverage(catalog: dict) -> dict[str, set[str]]:
    """Return style id -> set of ISO country codes with at least one package."""
    coverage: dict[str, set[str]] = defaultdict(set)
    for provider in catalog.get("providers", []):
        provider_id = provider.get("id")
        for package in provider.get("maps", []):
            if package.get("availability", "AVAILABLE") not in {"AVAILABLE", None}:
                continue
            map_type = package.get("mapType")
            for style_id, (style_provider, style_type) in STYLES.items():
                if style_provider != provider_id:
                    continue
                if style_type is not None and map_type != style_type:
                    continue
                coverage[style_id].update(package.get("countryCodes") or [])
    return coverage


def styles_for_area(area: dict, coverage: dict[str, set[str]]) -> list[str]:
    codes = set(area["countryCodes"])
    result = []
    for style_id in STYLES:
        covered = codes & coverage.get(style_id, set())
        if style_id == "freizeitkarte" and not coverage.get(style_id):
            covered = codes if (area["continent"] == "europe" or codes & FREIZEITKARTE_EXTRA) else set()
        if covered:
            result.append(style_id)
    return result


def install_counts(statistics: dict) -> Counter:
    counts: Counter = Counter()
    for row in statistics.get("rows", []):
        if row.get("event_type") != "INSTALL_SUCCEEDED" or row.get("outcome") != "SUCCEEDED":
            continue
        if (row.get("component_kind") or "main") != "main":
            continue
        code = str(row.get("region_country") or "").strip().upper()
        if len(code) != 2 or not code.isalpha():
            continue
        counts[code] += int(row.get("operation_count") or 0)
    return counts


def build_report(areas_doc: dict, catalog: dict, statistics: dict | None) -> dict:
    coverage = catalog_coverage(catalog)
    areas = []
    for area in areas_doc["areas"]:
        styles = styles_for_area(area, coverage)
        minimum = 3 if area["continent"] == "europe" else 2
        areas.append({
            "id": area["id"],
            "kind": area["kind"],
            "countryCodes": area["countryCodes"],
            "styles": styles,
            "meetsCoverageRule": len(styles) >= minimum,
        })
    covered_countries = {code for area in areas_doc["areas"] for code in area["countryCodes"]}
    gaps = []
    if statistics is not None:
        counts = install_counts(statistics)
        gaps = [
            {"countryCode": code, "installs": count}
            for code, count in counts.most_common()
            if code not in covered_countries
        ]
    return {
        "areaCount": len(areas),
        "kinds": dict(Counter(area["kind"] for area in areas_doc["areas"])),
        "belowCoverageRule": [area["id"] for area in areas if not area["meetsCoverageRule"]],
        "countriesWithInstallsButNoArea": gaps,
        "areas": areas,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--areas", type=Path, default=DEFAULT_AREAS)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--statistics", type=Path)
    parser.add_argument("--fail-on-gaps", action="store_true",
                        help="exit 1 when an area is below the coverage rule")
    args = parser.parse_args(argv)
    report = build_report(
        load_json(args.areas),
        load_json(args.catalog),
        load_json(args.statistics) if args.statistics else None,
    )
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 1 if args.fail_on_gaps and report["belowCoverageRule"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

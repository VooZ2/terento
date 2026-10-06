"""Curated map style preview areas and their Web Mercator tile extents.

The canonical list is ``contracts/map-preview-areas.json``; ``areas.json`` in
this package is a byte-identical copy so the API image can read it (the
contract parity test keeps them equal).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

PACKAGED_AREAS = Path(__file__).with_name("areas.json")
KM_PER_DEGREE_LAT = 111.32
MAX_MERCATOR_LAT = 85.05112878


@dataclass(frozen=True)
class PreviewArea:
    id: str
    kind: str
    name: dict[str, str]
    country_codes: tuple[str, ...]
    continent: str
    center: tuple[float, float]
    bbox: tuple[float, float, float, float]
    min_zoom: int
    max_zoom: int
    tags: tuple[str, ...]
    region_hints: tuple[str, ...]
    route_name: str | None
    featured: bool

    def contains(self, lon: float, lat: float) -> bool:
        west, south, east, north = self.bbox
        return west <= lon <= east and south <= lat <= north

    def public(self) -> dict[str, object]:
        document: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "name": dict(self.name),
            "countryCodes": list(self.country_codes),
            "continent": self.continent,
            "center": [self.center[0], self.center[1]],
            "bbox": [round(value, 6) for value in self.bbox],
            "minZoom": self.min_zoom,
            "maxZoom": self.max_zoom,
            "tags": list(self.tags),
            "featured": self.featured,
        }
        if self.route_name:
            document["routeName"] = self.route_name
        return document


def bbox_around(lon: float, lat: float, width_km: float, height_km: float) -> tuple[float, float, float, float]:
    half_lat = height_km / 2 / KM_PER_DEGREE_LAT
    half_lon = width_km / 2 / (KM_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 0.01))
    return (
        max(-180.0, lon - half_lon),
        max(-MAX_MERCATOR_LAT, lat - half_lat),
        min(180.0, lon + half_lon),
        min(MAX_MERCATOR_LAT, lat + half_lat),
    )


def parse_areas(document: dict) -> list[PreviewArea]:
    if document.get("schemaVersion") != 1:
        raise ValueError("unsupported preview area list")
    sizes, zooms = document["areaSizesKm"], document["zoom"]
    areas: list[PreviewArea] = []
    seen: set[str] = set()
    for item in document["areas"]:
        if item["id"] in seen:
            raise ValueError(f"duplicate preview area {item['id']}")
        seen.add(item["id"])
        lon, lat = float(item["center"][0]), float(item["center"][1])
        width, height = item.get("sizeKm") or sizes[item["kind"]]
        low, high = zooms[item["kind"]]
        areas.append(PreviewArea(
            id=item["id"],
            kind=item["kind"],
            name=dict(item["name"]),
            country_codes=tuple(item["countryCodes"]),
            continent=item["continent"],
            center=(lon, lat),
            bbox=bbox_around(lon, lat, float(width), float(height)),
            min_zoom=int(low),
            max_zoom=int(high),
            tags=tuple(item.get("tags", [])),
            region_hints=tuple(item.get("regionHints", [])),
            route_name=item.get("routeName"),
            featured=bool(item.get("featured", False)),
        ))
    return areas


def load_areas(path: Path | None = None) -> list[PreviewArea]:
    with (path or PACKAGED_AREAS).open(encoding="utf-8") as handle:
        return parse_areas(json.load(handle))


def tile_range(bbox: tuple[float, float, float, float], zoom: int) -> tuple[int, int, int, int]:
    """Inclusive slippy-map tile range (x0, y0, x1, y1) covering ``bbox``."""
    west, south, east, north = bbox
    return (_lon_to_tile(west, zoom), _lat_to_tile(north, zoom),
            _lon_to_tile(east, zoom), _lat_to_tile(south, zoom))


def tile_count(area: PreviewArea) -> int:
    total = 0
    for zoom in range(area.min_zoom, area.max_zoom + 1):
        x0, y0, x1, y1 = tile_range(area.bbox, zoom)
        total += (x1 - x0 + 1) * (y1 - y0 + 1)
    return total


def _lon_to_tile(lon: float, zoom: int) -> int:
    n = 1 << zoom
    return min(n - 1, max(0, int(math.floor((lon + 180.0) / 360.0 * n))))


def _lat_to_tile(lat: float, zoom: int) -> int:
    n = 1 << zoom
    rad = math.radians(max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat)))
    value = (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0
    return min(n - 1, max(0, int(math.floor(value * n))))

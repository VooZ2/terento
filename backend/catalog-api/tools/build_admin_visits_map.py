"""Generate the Web visits country map from the Admin world map.

Usage: python tools/build_admin_visits_map.py

Input: WORLD_MAP_SVG in src/terento_catalog/admin_world_map.py (OpenStreetMap
country boundaries via osm-countries-geojson, ODbL; built by
tools/build_admin_world_map.py, equirectangular, without Antarctica). Output:
src/terento_catalog/admin_visits_map.py, the same countries in the Equal Earth
projection (Šavrič, Patterson and Jenny 2018), simplified for a small,
decorative choropleth: whole-unit relative path commands, at most ~120 KB.
No runtime map service or dependency.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from terento_catalog.admin_world_map import WORLD_MAP_SVG  # noqa: E402

WIDTH = 1000  # viewBox width; the height follows the projected extent
TOLERANCE = 0.5  # Douglas–Peucker tolerance in output units
MIN_RING_AREA = 3.0  # rings smaller than this go, except a country's largest
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def equal_earth(lon: float, lat: float) -> tuple[float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    theta = math.asin(M * math.sin(phi))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = 2 * math.sqrt(3) * lam * math.cos(theta) / (3 * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = theta * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, -y


def simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) < 4:
        return points
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        farthest, distance = start, 0.0
        for index in range(start + 1, end):
            px, py = points[index]
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length)) if length else 0.0
            squared = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if squared > distance:
                farthest, distance = index, squared
        if distance > tolerance * tolerance:
            keep.add(farthest)
            pending.extend([(start, farthest), (farthest, end)])
    return [points[index] for index in sorted(keep)]


def area(points: list[tuple[int, int]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def main() -> None:
    countries: list[tuple[str, list[list[tuple[float, float]]]]] = []
    for code, d in re.findall(r'<path id="([a-z]{2})" fill-rule="evenodd" d="([^"]+)"/>', WORLD_MAP_SVG):
        rings = []
        for ring in re.findall(r"M([^Z]+)Z", d):
            # The source SVG: x = (lon + 180) * 2.5, y = (85 - lat) * 2.5.
            rings.append([equal_earth(float(x) / 2.5 - 180, 85 - float(y) / 2.5)
                          for x, y in (pair.split(",") for pair in ring.split("L"))])
        countries.append((code, rings))
    xs = [x for _, rings in countries for ring in rings for x, _ in ring]
    ys = [y for _, rings in countries for ring in rings for _, y in ring]
    scale = WIDTH / (max(xs) - min(xs))
    left, top = min(xs), min(ys)
    height = math.ceil((max(ys) - top) * scale)
    paths = []
    for code, rings in countries:
        shaped = []
        for ring in rings:
            points = simplify([((x - left) * scale, (y - top) * scale) for x, y in ring], TOLERANCE)
            whole: list[tuple[int, int]] = []
            for x, y in points:
                point = (round(x), round(y))
                if not whole or point != whole[-1]:
                    whole.append(point)
            if len(whole) > 1 and whole[0] == whole[-1]:
                whole.pop()
            if len(whole) >= 3:
                shaped.append(whole)
        if not shaped:
            # A microstate (Andorra, Monaco, Vatican …) keeps a small diamond
            # at its centre so its colour still shows.
            points = [((x - left) * scale, (y - top) * scale) for ring in rings for x, y in ring]
            cx = round(sum(x for x, _ in points) / len(points))
            cy = round(sum(y for _, y in points) / len(points))
            shaped = [[(cx, cy - 2), (cx + 2, cy), (cx, cy + 2), (cx - 2, cy)]]
        largest = max(shaped, key=area)
        shaped = [ring for ring in shaped if ring is largest or area(ring) >= MIN_RING_AREA]
        commands = []
        for ring in shaped:
            (x0, y0), rest = ring[0], ring[1:]
            moves, (px, py) = [], ring[0]
            for x, y in rest:
                moves.append(f"{x - px} {y - py}".replace(" -", "-"))
                px, py = x, y
            commands.append(f"M{x0} {y0}l" + " ".join(moves).replace(" -", "-") + "z")
        paths.append(f'<path id="v-{code}" d="{"".join(commands)}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" aria-hidden="true" focusable="false">'
           + "".join(paths) + "</svg>")
    source = hashlib.sha256(WORLD_MAP_SVG.encode("utf-8")).hexdigest()
    target = ROOT / "src/terento_catalog/admin_visits_map.py"
    target.write_text(
        "# Generated by tools/build_admin_visits_map.py; do not edit by hand.\n"
        "# OpenStreetMap country boundaries via osm-countries-geojson, ODbL\n"
        "# (© OpenStreetMap contributors), from admin_world_map.WORLD_MAP_SVG\n"
        f"# (SHA-256 {source}), Equal Earth projection, without Antarctica.\n"
        f"VISITS_MAP_SOURCE_SHA256 = {source!r}\n"
        f"VISITS_MAP_SVG = {svg!r}\n")
    print(len(paths), "countries;", len(svg), "SVG bytes;", f"viewBox {WIDTH}x{height}")


if __name__ == "__main__":
    main()

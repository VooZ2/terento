"""Preview styles and the choice of a covering catalog package per area."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from .areas import PreviewArea


@dataclass(frozen=True)
class PreviewStyle:
    id: str
    provider_id: str
    map_type: str | None
    name: str
    # Optional add-on artifact kinds drawn on top of the main map.
    overlays: tuple[str, ...] = ()


STYLES: tuple[PreviewStyle, ...] = (
    PreviewStyle("freizeitkarte", "freizeitkarte", None, "Freizeitkarte"),
    PreviewStyle("opentopomap", "opentopomap", None, "OpenTopoMap", overlays=("contours",)),
    PreviewStyle("maprando", "maprando", None, "MapRando"),
    PreviewStyle("bbbike", "bbbike", "bbbike-latin1", "BBBike"),
    PreviewStyle("bbbike-ontrail", "bbbike", "ontrail-latin1", "BBBike (Ontrail)"),
)
STYLE_BY_ID = {style.id: style for style in STYLES}

# Freizeitkarte region identifiers start with ISO 3166-1 alpha-3 codes.
_FZK_ALPHA3 = {
    "ALB": "AL", "AND": "AD", "AUT": "AT", "BEL": "BE", "BGR": "BG", "BIH": "BA",
    "BLR": "BY", "CHE": "CH", "CYP": "CY", "CZE": "CZ", "DEU": "DE", "DNK": "DK",
    "ESP": "ES", "EST": "EE", "FIN": "FI", "FRA": "FR", "FRO": "FO", "GBR": "GB",
    "GRC": "GR", "HRV": "HR", "HUN": "HU", "IMN": "IM", "IRL": "IE", "ISL": "IS",
    "ITA": "IT", "LIE": "LI", "LTU": "LT", "LUX": "LU", "LVA": "LV", "MDA": "MD",
    "MKD": "MK", "MLT": "MT", "MNE": "ME", "NLD": "NL", "NOR": "NO", "POL": "PL",
    "PRT": "PT", "ROU": "RO", "SRB": "RS", "SVK": "SK", "SVN": "SI", "SWE": "SE",
    "TUR": "TR", "UKR": "UA",
}
_UNUSABLE = {"FAILED", "UNAVAILABLE"}
_FZK_GROUPS = {"BALKAN": ("AL", "BA", "BG", "GR", "HR", "ME", "MK", "RS", "SI", "XK")}


@dataclass(frozen=True)
class Candidate:
    package_id: str
    package_version: str
    provider_id: str
    region_text: str
    size_bytes: int
    main_url: str
    overlay_urls: tuple[str, ...]
    hinted: bool


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def package_country_codes(row: dict[str, Any]) -> set[str]:
    codes = {str(code).upper() for code in (row.get("country_codes") or []) if code}
    if row.get("provider_id") == "freizeitkarte":
        region = str(row.get("provider_region_id") or "").upper()
        tokens = [token for token in re.split(r"[^A-Z]+", region) if token]
        for token in tokens:
            if token in _FZK_ALPHA3:
                codes.add(_FZK_ALPHA3[token])
            codes.update(_FZK_GROUPS.get(token, ()))
        codes = {code if len(code) == 2 else _FZK_ALPHA3.get(code, code) for code in codes}
    return codes


def packages_from_snapshot(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group catalog snapshot rows (one per artifact) into packages."""
    packages: dict[str, dict[str, Any]] = {}
    for row in rows:
        package_id = row.get("package_id")
        if not package_id:
            continue
        package = packages.setdefault(package_id, {
            "package_id": package_id,
            "provider_id": row["provider_id"],
            "provider_status": row.get("provider_status"),
            "provider_region_id": row.get("provider_region_id") or "",
            "region": row.get("package_region") or "",
            "name": row.get("package_name") or "",
            "map_type": row.get("map_type"),
            "country_codes": row.get("country_codes") or [],
            "availability": row.get("availability"),
            "downloads_disabled": bool(row.get("downloads_disabled")),
            "version": str(row.get("release_id") or row.get("release") or ""),
            "artifacts": {},
        })
        kind = row.get("artifact_kind")
        if kind and row.get("artifact_source_url"):
            package["artifacts"][kind] = {
                "url": row["artifact_source_url"],
                "size_bytes": int(row.get("artifact_size_bytes") or 0),
                "validation_status": row.get("artifact_validation_status"),
            }
    return list(packages.values())


def candidates_for(
    area: PreviewArea,
    style: PreviewStyle,
    packages: Iterable[dict[str, Any]],
    *,
    known_bounds: dict[tuple[str, str], tuple[float, float, float, float]] | None = None,
    limit: int = 3,
) -> list[Candidate]:
    """Packages that may cover the area, most likely first.

    Country membership is required. Region hints from the area list move
    matching packages to the front; smaller downloads come first otherwise.
    Packages whose recorded bounds miss the area centre are skipped.
    """
    known_bounds = known_bounds or {}
    hints = [normalize(hint) for hint in area.region_hints]
    lon, lat = area.center
    result: list[Candidate] = []
    for package in packages:
        if package["provider_id"] != style.provider_id:
            continue
        if style.map_type is not None and package.get("map_type") != style.map_type:
            continue
        if package.get("availability") not in {"AVAILABLE", None}:
            continue
        if package.get("downloads_disabled"):
            continue
        codes = package_country_codes(package)
        if "RU" in codes or not codes & set(area.country_codes):
            continue
        main = package["artifacts"].get("main")
        if not main or main.get("validation_status") in _UNUSABLE:
            continue
        bounds = known_bounds.get((package["package_id"], package["version"]))
        if bounds is not None:
            west, south, east, north = bounds
            if not (west <= lon <= east and south <= lat <= north):
                continue
        region_text = normalize(" ".join((package["provider_region_id"], package["region"], package["name"])))
        overlays = tuple(
            package["artifacts"][kind]["url"]
            for kind in style.overlays
            if kind in package["artifacts"]
            and package["artifacts"][kind].get("validation_status") not in _UNUSABLE
        )
        result.append(Candidate(
            package_id=package["package_id"],
            package_version=package["version"],
            provider_id=package["provider_id"],
            region_text=region_text,
            size_bytes=main["size_bytes"] + sum(
                package["artifacts"][kind]["size_bytes"] for kind in style.overlays if kind in package["artifacts"]
            ),
            main_url=main["url"],
            overlay_urls=overlays,
            hinted=any(hint and hint in region_text for hint in hints),
        ))
    result.sort(key=lambda item: (not item.hinted, item.size_bytes, item.package_id))
    return result[:limit]

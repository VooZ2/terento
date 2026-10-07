"""Public ``/maps/previews/manifest.json`` document."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from .areas import PreviewArea
from .styles import STYLES

DATA_ATTRIBUTION = "© OpenStreetMap contributors"
DATA_ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"
# Provider credits shown next to each preview layer. They restate the
# attribution each provider asks for; map data credit is shown separately.
STYLE_CREDITS: dict[str, tuple[str, str]] = {
    "freizeitkarte": ("Map © Freizeitkarte (FZK project)", "https://www.freizeitkarte-osm.de/garmin/en/index.html"),
    "opentopomap": ("Map rendering © OpenTopoMap (CC BY-SA)", "https://opentopomap.org/about"),
    "maprando": ("MapRando by Alexis Lecanu", "https://ravenfeld.gitlab.io/open-garmin-map/"),
    "bbbike": ("Garmin map style by BBBike", "https://extract.bbbike.org/garmin.html"),
    "bbbike-ontrail": ("Garmin Ontrail style by BBBike", "https://extract.bbbike.org/garmin.html"),
}


def build_manifest(
    *,
    areas: Iterable[PreviewArea],
    layers: dict[tuple[str, str], dict[str, Any]],
    published: set[tuple[str, str]],
    scores: dict[str, float | None],
    release: str | None,
    public_base_url: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    template = (
        f"{public_base_url.rstrip('/')}/assets/previews/{release}/{{area}}/{{style}}/{{z}}/{{x}}/{{y}}.webp"
        if release else None
    )
    documents = []
    for area in areas:
        document = area.public()
        document["diffScore"] = _rounded(scores.get(area.id))
        area_layers = []
        for style in STYLES:
            row = layers.get((area.id, style.id))
            status = "PENDING"
            version = rendered = None
            if row is not None:
                if row["status"] == "NOT_COVERED":
                    status = "NOT_COVERED"
                # The release's own tiles decide availability: a renderer
                # stopped mid-publish may not have recorded the release yet.
                elif (area.id, style.id) in published and row["status"] == "AVAILABLE" and release:
                    status = "AVAILABLE"
                    version = row.get("package_version")
                    rendered = _iso(row.get("rendered_at"))
            area_layers.append({
                "style": style.id,
                "status": status,
                "packageVersion": version,
                "renderedAt": rendered,
            })
        document["layers"] = area_layers
        documents.append(document)
    return {
        "schemaVersion": 1,
        "generatedAt": _iso(now or datetime.now(timezone.utc)),
        "release": release,
        "tileUrlTemplate": template,
        "dataAttribution": DATA_ATTRIBUTION,
        "dataAttributionUrl": DATA_ATTRIBUTION_URL,
        "styles": [
            {
                "id": style.id,
                "providerId": style.provider_id,
                "mapType": style.map_type,
                "name": style.name,
                "attribution": STYLE_CREDITS[style.id][0],
                "attributionUrl": STYLE_CREDITS[style.id][1],
            }
            for style in STYLES
        ],
        "areas": documents,
    }


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(max(0.0, min(1.0, float(value))), 4)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(value)

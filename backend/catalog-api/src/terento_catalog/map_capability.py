"""Map Manager capability classification shared with the native client.

This is not compatibility evidence and does not authorize a device write.
It answers only whether Garmin Map Manager lists the model for additional
maps. The prefix lists must stay aligned with
`GarminMapCapabilityRegistry` in the macOS client.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


SUPPORTED_PREFIXES = (
    "d2 mach 1",
    "d2 mach 2",
    "descent mk1",
    "descent mk2",
    "descent mk3",
    "enduro 2",
    "enduro 3",
    "epix gen 2",
    "epix pro gen 2",
    "fenix 5x",
    "fenix 5 plus",
    "fenix 6",
    "fenix 7",
    "fenix 8",
    "fenix e",
    "forerunner 945",
    "forerunner 955",
    "forerunner 965",
    "forerunner 970",
    "marq",
    "quatix 6",
    "quatix 7",
    "quatix 8",
    "tactix charlie",
    "tactix delta",
    "tactix 7",
    "tactix 8",
    "venu x1",
)

KNOWN_NON_MAP_PREFIXES = (
    "approach",
    "descent g1",
    "descent g2",
    "forerunner 55",
    "forerunner 165",
    "forerunner 255",
    "forerunner 265",
    "forerunner 570",
    "instinct",
    "lily",
    "venu",
    "vivoactive",
    "vivomove",
)


def classify_map_capable(
    model: Any,
    manufacturer: Any = "Garmin",
) -> bool | None:
    """Return True, False, or None when the model is unrecognized."""

    if not _is_garmin(manufacturer):
        return None

    normalized = _normalize_model(model)
    if not normalized:
        return None
    if normalized.startswith("approach s70"):
        return False
    if any(normalized.startswith(prefix) for prefix in SUPPORTED_PREFIXES):
        return True
    if any(normalized.startswith(prefix) for prefix in KNOWN_NON_MAP_PREFIXES):
        return False
    return None


def _is_garmin(value: Any) -> bool:
    return "garmin" in _normalize_model(value)


def _normalize_model(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower())
    normalized = " ".join(normalized.split())
    if normalized.startswith("garmin "):
        normalized = normalized[len("garmin "):]
    return normalized

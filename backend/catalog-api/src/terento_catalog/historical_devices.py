"""Reviewed historical Garmin identities used to resolve compatibility evidence.

The retail collector is intentionally not the source of truth for this list.
These records describe models that can still be encountered in the native app
even after Garmin removes them from its current retail category.  The registry
is an identity/provenance aid only: it never grants permission to write to a
device.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


HISTORICAL_REGISTRY_VERSION = 2
REGISTRY_SOURCE_URL = "https://developer.garmin.com/connect-iq/compatible-devices/"
GARMIN_CATEGORY_URL = "https://www.garmin.com/en-US/c/wearables-smartwatches/"


@dataclass(frozen=True)
class HistoricalDeviceSpec:
    id: str
    family_id: str
    family_name: str
    manufacturer: str
    model: str
    canonical_model: str
    variant: str
    case_size_mm: int | None
    display_type: str | None
    product_url: str
    source_url: str = REGISTRY_SOURCE_URL
    source_image_url: str | None = None
    aliases: tuple[str, ...] = ()


def _spec(
    id: str,
    model: str,
    canonical_model: str,
    variant: str,
    case_size_mm: int | None,
    *,
    family_id: str = "garmin-fenix",
    family_name: str = "fēnix",
    display_type: str | None = None,
    aliases: tuple[str, ...] = (),
) -> HistoricalDeviceSpec:
    return HistoricalDeviceSpec(
        id=id,
        family_id=family_id,
        family_name=family_name,
        manufacturer="Garmin",
        model=model,
        canonical_model=canonical_model,
        variant=variant,
        case_size_mm=case_size_mm,
        display_type=display_type,
        product_url=GARMIN_CATEGORY_URL,
        aliases=(canonical_model, *aliases),
    )


# Keep this list small, explicit, and reviewable.  It is deliberately not
# generated from the current Garmin retail category.
HISTORICAL_DEVICE_REGISTRY: tuple[HistoricalDeviceSpec, ...] = (
    _spec("garmin-fenix-7-47", "fēnix 7", "fenix 7", "47 mm", 47),
    _spec(
        "garmin-fenix-7s-42", "fēnix 7S", "fenix 7s", "42 mm", 42,
        aliases=("fenix 7s",),
    ),
    _spec(
        "garmin-fenix-7x-51", "fēnix 7X", "fenix 7x", "51 mm", 51,
        aliases=("fenix 7x",),
    ),
    _spec("garmin-fenix-6-47", "fēnix 6", "fenix 6", "47 mm", 47),
    _spec(
        "garmin-fenix-6s-42", "fēnix 6S", "fenix 6s", "42 mm", 42,
        aliases=("fenix 6s",),
    ),
    _spec(
        "garmin-fenix-6x-51", "fēnix 6X", "fenix 6x", "51 mm", 51,
        aliases=("fenix 6x",),
    ),
    _spec(
        "garmin-epix-gen-2-47",
        "epix (Gen 2)",
        "epix gen 2",
        "47 mm",
        47,
        family_id="garmin-epix",
        family_name="epix",
        aliases=("epix", "epix gen 2"),
    ),
    _spec(
        "garmin-forerunner-955",
        "Forerunner 955",
        "forerunner 955",
        "Standard",
        None,
        family_id="garmin-forerunner",
        family_name="Forerunner",
        aliases=("forerunner 955",),
    ),
    # These families are retained because the native Map Manager registry
    # recognizes them, even though Garmin no longer lists them in its current
    # retail smartwatch category. Family-level records intentionally avoid
    # guessing a discontinued size/display variant.
    _spec(
        "garmin-d2-mach-1", "D2 Mach 1", "d2 mach 1", "Historical", None,
        family_id="garmin-d2", family_name="D2",
    ),
    _spec(
        "garmin-descent-mk1", "Descent Mk1", "descent mk1", "Historical", None,
        family_id="garmin-descent", family_name="Descent",
    ),
    _spec(
        "garmin-descent-mk2", "Descent Mk2", "descent mk2", "Historical", None,
        family_id="garmin-descent", family_name="Descent",
    ),
    _spec(
        "garmin-enduro-2", "Enduro 2", "enduro 2", "Historical", None,
        family_id="garmin-enduro", family_name="Enduro",
    ),
    _spec(
        "garmin-epix-pro-gen-2", "epix Pro (Gen 2)", "epix pro gen 2", "Historical", None,
        family_id="garmin-epix", family_name="epix",
    ),
    _spec("garmin-fenix-5x", "fēnix 5X", "fenix 5x", "Historical", None),
    _spec("garmin-fenix-5-plus", "fēnix 5 Plus", "fenix 5 plus", "Historical", None),
    _spec(
        "garmin-forerunner-945", "Forerunner 945", "forerunner 945", "Historical", None,
        family_id="garmin-forerunner", family_name="Forerunner",
    ),
    _spec(
        "garmin-forerunner-965", "Forerunner 965", "forerunner 965", "Historical", None,
        family_id="garmin-forerunner", family_name="Forerunner",
    ),
    _spec(
        "garmin-quatix-6", "quatix 6", "quatix 6", "Historical", None,
        family_id="garmin-quatix", family_name="quatix",
    ),
    _spec(
        "garmin-quatix-7", "quatix 7", "quatix 7", "Historical", None,
        family_id="garmin-quatix", family_name="quatix",
    ),
    _spec(
        "garmin-tactix-charlie", "tactix Charlie", "tactix charlie", "Historical", None,
        family_id="garmin-tactix", family_name="tactix",
    ),
    _spec(
        "garmin-tactix-delta", "tactix Delta", "tactix delta", "Historical", None,
        family_id="garmin-tactix", family_name="tactix",
    ),
    _spec(
        "garmin-tactix-7", "tactix 7", "tactix 7", "Historical", None,
        family_id="garmin-tactix", family_name="tactix",
    ),
)

_BY_ID = {spec.id: spec for spec in HISTORICAL_DEVICE_REGISTRY}


def normalize_identity(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    text = " ".join(text.split())
    if text.startswith("garmin "):
        text = text[len("garmin "):]
    return text


def historical_device_spec(device_id: str | None) -> HistoricalDeviceSpec | None:
    return _BY_ID.get(device_id or "")


def historical_device_for_event(event: dict[str, object]) -> HistoricalDeviceSpec | None:
    """Resolve a report to a reviewed historical identity without fuzzy joins."""

    identities = [
        normalize_identity(event.get("model")),
        normalize_identity(event.get("compatibilityIdentity")),
    ]
    identities = [identity for identity in identities if identity]
    if not identities:
        return None
    case_size = event.get("caseSizeMm")
    try:
        case_size = int(case_size) if case_size is not None else None
    except (TypeError, ValueError):
        case_size = None
    if case_size is None:
        for identity in identities:
            size_match = re.search(r"\b(\d{2})\s*mm\b", identity)
            if size_match:
                case_size = int(size_match.group(1))
                break

    candidates: list[HistoricalDeviceSpec] = []
    for spec in HISTORICAL_DEVICE_REGISTRY:
        aliases = {normalize_identity(alias) for alias in spec.aliases}
        if not any(
            identity == alias
            or (
                identity.startswith(f"{alias} ")
                and re.fullmatch(
                    r"\d{2,3}\s*mm", identity[len(alias):].strip()
                ) is not None
            )
            for identity in identities
            for alias in aliases
        ):
            continue
        if spec.case_size_mm is not None and case_size is not None and spec.case_size_mm != case_size:
            continue
        candidates.append(spec)

    exact_size = [spec for spec in candidates if spec.case_size_mm == case_size]
    if exact_size:
        return exact_size[0]
    unspecified_size = [spec for spec in candidates if spec.case_size_mm is None]
    if unspecified_size:
        return unspecified_size[0]
    return candidates[0] if candidates else None


def all_historical_device_specs() -> tuple[HistoricalDeviceSpec, ...]:
    return HISTORICAL_DEVICE_REGISTRY

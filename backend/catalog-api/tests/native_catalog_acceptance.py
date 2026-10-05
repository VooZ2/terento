"""Python mirror of the native per-package catalog acceptance rules.

Mirrors ``MapCatalogLoader.isCompatible`` in
``app/TerentoCore/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift`` together
with ``BBBikeProviderAdapter.validIdentity``/``expectedIMGIdentity``,
``MapPackage.hasUsableMainArtifact`` and the reviewed provider URL policies.
Released clients reject the *whole* catalog when one package fails, so a
backend publication must satisfy every rule for every package.

Provider-specific IMG identity matching (``MapIdentityMatcher``) is not
mirrored here; the native released-client gate
(``Packaging/validate-released-map-catalog.sh``) still runs the real Swift code
before deployment. Keep this mirror in step with the Swift sources it names.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

PROVIDER_HOSTS = {
    "freizeitkarte": {"download.freizeitkarte-osm.de"},
    "opentopomap": {"garmin.opentopomap.org"},
    "maprando": {"ravenfeld.fr"},
    "bbbike": {"data.bbbike.org"},
}
BBBIKE_MAP_TYPES = {"bbbike-latin1", "ontrail-latin1"}
BBBIKE_PATH = re.compile(
    r"^(?:africa|asia|australia-oceania|central-america|europe|north-america|south-america|antarctica)"
    r"/[a-z0-9]+(?:[-/][a-z0-9]+)*$"
)
BBBIKE_EXAMPLE_REGIONS = {"asia/cambodia", "asia/jordan", "europe/luxembourg"}


def _provider(value: Any) -> str:
    return str(value or "").strip().lower()


def _main(package: dict[str, Any]) -> dict[str, Any] | None:
    return next((item for item in package.get("artifacts") or [] if item.get("kind") == "main"), None)


def _download_url(package: dict[str, Any]) -> str | None:
    main = _main(package) or {}
    return package.get("sourceURL") or package.get("sourceUrl") or main.get("sourceURL") or main.get("sourceUrl")


def _url_allowed(provider: str, url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url)
    return (
        parts.scheme.lower() == "https"
        and (parts.hostname or "").lower() in PROVIDER_HOSTS.get(provider, set())
        and parts.username is None
        and parts.password is None
    )


def bbbike_valid_identity(package: dict[str, Any]) -> bool:
    path = str(package.get("providerRegionId") or "")
    map_type = package.get("mapType")
    canonical = str(package.get("canonicalRegionId") or "")
    return (
        _provider(package.get("providerId")) == "bbbike"
        and bool(BBBIKE_PATH.match(path)) and len(path.encode()) <= 180
        and map_type in BBBIKE_MAP_TYPES
        and canonical == (path + "-" + map_type).replace("/", "-").upper()
        and package.get("region") == canonical
        and package.get("id") == "bbbike-" + canonical.lower()
        and (package.get("version") or {}).get("day") is not None
    )


def _bbbike_proof_matches(package: dict[str, Any]) -> bool:
    proof = (_main(package) or {}).get("sourceProof")
    if not isinstance(proof, dict) or not bbbike_valid_identity(package):
        return False
    etag = proof.get("etag")
    try:
        datetime.fromisoformat(str(proof.get("generatedAt")).replace("Z", "+00:00"))
    except ValueError:
        return False
    expected_size = package.get("downloadSizeBytes") or package.get("sizeBytes")
    region, map_type = proof.get("sourceRegion"), proof.get("mapType")
    url = _download_url(package)
    leaf = str(region or "").split("/")[-1]
    suffix = f"{region}/{leaf}.osm.garmin-{map_type}.zip"
    path = urlsplit(url or "").path
    version = package.get("version") or {}
    version_label = "{:04d}-{:02d}-{:02d}".format(
        int(version.get("year") or 0), int(version.get("month") or 0), int(version.get("day") or 0))
    install_size = proof.get("installSizeBytes")
    download_size = proof.get("downloadSizeBytes")
    return (
        proof.get("sourceURL") == url
        and isinstance(etag, str) and etag.startswith('"') and etag.endswith('"') and len(etag) > 2
        and install_size == package.get("installSizeBytes")
        and isinstance(install_size, int) and install_size > 0
        and isinstance(download_size, int) and download_size > 0
        and bool(re.fullmatch(r"[a-f0-9]{32}", str(proof.get("payloadMD5") or "")))
        and bool(re.fullmatch(r"[a-f0-9]{64}", str(proof.get("revision") or "")))
        and proof.get("payloadPath") == f"{leaf}-garmin-{map_type}/gmapsupp.img"
        and str(proof.get("generatedAt") or "").startswith(version_label + "T")
        and bool(proof.get("lastModified"))
        and region == package.get("providerRegionId")
        and map_type == package.get("mapType")
        and proof.get("sourceIdentity") == f"bbbike:{region}:{map_type}"
        and proof.get("downloadSizeBytes") == expected_size
        and (path == "/osm/garmin/region/" + suffix
             or (region in BBBIKE_EXAMPLE_REGIONS and path == "/osm/garmin/example/" + suffix))
    )


def package_rejections(package: dict[str, Any]) -> list[str]:
    """Return why a released client would reject this package (empty when accepted)."""
    provider = _provider(package.get("providerId"))
    main = _main(package)
    if provider == "bbbike" and main is not None and main.get("validationState") == "unavailable":
        reasons = []
        if not bbbike_valid_identity(package):
            reasons.append("bbbike identity")
        if len(package.get("artifacts") or []) != 1:
            reasons.append("unavailable bbbike package must have exactly one artifact")
        if main.get("sourceProof") is not None:
            reasons.append("unavailable bbbike main artifact must not carry sourceProof")
        return reasons
    reasons = []
    if provider not in PROVIDER_HOSTS:
        reasons.append("no native adapter")
    if not _url_allowed(provider, _download_url(package)):
        reasons.append("download URL outside reviewed provider policy")
    if main is None or not (main.get("sourceURL") or main.get("sourceUrl")):
        reasons.append("no usable main artifact")
    elif provider == "bbbike":
        if main.get("validationState") in ("unavailable", "failed"):
            reasons.append("bbbike main artifact is not usable")
        if not _bbbike_proof_matches(package):
            reasons.append("bbbike source proof does not establish the IMG identity")
    if not str(package.get("providerRegionId") or package.get("identifier") or "").strip():
        reasons.append("missing provider region identity")
    return reasons


def catalog_rejections(catalog: dict[str, Any]) -> list[str]:
    """Mirror the whole-catalog acceptance used by released native clients."""
    providers = catalog.get("providers") or []
    provider_ids = [_provider(item.get("id")) for item in providers]
    packages = [
        {**package, "providerId": provider.get("id")}
        for provider in providers for package in provider.get("maps") or []
    ]
    package_ids = [str(package.get("id") or "") for package in packages]
    reasons = []
    if not provider_ids or not packages:
        reasons.append("catalog has no providers or packages")
    if any(not item for item in provider_ids) or len(set(provider_ids)) != len(provider_ids):
        reasons.append("provider ids must be unique and non-empty")
    if any(not item.strip() for item in package_ids) or len(set(package_ids)) != len(package_ids):
        reasons.append("package ids must be unique and non-empty")
    bbbike = [(p.get("providerRegionId"), p.get("mapType")) for p in packages if _provider(p.get("providerId")) == "bbbike"]
    if len(set(bbbike)) != len(bbbike):
        reasons.append("bbbike identities must be unique")
    for package in packages:
        reasons.extend(f"{package.get('id')}: {reason}" for reason in package_rejections(package))
    return reasons

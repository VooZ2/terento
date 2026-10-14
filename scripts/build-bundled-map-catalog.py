#!/usr/bin/env python3
"""Keep the bundled fallback map catalog free of packages Terento must not offer.

Usage:
  scripts/build-bundled-map-catalog.py --write   remove such packages in place
  scripts/build-bundled-map-catalog.py --check   fail if any remain

The bundled file is the legacy catalogVersion 1 catalog the app shows when the
catalog API is unreachable; it never authorizes a provider download on its
own. Withheld packages (russia, Crimea) and packages that cannot be written to
a FAT32 watch volume (over 4,294,967,295 bytes) are never bundled. Output is
deterministic and keeps the existing formatting; no network request is made.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLED = ROOT / "app/TerentoCore/Sources/TerentoPoC/Resources/Maps/catalog.json"
FAT32_MAX = 4_294_967_295
PROVIDER_ORDER = ("freizeitkarte", "opentopomap", "bbbike", "maprando")


def strict_load(raw: bytes):
    def unique(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate JSON key in {keys}")
        return dict(pairs)

    def reject(constant):
        raise ValueError(f"non-finite number {constant}")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject)


def is_size(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def withheld(provider_id: str, package: dict) -> bool:
    """Mirror of the backend acquisition policy and the app's MapAcquisitionPolicy."""
    codes = {str(code).upper() for code in package.get("countryCodes") or []}
    region = str(package.get("canonicalRegionId") or package.get("region") or "").upper()
    tokens = " ".join(str(package.get(key) or "")
                      for key in ("id", "region", "identifier", "providerRegionId", "name")).upper()
    if package.get("availability") == "WITHHELD" or "RU" in codes:
        return True
    if ("UA" in codes and region == "CRIMEA") or "CRIMEA" in tokens or "CRIMEAN" in tokens:
        return True
    if provider_id == "freizeitkarte" and region.replace("_", "-").replace("+", "-").startswith("RUS"):
        return True
    return "RUSSIA" in tokens or "RUSSIAN" in tokens


def install_size(item: dict) -> int:
    return max(value for value in (item.get("installSizeBytes"), item.get("sizeBytes"), 0) if is_size(value))


def too_large(package: dict) -> bool:
    return install_size(package) > FAT32_MAX or any(
        artifact.get("required") and install_size(artifact) > FAT32_MAX
        for artifact in package.get("artifacts") or [])


def render(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def check(text: str) -> dict:
    document = strict_load(text.encode("utf-8"))
    if render(document) != text:
        raise ValueError("bundled catalog is not canonically formatted")
    if set(document) != {"catalogVersion", "updatedAt", "providers"} or document["catalogVersion"] != 1:
        raise ValueError("bundled catalog must be the catalogVersion 1 projection")
    if tuple(provider["id"] for provider in document["providers"]) != PROVIDER_ORDER:
        raise ValueError("bundled catalog must list the four reviewed providers in order")
    ids = []
    for provider in document["providers"]:
        maps = provider["maps"]
        if [package["id"] for package in maps] != sorted(package["id"] for package in maps):
            raise ValueError(f"{provider['id']}: maps must be sorted by id")
        for package in maps:
            ids.append(package["id"])
            if withheld(provider["id"], package):
                raise ValueError(f"{package['id']}: withheld package must not be bundled")
            if too_large(package) or any(install_size(a) > FAT32_MAX for a in package.get("artifacts") or []):
                raise ValueError(f"{package['id']}: exceeds the FAT32 file size limit")
    if len(ids) != len(set(ids)):
        raise ValueError("bundled catalog package ids must be unique")
    return {provider["id"]: len(provider["maps"]) for provider in document["providers"]}


def prune(text: str) -> tuple[str, list[tuple[str, str]]]:
    document = strict_load(text.encode("utf-8"))
    dropped = []
    for provider in document["providers"]:
        kept = []
        for package in provider["maps"]:
            if withheld(provider["id"], package):
                dropped.append((package["id"], "withheld"))
            elif too_large(package):
                dropped.append((package["id"], "fat32"))
            else:
                artifacts = package.get("artifacts") or []
                small = [artifact for artifact in artifacts if install_size(artifact) <= FAT32_MAX]
                if len(small) != len(artifacts):
                    dropped.append((package["id"], "optional-artifact-fat32"))
                    package["artifacts"] = small
                kept.append(package)
        provider["maps"] = kept
    return render(document), dropped


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = BUNDLED.read_text(encoding="utf-8")
    if args.write:
        text, dropped = prune(text)
        BUNDLED.write_text(text, encoding="utf-8")
        for package_id, reason in dropped:
            print(f"removed {package_id}: {reason}")
    counts = check(text)
    print(f"Bundled catalog PASS: {counts}, total {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

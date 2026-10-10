#!/usr/bin/env python3
"""Select the minimum safe Terento test suites for changed repository paths."""

from __future__ import annotations

import json
import sys
from pathlib import PurePosixPath


ALL_SUITES = ("site", "app", "native", "backend", "release", "shared", "ci")
# Fallback for repository automation that the macOS app and native core never
# read: every other suite still runs, the long macOS app/native suites do not.
NON_MAC_FALLBACK = ("site", "backend", "release", "shared", "ci")

# Markdown documents that suite tests read as contracts. Other Markdown only
# needs the always-selected shared and CI documentation checks.
DOCUMENT_SUITES = {
    "README.md": ("release", "site"),
    "RELEASE_NOTES.md": ("release",),
    "THIRD_PARTY_NOTICES.md": ("release",),
    "VERSIONING.md": ("release",),
    "Packaging/README.md": ("release",),
    "Packaging/NativeDependencies/README.md": ("release",),
    "contracts/README.md": ("backend",),
    "site-deploy/README.md": ("site",),
}


def select_suites(paths: list[str]) -> list[str]:
    if not paths:
        return list(ALL_SUITES)

    selected = {"shared", "ci"}
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip().replace("\\", "/"))
        text = path.as_posix().removeprefix("./")
        if not text:
            continue

        if text.endswith(".md") and "fixtures" not in {part.lower() for part in path.parts}:
            selected.update(DOCUMENT_SUITES.get(text, ()))
            if text.startswith("legal/"):
                selected.update(("site", "release"))
            if text.startswith("brand/"):
                selected.add("shared")
            continue

        if text == "site/updates/macos-arm64.json":
            return list(ALL_SUITES)

        if text.startswith("Tests/"):
            stem = path.name.removeprefix("run-")
            if stem.startswith(("ci-", "select-test-suites")):
                selected.add("ci")
                continue
            suite = next((item for item in ALL_SUITES if stem.startswith(item + "-")), None)
            if suite:
                selected.add(suite)
                continue
            return list(ALL_SUITES)
        if text in {".github/workflows/deploy-catalog-api.yml", ".github/workflows/reusable-catalog-api-quality.yml"}:
            selected.add("backend")
            continue
        if text in {".github/workflows/deploy-site.yml", ".github/indexnow/site-state.json"}:
            selected.add("site")
            continue
        if text.startswith("contracts/fixtures/web-installer-"):
            # Web installer statistics: only the catalog API tests read these.
            selected.add("backend")
            continue
        if text == ".github/workflows/swift-ci.yml" or text.startswith("contracts/"):
            return list(ALL_SUITES)
        if text.startswith(".github/"):
            selected.update(NON_MAC_FALLBACK)
            continue
        if text.startswith("site-deploy/"):
            selected.add("site")
            continue
        if text.startswith("Packaging/"):
            selected.update(("app", "release"))
            if path.name not in {"verify-release-label.sh", "README.md"}:
                selected.add("native")
            continue
        if text.startswith("backend/catalog-api/"):
            selected.add("backend")
            if path.name in {
                "catalog.py",
                "provider_catalog.py",
                "compatibility_status.py",
                "device_catalog.py",
            }:
                selected.add("native")
            continue
        if text.startswith("site/"):
            selected.add("site")
            if text.startswith(("site/updates/", "site/releases/")):
                selected.update(("release", "app"))
            continue
        if text.startswith("scripts/"):
            if "brand" in text:
                selected.update(("site", "app"))
            elif any(
                token in text
                for token in (
                    "guide", "site", "public", "structured", "release", "about", "home",
                    "sitemap", "indexnow",
                )
            ):
                selected.update(("site", "release"))
            else:
                selected.update(NON_MAC_FALLBACK)
            continue
        if text == "app/TerentoCore/Tests/run-release-map-catalog-contract-gate-tests.sh":
            selected.add("release")
            continue
        if text.startswith("app/TerentoCore/"):
            selected.update(("app", "native"))
            continue
        if text.startswith("app/") or text.startswith("Terento.xcodeproj/"):
            selected.add("app")
            continue
        if text.startswith("internal/") or text.endswith(".md"):
            selected.add("release")
            continue
        if text in {"AGENTS.md", ".gitignore", "LICENSE"}:
            selected.add("release")
            continue
        return list(ALL_SUITES)

    return [suite for suite in ALL_SUITES if suite in selected]


def main() -> int:
    arguments = sys.argv[1:]
    as_json = False
    if arguments and arguments[0] == "--json":
        as_json = True
        arguments = arguments[1:]
    if arguments == ["--stdin"]:
        arguments = [line for line in sys.stdin.read().splitlines() if line.strip()]
    selected = select_suites(arguments)
    print(json.dumps(selected) if as_json else "\n".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

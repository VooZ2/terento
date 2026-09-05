#!/usr/bin/env python3
"""Select the minimum safe Terento test suites for changed repository paths."""

from __future__ import annotations

import json
import sys
from pathlib import PurePosixPath


ALL_SUITES = ("site", "app", "native", "backend", "release", "shared", "ci")


def select_suites(paths: list[str]) -> list[str]:
    if not paths:
        return list(ALL_SUITES)

    selected = {"shared", "ci"}
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip().replace("\\", "/"))
        text = path.as_posix().lstrip("./")
        if not text:
            continue

        if text.startswith(("Tests/", ".github/")):
            return list(ALL_SUITES)
        if text.startswith("Packaging/"):
            return list(ALL_SUITES)
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
                )
            ):
                selected.update(("site", "release"))
            else:
                return list(ALL_SUITES)
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

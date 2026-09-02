#!/usr/bin/env python3
"""Regression tests for changed-path test-suite selection."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("select-test-suites.py")
SPEC = importlib.util.spec_from_file_location("terento_test_selection", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect(paths: list[str], suites: set[str]) -> None:
    actual = set(MODULE.select_suites(paths))
    assert actual == suites, f"{paths}: expected {sorted(suites)}, got {sorted(actual)}"


def main() -> int:
    baseline = {"shared", "ci"}
    expect(["site/index.html"], baseline | {"site"})
    expect(["site/updates/macos-arm64.json"], baseline | {"site", "release", "app"})
    expect(["app/Terento/Info.plist"], baseline | {"app"})
    expect(
        ["lab/native-connectivity-poc/Sources/TerentoPoC/Installation/MapLifecycle.swift"],
        baseline | {"app", "native"},
    )
    expect(["backend/catalog-api/src/terento_catalog/admin.py"], baseline | {"backend"})
    expect(
        ["backend/catalog-api/src/terento_catalog/catalog.py"],
        baseline | {"backend", "native"},
    )
    expect(["internal/PROJECT_STATE.md"], baseline | {"release"})
    expect(["scripts/build-guide-pages.py"], baseline | {"site", "release"})
    expect(["scripts/generate-brand-tokens.py"], baseline | {"site", "app"})
    expect(["Tests/site-faq-content-tests.cjs"], set(MODULE.ALL_SUITES))
    expect([".github/workflows/swift-ci.yml"], set(MODULE.ALL_SUITES))
    expect(["Packaging/release.sh"], set(MODULE.ALL_SUITES))
    expect(["unknown-project-file.toml"], set(MODULE.ALL_SUITES))
    expect([], set(MODULE.ALL_SUITES))
    process = subprocess.run(
        [str(MODULE_PATH), "--json", "--stdin"],
        input="site/index.html\n",
        text=True,
        check=True,
        capture_output=True,
    )
    assert set(json.loads(process.stdout)) == baseline | {"site"}
    print("PASS: changed paths select the minimum safe test suites and fail open to all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regression tests for changed-path test-suite selection."""

from __future__ import annotations

import importlib.util
import json
import re
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
    expect(["site/updates/macos-arm64.json"], set(MODULE.ALL_SUITES))
    expect(["app/Terento/Info.plist"], baseline | {"app"})
    expect(
        ["app/TerentoCore/Sources/TerentoPoC/Installation/MapLifecycle.swift"],
        baseline | {"app", "native"},
    )
    expect(["backend/catalog-api/src/terento_catalog/admin.py"], baseline | {"backend"})
    expect(
        ["backend/catalog-api/src/terento_catalog/catalog.py"],
        baseline | {"backend", "native"},
    )
    expect(["internal/PROJECT_STATE.md"], baseline)
    expect(["scripts/build-guide-pages.py"], baseline | {"site", "release"})
    expect(["scripts/generate-sitemap.py"], baseline | {"site", "release"})
    expect(["scripts/submit-indexnow.py"], baseline | {"site", "release"})
    expect(["scripts/generate-brand-tokens.py"], baseline | {"site", "app"})
    expect(["Tests/site-faq-content-tests.cjs"], baseline | {"site"})
    expect([".github/workflows/swift-ci.yml"], set(MODULE.ALL_SUITES))
    expect(["contracts/map-catalog.schema.json"], set(MODULE.ALL_SUITES))
    expect(["contracts/fixtures/map-event.valid.json"], set(MODULE.ALL_SUITES))
    expect(["contracts/README.md"], baseline | {"backend"})
    expect(["app/TerentoCore/README.md"], baseline)
    expect(["reports/history.md"], baseline)
    expect(["app/TerentoCore/Tests/TerentoPoCTests/Fixtures/issue148-failure-report.md"], baseline | {"app", "native"})
    expect(["README.md"], baseline | {"release", "site"})
    expect(["VERSIONING.md"], baseline | {"release"})
    expect(["site-deploy/README.md"], baseline | {"site"})
    expect(["site-deploy/AI_DISCOVERABILITY.md"], baseline)
    expect(["legal/web/PRIVACY-PAGE-EN.md"], baseline | {"site", "release"})
    expect(["app/TerentoCore/README.md", "app/TerentoCore/Sources/Engine.swift"], baseline | {"app", "native"})
    expect(["app/TerentoCore/Package.swift"], {"app", "native", "shared", "ci"})
    expect(["Packaging/release.sh"], baseline | {"app", "native", "release"})
    expect(["unknown-project-file.toml"], set(MODULE.ALL_SUITES))
    expect(["Packaging/verify-release-label.sh"], baseline | {"app", "release"})
    expect(["Tests/select-test-suites.py"], baseline)
    expect(["Tests/ci-test-selection-tests.py"], baseline)
    expect([".github/workflows/deploy-catalog-api.yml"], baseline | {"backend"})
    expect([".github/workflows/deploy-site.yml"], baseline | {"site"})
    expect([".github/indexnow/site-state.json"], baseline | {"site"})
    non_mac = set(MODULE.NON_MAC_FALLBACK)
    expect([".github/workflows/publish-vps-images.yml"], non_mac)
    expect([".github/workflows/codeql.yml"], non_mac)
    expect([".github/ISSUE_TEMPLATE/bug_report.yml"], non_mac)
    expect(["scripts/ci_http.py"], non_mac)
    expect(["scripts/infra/deploy-vps-image.sh"], non_mac)
    expect(["site-deploy/Dockerfile"], baseline | {"site"})
    expect(["brand/DESIGN_TOKENS.json"], set(MODULE.ALL_SUITES))
    expect(["Tests/test-suites.json"], set(MODULE.ALL_SUITES))
    expect(["backend/catalog-api/src/terento_catalog/admin.py", "Tests/site-faq-content-tests.cjs"], baseline | {"backend", "site"})
    expect([], set(MODULE.ALL_SUITES))
    # Every Markdown document a suite test reads selects that suite.
    root = MODULE_PATH.parent.parent
    readers = {
        "README.md": ("site", "Tests/site-guide-content-tests.cjs"),
        "VERSIONING.md": ("release", "Tests/release-documentation-tests.cjs"),
        "RELEASE_NOTES.md": ("release", "Tests/release-documentation-tests.cjs"),
        "Packaging/NativeDependencies/README.md": ("release", "Tests/release-documentation-tests.cjs"),
        "contracts/README.md": ("backend", "backend/catalog-api/tests/test_shared_contracts.py"),
        "site-deploy/README.md": ("site", "Tests/site-indexnow-tests.py"),
    }
    for document, (suite, reader) in readers.items():
        source = (root / reader).read_text(encoding="utf-8")
        assert Path(document).name in source, f"{reader} no longer reads {document}"
        assert suite in MODULE.select_suites([document]), f"{document} must select {suite}"
    # macOS app/native runners must not read a path whose change skips them.
    inventory = json.loads((root / "Tests/test-suites.json").read_text(encoding="utf-8"))
    for suite in ("app", "native"):
        for runner in inventory[suite]:
            sources = [root / runner]
            sources += [root / ref for ref in re.findall(
                r"(?:Tests|app/TerentoCore/Tests)/[\w./-]+\.(?:py|cjs|js|swift|sh)",
                sources[0].read_text(encoding="utf-8")) if (root / ref).is_file()]
            for source in sources:
                for ref in re.findall(r"(?:\.github|scripts|site-deploy)/[\w./-]+",
                                      source.read_text(encoding="utf-8")):
                    assert suite in MODULE.select_suites([ref]), f"{source} reads {ref}, which skips {suite}"
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

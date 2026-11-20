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
    expect(["contracts/fixtures/web-installer-events.valid-session.json"], baseline | {"backend"})
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
    # PR #753 (backend and Admin only) must not start the macOS app or native jobs.
    pr_753 = [
        "THIRD_PARTY_NOTICES.md",
        "Tests/admin-access-boundary-tests.py",
        "backend/catalog-api/.env.example",
        "backend/catalog-api/README.md",
        "backend/catalog-api/docs/admin-behavior-contract.md",
        "backend/catalog-api/docs/api.md",
        "backend/catalog-api/docs/schema.md",
        "backend/catalog-api/pyproject.toml",
        "backend/catalog-api/src/terento_catalog/admin.py",
        "backend/catalog-api/src/terento_catalog/admin_website_stats.py",
        "backend/catalog-api/src/terento_catalog/app.py",
        "backend/catalog-api/src/terento_catalog/asc_stats.py",
        "backend/catalog-api/src/terento_catalog/config.py",
        "backend/catalog-api/src/terento_catalog/db.py",
        "backend/catalog-api/src/terento_catalog/http_api.py",
        "backend/catalog-api/src/terento_catalog/migrations/095_app_store_analytics.sql",
        "backend/catalog-api/src/terento_catalog/scheduler.py",
        "backend/catalog-api/tests/test_app_store_stats.py",
        "backend/catalog-api/tests/test_app_store_stats_postgres.py",
        "backend/catalog-api/tests/test_website_stats.py",
        "contracts/STATISTICS_CONTRACT.md",
        "scripts/infra/check-admin-boundary.py",
    ]
    expect(pr_753, baseline | {"backend", "release"})
    assert not {"app", "native"} & set(MODULE.select_suites(pr_753))
    expect(["Tests/admin-access-boundary-tests.py"], baseline)
    expect(["scripts/infra/check-admin-boundary.py"], baseline)
    expect(["contracts/STATISTICS_CONTRACT.md"], baseline | {"backend"})
    # App code still starts the app suite; unknown test files and contract
    # data still fail open to every suite.
    expect(["app/Terento/TerentoAppResourceCompatibility.swift"], baseline | {"app"})
    expect(pr_753 + ["app/Terento/TerentoAppResourceCompatibility.swift"], baseline | {"backend", "release", "app"})
    expect(pr_753 + ["app/TerentoCore/Sources/TerentoPoC/Installation/MapLifecycle.swift"],
           baseline | {"backend", "release", "app", "native"})
    expect(["Tests/new-boundary-tests.py"], set(MODULE.ALL_SUITES))
    expect(pr_753 + ["Tests/new-boundary-tests.py"], set(MODULE.ALL_SUITES))
    expect(["contracts/new-contract.schema.json"], set(MODULE.ALL_SUITES))
    expect(["contracts/released-catalog-clients.json"], set(MODULE.ALL_SUITES))
    expect(["contracts/release-hardware-gates.json"], set(MODULE.ALL_SUITES))
    expect(pr_753 + ["contracts/installation-policy.schema.json"], set(MODULE.ALL_SUITES))
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
    inventory = json.loads((root / "Tests/test-suites.json").read_text(encoding="utf-8"))

    def runner_sources(runner: str) -> list[Path]:
        sources = [root / runner]
        sources += [root / ref for ref in re.findall(
            r"(?:Tests|app/TerentoCore/Tests)/[\w./-]+\.(?:py|cjs|js|swift|sh)",
            sources[0].read_text(encoding="utf-8")) if (root / ref).is_file()]
        return sources

    # An explicitly mapped path selects every suite whose runners read it, and
    # at least one of its mapped suites really reads it.
    for mapped, suites in MODULE.PATH_SUITES.items():
        assert (root / mapped).is_file(), f"{mapped} no longer exists"
        readers = {
            suite
            for suite, runners in inventory.items()
            for runner in runners
            for source in runner_sources(runner)
            if source.as_posix() != (root / mapped).as_posix()
            and mapped in source.read_text(encoding="utf-8")
        }
        assert readers, f"no suite runner reads {mapped}"
        assert readers <= set(suites), f"{mapped} is read by {sorted(readers)}, mapped to {sorted(suites)}"

    # No Swift code and no macOS app/native runner reads a contract document,
    # so a contracts/*.md text change never needs those suites. Comments that
    # only name the document do not count.
    contract_documents = sorted(path.name for path in (root / "contracts").glob("*.md") if path.name != "README.md")
    assert "STATISTICS_CONTRACT.md" in contract_documents

    def code_lines(source: Path) -> str:
        comment = ("//", "/*", "*", "#") if source.suffix in {".swift", ".sh"} else ("#",)
        return "\n".join(
            line for line in source.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith(comment)
        )

    mac_sources = sorted((root / "app").rglob("*.swift"))
    mac_sources += [source for suite in ("app", "native") for runner in inventory[suite] for source in runner_sources(runner)]
    for source in mac_sources:
        text = code_lines(source)
        for document in contract_documents:
            assert document not in text, f"{source} reads contracts/{document}; map it to the macOS suites"

    # macOS app/native runners must not read a path whose change skips them.
    for suite in ("app", "native"):
        for runner in inventory[suite]:
            for source in runner_sources(runner):
                assert "web-installer-" not in source.read_text(encoding="utf-8"), f"{source} reads web installer fixtures, which skip {suite}"
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

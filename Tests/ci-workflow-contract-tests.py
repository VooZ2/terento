#!/usr/bin/env python3
"""Static contracts for pinned and complete GitHub Actions workflows."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PINNED_ACTION = re.compile(r"^\s*uses:\s*[^\s@]+@[0-9a-f]{40}\s*$")


def main() -> int:
    workflow_files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert workflow_files, "no GitHub workflows found"
    for workflow in workflow_files:
        source = workflow.read_text(encoding="utf-8")
        assert "permissions:" in source, f"{workflow.name}: permissions must be explicit"
        for line_number, line in enumerate(source.splitlines(), start=1):
            if line.lstrip().startswith("uses:"):
                assert PINNED_ACTION.match(line), (
                    f"{workflow.name}:{line_number}: action must be pinned to a full SHA"
                )

    swift = (WORKFLOWS / "swift-ci.yml").read_text(encoding="utf-8")
    for contract in (
        'cron: "30 6 * * 1"',
        "Select required test suites",
        "Site tests",
        "Backend API tests",
        "macOS app tests",
        "Native safety tests",
        "Release contract tests",
        "Shared and CI contract tests",
        "name: build-and-test",
        "Tests/select-test-suites.py --json --stdin",
        "xcodebuild \\",
        "postgres:16-alpine",
        "docker build --pull=false -f site-deploy/Dockerfile",
        "docker build --pull=false -t terento-catalog-api:ci",
        "Publish weekly or release health report",
        "scripts/send-weekly-health-report.py",
        "TERENTO_OPERATIONS_INGEST_SECRET",
        "SMTP2GO_USERNAME",
        "SMTP2GO_PASSWORD",
        "https://api.terento.app/internal/operations/observations",
    ):
        assert contract in swift, f"swift-ci.yml is missing {contract!r}"

    deploy_api = (WORKFLOWS / "deploy-catalog-api.yml").read_text(encoding="utf-8")
    assert "needs: tests" in deploy_api, "catalog deploy must wait for backend tests"
    assert "Retain API deployment health" in deploy_api
    deploy_site = (WORKFLOWS / "deploy-site.yml").read_text(encoding="utf-8")
    assert "Retain website deployment health" in deploy_site
    print(f"PASS: {len(workflow_files)} workflows use pinned actions and required quality gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

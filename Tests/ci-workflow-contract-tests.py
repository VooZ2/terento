#!/usr/bin/env python3
"""Static contracts for pinned and complete GitHub Actions workflows."""

from __future__ import annotations

import re
import json
import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PINNED_ACTION = re.compile(r"^\s*uses:\s*[^\s@]+@[0-9a-f]{40}\s*$")


def verify_scoped_transport() -> None:
    """Exercise the real request script with a local SSH spy; no network or secrets."""
    script = REPO_ROOT / "scripts/infra/deploy-vps-image.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        spy = root / "ssh"
        spy.write_text("#!/usr/bin/env python3\n" +
            "import json, os, pathlib, sys\n" +
            "args=sys.argv[1:]; key=pathlib.Path(args[args.index('-i')+1])\n" +
            "assert key.stat().st_mode & 0o777 == 0o600\n" +
            "assert 'VPS_SSH_KEY' not in os.environ\n" +
            "pathlib.Path(os.environ['SSH_RECORD']).write_text(json.dumps(args))\n")
        spy.chmod(0o700)
        record = root / "record.json"
        env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ["PATH"],
                   GITHUB_REPOSITORY="VooZ2/terento", GITHUB_REF="refs/heads/beta",
                   GITHUB_SHA="a"*40, VPS_IMAGE_DIGEST="sha256:"+"b"*64,
                   VPS_SSH_KEY="synthetic-test-key", RUNNER_TEMP=temporary,
                   SSH_RECORD=str(record))
        for role, ref in (("api", "refs/heads/beta"), ("site", "refs/heads/beta"),
                          ("site", "refs/tags/v0.1.0")):
            result = subprocess.run(["bash", str(script), role], env=dict(env, GITHUB_REF=ref), capture_output=True)
            assert result.returncode == 0, result.stderr.decode()
            args = json.loads(record.read_text())
            assert args[-2:] == [f"terento-ci-{role}@179.198.204.47", "deploy sha256:"+"b"*64+" "+"a"*40]
            assert "StrictHostKeyChecking=yes" in args and "IdentitiesOnly=yes" in args
            key = Path(args[args.index("-i")+1])
            assert not key.parent.exists(), "temporary credentials must be removed"
            record.unlink()
        rejected = [(["root"], {}), (["site", "extra"], {}),
                    (["api"], {"GITHUB_REF": "refs/tags/v0.1.0"}),
                    (["site"], {"GITHUB_REF": "refs/heads/unreviewed"}),
                    (["site"], {"GITHUB_REPOSITORY": "someone/terento"}),
                    (["api"], {"VPS_IMAGE_DIGEST": "sha256:"+"b"*64+"; id"}),
                    (["api"], {"GITHUB_SHA": "a"*40+" x"})]
        for args, changes in rejected:
            result = subprocess.run(["bash", str(script), *args], env=dict(env, **changes), capture_output=True)
            assert result.returncode == 64, (args, changes, result.returncode)
            assert not record.exists(), "invalid input reached SSH"
        assert not list(root.glob("rukas-ssh.*"))


def main() -> int:
    workflow_files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert workflow_files, "no GitHub workflows found"
    for workflow in workflow_files:
        source = workflow.read_text(encoding="utf-8")
        assert "permissions:" in source, f"{workflow.name}: permissions must be explicit"
        for line_number, line in enumerate(source.splitlines(), start=1):
            if line.lstrip().startswith("uses:"):
                local_call = re.fullmatch(
                    r"\s*uses: (\./\.github/workflows/[a-z0-9-]+\.yml)\s*", line
                )
                if local_call:
                    assert (REPO_ROOT / local_call.group(1)).is_file(), "local workflow is missing"
                assert PINNED_ACTION.match(line) or local_call, (
                    f"{workflow.name}:{line_number}: action must be pinned to a full SHA"
                )

    swift = (WORKFLOWS / "swift-ci.yml").read_text(encoding="utf-8")
    for contract in (
        'cron: "30 6 * * 1"',
        "send_health_report:",
        "github.event_name == 'workflow_dispatch' && inputs.send_health_report",
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
        "docker build --pull=false -f site-deploy/Dockerfile",
        "Publish weekly or release health report",
        "scripts/send-weekly-health-report.py",
        "TERENTO_OPERATIONS_INGEST_SECRET",
        "SMTP2GO_USERNAME",
        "SMTP2GO_PASSWORD",
        "https://api.terento.app/internal/operations/observations",
        "https://api.terento.app/internal/operations/report-context",
        "catalog_freizeitkarte_new_release",
        "catalog_opentopomap_new_release",
    ):
        assert contract in swift, f"swift-ci.yml is missing {contract!r}"

    reusable = (WORKFLOWS / "reusable-catalog-api-quality.yml").read_text(encoding="utf-8")
    for contract in (
        "workflow_call:", "postgres:16-alpine", 'python-version: "3.12"',
        'node-version: "22"', 'backend/catalog-api[test]',
        "Tests/run-backend-tests.sh", "Database(settings.database_url).health()",
        "docker build --pull=false -t terento-catalog-api:ci",
    ):
        assert contract in reusable, f"reusable API quality gate is missing {contract!r}"
    assert reusable.count("          terento-catalog-migrate\n") == 2
    assert "secrets." not in reusable
    assert "ref:" not in reusable, "checkout must use the caller commit"
    assert "uses: ./.github/workflows/reusable-catalog-api-quality.yml" in swift
    assert "      - backend-tests" in swift

    deploy_api = (WORKFLOWS / "deploy-catalog-api.yml").read_text(encoding="utf-8")
    assert "uses: ./.github/workflows/reusable-catalog-api-quality.yml" in deploy_api

    assert "needs: tests" in deploy_api, "catalog deploy must wait for backend tests"
    assert "Retain API deployment health" in deploy_api
    assert "https://api.terento.app/internal/operations/report-context" in deploy_api
    assert "verify-release-client-contract:" in deploy_api
    assert "Packaging/validate-live-map-catalog.sh" in deploy_api
    assert "TERENTO_ADMIN_ACCESS_REQUIRED: 'true'" in deploy_api
    deploy_site = (WORKFLOWS / "deploy-site.yml").read_text(encoding="utf-8")
    assert "Retain website deployment health" in deploy_site
    publisher = (WORKFLOWS / "publish-vps-images.yml").read_text(encoding="utf-8")
    assert "workflow_call:" in publisher
    assert "digest: ${{ steps.image.outputs.digest }}" in publisher
    assert "value: ${{ jobs.publish.outputs.digest }}" in publisher
    assert "git merge-base --is-ancestor" in publisher
    assert "VPS_SSH_KEY" not in publisher and "environment:" not in publisher
    assert "secrets." not in publisher.replace("secrets.GITHUB_TOKEN", "TOKEN")
    for gate in ("Tests/run-site-tests.sh", "Tests/run-release-documentation-tests.sh",
                 "Tests/run-release-legal-content-tests.sh"):
        assert gate in publisher
    for role, source in (("api", deploy_api), ("site", deploy_site)):
        assert "needs: publish" in source
        assert f"environment: rukas-{role}" in source
        assert f"bash scripts/infra/deploy-vps-image.sh {role}" in source
        assert "${{ needs.publish.outputs.digest }}" in source
        assert "github.ref == 'refs/heads/beta'" in source
        assert "github.event_name == 'workflow_dispatch' ||" not in source
        assert "TERENTO_SITE_SSH" not in source
        assert "scp " not in source and "bash -s" not in source
        assert "Synchronize operations ingest secret" not in source
    rejection = (WORKFLOWS / "check-vps-access.yml").read_text(encoding="utf-8")
    assert "expect 64 id" in rejection
    assert "expect 0 " not in rejection and "expect 1 " not in rejection
    assert "f7e394d" not in rejection
    verify_scoped_transport()
    compatibility_refresh = (WORKFLOWS / "refresh-compatibility-snapshot.yml").read_text(encoding="utf-8")
    for contract in (
        'cron: "30 3 * * *"',
        "workflow_dispatch:",
        "contents: write",
        "ref: beta",
        "scripts/update-compatibility-snapshot.py",
        "scripts/build-compatibility-pages.py",
        "Tests/run-test-suite.py site",
        "git diff --name-only",
        "git push origin HEAD:beta",
        "site/compatibility/public-models.snapshot.json",
        "site/de/compatibility/index.html",
        "site/fr/compatibility/index.html",
        "site/pl/compatibility/index.html",
        "site/cs/compatibility/index.html",
        "site/it/compatibility/index.html",
    ):
        assert contract in compatibility_refresh, (
            "refresh-compatibility-snapshot.yml is missing "
            f"{contract!r}"
        )
    codeql = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")
    assert "name: CodeQL (python)" in codeql
    assert "languages: python" in codeql
    assert "build-mode: none" in codeql
    assert "language: swift" not in codeql
    print(f"PASS: {len(workflow_files)} workflows use pinned actions and required quality gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def verify_refresh_flow():
    import importlib.util
    from unittest.mock import patch
    spec = importlib.util.spec_from_file_location("refresh_flow", REPO_ROOT / "scripts/integrate-compatibility-refresh.py")
    flow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flow)
    flow.allowed(flow.FACT_FILES)
    flow.allowed(flow.GENERATED_METADATA_FILES)
    try:
        flow.allowed(["site/index.html"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("unrelated content accepted")
    calls = []
    with patch.dict(os.environ, GITHUB_REPOSITORY=flow.REPO), patch.object(flow, "run", side_effect=lambda *a, **k: calls.append(a) or ""):
        flow.main()
    assert all(c[0] == "git" for c in calls), "no diff must not touch GitHub"

    def exercise_prepare(generated_paths):
        events = []
        final_sha = "f" * 40

        def fake_run(*args, **kwargs):
            events.append(("run", args))
            if args == ("git", "diff", "--name-only", "HEAD"):
                return "\n".join(generated_paths)
            if args == ("git", "rev-parse", "HEAD"):
                return final_sha
            return ""

        with patch.object(flow, "commit_files",
                          side_effect=lambda files, title: events.append(("commit", files, title))), \
             patch.object(flow, "run", side_effect=fake_run):
            assert flow.prepare_refresh_commits() == final_sha
        return events

    changed_events = exercise_prepare(flow.GENERATED_METADATA_FILES)
    changed_labels = [event[2] for event in changed_events if event[0] == "commit"]
    assert changed_labels == [flow.TITLE, flow.SITEMAP_TITLE]
    assert changed_events.index(("commit", flow.FACT_FILES, flow.TITLE)) < changed_events.index(
        ("run", ("python3", "scripts/generate-sitemap.py", "--write")))
    assert ("run", ("python3", "scripts/generate-sitemap.py", "--check")) in changed_events
    assert ("run", ("git", "diff", "--", *flow.GENERATED_METADATA_FILES)) in changed_events

    unchanged_events = exercise_prepare([])
    unchanged_labels = [event[2] for event in unchanged_events if event[0] == "commit"]
    assert unchanged_labels == [flow.TITLE], "unchanged sitemap must not create an empty commit"
    assert not any(event[0] == "run" and event[1][:3] == ("git", "diff", "--")
                   for event in unchanged_events)

    delayed_sha = "c" * 40
    with patch.object(flow, "gh", side_effect=[
        {"number": 310, "headRefOid": "b" * 40},
        {"number": 310, "headRefOid": delayed_sha},
    ]), patch.object(flow.time, "sleep") as sleeper:
        assert flow.wait_for_pr_head(flow.BRANCH, delayed_sha) == {
            "number": 310, "headRefOid": delayed_sha
        }
        sleeper.assert_called_once_with(5)

    staged_calls = []
    with patch.object(flow, "run", side_effect=lambda *a, **k: staged_calls.append(a) or
                      ("\n".join(flow.FACT_FILES) if a == ("git", "diff", "--cached", "--name-only") else "")):
        flow.commit_files(flow.FACT_FILES, flow.TITLE)
    assert staged_calls == [
        ("git", "add", "--", *flow.FACT_FILES),
        ("git", "diff", "--cached", "--name-only"),
        ("git", "diff", "--cached", "--check"),
        ("git", "commit", "-m", flow.TITLE, "-m", flow.MARKER),
    ]

    sha = "a" * 40
    with patch.object(flow, "run", return_value="") as command:
        flow.delete_merged_branch(sha)
        assert command.call_count == 1, "auto-deleted branch must not cause a second delete"
    with patch.object(flow, "run", return_value="b" * 40 + "\trefs/heads/" + flow.BRANCH):
        try:
            flow.delete_merged_branch(sha)
        except RuntimeError:
            pass
        else:
            raise AssertionError("changed branch deleted")
    old = dict(databaseId=1, headSha=sha, event="workflow_dispatch", status="completed", conclusion="success")
    wrong = dict(old, databaseId=2, headSha="b" * 40)
    fresh = dict(old, databaseId=3)
    calls = []
    with patch.object(flow, "runs", side_effect=[[old], [old, wrong, fresh]]), \
         patch.object(flow, "run", side_effect=lambda *a, **k: calls.append(a) or ""), \
         patch.object(flow, "gh", return_value={"headSha": sha, "conclusion": "success", "jobs": [{"name": "build-and-test", "conclusion": "success"}]}):
        assert flow.dispatch_and_wait("swift-ci.yml", flow.BRANCH, sha) == 3
    assert any(c[:4] == ("gh", "workflow", "run", "swift-ci.yml") for c in calls)
    assert any(c[:4] == ("gh", "run", "watch", "3") for c in calls)
    pending_pr = dict(databaseId=4, headSha=sha, event="pull_request", status="completed", conclusion="action_required")
    calls = []
    with patch.object(flow, "runs", return_value=[pending_pr]), \
         patch.object(flow, "run", side_effect=lambda *a, **k: calls.append(a) or ""), \
         patch.object(flow, "gh", return_value={
             "headSha": sha,
             "conclusion": "success",
             "jobs": [{"name": "build-and-test", "conclusion": "success"}],
         }):
        flow.ensure_pull_request_checks(flow.BRANCH, sha)
    assert any(c[:4] == ("gh", "run", "rerun", "4") for c in calls)
    assert any(c[:4] == ("gh", "run", "watch", "4") for c in calls)
    with patch.object(flow, "runs", return_value=[old]), patch.object(flow, "run") as command:
        assert flow.dispatch_and_wait("deploy-site.yml", "beta", sha, reuse=True) == 1
        command.assert_not_called()
    for result in ({"headSha": "b" * 40, "conclusion": "success", "jobs": []},
                   {"headSha": sha, "conclusion": "success", "jobs": [{"name": "build-and-test", "conclusion": "failure"}]}):
        with patch.object(flow, "runs", side_effect=[[], [fresh]]), patch.object(flow, "run"), patch.object(flow, "gh", return_value=result):
            try:
                flow.dispatch_and_wait("swift-ci.yml", flow.BRANCH, sha)
            except RuntimeError:
                pass
            else:
                raise AssertionError("wrong SHA or failed required job accepted")
    source = (REPO_ROOT / "scripts/integrate-compatibility-refresh.py").read_text()
    for guard in ('len(prs) > 1', 'MARKER not in', 'if not prs', 'wait_for_pr_head',
                  'ensure_pull_request_checks', '"event"] == "pull_request"',
                  'FACT_FILES', 'GENERATED_METADATA_FILES', 'SITEMAP_TITLE',
                  '--force-with-lease=refs/heads/{BRANCH}:{old}',
                  '"--required", "--watch"', '"CLEAN"', '"--match-head-commit", sha',
                  'merged["state"] != "MERGED"', 'merged["mergeCommit"]["oid"]', 'reuse=True'):
        assert guard in source, guard
    assert source.index('commit_files(FACT_FILES, TITLE)') < source.index(
        'scripts/generate-sitemap.py", "--write"')
    assert source.index('scripts/generate-sitemap.py", "--check"') < source.index(
        'sha = prepare_refresh_commits()')
    assert source.index('ensure_pull_request_checks(BRANCH, sha)') < source.index(
        '"gh", "pr", "checks"')
    assert source.index('merged["state"] != "MERGED"') < source.index('dispatch_and_wait("deploy-site.yml"')
    assert "HEAD:beta" not in source and "--admin" not in source


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
        for role, ref in (("api", "refs/heads/beta"), ("site", "refs/heads/beta")):
            result = subprocess.run(["bash", str(script), role], env=dict(env, GITHUB_REF=ref), capture_output=True)
            assert result.returncode == 0, result.stderr.decode()
            args = json.loads(record.read_text())
            assert args[-2:] == [f"terento-ci-{role}@179.198.204.47", "deploy sha256:"+"b"*64+" "+"a"*40]
            assert "StrictHostKeyChecking=yes" in args and "IdentitiesOnly=yes" in args
            key = Path(args[args.index("-i")+1])
            assert not key.parent.exists(), "temporary credentials must be removed"
            record.unlink()
        # Exercise the real retry boundary with a local spy; no connection or delay.
        spy.write_text(spy.read_text() +
            "scenario=os.environ.get('SSH_SCENARIO', '')\n" +
            "counter=pathlib.Path(os.environ.get('SSH_COUNTER', '/dev/null'))\n" +
            "attempt=int(counter.read_text())+1 if counter.exists() else 1\n" +
            "counter.write_text(str(attempt))\n" +
            "if scenario=='timeout' or (scenario=='recover' and attempt<3):\n" +
            " print('ssh: connect to host example port 22: Connection timed out',file=sys.stderr); sys.exit(255)\n" +
            "if scenario in {'lost','auth'}:\n" +
            " print('Connection closed by remote host' if scenario=='lost' else 'Permission denied (publickey)',file=sys.stderr); sys.exit(255)\n")
        sleeper = root / "sleep"
        sleeper.write_text("#!/bin/sh\nexit 0\n")
        sleeper.chmod(0o700)
        counter = root / "attempts"
        for scenario, expected_code, attempts in (("recover", 0, 3), ("timeout", 255, 3), ("lost", 255, 1), ("auth", 255, 1)):
            counter.unlink(missing_ok=True)
            result = subprocess.run(["bash", str(script), "site"],
                env=dict(env, SSH_SCENARIO=scenario, SSH_COUNTER=str(counter)), capture_output=True)
            assert result.returncode == expected_code, result.stderr.decode()
            assert int(counter.read_text()) == attempts
            record.unlink(missing_ok=True)
        rejected = [(["root"], {}), (["site", "extra"], {}),
                    (["api"], {"GITHUB_REF": "refs/tags/v0.1.0"}),
                    (["site"], {"GITHUB_REF": "refs/tags/v0.1.0"}),
                    (["site"], {"GITHUB_REF": "refs/heads/unreviewed"}),
                    (["site"], {"GITHUB_REPOSITORY": "someone/terento"}),
                    (["api"], {"VPS_IMAGE_DIGEST": "sha256:"+"b"*64+"; id"}),
                    (["api"], {"GITHUB_SHA": "a"*40+" x"})]
        for args, changes in rejected:
            result = subprocess.run(["bash", str(script), *args], env=dict(env, **changes), capture_output=True)
            assert result.returncode == 64, (args, changes, result.returncode)
            assert not record.exists(), "invalid input reached SSH"
        assert not list(root.glob("rukas-ssh.*"))



def verify_http_transport():
    """Exercise real retry policy with synthetic curl results; no sleeps/network."""
    import importlib.util
    import contextlib
    import io
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location("ci_http", REPO_ROOT / "scripts/ci_http.py")
    http = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(http)

    def exercise(sequence, arguments=("--fail",), expected=0):
        pending = list(sequence)
        calls, delays = [], []
        def run(command, **kwargs):
            calls.append(command)
            code, status, body = pending.pop(0)
            Path(command[command.index("--output") + 1]).write_bytes(body)
            assert "--compressed" in command
            return SimpleNamespace(returncode=code, stdout=status.encode())
        with contextlib.redirect_stderr(io.StringIO()):
            result = http.request("synthetic", list(arguments), run=run, sleep=delays.append)
        assert result[0] == expected, result
        assert not pending, pending
        assert delays == [2, 4][:len(calls)-1]
        return result[1]

    assert exercise([(28, "200", b"partial"), (0, "200", b"complete")]) == b"complete"
    for status in ("502", "503", "504", "525"):
        assert exercise([(0, status, b"edge"), (0, "200", b"ok")]) == b"ok"
    exercise([(28, "000", b"")] * 3, expected=75)
    exercise([(0, "503", b"")] * 3, expected=75)
    exercise([(0, "401", b"unauthorized")], expected=1)
    exercise([(60, "000", b"")], expected=1)
    assert exercise([(0, "401", b"")], ("-w", "%{http_code}")) == b"401"
    # A security mismatch (unexpected 200) reaches the caller immediately.
    assert exercise([(0, "200", b"")], ("-w", "%{http_code}")) == b"200"
    # Malformed JSON is never repaired or retried by transport.
    body = exercise([(0, "200", b"broken JSON")])
    try:
        json.loads(body)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid JSON accepted")
    for body, accepted in ((b'{ "status": "ok" }', True), (b'{"status":"down"}', False)):
        result = subprocess.run(["jq", "-e", '.status == "ok"'], input=body, capture_output=True)
        assert (result.returncode == 0) == accepted
    from unittest.mock import patch
    import sys
    # Only exhausted transport errors may become delivery warnings.
    for transport_code, expected in ((75, 0), (1, 1), (0, 0)):
        with patch.object(sys, 'argv', ['ci_http.py', '--observation', 'report']), \
             patch.object(http, 'request', return_value=(transport_code, b'')), \
             patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), \
             contextlib.redirect_stderr(io.StringIO()):
            assert http.main() == expected



def verify_quality_results():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_results", REPO_ROOT / "scripts/check-ci-results.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = {key: "skipped" for key in module.SUITES.values()}
    results.update(CHANGES_RESULT="success", SHARED_RESULT="success", LIVE_RESULT="skipped")
    module.validate(["shared", "ci"], results)
    for selected, actual, live in [
        (["app", "ci"], results, False),
        (["ci"], dict(results, CHANGES_RESULT="failure"), False),
        (["ci"], dict(results, NATIVE_RESULT="failure"), False),
        (["ci"], results, True),
        (["unknown"], results, False),
    ]:
        try:
            module.validate(selected, actual, live)
        except ValueError:
            pass
        else:
            raise AssertionError("incomplete selected quality gate accepted")
    module.validate(["app", "ci"], dict(results, APP_RESULT="success", LIVE_RESULT="success"), True)

def verify_live_manifest():
    import importlib.util
    spec = importlib.util.spec_from_file_location("live_manifest", REPO_ROOT / "scripts/check-live-release-manifest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = json.loads((REPO_ROOT / "site/updates/macos-arm64.json").read_text())
    module.validate(expected, dict(expected))
    for field in module.FIELDS:
        for actual in ({k:v for k,v in expected.items() if k != field}, dict(expected, **{field: None})):
            try:
                module.validate(expected, actual)
            except ValueError:
                pass
            else:
                raise AssertionError(f"live manifest accepted invalid {field}")
    stale = dict(expected, build=expected['build'] - 1)
    try:
        module.validate(expected, stale)
    except ValueError:
        pass
    else:
        raise AssertionError("old live build accepted")


def verify_release_reporting(swift):
    """Execute the actual selection shell against real temporary git history."""
    import textwrap
    shell = swift.split("      - name: Select suites from changed paths", 1)[1].split("        run: |\n", 1)[1].split("\n  site-tests:", 1)[0]
    shell = textwrap.dedent(shell)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "Tests").mkdir()
        (root / "Tests/select-test-suites.py").write_text((REPO_ROOT / "Tests/select-test-suites.py").read_text())
        manifest = root / "site/updates/macos-arm64.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"build":29}')
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        git("init")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "Test")
        git("add", ".")
        git("commit", "-m", "initial")
        before = git("rev-parse", "HEAD")
        manifest.write_text('{"build":30}')
        git("add", ".")
        git("commit", "-m", "publish next build")
        after = git("rev-parse", "HEAD")
        for event, ref, base, expected in (
            ("push", "refs/heads/beta", before, "true"),
            ("pull_request", "refs/pull/1/merge", before, "false"),
            ("push", "refs/heads/main", before, "false"),
            ("push", "refs/tags/v1.0.0", before, "false"),
            ("workflow_dispatch", "refs/heads/beta", "", "false"),
            ("push", "refs/heads/beta", after, "false"),
        ):
            output = root / "output"
            output.write_text("")
            subprocess.run(["bash", "-c", shell], cwd=root, check=True, capture_output=True,
                env={**os.environ, "EVENT_NAME":event, "GITHUB_REF":ref, "BASE_SHA":base,
                     "GITHUB_SHA":after, "GITHUB_OUTPUT":str(output)})
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            assert values["release_manifest_changed"] == expected, (event, ref, values)
            if expected == "true":
                assert set(json.loads(values["suites"])) == {"site", "app", "native", "backend", "release", "shared", "ci"}
    report = swift.split("  publish-operational-report:", 1)[1]
    assert "needs.changes.outputs.release_manifest_changed == 'true'" in report
    assert report.index("Reject superseded release metadata") < report.index("Build consolidated health report")
    assert 'scripts/check-live-release-manifest.py "$RUNNER_TEMP/current-release-manifest.json" site/updates/macos-arm64.json' in report
    assert "if: always() && steps.report.outcome == 'success'" in report
    assert 'if [ "$GATE_RESULT" = "success" ]; then' in report

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
        "send_health_report:",
        "run_release_gate:",
        "github.event_name == 'workflow_dispatch' && inputs.send_health_report",
        "inputs.send_health_report || inputs.run_release_gate",
        "name: build-and-test",
        "Tests/select-test-suites.py --json --stdin",
        "xcodebuild \\",
        "docker build --pull=false -f site-deploy/Dockerfile",
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
    assert "confirm_production_deploy:" in deploy_api
    assert "default: false" in deploy_api
    assert "github.event_name == 'workflow_dispatch'" in deploy_api
    assert "inputs.confirm_production_deploy == true" in deploy_api
    assert "vars.TERENTO_FIXED_OPS_INSTALLED == 'true'" in deploy_api
    assert "  migrate:" not in deploy_api
    assert "bash scripts/infra/migrate-vps-image.sh" not in deploy_api
    assert "needs.publish.outputs.migration_063_sha256" not in deploy_api
    assert "needs.publish.outputs.migrate_py_sha256" not in deploy_api
    assert "bash scripts/infra/deploy-vps-image.sh api" in deploy_api
    assert "needs: publish" in deploy_api

    cache_pattern = re.search(r"grep -Eiq '([^']+)' \"\$policy_headers_file\"", deploy_api).group(1)
    for header, expected in [
        ("cache-control: no-store\r\n", True),
        ("Cache-Control: private, no-store\n", True),
        ("cache-control: no-store, private\r\n", True),
        ("cache-control: public\r\n", False),
        ("cache-control: no-store-invalid\r\n", False),
    ]:
        result = subprocess.run(["grep", "-Ei", cache_pattern], input=header,
                                text=True, capture_output=True)
        assert (result.returncode == 0) == expected, repr(header)

    assert "needs: tests" in deploy_api, "catalog deploy must wait for backend tests"
    assert "Retain API deployment health" in deploy_api
    assert "https://api.terento.app/internal/operations/report-context" in deploy_api
    assert "retry_curl()" in deploy_api
    assert "map-catalog" in deploy_api
    assert "python3 scripts/ci_http.py" in deploy_api
    assert "map-catalog --fail --silent --show-error --compressed" in deploy_api
    assert "--max-time 60" in deploy_api
    assert "--retry 1" not in deploy_api
    assert "verify-release-client-contract:" in deploy_api
    assert "Packaging/validate-released-map-catalog.sh" in deploy_api
    assert "TERENTO_ADMIN_ACCESS_REQUIRED: 'true'" in deploy_api
    deploy_site = (WORKFLOWS / "deploy-site.yml").read_text(encoding="utf-8")
    assert "Retain website deployment health" in deploy_site
    assert "--observation deployment-observation" in deploy_site
    assert "--observation deployment-observation" in deploy_api
    publisher = (WORKFLOWS / "publish-vps-images.yml").read_text(encoding="utf-8")
    assert "workflow_call:" in publisher
    assert "digest: ${{ steps.image.outputs.digest }}" in publisher
    assert "value: ${{ jobs.publish.outputs.digest }}" in publisher
    assert "refs/tags/" not in publisher
    assert "pull_succeeded=false" in publisher
    assert "GHCR pull attempt" in publisher
    assert 'sleep $((attempt * 2))' in publisher
    assert "VPS_SSH_KEY" not in publisher and "environment:" not in publisher
    assert "secrets." not in publisher.replace("secrets.GITHUB_TOKEN", "TOKEN")
    assert "io.terento.migration.063.sha256" not in publisher
    assert "io.terento.migrate.py.sha256" not in publisher
    assert "migration_063_sha256" not in publisher
    assert "migrate_py_sha256" not in publisher
    assert "value: ${{ jobs.publish.outputs.build_timestamp }}" in publisher
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

    assert not (WORKFLOWS / "build-catalog-migration-candidate.yml").exists()
    assert not (REPO_ROOT / "scripts/infra/migrate-vps-image.sh").exists()
    assert "candidate_source_ref" not in publisher
    assert "candidate_source_sha" not in publisher
    publisher_validation = publisher.index("name: Validate release source and target")
    publisher_build = publisher.index("name: Build and publish immutable release")
    assert publisher_validation < publisher_build
    assert publisher.index('git status --porcelain=v1 --untracked-files=all', publisher_validation) < publisher.index('docker build --platform linux/amd64', publisher_build)
    assert publisher.index('git show --check --oneline "$GITHUB_SHA"', publisher_validation) < publisher.index('docker push "$image:$image_tag"', publisher_build)
    assert publisher.count('image_tag="sha-$GITHUB_SHA"') == 1
    assert "CANDIDATE_SOURCE_" not in publisher
    assert "candidate-" not in publisher
    assert 'local_image_id="$(docker image inspect --format \'{{.Id}}\' "$image:$image_tag")"' in publisher
    assert '[[ "$pulled_image_id" == "$local_image_id" ]]' in publisher
    assert 'docker push "$image:latest"' not in publisher
    assert 'docker push "$image:current"' not in publisher
    assert 'docker push "$image:production"' not in publisher
    assert '[[ "$(git rev-parse HEAD)" == "$GITHUB_SHA" ]]' in publisher
    rejection = (WORKFLOWS / "check-vps-access.yml").read_text(encoding="utf-8")
    assert "expect 64 id" in rejection
    assert "expect 0 " not in rejection and "expect 1 " not in rejection
    assert "f7e394d" not in rejection
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in swift
    assert "tags:" not in deploy_site, "a tag must not duplicate the beta site deployment"
    assert "scripts/check-live-release-manifest.py" in deploy_site
    for contract in (
        "scripts/generate-sitemap.py", "scripts/submit-indexnow.py",
        "scripts/verify-live-site.py", "TERENTO_INDEXNOW_KEY",
        "indexnow_manual_url", "--manual-url \"$INDEXNOW_MANUAL_URL\"",
        "Prepare IndexNow delta plan", "Verify live sitemap and changed pages before notification",
        "Persist IndexNow publication state", ".github/indexnow/site-state.json",
        "Prepare IndexNow report when notification was not run", "Report IndexNow submission result",
        "INDEXNOW", "component:\"indexnow\"", "indexnow-observation",
        "continue-on-error: true", "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ):
        assert contract in deploy_site, f"deploy-site.yml is missing {contract!r}"
    assert "keyLocation" not in deploy_site, "the IndexNow key location must not be printed by the workflow"
    assert "actions: write" in deploy_site
    assert "pull-requests: write" in deploy_site
    assert 'state_branch="terento/indexnow-state"' in deploy_site
    assert 'gh pr list --repo "$GITHUB_REPOSITORY" --base beta' in deploy_site
    assert 'gh workflow run swift-ci.yml --repo "$GITHUB_REPOSITORY" --ref "$state_branch"' in deploy_site
    assert 'select(.name == "build-and-test")' in deploy_site
    assert 'gh pr create --repo "$GITHUB_REPOSITORY" --base beta --head "$state_branch"' in deploy_site
    assert 'gh pr checks "$pr_number" --repo "$GITHUB_REPOSITORY" --required --watch' in deploy_site
    assert '--match-head-commit "$state_sha"' in deploy_site
    assert 'state_branch="terento/indexnow-state-${GITHUB_RUN_ID}' not in deploy_site
    assert "git push origin HEAD:beta" not in deploy_site
    assert "GitHub contents API" not in deploy_site
    assert "site-state.json" not in (WORKFLOWS / "publish-vps-images.yml").read_text(encoding="utf-8")
    assert "internal/infra/vps/deployment/site/compose.json" not in deploy_site
    assert "git diff --quiet" in deploy_site
    assert "steps.current.outputs.deploy == 'true'" in deploy_site
    assert '"!site/**/*.md"' in deploy_site
    assert "actions/upload-artifact@" in swift
    assert "actions/upload-artifact@" in reusable
    assert "schedule:" in swift
    assert "github.event_name == 'schedule' || startsWith(github.ref" not in swift
    verify_release_reporting(swift)
    verify_quality_results()
    verify_live_manifest()
    verify_http_transport()
    verify_scoped_transport()
    refresh = (WORKFLOWS / "refresh-compatibility-snapshot.yml").read_text(encoding="utf-8")
    assert "cron: \"0 */6 * * *\"" in refresh
    assert "workflow_dispatch:" in refresh
    assert "scripts/update-compatibility-snapshot.py" in refresh
    assert "git diff --quiet" in refresh
    assert not re.search(r"git\s+push[^\n]*:beta", refresh)
    assert "actions: write" in refresh
    assert "pull-requests: write" in refresh
    assert "scripts/ci_http.py compatibility-snapshot --fail" in refresh
    assert '--input "$RUNNER_TEMP/compatibility-live.json"' in refresh
    assert "Tests/compatibility-snapshot-growth-tests.cjs" in refresh
    assert "if: steps.diff.outputs.changed == 'true'" in refresh
    assert "scripts/integrate-compatibility-refresh.py" in refresh
    verify_refresh_flow()
    deploy_site = (WORKFLOWS / "deploy-site.yml").read_text(encoding="utf-8")
    assert "compatibility-page" in deploy_site
    assert "live-compatibility.html" in deploy_site
    assert "live Compatibility snapshot does not match deployed beta output" in deploy_site
    codeql = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")
    codeql_refs = re.findall(r"uses:\s*github/codeql-action/[^@\s]+@([0-9a-f]{40})", codeql)
    assert len(codeql_refs) >= 2 and len(set(codeql_refs)) == 1, "CodeQL steps must use the same pinned version"
    assert "name: CodeQL (python)" in codeql
    assert "languages: python" in codeql
    assert "build-mode: none" in codeql
    assert "language: swift" not in codeql
    print(f"PASS: {len(workflow_files)} workflows use pinned actions and required quality gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regression tests for sitemap semantics, IndexNow deltas and key boundaries."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sitemap = load("terento_generate_sitemap", "scripts/generate-sitemap.py")
indexnow = load("terento_submit_indexnow", "scripts/submit-indexnow.py")


ISOLATED_SENDER = r'''
import importlib.util
import json
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("isolated_indexnow", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

behavior = os.environ["TERENTO_TEST_INDEXNOW_BEHAVIOR"]
call_log = Path(os.environ["TERENTO_TEST_INDEXNOW_CALL_LOG"])

def fake_post(_key, urls):
    call_log.write_text(json.dumps(urls), encoding="utf-8")
    if behavior == "failure":
        return 503, "synthetic failure", 3
    if behavior == "unexpected":
        raise AssertionError("IndexNow was called for an already accepted/no-op state")
    return 202, None, 1

module.post_indexnow = fake_post
args = type("Args", (), {
    "mode": "send",
    "current_manifest": Path(sys.argv[2]),
    "state": Path(sys.argv[3]),
    "plan_out": Path(sys.argv[4]),
    "published_commit": "synthetic-commit",
    "key": "a" * 32,
})()
raise SystemExit(module.run(args))
'''


def test_sitemap_contract() -> None:
    manifest = sitemap.build_manifest(ROOT / ".github/indexnow/site-state.json")
    rendered = sitemap.render_sitemap(manifest)
    assert rendered == (ROOT / "site/sitemap.xml").read_text(encoding="utf-8")
    indexable = [page for page in manifest["pages"] if page["indexable"]]
    assert len(indexable) == 30
    assert len({page["lastmod"] for page in indexable}) > 1
    assert all(page.get("lastmod") for page in indexable)
    assert "https://terento.app/legal/" not in rendered
    assert "https://terento.app/privacy/" not in rendered
    assert all("?" not in page["url"] and "#" not in page["url"] for page in indexable)
    assert "Sitemap: https://terento.app/sitemap.xml" in (ROOT / "site/robots.txt").read_text()

    source = (ROOT / "site/index.html").read_text(encoding="utf-8")
    fingerprint, _ = sitemap.content_fingerprint(source)
    noisy = "<!-- ignored comment -->" + source.replace('class="site-header"', 'class="different-layout"', 1)
    noisy = noisy.replace("?v=20260912-bbbike-types-v1", "?v=unrelated-cache-version")
    assert sitemap.content_fingerprint(noisy)[0] == fingerprint
    assert sitemap.content_fingerprint(source.replace("Explore available maps.", "Explore all available maps.", 1))[0] != fingerprint
    assert sitemap.content_fingerprint(source.replace("softwareVersion", "softwareVersionChanged", 1))[0] != fingerprint

    compatibility = (ROOT / "site/compatibility/index.html").read_text(encoding="utf-8")
    technical_timestamp = re.sub(r'"generatedAt":"[^"]+"', '"generatedAt":"2099-01-01T00:00:00Z"', compatibility, count=1)
    assert sitemap.content_fingerprint(technical_timestamp)[0] == sitemap.content_fingerprint(compatibility)[0]
    changed_snapshot = compatibility.replace('"successfulInstallations":11', '"successfulInstallations":12', 1)
    assert sitemap.content_fingerprint(changed_snapshot)[0] != sitemap.content_fingerprint(compatibility)[0]


def test_sitemap_reproducibility_from_clean_git_history() -> None:
    with tempfile.TemporaryDirectory(prefix="terento-sitemap-clean-") as temporary:
        checkout = Path(temporary) / "checkout"
        shutil.copytree(ROOT / "site", checkout / "site")
        (checkout / ".github/indexnow").mkdir(parents=True)
        (checkout / ".github/indexnow/site-state.json").write_text(json.dumps(indexnow.empty_state()) + "\n", encoding="utf-8")

        def git(*arguments: str, date: str | None = None) -> None:
            environment = dict(os.environ)
            if date:
                environment["GIT_AUTHOR_DATE"] = f"{date}T12:00:00Z"
                environment["GIT_COMMITTER_DATE"] = f"{date}T12:00:00Z"
            subprocess.run(["git", *arguments], cwd=checkout, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        git("init", "-q")
        git("config", "user.email", "seo-tests@example.invalid")
        git("config", "user.name", "SEO tests")
        git("add", "site", ".github/indexnow/site-state.json")
        git("commit", "-qm", "baseline", date="2026-01-01")

        old_root = sitemap.ROOT
        old_config = sitemap.CONFIG_PATH
        old_sitemap = sitemap.SITEMAP_PATH
        try:
            sitemap.ROOT = checkout
            sitemap.CONFIG_PATH = checkout / "site/metadata.json"
            sitemap.SITEMAP_PATH = checkout / "site/sitemap.xml"
            state_path = checkout / ".github/indexnow/site-state.json"

            def render_and_write() -> dict[str, object]:
                manifest = sitemap.build_manifest(state_path)
                rendered = sitemap.render_sitemap(manifest)
                sitemap.SITEMAP_PATH.write_text(rendered, encoding="utf-8")
                assert sitemap.render_sitemap(sitemap.build_manifest(state_path)) == rendered
                return manifest

            baseline = render_and_write()
            baseline_dates = {page["path"]: page.get("lastmod") for page in baseline["pages"]}
            git("add", "site/sitemap.xml")
            git("commit", "-qm", "generated baseline sitemap", date="2026-01-01")

            home_path = checkout / "site/index.html"
            home_path.write_text(home_path.read_text(encoding="utf-8").replace(
                "Explore available maps.", "Explore all available maps.", 1), encoding="utf-8")
            git("add", "site/index.html")
            git("commit", "-qm", "meaningful home content", date="2026-01-02")
            home_change = render_and_write()
            assert home_change["pages"][0]["lastmod"] == "2026-01-02"
            assert home_change["pages"][1]["lastmod"] == baseline_dates["/de/"]
            git("add", "site/sitemap.xml")
            git("commit", "-qm", "generated changed sitemap", date="2026-01-02")

            home_path.write_text(home_path.read_text(encoding="utf-8").replace(
                "<body>", '<body class="formatting-only">', 1), encoding="utf-8")
            git("add", "site/index.html")
            git("commit", "-qm", "layout-only change", date="2026-01-03")
            formatting_change = render_and_write()
            assert formatting_change["pages"][0]["lastmod"] == "2026-01-02"

            compatibility_path = checkout / "site/compatibility/index.html"
            compatibility_path.write_text(re.sub(
                r'"generatedAt":"[^"]+"', '"generatedAt":"2099-01-01T00:00:00Z"',
                compatibility_path.read_text(encoding="utf-8"), count=1), encoding="utf-8")
            git("add", "site/compatibility/index.html")
            git("commit", "-qm", "technical timestamp only", date="2026-01-04")
            timestamp_change = render_and_write()
            compatibility_dates = {page["path"]: page.get("lastmod") for page in timestamp_change["pages"]}
            assert compatibility_dates["/compatibility/"] == baseline_dates["/compatibility/"]

            compatibility_path.write_text(compatibility_path.read_text(encoding="utf-8").replace(
                '"successfulInstallations":11', '"successfulInstallations":12', 1), encoding="utf-8")
            git("add", "site/compatibility/index.html")
            git("commit", "-qm", "meaningful snapshot change", date="2026-01-05")
            snapshot_change = render_and_write()
            assert snapshot_change["pages"][[page["path"] for page in snapshot_change["pages"]].index("/compatibility/")]["lastmod"] == "2026-01-05"
            assert snapshot_change["pages"][0]["lastmod"] == "2026-01-02"
            stable = sitemap.SITEMAP_PATH.read_bytes()
            assert sitemap.render_sitemap(sitemap.build_manifest(state_path)).encode("utf-8") == stable
        finally:
            sitemap.ROOT = old_root
            sitemap.CONFIG_PATH = old_config
            sitemap.SITEMAP_PATH = old_sitemap


def page(path: str, *, fingerprint: str, indexable: bool = True) -> dict[str, object]:
    return {
        "path": path,
        "url": f"https://terento.app{path}",
        "file": f"site{path}index.html",
        "locale": "en",
        "indexable": indexable,
        "fingerprint": fingerprint,
        "lastmod": "2026-09-20",
    }


def test_delta_selection_and_bootstrap() -> None:
    old = {
        "/": page("/", fingerprint="home-old"),
        "/about/": page("/about/", fingerprint="about-old"),
        "/gone/": page("/gone/", fingerprint="gone-old"),
        "/hidden/": page("/hidden/", fingerprint="hidden-old", indexable=True),
    }
    current = {
        "/": page("/", fingerprint="home-new"),
        "/about/": page("/about/", fingerprint="about-old"),
        "/new/": page("/new/", fingerprint="new"),
        "/hidden/": page("/hidden/", fingerprint="hidden-new", indexable=False),
    }
    state = {
        "schemaVersion": 1,
        "status": "published",
        "published": {"pages": list(old.values())},
        "indexNow": {"accepted": [], "pending": []},
    }
    plan = indexnow.build_plan(current, state, False)
    by_path = {entry["path"]: entry for entry in plan["entries"]}
    assert by_path["/"]["kind"] == "changed"
    assert by_path["/new/"]["kind"] == "new"
    assert by_path["/hidden/"]["kind"] == "changed"
    assert by_path["/gone/"]["kind"] == "removed"
    assert indexnow.build_plan(current, indexnow.empty_state(), True)["entries"] == []


def test_publication_state_survives_independent_runs() -> None:
    with tempfile.TemporaryDirectory(prefix="terento-indexnow-state-") as temporary:
        root = Path(temporary)
        source_manifest = sitemap.build_manifest(ROOT / ".github/indexnow/site-state.json")
        current_one = json.loads(json.dumps(source_manifest))
        current_one["pages"][0]["fingerprint"] = "synthetic-home-v1"
        current_one["pages"][1]["fingerprint"] = "synthetic-about-v1"
        current_one_path = root / "manifest-one.json"
        current_one_path.write_text(json.dumps(current_one), encoding="utf-8")

        old_pages = json.loads(json.dumps(current_one["pages"]))
        old_pages[0]["fingerprint"] = "synthetic-home-old"
        state_path = root / "state.json"
        state_path.write_text(json.dumps({
            "schemaVersion": 1,
            "status": "published",
            "published": {"commit": "old", "pages": old_pages},
            "indexNow": {"accepted": [], "pending": []},
        }), encoding="utf-8")

        def isolated(manifest_path: Path, behavior: str, expected_exit: int) -> dict[str, object]:
            call_log = root / f"calls-{behavior}-{len(list(root.glob('calls-*')))}.json"
            plan_path = root / f"plan-{behavior}-{len(list(root.glob('plan-*')))}.json"
            environment = dict(os.environ,
                PYTHONDONTWRITEBYTECODE="1",
                TERENTO_TEST_INDEXNOW_BEHAVIOR=behavior,
                TERENTO_TEST_INDEXNOW_CALL_LOG=str(call_log),
            )
            result = subprocess.run(
                [sys.executable, "-c", ISOLATED_SENDER, str(ROOT / "scripts/submit-indexnow.py"),
                 str(manifest_path), str(state_path), str(plan_path)],
                env=environment,
                capture_output=True,
                text=True,
            )
            assert result.returncode == expected_exit, result.stderr
            return json.loads(state_path.read_text(encoding="utf-8"))

        failed = isolated(current_one_path, "failure", 1)
        pending_after_failure = failed["indexNow"]["pending"]
        assert {entry["url"] for entry in pending_after_failure} == {current_one["pages"][0]["url"]}

        current_two = json.loads(json.dumps(current_one))
        current_two["pages"][1]["fingerprint"] = "synthetic-about-v2"
        current_two_path = root / "manifest-two.json"
        current_two_path.write_text(json.dumps(current_two), encoding="utf-8")
        failed_again = isolated(current_two_path, "failure", 1)
        assert {entry["url"] for entry in failed_again["indexNow"]["pending"]} == {
            current_two["pages"][0]["url"], current_two["pages"][1]["url"]
        }

        accepted = isolated(current_two_path, "accepted", 0)
        assert accepted["indexNow"]["pending"] == []
        assert {record["url"] for record in accepted["indexNow"]["accepted"]} == {
            current_two["pages"][0]["url"], current_two["pages"][1]["url"]
        }
        accepted_count = len(accepted["indexNow"]["accepted"])

        no_op = isolated(current_two_path, "unexpected", 0)
        assert len(no_op["indexNow"]["accepted"]) == accepted_count

        lost_state = root / "lost-state.json"
        lost_call_log = root / "lost-call.json"
        lost_plan = root / "lost-plan.json"
        environment = dict(os.environ,
            PYTHONDONTWRITEBYTECODE="1",
            TERENTO_TEST_INDEXNOW_BEHAVIOR="unexpected",
            TERENTO_TEST_INDEXNOW_CALL_LOG=str(lost_call_log),
        )
        result = subprocess.run(
            [sys.executable, "-c", ISOLATED_SENDER, str(ROOT / "scripts/submit-indexnow.py"),
             str(current_two_path), str(lost_state), str(lost_plan)],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert not lost_call_log.exists(), "bootstrap must not submit the whole sitemap"
        recovered = json.loads(lost_state.read_text(encoding="utf-8"))
        assert recovered["lastRun"]["bootstrap"] is True
        assert recovered["indexNow"]["pending"] == []


def fake_response(status: int):
    class Response:
        def __enter__(self):
            self.status = status
            self.headers = Message()
            return self

        def __exit__(self, *args):
            return False

        def read(self, _size=-1):
            return b""

    return Response()


def test_indexnow_http_status_policy() -> None:
    calls = []

    def accepted(request, timeout=None):
        calls.append(json.loads(request.data))
        return fake_response(202)

    original = indexnow.urlopen
    indexnow.urlopen = accepted
    try:
        status, error, attempts = indexnow.post_indexnow("a" * 32, ["https://terento.app/"])
    finally:
        indexnow.urlopen = original
    assert (status, error, attempts) == (202, None, 1)
    assert calls[0]["host"] == "terento.app"
    assert calls[0]["urlList"] == ["https://terento.app/"]
    assert calls[0]["key"] == "a" * 32
    assert calls[0]["keyLocation"].endswith(".txt")

    retry_calls = []

    def retry_then_accept(request, timeout=None):
        retry_calls.append(request)
        if len(retry_calls) == 1:
            headers = Message()
            headers["Retry-After"] = "0"
            raise HTTPError(request.full_url, 429, "retry", headers, None)
        return fake_response(200)

    indexnow.urlopen = retry_then_accept
    try:
        status, error, attempts = indexnow.post_indexnow("b" * 32, ["https://terento.app/about/"] , sleep=lambda _delay: None)
    finally:
        indexnow.urlopen = original
    assert (status, error, attempts) == (200, None, 2)

    def unavailable(request, timeout=None):
        headers = Message()
        raise HTTPError(request.full_url, 503, "unavailable", headers, None)

    indexnow.urlopen = unavailable
    try:
        status, error, attempts = indexnow.post_indexnow(
            "d" * 32, ["https://terento.app/compatibility/"], sleep=lambda _delay: None
        )
    finally:
        indexnow.urlopen = original
    assert status == 503 and attempts == 3

    def timeout(request, timeout=None):
        raise URLError("synthetic timeout")

    indexnow.urlopen = timeout
    try:
        status, error, attempts = indexnow.post_indexnow(
            "e" * 32, ["https://terento.app/guides/install-garmin-maps-mac/"], sleep=lambda _delay: None
        )
    finally:
        indexnow.urlopen = original
    assert status is None and attempts == 3

    permanent_calls = []

    def permanent(request, timeout=None):
        permanent_calls.append(request)
        headers = Message()
        raise HTTPError(request.full_url, 403, "forbidden", headers, None)

    indexnow.urlopen = permanent
    try:
        status, error, attempts = indexnow.post_indexnow("c" * 32, ["https://terento.app/download/"] , sleep=lambda _delay: None)
    finally:
        indexnow.urlopen = original
    assert status == 403 and attempts == 1 and len(permanent_calls) == 1


def test_submission_history_distinguishes_real_attempts_from_no_changes() -> None:
    current = {"/": page("/", fingerprint="current")}
    base = {
        "schemaVersion": 1,
        "status": "published",
        "published": {"commit": "old", "pages": [page("/", fingerprint="old")]},
        "indexNow": {"accepted": [], "pending": [], "lastSubmissionAt": None, "lastSuccessfulSubmissionAt": None},
    }
    plan = {"entries": [{"url": "https://terento.app/"}]}
    validation_pending = indexnow.state_after_publication(
        current, base, False, plan, [], [], published_commit="new", run_status="accepted",
        submission_at="2026-09-21T10:00:00Z",
        submission_result="validation_pending",
    )
    assert validation_pending["indexNow"]["lastSubmissionAt"] == "2026-09-21T10:00:00Z"
    assert validation_pending["indexNow"]["lastSuccessfulSubmissionAt"] is None
    carried_warning = indexnow.build_report(
        validation_pending, {"entries": []}, result="no_changes", publication_id="deployment-site-1-1"
    )
    assert carried_warning["status"] == "WARNING"
    assert carried_warning["details"]["result"] == "no_changes"
    no_changes = indexnow.state_after_publication(
        current, validation_pending, False, {"entries": []}, [], [], published_commit="new", run_status="no-eligible-notifications",
    )
    assert no_changes["indexNow"]["lastSubmissionAt"] == "2026-09-21T10:00:00Z"
    assert no_changes["indexNow"]["lastSuccessfulSubmissionAt"] is None
    submitted = indexnow.state_after_publication(
        current, no_changes, False, plan, [], [], published_commit="new", run_status="accepted",
        submission_at="2026-09-21T11:00:00Z", successful_submission_at="2026-09-21T11:00:00Z",
    )
    assert submitted["indexNow"]["lastSubmissionAt"] == "2026-09-21T11:00:00Z"
    assert submitted["indexNow"]["lastSuccessfulSubmissionAt"] == "2026-09-21T11:00:00Z"


def test_secret_and_runtime_boundaries() -> None:
    dockerfile = (ROOT / "site-deploy/Dockerfile").read_text(encoding="utf-8")
    caddy = (ROOT / "site-deploy/Caddyfile").read_text(encoding="utf-8")
    deployment_readme = (ROOT / "site-deploy/README.md").read_text(encoding="utf-8")
    assert "INDEXNOW_KEY" not in dockerfile
    assert "/etc/terento/deployment/site/indexnow-key.txt" in deployment_readme
    assert "mode `0444`" in deployment_readme
    assert "read-only" in deployment_readme
    # The operator Compose template is intentionally outside the public repo.
    # When present in a local deployment checkout, validate its exact mount too.
    compose_path = ROOT / "internal/infra/vps/deployment/site/compose.json"
    if compose_path.is_file():
        compose = json.loads(compose_path.read_text(encoding="utf-8"))
        mounts = compose["services"]["site"]["volumes"]
        assert any(
            mount["source"] == "/etc/terento/deployment/site/indexnow-key.txt"
            and "${INDEXNOW_KEY:?" in mount["target"]
            and mount["read_only"] is True
            for mount in mounts
        )
    assert "path_regexp indexNowKey" in caddy
    assert not list((ROOT / "site").glob("????????????????????????????????.txt"))


if __name__ == "__main__":
    test_sitemap_contract()
    test_sitemap_reproducibility_from_clean_git_history()
    test_delta_selection_and_bootstrap()
    test_publication_state_survives_independent_runs()
    test_indexnow_http_status_policy()
    test_submission_history_distinguishes_real_attempts_from_no_changes()
    test_secret_and_runtime_boundaries()
    print("IndexNow, sitemap, live-key boundary and semantic-change tests passed.")

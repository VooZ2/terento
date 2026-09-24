#!/usr/bin/env python3
"""Workflow-owned snapshot PR. Never push beta or bypass required checks."""
import json
import os
import subprocess
import time

REPO = "VooZ2/terento"
BRANCH = "terento/compatibility-snapshot-refresh"
MARKER = "<!-- terento-compatibility-snapshot-refresh -->"
TITLE = "chore: refresh compatibility snapshot"
FILES = ["site/compatibility/public-models.snapshot.json", "site/compatibility/index.html"] + [
    f"site/{locale}/compatibility/index.html" for locale in ("de", "fr", "pl", "cs", "it")
]


def run(*args, timeout=120):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def gh(*args):
    return json.loads(run("gh", *args))


def allowed(paths):
    if not set(paths).issubset(FILES):
        raise RuntimeError("Unexpected files in automation branch or worktree")


def runs(workflow, branch):
    return gh("run", "list", "--repo", REPO, "--workflow", workflow,
              "--branch", branch, "--limit", "100", "--json",
              "databaseId,headSha,event,status,conclusion")


def exact_runs(values, sha):
    return [r for r in values if r["headSha"] == sha]


def dispatch_and_wait(workflow, branch, sha, reuse=False):
    before = runs(workflow, branch)
    matching = exact_runs(before, sha)
    if reuse and not matching:
        # Allow an ordinary push-triggered run to become visible before dispatch.
        for _ in range(6):
            time.sleep(5)
            before = runs(workflow, branch)
            matching = exact_runs(before, sha)
            if matching:
                break
    if reuse and matching:
        successful = [r for r in matching if r["conclusion"] == "success"]
        active = [r for r in matching if r["status"] != "completed"]
        if successful:
            return successful[0]["databaseId"]
        if not active:
            raise RuntimeError("Existing exact-SHA deploy failed; inspect it, do not duplicate")
        selected = active[0]
    else:
        old_ids = {r["databaseId"] for r in before}
        run("gh", "workflow", "run", workflow, "--repo", REPO, "--ref", branch)
        selected = None
        for _ in range(60):
            fresh = [r for r in exact_runs(runs(workflow, branch), sha)
                     if r["event"] == "workflow_dispatch" and r["databaseId"] not in old_ids]
            if fresh:
                selected = fresh[0]
                break
            time.sleep(5)
        if selected is None:
            raise RuntimeError("No new workflow_dispatch run for exact head SHA")
    run("gh", "run", "watch", str(selected["databaseId"]), "--repo", REPO,
        "--interval", "30", "--exit-status", timeout=7200)
    result = gh("run", "view", str(selected["databaseId"]), "--repo", REPO,
                "--json", "headSha,conclusion,jobs")
    if result["headSha"] != sha or result["conclusion"] != "success":
        raise RuntimeError("Exact-SHA workflow did not pass")
    if workflow == "swift-ci.yml":
        if not any(j["name"] == "build-and-test" and j["conclusion"] == "success"
                   for j in result["jobs"]):
            raise RuntimeError("build-and-test did not pass for exact refresh SHA")
    return selected["databaseId"]


def main():
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise RuntimeError("Unexpected repository")
    paths = run("git", "diff", "--name-only", "HEAD").splitlines()
    allowed(paths)
    if run("git", "ls-files", "--others", "--exclude-standard"):
        raise RuntimeError("Unexpected untracked content")
    if not paths:
        print("No factual changes: success; no commit, PR or deploy")
        return
    prs = gh("pr", "list", "--repo", REPO, "--head", BRANCH, "--base", "beta",
             "--state", "open", "--json", "number,body,author,headRefOid")
    if len(prs) > 1:
        raise RuntimeError("Duplicate refresh PRs; refusing ambiguous ownership")
    if prs and (MARKER not in prs[0]["body"] or prs[0]["author"]["login"] != "app/github-actions"):
        raise RuntimeError("Existing PR is not workflow-owned")
    remote = run("git", "ls-remote", "origin", f"refs/heads/{BRANCH}")
    old = remote.split()[0] if remote else ""
    if old:
        run("git", "fetch", "origin", f"refs/heads/{BRANCH}")
        if MARKER not in run("git", "show", "-s", "--format=%B", old):
            raise RuntimeError("Existing branch is not workflow-owned")
        if run("git", "show", "-s", "--format=%ae", old) != "41898282+github-actions[bot]@users.noreply.github.com":
            raise RuntimeError("Unexpected automation branch author")
        allowed(run("git", "diff", "--name-only", f"HEAD...{old}").splitlines())
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", "--", *FILES)
    allowed(run("git", "diff", "--cached", "--name-only").splitlines())
    run("git", "diff", "--cached", "--check")
    run("git", "commit", "-m", TITLE, "-m", MARKER)
    sha = run("git", "rev-parse", "HEAD")
    # Explicit lease also protects first creation against a racing human branch.
    run("git", "push", f"--force-with-lease=refs/heads/{BRANCH}:{old}",
        "origin", f"HEAD:refs/heads/{BRANCH}")
    if not prs:
        run("gh", "pr", "create", "--repo", REPO, "--head", BRANCH, "--base", "beta",
            "--title", TITLE, "--body", MARKER + "\nGenerated public compatibility facts only. Required exact-head CI gates merge.")
    pr = gh("pr", "view", BRANCH, "--repo", REPO, "--json", "number,headRefOid")
    number = str(pr["number"])
    if pr["headRefOid"] != sha:
        raise RuntimeError("PR head changed unexpectedly")
    # GITHUB_TOKEN suppresses pull_request events: explicitly test this exact head.
    dispatch_and_wait("swift-ci.yml", BRANCH, sha)
    run("gh", "pr", "checks", number, "--repo", REPO, "--required", "--watch",
        "--fail-fast", timeout=7200)
    pr = gh("pr", "view", number, "--repo", REPO,
            "--json", "headRefOid,mergeStateStatus")
    if pr["headRefOid"] != sha or pr["mergeStateStatus"] != "CLEAN":
        raise RuntimeError("Exact PR head does not satisfy current branch protection")
    run("gh", "pr", "merge", number, "--repo", REPO, "--merge", "--match-head-commit", sha)
    merged = gh("pr", "view", number, "--repo", REPO, "--json", "state,mergeCommit")
    if merged["state"] != "MERGED":
        raise RuntimeError("PR not merged")
    beta = run("git", "ls-remote", "origin", "refs/heads/beta").split()[0]
    if beta != merged["mergeCommit"]["oid"]:
        raise RuntimeError("Beta advanced concurrently; do not deploy unrelated source")
    # Reuse an automatic exact-SHA deployment if present; never double deploy.
    dispatch_and_wait("deploy-site.yml", "beta", beta, reuse=True)
    remaining = gh("pr", "list", "--repo", REPO, "--head", BRANCH,
                   "--base", "beta", "--state", "open", "--json", "number")
    if remaining:
        raise RuntimeError("Unexpected open refresh PR remains")
    run("git", "push", f"--force-with-lease=refs/heads/{BRANCH}:{sha}",
        "origin", f":refs/heads/{BRANCH}")
    print(f"Merged refresh PR {number}; exact beta {beta} deployment passed")


if __name__ == "__main__":
    main()

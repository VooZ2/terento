#!/usr/bin/env python3
"""Fail when a Terento test runner or test source is no longer orchestrated."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = REPO_ROOT / "Tests"
NATIVE_TESTS_ROOT = REPO_ROOT / "app" / "TerentoCore" / "Tests"
AGGREGATE_RUNNERS = {
    "run-all-tests.sh",
    "run-app-tests.sh",
    "run-backend-tests.sh",
    "run-ci-test-inventory-tests.sh",
    "run-native-tests.sh",
    "run-release-tests.sh",
    "run-shared-tests.sh",
    "run-site-tests.sh",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def main() -> int:
    manifest = json.loads((TESTS_ROOT / "test-suites.json").read_text(encoding="utf-8"))
    declared = [runner for runners in manifest.values() for runner in runners]
    counts = Counter(declared)
    errors: list[str] = []

    duplicates = sorted(path for path, count in counts.items() if count != 1)
    if duplicates:
        errors.append("runners declared more than once: " + ", ".join(duplicates))

    root_runners = {
        relative(path)
        for path in TESTS_ROOT.glob("run-*-tests.sh")
        if path.name not in AGGREGATE_RUNNERS
    }
    native_runners = {relative(path) for path in NATIVE_TESTS_ROOT.glob("run-*.sh")}
    discovered = root_runners | native_runners
    declared_set = set(declared)
    missing = sorted(discovered - declared_set)
    stale = sorted(declared_set - discovered)
    if missing:
        errors.append("unassigned test runners: " + ", ".join(missing))
    if stale:
        errors.append("manifest paths without a runner: " + ", ".join(stale))

    for suite, runners in manifest.items():
        expected_prefix = f"run-{suite}-"
        for runner in runners:
            path = REPO_ROOT / runner
            if not path.name.startswith(expected_prefix):
                errors.append(
                    f"{runner} must use the {expected_prefix} prefix for suite {suite}"
                )
            if path.exists() and not os.access(path, os.X_OK):
                errors.append(f"test runner is not executable: {runner}")

    runner_text = {
        runner: (REPO_ROOT / runner).read_text(encoding="utf-8")
        for runner in discovered
    }
    source_tests = [*TESTS_ROOT.glob("*-tests.cjs"), *TESTS_ROOT.glob("*-tests.py")]
    source_tests.remove(TESTS_ROOT / "ci-test-inventory-tests.py")
    swift_tests = list((NATIVE_TESTS_ROOT / "TerentoPoCTests").glob("*Tests.swift"))
    for source in [*source_tests, *swift_tests]:
        references = [runner for runner, text in runner_text.items() if source.name in text]
        if len(references) != 1:
            errors.append(
                f"{relative(source)} must be referenced by exactly one runner; "
                f"found {len(references)}"
            )

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print(
        "PASS: test inventory covers "
        f"{len(discovered)} runners and {len(source_tests) + len(swift_tests)} test sources"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

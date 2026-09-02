#!/usr/bin/env python3
"""Run one declared Terento test suite with deterministic reporting."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "Tests" / "test-suites.json"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: Tests/run-test-suite.py <suite|all>", file=sys.stderr)
        return 2

    suites = json.loads(MANIFEST.read_text(encoding="utf-8"))
    requested = sys.argv[1]
    if requested == "all":
        selected = list(suites)
    elif requested in suites:
        selected = [requested]
    else:
        print(
            f"Unknown test suite {requested!r}; expected one of: "
            + ", ".join([*suites, "all"]),
            file=sys.stderr,
        )
        return 2

    total = sum(len(suites[suite]) for suite in selected)
    completed = 0
    started = time.monotonic()
    environment = os.environ.copy()
    module_cache = Path(tempfile.gettempdir()) / "terento-test-module-cache"
    module_cache.mkdir(parents=True, exist_ok=True)
    environment.setdefault("CLANG_MODULE_CACHE_PATH", str(module_cache))
    environment.setdefault("SWIFT_MODULECACHE_PATH", str(module_cache))
    print(f"Terento test plan: {', '.join(selected)} ({total} runners)", flush=True)

    for suite in selected:
        suite_started = time.monotonic()
        print(f"\n[{suite}] {len(suites[suite])} runners", flush=True)
        for runner_text in suites[suite]:
            runner = REPO_ROOT / runner_text
            print(f"  RUN  {runner_text}", flush=True)
            result = subprocess.run(
                [str(runner)], cwd=REPO_ROOT, env=environment, check=False,
            )
            if result.returncode:
                print(
                    f"  FAIL {runner_text} (exit {result.returncode})",
                    file=sys.stderr,
                    flush=True,
                )
                return result.returncode
            completed += 1
            print(f"  PASS {runner_text}", flush=True)
        print(
            f"[{suite}] PASS in {time.monotonic() - suite_started:.1f}s",
            flush=True,
        )

    print(
        f"\nALL PASS: {completed}/{total} runners in "
        f"{time.monotonic() - started:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

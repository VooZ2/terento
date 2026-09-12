#!/usr/bin/env python3
"""Reject a selected suite that was silently skipped, as well as failures."""
import json
import os

SUITES = {"site": "SITE_RESULT", "app": "APP_RESULT", "native": "NATIVE_RESULT",
          "backend": "BACKEND_RESULT", "release": "RELEASE_RESULT",
          "shared": "SHARED_RESULT", "ci": "SHARED_RESULT"}

def validate(selected, results, live_required=False):
    if not isinstance(selected, list) or not selected or any(s not in SUITES for s in selected):
        raise ValueError("invalid test selection")
    if results.get("CHANGES_RESULT") != "success":
        raise ValueError("suite selection did not succeed")
    for name in set(SUITES.values()) | {"LIVE_RESULT"}:
        if results.get(name) not in {"success", "skipped"}:
            raise ValueError(f"quality gate ended as {results.get(name)}: {name}")
    for suite in selected:
        if results.get(SUITES[suite]) != "success":
            raise ValueError(f"selected suite did not run successfully: {suite}")
    if live_required and results.get("LIVE_RESULT") != "success":
        raise ValueError("required live candidate gate was skipped")

if __name__ == "__main__":
    validate(json.loads(os.environ["SELECTED_SUITES"]), os.environ,
             os.environ.get("LIVE_REQUIRED") == "true")
    print("All selected quality gates ran successfully.")

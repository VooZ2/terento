#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
"$repo_root/Tests/run-ci-test-inventory-tests.sh"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/Tests/run-test-suite.py" app

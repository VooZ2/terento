#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/Tests/ci-workflow-contract-tests.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/Tests/admin-access-boundary-tests.py"

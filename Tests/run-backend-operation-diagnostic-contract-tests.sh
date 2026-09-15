#!/bin/sh
set -eu
repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
. "$repo_root/Tests/backend-python-runtime.sh"
export PYTHONPATH="$repo_root/backend/catalog-api/src:$repo_root/backend/catalog-api/tests${PYTHONPATH:+:$PYTHONPATH}"
PYTHONDONTWRITEBYTECODE=1 "$TERENTO_PYTHON_BIN" -m unittest test_operation_diagnostic_delivery

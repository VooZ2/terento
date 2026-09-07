#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
. "$repo_root/Tests/node-runtime.sh"
. "$repo_root/Tests/backend-python-runtime.sh"

export PYTHONPATH="$repo_root/backend/catalog-api/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHONDONTWRITEBYTECODE=1 "$TERENTO_PYTHON_BIN" -m unittest discover \
  -s "$repo_root/backend/catalog-api/tests" \
  -p 'test_*.py'

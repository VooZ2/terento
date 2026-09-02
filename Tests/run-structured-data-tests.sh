#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
. Tests/node-runtime.sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate-structured-data.py
"$NODE_BIN" Tests/structured-data-tests.cjs

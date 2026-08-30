#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate-structured-data.py
node Tests/structured-data-tests.cjs

#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
. Tests/node-runtime.sh
"$NODE_BIN" Tests/site-seo-contract-tests.cjs
PYTHONDONTWRITEBYTECODE=1 python3 Tests/site-indexnow-tests.py

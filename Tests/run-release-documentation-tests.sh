#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. Tests/node-runtime.sh
"$NODE_BIN" Tests/release-documentation-tests.cjs
python3 Tests/release-source-verification-tests.py

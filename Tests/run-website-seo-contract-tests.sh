#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
. Tests/node-runtime.sh
"$NODE_BIN" Tests/website-seo-contract-tests.cjs

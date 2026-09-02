#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."
. Tests/node-runtime.sh
"$NODE_BIN" Tests/site-faq-content-tests.cjs

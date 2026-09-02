#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
. "$repo_root/Tests/node-runtime.sh"
"$NODE_BIN" "$repo_root/Tests/site-home-copy-cta-tests.cjs"

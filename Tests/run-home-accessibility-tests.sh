#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
. "$repo_root/Tests/node-runtime.sh"
"$NODE_BIN" "$repo_root/Tests/home-accessibility-tests.cjs"

#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
node_bin="${TERENTO_NODE_BIN:-node}"
"$node_bin" "$repo_root/Tests/home-accessibility-tests.cjs"

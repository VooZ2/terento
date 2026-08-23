#!/bin/zsh
set -euo pipefail

if [[ "$#" -gt 1 ]]; then
  echo "Usage: $0 [physical|controlled]" >&2
  exit 2
fi

mode="${1:-physical}"
if [[ "$mode" != "physical" && "$mode" != "controlled" ]]; then
  echo "Usage: $0 [physical|controlled]" >&2
  exit 2
fi

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

export LIBMTP_PREFIX="/opt/homebrew/opt/libmtp"
export CLANG_MODULE_CACHE_PATH="/tmp/terento-native-poc-module-cache"
export SWIFTPM_CONFIG_DIR="/tmp/terento-native-poc-swiftpm"

swift run TerentoInterruptionTest --mode "$mode"

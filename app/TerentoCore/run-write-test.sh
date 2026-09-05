#!/bin/zsh
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 ~/Downloads/terento-write-test.txt" >&2
  exit 2
fi

PROJECT_DIR="${0:A:h}"
SOURCE_PATH="$1"

cd "$PROJECT_DIR"

export LIBMTP_PREFIX="/opt/homebrew/opt/libmtp"
export CLANG_MODULE_CACHE_PATH="/tmp/terento-native-poc-module-cache"
export SWIFTPM_CONFIG_DIR="/tmp/terento-native-poc-swiftpm"

swift run TerentoWriteTest --source "$SOURCE_PATH"

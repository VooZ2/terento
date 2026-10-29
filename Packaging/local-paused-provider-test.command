#!/bin/zsh
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
app="$script_dir/Terento.app"

if [[ ! -x "$app/Contents/MacOS/Terento" ]]; then
    print -u2 "Terento.app is missing beside this launcher. Unzip the complete local test package first."
    exit 1
fi

# The only supported way to install a provider the server still holds PAUSED
# from a local Debug artifact. Release builds ignore this variable.
export TERENTO_DEBUG_UNPAUSE_PROVIDERS="${TERENTO_DEBUG_UNPAUSE_PROVIDERS:-osmapa}"

exec "$app/Contents/MacOS/Terento"

#!/bin/zsh
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
app="$script_dir/Terento.app"

if [[ ! -x "$app/Contents/MacOS/Terento" ]]; then
    print -u2 "Terento.app is missing beside this launcher. Unzip the complete local test package first."
    exit 1
fi

# This launcher is intentionally the only supported way to expose the
# internal contour allowlist in a local Debug artifact. Release builds ignore
# these environment variables and keep contours disabled.
export TERENTO_OPENTOPO_MAP_CONTOUR_MODE=allowlist
export TERENTO_OPENTOPO_MAP_CONTOUR_ALLOWLIST=opentopomap-andorra,opentopomap-ltu

exec "$app/Contents/MacOS/Terento"

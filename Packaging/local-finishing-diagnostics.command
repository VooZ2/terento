#!/bin/zsh
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
app="$script_dir/Terento.app"
[[ -x "$app/Contents/MacOS/Terento" ]] || { print -u2 'Unzip the complete package first.'; exit 1; }
# Unique private local log; inherited by workers so timeout evidence survives.
umask 077
log_dir="$HOME/Library/Logs/Terento"
mkdir -p "$log_dir"
log_file="$(mktemp "$log_dir/finishing-r4-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
print "Finishing diagnostics: $log_file"
print 'Use this window to run the local test. Diagnostics are saved automatically.'
export TERENTO_FINISHING_TRACE=1
export TERENTO_OPENTOPO_MAP_CONTOUR_MODE=allowlist
export TERENTO_OPENTOPO_MAP_CONTOUR_ALLOWLIST=opentopomap-andorra,opentopomap-ltu
# A regular append-only file avoids a pipe consumer blocking native workers.
exec >> "$log_file" 2>&1
print "Finishing diagnostic build r4; started $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec "$app/Contents/MacOS/Terento"

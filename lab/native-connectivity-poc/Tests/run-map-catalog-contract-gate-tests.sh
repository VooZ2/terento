#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h:h:h}"
release_script="$repo_root/Packaging/release.sh"
live_gate="$repo_root/Packaging/validate-live-map-catalog.sh"
swift_ci="$repo_root/.github/workflows/swift-ci.yml"
deploy_workflow="$repo_root/.github/workflows/deploy-catalog-api.yml"
monitor_workflow="$repo_root/.github/workflows/map-catalog-contract.yml"

[[ -x "$live_gate" ]]
if ! grep -Fq 'node_bin="${TERENTO_NODE_BIN:-}"' "$release_script" \
    || ! grep -Fq 'command -v node || command -v nodejs' "$release_script" \
    || ! grep -Fq 'export TERENTO_NODE_BIN="$node_bin"' "$release_script"; then
    print -u2 "FAIL: release script does not resolve and export the shared Node.js runtime"
    exit 1
fi
grep -Fq 'require_command python3' "$release_script"
grep -Fq 'Packaging/validate-live-map-catalog.sh' "$swift_ci"
grep -Fq 'startsWith(github.ref, '\''refs/tags/v'\'')' "$swift_ci"
grep -Fq 'verify-release-client-contract:' "$deploy_workflow"
grep -Fq 'needs: deploy' "$deploy_workflow"
grep -Fq 'Packaging/validate-live-map-catalog.sh' "$deploy_workflow"
grep -Fq 'schedule:' "$monitor_workflow"
grep -Fq 'workflow_dispatch:' "$monitor_workflow"
grep -Fq 'Packaging/validate-live-map-catalog.sh' "$monitor_workflow"

python3 - "$release_script" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
gate = source.index('run_logged "live-map-catalog-contract"')
build = source.index('if ! xcodebuild', gate)
assert gate < build, "live catalog gate must run before the release app build"
PY

print "PASS: release, deploy, and scheduled live-catalog client contract gates"

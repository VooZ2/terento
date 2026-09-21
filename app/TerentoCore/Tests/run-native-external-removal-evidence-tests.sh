#!/bin/zsh
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-external-evidence.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
python3 - "$project_root" "$build_dir" <<'PY'
from pathlib import Path
import sys
root, build = map(Path, sys.argv[1:])
transport = (root / 'Sources/TerentoPoC/Installation/MTPSafeDeleteTransport.swift').read_text()
start = transport.index('private final class ExternalRemovalEvidence:')
end = transport.index('\nstruct MTPSafeDeleteTransport:', start)
cache = transport[start:end]
source = (root / 'Sources/TerentoPoC/Installation/SafeDeleteAdapter.swift').read_text()
start = source.index('struct SafeDeleteTarget:')
end = source.index('\nstruct SafeDeleteDeviceObject:', start)
target = source[start:end]
tests = (root / 'Tests/TerentoPoCTests/ExternalRemovalEvidenceTests.swift').read_text()
(build / 'Evidence.swift').write_text('import Foundation\n' + target + '\n' + cache + '\n' + tests)
PY
swiftc -parse-as-library "$build_dir/Evidence.swift" -o "$build_dir/evidence"
"$build_dir/evidence"

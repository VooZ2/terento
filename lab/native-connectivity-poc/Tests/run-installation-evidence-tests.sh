#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-installation-evidence-tests.XXXXXX")"

swiftc -parse-as-library -module-name TerentoInstallationEvidenceTests \
  "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/InstallationEvidence.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
  "$project_root/Tests/TerentoPoCTests/InstallationEvidenceTests.swift" \
  -o "$build_dir/tests"

"$build_dir/tests"

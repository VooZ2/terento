#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-installation-evidence-tests.XXXXXX")"

swiftc -D TERENTO_TESTING -parse-as-library -module-name TerentoInstallationEvidenceTests \
  "$project_root/Sources/TerentoPoC/Telemetry/TerentoTelemetryMetadata.swift" \
  "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/InstallationEvidence.swift" \
  "$project_root/Sources/TerentoPoC/Installation/InstallationTransportProtocols.swift" \
  "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
  "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
  "$project_root/Sources/TerentoPoC/Diagnostics/InstallationIssueReport.swift" \
  "$project_root/Sources/TerentoPoC/MTPTransport/BoundedNativeProcess.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
  "$project_root/Tests/TerentoPoCTests/InstallationEvidenceDiagnosticLogStub.swift" \
  "$project_root/Tests/TerentoPoCTests/InstallationEvidenceTests.swift" \
  -o "$build_dir/tests"


python3 - "$build_dir/tests" <<'PYTEST'
import subprocess, sys
# A hung retry remains a failing test; never retry a failed assertion.
subprocess.run([sys.argv[1]], check=True, timeout=30)
PYTEST

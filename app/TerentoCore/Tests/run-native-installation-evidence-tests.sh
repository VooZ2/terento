#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-installation-evidence-tests.XXXXXX")"

swiftc -D TERENTO_TESTING -parse-as-library -module-name TerentoInstallationEvidenceTests \
  "$project_root/Sources/TerentoPoC/Telemetry/TerentoTelemetryMetadata.swift" \
  "$project_root/Sources/TerentoPoC/Telemetry/TelemetryDeliveryPolicy.swift" \
  "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/InstallationEvidence.swift" \
  "$project_root/Sources/TerentoPoC/Installation/InstallationTransportProtocols.swift" \
  "$project_root/Sources/TerentoPoC/Installation/MapInventoryScope.swift" \
  "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
  "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
  "$project_root/Sources/TerentoPoC/Diagnostics/InstallationIssueReport.swift" \
  "$project_root/Sources/TerentoPoC/Diagnostics/SupportReport.swift" \
  "$project_root/Sources/TerentoPoC/MTPTransport/BoundedNativeProcess.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
  "$project_root/Tests/TerentoPoCTests/InstallationEvidenceDiagnosticLogStub.swift" \
  "$project_root/Tests/TerentoPoCTests/InstallationEvidenceTests.swift" \
  -o "$build_dir/tests"


python3 - "$build_dir/tests" "$build_dir/update-evidence.json" "$project_root/../../backend/catalog-api/src" <<'PYTEST'
import json, os, pathlib, subprocess, sys
# A hung retry remains a failing test; never retry a failed assertion.
environment = dict(os.environ, TERENTO_UPDATE_EVIDENCE_TEST_PAYLOAD=sys.argv[2])
subprocess.run([sys.argv[1]], check=True, timeout=30, env=environment)
# Verify the real Swift encoder's output with the actual server allowlist.
sys.path.insert(0, sys.argv[3])
from terento_catalog.compatibility_evidence import validate_event
payload = pathlib.Path(sys.argv[2]).read_bytes()
event = validate_event(payload)
assert event["operationKind"] == "update" and event["oldMapPreserved"] is True
assert event["failureCode"] == "UPDATE_FAILED_WRITE"
assert event["operationId"].lower() == "aabbccdd-2222-4222-8222-222222222222"
print("PASS: native update payload accepted by production server validator")
PYTEST

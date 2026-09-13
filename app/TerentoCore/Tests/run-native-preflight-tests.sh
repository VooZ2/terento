#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage401-preflight-tests.XXXXXX")"
binary_path="$build_dir/stage401-preflight-tests"

swiftc \
    -module-name TerentoStage401PreflightTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/MapCapability.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceAssetRegistry.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapConflictResolver.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationPreflight.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage401PreflightTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eq 'LibMTPBridge|MTPTransport|SendObject|DeleteObject|MoveObject' \
    "$project_root/Sources/TerentoPoC/Installation/InstallationPreflight.swift"; then
    print -u2 "FAIL: preflight engine contains a transport or write-operation dependency"
    exit 1
fi

print "PASS: preflight engine has no MTP transport or write-operation dependency"

python3 - "$project_root/Sources/LibMTPBridge/MTPBridge.c" <<'PYTHON'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
# USB manufacturer/product string descriptors are not MTP DeviceInfo. Keep
# snapshot discovery independent of optional text descriptors (OpenMTP lesson).
assert 'LIBMTP_Get_Modelname(device)' in source
assert 'LIBMTP_Get_Manufacturername(device)' in source
assert 'iManufacturer' not in source and 'iProduct' not in source
assert 'libusb_get_string_descriptor' not in source
print('PASS: snapshot uses MTP DeviceInfo without requiring optional USB text descriptors')
PYTHON

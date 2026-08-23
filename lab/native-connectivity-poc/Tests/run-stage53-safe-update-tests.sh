#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage53-safe-update-tests.XXXXXX")"
binary_path="$build_dir/stage53-safe-update-tests"

swiftc \
    -module-name TerentoStage53SafeUpdateTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationTransaction.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ReadBackupAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Installation/TerentoManifestStore.swift" \
    "$project_root/Sources/TerentoPoC/Installation/SafeDeleteAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Installation/SafeUpdateTransaction.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage53SafeUpdateTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'SendObject|MoveObject|RenameObject|DeleteObject' \
    "$project_root/Sources/TerentoPoC/Installation/SafeUpdateTransaction.swift"; then
    print -u2 "FAIL: Stage 5.3 coordinator contains a raw device operation"
    exit 1
fi

print "PASS: Stage 5.3 coordinator has no raw MTP operation names"

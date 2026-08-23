#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage52-safe-delete-tests.XXXXXX")"
binary_path="$build_dir/stage52-safe-delete-tests"

swiftc \
    -module-name TerentoStage52SafeDeleteTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" \
    "$project_root/Sources/TerentoPoC/Installation/TerentoManifestStore.swift" \
    "$project_root/Sources/TerentoPoC/Installation/SafeDeleteAdapter.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage52SafeDeleteTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'SendObject|MoveObject|RenameObject|terento_mtp_' \
    "$project_root/Sources/TerentoPoC/Installation/SafeDeleteAdapter.swift"; then
    print -u2 "FAIL: SafeDeleteAdapter must not call raw MTP or write operations"
    exit 1
fi

if grep -Eiq 'SendObject|MoveObject|RenameObject' \
    "$project_root/Sources/TerentoPoC/Installation/MTPSafeDeleteTransport.swift"; then
    print -u2 "FAIL: MTPSafeDeleteTransport contains a forbidden write operation"
    exit 1
fi

print "PASS: Stage 5.2 delete path has no SendObject, MoveObject, or RenameObject"

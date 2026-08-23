#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage5-map-lifecycle-tests.XXXXXX")"
binary_path="$build_dir/stage5-map-lifecycle-tests"

swiftc \
    -module-name TerentoStage5MapLifecycleTests \
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
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage5MapLifecycleTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'terento_mtp_|SendObject|DeleteObject|MoveObject|Rename' \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift"; then
    print -u2 "FAIL: Stage 5 lifecycle domain must not call raw MTP operations"
    exit 1
fi

print "PASS: Stage 5 lifecycle domain is transport-independent"

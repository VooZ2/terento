#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage45-map-selection-tests.XXXXXX")"
binary_path="$build_dir/stage45-map-selection-tests"

swiftc \
    -module-name TerentoStage45MapSelectionTests \
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
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapConflictResolver.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationPreflight.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPlanner.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPresentation.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage45MapSelectionTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eq 'LibMTPBridge|MTPTransport|SendObject|DeleteObject|MoveObject|Rename' \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPlanner.swift"; then
    print -u2 "FAIL: map selection planner contains transport or write-operation logic"
    exit 1
fi

if grep -Fq 'Text("(plan.selectedItems.count)' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift" \
    || grep -Fq 'Text("(formatBytes(' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"; then
    print -u2 "FAIL: raw Swift expressions are present in map-selection UI text"
    exit 1
fi

if grep -Eq 'Text\("Select|title: "Select' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"; then
    print -u2 "FAIL: Select pill/action remains in map-selection UI"
    exit 1
fi

print "PASS: map selection planner is transport-independent and read-only"

#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage3-generic-lifecycle-tests.XXXXXX")"
binary_path="$build_dir/stage3-generic-lifecycle-tests"

swiftc \
    -module-name TerentoStage3GenericLifecycleTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage3GenericLifecycleTests.swift" \
    -o "$binary_path"

"$binary_path"

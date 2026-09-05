#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage51-read-backup-tests.XXXXXX")"
binary_path="$build_dir/stage51-read-backup-tests"

swiftc \
    -module-name TerentoStage51ReadBackupTests \
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
    "$project_root/Sources/TerentoPoC/Installation/ReadBackupAdapter.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage51ReadBackupTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'terento_mtp_install_map_file|terento_mtp_delete_managed_map|SendObject|DeleteObject|MoveObject|Rename' \
    "$project_root/Sources/TerentoPoC/Installation/MTPReadBackupAdapter.swift"; then
    print -u2 "FAIL: Stage 5.1 native read adapter contains a write/delete operation"
    exit 1
fi

print "PASS: Stage 5.1 read/backup adapter remains write-independent"

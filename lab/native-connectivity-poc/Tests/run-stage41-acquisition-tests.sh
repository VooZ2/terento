#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage41-acquisition-tests.XXXXXX")"
binary_path="$build_dir/stage41-acquisition-tests"

swiftc \
    -module-name TerentoStage41AcquisitionTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage41AcquisitionTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eq 'LibMTPBridge|MTPTransport|SendObject|DeleteObject|MoveObject|RenameObject|Backup' \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift"; then
    print -u2 "FAIL: acquisition layer contains a device transport or write dependency"
    exit 1
fi

print "PASS: acquisition layer has no Garmin transport or write dependency"

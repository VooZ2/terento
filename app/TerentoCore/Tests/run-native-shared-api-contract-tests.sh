#!/bin/zsh
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-shared-contract-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/shared-contract-tests"
swiftc \
    -module-name TerentoSharedContractTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceRegistry.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/CompatibilityEngine.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/CompatibilityStatusClient.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceAssetRegistry.swift" \
    "$project_root/Tests/TerentoPoCTests/SharedContractFixtures.swift" \
    "$project_root/Tests/TerentoPoCTests/SharedAPIContractTests.swift" \
    -o "$binary_path"
cp "$project_root/Sources/TerentoPoC/Resources/Maps/catalog.json" "$build_dir/catalog.json"
"$binary_path"

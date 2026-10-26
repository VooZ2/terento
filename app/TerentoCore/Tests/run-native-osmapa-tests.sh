#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-osmapa-tests.XXXXXX")"
binary_path="$build_dir/osmapa-tests"

swiftc \
    -module-name TerentoOSMapaTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/MapCapability.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPlanner.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPresentation.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationAuthorization.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapConflictResolver.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationPreflight.swift" \
    "$project_root/Sources/TerentoPoC/Installation/TransferVerification.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationTransaction.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationTransportProtocols.swift" \
    "$project_root/Sources/TerentoPoC/Installation/TerentoManifestStore.swift" \
    "$project_root/Sources/TerentoPoC/Installation/Stage42TargetPolicy.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ProtectedMapInventory.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapInventoryScope.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapInstallationCoordinator.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/BBBikeArchiveSafety.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Tests/TerentoPoCTests/OSMapaTests.swift" \
    -o "$binary_path"

python3 "$project_root/Tests/Fixtures/OSMapa/make-fixtures.py" "$build_dir/fixtures"
TERENTO_OSMAPA_FIXTURES="$build_dir/fixtures" "$binary_path"

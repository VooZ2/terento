#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage42-installation-tests.XXXXXX")"
binary_path="$build_dir/stage42-installation-tests"

swiftc \
    -module-name TerentoStage42InstallationTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
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
    "$project_root/Sources/TerentoPoC/Installation/MapInstallationCoordinator.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage42InstallationTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -En "LIBMTP|MTPBridge|SendObject|DeleteObject|MoveObject|RenameObject" \
    "$project_root/Sources/TerentoPoC/Installation/MapInstallationCoordinator.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationTransportProtocols.swift"; then
    print -u2 "FAIL: Stage 4.2 domain coordinator contains a native transport dependency"
    exit 1
fi

print "PASS: Stage 4.2 domain coordinator is transport-injected and read-only in tests"

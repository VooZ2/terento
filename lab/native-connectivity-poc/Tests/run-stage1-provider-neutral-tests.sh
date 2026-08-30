#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage1-provider-neutral-tests.XXXXXX")"
binary_path="$build_dir/stage1-provider-neutral-tests"

swiftc \
    -module-name TerentoStage1ProviderNeutralTests \
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
    "$project_root/Tests/TerentoPoCTests/Stage1ProviderNeutralTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eq 'freizeitkarte|Freizeitkarte' \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPlanner.swift"; then
    print -u2 "FAIL: provider-neutral selection planner contains a provider-specific filter"
    exit 1
fi

print "PASS: selection planner has no provider-specific filter"

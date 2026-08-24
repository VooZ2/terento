#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-map-lifecycle-presentation-tests.XXXXXX")"
binary_path="$build_dir/map-lifecycle-presentation-tests"

swiftc \
    -module-name TerentoMapLifecyclePresentationTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecyclePresentation.swift" \
    "$project_root/Tests/TerentoPoCTests/MapLifecyclePresentationTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'terento_mtp_|SendObject|DeleteObject|MoveObject|RenameObject' \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycleViewModel.swift"; then
    print -u2 "FAIL: lifecycle ViewModel contains a raw device operation"
    exit 1
fi

if ! grep -Fq 'confirmationDialog' "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift" \
    || ! grep -Fq '.destructive' "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift" \
    || ! grep -Fq '.accessibilityLabel(operation.message)' "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift" \
    || ! grep -Fq 'lifecycleEpoch' "$project_root/Sources/TerentoPoC/Installation/MapLifecycleViewModel.swift"; then
    print -u2 "FAIL: lifecycle UI safety/accessibility hooks are incomplete"
    exit 1
fi

if grep -Fq 'ProgressView(value: operation.progress?.fractionCompleted ?? 0)' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift" \
    || ! grep -Fq '.progressViewStyle(.linear)' \
        "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"; then
    print -u2 "FAIL: backup progress must be real when available and indeterminate otherwise"
    exit 1
fi

print "PASS: lifecycle UI coordinator has no raw MTP operation calls"
print "PASS: lifecycle UI includes confirmation, destructive clarity, progress accessibility, and disconnect epochs"

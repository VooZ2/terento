#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-device-asset-tests.XXXXXX")"
binary_path="$build_dir/device-asset-matching-tests"

swiftc \
    -module-name TerentoDeviceAssetMatchingTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceRegistry.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/CompatibilityEngine.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceAssetRegistry.swift" \
    "$project_root/Tests/TerentoPoCTests/DeviceAssetMatchingTests.swift" \
    -o "$binary_path"

"$binary_path"

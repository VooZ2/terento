#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-device-binding-profile-tests.XXXXXX")"
binary_path="$build_dir/device-binding-profile-tests"

swiftc \
    -module-name TerentoDeviceBindingProfileTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/MapCapability.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceAssetRegistry.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Tests/TerentoPoCTests/DeviceBindingProfileTests.swift" \
    -o "$binary_path"

"$binary_path"

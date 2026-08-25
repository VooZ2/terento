#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-compatibility-status-client-tests.XXXXXX")"
binary_path="$build_dir/compatibility-status-client-tests"

swiftc \
    -module-name TerentoCompatibilityStatusClientTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/CompatibilityStatusClient.swift" \
    "$project_root/Tests/TerentoPoCTests/CompatibilityStatusClientTests.swift" \
    -o "$binary_path"

"$binary_path"

#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-map-capability-tests.XXXXXX")"
binary_path="$build_dir/map-capability-tests"

swiftc \
    -module-name TerentoMapCapabilityTests \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/MapCapability.swift" \
    "$project_root/Tests/TerentoPoCTests/MapCapabilityTests.swift" \
    -o "$binary_path"

"$binary_path"

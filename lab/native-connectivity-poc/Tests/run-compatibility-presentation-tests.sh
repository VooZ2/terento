#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-compatibility-presentation-tests.XXXXXX")"
binary_path="$build_dir/compatibility-presentation-tests"

swiftc \
    -module-name TerentoCompatibilityPresentationTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/CompatibilityPresentation.swift" \
    "$project_root/Tests/TerentoPoCTests/CompatibilityPresentationTests.swift" \
    -o "$binary_path"

"$binary_path"

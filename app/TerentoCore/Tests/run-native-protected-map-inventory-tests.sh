#!/bin/zsh
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-protected-map-inventory-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
swiftc \
    -module-name TerentoProtectedMapInventoryTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ProtectedMapInventory.swift" \
    "$project_root/Tests/TerentoPoCTests/ProtectedMapInventoryTests.swift" \
    -o "$build_dir/protected-map-inventory-tests"
"$build_dir/protected-map-inventory-tests"

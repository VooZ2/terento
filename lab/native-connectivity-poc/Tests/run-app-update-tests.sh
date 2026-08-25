#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-app-update-tests.XXXXXX")"
binary_path="$build_dir/app-update-tests"

swiftc \
    -module-name TerentoAppUpdateTests \
    "$project_root/Sources/TerentoPoC/Views/AppLinks.swift" \
    "$project_root/Tests/TerentoPoCTests/AppUpdateTests.swift" \
    -o "$binary_path"

"$binary_path"

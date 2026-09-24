#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-installation-authorization-tests.XXXXXX")"
binary_path="$build_dir/installation-authorization-tests"
trap 'rm -rf "$build_dir"' EXIT

swiftc \
    -module-name TerentoInstallationAuthorizationTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationAuthorization.swift" \
    "$project_root/Tests/TerentoPoCTests/InstallationAuthorizationTests.swift" \
    -o "$binary_path"

"$binary_path"

#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-connection-lifecycle-tests.XXXXXX")"
binary_path="$build_dir/connection-lifecycle-tests"

swiftc \
    -module-name TerentoConnectionLifecycleTests \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift" \
    "$project_root/Tests/TerentoPoCTests/ConnectionLifecycleTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'SendObject|DeleteObject|MoveObject|RenameObject|terento_mtp_install|terento_mtp_delete' \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift" \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceEngine.swift" \
    "$project_root/Sources/TerentoPoC/MTPTransport/MTPTransport.swift"; then
    print -u2 "FAIL: connection lifecycle boundary contains a write/delete operation"
    exit 1
fi

print "PASS: connection lifecycle boundary has no device write/delete surface"

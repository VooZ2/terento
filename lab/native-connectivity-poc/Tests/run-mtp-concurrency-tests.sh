#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-mtp-concurrency-tests.XXXXXX")"
binary_path="$build_dir/mtp-concurrency-tests"
export CLANG_MODULE_CACHE_PATH="$build_dir/module-cache"
mkdir -p "$CLANG_MODULE_CACHE_PATH"

swiftc \
    -parse-as-library \
    -module-name TerentoMTPConcurrencyTests \
    "$project_root/Sources/TerentoPoC/MTPTransport/MTPOperationGate.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapLifecycleOperationController.swift" \
    "$project_root/Tests/TerentoPoCTests/MTPOperationConcurrencyTests.swift" \
    -o "$binary_path"

"$binary_path"

print "PASS: MTP concurrency tests use the real operation gate and lifecycle controller"

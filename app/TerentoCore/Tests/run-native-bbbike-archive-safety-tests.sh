#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$project_root/../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-bbbike-archive-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

swiftc \
    -module-name TerentoBBBikeArchiveSafetyTests \
    "$project_root/Sources/TerentoPoC/MapCatalog/BBBikeArchiveSafety.swift" \
    "$repo_root/Tests/BBBikeArchiveSafetyTests.swift" \
    -o "$build_dir/bbbike-archive-tests"
"$build_dir/bbbike-archive-tests"

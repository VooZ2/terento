#!/bin/zsh
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-mutation-ledger-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
swiftc \
    -module-name TerentoMutationLedgerTests \
    "$project_root/Sources/TerentoPoC/Installation/NativeMutationLedger.swift" \
    "$project_root/Tests/TerentoPoCTests/NativeMutationLedgerTests.swift" \
    -o "$build_dir/mutation-ledger-tests"
"$build_dir/mutation-ledger-tests"

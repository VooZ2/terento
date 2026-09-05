#!/bin/sh
set -eu
root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/terento-bounded-tests.XXXXXX")"
swiftc "$root/Sources/TerentoPoC/MTPTransport/BoundedNativeProcess.swift" \
  "$root/Tests/TerentoPoCTests/BoundedNativeProcessTests.swift" -o "$build/tests"
"$build/tests"

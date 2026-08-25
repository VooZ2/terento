#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-user-facing-error-tests.XXXXXX")"
binary_path="$build_dir/user-facing-error-message-tests"

swiftc \
    -module-name TerentoUserFacingErrorMessageTests \
    "$project_root/Sources/TerentoPoC/Errors/UserFacingErrorMessage.swift" \
    "$project_root/Tests/TerentoPoCTests/UserFacingErrorMessageTests.swift" \
    -o "$binary_path"

"$binary_path"

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
if ! grep -Fq 'if let message = deviceEngine.userErrorMessage' "$connect_screen"; then
    print -u2 "FAIL: Connect screen does not present the resolved device error"
    exit 1
fi

print "PASS: Connect screen presents the resolved device error"

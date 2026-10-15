#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-user-facing-error-tests.XXXXXX")"
binary_path="$build_dir/user-facing-error-message-tests"

swiftc \
    -module-name TerentoUserFacingErrorMessageTests \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift" \
    "$project_root/Sources/TerentoPoC/Errors/UserFacingErrorMessage.swift" \
    "$project_root/Tests/TerentoPoCTests/UserFacingErrorMessageTests.swift" \
    -o "$binary_path"

"$binary_path"

# MacDroid runs as a menu bar app: accessory apps count, app extensions and
# background-only processes do not.
error_source="$project_root/Sources/TerentoPoC/Errors/UserFacingErrorMessage.swift"
for needle in 'isUserApplication: $0.activationPolicy != .prohibited' 'pathExtension.lowercased() != "appex"'; do
    if ! grep -Fq -- "$needle" "$error_source"; then
        print -u2 "FAIL: running-app conflict detection lost its menu bar app rule ($needle)"
        exit 1
    fi
done

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
if ! grep -Fq 'if let message = deviceEngine.userErrorMessage' "$connect_screen"; then
    print -u2 "FAIL: Connect screen does not present the resolved device error"
    exit 1
fi

# A problem names its cause, says what is wrong, then shows the help box.
for needle in 'return failure.title' 'return failure.reason' \
    'connectHelpBox(heading: issue.finding, steps: issue.steps, note: issue.note)' \
    'return deviceEngine.connectFailure' 'return UserFacingErrorMessage.detectionAttention(outcome)'; do
    if ! grep -Fq -- "$needle" "$connect_screen"; then
        print -u2 "FAIL: Connect screen does not present the cause-specific failure ($needle)"
        exit 1
    fi
done

print "PASS: Connect screen presents the resolved device error"

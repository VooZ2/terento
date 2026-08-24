#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/ConnectScreen.swift"
device_engine="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/DeviceEngine/DeviceEngine.swift"
map_lifecycle="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Installation/MapLifecycle.swift"

assert_contains() {
    local needle="$1"
    local file="$2"
    rg -Fq "$needle" "$file" || {
        print -u2 "FAIL: missing '$needle' in $file"
        exit 1
    }
}

assert_absent() {
    local needle="$1"
    local file="$2"
    if rg -Fq "$needle" "$file"; then
        print -u2 "FAIL: stale user-facing text '$needle' remains in $file"
        exit 1
    fi
}

assert_contains 'if deviceEngine.state == .detecting {' "$connect_screen"
assert_contains 'ProgressView()' "$connect_screen"
assert_contains 'This can take up to 2 minutes.' "$connect_screen"
assert_contains 'title: deviceEngine.state == .failed ? "Try again" : "Connect device"' "$connect_screen"
assert_contains 'shouldShowTroubleshooting' "$connect_screen"
assert_contains 'stateManager.fail()' "$device_engine"
assert_contains '120_000_000_000' "$device_engine"
assert_contains 'Connection timed out after 2 minutes.' "$device_engine"
assert_contains 'otherMapsExpanded = false' "$connect_screen"
assert_contains 'topPadding: TerentoPageLayout.primaryTopPadding' "$connect_screen"
assert_contains 'bottomPadding: TerentoPageLayout.primaryBottomPadding' "$connect_screen"
assert_contains 'Installed · Read-only' "$map_lifecycle"
assert_contains 'Read-only · Terento will leave it unchanged.' "$map_lifecycle"
assert_contains 'let note: String?' "$connect_screen"
assert_contains '.tint(TerentoColors.sky)' "$connect_screen"
assert_contains 'return TerentoColors.sky.opacity(0.20)' "$connect_screen"
assert_contains 'case .active:' "$connect_screen"
assert_absent '.tint(.white)' "$connect_screen"
assert_contains 'maxHeight: troubleshootingExpanded ? 220 : 300' "$connect_screen"
assert_contains '.frame(maxHeight: .infinity, alignment: .center)' "$connect_screen"
assert_contains 'return TerentoColors.lichenDark' "$connect_screen"
assert_absent 'return TerentoColors.warmStone' "$connect_screen"

assert_absent 'Identity unavailable' "$map_lifecycle"
assert_absent 'Installed · Garmin system map' "$map_lifecycle"
assert_absent 'Other maps are shown for reference and left unchanged.' "$connect_screen"
assert_absent 'Garmin system maps are not included in this list.' "$connect_screen"

print "PASS: connection activity, timeout recovery, shared layout, and Manage maps copy checks"

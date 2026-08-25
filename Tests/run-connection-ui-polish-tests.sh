#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/ConnectScreen.swift"
device_engine="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/DeviceEngine/DeviceEngine.swift"
map_lifecycle="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Installation/MapLifecycle.swift"
connecting_illustration="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Resources/Illustrations/connect-illustration-connecting.png"
project_file="$repo_root/Terento.xcodeproj/project.pbxproj"

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

assert_contains 'ProgressView()' "$connect_screen"
assert_contains 'ResourceImage(name: connectionIllustrationName' "$connect_screen"
assert_contains 'return "connect-illustration-connecting"' "$connect_screen"
assert_contains 'return "connect-illustration"' "$connect_screen"
assert_contains 'connect-illustration-connecting.png in Resources' "$project_file"
assert_contains 'return "Waiting for your Garmin…"' "$connect_screen"
assert_contains 'return "Garmin not found"' "$connect_screen"
assert_contains 'return "This may take up to 2 minutes."' "$connect_screen"
assert_contains "return \"We couldn't find your Garmin within 2 minutes. Reconnect your watch and try again.\"" "$connect_screen"
assert_contains 'return "Waiting…"' "$connect_screen"
assert_contains 'VStack(alignment: .center, spacing: 0)' "$connect_screen"
assert_contains 'multilineTextAlignment(.center)' "$connect_screen"
assert_contains '.frame(maxWidth: 620, alignment: .center)' "$connect_screen"
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
assert_contains 'return troubleshootingExpanded ? 220 : 300' "$connect_screen"
assert_contains 'return troubleshootingExpanded ? 180 : 220' "$connect_screen"
assert_contains '.frame(maxHeight: .infinity, alignment: .center)' "$connect_screen"
assert_contains 'return TerentoColors.lichenDark' "$connect_screen"
assert_contains 'title: "View diagnostic log"' "$connect_screen"
assert_contains 'title: "Report an issue ↗"' "$connect_screen"
assert_contains 'InstallationSupportActionButton' "$connect_screen"
assert_contains '.buttonStyle(.link)' "$connect_screen"
assert_contains 'TerentoDiagnosticLog.revealLog()' "$connect_screen"
assert_contains 'The diagnostic log is not available yet.' "$connect_screen"
assert_contains 'NSWorkspace.shared.open(fileURL)' "$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Diagnostics/TerentoDiagnosticLog.swift"
assert_contains 'TerentoDiagnosticLog.swift in Sources' "$project_file"
assert_absent 'Button("Show log.txt")' "$connect_screen"
assert_absent 'Button("Report issue")' "$connect_screen"
assert_absent 'return TerentoColors.warmStone' "$connect_screen"
assert_absent 'Looking for your Garmin' "$connect_screen"
assert_absent 'Looking for your Garmin' "$device_engine"
assert_contains 'Still waiting for your Garmin…' "$device_engine"
assert_absent 'Connecting your Garmin' "$connect_screen"
assert_absent 'Connecting your Garmin' "$device_engine"
assert_absent 'Connection problem' "$connect_screen"
assert_absent 'connectionStatusUsesInlineIndicator' "$connect_screen"

[[ -f "$connecting_illustration" ]] || {
    print -u2 "FAIL: missing connecting illustration variant"
    exit 1
}
[[ "$(sips -g hasAlpha "$connecting_illustration" | awk '/hasAlpha/ { print $2 }')" == "yes" ]] || {
    print -u2 "FAIL: connecting illustration must retain transparent alpha"
    exit 1
}

connection_status_view="$(awk '
    /private var connectionStatusView/ { capture = 1 }
    /private var connectionIllustrationName/ { capture = 0 }
    capture { print }
' "$connect_screen")"
if [[ "$connection_status_view" == *'ProgressView()'* ]]; then
    print -u2 "FAIL: connecting state still has an inline spinner"
    exit 1
fi
if [[ "$connection_status_view" == *'Circle()'* ]]; then
    print -u2 "FAIL: connection state still has a decorative status dot"
    exit 1
fi

assert_absent 'Identity unavailable' "$map_lifecycle"
assert_absent 'Installed · Garmin system map' "$map_lifecycle"
assert_absent 'Other maps are shown for reference and left unchanged.' "$connect_screen"
assert_absent 'Garmin system maps are not included in this list.' "$connect_screen"

print "PASS: connection activity, timeout recovery, shared layout, and Manage maps copy checks"

#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/ConnectScreen.swift"
device_engine="$repo_root/app/TerentoCore/Sources/TerentoPoC/DeviceEngine/DeviceEngine.swift"
map_lifecycle="$repo_root/app/TerentoCore/Sources/TerentoPoC/Installation/MapLifecycle.swift"
connecting_illustration="$repo_root/app/TerentoCore/Sources/TerentoPoC/Resources/Illustrations/connect-illustration-connecting.png"
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
assert_contains "return \"Couldn't connect to Garmin\"" "$connect_screen"
assert_contains 'return "This may take up to 2 minutes. Terento tells you if something is wrong."' "$connect_screen"
assert_contains "return \"We couldn't connect to your Garmin. Reconnect it and try again.\"" "$connect_screen"
assert_contains 'return message' "$connect_screen"
assert_absent 'return "Garmin not found"' "$connect_screen"
# A final failure names its cause; the generic title remains the fallback and
# the sidebar label.
if [[ "$(rg -Fxc "            return \"Couldn't connect to Garmin\"" "$connect_screen")" -ne 2 ]]; then
    print -u2 "FAIL: failed connection title must stay the fallback and the sidebar label"
    exit 1
fi
assert_contains 'if let failure = deviceEngine.connectFailure {' "$connect_screen"
assert_contains 'return failure.title' "$connect_screen"
assert_contains 'return failure.reason' "$connect_screen"
assert_contains 'connectFailure = failure' "$device_engine"
# Every Connect problem uses the calm "Still not showing up?" pattern: an
# outline status icon, a one-line description, then one light help box with a
# finding, icon steps, the guide link and a note. There is no second list.
assert_contains 'connectHelpBox(heading: issue.finding, steps: issue.steps, note: issue.note)' "$connect_screen"
assert_contains 'troubleshootingRow(step.text, icon: step.systemImage)' "$connect_screen"
assert_contains '.background(TerentoColors.helpSurface, in: RoundedRectangle(cornerRadius: 10))' "$connect_screen"
assert_contains 'return ("exclamationmark.circle", TerentoColors.warning)' "$connect_screen"
assert_contains 'return ("exclamationmark.triangle", TerentoColors.error)' "$connect_screen"
assert_absent 'Having trouble connecting?' "$connect_screen"
assert_absent 'troubleshootingExpanded' "$connect_screen"
# Two minutes with nothing on USB escalates the waiting page; detection keeps polling.
assert_contains 'showsConnectChecklist && deviceEngine.hasWaitedWithoutUSB' "$connect_screen"
assert_contains 'heading: "Still not showing up?"' "$connect_screen"
assert_contains 'Plug it directly into the Mac, not into a USB hub' "$connect_screen"
assert_contains 'detectionPolicy.reportedOutcomes.contains(.timeoutNoUSB)' "$device_engine"
# Every sidebar status has text and an icon; colour only supports it.
assert_contains 'Image(systemName: statusIcon)' "$connect_screen"
assert_contains 'return "Needs attention"' "$connect_screen"
sidebar_status="$(awk '
    /private struct SidebarConnectionStatus/ { capture = 1 }
    /private enum ConnectionStatusPresentation/ { capture = 0 }
    capture { print }
' "$connect_screen")"
if [[ "$sidebar_status" == *'Circle()'* ]]; then
    print -u2 "FAIL: sidebar status still relies on a colour dot"
    exit 1
fi
assert_contains '.accessibilityLabel("\(connectionStatusTitle) \(connectionStatusDescription)")' "$connect_screen"
assert_contains 'return "Waiting…"' "$connect_screen"
assert_contains 'VStack(alignment: .center, spacing: 0)' "$connect_screen"
assert_contains 'multilineTextAlignment(.center)' "$connect_screen"
assert_contains '.frame(maxWidth: 460, alignment: .center)' "$connect_screen"
assert_contains 'title: deviceEngine.state == .failed ? "Try again" : "Connect device"' "$connect_screen"
assert_contains 'stateManager.fail()' "$device_engine"
assert_contains 'static let connectionWindow: TimeInterval = 120' "$repo_root/app/TerentoCore/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift"
assert_contains 'Connection timed out after 2 minutes.' "$device_engine"
assert_contains '? "Connect your watch" : "Your Garmin was disconnected"' "$connect_screen"
assert_contains 'lifecycleViewModel.interruptedOperationNotice ?? deviceEngine.disconnectNotice' "$connect_screen"
assert_contains 'Use a USB data cable, not a charge-only cable' "$connect_screen"
assert_contains 'Quit Garmin Express' "$connect_screen"
assert_contains 'case .needsAttention(let outcome):' "$connect_screen"
assert_contains 'private var connectionStatusIcon: (name: String, color: Color)?' "$connect_screen"
# A failed map read on a connected watch says so, shows an error icon and offers Try again.
if [[ "$(rg -Fc "title: \"Couldn't read your maps\"" "$connect_screen")" -ne 2 \
    || "$(rg -Fc 'onRetry: refreshMapInventory' "$connect_screen")" -ne 2 ]]; then
    print -u2 "FAIL: Install and Manage maps must both present scan failure with Try again"
    exit 1
fi
assert_contains 'Image(systemName: isError ? "exclamationmark.triangle.fill" : "map")' "$connect_screen"
assert_contains 'externalMapsExpanded = false' "$connect_screen"
assert_contains 'topPadding: TerentoPageLayout.primaryTopPadding' "$connect_screen"
assert_contains 'bottomPadding: TerentoPageLayout.primaryBottomPadding' "$connect_screen"
assert_contains 'return "Read-only"' "$map_lifecycle"
assert_contains 'Read-only · Terento will leave it unchanged.' "$map_lifecycle"
assert_contains 'let note: String?' "$connect_screen"
assert_contains '.tint(TerentoColors.sky)' "$connect_screen"
assert_contains 'return TerentoColors.sky.opacity(0.20)' "$connect_screen"
assert_contains 'case .active:' "$connect_screen"
assert_absent '.tint(.white)' "$connect_screen"
assert_contains 'if shownConnectIssue != nil || showsNoUSBHelp {' "$connect_screen"
assert_contains '.frame(maxHeight: .infinity, alignment: .center)' "$connect_screen"
assert_contains 'return TerentoColors.lichenDark' "$connect_screen"
assert_contains 'InstallationFailureDialog(' "$connect_screen"
assert_contains 'onReportIssue: { reportInstallationIssue(for: selectedInstallationPlan) }' "$connect_screen"
assert_contains 'InstallationIssueReport.openGitHub(draft)' "$connect_screen"
assert_contains 'GitHub could not be opened. Please try again.' "$connect_screen"
assert_contains 'NSWorkspace.shared.open(fileURL)' "$repo_root/app/TerentoCore/Sources/TerentoPoC/Diagnostics/TerentoDiagnosticLog.swift"
assert_contains 'TerentoDiagnosticLog.swift in Sources' "$project_file"
assert_absent 'Button("Show log.txt")' "$connect_screen"
assert_absent 'Button("Report issue")' "$connect_screen"
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
if [[ "$connection_status_view" == *'TerentoColors.warmStone'* ]]; then
    print -u2 "FAIL: connection state must not use the compatibility Warm Stone token"
    exit 1
fi

assert_absent 'Identity unavailable' "$map_lifecycle"
assert_absent 'Installed · Garmin system map' "$map_lifecycle"
assert_absent 'Other maps are shown for reference and left unchanged.' "$connect_screen"
assert_absent 'Garmin system maps are not included in this list.' "$connect_screen"

print "PASS: connection activity, timeout recovery, shared layout, and Manage maps copy checks"

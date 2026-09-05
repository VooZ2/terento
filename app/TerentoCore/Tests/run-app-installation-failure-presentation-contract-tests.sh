#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
issue_report="$project_root/Sources/TerentoPoC/Diagnostics/InstallationIssueReport.swift"
github_asset="$project_root/../../app/Terento/Assets.xcassets/GitHubMark.imageset/github-mark.svg"
active_section="$(sed -n '/private func activeInstallationContent/,/private var installationJourneyView/p' "$connect_screen")"

require_source() {
    local text="$1"
    local message="$2"
    if ! grep -Fq "$text" "$connect_screen"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_active() {
    local text="$1"
    local message="$2"
    if ! grep -Fq "$text" <<< "$active_section"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_active() {
    local text="$1"
    local message="$2"
    if grep -Fq "$text" <<< "$active_section"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_issue() {
    local text="$1"
    local message="$2"
    if ! grep -Fq "$text" "$issue_report"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_active 'InstallationMapsSectionHeader(count: plan.selectedItems.count)' 'installation map count is not sourced from the operation plan'
require_source '\(count) \(count == 1 ? "map" : "maps")' 'installation count has no singular/plural grammar'
require_source '.accessibilityLabel("Installing maps, \(countLabel)")' 'installation count is not announced accessibly'
require_source 'private struct InstallationMapsList: View' 'installation map viewport is missing'
require_source 'private static let visibleRowCapacity = 3' 'installation viewport does not target three full rows'
require_source 'items.count > Self.visibleRowCapacity ? .automatic : .hidden' 'installation list does not scroll only from four maps'
require_active 'TerentoInstallationProgressPageShell' 'installation page does not use the measured progress viewport'
require_active 'installationJourneyView' 'installation progress card is missing below the map section'
require_source 'private let bottomBreathingRoom: CGFloat = 28' 'installation page lacks the 24–32 point bottom safety gap'
require_source 'proxy.size.height' 'installation page does not derive its layout from the actual viewport'
require_source 'min(items.count, Self.visibleRowCapacity)' 'one- and two-map list heights are not content-aware'
require_source 'items.count > Self.visibleRowCapacity ? .automatic : .hidden' 'four-plus map scrolling is not preserved'
require_source 'state == .active, bytes.speed > 0' 'completed downloads can still show historical transfer speed'
require_source 'state == .pending' 'pending stages have no explicit muted treatment'
reject_active 'Installation did not complete. Review the status above before trying again.' 'failure result is duplicated below the timeline'
reject_active 'installationEvidenceDeliveryView' 'compatibility-report delivery status remains in the main failure layout'
reject_active 'View diagnostic log' 'failure footer still exposes the old inline diagnostic action'
reject_active 'Installation stopped' 'active installation page still transforms into a dedicated failure page'
reject_active 'SecondaryButton(title: "Report issue")' 'active installation footer still owns the failure action'
require_source '@State private var isShowingInstallationFailure = false' 'terminal failure has no modal presentation state'
require_source 'if phase == .failed {' 'terminal failure does not present the failure modal'
require_source 'isPresented: $isShowingInstallationFailure' 'failure modal is not attached to the app shell'
require_source 'onDismiss: returnToDeviceAfterFailure' 'Escape or sheet dismissal does not recover to Device'
require_source 'selectedSection = .device' 'failure recovery does not navigate to Device'
require_source 'title: "Installation stopped"' 'failure modal title is incorrect'
require_source 'message: "The map could not be installed."' 'failure modal lacks the concise outcome'
require_source 'detailMessage: reason' 'failure modal does not show the normalized reason'
require_source '"Your existing maps were not changed."' 'failure modal has no conditional safety reassurance'
require_source 'secondaryLabel: "Report issue"' 'failure modal has no Report issue action'
require_source 'secondaryAssetIcon: "GitHubMark"' 'Report issue has no canonical GitHub mark'
require_source 'secondaryUsesCancelShortcut: false' 'Escape incorrectly activates Report issue'
require_source 'primaryLabel: "Back to device"' 'failure modal lacks the explicit primary recovery action'
require_source '.keyboardShortcut(.defaultAction)' 'Back to device is not the safe default action'
require_source 'InstallationIssueReport.copyAndOpenGitHub(draft)' 'Report issue is not connected to the reviewable GitHub flow'
test -f "$github_asset" || { print -u2 'FAIL: canonical GitHub mark asset is missing'; exit 1; }
require_issue 'URLQueryItem(name: "template", value: "installation-failure.yml")' 'GitHub issue does not target the installation failure form'
require_issue 'URLQueryItem(name: "diagnostic-report", value: body)' 'GitHub diagnostic form field is not pre-populated'
require_issue 'clipboard(draft.body)' 'sanitized report is not copied as the manual fallback'
require_issue 'Prepared by Terento. Please review before submitting.' 'prepared issue does not explain review-before-submit'

print 'PASS: installation progress and failure UX polish contract'

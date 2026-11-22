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
require_source 'onDismiss: handleInstallationFailureDismissed' 'Escape or sheet dismissal does not recover to Device'
require_source 'installationFailureFollowUp = .backToDevice' 'sheet dismissal does not default to Device recovery'
require_source 'case .backToDevice:
            returnToDeviceAfterFailure()' 'Device recovery path is missing'
require_source 'onTryAgain: mapEngine.canRetryFailedInstallation' 'Try again is not limited to retryable failures'
require_source 'if let wait = makeWatchReconnectWait() {' 'a stop before any write for a busy or missing watch does not wait for the watch'
require_source 'guard mapEngine.stoppedBeforeWriteForWatchReconnect,' 'the reconnect wait is not limited to stops before any write'
require_source '!plan.installItems.contains(where: { $0.package.sourceKind == .custom })' 'custom imports, which are not kept across a disconnect, wait for the watch'
require_source 'if let wait = watchReconnectWait {
                // The wait stays in place across the unplug' 'the reconnect wait is not on the page or does not survive the unplug'
if grep -Fq '.sheet(item: $watchReconnectWait' "$connect_screen"; then
    print -u2 'FAIL: the reconnect wait is still a dialog'
    exit 1
fi
require_source 'navigationLocked: installationOperationIsActive || watchReconnectWait != nil' 'the sidebar can leave the reconnect wait'
# Both ends of the wait (Cancel and the policy decision) run the follow-up once.
[[ "$(grep -c 'endWatchReconnectWait()' "$connect_screen")" == 3 ]] || { print -u2 'FAIL: an end of the reconnect wait skips its follow-up'; exit 1; }
require_source 'guard watchReconnectWait != nil else { return }
        watchReconnectWait = nil
        handleWatchReconnectWaitEnded()' 'the reconnect wait follow-up can run twice or not at all'
[[ "$(grep -c 'watchReconnectWait = nil' "$connect_screen")" == 1 ]] || { print -u2 'FAIL: the reconnect wait can end without its follow-up'; exit 1; }
require_source 'watchReconnectWait?.watchWasDisconnected = true' 'an unplug is not recorded for the reconnect wait'
require_source 'connectedWatchKey: identity?.physicalManifestDeviceKey' 'the reconnected watch is not compared with the watch that stopped'
require_source 'isCheckingWatch ? "arrow.triangle.2.circlepath" : "cable.connector"' 'the reconnect wait status has no icon'
require_source 'isCheckingWatch ? "Checking your device" : "Reconnect your device"' 'the reconnect wait status has no text'
reconnect_dialog="$(sed -n '/private struct WatchReconnectWaitPanel: View/,/private struct InstallationFailureDialog: View/p' "$connect_screen")"
if grep -Fq 'mapTitle' <<< "$reconnect_dialog"; then
    print -u2 'FAIL: the reconnect wait still shows a map name'
    exit 1
fi
require_source '// No map name here: the wait is about the watch, not one map.' 'the reconnect wait names a map'
require_source 'installationFailureSnapshot = makeInstallationFailureSnapshot()' 'the failure is not captured when the installation fails'
require_source 'mapEngine.installationPhase == .failed ? nil : installationFailureSnapshot' 'the captured failure is not limited to a reset engine'
require_source 'if let retained = retainedInstallationFailure { return retained.reason }' 'a disconnect replaces the real failure reason with a generic one'
require_source 'if let retained = retainedInstallationFailure { return retained.safetyMessage }' 'a disconnect drops the safety reassurance of the real failure'
require_source 'let draft = retainedInstallationFailure?.issueDraft ?? installationIssueDraft(for: plan)' 'Report issue loses the failure details after a disconnect'
require_source 'installationFailureSnapshot = nil' 'the captured failure outlives its dialog'
require_source '.onChange(of: isCheckingWatch) { _ in announceState() }' 'VoiceOver does not hear the reconnect wait state change'
require_source '&& watchReconnectWait == nil' 'the update prompt can open over the reconnect wait'
# The update offer is a quiet line on Device, not a dialog, with the same calls.
if grep -Fq '.sheet(item: $updatePrompt)' "$connect_screen"; then
    print -u2 'FAIL: the update offer is still a dialog'
    exit 1
fi
require_source 'if selectedSection == .device, watchReconnectWait == nil, let update = updatePrompt {' 'the update offer is not limited to Device'
require_source 'if appUpdateController.openDownload(for: update) {' 'Download does not use the validated update URL'
require_source 'appUpdateController.deferPrompt(for: update)' 'Later does not defer the offer'
require_source '_ = appUpdateController.openReleaseNotes(for: update)' 'release notes do not use the validated link'
require_source 'watchReconnectFollowUp = endFollowUp(for: wait, decision: .keepWaiting)' 'Cancel skips the failure dialog and its Report issue'
# The wait reports its start and its end to the funnel (RECONNECT_WAIT), once each.
require_source 'watchReconnectWait = wait
                    mapEngine.recordReconnectWait(.shown)' 'the reconnect wait is not reported when it appears'
require_source 'mapEngine.recordReconnectWait(WatchReconnectWaitPolicy.funnelOutcome(for: .keepWaiting))' 'Cancel of the reconnect wait is not reported'
require_source 'mapEngine.recordReconnectWait(WatchReconnectWaitPolicy.funnelOutcome(for: decision))' 'the end of the reconnect wait is not reported'
[[ "$(grep -c 'mapEngine.recordReconnectWait(' "$connect_screen")" == 3 ]] || { print -u2 'FAIL: the reconnect wait reports its outcome more than once'; exit 1; }
require_source 'Text("Nothing was written to your device. Terento waits up to 5 minutes.")' 'the reconnect wait does not say that nothing was written'
[[ "$(grep -c 'Button' <<< "$reconnect_dialog")" == 1 ]] && grep -Fq 'SecondaryButton(title: "Cancel", action: onCancel)' <<< "$reconnect_dialog" \
    || { print -u2 'FAIL: the reconnect wait offers an action other than Cancel'; exit 1; }
grep -Fq '.keyboardShortcut(.cancelAction)' <<< "$reconnect_dialog" || { print -u2 'FAIL: Escape does not end the reconnect wait'; exit 1; }
# One rule for every step that cannot be cancelled (owner QA 2026-11-22):
# Cancel is shown only while it works and is hidden in Preparing, Installing
# and Finishing alike; no disabled Cancel anywhere.
require_active 'if mapEngine.canCancelInstallationPreparation {' 'Cancel is not limited to the steps that can be cancelled'
[[ "$(grep -c 'SecondaryButton(title: "Cancel")' <<< "$active_section")" == 1 ]] \
    || { print -u2 'FAIL: the installation progress shows more than one Cancel'; exit 1; }
reject_active 'SecondaryButton(title: "Cancel") {}' 'a step that cannot be cancelled shows a disabled Cancel'
reject_active 'installationPhase == .preparing {' 'Preparing has its own Cancel rule'
reject_active 'Can’t cancel while' 'a step that cannot be cancelled shows a disabled Cancel with a reason'
# Owner QA 2026-11-22: while Finishing reads the map back ("X of Y checked")
# its bar is determinate and follows the checked bytes; the same 0.25 limit
# picks the bar and the line, and the sweep restarts for the later waits.
require_source 'progress: finishingReadBackFraction,' 'the Finishing bar does not follow the checked bytes'
require_source 'checkedBytes: mapEngine.finishingTransferProgress?.bytesTransferred,' 'the Finishing bar is not driven by the read-back bytes'
require_source 'case ..<InstallationFinishingStepPresentation.readBackPhaseLimit:' 'the "checked" line and the bar use different limits'
require_source 'withTransaction(transaction) { sweeping = false }' 'the indeterminate bar does not restart after a measured value'
require_source 'onManageMaps: mapEngine.installationResult?.mayHaveLeftMapOnWatch == true' 'leftover-map failures do not offer Manage maps'
require_source 'selectedSection = .device' 'failure recovery does not navigate to Device'
require_source 'title: "Installation stopped"' 'failure modal title is incorrect'
require_source 'message: "The map could not be installed."' 'failure modal lacks the concise outcome'
require_source 'detailMessage: reason' 'failure modal does not show the normalized reason'
require_source '"Your existing maps were not changed."' 'failure modal has no conditional safety reassurance'
require_source 'secondaryLabel: "Report issue"' 'failure modal has no Report issue action'
require_source 'secondaryAssetIcon: "GitHubMark"' 'Report issue has no canonical GitHub mark'
require_source 'secondaryUsesCancelShortcut: false' 'Escape incorrectly activates Report issue'
require_source 'primaryLabel: primaryAction?.label ?? "Back to device"' 'failure modal lacks the explicit primary recovery action'
require_source 'tertiaryLabel: primaryAction == nil ? nil : "Back to device"' 'Back to device is not kept beside Try again or Manage maps'
require_source '.keyboardShortcut(.defaultAction)' 'Back to device is not the safe default action'
require_source 'InstallationIssueReport.openGitHub(draft)' 'Report issue is not connected to the reviewable GitHub flow'
test -f "$github_asset" || { print -u2 'FAIL: canonical GitHub mark asset is missing'; exit 1; }
require_issue 'URLQueryItem(name: "body", value: body)' 'GitHub diagnostic form field is not pre-populated'
require_issue 'report = compactReport(safeBody)' 'oversized reports are not compacted for automatic prefill'
require_issue 'Prepared by Terento. Please review before submitting.' 'prepared issue does not explain review-before-submit'

print 'PASS: installation progress and failure UX polish contract'

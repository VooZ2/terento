#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"

review_content="$(awk '
    /private func reviewInstallContent/ { capture = 1 }
    /private func activeInstallationContent/ { capture = 0 }
    capture { print }
' "$connect_screen")"

require_review_text() {
    local text="$1"
    local message="$2"
    if [[ "$review_content" != *"$text"* ]]; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_review_text() {
    local text="$1"
    local message="$2"
    if [[ "$review_content" == *"$text"* ]]; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_review_text 'Terento will install these maps to your Garmin.' 'Ready repeats the installation explanation'
reject_review_text 'Terento sends privacy-minimised diagnostics by default' 'Ready repeats the About privacy explanation'
require_review_text 'TerentoInstallFooterPageShell(bodyScrolls: true)' 'Review body cannot scroll independently of Storage and actions'
require_review_text 'VStack(spacing: TerentoPageLayout.sectionSpacing + 18)' 'Storage-to-button spacing no longer matches Install maps'
require_review_text 'if !plan.canContinue, let reason = installAvailability.userReason' 'Review hides the resolved blocked-install reason'
require_review_text 'beginInstallationAfterConsent(plan)' 'Install maps bypasses the existing authorized path'
require_review_text '!mapSupport.canAttemptTerentoMapInstall' 'map capability guard is missing'
require_review_text '|| !installAvailability.isEnabled' 'resolved install availability guard is missing'
require_review_text 'selectedInstallationPlan = nil' 'Back no longer clears the selected plan'
require_review_text 'localInstallStep = .choose' 'Back no longer returns to selection'
# Assert placement, not merely presence: Storage belongs to the fixed footer
# before its actions, and cannot drift back into the scrollable review body.
review_body="${review_content%%\} footer:*}"
review_footer="${review_content#*\} footer:}"
if [[ "$review_body" == *'MapSelectionStorageSummary('* \
    || "$review_footer" != *'MapSelectionStorageSummary('*'TerentoPageFooter'* ]]; then
    print -u2 'FAIL: Storage is not immediately above the fixed footer actions'
    exit 1
fi
require_review_text 'ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)' 'selected-map count is not sourced from the plan'
require_review_text 'ReadyToInstallSelectedMapsList(plan: plan)' 'selected-map list behavior changed'
require_review_text 'MapSelectionStorageSummary(' 'Storage placement changed'
if [[ "$review_content" == *'Toggle(isOn: compatibilitySharingBinding)'* \
    || "$review_content" == *'Toggle(isOn: mapStatisticsSharingBinding)'* \
    || "$review_content" == *'Help improve Garmin compatibility'* \
    || "$review_content" == *'Share anonymous map statistics'* ]]; then
    print -u2 'FAIL: Review still exposes a diagnostics opt-in or opt-out control'
    exit 1
fi
require_review_text 'PrimaryButton(title: "Install maps")' 'footer action changed'
reject_review_text 'Terento will install these maps to your Garmin.\nExisting Garmin maps will not be changed.' 'legacy two-line safety copy remains'

print 'PASS: Ready to install final fixed-layout polish contract'

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

require_review_text 'Text("Terento will install these maps to your Garmin. Existing Garmin maps will not be changed.")' 'safety copy is not one compact sentence'
require_review_text '.font(.terentoUI(size: 13, weight: .regular))' 'safety copy is not supporting text'
require_review_text 'Terento sends anonymous diagnostics by default to help improve the app and its services. You can turn this off anytime in Terento → Diagnostics.' 'diagnostics disclosure is missing'
require_review_text '.padding(.bottom, TerentoPageLayout.sectionSpacing)' 'sharing block does not keep a stable gap above the footer'
require_review_text '.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)' 'Review content cannot absorb the fixed body height'
require_review_text 'bodyScrolls: mapEngine.installationPhase == .failed' 'normal Review state may scroll as a whole page'
require_review_text 'ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)' 'selected-map count is not sourced from the plan'
require_review_text 'ReadyToInstallSelectedMapsList(items: plan.selectedItems)' 'selected-map list behavior changed'
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

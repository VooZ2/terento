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
require_review_text 'Spacer(minLength: TerentoPageLayout.sectionSpacing)' 'sharing block is not moved with flexible space'
require_review_text '.frame(maxWidth: 740, alignment: .leading)' 'sharing block width is not compact'
require_review_text '.padding(.bottom, TerentoPageLayout.sectionSpacing)' 'sharing block does not keep a stable gap above the footer'
require_review_text '.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)' 'Review content cannot absorb the fixed body height'
require_review_text 'bodyScrolls: mapEngine.installationPhase == .failed' 'normal Review state may scroll as a whole page'
require_review_text 'ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)' 'selected-map count is not sourced from the plan'
require_review_text 'ReadyToInstallSelectedMapsList(items: plan.selectedItems)' 'selected-map list behavior changed'
require_review_text 'MapSelectionStorageSummary(' 'Storage placement changed'
require_review_text 'Text("Help improve Garmin compatibility")' 'compatibility sharing title changed'
require_review_text 'Share anonymous installation results to help improve Garmin compatibility.' 'sharing description changed'
require_review_text 'Text("Share anonymous map statistics")' 'separate map-statistics choice is missing'
require_review_text 'This is off until you choose it.' 'map-statistics choice is not explicit opt-in'
require_review_text 'What is shared and how to stop sharing ↗' 'sharing link changed'
require_review_text 'PrimaryButton(title: "Install maps")' 'footer action changed'
reject_review_text 'Terento will install these maps to your Garmin.\nExisting Garmin maps will not be changed.' 'legacy two-line safety copy remains'

print 'PASS: Ready to install final fixed-layout polish contract'

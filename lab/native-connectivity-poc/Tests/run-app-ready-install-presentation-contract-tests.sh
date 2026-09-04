#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"

require_text() {
    local text="$1"
    local message="$2"
    if ! grep -Fq "$text" "$connect_screen"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_text() {
    local text="$1"
    local message="$2"
    if grep -Fq "$text" "$connect_screen"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_text 'Text("Ready to install")' 'approved title is missing'
require_text 'Text("Review your selection before installing.")' 'approved subtitle is missing'
require_text 'ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)' 'selected-map heading does not use the actual selection count'
require_text 'ReadyToInstallSelectedMapsList(items: plan.selectedItems)' 'Review does not use the bounded selected-map list'
require_text 'private static let visibleRowCapacity = 3' 'selected-map viewport does not target three rows'
require_text 'items.count > Self.visibleRowCapacity ? .automatic : .hidden' 'scroll indicators do not follow visible capacity'
require_text 'idealHeight: Self.maximumListHeight' 'selected-map region does not keep a responsive ideal height'
require_text 'MapSelectionRow(' 'Review does not reuse the shared map row presentation'
require_text 'Text("Terento will install these maps to your Garmin. Existing Garmin maps will not be changed.")' 'compact safety sentence is missing'
require_text '.font(.terentoUI(size: 13, weight: .regular))' 'safety copy is not using compact supporting typography'
require_text 'Terento sends anonymous diagnostics by default to help improve the app and its services. You can turn this off anytime in Terento → Diagnostics.' 'diagnostics disclosure is missing'
require_text '.padding(.bottom, TerentoPageLayout.sectionSpacing)' 'sharing block does not keep the approved footer separation'
require_text 'PrimaryButton(title: "Install maps")' 'Install maps action changed'
reject_text 'Terento will install these maps to your Garmin.\nExisting Garmin maps will not be changed.' 'two-line safety copy remains'
reject_text 'Share anonymous installation data to help us understand device compatibility and improve support for other Garmin users.' 'old verbose sharing copy remains'
reject_text 'Toggle(isOn: compatibilitySharingBinding)' 'compatibility opt-in remains in Review'
reject_text 'Toggle(isOn: mapStatisticsSharingBinding)' 'map-statistics opt-in remains in Review'
reject_text 'Help improve Garmin compatibility' 'legacy compatibility sharing label remains'
reject_text 'Share anonymous map statistics' 'legacy map-statistics label remains'

print 'PASS: Ready to install UI polish contract'

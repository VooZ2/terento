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

require_text 'ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)' 'heading count is not sourced from selected maps'
require_text '\(count) \(count == 1 ? "map" : "maps")' 'selected count does not use singular/plural grammar'
require_text '.accessibilityLabel("Selected maps, \(countLabel)")' 'selected count is not exposed accessibly'
require_text 'private static let visibleRowCapacity = 3' 'default viewport capacity is not three rows'
require_text 'private static let rowHeight: CGFloat = 62' 'viewport is not derived from the selected-row height'
require_text 'CGFloat(min(componentRowCount, Self.visibleRowCapacity)) * Self.rowHeight' 'list height is not content-derived and capped at three components'
require_text 'componentRowCount > Self.visibleRowCapacity ? .automatic : .hidden' 'scroll threshold does not account for selected map components'
require_text 'idealHeight: visibleListHeight' 'list cannot compress at reduced height'
require_text 'maxHeight: visibleListHeight' 'list can expand beyond three rows'
require_text '.frame(minHeight: Self.rowHeight)' 'selected rows do not match the viewport calculation'
require_text 'TerentoInstallFooterPageShell(bodyScrolls: true)' 'Ready body cannot scroll independently when content overflows'
reject_text 'private static let listHeight: CGFloat = 116' 'legacy two-row viewport remains'

print 'PASS: Ready to install selected-count and three-row viewport contract'

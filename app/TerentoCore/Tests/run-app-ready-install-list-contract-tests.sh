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
require_text 'CGFloat(visibleRowCapacity) * rowHeight' 'maximum list height is not capacity-derived'
require_text 'items.count > Self.visibleRowCapacity ? .automatic : .hidden' 'scroll threshold is not four selected maps'
require_text 'idealHeight: Self.maximumListHeight' 'list cannot compress at reduced height'
require_text 'maxHeight: Self.maximumListHeight' 'list can expand beyond three rows'
require_text '.frame(minHeight: Self.rowHeight)' 'selected rows do not match the viewport calculation'
require_text 'bodyScrolls: mapEngine.installationPhase == .failed' 'normal Ready screen may scroll as a whole page'
reject_text 'private static let listHeight: CGFloat = 116' 'legacy two-row viewport remains'

print 'PASS: Ready to install selected-count and three-row viewport contract'

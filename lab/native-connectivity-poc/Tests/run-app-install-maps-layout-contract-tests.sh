#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
catalog_loader="$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift"
window_presentation="$project_root/Sources/TerentoPoC/Views/WindowPresentation.swift"

require_in_file() {
    local text="$1"
    local file="$2"
    local message="$3"
    if ! grep -Fq "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_in_file() {
    local text="$1"
    local file="$2"
    local message="$3"
    if grep -Fq "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_in_file 'static let sectionHeaderChevronHeight: CGFloat = sectionHeaderMinHeight' "$window_presentation" 'shared disclosure geometry is not vertically aligned'
require_in_file 'TerentoDisclosureIndicator(isExpanded:' "$connect_screen" 'shared disclosure indicator is missing'
require_in_file 'Install a third-party map (.img) from this Mac.' "$connect_screen" 'approved Import subtitle is missing'
reject_in_file 'Install a third-party map (.img) file from this Mac.' "$connect_screen" 'old mechanical Import subtitle remains'
require_in_file 'Using local catalog — may be out of date' "$catalog_loader" 'neutral local-catalog fallback label is missing'
reject_in_file 'Offline catalog — may be out of date' "$catalog_loader" 'misleading offline fallback label remains'
require_in_file 'if mapEngine.catalogSource == .bundledFallback' "$connect_screen" 'fallback status is not limited to the bundled catalog state'
require_in_file 'HStack(spacing: 10)' "$connect_screen" 'filter/search controls do not use the compact shared gap'
require_in_file '.frame(minWidth: 160, idealWidth: 168, maxWidth: 175, alignment: .leading)' "$connect_screen" 'provider picker proportions changed'
require_in_file '.layoutPriority(1)' "$connect_screen" 'provider picker is not protected before search compression'
require_in_file '.frame(minWidth: 190, idealWidth: 290, maxWidth: 300)' "$connect_screen" 'search is not wider or responsive'
reject_in_file '.frame(minWidth: 377, idealWidth: 477, maxWidth: 546, alignment: .trailing)' "$connect_screen" 'legacy flexible control-group frame remains'
require_in_file '.fixedSize(horizontal: false, vertical: true)' "$connect_screen" 'Import card is not protected from vertical compression'
require_in_file 'minHeight: 0,' "$connect_screen" 'map list cannot shrink cleanly when Import expands'
require_in_file '.clipped()' "$connect_screen" 'map-list boundary is not clipped'
require_in_file 'Label("Refresh", systemImage: "arrow.clockwise")' "$connect_screen" 'Refresh moved or changed'
require_in_file 'MapSelectionStorageSummary(' "$connect_screen" 'Storage presentation moved or changed'

print 'PASS: Install maps final polish contract'

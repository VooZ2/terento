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
require_in_file 'ViewThatFits(in: .horizontal)' "$connect_screen" 'catalog toolbar cannot adapt to narrow windows'
require_in_file '.fixedSize(horizontal: true, vertical: false)' "$connect_screen" 'filter menus cannot retain their intrinsic width'
require_in_file '.frame(minWidth: 240, maxWidth: .infinity)' "$connect_screen" 'search is not wider or responsive'
require_in_file 'let count = filteredAvailableSelectionItems.count' "$connect_screen" 'toolbar count is not filtered'
reject_in_file 'availableMapsExpanded' "$connect_screen" 'catalog still has a hidden/collapsed state'
reject_in_file 'title: "Available maps"' "$connect_screen" 'redundant catalogue heading remains'
reject_in_file '.frame(minWidth: 377, idealWidth: 477, maxWidth: 546, alignment: .trailing)' "$connect_screen" 'legacy flexible control-group frame remains'
require_in_file '.fixedSize(horizontal: false, vertical: true)' "$connect_screen" 'Import card is not protected from vertical compression'
require_in_file 'minHeight: 0,' "$connect_screen" 'map list cannot shrink cleanly when Import expands'
require_in_file '.clipped()' "$connect_screen" 'map-list boundary is not clipped'
require_in_file 'Label("Refresh", systemImage: "arrow.clockwise")' "$connect_screen" 'Refresh moved or changed'
require_in_file 'MapSelectionStorageSummary(' "$connect_screen" 'Storage presentation moved or changed'

print 'PASS: Install maps final polish contract'

# The toolbar gap belongs outside the GeometryReader/scroll content. Padding
# inside the list would disappear when rows are scrolled to its upper edge.
python3 - "$connect_screen" <<'PYTEST'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
region = source.split('private var catalogMapRegion: some View {', 1)[1].split('@ViewBuilder', 1)[0]
closing_reader = region.rfind('        }')
assert closing_reader >= 0
outer_modifiers = region[closing_reader:]
assert '.padding(.top, 12)' in outer_modifiers, 'catalog gap is not outside the scrolling region'
assert outer_modifiers.index('.padding(.top, 12)') < outer_modifiers.index('.clipped()'), 'catalog clipping does not preserve the external gap'
assert 'customMapImportPanel\n                        .fixedSize(horizontal: false, vertical: true)\n                        .padding(.top, 12)' in region, 'custom import gap differs from toolbar gap'
print('PASS: fixed catalogue boundaries preserve matching 12 pt gaps')
PYTEST

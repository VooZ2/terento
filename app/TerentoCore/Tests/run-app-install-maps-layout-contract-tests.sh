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
reject_in_file 'Install a third-party map (.img) from this Mac.' "$connect_screen" 'Import panel still repeats the drop zone in a first line'
reject_in_file 'Install a third-party map (.img) file from this Mac.' "$connect_screen" 'old mechanical Import subtitle remains'
require_in_file 'Using local catalog — may be out of date' "$catalog_loader" 'neutral local-catalog fallback label is missing'
reject_in_file 'Offline catalog — may be out of date' "$catalog_loader" 'misleading offline fallback label remains'
require_in_file 'if let notice = mapEngine.catalogSource?.installNotice {' "$connect_screen" 'the catalog-level notice is not driven by the catalog source'
require_in_file 'static let catalogUnavailableNotice = "Couldn'"'"'t load the map list. Maps can'"'"'t be installed right now."' "$catalog_loader" 'the no-catalog notice must use the owner wording'
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

# Owner design pass 2026-11-22: row status on its own line, one style name,
# Import in the header, Storage beside Continue, no "Ready for maps" badge.
python3 - "$connect_screen" "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" <<'PYTEST'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
lifecycle = Path(sys.argv[2]).read_text()

def block(start, end):
    return source.split(start, 1)[1].split(end, 1)[0]

row = block('private struct TerentoMapRow<', 'struct TerentoProgressBar')
assert row.index('Text(detail)') < row.index('Text(status.text)') < row.index('Text(note)'), 'row status is not the third line'
assert '.font(.terento(.meta, weight: .semibold))' in row and '.foregroundStyle(status.color)' in row, 'row status is not meta semibold in its status colour'
selection = block('struct MapSelectionRow: View {', 'private struct MapRowSurface')
detail = selection.split('private var detail: String {', 1)[1].split('private var rowStatus: String? {', 1)[0]
assert 'preflightReason' not in detail and 'shortStatus' not in detail.replace('shortStatus == nil', ''), 'a blocked message is appended to the metadata line'
assert 'status: rowStatus.map { TerentoMapRowStatus(text: $0) }' in selection, 'Install rows do not pass their status line'
assert 'if rowStatus != nil {\n            return "exclamationmark.triangle"' in selection, 'blocked rows do not show the warning icon that matches the status colour'
manage = block('private struct ManageMapRow: View {', 'private struct ManageActionGroup')
assert 'detail: item.manageRowMetadata' in manage and 'status: manageStatus' in manage, 'Manage rows do not split metadata and status'
assert 'title: item.title,' in manage and 'manageTitle' not in source, 'Manage rows still append the style to the title'
assert '[title, manageMetadataLabel]' in lifecycle and 'MapProviderDisplay.title(providerID: id' in lifecycle, 'Manage metadata does not start with the provider or "Provider (Style)" name'

maps = block('private var mapsContent: some View {', 'private var selectedMapProviderLabel')
assert maps.index('Label("Refresh", systemImage: "arrow.clockwise")') < maps.index('SecondaryButton(title: "Import map file", isSelected: customMapImportExpanded)') < maps.index('} mapRegion: {'), 'Import map file is not next to Refresh in the header'
button = block('private struct SecondaryButton: View {', 'private struct ResourceImage')
assert 'selected ? TerentoColors.interactive' in button and 'TerentoGeneratedTokens.Light.textMuted' in button and 'TerentoColors.interactiveHover' in button and '.isSelected' in button, 'Import map file has no selected look or 3:1 border'
footer = maps.split('} footer: {', 1)[1]
assert footer.index('MapSelectionStorageLine(') < footer.index('PrimaryButton(title: "Continue")'), 'Storage is not on the Continue row'
line = block('struct MapSelectionStorageLine: View {', '/// One look for the Install and Manage search field')
assert 'private var lineText: String { summary.footerLine }' in line, 'Storage line copy changed'
footer_line = block('fileprivate var footerLine: String {', 'fileprivate var selectedMapSummary: String {')
assert ') free · 0 maps selected"' in footer_line and ') selected · "' in footer_line and ') free after installation"' in footer_line, 'Storage line is not "1 map · 4.07 MB selected · 14.77 GB free after installation"'
assert 'appendSelectedProvider' not in footer_line, 'the Storage line repeats the provider of the selected rows'
device = block('struct DeviceCard: View {', 'extension DeviceAuthorizationPresentation.Tone')
assert 'if let authorization, authorization.tone != .success {' in device, '"Ready for maps" badge is shown in the ready state'
assert 'static let manageProgressWidth: CGFloat = 236' in source, 'Manage progress is too narrow for "Checking map contents before removal"'
manage_row = block('private struct ManageMapRow: View {', 'private struct ManageActionGroup')
# A Manage row keeps one height for the whole removal (Checking, Removing,
# time left, done): one hidden zero-width height block under actions and progress.
assert 'ZStack(alignment: .trailing) {\n                ManageRowTrailingHeight()' in manage_row, 'the Manage row has no fixed trailing height'
assert 'ManageOperationProgress(operation: operation, timeRemaining: timeRemaining)' in manage_row, 'time left is not inside the fixed progress block'
assert 'note: !availability.updateBlocked ? availability.updateNotice : nil' in manage_row, 'the row note disappears during an operation and the row shrinks'
height = block('private struct ManageRowTrailingHeight: View {', '/// The one warning notice')
assert '.frame(width: 0)' in height and '.hidden()' in height and '.lineLimit(1)' in height, 'the height block takes room or can wrap'
assert height.count('.font(.terento(') == 2 and 'TerentoProgressBar(value: 0)' in height, 'the height block does not mirror the three progress lines'
progress = block('private struct ManageOperationProgress: View {', '    private var accessibilityValue: String {')
assert 'spacing: ManageRowTrailingHeight.lineSpacing' in progress, 'progress and height block use different line spacing'
assert progress.count('.lineLimit(1)') >= 4, 'a progress line can wrap and grow the row'
assert 'TimeRemainingLabel(estimate: timeRemaining)' in progress and 'Text(detailLine)' in progress, 'line 3 must show time left or the detail'
assert 'countStyle: .binary' not in source, 'a size uses binary units; the app shows decimal sizes everywhere'
manage_page = block('private var managedMapsContent: some View {', 'private func managedMapGroups')
# Group header (owner 2026-11-22): name and count on one baseline, chevron
# centred on the name; the count is the number of rows the group shows.
header = block('private struct TerentoMapSectionHeader: View {', 'private struct ')
assert header.index('alignment: .center') < header.index('TerentoDisclosureIndicator(isExpanded: isExpanded)') < header.index('TerentoTitleCountLabel(') < header.index('count: countLabel,'), 'group header name and count are not on one baseline with the chevron centred'
assert 'Text(title)' not in header, 'the group header must use the shared baseline label that TypographyTests measures'
groups = block('private func managedMapGroups', 'title: "Imported maps"')
assert 'count: group.items.count,' in groups and 'ForEach(group.items) { item in' in groups, 'the group count and its rows come from different lists'

assert 'managedMapGroups(lifecycleInventory)' in manage_page and '.clipped()\n                .overlay(alignment: .top) { TerentoListTopDivider() }\n                .padding(.top, 8)' in manage_page, 'Manage rows can scroll visibly under the count line'
# Owner QA 2026-11-22: "Download 467,6 MB · about 2 min" wrapped to two lines,
# grew the row and cut off the last one at the list bottom. The size column
# stays on one line and keeps clear of the overlay scroller.
trailing = selection.split('} trailing: {', 1)[1].split('.frame(maxWidth: .infinity, alignment: .leading)', 1)[0]
assert 'maxWidth: 190' not in trailing and '.multilineTextAlignment(.trailing)' not in trailing, 'the size column can still wrap'
assert trailing.count('.lineLimit(1)\n') == 3 and trailing.count('.fixedSize()\n') == 3, 'size, estimate and Unavailable must each stay on one line'
assert trailing.count('.padding(.trailing, Self.scrollerTrailingInset)') == 2, 'the size column can sit under the overlay scroller'
inset = float(selection.split('static let scrollerTrailingInset: CGFloat = ', 1)[1].split('\n', 1)[0])
assert inset >= 12, 'the scroller inset is narrower than the overlay scroller'
print('PASS: Install maps size column on one line, clear of the overlay scroller')
print('PASS: map row status line, one style name, Import in the header, Storage beside Continue, no ready badge')
PYTEST

#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"

control_group="$(awk '
    /private var catalogToolbar/ { capture = 1 }
    /private var catalogSelectionNotice/ { capture = 0 }
    capture { print }
' "$connect_screen")"

require_group_text() {
    local text="$1"
    local message="$2"
    if [[ "$control_group" != *"$text"* ]]; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_group_text() {
    local text="$1"
    local message="$2"
    if [[ "$control_group" == *"$text"* ]]; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_group_text 'ViewThatFits(in: .horizontal)' 'toolbar does not adapt to available width'
require_group_text 'HStack(spacing: 10)' 'wide toolbar does not preserve compact spacing'
require_group_text 'VStack(alignment: .leading, spacing: 10)' 'narrow toolbar does not move search above menus'
require_group_text 'catalogSearchField' 'responsive toolbar has no search'
require_group_text 'catalogFilterMenus' 'responsive toolbar has no filters'
require_group_text '.frame(minWidth: 240, maxWidth: .infinity)' 'search has no usable minimum or flexible width'
require_group_text '.frame(width: 190)' 'geography menu width changed'
require_group_text '.frame(width: 175)' 'provider menu width changed'
require_group_text '.fixedSize(horizontal: true, vertical: false)' 'filter menus can collapse before toolbar wraps'
require_group_text '.pickerStyle(.menu)' 'native picker changed'
require_group_text '.textFieldStyle(.roundedBorder)' 'native search field changed'
require_group_text '.accessibilityLabel("Map provider")' 'provider lacks distinct accessible label'
require_group_text '.accessibilityLabel("Geographic region")' 'geography lacks distinct accessible label'
require_group_text '.accessibilityLabel("Search countries and regions")' 'search scope is not announced'
require_group_text '.accessibilityLabel("Clear search")' 'search clear lacks its own accessible label'
require_group_text '.focused($mapSearchFieldFocused)' 'search focus binding was removed'
require_group_text 'mapSearchFieldFocused = true' 'clearing search does not retain focus'
reject_group_text '.accessibilityLabel("Search available maps")' 'container still overrides child control labels'
# Only the count/clear row may expand; the input/filter rows remain compact.
require_group_text 'let count = filteredAvailableSelectionItems.count' 'toolbar count is not filtered'
require_group_text 'Button("Clear filters") { clearCatalogFilters() }' 'count row lacks clear filters'
python3 - "$connect_screen" <<'PYTEST'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
toolbar = source.split('private var catalogToolbar: some View {', 1)[1].split('private var catalogSearchField:', 1)[0]
assert toolbar.index('catalogSearchField') < toolbar.index('let count = filteredAvailableSelectionItems.count'), 'result count is not below search/filter controls'
controls = toolbar.split('            HStack {', 1)[0]
assert 'Spacer(' not in controls, 'expanding spacer exists in the adaptive input/filter rows'
assert 'availableMapsExpanded' not in source, 'catalog can still be collapsed'
print('PASS: permanent catalog toolbar places result count below its controls')
PYTEST

print 'PASS: responsive catalog toolbar and distinct accessible native controls'

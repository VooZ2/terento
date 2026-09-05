#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"

control_group="$(awk '
    /if availableMapsExpanded \{/ { capture = 1 }
    /\.accessibilityValue\("\\\(filteredAvailableSelectionItems.count\) results"\)/ { if (capture) { print; exit } }
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

require_group_text 'HStack(spacing: 10)' 'provider and search are not one compact group'
require_group_text '.frame(minWidth: 160, idealWidth: 168, maxWidth: 175, alignment: .leading)' 'provider picker is not compact and readable'
require_group_text '.layoutPriority(1)' 'search is not configured to shrink before the picker'
require_group_text '.frame(minWidth: 190, idealWidth: 290, maxWidth: 300)' 'search width is not wider and responsive'
require_group_text '.pickerStyle(.menu)' 'native provider picker changed'
require_group_text '.textFieldStyle(.roundedBorder)' 'native search field changed'
reject_group_text '.frame(minWidth: 377, idealWidth: 477, maxWidth: 546, alignment: .trailing)' 'independent flexible group frame remains'
reject_group_text 'Spacer(' 'an expanding spacer exists inside the provider/search group'

print 'PASS: Install maps provider/search micro-polish contract'

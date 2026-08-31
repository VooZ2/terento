#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
lifecycle="$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift"
presentation="$project_root/Sources/TerentoPoC/Installation/MapLifecyclePresentation.swift"

require_text() {
    local needle="$1"
    local file="$2"
    local message="$3"
    if ! grep -Fq "$needle" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

reject_text() {
    local needle="$1"
    local file="$2"
    local message="$3"
    if grep -Fq "$needle" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require_text 'title: "Imported maps"' "$connect_screen" "Imported maps section is missing"
require_text 'title: "External maps"' "$connect_screen" "External maps section is missing"
reject_text 'title: "Other maps"' "$connect_screen" "legacy Other maps section remains visible"
require_text 'if !importedMaps.isEmpty' "$connect_screen" "empty Imported maps section is not hidden"
require_text 'if !externalMaps.isEmpty' "$connect_screen" "empty External maps section is not hidden"

require_text 'item.manageMetadataLabel' "$connect_screen" "rows do not use compact metadata"
require_text 'formattedInstalledSize' "$lifecycle" "installed size is missing from row metadata"
require_text '"Contours included"' "$lifecycle" "contours package metadata is missing"
reject_text 'manageDetailLabel' "$connect_screen" "legacy Installed/provider row metadata remains wired"

require_text 'HStack(spacing: 9)' "$connect_screen" "Update and Remove do not use the approved gap"
require_text 'ManageActionButton' "$connect_screen" "separate Remove action is missing"
reject_text 'Export ownership' "$connect_screen" "ownership export remains in production UI"
reject_text 'ManageAdvancedActionTrigger' "$connect_screen" "normal UI still contains an overflow trigger"
reject_text 'Image(systemName: "ellipsis")' "$connect_screen" "normal UI still renders an ellipsis action"
reject_text 'Back up map' "$connect_screen" "normal UI still exposes Backup copy"
require_text 'productionMenuActions' "$presentation" "production action filtering is missing"
require_text '[.update, .remove].filter(availability.allows)' "$presentation" "production rows expose actions beyond Update and Remove"
require_text 'static func productionMenuActions' "$presentation" "production menu policy is missing"
require_text 'return []' "$presentation" "production overflow menu is not empty"
require_text '.frame(width: 152, alignment: .trailing)' "$connect_screen" "row actions do not use a stable right-side column"
require_text 'action == .update ? 72 : 68' "$connect_screen" "Update and Remove widths are not stable"
require_text 'return action == .update ? .white : TerentoColors.graphite' "$connect_screen" "Update does not use a white primary label"
require_text 'return TerentoColors.interactive' "$connect_screen" "Update does not use the Terento primary fill"

require_text '.accessibilityLabel("\(title) \(mapTitle)")' "$connect_screen" "visible actions lack map-specific accessibility labels"

print "PASS: Manage maps simplified beta.8 action contract"

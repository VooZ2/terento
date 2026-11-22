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
require_text 'return action == .update ? .white : TerentoColors.error' "$connect_screen" "Update must use a white label and Remove Error Rust text"
require_text 'return TerentoColors.interactive' "$connect_screen" "Update does not use the Terento primary fill"

require_text '.accessibilityLabel("\(title) \(mapTitle)")' "$connect_screen" "visible actions lack map-specific accessibility labels"
# VoiceOver names the provider ("Remove Lithuania, MapRando"), as the provider filter labels it.
require_text 'mapTitle: providerLabel.isEmpty ? item.title : "\(item.title), \(providerLabel)"' "$connect_screen" "action labels do not name the provider"
require_text 'managedMapRow(item, provider: group.title)' "$connect_screen" "provider rows do not pass their provider"
# A running Remove disables the other actions and Refresh, with a visible disabled colour.
require_text 'return TerentoGeneratedTokens.Light.textDisabled' "$connect_screen" "disabled Manage actions still look active"
require_text '.disabled(mapManagementActionsBusy)
                    .help("Refresh map information")' "$connect_screen" "Manage Refresh is not disabled during an operation"
# After Remove the list stays on screen and refreshes in place; the reading card is only for no list.
require_text 'if inventory == nil, managedInventory != nil, isReadingDeviceMaps { return }' "$connect_screen" "rescan replaces the list with the reading card"
# QA round 3: a rescan keeps the rows' buttons and Refresh in place, disabled, instead of drawing them late.
require_text '? keptManagedAvailability[item.id] ?? lifecycleViewModel.availability(for: item)' "$connect_screen" "kept rows lose their buttons during a rescan"
require_text 'if mapEngine.state == .scanned || (isReadingDeviceMaps && managedInventory != nil) {' "$connect_screen" "Refresh disappears during a rescan of the kept list"
require_text 'removedManagedMapIDs.insert(itemID)' "$connect_screen" "removed row is not hidden from the kept list"
require_text '.transition(.opacity)' "$connect_screen" "removed row does not fade out"
require_text '.animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: lifecycleInventory.allItems.map(\.id))' "$connect_screen" "row fade ignores reduced motion"
require_text '? "This can take a minute."' "$connect_screen" "reading card lacks its one detail line"
reject_text 'Map information will appear here when your device is ready.' "$connect_screen" "reading card repeats itself"
require_text 'TextField("Search installed maps", text: $managedSearchText)' "$connect_screen" "Manage search placeholder differs from its label"

# Garmin-installed images: one read-only row at the bottom, no group header,
# not counted in "N maps" (owner decision 2026-11-22).
reject_text 'title: "Garmin maps"' "$connect_screen" "Garmin maps still has its own group header"
reject_text 'Installed by Garmin. Terento does not change these.' "$connect_screen" "Garmin maps section still shows a caption"
reject_text 'garminMapsExpanded' "$connect_screen" "Garmin maps still collapses like a group"
require_text 'if lifecycleInventory.allItems.isEmpty && visibleGarminSummary == nil {' "$connect_screen" "empty state shows next to the Garmin row"
require_text 'visibleGarminSummary = GarminMapsSummary.visible(managedGarminMaps,' "$connect_screen" "Manage search does not reach the Garmin row"
reject_text 'visibleGarminSummary: visibleGarminSummary' "$connect_screen" "the Manage map count counts the Garmin row"

print "PASS: Manage maps simplified action contract"

python3 - "$connect_screen" <<'PYTEST'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
component = source.split("private struct ManageOperationProgress: View {", 1)[1].split("private struct ", 1)[0]
assert "ProgressView()" not in component, "Manage operations must not use an indeterminate bar"
assert "progress.phaseFraction != nil" in component, "non-byte checking progress must reach the bar"
assert "progress.detail ?? operation.message" in component, "checking needs an action description"
assert 'Text("0%")' not in component, "an unmeasured operation must not show a percentage (same rule as install steps)"
assert "TerentoProgressBar(value: 0" in component, "initial operations must still show an empty determinate bar"
print("PASS: determinate Manage maps progress, description and initial state")

groups = source.split("private func managedMapGroups(", 1)[1].split("private func confirmationItem(", 1)[0]
assert groups.index('title: "External maps"') < groups.index('if let garminSummary = visibleGarminSummary {'), "Garmin maps must follow External maps"
section = groups.split('if let garminSummary = visibleGarminSummary {', 1)[1].split("if lifecycleInventory.allItems.isEmpty", 1)[0]
assert "TerentoMapSection(" not in section, "the Garmin row must not sit under its own group header"
row = source.split("private struct GarminMapsSummaryRow: View {", 1)[1].split("private struct ", 1)[0]
for forbidden in ("Button", "contextMenu", "onRemove", "onUpdate", "ManageAction", "lifecycleViewModel", "onTapGesture", "selection"):
    assert forbidden not in row, f"Garmin rows must not offer {forbidden}"
    assert forbidden not in section, f"the Garmin section must not offer {forbidden}"
assert "GarminMapsSummaryRow(summary: garminSummary)" in section, "the Garmin section must use the read-only summary row"
assert "ForEach" not in section, "the Garmin section must show one summary row, not one row per file"
assert "Text(" not in section, "the Garmin section must not add a caption"
print("PASS: Garmin maps are one read-only row at the bottom, without a group header")
PYTEST

# Unavailability reasons (owner 2026-11-22): provider-wide ones once under the
# provider header, map-specific ones on line 3, one sentence, no retry advice.
map_models="$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift"
python3 - "$connect_screen" "$presentation" "$map_models" <<'PYAVAIL'
import sys
screen, presentation, models = (open(p).read() for p in sys.argv[1:4])
group = models[models.index("var manageGroupNotice: String?"):models.index("var manageRowReason: String?")]
row = models[models.index("var manageRowReason: String?"):models.index("var shortStatus: String?")]
for text in ('"\\(provider) servers are unreachable."', '"\\(provider) is limiting downloads."',
             '"\\(provider) downloads are paused."', 'case "STATUS_UNVERIFIED", "STATUS_STALE": return Self.availabilityCheckFailedNotice'):
    assert text in group, f"provider-wide reason missing: {text}"
assert 'static let availabilityCheckFailedNotice = "Couldn\'t check for updates."' in models, \
    "the failed-check notice must use the owner's wording"
for text in ('"Downloads for this map are turned off."', '"Update Terento to download this map."',
             '"This map is unavailable."'):
    assert text in row, f"map-specific reason missing: {text}"
for banned in ("try again", "connection", "internet"):
    assert banned not in (group + row).lower(), f"Manage reasons must not say '{banned}'"
assert "groupNotice: acquisitionAvailability.manageGroupNotice" in presentation, "the resolver must pass the group notice"
assert "acquisitionAvailability.manageRowReason ?? reason" in presentation, "line 3 must use the short row reason"
assert "acquisitionAvailability.detailedExplanation" not in presentation, "Manage must not use the long explanation"
groups = screen[screen.index("private func managedMapGroups"):screen.index('title: "Imported maps"')]
assert groups.count("providerGroupNotices(group.items)") == 1, "the notices must appear once per provider group"
assert groups.index("providerGroupNotices(group.items)") < groups.index("ForEach(group.items)"), \
    "the notices must sit under the provider header, before the rows"
helper = screen[screen.index("private func providerGroupNotices"):screen.index("private func managedAvailability")]
assert "!notices.contains(notice)" in helper, "each provider-wide reason is said once"
status = screen[screen.index("private var manageStatus: TerentoMapRowStatus?"):]
status = status[:status.index("\n    }\n")]
assert "availability.groupNotice == nil" in status, "rows must not repeat a provider-wide reason"
install_row = screen[screen.index("TerentoMapRow(\n                title: item.title,"):]
install_row = install_row[:install_row.index("contentSpacing: 9")]
assert "note: item.acquisitionAvailability.installRowNote," in install_row, \
    "Install maps rows must keep only the short status for a blocked map"
note = models[models.index("var installRowNote: String?"):models.index("static let availabilityCheckFailedNotice")]
assert "if case .blocked = self { return nil }" in note, "a blocked Install maps row has no second line"
block = models[models.index("var detailedExplanation: String?"):models.index("enum MapAcquisitionPolicyError")]
assert "Check your connection" not in block, "availability texts must not blame the connection"
print("PASS: unavailability reasons: provider-wide once under the header, map-specific on line 3, one sentence")
PYAVAIL

# Update appears only when usable; Remove is Error Rust text with an Error
# Rust tint; the failed-check notice starts where the provider name starts.
python3 - "$connect_screen" "$project_root/Sources/TerentoPoC/Views/WindowPresentation.swift" <<'PYROW'
import sys
screen, layout = (open(p).read() for p in sys.argv[1:3])
group = screen[screen.index("private struct ManageActionGroup"):screen.index("private struct TerentoKeyIndependentButtonStyle")]
assert "updateBlocked" not in group and "isEnabled: false" not in group, "Manage rows must never draw a disabled Update"
assert "updateBlocked: availability.updateBlocked" not in screen, "the row must not pass a blocked Update to the action group"
button = screen[screen.index("private struct ManageActionButton"):screen.index("private struct ManageOperationProgress")]
background = button[button.index("private var backgroundColor"):button.index("private var foregroundColor")]
assert "sky" not in background, "Remove hover and focus must not use Sky"
assert "TerentoColors.error.opacity(0.14)" in background and "TerentoColors.error.opacity(0.08)" in background, \
    "Remove hover and focus must use a light Error Rust tint"
assert "return TerentoGeneratedTokens.Light.textDisabled" in button, "disabled Remove keeps the disabled text token"
assert "static let sectionHeaderTitleInset: CGFloat = sectionHeaderChevronWidth + sectionHeaderItemSpacing" in layout, \
    "the header title inset must come from the header geometry"
groups = screen[screen.index("private func managedMapGroups"):screen.index('title: "Imported maps"')]
notice = groups[groups.index("providerGroupNotices(group.items)"):groups.index("ForEach(group.items)")]
assert "iconColumnWidth: TerentoPageLayout.sectionHeaderChevronWidth" in notice \
    and "spacing: TerentoPageLayout.sectionHeaderItemSpacing" in notice and ".padding(.horizontal" not in notice, \
    "the group notice text must start at the provider name (icon in the chevron column)"
print("PASS: usable-only Update, Error Rust Remove, notice aligned with the provider name")
PYROW

# Catalog-level notice (owner 2026-11-22): one shared warning component on both
# pages; the catalog's shared reason is said once, never on rows or groups.
python3 - "$connect_screen" "$presentation" "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" <<'PYCAT'
import sys
screen, presentation, loader = (open(p).read() for p in sys.argv[1:4])
comp = screen[screen.index("struct TerentoWarningNotice: View"):screen.index("private struct TerentoListTopDivider")]
assert ".foregroundStyle(TerentoColors.warning)" in comp and "TerentoColors.error" not in comp, \
    "the notice is a warning in Stone Dark, not Error Rust"
assert 'Image(systemName: "exclamationmark.triangle")' in comp, "the notice carries the warning icon"
assert ".font(.terento(.meta, weight: .semibold))" in comp, "the notice text is semibold"
assert ".accessibilityElement(children: .ignore)" in comp and ".accessibilityLabel(text)" in comp, \
    "VoiceOver reads the notice once"
assert screen.count("TerentoWarningNotice(") == 3, "Install page, Manage page and provider groups share one component"
assert "Using local catalog" not in screen and "wifi.slash" not in screen, "the grey fallback line is gone"
manage = screen[screen.index("private var managedMapsContent: some View"):screen.index("private func managedMapGroups")]
assert manage.index("managedCatalogToolbar") < manage.index("managePageNotice(lifecycleInventory)") < manage.index("ScrollView {"), \
    "the Manage notice sits once under the count line, above the list"
assert ".overlay(alignment: .top) { TerentoListTopDivider() }" in manage, "the Manage count line has the list divider"
region = screen[screen.index("private var catalogMapRegion: some View"):]
region = region[:region.index(".clipped()") + 10]
assert ".overlay(alignment: .top) { TerentoListTopDivider() }" in region, "Install maps uses the same list divider"
assert "return availability.removingCatalogWideReason(mapEngine.catalogSource?.sharedBlockReason)" in screen, \
    "Manage rows and groups drop the catalog-wide reason"
assert "guard let sharedBlockReason, blockReason == sharedBlockReason else { return self }" in presentation
row = screen[screen.index("private var rowStatus: String? {"):]
row = row[:row.index("guard item.package.sourceKind != .custom")]
assert row.index("if hidesCatalogWideReason") < row.index("shortStatus"), \
    "Install rows drop the catalog-wide reason before the short status"
assert 'case .bundledFallback, .cachedRemote: return "STATUS_UNVERIFIED"' in loader
assert 'case .appUpdateRequired: return "APP_UPDATE_REQUIRED"' in loader
assert 'static let environmentKey = "TERENTO_USE_BUNDLED_MAP_CATALOG"' in loader and "environment[environmentKey] == \"1\"" in loader, \
    "a local test build can show the fallback without editing Info.plist"
print("PASS: catalog-level reason said once per page with the shared warning notice")
PYCAT

# The bundled-catalog switch works in Debug and "-local" builds, never in App
# Store or TestFlight builds (run-time check of the release label).
python3 - "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" <<'PYSWITCH'
import sys
loader = open(sys.argv[1]).read()
switch = loader[loader.index("enum MapCatalogTestSwitch {"):loader.index("/// When the catalog itself is the cause")]
assert 'hasSuffix("-local")' in switch and "return isLocalTestLabel || (isDebug && !isAppStore)" in switch, \
    "only a -local label (any configuration) or a DMG Debug build may use the switch"
uses = switch[switch.index("static var usesBundledCatalog: Bool {"):]
assert "return false" not in uses, "the switch must be decided at run time, not compiled out of App Store -local builds"
assert "let isAppStore = true" in uses and 'forInfoDictionaryKey: "TerentoReleaseLabel"' in uses
endpoint = loader[loader.index("static let defaultEndpoint: URL? = {"):]
endpoint = endpoint[:endpoint.index("}()")]
assert "if MapCatalogTestSwitch.usesBundledCatalog {\n            return nil" in endpoint
assert "#if DEBUG" not in endpoint, "the switch must not be Debug-only (the -local build is Release)"
print("PASS: bundled-catalog switch only in -local and DMG Debug builds")
PYSWITCH


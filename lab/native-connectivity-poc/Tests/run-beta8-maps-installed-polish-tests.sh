#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
finish="$(sed -n '/private var finishContent/,/private func storageFillRatio/p' "$screen")"

require_finish() {
  grep -Fq "$1" <<< "$finish" || { print -u2 "FAIL: $2"; exit 1; }
}

require_source() {
  grep -Fq "$1" "$screen" || { print -u2 "FAIL: $2"; exit 1; }
}

reject_source() {
  if grep -Fq "$1" "$screen"; then
    print -u2 "FAIL: $2"
    exit 1
  fi
}

require_finish 'title: "Maps installed"' 'Done title changed'
require_finish 'installedCount == 1' 'Done copy is not driven by the successful result count'
require_finish 'Your selected map is ready on your Garmin.' 'one-map subtitle is missing'
require_finish 'Your selected maps are ready on your Garmin.' 'multi-map subtitle is missing'
require_finish 'InstalledMapsSectionHeader(count: installedCount)' 'installed-map count header is missing'
require_source 'Text(count == 1 ? "Installed map" : "Installed maps")' 'installed section title does not pluralize'
require_source '"\(count) \(count == 1 ? "map" : "maps")"' 'installed count label does not pluralize'
require_finish 'InstallationMapsList(' 'Done does not reuse the established map row/list system'
require_source 'private static let visibleRowCapacity = 3' 'shared list no longer shows up to three complete rows'
require_source '.scrollIndicators(items.count > Self.visibleRowCapacity ? .automatic : .hidden)' '4+ row scroll behavior is missing'
require_finish 'checkmark.circle.fill' 'success reassurance has no semantic checkmark'
require_finish '.foregroundStyle(TerentoColors.lichen)' 'success icon does not use the Lichen treatment'
require_finish '.accessibilityHidden(true)' 'decorative success icon is announced redundantly'
require_finish 'Your map is ready and verified. You can safely disconnect your Garmin.' 'one-map reassurance is missing'
require_finish 'Your maps are ready and verified. You can safely disconnect your Garmin.' 'multi-map reassurance is missing'
reject_source 'Compatibility report sent.' 'telemetry status remains visible on Done'
reject_source 'Compatibility reports sent.' 'plural telemetry status remains visible on Done'
require_finish 'PrimaryButton(title: "Back to device")' 'Back to device is not the primary trailing action'
require_finish 'returnToDeviceAfterSuccess()' 'Back to device does not use the safe navigation path'
require_source 'mapEngine.installationBatchResults.count == plan.installItems.count' 'Done can render requested maps without complete successful results'
require_source '.filter { $0.1.isSuccess }' 'Done list is not filtered by actual successful results'
require_source 'return plan.selectedItems.filter' 'provider/custom map rows are not preserved from the selected item model'
require_source 'refreshMapInventory()' 'Back to device does not refresh device state'

print 'PASS: Maps installed final UX polish contract'

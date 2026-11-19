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

require_finish 'title: installedCount == 1 ? "Map installed" : "Maps installed"' 'Done title is not singular for one map'
require_finish 'installedCount == 1' 'Done copy is not driven by the successful result count'
require_finish 'Installation complete.' 'concise completion subtitle is missing'
require_finish 'The main map is ready. An optional contour component needs attention.' 'partial-success warning was lost'
require_finish 'InstalledMapsSectionHeader(count: installedCount)' 'installed-map count header is missing'
require_source 'Text(count == 1 ? "Installed map" : "Installed maps")' 'installed section title does not pluralize'
require_source 'if count > 1 {' 'one installed map still shows a "1 map" count'
require_finish 'InstallationMapsList(' 'Done does not reuse the established map row/list system'
require_source 'private static let visibleRowCapacity = 3' 'shared list no longer shows up to three complete rows'
require_source '.scrollIndicators(items.count > Self.visibleRowCapacity ? .automatic : .hidden)' '4+ row scroll behavior is missing'
require_finish 'InstallationResultCallout(' 'Done has no result callout'
callout="$(sed -n '/private struct InstallationResultCallout/,/private struct InstalledMapsSectionHeader/p' "$screen")"
require_callout() {
  grep -Fq "$1" <<< "$callout" || { print -u2 "FAIL: $2"; exit 1; }
}
require_callout 'checkmark.circle.fill' 'success result has no semantic checkmark'
require_callout '.foregroundStyle(isPartial ? TerentoColors.error : TerentoColors.lichenDark)' 'success/partial-result icons do not use accessible semantic colors'
require_callout '.accessibilityHidden(true)' 'decorative success icon is announced redundantly'
require_callout 'is on your Garmin' 'one-map result is missing'
require_callout 'maps are on your Garmin' 'multi-map result is missing'
require_callout '"On your Garmin"' 'numbered next steps have no title'
require_callout '"Disconnect it from the Mac."' 'disconnect step is missing'
require_callout '"Open map settings and turn the new map on."' 'one-map turn-on step is missing'
require_callout '"Open map settings and turn the new maps on."' 'multi-map turn-on step is missing'
require_callout '"Not in the list? Restart the device."' 'restart step is missing'
require_callout 'Radius.card' 'result callout does not use the card radius'
reject_source 'Image(systemName: "switch.2")' 'Done still uses a settings toggle icon for a next step'
require_source 'Your map is installed and checked. Next: disconnect your Garmin, open its map settings and turn the new map on.' 'sharing dialog lacks the turn-on step'
reject_source 'ready and verified' 'Done still says verified, which reads as a promise that the device shows the map'
reject_source 'Compatibility report sent.' 'telemetry status remains visible on Done'
reject_source 'Compatibility reports sent.' 'plural telemetry status remains visible on Done'
require_finish 'PrimaryButton(title: "Back to device")' 'Back to device is not the primary trailing action'
require_finish 'returnToDeviceAfterSuccess()' 'Back to device does not use the safe navigation path'
require_source 'mapEngine.installationBatchResults.count == plan.installItems.count' 'Done can render requested maps without complete successful results'
require_source '.filter { $0.1.isSuccess }' 'Done list is not filtered by actual successful results'
require_source 'return plan.selectedItems.filter' 'provider/custom map rows are not preserved from the selected item model'
require_source 'refreshMapInventory()' 'Back to device does not refresh device state'

print 'PASS: Maps installed final UX polish contract'

#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage45-map-selection-tests.XXXXXX")"
binary_path="$build_dir/stage45-map-selection-tests"

swiftc \
    -module-name TerentoStage45MapSelectionTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/MapCapability.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapConflictResolver.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationPreflight.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPlanner.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPresentation.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage45MapSelectionTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eq 'LibMTPBridge|MTPTransport|SendObject|DeleteObject|MoveObject|Rename' \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPlanner.swift"; then
    print -u2 "FAIL: map selection planner contains transport or write-operation logic"
    exit 1
fi

if grep -Fq 'Text("(plan.selectedItems.count)' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift" \
    || grep -Fq 'Text("(formatBytes(' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"; then
    print -u2 "FAIL: raw Swift expressions are present in map-selection UI text"
    exit 1
fi

if grep -Eq 'Text\("Select([^e]|$)|title: "Select' \
    "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"; then
    print -u2 "FAIL: Select pill/action remains in map-selection UI"
    exit 1
fi

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
if ! grep -Fq 'Text("Ready to install")' "$connect_screen"; then
    print -u2 "FAIL: Review screen does not use the approved title"
    exit 1
fi

if grep -Fq 'plus.circle' "$connect_screen"; then
    print -u2 "FAIL: Review rows still use a plus icon"
    exit 1
fi

if grep -Fq 'This selection is ready. Multi-region installation will be enabled in a later step.' "$connect_screen"; then
    print -u2 "FAIL: development-only multi-region copy remains in Review"
    exit 1
fi

if [[ "$(grep -Fc 'MapSelectionStorageSummary(' "$connect_screen")" -lt 2 ]]; then
    print -u2 "FAIL: Choose and Review do not share the Storage component"
    exit 1
fi

if ! grep -Fq 'Terento will install these maps to your Garmin.' "$connect_screen" \
    || ! grep -Fq 'Existing Garmin maps will not be changed.' "$connect_screen" \
    || grep -Fq 'Terento will install the selected maps to your Garmin.' "$connect_screen" \
    || grep -Fq 'Existing Garmin system maps are left unchanged.' "$connect_screen"; then
    print -u2 "FAIL: Review safety disclosure is missing"
    exit 1
fi

if ! grep -Fq 'Text("Help improve Terento")' "$connect_screen" \
    || ! grep -Fq 'Share anonymous installation data to help us understand device compatibility and improve support for other Garmin users.' "$connect_screen" \
    || grep -Fq 'Help improve Terento for other watch owners' "$connect_screen" \
    || grep -Fq 'No Garmin Unit ID or serial number is collected.' "$connect_screen"; then
    print -u2 "FAIL: Review compatibility opt-in copy is too long or outdated"
    exit 1
fi

if grep -Fq 'shareCompatibilityEvidence' "$connect_screen" \
    || ! grep -Fq 'evidenceController.compatibilitySharingEnabled' "$connect_screen" \
    || ! grep -Fq 'evidenceController.commitCurrentSharingChoice()' "$connect_screen"; then
    print -u2 "FAIL: compatibility sharing does not use the shared persisted preference"
    exit 1
fi

if ! grep -Fq 'else if plan.storagePlan.status == .blockedInsufficientSpace' "$connect_screen" \
    || grep -Fq 'if let reason = installAvailability.userReason' "$connect_screen"; then
    print -u2 "FAIL: Review warning is not limited to insufficient storage"
    exit 1
fi

if grep -Eiq 'community maps?' "$connect_screen" \
    || ! grep -Fq 'title: "Available Freizeitkarte maps"' "$connect_screen"; then
    print -u2 "FAIL: primary map flow exposes origin terminology or hides the current source"
    exit 1
fi

if grep -Fq 'installedMapsExpanded' "$connect_screen" \
    || grep -Fq 'title: "Installed maps"' "$connect_screen" \
    || grep -Fq 'MapSelectionPresentationModel.supportedInstalled' "$connect_screen"; then
    print -u2 "FAIL: Install maps still owns a separate Installed maps section"
    exit 1
fi

if ! grep -Fq 'No new Freizeitkarte maps are available to install.' "$connect_screen" \
    || ! grep -Fq 'return "Already installed"' "$connect_screen" \
    || ! grep -Fq 'return item.comparison.installedMap == nil' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPresentation.swift"; then
    printf '%s\n' "FAIL: Install empty state or installed-search presentation is missing" >&2
    exit 1
fi

if ! grep -Fq 'case .update:' "$connect_screen" \
    || ! grep -Fq 'return "Update"' "$connect_screen"; then
    print -u2 "FAIL: Manage-only update action is missing"
    exit 1
fi

if ! grep -Fq 'InstallReviewAvailabilityResolver' "$connect_screen" \
    || ! grep -Fq 'frame(height: selectedMapListHeight)' "$connect_screen" \
    || ! grep -Fq 'padding(.top, 10)' "$connect_screen"; then
    print -u2 "FAIL: Review CTA or content-aware selected-map sizing is missing"
    exit 1
fi

if grep -Fq 'This map cannot be installed safely from this flow yet.' "$connect_screen" \
    || ! grep -Fq 'This map cannot be installed safely on this Garmin yet.' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapSelectionPresentation.swift"; then
    print -u2 "FAIL: Review blocker copy is still generic or missing the real unsupported-device reason"
    exit 1
fi

if ! grep -Fq 'mapEngine.beginInstallation(plan: plan)' "$connect_screen" \
    || ! grep -Fq 'func beginInstallation(plan: InstallationPlan)' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift" \
    || ! grep -Fq 'func installSelectedMaps()' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift"; then
    print -u2 "FAIL: Review CTA is not wired to the complete install lifecycle"
    exit 1
fi

if ! grep -Fq 'private func activeInstallationContent' "$connect_screen" \
    || ! grep -Fq 'Text("Installing maps")' "$connect_screen" \
    || ! grep -Fq 'Keep your Garmin connected until installation is complete.' "$connect_screen"; then
    print -u2 "FAIL: active installation state is not separated from Review"
    exit 1
fi

if ! grep -Fq 'ScrollView {' "$connect_screen" \
    || ! grep -Fq 'navigationLocked: installationOperationIsActive' "$connect_screen" \
    || ! grep -Fq 'isInstalling: installationOperationIsActive' "$connect_screen"; then
    print -u2 "FAIL: active installation lacks responsive scrolling or navigation/status locking"
    exit 1
fi

if grep -Fq 'LocalInstallStepperLayout' "$connect_screen" \
    || grep -Fq 'LocalInstallProgress' "$connect_screen" \
    || grep -Fq 'WorkflowProgress' "$connect_screen" \
    || ! grep -Fq 'title: "Maps installed"' "$connect_screen"; then
    print -u2 "FAIL: install stepper remains or successful Done state is missing"
    exit 1
fi

if ! grep -Fq 'TerentoInstallMapsVerticalLayout' "$connect_screen" \
    || ! grep -Fq 'mapRegion:' "$connect_screen" \
    || ! grep -Fq 'storageRegion:' "$connect_screen" \
    || ! grep -Fq 'TerentoBoundedMapSelectionRegion' "$connect_screen" \
    || ! grep -Fq 'storageFooterSpacing' "$connect_screen" \
    || ! grep -Fq 'height: listHeight' "$connect_screen" \
    || grep -Fq 'TerentoFlexibleScrollRegion' "$connect_screen" \
    || grep -Fq 'No supported maps installed' "$connect_screen" \
    || grep -Fq 'Select a map to continue.' "$connect_screen" \
    || ! grep -Fq 'Available maps list' "$connect_screen" \
    || ! grep -Fq '0 maps selected' "$connect_screen" \
    || ! grep -Fq 'maxHeight: .infinity, alignment: .topLeading' "$connect_screen"; then
    print -u2 "FAIL: Choose screen is not using the bounded three-region map layout"
    exit 1
fi

if ! grep -Fq 'evidencePrimaryFailureMapIndex = activePackageIndex' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift" \
    || ! grep -Fq 'evidencePrimaryFailureMapIndex = activeMapIndex.value' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift" \
    || ! grep -Fq 'index == primaryFailureIndex ? mapEngine.installationResult : nil' \
        "$connect_screen"; then
    print -u2 "FAIL: multi-map diagnostics do not preserve the actual failed map index"
    exit 1
fi

if ! grep -Fq '&& item.acquisitionAvailability == .available' "$connect_screen"; then
    print -u2 "FAIL: withheld map rows may still render a selectable-looking status circle"
    exit 1
fi

printf '%s\n' "PASS: withheld map rows render no checkbox-like status circle"

printf '%s\n' "PASS: map selection planner is transport-independent and read-only"

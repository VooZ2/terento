#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage7-navigation-tests.XXXXXX")"
binary_path="$build_dir/stage7-navigation-tests"

swiftc \
    -module-name TerentoStage7NavigationTests \
    "$project_root/Sources/TerentoPoC/Views/NavigationPresentation.swift" \
    "$project_root/Sources/TerentoPoC/Views/WindowPresentation.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage7NavigationTests.swift" \
    -o "$binary_path"

"$binary_path"

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
sidebar="$project_root/Sources/TerentoPoC/Views/NavigationPresentation.swift"

if ! grep -Fq 'case installMaps = "Install maps"' "$sidebar" \
    || ! grep -Fq 'case manageMaps = "Manage maps"' "$sidebar" \
    || ! grep -Fq 'case about = "About"' "$sidebar" \
    || ! grep -Fq 'TerentoSection.installMaps' "$connect_screen" \
    || ! grep -Fq 'TerentoSection.manageMaps' "$connect_screen" \
    || ! grep -Fq 'title: "About"' "$connect_screen"; then
    print -u2 "FAIL: sidebar does not expose the expected product destinations"
    exit 1
fi

if grep -Fq 'Settings' "$connect_screen" "$sidebar" \
    || grep -Fq 'case settings' "$connect_screen" "$sidebar"; then
    print -u2 "FAIL: Settings navigation remains in the primary app"
    exit 1
fi

if grep -Eq 'case maps|\.maps\b|showingManagedMaps' "$connect_screen" "$sidebar"; then
    print -u2 "FAIL: old standalone Maps navigation or managed-map toggle remains"
    exit 1
fi

if ! grep -Fq 'return "arrow.down.circle"' "$connect_screen" \
    || ! grep -Fq 'return "square.stack.3d.up"' "$connect_screen"; then
    print -u2 "FAIL: Install maps and Manage maps do not use distinct sidebar icons"
    exit 1
fi

if ! grep -Fq 'navigationLocked: installationOperationIsActive' "$connect_screen" \
    || ! grep -Fq 'isLifecycleBusy: mapManagementActionsBusy' "$connect_screen" \
    || ! grep -Fq '.onChange(of: mapEngine.installationPhase)' "$connect_screen" \
    || ! grep -Fq 'InstallationFlowPresentation.isActive' "$connect_screen" \
    || ! grep -Fq 'navigate(to: .installMaps)' "$connect_screen" \
    || ! grep -Fq 'navigate(to: .manageMaps)' "$connect_screen"; then
    print -u2 "FAIL: routing or active-operation navigation safety is incomplete"
    exit 1
fi

if ! grep -Fq 'defaultWidth' "$project_root/Sources/TerentoPoC/TerentoPoCApp.swift" \
    || ! grep -Fq 'defaultHeight' "$project_root/Sources/TerentoPoC/TerentoPoCApp.swift" \
    || ! grep -Fq 'minimumWidth' "$connect_screen" \
    || ! grep -Fq 'minimumHeight' "$connect_screen"; then
    print -u2 "FAIL: default or minimum window sizing is not wired to the app"
    exit 1
fi

if ! grep -Fq 'mapEngine.beginInstallation(plan: plan)' "$connect_screen" \
    || ! grep -Fq 'shouldContinueAfterPreflight' \
        "$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift" \
    || grep -Fq 'else if mapEngine.installationPhase == .awaitingConfirmation' "$connect_screen"; then
    print -u2 "FAIL: Review does not own the single authorization or active state still offers a second CTA"
    exit 1
fi

if ! grep -Fq 'let shouldRefreshMapInventory = section == .manageMaps' "$connect_screen" \
    || ! grep -Fq 'refreshMapInventory()' "$connect_screen"; then
    print -u2 "FAIL: map navigation does not refresh the device-backed inventory"
    exit 1
fi

if ! grep -Fq 'ProgressView()' "$connect_screen" \
    || ! grep -Fq 'Eject is unavailable while installing maps.' "$connect_screen" \
    || ! grep -Fq 'installationPhaseProgressIsMeasured' "$connect_screen"; then
    print -u2 "FAIL: active progress/eject presentation is incomplete"
    exit 1
fi

if ! grep -Fq 'ManageActionButton' "$connect_screen" \
    || grep -Fq 'Image(systemName: "ellipsis")' "$connect_screen" \
    || ! grep -Fq 'ManageActionGroup' "$connect_screen" \
    || ! grep -Fq '.buttonStyle(.borderless)' "$connect_screen" \
    || ! grep -Fq '@FocusState' "$connect_screen" \
    || ! grep -Fq '.onHover' "$connect_screen" \
    || ! grep -Fq 'frame(minWidth: 44, minHeight: 30)' "$connect_screen" \
    || ! grep -Fq 'ManageOperationProgress' "$connect_screen" \
    || ! grep -Fq 'ProgressView(value: progress.fractionCompleted)' \
        "$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"; then
    print -u2 "FAIL: Manage map actions or real-progress presentation is incomplete"
    exit 1
fi

if ! grep -Fq 'TerentoPageShell' "$connect_screen" \
    || ! grep -Fq 'TerentoPageFooter' "$connect_screen" \
    || ! grep -Fq 'TerentoFooterPageShell' "$connect_screen" \
    || ! grep -Fq 'TerentoInstallFooterPageShell' "$connect_screen" \
    || ! grep -Fq 'TerentoPageHeader' "$connect_screen" \
    || ! grep -Fq 'TerentoMapSection' "$connect_screen" \
    || ! grep -Fq 'TerentoMapSectionHeader' "$connect_screen" \
    || grep -Fq 'TerentoContentGrid' "$connect_screen" \
    || grep -Fq 'frame(maxWidth: 980)' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.maxWidth' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.horizontalPadding' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.titleSubtitleSpacing' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.firstSectionTopPadding' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.sectionSpacing' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.footerMinHeight' "$connect_screen" \
    || ! grep -Fq 'TerentoPageLayout.footerBottomPadding' "$connect_screen"; then
    print -u2 "FAIL: primary screens do not use one shared page-grid shell"
    exit 1
fi

if grep -Fq 'LocalInstallProgress' "$connect_screen" \
    || grep -Fq 'LocalInstallStepperLayout' "$connect_screen" \
    || grep -Fq 'WorkflowProgress' "$connect_screen" \
    || ! grep -Fq 'topPadding: TerentoPageLayout.primaryTopPadding' "$connect_screen"; then
    print -u2 "FAIL: Install Maps still has a stepper or a special title offset"
    exit 1
fi

if ! awk '
    /private var managedMapsContent/ { capture = 1 }
    /private func connectedDeviceContent/ { capture = 0 }
    capture { print }
' "$connect_screen" | grep -F 'TerentoFooterPageShell' >/dev/null \
    || ! awk '
        /private var mapsContent/ { capture = 1 }
        /private var unifiedMapInventory/ { capture = 0 }
        capture { print }
    ' "$connect_screen" | grep -F 'TerentoInstallFooterPageShell' >/dev/null \
    || ! awk '
        /private func reviewInstallContent/ { capture = 1 }
        /private func activeInstallationContent/ { capture = 0 }
        capture { print }
    ' "$connect_screen" | grep -F 'TerentoPageFooter' >/dev/null \
    || ! awk '
        /private var finishContent/ { capture = 1 }
        /private func storageFillRatio/ { capture = 0 }
        capture { print }
' "$connect_screen" | grep -F 'TerentoPageFooter' >/dev/null; then
    print -u2 "FAIL: footer shell migration is incomplete across Manage, Choose, Review, or Done"
    exit 1
fi

finish_content="$(awk '
    /private var finishContent/ { capture = 1 }
    /private func storageFillRatio/ { capture = 0 }
    capture { print }
' "$connect_screen")"
if [[ "$finish_content" != *'TerentoPageHeader'* \
    || "$finish_content" != *'MapSelectionRow'* \
    || "$finish_content" != *'Back to device'* \
    || "$finish_content" != *'Your map is ready and verified'* \
    || "$finish_content" == *'Installation was verified successfully'* \
    || "$finish_content" == *'.padding(.top, 14)'* ]]; then
    print -u2 "FAIL: completion screen is not using the shared header, map row, and calm completion copy"
    exit 1
fi

if grep -Fq 'title: "Freizeitkarte maps"' "$connect_screen" \
    || grep -Fq 'title: "Managed maps"' "$connect_screen" \
    || ! grep -Fq 'title: group.title' "$connect_screen" \
    || ! grep -Fq 'title: "Available maps"' "$connect_screen" \
    || grep -Eiq 'community maps?' "$connect_screen" \
    || ! grep -Fq 'title: "Other maps"' "$connect_screen" \
    || grep -Fq 'DisclosureGroup(isExpanded: $freizeitkarteMapsExpanded)' "$connect_screen"; then
    print -u2 "FAIL: Manage Maps section taxonomy or shared section presentation is incomplete"
    exit 1
fi

if ! grep -Fq 'item.manageDetailLabel' "$connect_screen" \
    || grep -Fq 'availability.reason ?? item.noteLabel' "$connect_screen" \
    || ! grep -Fq 'Incomplete installation' \
        "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift"; then
    print -u2 "FAIL: Manage rows still use repetitive diagnostic copy"
    exit 1
fi

if ! grep -Fq 'alignment: .center' "$connect_screen" \
    || ! grep -Fq 'tracking(-0.66)' "$connect_screen" \
    || ! grep -Fq 'Terento.windowGeometry.v2' \
        "$project_root/Sources/TerentoPoC/TerentoPoCApp.swift"; then
    print -u2 "FAIL: centered brand lockup or window geometry migration is incomplete"
    exit 1
fi

brand_lockup="$(awk '
    /private struct TerentoBrandLockup/ { capture = 1; depth = 0 }
    capture {
        print
        line = $0
        opens = gsub(/\{/, "", line)
        closes = gsub(/\}/, "", line)
        depth += opens - closes
        if (depth == 0) exit
    }
' "$connect_screen")"
if [[ "$brand_lockup" != *'Text("Terento")'* \
    || "$brand_lockup" != *'.foregroundStyle(TerentoColors.graphite)'* \
    || "$brand_lockup" == *'.foregroundStyle(TerentoColors.sky)'* ]]; then
    print -u2 "FAIL: sidebar wordmark is not the approved Graphite brand color"
    exit 1
fi

print "PASS: Stage 7 sidebar navigation static checks"

#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/ConnectScreen.swift"
phase_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Installation/MapLifecyclePresentation.swift"
lifecycle_view_model="$repo_root/app/TerentoCore/Sources/TerentoPoC/Installation/MapLifecycleViewModel.swift"

assert_contains() {
    local needle="$1"
    local file="$2"
    rg -Fq "$needle" "$file" || {
        print -u2 "FAIL: missing '$needle' in $file"
        exit 1
    }
}

progress_block="$(awk '
    /private struct ManageOperationProgress/ { capture = 1 }
    /private struct TerentoMapRow/ { capture = 0 }
    capture { print }
' "$connect_screen")"

if [[ "$progress_block" != *'TerentoProgressBar(value: progress.fractionCompleted'* \
   || "$progress_block" == *'ProgressView('* \
   || "$progress_block" != *'TerentoProgressBar(value: 0'* \
   || "$progress_block" == *'Text("0%")'* ]]; then
    print -u2 "FAIL: Manage progress must use the shared determinate TerentoProgressBar and show % only when measured"
    exit 1
fi

# One progress bar component for activity and storage: 6 pt, capsule, border track.
bar_block="$(awk '
    /^struct TerentoProgressBar: View/ { capture = 1 }
    /^struct StorageCard: View/ { capture = 0 }
    capture { print }
' "$connect_screen")"
for needle in '.frame(height: InstallationTimelineLayout.progressBarHeight)' 'Capsule()' \
    '.fill(TerentoColors.border)' 'var fill: Color = TerentoColors.interactive' \
    '.fill(TerentoColors.sky)' '.accessibilityValue(' '.accessibilityLabel(label)'; do
    [[ "$bar_block" == *"$needle"* ]] || { print -u2 "FAIL: TerentoProgressBar lost $needle"; exit 1; }
done
if rg -q 'ProgressView\(value:|progressViewStyle\(\.linear\)' "$repo_root/app/TerentoCore/Sources"; then
    print -u2 "FAIL: a native linear ProgressView is back; use TerentoProgressBar"
    exit 1
fi
assert_contains 'TerentoProgressBar(value: progress, label: title)' "$connect_screen"
# QA round 3: no "0%"; the % appears only for a measured value above zero, in Manage and install steps.
[[ "$progress_block" == *'if let measuredFraction {'* ]] || { print -u2 "FAIL: Manage % is not limited to a measured value"; exit 1; }
assert_contains 'let measured = TerentoProgressBar.measured(progress) {' "$connect_screen"
assert_contains 'guard let value, value.isFinite, value > 0 else { return nil }' "$connect_screen"
# Finishing is one indeterminate bar for the whole step, so it never jumps backwards.
finishing_block="$(awk '/title: "Finishing",/ { capture = 1 } capture { print } /isLast: true/ { capture = 0 }' "$connect_screen")"
[[ "$finishing_block" == *'progress: nil,'* && "$finishing_block" != *'installationPhaseProgress'* ]] \
    || { print -u2 "FAIL: Finishing must use one indeterminate bar"; exit 1; }
assert_contains '.onChange(of: value == nil) { _ in startSweepIfNeeded() }' "$connect_screen"
# Install start: the step list shows Downloading as current while the package is resolved.
assert_contains 'let current = InstallationDownloadStepPresentation.displayedPhase(mapEngine.installationPhase,' "$connect_screen"
assert_contains 'TerentoProgressBar(value: normalizedFillRatio, fill: TerentoColors.lichen' "$connect_screen"
assert_contains 'selectedValue: projection.fraction(for: projection.selectedMapBytes)' "$connect_screen"

assert_contains 'static let progressBarHeight: CGFloat = 6' "$connect_screen"
assert_contains 'static let manageProgressWidth: CGFloat = 236' "$connect_screen"
assert_contains 'Text(operation.phase.userLabel)' "$connect_screen"
assert_contains 'return "Removing"' "$phase_source"
assert_contains 'return "Checking"' "$phase_source"
# A confirmed removal leaves a short "<Map> removed." line for a few seconds.
assert_contains 'showRemovalNotice(context.item.title)' "$lifecycle_view_model"
assert_contains 'if let notice = lifecycleViewModel.removalNotice {' "$connect_screen"
assert_contains '.onChange(of: lifecycleViewModel.removalNotice) { notice in' "$connect_screen"
assert_contains '.announcement: notice,' "$connect_screen"

print "PASS: Manage map removal reuses the installation progress pattern"

#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/ConnectScreen.swift"
phase_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Installation/MapLifecyclePresentation.swift"

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

if [[ "$progress_block" != *'ProgressView(value: progress.fractionCompleted)'* \
   || "$progress_block" != *'ProgressView()'* \
   || "$progress_block" != *'.progressViewStyle(.linear)'* \
   || "$progress_block" != *'.tint(TerentoColors.interactive)'* \
   || "$progress_block" != *'.frame(height: InstallationTimelineLayout.progressBarHeight)'* ]]; then
    print -u2 "FAIL: Manage progress does not reuse the installation progress pattern"
    exit 1
fi

assert_contains 'static let progressBarHeight: CGFloat = 6' "$connect_screen"
assert_contains 'static let manageProgressWidth: CGFloat = 220' "$connect_screen"
assert_contains 'Text(operation.phase.userLabel)' "$connect_screen"
assert_contains 'return "Removing"' "$phase_source"

print "PASS: Manage map removal reuses the installation progress pattern"

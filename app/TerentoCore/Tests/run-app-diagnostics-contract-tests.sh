#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h:h:h}"
app_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/TerentoPoCApp.swift"
diagnostics_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/DiagnosticsView.swift"
about_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/AboutTerentoView.swift"
connect_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/ConnectScreen.swift"

for text in \
    'struct DiagnosticsView: View' \
    'Text("Diagnostics")' \
    'Text("Privacy-minimized diagnostics help improve the Terento app and its services.")' \
    'title: "Send compatibility diagnostics"' \
    'title: "Send map usage diagnostics"' \
    'Text("Both are on by default. Turning one off also deletes what is waiting to be sent.")' \
    'Text(compatibilitySharingBinding.wrappedValue || mapStatisticsSharingBinding.wrappedValue' \
    '? "Turning one off also deletes what is waiting to be sent."' \
    ': "Both are off until you turn them on. Turning one off also deletes what is waiting to be sent.")' \
    'DisclosureGroup("What is sent")' \
    'diagnosticsSection(title: "Problem with a map?")' \
    'Text("If an install, update or removal failed, send us the saved report.")' \
    'Button("Report on GitHub (public)", action: reportOnGitHub)' \
    'if pendingCount > 0 || actionMessage != nil {' \
    'Button(isSending ? "Sending…" : "Send now", action: sendDiagnostics)' \
    '.disabled(pendingCount == 0 || isSending)' \
    'await evidenceController.flushPendingUploads()' \
    'await mapStatisticsController.flushPendingEvents()'; do
    if ! grep -Fq "$text" "$diagnostics_source"; then
        print -u2 "FAIL: Diagnostics window is missing: $text"
        exit 1
    fi
done

for text in \
    'Window("Diagnostics", id: "diagnostics")' \
    'Button("Diagnostics…")' \
    'openWindow(id: "diagnostics")'; do
    if ! grep -Fq "$text" "$app_source"; then
        print -u2 "FAIL: Diagnostics menu/window wiring is missing: $text"
        exit 1
    fi
done

if ! grep -Fq 'AboutSecondaryButton(title: "Diagnostics")' "$about_source" \
    || ! grep -Fq 'openWindow(id: "diagnostics")' "$about_source"; then
    print -u2 "FAIL: About does not open Diagnostics"
    exit 1
fi

for source in "$connect_source" "$about_source" "$diagnostics_source"; do
    if grep -Fq 'Delete uploaded reports' "$source" \
        || grep -Fq 'deleteUploadedReports' "$source"; then
        print -u2 "FAIL: user-facing diagnostics deletion remains in $source"
        exit 1
    fi
done

if grep -Fq 'diagnosticsSection(title: "Privacy")' "$diagnostics_source" \
    || grep -Fq 'Privacy notice' "$diagnostics_source"; then
    print -u2 "FAIL: Diagnostics still duplicates the About privacy section"
    exit 1
fi

if [[ "$(grep -o 'privacy-minimized\|Privacy-minimized' "$diagnostics_source" | wc -l | tr -d ' ')" != 1 ]] \
    || grep -Fq 'minHeight: 600' "$diagnostics_source" \
    || ! grep -Fq 'minHeight: fittedHeight, idealHeight: fittedHeight, maxHeight: fittedHeight' "$diagnostics_source"; then
    print -u2 "FAIL: Diagnostics repeats privacy-minimized or does not fit its content"
    exit 1
fi

# Window title (deviceName), section titles (rowTitle), body and buttons
# (meta), help (caption): the app type scale, nothing else.
for source in "$diagnostics_source" "$about_source"; do
    if grep -o '\.terento(\.[a-zA-Z]*' "$source" | grep -qv '\.terento(\.\(deviceName\|rowTitle\|meta\|caption\)$' \
        || [[ "$(grep -c '\.terento(\.deviceName' "$source")" != 1 ]]; then
        print -u2 "FAIL: $source uses a text role outside title/section/meta/caption"
        exit 1
    fi
done

if ! grep -Fq 'padding: 28,' "$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/SupportReportSheet.swift" \
    || ! grep -Fq 'SavedSupportReport.noSavedReportLine' "$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/SupportReportSheet.swift"; then
    print -u2 "FAIL: Send report window is not aligned to 28 or does not say when there is no saved report"
    exit 1
fi

print 'PASS: Diagnostics window, default-on controls, manual sending, and deletion boundary contract'

python3 - "$diagnostics_source" <<'PYTHON'
from pathlib import Path
import re, sys
source = Path(sys.argv[1]).read_text()
debug = re.findall(r"#if DEBUG\n([\s\S]*?)#endif", source)
assert any('releaseLabel.hasSuffix("-local")' in block and 'Connected device identity' in block for block in debug)
public = re.sub(r"#if DEBUG\n[\s\S]*?#endif", "", source)
for field in ['Connected device identity', 'MTP model:', 'XML model:', 'XML part number:', 'USB VID/PID:', 'API catalog candidate:']:
    assert field not in public, field
assert 'diagnosticsSection(title: "Sharing")' in public
assert any('DisclosureGroup("Technical details")' in block and 'MTP model:' in block for block in debug), 'device fields are not under Technical details'
assert 'DiagnosticsActionButton(title: "Send diagnostics")' not in source, 'a disabled Send diagnostics button remains'
print('PASS: connected-watch technical fields are local-build only; public sharing controls remain')
PYTHON

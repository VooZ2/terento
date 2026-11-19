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
    'Send privacy-minimized compatibility diagnostics' \
    'Send privacy-minimized map usage diagnostics' \
    'Text("Both are on by default. Turning one off also deletes what is waiting to be sent.")' \
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

if ! grep -Fq 'AboutSecondaryButton(title: "Manage diagnostics")' "$about_source" \
    || ! grep -Fq 'openWindow(id: "diagnostics")' "$about_source"; then
    print -u2 "FAIL: About does not expose Manage diagnostics"
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

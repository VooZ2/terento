#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h:h:h}"
app_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/TerentoPoCApp.swift"
diagnostics_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/DiagnosticsView.swift"
about_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/AboutTerentoView.swift"
connect_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/ConnectScreen.swift"

for text in \
    'struct DiagnosticsView: View' \
    'Text("Diagnostics")' \
    'Text("Privacy-minimised diagnostics help improve the Terento app and its services.")' \
    'Send privacy-minimised compatibility diagnostics' \
    'Send privacy-minimised map usage diagnostics' \
    'Text("Both diagnostics streams are enabled by default.' \
    'DiagnosticsActionButton(title: isSending ? "Sending diagnostics…" : "Send diagnostics")' \
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
    'Button("Diagnostics")' \
    'openWindow(id: "diagnostics")'; do
    if ! grep -Fq "$text" "$app_source"; then
        print -u2 "FAIL: Diagnostics menu/window wiring is missing: $text"
        exit 1
    fi
done

if ! grep -Fq 'SecondaryButton(title: "Manage diagnostics")' "$connect_source" \
    || ! grep -Fq 'AboutSecondaryButton(title: "Manage diagnostics")' "$about_source"; then
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

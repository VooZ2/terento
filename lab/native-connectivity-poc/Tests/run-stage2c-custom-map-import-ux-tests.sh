#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"

panel_content="$(awk '
    /private var customMapImportPanel/ { capture = 1 }
    /private func loadDroppedCustomMap/ { capture = 0 }
    capture { print }
' "$connect_screen")"

if ! grep -Fq '@State private var customMapImportExpanded = false' "$connect_screen"; then
    print -u2 "FAIL: custom import does not default to a collapsed session-local state"
    exit 1
fi

if [[ "$panel_content" != *'Text("Import a map from Mac")'* \
    || "$panel_content" != *'Install a compatible Garmin .img file from this Mac.'* \
    || "$panel_content" != *'customMapImportExpanded.toggle()'* \
    || "$panel_content" != *'customMapDropZone'* \
    || "$panel_content" != *'isShowingCustomMapImporter = true'* \
    || "$panel_content" != *'Processed locally. The file is not uploaded.'* ]]; then
    print -u2 "FAIL: collapsed/expanded custom import presentation contract is incomplete"
    exit 1
fi

if [[ "$panel_content" == *'Import .img from Mac'* \
    || "$panel_content" == *'Text("or")'* \
    || "$panel_content" == *'.frame(minHeight: 104)'* \
    || "$panel_content" == *'Add a Garmin map file from this Mac.'* ]]; then
    print -u2 "FAIL: old oversized or duplicated custom import presentation remains"
    exit 1
fi

if ! grep -Fq 'allowsMultipleSelection: false' "$connect_screen" \
    || ! grep -Fq '.onDrop(' "$connect_screen" \
    || ! grep -Fq 'allowedContentTypes: [UTType(filenameExtension: "img") ?? .data]' "$connect_screen"; then
    print -u2 "FAIL: custom import Browse/drop or single-file picker wiring changed"
    exit 1
fi

if ! grep -Fq 'CustomMapImportConfirmationSheet' "$connect_screen" \
    || ! grep -Fq 'Text("Review imported map")' "$connect_screen" \
    || ! grep -Fq 'Button("Cancel", action: onCancel)' "$connect_screen" \
    || ! grep -Fq 'Button("Continue import", action: onContinue)' "$connect_screen" \
    || ! grep -Fq 'Terento does not execute or upload imported map files.' "$connect_screen" \
    || ! grep -Fq '.preferredColorScheme(.light)' "$connect_screen"; then
    print -u2 "FAIL: imported-map confirmation presentation contract is incomplete"
    exit 1
fi

if grep -Fq 'Review custom map risk' "$connect_screen" \
    || grep -Fq 'Text("I understand")' "$connect_screen" \
    || grep -Fq 'Text("Cancel import")' "$connect_screen"; then
    print -u2 "FAIL: legacy custom-map risk alert copy remains"
    exit 1
fi

print "PASS: custom map import UX is collapsed by default with compact local controls"
print "PASS: custom map import keeps Browse, drag-and-drop, and .img picker boundaries"
print "PASS: imported-map confirmation keeps local warning, safe basename, and action wiring"
print "PASS: Stage 2C custom map import UX contract"

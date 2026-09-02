#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
map_models="$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift"

if [[ "$(grep -Fc 'TerentoDisclosureIndicator(isExpanded:' "$connect_screen")" -lt 2 ]] \
    || ! grep -Fq 'alignment: .center' "$connect_screen"; then
    print -u2 "FAIL: Available maps and Import do not share the aligned disclosure indicator"
    exit 1
fi

if ! grep -Fq '.labelsHidden()' "$connect_screen" \
    || ! grep -Fq '.accessibilityLabel("Map provider")' "$connect_screen"; then
    print -u2 "FAIL: provider picker label duplication or accessibility regressed"
    exit 1
fi

if grep -Fq '"lock.fill"' "$connect_screen" \
    || ! grep -Fq 'Choose maps from one provider at a time.' "$connect_screen" \
    || ! grep -Fq 'Unavailable for this installation because maps from another provider are already selected.' "$connect_screen"; then
    print -u2 "FAIL: cross-provider disabled state does not use the quiet tooltip/accessibility contract"
    exit 1
fi

if ! grep -Fq '.toggleStyle(.checkbox)' "$connect_screen" \
    || ! grep -Fq '.tint(TerentoColors.interactive)' "$connect_screen"; then
    print -u2 "FAIL: native checkbox or native-safe Terento tint is missing"
    exit 1
fi

if ! grep -Fq 'appendSelectedProvider' "$connect_screen" \
    || ! grep -Fq 'item.comparison.providerName' "$connect_screen"; then
    print -u2 "FAIL: selected-map summary does not include the active provider"
    exit 1
fi

for expected in \
    'Install a third-party map (.img) from this Mac.' \
    'Drop a third-party map (.img) here' \
    'Button("Choose File…")' \
    'Processed locally on your Mac. Not sent to Terento servers.'; do
    if ! grep -Fq "$expected" "$connect_screen"; then
        print -u2 "FAIL: missing Install maps copy: $expected"
        exit 1
    fi
done

if grep -Fq 'Drop a .img file here' "$connect_screen" \
    || grep -Fq 'Button("Browse")' "$connect_screen" \
    || grep -Fq 'Processed locally. The file is not uploaded.' "$connect_screen"; then
    print -u2 "FAIL: legacy Import from Mac copy remains"
    exit 1
fi

if ! grep -Fq 'historical API serializer fallback' "$map_models" \
    || ! grep -Fq 'isUserFacingReleaseLabel' "$map_models"; then
    print -u2 "FAIL: fabricated or malformed release labels are not filtered"
    exit 1
fi

print "PASS: disclosure and provider filter presentation"
print "PASS: provider-neutral row metadata and release fallback"
print "PASS: quiet cross-provider disabled state and native checkbox tint"
print "PASS: selected summary and Import from Mac copy/style contract"
print "PASS: Install maps UI polish contract"

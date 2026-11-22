#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
map_models="$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift"

if [[ "$(grep -Fc 'TerentoDisclosureIndicator(isExpanded:' "$connect_screen")" -lt 1 ]] \
    || ! grep -Fq 'alignment: .center' "$connect_screen"; then
    print -u2 "FAIL: Custom import lost its aligned disclosure indicator"
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

# Owner QA 2026-11-22: the unchecked Install maps checkbox has a border of at
# least 3:1 against every row background; VoiceOver still gets a checkbox.
python3 - "$connect_screen" "$project_root/Sources/TerentoPoC/Views/DesignSystem/TerentoTokens.generated.swift" <<'PYBOX'
import re, sys
screen, tokens = (open(p).read() for p in sys.argv[1:3])
row = screen[screen.index("struct MapSelectionRow: View {"):screen.index("private struct MapRowSurface")]
assert ".toggleStyle(.checkbox)" not in row, "an Install maps row still uses the native borderless checkbox"
assert row.count(".toggleStyle(TerentoCheckboxToggleStyle())") == 3, "every Install maps checkbox must use the bordered checkbox"
style = screen[screen.index("struct TerentoCheckboxToggleStyle: ToggleStyle"):screen.index("struct MapSelectionRow: View {")]
assert "static let border = TerentoGeneratedTokens.Light.textMuted" in style, "the checkbox border is not Text Muted"
assert "shape.strokeBorder(borderColor, lineWidth: 1)" in style, "the unchecked checkbox has no border"
assert "return configuration.isOn ? TerentoColors.interactive : TerentoCheckboxToggleStyle.border" in style, "the enabled unchecked box does not use the 3:1 border"
assert ".accessibilityRepresentation {" in style and ".toggleStyle(.checkbox)" in style, "VoiceOver does not get a native checkbox"
assert ".focused($isFocused)" in style and "focusRing" in style, "the checkbox has no keyboard focus ring"
assert "static let frameSize: CGFloat = 18" in style, "the checkbox frame differs from the native one and moves the row"
def hex_token(group, name):
    block = tokens[tokens.index(f"enum {group} {{"):]
    return re.search(rf"static let {name} = Color\(terentoHex: 0x([0-9A-F]{{6}})\)", block).group(1)
def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
border = hex_token("Light", "textMuted")
for name in ("backgroundPrimary", "backgroundSecondary", "surfacePrimary", "surfaceElevated", "selectedBackground"):
    value = ratio(border, hex_token("Light", name))
    assert value >= 3, f"checkbox border is {value:.2f}:1 on {name}, below 3:1"
# The app is forced to the light appearance, so the light tokens are the dark-mode values too.
print("PASS: Install maps checkbox border is at least 3:1 on every row background")
PYBOX

if ! grep -Fq 'appendSelectedProvider' "$connect_screen" \
    || ! grep -Fq 'item.comparison.providerName' "$connect_screen"; then
    print -u2 "FAIL: selected-map summary does not include the active provider"
    exit 1
fi

for expected in \
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
    || grep -Fq 'Processed locally. The file is not uploaded.' "$connect_screen" \
    || grep -Fq 'Install a third-party map (.img) from this Mac.' "$connect_screen" \
    || grep -Fq 'Import from Mac' "$connect_screen"; then
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
print "PASS: quiet cross-provider disabled state"
print "PASS: selected summary and Import map file copy/style contract"
print "PASS: Install maps UI polish contract"

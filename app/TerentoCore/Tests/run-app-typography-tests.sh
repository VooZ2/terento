#!/bin/zsh
set -euo pipefail

# The app type scale (owner decision 2026-11-22) and the bundled brand fonts.
# Optional argument: a built Terento.app whose bundled fonts are registered
# with the same code as at launch (CI passes the Xcode product).

project_root="$(cd "$(dirname "$0")/.." && pwd)"
sources="$project_root/Sources/TerentoPoC"
fonts="$sources/Resources/Fonts"

# Static contract: every text font goes through a type role.
python3 - "$sources" <<'PYTEST'
import re, sys
from pathlib import Path

root = Path(sys.argv[1])
typography = root / "Views" / "DesignSystem" / "TerentoTypography.swift"
problems = []
for path in sorted(root.rglob("*.swift")):
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    rel = path.relative_to(root)
    for number, line in enumerate(lines, 1):
        if re.search(r"\.terento(UI|Body|Heading)\(", line):
            problems.append(f"{rel}:{number}: old size-based font helper")
        if path != typography and re.search(r"\.custom\(", line) and "monoFontName" not in line:
            problems.append(f"{rel}:{number}: custom font outside TerentoTypography")
        if path != typography and re.search(r"NSFont\(name: [^)]*size: [0-9]", line):
            problems.append(f"{rel}:{number}: NSFont with a literal size")
        if re.search(r"\.font\(\.(largeTitle|title|title2|title3|headline|subheadline|body|callout|footnote|caption|caption2)\b", line):
            problems.append(f"{rel}:{number}: system text style outside the app scale")
        system = re.search(r"\.system\(size:", line)
        if system and path != typography:
            context = "\n".join(lines[max(0, number - 5):number])
            monospaced = "design: .monospaced" in line and "Role.caption.size" in text
            if not monospaced and not re.search(r"Image\(|\bicon\b|configuration\.icon", context):
                problems.append(f"{rel}:{number}: .system(size:) on text (SF Symbol sizes only)")
        for size in re.findall(r"Font\.system\(size: ([0-9.]+)", line):
            problems.append(f"{rel}:{number}: Font.system size {size} on text")
if problems:
    print("FAIL: text uses a font size outside the app type scale", file=sys.stderr)
    print("\n".join(problems), file=sys.stderr)
    sys.exit(1)
print("PASS: every text font uses a TerentoTypography role")
PYTEST

for name in Inter-Regular Inter-Medium Inter-SemiBold InstrumentSans-Regular InstrumentSans-SemiBold; do
    if [[ ! -s "$fonts/$name.ttf" ]] \
        || ! grep -Fq "$name.ttf in Resources" "$project_root/../../Terento.xcodeproj/project.pbxproj"; then
        print -u2 "FAIL: $name.ttf is not bundled in the app resources"
        exit 1
    fi
done
for licence in Inter-OFL.txt Instrument-Sans-OFL.txt; do
    if ! grep -Fq 'SIL Open Font License, Version 1.1' "$fonts/$licence" \
        || ! grep -Fq "$licence in Resources" "$project_root/../../Terento.xcodeproj/project.pbxproj"; then
        print -u2 "FAIL: $licence is not bundled next to the fonts"
        exit 1
    fi
done
if ! grep -Fq 'TerentoBundledFonts.register()' "$sources/TerentoPoCApp.swift"; then
    print -u2 "FAIL: the bundled fonts are not registered at launch"
    exit 1
fi

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-typography-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/typography-tests"
swiftc \
    -module-name TerentoTypographyTests \
    -parse-as-library \
    "$sources/Views/DesignSystem/TerentoTokens.generated.swift" \
    "$sources/Views/DesignSystem/TerentoTypography.swift" \
    "$project_root/../Terento/TerentoAppResourceCompatibility.swift" \
    "$project_root/Tests/TerentoPoCTests/TypographyTests.swift" \
    -o "$binary_path"

"$binary_path" "${1:-$fonts}"

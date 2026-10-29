#!/bin/sh
# Builds the AppStore configuration ad-hoc signed and checks the result:
#   - the app and the embedded finishing helper carry exactly the reviewed
#     entitlements (no get-task-allow, nothing Xcode added);
#   - every nested code item is signed and the bundle verifies strictly;
#   - no update-check, donation or support-report upload string is in any
#     executable of the bundle (other diagnostics are sent only after an
#     opt-in, see README.md).
# Optional second argument: a DMG-configuration Terento.app built from the
# same source. Its executable must still contain every forbidden string, so a
# passing check cannot come from strings that never existed.
#
# Usage: Packaging/AppStore/verify-app-store-build.sh DERIVED_DATA_DIR [DMG_APP]
set -eu

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
    echo "Usage: $0 DERIVED_DATA_DIR [DMG_APP]" >&2
    exit 2
}
derived_data="$1"
control_app="${2:-}"
repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
app="$derived_data/Build/Products/AppStore/Terento.app"
helper="$app/Contents/MacOS/TerentoFinishingWorker"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

xcodebuild \
    -project "$repo_root/Terento.xcodeproj" \
    -scheme Terento \
    -configuration AppStore \
    -sdk macosx \
    -derivedDataPath "$derived_data" \
    ARCHS=arm64 \
    NATIVE_ARCH_ACTUAL=arm64 \
    CODE_SIGNING_ALLOWED=YES \
    CODE_SIGN_IDENTITY=- \
    build

test -x "$app/Contents/MacOS/Terento" || fail "app executable is missing"
test -x "$helper" || fail "sandboxed finishing helper is missing"
test -f "$app/Contents/Frameworks/libusb-1.0.0.dylib" || fail "bundled libusb is missing"
test -f "$app/Contents/Frameworks/libmtp.9.dylib" || fail "bundled libmtp is missing"
/usr/bin/cmp "$repo_root/LICENSE" "$app/Contents/Resources/LICENSE" || fail "bundled LICENSE differs"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")" = "app.terento.mac" \
    || fail "unexpected bundle identifier"
# A plain build never embeds the production migration manifest.
test ! -e "$app/Contents/Resources/container-migration.plist" \
    || fail "a non-archive build embedded a container migration manifest"

for nested in \
    "$app/Contents/Frameworks/libusb-1.0.0.dylib" \
    "$app/Contents/Frameworks/libmtp.9.dylib" \
    "$helper"; do
    /usr/bin/codesign --verify --strict --verbose=2 "$nested" || fail "nested code is not signed: $nested"
done
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app" || fail "app signature does not verify"

work="$(mktemp -d "${TMPDIR:-/tmp}/terento-appstore-verify.XXXXXX")"
trap 'rm -rf "$work"' EXIT
/usr/bin/codesign -d --entitlements - --xml "$app" >"$work/app.plist" 2>/dev/null
/usr/bin/codesign -d --entitlements - --xml "$helper" >"$work/helper.plist" 2>/dev/null
python3 - "$work/app.plist" "$repo_root/app/Terento/Terento-AppStore.entitlements" \
    "$work/helper.plist" "$repo_root/app/Terento/TerentoFinishingWorker-AppStore.entitlements" <<'PYCHECK'
import plistlib
import sys

for signed_path, expected_path in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    with open(signed_path, "rb") as signed_file, open(expected_path, "rb") as expected_file:
        raw = signed_file.read()
        signed = plistlib.loads(raw) if raw.strip() else {}
        expected = plistlib.load(expected_file)
    if signed != expected:
        raise SystemExit(f"FAIL: signed entitlements {signed} differ from {expected_path}: {expected}")
    print(f"PASS: entitlements match {expected_path.rsplit('/', 1)[-1]}: {sorted(signed)}")
PYCHECK

forbidden_strings="$work/forbidden-strings.txt"
cat >"$forbidden_strings" <<'STRINGS'
updates/macos-arm64.json
buymeacoffee
api.terento.app/support/reports
STRINGS

if [ -n "$control_app" ]; then
    # Debug builds put the app code in Contents/MacOS/Terento.debug.dylib
    # (Xcode ENABLE_DEBUG_DYLIB), so search every file in Contents/MacOS.
    test -f "$control_app/Contents/MacOS/Terento" || fail "control executable is missing: $control_app/Contents/MacOS/Terento"
    while IFS= read -r needle; do
        LC_ALL=C grep -a -F -q -- "$needle" "$control_app/Contents/MacOS/"* \
            || fail "control build lacks '$needle'; the absence check would prove nothing"
    done <"$forbidden_strings"
fi

# Every code file in the bundle: the app, the helper and the embedded libraries.
find "$app/Contents/MacOS" "$app/Contents/Frameworks" -type f >"$work/bundle-code.txt"
while IFS= read -r executable; do
    while IFS= read -r needle; do
        if LC_ALL=C grep -a -F -q -- "$needle" "$executable"; then
            fail "'$needle' is compiled into $executable"
        fi
    done <"$forbidden_strings"
done <"$work/bundle-code.txt"

echo "PASS: AppStore configuration builds, signs nested code, has exact entitlements and no update, donation or support-report strings"

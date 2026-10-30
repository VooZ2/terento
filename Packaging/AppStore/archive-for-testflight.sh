#!/bin/sh
# Builds the AppStore configuration as a signed Mac App Store package for an
# internal TestFlight test (App Store plan, stage 2). Run on the owner's Mac.
#
# Before the first run:
#   - Xcode > Settings > Accounts lists the Apple ID of team VXALAZU3B5;
#   - App Store Connect has the app record for bundle ID app.terento.mac.
# Xcode then creates the Apple Development and distribution certificates and
# the Mac App Store provisioning profile itself (-allowProvisioningUpdates).
#
# After every check passes, Xcode uploads the package to App Store Connect with
# the Apple ID signed in to Xcode (no API key leaves this Mac). The build then
# appears in TestFlight after Apple's processing.
#
# The package carries the production container migration. Its first launch
# MOVES ~/Library/Application Support/Terento into the app container; the DMG
# app then lacks its manifests. Back the folder up before the first launch
# (the script prints the command).
#
# App Store Connect accepts each build number once per version. The package
# keeps the Release build number (for example 46); a second upload of the same
# version passes a sequence number and gets build 46.1, 46.2, ...
#
# Usage: Packaging/AppStore/archive-for-testflight.sh [UPLOAD_SEQUENCE]
set -eu

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() { sed -n '2,/^# Usage:/p' "$0"; exit 2; }
[ "$#" -le 1 ] || usage
sequence="${1:-}"
case "$sequence" in
    "") ;;
    *[!0-9]* | 0*) usage ;;
esac
[ "$(uname -s)" = "Darwin" ] || die "Run this on macOS with Xcode."
command -v xcodebuild >/dev/null 2>&1 || die "xcodebuild not found. Install Xcode and run: sudo xcode-select -s /Applications/Xcode.app"

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
# shellcheck source=../release-config.sh
. "$repo_root/Packaging/release-config.sh"
team="$RELEASE_TEAM_ID"
bundle_id="$RELEASE_BUNDLE_IDENTIFIER"
production_manifest="$repo_root/Packaging/AppStore/container-migration.plist"
# Fixed path, never configurable: it is deleted at the start of every run.
output="$HOME/TerentoAppStoreArchive"
archive="$output/Terento.xcarchive"
export_dir="$output/export"
options="$output/ExportOptions.plist"
log="$output/xcodebuild.log"

[ ! -L "$output" ] || die "$output is a symbolic link. Delete it and run this script again."
rm -rf "$output"
mkdir -m 700 "$output"

cat >"$options" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>destination</key>
    <string>export</string>
    <key>teamID</key>
    <string>$team</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>uploadSymbols</key>
    <true/>
    <key>manageAppVersionAndBuildNumber</key>
    <false/>
</dict>
</plist>
EOF

build_override=""
if [ -n "$sequence" ]; then
    release_build="$(xcodebuild -project "$repo_root/$RELEASE_PROJECT" -scheme "$RELEASE_SCHEME" \
        -configuration AppStore -showBuildSettings 2>/dev/null \
        | awk '$1 == "CURRENT_PROJECT_VERSION" { print $3; exit }')"
    case "$release_build" in
        "" | *[!0-9]*) die "Could not read the AppStore build number." ;;
    esac
    build_override="CURRENT_PROJECT_VERSION=$release_build.$sequence"
fi

echo "Archiving the AppStore configuration (bundle ID $bundle_id, team $team)..."
# shellcheck disable=SC2086 # build_override is one word or empty
xcodebuild \
    -project "$repo_root/$RELEASE_PROJECT" \
    -scheme "$RELEASE_SCHEME" \
    -configuration AppStore \
    -destination 'generic/platform=macOS' \
    -archivePath "$archive" \
    -allowProvisioningUpdates \
    CODE_SIGN_STYLE=Automatic \
    CODE_SIGN_IDENTITY="Apple Development" \
    DEVELOPMENT_TEAM="$team" \
    PROVISIONING_PROFILE_SPECIFIER= \
    $build_override \
    archive >"$log" 2>&1 || {
    tail -n 60 "$log" >&2
    die "Archive failed. Full log: $log"
}

archived_app="$archive/Products/Applications/Terento.app"
[ -d "$archived_app" ] || die "The archive has no Terento.app: $archived_app"
/usr/bin/cmp -s "$production_manifest" "$archived_app/Contents/Resources/container-migration.plist" \
    || die "The archive does not carry the production migration manifest."

echo "Exporting the Mac App Store package..."
xcodebuild \
    -exportArchive \
    -archivePath "$archive" \
    -exportPath "$export_dir" \
    -exportOptionsPlist "$options" \
    -allowProvisioningUpdates >>"$log" 2>&1 || {
    tail -n 60 "$log" >&2
    die "Export failed. Full log: $log"
}

pkg="$(find "$export_dir" -maxdepth 1 -name '*.pkg' | sed -n '1p')"
[ -n "$pkg" ] || die "Export produced no .pkg. Full log: $log"

# Check what TestFlight will receive, not only what was archived.
check="$output/check"
/usr/sbin/pkgutil --expand-full "$pkg" "$check" >/dev/null
app="$(find "$check" -type d -name 'Terento.app' -prune | sed -n '1p')"
[ -n "$app" ] || die "The package has no Terento.app."
helper="$app/Contents/MacOS/TerentoFinishingWorker"
[ -f "$helper" ] || die "The package has no finishing helper."
[ -f "$app/Contents/embedded.provisionprofile" ] || die "The package has no provisioning profile."
/usr/bin/cmp -s "$production_manifest" "$app/Contents/Resources/container-migration.plist" \
    || die "The package does not carry the production migration manifest."
[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")" = "$bundle_id" ] \
    || die "The package has the wrong bundle ID."
[ "$(/usr/libexec/PlistBuddy -c 'Print :ITSAppUsesNonExemptEncryption' "$app/Contents/Info.plist")" = "false" ] \
    || die "The package does not declare ITSAppUsesNonExemptEncryption = NO."
/usr/bin/codesign --verify --deep --strict "$app" || die "The package's app signature is invalid."
/usr/sbin/pkgutil --check-signature "$pkg" >"$output/pkg-signature.txt" || die "The package is not signed."

/usr/bin/codesign -d --entitlements - --xml "$app" >"$output/app-entitlements.plist" 2>/dev/null
/usr/bin/codesign -d --entitlements - --xml "$helper" >"$output/helper-entitlements.plist" 2>/dev/null
/usr/bin/python3 - "$output/app-entitlements.plist" "$repo_root/app/Terento/Terento-AppStore.entitlements" \
    "$output/helper-entitlements.plist" "$repo_root/app/Terento/TerentoFinishingWorker-AppStore.entitlements" \
    "$team" "$bundle_id" <<'PYCHECK'
import plistlib
import sys

app_signed, app_file, helper_signed, helper_file, team, bundle_id = sys.argv[1:]
load = lambda path: plistlib.loads(open(path, "rb").read() or plistlib.dumps({}))
app, helper = load(app_signed), load(helper_signed)
# Distribution signing may add only the identity keys from the profile.
identity = {
    "com.apple.application-identifier": f"{team}.{bundle_id}",
    "com.apple.developer.team-identifier": team,
}
for key, value in identity.items():
    if key in app and app.pop(key) != value:
        raise SystemExit(f"FAIL: app {key} is not {value}")
if app != load(app_file):
    raise SystemExit(f"FAIL: app entitlements {app} differ from {app_file}")
if helper != load(helper_file):
    raise SystemExit(f"FAIL: helper entitlements {helper} are not exactly app-sandbox + inherit")
print("PASS: app and helper entitlements are exact")
PYCHECK

version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist")"
build="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app/Contents/Info.plist")"
backup="$HOME/TerentoDataBackup-$(date +%Y%m%d-%H%M%S)"
container="$HOME/Library/Containers/$bundle_id"
if [ -e "$container" ]; then
    backup_step="2. The App Store container already exists, so the DMG data was already
   moved into it. Do not back up again; keep the earlier backup."
else
    backup_step="2. Before the first launch (it moves the DMG app's data), back it up:
     ditto \"$HOME/Library/Application Support/Terento\" \"$backup\""
fi

# The same archive is exported again, now straight to App Store Connect.
upload_options="$output/UploadOptions.plist"
sed 's#<string>export</string>#<string>upload</string>#' "$options" >"$upload_options"
grep -q '<string>upload</string>' "$upload_options" || die "Could not write the upload options."
echo "Uploading version $version, build $build to App Store Connect..."
xcodebuild \
    -exportArchive \
    -archivePath "$archive" \
    -exportPath "$output/upload" \
    -exportOptionsPlist "$upload_options" \
    -allowProvisioningUpdates >>"$log" 2>&1 || {
    tail -n 60 "$log" >&2
    die "Upload failed. The checked package is still at $pkg; Transporter can deliver it. Full log: $log"
}

cat <<EOF

Uploaded: version $version, build $build. Signature:
$(sed -n '1,4p' "$output/pkg-signature.txt")

Next steps
1. Wait for Apple's processing email, then open TestFlight and press Update.
$backup_step
3. Use only one Terento on this Mac at a time.
EOF

#!/bin/zsh

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

# Do not let macOS resource-fork metadata become AppleDouble `._*` files in
# release archives or the DMG. These files are not part of the application
# and must not be shipped to users.
export COPYFILE_DISABLE=1

# shellcheck disable=SC1091
. "$script_dir/release-config.sh"

no_notarize=0
overwrite=0
output_dir="$repo_root/$RELEASE_OUTPUT_DIR"
version_assertion=""
build_assertion=""
release_label_assertion=""

usage() {
    cat <<'EOF'
Usage: Packaging/release.sh [options]

Options:
  --no-notarize       Build, sign, and verify only; do not create release artifacts.
  --overwrite         Replace the exact final ZIP and DMG if they already exist.
  --output-dir DIR    Write final artifacts under DIR instead of dist/.
  --version VERSION   Assert that the generated app has VERSION.
  --build NUMBER      Assert that the generated app has build NUMBER.
  --release-version V Use V in package filenames, for example 1.0.0-beta.3.
  --help              Show this help.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

setting_value() {
    /usr/bin/sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$build_settings" | /usr/bin/sed -n '1p'
}

plist_value() {
    /usr/bin/plutil -extract "$1" raw -o - "$2"
}

assert_equal() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    if [[ "$actual" != "$expected" ]]; then
        die "$label mismatch: expected '$expected', got '$actual'"
    fi
}

run_logged() {
    local label="$1"
    shift
    local log_path="$run_dir/$label.log"
    printf '%s\n' "[$label]"
    if "$@" >"$log_path" 2>&1; then
        tail -n 8 "$log_path"
    else
        tail -n 80 "$log_path" >&2
        die "$label failed; full log: $log_path"
    fi
}

json_string() {
    /usr/bin/sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$2" | /usr/bin/sed -n '1p'
}

launch_smoke() {
    local smoke_app="$1"
    local smoke_binary="$smoke_app/Contents/MacOS/Terento"
    local before_pids
    local after_pids
    local new_pids

    before_pids=$(/bin/ps -axo pid=,command= | /usr/bin/awk -v bin="$smoke_binary" '$2 == bin {print $1}')
    /usr/bin/open -n "$smoke_app" >/dev/null 2>&1 || die "Could not launch $smoke_app"
    /bin/sleep 5
    after_pids=$(/bin/ps -axo pid=,command= | /usr/bin/awk -v bin="$smoke_binary" '$2 == bin {print $1}')

    new_pids=""
    for pid in $after_pids; do
        if [[ " $before_pids " != *" $pid "* ]]; then
            new_pids="$new_pids $pid"
        fi
    done

    [[ -n "$new_pids" ]] || die "Launch smoke test did not find a new Terento process"
    printf '%s\n' "Launch smoke passed"
    for pid in $new_pids; do
        /bin/kill "$pid"
    done
}

while (( $# > 0 )); do
    case "$1" in
        --no-notarize)
            no_notarize=1
            shift
            ;;
        --overwrite)
            overwrite=1
            shift
            ;;
        --output-dir)
            (( $# >= 2 )) || die "--output-dir requires a value"
            output_dir="$2"
            shift 2
            ;;
        --version)
            (( $# >= 2 )) || die "--version requires a value"
            version_assertion="$2"
            shift 2
            ;;
        --build)
            (( $# >= 2 )) || die "--build requires a value"
            build_assertion="$2"
            shift 2
            ;;
        --release-version)
            (( $# >= 2 )) || die "--release-version requires a value"
            release_label_assertion="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "Unknown option: $1"
            ;;
    esac
done

if [[ "$output_dir" != /* ]]; then
    output_dir="$repo_root/$output_dir"
fi

require_command xcodebuild
require_command swift
require_command codesign
require_command security
require_command xcrun
require_command ditto
require_command otool
require_command lipo
require_command plutil
require_command shasum
require_command spctl
require_command open
require_command hdiutil
require_command rg

[[ -d "$repo_root/$RELEASE_PROJECT" ]] || die "Project not found: $RELEASE_PROJECT"
[[ -f "$repo_root/$RELEASE_ENTITLEMENTS" ]] || die "Entitlements not found: $RELEASE_ENTITLEMENTS"
[[ -f "$repo_root/$RELEASE_NATIVE_BUILD_SCRIPT" ]] || die "Native dependency script not found: $RELEASE_NATIVE_BUILD_SCRIPT"
[[ -f "$repo_root/LICENSE" ]] || die "Repository LICENSE is missing"
[[ -f "$repo_root/THIRD_PARTY_NOTICES.md" ]] || die "Repository THIRD_PARTY_NOTICES.md is missing"

run_dir="$(/usr/bin/mktemp -d /private/tmp/terento-stage65-run.XXXXXX)"
derived_data="$run_dir/derived-data"
app="$derived_data/Build/Products/$RELEASE_CONFIGURATION/$RELEASE_PRODUCT_NAME.app"
build_settings="$run_dir/build-settings.txt"
dmg_mount="$run_dir/dmg-mount"
dmg_attached=0

cleanup() {
    local result_code=$?
    trap - EXIT
    if (( dmg_attached )); then
        hdiutil detach "$dmg_mount" -force >/dev/null 2>&1 || true
    fi
    if (( result_code == 0 )); then
        /bin/rm -rf -- "$run_dir"
    else
        printf 'Release run data preserved at: %s\n' "$run_dir" >&2
    fi
    exit "$result_code"
}
trap cleanup EXIT

printf '%s\n' "Terento Stage 6.5 release pipeline"
printf '%s\n' "Project: $RELEASE_PROJECT"
printf '%s\n' "Configuration: $RELEASE_CONFIGURATION"
printf '%s\n' "Architecture: $RELEASE_ARCH"
printf '%s\n' "Output directory: $output_dir"
if (( no_notarize )); then
    printf '%s\n' "Mode: dry-run (--no-notarize)"
else
    printf '%s\n' "Mode: notarize and package"
fi

if ! xcodebuild \
    -project "$repo_root/$RELEASE_PROJECT" \
    -scheme "$RELEASE_SCHEME" \
    -configuration "$RELEASE_CONFIGURATION" \
    -sdk macosx \
    -derivedDataPath "$derived_data" \
    -showBuildSettings >"$build_settings" 2>&1; then
    tail -n 80 "$build_settings" >&2
    die "Could not read Xcode Release build settings"
fi

assert_equal "PRODUCT_NAME" "$(setting_value PRODUCT_NAME)" "$RELEASE_PRODUCT_NAME"
assert_equal "PRODUCT_BUNDLE_IDENTIFIER" "$(setting_value PRODUCT_BUNDLE_IDENTIFIER)" "$RELEASE_BUNDLE_IDENTIFIER"
assert_equal "DEVELOPMENT_TEAM" "$(setting_value DEVELOPMENT_TEAM)" "$RELEASE_TEAM_ID"
assert_equal "MACOSX_DEPLOYMENT_TARGET" "$(setting_value MACOSX_DEPLOYMENT_TARGET)" "$RELEASE_DEPLOYMENT_TARGET"
assert_equal "ARCHS" "$(setting_value ARCHS)" "$RELEASE_ARCH"
assert_equal "CODE_SIGN_ENTITLEMENTS" "$(setting_value CODE_SIGN_ENTITLEMENTS)" "$RELEASE_ENTITLEMENTS"
assert_equal "ENABLE_HARDENED_RUNTIME" "$(setting_value ENABLE_HARDENED_RUNTIME)" "YES"
assert_equal "CODE_SIGN_INJECT_BASE_ENTITLEMENTS" "$(setting_value CODE_SIGN_INJECT_BASE_ENTITLEMENTS)" "NO"

project_version="$(setting_value "$RELEASE_VERSION_SETTING")"
project_build="$(setting_value "$RELEASE_BUILD_SETTING")"
[[ -n "$project_version" ]] || die "Release version is missing from Xcode settings"
[[ -n "$project_build" ]] || die "Release build number is missing from Xcode settings"

if [[ -n "$version_assertion" ]]; then
    assert_equal "Requested version" "$project_version" "$version_assertion"
fi
if [[ -n "$build_assertion" ]]; then
    assert_equal "Requested build" "$project_build" "$build_assertion"
fi

release_tag=""
if [[ -v RELEASE_TAG ]]; then
    release_tag="$RELEASE_TAG"
elif [[ -v CI_COMMIT_TAG ]]; then
    release_tag="$CI_COMMIT_TAG"
fi
if [[ -n "$release_tag" ]]; then
    release_tag="$(printf '%s' "$release_tag" | /usr/bin/sed -e 's#^.*/##' -e 's/^v//')"
    release_tag_base="${release_tag%%-*}"
    assert_equal "Release tag base version" "$project_version" "$release_tag_base"
fi

release_label="$release_label_assertion"
if [[ -z "$release_label" ]]; then
    if [[ -n "$release_tag" ]]; then
        release_label="$release_tag"
    else
        release_label="$project_version"
    fi
fi
release_label="$(printf '%s' "$release_label" | /usr/bin/sed -e 's#^.*/##' -e 's/^v//')"
case "$release_label" in
    "$project_version"|"$project_version"-*)
        ;;
    *)
        die "Release package version must start with app version '$project_version': $release_label"
        ;;
esac
printf '%s\n' "Release package version: $release_label"

identity_check="$run_dir/signing-identities.txt"
if ! security find-identity -v -p codesigning >"$identity_check" 2>&1; then
    cat "$identity_check" >&2
    die "Could not inspect signing identities"
fi
rg -F "$RELEASE_SIGNING_IDENTITY" "$identity_check" >/dev/null || die "Configured Developer ID identity is not available"

if (( ! no_notarize )); then
    profile_check="$run_dir/notary-profile.json"
    if ! xcrun notarytool history \
        --keychain-profile "$RELEASE_NOTARY_PROFILE" \
        --output-format json >"$profile_check" 2>&1; then
        cat "$profile_check" >&2
        die "Notarytool Keychain profile is unavailable: $RELEASE_NOTARY_PROFILE"
    fi
fi

if [[ ! -v LIBMTP_PREFIX || -z "$LIBMTP_PREFIX" ]]; then
    [[ -d /opt/homebrew/opt/libmtp ]] || die "Legacy SwiftPM regression tests require LIBMTP_PREFIX or /opt/homebrew/opt/libmtp"
    export LIBMTP_PREFIX="/opt/homebrew/opt/libmtp"
fi
export SWIFTPM_CONFIG_DIR="$run_dir/swiftpm-config"
export CLANG_MODULE_CACHE_PATH="$run_dir/clang-module-cache"

run_logged "swift-build" \
    swift build \
    --package-path "$repo_root/lab/native-connectivity-poc" \
    --product TerentoPoC \
    --build-path "$run_dir/swift-build"

for test_script in "$repo_root"/lab/native-connectivity-poc/Tests/run-*.sh; do
    test_name="$(basename "$test_script" | /usr/bin/sed 's/\.sh$//')"
    run_logged "test-$test_name" "$test_script"
done

if ! xcodebuild \
    -project "$repo_root/$RELEASE_PROJECT" \
    -scheme "$RELEASE_SCHEME" \
    -configuration "$RELEASE_CONFIGURATION" \
    -sdk macosx \
    -derivedDataPath "$derived_data" \
    ARCHS="$RELEASE_ARCH" \
    NATIVE_ARCH_ACTUAL="$RELEASE_ARCH" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY=- \
    build >"$run_dir/xcodebuild.log" 2>&1; then
    tail -n 100 "$run_dir/xcodebuild.log" >&2
    die "Fresh Release app build failed; full log: $run_dir/xcodebuild.log"
fi
tail -n 12 "$run_dir/xcodebuild.log"

[[ -d "$app" ]] || die "Fresh app bundle was not produced: $app"
for native_library in \
    "$app/Contents/Frameworks/libusb-1.0.0.dylib" \
    "$app/Contents/Frameworks/libmtp.9.dylib"; do
    [[ -f "$native_library" ]] || die "Bundled native library missing: $native_library"
done

app_version="$(plist_value CFBundleShortVersionString "$app/Contents/Info.plist")"
app_build="$(plist_value CFBundleVersion "$app/Contents/Info.plist")"
app_bundle_identifier="$(plist_value CFBundleIdentifier "$app/Contents/Info.plist")"
app_minimum_os="$(plist_value LSMinimumSystemVersion "$app/Contents/Info.plist")"
assert_equal "Built app version" "$app_version" "$project_version"
assert_equal "Built app build" "$app_build" "$project_build"
assert_equal "Built app bundle identifier" "$app_bundle_identifier" "$RELEASE_BUNDLE_IDENTIFIER"
assert_equal "Built app minimum macOS" "$app_minimum_os" "$RELEASE_DEPLOYMENT_TARGET"
[[ "$(lipo -archs "$app/Contents/MacOS/$RELEASE_PRODUCT_NAME")" == "$RELEASE_ARCH" ]] || die "Unexpected app architecture"

/usr/bin/cmp "$repo_root/LICENSE" "$app/Contents/Resources/LICENSE" || die "Bundled LICENSE differs from repository LICENSE"
/usr/bin/cmp "$repo_root/THIRD_PARTY_NOTICES.md" "$app/Contents/Resources/THIRD_PARTY_NOTICES.md" || die "Bundled THIRD_PARTY_NOTICES.md differs from repository copy"

if find "$app" -type f \( -name '*.dSYM' -o -name '*.swiftmodule' -o -name '*.swiftdoc' -o -name '*.o' -o -name '*.log' \) -print -quit | rg -q .; then
    die "Debug/build file found inside app bundle"
fi

printf '%s\n' "Native dependency bundling: PASS"

printf '%s\n' "Signing libusb"
codesign --force --verbose --timestamp --options runtime \
    --sign "$RELEASE_SIGNING_IDENTITY" \
    "$app/Contents/Frameworks/libusb-1.0.0.dylib"
printf '%s\n' "Signing libmtp"
codesign --force --verbose --timestamp --options runtime \
    --sign "$RELEASE_SIGNING_IDENTITY" \
    "$app/Contents/Frameworks/libmtp.9.dylib"

while IFS= read -r nested_code; do
    [[ -n "$nested_code" ]] || continue
    case "$nested_code" in
        */libusb-1.0.0.dylib|*/libmtp.9.dylib)
            continue
            ;;
    esac
    printf '%s\n' "Signing nested code: $nested_code"
    codesign --force --verbose --timestamp --options runtime \
        --sign "$RELEASE_SIGNING_IDENTITY" "$nested_code"
done < <(
    find "$app/Contents" -type f \( -perm -111 -o -name '*.dylib' \) \
        ! -path "$app/Contents/MacOS/$RELEASE_PRODUCT_NAME" \
        -print | sort
)

printf '%s\n' "Signing Terento.app"
codesign --force --verbose --timestamp --options runtime \
    --entitlements "$repo_root/$RELEASE_ENTITLEMENTS" \
    --sign "$RELEASE_SIGNING_IDENTITY" "$app"

codesign --verify --strict --verbose=4 "$app/Contents/Frameworks/libusb-1.0.0.dylib"
codesign --verify --strict --verbose=4 "$app/Contents/Frameworks/libmtp.9.dylib"
codesign --verify --strict --verbose=4 "$app"
codesign --verify --deep --strict --verbose=4 "$app"

entitlements_output="$run_dir/entitlements.txt"
codesign -d --entitlements :- "$app" >"$entitlements_output" 2>&1
if rg -n 'get-task-allow|com.apple.security.cs.debugger' "$entitlements_output"; then
    die "Forbidden production entitlement found"
fi

linker_output="$run_dir/otool.txt"
(
    otool -L "$app/Contents/MacOS/$RELEASE_PRODUCT_NAME"
    otool -L "$app/Contents/Frameworks/libusb-1.0.0.dylib"
    otool -L "$app/Contents/Frameworks/libmtp.9.dylib"
    otool -l "$app/Contents/MacOS/$RELEASE_PRODUCT_NAME"
) >"$linker_output"
if rg -n '/opt/homebrew|/usr/local|/Users/' "$linker_output"; then
    die "Developer-machine runtime path found"
fi
printf '%s\n' "Signature and runtime path verification: PASS"

if (( no_notarize )); then
    printf '%s\n' "NOT NOTARIZED: dry-run completed; no release artifact was created"
    exit 0
fi

notary_zip="$run_dir/Terento-notarization.zip"
notary_extract="$run_dir/notary-extract"
ditto --norsrc --noextattr --noqtn --noacl -c -k --keepParent "$app" "$notary_zip"
mkdir -p "$notary_extract"
ditto --norsrc --noextattr --noqtn --noacl -x -k "$notary_zip" "$notary_extract"
notary_app="$notary_extract/$RELEASE_PRODUCT_NAME.app"
[[ -d "$notary_app" ]] || die "Notarization archive does not contain the expected app"
[[ "$(find "$notary_extract" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" == "1" ]] || die "Notarization archive has unexpected top-level entries"
if find "$notary_app" -name '.DS_Store' -print -quit | rg -q .; then
    die "Notarization archive contains .DS_Store"
fi
if find "$notary_app" \( -name '._*' -o -name '__MACOSX' \) -print -quit | rg -q .; then
    die "Notarization archive contains macOS metadata files"
fi
codesign --verify --deep --strict --verbose=4 "$notary_app"
printf '%s\n' "Notarization archive validation: PASS"

notary_submit="$run_dir/notary-submit.json"
if ! xcrun notarytool submit "$notary_zip" \
    --keychain-profile "$RELEASE_NOTARY_PROFILE" \
    --wait \
    --output-format json >"$notary_submit" 2>&1; then
    cat "$notary_submit" >&2
    die "Apple notarization submission failed"
fi
submission_id="$(json_string id "$notary_submit")"
notary_status="$(json_string status "$notary_submit")"
[[ -n "$submission_id" ]] || die "Apple submission ID missing from notarytool output"
printf '%s\n' "Notarization submission ID: $submission_id"
printf '%s\n' "Notarization status: $notary_status"
if [[ "$notary_status" != "Accepted" ]]; then
    xcrun notarytool log "$submission_id" --keychain-profile "$RELEASE_NOTARY_PROFILE" --output-format json || true
    die "Apple notarization did not return Accepted"
fi

notary_log="$run_dir/notary-log.json"
xcrun notarytool log "$submission_id" \
    --keychain-profile "$RELEASE_NOTARY_PROFILE" \
    --output-format json >"$notary_log"
rg -q '"status"[[:space:]]*:[[:space:]]*"Accepted"' "$notary_log" || die "Notarization log is not Accepted"
rg -q '"issues"[[:space:]]*:[[:space:]]*null' "$notary_log" || die "Notarization log contains issues"
printf '%s\n' "Notarization log: Accepted with no issues"

xcrun stapler staple "$app"
xcrun stapler validate "$app"
codesign --verify --deep --strict --verbose=4 "$app"
printf '%s\n' "Stapling and post-staple signature verification: PASS"

final_zip="$output_dir/$RELEASE_PRODUCT_NAME-$release_label-macOS-$RELEASE_ARCH.zip"
final_dmg="$output_dir/$RELEASE_PRODUCT_NAME-$release_label-macOS-$RELEASE_ARCH.dmg"
for final_artifact in "$final_zip" "$final_dmg"; do
    if [[ -e "$final_artifact" ]]; then
        (( overwrite )) || die "Final artifact already exists; use --overwrite: $final_artifact"
        /bin/rm -f -- "$final_artifact"
    fi
done
mkdir -p "$output_dir"
ditto --norsrc --noextattr --noqtn --noacl -c -k --keepParent "$app" "$final_zip"

final_extract="$run_dir/final-extract"
mkdir -p "$final_extract"
ditto --norsrc --noextattr --noqtn --noacl -x -k "$final_zip" "$final_extract"
final_app="$final_extract/$RELEASE_PRODUCT_NAME.app"
[[ -d "$final_app" ]] || die "Final ZIP does not contain Terento.app"
[[ "$(find "$final_extract" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" == "1" ]] || die "Final ZIP has unexpected top-level entries"
if find "$final_app" -name '.DS_Store' -print -quit | rg -q .; then
    die "Final ZIP contains .DS_Store"
fi
if find "$final_extract" \( -name '._*' -o -name '__MACOSX' \) -print -quit | rg -q .; then
    die "Final ZIP contains macOS metadata files"
fi
if find "$final_app" \( -name '*.img' -o -name '*.backup' -o -name '*.p12' -o -name '*.p8' -o -name '*.pem' -o -name '*.key' \) -print -quit | rg -q .; then
    die "Final ZIP contains forbidden content"
fi
codesign --verify --deep --strict --verbose=4 "$final_app"
xcrun stapler validate "$final_app"
gatekeeper_output="$run_dir/final-gatekeeper.txt"
if ! spctl --assess --type execute --verbose=4 "$final_app" >"$gatekeeper_output" 2>&1; then
    cat "$gatekeeper_output" >&2
    die "Gatekeeper rejected the extracted final artifact"
fi
cat "$gatekeeper_output"
rg -q 'accepted' "$gatekeeper_output" || die "Gatekeeper did not report accepted"
rg -q 'Notarized Developer ID' "$gatekeeper_output" || die "Gatekeeper source is not Notarized Developer ID"
launch_smoke "$final_app"

dmg_stage="$run_dir/dmg-stage"
mkdir -p "$dmg_stage"
ditto --norsrc --noextattr --noqtn --noacl "$app" "$dmg_stage/$RELEASE_PRODUCT_NAME.app"
ln -s /Applications "$dmg_stage/Applications"
run_logged "dmg-create" \
    hdiutil create \
    -volname "Terento $release_label" \
    -srcfolder "$dmg_stage" \
    -ov \
    -format UDZO \
    "$final_dmg"
run_logged "dmg-verify" hdiutil verify "$final_dmg"

mkdir -p "$dmg_mount"
if ! hdiutil attach "$final_dmg" \
    -nobrowse \
    -readonly \
    -mountpoint "$dmg_mount" \
    >"$run_dir/dmg-attach.log" 2>&1; then
    cat "$run_dir/dmg-attach.log" >&2
    die "Could not mount the final DMG"
fi
dmg_attached=1
dmg_app="$dmg_mount/$RELEASE_PRODUCT_NAME.app"
[[ -d "$dmg_app" ]] || die "Final DMG does not contain Terento.app"
[[ -L "$dmg_mount/Applications" ]] || die "Final DMG does not contain an Applications shortcut"
dmg_entry_count="$(find "$dmg_mount" -mindepth 1 -maxdepth 1 ! -name '.DS_Store' -print | wc -l | tr -d ' ')"
assert_equal "DMG top-level entry count" "$dmg_entry_count" "2"
if find "$dmg_app" -name '.DS_Store' -print -quit | rg -q .; then
    die "Final DMG contains .DS_Store"
fi
if find "$dmg_mount" \( -name '._*' -o -name '__MACOSX' \) -print -quit | rg -q .; then
    die "Final DMG contains macOS metadata files"
fi
codesign --verify --deep --strict --verbose=4 "$dmg_app"
xcrun stapler validate "$dmg_app"
dmg_gatekeeper_output="$run_dir/dmg-gatekeeper.txt"
if ! spctl --assess --type execute --verbose=4 "$dmg_app" >"$dmg_gatekeeper_output" 2>&1; then
    cat "$dmg_gatekeeper_output" >&2
    die "Gatekeeper rejected the app mounted from the final DMG"
fi
cat "$dmg_gatekeeper_output"
rg -q 'accepted' "$dmg_gatekeeper_output" || die "Gatekeeper did not accept the app mounted from the final DMG"
rg -q 'Notarized Developer ID' "$dmg_gatekeeper_output" || die "DMG app is not reported as Notarized Developer ID"
launch_smoke "$dmg_app"
hdiutil detach "$dmg_mount" -force >/dev/null
dmg_attached=0

artifact_sha256="$(shasum -a 256 "$final_zip" | awk '{print $1}')"
artifact_size="$(/usr/bin/stat -f %z "$final_zip")"
dmg_sha256="$(shasum -a 256 "$final_dmg" | awk '{print $1}')"
dmg_size="$(/usr/bin/stat -f %z "$final_dmg")"
printf '%s\n' "Final artifact: $final_zip"
printf '%s\n' "Artifact size: $artifact_size bytes"
printf '%s\n' "SHA-256: $artifact_sha256"
printf '%s\n' "Final artifact: $final_dmg"
printf '%s\n' "DMG size: $dmg_size bytes"
printf '%s\n' "DMG SHA-256: $dmg_sha256"
printf '%s\n' "STAGE_6_5_RELEASE_PIPELINE=PASS"

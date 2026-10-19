#!/bin/sh
# Local App Sandbox test build of the AppStore configuration (App Store plan,
# stage 1). Run on a Mac with Xcode; no Apple account is needed.
#
# Safety: the real DMG Terento data is never moved or changed.
#   - The test app uses its own bundle ID, app.terento.mac.sandboxtest, so it
#     gets its own container: ~/Library/Containers/app.terento.mac.sandboxtest.
#   - Its migration manifest (container-migration.sandboxtest.plist) copies only
#     items from a throwaway seed folder,
#     ~/Library/Application Support/TerentoSandboxTestSeed.
#   - With --seed copy (the default) the seed is a read-only copy of the DMG
#     data, so the test can show your maps as managed. The originals stay.
#
# Usage: Packaging/AppStore/build-local-sandbox-test.sh [--seed copy|empty] [--reset]
#   --seed empty  start with no migrated data (a first-time App Store user)
#   --reset       delete the previous test container and seed first, so the
#                 migration runs again on the next launch
set -eu

test_bundle_id="app.terento.mac.sandboxtest"
seed_mode="copy"
reset=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --seed)
            [ "$#" -ge 2 ] || { echo "--seed needs copy or empty" >&2; exit 2; }
            seed_mode="$2"
            shift 2
            ;;
        --reset)
            reset=1
            shift
            ;;
        -h|--help)
            sed -n '2,19p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done
case "$seed_mode" in copy|empty) ;; *) echo "--seed must be copy or empty" >&2; exit 2 ;; esac

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[ "$(uname -s)" = "Darwin" ] || die "Run this on macOS with Xcode."
command -v xcodebuild >/dev/null 2>&1 || die "xcodebuild not found. Install Xcode and run: sudo xcode-select -s /Applications/Xcode.app"

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
test_manifest="$repo_root/Packaging/AppStore/container-migration.sandboxtest.plist"
application_support="$HOME/Library/Application Support"
real_data="$application_support/Terento"
seed="$application_support/TerentoSandboxTestSeed"
container="$HOME/Library/Containers/$test_bundle_id"
# Fixed path, never configurable: the cleanup command below deletes it.
output="$HOME/TerentoSandboxTest"
app="$output/DerivedData/Build/Products/AppStore/Terento.app"

# Every migration source must be inside the seed folder. This guard is the
# reason the real DMG data is never a migration source in this test.
index=0
while source="$(/usr/bin/plutil -extract "Move.$index.0" raw -o - "$test_manifest" 2>/dev/null)"; do
    case "$source" in
        '${ApplicationSupport}/TerentoSandboxTestSeed/'*) ;;
        *) die "Test migration source is outside the seed folder: $source" ;;
    esac
    destination="$(/usr/bin/plutil -extract "Move.$index.1" raw -o - "$test_manifest")"
    case "$destination" in
        '${ApplicationSupport}/Terento/'*) ;;
        *) die "Unexpected test migration destination: $destination" ;;
    esac
    index=$((index + 1))
done
[ "$index" -gt 0 ] || die "Could not read $test_manifest"

if /usr/bin/pgrep -x Terento >/dev/null 2>&1; then
    die "Quit Terento first (the DMG app and any earlier test app). Only one app may use the watch."
fi

if [ "$reset" -eq 1 ]; then
    echo "Removing the previous test container and seed (test data only)..."
    rm -rf "$seed"
    if ! rm -rf "$container" 2>/dev/null || [ -e "$container" ]; then
        echo "Could not delete $container."
        echo "Delete it in Finder (Go > Go to Folder > ~/Library/Containers), then run this script again."
        exit 1
    fi
fi

if [ -e "$container" ]; then
    echo "NOTE: $container already exists."
    echo "      macOS migrates data only when it creates the container, so no migration will run."
    echo "      Run again with --reset to test the migration."
elif [ -e "$seed" ]; then
    echo "Using the existing seed: $seed"
else
    mkdir -p "$seed"
    chmod 700 "$seed"
    if [ "$seed_mode" = "copy" ] && [ -d "$real_data" ]; then
        echo "Copying DMG data into the seed (read-only; the originals stay in place)..."
        for item in .device-key-secret devices failed-install-recovery.json MutationEvidence \
            installation-evidence.json update-evidence.json map-statistics-events.json; do
            if [ -e "$real_data/$item" ]; then
                /usr/bin/ditto "$real_data/$item" "$seed/$item"
                echo "  copied $item"
            fi
        done
    else
        echo "Empty seed: the test app starts like a first-time user."
    fi
fi

# Local test builds carry the -local release label (app/TerentoCore/AGENTS.md).
marketing_version="$(sed -n 's/^[[:space:]]*MARKETING_VERSION = \(.*\);$/\1/p' \
    "$repo_root/Terento.xcodeproj/project.pbxproj" | sed -n '1p')"
[ -n "$marketing_version" ] || die "Could not read MARKETING_VERSION"

echo "Building the AppStore configuration (ad-hoc signed, bundle ID $test_bundle_id)..."
mkdir -p "$output"
xcodebuild \
    -project "$repo_root/Terento.xcodeproj" \
    -scheme Terento \
    -configuration AppStore \
    -sdk macosx \
    -derivedDataPath "$output/DerivedData" \
    ARCHS=arm64 \
    NATIVE_ARCH_ACTUAL=arm64 \
    CODE_SIGNING_ALLOWED=YES \
    CODE_SIGN_IDENTITY=- \
    PRODUCT_BUNDLE_IDENTIFIER="$test_bundle_id" \
    TERENTO_RELEASE_LABEL="$marketing_version-local" \
    TERENTO_CONTAINER_MIGRATION_MANIFEST="$test_manifest" \
    build >"$output/xcodebuild.log" 2>&1 || {
    tail -n 60 "$output/xcodebuild.log" >&2
    die "Build failed. Full log: $output/xcodebuild.log"
}

[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")" = "$test_bundle_id" ] \
    || die "Built app has the wrong bundle ID. Do not open it."
/usr/bin/cmp -s "$test_manifest" "$app/Contents/Resources/container-migration.plist" \
    || die "Built app does not carry the seed-only migration manifest. Do not open it."
/usr/bin/codesign --verify --deep --strict "$app" || die "Signature check failed."

echo
echo "App entitlements:"
/usr/bin/codesign -d --entitlements - --xml "$app" 2>/dev/null | /usr/bin/plutil -p - || true
echo "Helper entitlements (must be exactly app-sandbox + inherit):"
/usr/bin/codesign -d --entitlements - --xml "$app/Contents/MacOS/TerentoFinishingWorker" 2>/dev/null \
    | /usr/bin/plutil -p - || true

cat <<EOF

Built: $app

Next steps
1. Keep the DMG Terento and MacDroid (or other MTP apps) closed.
2. Open the test app WITHOUT the watch connected:
     open "$app"
   A3: the normal "connect your watch" screen appears.
   Migration (B6): this folder now holds the migrated files:
     ls -la "$container/Data/Library/Application Support/Terento"
   Apple documents the migration as a copy, so the seed may still hold the
   originals; that is not a failure. Note which happened:
     ls -la "$seed"
3. Connect the watch.
   A1: Terento shows the watch model, free space and the maps on it.
   With --seed copy, maps the DMG app installed show as managed by Terento.
4. A2: install one small catalog map that is not on the watch yet, and wait
   until Terento says it is done. While it verifies, this shows the helper:
     pgrep -fl TerentoFinishingWorker
   Remove that test map afterwards with this same test app. Do not update or
   remove maps that the DMG app manages: the DMG app's records are not changed
   by this test (the test app works on a copy).
5. A5: start another install, and while it verifies choose Terento > Quit,
   then "Quit anyway". Then this must print nothing:
     pgrep -fl TerentoFinishingWorker
   Also after a normal Quit, and after a force quit during verification
   (Activity Monitor > Force Quit): the helper must be gone within 1 second.
6. If something is blocked, collect the sandbox messages:
     log show --last 15m --predicate 'eventMessage CONTAINS "Sandbox" AND eventMessage CONTAINS "Terento"'

To repeat the migration test after a rebuild, quit the test app and run:
  Packaging/AppStore/build-local-sandbox-test.sh --reset
Every rebuild has a new ad-hoc signature; if macOS asks whether Terento may
access data from other apps, use --reset instead of allowing it.

To remove everything this test created:
  rm -rf "$seed" "$output"
  and delete $container in Finder.
EOF

#!/bin/sh
# Xcode build phase for the AppStore configuration only. Debug and Release
# (the DMG/GitHub build) leave TERENTO_APP_STORE_SANDBOX unset and return here
# without touching the bundle.
#
# For the AppStore configuration it:
#   1. embeds the sandboxed finishing helper: a copy of the app executable at
#      Contents/MacOS/TerentoFinishingWorker. Under App Sandbox a child process
#      must be a separate executable signed with exactly app-sandbox + inherit;
#      the app's own executable cannot be relaunched as the worker;
#   2. embeds a container migration manifest only when one is requested:
#      TERENTO_CONTAINER_MIGRATION_MANIFEST (the local sandbox test passes its
#      seed-only manifest), or the production manifest during `archive`.
#      An ordinary build never embeds the production manifest, so running it
#      can never migrate the real DMG data;
#   3. declares ITSAppUsesNonExemptEncryption = NO in the app's Info.plist;
#   4. signs nested code inside-out when code signing is allowed: both bundled
#      dylibs and the helper. Xcode then signs the app itself.
set -eu

if [ "${TERENTO_APP_STORE_SANDBOX:-NO}" != "YES" ]; then
    exit 0
fi

helper_name="TerentoFinishingWorker"
helper_identifier="${PRODUCT_BUNDLE_IDENTIFIER}.${helper_name}"
contents="${TARGET_BUILD_DIR}/${CONTENTS_FOLDER_PATH}"
main_executable="${TARGET_BUILD_DIR}/${EXECUTABLE_PATH}"
helper="${contents}/MacOS/${helper_name}"
helper_entitlements="${SRCROOT}/app/Terento/TerentoFinishingWorker-AppStore.entitlements"
production_manifest="${SRCROOT}/Packaging/AppStore/container-migration.plist"
embedded_manifest="${contents}/Resources/container-migration.plist"

[ -f "$main_executable" ] || { echo "error: app executable is missing: $main_executable" >&2; exit 1; }
[ -f "$helper_entitlements" ] || { echo "error: helper entitlements are missing" >&2; exit 1; }
for library in libmtp.9.dylib libusb-1.0.0.dylib; do
    [ -f "${contents}/Frameworks/${library}" ] || {
        echo "error: bundled ${library} is missing from Contents/Frameworks" >&2
        exit 1
    }
done

# 1. The helper is byte-for-byte the app executable before signing. It runs
# only MTPFinishingWorker.runIfRequested() and exits; it never starts the UI.
/bin/rm -f "$helper"
/bin/cp "$main_executable" "$helper"
/bin/chmod 755 "$helper"

# 2. Container migration manifest.
manifest="${TERENTO_CONTAINER_MIGRATION_MANIFEST:-}"
if [ -z "$manifest" ] && [ "${ACTION:-build}" = "install" ]; then
    manifest="$production_manifest"
fi
/bin/rm -f "$embedded_manifest"
if [ -n "$manifest" ]; then
    [ -f "$manifest" ] || { echo "error: container migration manifest not found: $manifest" >&2; exit 1; }
    /usr/bin/plutil -lint "$manifest" >/dev/null
    /bin/cp "$manifest" "$embedded_manifest"
    echo "Embedded container migration manifest: $manifest"
elif [ "$PRODUCT_BUNDLE_IDENTIFIER" = "app.terento.mac" ]; then
    echo "warning: this AppStore build has no container migration manifest. Running it creates ~/Library/Containers/app.terento.mac without migrating DMG data, and a later migration test with this bundle ID would then be skipped. Use Packaging/AppStore/build-local-sandbox-test.sh for local runs."
fi

# Terento uses only the encryption built into macOS (HTTPS, CommonCrypto and
# CryptoKit hashes), so App Store Connect needs no export compliance answer.
info_plist="${contents}/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :ITSAppUsesNonExemptEncryption" "$info_plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :ITSAppUsesNonExemptEncryption bool false" "$info_plist"

# 3. Nested code signing. Xcode does not sign files that build phases copy.
identity="${EXPANDED_CODE_SIGN_IDENTITY:-}"
if [ -z "$identity" ] && [ "${CODE_SIGN_IDENTITY:-}" = "-" ]; then
    identity="-"
fi
if [ "${CODE_SIGNING_ALLOWED:-NO}" != "YES" ] || [ -z "$identity" ]; then
    echo "Code signing is not allowed for this build; nested code left unsigned."
    exit 0
fi

runtime_option=""
if [ "${ENABLE_HARDENED_RUNTIME:-NO}" = "YES" ]; then
    runtime_option="--options=runtime"
fi

for library in libusb-1.0.0.dylib libmtp.9.dylib; do
    # shellcheck disable=SC2086
    /usr/bin/codesign --force --sign "$identity" --timestamp=none \
        $runtime_option ${OTHER_CODE_SIGN_FLAGS:-} "${contents}/Frameworks/${library}"
done

# The helper gets exactly app-sandbox + inherit and nothing else.
# shellcheck disable=SC2086
/usr/bin/codesign --force --sign "$identity" --timestamp=none \
    $runtime_option ${OTHER_CODE_SIGN_FLAGS:-} \
    --identifier "$helper_identifier" \
    --entitlements "$helper_entitlements" \
    "$helper"
echo "Signed nested code with identity: $identity"

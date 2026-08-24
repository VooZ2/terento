# Terento Developer ID signing

This procedure is for the Stage 6.3 local signing validation of the
production macOS app. It uses a Developer ID Application identity already
available in the local Keychain. Certificates, private keys, passwords, and
Keychain exports must never be stored in this repository.

## Preconditions

Build an unsigned Release app with the production Xcode target:

```sh
xcodebuild \
  -project Terento.xcodeproj \
  -scheme Terento \
  -configuration Release \
  -sdk macosx \
  -derivedDataPath /private/tmp/terento-derived \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build
```

Confirm that the expected identity is available before signing:

```sh
security find-identity -v -p codesigning
```

The production Team ID is `VXALAZU3B5`. The exact identity name is selected
from the local Keychain and must be a `Developer ID Application` identity.

## Signing order

Set `APP_PATH` to the unsigned `Terento.app` produced by the Release build and
set `SIGNING_IDENTITY` to the approved local Developer ID Application identity.
Sign nested code from the inside out. Do not use `--deep` as the signing
operation.

```sh
APP_PATH="/private/tmp/terento-derived/Build/Products/Release/Terento.app"
SIGNING_IDENTITY="Developer ID Application: Gediminas Cicinskas (VXALAZU3B5)"
ENTITLEMENTS_PATH="app/Terento/Terento.entitlements"

codesign --force --verbose --timestamp --options runtime \
  --sign "$SIGNING_IDENTITY" \
  "$APP_PATH/Contents/Frameworks/libusb-1.0.0.dylib"

codesign --force --verbose --timestamp --options runtime \
  --sign "$SIGNING_IDENTITY" \
  "$APP_PATH/Contents/Frameworks/libmtp.9.dylib"

codesign --force --verbose --timestamp --options runtime \
  --entitlements "$ENTITLEMENTS_PATH" \
  --sign "$SIGNING_IDENTITY" \
  "$APP_PATH"
```

The app entitlements file is intentionally minimal. Do not add
`com.apple.security.get-task-allow`, debugger permissions, sandbox exceptions,
or other entitlements without a separately reviewed requirement.

## Verification

Verify every nested library and the app independently, then verify the bundle
recursively:

```sh
codesign --verify --strict --verbose=4 \
  "$APP_PATH/Contents/Frameworks/libusb-1.0.0.dylib"
codesign --verify --strict --verbose=4 \
  "$APP_PATH/Contents/Frameworks/libmtp.9.dylib"
codesign --verify --strict --verbose=4 "$APP_PATH"
codesign --verify --deep --strict --verbose=4 "$APP_PATH"

codesign -dvvv "$APP_PATH" 2>&1
codesign -d --entitlements :- "$APP_PATH" 2>&1
spctl --assess --type execute --verbose=4 "$APP_PATH"
```

The signature details must show the Developer ID Application authority,
Team ID `VXALAZU3B5`, a secure timestamp, and the Hardened Runtime flag. The
entitlements output must not contain `get-task-allow`. Before notarization,
`spctl` may report `Unnotarized Developer ID`; that result is expected at
Stage 6.3 and is not a notarization attempt.

Also inspect all app and bundled-library load commands with `otool -L` and
confirm that production runtime paths contain no Homebrew, developer-home, or
other machine-specific library paths. The only non-system native libraries
should resolve through the app's `@rpath` Frameworks directory.

This document does not cover DMG/PKG creation, public release packaging,
upload, or publication. Those actions belong to later release stages.

## Notarization and stapling

Stage 6.4 uses the local Keychain profile `TerentoNotary`. The profile name is
safe to document; its password or API key is not. Create and validate the
profile outside the repository before submission.

Create a temporary archive from the freshly signed app with `ditto`, then
submit it and wait for Apple to return a final status:

```sh
ditto -c -k --keepParent "$APP_PATH" "/private/tmp/Terento-notarization.zip"

xcrun notarytool submit \
  "/private/tmp/Terento-notarization.zip" \
  --keychain-profile "TerentoNotary" \
  --wait
```

Record the submission ID. If the status is `Invalid` or `Rejected`, retrieve
the Apple log and stop before stapling:

```sh
xcrun notarytool info "$SUBMISSION_ID" \
  --keychain-profile "TerentoNotary"
xcrun notarytool log "$SUBMISSION_ID" \
  --keychain-profile "TerentoNotary" \
  --output-format json
```

Only after Apple returns `Accepted`:

```sh
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
codesign --verify --deep --strict --verbose=4 "$APP_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH"
```

The temporary ZIP must remain outside the repository. Do not create a DMG,
PKG, public release, or upload from this procedure.

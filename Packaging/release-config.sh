#!/bin/sh

# Canonical Stage 6.5 release configuration.
# Version and build are read from the Xcode Release build settings and the
# generated app Info.plist. They are intentionally not duplicated here.

RELEASE_PROJECT="Terento.xcodeproj"
RELEASE_SCHEME="Terento"
RELEASE_CONFIGURATION="Release"
RELEASE_PRODUCT_NAME="Terento"
RELEASE_BUNDLE_IDENTIFIER="app.terento.mac"
RELEASE_TEAM_ID="VXALAZU3B5"
RELEASE_DEPLOYMENT_TARGET="13.0"
RELEASE_ARCH="arm64"
RELEASE_SIGNING_IDENTITY="Developer ID Application: Gediminas Cicinskas (VXALAZU3B5)"
RELEASE_NOTARY_PROFILE="TerentoNotary"
RELEASE_ENTITLEMENTS="app/Terento/Terento.entitlements"
RELEASE_NATIVE_BUILD_SCRIPT="Packaging/NativeDependencies/build.sh"
RELEASE_VERSION_SETTING="MARKETING_VERSION"
RELEASE_BUILD_SETTING="CURRENT_PROJECT_VERSION"
RELEASE_OUTPUT_DIR="dist"

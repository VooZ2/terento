#!/bin/zsh
set -euo pipefail

# Sampled removal proof for Terento-managed maps: the Swift recording model and
# the production native delete entrypoints against a fake libmtp (no USB).
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-removal-proof-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

swiftc \
    -module-name TerentoRemovalProofTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/TerentoManifestStore.swift" \
    "$project_root/Tests/TerentoPoCTests/ManagedRemovalProofTests.swift" \
    -o "$build_dir/removal-proof-tests"
"$build_dir/removal-proof-tests"

mtp_prefix="$(brew --prefix libmtp)"
usb_prefix="$(brew --prefix libusb)"
clang -Wno-deprecated-declarations -I "$project_root/Sources/LibMTPBridge/include" \
  -I "$mtp_prefix/include" -I "$usb_prefix/include/libusb-1.0" \
  "$project_root/Tests/NativeRemovalProofTests.c" -L "$mtp_prefix/lib" -lmtp \
  -L "$usb_prefix/lib" -lusb-1.0 -framework CoreFoundation \
  -o "$build_dir/native-removal-proof-tests"
"$build_dir/native-removal-proof-tests"

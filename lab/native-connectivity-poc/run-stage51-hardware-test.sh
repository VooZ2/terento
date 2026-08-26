#!/bin/zsh
set -euo pipefail

project_root="${0:A:h}"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage51-hardware.XXXXXX")"
binary_path="$build_dir/TerentoStage51HardwareTest"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  swift build --product TerentoPoC
fi

if grep -En "terento_mtp_(write_test|delete_test|install_map_file|delete_managed_map)|SendObject|DeleteObject|MoveObject|RenameObject" \
    "$project_root/Sources/TerentoPoC/Installation/MTPReadBackupAdapter.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ReadBackupAdapter.swift"; then
  print -u2 "FAIL: Stage 5.1 read backup path contains a write/delete surface"
  exit 1
fi

swiftc \
  -module-name TerentoStage51HardwareTest \
  -I "$bridge_module_dir" \
  -module-cache-path "$module_cache_dir" \
  "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/MapCapability.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
  "$project_root/Sources/TerentoPoC/MTPTransport/MTPOperationGate.swift" \
  "$project_root/Sources/TerentoPoC/MTPTransport/MTPTransport.swift" \
  "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
  "$project_root/Sources/TerentoPoC/Installation/StoragePlanner.swift" \
  "$project_root/Sources/TerentoPoC/Installation/MapLifecycle.swift" \
  "$project_root/Sources/TerentoPoC/Installation/InstallProfile.swift" \
  "$project_root/Sources/TerentoPoC/Installation/TerentoManifestStore.swift" \
  "$project_root/Sources/TerentoPoC/Installation/ReadBackupAdapter.swift" \
  "$project_root/Sources/TerentoPoC/Installation/MTPMapOperationProfileBridge.swift" \
  "$project_root/Sources/TerentoPoC/Installation/MTPReadBackupAdapter.swift" \
  "$project_root/Tests/Stage51HardwareBackupMain.swift" \
  "$bridge_object" \
  -L "$libmtp_prefix/lib" \
  -lmtp \
  -L "$libusb_prefix/lib" \
  -lusb-1.0 \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -Xlinker -rpath -Xlinker "$libusb_prefix/lib" \
  -o "$binary_path"

if [[ "${1:-}" == "--compile-only" ]]; then
  print "Stage 5.1 Hardware Test: compile PASS"
  exit 0
fi

"$binary_path"

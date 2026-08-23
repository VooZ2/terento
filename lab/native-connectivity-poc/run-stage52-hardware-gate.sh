#!/bin/zsh
set -euo pipefail

project_root="${0:A:h}"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage52-hardware.XXXXXX")"
binary_path="$build_dir/TerentoStage52HardwareGate"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  swift build --product TerentoPoC
fi

swiftc \
  -module-name TerentoStage52HardwareGate \
  -I "$bridge_module_dir" \
  -module-cache-path "$module_cache_dir" \
  "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/DeviceIdentity.swift" \
  "$project_root/Sources/TerentoPoC/Compatibility/GarminDeviceIdentityAdapter.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapPresentation.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapComparison.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapInventoryList.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
  "$project_root/Sources/TerentoPoC/MTPTransport/MTPTransport.swift" \
  "$project_root"/Sources/TerentoPoC/Installation/*.swift \
  "$project_root/Tests/Stage52HardwareDeleteMain.swift" \
  "$bridge_object" \
  -L "$libmtp_prefix/lib" \
  -lmtp \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -o "$binary_path"

if [[ "${1:-}" == "--compile-only" ]]; then
  print "Stage 5.2 Hardware Gate: compile PASS"
  exit 0
fi

"$binary_path" "$@"

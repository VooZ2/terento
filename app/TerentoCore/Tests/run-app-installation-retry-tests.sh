#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-installation-retry-tests.XXXXXX")"
binary_path="$build_dir/installation-retry-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so retry tests can link LibMTPBridge…"
  swift build --build-system native --package-path "$project_root" --product TerentoPoC
fi

sources=()
while IFS= read -r source_file; do
  sources+=("$source_file")
done < <(
  find "$project_root/Sources/TerentoPoC" -name '*.swift' \
    ! -name 'TerentoPoCApp.swift' \
    ! -name 'ContentView.swift' \
    -print | sort
)

# Engine-level retry tests use local temp workspaces only; no device or network.
swiftc -D TERENTO_TESTING -target "${swiftpm_arch}-apple-macosx13.0" \
  -parse-as-library \
  -module-name TerentoInstallationRetryTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" -lmtp \
  -L "$libusb_prefix/lib" -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/InstallationRetryTests.swift" \
  -o "$binary_path"

"$binary_path"

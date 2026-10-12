#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
build_dir="$(mktemp -d /private/tmp/terento-local-managed-update.XXXXXX)"
trap 'rm -rf "$build_dir"' EXIT
mtp_prefix="$(brew --prefix libmtp)"
usb_prefix="$(brew --prefix libusb)"
clang -c -Wno-deprecated-declarations -I Sources/LibMTPBridge/include \
  -I "$mtp_prefix/include" -I "$usb_prefix/include/libusb-1.0" \
  Tests/NativeCleanupDenyFixture.c -o "$build_dir/bridge.o"
printf 'module LibMTPBridge { header "%s/Sources/LibMTPBridge/include/MTPBridge.h" export * }\n' "$PWD" > "$build_dir/module.modulemap"
sources=()
while IFS= read -r source; do sources+=("$source"); done < <(
  find Sources/TerentoPoC -type f -name '*.swift' | grep -Ev '/Views/|/TerentoPoCApp\.swift$' | sort
)
# macOS bash 3.2 can exit 0 on an empty array under set -u; never pass without sources.
(( ${#sources[@]} )) || { echo "FAIL: no TerentoPoC Swift sources found" >&2; exit 1; }
swiftc -module-cache-path "$build_dir/module-cache" -parse-as-library -module-name LocalManagedUpdateSimulationTests \
  -I "$build_dir" -L "$mtp_prefix/lib" -lmtp -L "$usb_prefix/lib" -lusb-1.0 -framework CoreFoundation \
  "$build_dir/bridge.o" "${sources[@]}" Tests/TerentoPoCTests/LocalManagedUpdateSimulationTests.swift \
  -o "$build_dir/tests"
mkdir -p "$build_dir/home"
CFFIXED_USER_HOME="$build_dir/home" "$build_dir/tests"

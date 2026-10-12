#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
build_dir="$(mktemp -d /private/tmp/terento-prefix-session.XXXXXX)"
trap 'rm -rf "$build_dir"' EXIT
mtp_prefix="$(brew --prefix libmtp)"
usb_prefix="$(brew --prefix libusb)"
clang -Wno-deprecated-declarations -I Sources/LibMTPBridge/include \
  -I "$mtp_prefix/include" -I "$usb_prefix/include/libusb-1.0" \
  Tests/NativePrefixSessionTests.c -L "$mtp_prefix/lib" -lmtp \
  -L "$usb_prefix/lib" -lusb-1.0 -framework CoreFoundation -o "$build_dir/prefix-tests"
"$build_dir/prefix-tests"
# Link the actual Swift transport to the same offline native fixture.
clang -c -DTERENTO_PREFIX_SWIFT_DRIVER -Wno-deprecated-declarations \
  -I Sources/LibMTPBridge/include -I "$mtp_prefix/include" -I "$usb_prefix/include/libusb-1.0" \
  Tests/NativePrefixSessionTests.c -o "$build_dir/prefix-fixture.o"
printf 'module LibMTPBridge { header "%s/Sources/LibMTPBridge/include/MTPBridge.h" export * }\n' "$PWD" > "$build_dir/module.modulemap"
sources=()
while IFS= read -r source; do sources+=("$source"); done < <(
  find Sources/TerentoPoC -type f -name '*.swift' | \
  grep -Ev '/Views/|/TerentoPoCApp\.swift$' | sort
)
# macOS bash 3.2 can exit 0 on an empty array under set -u; never pass without sources.
(( ${#sources[@]} )) || { echo "FAIL: no TerentoPoC Swift sources found" >&2; exit 1; }
swiftc -module-cache-path "$build_dir/module-cache" -parse-as-library -module-name TerentoPrefixSessionTests -I "$build_dir" \
  -L "$mtp_prefix/lib" -lmtp -L "$usb_prefix/lib" -lusb-1.0 -framework CoreFoundation \
  "$build_dir/prefix-fixture.o" "${sources[@]}" Tests/TerentoPoCTests/PrefixSessionWiringTests.swift \
  -o "$build_dir/prefix-swift-tests"
"$build_dir/prefix-swift-tests"

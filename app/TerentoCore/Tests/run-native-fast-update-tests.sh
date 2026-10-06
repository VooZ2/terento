#!/bin/zsh
set -euo pipefail

# Safe Update content checks of a Terento-managed map: the recorded sampled
# proof of the installed map, the install-equivalent sampled read-back of the
# new map and the sampled old-map removal, against a fake libmtp (no USB).
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-fast-update-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

mtp_prefix="$(brew --prefix libmtp)"
usb_prefix="$(brew --prefix libusb)"
clang -Wno-deprecated-declarations -I "$project_root/Sources/LibMTPBridge/include" \
  -I "$mtp_prefix/include" -I "$usb_prefix/include/libusb-1.0" \
  "$project_root/Tests/NativeFastUpdateTests.c" -L "$mtp_prefix/lib" -lmtp \
  -L "$usb_prefix/lib" -lusb-1.0 -framework CoreFoundation \
  -o "$build_dir/native-fast-update-tests"
"$build_dir/native-fast-update-tests"

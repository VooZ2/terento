#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
BUILD_DIR="$(mktemp -d /private/tmp/terento-native-mutation-build.XXXXXX)"
trap 'rm -rf "$BUILD_DIR"' EXIT
MTP_PREFIX="$(brew --prefix libmtp)"
USB_PREFIX="$(brew --prefix libusb)"
clang -Wno-deprecated-declarations -I Sources/LibMTPBridge/include \
  -I "$MTP_PREFIX/include" -I "$USB_PREFIX/include/libusb-1.0" \
  Tests/NativeMutationAuthorizationTests.c -L "$MTP_PREFIX/lib" -lmtp \
  -L "$USB_PREFIX/lib" -lusb-1.0 -framework CoreFoundation \
  -o "$BUILD_DIR/native-mutation-tests"
"$BUILD_DIR/native-mutation-tests"

#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_root="$PWD"
build_dir="$(mktemp -d /private/tmp/terento-cleanup-refusal.XXXXXX)"
trap 'rm -rf "$build_dir"' EXIT
mtp_prefix="$(brew --prefix libmtp)"
usb_prefix="$(brew --prefix libusb)"
clang -c -Wno-deprecated-declarations -I Sources/LibMTPBridge/include \
  -I "$mtp_prefix/include" -I "$usb_prefix/include/libusb-1.0" \
  Tests/NativeCleanupDenyFixture.c -o "$build_dir/cleanup-fixture.o"
printf 'module LibMTPBridge { header "%s/Sources/LibMTPBridge/include/MTPBridge.h" export * }\n' "$PWD" > "$build_dir/module.modulemap"
sources=()
while IFS= read -r source; do sources+=("$source"); done < <(
  rg --files Sources/TerentoPoC -g '*.swift' | grep -Ev '/Views/|/TerentoPoCApp\.swift$' | sort
)
swiftc -D TERENTO_PRODUCTION_CLEANUP_TEST -module-cache-path "$build_dir/module-cache" \
  -parse-as-library -module-name TerentoProductionCleanupTests -I "$build_dir" \
  -L "$mtp_prefix/lib" -lmtp -L "$usb_prefix/lib" -lusb-1.0 -framework CoreFoundation \
  "$build_dir/cleanup-fixture.o" "${sources[@]}" Tests/TerentoPoCTests/Stage42InstallationTests.swift \
  -o "$build_dir/cleanup-tests"
"$build_dir/cleanup-tests"

if grep -En "LIBMTP|MTPBridge|SendObject|DeleteObject|MoveObject|RenameObject" \
    "$project_root/Sources/TerentoPoC/Installation/MapInstallationCoordinator.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationTransportProtocols.swift"; then
    printf "%s\n" "FAIL: Stage 4.2 domain coordinator contains a native transport dependency" >&2
    exit 1
fi

printf "%s\n" "PASS: Stage 4.2 domain coordinator is transport-injected and read-only in tests"

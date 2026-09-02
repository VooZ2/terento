#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-connection-lifecycle-tests.XXXXXX")"
binary_path="$build_dir/connection-lifecycle-tests"

swiftc \
    -module-name TerentoConnectionLifecycleTests \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift" \
    "$project_root/Tests/TerentoPoCTests/ConnectionLifecycleTests.swift" \
    -o "$binary_path"

"$binary_path"

if grep -Eiq 'SendObject|DeleteObject|MoveObject|RenameObject|terento_mtp_install|terento_mtp_delete' \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift" \
    "$project_root/Sources/TerentoPoC/DeviceEngine/DeviceEngine.swift" \
    "$project_root/Sources/TerentoPoC/MTPTransport/MTPTransport.swift"; then
    print -u2 "FAIL: connection lifecycle boundary contains a write/delete operation"
    exit 1
fi

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
if [[ "$(grep -Fc 'deviceEngine.ejectDevice()' "$connect_screen")" -ne 1 ]]; then
    print -u2 "FAIL: Device and sidebar eject do not share one DeviceEngine path"
    exit 1
fi

if ! grep -Fq 'onEject: performSafeEject' "$connect_screen" \
    || ! grep -Fq 'canEject: canSafelyEject' "$connect_screen" \
    || ! grep -Fq '"Eject Garmin"' "$connect_screen" \
    || ! grep -Fq '.accessibilityLabel("Eject Garmin")' "$connect_screen"; then
    print -u2 "FAIL: global sidebar Safe Eject integration is incomplete"
    exit 1
fi

if ! grep -Fq 'onChange(of: lifecycleViewModel.isBusy)' "$connect_screen" \
    || ! grep -Fq '&& !lifecycleViewModel.isBusy' "$connect_screen"; then
    print -u2 "FAIL: lifecycle operations do not pause background presence monitoring"
    exit 1
fi

device_engine="$project_root/Sources/TerentoPoC/DeviceEngine/DeviceEngine.swift"
if ! grep -Fq 'activeNativeReadTask == nil' "$device_engine" \
    || ! grep -Fq 'activeNativePresenceTask == nil' "$device_engine" \
    || ! grep -Fq 'publishOperationAvailability()' "$device_engine"; then
    print -u2 "FAIL: native presence/read availability does not refresh Eject state"
    exit 1
fi

if ! grep -Fq 'DevicePresenceReader' \
    "$project_root/Sources/TerentoPoC/MTPTransport/MTPTransport.swift" \
    || ! grep -Fq 'terento_mtp_probe_garmin_presence' \
        "$project_root/Sources/LibMTPBridge/MTPBridge.c"; then
    print -u2 "FAIL: background presence monitoring still opens full libmtp sessions"
    exit 1
fi

if ! grep -Fq 'startPostEjectPresenceMonitoring()' "$device_engine" \
    || ! grep -Fq 'hasGarminUSBDevice()' "$device_engine" \
    || ! grep -Fq 'handlePhysicalDisconnectAfterEject()' "$device_engine" \
    || ! grep -Fq 'self.readDevice()' "$device_engine"; then
    print -u2 "FAIL: Safe Eject does not return to automatic discovery after physical unplug"
    exit 1
fi

if ! grep -Fq 'waitForGarminUSBPresenceBeforeSnapshot' "$device_engine" \
    || ! grep -Fq 'Garmin returned to USB; waiting for MTP enumeration' "$device_engine" \
    || ! grep -Fq 'try await Task.sleep(for: .milliseconds(750))' "$device_engine"; then
    print -u2 "FAIL: reconnect detection enters MTP before USB presence and enumeration settle"
    exit 1
fi

print "PASS: connection lifecycle boundary has no device write/delete surface"
print "PASS: Device and sidebar Safe Eject share one lifecycle path"
print "PASS: install and lifecycle work pause background presence monitoring"
print "PASS: idle presence monitoring uses a USB-only probe"
print "PASS: Safe Eject monitors physical unplug and restarts discovery"
print "PASS: reconnect waits for USB presence before reopening MTP"

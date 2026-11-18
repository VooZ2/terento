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
    || ! grep -Fq 'activeNativePresenceTasks.isEmpty' "$device_engine" \
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

if ! grep -Fq 'detectionPolicy.usbObserved(count: usbCount' "$device_engine" \
    || ! grep -Fq 'case .settleThenRead:' "$device_engine" \
    || ! grep -Fq 'Garmin returned to USB; waiting for MTP enumeration' "$device_engine" \
    || ! grep -Fq 'try await Task.sleep(for: .milliseconds(750))' "$device_engine"; then
    print -u2 "FAIL: reconnect detection enters MTP before USB presence, or lost its settle-first path"
    exit 1
fi

device_policy="$project_root/Sources/TerentoPoC/DeviceEngine/DeviceStateManager.swift"
if ! grep -Fq 'static let readsImmediatelyOnAppearance = true' "$device_policy" \
    || ! grep -Fq 'return .wait(Self.enumerationSettle)' "$device_policy" \
    || ! grep -Fq 'let isImmediateFirstRead = detectionPolicy.isImmediateFirstRead' "$device_engine"; then
    print -u2 "FAIL: an appearing Garmin is not read at once with the settle kept for a failed first read"
    exit 1
fi

if ! grep -Fq 'IOServiceAddMatchingNotification(' "$device_engine" \
    || ! grep -Fq 'static let garminVendorID = 0x091E' "$device_engine" \
    || ! grep -Fq 'orUSBChangeOn: usbChangeSignal' "$device_engine" \
    || ! grep -Fq 'static let presencePollInterval: TimeInterval = 0.5' "$device_policy" \
    || ! grep -Fq 'transport is BoundedDeviceTransport' "$device_engine"; then
    print -u2 "FAIL: USB change notifications are not wired next to the 0.5 s presence poll"
    exit 1
fi

if grep -Eq 'IOServiceOpen|IOUSBDeviceInterface|USBDeviceOpen|SMAppService|LaunchAgent|launchd' "$device_engine"; then
    print -u2 "FAIL: USB change notifications open a device or install a background service"
    exit 1
fi

print "PASS: connection lifecycle boundary has no device write/delete surface"
print "PASS: Device and sidebar Safe Eject share one lifecycle path"
print "PASS: install and lifecycle work pause background presence monitoring"
print "PASS: idle presence monitoring uses a USB-only probe"
print "PASS: Safe Eject monitors physical unplug and restarts discovery"
if ! grep -Fq 'startReplugWatch()' "$device_engine" \
    || ! grep -Fq 'countGarminUSBDevices()' "$device_engine"; then
    print -u2 "FAIL: a failed check does not restart discovery after a physical replug"
    exit 1
fi

print "PASS: reconnect waits for USB presence before reopening MTP"
print "PASS: an appearing Garmin is read at once; the settle follows only a failed first read"
print "PASS: USB change notifications only wake the presence poll, which stays as the fallback"
print "PASS: a failed check restarts discovery after a physical replug"

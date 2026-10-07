import Foundation

private enum ConnectionLifecycleTestError: Error {
    case failed(String)
}

private func require(
    _ condition: @autoclosure () -> Bool,
    _ message: String
) throws {
    guard condition() else {
        throw ConnectionLifecycleTestError.failed(message)
    }
}

private func testConnectedState() throws {
    var manager = DeviceStateManager()
    manager.beginDetection()
    manager.deviceConnected()

    try require(manager.state == .connected, "device detection should produce connected state")
    try require(manager.hasActiveDevice, "connected state should have an active device")
    try require(manager.canUseDevice, "connected device should be usable")
}

private func testDisconnectInvalidatesDevice() throws {
    var manager = DeviceStateManager()
    manager.beginDetection()
    manager.deviceConnected()
    manager.deviceDisconnected()

    try require(manager.state == .disconnected, "disconnect should produce disconnected state")
    try require(!manager.hasActiveDevice, "disconnect should clear the active device")
    try require(!manager.canUseDevice, "device actions should be unavailable after disconnect")
}

private func testNoStaleDeviceAfterDisconnect() throws {
    var manager = DeviceStateManager()
    manager.beginDetection()
    manager.deviceConnected()
    manager.deviceDisconnected()

    try require(manager.state != .connected, "disconnected device must not remain connected")
    try require(manager.state != .ready, "disconnected device must not remain ready")
    try require(!manager.hasActiveDevice, "cached active-device marker must be cleared")
}

private func testSafeEjectIsReadOnly() throws {
    var manager = DeviceStateManager()
    manager.beginDetection()
    manager.deviceConnected()

    try require(manager.beginEject(), "connected device should allow eject")
    try require(manager.state == .ejecting, "eject should enter ejecting state")

    manager.markSafeToDisconnect()
    try require(manager.state == .safeToDisconnect, "eject should finish at safe-to-disconnect")
    try require(!manager.hasActiveDevice, "safe-to-disconnect must not retain an active device")
    try require(!manager.canUseDevice, "device actions must be disabled after eject")
}

private func testEjectCannotStartWithoutDevice() throws {
    var manager = DeviceStateManager()
    try require(!manager.beginEject(), "eject must be rejected without an active device")
    try require(manager.state == .disconnected, "rejected eject must not change state")
}

private func testPhysicalDisconnectAfterEjectReturnsToDetection() throws {
    var manager = DeviceStateManager()
    manager.beginDetection()
    manager.deviceConnected()

    try require(manager.beginEject(), "connected device should allow eject")
    manager.markSafeToDisconnect()
    manager.deviceDisconnected()

    try require(manager.state == .disconnected, "physical unplug after eject should clear the safe state")
    try require(!manager.hasActiveDevice, "physical unplug after eject must not retain an active device")

    manager.beginDetection()
    try require(manager.state == .detecting, "the app should be able to restart discovery after unplug")
}

private func testSafeEjectPresentationStates() throws {
    try require(
        SafeEjectPresentation.resolve(state: .connected, canEject: true) == .enabled,
        "connected idle device should show enabled eject"
    )
    try require(
        SafeEjectPresentation.resolve(state: .ready, canEject: false) == .disabled,
        "connected device operation should show disabled eject"
    )
    try require(
        SafeEjectPresentation.resolve(state: .detecting, canEject: false) == .hidden,
        "connecting state should hide eject"
    )
    try require(
        SafeEjectPresentation.resolve(state: .disconnected, canEject: false) == .hidden,
        "disconnected state should hide eject"
    )
    try require(
        SafeEjectPresentation.resolve(state: .safeToDisconnect, canEject: false) == .hidden,
        "successful eject should remove the sidebar action"
    )
}

private func testSafeEjectPolicyAcrossOperations() throws {
    try require(
        SafeEjectPolicy.canEject(
            isConnected: true,
            transportAvailable: true,
            mapOperationBusy: false,
            lifecycleOperationBusy: false,
            installationActive: false
        ),
        "connected idle device keeps Eject enabled"
    )
    try require(
        SafeEjectPolicy.canEject(
            isConnected: true,
            transportAvailable: true,
            mapOperationBusy: false,
            lifecycleOperationBusy: false,
            installationActive: false
        ),
        "map selection alone does not disable Eject"
    )
    try require(
        !SafeEjectPolicy.canEject(
            isConnected: true,
            transportAvailable: true,
            mapOperationBusy: false,
            lifecycleOperationBusy: true,
            installationActive: false
        )
            && !SafeEjectPolicy.canEject(
                isConnected: true,
                transportAvailable: true,
                mapOperationBusy: true,
                lifecycleOperationBusy: false,
                installationActive: false
            )
            && !SafeEjectPolicy.canEject(
                isConnected: true,
                transportAvailable: true,
                mapOperationBusy: false,
                lifecycleOperationBusy: false,
                installationActive: true
            ),
        "read, remove/update, and active install disable Eject"
    )
    try require(
        SafeEjectPolicy.canEject(
            isConnected: true,
            transportAvailable: true,
            mapOperationBusy: false,
            lifecycleOperationBusy: false,
            installationActive: false
        ),
        "Eject re-enables after the operation is complete"
    )
}


private func testNoWatchStaysCalmWithoutClock() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    for second in stride(from: 0.0, through: 600.0, by: 0.5) {
        let step = policy.usbObserved(count: 0, now: second)
        try require(step == .wait(DeviceDetectionPolicy.presencePollInterval), "no Garmin on USB only polls")
        try require(policy.phase == .waitingForWatch, "no Garmin keeps the calm waiting phase")
        try require(!policy.connectionClockIsRunning, "no connection clock runs without a Garmin")
        // DeviceEngine.hasWaitedWithoutUSB reads this to add the "Still not showing up?" steps.
        try require(policy.reportedOutcomes.contains(.timeoutNoUSB) == (second >= DeviceDetectionPolicy.connectionWindow),
                    "the USB-absent signal fires once the whole connection window has passed")
    }
    let outcomes = policy.takeNewOutcomes()
    try require(outcomes == [.timeoutNoUSB], "a long USB-absent wait keeps polling calmly and is reported once")
}

private func testClockStartsOnlyWhenGarminAppears() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 0, now: 0)
    _ = policy.usbObserved(count: 0, now: 500)
    try require(policy.takeNewOutcomes() == [.timeoutNoUSB], "the long absent wait was reported before the watch appeared")
    let first = policy.usbObserved(count: 1, now: 500)
    try require(first == .settleThenRead(DeviceDetectionPolicy.enumerationSettle), "a newly present Garmin settles before libmtp")
    try require(policy.connectionDeadline == 620, "the 2-minute clock starts when the Garmin appears")
    try require(policy.phase == .connecting, "a present Garmin enters the connecting phase")
    try require(policy.usbObserved(count: 1, now: 501) == .read, "later attempts read without another settle")
    _ = policy.snapshotFailed(.notYetEnumerated, now: 502)
    try require(policy.phase == .connecting, "one not-yet-enumerated attempt is an ordinary retry")
    try require(policy.usbObserved(count: 1, now: 619) == .read, "the clock has not expired yet")
    try require(policy.usbObserved(count: 1, now: 620) == .fail(.timeoutUSBPresent), "an expired clock with a Garmin present times out")
    try require(policy.takeNewOutcomes() == [.timeoutUSBPresent], "USB-present timeout is reported")
}

private func testUnplugStopsClock() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 1, now: 10)
    try require(policy.connectionClockIsRunning, "clock runs with a Garmin present")
    _ = policy.usbObserved(count: 0, now: 50)
    try require(!policy.connectionClockIsRunning && policy.phase == .waitingForWatch, "unplug returns to calm waiting without a clock")
    try require(policy.usbObserved(count: 1, now: 300) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle), "replug settles again")
    try require(policy.connectionDeadline == 420, "replug starts a fresh 2-minute clock")
}

private func testBriefUSBDropKeepsConnecting() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 1, now: 10)
    _ = policy.snapshotFailed(.notYetEnumerated, now: 12)
    try require(policy.usbObserved(count: 0, now: 15) == .wait(DeviceDetectionPolicy.presencePollInterval), "a brief USB drop keeps polling")
    try require(policy.phase == .connecting, "a watch re-enumerating for a few seconds stays in the connecting state")
    try require(policy.connectionClockIsRunning, "the connection clock keeps running through a brief drop")
    try require(policy.usbObserved(count: 1, now: 18) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle), "the returning watch settles before reading")
    _ = policy.usbObserved(count: 0, now: 19)
    try require(policy.phase == .connecting, "repeated brief drops within the grace window stay calm")
    _ = policy.usbObserved(count: 0, now: 40)
    try require(policy.phase == .waitingForWatch && !policy.connectionClockIsRunning, "a watch gone longer than the grace window returns to waiting")
}

private func testMultipleDevicesShownImmediately() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    try require(policy.usbObserved(count: 2, now: 1) == .wait(DeviceDetectionPolicy.attentionPollInterval), "two Garmins keep polling")
    try require(policy.phase == .needsAttention(.multipleDevices), "two Garmins are shown on the first observation")
    try require(!policy.connectionClockIsRunning, "no timeout runs while two Garmins are shown")
    try require(policy.takeNewOutcomes() == [.multipleDevices], "multiple devices is reported once")
    _ = policy.usbObserved(count: 2, now: 2)
    try require(policy.takeNewOutcomes().isEmpty, "multiple devices is not reported twice")
    try require(policy.usbObserved(count: 1, now: 3) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle), "one Garmin remaining continues automatically")
    try require(policy.phase == .connecting, "attention clears when one Garmin remains")
    _ = policy.snapshotFailed(.multipleDevices, now: 4)
    try require(policy.phase == .needsAttention(.multipleDevices), "native multiple-device result is shown immediately")
}

private func testBusyNeedsConfirmationThenShows() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 1, now: 0)
    try require(policy.snapshotFailed(.busy, now: 1) == .wait(DeviceDetectionPolicy.busyRetryInterval), "busy retries")
    try require(policy.phase == .connecting, "a single open failure is not yet shown as busy")
    _ = policy.snapshotFailed(.busy, now: 3)
    try require(policy.phase == .needsAttention(.busy), "repeated open failures are shown as busy")
    try require(policy.takeNewOutcomes() == [.busy], "busy is reported")
    try require(policy.usbObserved(count: 1, now: 130) == .fail(.busy), "a busy episode that expires ends as busy")
}

private func testNotMTPModeHintAfterRepeatedInvisibility() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 1, now: 0)
    for attempt in 1..<DeviceDetectionPolicy.notMTPModeAfterAttempts {
        _ = policy.snapshotFailed(.notYetEnumerated, now: Double(attempt))
    }
    try require(policy.phase == .connecting, "a briefly invisible Garmin is still enumerating")
    _ = policy.snapshotFailed(.notYetEnumerated, now: 30)
    try require(policy.phase == .connecting, "a watch still preparing file transfer after 30 s is not shown a warning")
    _ = policy.snapshotFailed(.notYetEnumerated, now: 46)
    try require(policy.phase == .needsAttention(.notMTPMode), "a persistently invisible Garmin gets the USB-mode hint")
    try require(policy.takeNewOutcomes() == [.notMTPMode], "not-MTP-mode is reported")
}

private func testStoppedRespondingFailsImmediately() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 1, now: 0)
    try require(policy.snapshotFailed(.stoppedResponding, now: 60) == .fail(.failed), "a bounded read deadline stops detection")
    try require(policy.takeNewOutcomes() == [.failed], "a stalled read is reported as failed")
}

private func testConnectedReportedOnce() throws {
    var policy = DeviceDetectionPolicy(now: 0)
    _ = policy.usbObserved(count: 1, now: 0)
    policy.connected()
    policy.connected()
    try require(policy.takeNewOutcomes() == [.connected], "connected is reported once per episode")
}

@main
struct ConnectionLifecycleTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("connected state", testConnectedState),
            ("disconnect invalidates session and active device", testDisconnectInvalidatesDevice),
            ("no stale connected or ready state remains", testNoStaleDeviceAfterDisconnect),
            ("safe eject transitions to safe-to-disconnect", testSafeEjectIsReadOnly),
            ("eject is unavailable without a device", testEjectCannotStartWithoutDevice),
            ("physical unplug after eject restarts detection", testPhysicalDisconnectAfterEjectReturnsToDetection),
            ("sidebar eject visibility follows connection and lifecycle state", testSafeEjectPresentationStates),
            ("eject policy follows the shared operation state", testSafeEjectPolicyAcrossOperations),
            ("no watch stays calm without a connection clock", testNoWatchStaysCalmWithoutClock),
            ("connection clock starts only when a Garmin appears", testClockStartsOnlyWhenGarminAppears),
            ("unplug stops the connection clock", testUnplugStopsClock),
            ("a brief USB drop while connecting keeps the calm connecting state", testBriefUSBDropKeepsConnecting),
            ("multiple Garmins are shown immediately", testMultipleDevicesShownImmediately),
            ("busy is shown after a confirming retry", testBusyNeedsConfirmationThenShows),
            ("persistently invisible Garmin gets the USB-mode hint", testNotMTPModeHintAfterRepeatedInvisibility),
            ("stalled read stops detection", testStoppedRespondingFailsImmediately),
            ("connected outcome is reported once", testConnectedReportedOnce)
        ]

        do {
            for (name, test) in tests {
                try test()
                print("PASS: \(name)")
            }
            print("PASS: \(tests.count) connection lifecycle tests")
        } catch {
            print("FAIL: \(error)")
            exit(1)
        }
    }
}

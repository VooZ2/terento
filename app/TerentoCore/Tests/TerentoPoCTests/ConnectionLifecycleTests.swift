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
    try require(policy.takeNewOutcomes() == [.timeoutNoUSB], "the long absent wait was reported before the device appeared")
    let first = policy.usbObserved(count: 1, now: 500)
    try require(first == .settleThenRead(DeviceDetectionPolicy.enumerationSettle), "a newly present Garmin settles before libmtp")
    try require(!policy.isImmediateFirstRead, "the default order has no immediate first read")
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
    try require(policy.phase == .connecting, "a device re-enumerating for a few seconds stays in the connecting state")
    try require(policy.connectionClockIsRunning, "the connection clock keeps running through a brief drop")
    try require(policy.usbObserved(count: 1, now: 18) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle), "the returning device settles before reading")
    _ = policy.usbObserved(count: 0, now: 19)
    try require(policy.phase == .connecting, "repeated brief drops within the grace window stay calm")
    _ = policy.usbObserved(count: 0, now: 40)
    try require(policy.phase == .waitingForWatch && !policy.connectionClockIsRunning, "a device gone longer than the grace window returns to waiting")
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
    try require(policy.phase == .connecting, "a device still preparing file transfer after 30 s is not shown a warning")
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

private func testImmediateFirstReadIsOffByDefault() throws {
    try require(!DeviceDetectionPolicy.readsImmediatelyOnAppearanceByDefault,
                "the settle-before-read order stays the default until real-device checks allow the immediate read")
    var policy = DeviceDetectionPolicy(now: 0)
    try require(!policy.readsImmediatelyOnAppearance, "a policy made without the option settles first")
    _ = policy.usbObserved(count: 0, now: 0)
    try require(policy.usbObserved(count: 1, now: 5) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle),
                "an appearing Garmin settles before the first read")
    try require(policy.snapshotFailed(.notYetEnumerated, now: 6) == .wait(DeviceDetectionPolicy.retryInterval),
                "the read after the settle is a counted attempt with the ordinary retry interval")
}

private func testImmediateFirstReadSettlesOnlyAfterFailure() throws {
    func immediatePolicy() -> DeviceDetectionPolicy {
        DeviceDetectionPolicy(now: 0, readsImmediatelyOnAppearance: true)
    }
    for failure in [DeviceDetectionErrorClass.notYetEnumerated, .busy, .transient] {
        var policy = immediatePolicy()
        _ = policy.usbObserved(count: 0, now: 0)
        try require(policy.usbObserved(count: 1, now: 5) == .read, "the first read follows the appearance at once")
        try require(policy.isImmediateFirstRead, "the read made on appearance is the immediate first read")
        try require(policy.snapshotFailed(failure, now: 5.1) == .wait(DeviceDetectionPolicy.enumerationSettle),
                    "a failed immediate read is followed by the enumeration settle (\(failure))")
        try require(policy.phase == .connecting && policy.takeNewOutcomes().isEmpty,
                    "a failed immediate read shows and reports nothing (\(failure))")
        try require(!policy.isImmediateFirstRead, "the settle is spent once")
        try require(policy.usbObserved(count: 1, now: 6) == .read, "the read after the settle is an ordinary attempt")
        try require(!policy.isImmediateFirstRead, "later reads are ordinary attempts")
    }

    // One immediate read per plug-in: a brief drop after it (a link reset
    // following a failed open) settles before the next read, so a device that
    // re-enumerates after every failed open is not read at once in a loop.
    var reset = immediatePolicy()
    _ = reset.usbObserved(count: 0, now: 0)
    try require(reset.usbObserved(count: 1, now: 5) == .read, "immediate read on plug-in")
    _ = reset.snapshotFailed(.busy, now: 5.1)
    try require(reset.usbObserved(count: 0, now: 6) == .wait(DeviceDetectionPolicy.presencePollInterval), "brief drop keeps polling")
    try require(reset.usbObserved(count: 1, now: 7) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle),
                "the Garmin returning from a brief drop settles first")
    try require(!reset.isImmediateFirstRead, "no second immediate read for the same plug-in")
    _ = reset.usbObserved(count: 0, now: 8)
    try require(reset.usbObserved(count: 1, now: 9) == .settleThenRead(DeviceDetectionPolicy.enumerationSettle),
                "every further brief drop settles first as well")
    _ = reset.usbObserved(count: 0, now: 10)
    _ = reset.usbObserved(count: 0, now: 40)
    try require(reset.phase == .waitingForWatch, "a Garmin gone longer than the grace window was unplugged")
    try require(reset.usbObserved(count: 1, now: 41) == .read && reset.isImmediateFirstRead,
                "a new plug-in gets its one immediate read")

    // The immediate read does not count toward "busy" or the USB-mode hint.
    var busy = immediatePolicy()
    _ = busy.usbObserved(count: 0, now: 0)
    _ = busy.usbObserved(count: 1, now: 1)
    _ = busy.snapshotFailed(.busy, now: 1.1)
    _ = busy.usbObserved(count: 1, now: 2)
    try require(busy.snapshotFailed(.busy, now: 2.1) == .wait(DeviceDetectionPolicy.busyRetryInterval), "ordinary busy retry interval")
    try require(busy.phase == .connecting, "one counted open failure is not yet shown as busy")
    _ = busy.usbObserved(count: 1, now: 4)
    _ = busy.snapshotFailed(.busy, now: 4.1)
    try require(busy.phase == .needsAttention(.busy), "two counted open failures are shown as busy")

    // A stalled or multiple-device immediate read keeps its existing meaning.
    var stalled = immediatePolicy()
    _ = stalled.usbObserved(count: 0, now: 0)
    _ = stalled.usbObserved(count: 1, now: 1)
    try require(stalled.snapshotFailed(.stoppedResponding, now: 91) == .fail(.failed), "a stalled immediate read still stops detection")
    var multiple = immediatePolicy()
    _ = multiple.usbObserved(count: 0, now: 0)
    _ = multiple.usbObserved(count: 1, now: 1)
    try require(multiple.snapshotFailed(.multipleDevices, now: 1.1) == .wait(DeviceDetectionPolicy.attentionPollInterval),
                "a multiple-device immediate read is shown at once")
    try require(multiple.phase == .needsAttention(.multipleDevices), "multiple devices are shown after an immediate read")

    // A Garmin already present when detection starts was never a settle case.
    var present = immediatePolicy()
    try require(present.usbObserved(count: 1, now: 0) == .read && !present.isImmediateFirstRead,
                "a Garmin present from the start is an ordinary counted read")
    try require(present.snapshotFailed(.notYetEnumerated, now: 0.1) == .wait(DeviceDetectionPolicy.retryInterval),
                "its failure uses the ordinary retry interval")
}

private final class SignalWaitFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var finished = false
    var isFinished: Bool {
        lock.lock()
        defer { lock.unlock() }
        return finished
    }
    func finish() {
        lock.lock()
        finished = true
        lock.unlock()
    }
}

private func waitUntil(_ flag: SignalWaitFlag, seconds: TimeInterval) async -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if flag.isFinished { return true }
        try? await Task.sleep(nanoseconds: 5_000_000)
    }
    return flag.isFinished
}

private func testUSBChangeSignal() async throws {
    let signal = USBChangeSignal()
    let start = signal.currentGeneration

    // A change that happened after the generation was read is never lost.
    signal.notify()
    try require(signal.currentGeneration != start, "a notification advances the generation")
    let missed = SignalWaitFlag()
    let missedTask = Task { await signal.waitForChange(after: start); missed.finish() }
    let missedDone = await waitUntil(missed, seconds: 2)
    try require(missedDone, "a change newer than the seen generation returns at once")
    await missedTask.value

    // A waiter sleeps until the next change.
    let seen = signal.currentGeneration
    let woken = SignalWaitFlag()
    let wokenTask = Task { await signal.waitForChange(after: seen); woken.finish() }
    try? await Task.sleep(nanoseconds: 100_000_000)
    try require(!woken.isFinished, "no change keeps the waiter asleep")
    signal.notify()
    let wokenDone = await waitUntil(woken, seconds: 2)
    try require(wokenDone, "a change wakes the waiter")
    await wokenTask.value

    // Cancelling the waiting task releases it without a change.
    let later = signal.currentGeneration
    let cancelled = SignalWaitFlag()
    let cancelledTask = Task { await signal.waitForChange(after: later); cancelled.finish() }
    try? await Task.sleep(nanoseconds: 50_000_000)
    cancelledTask.cancel()
    let cancelledDone = await waitUntil(cancelled, seconds: 2)
    try require(cancelledDone, "cancellation releases the waiter")
    try require(signal.currentGeneration == later, "cancellation is not a change")

    // A task cancelled before it waits returns at once.
    let early = SignalWaitFlag()
    let earlyTask = Task {
        withUnsafeCurrentTask { $0?.cancel() }
        await signal.waitForChange(after: later)
        early.finish()
    }
    let earlyDone = await waitUntil(early, seconds: 2)
    try require(earlyDone, "an already cancelled task does not wait")
    await earlyTask.value
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
    static func main() async {
        let tests: [(String, () throws -> Void)] = [
            ("connected state", testConnectedState),
            ("disconnect invalidates session and active device", testDisconnectInvalidatesDevice),
            ("no stale connected or ready state remains", testNoStaleDeviceAfterDisconnect),
            ("safe eject transitions to safe-to-disconnect", testSafeEjectIsReadOnly),
            ("eject is unavailable without a device", testEjectCannotStartWithoutDevice),
            ("physical unplug after eject restarts detection", testPhysicalDisconnectAfterEjectReturnsToDetection),
            ("sidebar eject visibility follows connection and lifecycle state", testSafeEjectPresentationStates),
            ("eject policy follows the shared operation state", testSafeEjectPolicyAcrossOperations),
            ("no device stays calm without a connection clock", testNoWatchStaysCalmWithoutClock),
            ("connection clock starts only when a Garmin appears", testClockStartsOnlyWhenGarminAppears),
            ("unplug stops the connection clock", testUnplugStopsClock),
            ("a brief USB drop while connecting keeps the calm connecting state", testBriefUSBDropKeepsConnecting),
            ("multiple Garmins are shown immediately", testMultipleDevicesShownImmediately),
            ("busy is shown after a confirming retry", testBusyNeedsConfirmationThenShows),
            ("persistently invisible Garmin gets the USB-mode hint", testNotMTPModeHintAfterRepeatedInvisibility),
            ("stalled read stops detection", testStoppedRespondingFailsImmediately),
            ("an appearing Garmin settles before the first read by default", testImmediateFirstReadIsOffByDefault),
            ("the optional immediate first read settles only after a failed read, once per plug-in", testImmediateFirstReadSettlesOnlyAfterFailure),
            ("connected outcome is reported once", testConnectedReportedOnce)
        ]

        do {
            for (name, test) in tests {
                try test()
                print("PASS: \(name)")
            }
            try await testUSBChangeSignal()
            print("PASS: USB change signal wakes, never loses a change, and honours cancellation")
            print("PASS: \(tests.count + 1) connection lifecycle tests")
        } catch {
            print("FAIL: \(error)")
            exit(1)
        }
    }
}

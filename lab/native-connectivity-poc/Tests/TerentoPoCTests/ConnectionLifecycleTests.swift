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
        "backup, remove/update, and active install disable Eject"
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

@main
struct ConnectionLifecycleTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("connected state", testConnectedState),
            ("disconnect invalidates session and active device", testDisconnectInvalidatesDevice),
            ("no stale connected or ready state remains", testNoStaleDeviceAfterDisconnect),
            ("safe eject transitions to safe-to-disconnect", testSafeEjectIsReadOnly),
            ("eject is unavailable without a device", testEjectCannotStartWithoutDevice),
            ("sidebar eject visibility follows connection and lifecycle state", testSafeEjectPresentationStates),
            ("eject policy follows the shared operation state", testSafeEjectPolicyAcrossOperations)
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

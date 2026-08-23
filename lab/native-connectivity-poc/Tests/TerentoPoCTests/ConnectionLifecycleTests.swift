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

@main
struct ConnectionLifecycleTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("connected state", testConnectedState),
            ("disconnect invalidates session and active device", testDisconnectInvalidatesDevice),
            ("no stale connected or ready state remains", testNoStaleDeviceAfterDisconnect),
            ("safe eject transitions to safe-to-disconnect", testSafeEjectIsReadOnly),
            ("eject is unavailable without a device", testEjectCannotStartWithoutDevice)
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

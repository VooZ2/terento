import Foundation

/// The only state machine used by the UI for the connected Garmin lifecycle.
/// It intentionally contains no MTP or file-operation methods.
enum DeviceConnectionState: Equatable, Sendable {
    case disconnected
    case detecting
    case connected
    case ready
    case ejecting
    case safeToDisconnect
    case failed
}
/// Keeps lifecycle transitions and the presence of an active device out of
/// SwiftUI. A disconnected or ejected device can never remain active here.
struct DeviceStateManager: Sendable {
    private(set) var state: DeviceConnectionState = .disconnected
    private(set) var hasActiveDevice = false

    var canUseDevice: Bool {
        hasActiveDevice && (state == .connected || state == .ready)
    }

    mutating func beginDetection() {
        state = .detecting
        hasActiveDevice = false
    }

    mutating func deviceConnected() {
        state = .connected
        hasActiveDevice = true
    }

    mutating func deviceReady() {
        guard hasActiveDevice else { return }
        state = .ready
    }

    mutating func deviceDisconnected() {
        state = .disconnected
        hasActiveDevice = false
    }

    @discardableResult
    mutating func beginEject() -> Bool {
        guard canUseDevice else { return false }
        state = .ejecting
        return true
    }

    mutating func markSafeToDisconnect() {
        state = .safeToDisconnect
        hasActiveDevice = false
    }

    mutating func fail() {
        state = .failed
        hasActiveDevice = false
    }
}

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

enum SafeEjectPresentation: Equatable, Sendable {
    case hidden
    case disabled
    case enabled

    static func resolve(
        state: DeviceConnectionState,
        canEject: Bool
    ) -> Self {
        switch state {
        case .connected, .ready:
            return canEject ? .enabled : .disabled
        case .disconnected, .detecting, .ejecting, .safeToDisconnect, .failed:
            return .hidden
        }
    }
}

/// The UI-facing eject policy is shared by the Device card and the sidebar.
/// Transport availability remains supplied by the global MTP gate; view code
/// never infers safety from map ownership or filenames.
enum SafeEjectPolicy: Sendable {
    static func canEject(
        isConnected: Bool,
        transportAvailable: Bool,
        mapOperationBusy: Bool,
        lifecycleOperationBusy: Bool,
        installationActive: Bool
    ) -> Bool {
        isConnected
            && transportAvailable
            && !mapOperationBusy
            && !lifecycleOperationBusy
            && !installationActive
    }
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

/// Outcome of one device-connect episode, exposed for the app first-run funnel
/// (`DEVICE_CONNECT`). DeviceEngine reports each distinct outcome at most once
/// per detection episode; it never sends telemetry itself.
enum DeviceConnectOutcome: String, CaseIterable, Equatable, Sendable {
    /// A snapshot was read and the watch is ready.
    case connected
    /// The calm "Connect your watch" state lasted the whole connection window
    /// without any Garmin on USB. The UI stays calm; this is a funnel signal only.
    case timeoutNoUSB
    /// A Garmin was on USB for the whole connection window without becoming ready.
    case timeoutUSBPresent
    /// The watch is held by another app (repeated session-open failures).
    case busy
    /// More than one Garmin USB/MTP device is connected.
    case multipleDevices
    /// A Garmin is on USB but never appears as a file-transfer device.
    case notMTPMode
    /// A connected watch disappeared unexpectedly.
    case disconnected
    /// Detection stopped for another reason, including a stalled device read.
    case failed
}

/// What the Connect screen shows while `DeviceConnectionState.detecting`.
enum DeviceDetectionPhase: Equatable, Sendable {
    /// No Garmin is on USB. No connection clock is running.
    case waitingForWatch
    /// A Garmin is on USB; the connection clock is running.
    case connecting
    /// A deterministic issue is shown immediately while detection keeps polling.
    case needsAttention(DeviceConnectOutcome)
}

/// Classification of one failed detection attempt. Only `notYetEnumerated`
/// and `transient` are ordinary retry cases; the rest are shown to the user.
enum DeviceDetectionErrorClass: Equatable, Sendable {
    case notYetEnumerated
    case multipleDevices
    case busy
    case stoppedResponding
    case transient
}

/// Pure detection state machine. It owns the phase, the connection clock and
/// the per-attempt counters, but performs no device I/O. Times are monotonic
/// seconds supplied by the caller.
struct DeviceDetectionPolicy: Sendable {
    static let connectionWindow: TimeInterval = 120
    static let presencePollInterval: TimeInterval = 0.5
    static let attentionPollInterval: TimeInterval = 1.0
    static let retryInterval: TimeInterval = 1.2
    static let busyRetryInterval: TimeInterval = 2.0
    static let enumerationSettle: TimeInterval = 0.75
    /// Repeated session-open failures are treated as a device held elsewhere.
    static let busyAfterAttempts = 2
    /// A Garmin that stays invisible to file transfer this long is shown a USB-mode hint.
    static let notMTPModeAfterAttempts = 5
    static let notMTPModeAfterSeconds: TimeInterval = 10

    enum Step: Equatable, Sendable {
        /// Poll USB presence again after this many seconds.
        case wait(TimeInterval)
        /// A Garmin just appeared on USB; let macOS finish enumeration, then read.
        case settleThenRead(TimeInterval)
        /// Read the device snapshot now.
        case read
        /// Stop detection with this outcome.
        case fail(DeviceConnectOutcome)
    }

    private(set) var phase: DeviceDetectionPhase = .waitingForWatch
    private(set) var connectionDeadline: TimeInterval?
    private(set) var reportedOutcomes: Set<DeviceConnectOutcome> = []
    private var waitingSince: TimeInterval
    private var usbPresentSince: TimeInterval?
    private var needsSettle = false
    private var consecutiveNotEnumerated = 0
    private var consecutiveBusy = 0
    private var pendingOutcomes: [DeviceConnectOutcome] = []

    init(now: TimeInterval) {
        waitingSince = now
    }

    var connectionClockIsRunning: Bool { connectionDeadline != nil }

    /// Returns outcomes reached since the last call, each once per episode.
    mutating func takeNewOutcomes() -> [DeviceConnectOutcome] {
        defer { pendingOutcomes.removeAll() }
        return pendingOutcomes
    }

    /// `count` is the number of Garmin USB devices; nil means the probe failed.
    mutating func usbObserved(count: Int?, now: TimeInterval) -> Step {
        guard let count else {
            // An enumeration failure is not evidence either way.
            if let expired = expiredOutcome(now: now) { return .fail(expired) }
            return .wait(Self.presencePollInterval)
        }

        if count == 0 {
            if usbPresentSince != nil || phase != .waitingForWatch {
                waitingSince = now
            }
            phase = .waitingForWatch
            connectionDeadline = nil
            usbPresentSince = nil
            needsSettle = true
            consecutiveBusy = 0
            consecutiveNotEnumerated = 0
            if now - waitingSince >= Self.connectionWindow {
                report(.timeoutNoUSB)
            }
            return .wait(Self.presencePollInterval)
        }

        if count > 1 {
            // Deterministic: the native session requires exactly one Garmin.
            // Show it now and keep polling; no clock runs while it is shown.
            phase = .needsAttention(.multipleDevices)
            connectionDeadline = nil
            usbPresentSince = nil
            needsSettle = true
            report(.multipleDevices)
            return .wait(Self.attentionPollInterval)
        }

        if usbPresentSince == nil { usbPresentSince = now }
        if connectionDeadline == nil {
            connectionDeadline = now + Self.connectionWindow
        }
        if phase == .waitingForWatch || phase == .needsAttention(.multipleDevices) {
            phase = .connecting
        }
        if let expired = expiredOutcome(now: now) { return .fail(expired) }
        if needsSettle {
            needsSettle = false
            return .settleThenRead(Self.enumerationSettle)
        }
        return .read
    }

    mutating func snapshotFailed(_ failure: DeviceDetectionErrorClass, now: TimeInterval) -> Step {
        switch failure {
        case .stoppedResponding:
            report(.failed)
            return .fail(.failed)
        case .multipleDevices:
            phase = .needsAttention(.multipleDevices)
            connectionDeadline = nil
            usbPresentSince = nil
            needsSettle = true
            report(.multipleDevices)
            return .wait(Self.attentionPollInterval)
        case .busy:
            consecutiveNotEnumerated = 0
            consecutiveBusy += 1
            if consecutiveBusy >= Self.busyAfterAttempts {
                phase = .needsAttention(.busy)
                report(.busy)
            }
            return .wait(Self.busyRetryInterval)
        case .notYetEnumerated:
            consecutiveBusy = 0
            consecutiveNotEnumerated += 1
            let presentFor = usbPresentSince.map { now - $0 } ?? 0
            if consecutiveNotEnumerated >= Self.notMTPModeAfterAttempts,
               presentFor >= Self.notMTPModeAfterSeconds {
                phase = .needsAttention(.notMTPMode)
                report(.notMTPMode)
            }
            return .wait(Self.retryInterval)
        case .transient:
            return .wait(Self.retryInterval)
        }
    }

    /// The connection clock fired while a read was in flight.
    mutating func connectionWindowExpired() -> DeviceConnectOutcome {
        let outcome = finalOutcome
        report(outcome)
        return outcome
    }

    mutating func connected() {
        report(.connected)
    }

    private var finalOutcome: DeviceConnectOutcome {
        if case let .needsAttention(outcome) = phase { return outcome }
        return .timeoutUSBPresent
    }

    private mutating func expiredOutcome(now: TimeInterval) -> DeviceConnectOutcome? {
        guard let connectionDeadline, now >= connectionDeadline else { return nil }
        return connectionWindowExpired()
    }

    private mutating func report(_ outcome: DeviceConnectOutcome) {
        guard reportedOutcomes.insert(outcome).inserted else { return }
        pendingOutcomes.append(outcome)
    }
}

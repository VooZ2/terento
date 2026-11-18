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
    /// The calm "Connect your device" state lasted the whole connection window
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

extension DeviceDetectionErrorClass {
    /// The `errorCategory` a map-scan support report states for this class.
    var mapScanReportCategory: String {
        switch self {
        case .notYetEnumerated: return "watch_not_visible"
        case .multipleDevices: return "multiple_watches"
        case .busy: return "watch_busy"
        case .stoppedResponding: return "watch_stopped_responding"
        case .transient: return "read_failed"
        }
    }
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
    /// A Garmin that has just appeared on USB is read at once; the settle is
    /// spent only when that first read does not connect. `false` restores the
    /// earlier settle-before-read order.
    static let readsImmediatelyOnAppearance = true
    /// Repeated session-open failures are treated as a device held elsewhere.
    static let busyAfterAttempts = 2
    /// A Garmin that stays invisible to file transfer this long is shown a USB-mode hint.
    /// Watches commonly need 20-30 s after plugging in or unlocking before file
    /// transfer is offered, so the hint waits well beyond that normal window.
    static let notMTPModeAfterAttempts = 5
    static let notMTPModeAfterSeconds: TimeInterval = 45
    /// A watch can briefly drop off USB while it switches into file-transfer
    /// mode. Within this window the calm "connecting" state is kept instead of
    /// flipping back to "Connect your device".
    static let reconnectGrace: TimeInterval = 10

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
    private var lastUSBSeen: TimeInterval?
    private var needsSettle = false
    /// The read in flight is the immediate one made when the Garmin appeared.
    private(set) var isImmediateFirstRead = false
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
        isImmediateFirstRead = false
        guard let count else {
            // An enumeration failure is not evidence either way.
            if let expired = expiredOutcome(now: now) { return .fail(expired) }
            return .wait(Self.presencePollInterval)
        }

        if count == 0 {
            let connectingPhase = phase == .connecting || phase == .needsAttention(.notMTPMode)
            if connectingPhase, let lastUSBSeen, now - lastUSBSeen < Self.reconnectGrace {
                // A brief re-enumeration: keep connecting and settle again on return.
                needsSettle = true
                return .wait(Self.presencePollInterval)
            }
            lastUSBSeen = nil
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
        lastUSBSeen = now
        if connectionDeadline == nil {
            connectionDeadline = now + Self.connectionWindow
        }
        if phase == .waitingForWatch || phase == .needsAttention(.multipleDevices) {
            phase = .connecting
        }
        if let expired = expiredOutcome(now: now) { return .fail(expired) }
        if needsSettle {
            needsSettle = false
            guard Self.readsImmediatelyOnAppearance else {
                return .settleThenRead(Self.enumerationSettle)
            }
            isImmediateFirstRead = true
        }
        return .read
    }

    mutating func snapshotFailed(_ failure: DeviceDetectionErrorClass, now: TimeInterval) -> Step {
        let wasImmediateFirstRead = isImmediateFirstRead
        isImmediateFirstRead = false
        if wasImmediateFirstRead {
            switch failure {
            case .busy, .notYetEnumerated, .transient:
                // macOS may still be enumerating the Garmin. This read is not
                // counted as an attempt: settle once, then read as before.
                return .wait(Self.enumerationSettle)
            case .multipleDevices, .stoppedResponding:
                break
            }
        }
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
        isImmediateFirstRead = false
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

/// Wakes the detection loop when the set of USB devices changes. It carries no
/// device data and performs no device I/O: a wake-up only makes the loop run
/// its usual USB probe sooner. The presence poll stays as the fallback, so a
/// missed or unavailable notification costs only the polling delay.
final class USBChangeSignal: @unchecked Sendable {
    private let lock = NSLock()
    private var generation: UInt64 = 0
    private var waiters: [UUID: CheckedContinuation<Void, Never>] = [:]
    private var cancelledWaiters: Set<UUID> = []

    /// Read this before probing USB, then wait for a newer value.
    var currentGeneration: UInt64 {
        lock.lock()
        defer { lock.unlock() }
        return generation
    }

    func notify() {
        for waiter in takeWaitersForNewGeneration() {
            waiter.resume()
        }
    }

    /// Returns when a change newer than `seen` exists or the task is cancelled.
    func waitForChange(after seen: UInt64) async {
        let id = UUID()
        await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                if !register(continuation, id: id, seen: seen) {
                    continuation.resume()
                }
            }
        } onCancel: {
            cancelWaiter(id)?.resume()
        }
        forgetWaiter(id)
    }

    private func takeWaitersForNewGeneration() -> [CheckedContinuation<Void, Never>] {
        lock.lock()
        defer { lock.unlock() }
        generation &+= 1
        let all = Array(waiters.values)
        waiters.removeAll()
        return all
    }

    private func register(
        _ continuation: CheckedContinuation<Void, Never>,
        id: UUID,
        seen: UInt64
    ) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard generation == seen, !cancelledWaiters.contains(id) else { return false }
        waiters[id] = continuation
        return true
    }

    private func cancelWaiter(_ id: UUID) -> CheckedContinuation<Void, Never>? {
        lock.lock()
        defer { lock.unlock() }
        cancelledWaiters.insert(id)
        return waiters.removeValue(forKey: id)
    }

    private func forgetWaiter(_ id: UUID) {
        lock.lock()
        defer { lock.unlock() }
        cancelledWaiters.remove(id)
        waiters.removeValue(forKey: id)
    }
}

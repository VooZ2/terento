import Foundation
import os

@MainActor
final class DeviceEngine: ObservableObject {
    @Published private(set) var state: DeviceConnectionState = .disconnected
    @Published private(set) var snapshot: DeviceSnapshot?
    @Published private(set) var compatibility: CompatibilityDecision?
    @Published private(set) var errorMessage: String?
    @Published private(set) var userErrorMessage: String?
    @Published private(set) var readingMessage = "Connect your Garmin watch to this Mac. Nothing will be changed."
    @Published private(set) var readingAttempt = 0
    @Published private(set) var logLines: [String] = ["Ready for a read-only device check."]

    private let logger = Logger(subsystem: "app.terento.native-connectivity-poc", category: "MTP")
    private let compatibilityEngine = CompatibilityEngine()
    private let transport: any DeviceSnapshotReader
    private let operationGate: MTPOperationGate
    private var stateManager = DeviceStateManager()
    private var activeTask: Task<Void, Never>?
    private var presenceTask: Task<Void, Never>?
    private var activeNativeReadTask: Task<DeviceSnapshot, Error>?
    private var activeNativePresenceTask: Task<DeviceSnapshot, Error>?
    private var readingStatusTask: Task<Void, Never>?
    private var presenceMonitoringEnabled = true

    init(
        transport: any DeviceSnapshotReader = MTPTransport(),
        operationGate: MTPOperationGate = .shared
    ) {
        self.transport = transport
        self.operationGate = operationGate
    }

    var isReading: Bool {
        state == .detecting
    }

    var hasConnectedDevice: Bool {
        stateManager.canUseDevice
    }

    var canEject: Bool {
        hasConnectedDevice && operationGate.canEject
    }

    /// The Maps engine pauses this while it owns the MTP transport. This
    /// prevents a background presence probe from opening a competing MTP
    /// session during inventory or installation work.
    func setPresenceMonitoringEnabled(_ enabled: Bool) {
        presenceMonitoringEnabled = enabled

        guard enabled else {
            presenceTask?.cancel()
            presenceTask = nil
            return
        }

        if stateManager.canUseDevice {
            startPresenceMonitoring()
        }
    }

    func cancelReadDevice() {
        guard isReading else {
            return
        }

        cancelConnectionTasks()
        clearCachedDevice()
        stateManager.deviceDisconnected()
        state = stateManager.state
        readingMessage = "Device search stopped. Connect your Garmin watch and try again."
        appendLog("Read-only device check cancelled")
    }

    func readDevice() {
        guard !isReading,
              !stateManager.canUseDevice,
              state != .ejecting else {
            return
        }

        cancelConnectionTasks()
        stateManager.beginDetection()
        state = stateManager.state
        clearCachedDevice()
        errorMessage = nil
        userErrorMessage = nil
        readingAttempt = 0
        readingMessage = "Looking for your Garmin watch… Nothing will be changed."

        readingStatusTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 5_000_000_000)
            } catch {
                return
            }

            guard let self, self.state == .detecting else {
                return
            }

            self.readingMessage = "The watch is taking longer than expected. Close other Garmin or file-transfer apps, reconnect the watch, and keep this window open."
        }
        appendLog("Starting read-only MTP check")

        let startedAt = ContinuousClock.now
        let transport = self.transport
        activeTask = Task { [weak self] in
            do {
                let result = try await self?.readSnapshotWithRetries(
                    transport: transport,
                    maximumAttempts: .max
                )

                guard let result, !Task.isCancelled else {
                    return
                }

                let elapsed = startedAt.duration(to: .now)
                guard let self else {
                    return
                }

                let decision = self.compatibilityEngine.evaluate(snapshot: result)
                self.readingStatusTask?.cancel()
                self.snapshot = result
                self.compatibility = decision
                self.stateManager.deviceConnected()
                self.stateManager.deviceReady()
                self.state = self.stateManager.state
                self.readingMessage = "Your Garmin is connected and ready."
                self.appendLog("MTP read completed in \(Self.format(elapsed))")
                self.appendLog(
                    "Detected \(result.manufacturer) \(result.model) "
                        + "(VID \(Self.hex(result.vendorID)), PID \(Self.hex(result.productID)))"
                )
                self.appendLog("Read \(result.storages.count) storage record(s)")
                self.appendLog("Compatibility status: \(decision.status.rawValue)")
                self.appendLog("Compatibility evidence: USB PASS, MTP PASS, Device info PASS, Storage PASS, Maps PENDING")
                self.startPresenceMonitoring()
            } catch {
                guard !Task.isCancelled else {
                    return
                }

                self?.stateManager.fail()
                self?.state = self?.stateManager.state ?? .failed
                self?.errorMessage = error.localizedDescription
                self?.userErrorMessage = UserFacingErrorMessage.forDevice(error)
                self?.readingStatusTask?.cancel()
                self?.appendLog("MTP read failed: \(error.localizedDescription)")
            }
        }
    }

    /// Releases active read/presence work and clears the cached device. The
    /// native transport already closes every bridge-opened MTP handle at the
    /// end of each operation. This method has no device write surface.
    func ejectDevice() {
        guard canEject,
              stateManager.beginEject() else {
            return
        }

        state = stateManager.state
        cancelConnectionTasks()
        clearCachedDevice()
        errorMessage = nil
        userErrorMessage = nil
        readingMessage = "Releasing the connection…"
        appendLog("Eject requested; cancelling read-only work")

        Task { [weak self] in
            while let self,
                  self.state == .ejecting,
                  self.activeNativeReadTask != nil
                    || self.activeNativePresenceTask != nil
                    || self.operationGate.isNativeOperationActive {
                try? await Task.sleep(for: .milliseconds(50))
            }

            guard let self, self.state == .ejecting else { return }

            self.stateManager.markSafeToDisconnect()
            self.state = self.stateManager.state
            self.readingMessage = "Safe to disconnect — you can unplug your Garmin."
            self.appendLog("Safe to disconnect; no device files were changed")
        }
    }

    private func readSnapshotWithRetries(
        transport: any DeviceSnapshotReader,
        maximumAttempts: Int
    ) async throws -> DeviceSnapshot? {
        var lastError: Error?
        var attempt = 0

        while !Task.isCancelled && attempt < maximumAttempts {
            guard !Task.isCancelled else {
                return nil
            }

            attempt += 1
            readingAttempt = attempt
            readingMessage = attempt == 1
                ? "Looking for your Garmin watch… Nothing will be changed."
                : "Still looking for your Garmin watch… Attempt \(attempt). Retrying automatically."

            do {
                return try await readNativeSnapshot(transport: transport, presence: false)
            } catch {
                lastError = error
                guard !Task.isCancelled else {
                    return nil
                }

                try await Task.sleep(for: .milliseconds(1_200))
            }
        }

        if let lastError {
            throw lastError
        }
        return nil
    }

    private func startPresenceMonitoring() {
        presenceTask?.cancel()
        presenceTask = nil

        guard presenceMonitoringEnabled,
              stateManager.canUseDevice else {
            return
        }

        let transport = self.transport
        let expectedSnapshot = snapshot
        presenceTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .milliseconds(1_500))
                    guard !Task.isCancelled else { return }

                    guard let self, self.stateManager.canUseDevice else {
                        return
                    }

                    let probe = try await self.readNativeSnapshot(transport: transport, presence: true)

                    guard Self.isSamePhysicalDevice(expected: expectedSnapshot, actual: probe) else {
                        self.handleUnexpectedDisconnect("A different device was detected")
                        return
                    }
                } catch {
                    guard !Task.isCancelled else { return }

                    if let gateError = error as? MTPOperationGateError,
                       gateError == .lifecycleBusy {
                        // A map inventory or lifecycle operation owns the
                        // native boundary. Presence resumes after it ends;
                        // it must not turn a deliberate pause into a fake
                        // disconnect.
                        continue
                    }

                    self?.handleUnexpectedDisconnect(error.localizedDescription)
                    return
                }
            }
        }
    }

    private func handleUnexpectedDisconnect(_ reason: String) {
        guard stateManager.canUseDevice else {
            return
        }

        cancelConnectionTasks()
        clearCachedDevice()
        stateManager.deviceDisconnected()
        state = stateManager.state
        errorMessage = nil
        userErrorMessage = nil
        readingMessage = "Your Garmin was disconnected. Connect it again to continue."
        appendLog("Device connection invalidated: \(reason)")
    }

    private func cancelConnectionTasks() {
        activeTask?.cancel()
        activeTask = nil
        presenceTask?.cancel()
        presenceTask = nil
        activeNativeReadTask?.cancel()
        activeNativePresenceTask?.cancel()
        readingStatusTask?.cancel()
        readingStatusTask = nil
    }

    private func readNativeSnapshot(
        transport: any DeviceSnapshotReader,
        presence: Bool
    ) async throws -> DeviceSnapshot {
        let task = Task.detached(priority: presence ? .utility : .userInitiated) {
            try transport.readSnapshot()
        }

        if presence {
            activeNativePresenceTask = task
        } else {
            activeNativeReadTask = task
        }

        defer {
            if presence {
                activeNativePresenceTask = nil
            } else {
                activeNativeReadTask = nil
            }
        }

        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func clearCachedDevice() {
        snapshot = nil
        compatibility = nil
        readingAttempt = 0
    }

    private static func isSamePhysicalDevice(
        expected: DeviceSnapshot?,
        actual: DeviceSnapshot
    ) -> Bool {
        guard let expected else { return false }
        return expected.vendorID == actual.vendorID
            && expected.productID == actual.productID
            && expected.manufacturer.caseInsensitiveCompare(actual.manufacturer) == .orderedSame
    }

    func appendLog(_ message: String) {
        let line = "[\(Self.timestamp())] \(message)"
        logLines.append(line)
        if logLines.count > 120 {
            logLines.removeFirst(logLines.count - 120)
        }
        logger.info("\(message, privacy: .private)")
    }

    private static func timestamp() -> String {
        let formatter = ISO8601DateFormatter()
        return formatter.string(from: Date())
    }

    private static func format(_ duration: Duration) -> String {
        let components = duration.components
        let milliseconds = Double(components.seconds) * 1_000
            + Double(components.attoseconds) / 1_000_000_000_000_000
        return String(format: "%.0f ms", milliseconds)
    }

    private static func hex(_ value: UInt16) -> String {
        String(format: "0x%04X", value)
    }
}

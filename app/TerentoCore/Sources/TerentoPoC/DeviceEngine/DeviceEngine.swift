import Foundation
import os

@MainActor
final class DeviceEngine: ObservableObject {
    @Published private(set) var state: DeviceConnectionState = .disconnected
    @Published private(set) var snapshot: DeviceSnapshot?
    @Published private(set) var compatibility: CompatibilityDecision?
    @Published private(set) var installationAuthorization: InstallationAuthorizationState = .blocked(.catalogUnavailable)
    @Published private(set) var errorMessage: String?
    @Published private(set) var userErrorMessage: String?
    /// The cause-specific Connect message behind `userErrorMessage` after a
    /// detection episode ends without a connection. Presentation only.
    @Published private(set) var connectFailure: ConnectFailureMessage?
    @Published private(set) var readingMessage = "Connect your Garmin watch to this Mac."
    @Published private(set) var readingAttempt = 0
    @Published private(set) var logLines: [String] = ["Ready for a read-only device check."]
    @Published private(set) var operationAvailabilityRevision = 0
    /// What the Connect screen shows while detecting. A calm waiting state has
    /// no timeout; the connection clock starts only once a Garmin is on USB.
    @Published private(set) var detectionPhase: DeviceDetectionPhase = .waitingForWatch
    /// Most recent connect outcome, for presentation and the first-run funnel.
    @Published private(set) var lastConnectOutcome: DeviceConnectOutcome?
    /// Shown on the waiting screen after an unexpected disconnect.
    @Published private(set) var disconnectNotice: String?
    /// Integration hook for the first-run funnel. Called on the main actor with
    /// each distinct outcome of a detection episode; DeviceEngine sends nothing.
    var connectOutcomeHandler: ((DeviceConnectOutcome) -> Void)?
    private(set) var invalidationDevicePresence: InstallationFailureContext.DevicePresence = .unknown

    private let logger = Logger(subsystem: "app.terento.native-connectivity-poc", category: "MTP")
    private let compatibilityEngine = CompatibilityEngine()
    private let compatibilityStatusClient: CompatibilityStatusClient
    private let installationAuthorizationClient: InstallationAuthorizationClient
    private let transport: any DeviceSnapshotReader
    private let operationGate: MTPOperationGate
    private var stateManager = DeviceStateManager()
    private var activeTask: Task<Void, Never>?
    private var presenceTask: Task<Void, Never>?
    private var activeNativeReadTask: Task<DeviceSnapshot, Error>?
    private var activeNativePresenceTask: Task<Void, Never>?
    private var readingStatusTask: Task<Void, Never>?
    private var compatibilityStatusTask: Task<Void, Never>?
    private var postEjectPresenceTask: Task<Void, Never>?
    private var replugWatchTask: Task<Void, Never>?
    private var presenceMonitoringEnabled = true
    private var lastDetectionUSBPresence = false
    private var detectionPolicy = DeviceDetectionPolicy(now: 0)

    init(
        transport: any DeviceSnapshotReader = BoundedDeviceTransport(),
        operationGate: MTPOperationGate = .shared,
        compatibilityStatusClient: CompatibilityStatusClient = CompatibilityStatusClient(),
        installationAuthorizationClient: InstallationAuthorizationClient = InstallationAuthorizationClient()
    ) {
        self.transport = transport
        self.operationGate = operationGate
        self.compatibilityStatusClient = compatibilityStatusClient
        self.installationAuthorizationClient = installationAuthorizationClient
    }

    var isReading: Bool {
        state == .detecting
    }

    /// Whether this detection episode has already reported `timeoutNoUSB`:
    /// the whole connection window passed with no Garmin on USB. Read-only;
    /// detection keeps polling unchanged.
    var hasWaitedWithoutUSB: Bool {
        state == .detecting && detectionPolicy.reportedOutcomes.contains(.timeoutNoUSB)
    }

    var hasConnectedDevice: Bool {
        stateManager.canUseDevice
    }

    var canEject: Bool {
        hasConnectedDevice
            && activeNativeReadTask == nil
            && activeNativePresenceTask == nil
            && operationGate.canEject
    }

    /// The Maps engine pauses this while it owns the MTP transport. This
    /// prevents a background presence probe from opening a competing MTP
    /// session during inventory or installation work.
    func setPresenceMonitoringEnabled(_ enabled: Bool) {
        guard presenceMonitoringEnabled != enabled else {
            return
        }

        presenceMonitoringEnabled = enabled

        guard enabled else {
            presenceTask?.cancel()
            presenceTask = nil
            // The outer task may already be inside a detached synchronous
            // MTP read. Cancelling only the loop leaves the shared operation
            // gate occupied until that native read returns, which can make a
            // legitimate map installation appear blocked indefinitely.
            activeNativePresenceTask?.cancel()
            publishOperationAvailability()
            return
        }

        if stateManager.canUseDevice {
            startPresenceMonitoring()
        }
        publishOperationAvailability()
    }

    func cancelReadDevice() {
        guard isReading else {
            return
        }

        invalidationDevicePresence = .unknown
        cancelConnectionTasks()
        clearCachedDevice()
        installationAuthorization = .resolving
        stateManager.deviceDisconnected()
        state = stateManager.state
        readingMessage = "Device search stopped. Connect your Garmin watch and try again."
        appendLog("Read-only device check cancelled")
    }

    func retryInstallationAuthorization() {
        guard let compatibility, snapshot != nil else { return }
        installationAuthorization = .resolving
        refreshPublicCompatibilityStatus(for: compatibility)
    }

    /// Catalog-timer hook: re-resolve only while blocked by an unavailable
    /// policy, never while a decision is pending or already made.
    func retryInstallationAuthorizationIfUnavailable() {
        guard case .blocked(let reason) = installationAuthorization,
              reason.isRetryable else { return }
        retryInstallationAuthorization()
    }

    /// Replaces the storage figures of the connected watch with a newer read
    /// of the same watch (for example the scan after an install), so the
    /// Device page and the planner do not use the value captured at connect.
    func refreshStorage(_ observation: DeviceStorageObservation) {
        guard hasConnectedDevice,
              let current = snapshot,
              current.vendorID == observation.vendorID,
              current.productID == observation.productID,
              current.serialNumber == observation.serialNumber,
              !observation.storages.isEmpty else { return }
        snapshot = DeviceSnapshot(
            manufacturer: current.manufacturer,
            model: current.model,
            deviceVersion: current.deviceVersion,
            vendorID: current.vendorID,
            productID: current.productID,
            storages: observation.storages,
            serialNumber: current.serialNumber,
            garminDeviceXMLStatus: current.garminDeviceXMLStatus,
            garminDeviceXML: current.garminDeviceXML
        )
    }

    /// A fresh decision made at download time is applied here, so the Device
    /// and review pages show the same verdict that blocked or allowed the
    /// operation. Decisions for another watch are ignored.
    func applyFreshInstallationAuthorization(
        _ authorization: InstallationAuthorizationState,
        for identity: DeviceIdentity
    ) {
        guard currentInstallationIdentity == identity,
              installationAuthorization != authorization else { return }
        installationAuthorization = authorization
        appendLog(
            "Installation authorization refreshed: \(authorization.canInstall ? "approved" : "blocked")"
        )
    }

    var currentInstallationIdentity: DeviceIdentity? {
        guard hasConnectedDevice, snapshot != nil else { return nil }
        return compatibility?.identity
    }

    func resolveFreshInstallationAuthorization(for expected: DeviceIdentity) async -> InstallationAuthorizationState {
        guard currentInstallationIdentity == expected else { return .blocked(.pending) }
        let decision = await installationAuthorizationClient.resolve(identity: expected)
        guard currentInstallationIdentity == expected else { return .blocked(.pending) }
        return decision
    }

    func readDevice() {
        guard !isReading,
              !stateManager.canUseDevice,
              state != .ejecting else {
            return
        }

        invalidationDevicePresence = .unknown
        cancelConnectionTasks()
        stateManager.beginDetection()
        state = stateManager.state
        clearCachedDevice()
        errorMessage = nil
        userErrorMessage = nil
        connectFailure = nil
        readingAttempt = 0
        lastDetectionUSBPresence = false
        detectionPolicy = DeviceDetectionPolicy(now: Self.uptime())
        detectionPhase = detectionPolicy.phase
        readingMessage = "Waiting for your Garmin…"
        appendLog("Starting read-only MTP check")

        let startedAt = ContinuousClock.now
        let transport = self.transport
        activeTask = Task { [weak self] in
            await self?.runDetection(transport: transport, startedAt: startedAt)
        }
    }

    /// One detection episode. While no Garmin is on USB the loop only polls the
    /// USB-only probe; libmtp is entered only after a Garmin is present, and the
    /// 2-minute connection clock starts at that point.
    /// Deterministic problems are shown immediately while polling continues, so
    /// fixing the cause (unplugging a second Garmin, quitting another app)
    /// connects without another click. Only "not yet enumerated" and transient
    /// read failures are ordinary retries.
    private func runDetection(
        transport: any DeviceSnapshotReader,
        startedAt: ContinuousClock.Instant
    ) async {
        let counter = transport as? any GarminUSBDeviceCounter
        var attempt = 0
        var loggedWaiting = false

        while !Task.isCancelled, state == .detecting {
            let usbCount: Int?
            if let counter {
                usbCount = try? await readNativeGarminUSBDeviceCount(transport: counter)
            } else {
                // Readers without a USB-only probe go straight to a snapshot.
                usbCount = 1
            }
            guard !Task.isCancelled, state == .detecting else { return }

            if let usbCount {
                lastDetectionUSBPresence = usbCount > 0
                if usbCount == 0, !loggedWaiting {
                    appendLog("Waiting for Garmin USB connection before MTP detection")
                    loggedWaiting = true
                } else if usbCount > 0 {
                    loggedWaiting = false
                }
            }

            let step = detectionPolicy.usbObserved(count: usbCount, now: Self.uptime())
            publishDetectionProgress()
            switch step {
            case .wait(let seconds):
                if detectionPhase == .waitingForWatch {
                    readingAttempt = 0
                    readingMessage = "Waiting for your Garmin…"
                }
                guard await Self.pause(seconds) else { return }
                continue
            case .fail(let outcome):
                finishDetectionFailure(outcome)
                return
            case .settleThenRead:
                readingMessage = "Garmin detected. Checking the device…"
                appendLog("Garmin returned to USB; waiting for MTP enumeration")
                do {
                    try await Task.sleep(for: .milliseconds(750))
                } catch {
                    return
                }
                guard !Task.isCancelled, state == .detecting else { return }
            case .read:
                break
            }

            attempt += 1
            readingAttempt = attempt
            readingMessage = attempt == 1
                ? "Waiting for your Garmin…"
                : "Still waiting for your Garmin…"

            do {
                let result = try await readNativeSnapshot(transport: transport, presence: false)
                guard !Task.isCancelled, state == .detecting else { return }
                completeDetection(result, elapsed: startedAt.duration(to: .now))
                return
            } catch {
                guard !Task.isCancelled, state == .detecting else { return }
                let failure = DeviceDetectionErrorClassifier.classify(error)
                errorMessage = error.localizedDescription
                appendLog("Detection attempt \(attempt) did not connect: \(failure)")
                let next = detectionPolicy.snapshotFailed(failure, now: Self.uptime())
                publishDetectionProgress()
                switch next {
                case .fail(let outcome):
                    finishDetectionFailure(outcome)
                    return
                case .wait(let seconds):
                    guard await Self.pause(seconds) else { return }
                case .read, .settleThenRead:
                    break
                }
            }
        }
    }

    private func completeDetection(_ result: DeviceSnapshot, elapsed: Duration) {
        let decision = compatibilityEngine.evaluate(snapshot: result)
        readingStatusTask?.cancel()
        readingStatusTask = nil
        snapshot = result
        compatibility = decision
        errorMessage = nil
        disconnectNotice = nil
        // The policy decision is still in flight: show "Checking…", not a
        // connection error, until it resolves.
        installationAuthorization = .resolving
        stateManager.deviceConnected()
        stateManager.deviceReady()
        state = stateManager.state
        readingMessage = "Your Garmin is connected and ready."
        detectionPolicy.connected()
        publishDetectionProgress()
        appendLog("MTP read completed in \(Self.format(elapsed))")
        appendLog(
            "Detected \(result.manufacturer) \(result.model) "
                + "(VID \(Self.hex(result.vendorID)), PID \(Self.hex(result.productID)))"
        )
        appendLog("Read \(result.storages.count) storage record(s)")
        appendLog("Compatibility status: resolving canonical public status")
        appendLog("Compatibility evidence: USB PASS, MTP PASS, Device info PASS, Storage PASS, Maps PENDING")
        refreshPublicCompatibilityStatus(for: decision)
        startPresenceMonitoring()
    }

    /// Ends a detection episode. The user sees the classified reason and can
    /// press Try again; plugging the watch back in restarts discovery as well.
    private func finishDetectionFailure(_ outcome: DeviceConnectOutcome) {
        guard state == .detecting else { return }
        activeTask?.cancel()
        activeTask = nil
        activeNativeReadTask?.cancel()
        readingStatusTask?.cancel()
        readingStatusTask = nil
        stateManager.fail()
        state = stateManager.state
        publishDetectionProgress()
        let failure = UserFacingErrorMessage.detectionFailure(
            outcome,
            garminUSBPresent: lastDetectionUSBPresence
        )
        connectFailure = failure
        userErrorMessage = failure.text
        if outcome == .failed {
            readingMessage = "The watch stopped responding."
            appendLog("Connection check stopped: the watch did not respond within the device read bound")
        } else {
            readingMessage = "Connection timed out after 2 minutes."
            appendLog("Connection check timed out after 2 minutes (\(outcome.rawValue))")
        }
        startReplugWatch()
    }

    private func publishDetectionProgress() {
        if detectionPhase != detectionPolicy.phase {
            detectionPhase = detectionPolicy.phase
        }
        for outcome in detectionPolicy.takeNewOutcomes() {
            reportConnectOutcome(outcome)
        }
        syncConnectionClock()
    }

    private func reportConnectOutcome(_ outcome: DeviceConnectOutcome) {
        lastConnectOutcome = outcome
        appendLog("Connect outcome: \(outcome.rawValue)")
        connectOutcomeHandler?(outcome)
    }

    /// Keeps the timer that ends an in-flight read in step with the policy's
    /// connection clock. No clock exists while no Garmin is on USB.
    private func syncConnectionClock() {
        guard state == .detecting, let deadline = detectionPolicy.connectionDeadline else {
            readingStatusTask?.cancel()
            readingStatusTask = nil
            return
        }
        guard readingStatusTask == nil else { return }
        let delay = max(0, deadline - Self.uptime())
        readingStatusTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            } catch {
                return
            }
            guard let self,
                  self.state == .detecting,
                  self.detectionPolicy.connectionClockIsRunning else {
                return
            }
            self.readingStatusTask = nil
            self.finishDetectionFailure(self.detectionPolicy.connectionWindowExpired())
        }
    }

    /// After a failed check, a physical unplug and replug restarts discovery,
    /// matching the post-eject path. This only reads the USB device list.
    private func startReplugWatch() {
        replugWatchTask?.cancel()
        replugWatchTask = nil
        guard state == .failed,
              let counter = transport as? any GarminUSBDeviceCounter else {
            return
        }

        replugWatchTask = Task { [weak self] in
            var observedAbsence = false
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }
                guard let self, self.state == .failed else { return }
                guard let count = try? await self.readNativeGarminUSBDeviceCount(transport: counter),
                      !Task.isCancelled,
                      self.state == .failed else {
                    continue
                }
                if count == 0 {
                    observedAbsence = true
                } else if observedAbsence {
                    self.appendLog("Garmin reconnected after a failed check; restarting device discovery")
                    self.replugWatchTask = nil
                    self.readDevice()
                    return
                }
            }
        }
    }

    private static func uptime() -> TimeInterval {
        ProcessInfo.processInfo.systemUptime
    }

    private static func pause(_ seconds: TimeInterval) async -> Bool {
        do {
            try await Task.sleep(nanoseconds: UInt64(max(0, seconds) * 1_000_000_000))
            return true
        } catch {
            return false
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

        invalidationDevicePresence = .unknown
        state = stateManager.state
        cancelConnectionTasks()
        clearCachedDevice()
        errorMessage = nil
        userErrorMessage = nil
        connectFailure = nil
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
            self.startPostEjectPresenceMonitoring()
        }
    }

    /// Keeps the Safe to disconnect result visible while the watch remains
    /// physically attached. Once it disappears from the USB bus, Terento
    /// returns to normal detection so a reconnect or another watch can be
    /// discovered without restarting the app.
    private func startPostEjectPresenceMonitoring() {
        postEjectPresenceTask?.cancel()
        postEjectPresenceTask = nil

        guard state == .safeToDisconnect,
              let presenceTransport = transport as? any GarminUSBPresenceReader else {
            return
        }

        postEjectPresenceTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .milliseconds(500))
                    guard !Task.isCancelled,
                          let self,
                          self.state == .safeToDisconnect else {
                        return
                    }

                    let isPresent = try await self.readNativeGarminUSBPresence(
                        transport: presenceTransport
                    )
                    guard !Task.isCancelled else { return }

                    if !isPresent {
                        self.handlePhysicalDisconnectAfterEject()
                        return
                    }
                } catch {
                    guard !Task.isCancelled else { return }

                    if let gateError = error as? MTPOperationGateError,
                       gateError == .lifecycleBusy {
                        continue
                    }

                    // A transient USB enumeration failure is not evidence
                    // that the watch was unplugged. Keep the safe state and
                    // retry instead of guessing.
                    continue
                }
            }
        }
    }

    private func handlePhysicalDisconnectAfterEject() {
        guard state == .safeToDisconnect else {
            return
        }

        postEjectPresenceTask = nil
        invalidationDevicePresence = .absent
        stateManager.deviceDisconnected()
        state = stateManager.state
        readingMessage = "Waiting for your Garmin…"
        appendLog("Ejected Garmin physically disconnected; restarting device discovery")

        Task { [weak self] in
            await Task.yield()
            guard let self, self.state == .disconnected else { return }
            self.readDevice()
        }
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

                    if let presenceTransport = transport as? any DevicePresenceReader {
                        let probe = try await self.readNativePresence(transport: presenceTransport)

                        guard Self.isSamePhysicalDevice(expected: expectedSnapshot, actual: probe) else {
                            self.handleUnexpectedDisconnect("A different device was detected")
                            return
                        }
                    } else {
                        let probe = try await self.readNativeSnapshot(transport: transport, presence: true)

                        guard Self.isSamePhysicalDevice(expected: expectedSnapshot, actual: probe) else {
                            self.handleUnexpectedDisconnect("A different device was detected")
                            return
                        }
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

                    self?.handleUnexpectedDisconnect(error.localizedDescription,
                        presence: (error as? MTPTransportError)?.devicePresence ?? .unknown,
                        multipleDevices: DeviceDetectionErrorClassifier.classify(error) == .multipleDevices)
                    return
                }
            }
        }
    }

    private func handleUnexpectedDisconnect(
        _ reason: String,
        presence: InstallationFailureContext.DevicePresence = .unknown,
        multipleDevices: Bool = false
    ) {
        guard stateManager.canUseDevice else {
            return
        }

        invalidationDevicePresence = presence
        cancelConnectionTasks()
        clearCachedDevice()
        stateManager.deviceDisconnected()
        state = stateManager.state
        errorMessage = nil
        userErrorMessage = nil
        connectFailure = nil
        readingMessage = "Your Garmin was disconnected. Connect it again to continue."
        disconnectNotice = multipleDevices
            ? nil
            : "Plug it back in. Terento reconnects automatically."
        appendLog("Device connection invalidated: \(reason)")
        reportConnectOutcome(.disconnected)

        // Return to calm discovery, as after Safe Eject. A second Garmin is
        // then shown as its own issue instead of as a disconnect.
        Task { [weak self] in
            await Task.yield()
            guard let self, self.state == .disconnected else { return }
            self.readDevice()
        }
    }

    private func cancelConnectionTasks() {
        activeTask?.cancel()
        activeTask = nil
        presenceTask?.cancel()
        presenceTask = nil
        postEjectPresenceTask?.cancel()
        postEjectPresenceTask = nil
        activeNativeReadTask?.cancel()
        activeNativePresenceTask?.cancel()
        readingStatusTask?.cancel()
        readingStatusTask = nil
        replugWatchTask?.cancel()
        replugWatchTask = nil
        compatibilityStatusTask?.cancel()
        compatibilityStatusTask = nil
    }

    private func readNativeSnapshot(
        transport: any DeviceSnapshotReader,
        presence: Bool
    ) async throws -> DeviceSnapshot {
        let task = Task.detached(priority: presence ? .utility : .userInitiated) {
            try transport.readSnapshot()
        }

        if presence {
            activeNativePresenceTask = Task {
                _ = try? await task.value
            }
        } else {
            activeNativeReadTask = task
        }

        defer {
            if presence {
                activeNativePresenceTask = nil
            } else {
                activeNativeReadTask = nil
                publishOperationAvailability()
            }
        }

        if !presence {
            publishOperationAvailability()
        }

        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func readNativePresence(
        transport: any DevicePresenceReader
    ) async throws -> DevicePresence {
        let task = Task.detached(priority: .utility) {
            try transport.readPresence()
        }

        activeNativePresenceTask = Task {
            _ = try? await task.value
        }

        defer {
            activeNativePresenceTask = nil
        }

        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func readNativeGarminUSBPresence(
        transport: any GarminUSBPresenceReader
    ) async throws -> Bool {
        let task = Task.detached(priority: .utility) {
            try transport.hasGarminUSBDevice()
        }

        activeNativePresenceTask = Task {
            _ = try? await task.value
        }

        defer {
            activeNativePresenceTask = nil
        }

        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func readNativeGarminUSBDeviceCount(
        transport: any GarminUSBDeviceCounter
    ) async throws -> Int {
        let task = Task.detached(priority: .utility) {
            try transport.countGarminUSBDevices()
        }

        activeNativePresenceTask = Task {
            _ = try? await task.value
        }

        defer {
            activeNativePresenceTask = nil
        }

        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func publishOperationAvailability() {
        operationAvailabilityRevision &+= 1
    }

    private func clearCachedDevice() {
        snapshot = nil
        compatibility = nil
        installationAuthorization = .blocked(.catalogUnavailable)
        readingAttempt = 0
    }

    private func refreshPublicCompatibilityStatus(for decision: CompatibilityDecision) {
        compatibilityStatusTask?.cancel()
        let client = compatibilityStatusClient
        let authorizationClient = installationAuthorizationClient
        let identity = decision.identity
        compatibilityStatusTask = Task { [weak self] in
            let catalogMetadata = await client.resolveCatalogMetadata(identity: identity)
            let catalogDecision = decision.applying(catalogMetadata: catalogMetadata)
            let installationAuthorization = await authorizationClient.resolve(identity: catalogDecision.identity)
            // Publish the verdict as soon as it is known; the public
            // compatibility lookup below is presentation only.
            if !Task.isCancelled, let self, self.snapshot != nil, self.compatibility?.identity == identity {
                self.installationAuthorization = installationAuthorization
            }
            let resolution = await client.resolve(identity: catalogDecision.identity)
            guard !Task.isCancelled,
                  let self,
                  self.snapshot != nil,
                  self.compatibility?.identity == identity else {
                return
            }

            self.installationAuthorization = installationAuthorization
            let updatedDecision = catalogDecision.applying(resolution)
            self.compatibility = updatedDecision
            self.appendLog(
                "Installation authorization: \(installationAuthorization.canInstall ? "approved" : "blocked")"
            )
            self.appendLog(
                "Compatibility status: \(updatedDecision.status?.userLabel ?? "Unavailable") "
                    + "(\(updatedDecision.statusSource.rawValue))"
            )
            if let record = updatedDecision.publicRecord {
                self.appendLog(
                    "Compatibility record: id=\(record.canonicalDeviceId ?? "unavailable"), "
                        + "canonical=\(record.canonicalModel ?? "unavailable"), "
                        + "size=\(record.caseSizeMm.map(String.init) ?? "unavailable"), "
                        + "variant=\(record.variant ?? "unavailable"), "
                        + "display=\(record.displayType ?? "unavailable"), "
                        + "successes=\(record.successfulInstallations.map(String.init) ?? "unavailable"), "
                        + "lastEvidence=\(record.lastEvidence ?? "unavailable"), "
                        + "mapCapable=\(record.mapCapable.map(String.init) ?? "unavailable")"
                )
            }
            self.appendLog(
                "Local device: firmware=\(identity.firmware ?? "unavailable"), "
                    + "VID=\(Self.hex(identity.usbVendorId)), PID=\(Self.hex(identity.usbProductId))"
            )
        }
    }

    private static func isSamePhysicalDevice(
        expected: DeviceSnapshot?,
        actual: DevicePresence
    ) -> Bool {
        guard let expected else { return false }
        return expected.vendorID == actual.vendorID
            && (actual.productID == 0 || expected.productID == actual.productID)
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

/// Maps one failed detection read to a user-relevant class. Native result
/// codes come from `terento_mtp_read_snapshot_diagnostic`: -2/-3 no Garmin
/// file-transfer device yet, -4 more than one Garmin, -5 session could not be
/// opened. A worker deadline means the watch stopped responding.
enum DeviceDetectionErrorClassifier {
    static func classify(_ error: Error) -> DeviceDetectionErrorClass {
        if let transportError = error as? MTPTransportError,
           case .multipleGarminDevices = transportError {
            return .multipleDevices
        }
        if let context = (error as? any InstallationFailureContextProviding)?.failureContext {
            if context.resultKind == .timeout {
                return .stoppedResponding
            }
            if context.nativeCodeNamespace == .terentoSnapshot,
               let code = context.nativeResultCode {
                switch code {
                case -2, -3: return .notYetEnumerated
                case -4: return .multipleDevices
                case -5: return .busy
                default: break
                }
            }
        }
        let message = error.localizedDescription.lowercased()
        if message.contains("more than one garmin") {
            return .multipleDevices
        }
        if message.contains("libusb_error_busy")
            || message.contains("resource busy")
            || message.contains("already opened for exclusive access")
            || message.contains("could not be opened") {
            return .busy
        }
        if message.contains("no mtp device") || message.contains("no garmin") {
            return .notYetEnumerated
        }
        return .transient
    }
}

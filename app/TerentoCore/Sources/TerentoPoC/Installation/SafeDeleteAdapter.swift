import Foundation

/// Outcomes for the only destructive lifecycle operation currently allowed.
enum SafeDeleteStatus: String, Equatable, Sendable {
    case success = "DELETE_SUCCESS"
    case failedDeviceDisconnected = "DELETE_FAILED_DEVICE_DISCONNECTED"
    case failedDeviceBusy = "DELETE_FAILED_DEVICE_BUSY"
    case failedObjectNotFound = "DELETE_FAILED_OBJECT_NOT_FOUND"
    case blockedOwnership = "DELETE_BLOCKED_OWNERSHIP"
    case blockedIntegrityCheck = "DELETE_BLOCKED_INTEGRITY_CHECK"
    case failedOperation = "DELETE_FAILED_OPERATION"
    case failedPostVerify = "DELETE_FAILED_POST_VERIFY"
    case failedManifestCleanup = "DELETE_FAILED_MANIFEST_CLEANUP"
    case blockedConfirmationRequired = "DELETE_BLOCKED_CONFIRMATION_REQUIRED"
}

enum SafeDeleteTransportError: LocalizedError, Equatable, Sendable {
    case deviceDisconnected(String)
    case deviceBusy(String)
    case objectNotFound
    case operationFailed(String)

    var errorDescription: String? {
        switch self {
        case .deviceDisconnected(let message):
            return message
        case .deviceBusy(let message):
            return message
        case .objectNotFound:
            return "The managed map object was not found on the Garmin device."
        case .operationFailed(let message):
            return message
        }
    }
}

/// Exact deletion authorization. Every field is supplied by a validated
/// manifest/inventory decision; a filename alone is never sufficient.
struct SafeDeleteTarget: Equatable, Sendable {
    let deviceKey: String
    let mapIdentity: MapIdentity
    let ownership: MapManagementState
    let objectID: UInt32
    let expectedPath: String
    let expectedFilename: String
    let expectedSizeBytes: UInt64
    let expectedSHA256: String
    /// Set for a versioned map produced by Stage 5.3. Existing Stage 5.2
    /// base-filename targets leave this nil for source compatibility.
    let expectedVersion: MapVersion?
    /// Explicitly authorizes the beta one-by-one removal path for a parsed
    /// third-party map. This remains false for every manifest-backed target.
    let allowsExternalRemoval: Bool
    /// Sampled removal proof from the managed manifest entry, if recorded.
    /// The native managed delete enforces it; nil means the full SHA-256.
    /// Never set for external maps.
    let removalProof: ManagedRemovalProof?

    init(
        deviceKey: String,
        mapIdentity: MapIdentity,
        ownership: MapManagementState,
        objectID: UInt32,
        expectedPath: String,
        expectedFilename: String,
        expectedSizeBytes: UInt64,
        expectedSHA256: String,
        expectedVersion: MapVersion? = nil,
        allowsExternalRemoval: Bool = false,
        removalProof: ManagedRemovalProof? = nil
    ) {
        self.deviceKey = deviceKey
        self.mapIdentity = mapIdentity
        self.ownership = ownership
        self.objectID = objectID
        self.expectedPath = expectedPath
        self.expectedFilename = expectedFilename
        self.expectedSizeBytes = expectedSizeBytes
        self.expectedSHA256 = expectedSHA256
        self.expectedVersion = expectedVersion
        self.allowsExternalRemoval = allowsExternalRemoval
        self.removalProof = removalProof
    }

    var sourceFile: InstalledMapFile {
        InstalledMapFile(
            path: expectedPath,
            filename: expectedFilename,
            sizeBytes: expectedSizeBytes,
            itemID: objectID
        )
    }

    func resolvingObjectID(_ objectID: UInt32) -> SafeDeleteTarget {
        SafeDeleteTarget(
            deviceKey: deviceKey,
            mapIdentity: mapIdentity,
            ownership: ownership,
            objectID: objectID,
            expectedPath: expectedPath,
            expectedFilename: expectedFilename,
            expectedSizeBytes: expectedSizeBytes,
            expectedSHA256: expectedSHA256,
            expectedVersion: expectedVersion,
            allowsExternalRemoval: allowsExternalRemoval,
            removalProof: removalProof
        )
    }
}

struct SafeDeleteDeviceObject: Equatable, Sendable {
    let file: InstalledMapFile
    /// SHA-256 of the freshly resolved live object when a content read was
    /// performed. A manual Remove of a Terento-owned object may deliberately
    /// omit that expensive read: the local manifest plus the live exact path,
    /// filename, size, and session-local object identity are the ownership
    /// proof required by the device safety contract.
    let sha256: String
    let contentHashVerified: Bool

    init(
        file: InstalledMapFile,
        sha256: String,
        contentHashVerified: Bool = true
    ) {
        self.file = file
        self.sha256 = sha256
        self.contentHashVerified = contentHashVerified
    }
}

/// Transport boundary for SafeDeleteAdapter. The inspect operation must be
/// read-only. The delete operation is the sole destructive operation exposed
/// by this boundary.
protocol SafeDeleteTransport: Sendable {
    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject
    func deleteExactObject(_ target: SafeDeleteTarget) throws
    func inspectExactObject(_ target: SafeDeleteTarget,
                            onProgress: (@Sendable (TransferProgress) -> Void)?) throws -> SafeDeleteDeviceObject
    func deleteExactObject(_ target: SafeDeleteTarget,
                           onProgress: (@Sendable (TransferProgress) -> Void)?) throws
}

extension SafeDeleteTransport {
    func deleteExactObject(_ target: SafeDeleteTarget,
                           onProgress: (@Sendable (TransferProgress) -> Void)?) throws {
        try deleteExactObject(target)
    }

    func inspectExactObject(
        _ target: SafeDeleteTarget,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> SafeDeleteDeviceObject {
        try inspectExactObject(target)
    }
}

enum SafeDeleteProgressState: Equatable, Sendable {
    case verifying
    case checkingContent
    case postVerifying
    case completed
}

struct SafeDeleteProgress: Equatable, Sendable {
    var detail: String {
        switch state {
        case .verifying: return "Checking the selected map"
        case .checkingContent: return "Checking map contents before removal"
        case .postVerifying: return "Confirming the map was removed"
        case .completed: return "Map removal confirmed"
        }
    }

    let state: SafeDeleteProgressState
    let bytesCompleted: UInt64
    let totalBytes: UInt64
    let bytesPerSecond: Double

    var fractionCompleted: Double {
        guard totalBytes > 0 else { return 0 }
        return min(1, Double(bytesCompleted) / Double(totalBytes))
    }
}

private final class SafeDeleteProgressReporter: @unchecked Sendable {
    private let totalBytes: UInt64
    private let onProgress: (@Sendable (SafeDeleteProgress) -> Void)?

    init(
        totalBytes: UInt64,
        onProgress: (@Sendable (SafeDeleteProgress) -> Void)?
    ) {
        self.totalBytes = totalBytes
        self.onProgress = onProgress
    }

    func report(
        state: SafeDeleteProgressState,
        fraction: Double,
        bytesPerSecond: Double = 0
    ) {
        guard let onProgress else { return }
        let boundedFraction = min(1, max(0, fraction))
        let completed = UInt64(
            (Double(totalBytes) * boundedFraction).rounded(.down)
        )
        onProgress(SafeDeleteProgress(
            state: state,
            bytesCompleted: completed,
            totalBytes: totalBytes,
            bytesPerSecond: bytesPerSecond
        ))
    }
}

struct SafeDeleteResult: Equatable, Sendable {
    let mapIdentity: MapIdentity
    let status: SafeDeleteStatus
    let message: String

    var isSuccess: Bool {
        status == .success
    }
}

/// What the confirm step after a delete observed.
enum SafeDeleteConfirmOutcome: String, Equatable, Sendable {
    case absent
    case stillPresent = "still_present"
    case readFailed = "read_failed"
    case timedOut = "timed_out"
}

/// One Remove step, for the local log. Fixed labels only: no names or paths.
enum SafeDeleteStep: Equatable, Sendable {
    case checkStarted
    case checkFinished(succeeded: Bool)
    case deleteStarted
    case deleteFinished(succeeded: Bool)
    case confirmStarted(timeLimit: TimeInterval?)
    case confirmAttemptStarted(attempt: Int)
    case confirmAttemptFinished(attempt: Int, outcome: SafeDeleteConfirmOutcome)
    case confirmFinished(outcome: SafeDeleteConfirmOutcome, elapsed: TimeInterval)

    /// "step=<label> key=value ..." with numeric or fixed values.
    var logFields: String {
        switch self {
        case .checkStarted: return "step=check_begin"
        case .checkFinished(let ok): return "step=check_end outcome=\(ok ? "ok" : "failed")"
        case .deleteStarted: return "step=delete_begin"
        case .deleteFinished(let ok): return "step=delete_end outcome=\(ok ? "ok" : "failed")"
        case .confirmStarted(let limit):
            return "step=confirm_begin" + (limit.map { " limit=\(Int($0.rounded(.up)))" } ?? "")
        case .confirmAttemptStarted(let attempt): return "step=confirm_attempt_begin attempt=\(attempt)"
        case .confirmAttemptFinished(let attempt, let outcome):
            return "step=confirm_attempt_end attempt=\(attempt) outcome=\(outcome.rawValue)"
        case .confirmFinished(let outcome, let elapsed):
            return "step=confirm_end outcome=\(outcome.rawValue) elapsed=\(String(format: "%.1f", elapsed))"
        }
    }
}

/// Shared between the confirm thread and the caller that waits for it.
private final class SafeDeleteConfirmBox: @unchecked Sendable {
    private let lock = NSLock()
    private var storedOutcome: SafeDeleteConfirmOutcome?
    private var expired = false

    var isExpired: Bool { lock.withLock { expired } }
    var outcome: SafeDeleteConfirmOutcome? { lock.withLock { expired ? nil : storedOutcome } }

    func store(_ outcome: SafeDeleteConfirmOutcome) {
        lock.withLock { if !expired { storedOutcome = outcome } }
    }

    func expire() {
        lock.withLock { if storedOutcome == nil { expired = true } }
    }

    func whileActive(_ body: () -> Void) {
        lock.withLock { if !expired { body() } }
    }
}

/// The confirm step's remaining time, counted from its first rescan, so a
/// bounded rescan read ends with the confirm step instead of after it.
final class SafeDeleteConfirmWindow: @unchecked Sendable {
    private let lock = NSLock()
    private let limit: TimeInterval
    private let now: @Sendable () -> TimeInterval
    private var startedAt: TimeInterval?

    init(limit: TimeInterval,
         now: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.limit = limit
        self.now = now
    }

    func remaining() -> TimeInterval {
        lock.withLock {
            let current = now()
            let start = startedAt ?? current
            startedAt = start
            return max(0, limit - (current - start))
        }
    }
}

/// Isolated Stage 5.2 safety coordinator. It is deliberately not connected
/// to SwiftUI or MapEngine. A caller must provide explicit confirmation, a
/// live device check, exact manifest identity, and a post-delete rescan.
/// Safe Update verifies the newly written remote object before calling this
/// adapter to remove the exact previous object. No local backup is required.
struct SafeDeleteAdapter: Sendable {
    private static let postDeleteRescanAttempts = 3
    static let rescanFailedMessage = "The Garmin device could not be rescanned after removal."

    /// The confirm step (the rescans after the delete) ends at this limit.
    /// nil keeps the unbounded wait for callers whose rescan is bounded on
    /// its own. When the limit is reached Remove reports the confirm as
    /// failed at once; it never retries the delete.
    let confirmTimeLimit: TimeInterval?
    let settleInterval: TimeInterval
    let retryInterval: TimeInterval

    init(confirmTimeLimit: TimeInterval? = nil,
         settleInterval: TimeInterval = 0.75,
         retryInterval: TimeInterval = 0.5) {
        self.confirmTimeLimit = confirmTimeLimit
        self.settleInterval = settleInterval
        self.retryInterval = retryInterval
    }

    func delete(
        target: SafeDeleteTarget,
        confirmed: Bool,
        deviceConnected: Bool,
        rescan: @escaping @Sendable () throws -> [InstalledMapFile],
        transport: any SafeDeleteTransport,
        onProgress: (@Sendable (SafeDeleteProgress) -> Void)? = nil,
        onStep: (@Sendable (SafeDeleteStep) -> Void)? = nil
    ) -> SafeDeleteResult {
        guard confirmed else {
            return result(
                target,
                status: .blockedConfirmationRequired,
                message: "Explicit confirmation is required before removing this map."
            )
        }

        guard deviceConnected else {
            return result(
                target,
                status: .failedDeviceDisconnected,
                message: "The Garmin device is not connected. Nothing was removed."
            )
        }

        guard isEligibleTarget(target) else {
            return result(
                target,
                status: .blockedOwnership,
                message: "This map is not proven to be managed by Terento. It was left untouched."
            )
        }

        guard isValidIntegrityRecord(target) else {
            return result(
                target,
                status: .blockedIntegrityCheck,
                message: "The map identity or integrity record did not match exactly. Nothing was removed."
            )
        }

        let progressReporter = SafeDeleteProgressReporter(
            totalBytes: target.expectedSizeBytes,
            onProgress: onProgress
        )

        progressReporter.report(state: .verifying, fraction: 0)

        let current: SafeDeleteDeviceObject
        onStep?(.checkStarted)
        do {
            current = try transport.inspectExactObject(target, onProgress: { transfer in
                progressReporter.report(
                    state: .verifying,
                    fraction: transfer.fractionCompleted * 0.20,
                    bytesPerSecond: transfer.bytesPerSecond
                )
            })
            onStep?(.checkFinished(succeeded: true))
        } catch let error as SafeDeleteTransportError {
            onStep?(.checkFinished(succeeded: false))
            return result(target, status: status(for: error), message: message(for: error))
        } catch {
            onStep?(.checkFinished(succeeded: false))
            return result(
                target,
                status: .failedOperation,
                message: "Terento could not validate the map before removal. Nothing was removed."
            )
        }

        guard matchesExpectedObject(current, target: target) else {
            return result(
                target,
                status: .blockedIntegrityCheck,
                message: "The map on the device no longer matches the verified record. Nothing was removed."
            )
        }


        guard let currentObjectID = current.file.itemID, currentObjectID != 0 else {
            return result(
                target,
                status: .blockedIntegrityCheck,
                message: "The map no longer has a valid live object identity. Nothing was removed."
            )
        }
        let resolvedTarget = target.resolvingObjectID(currentObjectID)
        progressReporter.report(state: .checkingContent, fraction: 0.20)

        onStep?(.deleteStarted)
        do {
            try transport.deleteExactObject(resolvedTarget, onProgress: { transfer in
                progressReporter.report(state: .checkingContent,
                    fraction: 0.20 + 0.70 * transfer.fractionCompleted)
            })
            onStep?(.deleteFinished(succeeded: true))
        } catch let error as SafeDeleteTransportError {
            onStep?(.deleteFinished(succeeded: false))
            return result(target, status: status(for: error), message: message(for: error))
        } catch {
            onStep?(.deleteFinished(succeeded: false))
            return result(
                target,
                status: .failedOperation,
                message: "The map could not be removed. Nothing else was changed."
            )
        }

        progressReporter.report(state: .postVerifying, fraction: 0.93)
        onStep?(.confirmStarted(timeLimit: confirmTimeLimit))
        let confirmStarted = ProcessInfo.processInfo.systemUptime
        let outcome = boundedConfirm(target: target, rescan: rescan, onStep: onStep,
            reportConfirming: { progressReporter.report(state: .postVerifying, fraction: 0.93) })
        let elapsed = ProcessInfo.processInfo.systemUptime - confirmStarted
        onStep?(.confirmFinished(outcome: outcome, elapsed: elapsed))

        switch outcome {
        case .absent:
            progressReporter.report(state: .completed, fraction: 1)
            return result(
                target,
                status: .success,
                message: target.ownership == .detectedNotManaged
                    ? "The third-party map was removed and verified as absent."
                    : "The Terento-managed map was removed and verified as absent."
            )
        case .stillPresent:
            return result(
                target,
                status: .failedPostVerify,
                message: "Removal could not be verified after rescanning the Garmin device."
            )
        case .readFailed, .timedOut:
            return result(target, status: .failedPostVerify, message: Self.rescanFailedMessage)
        }
    }

    /// Runs the confirm step under `confirmTimeLimit`. A rescan that does not
    /// return in time is left to its own bounded read; no further attempt
    /// starts once the limit is reached.
    private func boundedConfirm(
        target: SafeDeleteTarget,
        rescan: @escaping @Sendable () throws -> [InstalledMapFile],
        onStep: (@Sendable (SafeDeleteStep) -> Void)?,
        reportConfirming: @escaping @Sendable () -> Void
    ) -> SafeDeleteConfirmOutcome {
        guard let confirmTimeLimit else {
            return confirmRemoval(target: target, rescan: rescan, isExpired: { false },
                                  onStep: onStep, reportConfirming: reportConfirming)
        }
        let box = SafeDeleteConfirmBox()
        let finished = DispatchSemaphore(value: 0)
        let adapter = self
        Thread.detachNewThread {
            box.store(adapter.confirmRemoval(target: target, rescan: rescan,
                isExpired: { box.isExpired }, onStep: onStep,
                // A rescan left running past the limit never moves the row again.
                reportConfirming: { box.whileActive(reportConfirming) }))
            finished.signal()
        }
        if finished.wait(timeout: .now() + max(0, confirmTimeLimit)) == .timedOut {
            box.expire()
        }
        return box.outcome ?? .timedOut
    }

    // DeleteObject completes before the watch has necessarily published
    // its refreshed object list. Wait briefly, then use fresh read-only
    // MTP sessions for bounded verification retries. This never retries
    // the destructive delete itself.
    private func confirmRemoval(
        target: SafeDeleteTarget,
        rescan: @Sendable () throws -> [InstalledMapFile],
        isExpired: () -> Bool,
        onStep: (@Sendable (SafeDeleteStep) -> Void)?,
        reportConfirming: () -> Void
    ) -> SafeDeleteConfirmOutcome {
        Thread.sleep(forTimeInterval: settleInterval)
        var observedSuccessfulRescan = false
        for attempt in 0..<Self.postDeleteRescanAttempts {
            if attempt > 0 {
                Thread.sleep(forTimeInterval: retryInterval)
            }
            guard !isExpired() else { return .timedOut }

            reportConfirming()
            onStep?(.confirmAttemptStarted(attempt: attempt + 1))
            do {
                let remaining = try rescan()
                observedSuccessfulRescan = true
                // Rescans open fresh sessions, where the deleted object's
                // handle may already identify an unrelated object. Its exact
                // stable path, not its historical handle, proves presence.
                let stillPresent = remaining.contains {
                    $0.path == target.expectedPath
                }
                onStep?(.confirmAttemptFinished(attempt: attempt + 1,
                                                outcome: stillPresent ? .stillPresent : .absent))
                if !stillPresent {
                    return .absent
                }
            } catch {
                onStep?(.confirmAttemptFinished(attempt: attempt + 1, outcome: .readFailed))
                continue
            }
        }
        return observedSuccessfulRescan ? .stillPresent : .readFailed
    }

    private func isEligibleTarget(_ target: SafeDeleteTarget) -> Bool {
        switch target.ownership {
        case .managedByTerento:
            guard target.expectedPath == "/GARMIN/\(target.expectedFilename)" else {
                return false
            }

            let generator = TerentoManagedFilenameGenerator()
            // The exact path, filename, size, identity, and hash still come
            // from the manifest-backed lifecycle context. Match normalized
            // identity here because composite provider regions such as
            // ESP_CANARIAS lose separators when represented as MapIdentity.
            let artifactKind = generator.artifactKind(for: target.expectedFilename) ?? .main
            return generator.matchesIdentity(
                target.expectedFilename,
                providerId: target.mapIdentity.provider,
                regionId: target.mapIdentity.region,
                version: target.expectedVersion,
                artifactKind: artifactKind
            )
        case .detectedNotManaged:
            return target.allowsExternalRemoval
                && isSafeExternalMapTarget(target)
        case .unknown:
            return false
        }
    }

    private func isValidIntegrityRecord(_ target: SafeDeleteTarget) -> Bool {
        guard target.objectID != 0,
              target.expectedSizeBytes > 0 else {
            return false
        }

        if target.ownership == .detectedNotManaged {
            // External maps need no trusted manifest hash. Production transport
            // binds confirmation to captured content and revalidates its full
            // hash, IMG header and exact target in the native delete session.
            return true
        }

        let hash = normalizedHash(target.expectedSHA256)
        return hash.count == 64
            && hash.allSatisfy { $0.isHexDigit }
    }

    private func matchesExpectedObject(
        _ object: SafeDeleteDeviceObject,
        target: SafeDeleteTarget
    ) -> Bool {
        let exactFile = object.file.itemID != nil
            && object.file.itemID != 0
            && object.file.path == target.expectedPath
            && object.file.filename == target.expectedFilename
            && object.file.sizeBytes == target.expectedSizeBytes

        guard exactFile else { return false }

        if !object.contentHashVerified {
            // This domain-level check can precede content verification. The
            // production native boundary must still match the manifest hash for
            // managed maps, or the confirmed content hash for external maps.
            return target.ownership == .managedByTerento
                || target.ownership == .detectedNotManaged
        }

        let liveHash = normalizedHash(object.sha256)
        guard liveHash.count == 64,
              liveHash.allSatisfy(\.isHexDigit) else {
            return false
        }

        if target.ownership == .detectedNotManaged {
            return true
        }

        return liveHash == normalizedHash(target.expectedSHA256)
    }

    private func isSafeExternalMapTarget(_ target: SafeDeleteTarget) -> Bool {
        guard target.expectedPath == "/GARMIN/\(target.expectedFilename)",
              target.expectedFilename.lowercased().hasSuffix(".img"),
              !target.expectedFilename.contains("/"),
              !target.expectedFilename.contains("\\"),
              !target.expectedFilename.contains(".."),
              !target.expectedFilename.contains("\0") else {
            return false
        }

        let lowercased = target.expectedFilename.lowercased()
        let protectedNames = Set([
            "gmapbmap.img",
            "gmaptz.img",
            "gmappmap.img",
            "gmapprom.img",
            "gmapdem.img",
            "gmap3d.img",
            "gmaprgn.img"
        ])
        return !protectedNames.contains(lowercased)
            && !(lowercased.hasPrefix("d") && lowercased.hasSuffix(".img"))
    }

    private func status(for error: SafeDeleteTransportError) -> SafeDeleteStatus {
        switch error {
        case .deviceDisconnected:
            return .failedDeviceDisconnected
        case .deviceBusy:
            return .failedDeviceBusy
        case .objectNotFound:
            return .failedObjectNotFound
        case .operationFailed:
            return .failedOperation
        }
    }

    private func message(for error: SafeDeleteTransportError) -> String {
        switch error {
        case .deviceDisconnected:
            return "The Garmin device was disconnected. Nothing else was changed."
        case .deviceBusy:
            return "The device is busy or another app is using it. Quit Garmin Express and other apps that connect to your device, unplug the device and plug it back in, then choose Refresh. Nothing was removed."
        case .objectNotFound:
            return "The map was not found on the Garmin device. Nothing was removed."
        case .operationFailed:
            return "The map could not be validated or removed. Nothing else was changed."
        }
    }

    private func result(
        _ target: SafeDeleteTarget,
        status: SafeDeleteStatus,
        message: String
    ) -> SafeDeleteResult {
        SafeDeleteResult(mapIdentity: target.mapIdentity, status: status, message: message)
    }

    private func normalizedHash(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

}

/// Lifecycle-facing façade kept separate from SwiftUI and MapEngine. Future
/// UI confirmation can call this façade without gaining direct MTP access.
enum MapLifecycleOwnershipSource: Sendable {
    case manifest
    case failedInstallRecovery
    case external
}

struct MapLifecycleManager: Sendable {
    private let safeDeleteAdapter: SafeDeleteAdapter
    private let manifestCleanupStore: any TerentoManifestCleanupStore
    private let recoveryCleanupStore: any TerentoFailedInstallRecoveryStore

    init(
        safeDeleteAdapter: SafeDeleteAdapter = SafeDeleteAdapter(),
        manifestCleanupStore: any TerentoManifestCleanupStore = LocalTerentoManifestStore(),
        recoveryCleanupStore: any TerentoFailedInstallRecoveryStore = LocalTerentoFailedInstallRecoveryStore()
    ) {
        self.safeDeleteAdapter = safeDeleteAdapter
        self.manifestCleanupStore = manifestCleanupStore
        self.recoveryCleanupStore = recoveryCleanupStore
    }

    func delete(
        target: SafeDeleteTarget,
        confirmed: Bool,
        deviceConnected: Bool,
        rescan: @escaping @Sendable () throws -> [InstalledMapFile],
        transport: any SafeDeleteTransport,
        ownershipSource: MapLifecycleOwnershipSource = .manifest,
        onProgress: (@Sendable (SafeDeleteProgress) -> Void)? = nil,
        onStep: (@Sendable (SafeDeleteStep) -> Void)? = nil
    ) -> SafeDeleteResult {
        let result = safeDeleteAdapter.delete(
            target: target,
            confirmed: confirmed,
            deviceConnected: deviceConnected,
            rescan: rescan,
            transport: transport,
            onProgress: onProgress,
            onStep: onStep
        )

        guard result.isSuccess else {
            return result
        }

        if case .external = ownershipSource {
            return result
        }

        do {
            let manifestRemoved: Bool
            let recoveryRemoved: Bool

            switch ownershipSource {
            case .manifest:
                manifestRemoved = try manifestCleanupStore.remove(
                    deviceKey: target.deviceKey,
                    devicePath: target.expectedPath,
                    filename: target.expectedFilename
                )
                recoveryRemoved = false
            case .failedInstallRecovery:
                recoveryRemoved = try recoveryCleanupStore.remove(
                    deviceKey: target.deviceKey,
                    devicePath: target.expectedPath,
                    filename: target.expectedFilename
                )
                // A stale recovery marker may coexist with a manifest if a
                // successful install could not clean its marker. Remove both
                // local records when the device object has already passed
                // the full Safe Delete verification.
                manifestRemoved = (try? manifestCleanupStore.remove(
                    deviceKey: target.deviceKey,
                    devicePath: target.expectedPath,
                    filename: target.expectedFilename
                )) == true
            case .external:
                manifestRemoved = false
                recoveryRemoved = false
            }

            guard manifestRemoved || recoveryRemoved else {
                return SafeDeleteResult(
                    mapIdentity: target.mapIdentity,
                    status: .failedManifestCleanup,
                    message: "The map was removed from the Garmin device, but its local recovery record was not found. Do not retry blindly."
                )
            }
        } catch {
            return SafeDeleteResult(
                mapIdentity: target.mapIdentity,
                status: .failedManifestCleanup,
                message: "The map was removed from the Garmin device, but Terento could not update its local ownership record. Do not retry blindly."
            )
        }

        return result
    }
}

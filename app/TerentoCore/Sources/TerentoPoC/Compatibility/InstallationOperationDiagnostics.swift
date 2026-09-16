import Foundation

/// One immutable operation context, owned by the operation rather than a view.
/// Observers only copy results: they never authorize or perform device operations.
/// The existing controller owns persistence, consent and retry of the same event IDs.
final class InstallationOperationDiagnostics: @unchecked Sendable {
    private struct Item {
        let package: MapPackage
        let artifactIDs: Set<String>
        let eventID = UUID()
        var results: [String: MapInstallationResult] = [:]
        var recorded = false
    }

    let operationID: UUID
    private let identity: DeviceIdentity
    private let controller: InstallationEvidenceController
    private let lock = NSLock()
    private var items: [Item]
    private var disconnected = false
    #if TERENTO_TESTING
    private var deliveryTasks: [Task<Void, Never>] = []
    #endif

    init(operationID: UUID, identity: DeviceIdentity, plan: InstallationPlan,
         controller: InstallationEvidenceController) {
        self.operationID = operationID
        self.identity = identity
        self.controller = controller
        items = plan.installItems.map { item in
            Item(package: item.package, artifactIDs: plan.selectedPackagePlans.first {
                $0.item.package.id == item.package.id
            }?.artifactPlan.selectedArtifactIDs ?? [])
        }
    }

    /// An observed device reset is distinct from ordinary task cancellation.
    /// Do not synthesize write facts here; a worker may still return its real result.
    func deviceDisconnected() {
        lock.lock(); defer { lock.unlock() }
        disconnected = true
    }

    func record(_ result: MapInstallationResult, packageID: String, artifactID: String) {
        guard result.status != .confirmationRequired else { return }
        lock.lock(); defer { lock.unlock() }
        guard let index = items.firstIndex(where: { $0.package.id == packageID }),
              !items[index].recorded, items[index].artifactIDs.contains(artifactID) else { return }
        items[index].results[artifactID] = result
        if !result.isSuccess {
            finishFailure(index: index, stage: result.failure == .deviceDisconnected && !result.diagnostics.writeStarted
                ? .preflight : Self.stage(for: result.failure), failure: result.failure,
                          native: result.diagnostics.nativeFailureCode.flatMap { EvidenceNativeFailureCode(rawValue: $0.rawValue) })
        } else if Set(items[index].results.keys) == items[index].artifactIDs {
            enqueue([event(index: index, outcome: .succeeded, stage: nil, failure: nil, native: nil)])
        }
    }

    /// Used only at an observed failed boundary. No raw exception text is retained.
    func failed(index: Int, stage: EvidenceFailureStage, failure: InstallationFailure?,
                native: EvidenceNativeFailureCode? = nil, cancelled: Bool = false) {
        lock.lock(); defer { lock.unlock() }
        // Cancellation is not an installation failure. Completed/failed component
        // facts already recorded remain intact; unattempted maps are not invented.
        guard !cancelled || disconnected, items.indices.contains(index) else { return }
        if items[index].recorded {
            // Disconnect during the between-map settle wait cannot change the
            // completed map into a failure or pretend the next map was attempted.
            if cancelled && disconnected {
                let remaining = items.indices.filter { !items[$0].recorded && items[$0].results.isEmpty }
                enqueue(remaining.map { event(index: $0, outcome: .notStarted, stage: .preflight,
                                             failure: nil, native: nil) })
            }
            return
        }
        finishFailure(index: index, stage: stage,
                      failure: disconnected ? .deviceDisconnected : failure,
                      native: disconnected ? .deviceDisconnected : native)
    }

    private func finishFailure(index: Int, stage: EvidenceFailureStage,
                               failure: InstallationFailure?, native: EvidenceNativeFailureCode?) {
        var events = [event(index: index, outcome: .failed, stage: stage, failure: failure, native: native)]
        for remaining in items.indices where !items[remaining].recorded {
            // A selected map is NOT_STARTED only if no component result proves a write.
            // Normally these are later batch maps, or all other maps after preflight.
            guard items[remaining].results.isEmpty else { continue }
            events.append(event(index: remaining, outcome: .notStarted, stage: .preflight, failure: nil, native: nil))
        }
        enqueue(events)
    }

    private func event(index: Int, outcome: InstallationEvidenceOutcome, stage: EvidenceFailureStage?,
                       failure: InstallationFailure?, native: EvidenceNativeFailureCode?) -> InstallationEvidenceEvent {
        let item = items[index]
        items[index].recorded = true
        let diagnostics = item.results.values.map(\.diagnostics)
        let failed = outcome == .failed
        let notStarted = outcome == .notStarted
        return InstallationEvidenceEvent(
            id: item.eventID, identity: identity, package: item.package, outcome: outcome,
            finishingResult: outcome == .succeeded ? .verified : (notStarted ? .notReached : .failed),
            errorCategory: failed ? Self.category(for: failure) : nil,
            operationId: operationID, mapResultIndex: index, selectedMapCount: items.count,
            failureStage: stage,
            failureCode: notStarted ? "INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE"
                : (failed ? failure?.rawValue ?? "INSTALL_FAILED_UNKNOWN" : nil),
            nativeFailureCode: failed ? native : nil,
            writeStarted: diagnostics.contains { $0.writeStarted },
            remoteObjectCreated: diagnostics.contains { $0.remoteObjectCreated },
            cleanupAttempted: diagnostics.contains { $0.cleanupAttempted },
            cleanupSucceeded: diagnostics.contains { $0.cleanupSucceeded },
            transferProgressBucket: EvidenceTransferProgressBucket(
                bytes: diagnostics.reduce(0) { $0 + $1.bytesTransferred },
                total: diagnostics.reduce(0) { $0 + $1.transferTotalBytes })
        )
    }

    private func enqueue(_ events: [InstallationEvidenceEvent]) {
        // This task belongs to delivery, not to the screen or cancelled native task.
        let controller = controller
        let task = Task { @MainActor in
            _ = await controller.recordAndUpload(events)
        }
        #if TERENTO_TESTING
        deliveryTasks.append(task)
        #endif
    }

    #if TERENTO_TESTING
    func waitForDeliveryForTesting() async {
        let tasks = deliverySnapshot()
        for task in tasks { await task.value }
    }
    private func deliverySnapshot() -> [Task<Void, Never>] {
        lock.lock(); defer { lock.unlock() }
        return deliveryTasks
    }
    #endif

    static func stage(for failure: InstallationFailure?) -> EvidenceFailureStage {
        switch failure {
        case .manifestFailed: return .manifest
        case .cleanupFailed: return .cleanup
        case .sizeMismatch, .hashMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired: return .verify
        case .writeFailed, .deviceDisconnected: return .write
        case .preflightMTPReadFailed: return .preflight
        case .sourceArtifactInvalid, .sourceValidationFailed: return .sourceValidation
        default: return .preflight
        }
    }

    private static func category(for failure: InstallationFailure?) -> EvidenceErrorCategory {
        switch failure {
        case .insufficientSpace: return .storage
        case .deviceDisconnected: return .deviceDisconnected
        case .downloadFailed: return .acquisition
        case .sourceArtifactInvalid, .sourceValidationFailed: return .sourceValidation
        case .hashMismatch, .sizeMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired: return .verification
        case .stableWatchIdentityUnavailable, nil: return .unknown
        case .preflightMTPReadFailed: return .transport
        default: return .transport
        }
    }
}

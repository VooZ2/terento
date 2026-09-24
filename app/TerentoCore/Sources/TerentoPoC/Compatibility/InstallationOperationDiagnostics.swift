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
        var failureContext: InstallationFailureContext?
        var originalFailureContext: InstallationFailureContext?
        var failedComponentKind: InstallationFailureContext.ComponentKind?
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
        guard result.status != .confirmationRequired,
              result.status != .blockedInstallationAuthorization else { return }
        lock.lock(); defer { lock.unlock() }
        guard let index = items.firstIndex(where: { $0.package.id == packageID }),
              !items[index].recorded, items[index].artifactIDs.contains(artifactID) else { return }
        items[index].results[artifactID] = result
        if !result.isSuccess {
            let component = items[index].package.artifacts.first { $0.id == artifactID }
                .flatMap { InstallationFailureContext.ComponentKind(rawValue: $0.kind.rawValue) }
            items[index].failedComponentKind = component
            items[index].failureContext = result.failureContext.map {
                $0.at($0.boundary, componentKind: component)
            }
            items[index].originalFailureContext = result.originalFailureContext.map {
                $0.at($0.boundary, componentKind: component)
            }
            finishFailure(index: index, stage: InstallationFailureStageResolver.stage(
                for: result.failure, context: items[index].failureContext,
                writeStarted: result.diagnostics.writeStarted), failure: result.failure,
                          native: result.diagnostics.nativeFailureCode.flatMap { EvidenceNativeFailureCode(rawValue: $0.rawValue) })
        } else if Set(items[index].results.keys) == items[index].artifactIDs {
            enqueue([event(index: index, outcome: .succeeded, stage: nil, failure: nil, native: nil)])
        }
    }

    /// Used only at an observed failed boundary. No raw exception text is retained.
    func failed(index: Int, stage: EvidenceFailureStage, failure: InstallationFailure?,
                native: EvidenceNativeFailureCode? = nil, cancelled: Bool = false,
                context: InstallationFailureContext? = nil,
                componentKind: InstallationFailureContext.ComponentKind? = nil) {
        lock.lock(); defer { lock.unlock() }
        let knownReadBoundary = context.map {
            [.initialSnapshot, .initialInventory, .prewriteInventory].contains($0.boundary)
        } ?? (native == .preflightMTPReadFailed)
        // The task's cancellation flag may arrive after the native read failed.
        // Only an actual cancellation outcome supersedes concrete read evidence.
        let observedReadFailure = context?.resultKind != .cancelled && (
            (knownReadBoundary && context?.resultKind != nil)
                || failure == .preflightMTPReadFailed || native == .preflightMTPReadFailed
        )
        let cancellationOnly = context?.resultKind == .cancelled || (cancelled && !observedReadFailure)
        guard !cancellationOnly || disconnected, items.indices.contains(index) else { return }
        if items[index].recorded {
            // Disconnect during the between-map settle wait cannot change the
            // completed map into a failure or pretend the next map was attempted.
            if cancellationOnly && disconnected {
                let remaining = items.indices.filter { !items[$0].recorded && items[$0].results.isEmpty }
                enqueue(remaining.map { event(index: $0, outcome: .notStarted, stage: .preflight,
                                             failure: nil, native: nil) })
            }
            return
        }
        items[index].failureContext = context
        items[index].failedComponentKind = componentKind ?? context?.componentKind
        // A later connection invalidation does not rewrite an observed cause.
        let confirmedCancellation = cancellationOnly && disconnected
        let classifiedFailure = failure ?? (knownReadBoundary ? .preflightMTPReadFailed : nil)
        finishFailure(index: index, stage: context.map { InstallationFailureStageResolver.stage(for: $0.boundary) } ?? stage,
                      failure: confirmedCancellation ? .deviceDisconnected : classifiedFailure,
                      native: confirmedCancellation ? .deviceDisconnected : native)
    }

    private func finishFailure(index: Int, stage: EvidenceFailureStage,
                               failure: InstallationFailure?, native: EvidenceNativeFailureCode?) {
        let item = items[index]
        let mainSucceeded = item.package.artifacts.filter { $0.kind == .main }
            .contains { item.results[$0.id]?.isSuccess == true }
        let optionalFailed = item.failedComponentKind == .contours
        var events = [event(index: index, outcome: mainSucceeded && optionalFailed ? .succeeded : .failed,
                            stage: stage, failure: failure, native: native)]
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
        let context = notStarted ? nil : item.failureContext
        let optionalFailed = !notStarted && item.failedComponentKind == .contours
        return InstallationEvidenceEvent(
            id: item.eventID, identity: identity, package: item.package, outcome: outcome,
            finishingResult: outcome == .succeeded ? .verified : (notStarted ? .notReached : .failed),
            errorCategory: failed ? Self.category(for: failure) : nil,
            operationId: operationID, mapResultIndex: index, selectedMapCount: items.count,
            failureStage: outcome == .succeeded ? nil : stage,
            failureCode: notStarted ? "INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE"
                : (failed ? failure?.rawValue ?? "INSTALL_FAILED_UNKNOWN" : nil),
            nativeFailureCode: failed ? native : nil,
            writeStarted: diagnostics.contains { $0.writeStarted },
            remoteObjectCreated: diagnostics.contains { $0.remoteObjectCreated },
            cleanupAttempted: diagnostics.contains { $0.cleanupAttempted },
            cleanupSucceeded: diagnostics.contains { $0.cleanupSucceeded },
            transferProgressBucket: EvidenceTransferProgressBucket(
                bytes: diagnostics.reduce(0) { $0 + $1.bytesTransferred },
                total: diagnostics.reduce(0) { $0 + $1.transferTotalBytes }),
            failureContext: context,
            originalFailureContext: notStarted ? nil : item.originalFailureContext,
            optionalComponentSelected: optionalFailed ? true : nil,
            optionalComponentOutcome: optionalFailed ? "FAILED" : nil,
            optionalComponentFailureStage: optionalFailed ? stage : nil,
            optionalComponentFailureCode: optionalFailed ? failure?.rawValue : nil,
            optionalComponentNativeFailureCode: optionalFailed ? native : nil
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
        InstallationFailureStageResolver.stage(for: failure, context: nil, writeStarted: true)
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

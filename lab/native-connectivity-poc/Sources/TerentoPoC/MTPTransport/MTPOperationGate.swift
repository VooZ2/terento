import Foundation

/// Native MTP operations are process-wide resources on macOS. This gate is
/// deliberately below SwiftUI so presence checks, catalog loading, inventory
/// reads, backup, removal, update, and installation cannot overlap.
enum MTPOperationKind: String, Sendable {
    case presence
    case catalog
    case inventory
    case backup
    case remove
    case update
    case install
}

struct MTPOperationLease: Equatable, Sendable {
    fileprivate let id: UUID
}

enum MTPOperationGateError: LocalizedError, Equatable, Sendable {
    case lifecycleBusy
    case lifecycleInvalidated

    var errorDescription: String? {
        switch self {
        case .lifecycleBusy:
            return "Another Garmin operation is already in progress."
        case .lifecycleInvalidated:
            return "The Garmin connection changed before this operation could continue."
        }
    }
}

/// A small synchronous arbiter around the synchronous libmtp bridge.
///
/// Waiting is cancellable while an operation is queued. Once the native
/// bridge has been entered, cancellation cannot interrupt libmtp safely; the
/// caller remains busy until that call returns and the resource is released.
final class MTPOperationGate: @unchecked Sendable {
    static let shared = MTPOperationGate()

    private let condition = NSCondition()
    private var activeNativeOperation: UUID?
    private var activeNativeOperationKind: MTPOperationKind?
    private var lifecycleLeaseID: UUID?
    private var lifecycleInvalidated = false

    var isNativeOperationActive: Bool {
        condition.lock()
        defer { condition.unlock() }
        return activeNativeOperation != nil
    }

    var isLifecycleActive: Bool {
        condition.lock()
        defer { condition.unlock() }
        return lifecycleLeaseID != nil
    }

    var isBusy: Bool {
        condition.lock()
        defer { condition.unlock() }
        return activeNativeOperation != nil || lifecycleLeaseID != nil
    }

    var canEject: Bool {
        condition.lock()
        defer { condition.unlock() }

        guard lifecycleLeaseID == nil else {
            return false
        }

        // A presence probe is read-only and cancellable at the Swift layer.
        // Safe Eject cancels that probe and waits for the synchronous native
        // call to release its handle before showing "Safe to disconnect".
        return activeNativeOperation == nil || activeNativeOperationKind == .presence
    }

    /// Reserves the lifecycle boundary without holding the native-operation
    /// lock across local download/validation work. Native adapters must pass
    /// this lease back to `withOperation`.
    func beginLifecycle() throws -> MTPOperationLease {
        condition.lock()
        defer { condition.unlock() }

        while lifecycleLeaseID != nil || activeNativeOperation != nil {
            try waitForChange()
        }

        let id = UUID()
        lifecycleLeaseID = id
        lifecycleInvalidated = false
        return MTPOperationLease(id: id)
    }

    /// Async counterpart used by UI-owned lifecycle tasks. It polls without
    /// blocking the main actor, so cancelling the task can stop a queued
    /// operation before it owns the native boundary.
    func beginLifecycleAsync() async throws -> MTPOperationLease {
        while !Task.isCancelled {
            if let lease = try beginLifecycleIfAvailable() {
                return lease
            }
            try await Task.sleep(for: .milliseconds(50))
        }

        throw CancellationError()
    }

    func invalidateLifecycleOperations() {
        condition.lock()
        lifecycleInvalidated = true
        condition.broadcast()
        condition.unlock()
    }

    func isValid(_ lease: MTPOperationLease) -> Bool {
        condition.lock()
        defer { condition.unlock() }
        return lifecycleLeaseID == lease.id && !lifecycleInvalidated
    }

    func endLifecycle(_ lease: MTPOperationLease) {
        condition.lock()
        if lifecycleLeaseID == lease.id {
            lifecycleLeaseID = nil
            lifecycleInvalidated = false
            condition.broadcast()
        }
        condition.unlock()
    }

    func withOperation<T>(
        kind: MTPOperationKind,
        lifecycleLease: MTPOperationLease? = nil,
        _ body: () throws -> T
    ) throws -> T {
        let operationID = UUID()

        condition.lock()
        do {
            while activeNativeOperation != nil {
                try waitForChange()
            }

            if let lifecycleID = lifecycleLeaseID {
                guard lifecycleLease?.id == lifecycleID else {
                    throw MTPOperationGateError.lifecycleBusy
                }
                guard !lifecycleInvalidated else {
                    throw MTPOperationGateError.lifecycleInvalidated
                }
            }

            guard !Task.isCancelled else {
                throw CancellationError()
            }

            activeNativeOperation = operationID
            activeNativeOperationKind = kind
            condition.unlock()
        } catch {
            condition.unlock()
            throw error
        }

        defer {
            condition.lock()
            if activeNativeOperation == operationID {
                activeNativeOperation = nil
                activeNativeOperationKind = nil
                condition.broadcast()
            }
            condition.unlock()
        }

        // Do not claim a queued cancellation stopped native work. This check
        // only prevents entry; once body starts, the bridge owns the thread.
        try Task.checkCancellation()
        return try body()
    }

    /// Serializes metadata work that does not open an MTP session with the
    /// native lifecycle. Catalog loading is kept here so Eject and presence
    /// monitoring observe one complete Maps operation instead of a gap between
    /// catalog and inventory work.
    func withAsyncOperation<T: Sendable>(
        kind: MTPOperationKind,
        _ body: @escaping @Sendable () async throws -> T
    ) async throws -> T {
        let operationID = try await beginAsyncOperation(kind: kind)
        defer { endOperation(operationID) }

        try Task.checkCancellation()
        return try await body()
    }

    private func waitForChange() throws {
        while !Task.isCancelled {
            _ = condition.wait(until: Date(timeIntervalSinceNow: 0.05))
            return
        }

        throw CancellationError()
    }

    private func beginLifecycleIfAvailable() throws -> MTPOperationLease? {
        condition.lock()
        defer { condition.unlock() }

        guard lifecycleLeaseID == nil, activeNativeOperation == nil else {
            return nil
        }

        let id = UUID()
        lifecycleLeaseID = id
        lifecycleInvalidated = false
        return MTPOperationLease(id: id)
    }

    private func beginAsyncOperation(kind: MTPOperationKind) async throws -> UUID {
        while !Task.isCancelled {
            if let operationID = claimAsyncOperationIfAvailable(kind: kind) {
                return operationID
            }

            try await Task.sleep(for: .milliseconds(50))
        }

        throw CancellationError()
    }

    private func claimAsyncOperationIfAvailable(kind: MTPOperationKind) -> UUID? {
        condition.lock()
        defer { condition.unlock() }

        guard activeNativeOperation == nil, lifecycleLeaseID == nil else {
            return nil
        }

        let operationID = UUID()
        activeNativeOperation = operationID
        activeNativeOperationKind = kind
        return operationID
    }

    private func endOperation(_ operationID: UUID) {
        condition.lock()
        if activeNativeOperation == operationID {
            activeNativeOperation = nil
            activeNativeOperationKind = nil
            condition.broadcast()
        }
        condition.unlock()
    }
}

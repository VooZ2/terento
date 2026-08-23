import Foundation

/// Native MTP operations are process-wide resources on macOS. This gate is
/// deliberately below SwiftUI so presence checks, inventory reads, backup,
/// removal, update, and installation cannot open competing sessions.
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
        !isBusy
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
            } else if kind == .presence {
                // A lifecycle reservation pauses presence before any new
                // native session can be opened.
                throw MTPOperationGateError.lifecycleBusy
            } else if lifecycleLeaseID != nil {
                throw MTPOperationGateError.lifecycleBusy
            }

            guard !Task.isCancelled else {
                throw CancellationError()
            }

            activeNativeOperation = operationID
            condition.unlock()
        } catch {
            condition.unlock()
            throw error
        }

        defer {
            condition.lock()
            if activeNativeOperation == operationID {
                activeNativeOperation = nil
                condition.broadcast()
            }
            condition.unlock()
        }

        // Do not claim a queued cancellation stopped native work. This check
        // only prevents entry; once body starts, the bridge owns the thread.
        try Task.checkCancellation()
        return try body()
    }

    private func waitForChange() throws {
        while !Task.isCancelled {
            _ = condition.wait(until: Date(timeIntervalSinceNow: 0.05))
            if activeNativeOperation == nil {
                return
            }
        }

        throw CancellationError()
    }
}

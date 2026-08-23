import Foundation

struct InstallationTransaction: Equatable, Sendable {
    let id: UUID
    private(set) var state: InstallationTransactionState = .idle
    private(set) var failure: InstallationFailure? = nil
    private(set) var sourceSizeBytes: UInt64?
    private(set) var sourceSHA256: String?
    private(set) var transferVerification: TransferVerification?

    init(id: UUID = UUID()) {
        self.id = id
    }

    mutating func begin() throws {
        guard state == .idle else {
            throw InstallationFailure.invalidStateTransition
        }

        state = .validating
    }

    mutating func recordSource(sizeBytes: UInt64, sha256: String) throws {
        guard state == .preparing || state == .readyToWrite else {
            throw InstallationFailure.invalidStateTransition
        }

        sourceSizeBytes = sizeBytes
        sourceSHA256 = sha256
    }

    mutating func recordTransferVerification(_ verification: TransferVerification) throws {
        guard state == .verifying else {
            throw InstallationFailure.invalidStateTransition
        }

        transferVerification = verification
    }

    mutating func fail(_ reason: InstallationFailure) throws {
        guard state != .idle, state != .completed, state != .failed else {
            throw InstallationFailure.invalidStateTransition
        }

        failure = reason
        state = .failed
    }

    mutating func transition(to nextState: InstallationTransactionState) throws {
        guard canTransition(from: state, to: nextState) else {
            throw InstallationFailure.invalidStateTransition
        }

        if nextState == .completed {
            guard transferVerification?.isVerified == true else {
                throw InstallationFailure.verificationRequired
            }
        }

        state = nextState
    }

    private func canTransition(
        from current: InstallationTransactionState,
        to next: InstallationTransactionState
    ) -> Bool {
        switch current {
        case .idle:
            return next == .validating
        case .validating:
            return next == .awaitingExistingMapDecision
                || next == .awaitingBackupDecision
                || next == .downloading
                // Stage 4.2 receives a source that has already completed the
                // Stage 4.1 acquisition pipeline, so downloading is optional.
                || next == .preparing
        case .awaitingExistingMapDecision:
            return next == .awaitingBackupDecision || next == .downloading
        case .awaitingBackupDecision:
            return next == .backingUp || next == .downloading
        case .backingUp:
            return next == .downloading
        case .downloading:
            return next == .preparing
        case .preparing:
            return next == .readyToWrite
        case .readyToWrite:
            return next == .writing
        case .writing:
            return next == .verifying
        case .verifying:
            return next == .completed
        case .completed, .failed:
            return false
        }
    }
}

final class InstallationTransactionGate: @unchecked Sendable {
    static let shared = InstallationTransactionGate()

    private let lock = NSLock()
    private var activeTransactionID: UUID?

    func acquire(transactionID: UUID) throws {
        lock.lock()
        defer { lock.unlock() }

        guard activeTransactionID == nil else {
            throw InstallationFailure.transactionAlreadyRunning
        }

        activeTransactionID = transactionID
    }

    func release(transactionID: UUID) {
        lock.lock()
        defer { lock.unlock() }

        guard activeTransactionID == transactionID else {
            return
        }

        activeTransactionID = nil
    }
}

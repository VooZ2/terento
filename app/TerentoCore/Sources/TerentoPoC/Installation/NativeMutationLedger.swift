import Foundation

enum MapMutationPurpose: UInt32, Codable, Sendable {
    case install = 1, updateNew = 2, updateOld = 3
    case removeManaged = 4, removeExternal = 5, cleanup = 6
    var kind: UInt32 { self == .install || self == .updateNew ? 1 : 2 }
}

/// One lifecycle operation, shared by transport copies. A failed or uncertain
/// step consumes the operation; it cannot mint a replacement grant.
final class NativeMutationOperation: @unchecked Sendable {
    private let lock = NSLock()
    private let mode: MapMutationPurpose
    private let root: URL?
    let operationID = UUID().uuidString.lowercased()
    private var state = "planned"
    private var oldTarget: NativeMutationLedger.Scope?
    private var sentTarget: NativeMutationLedger.Scope?
    private var directory: URL?

    init(mode: MapMutationPurpose, root: URL? = nil) {
        self.mode = mode
        self.root = root
    }

    func bindOldTarget(scope: NativeMutationLedger.Scope) throws {
        lock.lock(); defer { lock.unlock() }
        guard mode == .updateNew, state == "planned", scope.valid(requireHash: true) else {
            state = "failed"
            throw NativeMutationLedger.Failure.invalidTransition
        }
        if let oldTarget, oldTarget != scope {
            state = "failed"
            throw NativeMutationLedger.Failure.invalidTransition
        }
        oldTarget = scope
    }

    func begin(purpose: MapMutationPurpose, scope: NativeMutationLedger.Scope) throws -> NativeMutationLedger {
        lock.lock(); defer { lock.unlock() }
        let sequence: UInt32
        let allowed: Bool
        if mode == .updateNew {
            if purpose == .updateNew {
                sequence = 1
                allowed = state == "planned" && oldTarget != nil
                    && oldTarget?.physicalIdentifier == scope.physicalIdentifier
                    && oldTarget?.physicalIdentifierSource == scope.physicalIdentifierSource
                    && oldTarget?.expectedStorageID == scope.expectedStorageID
                    && oldTarget?.filename != scope.filename
            } else {
                sequence = 2
                allowed = purpose == .updateOld && state == "verified" && oldTarget == scope
            }
        } else {
            sequence = 1
            allowed = state == "planned" && ((mode == .install && purpose == .install)
                || ((mode == .removeManaged || mode == .removeExternal)
                    && (purpose == .removeManaged || purpose == .removeExternal)))
        }
        guard allowed, scope.valid(requireHash: purpose.kind == 2) else {
            state = "failed"
            throw NativeMutationLedger.Failure.invalidTransition
        }
        state = "inflight"
        if purpose == .updateNew { sentTarget = scope }
        do {
            let directory = try evidenceDirectory()
            return try NativeMutationLedger(operationID: operationID, sequence: sequence,
                purpose: purpose, scope: scope, directory: directory, operation: self)
        } catch {
            state = "failed"
            throw error
        }
    }

    fileprivate func invalidate() {
        lock.lock(); defer { lock.unlock() }
        state = "failed"
    }

    @discardableResult
    fileprivate func completed(purpose: MapMutationPurpose, success: Bool) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard state == "inflight" else { state = "failed"; return false }
        state = success ? (purpose == .updateNew ? "sent" : "completed") : "failed"
        return success
    }

    func markUpdateVerified(filename: String, size: UInt64, sha256: String) throws {
        lock.lock(); defer { lock.unlock() }
        guard mode == .updateNew, state == "sent", let sentTarget, let oldTarget,
              sentTarget.filename == filename, sentTarget.size == size,
              NativeMutationLedger.Scope.validHash(sha256), let directory else {
            state = "failed"
            throw NativeMutationLedger.Failure.invalidTransition
        }
        struct Verification: Encodable {
            let operationID: String
            let newTarget: NativeMutationLedger.Scope
            let oldTarget: NativeMutationLedger.Scope
            let verifiedSHA256: String
        }
        do {
            try NativeMutationLedger.persist(Verification(operationID: operationID,
                newTarget: sentTarget, oldTarget: oldTarget, verifiedSHA256: sha256),
                to: directory.appendingPathComponent("update-verified.json"))
            let marker = directory.appendingPathComponent("\(operationID)-verified-new")
            try Data(operationID.utf8).write(to: marker, options: .withoutOverwriting)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: marker.path)
            let handle = try FileHandle(forWritingTo: marker)
            try handle.synchronize()
            try handle.close()
            state = "verified"
        } catch {
            state = "failed"
            throw error
        }
    }

    private func evidenceDirectory() throws -> URL {
        if let directory { return directory }
        let manager = FileManager.default
        let base = try root ?? manager.url(for: .applicationSupportDirectory,
            in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("Terento/MutationEvidence", isDirectory: true)
        try manager.createDirectory(at: base, withIntermediateDirectories: true,
                                    attributes: [.posixPermissions: 0o700])
        let attributes = try manager.attributesOfItem(atPath: base.path)
        guard attributes[.type] as? FileAttributeType == .typeDirectory else {
            throw NativeMutationLedger.Failure.unsafeDirectory
        }
        let value = base.appendingPathComponent(operationID, isDirectory: true)
        try manager.createDirectory(at: value, withIntermediateDirectories: false,
                                    attributes: [.posixPermissions: 0o700])
        directory = value
        return value
    }
}

struct NativeMutationLedger {
    enum Failure: Error { case invalidTransition, incomplete, unsafeDirectory }
    /// Sensitive local evidence, never part of uploaded diagnostic payloads.
    struct Scope: Codable, Equatable, Sendable {
        let physicalIdentifierSource: UInt32
        let physicalIdentifier: String
        let expectedStorageID: UInt32
        let filename: String
        let size: UInt64
        let sha256: String?
        var path: String { "/GARMIN/\(filename)" }
        static func validHash(_ value: String) -> Bool {
            value.count == 64 && value.allSatisfy { $0.isASCII && $0.isHexDigit }
                && value != String(repeating: "0", count: 64)
        }
        func valid(requireHash: Bool) -> Bool {
            [1, 2].contains(physicalIdentifierSource) && !physicalIdentifier.isEmpty
                && expectedStorageID != 0 && size > 0 && !filename.isEmpty
                && !filename.contains("/") && !filename.contains("\\")
                && !filename.contains("..") && !filename.contains("\0")
                && (!requireHash || sha256.map(Self.validHash) == true)
        }
    }
    struct Outcome: Codable, Equatable {
        let authorized: Bool
        let attempted: Bool
        let completed: Bool
        let nativeResult: Int32
        let resultingObjectID: UInt32
        let sessionID: UInt64
        let sequence: UInt32
        let purpose: UInt32
        let kind: UInt32
    }
    private struct Entry: Codable {
        let operationID: String
        let sequence: UInt32
        let purpose: MapMutationPurpose
        let scope: Scope
        let exactPath: String
        var phase: String
        var outcome: Outcome?
    }
    let operationID: String
    let sequence: UInt32
    let purpose: MapMutationPurpose
    let claimPath: String
    private let recordURL: URL
    private var entry: Entry
    private let operation: NativeMutationOperation

    fileprivate init(operationID: String, sequence: UInt32, purpose: MapMutationPurpose,
                     scope: Scope, directory: URL, operation: NativeMutationOperation) throws {
        self.operationID = operationID
        self.sequence = sequence
        self.purpose = purpose
        self.claimPath = directory.appendingPathComponent("\(operationID)-\(sequence).claim").path
        self.recordURL = directory.appendingPathComponent("record-\(sequence).json")
        self.operation = operation
        self.entry = Entry(operationID: operationID, sequence: sequence, purpose: purpose,
            scope: scope, exactPath: scope.path, phase: "prepared")
        try Self.persist(entry, to: recordURL)
    }

    mutating func dispatch() throws {
        guard entry.phase == "prepared" else {
            operation.invalidate(); throw Failure.invalidTransition
        }
        entry.phase = "dispatched"
        do { try Self.persist(entry, to: recordURL) }
        catch { operation.completed(purpose: purpose, success: false); throw error }
    }

    mutating func finish(_ outcome: Outcome, returnedResult: Int32) throws {
        guard entry.phase == "dispatched" else {
            operation.invalidate(); throw Failure.invalidTransition
        }
        entry.outcome = outcome
        let coherent = outcome.sequence == sequence && outcome.purpose == purpose.rawValue
            && outcome.kind == purpose.kind && outcome.nativeResult == returnedResult
        let nativeSuccess = coherent && outcome.authorized && outcome.attempted && outcome.completed
            && outcome.sessionID != 0 && returnedResult == 0 && outcome.resultingObjectID != 0
        entry.phase = nativeSuccess ? "completed" : (outcome.attempted && !outcome.completed ? "unknown" : "failed")
        do { try Self.persist(entry, to: recordURL) }
        catch { operation.invalidate(); throw error }
        let success = operation.completed(purpose: purpose, success: nativeSuccess)
        if nativeSuccess && !success {
            entry.phase = "failed"
            try Self.persist(entry, to: recordURL)
        }
        guard returnedResult != 0 || success else { throw Failure.incomplete }
    }

    fileprivate static func persist<Value: Encodable>(_ value: Value, to url: URL) throws {
        try JSONEncoder().encode(value).write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.synchronize()
    }
}

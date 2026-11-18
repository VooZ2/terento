import Foundation

struct InstallationFailureContext: Codable, Equatable, Sendable {
    enum Boundary: String, Codable, Sendable {
        case initialSnapshot = "initial_snapshot"
        case initialInventory = "initial_inventory"
        case prewriteInventory = "prewrite_inventory"
        case prewriteProtection = "prewrite_protection"
        case write = "write"
        case readback = "readback"
        case postwriteInventory = "postwrite_inventory"
        case postwriteSnapshot = "postwrite_snapshot"
        case targetValidation = "target_validation"
        case postwriteProtection = "postwrite_protection"
        case cleanup = "cleanup"
        case manifest = "manifest"
        case sourceValidationComplete = "source_validation_complete"
        case preflightPolicyPassed = "preflight_policy_passed"
    }
    enum ClassificationSource: String, Codable, Sendable {
        case native = "native"
        case derived = "derived"
    }
    enum DevicePresence: String, Codable, Sendable {
        case unknown = "unknown"
        case present = "present"
        case absent = "absent"
    }
    enum Operation: String, Codable, Sendable {
        case snapshot = "snapshot"
        case inventory = "inventory"
        case filePrefix = "file_prefix"
        case fileRange = "file_range"
        case write = "write"
        case readback = "readback"
        case cleanup = "cleanup"
        case manifest = "manifest"
        case protectionCheck = "protection_check"
    }
    enum ExecutionMode: String, Codable, Sendable {
        case inProcess = "in_process"
        case worker = "worker"
    }
    enum ResultKind: String, Codable, Sendable {
        case nativeError = "native_error"
        case timeout = "timeout"
        case cancelled = "cancelled"
        case processLaunchError = "process_launch_error"
        case processExit = "process_exit"
        case requestIOError = "request_io_error"
        case responseIOError = "response_io_error"
        case decodeError = "decode_error"
        case invalidResponse = "invalid_response"
        case appError = "app_error"
        case protectionFailed = "protection_failed"
    }
    enum NativeCategory: String, Codable, Sendable {
        case detection = "detection"
        case sessionOpen = "session_open"
        case storageRead = "storage_read"
        case inventoryRead = "inventory_read"
        case objectRead = "object_read"
        case allocation = "allocation"
        case invalidArgument = "invalid_argument"
        case unspecified = "unspecified"
    }
    enum NativeCodeNamespace: String, Codable, Sendable {
        case terentoSnapshot = "terento_snapshot"
        case terentoInventory = "terento_inventory"
        case terentoFilePrefix = "terento_file_prefix"
        case terentoFileRange = "terento_file_range"
        case terentoMapWrite = "terento_map_write"
        case terentoMapVerify = "terento_map_verify"
    }
    enum ComponentKind: String, Codable, Sendable {
        case main = "main"
        case contours = "contours"
    }
    /// The step of a failed native map send (`terento_map_write` -7), from
    /// the exact libmtp error-stack texts. Never device text.
    enum WriteFailureStep: String, Codable, Sendable, CaseIterable {
        case unknown = "unknown"
        case sourceOpen = "source_open"
        case objectInfo = "object_info"
        case objectData = "object_data"
        case cancelled = "cancelled"
        case objectMetadata = "object_metadata"
    }

    let boundary: Boundary
    let classificationSource: ClassificationSource
    let devicePresence: DevicePresence
    let lastSuccessfulBoundary: Boundary?
    let operation: Operation?
    let executionMode: ExecutionMode?
    let resultKind: ResultKind?
    let nativeCategory: NativeCategory?
    let nativeCodeNamespace: NativeCodeNamespace?
    let nativeResultCode: Int32?
    let retryCount: UInt8?
    let componentKind: ComponentKind?
    let protection: InstallationProtectionContext?
    let writeFailureStep: WriteFailureStep?
    /// The PTP response the watch returned, or the Mac's PTP-layer error, for
    /// an `object_info` or `object_data` step (1...0xFFFF).
    let ptpResponseCode: UInt16?

    init(
        boundary: Boundary,
        classificationSource: ClassificationSource,
        devicePresence: DevicePresence,
        lastSuccessfulBoundary: Boundary? = nil,
        operation: Operation? = nil,
        executionMode: ExecutionMode? = nil,
        resultKind: ResultKind? = nil,
        nativeCategory: NativeCategory? = nil,
        nativeCodeNamespace: NativeCodeNamespace? = nil,
        nativeResultCode: Int32? = nil,
        retryCount: UInt8? = nil,
        componentKind: ComponentKind? = nil,
        protection: InstallationProtectionContext? = nil,
        writeFailureStep: WriteFailureStep? = nil,
        ptpResponseCode: UInt16? = nil
    ) {
        self.boundary = boundary
        self.classificationSource = classificationSource
        self.devicePresence = devicePresence
        self.lastSuccessfulBoundary = lastSuccessfulBoundary
        self.operation = operation
        self.executionMode = executionMode
        self.resultKind = resultKind
        self.nativeCategory = nativeCategory
        self.nativeCodeNamespace = nativeCodeNamespace
        self.nativeResultCode = nativeResultCode
        self.retryCount = retryCount
        self.componentKind = componentKind
        self.protection = protection
        self.writeFailureStep = writeFailureStep
        self.ptpResponseCode = ptpResponseCode
    }
}

extension InstallationFailureContext.Boundary {
    var stageRawValue: String {
        switch self {
        case .initialSnapshot, .initialInventory, .prewriteInventory, .prewriteProtection, .preflightPolicyPassed: return "preflight"
        case .write: return "write"
        case .readback, .postwriteInventory, .postwriteSnapshot, .targetValidation, .postwriteProtection: return "verify"
        case .cleanup: return "cleanup"
        case .manifest: return "manifest"
        case .sourceValidationComplete: return "source-validation"
        }
    }
}

extension InstallationFailureContext {
    /// Preserve native facts while attaching the boundary/component observed by the caller.
    func at(
        _ boundary: Boundary,
        lastSuccessfulBoundary: Boundary? = nil,
        componentKind: ComponentKind? = nil,
        classificationSource: ClassificationSource? = nil
    ) -> Self {
        Self(boundary: boundary, classificationSource: classificationSource ?? self.classificationSource, devicePresence: devicePresence,
             lastSuccessfulBoundary: lastSuccessfulBoundary ?? self.lastSuccessfulBoundary,
             operation: operation, executionMode: executionMode, resultKind: resultKind,
             nativeCategory: nativeCategory, nativeCodeNamespace: nativeCodeNamespace,
             nativeResultCode: nativeResultCode, retryCount: retryCount,
             componentKind: componentKind ?? self.componentKind, protection: protection,
             writeFailureStep: writeFailureStep, ptpResponseCode: ptpResponseCode)
    }

    /// The same facts with the number of retries made before this failure.
    func retried(_ count: UInt8) -> Self {
        Self(boundary: boundary, classificationSource: classificationSource, devicePresence: devicePresence,
             lastSuccessfulBoundary: lastSuccessfulBoundary, operation: operation, executionMode: executionMode,
             resultKind: resultKind, nativeCategory: nativeCategory, nativeCodeNamespace: nativeCodeNamespace,
             nativeResultCode: nativeResultCode, retryCount: count, componentKind: componentKind,
             protection: protection, writeFailureStep: writeFailureStep, ptpResponseCode: ptpResponseCode)
    }

    /// `terento_mtp_verify_managed_map_samples` -9: the fresh read-back
    /// session opened and resolved the exact written map, but one planned
    /// sample could not be read. Nothing was compared, so this is neither a
    /// match nor a mismatch (-11).
    var isSampledReadBackReadFailure: Bool {
        boundary == .readback && nativeCodeNamespace == .terentoMapVerify && nativeResultCode == -9
    }

    /// `terento_mtp_read_snapshot_diagnostic` -5: exactly one Garmin is on
    /// USB, but its file-transfer session could not be opened (usually another
    /// app holds the watch). Detection reports the same code as busy.
    var isWatchSessionBusy: Bool {
        nativeCodeNamespace == .terentoSnapshot && nativeResultCode == -5
    }

    /// `terento_mtp_read_snapshot_diagnostic` -2 or -3: no Garmin with file
    /// transfer is visible on USB any more (unplugged, USB dropped, or the
    /// watch left file transfer), for example after a long download.
    var isWatchNoLongerVisible: Bool {
        nativeCodeNamespace == .terentoSnapshot && (nativeResultCode == -2 || nativeResultCode == -3)
    }
}
/// The one automatic second attempt of the post-write sampled read-back.
///
/// A sample read that fails (`terento_map_verify` -9) after a complete write
/// is, in the field, a short-lived USB or device stall: the same device reads
/// the same map again later. The parent therefore waits and repeats the SAME
/// sampled read-back once, in a new worker process and so a new USB session.
/// The method, the planned regions and the validated local artifact do not
/// change; a mismatch, a changed identity or a second failure blocks exactly
/// as before. The repeat only reads: it sends no write and no delete. Opening
/// its session is the ordinary native open, which may reset the USB link on
/// some models exactly as every other session open does.
///
/// The earlier single repeat after a completed metadata lookup that did not
/// find the exact object shares the same count: a read-back makes at most ONE
/// repeat in total, so at most two USB sessions per written map.
enum SampledReadBackRetryPolicy {
    /// Wait before the second attempt, so the device can settle.
    static let delay: TimeInterval = 5
    /// Upper bound for the wait plus the second attempt.
    static let totalBudget: TimeInterval = 120
    /// At most this many repeats per written map, whatever their reason.
    static let maximumRetries = 1
    /// Wait before repeating a metadata lookup that did not find the object.
    static let metadataLookupDelay: TimeInterval = 1
    /// Upper bound of the whole read-back, as before the repeat existed.
    static let verificationBudget: TimeInterval = 600

    enum Repeat: Equatable, Sendable {
        /// A completed metadata lookup did not find the exact written object.
        case metadataLookup
        /// A sample could not be read; `timeout` bounds the attempt after the wait.
        case sampleRead(timeout: TimeInterval)

        var delay: TimeInterval {
            switch self {
            case .metadataLookup: return SampledReadBackRetryPolicy.metadataLookupDelay
            case .sampleRead: return SampledReadBackRetryPolicy.delay
            }
        }

        var traceReason: String {
            switch self {
            case .metadataLookup: return "metadata_lookup"
            case .sampleRead: return "sample_read_failed"
            }
        }
    }

    /// A completed lookup that did not find the exact object, or found another.
    static func isMetadataLookupMiss(_ error: Error) -> Bool {
        guard let error = error as? InstallationTransportError else { return false }
        switch error {
        case .remoteFileMissing, .objectIdentityMismatch:
            return true
        case .contextual, .deviceDisconnected, .operationFailed, .targetAlreadyExists,
             .unsupportedDevice, .liveIdentityMismatch:
            return false
        }
    }

    /// The exact "sample could not be read" result of the read-back.
    static func isSampleReadFailure(_ error: Error) -> Bool {
        guard case let InstallationTransportError.contextual(_, _, _, context) = error else {
            return false
        }
        return context.isSampledReadBackReadFailure
    }

    /// The repeat to make after `error`, or nil when the failure is final.
    /// Only the parent process repeats, and only once in total. A worker
    /// never repeats, and a mismatch (-11), an unopened session (-8), a
    /// disconnect or any other failure is never repeated.
    static func nextRepeat(
        after error: Error,
        isWorker: Bool,
        repeatsMade: Int,
        remainingVerificationTime: TimeInterval
    ) -> Repeat? {
        guard !isWorker, repeatsMade < maximumRetries else { return nil }
        if isMetadataLookupMiss(error) { return .metadataLookup }
        if isSampleReadFailure(error),
           let timeout = retryTimeout(remainingVerificationTime: remainingVerificationTime) {
            return .sampleRead(timeout: timeout)
        }
        return nil
    }

    /// Seconds the second attempt may take after the wait, or nil when the
    /// overall verification budget cannot hold the wait and a useful attempt.
    static func retryTimeout(remainingVerificationTime: TimeInterval) -> TimeInterval? {
        let available = min(totalBudget, remainingVerificationTime) - delay
        return available >= 1 ? available : nil
    }

    /// The failure of a second attempt, marked with the retry that was made.
    /// Other error cases carry no failure context and are returned unchanged.
    static func failureAfterRetry(_ error: Error, retriesMade: Int) -> Error {
        guard retriesMade > 0,
              case let InstallationTransportError.contextual(failure, message, createdItemID, context) = error else {
            return error
        }
        return InstallationTransportError.contextual(
            failure: failure, message: message, createdItemID: createdItemID,
            context: context.retried(UInt8(clamping: retriesMade))
        )
    }

    /// The whole read-back loop: the first attempt and at most one repeat.
    /// `attempt` performs one complete read-back in its own USB session and
    /// receives the seconds it may take. The clock, the wait and the trace are
    /// supplied by the caller, so the loop itself performs no device I/O.
    static func run<Value>(
        isWorker: Bool,
        now: () -> TimeInterval,
        sleep: (TimeInterval) -> Void,
        trace: (_ event: String, _ details: String) -> Void,
        attempt: (_ remainingTime: TimeInterval) throws -> Value
    ) throws -> Value {
        var deadline = now() + verificationBudget
        var repeatsMade = 0
        var madeRepeat: Repeat?
        var attemptNumber = 0
        var delay: TimeInterval = 0
        while true {
            attemptNumber += 1
            trace("readback_attempt", "worker=\(isWorker) attempt=\(attemptNumber) delay=\(delay)")
            if delay > 0 { sleep(delay) }

            let remaining = deadline - now()
            guard remaining > 0 else {
                throw InstallationTransportError.operationFailed(
                    "Map verification exceeded its total time budget.", createdItemID: nil)
            }
            do {
                let result = try attempt(remaining)
                if let madeRepeat {
                    // Local record that the repeat was what completed the check.
                    trace("readback_repeat_succeeded", "reason=\(madeRepeat.traceReason) attempt=\(attemptNumber)")
                }
                return result
            } catch {
                trace("readback_failed", "worker=\(isWorker) attempt=\(attemptNumber) error=\(traceName(of: error))")
                let failedAt = now()
                guard let next = nextRepeat(
                    after: error, isWorker: isWorker, repeatsMade: repeatsMade,
                    remainingVerificationTime: deadline - failedAt
                ) else {
                    throw failureAfterRetry(error, retriesMade: repeatsMade)
                }
                repeatsMade += 1
                madeRepeat = next
                delay = next.delay
                if case .sampleRead(let timeout) = next {
                    // From here the wait and the repeat share one bound.
                    deadline = failedAt + delay + timeout
                }
                trace("readback_retry", "reason=\(next.traceReason) delay=\(delay)")
            }
        }
    }

    static func traceName(of error: Error) -> String {
        guard let error = error as? InstallationTransportError else { return "other" }
        switch error {
        case .contextual:
            return error.isConfirmedDeviceDisconnected ? "deviceDisconnected" : "operationFailed"
        case .deviceDisconnected: return "deviceDisconnected"
        case .operationFailed: return "operationFailed"
        case .remoteFileMissing: return "remoteFileMissing"
        case .objectIdentityMismatch: return "objectIdentityMismatch"
        case .targetAlreadyExists: return "targetAlreadyExists"
        case .unsupportedDevice: return "unsupportedDevice"
        case .liveIdentityMismatch: return "liveIdentityMismatch"
        }
    }
}

/// Forwards transfer progress that only ever increases, so a repeated check
/// never moves a progress bar backwards.
final class MonotonicTransferProgress: @unchecked Sendable {
    private let lock = NSLock()
    private var highest: UInt64 = 0
    private var reportedAny = false
    private let forward: @Sendable (TransferProgress) -> Void

    init(_ forward: @escaping @Sendable (TransferProgress) -> Void) {
        self.forward = forward
    }

    func report(_ progress: TransferProgress) {
        lock.lock()
        let advances = !reportedAny || progress.bytesTransferred > highest
        if advances {
            highest = progress.bytesTransferred
            reportedAny = true
        }
        lock.unlock()
        if advances { forward(progress) }
    }
}

struct InstallationProtectionContext: Codable, Equatable, Sendable {
    enum Boundary: String, Codable, Sendable {
        case preWrite = "pre-write"
        case postWrite = "post-write"
    }
    enum Reason: String, Codable, Sendable {
        case targetPresentBeforeWrite = "target-present-before-write"
        case nonTargetObjectAdded = "non-target-object-added"
        case preexistingObjectRemoved = "preexisting-object-removed"
        case preexistingObjectChanged = "preexisting-object-changed"
        case inventoryAmbiguous = "inventory-ambiguous"
        case targetMissing = "target-missing"
        case targetDuplicate = "target-duplicate"
        case targetInvalid = "target-invalid"
        case targetFilenameMismatch = "target-filename-mismatch"
        case targetSizeMismatch = "target-size-mismatch"
    }
    /// Where the first protected non-target object that decided an
    /// added/removed/changed reason lives: a standard `/GARMIN` folder name,
    /// a map file, or a coarse bucket. Never a path or filename. The
    /// classifier lives in MapInstallationCoordinator.swift.
    enum AffectedFolder: String, Codable, Sendable, CaseIterable {
        case activity = "Activity", apps = "Apps", courses = "Courses", debug = "Debug"
        case device = "Device", errLogs = "ErrLogs", goals = "Goals", locations = "Locations"
        case map = "Map", metrics = "Metrics", monitor = "Monitor", newFiles = "NewFiles"
        case records = "Records", remoteSW = "RemoteSW", schedules = "Schedules"
        case settings = "Settings", sleep = "Sleep", sports = "Sports", text = "Text"
        case tlg = "TLG", totals = "Totals", workouts = "Workouts"
        case mapFile = "map-file"
        case garminRoot = "garmin-root"
        case garminOther = "garmin-other"
        case outsideGarmin = "outside-garmin"
    }

    let protectionBoundary: Boundary
    let protectionReason: Reason
    let stableIdentityComparisonVersion: Int?
    let beforeObjectCount: Int?
    let afterObjectCount: Int?
    let addedObjectCount: Int?
    let removedObjectCount: Int?
    let changedObjectCount: Int?
    let affectedFolder: AffectedFolder?
    let targetPresent: Bool?
    let targetUnique: Bool?
    let targetKindMatches: Bool?
    let targetFilenameMatches: Bool?
    let targetSizeMatches: Bool?
    let targetPathMatches: Bool?
    let targetItemIDMatches: Bool?

    init(
        protectionBoundary: Boundary,
        protectionReason: Reason,
        stableIdentityComparisonVersion: Int? = nil,
        beforeObjectCount: Int? = nil,
        afterObjectCount: Int? = nil,
        addedObjectCount: Int? = nil,
        removedObjectCount: Int? = nil,
        changedObjectCount: Int? = nil,
        affectedFolder: AffectedFolder? = nil,
        targetPresent: Bool? = nil,
        targetUnique: Bool? = nil,
        targetKindMatches: Bool? = nil,
        targetFilenameMatches: Bool? = nil,
        targetSizeMatches: Bool? = nil,
        targetPathMatches: Bool? = nil,
        targetItemIDMatches: Bool? = nil
    ) {
        self.protectionBoundary = protectionBoundary
        self.protectionReason = protectionReason
        self.stableIdentityComparisonVersion = stableIdentityComparisonVersion
        self.beforeObjectCount = beforeObjectCount
        self.afterObjectCount = afterObjectCount
        self.addedObjectCount = addedObjectCount
        self.removedObjectCount = removedObjectCount
        self.changedObjectCount = changedObjectCount
        self.affectedFolder = affectedFolder
        self.targetPresent = targetPresent
        self.targetUnique = targetUnique
        self.targetKindMatches = targetKindMatches
        self.targetFilenameMatches = targetFilenameMatches
        self.targetSizeMatches = targetSizeMatches
        self.targetPathMatches = targetPathMatches
        self.targetItemIDMatches = targetItemIDMatches
    }
}


enum InstallationNativeFailureCode: String, Equatable, Sendable {
    case targetAlreadyExists = "TARGET_ALREADY_EXISTS"
    case remoteFileMissing = "REMOTE_FILE_MISSING"
    case objectIDMismatch = "OBJECT_ID_MISMATCH"
    case unsupportedDevice = "UNSUPPORTED_DEVICE"
    case liveIdentityMismatch = "LIVE_IDENTITY_MISMATCH"
    case deviceDisconnected = "DEVICE_DISCONNECTED"
    case preflightMTPReadFailed = "PREFLIGHT_MTP_READ_FAILED"
    case sendObjectFailed = "SEND_OBJECT_FAILED"
    case readbackFailed = "READBACK_FAILED"
    case deleteFailed = "DELETE_FAILED"
}

struct MTPWrittenMapObject: Equatable, Sendable {
    let itemID: UInt32
    let sizeBytes: UInt64
}

struct MTPReadBackMapObject: Codable, Equatable, Sendable {
    let itemID: UInt32
    let targetPath: String
    let reportedSizeBytes: UInt64
    let sampledBytes: UInt64
    let sampleCount: Int
    let matchedSampleCount: Int
}

protocol InstallationFailureContextProviding: Error {
    var failureContext: InstallationFailureContext? { get }
}

enum InstallationTransportFailureKind: String, Codable, Sendable {
    case operationFailed
    case deviceDisconnected
}

enum InstallationTransportError: Codable, LocalizedError, Equatable, Sendable, InstallationFailureContextProviding {
    case targetAlreadyExists
    case remoteFileMissing
    case objectIdentityMismatch
    case unsupportedDevice
    case liveIdentityMismatch
    case deviceDisconnected(String, createdItemID: UInt32?)
    case operationFailed(String, createdItemID: UInt32?)
    case contextual(failure: InstallationTransportFailureKind, message: String,
                    createdItemID: UInt32?, context: InstallationFailureContext)

    var failureContext: InstallationFailureContext? {
        if case .contextual(_, _, _, let context) = self { return context }
        return nil
    }

    var createdItemID: UInt32? {
        switch self {
        case .deviceDisconnected(_, let id), .operationFailed(_, let id),
             .contextual(_, _, let id, _): return id
        default: return nil
        }
    }

    var isConfirmedDeviceDisconnected: Bool {
        switch self {
        case .deviceDisconnected: return true
        case .contextual(let failure, _, _, let context):
            return failure == .deviceDisconnected && context.devicePresence == .absent
        default: return false
        }
    }

    var errorDescription: String? {
        switch self {
        case .targetAlreadyExists:
            return "The selected map target already exists on the Garmin device."
        case .remoteFileMissing:
            return "The transferred map was not found on the Garmin device."
        case .objectIdentityMismatch:
            return "The Garmin object identity did not match the intended map."
        case .unsupportedDevice:
            return "This Garmin device is not enabled for the validated map installation path."
        case .liveIdentityMismatch:
            return "The connected Garmin device changed after this map operation was authorized."
        case .deviceDisconnected(let message, _),
             .operationFailed(let message, _):
            return message
        case .contextual(_, let message, _, _):
            return message
        }
    }
}

protocol MapInstallationTransport: Sendable {
    func validateWriteTarget(identity: DeviceIdentity, files: [DeviceFile]) throws
    func write(
        sourceURL: URL,
        targetFilename: String,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPWrittenMapObject

    func readBack(
        sourceURL: URL,
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String,
        expectedSizeBytes: UInt64,
        sampleOffsets: [UInt64],
        sampleLength: UInt32,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPReadBackMapObject

    func deleteExact(
        targetFilename: String,
        expectedItemID: UInt32,
        expectedSizeBytes: UInt64?
    ) throws
}

extension MapInstallationTransport {
    // Injected transports may have no native binding. Production overrides this.
    func validateWriteTarget(identity: DeviceIdentity, files: [DeviceFile]) throws {}
}

protocol InstallationInventoryReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    /// Pre/post-write protection read. It may cover only the map scope
    /// (storage roots plus the GARMIN subtree) and reports what it covers.
    func readMapScopeInventory() throws -> DeviceInventoryRead
}

extension InstallationInventoryReader {
    /// Injected readers without a scoped walk answer with the full inventory.
    func readMapScopeInventory() throws -> DeviceInventoryRead {
        .full(try readFileInventory())
    }
}

protocol InstallationDeviceReader: InstallationInventoryReader {
    func readSnapshot() throws -> DeviceSnapshot
}

/// A cleanup request was refused before any device mutation.
struct CleanupIdentityUnproven: LocalizedError {
    var errorDescription: String? { "Automatic cleanup could not prove the created map identity. Recovery is required." }
}

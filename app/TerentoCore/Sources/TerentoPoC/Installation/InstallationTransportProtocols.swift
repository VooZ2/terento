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
    }
    enum ComponentKind: String, Codable, Sendable {
        case main = "main"
        case contours = "contours"
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
        protection: InstallationProtectionContext? = nil
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
             componentKind: componentKind ?? self.componentKind, protection: protection)
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

    let protectionBoundary: Boundary
    let protectionReason: Reason
    let stableIdentityComparisonVersion: Int?
    let beforeObjectCount: Int?
    let afterObjectCount: Int?
    let addedObjectCount: Int?
    let removedObjectCount: Int?
    let changedObjectCount: Int?
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

    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws
    func deleteExact(
        targetFilename: String,
        expectedItemID: UInt32,
        expectedSizeBytes: UInt64?
    ) throws
}

extension MapInstallationTransport {
    func deleteExact(
        targetFilename: String,
        expectedItemID: UInt32,
        expectedSizeBytes: UInt64?
    ) throws {
        try deleteExact(targetFilename: targetFilename, expectedItemID: expectedItemID)
    }
}

protocol InstallationInventoryReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
}

protocol InstallationDeviceReader: InstallationInventoryReader {
    func readSnapshot() throws -> DeviceSnapshot
}

/// A cleanup request was refused before any device mutation.
struct CleanupIdentityUnproven: LocalizedError {
    var errorDescription: String? { "Automatic cleanup could not prove the created map identity. Recovery is required." }
}

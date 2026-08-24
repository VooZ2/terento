import Foundation

enum InstallationFailure: String, Codable, Error, Equatable, Sendable {
    case existingMapConflict = "INSTALL_BLOCKED_EXISTING_MAP_CONFLICT"
    case sourceArtifactInvalid = "INSTALL_BLOCKED_SOURCE_ARTIFACT_INVALID"
    case insufficientSpace = "INSTALL_BLOCKED_INSUFFICIENT_SPACE"
    case unknownInstallSize = "INSTALL_BLOCKED_UNKNOWN_INSTALL_SIZE"
    case unknownInstallTarget = "INSTALL_BLOCKED_UNKNOWN_TARGET"
    case mapIdentityAmbiguous = "INSTALL_BLOCKED_MAP_IDENTITY_AMBIGUOUS"
    case backupFailed = "INSTALL_BLOCKED_BACKUP_FAILED"
    case downloadFailed = "INSTALL_BLOCKED_DOWNLOAD_FAILED"
    case sourceValidationFailed = "INSTALL_BLOCKED_SOURCE_VALIDATION_FAILED"
    case deviceDisconnected = "INSTALL_FAILED_DEVICE_DISCONNECTED"
    case writeFailed = "INSTALL_FAILED_WRITE"
    case sizeMismatch = "INSTALL_FAILED_SIZE_MISMATCH"
    case hashMismatch = "INSTALL_FAILED_HASH_MISMATCH"
    case remoteFileMissing = "INSTALL_FAILED_REMOTE_FILE_MISSING"
    case metadataMismatch = "INSTALL_FAILED_METADATA_MISMATCH"
    case manifestFailed = "INSTALL_FAILED_MANIFEST"
    case protectionViolation = "INSTALL_FAILED_PROTECTION_VIOLATION"
    case cleanupFailed = "INSTALL_FAILED_CLEANUP"
    case transactionAlreadyRunning = "INSTALL_BLOCKED_TRANSACTION_ALREADY_RUNNING"
    case invalidStateTransition = "INSTALL_FAILED_INVALID_STATE_TRANSITION"
    case verificationRequired = "INSTALL_BLOCKED_VERIFICATION_REQUIRED"

    var userLabel: String {
        switch self {
        case .existingMapConflict:
            return "This map is already on the Garmin device. No replacement was attempted."
        case .sourceArtifactInvalid:
            return "The prepared map did not match the validated source artifact."
        case .insufficientSpace:
            return "There is not enough free space for a safe installation."
        case .unknownInstallSize:
            return "The final Garmin install size must be calculated before installation."
        case .unknownInstallTarget:
            return "This device does not have a validated map installation target."
        case .mapIdentityAmbiguous:
            return "An existing map could not be identified safely."
        case .backupFailed:
            return "The backup could not be verified, so installation was stopped."
        case .downloadFailed:
            return "The map could not be downloaded from the provider."
        case .sourceValidationFailed:
            return "The prepared map failed validation and was not transferred."
        case .deviceDisconnected:
            return "The Garmin device was disconnected during installation."
        case .writeFailed:
            return "The map could not be transferred to the Garmin device."
        case .sizeMismatch:
            return "The transferred map size did not match the source file."
        case .hashMismatch:
            return "The transferred map contents did not match the source file."
        case .remoteFileMissing:
            return "The transferred map could not be found on the Garmin device."
        case .metadataMismatch:
            return "The transferred map identity did not match the selected Freizeitkarte map."
        case .manifestFailed:
            return "The map was transferred, but local ownership could not be recorded safely."
        case .protectionViolation:
            return "Another device file changed unexpectedly, so installation was not accepted."
        case .cleanupFailed:
            return "Installation failed and a partial map may still remain on the Garmin device. Terento did not retry or remove it automatically. Reconnect the watch and refresh its maps before any further action."
        case .transactionAlreadyRunning:
            return "Another installation is already in progress."
        case .invalidStateTransition:
            return "The installation stopped because its safety sequence was invalid."
        case .verificationRequired:
            return "The installation cannot complete until the transferred file is verified."
        }
    }
}

enum InstallMapOwnership: String, Codable, Equatable, Sendable {
    case terentoManaged = "TERENTO_MANAGED"
    case externalRecognized = "EXTERNAL_RECOGNIZED"
    case unknown = "UNKNOWN"
}

struct TerentoManifestEntry: Codable, Equatable, Sendable {
    let deviceKey: String
    let devicePath: String
    let filename: String
    let providerId: String
    let regionId: String
    let version: MapVersion
    let sizeBytes: UInt64
    let sha256: String
    let installedAt: Date
}

struct TerentoManifest: Codable, Equatable, Sendable {
    let entries: [TerentoManifestEntry]
}

/// A durable marker for a device object created by an installation that did
/// not reach manifest recording. It is not normal ownership; it exists only
/// so a failed write can be recovered after the app or device reconnects.
struct TerentoFailedInstallRecoveryRecord: Codable, Equatable, Sendable {
    let deviceKey: String
    let packageID: String
    let providerId: String
    let regionId: String
    let version: MapVersion
    let devicePath: String
    let filename: String
    let sizeBytes: UInt64
    let sha256: String
    let createdAt: Date

    func matches(
        deviceKey: String,
        path: String,
        filename: String,
        sizeBytes: UInt64,
        providerId: String?,
        regionId: String?,
        version: MapVersion?
    ) -> Bool {
        self.deviceKey == deviceKey
            && devicePath == path
            && self.filename == filename
            && self.sizeBytes == sizeBytes
            && MapIdentity.normalizeProvider(self.providerId)
                == MapIdentity.normalizeProvider(providerId ?? "")
            && MapIdentity.normalizeRegion(self.regionId)
                == MapIdentity.normalizeRegion(regionId ?? "")
            && self.version == version
    }
}

struct TerentoFailedInstallRecoveryFile: Codable, Equatable, Sendable {
    let records: [TerentoFailedInstallRecoveryRecord]
}

enum InstallationProcessPhase: String, Equatable, Sendable {
    case idle
    case downloading
    case preparing
    case awaitingConfirmation
    case installing
    case finishing
    case completed
    case failed
}

struct TransferProgress: Equatable, Sendable {
    let bytesTransferred: UInt64
    let totalBytes: UInt64
    let bytesPerSecond: Double

    init(
        bytesTransferred: UInt64,
        totalBytes: UInt64,
        bytesPerSecond: Double = 0
    ) {
        self.bytesTransferred = bytesTransferred
        self.totalBytes = totalBytes
        self.bytesPerSecond = bytesPerSecond
    }

    var fractionCompleted: Double {
        guard totalBytes > 0 else {
            return 0
        }

        return min(1, Double(bytesTransferred) / Double(totalBytes))
    }
}

enum InstallationTransactionState: String, Codable, Equatable, Sendable {
    case idle = "IDLE"
    case validating = "VALIDATING"
    case awaitingExistingMapDecision = "AWAITING_EXISTING_MAP_DECISION"
    case awaitingBackupDecision = "AWAITING_BACKUP_DECISION"
    case backingUp = "BACKING_UP"
    case downloading = "DOWNLOADING"
    case preparing = "PREPARING"
    case readyToWrite = "READY_TO_WRITE"
    case writing = "WRITING"
    case verifying = "VERIFYING"
    case completed = "COMPLETED"
    case failed = "FAILED"
}

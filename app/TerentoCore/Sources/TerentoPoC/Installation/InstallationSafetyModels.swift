import Foundation

enum InstallationFailure: String, Codable, Error, Equatable, Sendable {
    case existingMapConflict = "INSTALL_BLOCKED_EXISTING_MAP_CONFLICT"
    case sourceArtifactInvalid = "INSTALL_BLOCKED_SOURCE_ARTIFACT_INVALID"
    case insufficientSpace = "INSTALL_BLOCKED_INSUFFICIENT_SPACE"
    case unknownInstallSize = "INSTALL_BLOCKED_UNKNOWN_INSTALL_SIZE"
    case unknownInstallTarget = "INSTALL_BLOCKED_UNKNOWN_TARGET"
    case stableWatchIdentityUnavailable = "INSTALL_BLOCKED_STABLE_WATCH_IDENTITY_UNAVAILABLE"
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
        case .stableWatchIdentityUnavailable:
            return "Terento could not establish the stable local watch identity required to manage this installation safely."
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
            return "The transferred map identity did not match the selected map."
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
    /// Optional for backwards compatibility with manifests written before
    /// package components were introduced. New writes always populate these
    /// fields so lifecycle ownership is component-exact.
    let packageID: String?
    let artifactID: String?
    let artifactKind: MapArtifactKind?

    init(
        deviceKey: String,
        devicePath: String,
        filename: String,
        providerId: String,
        regionId: String,
        version: MapVersion,
        sizeBytes: UInt64,
        sha256: String,
        installedAt: Date,
        packageID: String? = nil,
        artifactID: String? = nil,
        artifactKind: MapArtifactKind? = nil
    ) {
        self.deviceKey = deviceKey
        self.devicePath = devicePath
        self.filename = filename
        self.providerId = providerId
        self.regionId = regionId
        self.version = version
        self.sizeBytes = sizeBytes
        self.sha256 = sha256
        self.installedAt = installedAt
        self.packageID = packageID
        self.artifactID = artifactID
        self.artifactKind = artifactKind
    }

    private enum CodingKeys: String, CodingKey {
        case deviceKey, devicePath, filename, providerId, regionId, version
        case sizeBytes, sha256, installedAt, packageID, artifactID, artifactKind
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            deviceKey: try container.decode(String.self, forKey: .deviceKey),
            devicePath: try container.decode(String.self, forKey: .devicePath),
            filename: try container.decode(String.self, forKey: .filename),
            providerId: try container.decode(String.self, forKey: .providerId),
            regionId: try container.decode(String.self, forKey: .regionId),
            version: try container.decode(MapVersion.self, forKey: .version),
            sizeBytes: try container.decode(UInt64.self, forKey: .sizeBytes),
            sha256: try container.decode(String.self, forKey: .sha256),
            installedAt: try container.decode(Date.self, forKey: .installedAt),
            packageID: try container.decodeIfPresent(String.self, forKey: .packageID),
            artifactID: try container.decodeIfPresent(String.self, forKey: .artifactID),
            artifactKind: try container.decodeIfPresent(MapArtifactKind.self, forKey: .artifactKind)
        )
    }
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
    /// Component identity is optional for recovery files written by older
    /// beta builds. New writes keep it so a main map and its contour companion
    /// can be recovered and removed independently.
    let artifactID: String?
    let artifactKind: MapArtifactKind?

    init(
        deviceKey: String,
        packageID: String,
        providerId: String,
        regionId: String,
        version: MapVersion,
        devicePath: String,
        filename: String,
        sizeBytes: UInt64,
        sha256: String,
        createdAt: Date,
        artifactID: String? = nil,
        artifactKind: MapArtifactKind? = nil
    ) {
        self.deviceKey = deviceKey
        self.packageID = packageID
        self.providerId = providerId
        self.regionId = regionId
        self.version = version
        self.devicePath = devicePath
        self.filename = filename
        self.sizeBytes = sizeBytes
        self.sha256 = sha256
        self.createdAt = createdAt
        self.artifactID = artifactID
        self.artifactKind = artifactKind
    }

    private enum CodingKeys: String, CodingKey {
        case deviceKey, packageID, providerId, regionId, version
        case devicePath, filename, sizeBytes, sha256, createdAt
        case artifactID, artifactKind
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            deviceKey: try container.decode(String.self, forKey: .deviceKey),
            packageID: try container.decode(String.self, forKey: .packageID),
            providerId: try container.decode(String.self, forKey: .providerId),
            regionId: try container.decode(String.self, forKey: .regionId),
            version: try container.decode(MapVersion.self, forKey: .version),
            devicePath: try container.decode(String.self, forKey: .devicePath),
            filename: try container.decode(String.self, forKey: .filename),
            sizeBytes: try container.decode(UInt64.self, forKey: .sizeBytes),
            sha256: try container.decode(String.self, forKey: .sha256),
            createdAt: try container.decode(Date.self, forKey: .createdAt),
            artifactID: try container.decodeIfPresent(String.self, forKey: .artifactID),
            artifactKind: try container.decodeIfPresent(MapArtifactKind.self, forKey: .artifactKind)
        )
    }

    func matches(
        deviceKey: String,
        path: String,
        filename: String,
        sizeBytes: UInt64,
        providerId: String?,
        regionId: String?,
        version: MapVersion?
    ) -> Bool {
        // Custom imports intentionally have no provider identity in the scan.
        // Only the exact recorded target may supply that missing identity.
        // Header dates are not custom import versions (the import uses a sentinel).
        if providerId == nil, regionId == nil,
           MapIdentity.normalizeProvider(self.providerId) == "custom" {
            return self.deviceKey == deviceKey
                && devicePath == path
                && self.filename == filename
                && self.sizeBytes == sizeBytes
                && sizeBytes > 0
                && sha256.count == 64 && sha256.allSatisfy(\.isHexDigit)
                && devicePath == "/GARMIN/\(filename)"
                && TerentoManagedFilenameGenerator().matchesIdentity(
                    filename, providerId: self.providerId, regionId: self.regionId
                )
        }

        guard let actualIdentity = MapIdentity(provider: providerId, region: regionId),
              let expectedIdentity = MapIdentity(
                  provider: self.providerId,
                  region: self.regionId
              ) else {
            return false
        }

        return self.deviceKey == deviceKey
            && devicePath == path
            && self.filename == filename
            && self.sizeBytes == sizeBytes
            && MapIdentityMatcher.matches(
                actual: actualIdentity,
                expected: expectedIdentity,
                providerRegionId: self.regionId
            )
            // Contour IMG headers commonly omit the provider release. The
            // recovery record remains authoritative because path, filename,
            // size, provider and region are still matched exactly.
            && (version == nil || self.version == version)
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

    func normalized(sourceSize: UInt64) -> TransferProgress {
        TransferProgress(bytesTransferred: min(bytesTransferred, sourceSize),
                         totalBytes: sourceSize, bytesPerSecond: bytesPerSecond)
    }

    var fractionCompleted: Double {
        guard totalBytes > 0 else {
            return 0
        }

        return min(1, Double(bytesTransferred) / Double(totalBytes))
    }
}

/// The package-level outcome keeps the main map and an optional companion
/// separate. A successful main-map transfer must not be reported as a fully
/// completed package when the optional contour transfer failed.
enum MapPackageInstallationStatus: String, Equatable, Sendable {
    case completed = "COMPLETED"
    case completedWithWarnings = "COMPLETED_WITH_WARNINGS"
    case failed = "FAILED"
}

struct MapInstallationComponentOutcome: Equatable, Sendable {
    let artifactID: String
    let artifactKind: MapArtifactKind
    let succeeded: Bool
    let failure: InstallationFailure?

    var isSuccess: Bool {
        succeeded
    }
}

struct MapPackageInstallationOutcome: Equatable, Sendable {
    let packageID: String
    let status: MapPackageInstallationStatus
    let components: [MapInstallationComponentOutcome]

    var isComplete: Bool {
        status == .completed
    }

    var hasWarnings: Bool {
        status == .completedWithWarnings
    }

    var failedComponent: MapInstallationComponentOutcome? {
        components.first { !$0.isSuccess }
    }
}

/// Converts cumulative transfer callbacks into a stable, human-readable rate.
///
/// Callbacks can arrive in very small bursts, so dividing one callback delta
/// by its wall-clock interval produces implausible spikes. This estimator uses
/// monotonic time, waits for a meaningful sample interval, and smooths accepted
/// samples while preserving a cumulative-byte baseline.
enum TransferRateCalculator {
    static let minimumSampleInterval: TimeInterval = 0.25

    static func sample(
        deltaBytes: UInt64,
        elapsedSeconds: TimeInterval,
        previousRate: Double = 0
    ) -> Double? {
        guard deltaBytes > 0,
              elapsedSeconds.isFinite,
              elapsedSeconds >= minimumSampleInterval else {
            return nil
        }

        let instantaneousRate = Double(deltaBytes) / elapsedSeconds
        guard instantaneousRate.isFinite, instantaneousRate >= 0 else {
            return nil
        }

        let smoothedRate = previousRate > 0
            ? (previousRate * 0.75) + (instantaneousRate * 0.25)
            : instantaneousRate
        return smoothedRate.isFinite ? smoothedRate : nil
    }

    static func seconds(_ duration: Duration) -> TimeInterval {
        let components = duration.components
        return Double(components.seconds)
            + (Double(components.attoseconds) / 1_000_000_000_000_000_000)
    }
}

struct TransferSpeedEstimator: Sendable {
    private var sampleStart: ContinuousClock.Instant?
    private var sampleBytes: UInt64 = 0
    private var smoothedRate: Double = 0

    mutating func reset() {
        sampleStart = nil
        sampleBytes = 0
        smoothedRate = 0
    }

    mutating func update(
        bytes: UInt64,
        now: ContinuousClock.Instant = .now
    ) -> Double {
        guard let sampleStart else {
            self.sampleStart = now
            sampleBytes = bytes
            return 0
        }

        guard bytes >= sampleBytes else {
            self.sampleStart = now
            sampleBytes = bytes
            smoothedRate = 0
            return 0
        }

        let elapsed = TransferRateCalculator.seconds(sampleStart.duration(to: now))
        guard elapsed >= TransferRateCalculator.minimumSampleInterval else {
            return smoothedRate
        }

        let deltaBytes = bytes - sampleBytes
        self.sampleStart = now
        sampleBytes = bytes

        guard deltaBytes > 0 else {
            smoothedRate *= 0.75
            return smoothedRate.isFinite ? smoothedRate : 0
        }

        if let rate = TransferRateCalculator.sample(
            deltaBytes: deltaBytes,
            elapsedSeconds: elapsed,
            previousRate: smoothedRate
        ) {
            smoothedRate = rate
        }
        return smoothedRate
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

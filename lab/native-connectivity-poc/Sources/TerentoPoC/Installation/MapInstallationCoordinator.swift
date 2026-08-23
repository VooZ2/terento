import CryptoKit
import Foundation

enum MapInstallationStatus: String, Codable, Equatable, Sendable {
    case confirmationRequired = "CONFIRMATION_REQUIRED"
    case installVerified = "INSTALL_VERIFIED"
    case blockedExistingMapConflict = "BLOCKED_EXISTING_MAP_CONFLICT"
    case blockedInsufficientSpace = "BLOCKED_INSUFFICIENT_SPACE"
    case blockedUnknownTarget = "BLOCKED_UNKNOWN_TARGET"
    case blockedUnsupportedDevice = "BLOCKED_UNSUPPORTED_DEVICE"
    case blockedSourceArtifact = "BLOCKED_SOURCE_ARTIFACT"
    case blockedAmbiguousMapIdentity = "BLOCKED_AMBIGUOUS_MAP_IDENTITY"
    case failed = "FAILED"
}

struct MapInstallationDiagnostics: Equatable, Sendable {
    let sourceSizeBytes: UInt64
    let sourceSHA256: String
    let targetPath: String?
    let bytesTransferred: UInt64
    let transferTotalBytes: UInt64
    let elapsedMilliseconds: UInt64
    let remoteObjectExists: Bool
    let remoteSizeBytes: UInt64?
    let remoteSHA256: String?
    let metadataProvider: String?
    let metadataRegion: String?
    let metadataVersion: MapVersion?
    let metadataWarning: String?
    let freeSpaceBefore: UInt64
    let freeSpaceAfter: UInt64?
    let projectedFreeSpace: UInt64?
    let lithuaniaProtectionPassed: Bool
    let unrelatedFilesProtectionPassed: Bool

    static func initial(
        artifact: ValidatedMapArtifact?,
        freeSpaceBefore: UInt64
    ) -> MapInstallationDiagnostics {
        MapInstallationDiagnostics(
            sourceSizeBytes: artifact?.installSizeBytes ?? 0,
            sourceSHA256: artifact?.sha256 ?? "",
            targetPath: nil,
            bytesTransferred: 0,
            transferTotalBytes: artifact?.installSizeBytes ?? 0,
            elapsedMilliseconds: 0,
            remoteObjectExists: false,
            remoteSizeBytes: nil,
            remoteSHA256: nil,
            metadataProvider: nil,
            metadataRegion: nil,
            metadataVersion: nil,
            metadataWarning: nil,
            freeSpaceBefore: freeSpaceBefore,
            freeSpaceAfter: nil,
            projectedFreeSpace: nil,
            lithuaniaProtectionPassed: true,
            unrelatedFilesProtectionPassed: true
        )
    }
}

struct MapInstallationRequest: Sendable {
    let identity: DeviceIdentity
    let selectedMap: MapPackage
    let comparison: MapComparison
    let installedMaps: [InstalledMap]
    let inspectedFiles: [InstalledMapFile]
    let beforeDeviceFiles: [DeviceFile]
    let availableStorage: UInt64
    let profile: DeviceInstallProfile?
    let artifact: ValidatedMapArtifact?
    let userConfirmed: Bool
}

struct MapInstallationResult: Equatable, Sendable {
    let status: MapInstallationStatus
    let failure: InstallationFailure?
    let originalFailure: InstallationFailure?
    let cleanupFailure: InstallationFailure?
    let preflight: InstallationPreflightResult
    let transaction: InstallationTransaction
    let verification: TransferVerification?
    let diagnostics: MapInstallationDiagnostics
    let installedMap: InstalledMap?

    var isSuccess: Bool {
        status == .installVerified
    }
}

enum Stage42ArtifactValidationError: LocalizedError, Equatable, Sendable {
    case notExactValidatedArtifact
    case sourceUnavailable
    case sourceSizeMismatch
    case sourceHashMismatch

    var errorDescription: String? {
        switch self {
        case .notExactValidatedArtifact:
            return "The source is not the exact validated Stage 4.1 Latvia artifact."
        case .sourceUnavailable:
            return "The validated Latvia IMG is no longer available locally."
        case .sourceSizeMismatch:
            return "The local Latvia IMG size changed after validation."
        case .sourceHashMismatch:
            return "The local Latvia IMG contents changed after validation."
        }
    }
}

protocol MapInstallationArtifactValidator: Sendable {
    func validate(artifact: ValidatedMapArtifact, package: MapPackage) throws
}

/// The only artifact validator enabled by the Stage 4.2 production path.
/// It prevents an arbitrary local IMG from reaching the write transport.
struct Stage42ArtifactValidator: MapInstallationArtifactValidator, Sendable {
    static let expectedPackageID = "freizeitkarte-lva"
    static let expectedProvider = "freizeitkarte"
    static let expectedRegion = "LVA"
    static let expectedVersion = MapVersion(year: 2026, month: 5)
    static let expectedInstallSize: UInt64 = 348_684_288
    static let expectedDownloadSize: UInt64 = 298_518_679
    static let expectedSHA256 = "9a990a62156f61a78de82af78c6b1165c13ec5daaf789824029b2c6be4ba6103"
    static let expectedFilename = "terento_freizeitkarte_lva.img"

    func validate(artifact: ValidatedMapArtifact, package: MapPackage) throws {
        guard let expectedVersion = Self.expectedVersion else {
            throw Stage42ArtifactValidationError.notExactValidatedArtifact
        }

        guard package.id == Self.expectedPackageID,
              MapIdentity.normalizeProvider(package.providerId) == Self.expectedProvider,
              MapIdentity.normalizeRegion(package.regionId) == Self.expectedRegion,
              package.version == expectedVersion,
              artifact.catalogPackageID == Self.expectedPackageID,
              MapIdentity.normalizeProvider(artifact.provider) == Self.expectedProvider,
              MapIdentity.normalizeRegion(artifact.region) == Self.expectedRegion,
              artifact.version == expectedVersion,
              artifact.targetFilename == Self.expectedFilename,
              artifact.installSizeBytes == Self.expectedInstallSize,
              artifact.downloadSizeBytes == Self.expectedDownloadSize,
              artifact.sha256.caseInsensitiveCompare(Self.expectedSHA256) == .orderedSame,
              artifact.packageFormat == .zip else {
            throw Stage42ArtifactValidationError.notExactValidatedArtifact
        }

        let fileManager = FileManager.default
        guard fileManager.isReadableFile(atPath: artifact.localIMGURL.path) else {
            throw Stage42ArtifactValidationError.sourceUnavailable
        }

        let attributes = try fileManager.attributesOfItem(atPath: artifact.localIMGURL.path)
        guard let number = attributes[.size] as? NSNumber,
              number.uint64Value == Self.expectedInstallSize else {
            throw Stage42ArtifactValidationError.sourceSizeMismatch
        }

        let actualHash = try Self.sha256(of: artifact.localIMGURL)
        guard actualHash.caseInsensitiveCompare(Self.expectedSHA256) == .orderedSame else {
            throw Stage42ArtifactValidationError.sourceHashMismatch
        }
    }

    private static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty {
                break
            }
            hasher.update(data: data)
        }
        return hasher.finalize()
            .map { String(format: "%02x", $0) }
            .joined()
    }
}

private final class TransferProgressState: @unchecked Sendable {
    var value: TransferProgress

    init(value: TransferProgress) {
        self.value = value
    }
}

/// The single domain-level Stage 4.2 write coordinator. It owns the safety
/// sequence, but remains independent of libmtp through injected protocols.
struct MapInstallationCoordinator: Sendable {
    private let preflightEngine: InstallationPreflightEngine
    private let artifactValidator: any MapInstallationArtifactValidator
    private let transport: any MapInstallationTransport
    private let deviceReader: any InstallationDeviceReader
    private let manifestStore: any TerentoManifestStore
    private let transactionGate: InstallationTransactionGate
    private let now: @Sendable () -> Date

    init(
        preflightEngine: InstallationPreflightEngine = InstallationPreflightEngine(),
        artifactValidator: any MapInstallationArtifactValidator = Stage42ArtifactValidator(),
        transport: any MapInstallationTransport,
        deviceReader: any InstallationDeviceReader,
        manifestStore: any TerentoManifestStore,
        transactionGate: InstallationTransactionGate = .shared,
        now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.preflightEngine = preflightEngine
        self.artifactValidator = artifactValidator
        self.transport = transport
        self.deviceReader = deviceReader
        self.manifestStore = manifestStore
        self.transactionGate = transactionGate
        self.now = now
    }

    func run(
        _ request: MapInstallationRequest,
        onProgress: (@Sendable (TransferProgress) -> Void)? = nil,
        onPhase: (@Sendable (InstallationProcessPhase) -> Void)? = nil,
        onPhaseProgress: (@Sendable (InstallationProcessPhase, Double) -> Void)? = nil
    ) -> MapInstallationResult {
        let planningMap = request.artifact.map {
            request.selectedMap.withInstallSize($0.installSizeBytes)
        } ?? request.selectedMap
        let preflight = preflightEngine.evaluate(
            identity: request.identity,
            selectedMap: planningMap,
            comparison: request.comparison,
            installedMaps: request.installedMaps,
            inspectedFiles: request.inspectedFiles,
            availableStorage: request.availableStorage,
            profile: request.profile
        )
        var transaction = InstallationTransaction()
        var diagnostics = MapInstallationDiagnostics.initial(
            artifact: request.artifact,
            freeSpaceBefore: request.availableStorage
        )

        guard let artifact = request.artifact else {
            return blocked(
                status: .blockedSourceArtifact,
                failure: .sourceArtifactInvalid,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        guard preflight.status == .readyNewInstall else {
            return blockedForPreflight(
                preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        guard let targetDirectory = preflight.installTarget,
              let targetFilename = preflight.proposedFilename else {
            return blocked(
                status: .blockedUnknownTarget,
                failure: .unknownInstallTarget,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        let targetPath = "\(targetDirectory)/\(targetFilename)"
        diagnostics = diagnostics.withTarget(
            targetPath: targetPath,
            projectedFreeSpace: preflight.storagePlan?.projectedFreeSpace
        )

        if request.beforeDeviceFiles.contains(where: { $0.path == targetPath }) {
            return blocked(
                status: .blockedAmbiguousMapIdentity,
                failure: .mapIdentityAmbiguous,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        do {
            try artifactValidator.validate(artifact: artifact, package: request.selectedMap)
        } catch {
            return blocked(
                status: .blockedSourceArtifact,
                failure: .sourceArtifactInvalid,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        do {
            try Stage42TargetPolicy().validate(
                package: request.selectedMap,
                artifact: artifact,
                profile: request.profile
            )
        } catch let error as Stage42TargetPolicyError {
            let failure: InstallationFailure = error == .unsupportedDeviceProfile
                ? .unknownInstallTarget
                : .sourceArtifactInvalid
            let status: MapInstallationStatus = error == .unsupportedDeviceProfile
                ? .blockedUnsupportedDevice
                : .blockedSourceArtifact
            return blocked(
                status: status,
                failure: failure,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        } catch {
            return blocked(
                status: .blockedSourceArtifact,
                failure: .sourceArtifactInvalid,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        guard request.userConfirmed else {
            try? transaction.begin()
            return MapInstallationResult(
                status: .confirmationRequired,
                failure: nil,
                originalFailure: nil,
                cleanupFailure: nil,
                preflight: preflight,
                transaction: transaction,
                verification: nil,
                diagnostics: diagnostics,
                installedMap: nil
            )
        }

        do {
            try transactionGate.acquire(transactionID: transaction.id)
        } catch {
            return blocked(
                status: .failed,
                failure: .transactionAlreadyRunning,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }
        defer { transactionGate.release(transactionID: transaction.id) }

        do {
            let liveBeforeWrite = try deviceReader.readFileInventory()
            guard preWriteInventoryIsUnchanged(
                before: request.beforeDeviceFiles,
                live: liveBeforeWrite,
                targetPath: targetPath
            ) else {
                return blocked(
                    status: .blockedAmbiguousMapIdentity,
                    failure: .protectionViolation,
                    preflight: preflight,
                    transaction: transaction,
                    diagnostics: diagnostics
                )
            }
        } catch {
            return blocked(
                status: .failed,
                failure: Self.failure(for: error, during: .postVerification),
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }

        let startedAt = ContinuousClock.now
        do {
            try transaction.begin()
            try transaction.transition(to: .preparing)
            onPhase?(.preparing)
            onPhaseProgress?(.preparing, 0)
            try transaction.recordSource(
                sizeBytes: artifact.installSizeBytes,
                sha256: artifact.sha256
            )
            try transaction.transition(to: .readyToWrite)
            onPhaseProgress?(.preparing, 1)
            try transaction.transition(to: .writing)
            onPhase?(.installing)
            onPhaseProgress?(.installing, 0)

            let progressState = TransferProgressState(
                value: TransferProgress(
                    bytesTransferred: 0,
                    totalBytes: artifact.installSizeBytes
                )
            )
            let written = try transport.write(
                sourceURL: artifact.localIMGURL,
                targetFilename: targetFilename,
                progress: { progress in
                    progressState.value = progress
                    onProgress?(progress)
                }
            )

            try transaction.transition(to: .verifying)
            onPhase?(.finishing)
            onPhaseProgress?(.finishing, 0)
            let readBack: MTPReadBackMapObject
            do {
                readBack = try transport.readBack(
                    targetFilename: targetFilename,
                    expectedItemID: written.itemID,
                    targetPath: targetPath
                )
            } catch {
                let failure = Self.failure(for: error, during: .verification)
                return failureResult(
                    failure: failure,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: diagnostics.withProgress(
                        progress: progressState.value,
                        elapsedMilliseconds: elapsedMilliseconds(since: startedAt)
                    ),
                    remoteObjectID: written.itemID,
                    shouldCleanup: true
                )
            }
            defer { try? FileManager.default.removeItem(at: readBack.localURL) }
            onPhaseProgress?(.finishing, 0.25)

            let remoteHash: String
            do {
                remoteHash = try Self.sha256(of: readBack.localURL)
            } catch {
                return failureResult(
                    failure: .hashMismatch,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: diagnostics.withProgress(
                        progress: progressState.value,
                        elapsedMilliseconds: elapsedMilliseconds(since: startedAt)
                    ),
                    remoteObjectID: written.itemID,
                    shouldCleanup: true
                )
            }
            let verification = TransferVerifier().verify(
                sourceSizeBytes: artifact.installSizeBytes,
                sourceSHA256: artifact.sha256,
                remoteSizeBytes: readBack.reportedSizeBytes,
                remoteSHA256: remoteHash
            )
            try transaction.recordTransferVerification(verification)
            onPhaseProgress?(.finishing, 0.45)
            let verifiedDiagnostics = diagnostics.withRemote(
                exists: true,
                size: readBack.reportedSizeBytes,
                hash: remoteHash,
                progress: progressState.value,
                elapsedMilliseconds: elapsedMilliseconds(since: startedAt)
            )

            guard verification.isVerified else {
                let failure: InstallationFailure = verification.status == .sizeMismatch
                    ? .sizeMismatch
                    : .hashMismatch
                return failureResult(
                    failure: failure,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: verifiedDiagnostics,
                    remoteObjectID: written.itemID,
                    shouldCleanup: true,
                    verification: verification
                )
            }

            let metadataResult = verifyMetadata(
                at: readBack.localURL,
                expectedPackage: request.selectedMap
            )
            if let metadataFailure = metadataResult.failure {
                return failureResult(
                    failure: metadataFailure,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: verifiedDiagnostics.withMetadata(
                        provider: metadataResult.provider,
                        region: metadataResult.region,
                        version: metadataResult.version,
                        warning: metadataResult.warning
                    ),
                    remoteObjectID: written.itemID,
                    shouldCleanup: true,
                    verification: verification
                )
            }
            onPhaseProgress?(.finishing, 0.65)

            let afterFiles: [DeviceFile]
            let afterSnapshot: DeviceSnapshot
            do {
                afterFiles = try deviceReader.readFileInventory()
                afterSnapshot = try deviceReader.readSnapshot()
            } catch {
                return failureResult(
                    failure: Self.failure(for: error, during: .postVerification),
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: verifiedDiagnostics,
                    remoteObjectID: written.itemID,
                    shouldCleanup: true,
                    verification: verification
                )
            }

            guard let targetObject = afterFiles.first(where: {
                $0.path == targetPath && $0.itemID == written.itemID
            }) else {
                return failureResult(
                    failure: .remoteFileMissing,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: verifiedDiagnostics,
                    remoteObjectID: written.itemID,
                    shouldCleanup: true,
                    verification: verification
                )
            }
            onPhaseProgress?(.finishing, 0.85)

            let protection = protectionResult(
                before: request.beforeDeviceFiles,
                after: afterFiles,
                targetPath: targetPath,
                expectedItemID: written.itemID,
                expectedFilename: targetFilename,
                expectedSizeBytes: artifact.installSizeBytes
            )
            guard protection.unrelatedFilesUnchanged else {
                return failureResult(
                    failure: .protectionViolation,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: verifiedDiagnostics.withProtection(
                        lithuaniaUnchanged: protection.lithuaniaUnchanged,
                        unrelatedUnchanged: false,
                        freeSpaceAfter: afterSnapshot.freeSpace
                    ),
                    remoteObjectID: written.itemID,
                    shouldCleanup: true,
                    verification: verification
                )
            }

            let installedMap = makeManagedMap(
                artifact: artifact,
                package: request.selectedMap,
                target: targetObject,
                metadata: metadataResult
            )
            let manifestEntry = TerentoManifestEntry(
                deviceKey: request.identity.localManifestDeviceKey,
                devicePath: targetPath,
                filename: targetFilename,
                providerId: request.selectedMap.providerId,
                regionId: request.selectedMap.regionId,
                version: artifact.version,
                sizeBytes: artifact.installSizeBytes,
                sha256: artifact.sha256,
                installedAt: now()
            )

            do {
                try manifestStore.record(manifestEntry)
            } catch {
                return failureResult(
                    failure: .manifestFailed,
                    transaction: &transaction,
                    preflight: preflight,
                    diagnostics: verifiedDiagnostics.withProtection(
                        lithuaniaUnchanged: protection.lithuaniaUnchanged,
                        unrelatedUnchanged: true,
                        freeSpaceAfter: afterSnapshot.freeSpace
                    ),
                    remoteObjectID: nil,
                    shouldCleanup: false,
                    verification: verification
                )
            }
            onPhaseProgress?(.finishing, 1)

            try transaction.transition(to: .completed)
            return MapInstallationResult(
                status: .installVerified,
                failure: nil,
                originalFailure: nil,
                cleanupFailure: nil,
                preflight: preflight,
                transaction: transaction,
                verification: verification,
                diagnostics: verifiedDiagnostics.withMetadata(
                    provider: metadataResult.provider,
                    region: metadataResult.region,
                    version: metadataResult.version,
                    warning: metadataResult.warning
                ).withProtection(
                    lithuaniaUnchanged: protection.lithuaniaUnchanged,
                    unrelatedUnchanged: true,
                    freeSpaceAfter: afterSnapshot.freeSpace
                ),
                installedMap: installedMap
            )
        } catch {
            let failure = Self.failure(for: error, during: .write)
            let createdItemID = Self.createdItemID(from: error)
            return failureResult(
                failure: failure,
                transaction: &transaction,
                preflight: preflight,
                diagnostics: diagnostics.withProgress(
                    progress: TransferProgress(
                        bytesTransferred: 0,
                        totalBytes: artifact.installSizeBytes
                    ),
                    elapsedMilliseconds: elapsedMilliseconds(since: startedAt)
                    ),
                remoteObjectID: createdItemID,
                shouldCleanup: createdItemID != nil
            )
        }
    }

    private func blockedForPreflight(
        _ preflight: InstallationPreflightResult,
        transaction: InstallationTransaction,
        diagnostics: MapInstallationDiagnostics
    ) -> MapInstallationResult {
        switch preflight.status {
        case .readyWithExistingMapConflict:
            return blocked(
                status: .blockedExistingMapConflict,
                failure: .existingMapConflict,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .blockedInsufficientSpace:
            return blocked(
                status: .blockedInsufficientSpace,
                failure: .insufficientSpace,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .blockedUnknownInstallSize:
            return blocked(
                status: .blockedInsufficientSpace,
                failure: .unknownInstallSize,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .blockedUnknownTarget:
            return blocked(
                status: .blockedUnknownTarget,
                failure: .unknownInstallTarget,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .blockedUnsupportedDevice:
            return blocked(
                status: .blockedUnsupportedDevice,
                failure: .unknownInstallTarget,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .blockedAmbiguousMapIdentity:
            return blocked(
                status: .blockedAmbiguousMapIdentity,
                failure: .mapIdentityAmbiguous,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .error:
            return blocked(
                status: .failed,
                failure: .sourceArtifactInvalid,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        case .readyNewInstall:
            return blocked(
                status: .failed,
                failure: .invalidStateTransition,
                preflight: preflight,
                transaction: transaction,
                diagnostics: diagnostics
            )
        }
    }

    private func blocked(
        status: MapInstallationStatus,
        failure: InstallationFailure,
        preflight: InstallationPreflightResult,
        transaction: InstallationTransaction,
        diagnostics: MapInstallationDiagnostics
    ) -> MapInstallationResult {
        MapInstallationResult(
            status: status,
            failure: failure,
            originalFailure: nil,
            cleanupFailure: nil,
            preflight: preflight,
            transaction: transaction,
            verification: nil,
            diagnostics: diagnostics,
            installedMap: nil
        )
    }

    private func failureResult(
        failure: InstallationFailure,
        transaction: inout InstallationTransaction,
        preflight: InstallationPreflightResult,
        diagnostics: MapInstallationDiagnostics,
        remoteObjectID: UInt32?,
        shouldCleanup: Bool,
        verification: TransferVerification? = nil
    ) -> MapInstallationResult {
        var cleanupFailure: InstallationFailure?
        if shouldCleanup, let remoteObjectID, remoteObjectID != 0 {
            do {
                try transport.deleteExact(
                    targetFilename: preflight.proposedFilename ?? Stage42ArtifactValidator.expectedFilename,
                    expectedItemID: remoteObjectID
                )
            } catch {
                cleanupFailure = .cleanupFailed
            }
        }

        let finalFailure = cleanupFailure ?? failure
        if transaction.state != .failed && transaction.state != .completed {
            try? transaction.fail(finalFailure)
        }

        return MapInstallationResult(
            status: .failed,
            failure: finalFailure,
            originalFailure: cleanupFailure == nil ? nil : failure,
            cleanupFailure: cleanupFailure,
            preflight: preflight,
            transaction: transaction,
            verification: verification,
            diagnostics: diagnostics,
            installedMap: nil
        )
    }

    private enum FailurePhase {
        case write
        case verification
        case postVerification
    }

    private static func failure(for error: Error, during phase: FailurePhase) -> InstallationFailure {
        if let error = error as? InstallationTransportError {
            switch error {
            case .remoteFileMissing:
                return .remoteFileMissing
            case .deviceDisconnected(_, _):
                return .deviceDisconnected
            case .targetAlreadyExists:
                return .existingMapConflict
            case .objectIdentityMismatch:
                return .remoteFileMissing
            case .unsupportedDevice:
                return .unknownInstallTarget
            case .operationFailed(_, _):
                return phase == .write ? .writeFailed : .deviceDisconnected
            }
        }

        return phase == .write ? .writeFailed : .deviceDisconnected
    }

    private static func createdItemID(from error: Error) -> UInt32? {
        guard let error = error as? InstallationTransportError else {
            return nil
        }

        switch error {
        case .deviceDisconnected(_, let createdItemID),
             .operationFailed(_, let createdItemID):
            return createdItemID
        default:
            return nil
        }
    }

    private static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty {
                break
            }
            hasher.update(data: data)
        }
        return hasher.finalize()
            .map { String(format: "%02x", $0) }
            .joined()
    }

    private struct MetadataResult: Sendable {
        let provider: String?
        let region: String?
        let version: MapVersion?
        let rawVersion: String?
        let name: String?
        let family: String?
        let warning: String?
        let failure: InstallationFailure?
    }

    private func verifyMetadata(
        at url: URL,
        expectedPackage: MapPackage
    ) -> MetadataResult {
        do {
            let prefix = try MapPackageFormat.readPrefix(
                from: url,
                maxLength: GarminIMGMetadataParser.prefixLength
            )
            guard let metadata = GarminIMGMetadataParser().parse(prefix) else {
                return MetadataResult(
                    provider: nil,
                    region: nil,
                    version: nil,
                    rawVersion: nil,
                    name: nil,
                    family: nil,
                    warning: "The verified IMG could not be parsed again after read-back.",
                    failure: nil
                )
            }

            let actualIdentity = MapIdentity(provider: metadata.provider, region: metadata.region)
            guard actualIdentity == expectedPackage.identity else {
                return MetadataResult(
                    provider: metadata.provider,
                    region: metadata.region,
                    version: metadata.version,
                    rawVersion: metadata.rawVersion,
                    name: metadata.name,
                    family: metadata.family,
                    warning: nil,
                    failure: .metadataMismatch
                )
            }

            let warning = metadata.version == nil
                ? "The verified IMG identity is correct, but its release version could not be parsed again."
                : nil
            if let version = metadata.version, version != expectedPackage.version {
                return MetadataResult(
                    provider: metadata.provider,
                    region: metadata.region,
                    version: version,
                    rawVersion: metadata.rawVersion,
                    name: metadata.name,
                    family: metadata.family,
                    warning: nil,
                    failure: .metadataMismatch
                )
            }

            return MetadataResult(
                provider: metadata.provider,
                region: metadata.region,
                version: metadata.version,
                rawVersion: metadata.rawVersion,
                name: metadata.name,
                family: metadata.family,
                warning: warning,
                failure: nil
            )
        } catch {
            return MetadataResult(
                provider: nil,
                region: nil,
                version: nil,
                rawVersion: nil,
                name: nil,
                family: nil,
                warning: "The verified IMG metadata could not be read again.",
                failure: nil
            )
        }
    }

    private func makeManagedMap(
        artifact: ValidatedMapArtifact,
        package: MapPackage,
        target: DeviceFile,
        metadata: MetadataResult
    ) -> InstalledMap {
        InstalledMap(
            name: metadata.name ?? package.name,
            provider: metadata.provider ?? artifact.provider,
            region: metadata.region ?? artifact.region,
            family: metadata.family ?? "Freizeitkarte_\(artifact.region)+",
            rawVersion: metadata.rawVersion ?? artifact.rawRelease,
            version: metadata.version ?? artifact.version,
            identifier: package.identifier,
            productId: nil,
            familyId: nil,
            sizeBytes: target.sizeBytes,
            sourceFile: InstalledMapFile(
                path: target.path,
                filename: target.filename,
                sizeBytes: target.sizeBytes
            ),
            metadataStatus: .parsed,
            managementState: .managedByTerento
        )
    }

    private struct ProtectionResult: Sendable {
        let lithuaniaUnchanged: Bool
        let unrelatedFilesUnchanged: Bool
    }

    private func protectionResult(
        before: [DeviceFile],
        after: [DeviceFile],
        targetPath: String,
        expectedItemID: UInt32,
        expectedFilename: String,
        expectedSizeBytes: UInt64
    ) -> ProtectionResult {
        let beforeComparable = Set(before.filter { $0.path != targetPath }.map(Self.comparable))
        let afterComparable = Set(after.filter { $0.path != targetPath }.map(Self.comparable))
        let lithuaniaPath = "/GARMIN/freizeitkarte-lithuania.img"
        let beforeLithuania = before.first(where: { $0.path == lithuaniaPath })
        let afterLithuania = after.first(where: { $0.path == lithuaniaPath })
        let lithuaniaUnchanged: Bool
        switch (beforeLithuania, afterLithuania) {
        case (nil, nil):
            lithuaniaUnchanged = true
        case let (before?, after?):
            lithuaniaUnchanged = Self.comparable(before) == Self.comparable(after)
        default:
            lithuaniaUnchanged = false
        }

        let target = after.first(where: { $0.path == targetPath && $0.itemID == expectedItemID })
        let targetUnchanged = target.map {
            !$0.isFolder
                && $0.filename == expectedFilename
                && $0.sizeBytes == expectedSizeBytes
                && $0.path == targetPath
        } ?? false

        return ProtectionResult(
            lithuaniaUnchanged: lithuaniaUnchanged,
            unrelatedFilesUnchanged: beforeComparable == afterComparable
                && lithuaniaUnchanged
                && targetUnchanged
        )
    }

    private func preWriteInventoryIsUnchanged(
        before: [DeviceFile],
        live: [DeviceFile],
        targetPath: String
    ) -> Bool {
        // The target must still be absent immediately before the write. All
        // existing objects must retain their full stable identity. DeviceFile
        // has no volatile timestamp field, so it is intentionally excluded.
        guard !live.contains(where: { $0.path == targetPath }) else {
            return false
        }

        let beforeComparable = Set(before.filter { $0.path != targetPath }.map(Self.comparable))
        let liveComparable = Set(live.filter { $0.path != targetPath }.map(Self.comparable))
        return beforeComparable == liveComparable
    }

    private static func comparable(_ file: DeviceFile) -> String {
        "\(file.storageID)|\(file.itemID)|\(file.parentID)|\(file.path)|\(file.filename)|\(file.sizeBytes)|\(file.isFolder)"
    }

    private func elapsedMilliseconds(since start: ContinuousClock.Instant) -> UInt64 {
        let components = start.duration(to: .now).components
        let milliseconds = Double(components.seconds) * 1_000
            + Double(components.attoseconds) / 1_000_000_000_000_000
        return UInt64(max(0, milliseconds))
    }
}

private extension MapInstallationDiagnostics {
    func withTarget(targetPath: String, projectedFreeSpace: UInt64?) -> MapInstallationDiagnostics {
        MapInstallationDiagnostics(
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            targetPath: targetPath,
            bytesTransferred: bytesTransferred,
            transferTotalBytes: transferTotalBytes,
            elapsedMilliseconds: elapsedMilliseconds,
            remoteObjectExists: remoteObjectExists,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: remoteSHA256,
            metadataProvider: metadataProvider,
            metadataRegion: metadataRegion,
            metadataVersion: metadataVersion,
            metadataWarning: metadataWarning,
            freeSpaceBefore: freeSpaceBefore,
            freeSpaceAfter: freeSpaceAfter,
            projectedFreeSpace: projectedFreeSpace,
            lithuaniaProtectionPassed: lithuaniaProtectionPassed,
            unrelatedFilesProtectionPassed: unrelatedFilesProtectionPassed
        )
    }

    func withProgress(progress: TransferProgress, elapsedMilliseconds: UInt64) -> MapInstallationDiagnostics {
        MapInstallationDiagnostics(
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            targetPath: targetPath,
            bytesTransferred: progress.bytesTransferred,
            transferTotalBytes: progress.totalBytes,
            elapsedMilliseconds: elapsedMilliseconds,
            remoteObjectExists: remoteObjectExists,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: remoteSHA256,
            metadataProvider: metadataProvider,
            metadataRegion: metadataRegion,
            metadataVersion: metadataVersion,
            metadataWarning: metadataWarning,
            freeSpaceBefore: freeSpaceBefore,
            freeSpaceAfter: freeSpaceAfter,
            projectedFreeSpace: projectedFreeSpace,
            lithuaniaProtectionPassed: lithuaniaProtectionPassed,
            unrelatedFilesProtectionPassed: unrelatedFilesProtectionPassed
        )
    }

    func withRemote(
        exists: Bool,
        size: UInt64?,
        hash: String?,
        progress: TransferProgress,
        elapsedMilliseconds: UInt64
    ) -> MapInstallationDiagnostics {
        withProgress(progress: progress, elapsedMilliseconds: elapsedMilliseconds).withRemoteOnly(
            exists: exists,
            size: size,
            hash: hash
        )
    }

    private func withRemoteOnly(
        exists: Bool,
        size: UInt64?,
        hash: String?
    ) -> MapInstallationDiagnostics {
        MapInstallationDiagnostics(
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            targetPath: targetPath,
            bytesTransferred: bytesTransferred,
            transferTotalBytes: transferTotalBytes,
            elapsedMilliseconds: elapsedMilliseconds,
            remoteObjectExists: exists,
            remoteSizeBytes: size,
            remoteSHA256: hash,
            metadataProvider: metadataProvider,
            metadataRegion: metadataRegion,
            metadataVersion: metadataVersion,
            metadataWarning: metadataWarning,
            freeSpaceBefore: freeSpaceBefore,
            freeSpaceAfter: freeSpaceAfter,
            projectedFreeSpace: projectedFreeSpace,
            lithuaniaProtectionPassed: lithuaniaProtectionPassed,
            unrelatedFilesProtectionPassed: unrelatedFilesProtectionPassed
        )
    }

    func withMetadata(
        provider: String?,
        region: String?,
        version: MapVersion?,
        warning: String?
    ) -> MapInstallationDiagnostics {
        MapInstallationDiagnostics(
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            targetPath: targetPath,
            bytesTransferred: bytesTransferred,
            transferTotalBytes: transferTotalBytes,
            elapsedMilliseconds: elapsedMilliseconds,
            remoteObjectExists: remoteObjectExists,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: remoteSHA256,
            metadataProvider: provider,
            metadataRegion: region,
            metadataVersion: version,
            metadataWarning: warning,
            freeSpaceBefore: freeSpaceBefore,
            freeSpaceAfter: freeSpaceAfter,
            projectedFreeSpace: projectedFreeSpace,
            lithuaniaProtectionPassed: lithuaniaProtectionPassed,
            unrelatedFilesProtectionPassed: unrelatedFilesProtectionPassed
        )
    }

    func withProtection(
        lithuaniaUnchanged: Bool,
        unrelatedUnchanged: Bool,
        freeSpaceAfter: UInt64?
    ) -> MapInstallationDiagnostics {
        MapInstallationDiagnostics(
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            targetPath: targetPath,
            bytesTransferred: bytesTransferred,
            transferTotalBytes: transferTotalBytes,
            elapsedMilliseconds: elapsedMilliseconds,
            remoteObjectExists: remoteObjectExists,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: remoteSHA256,
            metadataProvider: metadataProvider,
            metadataRegion: metadataRegion,
            metadataVersion: metadataVersion,
            metadataWarning: metadataWarning,
            freeSpaceBefore: freeSpaceBefore,
            freeSpaceAfter: freeSpaceAfter,
            projectedFreeSpace: projectedFreeSpace,
            lithuaniaProtectionPassed: lithuaniaUnchanged,
            unrelatedFilesProtectionPassed: unrelatedUnchanged
        )
    }
}

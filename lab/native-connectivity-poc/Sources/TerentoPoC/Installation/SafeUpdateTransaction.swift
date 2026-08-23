import Foundation

/// Stage 5.3 is deliberately separate from SwiftUI. It coordinates the
/// update order, but the transport remains an injected boundary so automated
/// tests can prove that no device mutation happens before every safety gate.
enum SafeUpdateStatus: String, Equatable, Sendable {
    case success = "UPDATE_SUCCESS"
    case blockedNotManaged = "UPDATE_BLOCKED_NOT_MANAGED"
    case blockedNoUpdate = "UPDATE_BLOCKED_NO_UPDATE"
    case blockedNewerInstalled = "UPDATE_BLOCKED_NEWER_INSTALLED"
    case blockedUnknownState = "UPDATE_BLOCKED_UNKNOWN_STATE"
    case blockedAmbiguousMapIdentity = "UPDATE_BLOCKED_AMBIGUOUS_MAP_IDENTITY"
    case blockedCurrentObjectChanged = "UPDATE_BLOCKED_CURRENT_OBJECT_CHANGED"
    case blockedInsufficientSpace = "UPDATE_BLOCKED_INSUFFICIENT_SPACE"
    case blockedUnknownTarget = "UPDATE_BLOCKED_UNKNOWN_TARGET"
    case blockedUnsupportedDevice = "UPDATE_BLOCKED_UNSUPPORTED_DEVICE"
    case blockedConfirmationRequired = "UPDATE_BLOCKED_CONFIRMATION_REQUIRED"
    case blockedTransactionAlreadyRunning = "UPDATE_BLOCKED_TRANSACTION_ALREADY_RUNNING"
    case failedAcquisition = "UPDATE_FAILED_ACQUISITION"
    case failedSourceValidation = "UPDATE_FAILED_SOURCE_VALIDATION"
    case failedBackup = "UPDATE_FAILED_BACKUP"
    case failedDeviceDisconnected = "UPDATE_FAILED_DEVICE_DISCONNECTED"
    case failedWrite = "UPDATE_FAILED_WRITE"
    case failedRemoteMissing = "UPDATE_FAILED_REMOTE_MISSING"
    case failedSizeMismatch = "UPDATE_FAILED_SIZE_MISMATCH"
    case failedHashMismatch = "UPDATE_FAILED_HASH_MISMATCH"
    case failedMetadataMismatch = "UPDATE_FAILED_METADATA_MISMATCH"
    case failedCommit = "UPDATE_FAILED_COMMIT"
    case failedPostVerify = "UPDATE_FAILED_POST_VERIFY"
    case failedManifestReconciliation = "UPDATE_FAILED_MANIFEST_RECONCILIATION"
    case failedCleanup = "UPDATE_FAILED_CLEANUP"

    var isSuccess: Bool { self == .success }
}

enum SafeUpdateState: String, Equatable, Sendable {
    case idle = "IDLE"
    case validating = "VALIDATING"
    case revalidating = "REVALIDATING"
    case acquiring = "ACQUIRING"
    case backingUp = "BACKING_UP"
    case writing = "WRITING"
    case verifying = "VERIFYING"
    case committing = "COMMITTING"
    case postVerifying = "POST_VERIFYING"
    case reconcilingManifest = "RECONCILING_MANIFEST"
    case completed = "COMPLETED"
    case failed = "FAILED"
}

struct SafeUpdateProgress: Equatable, Sendable {
    let state: SafeUpdateState
    let bytesCompleted: UInt64
    let totalBytes: UInt64
    let bytesPerSecond: Double

    var fractionCompleted: Double {
        guard totalBytes > 0 else { return 0 }
        return min(1, Double(bytesCompleted) / Double(totalBytes))
    }
}

struct SafeUpdateRemoteObject: Equatable, Sendable {
    let file: InstalledMapFile
    let identity: MapIdentity
    let version: MapVersion?
    let ownership: MapManagementState
    let sha256: String?
}

struct SafeUpdateSourceArtifact: Equatable, Sendable {
    let provider: String
    let region: String
    let version: MapVersion
    let localIMGURL: URL
    let installSizeBytes: UInt64
    let sha256: String
    let sourcePackageURL: URL
    let catalogPackageID: String
    let targetFilename: String

    init(
        provider: String,
        region: String,
        version: MapVersion,
        localIMGURL: URL,
        installSizeBytes: UInt64,
        sha256: String,
        sourcePackageURL: URL,
        catalogPackageID: String,
        targetFilename: String
    ) {
        self.provider = provider
        self.region = region
        self.version = version
        self.localIMGURL = localIMGURL
        self.installSizeBytes = installSizeBytes
        self.sha256 = sha256
        self.sourcePackageURL = sourcePackageURL
        self.catalogPackageID = catalogPackageID
        self.targetFilename = targetFilename
    }

    init(_ artifact: ValidatedMapArtifact) {
        self.init(
            provider: artifact.provider,
            region: artifact.region,
            version: artifact.version,
            localIMGURL: artifact.localIMGURL,
            installSizeBytes: artifact.installSizeBytes,
            sha256: artifact.sha256,
            sourcePackageURL: artifact.sourcePackageURL,
            catalogPackageID: artifact.catalogPackageID,
            targetFilename: artifact.targetFilename
        )
    }
}

enum SafeUpdateAcquisitionError: LocalizedError, Equatable, Sendable {
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .failed(let message): return message
        }
    }
}

protocol SafeUpdateArtifactProvider: Sendable {
    func acquire(
        package: MapPackage,
        onProgress: (@Sendable (SafeUpdateProgress) -> Void)?
    ) async throws -> SafeUpdateSourceArtifact
}

/// Production adapter for the existing Stage 4.1 acquisition pipeline. It
/// does not introduce a second download path or a hardcoded provider URL.
struct MapPackageAcquisitionProvider: SafeUpdateArtifactProvider, Sendable {
    private let acquirer: MapPackageAcquirer

    init(acquirer: MapPackageAcquirer = MapPackageAcquirer()) {
        self.acquirer = acquirer
    }

    func acquire(
        package: MapPackage,
        onProgress: (@Sendable (SafeUpdateProgress) -> Void)? = nil
    ) async throws -> SafeUpdateSourceArtifact {
        do {
            let artifact = try await acquirer.acquire(
                package: package,
                onStateChange: { state in
                    let safeState: SafeUpdateState = {
                        switch state {
                        case .downloading: return .acquiring
                        case .validatingDownload, .extracting, .inspectingIMG,
                             .validatingIdentity, .hashing, .validated,
                             .resolvingPackage, .failed, .idle:
                            return .acquiring
                        }
                    }()
                    onProgress?(SafeUpdateProgress(
                        state: safeState,
                        bytesCompleted: 0,
                        totalBytes: package.expectedDownloadSizeBytes ?? 0,
                        bytesPerSecond: 0
                    ))
                },
                onDownloadProgress: { progress in
                    onProgress?(SafeUpdateProgress(
                        state: .acquiring,
                        bytesCompleted: progress.bytesDownloaded,
                        totalBytes: progress.totalBytes,
                        bytesPerSecond: progress.bytesPerSecond
                    ))
                }
            )
            return SafeUpdateSourceArtifact(artifact)
        } catch {
            throw SafeUpdateAcquisitionError.failed(error.localizedDescription)
        }
    }
}

protocol SafeUpdateSourceValidator: Sendable {
    func validate(
        artifact: SafeUpdateSourceArtifact,
        package: MapPackage
    ) throws
}

enum SafeUpdateSourceValidationError: LocalizedError, Equatable, Sendable {
    case mismatch(String)

    var errorDescription: String? {
        switch self {
        case .mismatch(let message): return message
        }
    }
}

/// Re-checks the locally acquired IMG immediately before any device write.
/// Stage 4.1 already validates the source; this second check protects the
/// update transaction from a changed or replaced local artifact.
struct DefaultSafeUpdateSourceValidator: SafeUpdateSourceValidator, Sendable {
    func validate(
        artifact: SafeUpdateSourceArtifact,
        package: MapPackage
    ) throws {
        guard let expectedIdentity = package.identity,
              MapIdentity(provider: artifact.provider, region: artifact.region) == expectedIdentity else {
            throw SafeUpdateSourceValidationError.mismatch("The source provider or region does not match the selected map.")
        }

        guard artifact.version == package.version,
              artifact.catalogPackageID == package.id,
              artifact.installSizeBytes > 0,
              artifact.sha256.count == 64,
              artifact.sha256.allSatisfy({ $0.isHexDigit }) else {
            throw SafeUpdateSourceValidationError.mismatch("The source version or integrity record is incomplete.")
        }

        let expectedFilename = try TerentoManagedFilenameGenerator().filename(
            providerId: package.providerId,
            regionId: package.regionId
        )
        guard artifact.targetFilename == expectedFilename else {
            throw SafeUpdateSourceValidationError.mismatch("The source target filename is not the approved Terento name.")
        }

        do {
            let validated = try MapSourceValidator().validate(
                fileURL: artifact.localIMGURL,
                expectedPackage: package
            )
            guard validated.sizeBytes == artifact.installSizeBytes,
                  normalized(validated.sha256) == normalized(artifact.sha256) else {
                throw SafeUpdateSourceValidationError.mismatch("The local source file changed after acquisition.")
            }
        } catch let error as SafeUpdateSourceValidationError {
            throw error
        } catch {
            throw SafeUpdateSourceValidationError.mismatch("The acquired IMG failed its final validation.")
        }
    }

    private func normalized(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}

enum SafeUpdateTransportError: LocalizedError, Equatable, Sendable {
    case deviceDisconnected(String)
    case writeFailed(String)
    case remoteMissing
    case sizeMismatch
    case hashMismatch
    case metadataMismatch
    case operationFailed(String)

    var errorDescription: String? {
        switch self {
        case .deviceDisconnected(let message),
             .writeFailed(let message),
             .operationFailed(let message):
            return message
        case .remoteMissing: return "The new map was not found after transfer."
        case .sizeMismatch: return "The transferred map size did not match the source."
        case .hashMismatch: return "The transferred map contents did not match the source."
        case .metadataMismatch: return "The transferred map metadata did not match the selected map."
        }
    }
}

/// The Stage 5.3 transport includes only operations needed by this
/// coordinator. Device adapters must implement transaction cleanup only for
/// the exact object returned by this transaction, never by filename alone.
protocol SafeUpdateTransport: MapLifecycleReadTransport, SafeDeleteTransport, Sendable {
    func inspectCurrentObject(_ expected: SafeUpdateRemoteObject) throws -> SafeUpdateRemoteObject

    func writeTransactionObject(
        sourceURL: URL,
        targetPath: String,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> SafeUpdateRemoteObject

    func verifyTransactionObject(
        _ object: SafeUpdateRemoteObject,
        expected: SafeUpdateSourceArtifact
    ) throws -> SafeUpdateRemoteObject

    func cleanupTransactionObject(_ object: SafeUpdateRemoteObject) throws
    func readFreeSpace() throws -> UInt64
    func rescanObjects() throws -> [SafeUpdateRemoteObject]
}

protocol SafeUpdateManifestReconciler: Sendable {
    func reconcile(
        deviceKey: String,
        oldObject: SafeUpdateRemoteObject,
        newObject: SafeUpdateRemoteObject,
        package: MapPackage,
        finalObjects: [SafeUpdateRemoteObject]
    ) throws
}

struct LocalSafeUpdateManifestReconciler: SafeUpdateManifestReconciler, Sendable {
    private let store: any TerentoManifestUpdateStore
    private let now: @Sendable () -> Date

    init(
        store: any TerentoManifestUpdateStore = LocalTerentoManifestStore(),
        now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.store = store
        self.now = now
    }

    func reconcile(
        deviceKey: String,
        oldObject: SafeUpdateRemoteObject,
        newObject: SafeUpdateRemoteObject,
        package: MapPackage,
        finalObjects: [SafeUpdateRemoteObject]
    ) throws {
        guard finalObjects.contains(where: { $0.file == newObject.file }),
              !finalObjects.contains(where: {
                  $0.file.itemID == oldObject.file.itemID
                      || $0.file.path == oldObject.file.path
              }),
              let identity = package.identity,
              let hash = newObject.sha256,
              newObject.version == package.version,
              newObject.ownership == .managedByTerento else {
            throw TerentoManifestStoreError.cleanupFailed
        }

        let entry = TerentoManifestEntry(
            deviceKey: deviceKey,
            devicePath: newObject.file.path,
            filename: newObject.file.filename,
            providerId: identity.provider,
            regionId: identity.region,
            version: package.version,
            sizeBytes: newObject.file.sizeBytes,
            sha256: hash,
            installedAt: now()
        )
        try store.replaceAfterUpdate(
            deviceKey: deviceKey,
            oldDevicePath: oldObject.file.path,
            oldFilename: oldObject.file.filename,
            newEntry: entry
        )
    }
}

struct SafeUpdateRequest: Sendable {
    let deviceKey: String
    let identity: DeviceIdentity
    let profile: DeviceInstallProfile?
    let selectedMap: MapPackage
    let comparison: MapComparison
    let currentItem: MapLifecycleItem
    let currentObject: SafeUpdateRemoteObject
    let backupDirectory: URL
    let confirmed: Bool
    let deviceConnected: Bool
}

struct SafeUpdateResult: Equatable, Sendable {
    let status: SafeUpdateStatus
    let state: SafeUpdateState
    let message: String
    let storagePlan: StoragePlan?
    let backup: ReadBackupResult?
    let newObject: SafeUpdateRemoteObject?
    let finalObjects: [SafeUpdateRemoteObject]
    let oldMapPreserved: Bool

    var isSuccess: Bool { status.isSuccess }
}

struct SafeUpdateTransaction: Sendable {
    private let gate: InstallationTransactionGate
    private let sourceValidator: any SafeUpdateSourceValidator
    private let manifestReconciler: any SafeUpdateManifestReconciler

    init(
        gate: InstallationTransactionGate = .shared,
        sourceValidator: any SafeUpdateSourceValidator = DefaultSafeUpdateSourceValidator(),
        manifestReconciler: any SafeUpdateManifestReconciler = LocalSafeUpdateManifestReconciler()
    ) {
        self.gate = gate
        self.sourceValidator = sourceValidator
        self.manifestReconciler = manifestReconciler
    }

    func run(
        request: SafeUpdateRequest,
        provider: any SafeUpdateArtifactProvider,
        transport: any SafeUpdateTransport,
        onProgress: (@Sendable (SafeUpdateProgress) -> Void)? = nil
    ) async -> SafeUpdateResult {
        let transactionID = UUID()

        guard request.deviceConnected else {
            return failure(.failedDeviceDisconnected, "The Garmin device is not connected. Nothing was changed.")
        }
        guard request.confirmed else {
            return failure(.blockedConfirmationRequired, "Explicit confirmation is required before replacing the installed map.")
        }
        guard request.currentItem.classification == .terentoManaged,
              request.currentObject.ownership == .managedByTerento else {
            return failure(.blockedNotManaged, "The installed map is not proven to be managed by Terento. It was left untouched.")
        }
        guard let selectedIdentity = request.selectedMap.identity,
              request.currentObject.identity == selectedIdentity,
              request.currentItem.provider == selectedIdentity.provider,
              request.currentItem.region == selectedIdentity.region else {
            return failure(.blockedAmbiguousMapIdentity, "The installed map does not match the selected catalog map. It was left untouched.")
        }
        guard request.currentItem.isInstalled,
              request.currentItem.installedMaps.count == 1,
              request.currentItem.installedMaps.first?.sourceFile == request.currentObject.file,
              request.currentObject.file.itemID != nil,
              request.currentObject.sha256?.count == 64 else {
            return failure(.blockedUnknownState, "The installed map does not have one complete exact identity record.")
        }
        guard let profile = request.profile else {
            return failure(.blockedUnsupportedDevice, "This device has no validated update profile.")
        }
        guard profile.matches(request.identity), profile.supportsMapWrite else {
            return failure(.blockedUnsupportedDevice, "This device is not enabled for the validated map update path.")
        }
        guard profile.targetDirectory == "/GARMIN" else {
            return failure(.blockedUnknownTarget, "The device profile does not provide the validated Garmin map target.")
        }

        switch request.comparison.status {
        case .updateAvailable:
            break
        case .upToDate, .notInstalled:
            return failure(.blockedNoUpdate, "There is no older Terento-managed map to update.")
        case .newerInstalled:
            return failure(.blockedNewerInstalled, "A newer map is already installed. Terento will not downgrade it.")
        case .unknown:
            return failure(.blockedUnknownState, "The installed map version could not be compared safely.")
        }

        do {
            try gate.acquire(transactionID: transactionID)
        } catch {
            return failure(.blockedTransactionAlreadyRunning, "Another map operation is already in progress.")
        }
        defer { gate.release(transactionID: transactionID) }

        emit(.validating, onProgress)
        guard let installedVersion = request.currentObject.version,
              installedVersion < request.selectedMap.version else {
            return failure(.blockedNoUpdate, "The installed version is not older than the selected catalog version.")
        }

        emit(.acquiring, onProgress)
        let artifact: SafeUpdateSourceArtifact
        do {
            artifact = try await provider.acquire(
                package: request.selectedMap,
                onProgress: onProgress
            )
        } catch {
            return failure(.failedAcquisition, "The selected map could not be acquired from its provider.")
        }

        do {
            try sourceValidator.validate(artifact: artifact, package: request.selectedMap)
        } catch {
            return failure(.failedSourceValidation, error.localizedDescription)
        }

        emit(.revalidating, onProgress)
        let current: SafeUpdateRemoteObject
        do {
            current = try transport.inspectCurrentObject(request.currentObject)
        } catch let error as SafeUpdateTransportError {
            return failure(status(for: error), error.localizedDescription)
        } catch {
            return failure(.failedDeviceDisconnected, "The Garmin device could not be revalidated before the update.")
        }

        guard matches(current, request.currentObject),
              current.version == installedVersion,
              current.ownership == .managedByTerento else {
            return failure(.blockedCurrentObjectChanged, "The installed map changed while the new version was being prepared. Nothing was changed.")
        }

        let freeSpace: UInt64
        do {
            freeSpace = try transport.readFreeSpace()
        } catch {
            return failure(.failedDeviceDisconnected, "Current device storage could not be read safely.")
        }
        let storagePlan = StoragePlanner().plan(
            currentFreeSpace: freeSpace,
            selectedMapSizes: [artifact.installSizeBytes]
        )
        guard storagePlan.isAllowed else {
            return failure(
                .blockedInsufficientSpace,
                "There is not enough free space to keep the old map while the new one is verified.",
                storagePlan: storagePlan
            )
        }

        emit(.backingUp, onProgress)
        let backup = ReadBackupAdapter(
            transport: transport,
            backupDirectory: request.backupDirectory
        ).backup(
            target: ManagedMapBackupTarget(
                item: request.currentItem,
                expectedSHA256ByItemID: [
                    current.file.itemID!: current.sha256!
                ]
            ),
            onProgress: { progress in
                onProgress?(SafeUpdateProgress(
                    state: .backingUp,
                    bytesCompleted: progress.bytesTransferred,
                    totalBytes: progress.totalBytes,
                    bytesPerSecond: progress.bytesPerSecond
                ))
            }
        )
        guard backup.isSuccess, let verifiedBackup = backup.files.first else {
            let status: SafeUpdateStatus = backup.status == .backupFailedDeviceDisconnected
                ? .failedDeviceDisconnected
                : .failedBackup
            return failure(status, "The existing map could not be backed up and verified. The old map remains installed.", storagePlan: storagePlan, backup: backup)
        }

        let targetFilename: String
        do {
            targetFilename = try TerentoManagedFilenameGenerator().versionedFilename(
                providerId: request.selectedMap.providerId,
                regionId: request.selectedMap.regionId,
                version: artifact.version
            )
        } catch {
            return failure(.failedWrite, "A safe versioned target filename could not be generated.", storagePlan: storagePlan, backup: backup)
        }
        let targetPath = "/GARMIN/\(targetFilename)"

        do {
            let occupied = try transport.rescanObjects().contains {
                $0.file.path == targetPath || $0.file.filename == targetFilename
            }
            guard !occupied else {
                return failure(.failedWrite, "The safe update target already exists. Nothing was overwritten.", storagePlan: storagePlan, backup: backup)
            }
        } catch {
            return failure(.failedDeviceDisconnected, "The Garmin device could not be scanned before the new map was written.", storagePlan: storagePlan, backup: backup)
        }

        emit(.writing, onProgress)
        let written: SafeUpdateRemoteObject
        let transferProgress: (@Sendable (TransferProgress) -> Void)?
        if let callback = onProgress {
            transferProgress = { progress in
                callback(SafeUpdateProgress(
                    state: .writing,
                    bytesCompleted: progress.bytesTransferred,
                    totalBytes: progress.totalBytes,
                    bytesPerSecond: progress.bytesPerSecond
                ))
            }
        } else {
            transferProgress = nil
        }
        do {
            written = try transport.writeTransactionObject(
                sourceURL: artifact.localIMGURL,
                targetPath: targetPath,
                onProgress: transferProgress
            )
        } catch let error as SafeUpdateTransportError {
            return failure(status(for: error), error.localizedDescription, storagePlan: storagePlan, backup: backup)
        } catch {
            return failure(.failedWrite, "The new map could not be written. The old map remains installed.", storagePlan: storagePlan, backup: backup)
        }

        guard written.file.path == targetPath,
              written.file.filename == targetFilename,
              written.file.itemID != nil else {
            let cleanupStatus = cleanup(written, transport: transport)
            return failure(cleanupStatus, "The write returned an unsafe object identity. The old map remains installed.", storagePlan: storagePlan, backup: backup, newObject: written)
        }

        emit(.verifying, onProgress)
        let verified: SafeUpdateRemoteObject
        do {
            verified = try transport.verifyTransactionObject(written, expected: artifact)
        } catch let error as SafeUpdateTransportError {
            let cleanupStatus = cleanup(written, transport: transport)
            return failure(
                cleanupStatus == .failedCleanup ? .failedCleanup : status(for: error),
                error.localizedDescription,
                storagePlan: storagePlan,
                backup: backup,
                newObject: written
            )
        } catch {
            let cleanupStatus = cleanup(written, transport: transport)
            return failure(
                cleanupStatus == .failedCleanup ? .failedCleanup : .failedWrite,
                "The new map could not be verified. The old map remains installed.",
                storagePlan: storagePlan,
                backup: backup,
                newObject: written
            )
        }

        guard verified.file.sizeBytes == artifact.installSizeBytes else {
            let cleanupStatus = cleanup(verified, transport: transport)
            return failure(cleanupStatus == .failedCleanup ? .failedCleanup : .failedSizeMismatch, "The new map size did not match the validated source.", storagePlan: storagePlan, backup: backup, newObject: verified)
        }
        guard normalized(verified.sha256) == normalized(artifact.sha256) else {
            let cleanupStatus = cleanup(verified, transport: transport)
            return failure(cleanupStatus == .failedCleanup ? .failedCleanup : .failedHashMismatch, "The new map hash did not match the validated source.", storagePlan: storagePlan, backup: backup, newObject: verified)
        }
        guard verified.identity == request.selectedMap.identity,
              verified.version == artifact.version,
              verified.ownership == .managedByTerento else {
            let cleanupStatus = cleanup(verified, transport: transport)
            return failure(cleanupStatus == .failedCleanup ? .failedCleanup : .failedMetadataMismatch, "The new map metadata did not match the selected map.", storagePlan: storagePlan, backup: backup, newObject: verified)
        }

        emit(.committing, onProgress)
        let filenameGenerator = TerentoManagedFilenameGenerator()
        let expectedOldVersion: MapVersion? = {
            guard let version = current.version,
                  let baseFilename = try? filenameGenerator.filename(
                    providerId: request.currentObject.identity.provider,
                    regionId: request.currentObject.identity.region
                  ) else {
                return nil
            }

            return current.file.filename == baseFilename ? nil : version
        }()
        let deleteTarget = SafeDeleteTarget(
            deviceKey: request.deviceKey,
            mapIdentity: request.currentObject.identity,
            ownership: request.currentObject.ownership,
            objectID: current.file.itemID!,
            expectedPath: current.file.path,
            expectedFilename: current.file.filename,
            expectedSizeBytes: current.file.sizeBytes,
            expectedSHA256: current.sha256!,
            backup: verifiedBackup,
            expectedVersion: expectedOldVersion
        )
        let deleteResult = SafeDeleteAdapter().delete(
            target: deleteTarget,
            confirmed: true,
            deviceConnected: request.deviceConnected,
            rescan: {
                try transport.rescanObjects().map(\.file)
            },
            transport: transport
        )
        guard deleteResult.isSuccess else {
            return failure(.failedCommit, "The new map is verified, but the previous map could not be removed. No success was reported.", storagePlan: storagePlan, backup: backup, newObject: verified)
        }

        emit(.postVerifying, onProgress)
        let finalObjects: [SafeUpdateRemoteObject]
        do {
            finalObjects = try transport.rescanObjects()
        } catch {
            return failure(.failedPostVerify, "The device could not be rescanned after the update.", storagePlan: storagePlan, backup: backup, newObject: verified, oldMapPreserved: false)
        }
        guard finalObjects.contains(where: { $0.file == verified.file }),
              !finalObjects.contains(where: {
                  $0.file.itemID == current.file.itemID || $0.file.path == current.file.path
              }) else {
            return failure(.failedPostVerify, "The final device state did not match the verified update.", storagePlan: storagePlan, backup: backup, newObject: verified, oldMapPreserved: false, finalObjects: finalObjects)
        }

        emit(.reconcilingManifest, onProgress)
        do {
            try manifestReconciler.reconcile(
                deviceKey: request.deviceKey,
                oldObject: current,
                newObject: verified,
                package: request.selectedMap,
                finalObjects: finalObjects
            )
        } catch {
            return failure(.failedManifestReconciliation, "The device update finished, but local ownership could not be reconciled safely.", storagePlan: storagePlan, backup: backup, newObject: verified, oldMapPreserved: false, finalObjects: finalObjects)
        }

        emit(.completed, onProgress)
        return SafeUpdateResult(
            status: .success,
            state: .completed,
            message: "The map was updated, verified, and recorded as managed by Terento.",
            storagePlan: storagePlan,
            backup: backup,
            newObject: verified,
            finalObjects: finalObjects,
            oldMapPreserved: false
        )
    }

    private func matches(_ lhs: SafeUpdateRemoteObject, _ rhs: SafeUpdateRemoteObject) -> Bool {
        lhs.file == rhs.file
            && lhs.identity == rhs.identity
            && lhs.ownership == rhs.ownership
            && normalized(lhs.sha256) == normalized(rhs.sha256)
    }

    private func cleanup(_ object: SafeUpdateRemoteObject, transport: any SafeUpdateTransport) -> SafeUpdateStatus {
        do {
            try transport.cleanupTransactionObject(object)
            return .failedWrite
        } catch {
            return .failedCleanup
        }
    }

    private func status(for error: SafeUpdateTransportError) -> SafeUpdateStatus {
        switch error {
        case .deviceDisconnected: return .failedDeviceDisconnected
        case .remoteMissing: return .failedRemoteMissing
        case .sizeMismatch: return .failedSizeMismatch
        case .hashMismatch: return .failedHashMismatch
        case .metadataMismatch: return .failedMetadataMismatch
        case .writeFailed, .operationFailed: return .failedWrite
        }
    }

    private func normalized(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    }

    private func emit(
        _ state: SafeUpdateState,
        _ callback: (@Sendable (SafeUpdateProgress) -> Void)?
    ) {
        callback?(SafeUpdateProgress(state: state, bytesCompleted: 0, totalBytes: 0, bytesPerSecond: 0))
    }

    private func failure(
        _ status: SafeUpdateStatus,
        _ message: String,
        storagePlan: StoragePlan? = nil,
        backup: ReadBackupResult? = nil,
        newObject: SafeUpdateRemoteObject? = nil,
        oldMapPreserved: Bool = true,
        finalObjects: [SafeUpdateRemoteObject] = []
    ) -> SafeUpdateResult {
        SafeUpdateResult(
            status: status,
            state: .failed,
            message: message,
            storagePlan: storagePlan,
            backup: backup,
            newObject: newObject,
            finalObjects: finalObjects,
            oldMapPreserved: oldMapPreserved
        )
    }
}

import CryptoKit
import Foundation

/// Outcomes for the only destructive lifecycle operation currently allowed.
enum SafeDeleteStatus: String, Equatable, Sendable {
    case success = "DELETE_SUCCESS"
    case failedDeviceDisconnected = "DELETE_FAILED_DEVICE_DISCONNECTED"
    case failedObjectNotFound = "DELETE_FAILED_OBJECT_NOT_FOUND"
    case blockedOwnership = "DELETE_BLOCKED_OWNERSHIP"
    case blockedIntegrityCheck = "DELETE_BLOCKED_INTEGRITY_CHECK"
    case blockedBackupRequired = "DELETE_BLOCKED_BACKUP_REQUIRED"
    case failedOperation = "DELETE_FAILED_OPERATION"
    case failedPostVerify = "DELETE_FAILED_POST_VERIFY"
    case failedManifestCleanup = "DELETE_FAILED_MANIFEST_CLEANUP"
    case blockedConfirmationRequired = "DELETE_BLOCKED_CONFIRMATION_REQUIRED"
}

enum SafeDeleteTransportError: LocalizedError, Equatable, Sendable {
    case deviceDisconnected(String)
    case objectNotFound
    case operationFailed(String)

    var errorDescription: String? {
        switch self {
        case .deviceDisconnected(let message):
            return message
        case .objectNotFound:
            return "The managed map object was not found on the Garmin device."
        case .operationFailed(let message):
            return message
        }
    }
}

/// Exact deletion authorization. Every field is supplied by a validated
/// manifest/inventory decision; a filename alone is never sufficient.
struct SafeDeleteTarget: Equatable, Sendable {
    let deviceKey: String
    let mapIdentity: MapIdentity
    let ownership: MapManagementState
    let objectID: UInt32
    let expectedPath: String
    let expectedFilename: String
    let expectedSizeBytes: UInt64
    let expectedSHA256: String
    let backup: VerifiedBackupFile?
    /// Set for a versioned map produced by Stage 5.3. Existing Stage 5.2
    /// base-filename targets leave this nil for source compatibility.
    let expectedVersion: MapVersion?

    init(
        deviceKey: String,
        mapIdentity: MapIdentity,
        ownership: MapManagementState,
        objectID: UInt32,
        expectedPath: String,
        expectedFilename: String,
        expectedSizeBytes: UInt64,
        expectedSHA256: String,
        backup: VerifiedBackupFile?,
        expectedVersion: MapVersion? = nil
    ) {
        self.deviceKey = deviceKey
        self.mapIdentity = mapIdentity
        self.ownership = ownership
        self.objectID = objectID
        self.expectedPath = expectedPath
        self.expectedFilename = expectedFilename
        self.expectedSizeBytes = expectedSizeBytes
        self.expectedSHA256 = expectedSHA256
        self.backup = backup
        self.expectedVersion = expectedVersion
    }

    var sourceFile: InstalledMapFile {
        InstalledMapFile(
            path: expectedPath,
            filename: expectedFilename,
            sizeBytes: expectedSizeBytes,
            itemID: objectID
        )
    }
}

struct SafeDeleteDeviceObject: Equatable, Sendable {
    let file: InstalledMapFile
    let sha256: String
}

/// Transport boundary for SafeDeleteAdapter. The inspect operation must be
/// read-only. The delete operation is the sole destructive operation exposed
/// by this boundary.
protocol SafeDeleteTransport: Sendable {
    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject
    func deleteExactObject(_ target: SafeDeleteTarget) throws
}

struct SafeDeleteResult: Equatable, Sendable {
    let mapIdentity: MapIdentity
    let status: SafeDeleteStatus
    let message: String

    var isSuccess: Bool {
        status == .success
    }
}

/// Isolated Stage 5.2 safety coordinator. It is deliberately not connected
/// to SwiftUI or MapEngine. A caller must provide explicit confirmation, a
/// live device check, a verified Stage 5.1 backup, and a post-delete rescan.
struct SafeDeleteAdapter: Sendable {
    func delete(
        target: SafeDeleteTarget,
        confirmed: Bool,
        deviceConnected: Bool,
        rescan: @escaping @Sendable () throws -> [InstalledMapFile],
        transport: any SafeDeleteTransport
    ) -> SafeDeleteResult {
        guard confirmed else {
            return result(
                target,
                status: .blockedConfirmationRequired,
                message: "Explicit confirmation is required before removing this map."
            )
        }

        guard deviceConnected else {
            return result(
                target,
                status: .failedDeviceDisconnected,
                message: "The Garmin device is not connected. Nothing was removed."
            )
        }

        guard isEligibleManagedTarget(target) else {
            return result(
                target,
                status: .blockedOwnership,
                message: "This map is not proven to be managed by Terento. It was left untouched."
            )
        }

        guard isValidIntegrityRecord(target) else {
            return result(
                target,
                status: .blockedIntegrityCheck,
                message: "The map identity or integrity record did not match exactly. Nothing was removed."
            )
        }

        guard let backup = target.backup else {
            return result(
                target,
                status: .blockedBackupRequired,
                message: "A verified local backup is required before this map can be removed."
            )
        }

        guard isVerifiedBackup(backup, for: target) else {
            return result(
                target,
                status: .blockedIntegrityCheck,
                message: "The local backup did not match the managed map. Nothing was removed."
            )
        }

        let current: SafeDeleteDeviceObject
        do {
            current = try transport.inspectExactObject(target)
        } catch let error as SafeDeleteTransportError {
            return result(target, status: status(for: error), message: message(for: error))
        } catch {
            return result(
                target,
                status: .failedOperation,
                message: "Terento could not validate the map before removal. Nothing was removed."
            )
        }

        guard matchesExpectedObject(current, target: target) else {
            return result(
                target,
                status: .blockedIntegrityCheck,
                message: "The map on the watch no longer matches the verified record. Nothing was removed."
            )
        }

        do {
            try transport.deleteExactObject(target)
        } catch let error as SafeDeleteTransportError {
            return result(target, status: status(for: error), message: message(for: error))
        } catch {
            return result(
                target,
                status: .failedOperation,
                message: "The map could not be removed. Nothing else was changed."
            )
        }

        do {
            let remaining = try rescan()
            let stillPresent = remaining.contains {
                $0.itemID == target.objectID || $0.path == target.expectedPath
            }
            guard !stillPresent else {
                return result(
                    target,
                    status: .failedPostVerify,
                    message: "Removal could not be verified after rescanning the Garmin device."
                )
            }
        } catch {
            return result(
                target,
                status: .failedPostVerify,
                message: "The Garmin device could not be rescanned after removal."
            )
        }

        return result(
            target,
            status: .success,
            message: "The Terento-managed map was removed and verified as absent."
        )
    }

    private func isEligibleManagedTarget(_ target: SafeDeleteTarget) -> Bool {
        guard target.ownership == .managedByTerento,
              target.expectedPath == "/GARMIN/\(target.expectedFilename)" else {
            return false
        }

        let generator = TerentoManagedFilenameGenerator()
        if let expectedVersion = target.expectedVersion {
            return generator.isVersioned(
                target.expectedFilename,
                providerId: target.mapIdentity.provider,
                regionId: target.mapIdentity.region,
                version: expectedVersion
            )
        }

        guard generator.isValid(target.expectedFilename),
              let generated = try? generator.filename(
                  providerId: target.mapIdentity.provider,
                  regionId: target.mapIdentity.region
              ) else {
            return false
        }

        return generated == target.expectedFilename
    }

    private func isValidIntegrityRecord(_ target: SafeDeleteTarget) -> Bool {
        guard target.objectID != 0,
              target.expectedSizeBytes > 0 else {
            return false
        }

        let hash = normalizedHash(target.expectedSHA256)
        return hash.count == 64
            && hash.allSatisfy { $0.isHexDigit }
    }

    private func isVerifiedBackup(
        _ backup: VerifiedBackupFile,
        for target: SafeDeleteTarget
    ) -> Bool {
        let source = backup.source
        guard source.itemID == target.objectID,
              source.path == target.expectedPath,
              source.filename == target.expectedFilename,
              source.sizeBytes == target.expectedSizeBytes,
              backup.sizeBytes == target.expectedSizeBytes,
              normalizedHash(backup.sha256) == normalizedHash(target.expectedSHA256),
              FileManager.default.fileExists(atPath: backup.localURL.path) else {
            return false
        }

        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: backup.localURL.path)
            guard let number = attributes[.size] as? NSNumber,
                  number.uint64Value == target.expectedSizeBytes else {
                return false
            }
            return try sha256(of: backup.localURL) == normalizedHash(target.expectedSHA256)
        } catch {
            return false
        }
    }

    private func matchesExpectedObject(
        _ object: SafeDeleteDeviceObject,
        target: SafeDeleteTarget
    ) -> Bool {
        object.file.itemID == target.objectID
            && object.file.path == target.expectedPath
            && object.file.filename == target.expectedFilename
            && object.file.sizeBytes == target.expectedSizeBytes
            && normalizedHash(object.sha256) == normalizedHash(target.expectedSHA256)
    }

    private func status(for error: SafeDeleteTransportError) -> SafeDeleteStatus {
        switch error {
        case .deviceDisconnected:
            return .failedDeviceDisconnected
        case .objectNotFound:
            return .failedObjectNotFound
        case .operationFailed:
            return .failedOperation
        }
    }

    private func message(for error: SafeDeleteTransportError) -> String {
        switch error {
        case .deviceDisconnected:
            return "The Garmin device was disconnected. Nothing else was changed."
        case .objectNotFound:
            return "The managed map was not found on the Garmin device. Nothing was removed."
        case .operationFailed:
            return "The map could not be validated or removed. Nothing else was changed."
        }
    }

    private func result(
        _ target: SafeDeleteTarget,
        status: SafeDeleteStatus,
        message: String
    ) -> SafeDeleteResult {
        SafeDeleteResult(mapIdentity: target.mapIdentity, status: status, message: message)
    }

    private func normalizedHash(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func sha256(of url: URL) throws -> String {
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

/// Lifecycle-facing façade kept separate from SwiftUI and MapEngine. Future
/// UI confirmation can call this façade without gaining direct MTP access.
struct MapLifecycleManager: Sendable {
    private let safeDeleteAdapter: SafeDeleteAdapter
    private let manifestCleanupStore: any TerentoManifestCleanupStore

    init(
        safeDeleteAdapter: SafeDeleteAdapter = SafeDeleteAdapter(),
        manifestCleanupStore: any TerentoManifestCleanupStore = LocalTerentoManifestStore()
    ) {
        self.safeDeleteAdapter = safeDeleteAdapter
        self.manifestCleanupStore = manifestCleanupStore
    }

    func delete(
        target: SafeDeleteTarget,
        confirmed: Bool,
        deviceConnected: Bool,
        rescan: @escaping @Sendable () throws -> [InstalledMapFile],
        transport: any SafeDeleteTransport
    ) -> SafeDeleteResult {
        let result = safeDeleteAdapter.delete(
            target: target,
            confirmed: confirmed,
            deviceConnected: deviceConnected,
            rescan: rescan,
            transport: transport
        )

        guard result.isSuccess else {
            return result
        }

        do {
            guard try manifestCleanupStore.remove(
                deviceKey: target.deviceKey,
                devicePath: target.expectedPath,
                filename: target.expectedFilename
            ) else {
                return SafeDeleteResult(
                    mapIdentity: target.mapIdentity,
                    status: .failedManifestCleanup,
                    message: "The map was removed from the Garmin device, but its local ownership record was not found. Do not retry blindly."
                )
            }
        } catch {
            return SafeDeleteResult(
                mapIdentity: target.mapIdentity,
                status: .failedManifestCleanup,
                message: "The map was removed from the Garmin device, but Terento could not update its local ownership record. Do not retry blindly."
            )
        }

        return result
    }
}

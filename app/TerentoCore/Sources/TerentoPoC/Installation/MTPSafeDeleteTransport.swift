import CryptoKit
import Foundation

/// Read-only inspection prepares local evidence; the authorized native delete
/// independently rechecks the exact content in its own mutation session.
private final class ExternalRemovalEvidence: @unchecked Sendable {
    private let lock = NSLock()
    private var entry: (target: SafeDeleteTarget, sha256: String)?

    func clear() {
        lock.lock()
        defer { lock.unlock() }
        entry = nil
    }

    func store(target: SafeDeleteTarget, sha256: String) {
        lock.lock()
        defer { lock.unlock() }
        entry = (target.resolvingObjectID(0), sha256)
    }

    func consume(target: SafeDeleteTarget) -> String? {
        lock.lock()
        defer { lock.unlock() }
        let evidence = entry
        entry = nil
        guard evidence?.target == target.resolvingObjectID(0) else { return nil }
        return evidence?.sha256
    }
}

struct ExternalMapSelectionEvidence: Sendable {
    let sha256: String
    let displayName: String
}

struct MTPSafeDeleteTransport: SafeDeleteTransport, Sendable {
    private let operationGate: MTPOperationGate
    private let lifecycleLease: MTPOperationLease?
    private let operationProfile: DeviceMapOperationProfile?
    private let externalEvidence = ExternalRemovalEvidence()
    private let mapTransport: MTPMapInstallationTransport

    init(
        operationProfile: DeviceMapOperationProfile? = nil,
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) {
        self.operationProfile = operationProfile
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
        self.mapTransport = MTPMapInstallationTransport(
            operationProfile: operationProfile, operationGate: operationGate,
            lifecycleLease: lifecycleLease, mutationPurpose: .removeManaged
        )
    }

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        try inspectExactObject(target, onProgress: nil)
    }

    func prepareExternalSelection(
        _ target: SafeDeleteTarget,
        onProgress: (@Sendable (TransferProgress) -> Void)? = nil
    ) throws -> ExternalMapSelectionEvidence {
        guard target.ownership == .detectedNotManaged else {
            throw SafeDeleteTransportError.operationFailed("Only external selection can be prepared.")
        }
        var displayName = target.expectedFilename
        let object = try inspect(target, onProgress: onProgress, preparingSelection: true) { metadata in
            if let name = metadata.name, !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                displayName = name
            }
        }
        return ExternalMapSelectionEvidence(sha256: object.sha256, displayName: displayName)
    }

    func inspectExactObject(
        _ target: SafeDeleteTarget,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> SafeDeleteDeviceObject {
        try inspect(target, onProgress: onProgress, preparingSelection: false)
    }

    private func inspect(
        _ target: SafeDeleteTarget,
        onProgress: (@Sendable (TransferProgress) -> Void)?,
        preparingSelection: Bool,
        onMetadata: ((GarminIMGMetadata) -> Void)? = nil
    ) throws -> SafeDeleteDeviceObject {
        externalEvidence.clear()
        guard let operationProfile,
              target.expectedPath == "/GARMIN/\(target.expectedFilename)" else {
            throw SafeDeleteTransportError.operationFailed("The map removal binding is unavailable.")
        }
        let files: [DeviceFile]
        do {
            files = try MTPTransport(
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ).readFileInventory()
        } catch let error as MTPTransportError {
            switch error {
            case .deviceAbsent:
                throw SafeDeleteTransportError.deviceDisconnected(error.localizedDescription)
            case .readFailed(let message), .contextual(let message, _):
                if isMissing(message) {
                    throw SafeDeleteTransportError.objectNotFound
                }
                if isBusy(message) {
                    throw SafeDeleteTransportError.deviceBusy(message)
                }
                if isDisconnected(message) {
                    throw SafeDeleteTransportError.deviceDisconnected(message)
                }
                throw SafeDeleteTransportError.operationFailed(message)
            }
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }

        let candidates = files.filter { $0.path == target.expectedPath }
        guard !candidates.isEmpty else {
            throw SafeDeleteTransportError.objectNotFound
        }

        guard candidates.count == 1,
              let object = candidates.first,
              object.path == target.expectedPath,
              object.filename == target.expectedFilename,
              object.sizeBytes == target.expectedSizeBytes,
              object.storageID == operationProfile.expectedStorageID,
              !object.isFolder else {
            throw SafeDeleteTransportError.operationFailed(
                "The exact managed map identity changed during validation."
            )
        }

        let liveFile = InstalledMapFile(
            path: object.path,
            filename: object.filename,
            sizeBytes: object.sizeBytes,
            itemID: object.itemID
        )

        // The manifest supplies managed content authority. Native deletion
        // still performs the full live content check before DeleteObject.
        if target.ownership == .managedByTerento {
            onProgress?(TransferProgress(
                bytesTransferred: target.expectedSizeBytes,
                totalBytes: target.expectedSizeBytes
            ))
            return SafeDeleteDeviceObject(
                file: liveFile,
                sha256: target.expectedSHA256,
                contentHashVerified: false
            )
        }

        guard target.ownership == .detectedNotManaged, target.allowsExternalRemoval else {
            throw SafeDeleteTransportError.operationFailed("The map is not authorized for external removal.")
        }
        let temporaryDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-remove-evidence-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(
            at: temporaryDirectory, withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        defer { try? FileManager.default.removeItem(at: temporaryDirectory) }
        let temporaryURL = temporaryDirectory.appendingPathComponent("map.img")
        let hash: String
        do {
            let transfer = try MTPMapReadAdapter(
                operationProfile: operationProfile,
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ).readExistingFile(file: liveFile, to: temporaryURL, onProgress: onProgress)
            guard transfer.sourcePath == target.expectedPath,
                  transfer.reportedSizeBytes == target.expectedSizeBytes else {
                throw SafeDeleteTransportError.operationFailed("The map changed during removal validation.")
            }
            let handle = try FileHandle(forReadingFrom: temporaryURL)
            defer { try? handle.close() }
            let prefix = try handle.read(upToCount: GarminIMGMetadataParser.prefixLength) ?? Data()
            guard let metadata = GarminIMGMetadataParser().parse(Array(prefix)) else {
                throw SafeDeleteTransportError.operationFailed(
                    "The selected third-party file is not a recognized Garmin map image. Nothing was removed."
                )
            }
            onMetadata?(metadata)
            try handle.seek(toOffset: 0)
            var hasher = SHA256()
            var count: UInt64 = 0
            while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty {
                count += UInt64(data.count)
                hasher.update(data: data)
            }
            guard count == target.expectedSizeBytes else {
                throw SafeDeleteTransportError.operationFailed("The map read did not match the expected size.")
            }
            hash = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        } catch let error as SafeDeleteTransportError {
            throw error
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }
        if !preparingSelection {
            guard NativeMutationLedger.Scope.validHash(target.expectedSHA256),
                  hash.caseInsensitiveCompare(target.expectedSHA256) == .orderedSame else {
                throw SafeDeleteTransportError.operationFailed(
                    "The selected map changed after confirmation was prepared. Nothing was removed."
                )
            }
            externalEvidence.store(target: target, sha256: hash)
        }

        return SafeDeleteDeviceObject(
            file: liveFile,
            sha256: hash,
            contentHashVerified: true
        )
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        do {
            let hash: String
            let purpose: MapMutationPurpose
            switch target.ownership {
            case .detectedNotManaged:
                guard target.allowsExternalRemoval,
                      let evidence = externalEvidence.consume(target: target) else {
                    throw SafeDeleteTransportError.operationFailed("Fresh map removal evidence is required.")
                }
                hash = evidence
                purpose = .removeExternal
            case .managedByTerento:
                hash = target.expectedSHA256
                purpose = .removeManaged
            default:
                throw SafeDeleteTransportError.operationFailed("The map removal is not authorized.")
            }
            guard target.expectedPath == "/GARMIN/\(target.expectedFilename)",
                  hash.count == 64, hash.allSatisfy({ $0.isASCII && $0.isHexDigit }),
                  hash != String(repeating: "0", count: 64) else {
                throw SafeDeleteTransportError.operationFailed("The map removal evidence is incomplete.")
            }
            try mapTransport.deleteAuthorized(
                targetFilename: target.expectedFilename,
                expectedItemID: target.objectID,
                expectedSizeBytes: target.expectedSizeBytes,
                expectedSHA256: hash,
                purpose: purpose
            )
        } catch let error as InstallationTransportError {
            if error.isConfirmedDeviceDisconnected {
                throw SafeDeleteTransportError.deviceDisconnected(error.localizedDescription)
            }
            switch error {
            case .deviceDisconnected(let message, _):
                throw SafeDeleteTransportError.deviceDisconnected(message)
            case .remoteFileMissing:
                throw SafeDeleteTransportError.objectNotFound
            default:
                let message = error.localizedDescription
                if isBusy(message) {
                    throw SafeDeleteTransportError.deviceBusy(message)
                }
                throw SafeDeleteTransportError.operationFailed(message)
            }
        } catch {
            let message = error.localizedDescription
            if isBusy(message) {
                throw SafeDeleteTransportError.deviceBusy(message)
            }
            throw SafeDeleteTransportError.operationFailed(message)
        }
    }

    private func isMissing(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("not found")
            || value.contains("missing")
            || value.contains("no such file")
    }

    private func isDisconnected(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("disconnected")
            || value.contains("not connected")
            || value.contains("no device")
    }

    private func isBusy(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("failed to open session")
            || value.contains("could not be opened")
            || value.contains("ptp_error_io")
            || value.contains("libusb")
            || value.contains("claim interface")
            || value.contains("claim_interface")
            || value.contains("resource busy")
            || value.contains("reset device")
            || value.contains("detach_kernel_driver")
            || value.contains("result too large")
    }

}

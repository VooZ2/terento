import CryptoKit
import Foundation

/// Live adapter for the Stage 5.3 transaction. The transaction owns the
/// safety order; this type only translates exact MTP reads/writes into the
/// domain protocol and never selects an object by filename alone.
struct MTPSafeUpdateTransport: SafeUpdateTransport, Sendable {
    private let operationGate: MTPOperationGate
    private let lifecycleLease: MTPOperationLease?
    private let deviceReader: MTPTransport
    private let mapTransport: MTPMapInstallationTransport
    private let operationProfile: DeviceMapOperationProfile

    init(
        operationProfile: DeviceMapOperationProfile,
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) {
        self.operationProfile = operationProfile
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
        self.deviceReader = MTPTransport(
            operationGate: operationGate,
            lifecycleLease: lifecycleLease
        )
        self.mapTransport = MTPMapInstallationTransport(
            operationProfile: operationProfile,
            operationGate: operationGate,
            lifecycleLease: lifecycleLease
        )
    }

    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        try MTPReadBackupAdapter(
            operationProfile: operationProfile,
            operationGate: operationGate,
            lifecycleLease: lifecycleLease
        ).readExistingFile(
            file: file,
            to: destinationURL,
            onProgress: onProgress
        )
    }

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        let object = try inspectCurrentObject(
            SafeUpdateRemoteObject(
                file: target.sourceFile,
                identity: target.mapIdentity,
                version: target.expectedVersion,
                ownership: target.ownership,
                sha256: target.expectedSHA256
            )
        )

        guard object.file.path == target.expectedPath,
              object.file.filename == target.expectedFilename,
              object.file.sizeBytes == target.expectedSizeBytes,
              MapIdentityMatcher.matches(
                  actual: object.identity,
                  expected: target.mapIdentity
              ),
              object.ownership == .managedByTerento,
              let hash = object.sha256 else {
            throw SafeDeleteTransportError.operationFailed(
                "The exact managed map identity could not be verified."
            )
        }

        return SafeDeleteDeviceObject(file: object.file, sha256: hash)
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        do {
            try mapTransport.deleteExact(
                targetFilename: target.expectedFilename,
                expectedItemID: target.objectID
            )
        } catch let error as InstallationTransportError {
            throw mapError(error)
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }
    }

    func inspectCurrentObject(_ expected: SafeUpdateRemoteObject) throws -> SafeUpdateRemoteObject {
        guard let itemID = expected.file.itemID, itemID != 0 else {
            throw SafeUpdateTransportError.operationFailed(
                "The installed map does not have an exact device object identity."
            )
        }

        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-update-inspect-\(UUID().uuidString).img")
        defer { try? FileManager.default.removeItem(at: temporaryURL) }

        do {
            let transfer = try readExistingFile(
                file: expected.file,
                to: temporaryURL,
                onProgress: nil
            )
            guard transfer.itemID == itemID,
                  transfer.sourcePath == expected.file.path,
                  transfer.reportedSizeBytes == expected.file.sizeBytes else {
                throw SafeUpdateTransportError.operationFailed(
                    "The installed map identity changed during validation."
                )
            }

            let metadata = try metadata(for: expected.file)
            guard let identity = MapIdentity(provider: metadata.provider, region: metadata.region) else {
                throw SafeUpdateTransportError.metadataMismatch
            }
            let hash = try sha256(of: temporaryURL)
            guard MapIdentityMatcher.matches(
                      actual: identity,
                      expected: expected.identity
                  ),
                  metadata.version == expected.version else {
                throw SafeUpdateTransportError.metadataMismatch
            }

            return SafeUpdateRemoteObject(
                file: expected.file,
                identity: identity,
                version: metadata.version,
                ownership: expected.ownership,
                sha256: hash
            )
        } catch let error as SafeUpdateTransportError {
            throw error
        } catch let error as MapLifecycleReadTransportError {
            throw readError(error)
        } catch {
            throw SafeUpdateTransportError.operationFailed(
                "The installed map could not be read for verification."
            )
        }
    }

    func writeTransactionObject(
        sourceURL: URL,
        targetPath: String,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> SafeUpdateRemoteObject {
        guard targetPath.hasPrefix("/GARMIN/"),
              targetPath.split(separator: "/").count == 2 else {
            throw SafeUpdateTransportError.operationFailed(
                "The update target is outside the validated Garmin map directory."
            )
        }

        let targetFilename = String(targetPath.dropFirst("/GARMIN/".count))
        guard TerentoManagedFilenameGenerator().isValid(targetFilename) else {
            throw SafeUpdateTransportError.operationFailed(
                "The update target filename is not a managed Terento filename."
            )
        }

        do {
            let written = try mapTransport.write(
                sourceURL: sourceURL,
                targetFilename: targetFilename,
                progress: onProgress ?? { _ in }
            )
            guard let parsed = parseManagedFilename(targetFilename) else {
                throw SafeUpdateTransportError.metadataMismatch
            }
            return SafeUpdateRemoteObject(
                file: InstalledMapFile(
                    path: targetPath,
                    filename: targetFilename,
                    sizeBytes: written.sizeBytes,
                    itemID: written.itemID
                ),
                identity: parsed.identity,
                version: parsed.version,
                ownership: .managedByTerento,
                sha256: nil
            )
        } catch let error as InstallationTransportError {
            throw mapError(error)
        } catch {
            throw SafeUpdateTransportError.writeFailed(error.localizedDescription)
        }
    }

    func verifyTransactionObject(
        _ object: SafeUpdateRemoteObject,
        expected: SafeUpdateSourceArtifact
    ) throws -> SafeUpdateRemoteObject {
        guard let expectedIdentity = MapIdentity(
            provider: expected.provider,
            region: expected.region
        ) else {
            throw SafeUpdateTransportError.metadataMismatch
        }

        let inspected = try inspectCurrentObject(
            SafeUpdateRemoteObject(
                file: object.file,
                identity: expectedIdentity,
                version: expected.version,
                ownership: .managedByTerento,
                sha256: nil
            )
        )

        guard inspected.file.sizeBytes == expected.installSizeBytes,
              inspected.sha256?.caseInsensitiveCompare(expected.sha256) == .orderedSame,
              MapIdentityMatcher.matches(
                  actual: inspected.identity,
                  expected: expectedIdentity
              ),
              inspected.version == expected.version else {
            throw SafeUpdateTransportError.metadataMismatch
        }

        return SafeUpdateRemoteObject(
            file: inspected.file,
            identity: inspected.identity,
            version: inspected.version,
            ownership: .managedByTerento,
            sha256: inspected.sha256
        )
    }

    func cleanupTransactionObject(_ object: SafeUpdateRemoteObject) throws {
        guard let itemID = object.file.itemID else {
            throw SafeUpdateTransportError.operationFailed(
                "The partial update object has no exact device identity."
            )
        }

        do {
            try mapTransport.deleteExact(
                targetFilename: object.file.filename,
                expectedItemID: itemID
            )
        } catch let error as InstallationTransportError {
            throw mapError(error)
        } catch {
            throw SafeUpdateTransportError.operationFailed(error.localizedDescription)
        }
    }

    func readFreeSpace() throws -> UInt64 {
        do {
            return try deviceReader.readSnapshot().freeSpace
        } catch {
            throw SafeUpdateTransportError.deviceDisconnected(
                "The Garmin device storage could not be read safely."
            )
        }
    }

    func rescanObjects() throws -> [SafeUpdateRemoteObject] {
        let files = try deviceReader.readFileInventory().filter {
            !$0.isFolder
                && $0.path.lowercased().hasPrefix("/garmin/")
                && $0.filename.lowercased().hasSuffix(".img")
        }

        let prefixes = try deviceReader.readFilePrefixes(
            for: files,
            maxLength: GarminIMGMetadataParser.prefixLength
        )

        return files.compactMap { file in
            let metadata = prefixes[file.itemID].flatMap {
                GarminIMGMetadataParser().parse($0, filename: file.filename)
            }
            guard let metadata,
                  let identity = MapIdentity(provider: metadata.provider, region: metadata.region) else {
                return nil
            }
            return SafeUpdateRemoteObject(
                file: InstalledMapFile(
                    path: file.path,
                    filename: file.filename,
                    sizeBytes: file.sizeBytes,
                    itemID: file.itemID
                ),
                identity: identity,
                version: metadata.version,
                ownership: .unknown,
                sha256: nil
            )
        }
    }

    private func metadata(for file: InstalledMapFile) throws -> GarminIMGMetadata {
        let mtpFile = DeviceFile(
            itemID: file.itemID ?? 0,
            parentID: 0,
            storageID: 0,
            path: file.path,
            filename: file.filename,
            sizeBytes: file.sizeBytes,
            isFolder: false
        )
        let prefix = try deviceReader.readFilePrefix(
            for: mtpFile,
            maxLength: GarminIMGMetadataParser.prefixLength
        )
        guard let metadata = GarminIMGMetadataParser().parse(
            prefix,
            filename: file.filename
        ) else {
            throw SafeUpdateTransportError.metadataMismatch
        }
        return metadata
    }

    private func parseManagedFilename(_ filename: String) -> (identity: MapIdentity, version: MapVersion?)? {
        let stem = filename.dropLast(".img".count)
        let components = stem.split(separator: "_").map(String.init)
        let version: MapVersion?
        let identityComponents: [String]
        if let last = components.last, let parsed = MapVersion(rawValue: last) {
            version = parsed
            identityComponents = Array(components.dropLast())
        } else {
            version = nil
            identityComponents = components
        }

        let provider = identityComponents.dropFirst().dropLast().joined(separator: "_")
        let region = identityComponents.last ?? "unknown"
        guard !provider.isEmpty,
              !region.isEmpty,
              let identity = MapIdentity(provider: provider, region: region) else {
            return nil
        }

        return (identity, version)
    }

    private func mapError(_ error: InstallationTransportError) -> SafeUpdateTransportError {
        switch error {
        case .deviceDisconnected(let message, _):
            return .deviceDisconnected(message)
        case .remoteFileMissing:
            return .remoteMissing
        case .targetAlreadyExists:
            return .writeFailed("The update target already exists. Nothing was overwritten.")
        case .objectIdentityMismatch:
            return .metadataMismatch
        case .unsupportedDevice:
            return .operationFailed("This device is not enabled for the validated update path.")
        case .liveIdentityMismatch:
            return .operationFailed("The connected Garmin device changed after the update was authorized.")
        case .operationFailed(let message, _):
            return .operationFailed(message)
        }
    }

    private func readError(_ error: MapLifecycleReadTransportError) -> SafeUpdateTransportError {
        switch error {
        case .deviceDisconnected(let message): return .deviceDisconnected(message)
        case .readFailed(let message): return .operationFailed(message)
        }
    }

    private func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty { break }
            hasher.update(data: data)
        }

        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

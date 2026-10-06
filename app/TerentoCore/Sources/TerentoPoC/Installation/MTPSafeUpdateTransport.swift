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
    private let bbbikeMetadata: BBBikeMapMetadata?

    init(
        operationProfile: DeviceMapOperationProfile,
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil,
        bbbikeMetadata: BBBikeMapMetadata? = nil
    ) {
        self.operationProfile = operationProfile
        self.bbbikeMetadata = bbbikeMetadata
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
        self.deviceReader = MTPTransport(
            operationGate: operationGate,
            lifecycleLease: lifecycleLease,
            operationProfile: operationProfile
        )
        self.mapTransport = MTPMapInstallationTransport(
            operationProfile: operationProfile,
            operationGate: operationGate,
            lifecycleLease: lifecycleLease,
            mutationPurpose: .updateNew
        )
    }

    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleReadTransfer {
        try MTPMapReadAdapter(
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
        // Inventory inspection is preliminary. The authorized native delete
        // checks the old manifest content proof (sampled proof, or the full
        // hash without one) again in the live mutation session.
        return try MTPSafeDeleteTransport(
            operationProfile: operationProfile,
            operationGate: operationGate,
            lifecycleLease: lifecycleLease
        ).inspectExactObject(target)
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        try deleteExactObject(target, onProgress: nil)
    }

    func deleteExactObject(_ target: SafeDeleteTarget,
                           onProgress: (@Sendable (TransferProgress) -> Void)?) throws {
        do {
            try mapTransport.deleteAuthorized(
                targetFilename: target.expectedFilename,
                expectedItemID: target.objectID,
                expectedSizeBytes: target.expectedSizeBytes,
                expectedSHA256: target.expectedSHA256,
                purpose: .updateOld,
                removalProof: target.removalProof,
                onProgress: onProgress
            )
        } catch let error as InstallationTransportError {
            throw mapError(error)
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }
    }

    func inspectCurrentObject(_ expected: SafeUpdateRemoteObject) throws -> SafeUpdateRemoteObject {
        try inspectCurrentObject(expected, onProgress: nil)
    }

    func inspectCurrentObject(_ expected: SafeUpdateRemoteObject,
                              onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateRemoteObject {
        let method = SafeUpdateCurrentMapCheck.method(for: expected)
        FinishingTrace.event("update_current_check", "method=\(method.traceName) "
            + "bytes=\(method.contentBytes(fileSizeBytes: expected.file.sizeBytes))")
        return try mapReadErrors("The installed map could not be read for verification.") {
            let current = try SafeUpdateContentVerifier(reader: contentReader)
                .inspectCurrent(expected, onProgress: onProgress)
            if let expectedHash = expected.sha256 {
                try mapTransport.bindUpdateOldTarget(
                    filename: expected.file.filename,
                    size: expected.file.sizeBytes, sha256: expectedHash
                )
            }
            return current
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
        try verifyTransactionObject(object, expected: expected, onProgress: nil)
    }

    func verifyTransactionObject(_ object: SafeUpdateRemoteObject, expected: SafeUpdateSourceArtifact,
                                 onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateRemoteObject {
        let regions = SampledReadBackPlan.offsets(fileSizeBytes: expected.installSizeBytes,
                                                  sourceSHA256: expected.sha256).count
        FinishingTrace.event("update_new_check", "method=sampled regions=\(regions) bytes="
            + "\(UInt64(regions) * min(UInt64(SampledReadBackPlan.sampleLength), expected.installSizeBytes))")
        let verified = try mapReadErrors("The new map could not be read back for verification.") {
            try SafeUpdateContentVerifier(reader: contentReader).verifyNew(object, expected: expected,
                                                                          onProgress: onProgress)
        }
        try mapTransport.markUpdateVerified(
            filename: verified.file.filename, size: verified.file.sizeBytes,
            sha256: verified.sha256 ?? ""
        )
        return verified
    }

    private var contentReader: LiveSafeUpdateContentReader {
        LiveSafeUpdateContentReader(transport: self)
    }

    /// The error mapping of the content checks: device read failures keep
    /// their disconnect classification, anything unexpected blocks.
    private func mapReadErrors<T>(_ fallback: String, _ body: () throws -> T) throws -> T {
        do {
            return try body()
        } catch let error as SafeUpdateTransportError {
            throw error
        } catch let error as MapLifecycleReadTransportError {
            throw readError(error)
        } catch let error as InstallationTransportError {
            throw mapError(error)
        } catch {
            throw SafeUpdateTransportError.operationFailed(fallback)
        }
    }

    fileprivate func readFullContent(_ file: InstalledMapFile,
                                     onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateFullContentRead {
        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-update-inspect-\(UUID().uuidString).img")
        defer { try? FileManager.default.removeItem(at: temporaryURL) }
        let transfer = try readExistingFile(
            file: file,
            to: temporaryURL,
            onProgress: { onProgress?($0.fractionCompleted * 0.86) }
        )
        let hash = try sha256(of: temporaryURL, onProgress: { onProgress?(0.86 + 0.14 * $0) })
        return SafeUpdateFullContentRead(itemID: transfer.itemID, sourcePath: transfer.sourcePath,
                                         reportedSizeBytes: transfer.reportedSizeBytes, sha256: hash)
    }

    fileprivate func readRecordedProof(_ file: InstalledMapFile, sha256: String, proof: ManagedRemovalProof,
                                       onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateRecordedProofRead {
        try MTPMapReadAdapter(
            operationProfile: operationProfile,
            operationGate: operationGate,
            lifecycleLease: lifecycleLease
        ).readRecordedProof(file: file, sha256: sha256, proof: proof,
                            onProgress: { onProgress?($0.fractionCompleted) })
    }

    fileprivate func readMetadata(_ file: InstalledMapFile) throws -> GarminIMGMetadata {
        try metadata(for: file)
    }

    fileprivate func readInstallSamples(_ file: InstalledMapFile, artifact: SafeUpdateSourceArtifact,
                                        offsets: [UInt64], sampleLength: UInt32,
                                        onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateSampledReadBack {
        // Exactly the fresh-install read-back: the same bounded settle after
        // the write session closes, then a fresh read-only session that
        // compares the regions with the validated local artifact.
        Thread.sleep(forTimeInterval: 3.0)
        let readBack = try mapTransport.readBack(
            sourceURL: artifact.localIMGURL,
            targetFilename: file.filename,
            expectedItemID: file.itemID ?? 0,
            targetPath: file.path,
            expectedSizeBytes: artifact.installSizeBytes,
            sampleOffsets: offsets,
            sampleLength: sampleLength,
            progress: { onProgress?($0.fractionCompleted) }
        )
        return SafeUpdateSampledReadBack(itemID: readBack.itemID, reportedSizeBytes: readBack.reportedSizeBytes,
                                         sampledBytes: readBack.sampledBytes, sampleCount: readBack.sampleCount,
                                         matchedSampleCount: readBack.matchedSampleCount)
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

    func readProtectedInventory() throws -> SafeUpdateInventorySnapshot {
        // The native session checks the immutable physical profile before
        // enumerating; a separate identity snapshot would permit substitution.
        // Map scope: storage roots plus the GARMIN subtree, or the full walk
        // when the native session cannot prove a single root.
        let read = try deviceReader.readMapScopeInventory(operationProfile: operationProfile)
        let files = read.files
        FinishingTrace.event("update_inventory_metrics",
            "scope=\(read.scope.rawValue) fallback=\(read.fallback.rawValue) objects=\(files.count)")
        do {
            let target = try GarminMapTarget.resolve(in: files)
            guard target.root.storageID == operationProfile.expectedStorageID else {
                throw MapTargetResolutionError.profileMismatch
            }
        } catch let reason as MapTargetResolutionError {
            FinishingTrace.event("target_resolution", "target_reason=\(reason.rawValue)")
            throw reason
        }
        return SafeUpdateInventorySnapshot(storageID: operationProfile.expectedStorageID, files: files,
                                           scope: read.scope, fallback: read.fallback)
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
            let metadata = prefixes[file.stableIdentity].flatMap {
                contextualMetadata($0, filename: file.filename) ?? GarminIMGMetadataParser().parse($0, filename: file.filename)
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
            storageID: operationProfile.expectedStorageID,
            path: file.path,
            filename: file.filename,
            sizeBytes: file.sizeBytes,
            isFolder: false
        )
        let prefix = try deviceReader.readFilePrefix(
            for: mtpFile,
            maxLength: GarminIMGMetadataParser.prefixLength
        )
        guard let metadata = contextualMetadata(prefix, filename: file.filename) ?? GarminIMGMetadataParser().parse(
            prefix,
            filename: file.filename
        ) else {
            throw SafeUpdateTransportError.metadataMismatch
        }
        return metadata
    }

    private func contextualMetadata(_ prefix: [UInt8], filename: String) -> GarminIMGMetadata? {
        guard let context = bbbikeMetadata, let version = BBBikeIMGMetadata.version(prefix),
              TerentoManagedFilenameGenerator().matchesIdentity(filename, providerId: "bbbike",
                  regionId: context.canonicalRegion, version: version) else { return nil }
        // The update transaction still checks exact object coordinates and the
        // complete recorded SHA-256. Context alone never grants ownership.
        return BBBikeIMGMetadata.metadata(prefix, context: context, version: version)
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

        if identityComponents.prefix(2) == ["terento", "bbbike"],
           let identity = MapIdentity(provider: "bbbike", region: identityComponents.dropFirst(2).joined(separator: "_")) {
            return (identity, version)
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
        case .contextual(_, let message, _, _):
            return error.isConfirmedDeviceDisconnected
                ? .deviceDisconnected(message)
                : .operationFailed(message)
        }
    }

    private func readError(_ error: MapLifecycleReadTransportError) -> SafeUpdateTransportError {
        switch error {
        case .deviceDisconnected(let message): return .deviceDisconnected(message)
        case .readFailed(let message): return .operationFailed(message)
        }
    }

    private func sha256(of url: URL, onProgress: (@Sendable (Double) -> Void)? = nil) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        let size = (try url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        var completed = 0
        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty { break }
            hasher.update(data: data)
            completed += data.count
            if size > 0 { onProgress?(min(1, Double(completed) / Double(size))) }
        }

        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

/// The live device reads behind `SafeUpdateContentVerifier`.
private struct LiveSafeUpdateContentReader: SafeUpdateContentReader {
    let transport: MTPSafeUpdateTransport

    func readFullContent(_ file: InstalledMapFile,
                         onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateFullContentRead {
        try transport.readFullContent(file, onProgress: onProgress)
    }

    func readRecordedProof(_ file: InstalledMapFile, sha256: String, proof: ManagedRemovalProof,
                           onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateRecordedProofRead {
        try transport.readRecordedProof(file, sha256: sha256, proof: proof, onProgress: onProgress)
    }

    func readMetadata(_ file: InstalledMapFile) throws -> GarminIMGMetadata {
        try transport.readMetadata(file)
    }

    func readInstallSamples(_ file: InstalledMapFile, artifact: SafeUpdateSourceArtifact,
                            offsets: [UInt64], sampleLength: UInt32,
                            onProgress: (@Sendable (Double) -> Void)?) throws -> SafeUpdateSampledReadBack {
        try transport.readInstallSamples(file, artifact: artifact, offsets: offsets,
                                         sampleLength: sampleLength, onProgress: onProgress)
    }
}

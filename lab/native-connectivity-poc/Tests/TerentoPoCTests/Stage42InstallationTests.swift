import CryptoKit
import Foundation

private let gigabyte: UInt64 = 1024 * 1024 * 1024
private let targetPath = "/GARMIN/terento_freizeitkarte_lva.img"

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

private final class AllowArtifactValidator: MapInstallationArtifactValidator, @unchecked Sendable {
    var shouldAllow = true

    func validate(artifact: ValidatedMapArtifact, package: MapPackage) throws {
        if !shouldAllow {
            throw Stage42ArtifactValidationError.notExactValidatedArtifact
        }
    }
}

private final class MockManifestStore: TerentoManifestStore, @unchecked Sendable {
    var entries: [TerentoManifestEntry] = []
    var shouldFail = false

    func record(_ entry: TerentoManifestEntry) throws {
        if shouldFail {
            throw TerentoManifestStoreError.writeFailed
        }
        entries.append(entry)
    }
}

private final class MockFailedInstallRecoveryStore: TerentoFailedInstallRecoveryStore, @unchecked Sendable {
    var records: [TerentoFailedInstallRecoveryRecord] = []
    var shouldFail = false

    func read(deviceKey: String) throws -> [TerentoFailedInstallRecoveryRecord] {
        if shouldFail {
            throw TerentoManifestStoreError.unreadableRecovery
        }
        return records.filter { $0.deviceKey == deviceKey }
    }

    func record(_ record: TerentoFailedInstallRecoveryRecord) throws {
        if shouldFail {
            throw TerentoManifestStoreError.recoveryWriteFailed
        }
        records.removeAll {
            $0.deviceKey == record.deviceKey
                && $0.devicePath == record.devicePath
                && $0.filename == record.filename
        }
        records.append(record)
    }

    func remove(deviceKey: String, devicePath: String, filename: String) throws -> Bool {
        if shouldFail {
            throw TerentoManifestStoreError.recoveryCleanupFailed
        }
        let count = records.count
        records.removeAll {
            $0.deviceKey == deviceKey
                && $0.devicePath == devicePath
                && $0.filename == filename
        }
        return records.count != count
    }
}

private final class MockDeviceReader: InstallationDeviceReader, @unchecked Sendable {
    var files: [DeviceFile]
    private let initialFiles: [DeviceFile]
    private var inventoryReadCount = 0
    var snapshot: DeviceSnapshot
    var shouldFail = false

    init(
        files: [DeviceFile],
        initialFiles: [DeviceFile]? = nil,
        freeSpace: UInt64 = 14 * gigabyte
    ) {
        self.files = files
        self.initialFiles = initialFiles ?? files
        self.snapshot = DeviceSnapshot(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            deviceVersion: "2243",
            vendorID: 0x091e,
            productID: 0x51b8,
            storages: [
                StorageInfo(
                    id: 1,
                    description: "Garmin storage",
                    volumeIdentifier: "GARMIN",
                    maximumCapacity: 31 * gigabyte,
                    freeSpace: freeSpace
                )
            ]
        )
    }

    func readFileInventory() throws -> [DeviceFile] {
        if shouldFail {
            throw InstallationTransportError.deviceDisconnected(
                "device disconnected",
                createdItemID: nil
            )
        }
        defer { inventoryReadCount += 1 }
        return inventoryReadCount == 0 ? initialFiles : files
    }

    func readSnapshot() throws -> DeviceSnapshot {
        if shouldFail {
            throw InstallationTransportError.deviceDisconnected(
                "device disconnected",
                createdItemID: nil
            )
        }
        return snapshot
    }
}

private final class MockTransport: MapInstallationTransport, @unchecked Sendable {
    enum ReadBackMode {
        case success
        case missing
        case sizeMismatch
        case hashMismatch
    }

    let remoteData: Data
    var readBackMode: ReadBackMode = .success
    var writeError: InstallationTransportError?
    var writeCount = 0
    var readBackCount = 0
    var deleteCount = 0
    var deletedFilename: String?
    var deletedItemID: UInt32?
    var deleteError: InstallationTransportError?

    init(remoteData: Data) {
        self.remoteData = remoteData
    }

    func write(
        sourceURL: URL,
        targetFilename: String,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPWrittenMapObject {
        writeCount += 1
        if let writeError {
            throw writeError
        }
        progress(TransferProgress(bytesTransferred: 0, totalBytes: UInt64(remoteData.count)))
        progress(TransferProgress(bytesTransferred: UInt64(remoteData.count), totalBytes: UInt64(remoteData.count)))
        return MTPWrittenMapObject(itemID: 77, sizeBytes: UInt64(remoteData.count))
    }

    func readBack(
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String
    ) throws -> MTPReadBackMapObject {
        readBackCount += 1
        if readBackMode == .missing {
            throw InstallationTransportError.remoteFileMissing
        }

        let data: Data
        let reportedSize: UInt64
        switch readBackMode {
        case .success:
            data = remoteData
            reportedSize = UInt64(remoteData.count)
        case .sizeMismatch:
            data = remoteData
            reportedSize = UInt64(remoteData.count + 1)
        case .hashMismatch:
            var bytes = Array(remoteData)
            bytes[bytes.startIndex] ^= 0x01
            data = Data(bytes)
            reportedSize = UInt64(data.count)
        case .missing:
            fatalError("handled above")
        }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage42-mock-readback-(UUID().uuidString).img")
        try data.write(to: url, options: .atomic)
        return MTPReadBackMapObject(
            itemID: expectedItemID,
            targetPath: targetPath,
            reportedSizeBytes: reportedSize,
            localURL: url
        )
    }

    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws {
        deleteCount += 1
        deletedFilename = targetFilename
        deletedItemID = expectedItemID
        if let deleteError {
            throw deleteError
        }
    }
}

@main
struct Stage42InstallationTests {
    static func main() throws {
        var passed = 0
        passed += testValidNewInstall()
        passed += testExistingLatviaBlocksNewInstall()
        passed += testInsufficientSpaceBlocksWrite()
        passed += testUnknownProfileBlocksWrite()
        passed += testTargetPolicyRejectsUnsupportedProviderBeforeTransport()
        passed += testTargetPolicyAcceptsAnotherFreizeitkarteRegion()
        passed += testCoordinatorUsesBusyTransactionGate()
        passed += testNonValidatedArtifactBlocksWrite()
        passed += testConfirmationIsRequiredBeforeWrite()
        passed += testWriteFailureIsNotSuccess()
        passed += testDisconnectDuringWriteFails()
        passed += testPartialObjectIsCleanedAfterWriteDisconnect()
        passed += testMissingRemoteIsFailure()
        passed += testSizeMismatchIsFailure()
        passed += testHashMismatchIsFailure()
        passed += testMatchingSizeAndHashVerifies()
        passed += testCleanupTargetsOnlyNewLatviaObject()
        passed += testLithuaniaIsNeverCleanupTarget()
        passed += testSuccessMarksMapManaged()
        passed += testSuccessRequiresHashVerification()
        passed += testSuccessClearsFailedInstallRecoveryRecord()
        passed += testFailedVerificationPreservesRecoveryRecordWhenCleanupFails()

        print("PASS: \(passed) Stage 4.2 installation tests")
    }

    private static func testValidNewInstall() -> Int {
        let harness = makeHarness()
        let result = harness.run()
        return expect(
            result.status == .installVerified
                && result.transaction.state == .completed
                && result.verification?.isVerified == true
                && harness.transport.writeCount == 1
                && harness.transport.deleteCount == 0,
            "valid new install reaches INSTALL_VERIFIED"
        )
    }

    private static func testExistingLatviaBlocksNewInstall() -> Int {
        let harness = makeHarness(installedLatvia: true)
        let result = harness.run()
        return expect(
            result.status == .blockedExistingMapConflict
                && result.failure == .existingMapConflict
                && harness.transport.writeCount == 0,
            "existing LVA blocks the Stage 4.2 new-install path"
        )
    }

    private static func testInsufficientSpaceBlocksWrite() -> Int {
        let harness = makeHarness(
            availableStorage: gigabyte + 4096 - 1
        )
        let result = harness.run()
        return expect(
            result.status == .blockedInsufficientSpace
                && harness.transport.writeCount == 0,
            "insufficient storage blocks SendObject"
        )
    }

    private static func testUnknownProfileBlocksWrite() -> Int {
        let harness = makeHarness(profile: nil)
        let result = harness.run()
        return expect(
            result.status == .blockedUnsupportedDevice
                && harness.transport.writeCount == 0,
            "unknown install profile blocks SendObject"
        )
    }

    private static func testTargetPolicyRejectsUnsupportedProviderBeforeTransport() -> Int {
        let harness = makeHarness()
        let unsupportedPackage = MapPackage(
            id: "opentopomap-ltu",
            providerId: "opentopomap",
            regionId: "LTU",
            name: "OpenTopoMap Lithuania",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 100,
            sourceURL: nil,
            releaseDate: nil,
            identifier: "LTU+"
        )

        do {
            try Stage42TargetPolicy().validate(
                package: unsupportedPackage,
                artifact: harness.request.artifact!,
                profile: harness.request.profile
            )
            return expect(false, "unsupported provider is rejected before transport")
        } catch Stage42TargetPolicyError.unsupportedPackage {
            return expect(
                harness.transport.writeCount == 0,
                "unsupported provider is rejected before transport"
            )
        } catch {
            return expect(false, "unsupported provider is rejected before transport")
        }
    }

    private static func testTargetPolicyAcceptsAnotherFreizeitkarteRegion() -> Int {
        let data = Harness.makeIMG(region: "LTU")
        let package = Harness.makePackage(
            size: UInt64(data.count),
            regionID: "LTU",
            name: "Lithuania"
        )
        let artifact = Harness.makeArtifact(package: package, data: data)

        do {
            try Stage42TargetPolicy().validate(
                package: package,
                artifact: artifact,
                profile: DeviceInstallProfileRegistry.local.profiles.first
            )
            return expect(true, "another validated Freizeitkarte region is accepted")
        } catch {
            return expect(false, "another validated Freizeitkarte region is accepted")
        }
    }

    private static func testCoordinatorUsesBusyTransactionGate() -> Int {
        let harness = makeHarness()
        let gate = InstallationTransactionGate()
        let reservation = UUID()

        do {
            try gate.acquire(transactionID: reservation)
        } catch {
            return expect(false, "coordinator respects a busy transaction gate")
        }
        defer { gate.release(transactionID: reservation) }

        let result = harness.run(transactionGate: gate)
        return expect(
            result.failure == .transactionAlreadyRunning
                && harness.transport.writeCount == 0,
            "coordinator respects a busy transaction gate"
        )
    }

    private static func testNonValidatedArtifactBlocksWrite() -> Int {
        let harness = makeHarness(noArtifact: true)
        let result = harness.run()
        return expect(
            result.status == .blockedSourceArtifact
                && harness.transport.writeCount == 0,
            "missing ValidatedMapArtifact blocks the write"
        )
    }

   private static func testConfirmationIsRequiredBeforeWrite() -> Int {
        let harness = makeHarness(userConfirmed: false)
        let result = harness.run()
        return expect(
            result.status == .confirmationRequired
            && harness.transport.writeCount == 0
            && result.transaction.state == .validating,
            "missing explicit confirmation performs no device write"
        )
    }

    private static func testWriteFailureIsNotSuccess() -> Int {
        let harness = makeHarness()
        harness.transport.writeError = .operationFailed("write failed", createdItemID: nil)
        let result = harness.run()
        return expect(
            result.status == .failed
                && result.failure == .writeFailed
                && result.transaction.state == .failed
                && harness.transport.readBackCount == 0,
            "write failure does not report success"
        )
    }

    private static func testDisconnectDuringWriteFails() -> Int {
        let harness = makeHarness()
        harness.transport.writeError = .deviceDisconnected(
            "device disconnected",
            createdItemID: nil
        )
        let result = harness.run()
        return expect(
            result.failure == .deviceDisconnected
                && result.status == .failed
                && harness.transport.writeCount == 1,
            "disconnect during write returns INSTALL_FAILED_DEVICE_DISCONNECTED"
        )
    }

    private static func testPartialObjectIsCleanedAfterWriteDisconnect() -> Int {
        let harness = makeHarness()
        harness.transport.writeError = .deviceDisconnected(
            "device disconnected after object creation",
            createdItemID: 77
        )
        let result = harness.run()
        return expect(
            result.failure == .deviceDisconnected
                && harness.transport.deletedFilename == "terento_freizeitkarte_lva.img"
                && harness.transport.deletedItemID == 77,
            "partial object identity is retained for exact cleanup"
        )
    }

    private static func testMissingRemoteIsFailure() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .missing
        let result = harness.run()
        return expect(
            result.failure == .remoteFileMissing
                && harness.transport.deleteCount == 1
                && !result.isSuccess,
            "missing remote object is a failure and cleans only the new object"
        )
    }

    private static func testSizeMismatchIsFailure() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .sizeMismatch
        let result = harness.run()
        return expect(
            result.failure == .sizeMismatch
                && result.verification?.status == .sizeMismatch
                && harness.transport.deleteCount == 1,
            "remote size mismatch is a failure"
        )
    }

    private static func testHashMismatchIsFailure() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        let result = harness.run()
        return expect(
            result.failure == .hashMismatch
                && result.verification?.status == .hashMismatch
                && harness.transport.deleteCount == 1,
            "remote hash mismatch is a failure"
        )
    }

    private static func testMatchingSizeAndHashVerifies() -> Int {
        let harness = makeHarness()
        let result = harness.run()
        return expect(
            result.verification?.status == .verified
                && result.diagnostics.remoteObjectExists
                && result.diagnostics.remoteSizeBytes == UInt64(harness.remoteData.count),
            "matching remote size and full hash verify the transfer"
        )
    }

    private static func testCleanupTargetsOnlyNewLatviaObject() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        _ = harness.run()
        return expect(
            harness.transport.deletedFilename == "terento_freizeitkarte_lva.img"
                && harness.transport.deletedItemID == 77,
            "cleanup can target only the exact new Latvia object"
        )
    }

    private static func testLithuaniaIsNeverCleanupTarget() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .missing
        _ = harness.run()
        return expect(
            harness.transport.deletedFilename != "freizeitkarte-lithuania.img"
                && harness.transport.deletedFilename != "terento_freizeitkarte_ltu.img",
            "Lithuania is never a cleanup or replacement target"
        )
    }

    private static func testSuccessMarksMapManaged() -> Int {
        let harness = makeHarness()
        let result = harness.run()
        return expect(
            result.installedMap?.managementState == .managedByTerento
                && harness.manifest.entries.first?.regionId == "LVA"
                && harness.manifest.entries.first?.filename == "terento_freizeitkarte_lva.img",
            "verified LVA is marked TERENTO_MANAGED in the local manifest"
        )
    }

    private static func testSuccessRequiresHashVerification() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        let result = harness.run()
        return expect(
            result.transaction.state == .failed
                && result.transaction.state != .completed
                && result.status != .installVerified,
            "installation cannot complete before full hash verification"
        )
    }

    private static func testSuccessClearsFailedInstallRecoveryRecord() -> Int {
        let harness = makeHarness()
        let result = harness.run()
        return expect(
            result.status == .installVerified
                && harness.recovery.records.isEmpty,
            "successful install clears the failed-install recovery record"
        )
    }

    private static func testFailedVerificationPreservesRecoveryRecordWhenCleanupFails() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .missing
        harness.transport.deleteError = .operationFailed(
            "cleanup failed",
            createdItemID: nil
        )
        let result = harness.run()
        return expect(
            result.status == .failed
                && result.failure == .cleanupFailed
                && harness.recovery.records.count == 1,
            "failed verification preserves recovery when exact cleanup fails"
        )
    }

    private final class Harness {
        let transport: MockTransport
        let manifest: MockManifestStore
        let recovery: MockFailedInstallRecoveryStore
        let request: MapInstallationRequest
        let remoteData: Data

        init(
            installedLatvia: Bool = false,
            availableStorage: UInt64 = 15 * gigabyte,
            profile: DeviceInstallProfile? = DeviceInstallProfileRegistry.local.profiles.first,
            artifact: ValidatedMapArtifact? = nil,
            noArtifact: Bool = false,
            userConfirmed: Bool = true
        ) {
            remoteData = Self.makeIMG()
            transport = MockTransport(remoteData: remoteData)
            manifest = MockManifestStore()
            recovery = MockFailedInstallRecoveryStore()

            let package = Self.makePackage(size: UInt64(remoteData.count))
            let installed = installedLatvia ? Self.makeLatviaMap(size: UInt64(remoteData.count)) : nil
            let before = Self.makeBeforeFiles(installedLatvia: installedLatvia)
            let resolvedArtifact = artifact ?? Self.makeArtifact(
                package: package,
                data: remoteData
            )
            request = MapInstallationRequest(
                identity: Self.identity(),
                selectedMap: package,
                comparison: MapComparison(
                    providerName: "Freizeitkarte",
                    regionName: "Latvia",
                    catalogMap: package,
                    installedMap: installed,
                    status: installed == nil ? .notInstalled : .upToDate
                ),
                installedMaps: installed.map { [$0] } ?? [],
                inspectedFiles: installed.map { [$0.sourceFile] } ?? [],
                beforeDeviceFiles: before,
                availableStorage: availableStorage,
                profile: profile,
                artifact: noArtifact ? nil : resolvedArtifact,
                userConfirmed: userConfirmed
            )
        }

        func run(
            transactionGate: InstallationTransactionGate = InstallationTransactionGate()
        ) -> MapInstallationResult {
            let reader = MockDeviceReader(
                files: Self.makeAfterFiles(),
                initialFiles: request.beforeDeviceFiles
            )
            let validator = AllowArtifactValidator()
            return MapInstallationCoordinator(
                artifactValidator: validator,
                transport: transport,
                deviceReader: reader,
                manifestStore: manifest,
                recoveryStore: recovery,
                transactionGate: transactionGate,
                now: { Date(timeIntervalSince1970: 0) }
            ).run(request)
        }

        private static func identity() -> DeviceIdentity {
            DeviceIdentity(
                manufacturer: "Garmin",
                model: "fenix 8 - 47mm",
                family: "fēnix",
                variant: "47mm",
                usbVendorId: 0x091e,
                usbProductId: 0x51b8,
                firmware: "2243",
                storageCapacity: 31 * gigabyte,
                freeSpace: 15 * gigabyte
            )
        }

        fileprivate static func makePackage(
            size: UInt64,
            regionID: String = "LVA",
            name: String = "Latvia"
        ) -> MapPackage {
            MapPackage(
                id: "freizeitkarte-\(regionID.lowercased())",
                providerId: "freizeitkarte",
                regionId: regionID,
                name: name,
                version: MapVersion(year: 2026, month: 5)!,
                sizeBytes: 100,
                sourceURL: URL(string: "https://provider.example/\(regionID).zip"),
                releaseDate: "2026-05-03",
                identifier: "\(regionID)+",
                downloadSizeBytes: 100,
                installSizeBytes: size
            )
        }

        fileprivate static func makeArtifact(package: MapPackage, data: Data) -> ValidatedMapArtifact {
            let sourceURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("terento-stage42-mock-source-(UUID().uuidString).img")
            try! data.write(to: sourceURL, options: .atomic)
            let digest = SHA256.hash(data: data)
                .map { String(format: "%02x", $0) }
                .joined()
            let targetFilename = try! TerentoManagedFilenameGenerator().filename(
                providerId: package.providerId,
                regionId: package.regionId
            )
            return ValidatedMapArtifact(
                provider: "Freizeitkarte",
                region: package.regionId,
                canonicalRegion: package.name,
                rawRelease: "Release 26.05",
                version: package.version,
                localIMGURL: sourceURL,
                installSizeBytes: UInt64(data.count),
                sha256: digest,
                sourcePackageURL: package.sourceURL!,
                catalogPackageID: package.id,
                targetFilename: targetFilename,
                downloadSizeBytes: 100,
                catalogDownloadSizeBytes: 100,
                downloadSizeMatchesCatalog: true,
                packageFormat: .rawIMG
            )
        }

        fileprivate static func makeIMG(region: String = "LVA") -> Data {
            var bytes = [UInt8](repeating: 0, count: 4096)
            write("DSKIMG", at: 0x10, into: &bytes)
            write("GARMIN", at: 0x41, into: &bytes)
            write("Freizeitkarte_\(region)+", at: 0x100, into: &bytes)
            write("Release 26.05", at: 0x200, into: &bytes)
            return Data(bytes)
        }

        private static func write(_ value: String, at offset: Int, into bytes: inout [UInt8]) {
            for (index, byte) in value.utf8.enumerated() where offset + index < bytes.count {
                bytes[offset + index] = byte
            }
        }

        private static func makeBeforeFiles(installedLatvia: Bool) -> [DeviceFile] {
            var files = [
                DeviceFile(
                    itemID: 1,
                    parentID: 0,
                    storageID: 1,
                    path: "/GARMIN/freizeitkarte-lithuania.img",
                    filename: "freizeitkarte-lithuania.img",
                    sizeBytes: 344_000_000,
                    isFolder: false
                ),
                DeviceFile(
                    itemID: 2,
                    parentID: 0,
                    storageID: 1,
                    path: "/GARMIN/gmapbmap.img",
                    filename: "gmapbmap.img",
                    sizeBytes: 1_000_000,
                    isFolder: false
                )
            ]
            if installedLatvia {
                files.append(
                    DeviceFile(
                        itemID: 3,
                        parentID: 0,
                        storageID: 1,
                        path: "/GARMIN/freizeitkarte-latvia.img",
                        filename: "freizeitkarte-latvia.img",
                        sizeBytes: 4096,
                        isFolder: false
                    )
                )
            }
            return files
        }

        private static func makeAfterFiles() -> [DeviceFile] {
            makeBeforeFiles(installedLatvia: false) + [
                DeviceFile(
                    itemID: 77,
                    parentID: 0,
                    storageID: 1,
                    path: targetPath,
                    filename: "terento_freizeitkarte_lva.img",
                    sizeBytes: 4096,
                    isFolder: false
                )
            ]
        }

        private static func makeLatviaMap(size: UInt64) -> InstalledMap {
            InstalledMap(
                name: "Freizeitkarte LVA",
                provider: "Freizeitkarte",
                region: "LVA",
                family: "Freizeitkarte_LVA+",
                rawVersion: "Release 26.05",
                version: MapVersion(year: 2026, month: 5),
                identifier: "LVA+",
                productId: nil,
                familyId: nil,
                sizeBytes: size,
                sourceFile: InstalledMapFile(
                    path: "/GARMIN/freizeitkarte-latvia.img",
                    filename: "freizeitkarte-latvia.img",
                    sizeBytes: size
                ),
                metadataStatus: .parsed,
                managementState: .detectedNotManaged
            )
        }
    }

    private static func makeHarness(
        installedLatvia: Bool = false,
        availableStorage: UInt64 = 15 * gigabyte,
       profile: DeviceInstallProfile? = DeviceInstallProfileRegistry.local.profiles.first,
       artifact: ValidatedMapArtifact? = nil,
        noArtifact: Bool = false,
        userConfirmed: Bool = true
   ) -> Harness {
        Harness(
            installedLatvia: installedLatvia,
            availableStorage: availableStorage,
           profile: profile,
           artifact: artifact,
            noArtifact: noArtifact,
            userConfirmed: userConfirmed
       )
    }

    private static func expect(_ condition: Bool, _ description: String) -> Int {
        if condition {
            print("PASS: \(description)")
            return 1
        }
        print("FAIL: \(description)")
        return 0
    }
}

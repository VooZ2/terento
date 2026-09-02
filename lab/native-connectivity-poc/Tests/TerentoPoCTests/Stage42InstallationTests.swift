import CryptoKit
import Foundation

private let gigabyte: UInt64 = 1024 * 1024 * 1024
private let targetPath = "/GARMIN/terento_freizeitkarte_fra.img"

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
    var renumberExistingObjectIDs = false
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
        let inventory = inventoryReadCount == 0 ? initialFiles : files
        guard renumberExistingObjectIDs, inventoryReadCount > 0 else {
            return inventory
        }

        return inventory.map { file in
            guard file.path != targetPath else { return file }
            return DeviceFile(
                itemID: file.itemID + 1000,
                parentID: file.parentID,
                storageID: file.storageID,
                path: file.path,
                filename: file.filename,
                sizeBytes: file.sizeBytes,
                isFolder: file.isFolder
            )
        }
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
    var deletedSizeBytes: UInt64?
    var readBackItemID: UInt32 = 77
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
        sourceURL: URL,
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String,
        expectedSizeBytes: UInt64,
        sampleOffsets: [UInt64],
        sampleLength: UInt32,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPReadBackMapObject {
        readBackCount += 1
        if readBackMode == .missing {
            throw InstallationTransportError.remoteFileMissing
        }

        let reportedSize: UInt64
        let matchedSampleCount: Int
        switch readBackMode {
        case .success:
            reportedSize = UInt64(remoteData.count)
            matchedSampleCount = sampleOffsets.count
        case .sizeMismatch:
            reportedSize = UInt64(remoteData.count + 1)
            matchedSampleCount = sampleOffsets.count
        case .hashMismatch:
            reportedSize = UInt64(remoteData.count)
            matchedSampleCount = max(0, sampleOffsets.count - 1)
        case .missing:
            fatalError("handled above")
        }
        let sampledBytes = UInt64(sampleOffsets.count) * UInt64(sampleLength)
        progress(TransferProgress(bytesTransferred: 0, totalBytes: sampledBytes))
        progress(TransferProgress(bytesTransferred: sampledBytes, totalBytes: sampledBytes))
        return MTPReadBackMapObject(
            itemID: readBackItemID,
            targetPath: targetPath,
            reportedSizeBytes: reportedSize,
            sampledBytes: sampledBytes,
            sampleCount: sampleOffsets.count,
            matchedSampleCount: matchedSampleCount
        )
    }

    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws {
        try deleteExact(
            targetFilename: targetFilename,
            expectedItemID: expectedItemID,
            expectedSizeBytes: nil
        )
    }

    func deleteExact(
        targetFilename: String,
        expectedItemID: UInt32,
        expectedSizeBytes: UInt64?
    ) throws {
        deleteCount += 1
        deletedFilename = targetFilename
        deletedItemID = expectedItemID
        deletedSizeBytes = expectedSizeBytes
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
        passed += testExistingFranceBlocksNewInstall()
        passed += testInsufficientSpaceBlocksWrite()
        passed += testUnknownProfileBlocksWrite()
        passed += testTargetPolicyRejectsUnsupportedProviderBeforeTransport()
        passed += testTargetPolicyAcceptsAnotherFreizeitkarteRegion()
        passed += testTargetPolicyAcceptsOpenTopoMapProvider()
        passed += testTargetPolicyAcceptsCurrentOpenTopoMapCatalogIdentity()
        passed += testArtifactValidatorAcceptsOpenTopoMapProvider()
        passed += testTargetPolicyAcceptsMapCapableBetaProfile()
        passed += testMapCapableNonLabPIDCompletesGenericLifecycle()
        passed += testMissingStableWatchIdentityBlocksBeforeMutation()
        passed += testTargetPolicyRejectsBetaProfileWithoutGarminRoot()
        passed += testCoordinatorUsesBusyTransactionGate()
        passed += testNonValidatedArtifactBlocksWrite()
        passed += testConfirmationIsRequiredBeforeWrite()
        passed += testWriteFailureIsNotSuccess()
        passed += testDisconnectDuringWriteFails()
        passed += testPartialObjectIsCleanedAfterWriteDisconnect()
        passed += testMissingRemoteIsFailure()
        passed += testSizeMismatchIsFailure()
        passed += testSampleMismatchIsFailure()
        passed += testMatchingSizeAndSamplesVerify()
        passed += testObjectIDMayChangeAcrossMTPReadSessions()
        passed += testExistingObjectIDsMayBeReenumeratedAfterWrite()
        passed += testCleanupTargetsOnlyNewFranceObject()
        passed += testGermanyIsNeverCleanupTarget()
        passed += testSuccessMarksMapManaged()
        passed += testSuccessRequiresSampledVerification()
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
            "valid new install reaches INSTALL_VERIFIED_SAMPLED_READBACK_V1"
        )
    }

    private static func testExistingFranceBlocksNewInstall() -> Int {
        let harness = makeHarness(installedFrance: true)
        let result = harness.run()
        return expect(
            result.status == .blockedExistingMapConflict
                && result.failure == .existingMapConflict
                && harness.transport.writeCount == 0,
            "existing FRA blocks the Stage 4.2 new-install path"
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
            id: "opentopomap-deu",
            providerId: "opentopomap",
            regionId: "DEU",
            name: "OpenTopoMap Germany",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 100,
            sourceURL: nil,
            releaseDate: nil,
            identifier: "DEU+"
        )

        do {
            try Stage42TargetPolicy().validate(
                package: unsupportedPackage,
                artifact: harness.request.artifact!,
                profile: harness.request.profile,
                identity: harness.request.identity,
                deviceFiles: harness.request.beforeDeviceFiles
            )
            return expect(false, "unknown provider is rejected before transport")
        } catch Stage42TargetPolicyError.unsupportedPackage {
            return expect(
                harness.transport.writeCount == 0,
                "unknown provider is rejected before transport"
            )
        } catch {
            return expect(false, "unknown provider is rejected before transport")
        }
    }

    private static func testTargetPolicyAcceptsAnotherFreizeitkarteRegion() -> Int {
        let data = Harness.makeIMG(region: "DEU")
        let package = Harness.makePackage(
            size: UInt64(data.count),
            regionID: "DEU",
            name: "Germany"
        )
        let artifact = Harness.makeArtifact(package: package, data: data)
        let harness = makeHarness()

        do {
            try Stage42TargetPolicy().validate(
                package: package,
                artifact: artifact,
                profile: DeviceInstallProfileRegistry.local.profiles.first,
                identity: harness.request.identity,
                deviceFiles: harness.request.beforeDeviceFiles
            )
            return expect(true, "another validated Freizeitkarte region is accepted")
        } catch {
            return expect(false, "another validated Freizeitkarte region is accepted")
        }
    }

    private static func testTargetPolicyAcceptsOpenTopoMapProvider() -> Int {
        let data = Harness.makeIMG(region: "LTU")
        let package = Harness.makePackage(
            size: UInt64(data.count),
            regionID: "LTU",
            name: "Lithuania",
            providerID: "opentopomap",
            packageID: "opentopomap-ltu"
        )
        let artifact = Harness.makeArtifact(
            package: package,
            data: data,
            provider: "OpenTopoMap",
            packageFormat: .zip
        )
        let harness = makeHarness()

        do {
            try Stage42TargetPolicy().validate(
                package: package,
                artifact: artifact,
                profile: DeviceInstallProfileRegistry.local.profiles.first,
                identity: harness.request.identity,
                deviceFiles: harness.request.beforeDeviceFiles
            )
            return expect(true, "validated OpenTopoMap provider passes the final write policy")
        } catch {
            return expect(false, "validated OpenTopoMap provider passes the final write policy")
        }
    }

    private static func testTargetPolicyAcceptsCurrentOpenTopoMapCatalogIdentity() -> Int {
        let data = Harness.makeIMG(region: "LTU")
        let package = MapPackage(
            id: "opentopomap-lithuania",
            providerId: "opentopomap",
            regionId: "LITHUANIA",
            name: "OpenTopoMap Lithuania",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: UInt64(data.count),
            sourceURL: URL(string: "https://garmin.opentopomap.org/europe/lithuania/otm-lithuania.zip"),
            releaseDate: "2026-05-25",
            identifier: "lithuania",
            downloadSizeBytes: 100,
            installSizeBytes: UInt64(data.count),
            providerRegionId: "lithuania",
            canonicalRegionId: "LITHUANIA"
        )
        let baseArtifact = Harness.makeArtifact(
            package: package,
            data: data,
            provider: "OpenTopoMap",
            packageFormat: .zip
        )
        let artifact = ValidatedMapArtifact(
            provider: baseArtifact.provider,
            region: "LTU",
            canonicalRegion: baseArtifact.canonicalRegion,
            rawRelease: baseArtifact.rawRelease,
            version: baseArtifact.version,
            localIMGURL: baseArtifact.localIMGURL,
            installSizeBytes: baseArtifact.installSizeBytes,
            sha256: baseArtifact.sha256,
            sourcePackageURL: baseArtifact.sourcePackageURL,
            catalogPackageID: baseArtifact.catalogPackageID,
            targetFilename: baseArtifact.targetFilename,
            downloadSizeBytes: baseArtifact.downloadSizeBytes,
            catalogDownloadSizeBytes: baseArtifact.catalogDownloadSizeBytes,
            downloadSizeMatchesCatalog: baseArtifact.downloadSizeMatchesCatalog,
            packageFormat: baseArtifact.packageFormat
        )
        let harness = makeHarness()

        do {
            try Stage42TargetPolicy().validate(
                package: package,
                artifact: artifact,
                profile: DeviceInstallProfileRegistry.local.profiles.first,
                identity: harness.request.identity,
                deviceFiles: harness.request.beforeDeviceFiles
            )
            return expect(
                true,
                "current OpenTopoMap catalog identity survives the final write policy"
            )
        } catch {
            return expect(
                false,
                "current OpenTopoMap catalog identity survives the final write policy"
            )
        }
    }

    private static func testArtifactValidatorAcceptsOpenTopoMapProvider() -> Int {
        let data = Harness.makeIMG(region: "LTU")
        let package = Harness.makePackage(
            size: UInt64(data.count),
            regionID: "LTU",
            name: "Lithuania",
            providerID: "opentopomap",
            packageID: "opentopomap-ltu"
        )
        let artifact = Harness.makeArtifact(
            package: package,
            data: data,
            provider: "OpenTopoMap",
            packageFormat: .zip
        )

        do {
            try Stage42ArtifactValidator().validate(artifact: artifact, package: package)
            return expect(true, "provider-neutral artifact validator accepts OpenTopoMap")
        } catch {
            return expect(false, "provider-neutral artifact validator accepts OpenTopoMap")
        }
    }

    private static func testTargetPolicyAcceptsMapCapableBetaProfile() -> Int {
        let data = Harness.makeIMG(region: "DEU")
        let package = Harness.makePackage(
            size: UInt64(data.count),
            regionID: "DEU",
            name: "Germany"
        )
        let artifact = Harness.makeArtifact(package: package, data: data)
        let identity = betaIdentity()
        let files = [betaGarminRoot()]
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: files
        )

        do {
            try Stage42TargetPolicy().validate(
                package: package,
                artifact: artifact,
                profile: profile,
                identity: identity,
                deviceFiles: files
            )
            return expect(true, "map-capable beta profile passes the final write policy")
        } catch {
            return expect(false, "map-capable beta profile passes the final write policy")
        }
    }

    private static func testTargetPolicyRejectsBetaProfileWithoutGarminRoot() -> Int {
        let data = Harness.makeIMG(region: "DEU")
        let package = Harness.makePackage(
            size: UInt64(data.count),
            regionID: "DEU",
            name: "Germany"
        )
        let artifact = Harness.makeArtifact(package: package, data: data)
        let identity = betaIdentity()
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: [betaGarminRoot()]
        )

        do {
            try Stage42TargetPolicy().validate(
                package: package,
                artifact: artifact,
                profile: profile,
                identity: identity,
                deviceFiles: []
            )
            return expect(false, "missing /GARMIN is rejected again at final write policy")
        } catch Stage42TargetPolicyError.unsupportedDeviceProfile {
            return expect(true, "missing /GARMIN is rejected again at final write policy")
        } catch {
            return expect(false, "missing /GARMIN is rejected again at final write policy")
        }
    }

    private static func testMapCapableNonLabPIDCompletesGenericLifecycle() -> Int {
        let identity = betaIdentity()
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: Harness.makeBeforeFiles(installedFrance: false)
        )
        let harness = Harness(profile: profile, identity: identity)
        let result = harness.run()

        return expect(
            result.status == .installVerified
                && harness.transport.writeCount == 1
                && harness.transport.readBackCount == 1
                && harness.manifest.entries.count == 1,
            "non-0x51b8 map-capable fixture completes the generic install lifecycle"
        )
    }

    private static func testMissingStableWatchIdentityBlocksBeforeMutation() -> Int {
        let identity = DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - 51mm",
            family: "fēnix",
            variant: "51mm",
            usbVendorId: 0x091e,
            usbProductId: 0x7777,
            firmware: "2244",
            storageCapacity: 31 * gigabyte,
            freeSpace: 16 * gigabyte
        )
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: Harness.makeBeforeFiles(installedFrance: false)
        )
        let harness = Harness(profile: profile, identity: identity)
        let result = harness.run()

        return expect(
            result.status == .blockedUnsupportedDevice
                && result.failure == .stableWatchIdentityUnavailable
                && harness.transport.writeCount == 0
                && harness.manifest.entries.isEmpty,
            "missing stable watch identity is rechecked before mutation"
        )
    }

    private static func betaIdentity() -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - 51mm",
            family: "fēnix",
            variant: "51mm",
            usbVendorId: 0x091e,
            usbProductId: 0x7777,
            firmware: "2244",
            storageCapacity: 31 * gigabyte,
            freeSpace: 16 * gigabyte,
            localHardwareIdentifier: "UNIT-ID-PRO-51",
            localIdentityResolution: .garminUnitID
        )
    }

    private static func betaGarminRoot() -> DeviceFile {
        DeviceFile(
            itemID: 9,
            parentID: 0,
            storageID: 1,
            path: "/GARMIN",
            filename: "GARMIN",
            sizeBytes: 0,
            isFolder: true
        )
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
                && harness.transport.deletedFilename == "terento_freizeitkarte_fra.img"
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
                && result.diagnostics.remoteObjectExists
                && result.diagnostics.remoteSizeBytes == UInt64(harness.remoteData.count)
                && !result.isSuccess,
            "read-back failure retains written-object diagnostics and cleans only the new object"
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

    private static func testSampleMismatchIsFailure() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        let result = harness.run()
        return expect(
            result.failure == .hashMismatch
                && result.verification?.status == .hashMismatch
                && harness.transport.deleteCount == 1,
            "sampled read-back mismatch is a failure"
        )
    }

    private static func testMatchingSizeAndSamplesVerify() -> Int {
        let harness = makeHarness()
        let result = harness.run()
        return expect(
            result.verification?.status == .verifiedSampledReadBack
                && result.verification?.mode == .sampledReadBack
                && result.verification?.sampleCount == result.verification?.matchedSampleCount
                && result.diagnostics.remoteObjectExists
                && result.diagnostics.remoteSizeBytes == UInt64(harness.remoteData.count),
            "matching remote size and sampled read-back verify the transfer"
        )
    }

    private static func testCleanupTargetsOnlyNewFranceObject() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        _ = harness.run()
        return expect(
            harness.transport.deletedFilename == "terento_freizeitkarte_fra.img"
                && harness.transport.deletedItemID == 77
                && harness.transport.deletedSizeBytes == UInt64(harness.remoteData.count),
            "cleanup can target only the exact new France object and size"
        )
    }

    private static func testObjectIDMayChangeAcrossMTPReadSessions() -> Int {
        let harness = makeHarness()
        harness.transport.readBackItemID = 99
        let result = harness.run()
        return expect(
            result.status == .installVerified
                && harness.manifest.entries.first?.filename == "terento_freizeitkarte_fra.img",
            "map verification does not require a volatile MTP object ID to remain unchanged"
        )
    }

    private static func testExistingObjectIDsMayBeReenumeratedAfterWrite() -> Int {
        let harness = makeHarness()
        harness.renumberExistingObjectIDs = true
        let result = harness.run()
        return expect(
            result.status == .installVerified
                && result.diagnostics.existingFilesProtectionPassed
                && result.diagnostics.unrelatedFilesProtectionPassed,
            "re-enumerated existing MTP object IDs do not make a multi-map install fail"
        )
    }

    private static func testGermanyIsNeverCleanupTarget() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .missing
        _ = harness.run()
        return expect(
            harness.transport.deletedFilename != "freizeitkarte-germany.img"
                && harness.transport.deletedFilename != "terento_freizeitkarte_deu.img",
            "Germany is never a cleanup or replacement target"
        )
    }

    private static func testSuccessMarksMapManaged() -> Int {
        let harness = makeHarness()
        let result = harness.run()
        return expect(
            result.installedMap?.managementState == .managedByTerento
                && harness.manifest.entries.first?.regionId == "FRA"
                && harness.manifest.entries.first?.filename == "terento_freizeitkarte_fra.img",
            "verified FRA is marked TERENTO_MANAGED in the local manifest"
        )
    }

    private static func testSuccessRequiresSampledVerification() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        let result = harness.run()
        return expect(
            result.transaction.state == .failed
                && result.transaction.state != .completed
                && result.status != .installVerified,
            "installation cannot complete before sampled read-back verification"
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
        var renumberExistingObjectIDs = false

        init(
            installedFrance: Bool = false,
            availableStorage: UInt64 = 15 * gigabyte,
            profile: DeviceInstallProfile? = DeviceInstallProfileRegistry.local.profiles.first,
            identity: DeviceIdentity? = nil,
            artifact: ValidatedMapArtifact? = nil,
            noArtifact: Bool = false,
            userConfirmed: Bool = true
        ) {
            remoteData = Self.makeIMG()
            transport = MockTransport(remoteData: remoteData)
            manifest = MockManifestStore()
            recovery = MockFailedInstallRecoveryStore()

            let package = Self.makePackage(size: UInt64(remoteData.count))
            let installed = installedFrance ? Self.makeFranceMap(size: UInt64(remoteData.count)) : nil
            let before = Self.makeBeforeFiles(installedFrance: installedFrance)
            let resolvedIdentity = identity ?? Self.identity()
            let resolvedArtifact = artifact ?? Self.makeArtifact(
                package: package,
                data: remoteData
            )
            request = MapInstallationRequest(
                identity: resolvedIdentity,
                selectedMap: package,
                comparison: MapComparison(
                    providerName: "Freizeitkarte",
                    regionName: "France",
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
            reader.renumberExistingObjectIDs = renumberExistingObjectIDs
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
                freeSpace: 15 * gigabyte,
                localHardwareIdentifier: "MTP-SERIAL-FENIX-47"
            )
        }

        fileprivate static func makePackage(
            size: UInt64,
            regionID: String = "FRA",
            name: String = "France",
            providerID: String = "freizeitkarte",
            packageID: String? = nil
        ) -> MapPackage {
            MapPackage(
                id: packageID ?? "\(providerID)-\(regionID.lowercased())",
                providerId: providerID,
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

        fileprivate static func makeArtifact(
            package: MapPackage,
            data: Data,
            provider: String? = nil,
            packageFormat: MapPackageFormat = .rawIMG
        ) -> ValidatedMapArtifact {
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
                provider: provider ?? package.providerId,
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
                packageFormat: packageFormat
            )
        }

        fileprivate static func makeIMG(region: String = "FRA") -> Data {
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

        fileprivate static func makeBeforeFiles(installedFrance: Bool) -> [DeviceFile] {
            var files = [
                DeviceFile(
                    itemID: 9,
                    parentID: 0,
                    storageID: 1,
                    path: "/GARMIN",
                    filename: "GARMIN",
                    sizeBytes: 0,
                    isFolder: true
                ),
                DeviceFile(
                    itemID: 1,
                    parentID: 0,
                    storageID: 1,
                    path: "/GARMIN/freizeitkarte-germany.img",
                    filename: "freizeitkarte-germany.img",
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
            if installedFrance {
                files.append(
                    DeviceFile(
                        itemID: 3,
                        parentID: 0,
                        storageID: 1,
                        path: "/GARMIN/freizeitkarte-france.img",
                        filename: "freizeitkarte-france.img",
                        sizeBytes: 4096,
                        isFolder: false
                    )
                )
            }
            return files
        }

        private static func makeAfterFiles() -> [DeviceFile] {
            makeBeforeFiles(installedFrance: false) + [
                DeviceFile(
                    itemID: 77,
                    parentID: 0,
                    storageID: 1,
                    path: targetPath,
                    filename: "terento_freizeitkarte_fra.img",
                    sizeBytes: 4096,
                    isFolder: false
                )
            ]
        }

        private static func makeFranceMap(size: UInt64) -> InstalledMap {
            InstalledMap(
                name: "Freizeitkarte FRA",
                provider: "Freizeitkarte",
                region: "FRA",
                family: "Freizeitkarte_FRA+",
                rawVersion: "Release 26.05",
                version: MapVersion(year: 2026, month: 5),
                identifier: "FRA+",
                productId: nil,
                familyId: nil,
                sizeBytes: size,
                sourceFile: InstalledMapFile(
                    path: "/GARMIN/freizeitkarte-france.img",
                    filename: "freizeitkarte-france.img",
                    sizeBytes: size
                ),
                metadataStatus: .parsed,
                managementState: .detectedNotManaged
            )
        }
    }

    private static func makeHarness(
        installedFrance: Bool = false,
        availableStorage: UInt64 = 15 * gigabyte,
       profile: DeviceInstallProfile? = DeviceInstallProfileRegistry.local.profiles.first,
       artifact: ValidatedMapArtifact? = nil,
        noArtifact: Bool = false,
        userConfirmed: Bool = true
   ) -> Harness {
        Harness(
            installedFrance: installedFrance,
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

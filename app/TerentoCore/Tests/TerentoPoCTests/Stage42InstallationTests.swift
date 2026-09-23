import CryptoKit
import Foundation

private final class DiagnosticRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var lines: [String] = []
    func record(_ event: String, _ details: String) { lock.lock(); defer { lock.unlock() }; lines.append(event + " " + details) }
    var text: String { lock.lock(); defer { lock.unlock() }; return lines.joined(separator: "\n") }
}

private let gigabyte: UInt64 = 1024 * 1024 * 1024
private let targetPath = "/GARMIN/terento_freizeitkarte_fra.img"

#if !TERENTO_PRODUCTION_CLEANUP_TEST
protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
}
#endif

#if TERENTO_PRODUCTION_CLEANUP_TEST
@_silgen_name("terento_cleanup_forbidden_calls")
private func cleanupForbiddenNativeCalls() -> Int32
#endif

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

private struct RawReadFailure: InstallationFailureContextProviding, Sendable {
    let failureContext: InstallationFailureContext?
}

private final class MockDeviceReader: InstallationDeviceReader, @unchecked Sendable {
    var files: [DeviceFile]
    var initialFiles: [DeviceFile]
    private(set) var inventoryReadCount = 0
    var missingTargetReads = 0
    var failInventoryRead: Int?
    var inventoryError: InstallationTransportError?
    var inventoryErrorRead: Int?
    var snapshotError: InstallationTransportError?
    var rawReadError: RawReadFailure?
    var rawReadErrorBoundary: InstallationFailureContext.Boundary?
    var inventoryFailureDelay: TimeInterval = 0
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
        if let rawReadError,
           (rawReadErrorBoundary == .prewriteInventory && inventoryReadCount == 0)
            || (rawReadErrorBoundary == .postwriteInventory && inventoryReadCount > 0) {
            throw rawReadError
        }
        if let inventoryError, inventoryErrorRead == nil || inventoryErrorRead == inventoryReadCount {
            if inventoryFailureDelay > 0 {
                Thread.sleep(forTimeInterval: inventoryFailureDelay)
            }
            throw inventoryError
        }
        if shouldFail || failInventoryRead == inventoryReadCount {
            throw InstallationTransportError.deviceDisconnected(
                "device disconnected",
                createdItemID: nil
            )
        }
        defer { inventoryReadCount += 1 }
        let inventory = inventoryReadCount == 0 ? initialFiles : files
        if inventoryReadCount > 0 && missingTargetReads > 0 {
            missingTargetReads -= 1
            return inventory.filter { $0.path != targetPath }
        }
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
        if let rawReadError, rawReadErrorBoundary == .postwriteSnapshot { throw rawReadError }
        if let snapshotError { throw snapshotError }
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
    var readError: InstallationTransportError?
    var writeError: InstallationTransportError?
    var writeCount = 0
    var readBackCount = 0
    var deleteCount = 0
    var declineCleanup = false
    #if TERENTO_PRODUCTION_CLEANUP_TEST
    var useProductionCleanup = false
    var productionCleanupEvaluations = 0
    #endif
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
        if let readError { throw readError }
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
        #if TERENTO_PRODUCTION_CLEANUP_TEST
        if useProductionCleanup {
            productionCleanupEvaluations += 1
            // Only the transport's upload/read side is simulated. Refusal is
            // evaluated by the actual production cleanup entrypoint.
            try MTPMapInstallationTransport().deleteExact(targetFilename: targetFilename,
                expectedItemID: expectedItemID, expectedSizeBytes: expectedSizeBytes)
            return
        }
        #endif
        if declineCleanup { throw CleanupIdentityUnproven() }
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
    private static var failed = 0

    static func main() throws {
        var passed = 0
        passed += testCanonicalTransferProgress()
        passed += testValidNewInstall()
        passed += testExistingFranceBlocksNewInstall()
        passed += testInsufficientSpaceBlocksWrite()
        passed += testUnknownProfileBlocksWrite()
        passed += testInstallationAuthorizationBlocksBeforeTransport()
        passed += testUnavailableAuthorizationBlocksBeforeTransport()
        passed += testTargetPolicyRejectsUnsupportedProviderBeforeTransport()
        passed += testTargetPolicyAcceptsAnotherFreizeitkarteRegion()
        passed += testTargetPolicyAcceptsOpenTopoMapProvider()
        passed += testTargetPolicyAcceptsCurrentOpenTopoMapCatalogIdentity()
        passed += testArtifactValidatorAcceptsOpenTopoMapProvider()
        passed += testRawMapRandoPassesFinalValidation()
        passed += testTargetPolicyAcceptsMapCapableBetaProfile()
        passed += testMapCapableNonLabPIDCompletesGenericLifecycle()
        passed += testMissingStableWatchIdentityBlocksBeforeMutation()
        passed += testTargetPolicyRejectsBetaProfileWithoutGarminRoot()
        passed += testCoordinatorUsesBusyTransactionGate()
        passed += testNonValidatedArtifactBlocksWrite()
        passed += testConfirmationIsRequiredBeforeWrite()
        passed += testReadFailureDoesNotClaimDisconnect()
        passed += testPreWriteInventoryFailureIsPreflightAndNoWrite()
        passed += testWriteFailureIsNotSuccess()
        passed += testDisconnectDuringWriteFails()
        passed += testPartialObjectIsCleanedAfterWriteDisconnect()
        passed += testMissingRemoteIsFailure()
        passed += testPostVerificationInventoryRecheck()
        passed += testPostVerificationChangedTargetsFailClosed()
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
        passed += testProtectionContextObservations()
        passed += testProtectionCleanupPreservesOriginalContext()
        passed += testTargetReasonObservations()
        passed += testContextualReadBoundaries()
        passed += testRawReadContextProvider()
        passed += testCrossSessionHandleMatrix()
        passed += testCrossSessionMutationMatrix()
        passed += testInitialInventoryAmbiguity()
        passed += testTargetHandleAndFolderValidation()
        passed += testOversizedProtectionCountsAreOmitted()
        passed += testRuntimeChurnIsDiagnostic()
        passed += testDeclinedCleanupPreservesEvidence()
        passed += testTargetStorageMismatch()
        #if TERENTO_PRODUCTION_CLEANUP_TEST
        passed += try testProductionCleanupRefusalRetainsDurableEvidence()
        #endif

        guard failed == 0 else {
            print("FAIL: \(failed) Stage 4.2 installation assertions failed")
            exit(1)
        }
        print("PASS: \(passed) Stage 4.2 installation tests")
    }

    private static func testProtectionContextObservations() -> Int {
        var passed = 0
        let reasons: [InstallationProtectionContext.Reason] = [
            .nonTargetObjectAdded, .preexistingObjectRemoved, .preexistingObjectChanged,
            .inventoryAmbiguous, .targetPresentBeforeWrite
        ]
        for prewrite in [true, false] {
            for reason in reasons where prewrite || reason != .targetPresentBeforeWrite {
                let harness = makeHarness()
                var reader: MockDeviceReader?
                let result = harness.run(configureReader: {
                    reader = $0
                    var files = prewrite ? $0.initialFiles : $0.files
                    let existing = files[1]
                    switch reason {
                    case .nonTargetObjectAdded:
                        files.append(DeviceFile(itemID: 600, parentID: 0, storageID: 1,
                            path: "/GARMIN/unknown.img", filename: "unknown.img", sizeBytes: 42, isFolder: false))
                    case .preexistingObjectRemoved: files.remove(at: 1)
                    case .preexistingObjectChanged:
                        // A real stable-field change must reject; session handles may change.
                        files[1] = DeviceFile(itemID: existing.itemID, parentID: existing.parentID,
                            storageID: existing.storageID, path: existing.path, filename: existing.filename,
                            sizeBytes: existing.sizeBytes + 1, isFolder: existing.isFolder)
                    case .inventoryAmbiguous:
                        files.append(DeviceFile(itemID: 600, parentID: 0, storageID: existing.storageID,
                            path: existing.path, filename: existing.filename, sizeBytes: 42, isFolder: false))
                    case .targetPresentBeforeWrite:
                        files.append($0.files.first { $0.path == targetPath }!)
                    default: fatalError("unexpected fixture")
                    }
                    if prewrite { $0.initialFiles = files } else { $0.files = files }
                })
                let context = result.failureContext
                let protection = context?.protection
                passed += expect(result.failure == .protectionViolation
                    && context?.boundary == (prewrite ? .prewriteProtection : .postwriteProtection)
                    && context?.boundary.stageRawValue == (prewrite ? "preflight" : "verify")
                    && protection?.protectionReason == reason
                    && protection?.beforeObjectCount == 3
                    && protection?.stableIdentityComparisonVersion == (reason == .targetPresentBeforeWrite ? nil : 2)
                    && protection?.targetItemIDMatches == nil
                    && result.originalFailureContext == nil
                    && harness.transport.writeCount == (prewrite ? 0 : 1)
                    && harness.transport.deleteCount == (prewrite ? 0 : 1)
                    && reader?.inventoryReadCount == (prewrite ? 1 : 2)
                    && harness.manifest.entries.isEmpty,
                    "\(prewrite ? "prewrite" : "postwrite") \(reason.rawValue) reports observed boundary without changing operations")
                if reason == .inventoryAmbiguous {
                    passed += expect(protection?.addedObjectCount == nil && protection?.removedObjectCount == nil
                        && protection?.changedObjectCount == nil, "ambiguous pairing omits delta counts")
                } else if reason != .targetPresentBeforeWrite {
                    passed += expect(protection?.addedObjectCount == (reason == .nonTargetObjectAdded ? 1 : 0)
                        && protection?.removedObjectCount == (reason == .preexistingObjectRemoved ? 1 : 0)
                        && protection?.changedObjectCount == (reason == .preexistingObjectChanged ? 1 : 0),
                        "non-target delta counts describe the current comparison")
                }
            }
        }
        return passed
    }

    private static func testProtectionCleanupPreservesOriginalContext() -> Int {
        var contexts: [InstallationFailureContext] = []
        var passed = 0
        for cleanupFails in [false, true] {
            let harness = makeHarness()
            if cleanupFails {
                harness.transport.deleteError = .contextual(failure: .operationFailed,
                    message: "cleanup fixture", createdItemID: nil,
                    context: InstallationFailureContext(boundary: .cleanup, classificationSource: .derived,
                        devicePresence: .unknown, operation: .cleanup, executionMode: .worker, resultKind: .timeout))
            }
            let result = harness.run(configureReader: { $0.files.remove(at: 1) })
            if let original = result.originalFailureContext ?? result.failureContext { contexts.append(original) }
            passed += expect(result.failure == (cleanupFails ? .cleanupFailed : .protectionViolation)
                && result.failureContext?.boundary == (cleanupFails ? .cleanup : .postwriteProtection)
                && result.originalFailure == (cleanupFails ? .protectionViolation : nil)
                && (!cleanupFails || result.failureContext?.resultKind == .timeout)
                && result.diagnostics.cleanupSucceeded == !cleanupFails
                && harness.transport.deletedFilename == "terento_freizeitkarte_fra.img"
                && harness.transport.deletedItemID == 77
                && harness.transport.deletedSizeBytes == UInt64(harness.remoteData.count)
                && harness.recovery.records.isEmpty == !cleanupFails,
                "cleanup outcome preserves original protection and exact cleanup/recovery behavior")
        }
        return passed + expect(contexts.count == 2 && contexts[0] == contexts[1],
            "cleanup failure retains the full immutable originating context")
    }

    private static func testTargetReasonObservations() -> Int {
        var passed = 0
        let reasons: [InstallationProtectionContext.Reason] = [
            .targetMissing, .targetDuplicate, .targetInvalid, .targetFilenameMismatch, .targetSizeMismatch
        ]
        for reason in reasons {
            let harness = makeHarness()
            var reader: MockDeviceReader?
            let result = harness.run(configureReader: {
                reader = $0
                let target = $0.files.removeLast()
                if reason != .targetMissing {
                    $0.files.append(DeviceFile(itemID: reason == .targetInvalid ? 0 : target.itemID,
                        parentID: target.parentID, storageID: target.storageID, path: target.path,
                        filename: reason == .targetFilenameMismatch ? "different.img" : target.filename,
                        sizeBytes: reason == .targetSizeMismatch ? target.sizeBytes + 1 : target.sizeBytes,
                        isFolder: target.isFolder))
                    if reason == .targetDuplicate { $0.files.append(target) }
                }
            })
            passed += expect(result.failure == .remoteFileMissing
                && result.failureContext?.boundary == .targetValidation
                && result.failureContext?.boundary.stageRawValue == "verify"
                && result.failureContext?.protection?.protectionReason == reason
                && result.failureContext?.protection?.stableIdentityComparisonVersion == nil
                && result.failureContext?.protection?.targetItemIDMatches == nil
                && harness.transport.writeCount == 1 && harness.transport.deleteCount == 1
                && reader?.inventoryReadCount == (reason == .targetMissing ? 3 : 2),
                "\(reason.rawValue) retains target failure code and existing read/cleanup behavior")
        }
        return passed
    }

    private static func testContextualReadBoundaries() -> Int {
        let native = InstallationFailureContext(boundary: .initialInventory, classificationSource: .native,
            devicePresence: .unknown, operation: .inventory, executionMode: .worker, resultKind: .nativeError,
            nativeCategory: .inventoryRead, nativeCodeNamespace: .terentoInventory, nativeResultCode: -3)
        let error = InstallationTransportError.contextual(failure: .operationFailed, message: "private fixture",
            createdItemID: nil, context: native)
        var passed = 0
        for boundary: InstallationFailureContext.Boundary in [.prewriteInventory, .readback, .postwriteInventory, .postwriteSnapshot] {
            let harness = makeHarness()
            if boundary == .readback { harness.transport.readError = error }
            let result = harness.run(configureReader: {
                if boundary == .prewriteInventory { $0.inventoryError = error }
                if boundary == .postwriteInventory { $0.inventoryError = error; $0.inventoryErrorRead = 1 }
                if boundary == .postwriteSnapshot { $0.snapshotError = error }
            })
            let context = result.failureContext
            passed += expect(context?.boundary == boundary && context?.nativeResultCode == -3
                && context?.nativeCodeNamespace == .terentoInventory && context?.executionMode == .worker
                && context?.resultKind == .nativeError && context?.devicePresence == .unknown
                && result.failure != .deviceDisconnected
                && harness.transport.writeCount == (boundary == .prewriteInventory ? 0 : 1),
                "observed \(boundary.rawValue) retains transport context through coordinator copies")
        }
        return passed
    }

    private static func testRawReadContextProvider() -> Int {
        var passed = 0
        for boundary: InstallationFailureContext.Boundary in [.prewriteInventory, .postwriteInventory, .postwriteSnapshot] {
            let snapshot = boundary == .postwriteSnapshot
            let native = InstallationFailureContext(
                boundary: snapshot ? .initialSnapshot : .initialInventory,
                classificationSource: .native, devicePresence: .unknown,
                operation: snapshot ? .snapshot : .inventory, executionMode: .inProcess,
                resultKind: .nativeError, nativeCategory: snapshot ? .storageRead : .inventoryRead,
                nativeCodeNamespace: snapshot ? .terentoSnapshot : .terentoInventory, nativeResultCode: -3)
            let harness = makeHarness()
            let result = harness.run(configureReader: {
                $0.rawReadError = RawReadFailure(failureContext: native)
                $0.rawReadErrorBoundary = boundary
            })
            passed += expect(result.failureContext == native.at(boundary)
                && result.failure == (boundary == .prewriteInventory ? .preflightMTPReadFailed : .verificationRequired)
                && result.failureContext?.retryCount == nil
                && harness.transport.writeCount == (boundary == .prewriteInventory ? 0 : 1)
                && harness.transport.deleteCount == (boundary == .prewriteInventory ? 0 : 1),
                "raw context provider survives \(boundary.rawValue) without a transport-specific dependency")
        }
        return passed
    }

    private static func testOversizedProtectionCountsAreOmitted() -> Int {
        let harness = makeHarness()
        let result = harness.run(configureReader: { reader in
            reader.initialFiles += (0...16384).map { index in
                DeviceFile(itemID: UInt32(index + 100), parentID: 0, storageID: 1,
                    path: "/GARMIN/fixture-\(index).img", filename: "fixture-\(index).img",
                    sizeBytes: 1, isFolder: false)
            }
        })
        let protection = result.failureContext?.protection
        return expect(result.failure == .protectionViolation && protection?.beforeObjectCount == 3
            && protection?.afterObjectCount == nil && protection?.addedObjectCount == nil
            && protection?.removedObjectCount == 0 && protection?.changedObjectCount == 0
            && harness.transport.writeCount == 0 && harness.transport.deleteCount == 0,
            "oversized observed counts are omitted rather than clamped or used as an inventory limit")
    }

    private static func changedFile(
        _ file: DeviceFile, itemID: UInt32? = nil, parentID: UInt32? = nil,
        storageID: UInt32? = nil, path: String? = nil, filename: String? = nil,
        sizeBytes: UInt64? = nil, isFolder: Bool? = nil
    ) -> DeviceFile {
        DeviceFile(itemID: itemID ?? file.itemID, parentID: parentID ?? file.parentID,
            storageID: storageID ?? file.storageID, path: path ?? file.path,
            filename: filename ?? file.filename, sizeBytes: sizeBytes ?? file.sizeBytes,
            isFolder: isFolder ?? file.isFolder)
    }

    private static func testCrossSessionHandleMatrix() -> Int {
        var passed = 0
        for prewrite in [true, false] {
            for kind in ["file", "folder", "hierarchy"] {
                let harness = makeHarness()
                let result = harness.run(configureReader: { reader in
                    func renumber(_ files: [DeviceFile]) -> [DeviceFile] {
                        files.map { file in
                            guard file.path != targetPath,
                                  kind == "hierarchy" || (kind == "folder") == file.isFolder else { return file }
                            return changedFile(file, itemID: file.itemID + 1000, parentID: file.parentID + 1000)
                        }
                    }
                    if prewrite { reader.initialFiles = renumber(reader.initialFiles) }
                    else { reader.files = renumber(reader.files) }
                })
                passed += expect(result.isSuccess && result.failureContext == nil
                    && result.diagnostics.existingFilesProtectionPassed
                    && result.diagnostics.unrelatedFilesProtectionPassed
                    && harness.transport.writeCount == 1 && harness.transport.deleteCount == 0
                    && harness.manifest.entries.count == 1,
                    "\(prewrite ? "prewrite" : "postwrite") \(kind) item and parent handles may renumber")
            }
        }
        return passed
    }

    private static func testRuntimeChurnIsDiagnostic() -> Int {
        func file(_ id: UInt32, _ path: String, folder: Bool = false, size: UInt64 = 10) -> DeviceFile {
            DeviceFile(itemID: id, parentID: 9, storageID: 1, path: path,
                filename: String(path.split(separator: "/").last!), sizeBytes: size, isFolder: folder)
        }
        let runtime = [file(1000, "/GARMIN/GarminDevice.xml"),
            file(1001, "/GARMIN/Monitor", folder: true, size: 0),
            file(1002, "/GARMIN/Monitor/before.FIT"),
            file(1003, "/GARMIN/TLG", folder: true, size: 0),
            file(1004, "/GARMIN/TLG/PER", folder: true, size: 0),
            file(1005, "/GARMIN/TLG/PER/before", folder: true, size: 0)]
        let changed = [file(1010, "/GARMIN/GarminDevice.xml", size: 99),
            runtime[1], file(1012, "/GARMIN/Monitor/after.FIT"), runtime[3], runtime[4],
            file(1015, "/GARMIN/TLG/PER/after", folder: true, size: 0)]
        var passed = 0
        for prewrite in [true, false] {
            let harness = Harness(beforeFilesTransform: { $0 + runtime })
            let recorder = DiagnosticRecorder()
            let result = harness.run(configureReader: { reader in
                if prewrite { reader.initialFiles = Harness.makeBeforeFiles(installedFrance: false) + changed }
                reader.files += changed
            }, diagnostic: recorder.record)
            passed += expect(result.isSuccess && harness.transport.writeCount == 1
                && harness.transport.deleteCount == 0 && result.diagnostics.existingFilesProtectionPassed
                && recorder.text.contains("global_inventory_observation"),
                "\(prewrite ? "prewrite and postwrite" : "postwrite") XML/FIT/runtime churn is diagnostic with protected maps unchanged")
        }
        return passed
    }

    private static func testTargetStorageMismatch() -> Int {
        let harness = makeHarness()
        let result = harness.run(configureReader: { reader in
            reader.files = reader.files.map { $0.path == targetPath ? changedFile($0, storageID: 2) : $0 }
        })
        return expect(!result.isSuccess && result.failure == .protectionViolation
            && harness.manifest.entries.isEmpty,
            "correct target name and size on another storage cannot pass independent protection")
    }

    private static func testDeclinedCleanupPreservesEvidence() -> Int {
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        harness.transport.declineCleanup = true
        let result = harness.run()
        return expect(result.failure == .cleanupFailed && result.originalFailure != nil
            && !result.diagnostics.cleanupAttempted && !result.diagnostics.cleanupSucceeded
            && harness.transport.deleteCount == 0 && harness.recovery.records.count == 1,
            "unproven cleanup identity refuses mutation and retains recovery plus original failure")
    }

    #if TERENTO_PRODUCTION_CLEANUP_TEST
    private static func testProductionCleanupRefusalRetainsDurableEvidence() throws -> Int {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-production-cleanup-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalTerentoFailedInstallRecoveryStore(rootDirectory: root)
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        harness.transport.useProductionCleanup = true
        var simulatedDevice: MockDeviceReader?
        let result = harness.run(configureReader: { simulatedDevice = $0 }, recoveryStore: store)
        let restartedStore = LocalTerentoFailedInstallRecoveryStore(rootDirectory: root)
        let records = try restartedStore.read(deviceKey: harness.request.identity.localManifestDeviceKey)
        let protectedBefore = harness.request.beforeDeviceFiles
        let protectedAfter = simulatedDevice?.files.filter { $0.path != targetPath }
        let checks = expect(result.status == .failed && result.failure == .cleanupFailed
            && result.originalFailure != nil && !result.diagnostics.cleanupAttempted
            && !result.diagnostics.cleanupSucceeded && harness.manifest.entries.isEmpty,
            "production cleanup refusal does not report success or record ownership")
            + expect(harness.transport.writeCount == 1 && harness.transport.productionCleanupEvaluations == 1
                && harness.transport.deleteCount == 0 && cleanupForbiddenNativeCalls() == 0,
                "actual production cleanup evaluation performs no native open/send/delete")
            + expect(records.count == 1 && records[0].devicePath == targetPath
                && records[0].sizeBytes == UInt64(harness.remoteData.count)
                && protectedBefore == protectedAfter,
                "failed install retains durable recovery after restart and leaves unrelated fixture objects unchanged")
        // Even a plausible target handle/size cannot confer creation authority
        // after the original session is lost.
        for historicalHandle: UInt32 in [77, 1077] {
            do {
                try MTPMapInstallationTransport().deleteExact(targetFilename: "terento_freizeitkarte_fra.img",
                    expectedItemID: historicalHandle)
                throw NSError(domain: "Production cleanup unexpectedly accepted", code: 1)
            } catch is CleanupIdentityUnproven { }
        }
        print("LOCAL CLEANUP: simulated Send=1; actual cleanup evaluations=3; native open/send/delete=0; durable recovery retained")
        return checks + expect(cleanupForbiddenNativeCalls() == 0, "stale and renumbered cleanup handles never reach native transport")
    }
    #endif

    private static func testCrossSessionMutationMatrix() -> Int {
        var passed = 0
        let mutations = ["filename", "rename", "move", "size", "storage", "kind", "folder to file", "removed", "added",
                         "duplicate", "duplicate handles", "ambiguous", "invalid path"]
        for prewrite in [true, false] {
            for mutation in mutations {
                let harness = makeHarness()
                let result = harness.run(configureReader: { reader in
                    var files = prewrite ? reader.initialFiles : reader.files
                    let original = files[1]
                    switch mutation {
                    case "filename": files[1] = changedFile(original, filename: "renamed.img")
                    case "rename": files[1] = changedFile(original, path: "/GARMIN/renamed.img", filename: "renamed.img")
                    case "folder to file": files[0] = changedFile(files[0], isFolder: false)
                    case "move": files[1] = changedFile(original, path: "/OTHER/" + original.filename)
                    case "size": files[1] = changedFile(original, sizeBytes: original.sizeBytes + 1)
                    case "storage": files[1] = changedFile(original, storageID: 2)
                    case "kind": files[1] = changedFile(original, isFolder: true)
                    case "removed": files.remove(at: 1)
                    case "added": files.append(changedFile(original, itemID: 900,
                        path: "/GARMIN/unrelated.img", filename: "unrelated.img"))
                    case "duplicate": files.append(original)
                    case "duplicate handles": files.append(changedFile(original, itemID: 901, parentID: 902))
                    case "ambiguous": files.append(changedFile(original, itemID: 903, sizeBytes: original.sizeBytes + 1))
                    case "invalid path": files[1] = changedFile(original, path: "")
                    default: fatalError("unexpected mutation")
                    }
                    if prewrite { reader.initialFiles = files } else { reader.files = files }
                })
                let ambiguous = ["duplicate", "duplicate handles", "ambiguous", "invalid path", "filename"].contains(mutation)
                passed += expect(result.failure == .protectionViolation
                    && result.failureContext?.boundary == (prewrite ? .prewriteProtection : .postwriteProtection)
                    && result.failureContext?.boundary.stageRawValue == (prewrite ? "preflight" : "verify")
                    && (!ambiguous || result.failureContext?.protection?.protectionReason == .inventoryAmbiguous)
                    && harness.transport.writeCount == (prewrite ? 0 : 1)
                    && harness.transport.deleteCount == (prewrite ? 0 : 1)
                    && harness.manifest.entries.isEmpty,
                    "\(prewrite ? "prewrite" : "postwrite") \(mutation) fails closed with exact mutation boundary")
            }
        }
        return passed
    }

    private static func testInitialInventoryAmbiguity() -> Int {
        var passed = 0
        for changedSize in [false, true] {
            let harness = Harness(beforeFilesTransform: { files in
                files + [changedFile(files[1], itemID: 900, parentID: 901,
                    sizeBytes: files[1].sizeBytes + (changedSize ? 1 : 0))]
            })
            let result = harness.run()
            passed += expect(result.failure == .protectionViolation
                && result.failureContext?.boundary == .prewriteProtection
                && result.failureContext?.protection?.protectionReason == .inventoryAmbiguous
                && harness.transport.writeCount == 0 && harness.transport.deleteCount == 0
                && harness.manifest.entries.isEmpty,
                "initial inventory \(changedSize ? "ambiguous path" : "duplicate stable identity") blocks before write")
        }
        return passed
    }

    private static func testTargetHandleAndFolderValidation() -> Int {
        var passed = 0
        for folder in [false, true] {
            let harness = makeHarness()
            let result = harness.run(configureReader: { reader in
                reader.files = reader.files.map { file in
                    file.path == targetPath
                        ? changedFile(file, itemID: 999, parentID: 998, isFolder: folder) : file
                }
            })
            passed += expect(folder
                ? result.failureContext?.protection?.protectionReason == .targetInvalid
                    && harness.transport.deleteCount == 1 && harness.manifest.entries.isEmpty
                : result.isSuccess && harness.transport.deleteCount == 0 && harness.manifest.entries.count == 1,
                folder ? "folder at exact target path fails validation" : "target stable identity survives item and parent handle changes")
        }
        return passed
    }

    private static func testCanonicalTransferProgress() -> Int {
        let callback = TransferProgress(bytesTransferred: 12_582_912, totalBytes: 29_360_128)
        let canonical = callback.normalized(sourceSize: 12_793_856)
        let harness = makeHarness()
        harness.transport.readBackMode = .hashMismatch
        let result = harness.run()
        return expect(
            canonical.totalBytes == 12_793_856 && canonical.fractionCompleted > 0.98
                && result.diagnostics.bytesTransferred == UInt64(harness.remoteData.count)
                && result.diagnostics.transferTotalBytes == UInt64(harness.remoteData.count)
                && result.status != .installVerified
                && harness.transport.writeCount == 1,
            "invalid native total is normalized and read-back cannot replace completed transfer diagnostics"
        )
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

    private static func testInstallationAuthorizationBlocksBeforeTransport() -> Int {
        let harness = makeHarness(authorization: .blocked(.unknownModel))
        let result = harness.run()
        return expect(
            result.status == .blockedInstallationAuthorization
                && result.failure == .installationAuthorization
                && harness.transport.writeCount == 0
                && harness.transport.readBackCount == 0
                && harness.transport.deleteCount == 0
                && harness.manifest.entries.isEmpty,
            "out-of-scope authorization blocks direct coordinator before transport or statistics-worthy mutation"
        )
    }

    private static func testUnavailableAuthorizationBlocksBeforeTransport() -> Int {
        let harness = makeHarness(authorization: .blocked(.catalogUnavailable))
        let result = harness.run()
        return expect(
            result.status == .blockedInstallationAuthorization
                && result.failure == .installationAuthorizationUnavailable
                && result.failure?.userLabel.contains("try again") == true
                && harness.transport.writeCount == 0
                && harness.transport.readBackCount == 0
                && harness.transport.deleteCount == 0
                && harness.manifest.entries.isEmpty,
            "temporary authorization failure blocks before transport with retry guidance"
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
                deviceFiles: harness.request.beforeDeviceFiles,
                installationAuthorization: authorization(for: harness.request.identity)
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
                deviceFiles: harness.request.beforeDeviceFiles,
                installationAuthorization: authorization(for: harness.request.identity)
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
                deviceFiles: harness.request.beforeDeviceFiles,
                installationAuthorization: authorization(for: harness.request.identity)
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
                deviceFiles: harness.request.beforeDeviceFiles,
                installationAuthorization: authorization(for: harness.request.identity)
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

    private static func testRawMapRandoPassesFinalValidation() -> Int {
        var bytes = [UInt8](Harness.makeIMG())
        let description = Array("MapRando Lituanie 02.09.2026".utf8)
        bytes.replaceSubrange(0x49..<0x5D, with: Array(repeating: UInt8(32), count: 20))
        bytes.replaceSubrange(0x65..<0x83, with: Array(repeating: UInt8(32), count: 30))
        for (index, byte) in description.enumerated() {
            bytes[index < 20 ? 0x49 + index : 0x65 + index - 20] = byte
        }
        let data = Data(bytes)
        let package = MapPackage(
            id: "maprando-lituanie", providerId: "maprando", regionId: "LITUANIE",
            name: "Lithuania", version: MapVersion(year: 2026, month: 9, day: 2)!,
            sizeBytes: UInt64(data.count),
            sourceURL: URL(string: "https://ravenfeld.fr/MapRando/Lituanie/MapRando_Lituanie_2026_09_02.img"),
            releaseDate: "2026-09-02", identifier: "lituanie",
            downloadSizeBytes: UInt64(data.count), installSizeBytes: UInt64(data.count)
        )
        let artifact = Harness.makeArtifact(package: package, data: data, packageFormat: .rawIMG)
        defer { try? FileManager.default.removeItem(at: artifact.localIMGURL) }
        do {
            _ = try MapSourceValidator().validate(fileURL: artifact.localIMGURL, expectedPackage: package)
            try Stage42ArtifactValidator().validate(artifact: artifact, package: package)
            let identity = betaIdentity()
            let files = [betaGarminRoot()]
            try Stage42TargetPolicy().validate(package: package, artifact: artifact,
                profile: DeviceInstallProfileRegistry.local.profile(for: identity, deviceFiles: files),
                identity: identity, deviceFiles: files,
                installationAuthorization: authorization(for: identity))
            // A changed local file must still fail the final hash recheck.
            var changed = data
            changed[changed.count - 1] ^= 1
            try changed.write(to: artifact.localIMGURL)
            do {
                try Stage42ArtifactValidator().validate(artifact: artifact, package: package)
                return expect(false, "MapRando changed content must be rejected")
            } catch Stage42ArtifactValidationError.sourceHashMismatch {}

            // Existing ZIP providers do not acquire an unreviewed raw-IMG path.
            for provider in ["freizeitkarte", "opentopomap"] {
                let existing = Harness.makePackage(size: UInt64(data.count), providerID: provider)
                let raw = Harness.makeArtifact(package: existing, data: data, packageFormat: .rawIMG)
                defer { try? FileManager.default.removeItem(at: raw.localIMGURL) }
                do {
                    try Stage42ArtifactValidator().validate(artifact: raw, package: existing)
                    return expect(false, "\(provider) must retain its reviewed ZIP format")
                } catch Stage42ArtifactValidationError.sourceFormatMismatch {}
            }
            return expect(true, "raw MapRando passes source and final write policies; hash and ZIP-provider guards remain")
        } catch {
            return expect(false, "raw MapRando final validation: \(error)")
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
                deviceFiles: files,
                installationAuthorization: authorization(for: identity)
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
                deviceFiles: [],
                installationAuthorization: authorization(for: identity)
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

    private static func authorization(for identity: DeviceIdentity) -> InstallationAuthorizationState {
        let record = InstallationAuthorizationRecord(
            id: identity.catalogDeviceID ?? "test-device",
            manufacturer: identity.manufacturer,
        model: identity.model,
        baseModel: identity.canonicalModel ?? identity.model,
            canonicalModel: identity.canonicalModel ?? identity.model,
            variant: identity.variant ?? "",
            caseSizeMm: identity.caseSizeMm,
            displayType: identity.displayType,
            screenTechnology: identity.screenTechnology,
            solar: identity.solar,
            inReach: identity.inReach,
            active: true,
            scope: "IN_SCOPE",
            installationAuthorization: "APPROVED"
        )
        return .approved(record: record, policyVersion: 1)
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

    private static func testReadFailureDoesNotClaimDisconnect() -> Int {
        let harness = makeHarness()
        harness.transport.readError = .operationFailed("USB read failed", createdItemID: nil)
        harness.transport.deleteError = .operationFailed("device unavailable", createdItemID: nil)
        let result = harness.run()
        return expect(result.failure == .cleanupFailed
            && result.originalFailure == .verificationRequired
            && result.cleanupFailure == .cleanupFailed
            && harness.transport.readBackCount == 1,
            "read I/O preserves verification failure separately from cleanup, without claiming cable removal")
    }

    private static func testPreWriteInventoryFailureIsPreflightAndNoWrite() -> Int {
        let harness = makeHarness()
        let recorder = DiagnosticRecorder()
        let result = harness.run(configureReader: {
            $0.inventoryError = .operationFailed("worker deadline", createdItemID: nil)
            $0.inventoryFailureDelay = 0.01
        }, diagnostic: recorder.record)
        return expect(
            result.status == .failed
                && result.failure == .preflightMTPReadFailed
                && result.diagnostics.nativeFailureCode == .preflightMTPReadFailed
                && result.diagnostics.writeStarted == false
                && result.diagnostics.remoteObjectCreated == false
                && result.diagnostics.elapsedMilliseconds > 0
                && harness.transport.writeCount == 0
                && harness.manifest.entries.isEmpty
                && harness.recovery.records.isEmpty
                && recorder.text.contains("preflight_inventory_begin")
                && recorder.text.contains("preflight_inventory_failed elapsed="),
            "pre-write inventory timeout stays in preflight, records measured wait, and never starts upload"
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

    private static func testPostVerificationInventoryRecheck() -> Int {
        var passed = 0
        for missingReads in [0, 1, 2] {
            let harness = makeHarness()
            var reader: MockDeviceReader?
            let recorder = DiagnosticRecorder()
            let result = harness.run(configureReader: {
                $0.missingTargetReads = missingReads
                reader = $0
            }, diagnostic: { recorder.record($0, $1) })
            passed += expect(
                recorder.text.contains("final_inventory attempt=1 matches=\(missingReads == 0 ? 1 : 0)")
                    && !recorder.text.contains("/GARMIN")
                    && (missingReads < 2 || recorder.text.contains("cleanup_result attempt=1 succeeded=1"))
                    && result.isSuccess == (missingReads < 2)
                    && reader?.inventoryReadCount == (missingReads == 0 ? 2 : 3)
                    && harness.transport.writeCount == 1
                    && harness.transport.deleteCount == (missingReads < 2 ? 0 : 1),
                "post-verify inventory missing \(missingReads) times: bounded recheck, no repeated write"
            )
        }
        let harness = makeHarness()
        let result = harness.run(configureReader: {
            $0.missingTargetReads = 1
            $0.failInventoryRead = 2
        })
        passed += expect(!result.isSuccess && harness.transport.writeCount == 1
            && harness.transport.deleteCount == 1,
            "disconnect during inventory recheck fails with existing exact cleanup")
        return passed
    }

    private static func testPostVerificationChangedTargetsFailClosed() -> Int {
        var passed = 0
        for duplicate in [false, true] {
            let harness = makeHarness()
            var reader: MockDeviceReader?
            let result = harness.run(configureReader: {
                reader = $0
                let target = $0.files.first { $0.path == targetPath }!
                if duplicate {
                    $0.files.append(target)
                } else {
                    $0.files = $0.files.map { file in
                        guard file.path == targetPath else { return file }
                        return DeviceFile(itemID: file.itemID, parentID: file.parentID,
                            storageID: file.storageID, path: file.path, filename: file.filename,
                            sizeBytes: file.sizeBytes + 1, isFolder: file.isFolder)
                    }
                }
            })
            passed += expect(!result.isSuccess && reader?.inventoryReadCount == 2
                && harness.transport.writeCount == 1 && harness.transport.deleteCount == 1,
                "present \(duplicate ? "duplicate" : "wrong-size") target fails without inventory retry")
        }
        return passed
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
        let progress = FinishingProgressRecorder()
        let result = harness.run(onProgress: progress.receive, onPhase: progress.setPhase)
        return expect(
            progress.sawIncompleteRead && progress.sawCompleteRead
                && result.verification?.status == .verifiedSampledReadBack
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
            userConfirmed: Bool = true,
            authorization: InstallationAuthorizationState? = nil,
            beforeFilesTransform: ([DeviceFile]) -> [DeviceFile] = { $0 }
        ) {
            remoteData = Self.makeIMG()
            transport = MockTransport(remoteData: remoteData)
            manifest = MockManifestStore()
            recovery = MockFailedInstallRecoveryStore()

            let package = Self.makePackage(size: UInt64(remoteData.count))
            let installed = installedFrance ? Self.makeFranceMap(size: UInt64(remoteData.count)) : nil
            let before = beforeFilesTransform(Self.makeBeforeFiles(installedFrance: installedFrance))
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
                userConfirmed: userConfirmed,
                installationAuthorization: authorization ?? Stage42InstallationTests.authorization(for: resolvedIdentity)
            )
        }

        func run(
            transactionGate: InstallationTransactionGate = InstallationTransactionGate(),
            onProgress: (@Sendable (TransferProgress) -> Void)? = nil,
            onPhase: (@Sendable (InstallationProcessPhase) -> Void)? = nil,
            configureReader: (MockDeviceReader) -> Void = { _ in },
            diagnostic: @escaping @Sendable (String, String) -> Void = { _, _ in },
            recoveryStore: (any TerentoFailedInstallRecoveryStore)? = nil
        ) -> MapInstallationResult {
            let reader = MockDeviceReader(
                files: Self.makeAfterFiles(),
                initialFiles: request.beforeDeviceFiles
            )
            reader.renumberExistingObjectIDs = renumberExistingObjectIDs
            configureReader(reader)
            let validator = AllowArtifactValidator()
            return MapInstallationCoordinator(
                artifactValidator: validator,
                transport: transport,
                deviceReader: reader,
                manifestStore: manifest,
                recoveryStore: recoveryStore ?? recovery,
                transactionGate: transactionGate,
                now: { Date(timeIntervalSince1970: 0) },
                diagnostic: diagnostic
            ).run(request, onProgress: onProgress, onPhase: onPhase)
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
                .appendingPathComponent("terento-stage42-mock-source-\(UUID().uuidString).img")
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
        userConfirmed: Bool = true,
        authorization: InstallationAuthorizationState? = nil
   ) -> Harness {
        Harness(
            installedFrance: installedFrance,
            availableStorage: availableStorage,
           profile: profile,
            artifact: artifact,
            noArtifact: noArtifact,
            userConfirmed: userConfirmed,
            authorization: authorization
       )
    }

    private static func expect(_ condition: Bool, _ description: String) -> Int {
        if condition {
            print("PASS: \(description)")
            return 1
        }
        failed += 1
        print("FAIL: \(description)")
        return 0
    }
}

private final class FinishingProgressRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var phase: InstallationProcessPhase?
    private(set) var sawIncompleteRead = false
    private(set) var sawCompleteRead = false
    func setPhase(_ value: InstallationProcessPhase) {
        lock.lock(); defer { lock.unlock() }
        phase = value
    }
    func receive(_ value: TransferProgress) {
        lock.lock(); defer { lock.unlock() }
        guard phase == .finishing, value.totalBytes > 0 else { return }
        sawIncompleteRead = sawIncompleteRead || value.bytesTransferred < value.totalBytes
        sawCompleteRead = sawCompleteRead || value.bytesTransferred == value.totalBytes
    }
}

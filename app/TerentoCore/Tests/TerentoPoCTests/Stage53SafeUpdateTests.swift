import CryptoKit
import Foundation

protocol DeviceFileReader: Sendable {
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

struct TransferVerification: Equatable, Sendable {
    let isVerified: Bool
}

private enum Stage53TestError: Error {
    case failed(String)
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else { throw Stage53TestError.failed(message) }
}

private final class AllowSafeUpdateSourceValidator: SafeUpdateSourceValidator, @unchecked Sendable {
    var shouldFail = false

    func validate(artifact: SafeUpdateSourceArtifact, package: MapPackage) throws {
        if shouldFail {
            throw SafeUpdateSourceValidationError.mismatch("source rejected")
        }
    }
}

private final class FakeSafeUpdateProvider: SafeUpdateArtifactProvider, @unchecked Sendable {
    let artifact: SafeUpdateSourceArtifact
    var shouldFail = false

    init(artifact: SafeUpdateSourceArtifact) {
        self.artifact = artifact
    }

    func acquire(
        package: MapPackage,
        onProgress: (@Sendable (SafeUpdateProgress) -> Void)?
    ) async throws -> SafeUpdateSourceArtifact {
        onProgress?(SafeUpdateProgress(state: .acquiring, bytesCompleted: 10, totalBytes: 10, bytesPerSecond: 100))
        if shouldFail {
            throw SafeUpdateAcquisitionError.failed("provider unavailable")
        }
        return artifact
    }
}

private final class FakeSafeUpdateManifestReconciler: SafeUpdateManifestReconciler, @unchecked Sendable {
    var shouldFail = false
    var called = false

    func reconcile(
        deviceKey: String,
        oldObject: SafeUpdateRemoteObject,
        newObject: SafeUpdateRemoteObject,
        package: MapPackage,
        finalObjects: [SafeUpdateRemoteObject]
    ) throws {
        called = true
        if shouldFail { throw TerentoManifestStoreError.cleanupFailed }
    }
}

private final class FakeSafeUpdateTransport: SafeUpdateTransport, @unchecked Sendable {
    enum Mode {
        case success
        case writeFailure
        case verifyHashMismatch
        case deleteFailure
        case disconnectOnRead
    }

    let oldObject: SafeUpdateRemoteObject
    let newObject: SafeUpdateRemoteObject
    let oldData: Data
    let oldHash: String
    var freeSpace: UInt64 = 12 * 1024 * 1024 * 1024
    var mode: Mode = .success
    var events: [String] = []
    var objects: [SafeUpdateRemoteObject]
    var currentInspectionObject: SafeUpdateRemoteObject

    init(oldObject: SafeUpdateRemoteObject, newObject: SafeUpdateRemoteObject, oldData: Data) {
        self.oldObject = oldObject
        self.newObject = newObject
        self.oldData = oldData
        self.oldHash = SHA256.hash(data: oldData).map { String(format: "%02x", $0) }.joined()
        self.objects = [oldObject]
        self.currentInspectionObject = oldObject
    }

    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        events.append("readExistingFile")
        if mode == .disconnectOnRead {
            throw MapLifecycleReadTransportError.deviceDisconnected("disconnected")
        }
        try oldData.write(to: destinationURL, options: .atomic)
        onProgress?(TransferProgress(bytesTransferred: UInt64(oldData.count), totalBytes: UInt64(oldData.count), bytesPerSecond: 1))
        return MapLifecycleBackupTransfer(
            itemID: file.itemID!,
            sourcePath: file.path,
            reportedSizeBytes: UInt64(oldData.count)
        )
    }

    func inspectCurrentObject(_ expected: SafeUpdateRemoteObject) throws -> SafeUpdateRemoteObject {
        events.append("inspectCurrentObject")
        return currentInspectionObject
    }

    func writeTransactionObject(
        sourceURL: URL,
        targetPath: String,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> SafeUpdateRemoteObject {
        events.append("writeTransactionObject")
        if mode == .writeFailure {
            throw SafeUpdateTransportError.writeFailed("write failed")
        }
        objects.append(newObject)
        onProgress?(TransferProgress(bytesTransferred: newObject.file.sizeBytes, totalBytes: newObject.file.sizeBytes, bytesPerSecond: 1))
        return newObject
    }

    func verifyTransactionObject(
        _ object: SafeUpdateRemoteObject,
        expected: SafeUpdateSourceArtifact
    ) throws -> SafeUpdateRemoteObject {
        events.append("verifyTransactionObject")
        if mode == .verifyHashMismatch {
            return SafeUpdateRemoteObject(
                file: newObject.file,
                identity: newObject.identity,
                version: newObject.version,
                ownership: newObject.ownership,
                sha256: String(repeating: "0", count: 64)
            )
        }
        return newObject
    }

    func cleanupTransactionObject(_ object: SafeUpdateRemoteObject) throws {
        events.append("cleanupTransactionObject")
        objects.removeAll { $0.file == object.file }
    }

    func readFreeSpace() throws -> UInt64 {
        events.append("readFreeSpace")
        return freeSpace
    }

    func rescanObjects() throws -> [SafeUpdateRemoteObject] {
        events.append("rescanObjects")
        return objects
    }

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        events.append("inspectExactObject")
        return SafeDeleteDeviceObject(file: oldObject.file, sha256: oldHash)
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        events.append("deleteExactObject")
        if mode == .deleteFailure {
            throw SafeDeleteTransportError.operationFailed("delete failed")
        }
        objects.removeAll { $0.file == oldObject.file }
    }
}

private struct Harness {
    let request: SafeUpdateRequest
    let package: MapPackage
    let artifact: SafeUpdateSourceArtifact
    let transport: FakeSafeUpdateTransport
    let provider: FakeSafeUpdateProvider
    let validator: AllowSafeUpdateSourceValidator
    let reconciler: FakeSafeUpdateManifestReconciler
    let gate: InstallationTransactionGate
}

private func makeHarness(oldVersioned: Bool = false) -> Harness {
    let identity = DeviceIdentity(
        manufacturer: "Garmin",
        model: "fenix 8 - 47mm",
        family: "fēnix",
        variant: nil,
        usbVendorId: 0x091e,
        usbProductId: 0x51b8,
        firmware: "2244",
        storageCapacity: 31_060_000_000,
        freeSpace: 15_000_000_000
    )
    let oldVersion = MapVersion(year: 2026, month: 5)!
    let newVersion = MapVersion(year: 2026, month: 6)!
    let mapIdentity = MapIdentity(provider: "freizeitkarte", region: "FRA")!
    let oldData = Data(repeating: 0x41, count: 16)
    let oldFilename = oldVersioned
        ? "terento_freizeitkarte_fra_2026-05.img"
        : "terento_freizeitkarte_fra.img"
    let oldFile = InstalledMapFile(
        path: "/GARMIN/\(oldFilename)",
        filename: oldFilename,
        sizeBytes: UInt64(oldData.count),
        itemID: 101
    )
    let newFile = InstalledMapFile(
        path: "/GARMIN/terento_freizeitkarte_fra_2026-06.img",
        filename: "terento_freizeitkarte_fra_2026-06.img",
        sizeBytes: 24,
        itemID: 202
    )
    let oldHash = SHA256.hash(data: oldData).map { String(format: "%02x", $0) }.joined()
    let sourceHash = String(repeating: "b", count: 64)
    let installedMap = InstalledMap(
        name: "Freizeitkarte FRA",
        provider: "Freizeitkarte",
        region: "FRA",
        family: "Freizeitkarte",
        rawVersion: "Release 26.05",
        version: oldVersion,
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: UInt64(oldData.count),
        sourceFile: oldFile,
        metadataStatus: .parsed,
        managementState: .managedByTerento
    )
    let item = MapLifecycleItem(
        id: "freizeitkarte-fra",
        title: "Freizeitkarte France",
        provider: "freizeitkarte",
        region: "FRA",
        version: oldVersion,
        rawVersion: "Release 26.05",
        sizeBytes: UInt64(oldData.count),
        installedMaps: [installedMap],
        classification: .terentoManaged
    )
    let package = MapPackage(
        id: "freizeitkarte-fra",
        providerId: "freizeitkarte",
        regionId: "FRA",
        name: "Freizeitkarte France",
        version: newVersion,
        sizeBytes: 24,
        sourceURL: URL(string: "https://provider.example/fra.zip"),
        releaseDate: nil,
        identifier: nil,
        installSizeBytes: 24
    )
    let artifactURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage53-artifact-\(UUID().uuidString).img")
    try? Data(repeating: 0x42, count: 24).write(to: artifactURL, options: .atomic)
    let artifact = SafeUpdateSourceArtifact(
        provider: "freizeitkarte",
        region: "FRA",
        version: newVersion,
        localIMGURL: artifactURL,
        installSizeBytes: 24,
        sha256: sourceHash,
        sourcePackageURL: package.sourceURL!,
        catalogPackageID: package.id,
        targetFilename: "terento_freizeitkarte_fra.img"
    )
    let oldObject = SafeUpdateRemoteObject(
        file: oldFile,
        identity: mapIdentity,
        version: oldVersion,
        ownership: .managedByTerento,
        sha256: oldHash
    )
    let newObject = SafeUpdateRemoteObject(
        file: newFile,
        identity: mapIdentity,
        version: newVersion,
        ownership: .managedByTerento,
        sha256: sourceHash
    )
    let comparison = MapComparison(
        providerName: "Freizeitkarte",
        regionName: "France",
        catalogMap: package,
        installedMap: installedMap,
        status: .updateAvailable
    )
    let gate = InstallationTransactionGate()
    let request = SafeUpdateRequest(
        deviceKey: "fenix-8-091e-51b8",
        identity: identity,
        profile: DeviceInstallProfileRegistry.local.profile(for: identity),
        selectedMap: package,
        comparison: comparison,
        currentItem: item,
        currentObject: oldObject,
        backupDirectory: FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage53-backups-\(UUID().uuidString)", isDirectory: true),
        confirmed: true,
        deviceConnected: true
    )
    let transport = FakeSafeUpdateTransport(oldObject: oldObject, newObject: newObject, oldData: oldData)
    let provider = FakeSafeUpdateProvider(artifact: artifact)
    let validator = AllowSafeUpdateSourceValidator()
    let reconciler = FakeSafeUpdateManifestReconciler()
    return Harness(request: request, package: package, artifact: artifact, transport: transport, provider: provider, validator: validator, reconciler: reconciler, gate: gate)
}

private func run(_ harness: Harness) async -> SafeUpdateResult {
    await SafeUpdateTransaction(
        gate: harness.gate,
        sourceValidator: harness.validator,
        manifestReconciler: harness.reconciler
    ).run(
        request: harness.request,
        provider: harness.provider,
        transport: harness.transport
    )
}

private func testSuccessfulUpdateAndOrdering() async throws {
    let harness = makeHarness()
    let result = await run(harness)
    try require(result.status == .success, "valid update should succeed")
    try require(!result.oldMapPreserved, "old map should be replaced only after verification")
    try require(harness.reconciler.called, "manifest reconciliation should be last domain step")
    try require(harness.transport.events.contains("writeTransactionObject"), "new object should be written")
    try require(harness.transport.events.contains("verifyTransactionObject"), "new object should be verified")
    try require(harness.transport.events.firstIndex(of: "deleteExactObject")! > harness.transport.events.firstIndex(of: "verifyTransactionObject")!, "delete must follow verification")
}

private func testNoUpdateAndOwnershipAreBlockedBeforeTransport() async throws {
    let harness = makeHarness()
    var request = harness.request
    request = SafeUpdateRequest(deviceKey: request.deviceKey, identity: request.identity, profile: request.profile, selectedMap: request.selectedMap, comparison: MapComparison(providerName: "Freizeitkarte", regionName: "France", catalogMap: request.selectedMap, installedMap: request.comparison.installedMap, status: .upToDate), currentItem: request.currentItem, currentObject: request.currentObject, backupDirectory: request.backupDirectory, confirmed: true, deviceConnected: true)
    let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator, manifestReconciler: harness.reconciler).run(request: request, provider: harness.provider, transport: harness.transport)
    try require(result.status == .blockedNoUpdate, "up-to-date map must not enter update")
    try require(harness.transport.events.isEmpty, "blocked update must not touch transport")

    let unmanaged = makeHarness()
    let unmanagedMap = InstalledMap(name: "External", provider: "Freizeitkarte", region: "FRA", family: nil, rawVersion: "Release 26.05", version: MapVersion(year: 2026, month: 5), identifier: nil, productId: nil, familyId: nil, sizeBytes: unmanaged.request.currentObject.file.sizeBytes, sourceFile: unmanaged.request.currentObject.file, metadataStatus: .parsed, managementState: .detectedNotManaged)
    let unmanagedItem = MapLifecycleItem(id: "freizeitkarte-fra", title: "External", provider: "freizeitkarte", region: "FRA", version: unmanagedMap.version, rawVersion: unmanagedMap.rawVersion, sizeBytes: unmanagedMap.sizeBytes, installedMaps: [unmanagedMap], classification: .externalRecognized)
    let unmanagedRequest = SafeUpdateRequest(deviceKey: unmanaged.request.deviceKey, identity: unmanaged.request.identity, profile: unmanaged.request.profile, selectedMap: unmanaged.request.selectedMap, comparison: unmanaged.request.comparison, currentItem: unmanagedItem, currentObject: unmanaged.request.currentObject, backupDirectory: unmanaged.request.backupDirectory, confirmed: true, deviceConnected: true)
    let unmanagedResult = await SafeUpdateTransaction(gate: unmanaged.gate, sourceValidator: unmanaged.validator, manifestReconciler: unmanaged.reconciler).run(request: unmanagedRequest, provider: unmanaged.provider, transport: unmanaged.transport)
    try require(unmanagedResult.status == .blockedNotManaged, "external map must be blocked")
    try require(unmanaged.transport.events.isEmpty, "unmanaged map must not touch transport")
}

private func testCurrentObjectChangedStopsBeforeBackup() async throws {
    let harness = makeHarness()
    let changed = SafeUpdateRemoteObject(file: InstalledMapFile(path: harness.request.currentObject.file.path, filename: harness.request.currentObject.file.filename, sizeBytes: 99, itemID: 101), identity: harness.request.currentObject.identity, version: harness.request.currentObject.version, ownership: .managedByTerento, sha256: harness.request.currentObject.sha256)
    harness.transport.currentInspectionObject = changed
    let result = await run(harness)
    try require(result.status == .blockedCurrentObjectChanged, "changed current object must be blocked")
    try require(!harness.transport.events.contains("readExistingFile"), "backup must not start after stale-object detection")
    try require(!harness.transport.events.contains("writeTransactionObject"), "write must not start after stale-object detection")
}

private func testMismatchedMapIdentityIsBlockedBeforeTransport() async throws {
    let harness = makeHarness()
    let mismatchedObject = SafeUpdateRemoteObject(
        file: harness.request.currentObject.file,
        identity: MapIdentity(provider: "opentopomap", region: "FRA")!,
        version: harness.request.currentObject.version,
        ownership: .managedByTerento,
        sha256: harness.request.currentObject.sha256
    )
    let request = SafeUpdateRequest(
        deviceKey: harness.request.deviceKey,
        identity: harness.request.identity,
        profile: harness.request.profile,
        selectedMap: harness.request.selectedMap,
        comparison: harness.request.comparison,
        currentItem: harness.request.currentItem,
        currentObject: mismatchedObject,
        backupDirectory: harness.request.backupDirectory,
        confirmed: true,
        deviceConnected: true
    )
    let result = await SafeUpdateTransaction(
        gate: harness.gate,
        sourceValidator: harness.validator,
        manifestReconciler: harness.reconciler
    ).run(request: request, provider: harness.provider, transport: harness.transport)
    try require(result.status == .blockedAmbiguousMapIdentity, "mismatched map identity must be blocked")
    try require(harness.transport.events.isEmpty, "identity mismatch must not touch transport")
}

private func testStorageAndBackupGates() async throws {
    let insufficient = makeHarness()
    insufficient.transport.freeSpace = insufficient.artifact.installSizeBytes + StoragePlanner.defaultSafetyReserve - 1
    let storageResult = await run(insufficient)
    try require(storageResult.status == .blockedInsufficientSpace, "insufficient storage must block before backup")
    try require(!insufficient.transport.events.contains("readExistingFile"), "insufficient storage must not create backup")

    let backupFailure = makeHarness()
    backupFailure.transport.mode = .disconnectOnRead
    let backupResult = await run(backupFailure)
    try require(backupResult.status == .failedDeviceDisconnected, "backup disconnect must fail safely")
    try require(!backupFailure.transport.events.contains("writeTransactionObject"), "write must not start after backup failure")
}

private func testVerificationFailureCleansOnlyNewObject() async throws {
    let harness = makeHarness()
    harness.transport.mode = .verifyHashMismatch
    let result = await run(harness)
    try require(result.status == .failedHashMismatch, "hash mismatch must fail the update")
    try require(harness.transport.events.contains("cleanupTransactionObject"), "failed verification must clean the new transaction object")
    try require(harness.transport.objects.contains(where: { $0.file == harness.request.currentObject.file }), "old map must remain after failed verification")
    try require(!harness.transport.events.contains("deleteExactObject"), "old map must not be deleted after failed verification")
}

private func testCommitAndManifestFailuresAreNotSuccess() async throws {
    let deleteFailure = makeHarness()
    deleteFailure.transport.mode = .deleteFailure
    let deleteResult = await run(deleteFailure)
    try require(deleteResult.status == .failedCommit, "delete failure must fail commit")
    try require(deleteResult.oldMapPreserved, "old map remains when commit delete fails")

    let manifestFailure = makeHarness()
    manifestFailure.reconciler.shouldFail = true
    let manifestResult = await run(manifestFailure)
    try require(manifestResult.status == .failedManifestReconciliation, "manifest failure must not be success")
    try require(!manifestResult.oldMapPreserved, "manifest failure occurs after device commit")
}

private func testPreviouslyVersionedMapCanBeUpdated() async throws {
    let harness = makeHarness(oldVersioned: true)
    let result = await run(harness)
    try require(result.status == .success, "a previously versioned managed map should be updateable: \(result.status) / \(result.message)")
    try require(harness.transport.events.contains("deleteExactObject"), "the verified versioned old object should be removable")
}

private func testBusyGateAndNoDowngrade() async throws {
    let busy = makeHarness()
    let heldID = UUID()
    try busy.gate.acquire(transactionID: heldID)
    let busyResult = await run(busy)
    busy.gate.release(transactionID: heldID)
    try require(busyResult.status == .blockedTransactionAlreadyRunning, "parallel update must be blocked")
    try require(busy.transport.events.isEmpty, "busy gate must not touch transport")

    let downgrade = makeHarness()
    let newerInstalled = SafeUpdateRemoteObject(file: downgrade.request.currentObject.file, identity: downgrade.request.currentObject.identity, version: MapVersion(year: 2026, month: 7), ownership: .managedByTerento, sha256: downgrade.request.currentObject.sha256)
    let request = SafeUpdateRequest(deviceKey: downgrade.request.deviceKey, identity: downgrade.request.identity, profile: downgrade.request.profile, selectedMap: downgrade.request.selectedMap, comparison: MapComparison(providerName: "Freizeitkarte", regionName: "France", catalogMap: downgrade.request.selectedMap, installedMap: downgrade.request.comparison.installedMap, status: .newerInstalled), currentItem: downgrade.request.currentItem, currentObject: newerInstalled, backupDirectory: downgrade.request.backupDirectory, confirmed: true, deviceConnected: true)
    let downgradeResult = await SafeUpdateTransaction(gate: downgrade.gate, sourceValidator: downgrade.validator, manifestReconciler: downgrade.reconciler).run(request: request, provider: downgrade.provider, transport: downgrade.transport)
    try require(downgradeResult.status == .blockedNewerInstalled, "newer installed map must never be downgraded")
}

@main
struct Stage53SafeUpdateTests {
    static func main() async throws {
        let tests: [(String, () async throws -> Void)] = [
            ("successful update and ordering", testSuccessfulUpdateAndOrdering),
            ("no-update and ownership gates", testNoUpdateAndOwnershipAreBlockedBeforeTransport),
            ("current-object revalidation", testCurrentObjectChangedStopsBeforeBackup),
            ("map identity gate", testMismatchedMapIdentityIsBlockedBeforeTransport),
            ("storage and backup gates", testStorageAndBackupGates),
            ("verification cleanup", testVerificationFailureCleansOnlyNewObject),
            ("commit and manifest failures", testCommitAndManifestFailuresAreNotSuccess),
            ("previously versioned target", testPreviouslyVersionedMapCanBeUpdated),
            ("busy gate and no downgrade", testBusyGateAndNoDowngrade)
        ]
        var passed = 0
        for (name, test) in tests {
            do {
                try await test()
                print("PASS: \(name)")
                passed += 1
            } catch {
                print("FAIL: \(name): \(error)")
                throw error
            }
        }
        print("PASS: \(passed) Stage 5.3 safe update tests")
    }
}

import CryptoKit
import Foundation

protocol DeviceFileReader: Sendable {
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
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

private func approvedAuthorization(for identity: DeviceIdentity) -> InstallationAuthorizationState {
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
        case deleteDisconnected
        case oldMissingBeforeDelete
    }

    let oldObject: SafeUpdateRemoteObject
    let newObject: SafeUpdateRemoteObject
    let oldHash: String
    var freeSpace: UInt64 = 12 * 1024 * 1024 * 1024
    var mode: Mode = .success
    var postDeleteSnapshot: (([SafeUpdateRemoteObject]) -> [SafeUpdateRemoteObject])?
    var rawSnapshotTransform: (([DeviceFile], Bool) throws -> [DeviceFile])?
    var renumberAfterOldDeletion = false
    var events: [String] = []
    var objects: [SafeUpdateRemoteObject]
    var currentInspectionObject: SafeUpdateRemoteObject

    init(oldObject: SafeUpdateRemoteObject, newObject: SafeUpdateRemoteObject) {
        self.oldObject = oldObject
        self.newObject = newObject
        self.oldHash = oldObject.sha256 ?? ""
        self.objects = [oldObject]
        self.currentInspectionObject = oldObject
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

    func readProtectedInventory() throws -> SafeUpdateInventorySnapshot {
        events.append("readProtectedInventory")
        let afterDelete = !objects.contains { $0.file.path == oldObject.file.path }
        let root = DeviceFile(itemID: 1, parentID: 0, storageID: 1,
            path: "/GARMIN", filename: "GARMIN", sizeBytes: 0, isFolder: true)
        let files = [root] + objects.map { object in
            DeviceFile(itemID: object.file.itemID!, parentID: 1, storageID: 1,
                path: object.file.path, filename: object.file.filename,
                sizeBytes: object.file.sizeBytes, isFolder: false)
        }
        return SafeUpdateInventorySnapshot(storageID: 1,
            files: try rawSnapshotTransform?(files, afterDelete) ?? files)
    }

    func rescanObjects() throws -> [SafeUpdateRemoteObject] {
        events.append("rescanObjects")
        if !objects.contains(where: { $0.file.path == oldObject.file.path }), let postDeleteSnapshot {
            return postDeleteSnapshot(objects)
        }
        if renumberAfterOldDeletion, !objects.contains(where: { $0.file.path == oldObject.file.path }) {
            // A fresh inventory session retains stable coordinates/content but
            // assigns a different handle to the verified new map.
            return objects.map { object in
                SafeUpdateRemoteObject(file: InstalledMapFile(path: object.file.path,
                    filename: object.file.filename, sizeBytes: object.file.sizeBytes,
                    itemID: (object.file.itemID ?? 0) + 1000), identity: object.identity,
                    version: object.version, ownership: object.ownership, sha256: object.sha256)
            }
        }
        return objects
    }

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        events.append("inspectExactObject")
        if mode == .oldMissingBeforeDelete { throw SafeDeleteTransportError.objectNotFound }
        return SafeDeleteDeviceObject(file: oldObject.file, sha256: oldHash)
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        events.append("deleteExactObject")
        if mode == .deleteFailure {
            throw SafeDeleteTransportError.operationFailed("delete failed")
        }
        if mode == .deleteDisconnected {
            throw SafeDeleteTransportError.deviceDisconnected("delete outcome unknown")
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

private func makeHarness(oldVersioned: Bool = false, withWorkspace: Bool = false) -> Harness {
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
    let workspaceRoot = withWorkspace
        ? FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage53-acquisition-\(UUID().uuidString)", isDirectory: true)
        : nil
    if let workspaceRoot {
        try? FileManager.default.createDirectory(at: workspaceRoot, withIntermediateDirectories: true)
    }
    let artifactURL = (workspaceRoot ?? FileManager.default.temporaryDirectory)
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
        targetFilename: "terento_freizeitkarte_fra.img",
        workspaceRootURL: workspaceRoot
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
        confirmed: true,
        deviceConnected: true,
        installationAuthorization: approvedAuthorization(for: identity)
    )
    let transport = FakeSafeUpdateTransport(oldObject: oldObject, newObject: newObject)
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
        request: withFixtureAuthorization(harness.request),
        provider: harness.provider,
        transport: harness.transport
    )
}

private func withFixtureAuthorization(_ request: SafeUpdateRequest) -> SafeUpdateRequest {
    let decision = request.installationAuthorization
    let expected = request.identity
    return SafeUpdateRequest(deviceKey: request.deviceKey, identity: expected, profile: request.profile,
        selectedMap: request.selectedMap, comparison: request.comparison,
        currentItem: request.currentItem, currentObject: request.currentObject,
        confirmed: request.confirmed, deviceConnected: request.deviceConnected,
        installationAuthorization: decision, deviceConnectionCheck: request.deviceConnectionCheck,
        authorizationRefresh: { _ in decision }, currentIdentity: { expected })
}

private actor AuthorizationProbe {
    var decisions: [InstallationAuthorizationState]
    var calls = 0
    var identityChecks = 0
    let expected: DeviceIdentity
    let swapAfterChecks: Int?

    init(_ decisions: [InstallationAuthorizationState], expected: DeviceIdentity, swapAfterChecks: Int? = nil) {
        self.decisions = decisions
        self.expected = expected
        self.swapAfterChecks = swapAfterChecks
    }

    func resolve(_ identity: DeviceIdentity) -> InstallationAuthorizationState {
        calls += 1
        return decisions[min(calls - 1, decisions.count - 1)]
    }

    func currentIdentity() -> DeviceIdentity? {
        identityChecks += 1
        if let swapAfterChecks, identityChecks > swapAfterChecks { return nil }
        return expected
    }
}

private func withFreshAuthorization(_ request: SafeUpdateRequest, probe: AuthorizationProbe) -> SafeUpdateRequest {
    SafeUpdateRequest(
        deviceKey: request.deviceKey, identity: request.identity, profile: request.profile,
        selectedMap: request.selectedMap, comparison: request.comparison,
        currentItem: request.currentItem, currentObject: request.currentObject,
        confirmed: request.confirmed, deviceConnected: request.deviceConnected,
        installationAuthorization: request.installationAuthorization,
        authorizationRefresh: { identity in await probe.resolve(identity) },
        currentIdentity: { await probe.currentIdentity() }
    )
}

private func testFreshUpdateAuthorization() async throws {
    let missing = makeHarness()
    let missingResult = await SafeUpdateTransaction(gate: missing.gate,
        sourceValidator: missing.validator, manifestReconciler: missing.reconciler).run(
        request: missing.request, provider: missing.provider, transport: missing.transport)
    try require(missingResult.status == .blockedInstallationAuthorization && missing.transport.events.isEmpty,
        "direct update without a fresh policy source cannot touch the device")

    let decisions: [(InstallationAuthorizationState?, SafeUpdateStatus, Int)] = [
        (nil, .success, 2),
        (.blocked(.pending), .blockedInstallationAuthorization, 1),
        (.blocked(.outOfScope), .blockedInstallationAuthorization, 1),
        (.blocked(.catalogUnavailable), .blockedInstallationAuthorization, 1),
    ]
    for (decision, expectedStatus, expectedCalls) in decisions {
        let harness = makeHarness()
        let probe = AuthorizationProbe([decision ?? harness.request.installationAuthorization], expected: harness.request.identity)
        let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator,
            manifestReconciler: harness.reconciler).run(
            request: withFreshAuthorization(harness.request, probe: probe),
            provider: harness.provider, transport: harness.transport)
        try require(result.status == expectedStatus, "fresh policy controls stale approved update")
        let callCount = await probe.calls
        try require(callCount == expectedCalls, "authorization is fetched at start and before write")
        if expectedStatus != .success {
            try require(harness.transport.events.isEmpty, "rejected update never reaches transport")
        }
    }

    let changed = makeHarness()
    let changedProbe = AuthorizationProbe([changed.request.installationAuthorization, .blocked(.pending)],
        expected: changed.request.identity)
    let changedResult = await SafeUpdateTransaction(gate: changed.gate, sourceValidator: changed.validator,
        manifestReconciler: changed.reconciler).run(
        request: withFreshAuthorization(changed.request, probe: changedProbe),
        provider: changed.provider, transport: changed.transport)
    try require(changedResult.status == .blockedInstallationAuthorization, "policy change before mutation aborts")
    try require(!changed.transport.events.contains("writeTransactionObject"), "changed policy prevents write")

    let swapped = makeHarness()
    let swapProbe = AuthorizationProbe([swapped.request.installationAuthorization],
        expected: swapped.request.identity, swapAfterChecks: 2)
    let swapResult = await SafeUpdateTransaction(gate: swapped.gate, sourceValidator: swapped.validator,
        manifestReconciler: swapped.reconciler).run(
        request: withFreshAuthorization(swapped.request, probe: swapProbe),
        provider: swapped.provider, transport: swapped.transport)
    try require(swapResult.status == .blockedInstallationAuthorization, "identity swap before write aborts")
    try require(!swapped.transport.events.contains("writeTransactionObject"), "swapped device receives no write")

    let cleanup = makeHarness()
    cleanup.transport.mode = .verifyHashMismatch
    let cleanupProbe = AuthorizationProbe([cleanup.request.installationAuthorization,
        cleanup.request.installationAuthorization, .blocked(.catalogUnavailable)],
        expected: cleanup.request.identity)
    let cleanupResult = await SafeUpdateTransaction(gate: cleanup.gate,
        sourceValidator: cleanup.validator, manifestReconciler: cleanup.reconciler).run(
        request: withFreshAuthorization(cleanup.request, probe: cleanupProbe),
        provider: cleanup.provider, transport: cleanup.transport)
    try require(cleanupResult.status == .failedHashMismatch, "postwrite verification fails as expected")
    try require(cleanup.transport.events.contains("cleanupTransactionObject"), "postwrite cleanup still runs")
    let cleanupCalls = await cleanupProbe.calls
    try require(cleanupCalls == 2, "cleanup needs no third policy request")
}

private func testSuccessfulUpdateAndOrdering() async throws {
    let harness = makeHarness(withWorkspace: true)
    let result = await run(harness)
    try require(result.status == .success, "valid update should succeed")
    try require(!result.oldMapPreserved, "old map should be replaced only after verification")
    try require(harness.reconciler.called, "manifest reconciliation should be last domain step")
    try require(harness.transport.events == [
        "inspectCurrentObject", "readFreeSpace", "readProtectedInventory",
        "writeTransactionObject", "verifyTransactionObject",
        "inspectExactObject", "deleteExactObject", "rescanObjects",
        "readProtectedInventory", "rescanObjects"
    ], "update should write, verify, remove old, and finish without a local backup")
    try require(harness.artifact.workspaceRootURL.map { !FileManager.default.fileExists(atPath: $0.path) } == true, "successful update should remove its acquisition workspace")
}

private func testInstallFailureRemovesAcquisitionWorkspace() async throws {
    let harness = makeHarness(withWorkspace: true)
    harness.transport.mode = .writeFailure
    let result = await run(harness)
    try require(result.status == .failedWrite, "install failure should be reported")
    try require(harness.artifact.workspaceRootURL.map { !FileManager.default.fileExists(atPath: $0.path) } == true, "install failure should remove its acquisition workspace")
}

private func testNoUpdateAndOwnershipAreBlockedBeforeTransport() async throws {
    let harness = makeHarness()
    var request = harness.request
    request = SafeUpdateRequest(deviceKey: request.deviceKey, identity: request.identity, profile: request.profile, selectedMap: request.selectedMap, comparison: MapComparison(providerName: "Freizeitkarte", regionName: "France", catalogMap: request.selectedMap, installedMap: request.comparison.installedMap, status: .upToDate), currentItem: request.currentItem, currentObject: request.currentObject, confirmed: true, deviceConnected: true, installationAuthorization: request.installationAuthorization)
    let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator, manifestReconciler: harness.reconciler).run(request: withFixtureAuthorization(request), provider: harness.provider, transport: harness.transport)
    try require(result.status == .blockedNoUpdate, "up-to-date map must not enter update")
    try require(harness.transport.events.isEmpty, "blocked update must not touch transport")

    let unmanaged = makeHarness()
    let unmanagedMap = InstalledMap(name: "External", provider: "Freizeitkarte", region: "FRA", family: nil, rawVersion: "Release 26.05", version: MapVersion(year: 2026, month: 5), identifier: nil, productId: nil, familyId: nil, sizeBytes: unmanaged.request.currentObject.file.sizeBytes, sourceFile: unmanaged.request.currentObject.file, metadataStatus: .parsed, managementState: .detectedNotManaged)
    let unmanagedItem = MapLifecycleItem(id: "freizeitkarte-fra", title: "External", provider: "freizeitkarte", region: "FRA", version: unmanagedMap.version, rawVersion: unmanagedMap.rawVersion, sizeBytes: unmanagedMap.sizeBytes, installedMaps: [unmanagedMap], classification: .externalRecognized)
    let unmanagedRequest = SafeUpdateRequest(deviceKey: unmanaged.request.deviceKey, identity: unmanaged.request.identity, profile: unmanaged.request.profile, selectedMap: unmanaged.request.selectedMap, comparison: unmanaged.request.comparison, currentItem: unmanagedItem, currentObject: unmanaged.request.currentObject, confirmed: true, deviceConnected: true, installationAuthorization: unmanaged.request.installationAuthorization)
    let unmanagedResult = await SafeUpdateTransaction(gate: unmanaged.gate, sourceValidator: unmanaged.validator, manifestReconciler: unmanaged.reconciler).run(request: withFixtureAuthorization(unmanagedRequest), provider: unmanaged.provider, transport: unmanaged.transport)
    try require(unmanagedResult.status == .blockedNotManaged, "external map must be blocked")
    try require(unmanaged.transport.events.isEmpty, "unmanaged map must not touch transport")
}

private func testInstallationAuthorizationIsCheckedBeforeUpdateAcquisition() async throws {
    let harness = makeHarness()
    let request = SafeUpdateRequest(
        deviceKey: harness.request.deviceKey,
        identity: harness.request.identity,
        profile: harness.request.profile,
        selectedMap: harness.request.selectedMap,
        comparison: harness.request.comparison,
        currentItem: harness.request.currentItem,
        currentObject: harness.request.currentObject,
        confirmed: true,
        deviceConnected: true,
        installationAuthorization: .blocked(.unknownModel)
    )
    let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator,
        manifestReconciler: harness.reconciler).run(
            request: withFixtureAuthorization(request), provider: harness.provider, transport: harness.transport)
    try require(result.status == .blockedInstallationAuthorization,
                "unknown installation authorization blocks update")
    try require(harness.transport.events.isEmpty && !harness.reconciler.called,
                "blocked update does not acquire, inspect, write, delete or reconcile")
}

private func testUnavailableInstallationAuthorizationIsRetryable() async throws {
    let harness = makeHarness()
    let request = SafeUpdateRequest(
        deviceKey: harness.request.deviceKey,
        identity: harness.request.identity,
        profile: harness.request.profile,
        selectedMap: harness.request.selectedMap,
        comparison: harness.request.comparison,
        currentItem: harness.request.currentItem,
        currentObject: harness.request.currentObject,
        confirmed: true,
        deviceConnected: true,
        installationAuthorization: .blocked(.catalogUnavailable)
    )
    let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator,
        manifestReconciler: harness.reconciler).run(
            request: withFixtureAuthorization(request), provider: harness.provider, transport: harness.transport)
    try require(result.status == .blockedInstallationAuthorization,
                "unavailable installation authorization blocks update")
    try require(result.message.contains("try again"),
                "unavailable installation authorization provides retry guidance")
    try require(harness.transport.events.isEmpty && !harness.reconciler.called,
                "unavailable authorization does not acquire, inspect, write, delete or reconcile")
}

private func testCurrentObjectChangedStopsBeforeWrite() async throws {
    let harness = makeHarness()
    let changed = SafeUpdateRemoteObject(file: InstalledMapFile(path: harness.request.currentObject.file.path, filename: harness.request.currentObject.file.filename, sizeBytes: 99, itemID: 101), identity: harness.request.currentObject.identity, version: harness.request.currentObject.version, ownership: .managedByTerento, sha256: harness.request.currentObject.sha256)
    harness.transport.currentInspectionObject = changed
    let result = await run(harness)
    try require(result.status == .blockedCurrentObjectChanged, "changed current object must be blocked")
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
        confirmed: true,
        deviceConnected: true,
        installationAuthorization: harness.request.installationAuthorization
    )
    let result = await SafeUpdateTransaction(
        gate: harness.gate,
        sourceValidator: harness.validator,
        manifestReconciler: harness.reconciler
    ).run(request: withFixtureAuthorization(request), provider: harness.provider, transport: harness.transport)
    try require(result.status == .blockedAmbiguousMapIdentity, "mismatched map identity must be blocked")
    try require(harness.transport.events.isEmpty, "identity mismatch must not touch transport")
}

private func testStorageGateAndBackupFreeUpdate() async throws {
    let insufficient = makeHarness()
    insufficient.transport.freeSpace = insufficient.artifact.installSizeBytes + StoragePlanner.defaultSafetyReserve - 1
    let storageResult = await run(insufficient)
    try require(storageResult.status == .blockedInsufficientSpace, "insufficient storage must block before writing")
    try require(!insufficient.transport.events.contains("writeTransactionObject"), "insufficient storage must not write a new map")

    let successful = makeHarness()
    let successfulResult = await run(successful)
    try require(successfulResult.isSuccess, "backup-free update should succeed")
    try require(!successful.transport.events.contains("readExistingFile"), "Safe Update must not copy the old map locally")
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
    try require(!deleteResult.oldMapPreserved, "an ambiguous delete failure cannot promise that the old map remains")

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
    let request = SafeUpdateRequest(deviceKey: downgrade.request.deviceKey, identity: downgrade.request.identity, profile: downgrade.request.profile, selectedMap: downgrade.request.selectedMap, comparison: MapComparison(providerName: "Freizeitkarte", regionName: "France", catalogMap: downgrade.request.selectedMap, installedMap: downgrade.request.comparison.installedMap, status: .newerInstalled), currentItem: downgrade.request.currentItem, currentObject: newerInstalled, confirmed: true, deviceConnected: true, installationAuthorization: downgrade.request.installationAuthorization)
    let downgradeResult = await SafeUpdateTransaction(gate: downgrade.gate, sourceValidator: downgrade.validator, manifestReconciler: downgrade.reconciler).run(request: withFixtureAuthorization(request), provider: downgrade.provider, transport: downgrade.transport)
    try require(downgradeResult.status == .blockedNewerInstalled, "newer installed map must never be downgraded")
}

private func testCrossComputerAbsenceNeverAuthorizesUpdate() async throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-update-owner-" + UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    for scenario in ["another-mac", "reinstalled-empty-state", "lost-local-manifest"] {
        let harness = makeHarness()
        let store = LocalTerentoManifestStore(rootDirectory: root.appendingPathComponent(scenario))
        let manifest = try store.read(deviceKey: harness.request.deviceKey)
        try require(manifest == nil, "scenario must have no durable local ownership")
        let current = harness.request.currentObject
        let metadata = GarminIMGMetadata(name: "France", provider: "freizeitkarte", region: "FRA",
            family: nil, rawVersion: nil, version: current.version, identifier: nil, productId: nil, familyId: nil)
        let ownership = MapOwnershipMatcher().managementState(for: current.file, metadata: metadata, records: [])
        try require(ownership == .detectedNotManaged, "Terento filename cannot replace missing ownership")
        let scanned = InstalledMap(name: "France", provider: "freizeitkarte", region: "FRA", family: nil,
            rawVersion: nil, version: current.version, identifier: nil, productId: nil, familyId: nil,
            sizeBytes: current.file.sizeBytes, sourceFile: current.file, metadataStatus: .parsed, managementState: ownership)
        let item = MapLifecycleItem(id: harness.request.currentItem.id, title: "France", provider: "freizeitkarte",
            region: "FRA", version: current.version, rawVersion: nil, sizeBytes: current.file.sizeBytes,
            installedMaps: [scanned], classification: .externalRecognized)
        let request = SafeUpdateRequest(deviceKey: harness.request.deviceKey, identity: harness.request.identity,
            profile: harness.request.profile, selectedMap: harness.request.selectedMap, comparison: harness.request.comparison,
            currentItem: item, currentObject: SafeUpdateRemoteObject(file: current.file, identity: current.identity,
            version: current.version, ownership: ownership, sha256: current.sha256),
            confirmed: true, deviceConnected: true,
            installationAuthorization: harness.request.installationAuthorization)
        let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator,
            manifestReconciler: harness.reconciler).run(request: withFixtureAuthorization(request), provider: harness.provider, transport: harness.transport)
        try require(result.status == .blockedNotManaged, "confirmed external Remove eligibility never grants managed Update")
        try require(harness.transport.events.isEmpty && !harness.reconciler.called,
                    "missing manifest must block before update transport or ownership reconciliation")
    }
}

private func snapshotObject(_ object: SafeUpdateRemoteObject, path: String? = nil,
                            filename: String? = nil, itemID: UInt32? = nil,
                            version: MapVersion? = nil, ownership: MapManagementState = .unknown,
                            hash: String? = nil, size: UInt64? = nil, identity: MapIdentity? = nil) -> SafeUpdateRemoteObject {
    SafeUpdateRemoteObject(file: InstalledMapFile(path: path ?? object.file.path,
        filename: filename ?? object.file.filename, sizeBytes: size ?? object.file.sizeBytes,
        itemID: itemID ?? object.file.itemID), identity: identity ?? object.identity,
        version: version ?? object.version, ownership: ownership, sha256: hash)
}

private func testPostCommitHandleRenumberAndReuse() async throws {
    for reuseOldHandle in [true, false] {
        let harness = makeHarness(withWorkspace: true)
        let old = harness.request.currentObject
        let unrelated = snapshotObject(harness.transport.newObject, path: "/GARMIN/protected-other.img",
            filename: "protected-other.img", itemID: 4000)
        harness.transport.objects.append(unrelated)
        harness.transport.postDeleteSnapshot = { objects in
            objects.map { object in
                object.file.path == unrelated.file.path
                    ? snapshotObject(object, itemID: reuseOldHandle ? old.file.itemID : unrelated.file.itemID)
                    : snapshotObject(object, itemID: reuseOldHandle ? object.file.itemID : (object.file.itemID ?? 0) + 1000)
            }
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-update-postverify-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalTerentoManifestStore(rootDirectory: root)
        try store.record(TerentoManifestEntry(deviceKey: harness.request.deviceKey,
            devicePath: old.file.path, filename: old.file.filename,
            providerId: old.identity.provider, regionId: old.identity.region,
            version: old.version!, sizeBytes: old.file.sizeBytes, sha256: old.sha256!, installedAt: Date()))
        let unrelatedEntry = manifestEntry(unrelated, deviceKey: harness.request.deviceKey)
        try store.record(unrelatedEntry)
        let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator,
            manifestReconciler: LocalSafeUpdateManifestReconciler(store: store))
            .run(request: withFixtureAuthorization(harness.request), provider: harness.provider, transport: harness.transport)
        let persisted = try store.read(deviceKey: harness.request.deviceKey)?.entries ?? []
        let sends = harness.transport.events.filter { $0 == "writeTransactionObject" }.count
        let deletes = harness.transport.events.filter { $0 == "deleteExactObject" }.count
        let diagnostic = "POSTVERIFY reuse=\(reuseOldHandle) status=\(result.status.rawValue) send=\(sends) delete=\(deletes) manifestOld=\(persisted.contains { $0.devicePath == old.file.path })\n"
        FileHandle.standardError.write(Data(diagnostic.utf8))
        try require(result.status == .success, "current snapshot handles must not invalidate verified replacement")
        try require(sends == 1 && deletes == 1, "postverification never repeats mutation")
        try require(harness.transport.objects.count == 2
            && harness.transport.objects.contains { $0.file.path == harness.transport.newObject.file.path }
            && !harness.transport.objects.contains { $0.file.path == old.file.path }
            && harness.transport.objects.contains(unrelated),
            "new target present, old stable path absent, preexisting unrelated map untouched")
        try require(persisted.count == 2 && persisted.contains(unrelatedEntry)
            && persisted.contains { $0.devicePath == harness.transport.newObject.file.path
                && $0.sha256 == harness.transport.newObject.sha256 },
            "durable manifest atomically advances to verified new target")
    }
}

private func finalSnapshotNegatives() -> [(String, (Harness) -> [SafeUpdateRemoteObject])] {
    let changes: [(String, (Harness) -> [SafeUpdateRemoteObject])] = [
        ("old path survives", { h in [snapshotObject(h.transport.newObject), snapshotObject(h.request.currentObject, itemID: 999)] }),
        ("new target missing", { _ in [] }),
        ("new identity changed", { h in [snapshotObject(h.transport.newObject, identity: MapIdentity(provider: "freizeitkarte", region: "DEU")!)] }),
        ("current handles duplicate", { h in [snapshotObject(h.transport.newObject, itemID: 99), snapshotObject(h.transport.newObject, path: "/GARMIN/other.img", filename: "other.img", itemID: 99)] }),
        ("current handle zero", { h in [snapshotObject(h.transport.newObject, itemID: 0)] }),
        ("case alias ambiguous", { h in [snapshotObject(h.transport.newObject), snapshotObject(h.transport.newObject, path: h.transport.newObject.file.path.uppercased(), itemID: 999)] }),
        ("new target ambiguous", { h in [snapshotObject(h.transport.newObject), snapshotObject(h.transport.newObject, itemID: 999)] }),
        ("new filename changed", { h in [snapshotObject(h.transport.newObject, filename: "other.img")] }),
        ("new size changed", { h in [snapshotObject(h.transport.newObject, size: h.transport.newObject.file.sizeBytes + 1)] }),
        ("new version changed", { h in [snapshotObject(h.transport.newObject, version: MapVersion(year: 2020, month: 1)!)] }),
        ("new hash contradicts verified content", { h in [snapshotObject(h.transport.newObject, hash: String(repeating: "c", count: 64))] }),
        ("new ownership contradicts managed proof", { h in [snapshotObject(h.transport.newObject, ownership: .detectedNotManaged)] })
    ]
    return changes
}

private func manifestEntry(_ object: SafeUpdateRemoteObject, deviceKey: String) -> TerentoManifestEntry {
    TerentoManifestEntry(deviceKey: deviceKey, devicePath: object.file.path,
        filename: object.file.filename, providerId: object.identity.provider,
        regionId: object.identity.region, version: object.version!,
        sizeBytes: object.file.sizeBytes, sha256: object.sha256 ?? String(repeating: "d", count: 64),
        installedAt: Date(timeIntervalSince1970: 123))
}

private func testRealReconcilerSnapshotNegatives() async throws {
    for (name, snapshot) in finalSnapshotNegatives() {
        let h = makeHarness()
        defer { try? FileManager.default.removeItem(at: h.artifact.localIMGURL) }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-reconciler-negative-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalTerentoManifestStore(rootDirectory: root)
        try store.record(manifestEntry(h.request.currentObject, deviceKey: h.request.deviceKey))
        try store.record(manifestEntry(snapshotObject(h.transport.newObject,
            path: "/GARMIN/other.img", filename: "other.img", itemID: 300), deviceKey: h.request.deviceKey))
        let before = try store.read(deviceKey: h.request.deviceKey)!.entries
        var rejected = false
        do {
            try LocalSafeUpdateManifestReconciler(store: store).reconcile(deviceKey: h.request.deviceKey,
                oldObject: h.request.currentObject, newObject: h.transport.newObject,
                package: h.package, finalObjects: snapshot(h))
        } catch { rejected = true }
        try require(rejected, "real reconciler rejects " + name)
        let after = try store.read(deviceKey: h.request.deviceKey)!.entries
        try require(after == before, "real reconciler preserves durable entries for " + name)
    }
}

private func testUpdateFinalSnapshotNegatives() async throws {
    for (name, snapshot) in finalSnapshotNegatives() {
        let harness = makeHarness(withWorkspace: true)
        let values = snapshot(harness)
        harness.transport.postDeleteSnapshot = { _ in values }
        let result = await run(harness)
        try require(!result.isSuccess && !harness.reconciler.called, "must reject final state: " + name)
        try require(harness.transport.events.filter { $0 == "writeTransactionObject" }.count == 1
            && harness.transport.events.filter { $0 == "deleteExactObject" }.count == 1,
            "negative final snapshot does not repeat mutations")
    }
}

private func rawFile(_ path: String, id: UInt32, storage: UInt32 = 1,
                     size: UInt64 = 10, folder: Bool = false, parent: UInt32 = 1) -> DeviceFile {
    DeviceFile(itemID: id, parentID: parent, storageID: storage, path: path,
        filename: String(path.split(separator: "/").last!), sizeBytes: size, isFolder: folder)
}

private func testProtectedUpdateTransitionMatrix() async throws {
    typealias Change = ([DeviceFile], Harness) -> [DeviceFile]
    let cases: [(String, Bool, Change)] = [
        ("only replacement", true, { files, _ in files }),
        ("all handles renumber", true, { files, _ in files.map {
            rawFile($0.path, id: $0.itemID + 10000, storage: $0.storageID,
                size: $0.sizeBytes, folder: $0.isFolder, parent: $0.parentID + 10000)
        } }),
        ("historical handle reused", true, { files, h in files.map {
            $0.path == "/GARMIN/external.img"
                ? rawFile($0.path, id: h.request.currentObject.file.itemID!) : $0
        } }),
        ("exact device XML churn", true, { files, _ in files.map {
            $0.path == "/GARMIN/GarminDevice.xml" ? rawFile($0.path, id: $0.itemID, size: 300) : $0
        } }),
        ("typed Monitor FIT churn", true, { files, _ in
            files.filter { $0.path != "/GARMIN/Monitor/old.fit" }
                + [rawFile("/GARMIN/Monitor/new.fit", id: 990, size: 789)]
        }),
        ("Garmin map removed", false, { files, _ in files.filter { $0.path != "/GARMIN/D123.img" } }),
        ("third party removed", false, { files, _ in files.filter { $0.path != "/GARMIN/external.img" } }),
        ("protected added", false, { files, _ in files + [rawFile("/GARMIN/extra.img", id: 990)] }),
        ("protected renamed", false, { files, _ in files.map {
            $0.path == "/GARMIN/external.img" ? rawFile("/GARMIN/moved.img", id: $0.itemID) : $0
        } }),
        ("protected size changed", false, { files, _ in files.map {
            $0.path == "/GARMIN/external.img" ? rawFile($0.path, id: $0.itemID, size: 999) : $0
        } }),
        ("protected storage changed", false, { files, _ in
            files.map { $0.path == "/GARMIN/external.img" ? rawFile($0.path, id: $0.itemID, storage: 2) : $0 }
                + [rawFile("/GARMIN", id: 991, storage: 2, size: 0, folder: true)]
        }),
        ("protected kind changed", false, { files, _ in files.map {
            $0.path == "/GARMIN/external.img" ? rawFile($0.path, id: $0.itemID, folder: true) : $0
        } }),
        ("duplicate identity", false, { files, _ in files + [rawFile("/GARMIN/external.img", id: 990)] }),
        ("case alias ambiguity", false, { files, _ in files + [rawFile("/GARMIN/EXTERNAL.IMG", id: 990)] }),
        ("unknown companion changed", false, { files, _ in files.map {
            $0.path == "/GARMIN/unknown-companion" ? rawFile($0.path, id: $0.itemID, size: 999) : $0
        } }),
        ("old remains", false, { files, h in files + [rawFile(h.request.currentObject.file.path, id: 990, size: h.request.currentObject.file.sizeBytes)] }),
        ("new missing", false, { files, h in files.filter { $0.path != h.transport.newObject.file.path } }),
        ("new wrong path", false, { files, h in files.map {
            $0.path == h.transport.newObject.file.path ? rawFile("/GARMIN/wrong.img", id: $0.itemID, size: $0.sizeBytes) : $0
        } }),
        ("new wrong size", false, { files, h in files.map {
            $0.path == h.transport.newObject.file.path ? rawFile($0.path, id: $0.itemID, size: 999) : $0
        } }),
        ("new folder", false, { files, h in files.map {
            $0.path == h.transport.newObject.file.path ? rawFile($0.path, id: $0.itemID, size: $0.sizeBytes, folder: true) : $0
        } }),
        ("duplicate current handle", false, { files, h in files + [rawFile("/GARMIN/extra.img", id: h.transport.newObject.file.itemID!)] }),
        ("unknown XML not exempt", false, { files, _ in files.map {
            $0.path == "/GARMIN/unknown.xml" ? rawFile($0.path, id: $0.itemID, size: 999) : $0
        } }),
        ("unknown FIT not exempt", false, { files, _ in files.map {
            $0.path == "/GARMIN/unknown.fit" ? rawFile($0.path, id: $0.itemID, size: 999) : $0
        } })
    ]
    for (name, success, change) in cases {
        let h = makeHarness(withWorkspace: true)
        h.transport.rawSnapshotTransform = { files, final in
            let full = files + [rawFile("/GARMIN/D123.img", id: 500),
                rawFile("/GARMIN/external.img", id: 501),
                rawFile("/GARMIN/unknown-companion", id: 502),
                rawFile("/GARMIN/GarminDevice.xml", id: 503),
                rawFile("/GARMIN/Monitor", id: 504, size: 0, folder: true),
                rawFile("/GARMIN/Monitor/old.fit", id: 505),
                rawFile("/GARMIN/unknown.xml", id: 506),
                rawFile("/GARMIN/unknown.fit", id: 507)]
            return final ? change(full, h) : full
        }
        let result = await run(h)
        try require(result.isSuccess == success, "protected transition outcome: " + name)
        try require(h.reconciler.called == success, "protected failure must not reconcile: " + name)
        try require(!result.oldMapPreserved, "successful delete must be reported truthfully: " + name)
        try require(h.transport.events.filter { $0 == "writeTransactionObject" }.count == 1
            && h.transport.events.filter { $0 == "deleteExactObject" }.count == 1
            && !h.transport.events.contains("cleanupTransactionObject"),
            "protected post-delete failure never retries or cleans up: " + name)
        print("PASS: protected update " + name)
    }
}

private func testProtectedBaselineRefusesBeforeSend() async throws {
    for kind in 0..<5 {
        let h = makeHarness(withWorkspace: true)
        h.transport.rawSnapshotTransform = { files, _ in
            switch kind {
            case 0: throw SafeUpdateTransportError.operationFailed("physical binding mismatch")
            case 1: return files + [files[0]]
            case 2: return files.filter { $0.path != h.request.currentObject.file.path }
            case 3: return files + [rawFile(h.transport.newObject.file.path, id: 999)]
            default: return files + [rawFile("/GARMIN/missing/child.img", id: 999)]
            }
        }
        let result = await run(h)
        try require(!result.isSuccess && result.oldMapPreserved && !h.reconciler.called,
            "invalid baseline must refuse before mutation")
        try require(!h.transport.events.contains("writeTransactionObject")
            && !h.transport.events.contains("deleteExactObject"), "baseline failure has zero mutations")
    }
}

private func testDeletePostVerifyFailureReportsDeletion() async throws {
    let h = makeHarness(withWorkspace: true)
    h.transport.postDeleteSnapshot = { $0 + [h.request.currentObject] }
    let result = await run(h)
    try require(result.status == .failedCommit && !result.oldMapPreserved,
        "delete completed but absence unverifiable must not claim old preserved")
    try require(h.transport.events.filter { $0 == "deleteExactObject" }.count == 1
        && !h.reconciler.called, "failed post-delete verification must not retry or reconcile")
}

private func testProtectedFinalReadFailure() async throws {
    let h = makeHarness(withWorkspace: true)
    h.transport.rawSnapshotTransform = { files, final in
        if final { throw SafeUpdateTransportError.operationFailed("bound raw inventory unavailable") }
        return files
    }
    let result = await run(h)
    try require(result.status == .failedPostVerify && !result.oldMapPreserved && !h.reconciler.called,
        "final raw read failure after deletion must retain actual state and no manifest success")
    try require(h.transport.events.filter { $0 == "deleteExactObject" }.count == 1
        && !h.transport.events.contains("cleanupTransactionObject"), "final read failure never mutates again")
}

private func testAmbiguousDeleteOutcomeIsNotPreserved() async throws {
    for mode: FakeSafeUpdateTransport.Mode in [.deleteFailure, .deleteDisconnected, .oldMissingBeforeDelete] {
        let h = makeHarness(withWorkspace: true)
        h.transport.mode = mode
        let result = await run(h)
        try require(result.status == .failedCommit && !result.oldMapPreserved && !h.reconciler.called,
            "unknown delete result cannot promise preserved old map or clean manifest")
        try require(result.message.contains("could not be confirmed"), "unknown outcome message stays truthful")
        try require(h.transport.events.filter { $0 == "deleteExactObject" }.count == (mode == .oldMissingBeforeDelete ? 0 : 1)
            && !h.transport.events.contains("cleanupTransactionObject"), "unknown delete never retries or cleans up")
    }
}

private func testPostCommitHandleRenumberPreservesSuccessfulUpdate() async throws {
    let harness = makeHarness(withWorkspace: true)
    harness.transport.renumberAfterOldDeletion = true
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-update-renumber-repro-" + UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    let store = LocalTerentoManifestStore(rootDirectory: root)
    let old = harness.request.currentObject
    try store.record(TerentoManifestEntry(deviceKey: harness.request.deviceKey,
        devicePath: old.file.path, filename: old.file.filename,
        providerId: old.identity.provider, regionId: old.identity.region,
        version: old.version!, sizeBytes: old.file.sizeBytes, sha256: old.sha256!, installedAt: Date()))
    let result = await SafeUpdateTransaction(gate: harness.gate, sourceValidator: harness.validator,
        manifestReconciler: LocalSafeUpdateManifestReconciler(store: store))
        .run(request: withFixtureAuthorization(harness.request), provider: harness.provider, transport: harness.transport)
    let persisted = try store.read(deviceKey: harness.request.deviceKey)?.entries ?? []
    let sends = harness.transport.events.filter { $0 == "writeTransactionObject" }.count
    let deletes = harness.transport.events.filter { $0 == "deleteExactObject" }.count
    let oldPresent = harness.transport.objects.contains { $0.file.path == old.file.path }
    let newPresent = harness.transport.objects.contains { $0.file.path == harness.transport.newObject.file.path }
    let manifestStillOld = persisted.contains { $0.devicePath == old.file.path }
    let diagnostic = "REPRO: handle-only post-commit renumber status=\(result.status.rawValue) send=\(sends) delete=\(deletes) oldPresent=\(oldPresent) newPresent=\(newPresent) manifestStillOld=\(manifestStillOld)\n"
    FileHandle.standardError.write(Data(diagnostic.utf8))
    try require(result.status == .success, "handle-only post-commit renumber must not fail the already committed update")
    try require(sends == 1 && deletes == 1 && !oldPresent && newPresent,
                "safe update must send once, verify, delete old once and retain new")
    try require(persisted.count == 1 && persisted[0].devicePath == harness.transport.newObject.file.path,
                "durable manifest must advance to the verified new map despite handle renumbering")
}

@main
struct Stage53SafeUpdateTests {
    static func main() async throws {
        let tests: [(String, () async throws -> Void)] = [
            ("successful update and ordering", testSuccessfulUpdateAndOrdering),
            ("protected replacement full raw matrix", testProtectedUpdateTransitionMatrix),
            ("protected baseline and binding gate", testProtectedBaselineRefusesBeforeSend),
            ("truthful delete postverify failure", testDeletePostVerifyFailureReportsDeletion),
            ("protected final read failure", testProtectedFinalReadFailure),
            ("ambiguous delete outcome", testAmbiguousDeleteOutcomeIsNotPreserved),
            ("post-commit handle renumber retains success", testPostCommitHandleRenumberPreservesSuccessfulUpdate),
            ("post-commit renumber and old-handle reuse", testPostCommitHandleRenumberAndReuse),
            ("update final snapshot safety negatives", testUpdateFinalSnapshotNegatives),
            ("real reconciler durable negative guards", testRealReconcilerSnapshotNegatives),
            ("install failure acquisition cleanup", testInstallFailureRemovesAcquisitionWorkspace),
            ("no-update and ownership gates", testNoUpdateAndOwnershipAreBlockedBeforeTransport),
            ("installation authorization gate", testInstallationAuthorizationIsCheckedBeforeUpdateAcquisition),
            ("fresh update authorization", testFreshUpdateAuthorization),
            ("temporary installation authorization gate", testUnavailableInstallationAuthorizationIsRetryable),
            ("cross-computer and state-loss update refusal", testCrossComputerAbsenceNeverAuthorizesUpdate),
            ("current-object revalidation", testCurrentObjectChangedStopsBeforeWrite),
            ("map identity gate", testMismatchedMapIdentityIsBlockedBeforeTransport),
            ("storage gate and backup-free update", testStorageGateAndBackupFreeUpdate),
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

import CryptoKit
import Foundation

// This executable never creates an MTP transport or calls a native device API.
// Ledger outcomes below describe injected I/O, not native authorization evidence.
extension Bundle { static var module: Bundle { .main } }
@_silgen_name("terento_cleanup_forbidden_calls") private func forbiddenNativeCalls() -> Int32
private enum SimulationError: Error { case refused(String) }
private func check(_ value: @autoclosure () -> Bool, _ message: String) throws {
    if !value() { throw SimulationError.refused(message) }
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
private func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
private let oldPath = "/GARMIN/terento_freizeitkarte_fra.img"
private let newPath = "/GARMIN/terento_freizeitkarte_fra_2026-06.img"
private func identity(_ serial: String? = "SIMULATED-WATCH-A") -> DeviceIdentity {
    DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 47mm", family: "fēnix", variant: nil,
        usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: "local-fixture",
        storageCapacity: 32_000_000_000, freeSpace: 16_000_000_000, localHardwareIdentifier: serial)
}
private func package(_ month: Int) -> MapPackage {
    MapPackage(id: "freizeitkarte-fra", providerId: "freizeitkarte", regionId: "FRA", name: "France",
        version: MapVersion(year: 2026, month: month)!, sizeBytes: 4096,
        sourceURL: URL(string: "https://provider.invalid/local-fixture.zip"), releaseDate: nil,
        identifier: "FRA+", installSizeBytes: 4096)
}
private func image(_ month: Int) -> Data {
    var bytes = [UInt8](repeating: 0, count: 4096)
    for (offset, text) in [(0x10, "DSKIMG"), (0x41, "GARMIN"),
        (0x100, "Freizeitkarte_FRA+"), (0x200, String(format: "Release 26.%02d", month))] {
        for (index, byte) in text.utf8.enumerated() { bytes[offset + index] = byte }
    }
    return Data(bytes)
}
private func artifact(_ month: Int, root: URL) throws -> ValidatedMapArtifact {
    let p = package(month), data = image(month)
    let url = root.appendingPathComponent("source-\(month).img")
    try data.write(to: url)
    _ = try MapSourceValidator().validate(fileURL: url, expectedPackage: p)
    return ValidatedMapArtifact(provider: "freizeitkarte", region: "FRA", canonicalRegion: "France",
        rawRelease: String(format: "Release 26.%02d", month), version: p.version, localIMGURL: url,
        installSizeBytes: UInt64(data.count), sha256: hash(data), sourcePackageURL: p.sourceURL!,
        catalogPackageID: p.id, targetFilename: "terento_freizeitkarte_fra.img", downloadSizeBytes: 4096,
        catalogDownloadSizeBytes: 4096, downloadSizeMatchesCatalog: true, packageFormat: .zip)
}

private final class LocalDevice: InstallationDeviceReader, @unchecked Sendable {
    var serial = "SIMULATED-WATCH-A"
    var bytes: [String: Data] = ["/GARMIN/D123.img": Data(repeating: 7, count: 64)]
    var handles: [String: UInt32] = ["/GARMIN": 1, "/GARMIN/D123.img": 2]
    var nextID: UInt32 = 20
    func put(_ data: Data, path: String) -> UInt32 {
        bytes[path] = data; nextID += 1; handles[path] = nextID; return nextID
    }
    func readFileInventory() throws -> [DeviceFile] {
        handles.keys.sorted().map { path in
            DeviceFile(itemID: handles[path]!, parentID: path == "/GARMIN" ? 0 : handles["/GARMIN"]!,
                storageID: 1, path: path, filename: String(path.split(separator: "/").last!),
                sizeBytes: UInt64(bytes[path]?.count ?? 0), isFolder: path == "/GARMIN")
        }
    }
    func readSnapshot() throws -> DeviceSnapshot {
        DeviceSnapshot(manufacturer: "Garmin", model: "fenix 8 - 47mm", deviceVersion: "local-fixture",
            vendorID: 0x091e, productID: 0x51b8, storages: [.init(id: 1, description: "fixture",
                volumeIdentifier: "GARMIN", maximumCapacity: 32_000_000_000, freeSpace: 16_000_000_000)], serialNumber: serial)
    }
    func reconnect(reuse: UInt32? = nil) {
        for path in handles.keys.sorted() { nextID += 1; handles[path] = nextID }
        if let reuse { handles["/GARMIN/D123.img"] = reuse }
    }
    func remote(_ path: String, managed: Bool = true, withHash: Bool = true) throws -> SafeUpdateRemoteObject {
        guard let data = bytes[path], let id = handles[path],
              let metadata = GarminIMGMetadataParser().parse(Array(data), filename: String(path.split(separator: "/").last!)),
              let mapID = MapIdentity(provider: metadata.provider, region: metadata.region) else {
            throw SimulationError.refused("missing or invalid fixture map")
        }
        return SafeUpdateRemoteObject(file: InstalledMapFile(path: path, filename: String(path.split(separator: "/").last!),
            sizeBytes: UInt64(data.count), itemID: id), identity: mapID, version: metadata.version,
            ownership: managed ? .managedByTerento : .unknown, sha256: withHash ? hash(data) : nil)
    }
}

private class LocalLedgerIO: @unchecked Sendable {
    let device: LocalDevice
    let operation: NativeMutationOperation
    var sends = 0, deletes = 0
    var incompleteSend = false
    var lastLedger: NativeMutationLedger?
    init(_ device: LocalDevice, mode: MapMutationPurpose, root: URL) {
        self.device = device; operation = NativeMutationOperation(mode: mode, root: root)
    }
    func scope(_ path: String, data: Data, content: Bool) -> NativeMutationLedger.Scope {
        .init(physicalIdentifierSource: 1, physicalIdentifier: "SIMULATED-WATCH-A", expectedStorageID: 1,
            filename: String(path.split(separator: "/").last!), size: UInt64(data.count), sha256: content ? hash(data) : nil)
    }
    func bound() throws { try check(device.serial == "SIMULATED-WATCH-A", "physical substitution") }
    func send(_ data: Data, path: String, purpose: MapMutationPurpose) throws -> UInt32 {
        try bound()
        var ledger = try operation.begin(purpose: purpose, scope: scope(path, data: data, content: false))
        try ledger.dispatch(); sends += 1
        let id = device.put(data, path: path)
        do { try ledger.finish(.init(authorized: true, attempted: true, completed: !incompleteSend,
            nativeResult: 0, resultingObjectID: id, sessionID: UInt64(sends), sequence: ledger.sequence,
            purpose: purpose.rawValue, kind: purpose.kind), returnedResult: 0) }
        catch { lastLedger = ledger; throw error }
        lastLedger = ledger; return id
    }
}
private final class LocalInstallIO: LocalLedgerIO, MapInstallationTransport, @unchecked Sendable {
    func write(sourceURL: URL, targetFilename: String, progress: @escaping @Sendable (TransferProgress) -> Void) throws -> MTPWrittenMapObject {
        let data = try Data(contentsOf: sourceURL)
        let id = try send(data, path: "/GARMIN/" + targetFilename, purpose: .install)
        progress(.init(bytesTransferred: UInt64(data.count), totalBytes: UInt64(data.count), bytesPerSecond: 4096))
        return .init(itemID: id, sizeBytes: UInt64(data.count))
    }
    func readBack(sourceURL: URL, targetFilename: String, expectedItemID: UInt32, targetPath: String,
                  expectedSizeBytes: UInt64, sampleOffsets: [UInt64], sampleLength: UInt32,
                  progress: @escaping @Sendable (TransferProgress) -> Void) throws -> MTPReadBackMapObject {
        let source = try Data(contentsOf: sourceURL)
        try check(device.bytes[targetPath] == source, "install complete byte comparison")
        let count = sampleOffsets.reduce(UInt64(0)) { $0 + min(UInt64(sampleLength), expectedSizeBytes - $1) }
        return .init(itemID: device.handles[targetPath]!, targetPath: targetPath, reportedSizeBytes: expectedSizeBytes,
            sampledBytes: count, sampleCount: sampleOffsets.count, matchedSampleCount: sampleOffsets.count)
    }
    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws { throw CleanupIdentityUnproven() }
}
private final class LocalUpdateIO: LocalLedgerIO, SafeUpdateTransport, @unchecked Sendable {
    var corruptVerification = false, protectedDelta = false
    func inspectCurrentObject(_ expected: SafeUpdateRemoteObject) throws -> SafeUpdateRemoteObject {
        try bound()
        let current = try device.remote(expected.file.path)
        try operation.bindOldTarget(scope: scope(expected.file.path, data: device.bytes[expected.file.path]!, content: true))
        return current
    }
    func writeTransactionObject(sourceURL: URL, targetPath: String, onProgress: (@Sendable (TransferProgress) -> Void)?) throws -> SafeUpdateRemoteObject {
        _ = try send(Data(contentsOf: sourceURL), path: targetPath, purpose: .updateNew)
        return try device.remote(targetPath)
    }
    func verifyTransactionObject(_ object: SafeUpdateRemoteObject, expected: SafeUpdateSourceArtifact) throws -> SafeUpdateRemoteObject {
        if corruptVerification { throw SafeUpdateTransportError.hashMismatch }
        let verified = try device.remote(object.file.path)
        try check(verified.sha256 == expected.sha256, "full replacement SHA verification")
        try operation.markUpdateVerified(filename: verified.file.filename, size: verified.file.sizeBytes, sha256: verified.sha256!)
        return verified
    }
    func cleanupTransactionObject(_ object: SafeUpdateRemoteObject) throws { throw CleanupIdentityUnproven() }
    func readFreeSpace() throws -> UInt64 { 16_000_000_000 }
    func readProtectedInventory() throws -> SafeUpdateInventorySnapshot {
        try bound(); return .init(storageID: 1, files: try device.readFileInventory())
    }
    func rescanObjects() throws -> [SafeUpdateRemoteObject] {
        try device.bytes.keys.filter { $0.hasPrefix("/GARMIN/terento_") }.sorted().map {
            try device.remote($0, managed: false, withHash: false)
        }
    }
    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        try bound(); let current = try device.remote(target.expectedPath)
        return .init(file: current.file, sha256: current.sha256!)
    }
    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        try bound(); let data = device.bytes[target.expectedPath]!
        try check(hash(data) == target.expectedSHA256, "old exact content recheck")
        var ledger = try operation.begin(purpose: .updateOld, scope: scope(target.expectedPath, data: data, content: true))
        try ledger.dispatch(); deletes += 1
        let id = device.handles[target.expectedPath]!
        device.bytes.removeValue(forKey: target.expectedPath); device.handles.removeValue(forKey: target.expectedPath)
        try ledger.finish(.init(authorized: true, attempted: true, completed: true, nativeResult: 0,
            resultingObjectID: id, sessionID: 2, sequence: ledger.sequence, purpose: 3, kind: 2), returnedResult: 0)
        lastLedger = ledger
        device.reconnect(reuse: id)
        if protectedDelta { device.bytes["/GARMIN/D123.img"] = Data([0]) }
    }
}
private struct LocalProvider: SafeUpdateArtifactProvider {
    let artifact: SafeUpdateSourceArtifact
    func acquire(package: MapPackage, onProgress: (@Sendable (SafeUpdateProgress) -> Void)?) async throws -> SafeUpdateSourceArtifact { artifact }
}

private func installed(_ device: LocalDevice, records: [TerentoManifestEntry]) throws -> InstalledMap {
    let current = try device.remote(oldPath)
    let meta = GarminIMGMetadataParser().parse(Array(device.bytes[oldPath]!), filename: current.file.filename)!
    let ownership = records.map { MapOwnershipRecord(devicePath: $0.devicePath, filename: $0.filename,
        providerId: $0.providerId, regionId: $0.regionId, version: $0.version, sizeBytes: $0.sizeBytes) }
    let state = MapOwnershipMatcher().managementState(for: current.file, metadata: meta, records: ownership)
    return InstalledMap(name: "France", provider: meta.provider, region: meta.region, family: meta.family,
        rawVersion: meta.rawVersion, version: meta.version, identifier: meta.identifier,
        productId: meta.productId, familyId: meta.familyId, sizeBytes: current.file.sizeBytes,
        sourceFile: current.file, metadataStatus: .parsed, managementState: state)
}
private let provider = MapProvider(id: "freizeitkarte", name: "Freizeitkarte", website: nil, attribution: nil, licenseURL: nil)
private let region = MapRegion(id: "FRA", name: "France", country: "FR", providerId: "freizeitkarte")

@main
struct LocalManagedUpdateSimulationTests {
    static func main() async throws {
        guard let home = ProcessInfo.processInfo.environment["CFFIXED_USER_HOME"],
              FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?.resolvingSymlinksInPath().path.hasPrefix(URL(fileURLWithPath: home).resolvingSymlinksInPath().path + "/") == true else {
            throw SimulationError.refused("runner must isolate all default application-support state")
        }
        for scenario in ["success", "no-manifest", "state-loss", "legacy", "wrong-device", "live-substitution", "target-changed", "source-changed",
                         "new-verification", "protected-delta", "incomplete-ledger"] {
            try await run(scenario)
            try check(forbiddenNativeCalls() == 0, "local fixture must never enter native device I/O")
        }
        print("PASS: local managed update production coordinators; injected I/O + real ledger evidence (native authorization tested separately)")
    }
    private static func run(_ scenario: String) async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-local-update-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let manifestRoot = root.appendingPathComponent("manifests"), ledgerRoot = root.appendingPathComponent("ledger")
        let store = LocalTerentoManifestStore(rootDirectory: manifestRoot)
        let device = LocalDevice(), initialProtected = device.bytes["/GARMIN/D123.img"]!
        let v1 = try artifact(5, root: root), v2 = try artifact(6, root: root)
        let id = identity(), profile = DeviceInstallProfileRegistry.local.profile(for: id)
        try check(id.physicalManifestDeviceKey?.hasPrefix("watch-v2-") == true, "fixture physical namespace must be available")
        let installer = LocalInstallIO(device, mode: .install, root: ledgerRoot)
        let initialComparison = MapComparisonEngine().compare(installedMaps: [], provider: provider, region: region, catalogMap: package(5))
        let result = MapInstallationCoordinator(transport: installer, deviceReader: device, manifestStore: store,
            recoveryStore: LocalTerentoFailedInstallRecoveryStore(rootDirectory: root.appendingPathComponent("recovery")),
            transactionGate: InstallationTransactionGate()).run(.init(identity: id, selectedMap: package(5),
            comparison: initialComparison, installedMaps: [], inspectedFiles: [], beforeDeviceFiles: try device.readFileInventory(),
                availableStorage: 16_000_000_000, profile: profile, artifact: v1, userConfirmed: true,
                installationAuthorization: approvedAuthorization(for: id)))
        try check(result.isSuccess && installer.sends == 1 && installer.deletes == 0, "real v1 install failed: \(result.status)")
        device.reconnect()
        // Reopened store models a new app process/version; ownership has no app-version dependency.
        let reopened = LocalTerentoManifestStore(rootDirectory: manifestRoot)
        let durable = try reopened.read(deviceKey: id.localManifestDeviceKey)!.entries
        try check(durable.count == 1 && durable[0].sha256 == v1.sha256, "install must durably own v1")
        let currentIdentity = scenario == "wrong-device" ? identity("SIMULATED-WATCH-B") : id
        let keys = MapEngine.manifestDeviceKeys(for: [id, currentIdentity])
        var entries = try keys.flatMap { try reopened.read(deviceKey: $0)?.entries ?? [] }
        if scenario == "no-manifest" || scenario == "state-loss" { entries = try LocalTerentoManifestStore(rootDirectory: root.appendingPathComponent("other-mac")).read(deviceKey: id.localManifestDeviceKey)?.entries ?? [] }
        if scenario == "legacy" {
            let modelOnly = identity(nil)
            let old = durable[0]
            try reopened.record(TerentoManifestEntry(deviceKey: modelOnly.localManifestDeviceKey,
                devicePath: old.devicePath, filename: old.filename, providerId: old.providerId,
                regionId: old.regionId, version: old.version, sizeBytes: old.sizeBytes,
                sha256: old.sha256, installedAt: old.installedAt))
            let legacyKeys = MapEngine.manifestDeviceKeys(for: [id, modelOnly])
            try check(legacyKeys.isEmpty, "legacy namespace must never confer ownership")
            entries = try legacyKeys.flatMap { try reopened.read(deviceKey: $0)?.entries ?? [] }
        }
        let map = try installed(device, records: entries)
        let comparison = MapComparisonEngine().compare(installedMaps: [map], provider: provider, region: region, catalogMap: package(6))
        try check(comparison.status == .updateAvailable, "actual version comparison")
        let current = try device.remote(oldPath)
        let owned = map.managementState == .managedByTerento
        let item = MapLifecycleItem(id: "fra", title: "France", provider: "freizeitkarte", region: "FRA",
            version: map.version, rawVersion: map.rawVersion, sizeBytes: map.sizeBytes, installedMaps: [map],
            classification: owned ? .terentoManaged : .externalRecognized)
        let request = SafeUpdateRequest(deviceKey: id.localManifestDeviceKey, identity: currentIdentity,
            profile: profile, selectedMap: package(6), comparison: comparison, currentItem: item,
            currentObject: .init(file: current.file, identity: current.identity, version: current.version,
                ownership: owned ? .managedByTerento : .detectedNotManaged, sha256: entries.first?.sha256),
            confirmed: true, deviceConnected: true,
            installationAuthorization: approvedAuthorization(for: currentIdentity),
            authorizationRefresh: { identity in approvedAuthorization(for: identity) },
            currentIdentity: { currentIdentity })
        let updater = LocalUpdateIO(device, mode: .updateNew, root: ledgerRoot)
        if scenario == "wrong-device" || scenario == "live-substitution" { device.serial = "SIMULATED-WATCH-B" }
        if scenario == "target-changed" { device.bytes[oldPath]![1000] = 1 }
        if scenario == "source-changed" { try Data([1]).write(to: v2.localIMGURL) }
        updater.corruptVerification = scenario == "new-verification"
        updater.protectedDelta = scenario == "protected-delta"
        updater.incompleteSend = scenario == "incomplete-ledger"
        let update = await SafeUpdateTransaction(gate: InstallationTransactionGate(),
            manifestReconciler: LocalSafeUpdateManifestReconciler(store: reopened)).run(request: request,
                provider: LocalProvider(artifact: SafeUpdateSourceArtifact(v2)), transport: updater)
        let after = try reopened.read(deviceKey: id.localManifestDeviceKey)!.entries
        if scenario == "success" {
            try check(update.isSuccess && updater.sends == 1 && updater.deletes == 1, "real update success/counters: \(update.status.rawValue) \(update.message) send=\(updater.sends) delete=\(updater.deletes)")
            try check(device.bytes[oldPath] == nil && device.bytes[newPath] == image(6), "only intended replacement")
            try check(after.count == 1 && after[0].devicePath == newPath && after[0].sha256 == v2.sha256, "manifest v2 committed")
            try check(device.bytes["/GARMIN/D123.img"] == initialProtected, "protected bytes preserved")
            let opRoot = ledgerRoot.appendingPathComponent(updater.operation.operationID)
            for step in [1, 2] {
                let record = try JSONSerialization.jsonObject(with: Data(contentsOf: opRoot.appendingPathComponent("record-\(step).json"))) as! [String: Any]
                try check(record["phase"] as? String == "completed" && record["sequence"] as? Int == step, "durable ordered ledger")
            }
            let before = (updater.sends, updater.deletes)
            do { _ = try updater.operation.begin(purpose: .updateNew, scope: updater.scope(newPath, data: image(6), content: false)); throw SimulationError.refused("extra send accepted") }
            catch NativeMutationLedger.Failure.invalidTransition { }
            do { _ = try updater.operation.begin(purpose: .updateOld, scope: updater.scope(oldPath, data: image(5), content: true)); throw SimulationError.refused("extra delete accepted") }
            catch NativeMutationLedger.Failure.invalidTransition { }
            if var replay = updater.lastLedger {
                do { try replay.dispatch(); throw SimulationError.refused("ledger replay accepted") }
                catch NativeMutationLedger.Failure.invalidTransition { }
            }
            try check(updater.sends == before.0 && updater.deletes == before.1, "rejected grants never reach fake I/O")
        } else {
            try check(!update.isSuccess && after == durable, "failure must retain old ownership evidence: " + scenario)
            let expectedSend = ["new-verification", "protected-delta", "incomplete-ledger"].contains(scenario) ? 1 : 0
            let expectedDelete = scenario == "protected-delta" ? 1 : 0
            try check(updater.sends == expectedSend && updater.deletes == expectedDelete, "negative counters: " + scenario)
            if expectedDelete == 0 { try check(device.bytes[oldPath] != nil, "old remains on precommit failure") }
        }
        print("PASS: local update \(scenario) installSend=\(installer.sends) updateSend=\(updater.sends) updateDelete=\(updater.deletes) status=\(update.status.rawValue)")
    }
}

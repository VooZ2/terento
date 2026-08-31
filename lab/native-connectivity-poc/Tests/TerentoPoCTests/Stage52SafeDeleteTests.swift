import CryptoKit
import Foundation

protocol DeviceFileReader: Sendable {
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

private final class FakeSafeDeleteTransport: SafeDeleteTransport, @unchecked Sendable {
    var events: [String] = []
    var deletedObjectIDs: [UInt32] = []
    var currentObject: SafeDeleteDeviceObject?
    var deleteError: SafeDeleteTransportError?

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        events.append("inspect")
        guard let currentObject else {
            throw SafeDeleteTransportError.objectNotFound
        }
        return currentObject
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        events.append("delete")
        deletedObjectIDs.append(target.objectID)
        if let deleteError {
            throw deleteError
        }
    }
}

private final class ProgressCollector: @unchecked Sendable {
    private(set) var values: [SafeDeleteProgress] = []

    func append(_ value: SafeDeleteProgress) {
        values.append(value)
    }
}

private final class FakeManifestCleanupStore: TerentoManifestCleanupStore, @unchecked Sendable {
    var removed: [(deviceKey: String, devicePath: String, filename: String)] = []
    var shouldFail = false

    func remove(deviceKey: String, devicePath: String, filename: String) throws -> Bool {
        if shouldFail {
            throw TerentoManifestStoreError.cleanupFailed
        }

        removed.append((deviceKey, devicePath, filename))
        return true
    }
}

private final class SafeDeleteScanSequence: @unchecked Sendable {
    private var index = 0
    private let scans: [[InstalledMapFile]]

    init(_ scans: [[InstalledMapFile]]) {
        self.scans = scans
    }

    func next() -> [InstalledMapFile] {
        defer { index += 1 }
        return scans[min(index, scans.count - 1)]
    }
}

private enum Stage52TestError: Error {
    case failed(String)
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else {
        throw Stage52TestError.failed(message)
    }
}

private func sha256(_ data: Data) -> String {
    SHA256.hash(data: data)
        .map { String(format: "%02x", $0) }
        .joined()
}

private func validTarget(
    ownership: MapManagementState = .managedByTerento,
    backup: VerifiedBackupFile? = nil
) -> (target: SafeDeleteTarget, contents: Data) {
    let contents = Data(repeating: 0x41, count: 12)
    let hash = sha256(contents)
    let identity = MapIdentity(provider: "Freizeitkarte", region: "FRA")!
    let file = InstalledMapFile(
        path: "/GARMIN/terento_freizeitkarte_fra.img",
        filename: "terento_freizeitkarte_fra.img",
        sizeBytes: UInt64(contents.count),
        itemID: 101
    )
    let target = SafeDeleteTarget(
        deviceKey: "fenix-8-091e-51b8",
        mapIdentity: identity,
        ownership: ownership,
        objectID: 101,
        expectedPath: file.path,
        expectedFilename: file.filename,
        expectedSizeBytes: file.sizeBytes,
        expectedSHA256: hash,
        backup: backup
    )
    return (target, contents)
}

private func externalTarget() -> (target: SafeDeleteTarget, contents: Data) {
    let contents = Data(repeating: 0x4F, count: 12)
    let identity = MapIdentity(provider: "external", region: "otm-lithuania-contours")!
    let file = InstalledMapFile(
        path: "/GARMIN/otm-lithuania-contours.img",
        filename: "otm-lithuania-contours.img",
        sizeBytes: UInt64(contents.count),
        itemID: 303
    )
    let target = SafeDeleteTarget(
        deviceKey: "fenix-8-091e-51b8",
        mapIdentity: identity,
        ownership: .detectedNotManaged,
        objectID: 303,
        expectedPath: file.path,
        expectedFilename: file.filename,
        expectedSizeBytes: file.sizeBytes,
        expectedSHA256: "",
        backup: nil,
        allowsExternalRemoval: true
    )
    return (target, contents)
}

private func targetWithVerifiedBackup() throws -> (target: SafeDeleteTarget, contents: Data, backupURL: URL) {
    let initial = validTarget()
    let backupURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage52-backup-(UUID().uuidString).img")
    try initial.contents.write(to: backupURL, options: .atomic)

    let source = MapLifecycleFileIdentity(file: initial.target.sourceFile)!
    let backup = VerifiedBackupFile(
        source: source,
        localURL: backupURL,
        sizeBytes: initial.target.expectedSizeBytes,
        sha256: initial.target.expectedSHA256
    )
    let target = SafeDeleteTarget(
        deviceKey: initial.target.deviceKey,
        mapIdentity: initial.target.mapIdentity,
        ownership: initial.target.ownership,
        objectID: initial.target.objectID,
        expectedPath: initial.target.expectedPath,
        expectedFilename: initial.target.expectedFilename,
        expectedSizeBytes: initial.target.expectedSizeBytes,
        expectedSHA256: initial.target.expectedSHA256,
        backup: backup
    )
    return (target, initial.contents, backupURL)
}

private func run(
    target: SafeDeleteTarget,
    current: SafeDeleteDeviceObject?,
    confirmed: Bool = true,
    deviceConnected: Bool = true,
    requiresVerifiedBackup: Bool = true,
    scans: [[InstalledMapFile]],
    transport: FakeSafeDeleteTransport? = nil,
    onProgress: (@Sendable (SafeDeleteProgress) -> Void)? = nil
) -> (SafeDeleteResult, FakeSafeDeleteTransport) {
    let transport = transport ?? FakeSafeDeleteTransport()
    transport.currentObject = current
    let scanSequence = SafeDeleteScanSequence(scans)
    let result = SafeDeleteAdapter().delete(
        target: target,
        confirmed: confirmed,
        deviceConnected: deviceConnected,
        rescan: { scanSequence.next() },
        transport: transport,
        requiresVerifiedBackup: requiresVerifiedBackup,
        onProgress: onProgress
    )
    return (result, transport)
}

private func deviceObject(for target: SafeDeleteTarget, sha256 hash: String? = nil) -> SafeDeleteDeviceObject {
    SafeDeleteDeviceObject(
        file: target.sourceFile,
        sha256: hash ?? target.expectedSHA256
    )
}

private func testManagedMapDeletesAfterVerifiedBackup() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }
    let (result, transport) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target),
        scans: [ [] ]
    )

    try require(result.status == .success, "managed map should delete successfully")
    try require(transport.events == ["inspect", "delete"], "delete must inspect first and use one delete operation")
}

private func testManagedMapDeletesWithoutBackup() throws {
    let prepared = validTarget()
    let current = SafeDeleteDeviceObject(
        file: prepared.target.sourceFile,
        sha256: prepared.target.expectedSHA256
    )
    let (result, transport) = run(
        target: prepared.target,
        current: current,
        requiresVerifiedBackup: false,
        scans: [ [] ]
    )

    try require(result.status == .success, "manual remove must not require a local backup")
    try require(transport.events == ["inspect", "delete"], "backup-free remove must still inspect before deleting")
}

private func testReconnectUsesFreshLiveObjectID() throws {
    let prepared = validTarget()
    let liveFile = InstalledMapFile(
        path: prepared.target.expectedPath,
        filename: prepared.target.expectedFilename,
        sizeBytes: prepared.target.expectedSizeBytes,
        itemID: 777
    )
    let current = SafeDeleteDeviceObject(
        file: liveFile,
        sha256: prepared.target.expectedSHA256
    )
    let (result, transport) = run(
        target: prepared.target,
        current: current,
        requiresVerifiedBackup: false,
        scans: [[]]
    )

    try require(result.status == .success, "reconnected managed map should resolve its fresh live object ID")
    try require(transport.deletedObjectIDs == [777], "delete must use only the freshly resolved live object ID")
}

private func testBaseManagedFilenameAllowsRecordedMapVersion() throws {
    let prepared = validTarget()
    let target = SafeDeleteTarget(
        deviceKey: prepared.target.deviceKey,
        mapIdentity: prepared.target.mapIdentity,
        ownership: prepared.target.ownership,
        objectID: prepared.target.objectID,
        expectedPath: prepared.target.expectedPath,
        expectedFilename: prepared.target.expectedFilename,
        expectedSizeBytes: prepared.target.expectedSizeBytes,
        expectedSHA256: prepared.target.expectedSHA256,
        backup: nil,
        expectedVersion: MapVersion(year: 2026, month: 5)
    )
    let (result, transport) = run(
        target: target,
        current: deviceObject(for: target, sha256: nil),
        requiresVerifiedBackup: false,
        scans: [[]]
    )

    try require(result.status == .success, "a base managed filename must remain removable when metadata has a release")
    try require(transport.events == ["inspect", "delete"], "base filename removal must still verify before delete")
}

private func testCompositeRegionManagedFilenameCanBeRemoved() throws {
    let contents = Data(repeating: 0x43, count: 12)
    let identity = MapIdentity(provider: "Freizeitkarte", region: "ESP_CANARIAS")!
    let file = InstalledMapFile(
        path: "/GARMIN/terento_freizeitkarte_esp_canarias.img",
        filename: "terento_freizeitkarte_esp_canarias.img",
        sizeBytes: UInt64(contents.count),
        itemID: 202
    )
    let target = SafeDeleteTarget(
        deviceKey: "fenix-8-091e-51b8",
        mapIdentity: identity,
        ownership: .managedByTerento,
        objectID: 202,
        expectedPath: file.path,
        expectedFilename: file.filename,
        expectedSizeBytes: file.sizeBytes,
        expectedSHA256: sha256(contents),
        backup: nil,
        expectedVersion: MapVersion(year: 2026, month: 5)
    )
    let (result, transport) = run(
        target: target,
        current: deviceObject(for: target, sha256: nil),
        requiresVerifiedBackup: false,
        scans: [[]]
    )

    try require(result.status == .success, "a manifest-owned composite region map must be removable")
    try require(transport.events == ["inspect", "delete"], "composite region removal must still inspect before delete")
}

private func testManagedFilenameMustMatchNormalizedIdentity() throws {
    let prepared = validTarget()
    let wrongIdentity = MapIdentity(provider: "Freizeitkarte", region: "AUT")!
    let target = SafeDeleteTarget(
        deviceKey: prepared.target.deviceKey,
        mapIdentity: wrongIdentity,
        ownership: .managedByTerento,
        objectID: prepared.target.objectID,
        expectedPath: prepared.target.expectedPath,
        expectedFilename: prepared.target.expectedFilename,
        expectedSizeBytes: prepared.target.expectedSizeBytes,
        expectedSHA256: prepared.target.expectedSHA256,
        backup: nil
    )
    let (result, transport) = run(
        target: target,
        current: deviceObject(for: target, sha256: nil),
        requiresVerifiedBackup: false,
        scans: [[]]
    )

    try require(result.status == .blockedOwnership, "a managed filename for another region must remain blocked")
    try require(transport.events.isEmpty, "identity mismatch must stop before transport access")
}

private func testExternalAndUnknownMapsAreBlocked() throws {
    for state in [MapManagementState.detectedNotManaged, .unknown] {
        let initial = validTarget(ownership: state)
        let (result, transport) = run(
            target: initial.target,
            current: deviceObject(for: initial.target),
            scans: [ [] ]
        )

        try require(result.status == .blockedOwnership, "non-managed map must be blocked")
        try require(transport.events.isEmpty, "blocked ownership must not inspect or delete")
    }
}

private func testConfirmedExternalMapDeletesWithoutManifestCleanup() throws {
    let prepared = externalTarget()
    let current = SafeDeleteDeviceObject(
        file: prepared.target.sourceFile,
        sha256: sha256(prepared.contents)
    )
    let (result, transport) = run(
        target: prepared.target,
        current: current,
        requiresVerifiedBackup: false,
        scans: [[]]
    )

    try require(result.status == .success, "a confirmed parsed third-party map should be removable")
    try require(transport.events == ["inspect", "delete"], "third-party removal must inspect before delete")

    let cleanupStore = FakeManifestCleanupStore()
    let managerTransport = FakeSafeDeleteTransport()
    managerTransport.currentObject = current
    let scanSequence = SafeDeleteScanSequence([[]])
    let managedResult = MapLifecycleManager(manifestCleanupStore: cleanupStore).delete(
        target: prepared.target,
        confirmed: true,
        deviceConnected: true,
        rescan: { scanSequence.next() },
        transport: managerTransport,
        ownershipSource: .external,
        requiresVerifiedBackup: false
    )
    try require(managedResult.status == .success, "third-party removal should not require manifest cleanup")
    try require(cleanupStore.removed.isEmpty, "third-party removal must not create or delete ownership records")
}

private func testRemovalReportsMeasuredProgress() throws {
    let prepared = validTarget()
    let collector = ProgressCollector()
    let (result, _) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target),
        requiresVerifiedBackup: false,
        scans: [ [] ],
        onProgress: { progress in collector.append(progress) }
    )

    try require(result.status == .success, "progress reporting must not change a successful removal")
    try require(!collector.values.isEmpty, "removal must report progress values")
    try require(collector.values.first?.fractionCompleted == 0, "removal progress should start at zero")
    try require(collector.values.last?.fractionCompleted == 1, "removal progress should finish at one hundred percent")
    try require(
        zip(collector.values, collector.values.dropFirst()).allSatisfy {
            $0.fractionCompleted <= $1.fractionCompleted
        },
        "removal progress must never move backwards"
    )
}

private func testHashMismatchAndMissingBackupAreBlocked() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }

    let (hashResult, hashTransport) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target, sha256: String(repeating: "0", count: 64)),
        scans: [ [] ]
    )
    try require(hashResult.status == .blockedIntegrityCheck, "device hash mismatch must be blocked")
    try require(hashTransport.events == ["inspect"], "hash mismatch must stop before delete")

    let withoutBackup = SafeDeleteTarget(
        deviceKey: prepared.target.deviceKey,
        mapIdentity: prepared.target.mapIdentity,
        ownership: prepared.target.ownership,
        objectID: prepared.target.objectID,
        expectedPath: prepared.target.expectedPath,
        expectedFilename: prepared.target.expectedFilename,
        expectedSizeBytes: prepared.target.expectedSizeBytes,
        expectedSHA256: prepared.target.expectedSHA256,
        backup: nil
    )
    let (backupResult, backupTransport) = run(
        target: withoutBackup,
        current: deviceObject(for: withoutBackup),
        scans: [ [] ]
    )
    try require(backupResult.status == .blockedBackupRequired, "missing backup must be blocked")
    try require(backupTransport.events.isEmpty, "missing backup must stop before inspection")
}

private func testDisconnectAndConfirmationAreBlocked() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }

    let (disconnected, disconnectedTransport) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target),
        deviceConnected: false,
        scans: [ [] ]
    )
    try require(disconnected.status == .failedDeviceDisconnected, "disconnected device must fail safely")
    try require(disconnectedTransport.events.isEmpty, "disconnect must not inspect or delete")

    let (unconfirmed, unconfirmedTransport) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target),
        confirmed: false,
        scans: [ [] ]
    )
    try require(unconfirmed.status == .blockedConfirmationRequired, "delete must require explicit confirmation")
    try require(unconfirmedTransport.events.isEmpty, "missing confirmation must not inspect or delete")
}

private func testPostDeleteRescanAndExactIdentityAreRequired() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }

    let (stillPresent, stillPresentTransport) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target),
        scans: [ [prepared.target.sourceFile] ]
    )
    try require(stillPresent.status == .failedPostVerify, "remaining object must fail post-delete verification")
    try require(stillPresentTransport.events == ["inspect", "delete"], "post-delete verification must occur after delete")

    var wrongIdentity = prepared.target.sourceFile
    wrongIdentity = InstalledMapFile(
        path: "/GARMIN/terento_freizeitkarte_est.img",
        filename: "terento_freizeitkarte_est.img",
        sizeBytes: wrongIdentity.sizeBytes,
        itemID: 102
    )
    let mismatched = SafeDeleteDeviceObject(file: wrongIdentity, sha256: prepared.target.expectedSHA256)
    let (identityResult, identityTransport) = run(
        target: prepared.target,
        current: mismatched,
        scans: [ [] ]
    )
    try require(identityResult.status == .blockedIntegrityCheck, "object handle mismatch must be blocked")
    try require(identityTransport.events == ["inspect"], "identity mismatch must stop before delete")
}

private func testPostDeleteRescanRetriesWithoutRepeatingDelete() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }

    let (result, transport) = run(
        target: prepared.target,
        current: deviceObject(for: prepared.target),
        scans: [
            [prepared.target.sourceFile],
            [prepared.target.sourceFile],
            []
        ]
    )

    try require(result.status == .success, "a delayed device inventory refresh should be retried")
    try require(transport.events == ["inspect", "delete"], "rescan retry must never repeat the destructive delete")
}

private func testTransportFailureIsReported() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }
    let transport = FakeSafeDeleteTransport()
    transport.currentObject = deviceObject(for: prepared.target)
    transport.deleteError = .operationFailed("simulated delete failure")
    let (result, returnedTransport) = run(
        target: prepared.target,
        current: transport.currentObject,
        scans: [ [] ],
        transport: transport
    )

    try require(result.status == .failedOperation, "delete transport failure must be reported")
    try require(returnedTransport.events == ["inspect", "delete"], "transport failure must not trigger extra operations")

    let (missing, missingTransport) = run(
        target: prepared.target,
        current: nil,
        scans: [ [] ]
    )
    try require(missing.status == .failedObjectNotFound, "a missing object must be reported explicitly")
    try require(missingTransport.events == ["inspect"], "a missing object must stop before delete")
}

private func testLifecycleManagerCleansManifestAfterVerifiedDelete() throws {
    let prepared = try targetWithVerifiedBackup()
    defer { try? FileManager.default.removeItem(at: prepared.backupURL) }

    let cleanupStore = FakeManifestCleanupStore()
    let transport = FakeSafeDeleteTransport()
    transport.currentObject = deviceObject(for: prepared.target)
    let scanSequence = SafeDeleteScanSequence([[]])
    let result = MapLifecycleManager(manifestCleanupStore: cleanupStore).delete(
        target: prepared.target,
        confirmed: true,
        deviceConnected: true,
        rescan: { scanSequence.next() },
        transport: transport
    )

    try require(result.status == .success, "verified delete should succeed when manifest cleanup succeeds")
    try require(cleanupStore.removed.count == 1, "successful delete should remove one exact manifest entry")
    try require(cleanupStore.removed[0].deviceKey == prepared.target.deviceKey, "manifest cleanup must use the exact device key")
    try require(cleanupStore.removed[0].devicePath == prepared.target.expectedPath, "manifest cleanup must use the exact device path")
    try require(cleanupStore.removed[0].filename == prepared.target.expectedFilename, "manifest cleanup must use the exact filename")

    let failingCleanup = FakeManifestCleanupStore()
    failingCleanup.shouldFail = true
    let failingTransport = FakeSafeDeleteTransport()
    failingTransport.currentObject = deviceObject(for: prepared.target)
    let failingScanSequence = SafeDeleteScanSequence([[]])
    let failedResult = MapLifecycleManager(manifestCleanupStore: failingCleanup).delete(
        target: prepared.target,
        confirmed: true,
        deviceConnected: true,
        rescan: { failingScanSequence.next() },
        transport: failingTransport
    )
    try require(failedResult.status == .failedManifestCleanup, "manifest cleanup failure must not report a clean success")
}

@main
struct Stage52SafeDeleteTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("managed map deletes after verified backup", testManagedMapDeletesAfterVerifiedBackup),
            ("managed map deletes without backup", testManagedMapDeletesWithoutBackup),
            ("reconnect uses fresh live object ID", testReconnectUsesFreshLiveObjectID),
            ("base managed filename allows recorded map version", testBaseManagedFilenameAllowsRecordedMapVersion),
            ("composite region managed filename can be removed", testCompositeRegionManagedFilenameCanBeRemoved),
            ("managed filename must match normalized identity", testManagedFilenameMustMatchNormalizedIdentity),
            ("external and unknown maps are blocked", testExternalAndUnknownMapsAreBlocked),
            ("confirmed external map deletes without manifest cleanup", testConfirmedExternalMapDeletesWithoutManifestCleanup),
            ("removal reports measured progress", testRemovalReportsMeasuredProgress),
            ("hash mismatch and missing backup are blocked", testHashMismatchAndMissingBackupAreBlocked),
            ("disconnect and confirmation are blocked", testDisconnectAndConfirmationAreBlocked),
            ("post-delete rescan and exact identity are required", testPostDeleteRescanAndExactIdentityAreRequired),
            ("post-delete rescan retries without repeating delete", testPostDeleteRescanRetriesWithoutRepeatingDelete),
            ("transport failure is reported", testTransportFailureIsReported),
            ("lifecycle manager cleans manifest after verified delete", testLifecycleManagerCleansManifestAfterVerifiedDelete)
        ]

        do {
            for (name, test) in tests {
                try test()
                print("PASS: " + name)
            }
            print("PASS: " + String(tests.count) + " Stage 5.2 safe-delete tests")
        } catch {
            print("FAIL: " + String(describing: error))
            exit(1)
        }
    }
}

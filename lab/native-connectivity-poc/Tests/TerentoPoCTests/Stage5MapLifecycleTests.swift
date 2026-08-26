import Foundation

protocol DeviceFileReader: Sendable {
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

private final class FakeLifecycleTransport: MapReplacementTransport, @unchecked Sendable {
    var events: [String] = []
    var contentsByObjectID: [UInt32: Data] = [:]
    var failWrite = false
    var failVerification = false
    var corruptBackup = false

    func backup(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        guard let itemID = file.itemID else {
            throw MapLifecycleError.exactObjectIdentityRequired
        }
        events.append("backup")
        var data = contentsByObjectID[itemID] ?? Data(repeating: 0x41, count: Int(file.sizeBytes))
        if corruptBackup {
            data = Data(repeating: 0x41, count: max(0, Int(file.sizeBytes) - 1))
        }
        try data.write(to: destinationURL, options: .atomic)
        onProgress?(TransferProgress(bytesTransferred: UInt64(data.count), totalBytes: file.sizeBytes))
        return MapLifecycleBackupTransfer(
            itemID: itemID,
            sourcePath: file.path,
            reportedSizeBytes: file.sizeBytes
        )
    }

    func delete(file: InstalledMapFile) throws {
        guard file.itemID != nil else {
            throw MapLifecycleError.exactObjectIdentityRequired
        }
        events.append("delete")
    }

    func writeReplacement(
        sourceURL: URL,
        targetFilename: String,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapReplacementObject {
        events.append("write")
        if failWrite {
            throw MapLifecycleError.transportFailure("simulated write failure")
        }

        let attributes = try FileManager.default.attributesOfItem(atPath: sourceURL.path)
        let size = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
        onProgress?(TransferProgress(bytesTransferred: size, totalBytes: size))
        return MapReplacementObject(
            itemID: 900,
            path: "/GARMIN/\(targetFilename)",
            sizeBytes: size,
            sha256: "artifact-hash"
        )
    }

    func verifyReplacement(
        _ object: MapReplacementObject,
        expected: MapUpdateArtifact
    ) throws {
        events.append("verify")
        if failVerification {
            throw MapLifecycleError.transportFailure("simulated verification failure")
        }
        guard object.sizeBytes == expected.sizeBytes,
              object.sha256 == expected.sha256 else {
            throw MapLifecycleError.postActionVerificationFailed
        }
    }
}

private final class ScanSequence: @unchecked Sendable {
    private var index = 0
    private let values: [MapLifecycleInventory]

    init(_ values: [MapLifecycleInventory]) {
        self.values = values
    }

    func next() throws -> MapLifecycleInventory {
        defer { index += 1 }
        return values[min(index, values.count - 1)]
    }
}

private enum Stage5TestError: Error {
    case failed(String)
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else {
        throw Stage5TestError.failed(message)
    }
}

private func expect(_ error: MapLifecycleError, from operation: () throws -> Void) throws {
    do {
        try operation()
    } catch let actual as MapLifecycleError {
        try require(actual == error, "expected \(error), got \(actual)")
        return
    }
    throw Stage5TestError.failed("expected \(error), but operation succeeded")
}

private func version(_ year: Int, _ month: Int) -> MapVersion {
    MapVersion(year: year, month: month)!
}

private func installedMap(
    id: UInt32 = 101,
    path: String = "/GARMIN/freizeitkarte-deu.img",
    filename: String = "freizeitkarte-deu.img",
    sizeBytes: UInt64 = 12,
    version: MapVersion? = version(2026, 5),
    managementState: MapManagementState = .detectedNotManaged
) -> InstalledMap {
    InstalledMap(
        name: "Freizeitkarte DEU+",
        provider: "Freizeitkarte",
        region: "DEU",
        family: "Freizeitkarte",
        rawVersion: version.map { "Release \($0.year - 2000).\(String(format: "%02d", $0.month))" },
        version: version,
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: sizeBytes,
        sourceFile: InstalledMapFile(
            path: path,
            filename: filename,
            sizeBytes: sizeBytes,
            itemID: id
        ),
        metadataStatus: .parsed,
        managementState: managementState
    )
}

private func lifecycleItem(
    map: InstalledMap,
    classification: MapLifecycleClassification = .terentoManaged,
    id: String = "freizeitkarte:DEU"
) -> MapLifecycleItem {
    MapLifecycleItem(
        id: id,
        title: "Freizeitkarte Germany",
        provider: "freizeitkarte",
        region: "DEU",
        version: map.version,
        rawVersion: map.rawVersion,
        sizeBytes: map.sizeBytes,
        installedMaps: [map],
        classification: classification
    )
}

private func inventory(_ item: MapLifecycleItem) -> MapLifecycleInventory {
    MapLifecycleInventory(
        freizeitkarte: item.provider == "freizeitkarte" ? [item] : [],
        otherMaps: item.provider == "freizeitkarte" ? [] : [item]
    )
}

private func testInventoryBuilderUsesRealEntries() throws {
    let map = installedMap()
    let entry = MapInventoryEntry(
        key: "freizeitkarte:identity:freizeitkarte:DEU",
        title: "Freizeitkarte Germany",
        catalogPackage: nil,
        comparison: nil,
        installedMaps: [map],
        isSelectedCatalogMap: false
    )
    let result = MapLifecycleInventoryBuilder().build(
        from: UnifiedMapInventory(freizeitkarte: [entry], otherMaps: [])
    )

    try require(result.freizeitkarte.count == 1, "inventory should contain one Freizeitkarte item")
    try require(result.freizeitkarte[0].hasExactObjectIdentity, "live inventory must retain the MTP object handle")
    try require(result.freizeitkarte[0].classification == .externalRecognized, "unmanaged parsed map should be external-recognized")
}

private func testInventoryBuilderUsesCanonicalPackageIdentity() throws {
    let map = InstalledMap(
        name: "Freizeitkarte Balearics",
        provider: "Freizeitkarte",
        region: "BALEARICS",
        family: "Freizeitkarte",
        rawVersion: "Release 26.05",
        version: version(2026, 5),
        identifier: "BALEARICS",
        productId: nil,
        familyId: nil,
        sizeBytes: 41_537_536,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_balearics.img",
            filename: "terento_freizeitkarte_balearics.img",
            sizeBytes: 41_537_536,
            itemID: 202
        ),
        metadataStatus: .parsed,
        managementState: .managedByTerento
    )
    let package = MapPackage(
        id: "freizeitkarte-esp-balearics",
        providerId: "freizeitkarte",
        regionId: "AZORES",
        name: "Balearics",
        version: version(2026, 5),
        sizeBytes: 1,
        sourceURL: nil,
        releaseDate: nil,
        identifier: "BALEARICS",
        installSizeBytes: map.sizeBytes
    )
    let entry = MapInventoryEntry(
        key: "freizeitkarte:identity:freizeitkarte:BALEARICS",
        title: "Freizeitkarte Balearics",
        catalogPackage: package,
        comparison: nil,
        installedMaps: [map],
        isSelectedCatalogMap: false
    )

    let result = MapLifecycleInventoryBuilder().build(
        from: UnifiedMapInventory(freizeitkarte: [entry], otherMaps: [])
    )

    try require(
        result.freizeitkarte.first?.region == "BALEARICS",
        "lifecycle identity must use the concrete package identifier, not the shared catalog region"
    )
}

private func testBackupIsVerified() throws {
    let map = installedMap(sizeBytes: 12)
    let item = lifecycleItem(map: map)
    let transport = FakeLifecycleTransport()
    let directory = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage5-backup-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let result = try MapBackupEngine().backup(
        item: item,
        to: directory,
        transport: transport
    )

    try require(result.files.count == 1, "backup should include the exact map object")
    try require(result.files[0].sizeBytes == map.sizeBytes, "backup size must match the device object")
    try require(FileManager.default.fileExists(atPath: result.files[0].localURL.path), "verified backup must exist locally")

    let corruptTransport = FakeLifecycleTransport()
    corruptTransport.corruptBackup = true
    let corruptDirectory = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage5-corrupt-backup-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: corruptDirectory) }
    try expect(.backupVerificationFailed) {
        _ = try MapBackupEngine().backup(
            item: item,
            to: corruptDirectory,
            transport: corruptTransport
        )
    }
}

private func testUpdatePlanProtectsStorageAndVersionDirection() throws {
    let item = lifecycleItem(map: installedMap())
    let planner = MapUpdatePlanner()

    let same = planner.plan(
        item: item,
        installedVersion: version(2026, 5),
        targetVersion: version(2026, 5),
        targetFilename: "terento_freizeitkarte_deu.img",
        newMapSizeBytes: 100,
        currentFreeSpace: 3 * 1024 * 1024 * 1024
    )
    try require(same.status == .noUpdateRequired, "same version must not trigger replacement")

    let newer = planner.plan(
        item: item,
        installedVersion: version(2026, 6),
        targetVersion: version(2026, 5),
        targetFilename: "terento_freizeitkarte_deu.img",
        newMapSizeBytes: 100,
        currentFreeSpace: 3 * 1024 * 1024 * 1024
    )
    try require(newer.status == .newerVersionAlreadyInstalled, "downgrade must never be recommended")

    let ready = planner.plan(
        item: item,
        installedVersion: version(2026, 5),
        targetVersion: version(2026, 6),
        targetFilename: "terento_freizeitkarte_deu.img",
        newMapSizeBytes: 100,
        currentFreeSpace: 3 * 1024 * 1024 * 1024
    )
    try require(ready.isReady && ready.backupRequired, "newer catalog version should produce a safe update plan")

    let blocked = planner.plan(
        item: item,
        installedVersion: version(2026, 5),
        targetVersion: version(2026, 6),
        targetFilename: "terento_freizeitkarte_deu.img",
        newMapSizeBytes: 100,
        currentFreeSpace: 100 + StoragePlanner.defaultSafetyReserve - 1
    )
    try require(blocked.status == .blockedInsufficientSpace, "update must preserve the storage reserve")
}

private func testReplacementOrderAndRecovery() throws {
    let oldMap = installedMap(sizeBytes: 12)
    let item = lifecycleItem(map: oldMap)
    let before = inventory(item)
    let replacementFile = InstalledMap(
        name: "Freizeitkarte DEU+",
        provider: "Freizeitkarte",
        region: "DEU",
        family: "Freizeitkarte",
        rawVersion: "Release 26.06",
        version: version(2026, 6),
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: 20,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_deu.img",
            filename: "terento_freizeitkarte_deu.img",
            sizeBytes: 20,
            itemID: 900
        ),
        metadataStatus: .parsed,
        managementState: .managedByTerento
    )
    let replacementItem = lifecycleItem(
        map: replacementFile,
        classification: .terentoManaged,
        id: item.id
    )
    let after = inventory(replacementItem)
    let scans = ScanSequence([before, after])
    let transport = FakeLifecycleTransport()
    let artifactURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage5-artifact-\(UUID().uuidString).img")
    try Data(repeating: 0x42, count: 20).write(to: artifactURL, options: .atomic)
    defer { try? FileManager.default.removeItem(at: artifactURL) }

    let plan = MapUpdatePlanner().plan(
        item: item,
        installedVersion: version(2026, 5),
        targetVersion: version(2026, 6),
        targetFilename: "terento_freizeitkarte_deu.img",
        newMapSizeBytes: 20,
        currentFreeSpace: 3 * 1024 * 1024 * 1024
    )
    let backupDirectory = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage5-replacement-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: backupDirectory) }

    _ = try MapReplacementEngine().replace(
        plan: plan,
        item: item,
        artifact: MapUpdateArtifact(localURL: artifactURL, sizeBytes: 20, sha256: "artifact-hash"),
        backupDirectory: backupDirectory,
        confirmed: true,
        rescan: { try scans.next() },
        transport: transport
    )
    try require(transport.events == ["backup", "write", "verify", "delete"], "replacement must verify before deleting the old map")

    let failedTransport = FakeLifecycleTransport()
    failedTransport.failWrite = true
    let failedScans = ScanSequence([before])
    let failedBackupDirectory = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage5-failed-replacement-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: failedBackupDirectory) }
    try expect(.transportFailure("simulated write failure")) {
        _ = try MapReplacementEngine().replace(
            plan: plan,
            item: item,
            artifact: MapUpdateArtifact(localURL: artifactURL, sizeBytes: 20, sha256: "artifact-hash"),
            backupDirectory: failedBackupDirectory,
            confirmed: true,
            rescan: { try failedScans.next() },
            transport: failedTransport
        )
    }
    try require(failedTransport.events == ["backup", "write"], "failed update must preserve the old map and skip delete")
}

@main
struct Stage5MapLifecycleTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("inventory uses exact object identity", testInventoryBuilderUsesRealEntries),
            ("inventory uses canonical package identity", testInventoryBuilderUsesCanonicalPackageIdentity),
            ("backup output is size-verified", testBackupIsVerified),
            ("update direction and storage reserve are safe", testUpdatePlanProtectsStorageAndVersionDirection),
            ("replacement verifies before delete and preserves on failure", testReplacementOrderAndRecovery)
        ]

        do {
            for (name, test) in tests {
                try test()
                print("PASS: \(name)")
            }
            print("PASS: \(tests.count) Stage 5 map lifecycle tests")
        } catch {
            print("FAIL: \(error)")
            exit(1)
        }
    }
}

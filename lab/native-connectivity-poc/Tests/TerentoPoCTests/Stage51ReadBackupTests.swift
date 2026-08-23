import CryptoKit
import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

private final class FakeReadTransport: MapLifecycleReadTransport, @unchecked Sendable {
    enum Failure: Error {
        case disconnected
        case failed
    }

    var events: [String] = []
    var data = Data(repeating: 0x42, count: 32)
    var reportedSizeOverride: UInt64?
    var failure: Failure?

    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        events.append("read")
        if let failure {
            switch failure {
            case .disconnected:
                throw MapLifecycleReadTransportError.deviceDisconnected("watch disconnected")
            case .failed:
                throw MapLifecycleReadTransportError.readFailed("read failed")
            }
        }

        try data.write(to: destinationURL, options: .atomic)
        onProgress?(TransferProgress(
            bytesTransferred: UInt64(data.count),
            totalBytes: file.sizeBytes
        ))
        return MapLifecycleBackupTransfer(
            itemID: file.itemID ?? 0,
            sourcePath: file.path,
            reportedSizeBytes: reportedSizeOverride ?? file.sizeBytes
        )
    }
}

private enum Stage51TestError: Error {
    case failed(String)
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else {
        throw Stage51TestError.failed(message)
    }
}

private func sha256(_ data: Data) -> String {
    SHA256.hash(data: data)
        .map { String(format: "%02x", $0) }
        .joined()
}

private func version(_ year: Int, _ month: Int) -> MapVersion {
    MapVersion(year: year, month: month)!
}

private func makeMap(
    id: UInt32 = 501,
    sizeBytes: UInt64 = 32,
    managementState: MapManagementState = .managedByTerento
) -> InstalledMap {
    InstalledMap(
        name: "Freizeitkarte LTU+",
        provider: "Freizeitkarte",
        region: "LTU",
        family: "Freizeitkarte",
        rawVersion: "Release 26.05",
        version: version(2026, 5),
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: sizeBytes,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_ltu.img",
            filename: "terento_freizeitkarte_ltu.img",
            sizeBytes: sizeBytes,
            itemID: id
        ),
        metadataStatus: .parsed,
        managementState: managementState
    )
}

private func makeItem(
    map: InstalledMap,
    classification: MapLifecycleClassification = .terentoManaged
) -> MapLifecycleItem {
    MapLifecycleItem(
        id: "freizeitkarte:LTU",
        title: "Freizeitkarte Lithuania",
        provider: "freizeitkarte",
        region: "LTU",
        version: map.version,
        rawVersion: map.rawVersion,
        sizeBytes: map.sizeBytes,
        installedMaps: [map],
        classification: classification
    )
}

private func backupDirectory() -> URL {
    FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-stage51-\(UUID().uuidString)", isDirectory: true)
}

private func hasNoBackupOutput(at root: URL) -> Bool {
    guard let entries = try? FileManager.default.contentsOfDirectory(
        at: root,
        includingPropertiesForKeys: nil
    ) else {
        return true
    }
    return entries.isEmpty
}

private func testSuccessfulBackup() throws {
    let transport = FakeReadTransport()
    let root = backupDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let map = makeMap()
    let item = makeItem(map: map)
    let expectedHash = sha256(transport.data)

    let result = ReadBackupAdapter(
        transport: transport,
        backupDirectory: root,
        now: { Date(timeIntervalSince1970: 1_750_000_000) }
    ).backup(
        target: ManagedMapBackupTarget(
            item: item,
            expectedSHA256ByItemID: [map.sourceFile.itemID!: expectedHash]
        )
    )

    try require(result.status == .backupSuccess, "verified managed map backup should succeed")
    try require(result.files.count == 1, "successful backup should return one verified file")
    try require(transport.events == ["read"], "successful backup must use the read-only transport once")
    try require(FileManager.default.fileExists(atPath: result.files[0].localURL.path), "verified backup must exist locally")
    try require(result.files[0].sizeBytes == map.sizeBytes, "verified backup size must match the source object")
    try require(result.files[0].sha256 == expectedHash, "verified backup hash must match the manifest hash")
    try require(result.files[0].localURL.lastPathComponent.contains("2026-05"), "backup filename should contain the map version")
    try require(result.files[0].localURL.lastPathComponent.contains("freizeitkarte-LTU"), "backup filename should contain map identity")
}

private func testUnmanagedObjectIsRefused() throws {
    let transport = FakeReadTransport()
    let root = backupDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let map = makeMap(managementState: .detectedNotManaged)
    let item = makeItem(map: map, classification: .externalRecognized)

    let result = ReadBackupAdapter(
        transport: transport,
        backupDirectory: root
    ).backup(
        target: ManagedMapBackupTarget(
            item: item,
            expectedSHA256ByItemID: [map.sourceFile.itemID!: sha256(transport.data)]
        )
    )

    try require(result.status == .unmanagedObject, "external map must be refused")
    try require(transport.events.isEmpty, "unmanaged map must not reach the read transport")
    try require(!FileManager.default.fileExists(atPath: root.path), "unmanaged map must not create a backup directory")
}

private func testSizeMismatchRemovesPartialBackup() throws {
    let transport = FakeReadTransport()
    transport.reportedSizeOverride = 31
    let root = backupDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let map = makeMap()
    let result = ReadBackupAdapter(
        transport: transport,
        backupDirectory: root
    ).backup(
        target: ManagedMapBackupTarget(
            item: makeItem(map: map),
            expectedSHA256ByItemID: [map.sourceFile.itemID!: sha256(transport.data)]
        )
    )

    try require(result.status == .backupFailedSizeMismatch, "reported size mismatch must fail the backup")
    try require(hasNoBackupOutput(at: root), "size mismatch must remove partial local output")
}

private func testHashMismatchRemovesPartialBackup() throws {
    let transport = FakeReadTransport()
    let root = backupDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let map = makeMap()
    let result = ReadBackupAdapter(
        transport: transport,
        backupDirectory: root
    ).backup(
        target: ManagedMapBackupTarget(
            item: makeItem(map: map),
            expectedSHA256ByItemID: [map.sourceFile.itemID!: sha256(Data(repeating: 0x99, count: 32))]
        )
    )

    try require(result.status == .backupFailedHashMismatch, "hash mismatch must fail the backup")
    try require(hasNoBackupOutput(at: root), "hash mismatch must remove partial local output")
}

private func testDisconnectIsReportedClearly() throws {
    let transport = FakeReadTransport()
    transport.failure = .disconnected
    let root = backupDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let map = makeMap()
    let result = ReadBackupAdapter(
        transport: transport,
        backupDirectory: root
    ).backup(
        target: ManagedMapBackupTarget(
            item: makeItem(map: map),
            expectedSHA256ByItemID: [map.sourceFile.itemID!: sha256(transport.data)]
        )
    )

    try require(result.status == .backupFailedDeviceDisconnected, "disconnect must have a dedicated backup status")
    try require(hasNoBackupOutput(at: root), "disconnect must remove partial local output")
}

private func testReadBackupHasNoWriteSurface() throws {
    let source = try String(
        contentsOfFile: #filePath.replacingOccurrences(
            of: "/Tests/TerentoPoCTests/Stage51ReadBackupTests.swift",
            with: "/Sources/TerentoPoC/Installation/MTPReadBackupAdapter.swift"
        ),
        encoding: .utf8
    )
    for forbidden in [
        "terento_mtp_install_map_file",
        "terento_mtp_delete_managed_map",
        "SendObject",
        "DeleteObject",
        "MoveObject",
        "Rename"
    ] {
        try require(!source.contains(forbidden), "read adapter must not contain write operation \(forbidden)")
    }
}

@main
struct Stage51ReadBackupTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("verified managed backup succeeds", testSuccessfulBackup),
            ("unmanaged object is refused without a backup", testUnmanagedObjectIsRefused),
            ("size mismatch removes partial backup", testSizeMismatchRemovesPartialBackup),
            ("hash mismatch removes partial backup", testHashMismatchRemovesPartialBackup),
            ("disconnect has a dedicated failure status", testDisconnectIsReportedClearly),
            ("read adapter has no write surface", testReadBackupHasNoWriteSurface)
        ]

        do {
            for (name, test) in tests {
                try test()
                print("PASS: \(name)")
            }
            print("PASS: \(tests.count) Stage 5.1 read/backup tests")
        } catch {
            print("FAIL: \(error)")
            exit(1)
        }
    }
}

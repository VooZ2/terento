import CryptoKit
import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

private final class RecoveryManifestStore: TerentoManifestStore, @unchecked Sendable {
    var entries: [TerentoManifestEntry] = []
    func record(_ entry: TerentoManifestEntry) throws { entries.append(entry) }
}

private final class RecoveryReader: MapLifecycleReadTransport, @unchecked Sendable {
    let data: Data
    let returnedItemID: UInt32?
    var reads = 0

    init(data: Data, returnedItemID: UInt32? = nil) {
        self.data = data
        self.returnedItemID = returnedItemID
    }

    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        reads += 1
        try data.write(to: destinationURL, options: .atomic)
        return MapLifecycleBackupTransfer(
            itemID: returnedItemID ?? file.itemID ?? 0,
            sourcePath: file.path,
            reportedSizeBytes: UInt64(data.count)
        )
    }
}

@main
struct ManagedMapRecoveryTests {
    static func main() throws {
        try testSameWatchRecoversAfterCompleteRead()
        try testAnotherIdenticalWatchCannotClaimExport()
        try testChangedMapRemainsReadOnly()
        try testMissingDiscriminatorFailsClosed()
        print("PASS: 4 managed-map recovery tests")
    }

    private static func testSameWatchRecoversAfterCompleteRead() throws {
        let data = Data(repeating: 0x41, count: 4096)
        let identity = makeIdentity(serial: "WATCH-A", resolution: .garminUnitID)
        let document = try makeDocument(data: data, identity: identity)
        let store = RecoveryManifestStore()
        // Garmin may issue a different object handle when the native read
        // opens a fresh MTP session. Stable path/name/size and full SHA are
        // authoritative; a session-local handle must not block recovery.
        let reader = RecoveryReader(data: data, returnedItemID: 888)
        let result = try ManagedMapRecoveryCoordinator(
            manifestStore: store,
            deviceKeyProvider: { _ in "watch-v2-local-a" }
        ).recover(
            document: document,
            identity: identity,
            liveFiles: [makeLiveFile(size: UInt64(data.count))],
            reader: reader
        )

        guard reader.reads == 1,
              store.entries == [result.recoveredEntry],
              result.recoveredEntry.deviceKey == "watch-v2-local-a",
              result.recoveredEntry.sha256 == sha256(data) else {
            throw Failure("same-watch recovery did not require and record the complete verified IMG")
        }
        print("PASS: same watch recovers across an MTP handle change after complete IMG verification")
    }

    private static func testAnotherIdenticalWatchCannotClaimExport() throws {
        let data = Data(repeating: 0x41, count: 4096)
        let document = try makeDocument(
            data: data,
            identity: makeIdentity(serial: "WATCH-A", resolution: .garminUnitID)
        )
        let store = RecoveryManifestStore()
        let reader = RecoveryReader(data: data)

        do {
            _ = try ManagedMapRecoveryCoordinator(
                manifestStore: store,
                deviceKeyProvider: { _ in "watch-v2-local-b" }
            ).recover(
                document: document,
                identity: makeIdentity(serial: "WATCH-B", resolution: .garminUnitID),
                liveFiles: [makeLiveFile(size: UInt64(data.count))],
                reader: reader
            )
            throw Failure("another identical watch claimed the export")
        } catch ManagedMapRecoveryError.exportBelongsToAnotherWatch {
            guard reader.reads == 0, store.entries.isEmpty else {
                throw Failure("wrong-watch recovery touched the map or manifest")
            }
        }
        print("PASS: same model and map SHA do not let another watch claim ownership")
    }

    private static func testChangedMapRemainsReadOnly() throws {
        let original = Data(repeating: 0x41, count: 4096)
        let changed = Data(repeating: 0x42, count: 4096)
        let identity = makeIdentity(serial: "WATCH-A")
        let document = try makeDocument(data: original, identity: identity)
        let store = RecoveryManifestStore()

        do {
            _ = try ManagedMapRecoveryCoordinator(
                manifestStore: store,
                deviceKeyProvider: { _ in "watch-v2-local-a" }
            ).recover(
                document: document,
                identity: identity,
                liveFiles: [makeLiveFile(size: UInt64(changed.count))],
                reader: RecoveryReader(data: changed)
            )
            throw Failure("changed live map was recovered")
        } catch ManagedMapRecoveryError.liveMapChanged {
            guard store.entries.isEmpty else { throw Failure("changed map received ownership") }
        }
        print("PASS: changed map remains read-only")
    }

    private static func testMissingDiscriminatorFailsClosed() throws {
        let data = Data(repeating: 0x41, count: 4096)
        let identity = makeIdentity(serial: nil)
        do {
            _ = try TerentoManifestExportService().makeDocument(
                manifest: makeManifest(data: data),
                identity: identity
            )
            throw Failure("missing discriminator produced an ownership export")
        } catch ManagedMapRecoveryError.stableWatchIdentityUnavailable {
            print("PASS: unavailable discriminator leaves ownership read-only")
        }
    }

    private static func makeDocument(
        data: Data,
        identity: DeviceIdentity
    ) throws -> TerentoManifestExportDocument {
        let service = TerentoManifestExportService()
        let document = try service.makeDocument(
            manifest: makeManifest(data: data),
            identity: identity,
            now: Date(timeIntervalSince1970: 1)
        )
        let encoded = try service.encode(document)
        guard !String(decoding: encoded, as: UTF8.self).contains("WATCH-A") else {
            throw Failure("raw watch identity leaked into the export")
        }
        return try service.decode(encoded)
    }

    private static func makeManifest(data: Data) -> TerentoManifest {
        TerentoManifest(entries: [
            TerentoManifestEntry(
                deviceKey: "legacy-fenix8-091e-51b8",
                devicePath: "/GARMIN/terento_freizeitkarte_deu.img",
                filename: "terento_freizeitkarte_deu.img",
                providerId: "freizeitkarte",
                regionId: "DEU",
                version: MapVersion(year: 2026, month: 5)!,
                sizeBytes: UInt64(data.count),
                sha256: sha256(data),
                installedAt: Date(timeIntervalSince1970: 1)
            )
        ])
    }

    private static func makeIdentity(
        serial: String?,
        resolution: DeviceIdentity.LocalIdentityResolution? = nil
    ) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            family: "fēnix",
            variant: "47mm",
            usbVendorId: 0x091e,
            usbProductId: 0x51b8,
            firmware: "2243",
            storageCapacity: 31 * 1024 * 1024 * 1024,
            freeSpace: 15 * 1024 * 1024 * 1024,
            localHardwareIdentifier: serial,
            localIdentityResolution: resolution
        )
    }

    private static func makeLiveFile(size: UInt64) -> DeviceFile {
        DeviceFile(
            itemID: 777,
            parentID: 1,
            storageID: 1,
            path: "/GARMIN/terento_freizeitkarte_deu.img",
            filename: "terento_freizeitkarte_deu.img",
            sizeBytes: size,
            isFolder: false
        )
    }

    private static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}

private struct Failure: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

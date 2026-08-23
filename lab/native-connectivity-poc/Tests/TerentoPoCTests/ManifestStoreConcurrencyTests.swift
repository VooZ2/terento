import Foundation

@main
struct ManifestStoreConcurrencyTests {
    static func main() throws {
        try testConcurrentReadModifyWritePreservesAllEntries()
        try testOlderEntryCannotReplaceNewerEntry()
        try testUnsafeDeviceKeyIsRejected()
        print("PASS: 3 manifest store concurrency tests")
    }

    private static func testConcurrentReadModifyWritePreservesAllEntries() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-manifest-concurrency-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let store = LocalTerentoManifestStore(rootDirectory: root)
        let version = try requireVersion()
        let errorLock = NSLock()
        var errors: [Error] = []

        DispatchQueue.concurrentPerform(iterations: 32) { index in
            let entry = TerentoManifestEntry(
                deviceKey: "fenix8-test-device",
                devicePath: "/GARMIN/terento_freizeitkarte_r\(index).img",
                filename: "terento_freizeitkarte_r\(index).img",
                providerId: "freizeitkarte",
                regionId: "R\(index)",
                version: version,
                sizeBytes: UInt64(index + 1),
                sha256: String(format: "%064x", index + 1),
                installedAt: Date(timeIntervalSince1970: Double(index))
            )

            do {
                try store.record(entry)
            } catch {
                errorLock.lock()
                errors.append(error)
                errorLock.unlock()
            }
        }

        guard errors.isEmpty else {
            throw TestFailure(message: "concurrent manifest writes failed: \(errors)")
        }

        let manifest = try store.read(deviceKey: "fenix8-test-device")
        let entries = manifest?.entries ?? []
        guard entries.count == 32,
              Set(entries.map(\.filename)).count == 32 else {
            throw TestFailure(message: "concurrent manifest writes lost entries")
        }

        print("PASS: concurrent manifest read-modify-write preserves all entries")
    }

    private static func testOlderEntryCannotReplaceNewerEntry() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-manifest-order-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let store = LocalTerentoManifestStore(rootDirectory: root)
        let version = try requireVersion()
        let newer = makeEntry(version: version, installedAt: 200, suffix: "new")
        let older = makeEntry(version: version, installedAt: 100, suffix: "old")
        try store.record(newer)

        do {
            try store.record(older)
            throw TestFailure(message: "older manifest entry replaced a newer entry")
        } catch TerentoManifestStoreError.newerEntryExists {
            guard let retained = try store.read(deviceKey: newer.deviceKey)?.entries.first,
                  retained.sha256 == newer.sha256 else {
                throw TestFailure(message: "newer manifest entry was not retained")
            }
            print("PASS: older manifest entry cannot replace a newer entry")
        }
    }

    private static func testUnsafeDeviceKeyIsRejected() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-manifest-key-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let store = LocalTerentoManifestStore(rootDirectory: root)
        do {
            _ = try store.read(deviceKey: "../outside")
            throw TestFailure(message: "unsafe device key was accepted")
        } catch TerentoManifestStoreError.invalidDeviceKey {
            print("PASS: unsafe manifest device key is rejected")
        }
    }

    private static func requireVersion() throws -> MapVersion {
        guard let version = MapVersion(year: 2026, month: 5) else {
            throw TestFailure(message: "test version could not be created")
        }
        return version
    }

    private static func makeEntry(
        version: MapVersion,
        installedAt: TimeInterval,
        suffix: String
    ) -> TerentoManifestEntry {
        TerentoManifestEntry(
            deviceKey: "fenix8-test-device",
            devicePath: "/GARMIN/terento_freizeitkarte_ltu.img",
            filename: "terento_freizeitkarte_ltu.img",
            providerId: "freizeitkarte",
            regionId: "LTU",
            version: version,
            sizeBytes: 100,
            sha256: suffix,
            installedAt: Date(timeIntervalSince1970: installedAt)
        )
    }
}

private struct TestFailure: LocalizedError {
    let message: String

    var errorDescription: String? { message }
}

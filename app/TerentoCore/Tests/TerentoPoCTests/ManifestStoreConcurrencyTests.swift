import Foundation

@main
struct ManifestStoreConcurrencyTests {
    static func main() throws {
        try testConcurrentReadModifyWritePreservesAllEntries()
        try testOlderEntryCannotReplaceNewerEntry()
        try testUnsafeDeviceKeyIsRejected()
        try testPhysicalWatchKeysAreStableAndDistinct()
        try testCatalogIdentityPreservesLegacyKeys()
        try testUnreadableManifestIsQuarantinedNotDeleted()
        try testUnreadableRecoveryIsQuarantinedAndDoesNotBlockRecord()
        try testUnknownRecoveryRecordsAreKeptAside()
        try testManifestQuarantineMoveFailureIsTyped()
        print("PASS: 9 manifest store tests")
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

    private static func testUnreadableManifestIsQuarantinedNotDeleted() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-manifest-quarantine-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalTerentoManifestStore(rootDirectory: root)
        let version = try requireVersion()
        let entry = makeEntry(version: version, installedAt: 100, suffix: "fresh")
        let manifestURL = root.appendingPathComponent("Terento/devices/\(entry.deviceKey)/manifest.json")

        guard try store.quarantineUnreadableManifest(deviceKey: entry.deviceKey) == nil else {
            throw TestFailure(message: "an absent manifest must not be quarantined")
        }
        try store.record(entry)
        guard try store.quarantineUnreadableManifest(deviceKey: entry.deviceKey) == nil,
              try store.read(deviceKey: entry.deviceKey)?.entries.count == 1 else {
            throw TestFailure(message: "a readable manifest must be left untouched")
        }

        let corrupt = Data("{ not json".utf8)
        try corrupt.write(to: manifestURL)
        do {
            try store.record(entry)
            throw TestFailure(message: "an unreadable manifest must still fail closed on record")
        } catch TerentoManifestStoreError.unreadableManifest {}

        let now = Date(timeIntervalSince1970: 1_790_000_000)
        guard let quarantined = try store.quarantineUnreadableManifest(deviceKey: entry.deviceKey, now: now) else {
            throw TestFailure(message: "an unreadable manifest must be quarantined")
        }
        guard quarantined.lastPathComponent.hasPrefix("manifest.corrupt-2026"),
              try Data(contentsOf: quarantined) == corrupt,
              !FileManager.default.fileExists(atPath: manifestURL.path) else {
            throw TestFailure(message: "quarantine must rename with the date and keep the original bytes")
        }
        try corrupt.write(to: manifestURL)
        guard let second = try store.quarantineUnreadableManifest(deviceKey: entry.deviceKey, now: now),
              second != quarantined, FileManager.default.fileExists(atPath: quarantined.path) else {
            throw TestFailure(message: "a second quarantine on the same date must not overwrite the first")
        }
        try store.record(entry)
        guard try store.read(deviceKey: entry.deviceKey)?.entries == [entry] else {
            throw TestFailure(message: "a fresh record works after quarantine")
        }
        print("PASS: an unreadable manifest is quarantined with its date, never deleted, and a fresh record works")
    }

    private static func testUnreadableRecoveryIsQuarantinedAndDoesNotBlockRecord() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-recovery-quarantine-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalTerentoFailedInstallRecoveryStore(rootDirectory: root)
        let recoveryURL = root.appendingPathComponent("Terento/failed-install-recovery.json")
        let record = TerentoFailedInstallRecoveryRecord(
            deviceKey: "fenix8-test-device", packageID: "freizeitkarte-deu",
            providerId: "freizeitkarte", regionId: "DEU", version: try requireVersion(),
            devicePath: "/GARMIN/terento_freizeitkarte_deu.img", filename: "terento_freizeitkarte_deu.img",
            sizeBytes: 100, sha256: String(repeating: "a", count: 64), createdAt: Date(timeIntervalSince1970: 0))
        let corrupt = Data("{ not json".utf8)
        try FileManager.default.createDirectory(at: recoveryURL.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        // Without a logging hook the corrupt file must still be set aside, not overwritten.
        LocalTerentoFailedInstallRecoveryStore.onSetAside = nil
        try corrupt.write(to: recoveryURL)
        try store.record(record)
        let unhooked = try FileManager.default.contentsOfDirectory(
            at: recoveryURL.deletingLastPathComponent(), includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix("failed-install-recovery.corrupt-") }
        guard unhooked.count == 1, try Data(contentsOf: unhooked[0]) == corrupt else {
            throw TestFailure(message: "a corrupt recovery file is set aside even when no logging hook is set")
        }
        try FileManager.default.removeItem(at: unhooked[0])

        let logged = LoggedURLs()
        LocalTerentoFailedInstallRecoveryStore.onSetAside = { logged.append($0) }
        defer { LocalTerentoFailedInstallRecoveryStore.onSetAside = nil }

        try corrupt.write(to: recoveryURL)
        try store.record(record)
        guard logged.values.count == 1 else {
            throw TestFailure(message: "a quarantine inside record() leaves a diagnostic trace")
        }
        let quarantined = try FileManager.default.contentsOfDirectory(
            at: recoveryURL.deletingLastPathComponent(), includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix("failed-install-recovery.corrupt-") }
        guard quarantined.count == 1, try Data(contentsOf: quarantined[0]) == corrupt,
              try store.read(deviceKey: record.deviceKey) == [record] else {
            throw TestFailure(message: "an unreadable recovery file is set aside and the new record is kept")
        }

        try corrupt.write(to: recoveryURL)
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        guard let second = try store.quarantineUnreadableRecovery(now: now),
              second.lastPathComponent.hasPrefix("failed-install-recovery.corrupt-2026"),
              try Data(contentsOf: second) == corrupt,
              FileManager.default.fileExists(atPath: quarantined[0].path),
              try store.quarantineUnreadableRecovery(now: now) == nil else {
            throw TestFailure(message: "explicit recovery quarantine keeps every corrupt copy")
        }
        print("PASS: an unreadable recovery file is quarantined, never deleted, and does not block a new record")
    }

    /// A record this build cannot decode (e.g. a newer artifact kind after a
    /// downgrade) neither hides the others nor is silently dropped on rewrite.
    private static func testUnknownRecoveryRecordsAreKeptAside() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-recovery-lossy-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalTerentoFailedInstallRecoveryStore(rootDirectory: root)
        let recoveryURL = root.appendingPathComponent("Terento/failed-install-recovery.json")
        func record(_ region: String) throws -> TerentoFailedInstallRecoveryRecord {
            TerentoFailedInstallRecoveryRecord(
                deviceKey: "fenix8-test-device", packageID: "freizeitkarte-\(region.lowercased())",
                providerId: "freizeitkarte", regionId: region, version: try requireVersion(),
                devicePath: "/GARMIN/terento_freizeitkarte_\(region.lowercased()).img",
                filename: "terento_freizeitkarte_\(region.lowercased()).img",
                sizeBytes: 100, sha256: String(repeating: "a", count: 64), createdAt: Date(timeIntervalSince1970: 0))
        }
        let known = try record("DEU")
        let encoded = try JSONEncoder().encode(TerentoFailedInstallRecoveryFile(records: [known, try record("FRA")]))
        var json = String(decoding: encoded, as: UTF8.self)
        // Turn the second record into one with an artifact kind from a newer build.
        json = json.replacingOccurrences(of: "\"regionId\":\"FRA\"", with: "\"regionId\":\"FRA\",\"artifactKind\":\"hillshade\"")
        let original = Data(json.utf8)
        try FileManager.default.createDirectory(at: recoveryURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try original.write(to: recoveryURL)
        let logged = LoggedURLs()
        LocalTerentoFailedInstallRecoveryStore.onSetAside = { logged.append($0) }
        defer { LocalTerentoFailedInstallRecoveryStore.onSetAside = nil }

        guard try store.read(deviceKey: known.deviceKey) == [known],
              try store.quarantineUnreadableRecovery() == nil, logged.values.isEmpty else {
            throw TestFailure(message: "one undecodable record keeps the readable records and the file in place")
        }
        let added = try record("LTU")
        try store.record(added)
        guard logged.values.count == 1, try Data(contentsOf: logged.values[0]) == original,
              try store.read(deviceKey: known.deviceKey) == [known, added] else {
            throw TestFailure(message: "a rewrite first keeps a dated copy holding the undecodable record")
        }
        try store.record(try record("LVA"))
        guard logged.values.count == 1 else {
            throw TestFailure(message: "the copy is made once, not on every later rewrite")
        }
        print("PASS: undecodable recovery records are skipped on read and preserved in a dated copy before a rewrite")
    }

    private static func testManifestQuarantineMoveFailureIsTyped() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-manifest-move-\(UUID().uuidString)", isDirectory: true)
        let store = LocalTerentoManifestStore(rootDirectory: root)
        let entry = makeEntry(version: try requireVersion(), installedAt: 100, suffix: "x")
        try store.record(entry)
        let directory = root.appendingPathComponent("Terento/devices/\(entry.deviceKey)")
        try Data("{ not json".utf8).write(to: directory.appendingPathComponent("manifest.json"))
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: directory.path)
        defer {
            try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
            try? FileManager.default.removeItem(at: root)
        }
        do {
            _ = try store.quarantineUnreadableManifest(deviceKey: entry.deviceKey)
            throw TestFailure(message: "a quarantine that cannot rename must fail")
        } catch TerentoManifestStoreError.writeFailed {}
        print("PASS: a failed manifest quarantine rename reports writeFailed")
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

    private static func testPhysicalWatchKeysAreStableAndDistinct() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-device-key-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let deriver = LocalPhysicalDeviceKeyDeriver(rootDirectory: root)
        let watchA = try deriver.derive(source: "mtp-serial", value: "SERIAL-A")
        let watchAAgain = try deriver.derive(source: "mtp-serial", value: "SERIAL-A")
        let watchB = try deriver.derive(source: "mtp-serial", value: "SERIAL-B")
        let unitIDA = try deriver.derive(source: "garmin-unit-id", value: "UNIT-A")
        let unitIDB = try deriver.derive(source: "garmin-unit-id", value: "UNIT-B")
        let sameValueDifferentSource = try deriver.derive(source: "garmin-unit-id", value: "SERIAL-A")
        let secretURL = root.appendingPathComponent(".device-key-secret")
        let attributes = try FileManager.default.attributesOfItem(atPath: secretURL.path)
        let permissions = (attributes[.posixPermissions] as? NSNumber)?.intValue

        guard watchA == watchAAgain,
              watchA != watchB,
              unitIDA != unitIDB,
              watchA != sameValueDifferentSource,
              watchA.hasPrefix("watch-v2-"),
              !watchA.contains("SERIAL-A"),
              permissions == 0o600 else {
            throw TestFailure(message: "physical watch keys were not stable, distinct, private, and permission-restricted")
        }

        print("PASS: identical models can use stable, distinct physical-watch namespaces")
    }

    private static func testCatalogIdentityPreservesLegacyKeys() throws {
        for (model, expected) in [
            ("fenix 8 - 47mm", "fenix-8-091e-51b8"),
            ("fenix 8 Pro - 51mm AMOLED", "fenix-8-pro-091e-51b8"),
            ("Forerunner 965 - 47mm", "forerunner-965-47mm-091e-51b8"),
            ("fenix 9 Pro - 51mm", "fenix-9-pro-51mm-091e-51b8")
        ] {
            let identity = DeviceIdentity(manufacturer: "Garmin", model: model, family: nil, variant: nil,
                usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: nil, storageCapacity: 0, freeSpace: 0)
            let catalogIdentity = identity.applying(catalogMetadata: CatalogDeviceMetadata(
                candidateDeviceID: "server-owned-id", model: "New catalog label",
                screenTechnology: "AMOLED", solar: false, inReach: false))
            guard identity.legacyManifestDeviceKey == expected,
                  catalogIdentity.legacyManifestDeviceKey == expected else {
                throw TestFailure(message: "API identification changed an existing legacy ownership key")
            }
        }
        print("PASS: generic model identification and API hints preserve historical manifest namespaces")
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
            devicePath: "/GARMIN/terento_freizeitkarte_deu.img",
            filename: "terento_freizeitkarte_deu.img",
            providerId: "freizeitkarte",
            regionId: "DEU",
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

private final class LoggedURLs: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [URL] = []
    var values: [URL] { lock.withLock { stored } }
    func append(_ url: URL) { lock.withLock { stored.append(url) } }
}

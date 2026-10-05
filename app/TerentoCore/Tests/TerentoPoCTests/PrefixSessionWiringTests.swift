import Foundation

extension Bundle { static var module: Bundle { .main } }
@_silgen_name("terento_prefix_test_reset") private func resetFixture(_ scenario: Int32)
@_silgen_name("terento_prefix_test_reads") private func fixtureReads() -> Int32

@main
struct PrefixSessionWiringTests {
    static func main() throws {
        let identity = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8", family: "fēnix", variant: nil,
            usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: nil, storageCapacity: 1_000_000,
            freeSpace: 900_000, localHardwareIdentifier: "TEST-SERIAL-A", localIdentityResolution: .mtpSerial)
        let root = DeviceFile(itemID: 1, parentID: 0, storageID: 7,
            path: "/GARMIN", filename: "Garmin", sizeBytes: 0, isFolder: true)
        let resolved = try ResolvedMapWriteProfile.resolve(identity: identity, files: [root])
        try MTPMapInstallationTransport(operationProfile: resolved.operationProfile)
            .validateWriteTarget(identity: identity, files: [root])
        let changedStorage = DeviceFile(itemID: 1, parentID: 0, storageID: 8,
            path: root.path, filename: root.filename, sizeBytes: 0, isFolder: true)
        for (profile, files) in [(nil, [root]), (resolved.operationProfile, [changedStorage])] as [(DeviceMapOperationProfile?, [DeviceFile])] {
            do {
                try MTPMapInstallationTransport(operationProfile: profile).validateWriteTarget(identity: identity, files: files)
                fatalError("missing or stale production write profile accepted")
            } catch { precondition(error as? MapTargetResolutionError == .profileMismatch) }
        }
        print("PASS: actual write adapter rejects missing/stale profiles before native mutation")
        let first = DeviceFile(itemID: 10, parentID: 1, storageID: 1,
            path: "/GARMIN/expected.img", filename: "expected.img", sizeBytes: 8, isFolder: false)
        // Deliberately collide historical handles: results must correlate by descriptor.
        let second = DeviceFile(itemID: 10, parentID: 2, storageID: 1,
            path: "/GARMIN/second.img", filename: "second.img", sizeBytes: 8, isFolder: false)
        let transport = MTPTransport(operationGate: MTPOperationGate())
        resetFixture(2)
        let prefix = try transport.readFilePrefix(for: first, maxLength: 8)
        precondition(prefix == Array(repeating: UInt8(ascii: "A"), count: 8) && fixtureReads() == 1)
        resetFixture(11)
        let batch = try transport.readFilePrefixes(for: [second, first], maxLength: 8)
        precondition(batch.count == 2 && fixtureReads() == 2)
        precondition(batch[first.stableIdentity] == Array(repeating: UInt8(ascii: "A"), count: 8))
        precondition(batch[second.stableIdentity] == Array(repeating: UInt8(ascii: "B"), count: 8))
        resetFixture(1)
        do {
            _ = try transport.readFilePrefixes(for: [first, first], maxLength: 8)
            fatalError("duplicate descriptor requests silently collapsed")
        } catch { precondition(fixtureReads() == 0) }
        resetFixture(1)
        let invalid = DeviceFile(itemID: 10, parentID: 1, storageID: 1,
            path: first.path + "\0suffix", filename: first.filename, sizeBytes: 8, isFolder: false)
        do {
            _ = try transport.readFilePrefix(for: invalid, maxLength: 8)
            fatalError("embedded NUL was silently truncated")
        } catch { precondition(fixtureReads() == 0) }
        resetFixture(10)
        do {
            _ = try transport.readFilePrefixes(for: [first, second], maxLength: 8)
            fatalError("ambiguous batch member accepted")
        } catch { precondition(fixtureReads() == 0) }
        print("PASS: actual Swift prefix transport uses stable descriptors, correct correlation and atomic batch resolution")
        resetFixture(18)
        let heavy = try MTPTransport(operationGate: MTPOperationGate()).readFileInventory()
        precondition(heavy.count == 12_005)
        let protected = try ProtectedMapInventory(files: heavy)
        precondition(protected.toleratedDuplicateLocationCount == 1 && protected.protected.count == heavy.count)
        let bound = MTPFinishingWorker.inventoryTimeout(expectedObjectCount: heavy.count)
        precondition(bound > 60 && bound < 600)
        print("PASS: heavy-watch inventory with duplicate music stays protected; worker bound \(Int(bound)) s scales with 12,005 objects")
    }
}

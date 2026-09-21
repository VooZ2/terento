import Foundation

extension Bundle { static var module: Bundle { .main } }
@_silgen_name("terento_prefix_test_reset") private func resetFixture(_ scenario: Int32)
@_silgen_name("terento_prefix_test_reads") private func fixtureReads() -> Int32

@main
struct PrefixSessionWiringTests {
    static func main() throws {
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
    }
}

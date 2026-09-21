// The runner compiles the unchanged production cache and target declarations
// with these minimal domain fixtures. No MTP implementation is linked.
struct MapIdentity: Equatable, Sendable { let key: String }
enum MapManagementState: Equatable, Sendable { case managedByTerento, detectedNotManaged, unknown }
struct MapVersion: Equatable, Sendable { let value: String }
struct InstalledMapFile: Equatable, Sendable {
    let path: String
    let filename: String
    let sizeBytes: UInt64
    let itemID: UInt32?
}

@main
struct ExternalRemovalEvidenceTests {
    static func main() {
        func target(path: String = "/GARMIN/external.img", device: String = "test-device",
                    size: UInt64 = 100, allow: Bool = true, hash: String = "") -> SafeDeleteTarget {
            SafeDeleteTarget(
                deviceKey: device, mapIdentity: MapIdentity(key: "map"),
                ownership: .detectedNotManaged, objectID: 7,
                expectedPath: path, expectedFilename: "external.img", expectedSizeBytes: size,
                expectedSHA256: hash, allowsExternalRemoval: allow
            )
        }
        let cache = ExternalRemovalEvidence()
        let selected = target()
        let digest = String(repeating: "a", count: 64)
        precondition(cache.consume(target: selected) == nil)
        cache.store(target: selected, sha256: digest)
        precondition(cache.consume(target: selected.resolvingObjectID(99)) == digest)
        precondition(cache.consume(target: selected) == nil)
        for wrong in [target(path: "/GARMIN/other.img"), target(device: "other-device"),
                      target(size: 101), target(allow: false), target(hash: "changed")] {
            cache.store(target: selected, sha256: digest)
            precondition(cache.consume(target: wrong) == nil)
            precondition(cache.consume(target: selected) == nil)
        }
        cache.store(target: selected, sha256: digest)
        cache.clear()
        precondition(cache.consume(target: selected) == nil)
        cache.store(target: selected, sha256: digest)
        let sharedReference = cache
        precondition(sharedReference.consume(target: selected) == digest)
        precondition(cache.consume(target: selected) == nil)
        cache.store(target: selected, sha256: digest)
        let results = Results()
        DispatchQueue.concurrentPerform(iterations: 32) { _ in
            if cache.consume(target: selected) != nil { results.recordSuccess() }
        }
        precondition(results.count == 1)
        print("PASS: actual external evidence cache matches exact target, ignores session handles, consumes once and serializes concurrent consumption")
    }
}

private final class Results: @unchecked Sendable {
    private let lock = NSLock()
    private var successes = 0
    var count: Int { lock.lock(); defer { lock.unlock() }; return successes }
    func recordSuccess() { lock.lock(); defer { lock.unlock() }; successes += 1 }
}

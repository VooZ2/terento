import CryptoKit
import Foundation

private enum ProofTestError: Error { case failed(String) }

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else { throw ProofTestError.failed(message) }
}

/// Deterministic content shared with NativeRemovalProofTests.c.
private func contentByte(_ offset: UInt64) -> UInt8 {
    if offset < 0x48 {
        if (0x10..<0x16).contains(offset) { return Array("DSKIMG".utf8)[Int(offset - 0x10)] }
        if (0x41..<0x47).contains(offset) { return Array("GARMIN".utf8)[Int(offset - 0x41)] }
        return 0
    }
    return UInt8(truncatingIfNeeded: ((offset &* 2654435761) >> 13) ^ (offset >> 20))
}

private func hex<D: Sequence>(_ digest: D) -> String where D.Element == UInt8 {
    digest.map { String(format: "%02x", $0) }.joined()
}

private func writeContent(size: UInt64) throws -> (URL, Data, String) {
    var data = Data(count: Int(size))
    data.withUnsafeMutableBytes { (buffer: UnsafeMutableRawBufferPointer) in
        for index in 0..<Int(size) { buffer[index] = contentByte(UInt64(index)) }
    }
    let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-removal-proof-\(UUID().uuidString).img")
    try data.write(to: url, options: .atomic)
    return (url, data, hex(SHA256.hash(data: data)))
}

/// Independent digest of the concatenated regions, not the production pass.
private func regionDigest(_ data: Data, offsets: [UInt64]) -> String {
    var hasher = SHA256()
    for offset in offsets {
        let end = min(Int(offset) + Int(ManagedRemovalProof.regionLength), data.count)
        hasher.update(data: data[Int(offset)..<end])
    }
    return hex(hasher.finalize())
}

// Golden values recorded from this implementation; NativeRemovalProofTests.c
// accepts exactly this plan and digest for the same virtual content.
private let goldenSize: UInt64 = 5_000_000
private let goldenPlan: [UInt64] = [
    0, 81005, 234085, 479683, 615030, 739104, 943268, 1060447,
    1233770, 1388787, 1606203, 1700738, 1913924, 2077926, 2186130, 2408816,
    2521019, 2721118, 2844610, 3013496, 3218342, 3407722, 3515707, 3712406,
    3806923, 4005117, 4165570, 4366903, 4492503, 4647142, 4825178, 4934465
]
private let goldenDigest = "ec831e2f7c30ea1650efecec649b82c2c27a85c043d987470308487877d089f1"
private let goldenFullSHA256 = "35b075826c4725a555a932903ef651024a548690b825fd366fa1558da901da1e"

private func testPlanGeometry() throws {
    let length = UInt64(ManagedRemovalProof.regionLength)
    let hash = String(repeating: "ab", count: 32)
    for size: UInt64 in [434_000_000, 5_000_000, 32 * 65_535 + 1, 32 * 65_535, 150_000, 65_535, 512] {
        let plan = ManagedRemovalProof.plan(fileSizeBytes: size, fileSHA256: hash)
        try require(plan == ManagedRemovalProof.plan(fileSizeBytes: size, fileSHA256: hash), "plan is deterministic")
        try require(plan.first == 0, "plan starts with the IMG header region (\(size))")
        var coveredEnd: UInt64 = 0
        var total: UInt64 = 0
        for (index, offset) in plan.enumerated() {
            try require(offset < size && (index == 0 || offset >= coveredEnd), "regions sorted and disjoint (\(size))")
            let region = min(length, size - offset)
            coveredEnd = offset + region
            total += region
        }
        try require(coveredEnd == size, "plan ends at the last byte (\(size))")
        if size > 32 * length {
            try require(plan.count == 32 && total == 32 * length, "large maps read exactly 32 full regions")
        } else {
            try require(total == size, "small maps are covered completely (\(size))")
        }
        let proof = ManagedRemovalProof(offsets: plan, sha256: String(repeating: "c", count: 64))
        try require(proof.sampledBytes(fileSizeBytes: size) == total, "sampled byte count matches the plan")
    }
    let large: UInt64 = 434_000_000
    let first = ManagedRemovalProof.plan(fileSizeBytes: large, fileSHA256: hash)
    let other = ManagedRemovalProof.plan(fileSizeBytes: large, fileSHA256: String(repeating: "cd", count: 32))
    try require(first != other, "a different artifact gets a different interior plan")
    try require(first.last == large - length && other.last == large - length, "the final bytes are always sampled")
    // The 30 interior regions are spread over equal strata of the file.
    let width = (large - 2 * length) / 30
    for index in 0..<30 {
        let lower = length + UInt64(index) * width
        try require(first[index + 1] >= lower && first[index + 1] + length <= lower + width,
                    "interior region \(index) stays inside its stratum")
    }
}

private func testMakeRecordsIndependentDigestAndGolden() throws {
    let (url, data, sha) = try writeContent(size: goldenSize)
    defer { try? FileManager.default.removeItem(at: url) }
    guard let proof = ManagedRemovalProof.make(localFileURL: url, fileSizeBytes: goldenSize, fileSHA256: sha) else {
        throw ProofTestError.failed("a verified local artifact must yield a proof")
    }
    try require(proof.format == 1 && proof.regionLength == 65_535 && proof.offsets.count == 32, "format-1 geometry")
    try require(proof.sha256 == regionDigest(data, offsets: proof.offsets), "digest of the concatenated regions")
    try require(proof.isBound(toFileSizeBytes: goldenSize, fileSHA256: sha), "fresh proof is bound to its artifact")
    if ProcessInfo.processInfo.environment["TERENTO_PRINT_REMOVAL_GOLDEN"] == "1" {
        FileHandle.standardError.write(Data(("GOLDEN_PLAN=\(proof.offsets.map(String.init).joined(separator: ","))\n"
            + "GOLDEN_DIGEST=\(proof.sha256)\nGOLDEN_FULL=\(sha)\n").utf8))
    }
    try require(sha == goldenFullSHA256 && proof.offsets == goldenPlan && proof.sha256 == goldenDigest,
                "golden plan and digest shared with the native harness")
    // Uppercase hashes in old records still bind to the same plan.
    try require(proof.isBound(toFileSizeBytes: goldenSize, fileSHA256: sha.uppercased()), "hash case is ignored")
}

private func testMakeRefusesUnverifiedLocalBytes() throws {
    let (url, _, sha) = try writeContent(size: 300_000)
    defer { try? FileManager.default.removeItem(at: url) }
    try require(ManagedRemovalProof.make(localFileURL: url, fileSizeBytes: 300_000, fileSHA256: sha) != nil, "control")
    try require(ManagedRemovalProof.make(localFileURL: url, fileSizeBytes: 300_000,
        fileSHA256: String(repeating: "e", count: 64)) == nil, "different full SHA-256 records no proof")
    try require(ManagedRemovalProof.make(localFileURL: url, fileSizeBytes: 300_001, fileSHA256: sha) == nil,
                "different size records no proof")
    try require(ManagedRemovalProof.make(localFileURL: url.appendingPathExtension("missing"),
        fileSizeBytes: 300_000, fileSHA256: sha) == nil, "missing artifact records no proof")
    try require(ManagedRemovalProof.make(localFileURL: url, fileSizeBytes: 300_000, fileSHA256: "abc") == nil,
                "malformed hash records no proof")
    let (tiny, _, tinySHA) = try writeContent(size: 100)
    defer { try? FileManager.default.removeItem(at: tiny) }
    try require(ManagedRemovalProof.make(localFileURL: tiny, fileSizeBytes: 100, fileSHA256: tinySHA) == nil,
                "a file below the IMG minimum records no proof")
}

private func testBindingAndNativeSelection() throws {
    let size: UInt64 = 434_000_000
    let sha = String(repeating: "ab", count: 32)
    let plan = ManagedRemovalProof.plan(fileSizeBytes: size, fileSHA256: sha)
    let digest = String(repeating: "c", count: 64)
    let proof = ManagedRemovalProof(offsets: plan, sha256: digest)
    try require(proof.isBound(toFileSizeBytes: size, fileSHA256: sha), "control binding")
    var shifted = plan; shifted[3] += 1
    let unbound: [ManagedRemovalProof] = [
        ManagedRemovalProof(offsets: shifted, sha256: digest),
        ManagedRemovalProof(offsets: Array(plan.dropLast()), sha256: digest),
        ManagedRemovalProof(format: 2, offsets: plan, sha256: digest),
        ManagedRemovalProof(regionLength: 65_536, offsets: plan, sha256: digest),
        ManagedRemovalProof(offsets: plan, sha256: String(repeating: "0", count: 64)),
        ManagedRemovalProof(offsets: plan, sha256: "not-a-digest")
    ]
    for candidate in unbound {
        try require(!candidate.isBound(toFileSizeBytes: size, fileSHA256: sha), "unbound proof is rejected")
        try require(ManagedRemovalProof.forNativeRemoval(candidate, managed: true, fileSizeBytes: size,
            fileSHA256: sha) == nil, "unbound proof falls back to the full check")
    }
    try require(!proof.isBound(toFileSizeBytes: size + 1, fileSHA256: sha), "other size is rejected")
    try require(!proof.isBound(toFileSizeBytes: size, fileSHA256: String(repeating: "cd", count: 32)),
                "other artifact hash is rejected")
    try require(ManagedRemovalProof.forNativeRemoval(proof, managed: true, fileSizeBytes: size, fileSHA256: sha) == proof,
                "managed removal with a bound proof uses sampled reads")
    try require(ManagedRemovalProof.forNativeRemoval(proof, managed: false, fileSizeBytes: size, fileSHA256: sha) == nil,
                "external removal never uses a proof")
    try require(ManagedRemovalProof.forNativeRemoval(nil, managed: true, fileSizeBytes: size, fileSHA256: sha) == nil,
                "entries without a proof keep the full check")
}

private func testManifestBackwardCompatibility() throws {
    let legacy = """
    {"entries":[{"deviceKey":"garmin-test","devicePath":"/GARMIN/terento_freizeitkarte_fra.img",
    "filename":"terento_freizeitkarte_fra.img","providerId":"freizeitkarte","regionId":"FRA",
    "version":{"year":2026,"month":5},"sizeBytes":434000000,
    "sha256":"\(String(repeating: "ab", count: 32))","installedAt":700000000}]}
    """
    let decoded = try JSONDecoder().decode(TerentoManifest.self, from: Data(legacy.utf8))
    try require(decoded.entries.count == 1 && decoded.entries[0].removalProof == nil
                && decoded.entries[0].boundRemovalProof == nil, "an old entry decodes without a proof")
    let reencoded = String(decoding: try JSONEncoder().encode(decoded), as: UTF8.self)
    try require(!reencoded.contains("removalProof"), "an old entry is re-encoded unchanged (no proof key)")

    let entry = decoded.entries[0]
    let proof = ManagedRemovalProof(offsets: ManagedRemovalProof.plan(fileSizeBytes: entry.sizeBytes,
        fileSHA256: entry.sha256), sha256: String(repeating: "c", count: 64))
    let withProof = TerentoManifestEntry(deviceKey: entry.deviceKey, devicePath: entry.devicePath,
        filename: entry.filename, providerId: entry.providerId, regionId: entry.regionId,
        version: entry.version, sizeBytes: entry.sizeBytes, sha256: entry.sha256,
        installedAt: entry.installedAt, removalProof: proof)
    let encoded = try JSONEncoder().encode(TerentoManifest(entries: [withProof]))
    let roundTrip = try JSONDecoder().decode(TerentoManifest.self, from: encoded)
    try require(roundTrip.entries == [withProof] && roundTrip.entries[0].boundRemovalProof == proof,
                "a new entry round-trips with its proof")

    let malformed = legacy.replacingOccurrences(of: "\"installedAt\":700000000",
        with: "\"installedAt\":700000000,\"removalProof\":{\"format\":\"x\"}")
    let tolerated = try JSONDecoder().decode(TerentoManifest.self, from: Data(malformed.utf8))
    try require(tolerated.entries.count == 1 && tolerated.entries[0].removalProof == nil,
                "an unreadable proof never makes the ownership record unreadable")

    let mismatched = TerentoManifestEntry(deviceKey: entry.deviceKey, devicePath: entry.devicePath,
        filename: entry.filename, providerId: entry.providerId, regionId: entry.regionId,
        version: entry.version, sizeBytes: entry.sizeBytes + 1, sha256: entry.sha256,
        installedAt: entry.installedAt, removalProof: proof)
    try require(mismatched.boundRemovalProof == nil, "a proof for other bytes is not used")

    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("terento-proof-manifest-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let store = LocalTerentoManifestStore(rootDirectory: root)
    try store.record(withProof)
    let stored = try store.read(deviceKey: entry.deviceKey)
    try require(stored?.entries == [withProof], "the local manifest store persists the proof")
}

@main
struct ManagedRemovalProofTests {
    static func main() throws {
        let tests: [(String, () throws -> Void)] = [
            ("format-1 plan geometry", testPlanGeometry),
            ("proof digest and cross-language golden", testMakeRecordsIndependentDigestAndGolden),
            ("no proof from unverified local bytes", testMakeRefusesUnverifiedLocalBytes),
            ("binding and native proof selection", testBindingAndNativeSelection),
            ("manifest backward compatibility", testManifestBackwardCompatibility)
        ]
        for (name, test) in tests {
            try test()
            print("PASS: \(name)")
        }
        print("PASS: \(tests.count) managed removal proof tests")
    }
}

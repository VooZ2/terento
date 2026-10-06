import Foundation

enum TransferVerificationStatus: String, Equatable, Sendable {
    case verifiedSampledReadBack = "INSTALL_VERIFIED_SAMPLED_READBACK_V1"
    case verifiedFullSHA256 = "INSTALL_VERIFIED_FULL_SHA256"
    case sizeMismatch = "INSTALL_FAILED_SIZE_MISMATCH"
    case hashMismatch = "INSTALL_FAILED_HASH_MISMATCH"
}

enum TransferVerificationMode: String, Equatable, Sendable {
    case fullHash = "full-hash"
    case sampledReadBack = "sampled-readback-v1"
}

struct TransferVerification: Equatable, Sendable {
    let status: TransferVerificationStatus
    let sourceSizeBytes: UInt64
    let sourceSHA256: String
    let remoteSizeBytes: UInt64
    let remoteSHA256: String
    let mode: TransferVerificationMode
    let sampledBytes: UInt64
    let sampleCount: Int
    let matchedSampleCount: Int

    var isVerified: Bool {
        status == .verifiedSampledReadBack || status == .verifiedFullSHA256
    }

    static func sampled(
        sourceSizeBytes: UInt64,
        sourceSHA256: String,
        remoteSizeBytes: UInt64,
        sampledBytes: UInt64,
        sampleCount: Int,
        matchedSampleCount: Int
    ) -> TransferVerification {
        let status: TransferVerificationStatus = sourceSizeBytes == remoteSizeBytes
            && sampleCount == matchedSampleCount
            ? .verifiedSampledReadBack
            : sourceSizeBytes == remoteSizeBytes ? .hashMismatch : .sizeMismatch

        return TransferVerification(
            status: status,
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: "",
            mode: .sampledReadBack,
            sampledBytes: sampledBytes,
            sampleCount: sampleCount,
            matchedSampleCount: matchedSampleCount
        )
    }
}

/// The sampled read-back of a written map against its validated local
/// artifact: the first and last 4 MiB plus up to five regions spread by the
/// artifact SHA-256 (at most 7 regions, 28 MiB). Fresh installation and Safe
/// Update's new-map verification use exactly this plan.
enum SampledReadBackPlan {
    static let sampleLength: UInt32 = 4 * 1024 * 1024

    static func offsets(fileSizeBytes: UInt64, sourceSHA256: String) -> [UInt64] {
        let sampleLength = min(UInt64(Self.sampleLength), fileSizeBytes)
        let maximumOffset = fileSizeBytes - sampleLength
        guard maximumOffset > 0 else {
            return [0]
        }

        var seed: UInt64 = 0xcbf29ce484222325
        for byte in sourceSHA256.utf8 {
            seed ^= UInt64(byte)
            seed = seed &* 0x100000001b3
        }

        var offsets: Set<UInt64> = [0, maximumOffset]
        for _ in 0..<5 {
            seed = seed &* 2862933555777941757 &+ 3037000493
            offsets.insert(seed % (maximumOffset + 1))
        }
        return offsets.sorted()
    }
}

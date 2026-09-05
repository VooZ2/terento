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

struct TransferVerifier: Sendable {
    func verify(
        sourceSizeBytes: UInt64,
        sourceSHA256: String,
        remoteSizeBytes: UInt64,
        remoteSHA256: String
    ) -> TransferVerification {
        let status: TransferVerificationStatus
        if sourceSizeBytes != remoteSizeBytes {
            status = .sizeMismatch
        } else if sourceSHA256.caseInsensitiveCompare(remoteSHA256) != .orderedSame {
            status = .hashMismatch
        } else {
            status = .verifiedFullSHA256
        }

        return TransferVerification(
            status: status,
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: remoteSHA256,
            mode: .fullHash,
            sampledBytes: remoteSizeBytes,
            sampleCount: 0,
            matchedSampleCount: 0
        )
    }
}

import Foundation

enum TransferVerificationStatus: String, Equatable, Sendable {
    case verified = "INSTALL_VERIFIED"
    case sizeMismatch = "INSTALL_FAILED_SIZE_MISMATCH"
    case hashMismatch = "INSTALL_FAILED_HASH_MISMATCH"
}

struct TransferVerification: Equatable, Sendable {
    let status: TransferVerificationStatus
    let sourceSizeBytes: UInt64
    let sourceSHA256: String
    let remoteSizeBytes: UInt64
    let remoteSHA256: String

    var isVerified: Bool {
        status == .verified
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
            status = .verified
        }

        return TransferVerification(
            status: status,
            sourceSizeBytes: sourceSizeBytes,
            sourceSHA256: sourceSHA256,
            remoteSizeBytes: remoteSizeBytes,
            remoteSHA256: remoteSHA256
        )
    }
}

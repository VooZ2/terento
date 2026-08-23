import Foundation

enum CompatibilityStatus: String, Codable, CaseIterable, Sendable {
    case unknown = "UNKNOWN"
    case testing = "TESTING"
    case tested = "TESTED"
    case supported = "SUPPORTED"
    case verified = "VERIFIED"

    var userLabel: String {
        switch self {
        case .unknown:
            return "Unknown"
        case .testing:
            return "Testing"
        case .tested:
            return "Tested"
        case .supported:
            return "Supported"
        case .verified:
            return "Verified"
        }
    }
}

enum EvidenceResult: String, Sendable, Equatable {
    case pass = "PASS"
    case pending = "PENDING"
    case fail = "FAIL"

    var userLabel: String {
        switch self {
        case .pass:
            return "Complete"
        case .pending:
            return "Not tested yet"
        case .fail:
            return "Failed"
        }
    }
}

struct CompatibilityEvidence: Sendable, Equatable {
    let usb: EvidenceResult
    let mtp: EvidenceResult
    let deviceInfo: EvidenceResult
    let storage: EvidenceResult
    let map: EvidenceResult

    // These remain internal evidence until a later PoC exercises the full map flow.
    let reconnect: EvidenceResult
    let mapVisible: EvidenceResult
    let multiplePhysicalDevices: EvidenceResult
    let firmwareVariation: EvidenceResult

    static let nativeConnectivityTested = CompatibilityEvidence(
        usb: .pass,
        mtp: .pass,
        deviceInfo: .pass,
        storage: .pass,
        map: .pending,
        reconnect: .pending,
        mapVisible: .pending,
        multiplePhysicalDevices: .pending,
        firmwareVariation: .pending
    )
}

struct DeviceIdentity: Sendable, Equatable {
    let manufacturer: String
    let model: String
    let family: String?
    let variant: String?
    let usbVendorId: UInt16
    let usbProductId: UInt16
    let firmware: String?
    let storageCapacity: UInt64
    let freeSpace: UInt64

    /// Stable model identity derived from the raw MTP model string when the
    /// string matches a locally validated model grammar. Cosmetic display
    /// variants are deliberately not part of this value.
    var canonicalModel: String? {
        GarminDeviceModelNormalizer.canonicalModel(from: model)
    }
}

struct GarminDeviceModelNormalizer: Sendable {
    static func canonicalModel(from rawModel: String) -> String? {
        let normalized = normalize(rawModel)

        // Keep this list explicit. A model prefix alone is not sufficient to
        // authorize a device install target.
        switch normalized {
        case "fenix 8", "fenix 8 47mm", "fenix 8 amoled 47mm":
            return "fēnix 8"
        default:
            return nil
        }
    }

    static func normalize(_ value: String) -> String {
        value
            .folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

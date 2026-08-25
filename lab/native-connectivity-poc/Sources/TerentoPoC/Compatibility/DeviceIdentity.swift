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

    /// Presentation/catalog identity for models that do not yet have a local
    /// transport/install profile. This never authorizes device writes.
    var catalogCanonicalModel: String? {
        GarminDeviceModelNormalizer.catalogCanonicalModel(from: model)
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

    static func catalogCanonicalModel(from rawModel: String) -> String? {
        var normalized = normalize(rawModel)
        if normalized.hasPrefix("garmin ") {
            normalized.removeFirst("garmin ".count)
        }
        let knownPrefixes = [
            "approach",
            "d2 mach",
            "descent",
            "enduro",
            "epix",
            "fenix",
            "forerunner",
            "instinct",
            "lily",
            "marq",
            "quatix",
            "tactix",
            "venu",
            "vivoactive",
            "vivomove"
        ]

        guard knownPrefixes.contains(where: normalized.hasPrefix) else {
            return nil
        }

        let cosmeticTokens = [
            " sapphire",
            " solar",
            " amoled",
            " mip",
            " microled",
            " leather",
            " titanium",
            " stainless",
            " silicone"
        ]
        for token in cosmeticTokens {
            if let range = normalized.range(of: token) {
                normalized = String(normalized[..<range.lowerBound])
            }
        }

        if let range = normalized.range(of: #"\s\d{2,3}\s*mm"#, options: .regularExpression) {
            normalized = String(normalized[..<range.lowerBound])
        }
        return normalized
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

/// Garmin's user-facing firmware notation is `major.minor`, while some MTP
/// devices expose the same value as a compact numeric string such as `2244`.
/// Keep the raw value in `DeviceIdentity` for compatibility gates and normalize
/// only the value shown in the UI.
enum GarminFirmwareVersionFormatter: Sendable {
    static func display(rawValue: String, manufacturer: String) -> String {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              isGarminManufacturer(manufacturer),
              !trimmed.contains("."),
              trimmed.allSatisfy(\.isNumber) else {
            return trimmed
        }

        switch trimmed.count {
        case 3:
            return "\(trimmed.prefix(1)).\(trimmed.suffix(2))"
        case 4:
            let major = Int(trimmed.prefix(2))
                .map(String.init)
                ?? String(trimmed.prefix(2))
            return "\(major).\(trimmed.suffix(2))"
        default:
            return trimmed
        }
    }

    private static func isGarminManufacturer(_ value: String) -> Bool {
        value.range(of: "garmin", options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
}

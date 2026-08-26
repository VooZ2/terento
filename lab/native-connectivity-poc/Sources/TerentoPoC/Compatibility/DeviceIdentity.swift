import Foundation

enum CompatibilityStatus: String, Codable, CaseIterable, Sendable {
    case testing = "TESTING"
    case tested = "TESTED"
    case supported = "SUPPORTED"
    case verified = "VERIFIED"

    var userLabel: String {
        switch self {
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
    let localHardwareIdentifier: String?

    init(
        manufacturer: String,
        model: String,
        family: String?,
        variant: String?,
        usbVendorId: UInt16,
        usbProductId: UInt16,
        firmware: String?,
        storageCapacity: UInt64,
        freeSpace: UInt64,
        localHardwareIdentifier: String? = nil
    ) {
        self.manufacturer = manufacturer
        self.model = model
        self.family = family
        self.variant = variant
        self.usbVendorId = usbVendorId
        self.usbProductId = usbProductId
        self.firmware = firmware
        self.storageCapacity = storageCapacity
        self.freeSpace = freeSpace
        self.localHardwareIdentifier = localHardwareIdentifier
    }

    /// Stable model identity derived from the raw MTP model string when the
    /// string matches a locally validated model grammar. Cosmetic display
    /// variants are deliberately not part of this value.
    var canonicalModel: String? {
        GarminDeviceModelNormalizer.canonicalModel(from: model)
    }

    /// Exact compatibility identity used for evidence aggregation.  The
    /// family/model label is intentionally augmented with case size and
    /// display evidence when available so 47 mm and 51 mm never share a
    /// status accidentally.
    var compatibilityIdentity: String {
        guard let canonicalModel else { return model.trimmingCharacters(in: .whitespacesAndNewlines) }
        let identitySource = [model, variant].compactMap { $0 }.joined(separator: " ")
        let size = GarminDeviceModelNormalizer.caseSizeMm(from: identitySource)
        let display = GarminDeviceModelNormalizer.displayType(from: identitySource)
        var details: [String] = []
        if let size { details.append("\(size) mm") }
        if let display { details.append(display) }
        guard !details.isEmpty else { return canonicalModel }
        return "\(canonicalModel) · \(details.joined(separator: ", "))"
    }

    var caseSizeMm: Int? {
        let identitySource = [model, variant].compactMap { $0 }.joined(separator: " ")
        return GarminDeviceModelNormalizer.caseSizeMm(from: identitySource)
    }

    var displayType: String? {
        let identitySource = [model, variant].compactMap { $0 }.joined(separator: " ")
        return GarminDeviceModelNormalizer.displayType(from: identitySource)
    }

    /// Canonical catalog identity backed by separately reviewed hardware
    /// evidence. This is intentionally narrower than model normalization:
    /// model text, case size, or artwork alone must never manufacture an
    /// AMOLED/Solar distinction.
    var reviewedCanonicalDeviceID: String? {
        guard usbVendorId == 0x091e,
              usbProductId == 0x51b8,
              canonicalModel == "fēnix 8",
              caseSizeMm == 47,
              displayType == nil || displayType == "AMOLED" else {
            return nil
        }
        return "garmin-fenix-8-47-amoled"
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
        case let value where value == "fenix 8" || value.hasPrefix("fenix 8 "):
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

    static func caseSizeMm(from value: String) -> Int? {
        guard let match = normalize(value).range(of: #"\b(\d{2,3})\s*mm\b"#, options: .regularExpression) else {
            return nil
        }
        let digits = normalize(value)[match]
            .replacingOccurrences(of: "mm", with: "")
            .trimmingCharacters(in: .whitespaces)
        return Int(digits)
    }

    static func displayType(from value: String) -> String? {
        let normalized = normalize(value)
        if normalized.contains("microled") { return "MicroLED" }
        if normalized.contains("amoled") { return "AMOLED" }
        if normalized.contains("solar") { return "Solar" }
        return nil
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

enum ConnectedDeviceSubtitleFormatter: Sendable {
    static func format(identity: DeviceIdentity, fallbackModel: String, manufacturer: String) -> String {
        var parts: [String] = []
        if let size = identity.caseSizeMm {
            parts.append("\(size) mm")
        }
        if let display = identity.displayType {
            parts.append(display)
        }
        if parts.isEmpty {
            let fallback = (identity.variant ?? fallbackModel)
                .replacingOccurrences(of: "47mm", with: "47 mm", options: .caseInsensitive)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !fallback.isEmpty { parts.append(fallback) }
        }
        let firmware = GarminFirmwareVersionFormatter.display(
            rawValue: identity.firmware ?? "",
            manufacturer: manufacturer
        )
        if !firmware.isEmpty { parts.append("Firmware \(firmware)") }
        return parts.joined(separator: " · ")
    }
}

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

/// Catalog hints are fetched from the API. They never authorize a write or
/// replace original MTP/XML observations; the server rechecks submitted IDs.
struct CatalogDeviceMetadata: Sendable, Equatable {
    let candidateDeviceID: String?
    let model: String
    let screenTechnology: String?
    let solar: Bool?
    let inReach: Bool?
}

struct DeviceIdentity: Sendable, Equatable {
    enum LocalIdentityResolution: String, Sendable, Equatable {
        case mtpSerial = "MTP_SERIAL"
        case garminUnitID = "GARMIN_UNIT_ID"
        case unavailable = "UNAVAILABLE"
    }

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
    let localIdentityResolution: LocalIdentityResolution
    let deviceDescription: String?
    let garminModelDescription: String?
    let garminModelPartNumber: String?
    let garminDeviceXMLStatus: GarminDeviceXMLReadStatus
    let catalogMetadata: CatalogDeviceMetadata?

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
        localHardwareIdentifier: String? = nil,
        localIdentityResolution: LocalIdentityResolution? = nil,
        deviceDescription: String? = nil,
        garminDeviceXMLStatus: GarminDeviceXMLReadStatus = .unavailable,
        garminModelDescription: String? = nil,
        garminModelPartNumber: String? = nil,
        catalogMetadata: CatalogDeviceMetadata? = nil
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
        self.localIdentityResolution = localIdentityResolution
            ?? (localHardwareIdentifier == nil ? .unavailable : .mtpSerial)
        self.deviceDescription = deviceDescription
        self.garminModelDescription = garminModelDescription
        self.garminModelPartNumber = garminModelPartNumber
        self.garminDeviceXMLStatus = garminDeviceXMLStatus
        self.catalogMetadata = catalogMetadata
    }

    /// Stable model identity derived from the raw MTP model string when the
    /// string matches a locally validated model grammar. Cosmetic display
    /// variants are deliberately not part of this value.
    var canonicalModel: String? {
        GarminDeviceModelNormalizer.canonicalModel(from: identityModelSource)
    }

    var presentationModel: String {
        catalogMetadata?.model ?? canonicalModel ?? deviceDescription?.trimmingCharacters(in: .whitespacesAndNewlines)
            ?? model.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var identityModelSource: String {
        let description = deviceDescription?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return description.isEmpty ? model : description
    }

    /// Exact compatibility identity used for evidence aggregation.  The
    /// family/model label is intentionally augmented with case size and
    /// display evidence when available so 47 mm and 51 mm never share a
    /// status accidentally.
    var compatibilityIdentity: String {
        guard let canonicalModel else { return presentationModel }
        let identitySource = [identityModelSource, model, variant, garminModelDescription].compactMap { $0 }.joined(separator: " ")
        let size = GarminDeviceModelNormalizer.caseSizeMm(from: identitySource)
        let display = GarminDeviceModelNormalizer.displayType(from: identitySource)
        var details: [String] = []
        if let size { details.append("\(size) mm") }
        if let display { details.append(display) }
        guard !details.isEmpty else { return canonicalModel }
        return "\(canonicalModel) · \(details.joined(separator: ", "))"
    }

    var caseSizeMm: Int? {
        let identitySource = [identityModelSource, model, variant, garminModelDescription].compactMap { $0 }.joined(separator: " ")
        return GarminDeviceModelNormalizer.caseSizeMm(from: identitySource)
    }

    var displayType: String? {
        let identitySource = [identityModelSource, model, variant, garminModelDescription].compactMap { $0 }.joined(separator: " ")
        return GarminDeviceModelNormalizer.displayType(from: identitySource)
    }

    // Additional presentation/diagnostic facts never participate in local
    // ownership keys or write-profile validation.
    private var reportedModelText: String {
        [model, garminModelDescription].compactMap { $0 }.joined(separator: " ")
    }

    var screenTechnology: String? {
        if hasReportedScreenTechnology {
            return GarminDeviceModelNormalizer.screenTechnology(from: reportedModelText)
        }
        return catalogMetadata?.screenTechnology
    }

    private var hasReportedScreenTechnology: Bool {
        ["amoled", "microled", "mip"].contains {
            GarminDeviceModelNormalizer.hasExplicitFeature($0, in: reportedModelText)
        }
    }

    var screenTechnologySource: String {
        if hasReportedScreenTechnology {
            return screenTechnology == nil ? "Conflicting MTP/XML model text" : "MTP/XML model text"
        }
        return screenTechnology == nil ? "Unavailable" : "Terento API catalog"
    }

    var solar: Bool? {
        GarminDeviceModelNormalizer.hasExplicitFeature("solar", in: reportedModelText) ? true : catalogMetadata?.solar
    }

    var inReach: Bool? {
        GarminDeviceModelNormalizer.hasExplicitFeature("inreach", in: reportedModelText) ? true : catalogMetadata?.inReach
    }

    var catalogDeviceID: String? { catalogMetadata?.candidateDeviceID }

    func applying(catalogMetadata: CatalogDeviceMetadata?) -> DeviceIdentity {
        DeviceIdentity(manufacturer: manufacturer, model: model, family: family, variant: variant,
            usbVendorId: usbVendorId, usbProductId: usbProductId, firmware: firmware,
            storageCapacity: storageCapacity, freeSpace: freeSpace,
            localHardwareIdentifier: localHardwareIdentifier, localIdentityResolution: localIdentityResolution,
            deviceDescription: deviceDescription, garminDeviceXMLStatus: garminDeviceXMLStatus,
            garminModelDescription: garminModelDescription, garminModelPartNumber: garminModelPartNumber,
            catalogMetadata: catalogMetadata)
    }

    /// Presentation/catalog identity for models that do not yet have a local
    /// transport/install profile. This never authorizes device writes.
    var catalogCanonicalModel: String? {
        GarminDeviceModelNormalizer.catalogCanonicalModel(from: identityModelSource)
    }
}

struct GarminDeviceModelNormalizer: Sendable {
    static func canonicalModel(from rawModel: String) -> String? {
        var model = rawModel.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"^garmin\s+"#, with: "", options: [.regularExpression, .caseInsensitive])
        guard !model.isEmpty, !normalize(model).hasPrefix("unknown") else { return nil }
        // This only removes explicitly reported variant tokens. All model
        // names and exact IDs come from the device or the API catalog.
        if let range = model.range(of: #"\b(?:\d{2,3}\s*mm|sapphire|solar|amoled|mip|microled|inreach|leather|titanium|stainless|silicone)\b"#,
                                   options: [.regularExpression, .caseInsensitive]) {
            model = String(model[..<range.lowerBound])
        }
        model = model.trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "-–·,")))
        return model.isEmpty ? nil : model
    }

    static func catalogCanonicalModel(from rawModel: String) -> String? {
        canonicalModel(from: rawModel).map(normalize)
    }

    static func displayCanonicalModel(_ normalizedModel: String) -> String {
        normalizedModel.trimmingCharacters(in: .whitespacesAndNewlines)
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

    static func hasExplicitFeature(_ feature: String, in value: String) -> Bool {
        normalize(value).split(separator: " ").contains(Substring(feature))
    }

    static func screenTechnology(from value: String) -> String? {
        let matches = [("amoled", "AMOLED"), ("microled", "MicroLED"), ("mip", "MIP")]
            .filter { hasExplicitFeature($0.0, in: value) }
        return matches.count == 1 ? matches[0].1 : nil
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
        if let display = identity.screenTechnology {
            parts.append(display)
        }
        if identity.solar == true && !parts.contains("Solar") { parts.append("Solar") }
        if identity.inReach == true { parts.append("inReach") }
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

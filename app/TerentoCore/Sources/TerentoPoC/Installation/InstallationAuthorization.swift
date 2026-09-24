import Foundation

/// The server-owned decision that a live device may enter a Terento write
/// operation. This is deliberately separate from public compatibility
/// evidence and from the physical MTP/install profile.
enum InstallationAuthorizationBlockReason: String, Codable, Equatable, Sendable {
    case pending = "PENDING"
    case outOfScope = "OUT_OF_SCOPE"
    case unknownModel = "UNKNOWN_MODEL"
    case notAuthorized = "NOT_AUTHORIZED"
    case catalogUnavailable = "CATALOG_UNAVAILABLE"
    case ambiguousCatalogMatch = "AMBIGUOUS_CATALOG_MATCH"

    var isRetryable: Bool {
        self == .catalogUnavailable
    }

    var userMessage: String {
        if self == .catalogUnavailable {
            return "Terento could not verify this device's installation authorization right now. Check your connection and try again."
        }
        if self == .pending || self == .unknownModel || self == .ambiguousCatalogMatch {
            return "Terento could not reliably determine whether this device is supported for map installation."
        }
        return "Map installation is not available for this device in Terento."
    }
}

struct InstallationAuthorizationRecord: Codable, Equatable, Sendable {
    let id: String
    let manufacturer: String
    let model: String
    let baseModel: String
    let canonicalModel: String
    let variant: String
    let caseSizeMm: Int?
    let displayType: String?
    let screenTechnology: String?
    let solar: Bool?
    let inReach: Bool?
    let active: Bool
    var mapCapable: Bool? = nil
    let scope: String
    let installationAuthorization: String
}

struct InstallationAuthorizationDocument: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let policyVersion: Int
    let updatedAt: String
    let manufacturer: String
    let devices: [InstallationAuthorizationRecord]
}

enum InstallationAuthorizationState: Equatable, Sendable {
    case resolving
    case approved(record: InstallationAuthorizationRecord, policyVersion: Int)
    case blocked(InstallationAuthorizationBlockReason)

    var canInstall: Bool {
        if case .approved = self { return true }
        return false
    }

    var blockReason: InstallationAuthorizationBlockReason? {
        if case let .blocked(reason) = self { return reason }
        return nil
    }

    var userMessage: String? {
        blockReason?.userMessage
    }

    func matches(identity: DeviceIdentity) -> Bool {
        guard case let .approved(record, _) = self else { return false }
        guard observedIdentityIsConsistent(identity),
              GarminDeviceModelNormalizer.normalize(record.manufacturer)
                == GarminDeviceModelNormalizer.normalize(identity.manufacturer),
              let identityCanonicalModel = authorizationBaseModel(identity),
              GarminDeviceModelNormalizer.normalize(record.baseModel)
                == GarminDeviceModelNormalizer.normalize(identityCanonicalModel),
              variantFieldsAreCompatible(identity: identity, record: record) else {
            return false
        }
        return true
    }
}

struct InstallationAuthorizationClient: Sendable {
    static let defaultEndpoint = URL(string: "https://api.terento.app/devices/installation-policy.json")!

    private let endpoint: URL
    private let dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)

    init(
        endpoint: URL = InstallationAuthorizationClient.defaultEndpoint,
        dataLoader: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.endpoint = endpoint
        self.dataLoader = dataLoader
    }

    func resolve(identity: DeviceIdentity) async -> InstallationAuthorizationState {
        do {
            var request = URLRequest(url: endpoint)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 15
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue("no-store", forHTTPHeaderField: "Cache-Control")

            let (data, response) = try await dataLoader(request)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200,
                  httpResponse.value(forHTTPHeaderField: "Content-Type")?
                    .lowercased().split(separator: ";", maxSplits: 1).first?
                    .trimmingCharacters(in: .whitespaces) == "application/json",
                  data.count <= 4 * 1024 * 1024 else {
                return .blocked(.catalogUnavailable)
            }

            let document = try JSONDecoder().decode(InstallationAuthorizationDocument.self, from: data)
            guard document.schemaVersion == 3,
                  document.policyVersion >= 3,
                  policyDocumentIsValid(document, rawData: data) else {
                return .blocked(.catalogUnavailable)
            }

            switch match(identity: identity, records: document.devices) {
            case .approved(let record):
                guard record.active,
                      record.mapCapable == true else {
                    return .blocked(.pending)
                }
                return .approved(record: record, policyVersion: document.policyVersion)
            case .blocked(let reason):
                return .blocked(reason)
            case .pending:
                return .blocked(.pending)
            }
        } catch {
            return .blocked(.catalogUnavailable)
        }
    }

    private enum MatchResult {
        case approved(InstallationAuthorizationRecord)
        case blocked(InstallationAuthorizationBlockReason)
        case pending
    }

    private func policyDocumentIsValid(
        _ document: InstallationAuthorizationDocument,
        rawData: Data
    ) -> Bool {
        let documentKeys: Set<String> = [
            "schemaVersion", "policyVersion", "updatedAt", "manufacturer", "devices"
        ]
        let recordKeys: Set<String> = [
            "id", "manufacturer", "model", "baseModel", "canonicalModel",
            "variant", "caseSizeMm", "displayType", "screenTechnology", "solar",
            "inReach", "active", "mapCapable", "scope", "installationAuthorization"
        ]
        guard document.manufacturer == "Garmin",
              let rawDocument = try? JSONSerialization.jsonObject(with: rawData) as? [String: Any],
              Set(rawDocument.keys) == documentKeys,
              let rawRecords = rawDocument["devices"] as? [[String: Any]],
              rawRecords.count == document.devices.count else {
            return false
        }

        var seenIDs = Set<String>()
        for (record, rawRecord) in zip(document.devices, rawRecords) {
            guard Set(rawRecord.keys) == recordKeys,
                  record.manufacturer == "Garmin",
                  !record.id.isEmpty,
                  !record.model.isEmpty,
                  !record.baseModel.isEmpty,
                  seenIDs.insert(record.id).inserted else {
                return false
            }
        }
        return true
    }

    private func match(
        identity: DeviceIdentity,
        records: [InstallationAuthorizationRecord]
    ) -> MatchResult {
        let manufacturer = GarminDeviceModelNormalizer.normalize(identity.manufacturer)
        guard manufacturer == "garmin" else { return .pending }

        // A disagreement about the base model is unsafe. Variant disagreements
        // are handled below as unknown facts, so they broaden the candidate set.
        guard observedIdentityIsConsistent(identity) else { return .pending }

        guard let canonicalModel = authorizationBaseModel(identity)
                .map(GarminDeviceModelNormalizer.normalize),
              !canonicalModel.isEmpty else {
            return .pending
        }

        let modelRecords = records.filter { record in
            GarminDeviceModelNormalizer.normalize(record.manufacturer) == manufacturer
                && GarminDeviceModelNormalizer.normalize(record.baseModel) == canonicalModel
        }
        // A catalogDeviceID is a prior catalog hint, never a write authority.
        // Only current device facts may narrow the current policy's base-model rows.
        let candidates = modelRecords.filter { record in
            record.active && variantFieldsAreCompatible(identity: identity, record: record)
        }
        guard !candidates.isEmpty else {
            if modelRecords.contains(where: { !$0.active }) {
                return .blocked(.outOfScope)
            }
            return .pending
        }
        return capabilityDecision(for: candidates)
    }

    private func capabilityDecision(
        for candidates: [InstallationAuthorizationRecord]
    ) -> MatchResult {
        if candidates.allSatisfy({ $0.mapCapable == true }) {
            return .approved(candidates[0])
        }
        if candidates.allSatisfy({ $0.mapCapable == false }) {
            return .blocked(.outOfScope)
        }
        return .pending
    }
}

/// Prevents first-party and custom map acquisition unless a fresh server
/// policy approves the same identity that will be used for installation.
struct InstallationAuthorizationAcquisitionError: Error, Sendable {
    let authorization: InstallationAuthorizationState
}

@MainActor
enum InstallationAuthorizationAcquisitionGate {
    static func run(
        identity: DeviceIdentity,
        client: InstallationAuthorizationClient,
        onAuthorized: (InstallationAuthorizationState) -> Void,
        acquisition: () async throws -> Void
    ) async throws {
        let authorization = await client.resolve(identity: identity)
        try Task.checkCancellation()
        guard authorization.canInstall,
              authorization.matches(identity: identity) else {
            throw InstallationAuthorizationAcquisitionError(authorization: authorization)
        }

        onAuthorized(authorization)
        try await acquisition()
    }
}

private func observedIdentityIsConsistent(_ identity: DeviceIdentity) -> Bool {
    let modelSources = [identity.model, identity.deviceDescription,
                        identity.garminModelDescription]
        .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
    let baseModels = Set(modelSources.compactMap(authorizationBaseModel(from:)))
    return baseModels.count <= 1
}

private func authorizationBaseModel(_ identity: DeviceIdentity) -> String? {
    let preferred = [identity.deviceDescription, identity.model]
        .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
        .first { !$0.isEmpty }
    guard let preferred else { return nil }
    return authorizationBaseModel(from: preferred)
}

private func authorizationBaseModel(from source: String) -> String? {
    // Remove explicit negative variant labels before the canonical model parser
    // strips their attribute token (e.g. "no inReach" must not leave "no" as
    // part of the base model).
    let withoutNegativeVariantLabels = source.replacingOccurrences(
        of: #"\b(?:no|not|without|non)\s*-?\s*(?:solar|inreach|amoled|microled|mip)\b"#,
        with: " ",
        options: [.regularExpression, .caseInsensitive]
    )
    return GarminDeviceModelNormalizer.catalogCanonicalModel(from: withoutNegativeVariantLabels)
}

/// A variant attribute is usable only when the current MTP/XML/model text has
/// one unambiguous value for it. Conflicting or internally contradictory facts
/// are treated as unknown for that attribute; they must not reject a base-model
/// candidate or turn an otherwise uniform Maps capability into PENDING.
private struct ObservedVariantFacts {
    let caseSizeMm: Int?
    let screenTechnology: String?
    let solar: Bool?
    let inReach: Bool?

    init(identity: DeviceIdentity) {
        let sources = [identity.model, identity.deviceDescription,
                       identity.garminModelDescription, identity.variant]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        let caseSizes = sources.reduce(into: Set<Int>()) { $0.formUnion(explicitCaseSizes(in: $1)) }
        caseSizeMm = caseSizes.count == 1 ? caseSizes.first : nil

        let displays = sources.reduce(into: Set<String>()) {
            $0.formUnion(explicitScreenTechnologies(in: $1))
        }
        screenTechnology = displays.count == 1 ? displays.first : nil

        let solarValues = sources.reduce(into: Set<Bool>()) {
            $0.formUnion(explicitBooleanFeatureValues("solar", in: $1))
        }
        solar = solarValues.count == 1 ? solarValues.first : nil

        let inReachValues = sources.reduce(into: Set<Bool>()) {
            $0.formUnion(explicitBooleanFeatureValues("inreach", in: $1))
        }
        inReach = inReachValues.count == 1 ? inReachValues.first : nil
    }

}

private func explicitCaseSizes(in source: String) -> Set<Int> {
    let normalized = GarminDeviceModelNormalizer.normalize(source)
    guard let pattern = try? NSRegularExpression(pattern: #"\b[0-9]{2,3}\s*mm\b"#) else {
        return []
    }
    let range = NSRange(normalized.startIndex..<normalized.endIndex, in: normalized)
    return Set(pattern.matches(in: normalized, range: range).compactMap { match in
        guard let tokenRange = Range(match.range, in: normalized) else { return nil }
        return GarminDeviceModelNormalizer.caseSizeMm(from: String(normalized[tokenRange]))
    })
}

private func explicitScreenTechnologies(in source: String) -> Set<String> {
    let normalized = GarminDeviceModelNormalizer.normalize(source)
    let tokens = Set(normalized.split(separator: " ").map(String.init))
    return Set([("amoled", "AMOLED"), ("microled", "MicroLED"), ("mip", "MIP")]
        .compactMap { tokens.contains($0.0) ? $0.1 : nil })
}

private func canonicalScreenTechnology(_ value: String) -> String {
    switch GarminDeviceModelNormalizer.normalize(value) {
    case "amoled": return "AMOLED"
    case "microled": return "MicroLED"
    case "mip": return "MIP"
    default: return GarminDeviceModelNormalizer.normalize(value)
    }
}

private func explicitBooleanFeatureValues(_ feature: String, in source: String) -> Set<Bool> {
    let normalized = GarminDeviceModelNormalizer.normalize(source)
    let negativePattern = #"\b(?:no|not|without|non)\s*-?\s*"#
        + NSRegularExpression.escapedPattern(for: feature) + #"\b"#
    guard let pattern = try? NSRegularExpression(pattern: negativePattern) else { return [] }
    let range = NSRange(normalized.startIndex..<normalized.endIndex, in: normalized)
    let negatives = pattern.matches(in: normalized, range: range)
    var values = negatives.isEmpty ? Set<Bool>() : Set([false])
    var remaining = normalized
    for match in negatives.reversed() {
        guard let tokenRange = Range(match.range, in: remaining) else { continue }
        remaining.replaceSubrange(tokenRange, with: " ")
    }
    if GarminDeviceModelNormalizer.hasExplicitFeature(feature, in: remaining) {
        values.insert(true)
    }
    return values
}

/// Catalog metadata (including the remembered candidate ID) is not independent
/// device evidence. It cannot narrow candidates or resolve conflicting MTP/XML
/// facts. Unknown/conflicted facts therefore leave every plausible variant in play.
private func variantFieldsAreCompatible(
    identity: DeviceIdentity,
    record: InstallationAuthorizationRecord
) -> Bool {
    let observed = ObservedVariantFacts(identity: identity)
    let recordText = [record.model, record.canonicalModel, record.variant]
        .joined(separator: " ")
    var recordSizes = explicitCaseSizes(in: recordText)
    if let caseSize = record.caseSizeMm { recordSizes.insert(caseSize) }
    let recordSize = recordSizes.count == 1 ? recordSizes.first : nil
    if let identitySize = observed.caseSizeMm,
       let recordSize,
       identitySize != recordSize {
        return false
    }

    var recordDisplays = explicitScreenTechnologies(in: recordText)
    for display in [record.screenTechnology, record.displayType].compactMap({ $0 }) {
        recordDisplays.insert(canonicalScreenTechnology(display))
    }
    let recordDisplay = recordDisplays.count == 1 ? recordDisplays.first : nil
    if let identityDisplay = observed.screenTechnology,
       let recordDisplay,
       GarminDeviceModelNormalizer.normalize(recordDisplay)
            != GarminDeviceModelNormalizer.normalize(identityDisplay) {
        return false
    }

    var recordSolarValues = explicitBooleanFeatureValues("solar", in: recordText)
    if let solar = record.solar { recordSolarValues.insert(solar) }
    let recordSolar = recordSolarValues.count == 1 ? recordSolarValues.first : nil
    if let observedSolar = observed.solar,
       let recordSolar,
       observedSolar != recordSolar {
        return false
    }

    var recordInReachValues = explicitBooleanFeatureValues("inreach", in: recordText)
    if let inReach = record.inReach { recordInReachValues.insert(inReach) }
    let recordInReach = recordInReachValues.count == 1 ? recordInReachValues.first : nil
    if let observedInReach = observed.inReach,
       let recordInReach,
       observedInReach != recordInReach {
        return false
    }
    return true
}

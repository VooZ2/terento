import Foundation

/// Stable content identity for a map. It is deliberately independent of the
/// device filename, because Garmin tools may rename the same IMG file.
struct MapIdentity: Codable, Equatable, Hashable, Sendable {
    let provider: String
    let region: String

    init?(provider: String?, region: String?) {
        guard let provider, let region else {
            return nil
        }

        let normalizedProvider = Self.normalizeProvider(provider)
        let normalizedRegion = Self.normalizeRegion(region)
        guard !normalizedProvider.isEmpty, !normalizedRegion.isEmpty else {
            return nil
        }

        self.provider = normalizedProvider
        self.region = normalizedRegion
    }

    static func normalizeProvider(_ value: String) -> String {
        value
            .folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
            .replacingOccurrences(of: "[^a-z0-9]+", with: "", options: .regularExpression)
            .lowercased()
    }

    static func normalizeRegion(_ value: String) -> String {
        value
            .uppercased()
            .replacingOccurrences(of: "+", with: "")
            .replacingOccurrences(of: "[^A-Z0-9]+", with: "", options: .regularExpression)
    }
}

/// Compares a parsed provider identity with a catalog identity while keeping
/// provider-specific compatibility aliases at the identity boundary. The
/// first beta OTM catalog used `LTU` for Lithuania; the live provider catalog
/// now uses its official `lithuania` slug (`LITHUANIA`). Both values describe
/// the same OTM package and must remain interchangeable for validation and
/// lifecycle matching.
struct MapIdentityMatcher: Sendable {
    static func matches(
        actual: MapIdentity?,
        expected: MapIdentity?,
        providerRegionId: String? = nil,
        identifier: String? = nil
    ) -> Bool {
        guard let actual, let expected,
              actual.provider == expected.provider else {
            return false
        }

        let actualRegion = MapIdentity.normalizeRegion(actual.region)
        let acceptedRegions = [expected.region, providerRegionId, identifier]
            .compactMap { $0 }
            .map(MapIdentity.normalizeRegion)

        if acceptedRegions.contains(actualRegion) {
            return true
        }

        guard actual.provider == "opentopomap" else {
            return false
        }

        return Set([actualRegion, expected.region]) == Set(["LTU", "LITHUANIA"])
    }
}

struct MapIdentityNormalizer: Sendable {
    func identity(provider: String?, region: String?) -> MapIdentity? {
        MapIdentity(provider: provider, region: region)
    }

    func namesMatch(
        installedName: String,
        installedFamily: String?,
        providerName: String,
        region: MapRegion
    ) -> Bool {
        let installed = normalizedText(
            [installedName, installedFamily].compactMap { $0 }.joined(separator: " ")
        )
        let providerMatches = installed.contains(normalizedText(providerName))
        let regionMatches = [region.id, region.name, region.country]
            .compactMap { $0 }
            .map(normalizedText)
            .contains { installed.contains($0) }

        return providerMatches && regionMatches
    }

    private func normalizedText(_ value: String) -> String {
        value
            .folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

enum MapManagementState: String, Codable, Equatable, Sendable {
    case managedByTerento = "MANAGED_BY_TERENTO"
    case detectedNotManaged = "DETECTED_NOT_MANAGED"
    case unknown = "UNKNOWN"

    var userLabel: String {
        switch self {
        case .managedByTerento:
            return "Managed by Terento"
        case .detectedNotManaged:
            return "Detected, not managed by Terento"
        case .unknown:
            return "Unknown"
        }
    }
}

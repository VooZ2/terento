import Foundation

/// Presentation-only names. Catalog and device metadata retain their original
/// provider wording; this keeps formal country names out of the normal UI
/// without changing identity or matching behaviour.
enum MapDisplayNameNormalizer: Sendable {
    private static let formalPrefixes = [
        "Federal Republic of ",
        "Grand Duchy of ",
        "Principality of ",
        "Kingdom of ",
        "Republic of ",
        "Italian Republic",
        "Portuguese Republic",
        "Slovak Republic",
        "Swiss Confederation",
        "French Republic",
        "Hellenic Republic"
    ]

    private static let formalNames: [String: String] = [
        "Italian Republic": "Italy",
        "Portuguese Republic": "Portugal",
        "Slovak Republic": "Slovakia",
        "Swiss Confederation": "Switzerland",
        "French Republic": "France",
        "Hellenic Republic": "Greece"
    ]

    private static let suffixNames: [String: String] = [
        "NORTH": "North",
        "SOUTH": "South",
        "NORTHEAST": "Northeast",
        "NORTHWEST": "Northwest",
        "SOUTHEAST": "Southeast",
        "SOUTHWEST": "Southwest",
        "CENTRAL": "Central",
        "VOLGA": "Volga",
        "KGD": "Kaliningrad"
    ]

    static func normalize(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if let formalName = formalNames[trimmed] {
            return formalName
        }

        for prefix in formalPrefixes {
            if trimmed.hasPrefix(prefix) {
                return String(trimmed.dropFirst(prefix.count))
            }
        }

        return trimmed
    }

    /// Returns one display title per catalog package. Duplicate formal names
    /// are made distinct only with identifiers already supplied by the
    /// catalog; no geographic coverage is inferred.
    static func displayNames(for packages: [MapPackage]) -> [String: String] {
        let baseNames = Dictionary(uniqueKeysWithValues: packages.map {
            ($0.id, normalize($0.name))
        })
        let duplicateBases = Set(
            Dictionary(grouping: packages, by: { baseNames[$0.id] ?? $0.name })
                .filter { $0.value.count > 1 }
                .keys
        )

        return Dictionary(uniqueKeysWithValues: packages.map { package in
            let base = baseNames[package.id] ?? package.name
            guard duplicateBases.contains(base) else {
                return (package.id, base)
            }

            let suffix = identifierSuffix(for: package)
            return (package.id, suffix.isEmpty ? "\(base) · \(package.regionId)" : "\(base) · \(suffix)")
        })
    }

    static func searchableText(package: MapPackage, displayName: String) -> String {
        [displayName, package.name, package.regionId, package.identifier, package.id]
            .compactMap { $0 }
            .joined(separator: " ")
            .folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
    }

    private static func identifierSuffix(for package: MapPackage) -> String {
        guard let identifier = package.identifier?.trimmingCharacters(in: .whitespacesAndNewlines),
              !identifier.isEmpty else {
            return ""
        }

        var suffix = identifier.uppercased()
        let region = package.regionId.uppercased()
        if suffix.hasPrefix(region) {
            suffix = String(suffix.dropFirst(region.count))
        }

        suffix = suffix
            .replacingOccurrences(of: "+", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .replacingOccurrences(of: "_", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        guard !suffix.isEmpty else {
            return region
        }

        return suffix
            .split(separator: " ")
            .map { suffixNames[String($0)] ?? String($0).capitalized }
            .joined(separator: " ")
    }
}

enum MapCatalogIdentityKey: Sendable {
    static func make(
        provider: String?,
        region: String?,
        identifier: String?,
        fallback: String,
        namespace: String
    ) -> String {
        let normalizedProvider = MapIdentity.normalizeProvider(provider ?? "")
        let normalizedRegion = MapIdentity.normalizeRegion(region ?? "")
        guard !normalizedProvider.isEmpty, !normalizedRegion.isEmpty else {
            return "\(namespace):catalog:\(fallback)"
        }

        let normalizedIdentifier = identifier.map {
            $0.folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
            .replacingOccurrences(of: "[^a-z0-9]+", with: "", options: .regularExpression)
            .lowercased()
        }

        if let normalizedIdentifier, !normalizedIdentifier.isEmpty {
            return "\(namespace):identity:\(normalizedProvider):\(normalizedRegion):\(normalizedIdentifier)"
        }

        return "\(namespace):identity:\(normalizedProvider):\(normalizedRegion)"
    }
}

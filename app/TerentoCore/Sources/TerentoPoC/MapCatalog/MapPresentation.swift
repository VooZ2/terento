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

    static func normalize(_ value: String, providerID: String? = nil) -> String {
        var trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if let providerID {
            trimmed = stripProviderDecoration(trimmed, providerID: providerID)
        }

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

    /// Returns one display title per catalog package. Duplicate names are
    /// scoped to one provider because the provider is already rendered in
    /// the row detail. Only variants within the same provider get a region
    /// qualifier; cross-provider names remain the same country title.
    static func displayNames(for packages: [MapPackage]) -> [String: String] {
        let baseNames = Dictionary(uniqueKeysWithValues: packages.map {
            ($0.id, baseDisplayName(for: $0))
        })
        let duplicateProviderNames = Set(
            Dictionary(grouping: packages, by: { package in
                duplicateKey(
                    for: package,
                    base: baseNames[package.id] ?? package.name
                )
            })
                .filter { $0.value.count > 1 }
                .keys
        )

        return Dictionary(uniqueKeysWithValues: packages.map { package in
            let base = baseNames[package.id] ?? package.name
            guard duplicateProviderNames.contains(duplicateKey(for: package, base: base)) else {
                return (package.id, base)
            }

            let suffix = identifierSuffix(for: package)
            return (package.id, suffix.isEmpty ? "\(base) (\(package.regionId))" : "\(base) (\(suffix))")
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
        let regionPrefix = region
            .split(whereSeparator: { $0 == "+" || $0 == "-" || $0 == "_" })
            .first
            .map(String.init) ?? region
        if suffix.hasPrefix(regionPrefix) {
            suffix = String(suffix.dropFirst(regionPrefix.count))
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

    /// Older remote catalogs used provider-decorated names such as
    /// `Lithuania · Otm Lithuania` or `OpenTopoMap Lithuania`. Keep that
    /// metadata for diagnostics, but never let it become the country title.
    private static func baseDisplayName(for package: MapPackage) -> String {
        let rawName = package.name.trimmingCharacters(in: .whitespacesAndNewlines)
        let fragments = rawName
            .split(separator: "·", omittingEmptySubsequences: true)
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }

        let candidate: String
        if fragments.count > 1 {
            let leading = fragments[0]
            let suffix = fragments.dropFirst().joined(separator: " · ")
            if isProviderDecoration(suffix, providerID: package.providerId)
                || isRegionDecoration(suffix, package: package) {
                candidate = leading
            } else {
                candidate = rawName
            }
        } else {
            candidate = rawName
        }

        return normalize(candidate, providerID: package.providerId)
    }

    private static func stripProviderDecoration(
        _ value: String,
        providerID: String
    ) -> String {
        let fragments = value
            .split(separator: "·", omittingEmptySubsequences: true)
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        if fragments.count > 1 {
            let suffix = fragments.dropFirst().joined(separator: " · ")
            if isProviderDecoration(suffix, providerID: providerID) {
                return fragments[0]
            }
        }

        let lowercased = value.lowercased()
        for prefix in providerPrefixes(for: providerID) {
            if lowercased.hasPrefix(prefix) {
                let stripped = String(value.dropFirst(prefix.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !stripped.isEmpty {
                    return stripped
                }
            }
        }
        return value
    }

    private static func isProviderDecoration(
        _ value: String,
        providerID: String
    ) -> Bool {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowercased = normalized.lowercased()
        return providerPrefixes(for: providerID).contains {
            lowercased.hasPrefix($0)
        }
    }

    private static func isRegionDecoration(
        _ value: String,
        package: MapPackage
    ) -> Bool {
        let normalizedValue = normalizeToken(value)
        guard !normalizedValue.isEmpty else { return false }

        return [package.regionId, package.providerRegionId, package.identifier]
            .compactMap { $0 }
            .contains { normalizeToken($0) == normalizedValue }
    }

    private static func providerPrefixes(for providerID: String) -> [String] {
        switch MapIdentity.normalizeProvider(providerID) {
        case "freizeitkarte":
            return ["freizeitkarte ", "fzk "]
        case "opentopomap":
            return ["opentopomap ", "otm "]
        default:
            return []
        }
    }

    private static func normalizeToken(_ value: String) -> String {
        value
            .lowercased()
            .filter { $0.isLetter || $0.isNumber }
    }

    private static func duplicateKey(for package: MapPackage, base: String) -> String {
        "\(MapIdentity.normalizeProvider(package.providerId)):\(base.lowercased())"
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
        // Use the concrete provider package token as the region key. This
        // joins scanned metadata such as `Freizeitkarte_DEU+NORTH` with the
        // catalog's `DEU-NORTH`/`DEU+NORTH` pair and keeps packages that share
        // a broad catalog region (AZORES, Balearics, Madeira) distinct.
        let concreteRegion: String
        if let trimmedIdentifier = identifier?.trimmingCharacters(in: .whitespacesAndNewlines),
           !trimmedIdentifier.isEmpty {
            concreteRegion = trimmedIdentifier
        } else {
            concreteRegion = region ?? ""
        }
        let normalizedRegion = MapIdentity.normalizeRegion(concreteRegion)
        guard !normalizedProvider.isEmpty, !normalizedRegion.isEmpty else {
            return "\(namespace):catalog:\(fallback)"
        }
        return "\(namespace):identity:\(normalizedProvider):\(normalizedRegion)"
    }
}

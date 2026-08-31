import Foundation

/// A presentation-ready map entry built from the catalog comparison and the
/// device scan. It is intentionally read-only: grouping entries here must not
/// be used as proof that Terento owns any device file.
struct MapInventoryEntry: Identifiable, Equatable, Sendable {
    let key: String
    let title: String
    let catalogPackage: MapPackage?
    let comparison: MapComparison?
    let installedMaps: [InstalledMap]
    let isSelectedCatalogMap: Bool

    var id: String { key }

    var isInstalled: Bool {
        !installedMaps.isEmpty
    }

    var installedSizeBytes: UInt64 {
        installedMaps.reduce(0) { $0 + $1.sizeBytes }
    }

    var installedFileCount: Int {
        installedMaps.count
    }

    var installedVersion: MapVersion? {
        installedMaps
            .compactMap(\.version)
            .max()
    }

    var installedRawVersion: String? {
        installedMaps
            .sorted { lhs, rhs in
                switch (lhs.version, rhs.version) {
                case let (left?, right?):
                    return left > right
                case (nil, .some):
                    return false
                case (.some, nil):
                    return true
                case (nil, nil):
                    return false
                }
            }
            .compactMap(\.rawVersion)
            .first
    }

    var managementState: MapManagementState {
        guard let firstState = installedMaps.first?.managementState else {
            return .unknown
        }

        if installedMaps.dropFirst().allSatisfy({ $0.managementState == firstState }) {
            return firstState
        }

        return installedMaps.contains(where: { $0.managementState == .unknown })
            ? .unknown
            : .detectedNotManaged
    }

    /// A catalog package is authoritative for source kind. For an installed
    /// custom map the catalog is intentionally absent, so the exact managed
    /// custom record is the only fallback that can identify it as custom.
    var sourceKind: MapSourceKind {
        if let catalogPackage {
            return catalogPackage.sourceKind
        }

        if installedMaps.contains(where: {
            $0.provider == nil && $0.managementState == .managedByTerento
        }) {
            return .custom
        }

        return .provider
    }

    var statusLabel: String {
        if isSelectedCatalogMap, let comparison {
            return comparison.status.userLabel
        }

        return isInstalled ? "Installed" : "Available"
    }
}

struct MapInventoryProviderGroup: Identifiable, Equatable, Sendable {
    let id: String
    let providerId: String
    let title: String
    let entries: [MapInventoryEntry]
}

struct UnifiedMapInventory: Equatable, Sendable {
    let providerGroups: [MapInventoryProviderGroup]
    let otherMaps: [MapInventoryEntry]

    init(
        providerGroups: [MapInventoryProviderGroup],
        otherMaps: [MapInventoryEntry]
    ) {
        self.providerGroups = providerGroups.sorted {
            let titleOrder = $0.title.localizedCaseInsensitiveCompare($1.title)
            if titleOrder != .orderedSame {
                return titleOrder == .orderedAscending
            }
            return $0.id < $1.id
        }
        self.otherMaps = otherMaps
    }

    /// Compatibility initializer for the existing Freizeitkarte lifecycle
    /// callers. New code should use `providerGroups` directly.
    init(
        freizeitkarte: [MapInventoryEntry],
        otherMaps: [MapInventoryEntry]
    ) {
        self.init(
            providerGroups: freizeitkarte.isEmpty
                ? []
                : [MapInventoryProviderGroup(
                    id: "freizeitkarte",
                    providerId: "freizeitkarte",
                    title: "Freizeitkarte",
                    entries: freizeitkarte
                )],
            otherMaps: otherMaps
        )
    }

    var freizeitkarte: [MapInventoryEntry] {
        providerGroups.first {
            MapIdentity.normalizeProvider($0.providerId) == "freizeitkarte"
        }?.entries ?? []
    }

    var allEntries: [MapInventoryEntry] {
        providerGroups.flatMap(\.entries) + otherMaps
    }
}

struct MapInventoryListBuilder: Sendable {
    func build(
        scan: MapScanResult,
        comparisons: [MapComparison],
        selectedCatalogPackageID: String? = nil
    ) -> UnifiedMapInventory {
        let providerMaps = scan.installedMaps + scan.otherMaps.filter { $0.provider != nil }
        let providerIDs = Set(
            comparisons
                .filter { $0.catalogMap.sourceKind == .provider }
                .map { MapIdentity.normalizeProvider($0.catalogMap.providerId) }
        ).union(
            providerMaps.compactMap { map in
                guard let provider = map.provider else { return nil }
                let normalized = MapIdentity.normalizeProvider(provider)
                return normalized.isEmpty ? nil : normalized
            }
        )

        let providerGroups = providerIDs.compactMap { providerID in
            buildProviderGroup(
                providerID: providerID,
                installedMaps: providerMaps,
                comparisons: comparisons,
                selectedCatalogPackageID: selectedCatalogPackageID
            )
        }

        return UnifiedMapInventory(
            providerGroups: providerGroups,
            otherMaps: buildOtherMapEntries(
                scan.otherMaps.filter { $0.provider == nil }
            )
        )
    }

    private func buildProviderGroup(
        providerID: String,
        installedMaps: [InstalledMap],
        comparisons: [MapComparison],
        selectedCatalogPackageID: String?
    ) -> MapInventoryProviderGroup? {
        let installedGroups = groupedInstalledMaps(
            installedMaps.filter {
                MapIdentity.normalizeProvider($0.provider ?? "") == providerID
            },
            namespace: "provider-\(providerID)"
        )
        var comparisonsByKey: [String: MapComparison] = [:]
        let providerComparisons = comparisons.filter {
            $0.catalogMap.sourceKind == .provider
                && MapIdentity.normalizeProvider($0.catalogMap.providerId) == providerID
        }
        let displayNames = MapDisplayNameNormalizer.displayNames(
            for: providerComparisons.map(\.catalogMap)
        )

        for comparison in providerComparisons {
            let key = identityKey(
                provider: comparison.catalogMap.providerId,
                region: comparison.catalogMap.regionId,
                identifier: comparison.catalogMap.identifier,
                fallback: comparison.catalogMap.id,
                namespace: "provider-\(providerID)"
            )

            // Keep one deterministic row per exact catalog identity. A broad
            // region value may intentionally be shared by distinct packages;
            // MapCatalogIdentityKey includes the explicit package identifier.
            comparisonsByKey[key] = comparisonsByKey[key] ?? comparison
        }

        var keys = Set(installedGroups.keys)
        for (key, comparison) in comparisonsByKey {
            if comparison.catalogMap.id == selectedCatalogPackageID
                || comparison.installedMap != nil {
                keys.insert(key)
            }
        }

        let entries: [MapInventoryEntry] = keys.compactMap { (key: String) -> MapInventoryEntry? in
            let comparison = comparisonsByKey[key]
            let installedMaps = installedGroups[key] ?? []
            guard comparison != nil || !installedMaps.isEmpty else {
                return nil
            }

            let title: String
            if let comparison {
                let displayName = displayNames[comparison.catalogMap.id]
                    ?? MapDisplayNameNormalizer.normalize(comparison.catalogMap.name)
                title = displayName
            } else if let installedMap = installedMaps.first {
                title = providerNeutralTitle(
                    for: installedMap,
                    providerID: providerID
                )
            } else {
                return nil
            }

            return MapInventoryEntry(
                key: key,
                title: title,
                catalogPackage: comparison?.catalogMap,
                comparison: comparison,
                installedMaps: installedMaps,
                isSelectedCatalogMap: comparison?.catalogMap.id == selectedCatalogPackageID
            )
        }
        .sorted { lhs, rhs in
            if lhs.isSelectedCatalogMap != rhs.isSelectedCatalogMap {
                return lhs.isSelectedCatalogMap
            }

            return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
        }

        guard !entries.isEmpty else { return nil }

        let title = providerComparisons.first?.providerName
            ?? installedMaps.first(where: {
                MapIdentity.normalizeProvider($0.provider ?? "") == providerID
            })?.provider
            ?? providerID

        return MapInventoryProviderGroup(
            id: providerID,
            providerId: providerID,
            title: title,
            entries: entries
        )
    }

    private func providerNeutralTitle(
        for map: InstalledMap,
        providerID: String
    ) -> String {
        let title = MapDisplayNameNormalizer.normalize(
            map.name,
            providerID: providerID
        )
        return title.isEmpty ? map.sourceFile.filename : title
    }

    private func buildOtherMapEntries(_ maps: [InstalledMap]) -> [MapInventoryEntry] {
        groupedInstalledMaps(maps, namespace: "other")
            .compactMap { key, installedMaps in
                guard let first = installedMaps.first else {
                    return nil
                }

                let title: String
                if first.managementState == .managedByTerento,
                   first.provider == nil {
                    let parsedName = first.name.trimmingCharacters(in: .whitespacesAndNewlines)
                    let isGenericName = parsedName.isEmpty
                        || ["custom map", "unknown map"].contains(parsedName.lowercased())
                    title = isGenericName
                        ? first.sourceFile.filename
                        : parsedName
                } else {
                    title = first.name.isEmpty ? first.sourceFile.filename : first.name
                }

                return MapInventoryEntry(
                    key: key,
                    title: title,
                    catalogPackage: nil,
                    comparison: nil,
                    installedMaps: installedMaps,
                    isSelectedCatalogMap: false
                )
            }
            .sorted { lhs, rhs in
                lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }

    private func groupedInstalledMaps(
        _ maps: [InstalledMap],
        namespace: String
    ) -> [String: [InstalledMap]] {
        Dictionary(grouping: maps) { map in
            // A verified custom import must never be grouped with an
            // unowned third-party IMG merely because both files expose the
            // same human-readable header name. Keep each managed custom
            // file as its own lifecycle item so it receives Custom map /
            // Remove, while the unrelated external file remains read-only.
            if namespace == "other",
               map.provider == nil,
               map.managementState == .managedByTerento {
                return "\(namespace):custom:\(map.sourceFile.path)"
            }

            if let identity = map.identity {
                return identityKey(
                    provider: identity.provider,
                    region: identity.region,
                    identifier: map.identifier,
                    fallback: map.sourceFile.path,
                    namespace: namespace
                )
            }

            // This is only a display grouping for maps without a stable
            // identity. It prevents companion map files from creating
            // duplicate cards, while leaving the underlying maps unknown and
            // unmanaged for safety decisions.
            let displayName = normalizeDisplayText(
                map.name.isEmpty ? map.sourceFile.filename : map.name
            )
            // A provider can expose companion IMG files with different or
            // missing version strings. Keep one user-facing card per
            // normalized map name; the entry still retains every file for
            // read-only diagnostics and size reporting.
            return "\(namespace):display:\(displayName)"
        }
    }

    private func identityKey(
        provider: String,
        region: String,
        identifier: String?,
        fallback: String,
        namespace: String
    ) -> String {
        MapCatalogIdentityKey.make(
            provider: provider,
            region: region,
            identifier: identifier,
            fallback: fallback,
            namespace: namespace
        )
    }

    private func normalizeDisplayText(_ value: String) -> String {
        value
            .folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

}

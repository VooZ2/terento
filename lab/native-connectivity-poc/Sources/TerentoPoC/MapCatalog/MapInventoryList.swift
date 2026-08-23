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

    var statusLabel: String {
        if isSelectedCatalogMap, let comparison {
            return comparison.status.userLabel
        }

        return isInstalled ? "Installed" : "Available"
    }
}

struct UnifiedMapInventory: Equatable, Sendable {
    let freizeitkarte: [MapInventoryEntry]
    let otherMaps: [MapInventoryEntry]

    var allEntries: [MapInventoryEntry] {
        freizeitkarte + otherMaps
    }
}

struct MapInventoryListBuilder: Sendable {
    func build(
        scan: MapScanResult,
        comparisons: [MapComparison],
        selectedCatalogPackageID: String
    ) -> UnifiedMapInventory {
        let freizeitkarteEntries = buildFreizeitkarteEntries(
            scan: scan,
            comparisons: comparisons,
            selectedCatalogPackageID: selectedCatalogPackageID
        )

        return UnifiedMapInventory(
            freizeitkarte: freizeitkarteEntries,
            otherMaps: buildOtherMapEntries(scan.otherMaps)
        )
    }

    private func buildFreizeitkarteEntries(
        scan: MapScanResult,
        comparisons: [MapComparison],
        selectedCatalogPackageID: String
    ) -> [MapInventoryEntry] {
        let installedGroups = groupedInstalledMaps(
            scan.installedMaps,
            namespace: "freizeitkarte"
        )
        var comparisonsByKey: [String: MapComparison] = [:]
        let displayNames = MapDisplayNameNormalizer.displayNames(
            for: comparisons.map(\.catalogMap)
        )

        for comparison in comparisons {
            guard MapIdentity.normalizeProvider(comparison.catalogMap.providerId)
                == "freizeitkarte" else {
                continue
            }

            let key = identityKey(
                provider: comparison.catalogMap.providerId,
                region: comparison.catalogMap.regionId,
                identifier: comparison.catalogMap.identifier,
                fallback: comparison.catalogMap.id,
                namespace: "freizeitkarte"
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

        return keys.compactMap { key in
            let comparison = comparisonsByKey[key]
            let installedMaps = installedGroups[key] ?? []
            guard comparison != nil || !installedMaps.isEmpty else {
                return nil
            }

            let title: String
            if let comparison {
                let displayName = displayNames[comparison.catalogMap.id]
                    ?? MapDisplayNameNormalizer.normalize(comparison.catalogMap.name)
                title = "Freizeitkarte \(displayName)"
            } else if let installedMap = installedMaps.first {
                title = installedMap.name
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
    }

    private func buildOtherMapEntries(_ maps: [InstalledMap]) -> [MapInventoryEntry] {
        groupedInstalledMaps(maps, namespace: "other")
            .compactMap { key, installedMaps in
                guard let first = installedMaps.first else {
                    return nil
                }

                let title = otherDisplayName(for: first)

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
            // identity. It prevents companion files such as an OpenTopoMap
            // contours IMG from creating duplicate cards, while leaving the
            // underlying maps unknown and unmanaged for safety decisions.
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

    private func otherDisplayName(for map: InstalledMap) -> String {
        let text = normalizeDisplayText(
            map.name.isEmpty ? map.sourceFile.filename : map.name
        )

        if text.contains("opentopomap") && text.contains("lithuania") {
            return "OpenTopoMap Lithuania"
        }

        return map.name.isEmpty ? map.sourceFile.filename : map.name
    }
}

private extension MapVersion {
    static let minimum = MapVersion(year: 0, month: 1)!
}

import Foundation

/// Pure list rules keep UI partitioning and search deterministic and testable.
enum MapSelectionPresentationModel: Sendable {
    static func installed(_ items: [MapSelectionItem]) -> [MapSelectionItem] {
        items
            .filter { $0.comparison.installedMap != nil }
            .sorted { lhs, rhs in
                if lhs.comparison.status != rhs.comparison.status {
                    return lhs.comparison.status == .updateAvailable
                }
                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }

    static func available(
        _ items: [MapSelectionItem],
        query: String
    ) -> [MapSelectionItem] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return items
            .filter { $0.comparison.installedMap == nil && $0.action == .install }
            .filter { item in
                guard !normalizedQuery.isEmpty else { return true }
                return MapDisplayNameNormalizer.searchableText(
                    package: item.package,
                    displayName: item.title
                ).localizedCaseInsensitiveContains(normalizedQuery)
            }
            .sorted { lhs, rhs in
                if lhs.isRecommended != rhs.isRecommended {
                    return lhs.isRecommended
                }
                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }
}

import Foundation

struct MapInventoryProviderOption: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
}

/// Local read-only projection. Item identity, grouping and lifecycle authority
/// always come from the original inventory, never from search text.
struct MapInventoryListPresentationIndex: Sendable {
    private let inventory: MapLifecycleInventory
    private let searchByID: [String: String]
    private let providerByID: [String: String]
    let providerOptions: [MapInventoryProviderOption]

    init(inventory: MapLifecycleInventory) {
        self.inventory = inventory
        var search: [String: String] = [:]
        var providers: [String: String] = [:]
        var options: [String: String] = [:]
        for group in inventory.providerGroups where !group.items.isEmpty {
            let providerID = MapIdentity.normalizeProvider(group.providerId)
            guard !providerID.isEmpty else { continue }
            options[providerID] = group.title
            for item in group.items { providers[item.id] = providerID }
        }
        for item in inventory.otherMaps where item.sourceKind == .provider
            && item.classification == .externalRecognized {
            guard let name = item.provider, !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { continue }
            let providerID = MapIdentity.normalizeProvider(name)
            guard !providerID.isEmpty else { continue }
            providers[item.id] = providerID
            if options[providerID] == nil { options[providerID] = name }
        }
        for item in inventory.providerGroups.flatMap(\.items) + inventory.otherMaps {
            search[item.id] = Self.searchText(item)
        }
        searchByID = search
        providerByID = providers
        providerOptions = options.map { MapInventoryProviderOption(id: $0.key, title: $0.value) }
            .sorted {
                let order = $0.title.localizedCaseInsensitiveCompare($1.title)
                return order == .orderedSame ? $0.id < $1.id : order == .orderedAscending
            }
    }

    func filtered(query: String, providerID: String = "") -> MapLifecycleInventory {
        let terms = Self.fold(query).split(whereSeparator: \.isWhitespace).map(String.init)
        if terms.isEmpty && providerID.isEmpty { return inventory }
        let provider = MapIdentity.normalizeProvider(providerID)
        func matches(_ item: MapLifecycleItem) -> Bool {
            (providerID.isEmpty || providerByID[item.id] == provider)
                && terms.allSatisfy { searchByID[item.id, default: ""].contains($0) }
        }
        return MapLifecycleInventory(
            providerGroups: inventory.providerGroups.compactMap { group in
                let items = group.items.filter(matches)
                guard !items.isEmpty else { return nil }
                return MapLifecycleProviderGroup(id: group.id, providerId: group.providerId,
                    title: group.title, items: items)
            },
            otherMaps: inventory.otherMaps.filter(matches)
        )
    }

    private static func fold(_ value: String) -> String {
        value.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func searchText(_ item: MapLifecycleItem) -> String {
        // Imported maps keep their user-chosen display name. Never inspect
        // filenames, filesystem paths or opaque imported region identifiers.
        var title = item.title
        if title.lowercased().hasSuffix(".img") { title = String(title.dropLast(4)) }
        guard item.sourceKind == .provider else { return fold(title) }
        title = MapDisplayNameNormalizer.normalize(title, providerID: item.provider)
        if let provider = item.provider, !provider.isEmpty {
            title = title.replacingOccurrences(of: #"(?i)\b"# + NSRegularExpression.escapedPattern(for: provider) + #"\b"#,
                with: "", options: .regularExpression)
        }
        title = title.replacingOccurrences(of: #"(?i)\s*\([^)]*(?:contours?|IGN|latin1|UTF-?8|ASCII|style)[^)]*\)"#,
            with: "", options: .regularExpression)
        title = title.replacingOccurrences(of: #"(?i)\b(?:IGN|contours?|courbes|latin1|UTF-?8|ASCII|style)\b"#,
            with: "", options: .regularExpression)
        // Display metadata can contain a release suffix; it is not geography.
        for version in [item.rawVersion, item.version?.description].compactMap({ $0 }) where !version.isEmpty {
            title = title.replacingOccurrences(of: version, with: "", options: .caseInsensitive)
        }
        var terms = [title]
        // Only whole geographic country codes are accepted from region metadata.
        if let region = item.region, (region.count == 2 || region.count == 3),
           region.allSatisfy({ $0.isASCII && $0.isLetter }),
           let name = Locale(identifier: "en").localizedString(forRegionCode: region.uppercased()), name != region.uppercased() {
            terms += [region, name]
        }
        return fold(terms.joined(separator: " "))
    }
}

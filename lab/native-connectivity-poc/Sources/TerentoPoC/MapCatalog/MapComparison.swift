import Foundation

enum MapStatus: String, Sendable, Equatable {
    case notInstalled
    case updateAvailable
    case upToDate
    case newerInstalled
    case unknown

    var userLabel: String {
        switch self {
        case .notInstalled:
            return "Install available"
        case .updateAvailable:
            return "Update available"
        case .upToDate:
            return "Up to date"
        case .newerInstalled:
            return "Newer version installed"
        case .unknown:
            return "Unknown"
        }
    }
}

struct MapComparison: Identifiable, Sendable, Equatable {
    let providerName: String
    let regionName: String
    let catalogMap: MapPackage
    let installedMap: InstalledMap?
    let status: MapStatus

    var id: String {
        catalogMap.id
    }

    var userStatusLabel: String {
        status.userLabel
    }

    var managementState: MapManagementState {
        installedMap?.managementState ?? .unknown
    }
}

struct MapComparisonEngine: Sendable {
    private let identityNormalizer = MapIdentityNormalizer()

    func compare(
        installedMaps: [InstalledMap],
        provider: MapProvider,
        region: MapRegion,
        catalogMap: MapPackage
    ) -> MapComparison {
        let candidates = installedMaps.filter {
            matches($0, provider: provider, region: region, catalogMap: catalogMap)
        }

        guard let installedMap = candidates.max(by: { lhs, rhs in
            switch (lhs.version, rhs.version) {
            case let (left?, right?):
                return left < right
            case (nil, .some):
                return true
            case (.some, nil), (nil, nil):
                return false
            }
        }) else {
            return MapComparison(
                providerName: provider.name,
                regionName: region.name,
                catalogMap: catalogMap,
                installedMap: nil,
                status: .notInstalled
            )
        }

        guard let installedVersion = installedMap.version else {
            return MapComparison(
                providerName: provider.name,
                regionName: region.name,
                catalogMap: catalogMap,
                installedMap: installedMap,
                status: .unknown
            )
        }

        let status: MapStatus
        if installedVersion < catalogMap.version {
            status = .updateAvailable
        } else if installedVersion == catalogMap.version {
            status = .upToDate
        } else {
            status = .newerInstalled
        }

        return MapComparison(
            providerName: provider.name,
            regionName: region.name,
            catalogMap: catalogMap,
            installedMap: installedMap,
            status: status
        )
    }

    private func matches(
        _ installedMap: InstalledMap,
        provider: MapProvider,
        region: MapRegion,
        catalogMap: MapPackage
    ) -> Bool {
        guard installedMap.metadataStatus == .parsed else {
            return false
        }

        // 1–2. Provider and region identity are the primary match. Once both
        // identities are known, a mismatch is definitive. Do not let a
        // weaker identifier/name fallback turn one regional image into
        // another regional match.
        if let installedIdentity = installedMap.identity,
           let catalogIdentity = catalogMap.identity {
            guard installedIdentity == catalogIdentity else {
                return false
            }

            // A provider can publish several packages for one broad region
            // (for example DEU+NORTH and DEU+SOUTH). If both sides expose a
            // stable package identifier, require that identifier too.
            if let installedIdentifier = installedMap.identifier,
               let catalogIdentifier = catalogMap.identifier {
                return installedIdentifier == catalogIdentifier
            }

            return true
        }

        // 3. Known provider/map identifiers are a stronger fallback than a
        // display name, but only exact values are accepted.
        if let catalogIdentifier = catalogMap.identifier,
           let installedIdentifier = installedMap.identifier,
           catalogIdentifier == installedIdentifier {
            return true
        }

        // 4. Last-resort identity matching uses normalized metadata names.
        // A filename alone can never reach this branch.
        return identityNormalizer.namesMatch(
            installedName: installedMap.name,
            installedFamily: installedMap.family,
            providerName: provider.name,
            region: region
        )
    }
}

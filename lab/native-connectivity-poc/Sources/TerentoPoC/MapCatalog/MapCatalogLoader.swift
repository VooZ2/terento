import Foundation

enum MapCatalogSource: String, Sendable, Equatable {
    case remote
    case bundledFallback

    var userLabel: String {
        switch self {
        case .remote:
            return "Remote catalog"
        case .bundledFallback:
            return "Offline catalog — may be out of date"
        }
    }
}

struct MapCatalogLoadResult: Sendable {
    let catalog: MapCatalog
    let source: MapCatalogSource
}

struct MapCatalogLoader: Sendable {
    static let defaultEndpoint = URLComponents(
        string: "https://api.terento.app/maps/catalog.json"
    )?.url

    let endpoint: URL?

    init(endpoint: URL? = MapCatalogLoader.defaultEndpoint) {
        self.endpoint = endpoint
    }

    /// Metadata is fetched from the future catalog service first. The local
    /// catalog is the safe fallback and may be stale; it never contains map
    /// binaries.
    func loadRemoteThenFallback() async throws -> MapCatalogLoadResult {
        do {
            let data = try await loadRemoteData()
            return MapCatalogLoadResult(
                catalog: try decode(data),
                source: .remote
            )
        } catch {
            return MapCatalogLoadResult(
                catalog: try loadBundled(),
                source: .bundledFallback
            )
        }
    }

    /// Kept for synchronous PoC callers and local fixture checks.
    func loadFreizeitkarte() throws -> MapCatalog {
        try loadBundled()
    }

    func loadBundled() throws -> MapCatalog {
        #if SWIFT_PACKAGE
        guard let resourceURL = Bundle.module.url(
            forResource: "catalog",
            withExtension: "json"
        ) else {
            throw MapCatalogError.resourceMissing
        }

        do {
            return try decode(Data(contentsOf: resourceURL))
        } catch let error as MapCatalogError {
            throw error
        } catch {
            throw MapCatalogError.invalidMetadata(error.localizedDescription)
        }
        #else
        guard let resourceURL = Bundle.main.url(
            forResource: "catalog",
            withExtension: "json"
        ) else {
            throw MapCatalogError.resourceMissing
        }

        do {
            return try decode(Data(contentsOf: resourceURL))
        } catch let error as MapCatalogError {
            throw error
        } catch {
            throw MapCatalogError.invalidMetadata(error.localizedDescription)
        }
        #endif
    }

    private func loadRemoteData() async throws -> Data {
        guard let endpoint,
              let components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == "https",
              components.host != nil else {
            throw MapCatalogError.remoteUnavailable
        }

        var request = URLRequest(url: endpoint)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 15

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw MapCatalogError.remoteUnavailable
        }

        return data
    }

    private func decode(_ data: Data) throws -> MapCatalog {
        try MapCatalogDocumentDecoder().decode(data)
    }
}

struct MapCatalogDocumentDecoder: Sendable {
    func decode(_ data: Data) throws -> MapCatalog {
        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            let document = try decoder.decode(MapCatalogDocument.self, from: data)
            return try document.catalog()
        } catch let error as MapCatalogError {
            throw error
        } catch {
            throw MapCatalogError.invalidMetadata(error.localizedDescription)
        }
    }
}

enum MapCatalogError: LocalizedError, Sendable {
    case resourceMissing
    case remoteUnavailable
    case invalidMetadata(String)

    var errorDescription: String? {
        switch self {
        case .resourceMissing:
            return "The local map catalog is unavailable."
        case .remoteUnavailable:
            return "The remote map catalog is unavailable."
        case .invalidMetadata(let message):
            return "The map catalog is invalid: \(message)"
        }
    }
}

private struct MapCatalogDocument: Decodable {
    let catalogVersion: Int
    let updatedAt: Date
    let providers: [ProviderDocument]

    func catalog() throws -> MapCatalog {
        guard catalogVersion > 0 else {
            throw MapCatalogError.invalidMetadata("catalogVersion must be positive")
        }

        var providers: [MapProvider] = []
        var regionsByID: [String: MapRegion] = [:]
        var packages: [MapPackage] = []

        for providerDocument in self.providers {
            providers.append(
                MapProvider(
                    id: providerDocument.id,
                    name: providerDocument.name,
                    website: providerDocument.website,
                    attribution: providerDocument.attribution,
                    licenseURL: providerDocument.licenseURL
                )
            )

            for map in providerDocument.maps {
                let regionID = map.region
                regionsByID[regionID] = MapRegion(
                    id: regionID,
                    name: map.name,
                    country: map.country ?? map.name
                )

                packages.append(
                    MapPackage(
                        id: map.id,
                        providerId: providerDocument.id,
                        regionId: regionID,
                        name: map.name,
                        version: map.version,
                        sizeBytes: map.sizeBytes,
                        sourceURL: map.sourceURL,
                        releaseDate: map.releaseDate,
                        identifier: map.identifier,
                        downloadSizeBytes: map.downloadSizeBytes,
                        installSizeBytes: map.installSizeBytes
                    )
                )
            }
        }

        return MapCatalog(
            catalogVersion: catalogVersion,
            updatedAt: updatedAt,
            providers: providers,
            regions: Array(regionsByID.values),
            packages: packages
        )
    }

}

private struct ProviderDocument: Decodable {
    let id: String
    let name: String
    let website: URL?
    let attribution: String?
    let licenseURL: URL?
    let maps: [MapDocument]
}

private struct MapDocument: Decodable {
    let id: String
    let region: String
    let name: String
    let country: String?
    let version: MapVersion
    let sizeBytes: UInt64
    let downloadSizeBytes: UInt64?
    let installSizeBytes: UInt64?
    let sourceURL: URL?
    let releaseDate: String?
    let identifier: String?
}

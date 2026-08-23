import Foundation

struct MapProvider: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let name: String
    let website: URL?
    let attribution: String?
    let licenseURL: URL?
}

struct MapRegion: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let name: String
    let country: String?
}

struct MapPackage: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let providerId: String
    let regionId: String
    let name: String
    let version: MapVersion
    /// Backwards-compatible catalog size. Existing documents use this for the
    /// provider package (usually the download/archive) size.
    let sizeBytes: UInt64
    /// Explicit package size when the catalog contract provides it.
    let downloadSizeBytes: UInt64?
    /// Optional metadata-only hint. Acquisition always measures the IMG.
    let installSizeBytes: UInt64?
    let sourceURL: URL?
    let releaseDate: String?
    let identifier: String?

    init(
        id: String,
        providerId: String,
        regionId: String,
        name: String,
        version: MapVersion,
        sizeBytes: UInt64,
        sourceURL: URL?,
        releaseDate: String?,
        identifier: String?,
        downloadSizeBytes: UInt64? = nil,
        installSizeBytes: UInt64? = nil
    ) {
        self.id = id
        self.providerId = providerId
        self.regionId = regionId
        self.name = name
        self.version = version
        self.sizeBytes = sizeBytes
        self.downloadSizeBytes = downloadSizeBytes ?? sizeBytes
        self.installSizeBytes = installSizeBytes
        self.sourceURL = sourceURL
        self.releaseDate = releaseDate
        self.identifier = identifier
    }

    var downloadURL: URL? {
        sourceURL
    }

    var expectedDownloadSizeBytes: UInt64? {
        downloadSizeBytes ?? sizeBytes
    }

    var identity: MapIdentity? {
        MapIdentity(provider: providerId, region: regionId)
    }

    func withInstallSize(_ installSizeBytes: UInt64) -> MapPackage {
        MapPackage(
            id: id,
            providerId: providerId,
            regionId: regionId,
            name: name,
            version: version,
            sizeBytes: sizeBytes,
            sourceURL: sourceURL,
            releaseDate: releaseDate,
            identifier: identifier,
            downloadSizeBytes: downloadSizeBytes,
            installSizeBytes: installSizeBytes
        )
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case providerId
        case regionId
        case name
        case version
        case sizeBytes
        case downloadSizeBytes
        case installSizeBytes
        case sourceURL
        case releaseDate
        case identifier
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        providerId = try container.decode(String.self, forKey: .providerId)
        regionId = try container.decode(String.self, forKey: .regionId)
        name = try container.decode(String.self, forKey: .name)
        version = try container.decode(MapVersion.self, forKey: .version)

        let legacySize = try container.decodeIfPresent(UInt64.self, forKey: .sizeBytes)
        let explicitDownloadSize = try container.decodeIfPresent(
            UInt64.self,
            forKey: .downloadSizeBytes
        )
        guard let resolvedSize = legacySize ?? explicitDownloadSize else {
            throw DecodingError.dataCorruptedError(
                forKey: .sizeBytes,
                in: container,
                debugDescription: "Map package must provide sizeBytes or downloadSizeBytes."
            )
        }

        sizeBytes = resolvedSize
        downloadSizeBytes = explicitDownloadSize ?? legacySize
        installSizeBytes = try container.decodeIfPresent(
            UInt64.self,
            forKey: .installSizeBytes
        )
        sourceURL = try container.decodeIfPresent(URL.self, forKey: .sourceURL)
        releaseDate = try container.decodeIfPresent(String.self, forKey: .releaseDate)
        identifier = try container.decodeIfPresent(String.self, forKey: .identifier)
    }
}

struct MapCatalog: Equatable, Sendable {
    let catalogVersion: Int
    let updatedAt: Date
    let providers: [MapProvider]
    let regions: [MapRegion]
    let packages: [MapPackage]

    func provider(for id: String) -> MapProvider? {
        providers.first { $0.id == id }
    }

    func region(for id: String) -> MapRegion? {
        regions.first { $0.id == id }
    }

    func packages(forProviderId providerId: String) -> [MapPackage] {
        packages.filter { $0.providerId == providerId }
    }
}

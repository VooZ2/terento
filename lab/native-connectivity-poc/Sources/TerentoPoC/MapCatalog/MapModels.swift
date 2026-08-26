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

/// Provider-independent geographic identity used only for product policy and
/// presentation. Provider catalog values remain unchanged and continue to be
/// the source of package provenance and map matching.
struct CanonicalMapRegionIdentity: Equatable, Sendable {
    let countryCode: String
    let locality: String?

    init(countryCode: String, locality: String? = nil) {
        self.countryCode = countryCode
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
        let normalizedLocality = locality?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
        self.locality = normalizedLocality?.isEmpty == false ? normalizedLocality : nil
    }
}

enum MapAcquisitionAvailability: String, Equatable, Hashable, Sendable {
    case available
    case withheldRussia
    case withheldCrimea

    var shortStatus: String? {
        switch self {
        case .available:
            return nil
        case .withheldRussia, .withheldCrimea:
            return "Downloads are not offered for this region under Terento's current policy."
        }
    }

    var detailedExplanation: String? {
        switch self {
        case .available:
            return nil
        case .withheldRussia:
            return "Terento does not offer map downloads for russia while its war of aggression against Ukraine continues."
        case .withheldCrimea:
            return "Crimea is part of Ukraine and is temporarily occupied by russia."
        }
    }
}

enum MapAcquisitionPolicyError: Error, Equatable, Sendable {
    case withheldRussia
    case withheldCrimea

    var availability: MapAcquisitionAvailability {
        switch self {
        case .withheldRussia: return .withheldRussia
        case .withheldCrimea: return .withheldCrimea
        }
    }
}

/// This is the only layer that interprets Freizeitkarte-specific package
/// tokens. Explicit Crimea aliases are resolved before the generic RUS*
/// family so Crimea cannot fall through to the russia policy result.
struct FreizeitkarteMapRegionIdentityMapper: Sendable {
    func map(package: MapPackage) -> CanonicalMapRegionIdentity? {
        guard MapIdentity.normalizeProvider(package.providerId) == "freizeitkarte" else {
            return nil
        }

        let tokens = [package.identifier, package.regionId, package.id]
            .compactMap { value -> String? in
                guard let value else { return nil }
                let normalized = normalize(value)
                return normalized.isEmpty ? nil : normalized
            }

        if tokens.contains("RUS-CRIMEA") {
            return CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA")
        }

        if let russiaToken = tokens.first(where: { $0.hasPrefix("RUS") }) {
            let locality = String(russiaToken.dropFirst(3))
                .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
            return CanonicalMapRegionIdentity(
                countryCode: "RU",
                locality: locality.isEmpty ? nil : locality
            )
        }

        for token in tokens {
            let components = token.split(separator: "-", omittingEmptySubsequences: true)
            guard let country = components.first,
                  country.count == 3,
                  country.allSatisfy({ $0.isASCII && $0.isLetter }) else {
                continue
            }

            let locality = components.dropFirst().isEmpty
                ? nil
                : components.dropFirst().joined(separator: "-")
            return CanonicalMapRegionIdentity(
                countryCode: String(country),
                locality: locality
            )
        }

        return nil
    }

    private func normalize(_ value: String) -> String {
        var normalized = value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
            .replacingOccurrences(of: "_", with: "-")
            .replacingOccurrences(of: "+", with: "-")

        if normalized.hasPrefix("FREIZEITKARTE-") {
            normalized.removeFirst("FREIZEITKARTE-".count)
        }

        while normalized.contains("--") {
            normalized = normalized.replacingOccurrences(of: "--", with: "-")
        }
        return normalized.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    }
}

/// Product policy consumes only canonical identity and has no knowledge of
/// Freizeitkarte identifiers, catalog records, downloads, or device state.
struct MapAcquisitionPolicy: Sendable {
    func availability(
        for identity: CanonicalMapRegionIdentity?
    ) -> MapAcquisitionAvailability {
        guard let identity else { return .available }
        if identity.countryCode == "UA", identity.locality == "CRIMEA" {
            return .withheldCrimea
        }
        if identity.countryCode == "RU" {
            return .withheldRussia
        }
        return .available
    }

    func validate(_ identity: CanonicalMapRegionIdentity?) throws {
        switch availability(for: identity) {
        case .available:
            return
        case .withheldRussia:
            throw MapAcquisitionPolicyError.withheldRussia
        case .withheldCrimea:
            throw MapAcquisitionPolicyError.withheldCrimea
        }
    }
}

/// Composes provider mapping with the provider-independent policy. Unknown
/// non-russia identities remain available rather than being guessed.
struct MapPackageAcquisitionPolicyResolver: Sendable {
    private let mapper = FreizeitkarteMapRegionIdentityMapper()
    private let policy = MapAcquisitionPolicy()

    func canonicalIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        mapper.map(package: package)
    }

    func availability(for package: MapPackage) -> MapAcquisitionAvailability {
        policy.availability(for: canonicalIdentity(for: package))
    }

    func validate(package: MapPackage) throws {
        try policy.validate(canonicalIdentity(for: package))
    }
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

    /// The provider identifier is the concrete map identity. Most packages
    /// use the same token for `regionId` and `identifier`, but a few provider
    /// catalog entries intentionally share a broad region (for example
    /// AZORES) while `identifier` distinguishes the actual package.
    var canonicalRegionId: String {
        guard let identifier = identifier?.trimmingCharacters(in: .whitespacesAndNewlines),
              !identifier.isEmpty else {
            return regionId
        }

        return identifier
    }

    var identity: MapIdentity? {
        MapIdentity(provider: providerId, region: canonicalRegionId)
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

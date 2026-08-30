import Foundation

enum MapRegionKind: String, Codable, Equatable, Sendable {
    case country
    case multiCountry
    case subregion
    case custom

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        guard let kind = Self(rawValue: value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()) else {
            throw DecodingError.dataCorruptedError(
                in: try decoder.singleValueContainer(),
                debugDescription: "Unknown map region kind: \(value)"
            )
        }
        self = kind
    }
}

enum MapSourceKind: String, Codable, Equatable, Sendable {
    case provider
    case custom
}

enum MapArtifactKind: String, Codable, Equatable, Hashable, Sendable {
    case main
    case contours

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        guard let kind = Self(rawValue: value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()) else {
            throw DecodingError.dataCorruptedError(
                in: try decoder.singleValueContainer(),
                debugDescription: "Unknown map artifact kind: \(value)"
            )
        }
        self = kind
    }
}

enum MapArtifactValidationState: String, Codable, Equatable, Sendable {
    case notValidated
    case validating
    case validated
    case unavailable
    case failed
}

/// Provider-native release information is intentionally string-based. A
/// provider may publish a date, a build identifier, or a semantic release
/// label; none of those formats should be forced into Freizeitkarte's
/// year/month comparison model.
struct MapReleaseMetadata: Codable, Equatable, Sendable {
    let releaseId: String?
    let versionLabel: String?
    let generatedAt: String?
    let sourceUpdatedAt: String?
}

/// One downloadable or locally staged map payload. `required` allows a
/// package to expose an optional contours companion without making the main
/// map unavailable when that companion is missing.
struct MapArtifact: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let source: MapSourceKind
    let kind: MapArtifactKind
    let required: Bool
    let providerId: String?
    let providerRegionId: String?
    let canonicalRegionId: String?
    let version: MapVersion?
    let releaseMetadata: MapReleaseMetadata?
    let sourceURL: URL?
    let localURL: URL?
    let sizeBytes: UInt64?
    let checksum: String?
    let validationState: MapArtifactValidationState

    init(
        id: String,
        source: MapSourceKind = .provider,
        kind: MapArtifactKind,
        required: Bool,
        providerId: String? = nil,
        providerRegionId: String? = nil,
        canonicalRegionId: String? = nil,
        version: MapVersion? = nil,
        releaseMetadata: MapReleaseMetadata? = nil,
        sourceURL: URL? = nil,
        localURL: URL? = nil,
        sizeBytes: UInt64? = nil,
        checksum: String? = nil,
        validationState: MapArtifactValidationState = .notValidated
    ) {
        self.id = id
        self.source = source
        self.kind = kind
        self.required = required
        self.providerId = providerId
        self.providerRegionId = providerRegionId
        self.canonicalRegionId = canonicalRegionId
        self.version = version
        self.releaseMetadata = releaseMetadata
        self.sourceURL = sourceURL
        self.localURL = localURL
        self.sizeBytes = sizeBytes
        self.checksum = checksum
        self.validationState = validationState
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case source
        case kind
        case required
        case providerId
        case providerRegionId
        case canonicalRegionId
        case version
        case releaseMetadata
        case sourceURL
        case localURL
        case sizeBytes
        case checksum
        case validationState
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            id: try container.decode(String.self, forKey: .id),
            source: try container.decodeIfPresent(MapSourceKind.self, forKey: .source) ?? .provider,
            kind: try container.decodeIfPresent(MapArtifactKind.self, forKey: .kind) ?? .main,
            required: try container.decodeIfPresent(Bool.self, forKey: .required) ?? true,
            providerId: try container.decodeIfPresent(String.self, forKey: .providerId),
            providerRegionId: try container.decodeIfPresent(String.self, forKey: .providerRegionId),
            canonicalRegionId: try container.decodeIfPresent(String.self, forKey: .canonicalRegionId),
            version: try container.decodeIfPresent(MapVersion.self, forKey: .version),
            releaseMetadata: try container.decodeIfPresent(MapReleaseMetadata.self, forKey: .releaseMetadata),
            sourceURL: try container.decodeIfPresent(URL.self, forKey: .sourceURL),
            localURL: try container.decodeIfPresent(URL.self, forKey: .localURL),
            sizeBytes: try container.decodeIfPresent(UInt64.self, forKey: .sizeBytes),
            checksum: try container.decodeIfPresent(String.self, forKey: .checksum),
            validationState: try container.decodeIfPresent(MapArtifactValidationState.self, forKey: .validationState) ?? .notValidated
        )
    }
}

enum MapProviderHealth: String, Codable, Equatable, Sendable {
    case healthy
    case degraded
    case down
    case unknown
}

enum MapProviderLifecycleStatus: String, Codable, Equatable, Sendable {
    case active
    case paused
    case retired
}

struct MapProviderHealthStatus: Codable, Equatable, Sendable {
    let providerId: String
    let health: MapProviderHealth
    let lifecycleStatus: MapProviderLifecycleStatus
    let lastCheckedAt: Date?
    let lastSuccessfulCatalogSync: Date?
    let activePackageCount: Int
    let brokenPackageCount: Int
    let lastError: String?
}

enum MapSource: Equatable, Sendable {
    case provider(package: MapPackage)
    case custom(fileURL: URL, displayName: String)

    var kind: MapSourceKind {
        switch self {
        case .provider:
            return .provider
        case .custom:
            return .custom
        }
    }
}

/// A deliberately narrow adapter seam. Provider-specific URL and identity
/// rules stay behind this interface; acquisition, inventory, and lifecycle
/// code consume the neutral package/artifact model.
protocol MapProviderAdapter: Sendable {
    var id: String { get }
    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity?
    func artifacts(for package: MapPackage) -> [MapArtifact]
}

struct FreizeitkarteProviderAdapter: MapProviderAdapter, Sendable {
    let id = "freizeitkarte"

    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        FreizeitkarteMapRegionIdentityMapper().map(package: package)
    }

    func artifacts(for package: MapPackage) -> [MapArtifact] {
        package.artifacts
    }
}

/// The registry has no implicit/default provider. Callers supply the
/// adapters they have intentionally enabled, and presentation order is
/// deterministic and alphabetical by display name.
struct MapProviderRegistry: Sendable {
    let adapters: [any MapProviderAdapter]

    init(adapters: [any MapProviderAdapter]) {
        self.adapters = adapters
    }

    func adapter(for providerId: String) -> (any MapProviderAdapter)? {
        adapters.first {
            MapIdentity.normalizeProvider($0.id) == MapIdentity.normalizeProvider(providerId)
        }
    }

    func sortedProviders(from catalog: MapCatalog) -> [MapProvider] {
        catalog.providers.sorted {
            let nameOrder = $0.name.localizedCaseInsensitiveCompare($1.name)
            if nameOrder != .orderedSame {
                return nameOrder == .orderedAscending
            }
            return MapIdentity.normalizeProvider($0.id) < MapIdentity.normalizeProvider($1.id)
        }
    }
}

struct MapProvider: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let name: String
    let website: URL?
    let attribution: String?
    let licenseURL: URL?
    let licenseInformation: String?

    init(
        id: String,
        name: String,
        website: URL?,
        attribution: String?,
        licenseURL: URL?,
        licenseInformation: String? = nil
    ) {
        self.id = id
        self.name = name
        self.website = website
        self.attribution = attribution
        self.licenseURL = licenseURL
        self.licenseInformation = licenseInformation
    }
}

struct MapRegion: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let name: String
    let country: String?
    /// Optional for legacy callers. Catalog regions are provider-scoped when
    /// more than one provider uses the same region token.
    let providerId: String?

    init(
        id: String,
        name: String,
        country: String?,
        providerId: String? = nil
    ) {
        self.id = id
        self.name = name
        self.country = country
        self.providerId = providerId
    }
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
    private let providerRegistry: MapProviderRegistry
    private let policy = MapAcquisitionPolicy()

    init(
        adapters: [any MapProviderAdapter] = [FreizeitkarteProviderAdapter()]
    ) {
        self.providerRegistry = MapProviderRegistry(adapters: adapters)
    }

    func canonicalIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        providerRegistry
            .adapter(for: package.providerId)?
            .canonicalRegionIdentity(for: package)
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
    /// The provider's own region/package token. It is kept separate from
    /// the catalog grouping field for providers that publish subregions or
    /// multiple packages under one broad region.
    let providerRegionId: String
    /// Stable Terento identity used for joins, filenames, and manifests.
    /// Providers may supply this explicitly; legacy catalogs derive it from
    /// `identifier` or `regionId`.
    let canonicalRegionId: String
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
    let countryCodes: [String]
    let regionKind: MapRegionKind
    let tags: [String]
    let capabilities: [String]
    let releaseMetadata: MapReleaseMetadata?
    let artifacts: [MapArtifact]

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
        installSizeBytes: UInt64? = nil,
        providerRegionId: String? = nil,
        canonicalRegionId: String? = nil,
        countryCodes: [String] = [],
        regionKind: MapRegionKind = .country,
        tags: [String] = [],
        capabilities: [String] = [],
        releaseMetadata: MapReleaseMetadata? = nil,
        artifacts: [MapArtifact]? = nil
    ) {
        self.id = id
        self.providerId = providerId
        self.regionId = regionId
        let resolvedProviderRegionId = Self.nonEmpty(providerRegionId)
            ?? Self.nonEmpty(identifier)
            ?? regionId
        self.providerRegionId = resolvedProviderRegionId
        self.canonicalRegionId = Self.nonEmpty(canonicalRegionId)
            ?? resolvedProviderRegionId
        self.name = name
        self.version = version
        self.sizeBytes = sizeBytes
        self.downloadSizeBytes = downloadSizeBytes ?? sizeBytes
        self.installSizeBytes = installSizeBytes
        self.sourceURL = sourceURL
        self.releaseDate = releaseDate
        self.identifier = identifier
        self.countryCodes = countryCodes
        self.regionKind = regionKind
        self.tags = tags
        self.capabilities = capabilities
        self.releaseMetadata = releaseMetadata
        self.artifacts = artifacts ?? [
            MapArtifact(
                id: "\(id)-main",
                kind: .main,
                required: true,
                providerId: providerId,
                providerRegionId: resolvedProviderRegionId,
                canonicalRegionId: self.canonicalRegionId,
                version: version,
                releaseMetadata: releaseMetadata,
                sourceURL: sourceURL,
                sizeBytes: installSizeBytes ?? sizeBytes
            )
        ]
    }

    var downloadURL: URL? {
        sourceURL ?? mainArtifact?.sourceURL
    }

    var expectedDownloadSizeBytes: UInt64? {
        downloadSizeBytes ?? sizeBytes
    }

    var identity: MapIdentity? {
        MapIdentity(provider: providerId, region: canonicalRegionId)
    }

    var mainArtifact: MapArtifact? {
        artifacts.first(where: { $0.kind == .main })
    }

    var optionalArtifacts: [MapArtifact] {
        artifacts.filter { !$0.required }
    }

    var hasUsableMainArtifact: Bool {
        guard let mainArtifact else { return false }
        return mainArtifact.sourceURL != nil || mainArtifact.localURL != nil
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
            installSizeBytes: installSizeBytes,
            providerRegionId: providerRegionId,
            canonicalRegionId: canonicalRegionId,
            countryCodes: countryCodes,
            regionKind: regionKind,
            tags: tags,
            capabilities: capabilities,
            releaseMetadata: releaseMetadata,
            artifacts: artifacts
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
        case providerRegionId
        case canonicalRegionId
        case countryCodes
        case regionKind
        case tags
        case capabilities
        case releaseMetadata
        case artifacts
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
        let decodedProviderRegionId = try container.decodeIfPresent(
            String.self,
            forKey: .providerRegionId
        )
        let decodedCanonicalRegionId = try container.decodeIfPresent(
            String.self,
            forKey: .canonicalRegionId
        )
        providerRegionId = Self.nonEmpty(decodedProviderRegionId)
            ?? Self.nonEmpty(identifier)
            ?? regionId
        canonicalRegionId = Self.nonEmpty(decodedCanonicalRegionId)
            ?? providerRegionId
        countryCodes = try container.decodeIfPresent([String].self, forKey: .countryCodes) ?? []
        regionKind = try container.decodeIfPresent(MapRegionKind.self, forKey: .regionKind) ?? .country
        tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
        capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
        releaseMetadata = try container.decodeIfPresent(
            MapReleaseMetadata.self,
            forKey: .releaseMetadata
        )
        artifacts = try container.decodeIfPresent([MapArtifact].self, forKey: .artifacts)
            ?? [
                MapArtifact(
                    id: "\(id)-main",
                    kind: .main,
                    required: true,
                    providerId: providerId,
                    providerRegionId: providerRegionId,
                    canonicalRegionId: canonicalRegionId,
                    version: version,
                    releaseMetadata: releaseMetadata,
                    sourceURL: sourceURL,
                    sizeBytes: installSizeBytes ?? sizeBytes
                )
            ]
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
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

    func region(for id: String, providerId: String? = nil) -> MapRegion? {
        if let providerId {
            let normalizedProvider = MapIdentity.normalizeProvider(providerId)
            if let scoped = regions.first(where: {
                $0.id == id
                    && MapIdentity.normalizeProvider($0.providerId ?? "") == normalizedProvider
            }) {
                return scoped
            }
        }
        return regions.first { $0.id == id }
    }

    func packages(forProviderId providerId: String) -> [MapPackage] {
        packages.filter { $0.providerId == providerId }
    }

    var sortedProviders: [MapProvider] {
        providers.sorted {
            let nameOrder = $0.name.localizedCaseInsensitiveCompare($1.name)
            if nameOrder != .orderedSame {
                return nameOrder == .orderedAscending
            }
            return MapIdentity.normalizeProvider($0.id) < MapIdentity.normalizeProvider($1.id)
        }
    }

    func sortedPackages(forProviderId providerId: String? = nil) -> [MapPackage] {
        packages
            .filter { providerId == nil || $0.providerId == providerId }
            .sorted {
                let providerOrder = MapIdentity.normalizeProvider($0.providerId)
                    .compare(MapIdentity.normalizeProvider($1.providerId))
                if providerOrder != .orderedSame {
                    return providerOrder == .orderedAscending
                }

                let nameOrder = $0.name.localizedCaseInsensitiveCompare($1.name)
                if nameOrder != .orderedSame {
                    return nameOrder == .orderedAscending
                }
                return $0.id < $1.id
            }
    }
}

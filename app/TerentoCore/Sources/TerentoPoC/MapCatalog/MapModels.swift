import Foundation

enum MapRegionKind: String, Codable, Equatable, Sendable {
    case country
    case multiCountry
    case subregion
    case custom

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        let normalized = value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let kind: MapRegionKind?
        switch normalized {
        case "country": kind = .country
        case "multicountry", "multi-country", "multi_country": kind = .multiCountry
        case "subregion": kind = .subregion
        case "custom": kind = .custom
        default: kind = nil
        }
        guard let kind else {
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
    let downloadSizeBytes: UInt64?
    let checksum: String?
    let validationState: MapArtifactValidationState
    let sourceProof: BBBikeSourceProof?

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
        downloadSizeBytes: UInt64? = nil,
        checksum: String? = nil,
        validationState: MapArtifactValidationState = .notValidated,
        sourceProof: BBBikeSourceProof? = nil
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
        self.downloadSizeBytes = downloadSizeBytes
        self.checksum = checksum
        self.validationState = validationState
        self.sourceProof = sourceProof
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
        case downloadSizeBytes
        case checksum
        case validationState
        case sourceProof
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
            downloadSizeBytes: try container.decodeIfPresent(UInt64.self, forKey: .downloadSizeBytes),
            checksum: try container.decodeIfPresent(String.self, forKey: .checksum),
            validationState: try container.decodeIfPresent(MapArtifactValidationState.self, forKey: .validationState) ?? .notValidated,
            sourceProof: try? container.decodeIfPresent(BBBikeSourceProof.self, forKey: .sourceProof)
        )
    }
}

enum MapProviderHealth: String, Codable, Equatable, Sendable {
    case healthy
    case degraded
    case down
    case unknown

    init(apiValue: String?) {
        switch apiValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "healthy": self = .healthy
        case "degraded": self = .degraded
        case "down": self = .down
        default: self = .unknown
        }
    }
}

enum MapProviderLifecycleStatus: String, Codable, Equatable, Sendable {
    case active
    case paused
    case retired

    init(apiValue: String?) {
        switch apiValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "paused": self = .paused
        case "retired": self = .retired
        default: self = .active
        }
    }
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
    /// Original provider download format; final write validation must match
    /// the reviewed acquisition path, independently of its IMG payload.
    var usesRawIMGDownload: Bool { get }
    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity?
    /// The identity the current client parser is expected to recover from the
    /// provider's IMG header/managed filename. This lets the catalog loader
    /// reject metadata that a released client cannot validate safely.
    func expectedIMGIdentity(for package: MapPackage) -> MapIdentity?
    func artifacts(for package: MapPackage) -> [MapArtifact]
}

extension MapProviderAdapter {
    var usesRawIMGDownload: Bool { false }
}

struct FreizeitkarteProviderAdapter: MapProviderAdapter, Sendable {
    let id = "freizeitkarte"

    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        FreizeitkarteMapRegionIdentityMapper().map(package: package)
    }

    func expectedIMGIdentity(for package: MapPackage) -> MapIdentity? {
        MapIdentity(provider: id, region: package.providerRegionId)
    }

    func artifacts(for package: MapPackage) -> [MapArtifact] {
        package.artifacts
    }
}

struct OpenTopoMapProviderAdapter: MapProviderAdapter, Sendable {
    let id = "opentopomap"

    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        OpenTopoMapRegionIdentityMapper().map(package: package)
    }

    func expectedIMGIdentity(for package: MapPackage) -> MapIdentity? {
        let providerRegion = MapIdentity.normalizeRegion(package.providerRegionId)
        let parsedRegion = providerRegion == "LITHUANIA" ? "LTU" : providerRegion
        return MapIdentity(provider: id, region: parsedRegion)
    }

    func artifacts(for package: MapPackage) -> [MapArtifact] {
        package.artifacts
    }
}

/// The French provider package token remains the identity, including variants.
struct MapRandoProviderAdapter: MapProviderAdapter, Sendable {
    let id = "maprando"
    let usesRawIMGDownload = true

    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        let tokens = [package.providerRegionId, package.canonicalRegionId, package.regionId]
            .compactMap { $0 }
            .compactMap { MapIdentity(provider: id, region: $0)?.region }
        if tokens.contains(where: { $0.contains("CRIMEE") || $0.contains("CRIMEA") }) {
            return CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA")
        }
        if tokens.contains(where: { $0.contains("RUSSIE") || $0.contains("RUSSIA") })
            || package.countryCodes.contains(where: { $0.uppercased() == "RU" }) {
            return CanonicalMapRegionIdentity(countryCode: "RU")
        }
        return package.countryCodes.first.map { CanonicalMapRegionIdentity(countryCode: $0) }
    }

    func expectedIMGIdentity(for package: MapPackage) -> MapIdentity? {
        MapIdentity(provider: id, region: package.providerRegionId)
    }

    func artifacts(for package: MapPackage) -> [MapArtifact] { package.artifacts }
}

/// OpenTopoMap publishes country names in its Garmin page while the catalog
/// keeps a stable ISO country code for product policy. This mapper is the
/// only place where that provider-specific representation is interpreted.
struct OpenTopoMapRegionIdentityMapper: Sendable {
    func map(package: MapPackage) -> CanonicalMapRegionIdentity? {
        guard MapIdentity.normalizeProvider(package.providerId) == "opentopomap" else {
            return nil
        }

        let countryCode = package.countryCodes
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
            .first { $0.count == 2 || $0.count == 3 }

        if let countryCode {
            return CanonicalMapRegionIdentity(countryCode: countryCode)
        }

        // Older and partially populated OTM catalogs omitted countryCodes.
        // Keep the current acquisition policy fail-closed for the provider's
        // explicit russia/Crimea identities instead of treating them as an
        // unknown, therefore available, non-russia region.
        let identityTokens = [
            package.providerRegionId,
            package.canonicalRegionId,
            package.regionId,
            package.identifier,
            package.id
        ]
        .compactMap { $0?.uppercased() }
        .map { $0.filter { $0.isLetter || $0.isNumber } }

        if identityTokens.contains(where: { $0.contains("CRIMEA") }) {
            return CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA")
        }
        if identityTokens.contains(where: { $0.contains("RUSSIA") }) {
            return CanonicalMapRegionIdentity(countryCode: "RU")
        }
        return nil
    }
}

/// The registry has no implicit/default provider. Callers supply the
/// adapters they have intentionally enabled, and presentation order is
/// deterministic and alphabetical by display name.
struct MapProviderRegistry: Sendable {
    let adapters: [any MapProviderAdapter]

    static let bundled = MapProviderRegistry(adapters: [
        FreizeitkarteProviderAdapter(),
        OpenTopoMapProviderAdapter(),
        MapRandoProviderAdapter(),
        BBBikeProviderAdapter()
    ])

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
    let lifecycleStatus: MapProviderLifecycleStatus
    let health: MapProviderHealth
    let lastCheckedAt: Date?
    let lastSuccessfulCatalogSync: Date?

    init(
        id: String,
        name: String,
        website: URL?,
        attribution: String?,
        licenseURL: URL?,
        licenseInformation: String? = nil,
        lifecycleStatus: MapProviderLifecycleStatus = .active,
        health: MapProviderHealth = .unknown,
        lastCheckedAt: Date? = nil,
        lastSuccessfulCatalogSync: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.website = website
        self.attribution = attribution
        self.licenseURL = licenseURL
        self.licenseInformation = licenseInformation
        self.lifecycleStatus = lifecycleStatus
        self.health = health
        self.lastCheckedAt = lastCheckedAt
        self.lastSuccessfulCatalogSync = lastSuccessfulCatalogSync
    }

    var allowsNewInstallCatalog: Bool {
        lifecycleStatus == .active && health != .down
    }

    var temporaryUnavailableReason: String? {
        guard !allowsNewInstallCatalog else { return nil }
        switch lifecycleStatus {
        case .paused, .retired:
            return "Temporarily unavailable"
        case .active:
            return health == .down ? "Temporarily unavailable" : nil
        }
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
        adapters: [any MapProviderAdapter] = MapProviderRegistry.bundled.adapters
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
    let sourceKind: MapSourceKind
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
    let mapType: String?
    let geographicRegionId: String?
    let countryCodes: [String]
    let regionKind: MapRegionKind
    let tags: [String]
    let capabilities: [String]
    let releaseMetadata: MapReleaseMetadata?
    let artifacts: [MapArtifact]
    /// Distinguishes explicit artifact metadata from the compatibility main
    /// artifact synthesized for legacy package records.
    let hasExplicitArtifactCollection: Bool

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
        mapType: String? = nil,
        geographicRegionId: String? = nil,
        countryCodes: [String] = [],
        regionKind: MapRegionKind = .country,
        tags: [String] = [],
        capabilities: [String] = [],
        releaseMetadata: MapReleaseMetadata? = nil,
        artifacts: [MapArtifact]? = nil,
        sourceKind: MapSourceKind = .provider
    ) {
        self.sourceKind = sourceKind
        self.id = id
        self.providerId = providerId
        self.regionId = regionId
        let resolvedProviderRegionId = Self.nonEmpty(providerRegionId)
            ?? Self.nonEmpty(identifier)
            ?? regionId
        self.providerRegionId = resolvedProviderRegionId
        self.canonicalRegionId = Self.resolvedCanonicalRegionID(
            providerId: providerId,
            providerRegionId: resolvedProviderRegionId,
            explicitCanonicalRegionId: canonicalRegionId
        )
        self.name = name
        self.version = version
        self.sizeBytes = sizeBytes
        self.downloadSizeBytes = downloadSizeBytes ?? sizeBytes
        self.installSizeBytes = installSizeBytes
        self.sourceURL = sourceURL
        self.releaseDate = releaseDate
        self.identifier = identifier
        self.mapType = mapType
        self.geographicRegionId = geographicRegionId
        self.countryCodes = countryCodes
        self.regionKind = regionKind
        self.tags = tags
        self.capabilities = capabilities
        self.releaseMetadata = releaseMetadata
        self.hasExplicitArtifactCollection = artifacts != nil
        self.artifacts = artifacts ?? [
            MapArtifact(
                id: "\(id)-main",
                source: sourceKind,
                kind: .main,
                required: true,
                providerId: providerId,
                providerRegionId: resolvedProviderRegionId,
                canonicalRegionId: self.canonicalRegionId,
                version: version,
                releaseMetadata: releaseMetadata,
                sourceURL: sourceURL,
                sizeBytes: installSizeBytes ?? sizeBytes,
                downloadSizeBytes: downloadSizeBytes ?? sizeBytes
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

    /// Provider-native labels are intended for user-facing display. The
    /// normalized version remains available for comparisons and update logic.
    var displayVersionLabel: String? {
        if let label = releaseMetadata?.versionLabel?.trimmingCharacters(
            in: .whitespacesAndNewlines
        ), Self.isUserFacingReleaseLabel(label) {
            return label
        }

        // 2000-01 was the historical API serializer fallback. It is not a
        // real map version and must never reach the user-facing UI.
        guard version.year != 2000 || version.month != 1 else {
            return nil
        }
        return version.description
    }

    private static func isUserFacingReleaseLabel(_ value: String) -> Bool {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return false }

        let placeholderValues: Set<String> = [
            "unknown", "n/a", "na", "none", "null", "2000-01", "1970-01"
        ]
        guard !placeholderValues.contains(normalized.lowercased()) else {
            return false
        }

        let dateOrSemanticVersion = #"(?i)(?:^|\b)(?:20\d{2}[-/.](?:0?[1-9]|1[0-2])(?:[-/.](?:0?[1-9]|[12]\d|3[01]))?|(?:0?[1-9]|1[0-2])/20\d{2}|v?\d+\.\d+(?:\.\d+)?)(?:\b|$)"#
        let explicitBuildIdentifier = #"(?i)\b(?:build|release)[- _#]?[a-z0-9.-]*\d[a-z0-9.-]*\b"#
        return normalized.range(of: dateOrSemanticVersion, options: .regularExpression) != nil
            || normalized.range(of: explicitBuildIdentifier, options: .regularExpression) != nil
    }

    var optionalArtifacts: [MapArtifact] {
        artifacts.filter { !$0.required }
    }

    /// Returns a package projection for acquiring one exact artifact. Package
    /// identity and release remain unchanged; only the source and size
    /// contract are narrowed to the selected artifact.
    func acquisitionPackage(for artifact: MapArtifact) -> MapPackage {
        MapPackage(
            id: id,
            providerId: providerId,
            regionId: regionId,
            name: name,
            version: version,
            sizeBytes: artifact.downloadSizeBytes ?? artifact.sizeBytes ?? sizeBytes,
            sourceURL: artifact.sourceURL ?? sourceURL,
            releaseDate: releaseDate,
            identifier: identifier,
            downloadSizeBytes: artifact.downloadSizeBytes ?? downloadSizeBytes,
            installSizeBytes: artifact.sizeBytes,
            providerRegionId: providerRegionId,
            canonicalRegionId: canonicalRegionId,
            mapType: mapType,
            geographicRegionId: geographicRegionId,
            countryCodes: countryCodes,
            regionKind: regionKind,
            tags: tags,
            capabilities: capabilities,
            releaseMetadata: releaseMetadata,
            artifacts: [artifact],
            sourceKind: sourceKind
        )
    }

    func withArtifacts(_ artifacts: [MapArtifact]) -> MapPackage {
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
            mapType: mapType,
            geographicRegionId: geographicRegionId,
            countryCodes: countryCodes,
            regionKind: regionKind,
            tags: tags,
            capabilities: capabilities,
            releaseMetadata: releaseMetadata,
            artifacts: artifacts,
            sourceKind: sourceKind
        )
    }

    var defaultArtifactPlan: MapArtifactPlan {
        artifactPlan()
    }

    func artifactPlan(
        includingOptionalArtifactIDs optionalArtifactIDs: Set<String> = []
    ) -> MapArtifactPlan {
        let plannedArtifacts = hasExplicitArtifactCollection || installSizeBytes != nil
            ? artifacts
            : artifacts.map { artifact in
                // `sizeBytes` is historically the archive/download size. A
                // legacy record with no measured install size must remain
                // unresolved even though its synthesized main artifact carries
                // that value.
                artifact.kind == .main ? artifact.withSize(nil) : artifact
            }
        return MapArtifactPlan(
            packageID: id,
            artifacts: plannedArtifacts,
            includingOptionalArtifactIDs: optionalArtifactIDs
        )
    }

    var hasUsableMainArtifact: Bool {
        guard let mainArtifact else { return false }
        // Existing providers retain their reviewed catalog contract, including
        // source-unavailable MapRando rows. BBBike unavailable source metadata is
        // visible but never a usable install artifact.
        if MapIdentity.normalizeProvider(providerId) == "bbbike",
           mainArtifact.validationState == .unavailable || mainArtifact.validationState == .failed { return false }
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
            mapType: mapType,
            geographicRegionId: geographicRegionId,
            countryCodes: countryCodes,
            regionKind: regionKind,
            tags: tags,
            capabilities: capabilities,
            releaseMetadata: releaseMetadata,
            artifacts: artifacts,
            sourceKind: sourceKind
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
        case mapType, geographicRegionId
        case countryCodes
        case regionKind
        case tags
        case capabilities
        case releaseMetadata
        case artifacts
        case sourceKind
        case hasExplicitArtifactCollection
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceKind = try container.decodeIfPresent(MapSourceKind.self, forKey: .sourceKind) ?? .provider
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
        canonicalRegionId = Self.resolvedCanonicalRegionID(
            providerId: providerId,
            providerRegionId: providerRegionId,
            explicitCanonicalRegionId: decodedCanonicalRegionId
        )
        mapType = try container.decodeIfPresent(String.self, forKey: .mapType)
        geographicRegionId = try container.decodeIfPresent(String.self, forKey: .geographicRegionId)
        countryCodes = try container.decodeIfPresent([String].self, forKey: .countryCodes) ?? []
        regionKind = try container.decodeIfPresent(MapRegionKind.self, forKey: .regionKind) ?? .country
        tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
        capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
        releaseMetadata = try container.decodeIfPresent(
            MapReleaseMetadata.self,
            forKey: .releaseMetadata
        )
        let decodedArtifacts = try container.decodeIfPresent([MapArtifact].self, forKey: .artifacts)
        hasExplicitArtifactCollection = try container.decodeIfPresent(
            Bool.self,
            forKey: .hasExplicitArtifactCollection
        ) ?? (decodedArtifacts != nil)
        artifacts = decodedArtifacts
            ?? [
                MapArtifact(
                    id: "\(id)-main",
                    source: sourceKind,
                    kind: .main,
                    required: true,
                    providerId: providerId,
                    providerRegionId: providerRegionId,
                    canonicalRegionId: canonicalRegionId,
                    version: version,
                    releaseMetadata: releaseMetadata,
                    sourceURL: sourceURL,
                    sizeBytes: installSizeBytes ?? sizeBytes,
                    downloadSizeBytes: downloadSizeBytes ?? sizeBytes
                )
            ]
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Freizeitkarte's legacy/API catalog may group several concrete
    /// packages under one broad region (AZORES also contains BALEARICS and
    /// MADEIRA). Its provider-region token is the identity embedded in the
    /// IMG and therefore the stable filename/manifest identity. Other
    /// providers retain their explicit canonical identity (for example OTM
    /// uses an ISO code while its provider-region value is a URL slug).
    private static func resolvedCanonicalRegionID(
        providerId: String,
        providerRegionId: String,
        explicitCanonicalRegionId: String?
    ) -> String {
        if MapIdentity.normalizeProvider(providerId) == "freizeitkarte" {
            return providerRegionId
        }
        return nonEmpty(explicitCanonicalRegionId) ?? providerRegionId
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

/// One provider, two independent complete maps. This is not an optional component.
enum BBBikeMapType: String, Codable, CaseIterable, Sendable {
    case bbbike = "bbbike-latin1"
    case ontrail = "ontrail-latin1"
    var style: String { self == .bbbike ? "bbbike" : "ontrail" }
    var title: String { self == .bbbike ? "BBBike" : "BBBike (Ontrail)" }
    var filterID: String { self == .bbbike ? "bbbike" : "bbbikeontrail" }
}

struct BBBikeSourceProof: Codable, Equatable, Sendable {
    let sourceURL: URL
    let etag: String?
    let lastModified: String?
    let downloadSizeBytes: UInt64
    let installSizeBytes: UInt64
    let payloadPath: String
    let revision: String
    let sourceIdentity: String
    let mapType: String
    let sourceRegion: String
    let payloadMD5: String
    let generatedAt: String
}

/// Optional manifest context. Display names never grant ownership; source path and
/// type only corroborate the bounded IMG header after an exact ownership match.
struct BBBikeMapMetadata: Codable, Equatable, Sendable {
    let sourcePath: String
    let mapType: String
    let displayName: String
    let geographicRegionId: String?
    init?(package: MapPackage) {
        guard MapIdentity.normalizeProvider(package.providerId) == "bbbike",
              BBBikeProviderAdapter.validIdentity(package), let type = package.mapType else { return nil }
        sourcePath = package.providerRegionId
        mapType = type
        displayName = package.name
        geographicRegionId = package.geographicRegionId
    }
    var canonicalRegion: String { BBBikeProviderAdapter.regionToken(path: sourcePath, type: mapType) }
}

struct MapProviderFilterOption: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
}

enum MapProviderDisplay {
    static func sourceProviderID(filterID: String) -> String {
        let id = MapIdentity.normalizeProvider(filterID)
        return id == "bbbikeontrail" ? "bbbike" : id
    }
    static func filterOptions(providers: [MapProvider]) -> [MapProviderFilterOption] {
        providers.flatMap { provider in
            if MapIdentity.normalizeProvider(provider.id) == "bbbike" {
                return BBBikeMapType.allCases.map { MapProviderFilterOption(id: $0.filterID, title: $0.title) }
            }
            return [MapProviderFilterOption(id: MapIdentity.normalizeProvider(provider.id), title: provider.name)]
        }
    }

    static func filterID(providerID: String, regionID: String?) -> String {
        let provider = MapIdentity.normalizeProvider(providerID)
        guard provider == "bbbike" else { return provider }
        return MapIdentity.normalizeRegion(regionID ?? "").hasSuffix("ONTRAILLATIN1") ? "bbbikeontrail" : "bbbike"
    }
    static func title(providerID: String, regionID: String?, fallback: String) -> String {
        guard MapIdentity.normalizeProvider(providerID) == "bbbike" else { return fallback }
        return filterID(providerID: providerID, regionID: regionID) == "bbbikeontrail" ? "BBBike (Ontrail)" : "BBBike"
    }
}

struct BBBikeProviderAdapter: MapProviderAdapter, Sendable {
    let id = "bbbike"
    static func regionToken(path: String, type: String) -> String {
        (path + "-" + type).replacingOccurrences(of: "/", with: "-").uppercased()
    }
    static let exampleRegions: Set<String> = ["asia/cambodia", "asia/jordan", "europe/luxembourg"]
    static func isReviewedSourcePath(_ path: String, sourceRegion: String, type: String) -> Bool {
        guard let leaf = sourceRegion.split(separator: "/").last, BBBikeMapType(rawValue: type) != nil else { return false }
        let suffix = "\(sourceRegion)/\(leaf).osm.garmin-\(type).zip"
        return path == "/osm/garmin/region/" + suffix
            || (exampleRegions.contains(sourceRegion) && path == "/osm/garmin/example/" + suffix)
    }
    static let coexistenceReason = "Select either BBBike or BBBike (Ontrail) for the same region. These two map types cannot be installed together."
    static func installedTypeConflictMessage(for package: MapPackage) -> String {
        guard let selectedType = BBBikeMapType(rawValue: package.mapType ?? "") else { return coexistenceReason }
        let installedType: BBBikeMapType = selectedType == .bbbike ? .ontrail : .bbbike
        return "To install “\(selectedType.title) - \(package.name)”, first remove “\(installedType.title) - \(package.name)” in Manage maps. BBBike and BBBike (Ontrail) cannot be installed together for the same region."
    }
    static func conflicts(_ package: MapPackage, provider: String?, region: String?) -> Bool {
        guard MapIdentity.normalizeProvider(package.providerId) == "bbbike",
              MapIdentity.normalizeProvider(provider ?? "") == "bbbike", let region else { return false }
        return BBBikeMapType.allCases.filter { $0.rawValue != package.mapType }.contains {
            MapIdentity.normalizeRegion(regionToken(path: package.providerRegionId, type: $0.rawValue)) == MapIdentity.normalizeRegion(region)
        }
    }
    static func conflicts(_ package: MapPackage, filename: String) -> Bool {
        guard MapIdentity.normalizeProvider(package.providerId) == "bbbike",
              filename.hasPrefix("terento_bbbike_"), filename.hasSuffix(".img") else { return false }
        var token = String(filename.dropFirst("terento_bbbike_".count).dropLast(4))
        if let date = token.range(of: #"_[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?$"#, options: .regularExpression) { token.removeSubrange(date) }
        return conflicts(package, provider: "bbbike", region: token)
    }
    static func selectionConflicts(_ packages: [MapPackage]) -> Bool {
        packages.contains { package in packages.contains { other in
            package.id != other.id && conflicts(package, provider: other.providerId, region: other.canonicalRegionId)
        } }
    }
    static func validPath(_ path: String) -> Bool {
        path.range(of: #"^(?:africa|asia|australia-oceania|central-america|europe|north-america|south-america|antarctica)/[a-z0-9]+(?:[-/][a-z0-9]+)*$"#, options: .regularExpression) != nil
            && path.utf8.count <= 180
    }
    static func validIdentity(_ package: MapPackage) -> Bool {
        guard MapIdentity.normalizeProvider(package.providerId) == "bbbike",
              validPath(package.providerRegionId),
              let type = package.mapType, BBBikeMapType(rawValue: type) != nil,
              package.canonicalRegionId == regionToken(path: package.providerRegionId, type: type),
              package.regionId == package.canonicalRegionId,
              package.id == "bbbike-" + package.canonicalRegionId.lowercased(),
              package.version.day != nil else { return false }
        return true
    }
    func canonicalRegionIdentity(for package: MapPackage) -> CanonicalMapRegionIdentity? {
        let parts = package.providerRegionId.lowercased().split(separator: "/")
        if parts.contains("crimea") { return CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA") }
        if parts.contains("russia") || package.countryCodes.contains("RU") { return CanonicalMapRegionIdentity(countryCode: "RU") }
        return package.countryCodes.first.map { CanonicalMapRegionIdentity(countryCode: $0) }
    }
    func expectedIMGIdentity(for package: MapPackage) -> MapIdentity? {
        guard Self.validIdentity(package), let proof = package.mainArtifact?.sourceProof,
              proof.sourceURL == package.downloadURL,
              let etag = proof.etag, etag.hasPrefix("\""), etag.hasSuffix("\""), etag.count > 2,
              proof.lastModified?.isEmpty == false,
              ISO8601DateFormatter().date(from: proof.generatedAt) != nil,
              proof.sourceRegion == package.providerRegionId,
              proof.mapType == package.mapType,
              proof.sourceIdentity == "bbbike:\(proof.sourceRegion):\(proof.mapType)",
              proof.downloadSizeBytes == package.expectedDownloadSizeBytes,
              proof.installSizeBytes == package.installSizeBytes,
              proof.installSizeBytes > 0, proof.downloadSizeBytes > 0,
              proof.downloadSizeBytes <= UInt64(Int64.max), proof.installSizeBytes <= UInt64(Int64.max),
              proof.payloadMD5.range(of: #"^[a-f0-9]{32}$"#, options: .regularExpression) != nil,
              proof.revision.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil,
              let leaf = package.providerRegionId.split(separator: "/").last,
              proof.payloadPath == "\(leaf)-garmin-\(proof.mapType)/gmapsupp.img",
              Self.isReviewedSourcePath(proof.sourceURL.path, sourceRegion: proof.sourceRegion, type: proof.mapType),
              proof.generatedAt.hasPrefix(package.version.description + "T") else { return nil }
        return package.identity
    }
    func artifacts(for package: MapPackage) -> [MapArtifact] { package.artifacts }
}

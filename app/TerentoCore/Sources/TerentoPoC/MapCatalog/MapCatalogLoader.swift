import Foundation

enum MapCatalogSource: String, Sendable, Equatable {
    case remote
    case bundledFallback

    var userLabel: String {
        switch self {
        case .remote:
            return "Remote catalog"
        case .bundledFallback:
            return "Using local catalog — may be out of date"
        }
    }
}

/// Release builds expose only source-validated contour metadata. Debug builds
/// retain the explicit internal rollout override for focused diagnostics.
struct MapContourRolloutPolicy: Sendable, Equatable {
    enum Mode: String, Equatable, Sendable {
        case off
        case allowlist
        case publicValidated
    }

    let mode: Mode
    let allowlist: Set<String>

    init(mode: Mode = .off, allowlist: Set<String> = []) {
        self.mode = mode
        self.allowlist = allowlist
    }

    #if DEBUG
    static var localDebugRC: MapContourRolloutPolicy {
        let environment = ProcessInfo.processInfo.environment
        let mode = Mode(rawValue: environment[
            "TERENTO_OPENTOPO_MAP_CONTOUR_MODE"
        ]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? "publicValidated") ?? .publicValidated
        let allowlist = Set(
            (environment["TERENTO_OPENTOPO_MAP_CONTOUR_ALLOWLIST"] ?? "")
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        )
        return MapContourRolloutPolicy(mode: mode, allowlist: allowlist)
    }
    #else
    static let localDebugRC = MapContourRolloutPolicy(mode: .publicValidated)
    #endif

    func applying(to catalog: MapCatalog) -> MapCatalog {
        let packages = catalog.packages.map { package in
            let artifacts = package.artifacts.map { artifact in
                guard artifact.kind == .contours,
                      MapIdentity.normalizeProvider(artifact.providerId ?? "") == "opentopomap" else {
                    return artifact
                }
                switch mode {
                case .off:
                    return artifact.withValidationState(
                        artifact.validationState == .unavailable ? .unavailable : .notValidated
                    )
                case .publicValidated:
                    return artifact.validationState == .validated
                        ? artifact
                        : artifact.withValidationState(.notValidated)
                case .allowlist:
                    guard artifact.validationState != .unavailable,
                          isAllowlisted(package) else {
                        return artifact.withValidationState(.notValidated)
                    }
                    return artifact.withValidationState(.validated)
                }
            }
            return package.withArtifacts(artifacts)
        }
        return MapCatalog(
            catalogVersion: catalog.catalogVersion,
            updatedAt: catalog.updatedAt,
            providers: catalog.providers,
            regions: catalog.regions,
            packages: packages
        )
    }

    private func isAllowlisted(_ package: MapPackage) -> Bool {
        let normalizedAllowlist = Set(allowlist.map(normalizeAllowlistToken))
        if normalizedAllowlist.contains(normalizeAllowlistToken(package.id)) {
            return true
        }

        let providerID = MapIdentity.normalizeProvider(package.providerId)
        let packageRegions = [
            package.providerRegionId,
            package.identifier,
            package.canonicalRegionId,
            package.regionId
        ]
        .compactMap { $0 }
        .map(MapIdentity.normalizeRegion)
        .filter { !$0.isEmpty }

        return normalizedAllowlist.contains { token in
            let prefix = "\(providerID)-"
            guard token.hasPrefix(prefix) else { return false }
            let allowlistedRegion = String(token.dropFirst(prefix.count))
            return packageRegions.contains {
                equivalentProviderRegions(
                    providerID: providerID,
                    lhs: allowlistedRegion,
                    rhs: $0
                )
            }
        }
    }

    private func normalizeAllowlistToken(_ value: String) -> String {
        value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "_", with: "-")
    }

    private func equivalentProviderRegions(
        providerID: String,
        lhs: String,
        rhs: String
    ) -> Bool {
        let left = MapIdentity.normalizeRegion(lhs)
        let right = MapIdentity.normalizeRegion(rhs)
        guard left != right else { return true }

        // OTM changed Lithuania's published region token from LTU to its
        // country slug. Keep the reviewed local allowlist stable across that
        // catalog transition.
        return providerID == "opentopomap"
            && Set([left, right]) == Set(["LTU", "LITHUANIA"])
    }
}

struct MapCatalogLoadResult: Sendable {
    let catalog: MapCatalog
    let source: MapCatalogSource
}

struct MapCatalogLoader: Sendable {
    static let defaultEndpoint: URL? = {
        #if DEBUG
        // A local hardware candidate can pin its reviewed metadata snapshot
        // while the new API/provider is still paused. Public builds ignore it.
        if Bundle.main.object(forInfoDictionaryKey: "TerentoUseBundledMapCatalog") as? Bool == true {
            return nil
        }
        #endif
        return URLComponents(string: "https://api.terento.app/maps/catalog-v3.json")?.url
    }()

    let endpoint: URL?
    let contourRolloutPolicy: MapContourRolloutPolicy

    init(
        endpoint: URL? = MapCatalogLoader.defaultEndpoint,
        contourRolloutPolicy: MapContourRolloutPolicy = .localDebugRC
    ) {
        self.endpoint = endpoint
        self.contourRolloutPolicy = contourRolloutPolicy
    }

    /// Metadata is fetched from the future catalog service first. The local
    /// catalog is the safe fallback and may be stale; it never contains map
    /// binaries.
    func loadRemoteThenFallback() async throws -> MapCatalogLoadResult {
        do {
            let data = try await loadRemoteData()
            let remoteCatalog = try decode(data)
            let bundledCatalog = try loadBundled()
            guard MapCatalogClientCompatibilityValidator().isCompatible(
                remoteCatalog
            ) else {
                throw MapCatalogError.invalidMetadata(
                    "the remote catalog is incompatible with this app build"
                )
            }
            // The API may roll out provider records independently from the
            // app. Keep the remote catalog authoritative for records it knows
            // and add only missing bundled records so a provider rollout does
            // not make the app silently lose an enabled provider.
            let catalog = contourRolloutPolicy.applying(
                to: remoteCatalog.mergingSupplemental(bundledCatalog)
            )
            return MapCatalogLoadResult(
                catalog: catalog,
                source: .remote
            )
        } catch {
            return MapCatalogLoadResult(
                catalog: try loadBundled(),
                source: .bundledFallback
            )
        }
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
            return contourRolloutPolicy.applying(
                to: try decode(Data(contentsOf: resourceURL))
            )
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
            return contourRolloutPolicy.applying(
                to: try decode(Data(contentsOf: resourceURL))
            )
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

/// A release-bound semantic gate for remotely mutable map metadata. JSON can
/// be structurally valid while still naming an IMG identity that the current
/// app parser cannot recover. Such a catalog must fall back as a whole to the
/// bundled last-known-good snapshot instead of breaking only some regions.
struct MapCatalogClientCompatibilityValidator: Sendable {
    private let providerRegistry: MapProviderRegistry
    private let sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry

    init(
        providerRegistry: MapProviderRegistry = .bundled,
        sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry = .bundled
    ) {
        self.providerRegistry = providerRegistry
        self.sourcePolicyRegistry = sourcePolicyRegistry
    }

    func isCompatible(_ catalog: MapCatalog) -> Bool {
        let installableProviderIDs = catalog.providers
            .filter(\.allowsNewInstallCatalog)
            .map { MapIdentity.normalizeProvider($0.id) }
        let packageProviderIDs = catalog.packages
            .map { MapIdentity.normalizeProvider($0.providerId) }
        let packageIDs = catalog.packages.map(\.id)

        guard !installableProviderIDs.isEmpty,
              !catalog.packages.isEmpty,
              installableProviderIDs.allSatisfy({ !$0.isEmpty }),
              Set(installableProviderIDs).count == installableProviderIDs.count,
              Set(packageProviderIDs) == Set(installableProviderIDs),
              packageIDs.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              Set(packageIDs).count == packageIDs.count else {
            return false
        }

        return catalog.packages.allSatisfy { package in
            let providerID = MapIdentity.normalizeProvider(package.providerId)
            guard let adapter = providerRegistry.adapter(for: providerID),
                  let sourcePolicy = sourcePolicyRegistry.policy(for: providerID),
                  let downloadURL = package.downloadURL,
                  let expectedIdentity = package.identity,
                  let parsedIdentity = adapter.expectedIMGIdentity(for: package),
                  package.hasUsableMainArtifact else {
                return false
            }

            do {
                try sourcePolicy.validate(downloadURL)
            } catch {
                return false
            }

            return MapIdentityMatcher.matches(
                actual: parsedIdentity,
                expected: expectedIdentity,
                providerRegionId: package.providerRegionId,
                identifier: package.identifier
            )
        }
    }
}

extension MapCatalog {
    func mergingSupplemental(_ supplemental: MapCatalog) -> MapCatalog {
        let providerIDs = Set(
            providers.map { MapIdentity.normalizeProvider($0.id) }
        )
        let regionKeys = Set(regions.map { region in
            "\(MapIdentity.normalizeProvider(region.providerId ?? "")):\(MapIdentity.normalizeRegion(region.id))"
        })
        let packageIDs = Set(packages.map(\.id))

        let additionalProviders = supplemental.providers.filter {
            !providerIDs.contains(MapIdentity.normalizeProvider($0.id))
        }
        let additionalRegions = supplemental.regions.filter { region in
            let key = "\(MapIdentity.normalizeProvider(region.providerId ?? "")):\(MapIdentity.normalizeRegion(region.id))"
            let providerID = MapIdentity.normalizeProvider(region.providerId ?? "")
            return !providerIDs.contains(providerID) && !regionKeys.contains(key)
        }
        let additionalPackages = supplemental.packages.filter {
            !providerIDs.contains(MapIdentity.normalizeProvider($0.providerId))
                && !packageIDs.contains($0.id)
        }

        // A remote catalog can contain the same provider package under a
        // provider-renamed ID or region spelling. Preserve that remote
        // package as authoritative, but add independently reviewed optional
        // artifacts (currently OTM contours) from the bundled catalog. The
        // previous ID-only merge silently dropped those artifacts whenever
        // the remote catalog used a newer package ID such as
        // `opentopomap-lithuania`.
        let supplementalByIdentity = Dictionary(
            supplemental.packages.compactMap { package in
                packageMergeKey(for: package).map { ($0, package) }
            },
            uniquingKeysWith: { first, _ in first }
        )
        let mergedPackages = packages.map { package in
            guard let key = packageMergeKey(for: package),
                  let supplementalPackage = supplementalByIdentity[key] else {
                return package
            }

            let existingKinds = Set(package.artifacts.map(\.kind))
            let supplementalArtifacts = supplementalPackage.artifacts.filter { artifact in
                artifact.kind != .main
                    && !artifact.required
                    && !existingKinds.contains(artifact.kind)
                    && !package.artifacts.contains(where: { $0.id == artifact.id })
            }
            guard !supplementalArtifacts.isEmpty else { return package }
            return package.withArtifacts(package.artifacts + supplementalArtifacts)
        }

        return MapCatalog(
            catalogVersion: max(catalogVersion, supplemental.catalogVersion),
            updatedAt: max(updatedAt, supplemental.updatedAt),
            providers: providers + additionalProviders,
            regions: regions + additionalRegions,
            packages: mergedPackages + additionalPackages
        )
    }

    private func packageMergeKey(for package: MapPackage) -> String? {
        let provider = MapIdentity.normalizeProvider(package.providerId)
        guard !provider.isEmpty else { return nil }

        let region = [
            package.providerRegionId,
            package.identifier,
            package.canonicalRegionId,
            package.regionId
        ]
        .compactMap { $0 }
        .compactMap { value -> String? in
            let normalized = MapIdentity.normalizeRegion(value)
            return normalized.isEmpty ? nil : normalized
        }
        .first

        guard let region else { return nil }
        return "\(provider):\(region)"
    }
}

struct MapCatalogDocumentDecoder: Sendable {
    func decode(_ data: Data) throws -> MapCatalog {
        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .custom { decoder in
                let container = try decoder.singleValueContainer()
                let value = try container.decode(String.self)
                let formatOptions: [ISO8601DateFormatter.Options] = [
                    [.withInternetDateTime, .withFractionalSeconds],
                    [.withInternetDateTime]
                ]

                for options in formatOptions {
                    let formatter = ISO8601DateFormatter()
                    formatter.formatOptions = options
                    formatter.timeZone = TimeZone(secondsFromGMT: 0)
                    if let date = formatter.date(from: value) {
                        return date
                    }
                }

                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Expected an ISO 8601 timestamp with optional fractional seconds."
                )
            }
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
            let lifecycleStatus = MapProviderLifecycleStatus(apiValue: providerDocument.status)
            let health = MapProviderHealth(apiValue: providerDocument.health)
            let provider = MapProvider(
                id: providerDocument.id,
                name: providerDocument.name,
                website: providerDocument.website,
                attribution: providerDocument.attribution,
                licenseURL: providerDocument.licenseURL,
                licenseInformation: providerDocument.licenseInformation,
                lifecycleStatus: lifecycleStatus,
                health: health,
                lastCheckedAt: providerDocument.lastCheckedAt,
                lastSuccessfulCatalogSync: providerDocument.lastSuccessfulCatalogSync
            )
            providers.append(
                provider
            )

            guard provider.allowsNewInstallCatalog else { continue }

            for map in providerDocument.maps {
                let regionID = map.region
                let scopedRegionKey = "\(MapIdentity.normalizeProvider(providerDocument.id)):\(regionID)"
                regionsByID[scopedRegionKey] = MapRegion(
                    id: regionID,
                    name: map.name,
                    country: map.country ?? map.name,
                    providerId: providerDocument.id
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
                        installSizeBytes: map.installSizeBytes,
                        providerRegionId: map.providerRegionId,
                        canonicalRegionId: map.canonicalRegionId,
                        countryCodes: map.countryCodes ?? map.country.map { [$0] } ?? [],
                        regionKind: map.regionKind ?? .country,
                        tags: map.tags ?? [],
                        capabilities: map.capabilities ?? [],
                        releaseMetadata: map.releaseMetadata,
                        artifacts: map.artifacts
                    )
                )
            }
        }

        return MapCatalog(
            catalogVersion: catalogVersion,
            updatedAt: updatedAt,
            providers: providers.sorted {
                $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            },
            regions: Array(regionsByID.values).sorted {
                let nameOrder = $0.name.localizedCaseInsensitiveCompare($1.name)
                if nameOrder != .orderedSame {
                    return nameOrder == .orderedAscending
                }
                return $0.id < $1.id
            },
            packages: packages.sorted {
                let providerOrder = MapIdentity.normalizeProvider($0.providerId)
                    .compare(MapIdentity.normalizeProvider($1.providerId))
                if providerOrder != .orderedSame {
                    return providerOrder == .orderedAscending
                }
                return $0.id < $1.id
            }
        )
    }

}

private struct ProviderDocument: Decodable {
    let id: String
    let name: String
    let website: URL?
    let attribution: String?
    let licenseURL: URL?
    let licenseInformation: String?
    let status: String?
    let health: String?
    let lastCheckedAt: Date?
    let lastSuccessfulCatalogSync: Date?
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
    let providerRegionId: String?
    let canonicalRegionId: String?
    let countryCodes: [String]?
    let regionKind: MapRegionKind?
    let tags: [String]?
    let capabilities: [String]?
    let releaseMetadata: MapReleaseMetadata?
    let artifacts: [MapArtifact]?
}

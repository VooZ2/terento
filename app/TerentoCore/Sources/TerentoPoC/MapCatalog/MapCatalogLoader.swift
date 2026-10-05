import Foundation

enum MapCatalogSource: String, Sendable, Equatable {
    case remote
    case cachedRemote
    case bundledFallback
    /// The current remote catalog was reached but cannot be used by this app
    /// version. Maps stay browsable from the local catalog; installs wait for
    /// a Terento update. This is not a connection problem.
    case appUpdateRequired

    var userLabel: String {
        switch self {
        case .remote:
            return "Remote catalog"
        case .cachedRemote:
            return "Using the last checked catalog — status may be out of date"
        case .bundledFallback:
            return "Using local catalog — may be out of date"
        case .appUpdateRequired:
            return "Update Terento to install maps from the current catalog"
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
    /// Remote packages this app version could not accept. They are omitted;
    /// every other package remains available.
    var droppedPackageCount: Int = 0
}

/// Why the current remote catalog could not be used.
enum MapCatalogRemoteFailure: Error, Equatable, Sendable {
    /// No usable response (offline, timeout, HTTP error, non-JSON body).
    case unavailable
    /// A JSON catalog was received but this app version cannot use it
    /// (document shape, catalog invariants, or no compatible package).
    case incompatible
}

/// The current server catalog after per-package acceptance, before the
/// bundled supplement is merged. Only this catalog authorizes acquisition.
struct MapCatalogRemoteLoad: Sendable {
    let catalog: MapCatalog
    let droppedPackageIDs: Set<String>
    let droppedPackageCount: Int
}

private actor LatestRemoteMapCatalog {
    static let shared = LatestRemoteMapCatalog()
    var catalogs: [URL: MapCatalog] = [:]
    func save(_ catalog: MapCatalog, for endpoint: URL?) {
        if let endpoint { catalogs[endpoint] = catalog }
    }
    func load(for endpoint: URL?) -> MapCatalog? {
        endpoint.flatMap { catalogs[$0] }
    }
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
        return URLComponents(string: "https://api.terento.app/maps/catalog-v4.json")?.url
    }()

    let endpoint: URL?
    let contourRolloutPolicy: MapContourRolloutPolicy
    private let dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)

    init(
        endpoint: URL? = MapCatalogLoader.defaultEndpoint,
        contourRolloutPolicy: MapContourRolloutPolicy = .localDebugRC,
        dataLoader: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.endpoint = endpoint
        self.contourRolloutPolicy = contourRolloutPolicy
        self.dataLoader = dataLoader
    }

    /// Metadata is fetched from the future catalog service first. The local
    /// catalog is the safe fallback and may be stale; it never contains map
    /// binaries. Connect and the periodic refresh share this load path.
    func loadRemoteThenFallback() async throws -> MapCatalogLoadResult {
        do {
            return try await loadCurrentMerged()
        } catch {
            if Task.isCancelled { throw CancellationError() }
            let incompatible = (error as? MapCatalogRemoteFailure) == .incompatible
            if let catalog = await LatestRemoteMapCatalog.shared.load(for: endpoint) {
                return MapCatalogLoadResult(
                    catalog: incompatible ? catalog.withAppUpdateRequiredDownloadAvailability()
                        : catalog.withUnverifiedDownloadAvailability(),
                    source: incompatible ? .appUpdateRequired : .cachedRemote)
            }
            let bundled = try loadBundled()
            return MapCatalogLoadResult(
                catalog: incompatible ? bundled.withAppUpdateRequiredDownloadAvailability()
                    : bundled.withUnverifiedDownloadAvailability(),
                source: incompatible ? .appUpdateRequired : .bundledFallback
            )
        }
    }

    /// The current remote catalog, accepted per package and merged with the
    /// bundled supplement exactly like the connect-time load. Throws
    /// `MapCatalogRemoteFailure` without any fallback.
    func loadCurrentMerged() async throws -> MapCatalogLoadResult {
        let remote = try await loadAcceptedRemote()
        let bundledCatalog = try loadBundled()
        // The API may roll out provider records independently from the
        // app. Keep the remote catalog authoritative for records it knows
        // and add only missing bundled records so a provider rollout does
        // not make the app silently lose an enabled provider.
        let catalog = contourRolloutPolicy.applying(
            to: remote.catalog.mergingSupplemental(bundledCatalog)
        )
        await LatestRemoteMapCatalog.shared.save(catalog, for: endpoint)
        return MapCatalogLoadResult(catalog: catalog, source: .remote,
                                    droppedPackageCount: remote.droppedPackageCount)
    }

    /// Fetches the current server catalog and keeps every package this app
    /// version can validate. Incompatible packages are dropped one by one;
    /// only document shape and catalog-level invariants reject the whole
    /// catalog. Never merged with or replaced by bundled data.
    func loadAcceptedRemote() async throws -> MapCatalogRemoteLoad {
        let data: Data
        do {
            data = try await loadRemoteData()
        } catch {
            if Task.isCancelled || error is CancellationError { throw CancellationError() }
            throw MapCatalogRemoteFailure.unavailable
        }
        // A captive portal or proxy page is not evidence of an incompatible
        // catalog. Only a JSON object can be judged against this app version.
        guard (try? JSONSerialization.jsonObject(with: data)) is [String: Any] else {
            throw MapCatalogRemoteFailure.unavailable
        }
        let report: MapCatalogDecodeReport
        do {
            report = try MapCatalogDocumentDecoder().decodeTolerant(data)
        } catch {
            throw MapCatalogRemoteFailure.incompatible
        }
        guard let accepted = MapCatalogClientCompatibilityValidator().acceptCompatiblePackages(report.catalog) else {
            throw MapCatalogRemoteFailure.incompatible
        }
        return MapCatalogRemoteLoad(
            catalog: accepted.catalog,
            droppedPackageIDs: accepted.droppedPackageIDs.union(report.droppedPackageIDs),
            droppedPackageCount: accepted.droppedPackageIDs.count + report.droppedPackageCount
        )
    }

    /// Acquisition must use current server authorization, never a bundled
    /// fallback. Only the package being acquired (plus catalog invariants)
    /// must be compatible; unrelated incompatible packages do not block it.
    func validateCurrentAvailability(package: MapPackage) async throws {
        guard package.sourceKind == .provider else { return }
        let remote: MapCatalogRemoteLoad
        do {
            remote = try await loadAcceptedRemote()
        } catch MapCatalogRemoteFailure.incompatible {
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(package.providerId), reason: "APP_UPDATE_REQUIRED"))
        } catch {
            if Task.isCancelled || error is CancellationError { throw CancellationError() }
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(package.providerId), reason: "STATUS_UNVERIFIED"))
        }
        let catalog = contourRolloutPolicy.applying(to: remote.catalog)
        guard let current = catalog.packages.first(where: { $0.id == package.id }) else {
            if remote.droppedPackageIDs.contains(package.id) {
                throw MapAcquisitionError.acquisitionWithheld(.blocked(
                    provider: MapProviderDisplay.downloadName(package.providerId), reason: "APP_UPDATE_REQUIRED"))
            }
            throw MapAcquisitionError.invalidPackage("This map is no longer available. Refresh the catalog.")
        }
        guard !current.requiredMainArtifactUnavailable else {
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(current.providerId), reason: "PACKAGE_UNAVAILABLE"))
        }
        let availability = MapPackageAcquisitionPolicyResolver().availability(for: current)
        guard availability == .available else {
            throw MapAcquisitionError.acquisitionWithheld(availability)
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

        let (data, response) = try await dataLoader(request)
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

/// The packages of one remote catalog that this app version can use.
struct MapCatalogAcceptance: Sendable, Equatable {
    let catalog: MapCatalog
    let droppedPackageIDs: Set<String>
}

/// A release-bound semantic gate for remotely mutable map metadata. JSON can
/// be structurally valid while still naming an IMG identity that the current
/// app parser cannot recover. At runtime such a package is dropped on its own
/// (`acceptCompatiblePackages`); only catalog-level invariants reject the
/// whole document. Release gates keep the strict all-package `isCompatible`.
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

    /// Strict release gate: catalog invariants hold and every package is
    /// compatible with this app build.
    func isCompatible(_ catalog: MapCatalog) -> Bool {
        guard satisfiesCatalogInvariants(catalog), !catalog.packages.isEmpty else { return false }
        return duplicateBBBikeIdentityPackageIDs(catalog.packages).isEmpty
            && catalog.packages.allSatisfy(isPackageCompatible)
    }

    /// Unique non-empty provider IDs and package IDs, and every package owned
    /// by a listed provider. A violation makes the whole catalog unusable.
    func satisfiesCatalogInvariants(_ catalog: MapCatalog) -> Bool {
        let catalogProviderIDs = catalog.providers
            .map { MapIdentity.normalizeProvider($0.id) }
        let packageProviderIDs = catalog.packages
            .map { MapIdentity.normalizeProvider($0.providerId) }
        let packageIDs = catalog.packages.map(\.id)
        return !catalogProviderIDs.isEmpty
            && catalogProviderIDs.allSatisfy({ !$0.isEmpty })
            && Set(catalogProviderIDs).count == catalogProviderIDs.count
            && Set(packageProviderIDs).isSubset(of: Set(catalogProviderIDs))
            && packageIDs.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
            && Set(packageIDs).count == packageIDs.count
    }

    /// Keeps every compatible package and drops the rest individually. Each
    /// kept package passed the same provider adapter, reviewed source host,
    /// IMG identity and BBBike rules as before. Returns nil when catalog
    /// invariants fail or no package is compatible.
    func acceptCompatiblePackages(_ catalog: MapCatalog) -> MapCatalogAcceptance? {
        guard satisfiesCatalogInvariants(catalog) else { return nil }
        let duplicateIdentities = duplicateBBBikeIdentityPackageIDs(catalog.packages)
        let accepted = catalog.packages.filter {
            !duplicateIdentities.contains($0.id) && isPackageCompatible($0)
        }
        guard !accepted.isEmpty else { return nil }
        let dropped = Set(catalog.packages.map(\.id)).subtracting(accepted.map(\.id))
        guard !dropped.isEmpty else {
            return MapCatalogAcceptance(catalog: catalog, droppedPackageIDs: [])
        }
        let acceptedProviders = Set(accepted.map { MapIdentity.normalizeProvider($0.providerId) })
        let rawProviders = Set(catalog.packages.map { MapIdentity.normalizeProvider($0.providerId) })
        // A provider whose every package was dropped (for example one this
        // app version has no adapter for) is omitted; providers that never
        // listed packages keep their existing presentation.
        let providers = catalog.providers.filter { provider in
            let id = MapIdentity.normalizeProvider(provider.id)
            return acceptedProviders.contains(id) || !rawProviders.contains(id)
        }
        let regionKeys = Set(accepted.map {
            "\(MapIdentity.normalizeProvider($0.providerId)):\($0.regionId)"
        })
        let regions = catalog.regions.filter {
            regionKeys.contains("\(MapIdentity.normalizeProvider($0.providerId ?? "")):\($0.id)")
        }
        return MapCatalogAcceptance(
            catalog: MapCatalog(catalogVersion: catalog.catalogVersion, updatedAt: catalog.updatedAt,
                                providers: providers, regions: regions, packages: accepted),
            droppedPackageIDs: dropped
        )
    }

    /// Per-package security and identity checks (unchanged rules).
    func isPackageCompatible(_ package: MapPackage) -> Bool {
        if MapIdentity.normalizeProvider(package.providerId) == "bbbike",
           package.mainArtifact?.validationState == .unavailable {
            return BBBikeProviderAdapter.validIdentity(package)
                && package.artifacts.count == 1 && package.mainArtifact?.sourceProof == nil
        }
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

    /// Two BBBike packages claiming one IMG identity are ambiguous; neither
    /// can be installed safely.
    private func duplicateBBBikeIdentityPackageIDs(_ packages: [MapPackage]) -> Set<String> {
        let bbbike = packages.filter { MapIdentity.normalizeProvider($0.providerId) == "bbbike" }
        let grouped = Dictionary(grouping: bbbike.compactMap { package in
            package.identity.map { ($0, package.id) }
        }, by: \.0)
        return Set(grouped.values.filter { $0.count > 1 }.flatMap { $0.map(\.1) })
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
            provider == "bbbike" ? package.canonicalRegionId : package.providerRegionId,
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

/// A tolerant decode result: packages that could not be decoded (for
/// example a required artifact of a kind this app does not know) are omitted
/// and counted instead of failing the document.
struct MapCatalogDecodeReport: Sendable {
    let catalog: MapCatalog
    let droppedPackageIDs: Set<String>
    let droppedPackageCount: Int
}

private extension CodingUserInfoKey {
    static let terentoTolerantCatalog = CodingUserInfoKey(rawValue: "terento.tolerantCatalog")!
}

struct MapCatalogDocumentDecoder: Sendable {
    /// Strict decode used for the bundled catalog and release gates: any
    /// malformed package or unknown artifact kind fails the whole document.
    func decode(_ data: Data) throws -> MapCatalog {
        try decodeReport(data, tolerant: false).catalog
    }

    /// Runtime remote decode. Document-level fields stay strict; a package
    /// that cannot be decoded is dropped and counted. An optional artifact of
    /// an unknown kind is ignored; a required one drops its package.
    func decodeTolerant(_ data: Data) throws -> MapCatalogDecodeReport {
        try decodeReport(data, tolerant: true)
    }

    private func decodeReport(_ data: Data, tolerant: Bool) throws -> MapCatalogDecodeReport {
        do {
            let decoder = JSONDecoder()
            decoder.userInfo[.terentoTolerantCatalog] = tolerant
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
            let dropped = document.providers.flatMap(\.maps.droppedPackageIDs)
            return MapCatalogDecodeReport(
                catalog: try document.catalog(),
                droppedPackageIDs: Set(dropped.compactMap { $0 }),
                droppedPackageCount: dropped.count
            )
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
                lastSuccessfulCatalogSync: providerDocument.lastSuccessfulCatalogSync,
                downloadBlockReason: providerDocument.downloadBlockReason
            )
            providers.append(
                provider
            )

            for map in providerDocument.maps.documents {
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
                        mapType: map.mapType,
                        geographicRegionId: map.geographicRegionId,
                        countryCodes: map.countryCodes ?? map.country.map { [$0] } ?? [],
                        regionKind: map.regionKind ?? .country,
                        tags: map.tags ?? [],
                        capabilities: map.capabilities ?? [],
                        releaseMetadata: map.releaseMetadata,
                        artifacts: map.artifacts?.artifacts,
                        downloadBlockReason: map.downloadBlockReason ?? provider.downloadBlockReason
                            ?? (provider.lifecycleStatus != .active ? "PROVIDER_PAUSED" : nil)
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
                if $0.id != $1.id { return $0.id < $1.id }
                // Distinct providers can share both geographic name and region ID.
                // Complete the order before dictionary iteration reaches the UI.
                return ($0.providerId ?? "") < ($1.providerId ?? "")
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
    let downloadBlockReason: String?
    let maps: MapDocumentList
}

/// Strict mode decodes every map document. Tolerant mode keeps decodable
/// documents and records the (possibly unknown) ID of each dropped one.
private struct MapDocumentList: Decodable {
    let documents: [MapDocument]
    let droppedPackageIDs: [String?]

    private struct Element: Decodable {
        let document: MapDocument?
        let id: String?
        private enum IDKey: String, CodingKey { case id }
        init(from decoder: Decoder) throws {
            document = try? MapDocument(from: decoder)
            id = try? decoder.container(keyedBy: IDKey.self).decode(String.self, forKey: .id)
        }
    }

    init(from decoder: Decoder) throws {
        guard decoder.userInfo[.terentoTolerantCatalog] as? Bool == true else {
            documents = try [MapDocument](from: decoder)
            droppedPackageIDs = []
            return
        }
        let elements = try [Element](from: decoder)
        documents = elements.compactMap(\.document)
        droppedPackageIDs = elements.filter { $0.document == nil }.map(\.id)
    }
}

/// Unknown artifact kinds are a forward-compatible extension. Tolerant mode
/// ignores an optional unknown artifact and rejects (drops) a package whose
/// unknown artifact is required. Strict mode keeps the original failure.
private struct MapArtifactList: Decodable {
    let artifacts: [MapArtifact]

    private struct KindProbe: Decodable {
        let kind: String?
        let required: Bool?
    }

    private enum Element: Decodable {
        case artifact(MapArtifact)
        case ignoredUnknownKind

        init(from decoder: Decoder) throws {
            do {
                self = .artifact(try MapArtifact(from: decoder))
            } catch {
                let probe = try KindProbe(from: decoder)
                let kind = probe.kind?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                guard let kind, MapArtifactKind(rawValue: kind) == nil, probe.required == false else {
                    throw error
                }
                self = .ignoredUnknownKind
            }
        }
    }

    init(from decoder: Decoder) throws {
        guard decoder.userInfo[.terentoTolerantCatalog] as? Bool == true else {
            artifacts = try [MapArtifact](from: decoder)
            return
        }
        artifacts = try [Element](from: decoder).compactMap {
            if case let .artifact(artifact) = $0 { return artifact }
            return nil
        }
    }
}

private struct MapDocument: Decodable {
    let downloadBlockReason: String?
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
    let mapType: String?
    let geographicRegionId: String?
    let countryCodes: [String]?
    let regionKind: MapRegionKind?
    let tags: [String]?
    let capabilities: [String]?
    let releaseMetadata: MapReleaseMetadata?
    let artifacts: MapArtifactList?
}

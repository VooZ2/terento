import Compression
import CryptoKit
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

/// TERENTO_USE_BUNDLED_MAP_CATALOG=1 (or Info.plist TerentoUseBundledMapCatalog)
/// starts with only the bundled catalog. Builds whose TerentoReleaseLabel ends
/// in "-local" honour it, App Store configuration included (the owner's local
/// test build), decided at run time from the label; DMG Debug builds honour
/// it too. A stable App Store or TestFlight build never has a "-local" label,
/// so it ignores the switch.
enum MapCatalogTestSwitch {
    static let environmentKey = "TERENTO_USE_BUNDLED_MAP_CATALOG"
    static let infoKey = "TerentoUseBundledMapCatalog"

    static func isAllowed(isDebug: Bool, isAppStore: Bool, releaseLabel: String?) -> Bool {
        let isLocalTestLabel = releaseLabel?.trimmingCharacters(in: .whitespacesAndNewlines)
            .hasSuffix("-local") ?? false
        return isLocalTestLabel || (isDebug && !isAppStore)
    }

    static func isRequested(environment: [String: String], infoValue: Any?) -> Bool {
        infoValue as? Bool == true || environment[environmentKey] == "1"
    }

    /// A "-local" test build (any configuration) or a DMG Debug build.
    static var currentBuildAllowsLocalTesting: Bool {
        #if DEBUG
        let isDebug = true
        #else
        let isDebug = false
        #endif
        #if TERENTO_APP_STORE
        let isAppStore = true
        #else
        let isAppStore = false
        #endif
        return isAllowed(isDebug: isDebug, isAppStore: isAppStore,
            releaseLabel: Bundle.main.object(forInfoDictionaryKey: "TerentoReleaseLabel") as? String)
    }

    static var usesBundledCatalog: Bool {
        currentBuildAllowsLocalTesting
            && isRequested(environment: ProcessInfo.processInfo.environment,
                infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey))
    }
}

/// When the catalog itself is the cause, the page says so once and rows and
/// provider groups drop the reason every map shares.
extension MapCatalogSource {
    static let catalogUnavailableNotice = "Couldn't load the map list. Maps can't be installed right now."

    /// Install maps: the one notice under the subtitle.
    var installNotice: String? {
        switch self {
        case .remote: return nil
        case .bundledFallback: return Self.catalogUnavailableNotice
        case .cachedRemote, .appUpdateRequired: return userLabel
        }
    }

    /// Manage maps: the one notice under the "N maps" count line.
    var manageNotice: String? {
        switch self {
        case .remote: return nil
        case .bundledFallback, .cachedRemote: return MapAcquisitionAvailability.availabilityCheckFailedNotice
        case .appUpdateRequired: return userLabel
        }
    }

    /// The block reason every package carries because of this source.
    var sharedBlockReason: String? {
        switch self {
        case .remote: return nil
        case .bundledFallback, .cachedRemote: return "STATUS_UNVERIFIED"
        case .appUpdateRequired: return "APP_UPDATE_REQUIRED"
        }
    }

    /// True when this map is blocked only for the reason the whole catalog shares.
    func isShared(_ availability: MapAcquisitionAvailability) -> Bool {
        guard let sharedBlockReason, let reason = availability.blockReason else { return false }
        return reason == sharedBlockReason
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
        // A local test build can pin its bundled catalog (no remote catalog),
        // so the "Couldn't load the map list" notice can be checked live.
        if MapCatalogTestSwitch.usesBundledCatalog {
            return nil
        }
        var components = URLComponents(string: "https://api.terento.app/maps/catalog-v6.json")
        // The server leaves a never-activated provider out of the catalog;
        // a Debug hardware test names it to see it (still PAUSED there).
        if let preview = MapCatalogDebugUnpause.previewQuery(MapCatalogDebugUnpause.providerIDs) {
            components?.queryItems = [URLQueryItem(name: "preview", value: preview)]
        }
        return components?.url
    }()

    let endpoint: URL?
    let contourRolloutPolicy: MapContourRolloutPolicy
    private let dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)
    private let tmzCatalogLoader: (@Sendable () async -> MapCatalog?)?

    init(
        endpoint: URL? = MapCatalogLoader.defaultEndpoint,
        contourRolloutPolicy: MapContourRolloutPolicy = .localDebugRC,
        dataLoader: (@Sendable (URLRequest) async throws -> (Data, URLResponse))? = nil,
        tmzCatalogLoader: (@Sendable () async -> MapCatalog?)? = nil
    ) {
        self.endpoint = endpoint
        self.contourRolloutPolicy = contourRolloutPolicy
        self.dataLoader = dataLoader ?? { request in
            try await URLSession.shared.data(for: request)
        }
        if let tmzCatalogLoader {
            self.tmzCatalogLoader = tmzCatalogLoader
        } else if dataLoader == nil && !MapCatalogTestSwitch.usesBundledCatalog {
            self.tmzCatalogLoader = { await TMZLiveCatalogResolver().loadCatalog() }
        } else {
            self.tmzCatalogLoader = nil
        }
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
        var merged = remote.catalog.mergingSupplemental(bundledCatalog)
        if !merged.providers.contains(where: { MapIdentity.normalizeProvider($0.id) == "tmz" }),
           let tmzCatalogLoader,
           let liveTMZ = await tmzCatalogLoader() {
            merged = merged.mergingSupplemental(liveTMZ)
        }
        let catalog = contourRolloutPolicy.applying(to: merged)
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
        let isTMZ = MapIdentity.normalizeProvider(package.providerId) == "tmz"
        let remote: MapCatalogRemoteLoad
        do {
            remote = try await loadAcceptedRemote()
        } catch MapCatalogRemoteFailure.incompatible {
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(package.providerId), reason: "APP_UPDATE_REQUIRED"))
        } catch {
            if Task.isCancelled || error is CancellationError { throw CancellationError() }
            if isTMZ, let tmzCatalogLoader {
                try await validateLiveTMZAvailability(package: package, loader: tmzCatalogLoader)
                return
            }
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(package.providerId), reason: "STATUS_UNVERIFIED"))
        }
        let catalog = contourRolloutPolicy.applying(to: remote.catalog)
        guard let current = catalog.packages.first(where: { $0.id == package.id }) else {
            if isTMZ, !remote.droppedPackageIDs.contains(package.id), let tmzCatalogLoader {
                try await validateLiveTMZAvailability(package: package, loader: tmzCatalogLoader)
                return
            }
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

    private func validateLiveTMZAvailability(
        package: MapPackage,
        loader: @Sendable () async -> MapCatalog?
    ) async throws {
        guard let liveCatalog = await loader() else {
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(package.providerId), reason: "STATUS_UNVERIFIED"))
        }
        guard let current = liveCatalog.packages.first(where: { $0.id == package.id }) else {
            throw MapAcquisitionError.invalidPackage("This map is no longer available. Refresh the catalog.")
        }
        guard MapCatalogClientCompatibilityValidator().isPackageCompatible(current),
              !current.requiredMainArtifactUnavailable else {
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(current.providerId), reason: "PACKAGE_UNAVAILABLE"))
        }
        if let expectedProof = package.mainArtifact?.tmzSourceProof,
           let liveProof = current.mainArtifact?.tmzSourceProof,
           expectedProof != liveProof {
            throw MapAcquisitionError.providerSourceUpdated(providerId: "tmz")
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
            && LuckyMapsProviderAdapter.duplicateFamilyPackageIDs(catalog.packages).isEmpty
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
            .union(LuckyMapsProviderAdapter.duplicateFamilyPackageIDs(catalog.packages))
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
                && package.artifacts.count == 1 && package.mainArtifact?.carriesSourceProof == false
        }
        if MapIdentity.normalizeProvider(package.providerId) == "osmapa",
           package.mainArtifact?.validationState == .unavailable {
            return OSMapaProviderAdapter.validIdentity(package) && package.artifacts.count == 1
                && package.mainArtifact?.carriesSourceProof == false
        }
        if MapIdentity.normalizeProvider(package.providerId) == "luckymaps",
           package.mainArtifact?.validationState == .unavailable {
            return LuckyMapsProviderAdapter.validIdentity(package) && package.artifacts.count == 1
                && package.mainArtifact?.carriesSourceProof == false
                && package.mainArtifact?.sourceURL.flatMap(LuckyMapsProviderAdapter.reviewedSource) == package.providerRegionId
        }
        if MapIdentity.normalizeProvider(package.providerId) == "openfietsmap",
           package.mainArtifact?.validationState == .unavailable {
            return OpenFietsMapProviderAdapter.validIdentity(package) && package.artifacts.count == 1
                && package.mainArtifact?.carriesSourceProof == false
                && package.mainArtifact?.sourceURL.flatMap(OpenFietsMapProviderAdapter.reviewedSource)?.key == package.providerRegionId
        }
        if MapIdentity.normalizeProvider(package.providerId) == "tmz",
           package.mainArtifact?.validationState == .unavailable {
            return TMZProviderAdapter.validIdentity(package) && package.artifacts.count == 1
                && package.mainArtifact?.carriesSourceProof == false
                && package.mainArtifact?.sourceURL.flatMap(TMZProviderAdapter.reviewedSource)?.variant.key == package.providerRegionId
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

    /// Two BBBike, OSMapaPL, Lucky Maps, OpenFietsMap or T-MZ packages claiming
    /// one IMG identity are ambiguous; neither can be installed safely.
    private func duplicateBBBikeIdentityPackageIDs(_ packages: [MapPackage]) -> Set<String> {
        let bbbike = packages.filter { ["bbbike", "osmapa", "luckymaps", "openfietsmap", "tmz"].contains(MapIdentity.normalizeProvider($0.providerId)) }
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
    var unpausedProviderIDs: Set<String> = MapCatalogDebugUnpause.providerIDs

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
                catalog: try document.catalog(unpausedProviderIDs: unpausedProviderIDs),
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

/// Local hardware testing of a provider the server still holds PAUSED: a
/// "-local" test build (App Store configuration included) or a DMG Debug
/// build run with TERENTO_DEBUG_UNPAUSE_PROVIDERS=<id,...> treats that
/// provider as active. Only the PROVIDER_PAUSED reason is lifted; region,
/// package and authorization checks stay. A stable App Store, TestFlight or
/// DMG build never reads it (same run-time rule as MapCatalogTestSwitch).
enum MapCatalogDebugUnpause {
    static let providerIDs: Set<String> = MapCatalogTestSwitch.currentBuildAllowsLocalTesting
        ? parse(ProcessInfo.processInfo.environment["TERENTO_DEBUG_UNPAUSE_PROVIDERS"]) : []

    /// `nil` when no provider is named, which is always so in stable builds.
    static func previewQuery(_ ids: Set<String>) -> String? {
        ids.isEmpty ? nil : ids.sorted().joined(separator: ",")
    }

    static func parse(_ value: String?) -> Set<String> {
        Set((value ?? "").split(separator: ",")
            .map { MapIdentity.normalizeProvider(String($0)) }
            .filter { !$0.isEmpty })
    }
}

private struct MapCatalogDocument: Decodable {
    let catalogVersion: Int
    let updatedAt: Date
    let providers: [ProviderDocument]

    func catalog(unpausedProviderIDs: Set<String>) throws -> MapCatalog {
        guard catalogVersion > 0 else {
            throw MapCatalogError.invalidMetadata("catalogVersion must be positive")
        }

        var providers: [MapProvider] = []
        var regionsByID: [String: MapRegion] = [:]
        var packages: [MapPackage] = []

        for providerDocument in self.providers {
            let serverLifecycleStatus = MapProviderLifecycleStatus(apiValue: providerDocument.status)
            let unpaused = serverLifecycleStatus == .paused && unpausedProviderIDs
                .contains(MapIdentity.normalizeProvider(providerDocument.id))
            let lifecycleStatus = unpaused ? .active : serverLifecycleStatus
            func blockReason(_ reason: String?) -> String? {
                unpaused && reason == "PROVIDER_PAUSED" ? nil : reason
            }
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
                downloadBlockReason: blockReason(providerDocument.downloadBlockReason)
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
                        downloadBlockReason: blockReason(map.downloadBlockReason) ?? provider.downloadBlockReason
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

/// Discovers the latest T-MZ Japan OSM cycling maps directly from
/// `https://tmz.skr.jp/data/gmap.html` and measures each ZIP with two bounded
/// 64 KiB HTTP Range GETs (central directory + IMG header) without downloading
/// the full archive. Transient network and 5xx/429 responses are retried.
struct TMZLiveCatalogResolver: Sendable {
    static let maximumIndexBytes = 1024 * 1024
    static let probeBytes: UInt64 = 65_536
    static let imgInspectBytes = 8 * 1024
    static let defaultRetryDelays: [TimeInterval] = [1, 2]

    private let indexURL: URL
    private let dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)
    private let retryDelays: [TimeInterval]
    private let sleep: @Sendable (TimeInterval) async throws -> Void

    init(
        indexURL: URL = TMZProviderAdapter.indexURL,
        dataLoader: (@Sendable (URLRequest) async throws -> (Data, URLResponse))? = nil,
        retryDelays: [TimeInterval] = TMZLiveCatalogResolver.defaultRetryDelays,
        sleep: @escaping @Sendable (TimeInterval) async throws -> Void = { seconds in
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        }
    ) {
        self.indexURL = indexURL
        self.dataLoader = dataLoader ?? Self.noRedirectDataLoader
        self.retryDelays = retryDelays
        self.sleep = sleep
    }

    /// Resolves the latest T-MZ packages into a `MapCatalog`, or returns `nil`
    /// if the source cannot be reached or validated right now.
    func loadCatalog(now: Date = Date()) async -> MapCatalog? {
        try? await loadCatalogThrowing(now: now)
    }

    func loadCatalogThrowing(now: Date = Date()) async throws -> MapCatalog {
        let html = try await fetchIndex()
        guard let latest = Self.discoverLatestSources(inHTML: html, baseURL: indexURL),
              !latest.isEmpty else {
            throw MapCatalogError.invalidMetadata("No reviewed T-MZ links found in index HTML")
        }

        var packages: [MapPackage] = []
        var regions: [MapRegion] = []
        var lastError: Error?
        for variant in TMZVariant.allCases {
            guard let source = latest[variant] else { continue }
            do {
                let package = try await probePackage(for: source)
                packages.append(package)
                regions.append(MapRegion(
                    id: package.regionId,
                    name: package.name,
                    country: "Japan",
                    providerId: "tmz"
                ))
            } catch {
                lastError = error
            }
        }
        guard !packages.isEmpty else {
            throw lastError ?? MapCatalogError.remoteUnavailable
        }

        let provider = MapProvider(
            id: "tmz",
            name: "T-MZ",
            website: TMZProviderAdapter.websiteURL,
            attribution: "Map data © OpenStreetMap contributors; Garmin Japan map by T-MZ",
            licenseURL: TMZProviderAdapter.licenseURL,
            licenseInformation: "Map data © OpenStreetMap contributors (ODbL 1.0); Garmin Japan map compiled by T-MZ.",
            lifecycleStatus: .active,
            health: .healthy,
            lastCheckedAt: now,
            lastSuccessfulCatalogSync: now
        )
        return MapCatalog(
            catalogVersion: 1,
            updatedAt: now,
            providers: [provider],
            regions: regions,
            packages: packages
        )
    }

    /// Parses the T-MZ HTML download table, stripping HTML comments, and returns
    /// the newest valid release for each variant (with and without contours).
    static func discoverLatestSources(inHTML html: String, baseURL: URL = TMZProviderAdapter.indexURL) -> [TMZVariant: TMZSource]? {
        let withoutComments = html.replacingOccurrences(
            of: #"<!--[\s\S]*?-->"#,
            with: "",
            options: .regularExpression
        )
        guard let regex = try? NSRegularExpression(
            pattern: #"href\s*=\s*["']([^"']*gmapsupp_[0-9]{6}(?:cntr)?\.zip)["']"#,
            options: [.caseInsensitive]
        ) else { return nil }

        var newest: [TMZVariant: TMZSource] = [:]
        let matches = regex.matches(
            in: withoutComments,
            range: NSRange(withoutComments.startIndex..., in: withoutComments)
        )
        for match in matches {
            guard let hrefRange = Range(match.range(at: 1), in: withoutComments) else { continue }
            let href = String(withoutComments[hrefRange]).trimmingCharacters(in: .whitespacesAndNewlines)
            guard let resolved = URL(string: href, relativeTo: baseURL)?.absoluteURL,
                  let source = TMZProviderAdapter.reviewedSource(resolved) else { continue }
            if let existing = newest[source.variant] {
                if existing.publishedDate < source.publishedDate {
                    newest[source.variant] = source
                }
            } else {
                newest[source.variant] = source
            }
        }
        return newest.isEmpty ? nil : newest
    }

    static func decodeHTML(_ data: Data) -> String? {
        if let decoded = String(data: data, encoding: .shiftJIS) { return decoded }
        let cp932 = String.Encoding(
            rawValue: CFStringConvertEncodingToNSStringEncoding(
                CFStringEncoding(CFStringEncodings.dosJapanese.rawValue)
            )
        )
        if let decoded = String(data: data, encoding: cp932) { return decoded }
        if let decoded = String(data: data, encoding: .utf8) { return decoded }
        return String(data: data, encoding: .isoLatin1)
    }

    private func fetchIndex() async throws -> String {
        var request = URLRequest(url: indexURL)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 15
        request.setValue("Terento/1.3 (+https://terento.app)", forHTTPHeaderField: "User-Agent")

        let (data, http) = try await fetchWithRetry(request: request)
        guard http.statusCode == 200,
              http.url == indexURL,
              !data.isEmpty,
              data.count <= Self.maximumIndexBytes,
              let html = Self.decodeHTML(data) else {
            throw MapCatalogError.remoteUnavailable
        }
        return html
    }

    private func probePackage(for source: TMZSource) async throws -> MapPackage {
        // 1. Fetch ZIP tail (last 64 KiB) to inspect EOCD and central directory.
        let tail = try await fetchRange(url: source.url, rangeHeader: "bytes=-\(Self.probeBytes)")
        let total = tail.total
        guard total >= 22,
              tail.start == (total > Self.probeBytes ? total - Self.probeBytes : 0),
              tail.end == total - 1 else {
            throw MapCatalogError.invalidMetadata("T-MZ tail Content-Range mismatch")
        }

        let central = try Self.parseCentralDirectory(tailBytes: tail.bytes, tailStart: tail.start, totalSize: total)

        // 2. Fetch ZIP head at `gmapsupp.img`'s local header and inflate first 8 KiB.
        let headEnd = min(total - 1, central.localOffset + Self.probeBytes - 1)
        let head = try await fetchRange(url: source.url, rangeHeader: "bytes=\(central.localOffset)-\(headEnd)")
        guard head.total == total,
              head.etag == tail.etag,
              head.start == central.localOffset,
              head.end == headEnd else {
            throw MapCatalogError.invalidMetadata("T-MZ head Content-Range or ETag mismatch")
        }

        let imgPrefix = try Self.extractIMGHeader(headBytes: head.bytes, entry: central)
        guard let title = TMZIMGMetadata.title(imgPrefix),
              title == source.variant.imgTitle,
              let buildVersion = OSMapaIMGMetadata.version(imgPrefix),
              buildVersion.day != nil,
              TMZProviderAdapter.releaseMatches(buildVersion, source: source),
              OSMapaIMGMetadata.mdrFamilyIDs(imgPrefix) == [TMZProviderAdapter.familyID],
              TMZIMGMetadata.hasTMZTYP(imgPrefix) else {
            throw MapCatalogError.invalidMetadata("T-MZ IMG header verification failed")
        }

        let crcHex = String(format: "%08x", central.crc32)
        let generatedAt = "\(buildVersion.description)T00:00:00Z"
        let revisionInput = [
            "tmz", source.variant.key, source.url.absoluteString,
            tail.etag, tail.lastModified, String(total), String(central.unpackedSize),
            crcHex, buildVersion.description, title
        ].joined(separator: "|")
        let revision = SHA256.hash(data: Data(revisionInput.utf8))
            .map { String(format: "%02x", $0) }
            .joined()

        let proof = TMZSourceProof(
            sourceURL: source.url,
            etag: tail.etag,
            lastModified: tail.lastModified,
            downloadSizeBytes: total,
            installSizeBytes: central.unpackedSize,
            payloadPath: "gmapsupp.img",
            crc32: crcHex,
            sourceIdentity: "tmz:\(source.variant.key)",
            variant: source.variant.key,
            mapType: source.variant.mapType,
            familyId: TMZProviderAdapter.familyID,
            imgTitle: title,
            publishedDate: source.publishedDate.description,
            generatedAt: generatedAt,
            headerIdentityValidated: true,
            revision: revision
        )

        let packageID = "tmz-\(source.variant.key)"
        let canonicalRegion = source.variant.key.uppercased()
        let releaseMetadata = MapReleaseMetadata(
            releaseId: buildVersion.description,
            versionLabel: buildVersion.description,
            generatedAt: generatedAt,
            sourceUpdatedAt: source.publishedDate.description
        )
        let artifact = MapArtifact(
            id: "\(packageID)-main",
            source: .provider,
            kind: .main,
            required: true,
            providerId: "tmz",
            providerRegionId: source.variant.key,
            canonicalRegionId: canonicalRegion,
            version: buildVersion,
            releaseMetadata: releaseMetadata,
            sourceURL: source.url,
            sizeBytes: central.unpackedSize,
            downloadSizeBytes: total,
            checksum: nil,
            validationState: .validated,
            tmzSourceProof: proof
        )
        let package = MapPackage(
            id: packageID,
            providerId: "tmz",
            regionId: canonicalRegion,
            name: source.variant.displayName,
            version: buildVersion,
            sizeBytes: total,
            sourceURL: source.url,
            releaseDate: buildVersion.description,
            identifier: source.variant.key,
            downloadSizeBytes: total,
            installSizeBytes: central.unpackedSize,
            providerRegionId: source.variant.key,
            canonicalRegionId: canonicalRegion,
            mapType: source.variant.mapType,
            geographicRegionId: "JP",
            countryCodes: ["JP"],
            regionKind: .country,
            tags: [source.variant.mapType, "cycling", "japan"],
            capabilities: ["main"],
            releaseMetadata: releaseMetadata,
            artifacts: [artifact]
        )
        guard TMZProviderAdapter().expectedIMGIdentity(for: package) != nil else {
            throw MapCatalogError.invalidMetadata("T-MZ synthesized package failed self-validation")
        }
        return package
    }

    private struct RangeProbeResult {
        let bytes: [UInt8]
        let start: UInt64
        let end: UInt64
        let total: UInt64
        let etag: String
        let lastModified: String
    }

    private func fetchRange(url: URL, rangeHeader: String) async throws -> RangeProbeResult {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 20
        request.setValue(rangeHeader, forHTTPHeaderField: "Range")
        request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")
        request.setValue("Terento/1.3 (+https://terento.app)", forHTTPHeaderField: "User-Agent")

        let (data, http) = try await fetchWithRetry(request: request)
        guard http.statusCode == 206,
              http.url == url,
              let etag = http.value(forHTTPHeaderField: "ETag")?.trimmingCharacters(in: .whitespacesAndNewlines),
              etag.hasPrefix("\""), etag.hasSuffix("\""), etag.count > 2,
              let lastModified = http.value(forHTTPHeaderField: "Last-Modified")?.trimmingCharacters(in: .whitespacesAndNewlines),
              !lastModified.isEmpty,
              let contentRange = http.value(forHTTPHeaderField: "Content-Range"),
              let parsed = Self.parseContentRange(contentRange),
              parsed.end >= parsed.start,
              parsed.total > parsed.end,
              UInt64(data.count) == parsed.end - parsed.start + 1 else {
            throw MapCatalogError.remoteUnavailable
        }
        return RangeProbeResult(
            bytes: [UInt8](data), start: parsed.start, end: parsed.end, total: parsed.total,
            etag: etag, lastModified: lastModified
        )
    }

    private func fetchWithRetry(request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        var remaining = retryDelays[...]
        while true {
            do {
                let (data, response) = try await dataLoader(request)
                guard let http = response as? HTTPURLResponse else {
                    throw MapCatalogError.remoteUnavailable
                }
                if [429, 500, 502, 503, 504].contains(http.statusCode), let delay = remaining.popFirst() {
                    try await sleep(delay)
                    continue
                }
                return (data, http)
            } catch let error as URLError where FoundationMapPackageDownloadClient.isRetryableConnectionFailure(error) {
                guard let delay = remaining.popFirst() else { throw error }
                try await sleep(delay)
            }
        }
    }

    private static func parseContentRange(_ header: String) -> (start: UInt64, end: UInt64, total: UInt64)? {
        let trimmed = header.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("bytes ") else { return nil }
        let parts = trimmed.dropFirst(6).split(separator: "/", omittingEmptySubsequences: false)
        guard parts.count == 2, let total = UInt64(parts[1]) else { return nil }
        let bounds = parts[0].split(separator: "-", omittingEmptySubsequences: false)
        guard bounds.count == 2, let start = UInt64(bounds[0]), let end = UInt64(bounds[1]) else { return nil }
        return (start, end, total)
    }

    private struct CentralEntry {
        let flags: UInt64
        let crc32: UInt32
        let packedSize: UInt64
        let unpackedSize: UInt64
        let localOffset: UInt64
    }

    private static func number(_ bytes: [UInt8], _ offset: Int, _ count: Int) throws -> UInt64 {
        guard offset >= 0, count <= 8, offset <= bytes.count, count <= bytes.count - offset else {
            throw MapCatalogError.invalidMetadata("Out-of-bounds ZIP read")
        }
        return (0..<count).reduce(UInt64(0)) { $0 | UInt64(bytes[offset + $1]) << ($1 * 8) }
    }

    private static func requireSafeExtraFields(_ extra: [UInt8]) throws {
        var cursor = 0
        while cursor < extra.count {
            let tag = try number(extra, cursor, 2)
            let length = Int(try number(extra, cursor + 2, 2))
            guard tag != 0x0001, tag != 0x9901, cursor + 4 + length <= extra.count else {
                throw MapCatalogError.invalidMetadata("Unsupported ZIP extra field")
            }
            cursor += 4 + length
        }
    }

    private static func parseCentralDirectory(tailBytes: [UInt8], tailStart: UInt64, totalSize: UInt64) throws -> CentralEntry {
        guard tailBytes.count >= 22 else { throw MapCatalogError.invalidMetadata("ZIP too small") }
        let eocdOffset = tailBytes.count - 22
        let entries = try number(tailBytes, eocdOffset + 10, 2)
        guard try number(tailBytes, eocdOffset, 4) == 0x06054b50,
              try number(tailBytes, eocdOffset + 4, 4) == 0,
              try number(tailBytes, eocdOffset + 8, 2) == entries,
              entries >= 1, entries <= UInt64(TMZArchiveSafety.maximumEntries),
              try number(tailBytes, eocdOffset + 20, 2) == 0 else {
            throw MapCatalogError.invalidMetadata("Invalid ZIP EOCD")
        }
        let centralSize = try number(tailBytes, eocdOffset + 12, 4)
        let centralOffset = try number(tailBytes, eocdOffset + 16, 4)
        guard centralSize <= 65_535,
              centralOffset + centralSize == totalSize - 22,
              centralOffset >= tailStart else {
            throw MapCatalogError.invalidMetadata("Central directory outside tail probe")
        }
        let localStart = Int(centralOffset - tailStart)
        let localEnd = localStart + Int(centralSize)
        guard localEnd <= tailBytes.count else { throw MapCatalogError.invalidMetadata("Truncated central directory") }
        let central = Array(tailBytes[localStart..<localEnd])

        var cursor = 0
        var payloadEntry: CentralEntry?
        var seenNames = Set<String>()
        for _ in 0..<entries {
            guard try number(central, cursor, 4) == 0x02014b50 else {
                throw MapCatalogError.invalidMetadata("Invalid central directory signature")
            }
            let flags = try number(central, cursor + 8, 2)
            let method = try number(central, cursor + 10, 2)
            let entryCRC = try number(central, cursor + 16, 4)
            let packed = try number(central, cursor + 20, 4)
            let unpacked = try number(central, cursor + 24, 4)
            let nameLength = Int(try number(central, cursor + 28, 2))
            let extraLength = Int(try number(central, cursor + 30, 2))
            let commentLength = Int(try number(central, cursor + 32, 2))
            let mode = try number(central, cursor + 38, 4) >> 16
            let localOffset = try number(central, cursor + 42, 4)
            let end = cursor + 46 + nameLength + extraLength + commentLength
            guard end <= central.count, nameLength > 0, commentLength == 0,
                  try number(central, cursor + 34, 2) == 0 else {
                throw MapCatalogError.invalidMetadata("Malformed central directory entry")
            }
            let name = Array(central[(cursor + 46)..<(cursor + 46 + nameLength)])
            try requireSafeExtraFields(Array(central[(cursor + 46 + nameLength)..<(cursor + 46 + nameLength + extraLength)]))
            guard let text = String(bytes: name, encoding: .ascii),
                  flags & 0x0041 == 0,
                  !text.contains("/"), !text.contains("\\"), text != "..", text != ".",
                  (mode & 0xf000 == 0 || mode & 0xf000 == 0x8000),
                  seenNames.insert(text.lowercased()).inserted,
                  localOffset < centralOffset else {
                throw MapCatalogError.invalidMetadata("Unsafe ZIP entry")
            }
            if text == "gmapsupp.img" {
                guard payloadEntry == nil, method == 8,
                      unpacked >= 0x1000, unpacked <= TMZProviderAdapter.maximumIMGBytes else {
                    throw MapCatalogError.invalidMetadata("Invalid gmapsupp.img entry")
                }
                payloadEntry = CentralEntry(
                    flags: flags, crc32: UInt32(entryCRC), packedSize: packed,
                    unpackedSize: unpacked, localOffset: localOffset
                )
            } else if text == "gmapsupp_search.img" {
                guard (method == 8 || method == 0), unpacked <= TMZArchiveSafety.maximumSearchIMGBytes else {
                    throw MapCatalogError.invalidMetadata("Invalid gmapsupp_search.img entry")
                }
            } else {
                guard text.range(of: TMZArchiveSafety.licensePattern, options: [.regularExpression, .caseInsensitive]) != nil,
                      unpacked <= TMZArchiveSafety.maximumLicenseBytes else {
                    throw MapCatalogError.invalidMetadata("Unexpected side file in T-MZ ZIP")
                }
            }
            cursor = end
        }
        guard cursor == central.count, let entry = payloadEntry else {
            throw MapCatalogError.invalidMetadata("Missing gmapsupp.img in T-MZ ZIP")
        }
        return entry
    }

    private static func extractIMGHeader(headBytes: [UInt8], entry: CentralEntry) throws -> [UInt8] {
        let expectedName = Array("gmapsupp.img".utf8)
        let headerFixed = 30 + expectedName.count
        guard headBytes.count > headerFixed,
              try number(headBytes, 0, 4) == 0x04034b50,
              try number(headBytes, 6, 2) == entry.flags,
              try number(headBytes, 8, 2) == 8,
              try number(headBytes, 26, 2) == UInt64(expectedName.count),
              Array(headBytes[30..<headerFixed]) == expectedName else {
            throw MapCatalogError.invalidMetadata("Invalid local header for gmapsupp.img")
        }
        let localExtra = Int(try number(headBytes, 28, 2))
        guard localExtra <= 256, headerFixed + localExtra < headBytes.count else {
            throw MapCatalogError.invalidMetadata("Invalid local extra length")
        }
        try requireSafeExtraFields(Array(headBytes[headerFixed..<(headerFixed + localExtra)]))
        if entry.flags & 8 == 0 {
            guard try number(headBytes, 14, 4) == UInt64(entry.crc32),
                  try number(headBytes, 18, 4) == entry.packedSize,
                  try number(headBytes, 22, 4) == entry.unpackedSize else {
                throw MapCatalogError.invalidMetadata("Local header metadata mismatch")
            }
        }
        let dataStart = headerFixed + localExtra
        let availablePacked = min(UInt64(headBytes.count - dataStart), entry.packedSize)
        let compressed = Array(headBytes[dataStart..<(dataStart + Int(availablePacked))])
        guard let inflated = inflateRawDeflate(compressed, maxOutputBytes: imgInspectBytes),
              inflated.count >= 0x84 else {
            throw MapCatalogError.invalidMetadata("Could not inflate gmapsupp.img header")
        }
        return inflated
    }

    static func inflateRawDeflate(_ compressed: [UInt8], maxOutputBytes: Int) -> [UInt8]? {
        guard !compressed.isEmpty, maxOutputBytes > 0 else { return nil }
        var output = [UInt8](repeating: 0, count: maxOutputBytes)
        let decodedCount: Int? = compressed.withUnsafeBufferPointer { srcBuf in
            output.withUnsafeMutableBufferPointer { dstBuf in
                guard let srcBase = srcBuf.baseAddress, let dstBase = dstBuf.baseAddress else { return nil }
                var stream = compression_stream(
                    dst_ptr: dstBase, dst_size: 0,
                    src_ptr: srcBase, src_size: 0, state: nil
                )
                guard compression_stream_init(&stream, COMPRESSION_STREAM_DECODE, COMPRESSION_ZLIB) == COMPRESSION_STATUS_OK else {
                    return nil
                }
                defer { compression_stream_destroy(&stream) }
                stream.dst_ptr = dstBase
                stream.dst_size = dstBuf.count
                stream.src_ptr = srcBase
                stream.src_size = srcBuf.count
                while stream.dst_size > 0 {
                    let prevDst = stream.dst_size
                    let prevSrc = stream.src_size
                    let status = compression_stream_process(&stream, 0)
                    if status == COMPRESSION_STATUS_END {
                        break
                    }
                    guard status == COMPRESSION_STATUS_OK else { return nil }
                    if stream.dst_size == prevDst && stream.src_size == prevSrc {
                        break
                    }
                }
                return dstBuf.count - stream.dst_size
            }
        }
        guard let decodedCount, decodedCount > 0 else { return nil }
        return Array(output.prefix(decodedCount))
    }

    private final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
        func urlSession(
            _ session: URLSession,
            task: URLSessionTask,
            willPerformHTTPRedirection response: HTTPURLResponse,
            newRequest request: URLRequest,
            completionHandler: @escaping (URLRequest?) -> Void
        ) {
            completionHandler(nil)
        }
    }

    private static let noRedirectDataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
        let delegate = NoRedirectDelegate()
        let session = URLSession(configuration: .ephemeral, delegate: delegate, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        return try await session.data(for: request)
    }
}

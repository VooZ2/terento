import CryptoKit
import Foundation

enum DeviceAssetScope: String, Equatable, Sendable {
    case fallback
    case family = "FAMILY"
    case model = "MODEL"
    case modelSize = "MODEL_SIZE"
    case exactVariant = "EXACT_VARIANT"
    case generic = "GENERIC"
}

struct DeviceAsset: Equatable, Sendable {
    let resourceName: String
    let resourceSubdirectory: String
    let scope: DeviceAssetScope

    var isExactMatch: Bool {
        scope == .exactVariant
    }
}

enum DeviceAssetSourceType: String, Equatable, Sendable {
    case officialProductMedia = "OFFICIAL_PRODUCT_MEDIA"
    case terentoRender = "TERENTO_RENDER"
    case genericFallback = "GENERIC_FALLBACK"
}

struct DeviceCatalogLegalMetadata: Decodable, Equatable, Sendable {
    let manufacturerNotice: Bool?
    let text: String?
}

/// The result used by the UI. A bundled model render is deliberately not the
/// source of truth for the connected device; it remains available only for
/// older registry tests and local development fixtures.
struct ResolvedDeviceAsset: Equatable, Sendable {
    let cachedFileURL: URL?
    let assetURL: URL?
    let scope: DeviceAssetScope?
    let assetVersion: Int?
    let attribution: String?
    let assetSource: DeviceAssetSource?
    let legalManufacturerNotice: Bool?
    let legalNotice: String?
    let source: Source

    enum Source: String, Equatable, Sendable {
        case catalog
        case fallback
    }

    static let fallback = ResolvedDeviceAsset(
        cachedFileURL: nil,
        assetURL: nil,
        scope: nil,
        assetVersion: nil,
        attribution: nil,
        assetSource: nil,
        legalManufacturerNotice: nil,
        legalNotice: nil,
        source: .fallback
    )

    var isFallback: Bool {
        source == .fallback
    }

    var attributionRequired: Bool {
        assetSource?.attributionRequired == true
    }

    var assetAttribution: String? {
        attribution
    }
}

struct DeviceCatalogResponse: Decodable, Sendable {
    let catalogVersion: Int?
    let legal: DeviceCatalogLegalMetadata?
    let devices: [DeviceCatalogRecord]
}

struct DeviceCatalogRecord: Decodable, Sendable {
    let id: String
    let manufacturer: String
    let family: String
    let familyName: String?
    let model: String
    let canonicalModel: String
    let variant: String
    let caseSizeMm: Int?
    let displayType: String?
    let partNumber: String?
    let productURL: URL?
    let active: Bool?
    let asset: DeviceCatalogAsset?
    let sourceAsset: DeviceCatalogSourceAsset?

    enum CodingKeys: String, CodingKey {
        case id
        case manufacturer
        case family
        case familyName
        case model
        case canonicalModel
        case variant
        case caseSizeMm
        case displayType
        case partNumber
        case productURL
        case active
        case asset
        case sourceAsset
    }

    init(
        id: String,
        manufacturer: String,
        family: String,
        familyName: String? = nil,
        model: String,
        canonicalModel: String,
        variant: String,
        caseSizeMm: Int?,
        displayType: String?,
        partNumber: String? = nil,
        productURL: URL? = nil,
        active: Bool? = nil,
        asset: DeviceCatalogAsset?,
        sourceAsset: DeviceCatalogSourceAsset? = nil
    ) {
        self.id = id
        self.manufacturer = manufacturer
        self.family = family
        self.familyName = familyName
        self.model = model
        self.canonicalModel = canonicalModel
        self.variant = variant
        self.caseSizeMm = caseSizeMm
        self.displayType = displayType
        self.partNumber = partNumber
        self.productURL = productURL
        self.active = active
        self.asset = asset
        self.sourceAsset = sourceAsset
    }
}

struct DeviceCatalogSourceAsset: Decodable, Sendable {
    let url: URL?
    let scope: String?
    let version: Int?
    let attribution: String?
    let source: DeviceAssetSource?

    var hasValidSourceMetadata: Bool {
        source?.isValid == true
    }

    func asCatalogAsset() -> DeviceCatalogAsset {
        DeviceCatalogAsset(
            status: "AVAILABLE",
            url: url,
            scope: scope ?? "MODEL",
            version: version,
            attribution: attribution,
            source: source
        )
    }
}

struct DeviceCatalogAsset: Decodable, Sendable {
    let status: String?
    let url: URL?
    let scope: String?
    let sha256: String?
    let version: Int?
    let attribution: String?
    let source: DeviceAssetSource?

    init(
        status: String? = "AVAILABLE",
        url: URL?,
        scope: String?,
        sha256: String? = nil,
        version: Int? = nil,
        attribution: String? = nil,
        source: DeviceAssetSource? = nil
    ) {
        self.status = status
        self.url = url
        self.scope = scope
        self.sha256 = sha256
        self.version = version
        self.attribution = attribution
        self.source = source
    }

    enum CodingKeys: String, CodingKey {
        case url
        case status
        case scope
        case sha256
        case version
        case assetVersion
        case attribution
        case source
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        url = try container.decodeIfPresent(URL.self, forKey: .url)
        scope = try container.decodeIfPresent(String.self, forKey: .scope)
        sha256 = try container.decodeIfPresent(String.self, forKey: .sha256)
        let currentVersion = try container.decodeIfPresent(Int.self, forKey: .version)
        let legacyVersion = try container.decodeIfPresent(Int.self, forKey: .assetVersion)
        version = currentVersion ?? legacyVersion
        attribution = try container.decodeIfPresent(String.self, forKey: .attribution)
        source = try container.decodeIfPresent(DeviceAssetSource.self, forKey: .source)
    }

    var hasValidSourceMetadata: Bool {
        source?.isValid == true
    }

    var isAvailable: Bool {
        status?.uppercased() == "AVAILABLE"
    }
}

struct DeviceAssetSource: Decodable, Equatable, Sendable {
    let type: String
    let brand: String
    let attributionRequired: Bool

    var isValid: Bool {
        switch (type, brand, attributionRequired) {
        case ("OFFICIAL_PRODUCT_MEDIA", "Garmin", true):
            return true
        case ("TERENTO_RENDER", "Terento", false):
            return true
        case ("GENERIC_FALLBACK", "Terento", false):
            return true
        default:
            return false
        }
    }

    var sourceType: DeviceAssetSourceType? {
        DeviceAssetSourceType(rawValue: type)
    }
}

/// Resolves approved Terento-controlled catalogue assets first, then an
/// allowlisted official Garmin source image from catalog metadata or the
/// catalog's official Garmin product page when no controlled asset applies.
/// The API never authorizes a device operation; it supplies presentation
/// metadata only. Any ambiguity returns the neutral watch fallback.
protocol DeviceCatalogAPIClient {
    func fetchCatalog() async throws -> DeviceCatalogResponse
    func fetchAsset(from url: URL) async throws -> Data
    func fetchProductImageURL(from productURL: URL) async throws -> URL?
}

struct URLSessionDeviceCatalogAPIClient: DeviceCatalogAPIClient {
    let endpoint: URL?

    init(endpoint: URL? = DeviceAssetResolver.endpoint) {
        self.endpoint = endpoint
    }

    func fetchCatalog() async throws -> DeviceCatalogResponse {
        guard let endpoint else {
            throw DeviceAssetResolverError.invalidHTTPResponse
        }

        var request = URLRequest(url: endpoint)
        request.timeoutInterval = 8
        request.cachePolicy = .reloadRevalidatingCacheData

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw DeviceAssetResolverError.invalidHTTPResponse
        }

        return try JSONDecoder().decode(DeviceCatalogResponse.self, from: data)
    }

    func fetchAsset(from url: URL) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw DeviceAssetResolverError.invalidHTTPResponse
        }
        return data
    }

    func fetchProductImageURL(from productURL: URL) async throws -> URL? {
        guard DeviceAssetResolver.officialProductURL(for: productURL) != nil else {
            throw DeviceAssetResolverError.uncontrolledAssetURL
        }

        var request = URLRequest(url: productURL)
        request.timeoutInterval = 8
        request.cachePolicy = .reloadRevalidatingCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode,
              let finalURL = httpResponse.url,
              DeviceAssetResolver.officialProductURL(for: finalURL) != nil,
              data.count <= 4 * 1_024 * 1_024,
              let html = String(data: data, encoding: .utf8) else {
            throw DeviceAssetResolverError.invalidHTTPResponse
        }

        return Self.openGraphImageURL(in: html)
    }

    private static func openGraphImageURL(in html: String) -> URL? {
        let metaPattern = #"<meta\b[^>]*>"#
        guard let expression = try? NSRegularExpression(
            pattern: metaPattern,
            options: [.caseInsensitive]
        ) else {
            return nil
        }

        let range = NSRange(html.startIndex..<html.endIndex, in: html)
        for match in expression.matches(in: html, range: range) {
            guard let tagRange = Range(match.range, in: html) else { continue }
            let tag = String(html[tagRange])
            guard tag.range(
                of: #"(?:property|name)\s*=\s*[\"']og:image[\"']"#,
                options: [.regularExpression, .caseInsensitive]
            ) != nil,
            let contentRange = tag.range(
                of: #"content\s*=\s*[\"'][^\"']+[\"']"#,
                options: [.regularExpression, .caseInsensitive]
            ) else {
                continue
            }

            let content = tag[contentRange]
            guard let equals = content.firstIndex(of: "=") else { continue }
            let rawValue = content[content.index(after: equals)...]
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                .replacingOccurrences(of: "&amp;", with: "&")
            if let url = URL(string: rawValue) {
                return url
            }
        }
        return nil
    }
}

enum DeviceAssetResolverError: Error {
    case invalidHTTPResponse
    case unsupportedCatalogVersion
    case uncontrolledAssetURL
    case checksumMismatch
}

struct DeviceAssetCache {
    let directory: URL

    init(directory: URL? = nil) {
        self.directory = directory ?? Self.defaultDirectory()
    }

    func load(assetURL: URL, checksum: String?, version: Int?) -> Data? {
        let location = location(assetURL: assetURL, checksum: checksum, version: version)
        guard let data = try? Data(contentsOf: location),
              DeviceAssetResolver.checksumMatches(data, checksum: checksum) else {
            return nil
        }
        return data
    }

    func save(_ data: Data, assetURL: URL, checksum: String?, version: Int?) throws -> URL {
        let location = location(assetURL: assetURL, checksum: checksum, version: version)
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        try data.write(to: location, options: .atomic)
        return location
    }

    func location(assetURL: URL, checksum: String?, version: Int?) -> URL {
        let rawKey: String
        if let checksum = checksum?.trimmingCharacters(in: .whitespacesAndNewlines),
           !checksum.isEmpty {
            rawKey = checksum
        } else {
            rawKey = "\(assetURL.absoluteString)-v\(version ?? 0)"
        }
        let key = rawKey.replacingOccurrences(
            of: "[^A-Za-z0-9._-]",
            with: "_",
            options: .regularExpression
        )
        return directory.appendingPathComponent(key)
    }

    private static func defaultDirectory() -> URL {
        let base = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("Terento/DeviceAssets", isDirectory: true)
    }
}

struct DeviceAssetResolver {
    static let endpoint = URLComponents(
        string: "https://api.terento.app/devices/catalog.json"
    )?.url
    static let catalogVersion = 2
    private static let controlledAssetOrigin = URLComponents(
        string: "https://api.terento.app"
    )?.url
    private static let controlledAssetPath = "/assets/devices/"
    private static let officialMediaHost = "res.garmin.com"
    private static let officialProductHosts: Set<String> = ["garmin.com", "www.garmin.com"]
    private let client: any DeviceCatalogAPIClient
    private let cache: DeviceAssetCache

    init(
        client: any DeviceCatalogAPIClient = URLSessionDeviceCatalogAPIClient(),
        cache: DeviceAssetCache = DeviceAssetCache()
    ) {
        self.client = client
        self.cache = cache
    }

    func resolve(identity: DeviceIdentity) async -> ResolvedDeviceAsset {
        guard let canonicalModel = identity.catalogCanonicalModel else {
            return .fallback
        }

        do {
            let catalog = try await client.fetchCatalog()
            guard catalog.catalogVersion == Self.catalogVersion else {
                return .fallback
            }

            let match: Match
            if let catalogMatch = Self.matchingRecord(
                      identity: identity,
                      canonicalModel: canonicalModel,
                      records: catalog.devices
                  ) {
                match = catalogMatch
            } else if let productMatch = Self.matchingProductRecord(
                identity: identity,
                canonicalModel: canonicalModel,
                records: catalog.devices
            ), let productURL = Self.officialProductURL(for: productMatch.record.productURL),
               let sourceURL = try await client.fetchProductImageURL(from: productURL),
               let officialURL = Self.officialSourceURL(for: sourceURL) {
                match = Match(
                    record: productMatch.record,
                    asset: DeviceCatalogAsset(
                        url: officialURL,
                        scope: productMatch.scope.rawValue,
                        version: 1,
                        attribution: "Garmin official product media",
                        source: DeviceAssetSource(
                            type: "OFFICIAL_PRODUCT_MEDIA",
                            brand: "Garmin",
                            attributionRequired: true
                        )
                    ),
                    rank: productMatch.rank
                )
            } else {
                return .fallback
            }

            guard let assetURL = Self.downloadURL(for: match.asset.url),
                  let scope = Self.scope(for: match.asset.scope),
                  match.asset.isAvailable,
                  match.asset.hasValidSourceMetadata else {
                return .fallback
            }

            let imageData: Data
            if let cached = cache.load(
                assetURL: assetURL,
                checksum: match.asset.sha256,
                version: match.asset.version
            ) {
                imageData = cached
            } else {
                let downloaded = try await client.fetchAsset(from: assetURL)
                guard Self.checksumMatches(downloaded, checksum: match.asset.sha256) else {
                    throw DeviceAssetResolverError.checksumMismatch
                }
                imageData = downloaded
            }

            let fileURL = try cache.save(
                imageData,
                assetURL: assetURL,
                checksum: match.asset.sha256,
                version: match.asset.version
            )

            return ResolvedDeviceAsset(
                cachedFileURL: fileURL,
                assetURL: assetURL,
                scope: scope,
                assetVersion: match.asset.version,
                attribution: match.asset.attribution,
                assetSource: match.asset.source,
                legalManufacturerNotice: catalog.legal?.manufacturerNotice,
                legalNotice: catalog.legal?.text,
                source: .catalog
            )
        } catch {
            return .fallback
        }
    }

    struct Match: Sendable {
        let record: DeviceCatalogRecord
        let asset: DeviceCatalogAsset
        let rank: Int
    }

    struct ProductMatch: Sendable {
        let record: DeviceCatalogRecord
        let scope: DeviceAssetScope
        let rank: Int
    }

    static func matchingAsset(
        identity: DeviceIdentity,
        canonicalModel: String,
        records: [DeviceCatalogRecord]
    ) -> DeviceCatalogAsset? {
        matchingRecord(
            identity: identity,
            canonicalModel: canonicalModel,
            records: records
        )?.asset
    }

    static func controlledURL(for value: URL?) -> URL? {
        guard let value, let controlledAssetOrigin else { return nil }

        let resolved: URL
        if value.scheme != nil {
            resolved = value
        } else {
            resolved = URL(string: value.absoluteString, relativeTo: controlledAssetOrigin)?.absoluteURL
                ?? value
        }

        guard let components = URLComponents(url: resolved, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == "https",
              components.host?.lowercased() == controlledAssetOrigin.host?.lowercased(),
              components.port == controlledAssetOrigin.port,
              components.user == nil,
              components.password == nil,
              components.path.hasPrefix(Self.controlledAssetPath) else {
            return nil
        }

        return resolved
    }

    static func officialSourceURL(for value: URL?) -> URL? {
        guard let value,
              let components = URLComponents(url: value, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == "https",
              components.host?.lowercased() == officialMediaHost,
              components.port == nil,
              components.user == nil,
              components.password == nil,
              !components.path.isEmpty else {
            return nil
        }
        return value
    }

    static func officialProductURL(for value: URL?) -> URL? {
        guard let value,
              let components = URLComponents(url: value, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == "https",
              let host = components.host?.lowercased(),
              officialProductHosts.contains(host),
              components.port == nil,
              components.user == nil,
              components.password == nil,
              components.path.hasPrefix("/") else {
            return nil
        }
        return value
    }

    private static func downloadURL(for value: URL?) -> URL? {
        controlledURL(for: value) ?? officialSourceURL(for: value)
    }

    private static func matchingRecord(
        identity: DeviceIdentity,
        canonicalModel: String,
        records: [DeviceCatalogRecord]
    ) -> Match? {
        let identityVariant = Self.normalized(identity.variant ?? "")
        let identityFamily = Self.normalized(identity.family ?? "")
        let knownSize = Self.parsedCaseSize(from: identityVariant)
        let knownDisplay = Self.displayType(from: identityVariant)

        return records.compactMap { record -> Match? in
            guard Self.normalized(record.manufacturer) == Self.normalized(identity.manufacturer) else {
                return nil
            }

            if let asset = record.asset,
               asset.isAvailable,
               Self.downloadURL(for: asset.url) != nil,
               asset.hasValidSourceMetadata {
                return Self.match(record: record, asset: asset, canonicalModel: canonicalModel,
                                  identityFamily: identityFamily, knownSize: knownSize,
                                  knownDisplay: knownDisplay)
            }

            if let sourceAsset = record.sourceAsset,
               sourceAsset.hasValidSourceMetadata,
               Self.officialSourceURL(for: sourceAsset.url) != nil {
                return Self.match(
                    record: record,
                    asset: sourceAsset.asCatalogAsset(),
                    canonicalModel: canonicalModel,
                    identityFamily: identityFamily,
                    knownSize: knownSize,
                    knownDisplay: knownDisplay
                )
            }

            return nil
        }
        .sorted {
            if $0.rank != $1.rank { return $0.rank < $1.rank }
            return $0.record.id < $1.record.id
        }
        .first
    }

    private static func matchingProductRecord(
        identity: DeviceIdentity,
        canonicalModel: String,
        records: [DeviceCatalogRecord]
    ) -> ProductMatch? {
        let knownSize = parsedCaseSize(from: normalized(identity.variant ?? ""))
        let knownDisplay = displayType(from: normalized(identity.variant ?? ""))

        return records.compactMap { record -> ProductMatch? in
            guard normalized(record.manufacturer) == normalized(identity.manufacturer),
                  normalized(record.canonicalModel) == normalized(canonicalModel),
                  officialProductURL(for: record.productURL) != nil else {
                return nil
            }

            if let knownSize,
               let knownDisplay,
               record.caseSizeMm == knownSize,
               normalized(record.displayType ?? "") == knownDisplay {
                return ProductMatch(record: record, scope: .exactVariant, rank: 0)
            }
            if let knownSize, record.caseSizeMm == knownSize {
                return ProductMatch(record: record, scope: .modelSize, rank: 1)
            }
            return ProductMatch(record: record, scope: .model, rank: 2)
        }
        .sorted {
            if $0.rank != $1.rank { return $0.rank < $1.rank }
            return $0.record.id < $1.record.id
        }
        .first
    }

    private static func match(
        record: DeviceCatalogRecord,
        asset: DeviceCatalogAsset,
        canonicalModel: String,
        identityFamily: String,
        knownSize: Int?,
        knownDisplay: String?
    ) -> Match? {
        let assetScope = Self.normalized(asset.scope ?? "")
        switch assetScope {
        case "exact variant":
            guard Self.normalized(record.canonicalModel) == Self.normalized(canonicalModel)
            else { return nil }
            guard Self.normalized(record.family) == identityFamily else { return nil }
            guard let knownSize,
                  let knownDisplay,
                  record.caseSizeMm == knownSize,
                  Self.normalized(record.displayType ?? "") == knownDisplay else {
                return nil
            }
            return Match(record: record, asset: asset, rank: 0)
        case "model size":
            guard Self.normalized(record.canonicalModel) == Self.normalized(canonicalModel)
            else { return nil }
            guard Self.normalized(record.family) == identityFamily else { return nil }
            guard let knownSize, record.caseSizeMm == knownSize else {
                return nil
            }
            return Match(record: record, asset: asset, rank: 1)
        case "model":
            guard Self.normalized(record.canonicalModel) == Self.normalized(canonicalModel)
            else { return nil }
            guard Self.normalized(record.family) == identityFamily else { return nil }
            return Match(record: record, asset: asset, rank: 2)
        case "family":
            guard !identityFamily.isEmpty,
                  Self.normalized(record.family) == identityFamily else { return nil }
            return Match(record: record, asset: asset, rank: 3)
        case "generic":
            return Match(record: record, asset: asset, rank: 4)
        default:
            return nil
        }
    }

    private static func scope(for value: String?) -> DeviceAssetScope? {
        switch Self.normalized(value ?? "") {
        case "family": return .family
        case "model": return .model
        case "model size": return .modelSize
        case "exact variant": return .exactVariant
        case "generic": return .generic
        default: return nil
        }
    }
    static func checksumMatches(_ data: Data, checksum: String?) -> Bool {
        guard let checksum, !checksum.isEmpty else {
            return true
        }

        let digest = SHA256.hash(data: data)
            .map { String(format: "%02x", $0) }
            .joined()
        return digest.caseInsensitiveCompare(checksum) == .orderedSame
    }

    private static func parsedCaseSize(from value: String) -> Int? {
        let pattern = #"(\d{2,3})\s*mm"#
        guard let match = value.range(of: pattern, options: .regularExpression),
              let number = value[match].replacingOccurrences(of: "mm", with: "", options: .caseInsensitive)
                .trimmingCharacters(in: .whitespaces)
                .split(separator: " ")
                .first,
              let size = Int(number) else {
            return nil
        }
        return size
    }

    private static func displayType(from value: String) -> String? {
        if value.contains("amoled") { return "amoled" }
        if value.contains("mip") { return "mip" }
        return nil
    }

    private static func normalized(_ value: String) -> String {
        value
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }
}

/// Source-compatible name retained for the existing PoC call sites and tests.
typealias DeviceCatalogAssetResolver = DeviceAssetResolver

/// Maps validated device identity to an approved local asset. A fallback is
/// returned for unknown devices so the UI can never display a wrong model.
struct DeviceAssetRegistry: Sendable {
    static let local = DeviceAssetRegistry()

    func asset(for identity: DeviceIdentity?) -> DeviceAsset {
        guard let identity,
              identity.canonicalModel == "fēnix 8",
              identity.usbVendorId == 0x091e,
              identity.usbProductId == 0x51b8 else {
            return DeviceAsset(
                resourceName: "generic-garmin-watch",
                resourceSubdirectory: "Devices",
                scope: .fallback
            )
        }

        let scope: DeviceAssetScope
        if identity.caseSizeMm == 47, identity.displayType == "AMOLED" {
            scope = .exactVariant
        } else if identity.caseSizeMm == 47 {
            scope = .modelSize
        } else {
            scope = .model
        }

        return DeviceAsset(
            resourceName: "fenix8-render",
            resourceSubdirectory: "Devices",
            scope: scope
        )
    }
}

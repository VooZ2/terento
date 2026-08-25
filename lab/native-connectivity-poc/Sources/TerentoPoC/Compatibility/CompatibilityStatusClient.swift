import Foundation

enum CompatibilityStatusSource: String, Codable, Equatable, Sendable {
    case remote
    case cache
    case unavailable
}

struct CompatibilityStatusResolution: Equatable, Sendable {
    let status: CompatibilityStatus?
    let source: CompatibilityStatusSource
    let identityKey: String
    let record: CompatibilityStatusRecord?

    var isAvailable: Bool {
        source != .unavailable
    }
}

struct CompatibilityStatusRecord: Decodable, Equatable, Sendable {
    let model: String
    let canonicalModel: String?
    let compatibilityIdentity: String?
    let variant: String?
    let caseSizeMm: Int?
    let displayType: String?
    let canonicalDeviceId: String?
    let attemptedInstallations: Int?
    let successfulInstallations: Int?
    let failedInstallations: Int?
    let lastSuccessfulInstallation: String?
    let lastEvidence: String?
    let mapCapable: Bool?
    let status: CompatibilityStatus?

    private enum CodingKeys: String, CodingKey {
        case model
        case canonicalModel
        case compatibilityIdentity
        case variant
        case caseSizeMm
        case displayType
        case canonicalDeviceId
        case attemptedInstallations
        case successfulInstallations
        case failedInstallations
        case lastSuccessfulInstallation
        case lastEvidence
        case mapCapable
        case evidenceStatus
        case status
        case calculatedStatus
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        model = try container.decode(String.self, forKey: .model)
        canonicalModel = try container.decodeIfPresent(String.self, forKey: .canonicalModel)
        compatibilityIdentity = try container.decodeIfPresent(String.self, forKey: .compatibilityIdentity)
        variant = try container.decodeIfPresent(String.self, forKey: .variant)
        caseSizeMm = try container.decodeIfPresent(Int.self, forKey: .caseSizeMm)
        displayType = try container.decodeIfPresent(String.self, forKey: .displayType)
        canonicalDeviceId = try container.decodeIfPresent(String.self, forKey: .canonicalDeviceId)
        attemptedInstallations = try container.decodeIfPresent(Int.self, forKey: .attemptedInstallations)
        successfulInstallations = try container.decodeIfPresent(Int.self, forKey: .successfulInstallations)
        failedInstallations = try container.decodeIfPresent(Int.self, forKey: .failedInstallations)
        lastSuccessfulInstallation = try container.decodeIfPresent(String.self, forKey: .lastSuccessfulInstallation)
        lastEvidence = try container.decodeIfPresent(String.self, forKey: .lastEvidence)
        mapCapable = try container.decodeIfPresent(Bool.self, forKey: .mapCapable)

        let rawStatus = try container.decodeIfPresent(String.self, forKey: .evidenceStatus)
            ?? container.decodeIfPresent(String.self, forKey: .status)
            ?? container.decodeIfPresent(String.self, forKey: .calculatedStatus)
        status = rawStatus.flatMap { CompatibilityStatus(rawValue: $0.uppercased()) }
    }
}

private struct CompatibilityStatusResponse: Decodable {
    let schemaVersion: Int
    let models: [CompatibilityStatusRecord]
}

private struct CompatibilityStatusCacheEntry: Codable, Equatable, Sendable {
    let status: CompatibilityStatus
    let storedAt: Date
}

private struct CompatibilityStatusCacheDocument: Codable, Sendable {
    var entries: [String: CompatibilityStatusCacheEntry] = [:]
}

actor CompatibilityStatusCache {
    private let fileURL: URL

    init(fileURL: URL? = nil) {
        self.fileURL = fileURL ?? FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first!.appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("compatibility-status.json")
    }

    func read(identityKey: String, now: Date = Date()) -> CompatibilityStatus? {
        guard let document = try? load(),
              let entry = document.entries[identityKey],
              now.timeIntervalSince(entry.storedAt) <= CompatibilityStatusClient.cacheMaxAge,
              now >= entry.storedAt else {
            return nil
        }
        return entry.status
    }

    func write(status: CompatibilityStatus, identityKey: String, now: Date = Date()) {
        var document = (try? load()) ?? CompatibilityStatusCacheDocument()
        document.entries[identityKey] = CompatibilityStatusCacheEntry(status: status, storedAt: now)
        guard let data = try? Self.encoder.encode(document) else { return }
        do {
            try FileManager.default.createDirectory(
                at: fileURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
        } catch {
            // Compatibility metadata is best-effort and must never block the
            // device read or any map safety operation.
        }
    }

    private func load() throws -> CompatibilityStatusCacheDocument {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return CompatibilityStatusCacheDocument()
        }
        return try Self.decoder.decode(
            CompatibilityStatusCacheDocument.self,
            from: Data(contentsOf: fileURL)
        )
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}

struct CompatibilityStatusClient: Sendable {
    static let defaultEndpoint = URL(
        string: "https://api.terento.app/compatibility/public/top-models.json?limit=500"
    )!

    // A cache older than one day is not a trustworthy public compatibility
    // result. An expired cache is ignored rather than presented as a local
    // downgrade or an invented status.
    static let cacheMaxAge: TimeInterval = 24 * 60 * 60

    private let endpoint: URL
    private let cache: CompatibilityStatusCache
    private let dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)

    init(
        endpoint: URL = CompatibilityStatusClient.defaultEndpoint,
        cache: CompatibilityStatusCache = CompatibilityStatusCache(),
        dataLoader: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.endpoint = endpoint
        self.cache = cache
        self.dataLoader = dataLoader
    }

    func resolve(identity: DeviceIdentity) async -> CompatibilityStatusResolution {
        let identityKey = CompatibilityStatusIdentityKey(deviceIdentity: identity)
        do {
            let records = try await fetchRecords()
            if let record = matchingRecord(for: identityKey, identity: identity, in: records),
               let status = record.status {
                await cache.write(status: status, identityKey: identityKey.rawValue)
                return CompatibilityStatusResolution(
                    status: status,
                    source: .remote,
                    identityKey: identityKey.rawValue,
                    record: record
                )
            }
        } catch {
            // A cache result is considered below. There is no safe reason to
            // turn a network failure into a lower public status.
        }

        if let cachedStatus = await cache.read(identityKey: identityKey.rawValue) {
            return CompatibilityStatusResolution(
                status: cachedStatus,
                source: .cache,
                identityKey: identityKey.rawValue,
                record: nil
            )
        }

        return CompatibilityStatusResolution(
            status: nil,
            source: .unavailable,
            identityKey: identityKey.rawValue,
            record: nil
        )
    }

    private func fetchRecords() async throws -> [CompatibilityStatusRecord] {
        var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false)
        var queryItems = components?.queryItems ?? []
        queryItems.append(URLQueryItem(name: "refresh", value: String(Int(Date().timeIntervalSince1970))))
        components?.queryItems = queryItems
        guard let requestURL = components?.url,
              requestURL.scheme?.lowercased() == "https",
              requestURL.host?.lowercased() == "api.terento.app" else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: requestURL)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")

        let (data, response) = try await dataLoader(request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }

        let document = try JSONDecoder().decode(CompatibilityStatusResponse.self, from: data)
        guard document.schemaVersion >= 2 else {
            throw URLError(.cannotParseResponse)
        }
        return document.models
    }

    private func matchingRecord(
        for identityKey: CompatibilityStatusIdentityKey,
        identity: DeviceIdentity,
        in records: [CompatibilityStatusRecord]
    ) -> CompatibilityStatusRecord? {
        let reviewedID = identity.reviewedCanonicalDeviceID
        let candidates = records.compactMap { record -> (CompatibilityStatusIdentityKey, CompatibilityStatusRecord)? in
            guard record.status != nil,
                  record.mapCapable != false else {
                return nil
            }
            let recordKey = CompatibilityStatusIdentityKey(record: record)
            guard recordKey.model == identityKey.model,
                  recordKey.caseSizeMm == identityKey.caseSizeMm else {
                return nil
            }
            if let reviewedID {
                guard record.canonicalDeviceId == reviewedID else { return nil }
            } else if let deviceDisplay = identityKey.displayType {
                guard recordKey.displayType == deviceDisplay else { return nil }
            } else if recordKey.displayType != nil {
                // A size-only identity cannot claim an AMOLED/Solar row.
                return nil
            }
            return (recordKey, record)
        }

        // If MTP did not expose display technology, a size-specific row is
        // usable only when it is unambiguous. This prevents AMOLED/Solar rows
        // from inheriting one another's public status.
        let unique = Dictionary(grouping: candidates, by: { $0.0 })
        guard unique.count == 1,
              let matches = unique.values.first,
              let record = matches.first?.1,
              matches.allSatisfy({ $0.1.status == record.status }) else {
            return nil
        }
        return record
    }
}

struct CompatibilityStatusIdentityKey: Hashable, Codable, Equatable, Sendable {
    let model: String
    let caseSizeMm: Int?
    let displayType: String?
    let canonicalDeviceID: String?

    var rawValue: String {
        [model, caseSizeMm.map(String.init) ?? "", displayType ?? "", canonicalDeviceID ?? ""]
            .joined(separator: "|")
    }

    init(deviceIdentity: DeviceIdentity) {
        self.model = Self.baseModel(deviceIdentity.canonicalModel ?? deviceIdentity.model)
        self.caseSizeMm = deviceIdentity.caseSizeMm
        self.displayType = deviceIdentity.displayType.flatMap { Self.normalizeDisplay($0) }
        self.canonicalDeviceID = deviceIdentity.reviewedCanonicalDeviceID
    }

    init(record: CompatibilityStatusRecord) {
        let source = [record.model, record.canonicalModel, record.compatibilityIdentity, record.variant, record.displayType]
            .compactMap { $0 }
            .joined(separator: " ")
        // The API's model field is the canonical base-model label. Use the
        // richer identity only for size/display extraction; concatenating all
        // fields before base normalization would duplicate the model tokens.
        self.model = Self.baseModel(record.model)
        self.caseSizeMm = record.caseSizeMm ?? GarminDeviceModelNormalizer.caseSizeMm(from: source)
        self.displayType = Self.normalizeDisplay(
            GarminDeviceModelNormalizer.displayType(from: source)
        )
        self.canonicalDeviceID = record.canonicalDeviceId
    }

    private static func baseModel(_ value: String) -> String {
        GarminDeviceModelNormalizer.catalogCanonicalModel(from: value)
            .map(GarminDeviceModelNormalizer.normalize)
            ?? GarminDeviceModelNormalizer.normalize(value)
    }

    private static func normalizeDisplay(_ value: String?) -> String? {
        guard let value else { return nil }
        return GarminDeviceModelNormalizer.normalize(value)
    }
}

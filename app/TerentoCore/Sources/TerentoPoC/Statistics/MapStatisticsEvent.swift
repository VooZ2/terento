import Combine
import Foundation

private extension NSLock {
    func withLock<T>(_ body: () throws -> T) rethrows -> T {
        lock()
        defer { unlock() }
        return try body()
    }
}

enum MapStatisticsEventType: String, Codable, Sendable {
    case downloadStarted = "DOWNLOAD_STARTED"
    case downloadProcessing = "DOWNLOAD_PROCESSING"
    case downloadCancelled = "DOWNLOAD_CANCELLED"
    case downloadInterrupted = "DOWNLOAD_INTERRUPTED"
    case downloadSucceeded = "DOWNLOAD_SUCCEEDED"
    case downloadFailed = "DOWNLOAD_FAILED"
    case installSucceeded = "INSTALL_SUCCEEDED"
    case installFailed = "INSTALL_FAILED"
    case mapUpdateSucceeded = "MAP_UPDATE_SUCCEEDED"
    case mapUpdateFailed = "MAP_UPDATE_FAILED"
}

enum MapStatisticsEventOutcome: String, Codable, Sendable {
    case succeeded = "SUCCEEDED"
    case failed = "FAILED"
    case unknown = "UNKNOWN"
}

/// Privacy-minimised product statistics. This model intentionally has no
/// device identity, source URL, local path, manifest, checksum, or diagnostic
/// fields, so those values cannot accidentally enter the API payload.
struct MapStatisticsEvent: Codable, Equatable, Identifiable, Sendable {
    static let schemaVersion = 1

    let schemaVersion: Int
    let id: UUID
    let operationId: UUID
    let providerId: String
    let mapId: String
    let region: String?
    let acquisitionId: UUID?
    let componentKind: MapArtifactKind?
    let mapResultIndex: Int?
    let eventType: MapStatisticsEventType
    let outcome: MapStatisticsEventOutcome
    let timestamp: Date
    let appBuild: String
    let releaseLabel: String

    init(
        id: UUID = UUID(),
        operationId: UUID,
        package: MapPackage,
        eventType: MapStatisticsEventType,
        outcome: MapStatisticsEventOutcome,
        timestamp: Date = Date(),
        acquisitionId: UUID? = nil,
        componentKind: MapArtifactKind? = nil,
        mapResultIndex: Int? = nil,
        appBuild: String = TerentoTelemetryMetadata.eventBuild,
        releaseLabel: String = TerentoTelemetryMetadata.releaseLabel
    ) {
        schemaVersion = Self.schemaVersion
        self.id = id
        self.operationId = operationId
        self.acquisitionId = acquisitionId
        self.componentKind = componentKind
        self.mapResultIndex = mapResultIndex

        // A custom package ID may be derived from a local file hash. Never
        // disclose that identity; custom imports use deliberately coarse,
        // stable labels instead.
        if package.sourceKind == .custom {
            providerId = "custom"
            mapId = "custom-map"
            region = nil
        } else {
            providerId = Self.safeIdentifier(package.providerId, fallback: "unknown-provider")
            mapId = Self.safeIdentifier(package.id, fallback: "unknown-map")
            region = Self.optionalSafeIdentifier(package.canonicalRegionId)
        }
        self.eventType = eventType
        self.outcome = outcome
        self.timestamp = timestamp
        self.appBuild = String(appBuild.prefix(80))
        self.releaseLabel = String(releaseLabel.prefix(80))
    }

    /// Derive a phase from the immutable start, preserving package/build identity.
    func phase(_ type: MapStatisticsEventType, at timestamp: Date = Date()) -> Self {
        Self(start: self, type: type, timestamp: timestamp)
    }

    private init(start: Self, type: MapStatisticsEventType, timestamp: Date) {
        schemaVersion = start.schemaVersion
        id = UUID()
        operationId = start.operationId
        providerId = start.providerId
        mapId = start.mapId
        region = start.region
        acquisitionId = start.acquisitionId
        componentKind = start.componentKind
        mapResultIndex = start.mapResultIndex
        eventType = type
        outcome = type == .downloadSucceeded ? .succeeded : type == .downloadFailed ? .failed : .unknown
        self.timestamp = timestamp
        appBuild = start.appBuild
        releaseLabel = start.releaseLabel
    }

    private static func optionalSafeIdentifier(_ value: String) -> String? {
        let safe = safeIdentifier(value, fallback: "")
        return safe.isEmpty ? nil : safe
    }

    private static func safeIdentifier(_ value: String, fallback: String) -> String {
        let folded = value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .folding(options: [.diacriticInsensitive, .widthInsensitive], locale: Locale(identifier: "en_US_POSIX"))
        let normalized = folded.unicodeScalars.map { scalar -> Character in
            let value = scalar.value
            let isASCIIAlphaNumeric = (value >= 97 && value <= 122) || (value >= 48 && value <= 57)
            let isAllowedPunctuation = value == 46 || value == 95 || value == 45
            return isASCIIAlphaNumeric || isAllowedPunctuation
                ? Character(scalar)
                : "-"
            }
        let collapsed = String(normalized)
            .replacingOccurrences(of: #"-+"#, with: "-", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "-._"))
        return String((collapsed.isEmpty ? fallback : collapsed).prefix(160))
    }
}

enum MapStatisticsConsentChoice: String, Codable, Sendable {
    case accepted
    case declined
}

struct VersionedMapStatisticsConsent: Codable, Equatable, Sendable {
    static let currentNoticeVersion = 2
    let noticeVersion: Int
    let choice: MapStatisticsConsentChoice
    let decidedAt: Date
}

private struct MapStatisticsQueueFile: Codable {
    var pendingEvents: [MapStatisticsEvent] = []
    var consent: VersionedMapStatisticsConsent?
    // Optional for backwards-compatible decoding of existing queues.
    var activeAcquisitions: [MapStatisticsEvent]?
}

final class LocalMapStatisticsEventStore: @unchecked Sendable {
    private let fileURL: URL
    private let lock = NSLock()
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(rootURL: URL? = nil) {
        let root = rootURL ?? FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first!.appendingPathComponent("Terento", isDirectory: true)
        fileURL = root.appendingPathComponent("map-statistics-events.json")
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
    }

    func consent() -> VersionedMapStatisticsConsent? { lockedLoad().consent }
    func pendingEvents() -> [MapStatisticsEvent] { lockedLoad().pendingEvents }

    @discardableResult
    func append(_ event: MapStatisticsEvent) throws -> Bool {
        try lock.withLock {
            var file = try loadUnlocked()
            guard !file.pendingEvents.contains(where: { $0.id == event.id }) else { return false }
            file.pendingEvents.append(event)
            try saveUnlocked(file)
            return true
        }
    }

    @discardableResult
    func appendIfSharingEnabled(_ event: MapStatisticsEvent) throws -> Bool {
        try lock.withLock {
            var file = try loadUnlocked()
            guard file.consent?.choice != .declined,
                  !file.pendingEvents.contains(where: { $0.id == event.id }) else {
                return false
            }
            if let acquisitionID = event.acquisitionId {
                var active = file.activeAcquisitions ?? []
                if event.eventType == .downloadStarted {
                    guard !active.contains(where: { $0.acquisitionId == acquisitionID }) else { return false }
                    active.append(event)
                } else {
                    guard active.contains(where: { $0.acquisitionId == acquisitionID }) else { return false }
                    if event.eventType != .downloadProcessing {
                        active.removeAll { $0.acquisitionId == acquisitionID }
                    }
                }
                file.activeAcquisitions = active
            }
            file.pendingEvents.append(event)
            try saveUnlocked(file)
            return true
        }
    }

    /// Called once by the app's controller at launch, never by a view refresh.
    func reconcileInterruptedAcquisitions() throws {
        try lock.withLock {
            var file = try loadUnlocked()
            if file.consent?.choice != .declined {
                file.pendingEvents += (file.activeAcquisitions ?? []).map { $0.phase(.downloadInterrupted) }
            }
            file.activeAcquisitions = []
            try saveUnlocked(file)
        }
    }

    func migrateConsentToCurrentNotice() throws {
        try lock.withLock {
            var file = try loadUnlocked()
            guard let consent = file.consent,
                  consent.noticeVersion != VersionedMapStatisticsConsent.currentNoticeVersion else {
                return
            }
            file.consent = VersionedMapStatisticsConsent(
                noticeVersion: VersionedMapStatisticsConsent.currentNoticeVersion,
                choice: consent.choice,
                decidedAt: consent.decidedAt
            )
            if consent.choice == .declined {
                file.pendingEvents.removeAll()
                file.activeAcquisitions = []
            }
            try saveUnlocked(file)
        }
    }

    func markUploaded(eventID: UUID) throws {
        try lock.withLock {
            var file = try loadUnlocked()
            file.pendingEvents.removeAll { $0.id == eventID }
            try saveUnlocked(file)
        }
    }

    func setConsent(_ choice: MapStatisticsConsentChoice, now: Date = Date()) throws {
        try lock.withLock {
            var file = try loadUnlocked()
            file.consent = VersionedMapStatisticsConsent(
                noticeVersion: VersionedMapStatisticsConsent.currentNoticeVersion,
                choice: choice,
                decidedAt: now
            )
            if choice == .declined {
                file.pendingEvents.removeAll()
                file.activeAcquisitions = []
            }
            try saveUnlocked(file)
        }
    }

    private func lockedLoad() -> MapStatisticsQueueFile {
        lock.withLock { (try? loadUnlocked()) ?? MapStatisticsQueueFile() }
    }

    private func loadUnlocked() throws -> MapStatisticsQueueFile {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return MapStatisticsQueueFile()
        }
        return try decoder.decode(MapStatisticsQueueFile.self, from: Data(contentsOf: fileURL))
    }

    private func saveUnlocked(_ file: MapStatisticsQueueFile) throws {
        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try encoder.encode(file).write(to: fileURL, options: [.atomic, .completeFileProtection])
    }
}

protocol MapStatisticsEventUploading: Sendable {
    func upload(_ event: MapStatisticsEvent) async throws
}

enum MapStatisticsUploadError: Error, Sendable {
    case invalidResponse
    case httpStatus(Int)

    var isRetryable: Bool {
        switch self {
        case .invalidResponse: return true
        case let .httpStatus(code): return code == 408 || code == 425 || code == 429 || code >= 500
        }
    }
}

struct HTTPMapStatisticsEventUploader: MapStatisticsEventUploading {
    let endpoint: URL

    init(endpoint: URL = URL(string: "https://api.terento.app/map-events")!) {
        self.endpoint = endpoint
    }

    func upload(_ event: MapStatisticsEvent) async throws {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        request.httpBody = try encoder.encode(event)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw MapStatisticsUploadError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw MapStatisticsUploadError.httpStatus(http.statusCode)
        }
    }
}

enum MapStatisticsUploadStatus: Equatable, Sendable {
    case idle
    case uploading(Int)
    case uploaded
    case waiting(Int, willRetry: Bool)
}

@MainActor
final class MapStatisticsEventController: ObservableObject {
    let store: LocalMapStatisticsEventStore
    private let uploader: any MapStatisticsEventUploading
    private let retryDelays: [UInt64]
    private var uploadTask: Task<Void, Never>?
    private var unsavedEvents: [MapStatisticsEvent] = []
    #if TERENTO_TESTING
    /// Observe the automatic sender without replacing it with a manual flush.
    func scheduledUploadForTesting() -> Task<Void, Never>? { uploadTask }
    private var recordTaskForTesting: Task<Void, Never>?
    func scheduledRecordForTesting() -> Task<Void, Never>? { recordTaskForTesting }
    #endif
    @Published private(set) var uploadStatus: MapStatisticsUploadStatus = .idle

    init(
        store: LocalMapStatisticsEventStore = LocalMapStatisticsEventStore(),
        uploader: any MapStatisticsEventUploading = HTTPMapStatisticsEventUploader(),
        retryDelays: [UInt64] = [0, 5_000_000_000, 30_000_000_000]
    ) {
        self.store = store
        self.uploader = uploader
        self.retryDelays = retryDelays
        try? store.migrateConsentToCurrentNotice()
        try? store.reconcileInterruptedAcquisitions()
        if sharingEnabled { scheduleFlush() }
    }

    /// Privacy-minimised map usage diagnostics are enabled by default. An explicit
    /// opt-out remains persisted and is independent from compatibility data.
    var sharingEnabled: Bool {
        store.consent()?.choice != .declined
    }

    func decideConsent(_ choice: MapStatisticsConsentChoice) {
        objectWillChange.send()
        try? store.setConsent(choice)
        if choice == .accepted {
            scheduleFlush()
        } else {
            unsavedEvents.removeAll()
            uploadTask?.cancel()
            uploadTask = nil
            uploadStatus = .idle
        }
    }

    /// Persist before returning; network delivery runs separately. Any local
    /// or network error is contained here and cannot change installation state.
    func record(_ event: MapStatisticsEvent) {
        // Custom IMG imports belong to compatibility evidence only. Keep this
        // boundary defensive so a stale caller cannot add them to map stats.
        guard sharingEnabled, event.providerId != "custom" else { return }
        // Persist before returning to the producer. UI teardown and process
        // cancellation must not race an unstructured record task.
        unsavedEvents.append(event)
        persistBufferedEvents()
        scheduleFlush()
    }

    private func persistBufferedEvents() {
        while let event = unsavedEvents.first {
            do {
                _ = try store.appendIfSharingEnabled(event)
                unsavedEvents.removeFirst()
            } catch {
                uploadStatus = .waiting(unsavedEvents.count + store.pendingEvents().count, willRetry: true)
                return
            }
        }
    }

    func flushPendingEvents() async {
        let previous = uploadTask
        previous?.cancel()
        await previous?.value
        uploadTask = nil
        if await uploadOnce() == .retryableFailure { scheduleFlush() }
    }

    private func scheduleFlush() {
        guard sharingEnabled, uploadTask == nil, (!store.pendingEvents().isEmpty || !unsavedEvents.isEmpty) else { return }
        let delays = retryDelays
        uploadTask = Task { [weak self] in
            defer { self?.uploadTask = nil }
            for delay in delays {
                if delay > 0 {
                    do { try await Task.sleep(nanoseconds: delay) }
                    catch { return }
                }
                guard !Task.isCancelled, let self, self.sharingEnabled else { return }
                switch await self.uploadOnce() {
                case .empty, .completed, .permanentFailure: return
                case .retryableFailure: continue
                }
            }
        }
    }

    private enum UploadResult { case empty, completed, retryableFailure, permanentFailure }

    private func uploadOnce() async -> UploadResult {
        while sharingEnabled && !Task.isCancelled {
            persistBufferedEvents()
            guard unsavedEvents.isEmpty else { return .retryableFailure }
            // A record can arrive while an upload suspends this actor. Keep
            // draining fresh snapshots before declaring the queue uploaded;
            // scheduleFlush cannot start another sender while this one exists.
            let pending = store.pendingEvents()
            guard !pending.isEmpty else {
                uploadStatus = .uploaded
                return .completed
            }
            uploadStatus = .uploading(pending.count)
            for event in pending {
                guard sharingEnabled, !Task.isCancelled else { return .empty }
                do {
                    // Discard stale custom events locally. A failed queue write
                    // must use the bounded retry path, not repeat forever.
                    if event.providerId != "custom" {
                        try await uploader.upload(event)
                    }
                    guard sharingEnabled, !Task.isCancelled else { return .empty }
                    try store.markUploaded(eventID: event.id)
                } catch {
                    guard sharingEnabled, !Task.isCancelled else { return .empty }
                    let retryable = Self.isRetryable(error)
                    uploadStatus = .waiting(store.pendingEvents().count, willRetry: retryable)
                    return retryable ? .retryableFailure : .permanentFailure
                }
            }
        }
        return .empty
    }

    private static func isRetryable(_ error: Error) -> Bool {
        if let uploadError = error as? MapStatisticsUploadError {
            return uploadError.isRetryable
        }
        if let urlError = error as? URLError {
            return urlError.code != .userAuthenticationRequired
        }
        return true
    }
}

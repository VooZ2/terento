import Combine
import Foundation

enum DiagnosticReportSanitizer {
    static func sanitize(_ value: String) -> String {
        var result = value
        let replacements: [(String, String)] = [
            (#"(?i)\"(unit[ _-]?id|serial(?: number)?|password|token|credential)\"\s*:\s*\"[^\"]*\""#, "\"$1\":\"[REDACTED]\""),
            (#"(?i)(unit[ _-]?id|serial(?: number)?|password|token|credential)\s*[:=]\s*\S+"#, "$1: [REDACTED]"),
            (#"/Users/[^/\s]+"#, "/Users/[REDACTED]"),
            (#"(?i)file://\S+"#, "[LOCAL FILE REDACTED]"),
            (#"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"#, "Bearer [REDACTED]")
        ]
        for (pattern, replacement) in replacements {
            result = result.replacingOccurrences(
                of: pattern,
                with: replacement,
                options: .regularExpression
            )
        }
        return result
    }
}

enum InstallationEvidenceOutcome: String, Codable, Sendable {
    case succeeded = "SUCCEEDED"
    case failed = "FAILED"
}

enum AutomaticFinishingResult: String, Codable, Sendable {
    case verified = "VERIFIED"
    case failed = "FAILED"
    case notReached = "NOT_REACHED"
}

enum EvidenceErrorCategory: String, Codable, CaseIterable, Sendable {
    case acquisition
    case transport
    case verification
    case storage
    case deviceDisconnected
    case sourceValidation
    case unknown
}

struct InstallationEvidenceEvent: Codable, Equatable, Identifiable, Sendable {
    static let schemaVersion = 1

    let schemaVersion: Int
    let id: UUID
    let timestamp: Date
    let model: String
    let family: String?
    let firmwareVersion: String?
    let usbVendorID: UInt16
    let usbProductID: UInt16
    let transport: String
    let provider: String
    let region: String
    let mapRelease: String
    let terentoVersion: String
    let macOSVersion: String
    let phaseOutcome: InstallationEvidenceOutcome
    let automaticFinishingResult: AutomaticFinishingResult
    let errorCategory: EvidenceErrorCategory?
    let deletionToken: String?

    init(
        id: UUID = UUID(),
        timestamp: Date = Date(),
        identity: DeviceIdentity,
        package: MapPackage,
        outcome: InstallationEvidenceOutcome,
        finishingResult: AutomaticFinishingResult,
        errorCategory: EvidenceErrorCategory? = nil,
        terentoVersion: String = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "development",
        macOSVersion: String = ProcessInfo.processInfo.operatingSystemVersionString,
        deletionToken: String = InstallationEvidenceEvent.makeDeletionToken()
    ) {
        self.schemaVersion = Self.schemaVersion
        self.id = id
        self.timestamp = timestamp
        self.model = identity.canonicalModel ?? identity.model
        self.family = identity.family
        self.firmwareVersion = identity.firmware
        self.usbVendorID = identity.usbVendorId
        self.usbProductID = identity.usbProductId
        self.transport = "MTP"
        self.provider = package.providerId
        // `regionId` is the provider's grouping region. Some catalog entries
        // share that group (for example AZORES and BALEARICS), so evidence
        // must use the concrete package identity to remain unambiguous.
        self.region = package.canonicalRegionId
        self.mapRelease = String(describing: package.version)
        self.terentoVersion = terentoVersion
        self.macOSVersion = macOSVersion
        self.phaseOutcome = outcome
        self.automaticFinishingResult = finishingResult
        self.errorCategory = errorCategory
        self.deletionToken = deletionToken
    }

    private static func makeDeletionToken() -> String {
        (UUID().uuidString + UUID().uuidString).replacingOccurrences(of: "-", with: "").lowercased()
    }
}

enum EvidenceConsentChoice: String, Codable, Sendable {
    case accepted
    case declined
}

struct VersionedEvidenceConsent: Codable, Equatable, Sendable {
    static let currentNoticeVersion = 2
    let noticeVersion: Int
    let choice: EvidenceConsentChoice
    let decidedAt: Date
}

struct CompatibilityEvidenceSummary: Equatable, Sendable {
    let attemptedInstallCount: Int
    let successfulInstallCount: Int
    let failedInstallCount: Int
    let successRate: Double
    let firmwareVersions: Set<String>
    let lastSuccessfulInstallation: Date?
    let lastFailure: Date?
    let errorCategories: [EvidenceErrorCategory: Int]
    let calculatedStatus: CompatibilityStatus
    let verifiedRequiresPhysicalDeviceReview: Bool
}

enum CompatibilityEvidenceCalculator {
    /// The denominator contains only started map writes that reached a final
    /// success or failure event. Polling, preflight conflicts, and cancellation
    /// before the write are never events and therefore never enter this count.
    static func summarize(
        _ events: [InstallationEvidenceEvent],
        forModel model: String,
        reviewedPhysicalDeviceCount: Int = 0
    ) -> CompatibilityEvidenceSummary {
        let matching = events.filter { $0.model == model }
        let successes = matching.filter {
            $0.phaseOutcome == .succeeded && $0.automaticFinishingResult == .verified
        }
        let failures = matching.filter { $0.phaseOutcome == .failed }
        let firmware = Set(successes.compactMap(\.firmwareVersion))
        let maximumSuccessesOnOneFirmware = Dictionary(
            grouping: successes.filter { !($0.firmwareVersion ?? "").isEmpty },
            by: { $0.firmwareVersion ?? "" }
        ).values.map(\.count).max() ?? 0
        let candidateVerified = successes.count >= 3 && firmware.count >= 2
        let status: CompatibilityStatus
        if candidateVerified && reviewedPhysicalDeviceCount >= 2 {
            status = .verified
        } else if maximumSuccessesOnOneFirmware >= 3 {
            status = .supported
        } else if !successes.isEmpty && !firmware.isEmpty {
            status = .tested
        } else {
            status = .unknown
        }

        return CompatibilityEvidenceSummary(
            attemptedInstallCount: matching.count,
            successfulInstallCount: successes.count,
            failedInstallCount: failures.count,
            successRate: matching.isEmpty ? 0 : Double(successes.count) / Double(matching.count),
            firmwareVersions: firmware,
            lastSuccessfulInstallation: successes.map(\.timestamp).max(),
            lastFailure: failures.map(\.timestamp).max(),
            errorCategories: Dictionary(grouping: failures.compactMap(\.errorCategory), by: { $0 })
                .mapValues(\.count),
            calculatedStatus: status,
            verifiedRequiresPhysicalDeviceReview: candidateVerified && reviewedPhysicalDeviceCount < 2
        )
    }
}

private struct InstallationEvidenceFile: Codable {
    var events: [InstallationEvidenceEvent] = []
    var pendingUploadEventIDs: [UUID] = []
    var uploadedEventIDs: [UUID]?
    var consent: VersionedEvidenceConsent?
}

final class LocalInstallationEvidenceStore: @unchecked Sendable {
    private let fileURL: URL
    private let lock = NSLock()
    private let encoder: JSONEncoder
    private let decoder = JSONDecoder()

    init(rootURL: URL? = nil) {
        let root = rootURL ?? FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first!.appendingPathComponent("Terento", isDirectory: true)
        fileURL = root.appendingPathComponent("installation-evidence.json")
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
    }

    func events() -> [InstallationEvidenceEvent] { lockedLoad().events }
    func consent() -> VersionedEvidenceConsent? { lockedLoad().consent }

    @discardableResult
    func append(_ event: InstallationEvidenceEvent, queueForUpload: Bool) throws -> Bool {
        try lock.withLock {
            var file = try loadUnlocked()
            guard !file.events.contains(where: { $0.id == event.id }) else { return false }
            file.events.append(event)
            if queueForUpload { file.pendingUploadEventIDs.append(event.id) }
            try saveUnlocked(file)
            return true
        }
    }

    func setConsent(_ choice: EvidenceConsentChoice, now: Date = Date()) throws {
        try lock.withLock {
            var file = try loadUnlocked()
            file.consent = VersionedEvidenceConsent(
                noticeVersion: VersionedEvidenceConsent.currentNoticeVersion,
                choice: choice,
                decidedAt: now
            )
            if choice == .declined {
                file.pendingUploadEventIDs.removeAll()
            }
            try saveUnlocked(file)
        }
    }

    func pendingUploads() -> [InstallationEvidenceEvent] {
        let file = lockedLoad()
        let ids = Set(file.pendingUploadEventIDs)
        return file.events.filter { ids.contains($0.id) }
    }

    func markUploaded(eventID: UUID) throws {
        try lock.withLock {
            var file = try loadUnlocked()
            file.pendingUploadEventIDs.removeAll { $0 == eventID }
            var uploaded = file.uploadedEventIDs ?? []
            if !uploaded.contains(eventID) {
                uploaded.append(eventID)
            }
            file.uploadedEventIDs = uploaded
            try saveUnlocked(file)
        }
    }

    func uploadedEvents() -> [InstallationEvidenceEvent] {
        let file = lockedLoad()
        let ids = Set(file.uploadedEventIDs ?? [])
        return file.events.filter { ids.contains($0.id) && $0.deletionToken != nil }
    }

    func markDeleted(eventID: UUID) throws {
        try lock.withLock {
            var file = try loadUnlocked()
            file.uploadedEventIDs?.removeAll { $0 == eventID }
            try saveUnlocked(file)
        }
    }

    private func lockedLoad() -> InstallationEvidenceFile {
        lock.withLock { (try? loadUnlocked()) ?? InstallationEvidenceFile() }
    }

    private func loadUnlocked() throws -> InstallationEvidenceFile {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return InstallationEvidenceFile()
        }
        return try decoder.decode(InstallationEvidenceFile.self, from: Data(contentsOf: fileURL))
    }

    private func saveUnlocked(_ file: InstallationEvidenceFile) throws {
        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try encoder.encode(file)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
    }
}

private extension NSLock {
    func withLock<T>(_ body: () throws -> T) rethrows -> T {
        lock(); defer { unlock() }
        return try body()
    }
}

protocol InstallationEvidenceUploading: Sendable {
    func upload(_ event: InstallationEvidenceEvent) async throws
    func delete(_ event: InstallationEvidenceEvent) async throws
}

enum InstallationEvidenceUploadError: LocalizedError, Equatable, Sendable {
    case invalidResponse
    case httpStatus(code: Int, body: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The compatibility service is temporarily unavailable."
        case let .httpStatus(code, _):
            switch code {
            case 408, 425, 429...:
                return "The compatibility service is temporarily unavailable."
            case 400..<500:
                return "The compatibility report could not be accepted."
            default:
                return "The compatibility report could not be sent."
            }
        }
    }

    var isRetryable: Bool {
        switch self {
        case .invalidResponse:
            return true
        case let .httpStatus(code, _):
            return code == 408 || code == 425 || code == 429 || code >= 500
        }
    }
}

struct HTTPInstallationEvidenceUploader: InstallationEvidenceUploading {
    let endpoint: URL

    init(endpoint: URL = URL(string: "https://api.terento.app/compatibility/events")!) {
        self.endpoint = endpoint
    }

    func upload(_ event: InstallationEvidenceEvent) async throws {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = try JSONEncoder.iso8601.encode(event)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw InstallationEvidenceUploadError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(decoding: data.prefix(512), as: UTF8.self)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            throw InstallationEvidenceUploadError.httpStatus(code: http.statusCode, body: body)
        }
    }

    func delete(_ event: InstallationEvidenceEvent) async throws {
        guard let deletionToken = event.deletionToken else {
            throw URLError(.userAuthenticationRequired)
        }
        var request = URLRequest(url: endpoint)
        request.httpMethod = "DELETE"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "id": event.id.uuidString.lowercased(),
            "deletionToken": deletionToken,
        ])
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw InstallationEvidenceUploadError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(decoding: data.prefix(512), as: UTF8.self)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            throw InstallationEvidenceUploadError.httpStatus(code: http.statusCode, body: body)
        }
    }
}

enum InstallationEvidenceUploadStatus: Equatable, Sendable {
    case idle
    case uploading(count: Int)
    case uploaded
    case waiting(count: Int, reason: String, willRetry: Bool)
}

enum InstallationEvidenceDeliveryStatus: Equatable, Sendable {
    case idle
    case notShared
    case sending(count: Int)
    case sent(count: Int)
    case queued(count: Int, reason: String, willRetry: Bool)
}

@MainActor
final class InstallationEvidenceController: ObservableObject {
    let store: LocalInstallationEvidenceStore
    private let uploader: any InstallationEvidenceUploading
    private let automaticRetryDelays: [UInt64]
    private var uploadTask: Task<Void, Never>?
    private var uploadTaskGeneration: UUID?
    private var activeUploadTask: Task<UploadAttemptResult, Never>?
    private var activeUploadTaskGeneration: UUID?
    @Published private(set) var uploadStatus: InstallationEvidenceUploadStatus = .idle
    @Published private(set) var latestDeliveryStatus: InstallationEvidenceDeliveryStatus = .idle

    init(
        store: LocalInstallationEvidenceStore = LocalInstallationEvidenceStore(),
        uploader: any InstallationEvidenceUploading = HTTPInstallationEvidenceUploader(),
        automaticRetryDelays: [UInt64] = [0, 5_000_000_000, 30_000_000_000]
    ) {
        self.store = store
        self.uploader = uploader
        self.automaticRetryDelays = automaticRetryDelays
        if let consent = store.consent(),
           consent.noticeVersion != VersionedEvidenceConsent.currentNoticeVersion {
            try? store.setConsent(.declined)
        }
        if uploadEnabled {
            schedulePendingUploadFlush()
        }
    }

    var uploadEnabled: Bool {
        currentConsentChoice == .accepted
    }

    var currentConsentChoice: EvidenceConsentChoice? {
        guard let consent = store.consent(),
              consent.noticeVersion == VersionedEvidenceConsent.currentNoticeVersion else {
            return nil
        }
        return consent.choice
    }

    /// One shared, persisted preference for Ready, About, and report delivery.
    /// No consent record means the visible first-install default is checked;
    /// the first installation commits that default as an explicit choice.
    var compatibilitySharingEnabled: Bool {
        currentConsentChoice != .declined
    }

    func decideConsent(_ choice: EvidenceConsentChoice) {
        objectWillChange.send()
        try? store.setConsent(choice)
        if choice == .accepted {
            schedulePendingUploadFlush()
        } else {
            uploadTask?.cancel()
            uploadTask = nil
            uploadTaskGeneration = nil
            uploadStatus = .idle
        }
    }

    /// Commits the visible default only when the user starts an installation.
    /// Existing decisions are already persisted by `decideConsent`.
    func commitCurrentSharingChoice() {
        guard currentConsentChoice == nil else { return }
        decideConsent(compatibilitySharingEnabled ? .accepted : .declined)
    }

    func resetLatestDeliveryStatus() {
        latestDeliveryStatus = .idle
    }

    func record(_ event: InstallationEvidenceEvent) {
        let upload = uploadEnabled
        guard (try? store.append(event, queueForUpload: upload)) == true else { return }
        if upload { schedulePendingUploadFlush() }
    }

    /// Records the events for the just-finished operation and waits for their
    /// first upload attempt. The existing background retry path remains in
    /// place, but the UI now gets a definitive immediate state for this
    /// operation instead of only seeing an aggregate queue state.
    @discardableResult
    func recordAndUpload(_ events: [InstallationEvidenceEvent]) async -> InstallationEvidenceDeliveryStatus {
        guard !events.isEmpty else {
            latestDeliveryStatus = .idle
            return .idle
        }

        let shouldUpload = uploadEnabled
        var insertedCount = 0
        do {
            for event in events {
                if try store.append(event, queueForUpload: shouldUpload) {
                    insertedCount += 1
                }
            }
        } catch {
            TerentoDiagnosticLog.recordCompatibilityReportDeliveryFailure(
                reportIDs: events.map(\.id),
                error: error,
                willRetry: false,
                pendingCount: store.pendingUploads().count
            )
            let status = InstallationEvidenceDeliveryStatus.queued(
                count: events.count,
                reason: "Could not save the compatibility report on this Mac: \(Self.userVisibleUploadError(error))",
                willRetry: false
            )
            latestDeliveryStatus = status
            return status
        }

        guard shouldUpload else {
            latestDeliveryStatus = .notShared
            return .notShared
        }

        uploadTask?.cancel()
        uploadTask = nil
        uploadTaskGeneration = nil
        latestDeliveryStatus = .sending(count: max(insertedCount, 1))

        let requestedIDs = Set(events.map(\.id))
        var result = await uploadPendingEventsOnce()

        // A scheduled upload may have taken a snapshot immediately before
        // these events were appended. If it completed without seeing them,
        // make one more pass so this operation is not reported as sent while
        // its own event is still pending.
        while result == .completed,
              !requestedIDs.isDisjoint(with: Set(store.pendingUploads().map(\.id))) {
            result = await uploadPendingEventsOnce()
        }

        let status = deliveryStatus(for: result, count: max(insertedCount, 1))
        latestDeliveryStatus = status
        if case let .queued(_, _, willRetry) = status, willRetry {
            schedulePendingUploadFlush()
        }
        return status
    }

    func flushPendingUploads() async {
        uploadTask?.cancel()
        uploadTask = nil
        uploadTaskGeneration = nil
        _ = await uploadPendingEventsOnce()
    }

    private func schedulePendingUploadFlush() {
        guard uploadEnabled, uploadTask == nil, !store.pendingUploads().isEmpty else {
            return
        }

        let retryDelays = automaticRetryDelays
        let generation = UUID()
        uploadTaskGeneration = generation
        uploadTask = Task { [weak self] in
            defer {
                if let self, self.uploadTaskGeneration == generation {
                    self.uploadTask = nil
                    self.uploadTaskGeneration = nil
                }
            }

            for delay in retryDelays {
                if delay > 0 {
                    do {
                        try await Task.sleep(nanoseconds: delay)
                    } catch {
                        return
                    }
                }

                guard !Task.isCancelled, let self, self.uploadEnabled else {
                    return
                }

                let result = await self.uploadPendingEventsOnce()
                switch result {
                case .empty, .completed, .permanentFailure:
                    return
                case .retryableFailure:
                    continue
                }
            }
        }
    }

    private enum UploadAttemptResult: Equatable {
        case empty
        case completed
        case retryableFailure
        case permanentFailure
    }

    private func uploadPendingEventsOnce() async -> UploadAttemptResult {
        if let activeUploadTask {
            return await activeUploadTask.value
        }

        let generation = UUID()
        activeUploadTaskGeneration = generation
        let task = Task { @MainActor [weak self] () -> UploadAttemptResult in
            guard let self else { return .empty }
            return await self.performUploadPendingEventsOnce()
        }
        activeUploadTask = task
        let result = await task.value
        if activeUploadTaskGeneration == generation {
            activeUploadTask = nil
            activeUploadTaskGeneration = nil
        }
        return result
    }

    private func performUploadPendingEventsOnce() async -> UploadAttemptResult {
        guard uploadEnabled else { return .empty }
        let pending = store.pendingUploads()
        guard !pending.isEmpty else {
            uploadStatus = .uploaded
            return .empty
        }

        uploadStatus = .uploading(count: pending.count)
        for event in pending {
            do {
                try await uploader.upload(event)
                try store.markUploaded(eventID: event.id)
            } catch {
                let remaining = store.pendingUploads().count
                let reason = Self.userVisibleUploadError(error)
                let willRetry = Self.isRetryable(error)
                TerentoDiagnosticLog.recordCompatibilityReportDeliveryFailure(
                    reportIDs: pending.map(\.id),
                    error: error,
                    willRetry: willRetry,
                    pendingCount: remaining
                )
                uploadStatus = .waiting(count: remaining, reason: reason, willRetry: willRetry)
                return willRetry ? .retryableFailure : .permanentFailure
            }
        }

        uploadStatus = .uploaded
        return .completed
    }

    private func deliveryStatus(
        for result: UploadAttemptResult,
        count: Int
    ) -> InstallationEvidenceDeliveryStatus {
        switch result {
        case .empty, .completed:
            return .sent(count: count)
        case .retryableFailure, .permanentFailure:
            if case let .waiting(_, reason, willRetry) = uploadStatus {
                return .queued(count: count, reason: reason, willRetry: willRetry)
            }
            return .queued(
                count: count,
                reason: "The compatibility report could not be sent.",
                willRetry: result == .retryableFailure
            )
        }
    }

    private static func isRetryable(_ error: Error) -> Bool {
        if let error = error as? InstallationEvidenceUploadError {
            return error.isRetryable
        }
        if let urlError = error as? URLError {
            return urlError.code != .userAuthenticationRequired
        }
        return true
    }

    private static func userVisibleUploadError(_ error: Error) -> String {
        if let uploadError = error as? InstallationEvidenceUploadError {
            return uploadError.errorDescription ?? "The compatibility report could not be sent."
        }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .userAuthenticationRequired:
                return "The compatibility report could not be accepted."
            default:
                return "The compatibility service is temporarily unavailable."
            }
        }
        return "The compatibility report could not be sent."
    }

    func deleteUploadedReports() async -> Int {
        var deleted = 0
        for event in store.uploadedEvents() {
            do {
                try await uploader.delete(event)
                try store.markDeleted(eventID: event.id)
                deleted += 1
            } catch {
                return deleted
            }
        }
        return deleted
    }
}

private extension JSONEncoder {
    static var iso8601: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

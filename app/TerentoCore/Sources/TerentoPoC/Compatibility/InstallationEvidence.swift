import Combine
import Foundation

enum DiagnosticReportSanitizer {
    static func sanitize(_ value: String) -> String {
        var result = value
        let replacements: [(String, String)] = [
            (#"(?i)\"(unit[ _-]?id|serial(?: number)?|password|token|credential)\"\s*:\s*\"[^\"]*\""#, "\"$1\":\"[REDACTED]\""),
            (#"(?i)(unit[ _-]?id|serial(?: number)?|password|token|credential|authorization|account|username|user name)\s*[:=]\s*[^\s&]+"#, "$1: [REDACTED]"),
            (#"/Users/\S+"#, "[LOCAL PATH REDACTED]"),
            (#"(?i)(?:^|\s)/(?:private|var|tmp|Volumes|home)/\S+"#, " [LOCAL PATH REDACTED]"),
            (#"(?i)[A-Z]:\\\\Users\\\\[^\\\s]+"#, "[LOCAL PATH REDACTED]"),
            (#"(?i)file://\S+"#, "[LOCAL FILE REDACTED]"),
            (#"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"#, "Bearer [REDACTED]"),
            (#"(?i)([?&](?:token|access_token|auth|authorization|signature|sig|key)=)[^&\s]+"#, "$1[REDACTED]")
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
    case notStarted = "NOT_STARTED"
}

enum EvidenceFailureStage: String, Codable, Sendable {
    case download, extract, preflight, write, verify, cleanup, manifest
    case sourceValidation = "source-validation"
}

enum EvidenceNativeFailureCode: String, Codable, Sendable {
    case targetAlreadyExists = "TARGET_ALREADY_EXISTS"
    case remoteFileMissing = "REMOTE_FILE_MISSING"
    case objectIDMismatch = "OBJECT_ID_MISMATCH"
    case unsupportedDevice = "UNSUPPORTED_DEVICE"
    case deviceDisconnected = "DEVICE_DISCONNECTED"
    case sendObjectFailed = "SEND_OBJECT_FAILED"
    case readbackFailed = "READBACK_FAILED"
    case deleteFailed = "DELETE_FAILED"
    case mtpOpenFailed = "MTP_OPEN_FAILED"
    case garminRootCountInvalid = "GARMIN_ROOT_COUNT_INVALID"
    case preflightMTPReadFailed = "PREFLIGHT_MTP_READ_FAILED"
    case liveIdentityMismatch = "LIVE_IDENTITY_MISMATCH"
    case stableWatchIdentityUnavailable = "STABLE_WATCH_IDENTITY_UNAVAILABLE"
    case garminDeviceXMLInvalid = "GARMIN_DEVICE_XML_INVALID"
}

enum EvidenceTransferProgressBucket: String, Codable, Sendable {
    case zero = "0"
    case oneToTwentyFour = "1-24"
    case twentyFiveToNinetyNine = "25-99"
    case complete = "100"

    init(bytes: UInt64, total: UInt64) {
        guard total > 0, bytes > 0 else { self = .zero; return }
        let percentage = min(100, Int((Double(bytes) / Double(total)) * 100))
        if percentage >= 100 { self = .complete }
        else if percentage >= 25 { self = .twentyFiveToNinetyNine }
        else { self = .oneToTwentyFour }
    }
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
    static let schemaVersion = 4

    let schemaVersion: Int
    let id: UUID
    let timestamp: Date
    let model: String
    let compatibilityIdentity: String
    let variant: String?
    let caseSizeMm: Int?
    let displayType: String?
    let canonicalDeviceId: String?
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
    let reconnectVerified: Bool
    let mapVisibleAfterReconnect: Bool
    let errorCategory: EvidenceErrorCategory?
    let rawMTPModel: String?
    let identityResolutionCode: String?
    let operationId: UUID?
    let mapResultIndex: Int?
    let selectedMapCount: Int?
    let appBuild: String?
    let releaseLabel: String?
    let failureStage: EvidenceFailureStage?
    let failureCode: String?
    let nativeFailureCode: EvidenceNativeFailureCode?
    let writeStarted: Bool?
    let remoteObjectCreated: Bool?
    let cleanupAttempted: Bool?
    let cleanupSucceeded: Bool?
    let transferProgressBucket: EvidenceTransferProgressBucket?

    init(
        id: UUID = UUID(),
        timestamp: Date = Date(),
        identity: DeviceIdentity,
        package: MapPackage,
        outcome: InstallationEvidenceOutcome,
        finishingResult: AutomaticFinishingResult,
        reconnectVerified: Bool = false,
        mapVisibleAfterReconnect: Bool = false,
        errorCategory: EvidenceErrorCategory? = nil,
        operationId: UUID = UUID(),
        mapResultIndex: Int = 0,
        selectedMapCount: Int = 1,
        appBuild: String = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "development",
        releaseLabel: String = Bundle.main.infoDictionary?["TerentoReleaseLabel"] as? String
            ?? Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
            ?? "development",
        failureStage: EvidenceFailureStage? = nil,
        failureCode: String? = nil,
        nativeFailureCode: EvidenceNativeFailureCode? = nil,
        writeStarted: Bool = true,
        remoteObjectCreated: Bool = false,
        cleanupAttempted: Bool = false,
        cleanupSucceeded: Bool = false,
        transferProgressBucket: EvidenceTransferProgressBucket = .zero,
        terentoVersion: String = (Bundle.main.infoDictionary?["TerentoReleaseLabel"] as? String)
            ?? (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String)
            ?? "development",
        macOSVersion: String = ProcessInfo.processInfo.operatingSystemVersionString
    ) {
        self.schemaVersion = Self.schemaVersion
        self.id = id
        self.timestamp = timestamp
        self.model = identity.canonicalModel ?? identity.presentationModel
        self.compatibilityIdentity = identity.compatibilityIdentity
        self.variant = identity.variant
        self.caseSizeMm = identity.caseSizeMm
        self.displayType = identity.displayType
        self.canonicalDeviceId = identity.reviewedCanonicalDeviceID
        self.family = identity.family
        self.firmwareVersion = identity.firmware
        self.usbVendorID = identity.usbVendorId
        self.usbProductID = identity.usbProductId
        self.transport = "MTP"
        if package.sourceKind == .custom {
            // A custom IMG has no trusted provider identity. Its canonical
            // region is derived from the local content hash, so never send
            // that value (or a local release guess) as compatibility evidence.
            self.provider = "custom"
            self.region = "custom"
            self.mapRelease = "custom"
        } else {
            self.provider = package.providerId
            // `regionId` is the provider's grouping region. Some catalog
            // entries share that group (for example AZORES and BALEARICS),
            // so evidence must use the concrete package identity to remain
            // unambiguous.
            self.region = package.canonicalRegionId
            self.mapRelease = String(describing: package.version)
        }
        self.terentoVersion = terentoVersion
        self.macOSVersion = macOSVersion
        self.phaseOutcome = outcome
        self.automaticFinishingResult = finishingResult
        self.reconnectVerified = reconnectVerified
        self.mapVisibleAfterReconnect = mapVisibleAfterReconnect
        self.errorCategory = errorCategory
        self.rawMTPModel = Self.sanitizedDiagnosticLabel(identity.model)
        self.identityResolutionCode = identity.localIdentityResolution.rawValue
        self.operationId = operationId
        self.mapResultIndex = mapResultIndex
        self.selectedMapCount = selectedMapCount
        self.appBuild = appBuild
        self.releaseLabel = releaseLabel
        self.failureStage = failureStage
        self.failureCode = failureCode
        self.nativeFailureCode = nativeFailureCode
        self.writeStarted = writeStarted
        self.remoteObjectCreated = remoteObjectCreated
        self.cleanupAttempted = cleanupAttempted
        self.cleanupSucceeded = cleanupSucceeded
        self.transferProgressBucket = transferProgressBucket
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion, id, timestamp, model, compatibilityIdentity, variant, caseSizeMm,
             displayType, canonicalDeviceId, family, firmwareVersion, usbVendorID, usbProductID, transport, provider, region,
             mapRelease, terentoVersion, macOSVersion, phaseOutcome, automaticFinishingResult,
             reconnectVerified, mapVisibleAfterReconnect, errorCategory
        case rawMTPModel, identityResolutionCode
        case operationId, mapResultIndex, selectedMapCount, appBuild, releaseLabel,
             failureStage, failureCode, nativeFailureCode, writeStarted, remoteObjectCreated,
             cleanupAttempted, cleanupSucceeded, transferProgressBucket
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decode(Int.self, forKey: .schemaVersion)
        id = try container.decode(UUID.self, forKey: .id)
        timestamp = try container.decode(Date.self, forKey: .timestamp)
        model = try container.decode(String.self, forKey: .model)
        compatibilityIdentity = try container.decodeIfPresent(String.self, forKey: .compatibilityIdentity) ?? model
        variant = try container.decodeIfPresent(String.self, forKey: .variant)
        caseSizeMm = try container.decodeIfPresent(Int.self, forKey: .caseSizeMm)
        displayType = try container.decodeIfPresent(String.self, forKey: .displayType)
        canonicalDeviceId = try container.decodeIfPresent(String.self, forKey: .canonicalDeviceId)
        family = try container.decodeIfPresent(String.self, forKey: .family)
        firmwareVersion = try container.decodeIfPresent(String.self, forKey: .firmwareVersion)
        usbVendorID = try container.decode(UInt16.self, forKey: .usbVendorID)
        usbProductID = try container.decode(UInt16.self, forKey: .usbProductID)
        transport = try container.decode(String.self, forKey: .transport)
        provider = try container.decode(String.self, forKey: .provider)
        region = try container.decode(String.self, forKey: .region)
        mapRelease = try container.decode(String.self, forKey: .mapRelease)
        terentoVersion = try container.decode(String.self, forKey: .terentoVersion)
        macOSVersion = try container.decode(String.self, forKey: .macOSVersion)
        phaseOutcome = try container.decode(InstallationEvidenceOutcome.self, forKey: .phaseOutcome)
        automaticFinishingResult = try container.decode(AutomaticFinishingResult.self, forKey: .automaticFinishingResult)
        reconnectVerified = try container.decodeIfPresent(Bool.self, forKey: .reconnectVerified) ?? false
        mapVisibleAfterReconnect = try container.decodeIfPresent(Bool.self, forKey: .mapVisibleAfterReconnect) ?? false
        errorCategory = try container.decodeIfPresent(EvidenceErrorCategory.self, forKey: .errorCategory)
        rawMTPModel = try container.decodeIfPresent(String.self, forKey: .rawMTPModel)
        identityResolutionCode = try container.decodeIfPresent(String.self, forKey: .identityResolutionCode)
        operationId = try container.decodeIfPresent(UUID.self, forKey: .operationId)
        mapResultIndex = try container.decodeIfPresent(Int.self, forKey: .mapResultIndex)
        selectedMapCount = try container.decodeIfPresent(Int.self, forKey: .selectedMapCount)
        appBuild = try container.decodeIfPresent(String.self, forKey: .appBuild)
        releaseLabel = try container.decodeIfPresent(String.self, forKey: .releaseLabel)
        failureStage = try container.decodeIfPresent(EvidenceFailureStage.self, forKey: .failureStage)
        failureCode = try container.decodeIfPresent(String.self, forKey: .failureCode)
        nativeFailureCode = try container.decodeIfPresent(EvidenceNativeFailureCode.self, forKey: .nativeFailureCode)
        writeStarted = try container.decodeIfPresent(Bool.self, forKey: .writeStarted)
        remoteObjectCreated = try container.decodeIfPresent(Bool.self, forKey: .remoteObjectCreated)
        cleanupAttempted = try container.decodeIfPresent(Bool.self, forKey: .cleanupAttempted)
        cleanupSucceeded = try container.decodeIfPresent(Bool.self, forKey: .cleanupSucceeded)
        transferProgressBucket = try container.decodeIfPresent(EvidenceTransferProgressBucket.self, forKey: .transferProgressBucket)
    }

    private static func sanitizedDiagnosticLabel(_ value: String) -> String? {
        let permittedScalars = value.unicodeScalars.filter {
            $0.value >= 32 && $0.value != 127
        }
        let sanitized = String(String.UnicodeScalarView(permittedScalars))
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sanitized.isEmpty else { return nil }
        return String(sanitized.prefix(160))
    }
}

enum EvidenceConsentChoice: String, Codable, Sendable {
    case accepted
    case declined
}

struct VersionedEvidenceConsent: Codable, Equatable, Sendable {
    static let currentNoticeVersion = 4
    let noticeVersion: Int
    let choice: EvidenceConsentChoice
    let decidedAt: Date
}

struct CompatibilityEvidenceSummary: Equatable, Sendable {
    let attemptedInstallCount: Int
    let successfulInstallCount: Int
    let reconnectVerifiedInstallCount: Int
    let failedInstallCount: Int
    let successRate: Double
    let firmwareVersions: Set<String>
    let lastSuccessfulInstallation: Date?
    let lastFailure: Date?
    let errorCategories: [EvidenceErrorCategory: Int]
}

enum CompatibilityEvidenceCalculator {
    /// The denominator contains only started map writes that reached a final
    /// success or failure event. Polling, preflight conflicts, and cancellation
    /// before the write are never events and therefore never enter this count.
    static func summarize(
        _ events: [InstallationEvidenceEvent],
        forModel model: String
    ) -> CompatibilityEvidenceSummary {
        // The identity key is exact. Legacy v1 events decode their missing
        // key as `model`, so this remains backwards-compatible without
        // allowing a base family label to absorb a sized variant.
        let matching = events.filter { $0.compatibilityIdentity == model }
        let operations = Dictionary(grouping: matching) { event in
            event.operationId?.uuidString ?? "legacy:\(event.id.uuidString)"
        }.values
        let writeStartedOperations = operations.filter { operation in
            operation.contains { $0.writeStarted ?? true }
        }
        let successes = writeStartedOperations.filter { operation in
            let expected = operation.compactMap(\.selectedMapCount).max() ?? 1
            return operation.count == expected && operation.allSatisfy {
                $0.phaseOutcome == .succeeded && $0.automaticFinishingResult == .verified
            }
        }
        let failures = writeStartedOperations.filter { operation in
            !successes.contains { successful in
                successful.first?.operationId == operation.first?.operationId
                    && successful.first?.id == operation.first?.id
            }
        }
        let successfulEvents = successes.flatMap { $0 }
        let failedEvents = failures.flatMap { $0 }.filter { $0.phaseOutcome == .failed }
        return CompatibilityEvidenceSummary(
            attemptedInstallCount: writeStartedOperations.count,
            successfulInstallCount: successes.count,
            reconnectVerifiedInstallCount: successes.filter { $0.contains(where: \.reconnectVerified) }.count,
            failedInstallCount: failures.count,
            successRate: writeStartedOperations.isEmpty ? 0 : Double(successes.count) / Double(writeStartedOperations.count),
            firmwareVersions: Set(successfulEvents.compactMap(\.firmwareVersion)),
            lastSuccessfulInstallation: successfulEvents.map(\.timestamp).max(),
            lastFailure: failedEvents.map(\.timestamp).max(),
            errorCategories: Dictionary(grouping: failedEvents.compactMap(\.errorCategory), by: { $0 })
                .mapValues(\.count)
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

    func migrateConsentToCurrentNotice() throws {
        try lock.withLock {
            var file = try loadUnlocked()
            guard let consent = file.consent,
                  consent.noticeVersion != VersionedEvidenceConsent.currentNoticeVersion else {
                return
            }
            file.consent = VersionedEvidenceConsent(
                noticeVersion: VersionedEvidenceConsent.currentNoticeVersion,
                choice: consent.choice,
                decidedAt: consent.decidedAt
            )
            if consent.choice == .declined {
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
        try? store.migrateConsentToCurrentNotice()
        if uploadEnabled {
            schedulePendingUploadFlush()
        }
    }

    var uploadEnabled: Bool {
        compatibilitySharingEnabled
    }

    var currentConsentChoice: EvidenceConsentChoice? {
        store.consent()?.choice
    }

    /// No consent record means privacy-minimised diagnostics are enabled by default.
    /// An explicit opt-out remains persisted across app updates.
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
        let previous = uploadTask
        previous?.cancel()
        await previous?.value
        uploadTask = nil
        uploadTaskGeneration = nil
        if await uploadPendingEventsOnce() == .retryableFailure {
            schedulePendingUploadFlush()
        }
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

}

private extension JSONEncoder {
    static var iso8601: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

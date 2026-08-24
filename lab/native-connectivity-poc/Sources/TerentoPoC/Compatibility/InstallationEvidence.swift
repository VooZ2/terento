import Combine
import Foundation

enum DiagnosticReportSanitizer {
    static func sanitize(_ value: String) -> String {
        var result = value
        let replacements: [(String, String)] = [
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
    var userConfirmed: Bool

    init(
        id: UUID = UUID(),
        timestamp: Date = Date(),
        identity: DeviceIdentity,
        package: MapPackage,
        outcome: InstallationEvidenceOutcome,
        finishingResult: AutomaticFinishingResult,
        errorCategory: EvidenceErrorCategory? = nil,
        userConfirmed: Bool = false,
        terentoVersion: String = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "development",
        macOSVersion: String = ProcessInfo.processInfo.operatingSystemVersionString
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
        self.region = package.regionId
        self.mapRelease = String(describing: package.version)
        self.terentoVersion = terentoVersion
        self.macOSVersion = macOSVersion
        self.phaseOutcome = outcome
        self.automaticFinishingResult = finishingResult
        self.errorCategory = errorCategory
        self.userConfirmed = userConfirmed
    }
}

enum EvidenceConsentChoice: String, Codable, Sendable {
    case accepted
    case declined
}

struct VersionedEvidenceConsent: Codable, Equatable, Sendable {
    static let currentNoticeVersion = 1
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
            try saveUnlocked(file)
        }
    }

    func confirm(eventID: UUID, queueForUpload: Bool) throws -> InstallationEvidenceEvent? {
        try lock.withLock {
            var file = try loadUnlocked()
            guard let index = file.events.firstIndex(where: { $0.id == eventID }) else { return nil }
            file.events[index].userConfirmed = true
            if queueForUpload && !file.pendingUploadEventIDs.contains(eventID) {
                file.pendingUploadEventIDs.append(eventID)
            }
            try saveUnlocked(file)
            return file.events[index]
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

struct HTTPInstallationEvidenceUploader: InstallationEvidenceUploading {
    let endpoint: URL

    init(endpoint: URL = URL(string: "https://api.terento.app/compatibility/events")!) {
        self.endpoint = endpoint
    }

    func upload(_ event: InstallationEvidenceEvent) async throws {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder.iso8601.encode(event)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}

@MainActor
final class InstallationEvidenceController: ObservableObject {
    @Published private(set) var latestSuccessfulEventID: UUID?
    @Published private(set) var latestEvent: InstallationEvidenceEvent?

    let store: LocalInstallationEvidenceStore
    private let uploader: any InstallationEvidenceUploading

    init(
        store: LocalInstallationEvidenceStore = LocalInstallationEvidenceStore(),
        uploader: any InstallationEvidenceUploading = HTTPInstallationEvidenceUploader()
    ) {
        self.store = store
        self.uploader = uploader
        latestEvent = store.events().last
        latestSuccessfulEventID = store.events().last(where: {
            $0.phaseOutcome == .succeeded && $0.automaticFinishingResult == .verified
        })?.id
        if store.consent()?.choice == .accepted {
            Task { await flushPendingUploads() }
        }
    }

    var requiresConsentDecision: Bool {
        guard let consent = store.consent() else { return true }
        return consent.noticeVersion != VersionedEvidenceConsent.currentNoticeVersion
    }

    var uploadEnabled: Bool {
        store.consent()?.choice == .accepted
    }

    func decideConsent(_ choice: EvidenceConsentChoice) {
        try? store.setConsent(choice)
    }

    func record(_ event: InstallationEvidenceEvent) {
        let upload = uploadEnabled
        guard (try? store.append(event, queueForUpload: upload)) == true else { return }
        latestEvent = event
        if event.phaseOutcome == .succeeded && event.automaticFinishingResult == .verified {
            latestSuccessfulEventID = event.id
        }
        if upload { Task { await flushPendingUploads() } }
    }

    func confirmLatestSuccessfulInstallation() {
        guard let id = latestSuccessfulEventID,
              let event = try? store.confirm(eventID: id, queueForUpload: uploadEnabled) else {
            return
        }
        latestEvent = event
        if uploadEnabled { Task { await flushPendingUploads() } }
    }

    func flushPendingUploads() async {
        guard uploadEnabled else { return }
        for event in store.pendingUploads() {
            do {
                try await uploader.upload(event)
                try store.markUploaded(eventID: event.id)
            } catch {
                // Evidence upload is deliberately best effort. The queue is
                // retained and installation state is never changed.
                return
            }
        }
    }
}

private extension JSONEncoder {
    static var iso8601: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

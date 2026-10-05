import Combine
import Foundation

/// First-run funnel telemetry (contracts/APP_FUNNEL_CONTRACT.md, schema v1).
///
/// Privacy-minimised and governed by the existing device-compatibility
/// reporting preference. Events carry no serial, Unit ID, account, path, IP or
/// persistent user/device identifier; `sessionId` is random per app launch and
/// lives only in memory.
enum AppFunnelStage: String, Codable, CaseIterable, Sendable {
    case deviceConnect = "DEVICE_CONNECT"
    case authorization = "AUTHORIZATION"
    case catalog = "CATALOG"
    case installBlocked = "INSTALL_BLOCKED"
}

/// Case names match `DeviceConnectOutcome` of the connect classifier so the
/// device engine's outcome can be forwarded with `init?(deviceConnectOutcome:)`.
enum AppFunnelDeviceConnectOutcome: String, CaseIterable, Sendable {
    case connected = "CONNECTED"
    case timeoutNoUSB = "TIMEOUT_NO_USB"
    case timeoutUSBPresent = "TIMEOUT_USB_PRESENT"
    case busy = "BUSY"
    case multipleDevices = "MULTIPLE_DEVICES"
    case notMTPMode = "NOT_MTP_MODE"
    case disconnected = "DISCONNECTED"
    case failed = "FAILED"

    /// Maps a connect-outcome case name (for example `DeviceConnectOutcome`'s
    /// raw value `"timeoutUSBPresent"`) to the funnel outcome.
    init?(deviceConnectOutcome name: String) {
        guard let match = Self.allCases.first(where: { "\($0)" == name }) else { return nil }
        self = match
    }
}

enum AppFunnelAuthorizationOutcome: String, CaseIterable, Sendable {
    case approved = "APPROVED"
    case pending = "PENDING"
    case outOfScope = "OUT_OF_SCOPE"
    case unknownModel = "UNKNOWN_MODEL"
    case ambiguous = "AMBIGUOUS"
    case catalogUnavailable = "CATALOG_UNAVAILABLE"
    case updateRequired = "UPDATE_REQUIRED"

    /// `nil` while authorization is still resolving.
    init?(_ state: InstallationAuthorizationState) {
        switch state {
        case .resolving: return nil
        case .approved: self = .approved
        case .blocked(let reason):
            switch reason {
            case .pending: self = .pending
            case .outOfScope, .notAuthorized: self = .outOfScope
            case .unknownModel: self = .unknownModel
            case .ambiguousCatalogMatch: self = .ambiguous
            case .catalogUnavailable: self = .catalogUnavailable
            case .updateRequired: self = .updateRequired
            }
        }
    }
}

enum AppFunnelCatalogOutcome: String, CaseIterable, Sendable {
    case remote = "REMOTE"
    case remotePartial = "REMOTE_PARTIAL"
    case bundledFallback = "BUNDLED_FALLBACK"
    case updateRequired = "UPDATE_REQUIRED"

    /// `nil` for a same-session cached catalog, which is neither a fresh
    /// remote result nor the bundled fallback.
    init?(source: MapCatalogSource, droppedPackageCount: Int) {
        switch source {
        case .remote: self = droppedPackageCount > 0 ? .remotePartial : .remote
        case .bundledFallback: self = .bundledFallback
        case .appUpdateRequired: self = .updateRequired
        case .cachedRemote: return nil
        }
    }
}

enum AppFunnelInstallBlockedReason: String, CaseIterable, Sendable {
    case authorization = "AUTHORIZATION"
    case deviceStorage = "DEVICE_STORAGE"
    case macStorage = "MAC_STORAGE"
    case catalogUnverified = "CATALOG_UNVERIFIED"
    case localCapability = "LOCAL_CAPABILITY"
    case other = "OTHER"

    /// Classifies a review-step block from the same inputs the review uses.
    static func forReview(
        plan: InstallationPlan,
        installationAuthorization: InstallationAuthorizationState,
        supportedInstallFlow: Bool
    ) -> Self? {
        if !plan.canContinue {
            if plan.selectedItems.contains(where: {
                if case let .blocked(_, reason) = $0.acquisitionAvailability {
                    return reason == "STATUS_UNVERIFIED" || reason == "APP_UPDATE_REQUIRED"
                }
                return false
            }) { return .catalogUnverified }
            return plan.storagePlan.status == .blockedInsufficientSpace ? .deviceStorage : .other
        }
        if !installationAuthorization.canInstall { return .authorization }
        if !supportedInstallFlow { return .localCapability }
        return nil
    }

    /// Classifies an Install press that stopped before any device write.
    static func forAcquisition(_ error: Error) -> Self {
        if error is InstallationAuthorizationAcquisitionError { return .authorization }
        guard let acquisition = error as? MapAcquisitionError else { return .other }
        switch acquisition {
        case .acquisitionWithheld(.blocked(_, let reason))
            where reason == "STATUS_UNVERIFIED" || reason == "APP_UPDATE_REQUIRED":
            return .catalogUnverified
        case .workspaceFailed:
            return .macStorage
        default:
            return .other
        }
    }

    /// Classifies a no-write preflight result that blocked installation.
    static func forPreflight(_ failure: InstallationFailure?) -> Self {
        switch failure {
        case .insufficientSpace: return .deviceStorage
        case .installationAuthorization, .installationAuthorizationUnavailable: return .authorization
        case .stableWatchIdentityUnavailable, .unknownInstallTarget: return .localCapability
        default: return .other
        }
    }
}

/// Random per app launch; never persisted.
enum AppFunnelSession {
    static let id = UUID()
}

struct AppFunnelEvent: Codable, Equatable, Identifiable, Sendable {
    static let schemaVersion = 1
    static let maximumBaseModelLength = 80

    let schemaVersion: Int
    let id: UUID
    let sessionId: UUID
    let occurredAt: Date
    let appBuild: String
    let releaseLabel: String
    let stage: AppFunnelStage
    let outcome: String
    let baseModel: String?
    let droppedPackageCount: Int?

    private init(stage: AppFunnelStage, outcome: String, baseModel: String?, droppedPackageCount: Int?,
                 id: UUID, sessionId: UUID, occurredAt: Date, appBuild: String, releaseLabel: String) {
        schemaVersion = Self.schemaVersion
        self.id = id
        self.sessionId = sessionId
        self.occurredAt = occurredAt
        self.appBuild = String(appBuild.prefix(80))
        self.releaseLabel = String(releaseLabel.prefix(80))
        self.stage = stage
        self.outcome = outcome
        self.baseModel = baseModel
        self.droppedPackageCount = droppedPackageCount
    }

    /// `baseModel` is kept only for a successful connection and authorization.
    static func deviceConnect(_ outcome: AppFunnelDeviceConnectOutcome, baseModel: String?,
                              context: AppFunnelEventContext) -> Self {
        Self(stage: .deviceConnect, outcome: outcome.rawValue,
             baseModel: outcome == .connected ? sanitizedBaseModel(baseModel) : nil,
             droppedPackageCount: nil, context: context)
    }

    static func authorization(_ outcome: AppFunnelAuthorizationOutcome, baseModel: String?,
                              context: AppFunnelEventContext) -> Self {
        Self(stage: .authorization, outcome: outcome.rawValue, baseModel: sanitizedBaseModel(baseModel),
             droppedPackageCount: nil, context: context)
    }

    /// `droppedPackageCount` is kept only for a partial remote catalog.
    static func catalog(_ outcome: AppFunnelCatalogOutcome, droppedPackageCount: Int?,
                        context: AppFunnelEventContext) -> Self {
        Self(stage: .catalog, outcome: outcome.rawValue, baseModel: nil,
             droppedPackageCount: outcome == .remotePartial ? max(0, droppedPackageCount ?? 0) : nil,
             context: context)
    }

    static func installBlocked(_ reason: AppFunnelInstallBlockedReason,
                               context: AppFunnelEventContext) -> Self {
        Self(stage: .installBlocked, outcome: reason.rawValue, baseModel: nil,
             droppedPackageCount: nil, context: context)
    }

    private init(stage: AppFunnelStage, outcome: String, baseModel: String?, droppedPackageCount: Int?,
                 context: AppFunnelEventContext) {
        self.init(stage: stage, outcome: outcome, baseModel: baseModel,
                  droppedPackageCount: droppedPackageCount, id: UUID(), sessionId: context.sessionID,
                  occurredAt: context.now, appBuild: context.appBuild, releaseLabel: context.releaseLabel)
    }

    /// A normalized Garmin base model such as `fenix 8`; never a raw device
    /// label, serial or path.
    static func sanitizedBaseModel(_ value: String?) -> String? {
        guard let value else { return nil }
        let normalized = GarminDeviceModelNormalizer.normalize(value)
        guard !normalized.isEmpty else { return nil }
        return String(normalized.prefix(maximumBaseModelLength))
    }

    /// Session de-duplication key: one event per (stage, outcome, baseModel).
    var sessionKey: String { "\(stage.rawValue)|\(outcome)|\(baseModel ?? "")" }
}

struct AppFunnelEventContext: Sendable {
    let sessionID: UUID
    let now: Date
    let appBuild: String
    let releaseLabel: String
}

struct ParkedAppFunnelEvent: Codable, Equatable, Sendable {
    let event: AppFunnelEvent
    let rejection: TelemetryRejection
}

private struct AppFunnelQueueFile: Codable {
    var pendingEvents: [AppFunnelEvent] = []
    var parkedEvents: [ParkedAppFunnelEvent]?
}

private extension NSLock {
    func withFunnelLock<T>(_ body: () throws -> T) rethrows -> T {
        lock()
        defer { unlock() }
        return try body()
    }
}

/// Durable funnel outbox. The same parking rules as the other telemetry
/// queues apply; pending events also expire after the retention window and
/// the outbox keeps at most `maximumPendingEvents` (oldest dropped first).
final class LocalAppFunnelEventStore: @unchecked Sendable {
    static let maximumPendingEvents = 1000

    private let fileURL: URL
    private let lock = NSLock()
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(rootURL: URL? = nil) {
        let root = rootURL ?? FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first!.appendingPathComponent("Terento", isDirectory: true)
        fileURL = root.appendingPathComponent("app-funnel-events.json")
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
    }

    func pendingEvents() -> [AppFunnelEvent] { lockedLoad().pendingEvents }
    func parkedEvents() -> [ParkedAppFunnelEvent] { lockedLoad().parkedEvents ?? [] }

    func parkedEventsEligibleForRetry(now: Date, appBuild: String) -> [AppFunnelEvent] {
        parkedEvents()
            .filter { TelemetryDeliveryPolicy.isEligibleForRetry($0.rejection, now: now, appBuild: appBuild) }
            .map(\.event)
    }

    func append(_ event: AppFunnelEvent) throws {
        try lock.withFunnelLock {
            var file = try loadUnlocked()
            guard !file.pendingEvents.contains(where: { $0.id == event.id }) else { return }
            file.pendingEvents.append(event)
            if file.pendingEvents.count > Self.maximumPendingEvents {
                file.pendingEvents.removeFirst(file.pendingEvents.count - Self.maximumPendingEvents)
            }
            try saveUnlocked(file)
        }
    }

    func markUploaded(eventID: UUID) throws {
        try lock.withFunnelLock {
            var file = try loadUnlocked()
            file.pendingEvents.removeAll { $0.id == eventID }
            file.parkedEvents?.removeAll { $0.event.id == eventID }
            try saveUnlocked(file)
        }
    }

    func park(eventID: UUID, statusCode: Int, now: Date, appBuild: String) throws {
        try lock.withFunnelLock {
            var file = try loadUnlocked()
            var parked = file.parkedEvents ?? []
            if let index = parked.firstIndex(where: { $0.event.id == eventID }) {
                parked[index] = ParkedAppFunnelEvent(event: parked[index].event,
                    rejection: TelemetryDeliveryPolicy.rejection(after: parked[index].rejection,
                        statusCode: statusCode, now: now, appBuild: appBuild))
            } else if let event = file.pendingEvents.first(where: { $0.id == eventID }) {
                parked.append(ParkedAppFunnelEvent(event: event,
                    rejection: TelemetryDeliveryPolicy.rejection(after: nil,
                        statusCode: statusCode, now: now, appBuild: appBuild)))
            } else {
                return
            }
            file.pendingEvents.removeAll { $0.id == eventID }
            if parked.count > TelemetryDeliveryPolicy.maximumParkedEvents {
                parked.removeFirst(parked.count - TelemetryDeliveryPolicy.maximumParkedEvents)
            }
            file.parkedEvents = parked
            try saveUnlocked(file)
        }
    }

    func expire(now: Date) throws {
        try lock.withFunnelLock {
            var file = try loadUnlocked()
            let pending = file.pendingEvents.filter {
                now.timeIntervalSince($0.occurredAt) <= TelemetryDeliveryPolicy.retentionInterval
            }
            let parked = file.parkedEvents?.filter {
                !TelemetryDeliveryPolicy.isExpired($0.rejection, occurredAt: $0.event.occurredAt, now: now)
            }
            guard pending.count != file.pendingEvents.count
                    || parked?.count != file.parkedEvents?.count else { return }
            file.pendingEvents = pending
            file.parkedEvents = parked
            try saveUnlocked(file)
        }
    }

    /// Opt-out removes every queued funnel event.
    func clear() throws {
        try lock.withFunnelLock {
            guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
            try saveUnlocked(AppFunnelQueueFile())
        }
    }

    private func lockedLoad() -> AppFunnelQueueFile {
        lock.withFunnelLock { (try? loadUnlocked()) ?? AppFunnelQueueFile() }
    }

    private func loadUnlocked() throws -> AppFunnelQueueFile {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return AppFunnelQueueFile() }
        return try decoder.decode(AppFunnelQueueFile.self, from: Data(contentsOf: fileURL))
    }

    private func saveUnlocked(_ file: AppFunnelQueueFile) throws {
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        try encoder.encode(file).write(to: fileURL, options: [.atomic, .completeFileProtection])
    }
}

protocol AppFunnelEventUploading: Sendable {
    func upload(_ event: AppFunnelEvent) async throws
}

enum AppFunnelUploadError: Error, Equatable, Sendable {
    case invalidResponse
    case httpStatus(Int)
}

struct HTTPAppFunnelEventUploader: AppFunnelEventUploading {
    let endpoint: URL

    init(endpoint: URL = URL(string: "https://api.terento.app/app-funnel/events")!) {
        self.endpoint = endpoint
    }

    func upload(_ event: AppFunnelEvent) async throws {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = try AppFunnelEventEncoding.encoder().encode(event)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw AppFunnelUploadError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else { throw AppFunnelUploadError.httpStatus(http.statusCode) }
    }
}

enum AppFunnelEventEncoding {
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}

/// Producer and sender for funnel events. Recording is a no-op while the
/// device-compatibility reporting preference is declined; declining clears the
/// queue. At most one event per (stage, outcome, baseModel) is recorded per
/// app session.
@MainActor
final class AppFunnelTelemetryController {
    let store: LocalAppFunnelEventStore
    private let uploader: any AppFunnelEventUploading
    private let sharingEnabled: @Sendable () -> Bool
    private let retryDelays: [UInt64]
    private let now: @Sendable () -> Date
    private let appBuild: String
    private let releaseLabel: String
    private let sessionID: UUID
    private var recordedSessionKeys = Set<String>()
    private var uploadTask: Task<Void, Never>?
    #if TERENTO_TESTING
    func scheduledUploadForTesting() -> Task<Void, Never>? { uploadTask }
    #endif

    init(
        store: LocalAppFunnelEventStore = LocalAppFunnelEventStore(),
        uploader: any AppFunnelEventUploading = HTTPAppFunnelEventUploader(),
        sharingEnabled: @escaping @Sendable () -> Bool,
        retryDelays: [UInt64] = [0, 5_000_000_000, 30_000_000_000],
        now: @escaping @Sendable () -> Date = { Date() },
        appBuild: String = TerentoTelemetryMetadata.eventBuild,
        releaseLabel: String = TerentoTelemetryMetadata.releaseLabel,
        sessionID: UUID = AppFunnelSession.id
    ) {
        self.store = store
        self.uploader = uploader
        self.sharingEnabled = sharingEnabled
        self.retryDelays = retryDelays
        self.now = now
        self.appBuild = appBuild
        self.releaseLabel = releaseLabel
        self.sessionID = sessionID
        if sharingEnabled() { scheduleFlush() } else { try? store.clear() }
    }

    private var context: AppFunnelEventContext {
        AppFunnelEventContext(sessionID: sessionID, now: now(), appBuild: appBuild, releaseLabel: releaseLabel)
    }

    // MARK: Producer API

    /// Hook for the connect classifier (for example the device engine's
    /// `connectOutcomeHandler`). `baseModel` is used only for `.connected`.
    func recordDeviceConnect(_ outcome: AppFunnelDeviceConnectOutcome, baseModel: String? = nil) {
        record(.deviceConnect(outcome, baseModel: baseModel, context: context))
    }

    /// Records a resolved authorization; `.resolving` is ignored.
    func recordAuthorization(_ state: InstallationAuthorizationState, baseModel: String?) {
        guard let outcome = AppFunnelAuthorizationOutcome(state) else { return }
        record(.authorization(outcome, baseModel: baseModel, context: context))
    }

    func recordCatalog(source: MapCatalogSource, droppedPackageCount: Int) {
        guard let outcome = AppFunnelCatalogOutcome(source: source, droppedPackageCount: droppedPackageCount) else { return }
        record(.catalog(outcome, droppedPackageCount: droppedPackageCount, context: context))
    }

    func recordInstallBlocked(_ reason: AppFunnelInstallBlockedReason) {
        record(.installBlocked(reason, context: context))
    }

    /// Called when device-compatibility reporting is turned off.
    func sharingDeclined() {
        uploadTask?.cancel()
        uploadTask = nil
        try? store.clear()
    }

    func record(_ event: AppFunnelEvent) {
        guard sharingEnabled() else {
            try? store.clear()
            return
        }
        guard recordedSessionKeys.insert(event.sessionKey).inserted else { return }
        // Persist before returning; delivery runs separately and cannot
        // affect device, catalog or installation state.
        try? store.append(event)
        scheduleFlush()
    }

    // MARK: Delivery

    func flushPendingEvents() async {
        let previous = uploadTask
        previous?.cancel()
        await previous?.value
        uploadTask = nil
        if await uploadOnce() == .retryableFailure { scheduleFlush() }
    }

    private func scheduleFlush() {
        guard sharingEnabled(), uploadTask == nil,
              !store.pendingEvents().isEmpty
                || !store.parkedEventsEligibleForRetry(now: now(), appBuild: appBuild).isEmpty else { return }
        let delays = retryDelays
        uploadTask = Task { [weak self] in
            defer { self?.uploadTask = nil }
            for delay in delays {
                if delay > 0 {
                    do { try await Task.sleep(nanoseconds: delay) } catch { return }
                }
                guard !Task.isCancelled, let self else { return }
                switch await self.uploadOnce() {
                case .completed, .stopped: return
                case .retryableFailure: continue
                }
            }
        }
    }

    private enum UploadResult { case completed, retryableFailure, stopped }

    private func uploadOnce() async -> UploadResult {
        guard sharingEnabled() else {
            try? store.clear()
            return .stopped
        }
        let currentTime = now()
        try? store.expire(now: currentTime)
        let pending = store.pendingEvents()
        let parked = store.parkedEventsEligibleForRetry(now: currentTime, appBuild: appBuild)
        for event in pending + parked {
            guard sharingEnabled(), !Task.isCancelled else { return .stopped }
            do {
                try await uploader.upload(event)
                try store.markUploaded(eventID: event.id)
            } catch {
                guard sharingEnabled(), !Task.isCancelled else { return .stopped }
                if case let AppFunnelUploadError.httpStatus(code) = error,
                   TelemetryDeliveryPolicy.isNonRetryableRejection(statusCode: code) {
                    do {
                        try store.park(eventID: event.id, statusCode: code, now: now(), appBuild: appBuild)
                        continue
                    } catch {
                        return .stopped
                    }
                }
                if let urlError = error as? URLError, urlError.code == .userAuthenticationRequired {
                    return .stopped
                }
                return .retryableFailure
            }
        }
        return .completed
    }
}

/// Wires funnel stages that are observable from existing published state.
/// Connect outcomes are inferred from `DeviceEngine` transitions until the
/// connect classifier forwards them through `recordDeviceConnect` directly.
@MainActor
final class AppFunnelStateObserver {
    private let funnel: AppFunnelTelemetryController
    private var cancellables = Set<AnyCancellable>()
    private var lastDeviceState: DeviceConnectionState

    init(funnel: AppFunnelTelemetryController, deviceEngine: DeviceEngine, mapEngine: MapEngine) {
        self.funnel = funnel
        lastDeviceState = deviceEngine.state

        deviceEngine.$state
            .receive(on: RunLoop.main)
            .sink { [weak self, weak deviceEngine] state in
                guard let self, let deviceEngine else { return }
                let previous = self.lastDeviceState
                self.lastDeviceState = state
                guard let outcome = AppFunnelConnectTransition.outcome(
                    from: previous, to: state,
                    readingMessage: deviceEngine.readingMessage,
                    userErrorMessage: deviceEngine.userErrorMessage) else { return }
                let baseModel = deviceEngine.compatibility.flatMap {
                    InstallationAuthorizationClient.funnelBaseModel(for: $0.identity)
                }
                self.funnel.recordDeviceConnect(outcome, baseModel: baseModel)
            }
            .store(in: &cancellables)

        // A resolved policy is assigned while the device snapshot exists; the
        // placeholder reset on connect/disconnect clears the snapshot first.
        deviceEngine.$installationAuthorization
            .sink { [weak self, weak deviceEngine] authorization in
                guard let self, let deviceEngine, deviceEngine.snapshot != nil,
                      let identity = deviceEngine.compatibility?.identity else { return }
                self.funnel.recordAuthorization(authorization,
                    baseModel: InstallationAuthorizationClient.funnelBaseModel(for: identity))
            }
            .store(in: &cancellables)

        mapEngine.$catalogSource
            .sink { [weak self, weak mapEngine] source in
                guard let self, let mapEngine, let source else { return }
                self.funnel.recordCatalog(source: source,
                    droppedPackageCount: mapEngine.catalogDroppedPackageCount)
            }
            .store(in: &cancellables)
    }
}

/// Infers connect outcomes from the published device state of today's
/// detection flow. Pure, so the mapping is testable without hardware.
enum AppFunnelConnectTransition {
    static let timeoutReadingMessage = "Connection timed out after 2 minutes."
    static let disconnectReadingMessage = "Your Garmin was disconnected. Connect it again to continue."

    static func outcome(
        from previous: DeviceConnectionState,
        to state: DeviceConnectionState,
        readingMessage: String,
        userErrorMessage: String?
    ) -> AppFunnelDeviceConnectOutcome? {
        guard previous != state else { return nil }
        switch (previous, state) {
        case (.detecting, .connected), (.detecting, .ready):
            return .connected
        case (.detecting, .failed):
            guard readingMessage == timeoutReadingMessage else { return .failed }
            return userErrorMessage == UserFacingErrorMessage.forConnectionTimeout(
                garminUSBPresent: false, detectedConflicts: [])
                ? .timeoutNoUSB : .timeoutUSBPresent
        case (.connected, .disconnected), (.ready, .disconnected):
            return readingMessage == disconnectReadingMessage ? .disconnected : nil
        default:
            return nil
        }
    }
}

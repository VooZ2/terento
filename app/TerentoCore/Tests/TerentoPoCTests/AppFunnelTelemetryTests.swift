import Foundation

// Whole-app test binaries have no SwiftPM resource bundle.
extension Bundle { static var module: Bundle { .main } }

private actor FunnelUploadRecorder: AppFunnelEventUploading {
    private let rejected: [AppFunnelStage: Int]
    private var failuresRemaining: Int
    private(set) var attempts: [AppFunnelEvent] = []
    private(set) var delivered: [AppFunnelEvent] = []

    init(rejected: [AppFunnelStage: Int] = [:], failuresRemaining: Int = 0) {
        self.rejected = rejected
        self.failuresRemaining = failuresRemaining
    }

    func upload(_ event: AppFunnelEvent) async throws {
        attempts.append(event)
        if failuresRemaining > 0 {
            failuresRemaining -= 1
            throw URLError(.notConnectedToInternet)
        }
        if let status = rejected[event.stage] { throw AppFunnelUploadError.httpStatus(status) }
        delivered.append(event)
    }

    func deliveredEvents() -> [AppFunnelEvent] { delivered }
    func attemptedEvents() -> [AppFunnelEvent] { attempts }
}

private final class SharingSwitch: @unchecked Sendable {
    private let lock = NSLock()
    private var value = true
    var enabled: Bool { lock.lock(); defer { lock.unlock() }; return value }
    func set(_ newValue: Bool) { lock.lock(); value = newValue; lock.unlock() }
}

@main
struct AppFunnelTelemetryTests {
    static let allowedKeys: Set<String> = [
        "schemaVersion", "id", "sessionId", "occurredAt", "appBuild", "releaseLabel",
        "stage", "outcome", "baseModel", "droppedPackageCount"
    ]

    @MainActor
    static func main() async throws {
        let watchdog = Task.detached {
            try await Task.sleep(nanoseconds: 20_000_000_000)
            fputs("FAIL: app funnel tests exceeded 20 seconds\n", stderr)
            exit(1)
        }
        defer { watchdog.cancel() }
        try testPayloadShapeAndFixtures()
        testOutcomeMappings()
        testConnectTransitionInference()
        try await testSessionDeduplicationAndDurableQueue()
        try await testConsentGovernsTheFunnel()
        try await testParkingAndRetryableDelivery()
        print("PASS: app funnel payload, mapping, session de-duplication, consent and delivery tests")
    }

    static func root() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }

    static func context() -> AppFunnelEventContext {
        AppFunnelEventContext(sessionID: UUID(uuidString: "11111111-2222-4333-8444-555555555555")!,
            now: Date(timeIntervalSince1970: 1_790_000_000), appBuild: "41-local",
            releaseLabel: "1.0.0-beta.19-local")
    }

    static func testPayloadShapeAndFixtures() throws {
        let ctx = context()
        var events: [AppFunnelEvent] = []
        for outcome in AppFunnelDeviceConnectOutcome.allCases {
            events.append(.deviceConnect(outcome, baseModel: "Garmin fēnix 8", context: ctx))
        }
        for outcome in AppFunnelAuthorizationOutcome.allCases {
            events.append(.authorization(outcome, baseModel: "Forerunner 965", context: ctx))
        }
        for outcome in AppFunnelCatalogOutcome.allCases {
            events.append(.catalog(outcome, droppedPackageCount: 3, context: ctx))
        }
        for reason in AppFunnelInstallBlockedReason.allCases {
            events.append(.installBlocked(reason, context: ctx))
        }
        let encoder = AppFunnelEventEncoding.encoder()
        for event in events {
            let json = try JSONSerialization.jsonObject(with: encoder.encode(event)) as! [String: Any]
            expect(Set(json.keys).isSubset(of: allowedKeys), "payload uses only schema-v1 fields")
            expect(json["schemaVersion"] as? Int == 1 && json["sessionId"] as? String == ctx.sessionID.uuidString,
                "schema version and the memory-only session ID are present")
            expect((json["occurredAt"] as? String)?.hasSuffix("Z") == true,
                "occurredAt is an RFC 3339 UTC timestamp")
            expect(json["releaseLabel"] as? String == "1.0.0-beta.19-local" && json["appBuild"] as? String == "41-local",
                "local builds keep the -local release label that excludes them from statistics")
            let mayCarryModel = event.stage == .authorization
                || (event.stage == .deviceConnect && event.outcome == "CONNECTED")
            expect((json["baseModel"] != nil) == mayCarryModel,
                "baseModel appears only for a successful connection and authorization")
            expect((json["droppedPackageCount"] != nil) == (event.outcome == "REMOTE_PARTIAL"),
                "droppedPackageCount appears only for a partial remote catalog")
            let text = String(decoding: try encoder.encode(event), as: UTF8.self).lowercased()
            for forbidden in ["serial", "unit", "/users/", "path", "account", "deviceid"] {
                expect(!text.contains(forbidden), "payload excludes \(forbidden)")
            }
        }
        expect(events.first?.baseModel == "garmin fenix 8"
            && AppFunnelEvent.sanitizedBaseModel(String(repeating: "a", count: 120))?.count == 80
            && AppFunnelEvent.sanitizedBaseModel("  ") == nil,
            "base models are normalized and bounded to 80 characters")
        if let path = ProcessInfo.processInfo.environment["TERENTO_APP_FUNNEL_EVENT_FIXTURES"] {
            try encoder.encode(events).write(to: URL(fileURLWithPath: path), options: .atomic)
        }
    }

    static func testOutcomeMappings() {
        expect(AppFunnelAuthorizationOutcome(.resolving) == nil, "resolving authorization is not an outcome")
        let pairs: [(InstallationAuthorizationBlockReason, AppFunnelAuthorizationOutcome)] = [
            (.pending, .pending), (.outOfScope, .outOfScope), (.notAuthorized, .outOfScope),
            (.unknownModel, .unknownModel), (.ambiguousCatalogMatch, .ambiguous),
            (.catalogUnavailable, .catalogUnavailable), (.updateRequired, .updateRequired)
        ]
        for (reason, outcome) in pairs {
            expect(AppFunnelAuthorizationOutcome(.blocked(reason)) == outcome, "\(reason) maps to \(outcome.rawValue)")
        }
        expect(AppFunnelCatalogOutcome(source: .remote, droppedPackageCount: 0) == .remote
            && AppFunnelCatalogOutcome(source: .remote, droppedPackageCount: 2) == .remotePartial
            && AppFunnelCatalogOutcome(source: .bundledFallback, droppedPackageCount: 0) == .bundledFallback
            && AppFunnelCatalogOutcome(source: .appUpdateRequired, droppedPackageCount: 0) == .updateRequired
            && AppFunnelCatalogOutcome(source: .cachedRemote, droppedPackageCount: 0) == nil,
            "catalog load results map to REMOTE, REMOTE_PARTIAL, BUNDLED_FALLBACK and UPDATE_REQUIRED")
        for (name, outcome) in [("connected", AppFunnelDeviceConnectOutcome.connected),
                                ("timeoutNoUSB", .timeoutNoUSB), ("timeoutUSBPresent", .timeoutUSBPresent),
                                ("busy", .busy), ("multipleDevices", .multipleDevices),
                                ("notMTPMode", .notMTPMode), ("disconnected", .disconnected), ("failed", .failed)] {
            expect(AppFunnelDeviceConnectOutcome(deviceConnectOutcome: name) == outcome,
                "connect classifier case \(name) forwards to \(outcome.rawValue)")
        }
        expect(AppFunnelDeviceConnectOutcome(deviceConnectOutcome: "unknown") == nil, "unknown connect names are ignored")
        expect(AppFunnelInstallBlockedReason.forPreflight(.insufficientSpace) == .deviceStorage
            && AppFunnelInstallBlockedReason.forPreflight(.installationAuthorization) == .authorization
            && AppFunnelInstallBlockedReason.forPreflight(.stableWatchIdentityUnavailable) == .localCapability
            && AppFunnelInstallBlockedReason.forPreflight(.existingMapConflict) == .other,
            "preflight blocks map to the funnel reasons")
        expect(AppFunnelInstallBlockedReason.forAcquisition(MapAcquisitionError.acquisitionWithheld(
                .blocked(provider: "X", reason: "APP_UPDATE_REQUIRED"))) == .catalogUnverified
            && AppFunnelInstallBlockedReason.forAcquisition(MapAcquisitionError.acquisitionWithheld(
                .blocked(provider: "X", reason: "STATUS_UNVERIFIED"))) == .catalogUnverified
            && AppFunnelInstallBlockedReason.forAcquisition(MapAcquisitionError.workspaceFailed("disk")) == .macStorage
            && AppFunnelInstallBlockedReason.forAcquisition(InstallationAuthorizationAcquisitionError(
                authorization: .blocked(.pending))) == .authorization,
            "acquisition refusals map to the funnel reasons")
    }

    static func testConnectTransitionInference() {
        let noUSB = UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: false, detectedConflicts: [])
        let timeout = AppFunnelConnectTransition.timeoutReadingMessage
        expect(AppFunnelConnectTransition.outcome(from: .detecting, to: .ready, readingMessage: "", userErrorMessage: nil) == .connected,
            "a completed detection is CONNECTED")
        expect(AppFunnelConnectTransition.outcome(from: .detecting, to: .failed, readingMessage: timeout, userErrorMessage: noUSB) == .timeoutNoUSB,
            "a timeout without a Garmin on USB is TIMEOUT_NO_USB")
        expect(AppFunnelConnectTransition.outcome(from: .detecting, to: .failed, readingMessage: timeout,
                userErrorMessage: UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: true, detectedConflicts: [])) == .timeoutUSBPresent,
            "a timeout with a Garmin on USB is TIMEOUT_USB_PRESENT")
        expect(AppFunnelConnectTransition.outcome(from: .detecting, to: .failed, readingMessage: "x", userErrorMessage: "y") == .failed,
            "another detection failure is FAILED")
        expect(AppFunnelConnectTransition.outcome(from: .ready, to: .disconnected,
                readingMessage: AppFunnelConnectTransition.disconnectReadingMessage, userErrorMessage: nil) == .disconnected,
            "an unexpected disconnect is DISCONNECTED")
        expect(AppFunnelConnectTransition.outcome(from: .detecting, to: .disconnected, readingMessage: "stopped", userErrorMessage: nil) == nil
            && AppFunnelConnectTransition.outcome(from: .ready, to: .ejecting, readingMessage: "", userErrorMessage: nil) == nil
            && AppFunnelConnectTransition.outcome(from: .safeToDisconnect, to: .disconnected, readingMessage: "", userErrorMessage: nil) == nil,
            "user cancellation and safe eject are not connect outcomes")
    }

    @MainActor
    static func testSessionDeduplicationAndDurableQueue() async throws {
        let directory = root()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LocalAppFunnelEventStore(rootURL: directory)
        let uploader = FunnelUploadRecorder(failuresRemaining: 100)
        let session = UUID()
        let funnel = AppFunnelTelemetryController(store: store, uploader: uploader, sharingEnabled: { true },
            retryDelays: [], appBuild: "41-local", releaseLabel: "1.0.0-beta.19-local", sessionID: session)
        funnel.recordDeviceConnect(.connected, baseModel: "fenix 8")
        funnel.recordDeviceConnect(.connected, baseModel: "fenix 8")
        funnel.recordDeviceConnect(.connected, baseModel: "Forerunner 965")
        funnel.recordAuthorization(.blocked(.pending), baseModel: "fenix 8")
        funnel.recordAuthorization(.blocked(.pending), baseModel: "fenix 8")
        funnel.recordAuthorization(.resolving, baseModel: "fenix 8")
        funnel.recordCatalog(source: .remote, droppedPackageCount: 4)
        funnel.recordCatalog(source: .remote, droppedPackageCount: 4)
        funnel.recordInstallBlocked(.authorization)
        funnel.recordInstallBlocked(.authorization)
        let pending = store.pendingEvents()
        expect(pending.count == 5, "one event per (stage, outcome, baseModel) per session is queued durably")
        expect(Set(pending.map(\.sessionId)) == [session], "every event of a launch carries one session ID")
        expect(pending.first { $0.stage == .catalog }?.droppedPackageCount == 4,
            "the partial catalog event carries the dropped package count")
        let restarted = LocalAppFunnelEventStore(rootURL: directory)
        expect(restarted.pendingEvents().map(\.id) == pending.map(\.id),
            "queued funnel events survive a restart while delivery is unavailable")
        let nextLaunch = AppFunnelTelemetryController(store: restarted, uploader: FunnelUploadRecorder(),
            sharingEnabled: { true }, retryDelays: [], sessionID: UUID())
        nextLaunch.recordDeviceConnect(.connected, baseModel: "fenix 8")
        expect(restarted.pendingEvents().filter { $0.stage == .deviceConnect }.count >= 3,
            "a new launch is a new session and may report the same outcome again")
    }

    @MainActor
    static func testConsentGovernsTheFunnel() async throws {
        let directory = root()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LocalAppFunnelEventStore(rootURL: directory)
        let sharing = SharingSwitch()
        let uploader = FunnelUploadRecorder(failuresRemaining: 100)
        let funnel = AppFunnelTelemetryController(store: store, uploader: uploader,
            sharingEnabled: { sharing.enabled }, retryDelays: [])
        funnel.recordCatalog(source: .bundledFallback, droppedPackageCount: 0)
        expect(store.pendingEvents().count == 1, "enabled device-compatibility reporting queues funnel events")
        sharing.set(false)
        funnel.sharingDeclined()
        expect(store.pendingEvents().isEmpty, "declining device-compatibility reporting clears the funnel queue")
        funnel.recordInstallBlocked(.deviceStorage)
        expect(store.pendingEvents().isEmpty, "nothing is recorded while reporting is declined")

        let evidenceRoot = root()
        defer { try? FileManager.default.removeItem(at: evidenceRoot) }
        let evidence = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: evidenceRoot),
            automaticRetryDelays: [])
        let evidenceStore = evidence.store
        let shared = AppFunnelTelemetryController(store: store, uploader: FunnelUploadRecorder(failuresRemaining: 100),
            sharingEnabled: { evidenceStore.consent()?.choice != .declined }, retryDelays: [])
        evidence.onSharingDeclined = { [weak shared] in shared?.sharingDeclined() }
        shared.recordDeviceConnect(.busy)
        expect(store.pendingEvents().count == 1, "the funnel follows the shared compatibility preference")
        evidence.decideConsent(.declined)
        expect(store.pendingEvents().isEmpty, "the compatibility opt-out also clears funnel events")
    }

    @MainActor
    static func testParkingAndRetryableDelivery() async throws {
        let directory = root()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LocalAppFunnelEventStore(rootURL: directory)
        let uploader = FunnelUploadRecorder(rejected: [.deviceConnect: 404])
        let funnel = AppFunnelTelemetryController(store: store, uploader: uploader, sharingEnabled: { true },
            retryDelays: [0])
        funnel.recordDeviceConnect(.timeoutUSBPresent)
        funnel.recordAuthorization(.blocked(.updateRequired), baseModel: "fenix 8")
        funnel.recordCatalog(source: .appUpdateRequired, droppedPackageCount: 0)
        await funnel.flushPendingEvents()
        let delivered = await uploader.deliveredEvents()
        expect(delivered.map(\.stage) == [.authorization, .catalog],
            "a rejected funnel event is parked and later events are still delivered in order")
        expect(store.pendingEvents().isEmpty && store.parkedEvents().map(\.event.stage) == [.deviceConnect]
            && store.parkedEvents().first?.rejection.statusCode == 404,
            "the rejected event is parked with its status before the API route exists")

        let offlineRoot = root()
        defer { try? FileManager.default.removeItem(at: offlineRoot) }
        let offlineStore = LocalAppFunnelEventStore(rootURL: offlineRoot)
        let offline = AppFunnelTelemetryController(store: offlineStore, uploader: FunnelUploadRecorder(failuresRemaining: 100),
            sharingEnabled: { true }, retryDelays: [])
        offline.recordInstallBlocked(.macStorage)
        await offline.flushPendingEvents()
        expect(offlineStore.pendingEvents().count == 1 && offlineStore.parkedEvents().isEmpty,
            "retryable network failures keep the event pending and never park it")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else {
            fputs("FAIL: \(message)\n", stderr)
            exit(1)
        }
        print("PASS: \(message)")
    }
}

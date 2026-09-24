import Foundation

private actor MapStatisticsUploadRecorder: MapStatisticsEventUploading {
    private var failuresRemaining: Int
    private(set) var events: [MapStatisticsEvent] = []

    init(failuresRemaining: Int = 0) {
        self.failuresRemaining = failuresRemaining
    }

    func upload(_ event: MapStatisticsEvent) async throws {
        if failuresRemaining > 0 {
            failuresRemaining -= 1
            throw URLError(.cannotConnectToHost)
        }
        events.append(event)
    }

    func uploadedEvents() -> [MapStatisticsEvent] { events }
}

/// Hold the first response until a second event is durably queued. No network
/// or scheduler delay determines when the tested interleaving occurs.
private actor GatedMapStatisticsUploader: MapStatisticsEventUploading {
    private var firstResponse: CheckedContinuation<Void, Never>?
    private var calls: [MapStatisticsEvent] = []
    private let failure: MapStatisticsUploadError?
    private var failuresRemaining: Int

    init(failure: MapStatisticsUploadError? = nil, failuresRemaining: Int = 0) {
        self.failure = failure
        self.failuresRemaining = failuresRemaining
    }

    func upload(_ event: MapStatisticsEvent) async throws {
        calls.append(event)
        if calls.count == 1 {
            await withCheckedContinuation { firstResponse = $0 }
        }
        if failuresRemaining > 0, let failure {
            failuresRemaining -= 1
            throw failure
        }
    }

    func waitingForFirstResponse() -> Bool { firstResponse != nil }
    func releaseFirstResponse() { firstResponse?.resume(); firstResponse = nil }
    func attemptedEvents() -> [MapStatisticsEvent] { calls }
}

@main
struct MapStatisticsEventTests {
    static let package = MapPackage(
        id: "opentopomap-lithuania",
        providerId: "opentopomap",
        regionId: "LTU",
        name: "Lithuania",
        version: MapVersion(year: 2026, month: 8)!,
        sizeBytes: 123,
        sourceURL: URL(string: "https://example.invalid/map.zip"),
        releaseDate: nil,
        identifier: "LTU"
    )

    @MainActor
    static func main() async throws {
        let watchdog = Task.detached {
            try await Task.sleep(nanoseconds: 10_000_000_000)
            fputs("FAIL: map statistics asynchronous tests exceeded 10 seconds\n", stderr)
            exit(1)
        }
        defer { watchdog.cancel() }
        try await testEventsQueuedDuringUpload()
        try await testQueuedEventsRespectRetryPolicy()
        try await testOptOutDuringUpload()
        try await testJournalWriteRecovery()
        try testAcquisitionJournal()
        try testPayloadAndOperationIdentity()
        try testCustomMapPrivacyBoundary()
        try await testCustomMapStatsNeverUpload()
        try testQueueAndIdempotency()
        await testSeparateOptInAndRetry()
        print("PASS: map usage diagnostics payload, privacy, default-on queue, retry, and idempotency tests")
    }

    @MainActor
    static func testJournalWriteRecovery() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        // A regular file in place of the directory makes atomic saves fail.
        try Data("blocked".utf8).write(to: root)
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let uploader = MapStatisticsUploadRecorder()
        let controller = MapStatisticsEventController(store: store, uploader: uploader, retryDelays: [0])
        let start = MapStatisticsEvent(operationId: UUID(), package: package,
            eventType: .downloadStarted, outcome: .unknown,
            acquisitionId: UUID(), componentKind: .main)
        let end = start.phase(.downloadFailed)
        controller.record(start)
        controller.record(end)
        await controller.scheduledUploadForTesting()?.value
        expect(controller.uploadStatus == .waiting(2, willRetry: true), "disk failure is visible and retains both events")
        try FileManager.default.removeItem(at: root)
        await controller.flushPendingEvents()
        let events = await uploader.uploadedEvents()
        expect(events.map(\.id) == [start.id, end.id], "disk recovery retains IDs and start/terminal order")
        try store.reconcileInterruptedAcquisitions()
        expect(store.pendingEvents().isEmpty, "saved terminal closes journal before sending; restart cannot invent interruption")
    }

    static func testAcquisitionJournal() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let operation = UUID()
        func start(_ kind: MapArtifactKind = .main) -> MapStatisticsEvent {
            MapStatisticsEvent(operationId: operation, package: package,
                eventType: .downloadStarted, outcome: .unknown,
                acquisitionId: UUID(), componentKind: kind)
        }
        let main = start(), contours = start(.contours)
        try store.appendIfSharingEnabled(main)
        try store.appendIfSharingEnabled(contours)
        try store.markUploaded(eventID: main.id)
        try store.appendIfSharingEnabled(main.phase(.downloadProcessing))
        try store.appendIfSharingEnabled(main.phase(.downloadSucceeded))
        // Simulate process death/restart after the start was already delivered.
        let restarted = LocalMapStatisticsEventStore(rootURL: root)
        try restarted.reconcileInterruptedAcquisitions()
        let recovered = restarted.pendingEvents().filter { $0.eventType == .downloadInterrupted }
        expect(recovered.count == 1 && recovered[0].acquisitionId == contours.acquisitionId,
               "restart interrupts only the unfinished contour component")
        expect(recovered[0].providerId == "opentopomap" && recovered[0].operationId == operation,
               "recovery preserves provider and operation without converting to custom")
        try restarted.reconcileInterruptedAcquisitions()
        expect(restarted.pendingEvents().filter { $0.eventType == .downloadInterrupted }.map(\.id) == recovered.map(\.id),
               "repeated recovery retains exactly one durable event ID")
        for terminal in [MapStatisticsEventType.downloadCancelled, .downloadInterrupted, .downloadFailed, .downloadSucceeded] {
            let event = start()
            try restarted.appendIfSharingEnabled(event)
            let ended = event.phase(terminal)
            let saved = try restarted.appendIfSharingEnabled(ended)
            expect(saved, "terminal event persists")
            let lateFailure = try restarted.appendIfSharingEnabled(event.phase(.downloadFailed))
            expect(!lateFailure, "late callbacks cannot create a second terminal")
            let latePhase = try restarted.appendIfSharingEnabled(event.phase(.downloadProcessing))
            expect(!latePhase, "late phase cannot reopen a completed acquisition")
            try restarted.markUploaded(eventID: ended.id)
        }
        let optedOut = start()
        try restarted.appendIfSharingEnabled(optedOut)
        try restarted.setConsent(.declined)
        try restarted.reconcileInterruptedAcquisitions()
        try restarted.setConsent(.accepted)
        let oldCallback = try restarted.appendIfSharingEnabled(optedOut.phase(.downloadCancelled))
        expect(!oldCallback, "opt-out clears journal; re-enable cannot revive old acquisition")
        expect(restarted.pendingEvents().isEmpty, "opt-out clears pending events and recovery")
        print("PASS: durable acquisition completion, cancellation, interruption, recovery, components and opt-out")
    }

    static func testPayloadAndOperationIdentity() throws {
        var fixtureRoot = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { fixtureRoot.deleteLastPathComponent() }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let shared = try decoder.decode(MapStatisticsEvent.self, from: Data(contentsOf:
            fixtureRoot.appendingPathComponent("contracts/fixtures/map-event.valid-acquisition.json")))
        expect(shared.eventType == .downloadInterrupted && shared.componentKind == .contours
            && shared.acquisitionId != nil, "shared API fixture preserves component interruption")
        let operationID = UUID()
        let first = MapStatisticsEvent(
            operationId: operationID,
            package: package,
            eventType: .downloadSucceeded,
            outcome: .succeeded,
            mapResultIndex: 2,
            appBuild: "7-local",
            releaseLabel: "1.0.0-beta.10-local"
        )
        let second = MapStatisticsEvent(
            operationId: operationID,
            package: package,
            eventType: .installSucceeded,
            outcome: .succeeded,
            appBuild: "7-local",
            releaseLabel: "1.0.0-beta.10-local"
        )
        expect(first.operationId == second.operationId, "one user operation keeps one operationId")
        expect(first.id != second.id, "each event keeps its own idempotency ID")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let output = ProcessInfo.processInfo.environment["TERENTO_MAP_EVENT_FIXTURE_OUTPUT"] {
            try encoder.encode([first, second]).write(to: URL(fileURLWithPath: output), options: .atomic)
        }
        let payload = String(decoding: try encoder.encode(first), as: UTF8.self)
        for field in ["schemaVersion", "id", "operationId", "providerId", "mapId", "region", "mapResultIndex", "eventType", "outcome", "timestamp", "appBuild", "releaseLabel"] {
            expect(payload.contains("\"\(field)\""), "payload includes \(field)")
        }
        expect(first.releaseLabel == "1.0.0-beta.10-local", "map events carry the local release label")
        expect(first.operationId == second.operationId, "all package events share the operation ID")
        for forbidden in ["device", "serial", "unitId", "filePath", "manifest", "diagnostic", "sourceURL", "/Users/"] {
            expect(!payload.lowercased().contains(forbidden.lowercased()), "payload excludes \(forbidden)")
        }
    }

    static func testCustomMapPrivacyBoundary() throws {
        let custom = MapPackage(
            id: "custom-sha256-secret-local-fingerprint",
            providerId: "custom",
            regionId: "LOCAL-PATH",
            name: "private-map.img",
            version: MapVersion(year: 2026, month: 8)!,
            sizeBytes: 1,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil,
            sourceKind: .custom
        )
        let event = MapStatisticsEvent(
            operationId: UUID(),
            package: custom,
            eventType: .installSucceeded,
            outcome: .succeeded
        )
        expect(event.providerId == "custom", "custom provider uses a coarse label")
        expect(event.mapId == "custom-map", "custom local identity is redacted")
        expect(event.region == nil, "custom local region is not shared")
    }

    @MainActor
    static func testCustomMapStatsNeverUpload() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let uploader = MapStatisticsUploadRecorder()
        let controller = MapStatisticsEventController(
            store: store,
            uploader: uploader,
            retryDelays: []
        )
        controller.decideConsent(.accepted)
        let custom = MapPackage(
            id: "custom-stale-local-fingerprint",
            providerId: "custom",
            regionId: "custom",
            name: "Custom map",
            version: MapVersion(year: 2000, month: 1)!,
            sizeBytes: 1,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil,
            sourceKind: .custom
        )
        let event = MapStatisticsEvent(
            operationId: UUID(),
            package: custom,
            eventType: .installSucceeded,
            outcome: .succeeded
        )
        try store.append(event)
        await controller.flushPendingEvents()
        expect(store.pendingEvents().isEmpty, "stale custom map-statistics events are discarded locally")
        let uploaded = await uploader.uploadedEvents()
        expect(uploaded.isEmpty, "custom IMG events never reach the map-statistics uploader")
    }

    static func testQueueAndIdempotency() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let event = MapStatisticsEvent(
            operationId: UUID(),
            package: package,
            eventType: .downloadStarted,
            outcome: .unknown
        )
        expect(store.consent() == nil, "new map usage diagnostics have no persisted opt-out")
        let inserted = try store.append(event)
        let duplicated = try store.append(event)
        expect(inserted, "new event enters the local queue")
        expect(!duplicated, "duplicate idempotency ID is rejected")
        expect(store.pendingEvents().count == 1, "queue contains one event")
        try store.markUploaded(eventID: event.id)
        expect(store.pendingEvents().isEmpty, "uploaded event leaves the queue")
    }

    @MainActor
    static func testSeparateOptInAndRetry() async {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let uploader = MapStatisticsUploadRecorder(failuresRemaining: 1)
        let controller = MapStatisticsEventController(
            store: store,
            uploader: uploader,
            retryDelays: [0, 1_000_000]
        )
        let event = MapStatisticsEvent(
            operationId: UUID(),
            package: package,
            eventType: .installSucceeded,
            outcome: .succeeded
        )

        expect(controller.sharingEnabled, "new map usage diagnostics are enabled by default")
        controller.record(event)
        for _ in 0..<50 {
            if !(await uploader.uploadedEvents()).isEmpty { break }
            try? await Task.sleep(nanoseconds: 5_000_000)
        }
        let uploadedAfterRetry = await uploader.uploadedEvents()
        expect(uploadedAfterRetry.map(\.id) == [event.id], "retry uploads the same idempotent event")
        expect(store.pendingEvents().isEmpty, "successful retry clears the queue")

        controller.decideConsent(.declined)
        expect(!controller.sharingEnabled, "map usage diagnostics remain independently reversible")
    }


    @MainActor
    private static func waitForFirstResponse(_ uploader: GatedMapStatisticsUploader) async {
        while !(await uploader.waitingForFirstResponse()) { await Task.yield() }
    }

    @MainActor
    static func testEventsQueuedDuringUpload() async throws {
        for (type, outcome) in [
            (MapStatisticsEventType.downloadSucceeded, MapStatisticsEventOutcome.succeeded),
            (.downloadFailed, .failed), (.installSucceeded, .succeeded), (.installFailed, .failed),
            (.mapUpdateSucceeded, .succeeded), (.mapUpdateFailed, .failed)
        ] {
            let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: root) }
            let store = LocalMapStatisticsEventStore(rootURL: root)
            let uploader = GatedMapStatisticsUploader()
            let controller = MapStatisticsEventController(store: store, uploader: uploader)
            let operation = UUID()
            let start = MapStatisticsEvent(operationId: operation, package: package,
                                          eventType: .downloadStarted, outcome: .unknown)
            let terminal = MapStatisticsEvent(operationId: operation, package: package,
                                             eventType: type, outcome: outcome)
            controller.record(start)
            await waitForFirstResponse(uploader)
            let sending = controller.scheduledUploadForTesting()
            expect(sending != nil, "record starts the real automatic sender")
            controller.record(terminal)
            await controller.scheduledRecordForTesting()?.value
            expect(store.pendingEvents().count == 2, "terminal event is durably queued before the first response")
            await uploader.releaseFirstResponse()
            await sending?.value
            let attempts = await uploader.attemptedEvents()
            expect(attempts.map(\.id) == [start.id, terminal.id],
                   "automatic sender delivers an event queued during an in-flight upload")
            expect(store.pendingEvents().isEmpty && controller.uploadStatus == .uploaded,
                   "uploaded means all queued outcomes were delivered")
            await controller.flushPendingEvents()
            let afterFlush = await uploader.attemptedEvents()
            expect(afterFlush.map(\.id) == attempts.map(\.id), "a drained queue is not sent again")
        }
    }

    @MainActor
    static func testQueuedEventsRespectRetryPolicy() async throws {
        for (failure, failures, expectedAttempts, expectedPending) in [
            (MapStatisticsUploadError.httpStatus(503), 1, 3, 0),
            (.httpStatus(503), 10, 2, 2),
            (.httpStatus(400), 10, 1, 2)
        ] {
            let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: root) }
            let store = LocalMapStatisticsEventStore(rootURL: root)
            let uploader = GatedMapStatisticsUploader(failure: failure, failuresRemaining: failures)
            let controller = MapStatisticsEventController(store: store, uploader: uploader, retryDelays: [0, 0])
            let operation = UUID()
            let start = MapStatisticsEvent(operationId: operation, package: package,
                                          eventType: .downloadStarted, outcome: .unknown)
            let terminal = MapStatisticsEvent(operationId: operation, package: package,
                                             eventType: .downloadFailed, outcome: .failed)
            controller.record(start)
            await waitForFirstResponse(uploader)
            let sending = controller.scheduledUploadForTesting()
            controller.record(terminal)
            await controller.scheduledRecordForTesting()?.value
            expect(store.pendingEvents().count == 2, "terminal event is durably queued before the first response")
            await uploader.releaseFirstResponse()
            await sending?.value
            let attempts = await uploader.attemptedEvents()
            expect(attempts.count == expectedAttempts, "draining respects retry bounds and permanent failures")
            expect(attempts.first?.id == start.id, "retries preserve the start event identity")
            expect(store.pendingEvents().count == expectedPending, "unsent outcomes remain durable after failure")
            if expectedPending == 0 {
                expect(attempts.map(\.id) == [start.id, start.id, terminal.id], "retry preserves IDs and drains the outcome")
            } else {
                expect(attempts.allSatisfy { $0.id == start.id }, "failed first event does not skip ahead or spin")
                expect(controller.uploadStatus == .waiting(2, willRetry: failure.isRetryable),
                       "failed delivery never reports uploaded")
            }
        }
    }

    @MainActor
    static func testOptOutDuringUpload() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let operation = UUID()
        let start = MapStatisticsEvent(operationId: operation, package: package,
                                      eventType: .downloadStarted, outcome: .unknown)
        let terminal = MapStatisticsEvent(operationId: operation, package: package,
                                         eventType: .downloadFailed, outcome: .failed)
        // Both events are in the sender's initial snapshot before opt-out.
        try store.append(start)
        try store.append(terminal)
        let uploader = GatedMapStatisticsUploader()
        let controller = MapStatisticsEventController(store: store, uploader: uploader)
        await waitForFirstResponse(uploader)
        let sending = controller.scheduledUploadForTesting()
        controller.decideConsent(.declined)
        await uploader.releaseFirstResponse()
        await sending?.value
        let attempts = await uploader.attemptedEvents()
        expect(attempts.map(\.id) == [start.id], "opt-out prevents sending the remaining snapshot")
        expect(store.pendingEvents().isEmpty && controller.uploadStatus == .idle,
               "a late response cannot replace opted-out idle state with uploaded")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else {
            fputs("FAIL: \(message)\n", stderr)
            exit(1)
        }
    }
}

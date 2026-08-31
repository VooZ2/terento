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
        try testPayloadAndOperationIdentity()
        try testCustomMapPrivacyBoundary()
        try testQueueAndIdempotency()
        await testSeparateOptInAndRetry()
        print("PASS: map statistics payload, privacy, consent, queue, retry, and idempotency tests")
    }

    static func testPayloadAndOperationIdentity() throws {
        let operationID = UUID()
        let first = MapStatisticsEvent(
            operationId: operationID,
            package: package,
            eventType: .downloadSucceeded,
            outcome: .succeeded,
            appBuild: "7"
        )
        let second = MapStatisticsEvent(
            operationId: operationID,
            package: package,
            eventType: .installSucceeded,
            outcome: .succeeded,
            appBuild: "7"
        )
        expect(first.operationId == second.operationId, "one user operation keeps one operationId")
        expect(first.id != second.id, "each event keeps its own idempotency ID")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let payload = String(decoding: try encoder.encode(first), as: UTF8.self)
        for field in ["schemaVersion", "id", "operationId", "providerId", "mapId", "region", "eventType", "outcome", "timestamp", "appBuild"] {
            expect(payload.contains("\"\(field)\""), "payload includes \(field)")
        }
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

    static func testQueueAndIdempotency() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let event = MapStatisticsEvent(
            operationId: UUID(),
            package: package,
            eventType: .downloadStarted,
            outcome: .unknown
        )
        expect(store.consent() == nil, "statistics have no implicit consent")
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

        controller.record(event)
        try? await Task.sleep(nanoseconds: 20_000_000)
        expect(store.pendingEvents().isEmpty, "default-off statistics do not collect an event")
        let uploadedBeforeConsent = await uploader.uploadedEvents()
        expect(uploadedBeforeConsent.isEmpty, "default-off statistics do not upload")

        controller.decideConsent(.accepted)
        controller.record(event)
        for _ in 0..<50 {
            if !(await uploader.uploadedEvents()).isEmpty { break }
            try? await Task.sleep(nanoseconds: 5_000_000)
        }
        let uploadedAfterRetry = await uploader.uploadedEvents()
        expect(uploadedAfterRetry.map(\.id) == [event.id], "retry uploads the same idempotent event")
        expect(store.pendingEvents().isEmpty, "successful retry clears the queue")

        controller.decideConsent(.declined)
        expect(!controller.sharingEnabled, "statistics consent remains independent and reversible")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else {
            fputs("FAIL: \(message)\n", stderr)
            exit(1)
        }
    }
}

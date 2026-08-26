import Foundation

private actor UploadRecorder: InstallationEvidenceUploading {
    let shouldFail: Bool
    var failuresRemaining: Int
    private(set) var uploaded: [UUID] = []
    private(set) var deleted: [UUID] = []
    init(shouldFail: Bool = false, failuresRemaining: Int = 0) {
        self.shouldFail = shouldFail
        self.failuresRemaining = failuresRemaining
    }
    func upload(_ event: InstallationEvidenceEvent) async throws {
        if shouldFail || failuresRemaining > 0 {
            if failuresRemaining > 0 { failuresRemaining -= 1 }
            throw URLError(.cannotConnectToHost)
        }
        uploaded.append(event.id)
    }
    func delete(_ event: InstallationEvidenceEvent) async throws {
        if shouldFail { throw URLError(.cannotConnectToHost) }
        deleted.append(event.id)
    }
    func count() -> Int { uploaded.count }
    func deletionCount() -> Int { deleted.count }
}

@main
struct InstallationEvidenceTests {
    @MainActor
    static func main() async throws {
        try testEventStorageAndDuplicatePrevention()
        testStatisticsAndPromotionThresholds()
        try await testConsentAndUploadIsolation()
        testDiagnosticSanitization()
        print("PASS: installation evidence, privacy, consent, upload, report, and promotion tests")
    }

    static let identity = DeviceIdentity(
        manufacturer: "Garmin", model: "fenix 8", family: "fēnix", variant: nil,
        usbVendorId: 0x091e, usbProductId: 0x2841, firmware: "20.19",
        storageCapacity: 32_000_000_000, freeSpace: 10_000_000_000
    )
    static let package = MapPackage(
        id: "freizeitkarte-ltu", providerId: "freizeitkarte", regionId: "LTU",
        name: "Lithuania", version: MapVersion(year: 2026, month: 8)!, sizeBytes: 1,
        sourceURL: nil, releaseDate: nil, identifier: "LTU+"
    )

    static func makeEvent(
        id: UUID = UUID(), firmware: String = "20.19",
        variant: String? = nil,
        outcome: InstallationEvidenceOutcome = .succeeded,
        finishing: AutomaticFinishingResult = .verified
    ) -> InstallationEvidenceEvent {
        let changedIdentity = DeviceIdentity(
            manufacturer: identity.manufacturer, model: identity.model, family: identity.family,
            variant: variant, usbVendorId: identity.usbVendorId, usbProductId: identity.usbProductId,
            firmware: firmware, storageCapacity: identity.storageCapacity, freeSpace: identity.freeSpace
        )
        return InstallationEvidenceEvent(
            id: id, identity: changedIdentity, package: package, outcome: outcome,
            finishingResult: finishing, errorCategory: outcome == .failed ? .transport : nil,
            terentoVersion: "test", macOSVersion: "test"
        )
    }

    static func testEventStorageAndDuplicatePrevention() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = LocalInstallationEvidenceStore(rootURL: root)
        let event = makeEvent()
        let inserted = try store.append(event, queueForUpload: false)
        let duplicated = try store.append(event, queueForUpload: false)
        expect(inserted, "successful Finishing event is stored")
        expect(!duplicated, "duplicate event ID is rejected")
        expect(store.events().count == 1, "polling and preflight create no event unless append is explicitly called")
        let broadRegionPackage = MapPackage(
            id: "freizeitkarte-balearics", providerId: "freizeitkarte", regionId: "AZORES",
            name: "Balearics", version: MapVersion(year: 2026, month: 5)!, sizeBytes: 1,
            sourceURL: nil, releaseDate: nil, identifier: "BALEARICS"
        )
        let broadRegionEvent = InstallationEvidenceEvent(
            identity: identity, package: broadRegionPackage, outcome: .succeeded,
            finishingResult: .verified, terentoVersion: "test", macOSVersion: "test"
        )
        expect(broadRegionEvent.region == "BALEARICS", "evidence uses concrete package identity, not its broad catalog group")
        let reviewedIdentity = DeviceIdentity(
            manufacturer: "Garmin", model: "fenix 8 - 47mm", family: "fēnix",
            variant: "47 mm, AMOLED", usbVendorId: 0x091e, usbProductId: 0x51b8,
            firmware: "2244", storageCapacity: 32_000_000_000,
            freeSpace: 10_000_000_000
        )
        let reviewedEvent = InstallationEvidenceEvent(
            identity: reviewedIdentity, package: package, outcome: .succeeded,
            finishingResult: .verified, terentoVersion: "test", macOSVersion: "test"
        )
        expect(
            reviewedEvent.canonicalDeviceId == "garmin-fenix-8-47-amoled"
                && reviewedEvent.displayType == "AMOLED",
            "reviewed exact identity is sent with canonical device and display fields"
        )
        let reviewedPayload = String(decoding: try JSONEncoder().encode(reviewedEvent), as: UTF8.self)
        expect(
            reviewedPayload.contains("\"canonicalDeviceId\":\"garmin-fenix-8-47-amoled\"")
                && reviewedPayload.contains("\"displayType\":\"AMOLED\""),
            "schema v2 payload encodes canonical identity fields"
        )
        let failed = makeEvent(outcome: .failed, finishing: .failed)
        let failedInserted = try store.append(failed, queueForUpload: false)
        expect(failedInserted, "failed started installation is stored")
        let encoded = try JSONEncoder().encode(failed)
        let payload = String(decoding: encoded, as: UTF8.self)
        expect(!payload.lowercased().contains("serial"), "payload has no serial number")
        expect(!payload.contains("/Users/"), "payload has no local path")
    }

    static func testStatisticsAndPromotionThresholds() {
        let model = identity.canonicalModel ?? identity.model
        let one = CompatibilityEvidenceCalculator.summarize([makeEvent()], forModel: model)
        expect(one.attemptedInstallCount == 1 && one.successRate == 1, "success rate denominator contains started installs")

        let three = [makeEvent(), makeEvent(), makeEvent()]
        let supported = CompatibilityEvidenceCalculator.summarize(three, forModel: model)
        expect(supported.successfulInstallCount == 3, "three successful installs remain exact evidence counts")

        let twoFirmware = [makeEvent(), makeEvent(firmware: "20.20")]
        let tested = CompatibilityEvidenceCalculator.summarize(twoFirmware, forModel: model)
        expect(tested.successfulInstallCount == 2 && tested.firmwareVersions.count == 2, "firmware is retained as diagnostics only")
        let verified = CompatibilityEvidenceCalculator.summarize(
            twoFirmware + [makeEvent(), makeEvent(), makeEvent()], forModel: model
        )
        expect(verified.successfulInstallCount == 5, "five successful installs remain exact evidence counts")

        let failedOnly = CompatibilityEvidenceCalculator.summarize(
            [makeEvent(outcome: .failed, finishing: .failed)], forModel: model
        )
        expect(failedOnly.successfulInstallCount == 0 && failedOnly.failedInstallCount == 1, "failed evidence does not become a successful count")

        let variant47 = CompatibilityEvidenceCalculator.summarize(
            [makeEvent(variant: "47mm")], forModel: "fēnix 8 · 47 mm"
        )
        let variant51 = CompatibilityEvidenceCalculator.summarize(
            [makeEvent(variant: "51mm")], forModel: "fēnix 8 · 51 mm"
        )
        expect(variant47.successfulInstallCount == 1 && variant51.successfulInstallCount == 1, "47 mm and 51 mm evidence stays isolated")

        let withFailure = CompatibilityEvidenceCalculator.summarize(three + [makeEvent(outcome: .failed, finishing: .failed)], forModel: model)
        expect(withFailure.attemptedInstallCount == 4 && withFailure.failedInstallCount == 1 && withFailure.successRate == 0.75, "failures affect the denominator but not promotion")
    }

    static func testDiagnosticSanitization() {
        let report = DiagnosticReportSanitizer.sanitize("User /Users/alice/private Unit ID: 123 Serial Number=ABC token: secret")
        expect(!report.contains("alice"), "diagnostic report removes usernames and local paths")
        expect(!report.contains("123") && !report.contains("ABC") && !report.contains("secret"), "diagnostic report removes identifiers and secrets")
        let backendPayload = DiagnosticReportSanitizer.sanitize("{\"serial\":\"ABC\",\"detail\":\"safe status\"}")
        expect(!backendPayload.contains("ABC") && backendPayload.contains("safe status"), "JSON backend payload redacts restricted identifiers")
    }

    @MainActor
    static func testConsentAndUploadIsolation() async throws {
        struct LegacyEvidenceFile: Encodable {
            let events: [InstallationEvidenceEvent]
            let pendingUploadEventIDs: [UUID]
            let uploadedEventIDs: [UUID]
            let consent: VersionedEvidenceConsent
        }

        let staleRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: staleRoot, withIntermediateDirectories: true)
        let staleEvent = makeEvent()
        let staleFile = LegacyEvidenceFile(
            events: [staleEvent],
            pendingUploadEventIDs: [staleEvent.id],
            uploadedEventIDs: [],
            consent: VersionedEvidenceConsent(noticeVersion: 1, choice: .accepted, decidedAt: Date())
        )
        let staleEncoder = JSONEncoder()
        staleEncoder.dateEncodingStrategy = .iso8601
        try staleEncoder.encode(staleFile).write(
            to: staleRoot.appendingPathComponent("installation-evidence.json"),
            options: .atomic
        )
        let stale = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: staleRoot),
            uploader: UploadRecorder()
        )
        expect(stale.currentConsentChoice == .declined, "an older consent notice is invalidated")
        expect(stale.store.pendingUploads().isEmpty, "invalidating stale consent clears its upload queue")

        let declinedRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let declinedUploader = UploadRecorder()
        let declined = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: declinedRoot), uploader: declinedUploader)
        expect(declined.compatibilitySharingEnabled, "first-install compatibility sharing is visibly checked")
        declined.decideConsent(.declined)
        expect(!declined.compatibilitySharingEnabled, "turning sharing off updates the shared preference")
        let declinedReloaded = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: declinedRoot),
            uploader: UploadRecorder()
        )
        expect(!declinedReloaded.compatibilitySharingEnabled, "the declined preference persists across controller instances")
        declined.record(makeEvent())
        await declined.flushPendingUploads()
        let declinedUploadCount = await declinedUploader.count()
        expect(declinedUploadCount == 0, "declined consent disables upload")

        let acceptedRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let acceptedUploader = UploadRecorder()
        let accepted = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: acceptedRoot),
            uploader: acceptedUploader,
            automaticRetryDelays: []
        )
        accepted.decideConsent(.accepted)
        expect(accepted.compatibilitySharingEnabled, "turning sharing on updates the shared preference")
        let acceptedReloaded = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: acceptedRoot),
            uploader: UploadRecorder(),
            automaticRetryDelays: []
        )
        expect(acceptedReloaded.compatibilitySharingEnabled, "the accepted preference persists across controller instances")
        let immediateStatus = await accepted.recordAndUpload([makeEvent()])
        if case let .sent(count) = immediateStatus {
            expect(count == 1, "immediate opt-in upload reports the current event as sent")
        } else {
            expect(false, "immediate opt-in upload exposes sent status")
        }
        let acceptedUploadCount = await acceptedUploader.count()
        expect(acceptedUploadCount >= 1, "opt-in uploads installation evidence")
        expect(accepted.store.pendingUploads().isEmpty, "successful immediate upload clears the pending queue")

        let declinedImmediateRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let declinedImmediate = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: declinedImmediateRoot),
            uploader: UploadRecorder(),
            automaticRetryDelays: []
        )
        declinedImmediate.decideConsent(.declined)
        let declinedStatus = await declinedImmediate.recordAndUpload([makeEvent()])
        expect(declinedStatus == .notShared, "opt-out reports that compatibility evidence was not shared")

        let immediateFailureRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let immediateFailure = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: immediateFailureRoot),
            uploader: UploadRecorder(shouldFail: true),
            automaticRetryDelays: []
        )
        immediateFailure.decideConsent(.accepted)
        let immediateFailureStatus = await immediateFailure.recordAndUpload([makeEvent()])
        if case let .queued(count, _, willRetry) = immediateFailureStatus {
            expect(count == 1 && willRetry, "immediate upload failure reports a retryable queued state")
        } else {
            expect(false, "immediate upload failure exposes a delivery reason")
        }
        expect(immediateFailure.store.pendingUploads().count == 1, "failed immediate upload remains queued for retry")

        let failingRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let failing = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: failingRoot),
            uploader: UploadRecorder(shouldFail: true),
            automaticRetryDelays: []
        )
        failing.decideConsent(.accepted)
        failing.record(makeEvent())
        await failing.flushPendingUploads()
        expect(failing.store.pendingUploads().count == 1, "upload failure remains queued and does not change install evidence")
        if case let .waiting(count, _, willRetry) = failing.uploadStatus {
            expect(count == 1 && willRetry, "transient upload failure is visible and retryable")
        } else {
            expect(false, "transient upload failure exposes waiting status")
        }
        expect(
            InstallationEvidenceUploadError.httpStatus(code: 400, body: "missing_fields").isRetryable == false,
            "permanent HTTP validation errors are not retried"
        )
        let safeFailureMessage = InstallationEvidenceUploadError
            .httpStatus(code: 500, body: "{\"serial\":\"hidden\",\"detail\":\"backend trace\"}")
            .errorDescription ?? ""
        expect(
            !safeFailureMessage.contains("500")
                && !safeFailureMessage.contains("backend trace")
                && !safeFailureMessage.contains("hidden"),
            "backend and HTTP details stay out of user-facing upload errors"
        )
        failing.decideConsent(.declined)
        expect(failing.store.pendingUploads().isEmpty, "withdrawing consent clears queued reports")

        let retryRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let retryUploader = UploadRecorder(failuresRemaining: 1)
        let retrying = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: retryRoot),
            uploader: retryUploader,
            automaticRetryDelays: [0, 0, 0]
        )
        retrying.decideConsent(.accepted)
        retrying.record(makeEvent())
        try await Task.sleep(nanoseconds: 100_000_000)
        expect(retrying.store.pendingUploads().isEmpty, "transient upload failure is retried automatically")
        let retriedUploadCount = await retryUploader.count()
        expect(retriedUploadCount == 1, "retried evidence is marked uploaded after success")

        let deletionRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let deletionUploader = UploadRecorder()
        let deletion = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: deletionRoot),
            uploader: deletionUploader,
            automaticRetryDelays: []
        )
        deletion.decideConsent(.accepted)
        deletion.record(makeEvent())
        await deletion.flushPendingUploads()
        let deleted = await deletion.deleteUploadedReports()
        let deletionCount = await deletionUploader.deletionCount()
        expect(deleted == 1 && deletionCount == 1, "uploaded reports can be deleted with their local deletion token")
        expect(deletion.store.uploadedEvents().isEmpty, "deleted reports are no longer marked as uploaded")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fatalError("FAIL: \(message)") }
    }
}

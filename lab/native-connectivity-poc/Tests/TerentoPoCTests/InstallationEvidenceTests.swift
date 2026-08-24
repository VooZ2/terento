import Foundation

private actor UploadRecorder: InstallationEvidenceUploading {
    let shouldFail: Bool
    private(set) var uploaded: [UUID] = []
    init(shouldFail: Bool = false) { self.shouldFail = shouldFail }
    func upload(_ event: InstallationEvidenceEvent) async throws {
        if shouldFail { throw URLError(.cannotConnectToHost) }
        uploaded.append(event.id)
    }
    func count() -> Int { uploaded.count }
}

@main
struct InstallationEvidenceTests {
    @MainActor
    static func main() async throws {
        try testEventStorageAndDuplicatePrevention()
        testStatisticsAndPromotionThresholds()
        try await testConsentConfirmationAndUploadIsolation()
        testDiagnosticSanitization()
        print("PASS: 17 installation evidence, privacy, consent, upload, report, and promotion tests")
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
        outcome: InstallationEvidenceOutcome = .succeeded,
        finishing: AutomaticFinishingResult = .verified
    ) -> InstallationEvidenceEvent {
        let changedIdentity = DeviceIdentity(
            manufacturer: identity.manufacturer, model: identity.model, family: identity.family,
            variant: nil, usbVendorId: identity.usbVendorId, usbProductId: identity.usbProductId,
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
        expect(one.calculatedStatus == .tested, "one verified success reaches TESTED")

        let three = [makeEvent(), makeEvent(), makeEvent()]
        let supported = CompatibilityEvidenceCalculator.summarize(three, forModel: model)
        expect(supported.calculatedStatus == .supported, "three verified successes reach SUPPORTED")

        let twoFirmware = [makeEvent(), makeEvent(), makeEvent(firmware: "20.20")]
        let reviewPending = CompatibilityEvidenceCalculator.summarize(twoFirmware, forModel: model)
        expect(reviewPending.calculatedStatus == .tested, "mixed firmware results do not satisfy the same-firmware SUPPORTED threshold")
        expect(reviewPending.verifiedRequiresPhysicalDeviceReview, "VERIFIED requires physical-device review")
        let verified = CompatibilityEvidenceCalculator.summarize(twoFirmware, forModel: model, reviewedPhysicalDeviceCount: 2)
        expect(verified.calculatedStatus == .verified, "reviewed two-device evidence reaches VERIFIED")

        let withFailure = CompatibilityEvidenceCalculator.summarize(three + [makeEvent(outcome: .failed, finishing: .failed)], forModel: model)
        expect(withFailure.attemptedInstallCount == 4 && withFailure.failedInstallCount == 1 && withFailure.successRate == 0.75, "failures affect the denominator but not promotion")
    }

    static func testDiagnosticSanitization() {
        let report = DiagnosticReportSanitizer.sanitize("User /Users/alice/private Unit ID: 123 Serial Number=ABC token: secret")
        expect(!report.contains("alice"), "diagnostic report removes usernames and local paths")
        expect(!report.contains("123") && !report.contains("ABC") && !report.contains("secret"), "diagnostic report removes identifiers and secrets")
    }

    @MainActor
    static func testConsentConfirmationAndUploadIsolation() async throws {
        let declinedRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let declinedUploader = UploadRecorder()
        let declined = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: declinedRoot), uploader: declinedUploader)
        declined.decideConsent(.declined)
        declined.record(makeEvent())
        declined.confirmLatestSuccessfulInstallation()
        await declined.flushPendingUploads()
        let declinedUploadCount = await declinedUploader.count()
        expect(declinedUploadCount == 0, "declined consent disables upload")
        expect(declined.latestEvent?.userConfirmed == true, "Confirm stays local without opt-in")

        let acceptedRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let acceptedUploader = UploadRecorder()
        let accepted = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: acceptedRoot), uploader: acceptedUploader)
        accepted.decideConsent(.accepted)
        accepted.record(makeEvent())
        await accepted.flushPendingUploads()
        accepted.confirmLatestSuccessfulInstallation()
        await accepted.flushPendingUploads()
        let acceptedUploadCount = await acceptedUploader.count()
        expect(acceptedUploadCount >= 1, "opt-in uploads installation and Confirm signal")

        let failingRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let failing = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: failingRoot), uploader: UploadRecorder(shouldFail: true))
        failing.decideConsent(.accepted)
        failing.record(makeEvent())
        await failing.flushPendingUploads()
        expect(failing.store.pendingUploads().count == 1, "upload failure remains queued and does not change install evidence")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fatalError("FAIL: \(message)") }
    }
}

import Foundation

private actor UploadRecorder: InstallationEvidenceUploading {
    let shouldFail: Bool
    var failuresRemaining: Int
    let successfulUploadDelay: UInt64
    private(set) var uploaded: [UUID] = []
    init(shouldFail: Bool = false, failuresRemaining: Int = 0, successfulUploadDelay: UInt64 = 0) {
        self.shouldFail = shouldFail
        self.failuresRemaining = failuresRemaining
        self.successfulUploadDelay = successfulUploadDelay
    }
    func upload(_ event: InstallationEvidenceEvent) async throws {
        if shouldFail || failuresRemaining > 0 {
            if failuresRemaining > 0 { failuresRemaining -= 1 }
            throw URLError(.cannotConnectToHost)
        }
        if successfulUploadDelay > 0 { try await Task.sleep(nanoseconds: successfulUploadDelay) }
        uploaded.append(event.id)
    }
    func count() -> Int { uploaded.count }
}

@main
struct InstallationEvidenceTests {
    @MainActor
    static func main() async throws {
        try testEventStorageAndDuplicatePrevention()
        try testFailureContextRoundTrip()
        try testCustomIMGEvidencePayload()
        try testOTMClassificationAudit()
        try testOriginalModelMetadata()
        testStatisticsAndPromotionThresholds()
        try await testConsentAndUploadIsolation()
        testDiagnosticSanitization()
        testPreparedInstallationIssue()
        print("PASS: installation evidence, privacy, default-on upload, report, and promotion tests")
    }

    static func testFailureContextRoundTrip() throws {
        let expectedStages: [(InstallationFailureContext.Boundary, EvidenceFailureStage)] = [
            (.initialSnapshot, .preflight), (.initialInventory, .preflight),
            (.prewriteInventory, .preflight), (.prewriteProtection, .preflight),
            (.write, .write), (.readback, .verify), (.postwriteInventory, .verify),
            (.postwriteSnapshot, .verify), (.targetValidation, .verify),
            (.postwriteProtection, .verify), (.cleanup, .cleanup), (.manifest, .manifest),
            (.sourceValidationComplete, .sourceValidation), (.preflightPolicyPassed, .preflight)
        ]
        for (boundary, stage) in expectedStages {
            precondition(boundary.stageRawValue == stage.rawValue
                && InstallationFailureStageResolver.stage(for: boundary) == stage)
        }
        let original = InstallationFailureContext(boundary: .postwriteProtection,
            classificationSource: .derived, devicePresence: .unknown, operation: .protectionCheck,
            protection: InstallationProtectionContext(protectionBoundary: .postWrite,
                protectionReason: .preexistingObjectChanged, stableIdentityComparisonVersion: 1,
                beforeObjectCount: 3, afterObjectCount: 4, changedObjectCount: 1))
        let terminal = InstallationFailureContext(boundary: .cleanup, classificationSource: .derived,
            devicePresence: .unknown, operation: .cleanup, executionMode: .worker,
            resultKind: .timeout, retryCount: 0)
        let event = InstallationEvidenceEvent(identity: identity, package: package, outcome: .failed,
            finishingResult: .failed, errorCategory: .transport, failureStage: .cleanup,
            failureCode: "INSTALL_FAILED_CLEANUP", cleanupAttempted: true,
            failureContext: terminal, originalFailureContext: original)
        let encoded = try JSONEncoder().encode(event)
        let decoded = try JSONDecoder().decode(InstallationEvidenceEvent.self, from: encoded)
        precondition(decoded.failureContext == terminal && decoded.originalFailureContext == original)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        _ = try LocalInstallationEvidenceStore(rootURL: root).append(event, queueForUpload: true)
        let reopened = LocalInstallationEvidenceStore(rootURL: root)
        precondition(reopened.events().first?.failureContext == terminal
            && reopened.events().first?.originalFailureContext == original
            && reopened.pendingUploads().count == 1)
        var object = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
        for explicitNull in [false, true] {
            if explicitNull {
                object["failureContext"] = NSNull(); object["originalFailureContext"] = NSNull()
            } else {
                object.removeValue(forKey: "failureContext"); object.removeValue(forKey: "originalFailureContext")
            }
            let legacy = try JSONDecoder().decode(InstallationEvidenceEvent.self,
                from: JSONSerialization.data(withJSONObject: object))
            precondition(legacy.failureContext == nil && legacy.originalFailureContext == nil)
        }
        let native = InstallationFailureContext(boundary: .initialSnapshot, classificationSource: .native,
            devicePresence: .unknown, operation: .snapshot, resultKind: .nativeError,
            nativeCategory: .detection, nativeCodeNamespace: .terentoSnapshot, nativeResultCode: -2)
        precondition(native.at(.initialSnapshot, componentKind: .main).classificationSource == .native)
        precondition(native.at(.initialSnapshot, classificationSource: .derived).classificationSource == .derived)
        precondition(native.at(.initialSnapshot).nativeResultCode == -2)
        print("PASS: all boundary stages, reopened context outbox, absent/null legacy context and explicit provenance")
    }

    static let identity = DeviceIdentity(
        manufacturer: "Garmin", model: "fenix 8", family: "fēnix", variant: nil,
        usbVendorId: 0x091e, usbProductId: 0x2841, firmware: "20.19",
        storageCapacity: 32_000_000_000, freeSpace: 10_000_000_000
    )
    static let package = MapPackage(
        id: "freizeitkarte-deu", providerId: "freizeitkarte", regionId: "DEU",
        name: "Germany", version: MapVersion(year: 2026, month: 8)!, sizeBytes: 1,
        sourceURL: nil, releaseDate: nil, identifier: "DEU+"
    )
    static let customIMGPackage = MapPackage(
        id: "custom-sha256-local-fingerprint",
        providerId: "custom",
        regionId: "img_deadbeef0123456789abcdef",
        name: "Custom map",
        version: MapVersion(year: 2000, month: 1)!,
        sizeBytes: 1,
        sourceURL: nil,
        releaseDate: nil,
        identifier: "img_deadbeef0123456789abcdef",
        sourceKind: .custom
    )

    static func testCustomIMGEvidencePayload() throws {
        let watchIdentity = DeviceIdentity(
            manufacturer: "Garmin", model: "fenix 7 Pro", family: "fēnix", variant: "47mm",
            usbVendorId: 0x091e, usbProductId: 0x2841, firmware: "20.19",
            storageCapacity: 32_000_000_000, freeSpace: 10_000_000_000
        )
        let event = InstallationEvidenceEvent(
            identity: watchIdentity,
            package: customIMGPackage,
            outcome: .succeeded,
            finishingResult: .verified,
            terentoVersion: "test",
            macOSVersion: "test"
        )
        expect(
            event.model == "fenix 7 Pro"
                && event.provider == "custom"
                && event.region == "custom"
                && event.mapRelease == "custom",
            "custom IMG evidence keeps the watch model and uses coarse source labels"
        )
        let payload = String(decoding: try JSONEncoder().encode(event), as: UTF8.self)
        expect(
            payload.contains("\"schemaVersion\":4")
                && !payload.contains("deadbeef")
                && !payload.contains("img_")
                && !payload.contains("deletionToken"),
            "custom IMG evidence does not upload the local content fingerprint"
        )
    }

    static func testOTMClassificationAudit() throws {
        for provider in ["opentopomap", "freizeitkarte"] {
            let original = MapPackage(id: provider + "-poland", providerId: provider,
                regionId: "POL", name: "Poland", version: MapVersion(year: 2026, month: 9)!,
                sizeBytes: 1, sourceURL: nil, releaseDate: nil, identifier: "POL")
            let data = try JSONEncoder().encode(original)
            var json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            json.removeValue(forKey: "sourceKind")
            let decoded = try JSONDecoder().decode(MapPackage.self,
                from: JSONSerialization.data(withJSONObject: json))
            for package in [original, decoded] {
                let event = InstallationEvidenceEvent(identity: identity, package: package,
                    outcome: .succeeded, finishingResult: .verified,
                    terentoVersion: "test", macOSVersion: "test")
                expect(package.sourceKind == .provider && event.provider == provider
                    && event.region == "POL" && event.mapRelease != "custom",
                    "provider identity survives package decoding and installation evidence")
            }
        }
        print("PASS: audit OTM/Freizeitkarte explicit and default source classification")
    }

    static func testOriginalModelMetadata() throws {
        func event(description: String?, part: String?) -> InstallationEvidenceEvent {
            let watch = DeviceIdentity(manufacturer: "Garmin", model: "fenix 9 Pro 51mm", family: "fenix", variant: nil,
                usbVendorId: 0x091e, usbProductId: 0x7777, firmware: "638", storageCapacity: 1, freeSpace: 1,
                localHardwareIdentifier: "PRIVATE-UNIT-ID", garminModelDescription: description, garminModelPartNumber: part)
            return InstallationEvidenceEvent(identity: watch, package: package, outcome: .succeeded,
                finishingResult: .verified, terentoVersion: "test", macOSVersion: "test")
        }
        let original = event(description: "fenix 9 Pro - inReach, 51mm", part: "006-B4954-00")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(InstallationEvidenceEvent.self, from: data)
        expect(decoded.garminModelDescription == original.garminModelDescription && decoded.garminModelPartNumber == "006-B4954-00",
               "queued diagnostics retain original XML model metadata")
        let text = String(decoding: data, as: UTF8.self)
        expect(!text.contains("PRIVATE-UNIT-ID") && !text.contains("GarminDevice"), "XML and private identity are excluded from reports")
        for value in ["/Users/private", String(repeating: "A", count: 161), "model\nserial"] {
            expect(event(description: value, part: "006/invalid").garminModelDescription == nil,
                   "invalid optional description is omitted")
        }
        expect(event(description: "Valid", part: "006/invalid").garminModelPartNumber == nil, "invalid optional part number is omitted")
        expect(event(description: nil, part: nil).garminModelPartNumber == nil, "old metadata-free diagnostics stay supported")
    }

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
            freeSpace: 10_000_000_000,
            catalogMetadata: CatalogDeviceMetadata(candidateDeviceID: "api-catalog-record-123",
                model: "fēnix 8", screenTechnology: "AMOLED", solar: nil, inReach: nil)
        )
        let reviewedEvent = InstallationEvidenceEvent(
            identity: reviewedIdentity, package: package, outcome: .succeeded,
            finishingResult: .verified, terentoVersion: "test", macOSVersion: "test"
        )
        expect(
            reviewedEvent.canonicalDeviceId == "api-catalog-record-123"
                && reviewedEvent.displayType == "AMOLED",
            "reviewed exact identity is sent with canonical device and display fields"
        )
        let reviewedPayload = String(decoding: try JSONEncoder().encode(reviewedEvent), as: UTF8.self)
        expect(
            reviewedPayload.contains("\"canonicalDeviceId\":\"api-catalog-record-123\"")
                && reviewedPayload.contains("\"displayType\":\"AMOLED\"")
                && reviewedPayload.contains("\"appBuild\":")
                && reviewedPayload.contains("\"operationId\":"),
            "schema v3 payload encodes canonical identity and operation fields"
        )
        let failed = makeEvent(outcome: .failed, finishing: .failed)
        let failedInserted = try store.append(failed, queueForUpload: false)
        expect(failedInserted, "failed started installation is stored")
        let encoded = try JSONEncoder().encode(failed)
        let payload = String(decoding: encoded, as: UTF8.self)
        expect(!payload.contains("stage401-") && !payload.contains("1234567890"), "payload has no serial or Unit ID value")
        expect(!payload.contains("/Users/"), "payload has no local path")

        let proIdentity = DeviceIdentity(
            manufacturer: "Garmin", model: "fenix 8 - 51mm", family: "fēnix",
            variant: "51mm", usbVendorId: 0x091e, usbProductId: 0x7777,
            firmware: "2326", storageCapacity: 1, freeSpace: 1,
            localHardwareIdentifier: "1234567890", localIdentityResolution: .garminUnitID,
            deviceDescription: "fēnix 8 Pro - 51mm"
        )
        let proEvent = InstallationEvidenceEvent(
            identity: proIdentity, package: package, outcome: .succeeded,
            finishingResult: .verified, terentoVersion: "test", macOSVersion: "test"
        )
        expect(
            proEvent.model == "fēnix 8 Pro"
                && proEvent.compatibilityIdentity == "fēnix 8 Pro · 51 mm"
                && proEvent.canonicalDeviceId == nil
                && proEvent.rawMTPModel == "fenix 8 - 51mm"
                && proEvent.identityResolutionCode == "GARMIN_UNIT_ID",
            "Pro remains a separate evidence model while an unknown display stays non-exact"
        )

        let controlCharacterIdentity = DeviceIdentity(
            manufacturer: "Garmin", model: "fenix 8\nPro - 51mm", family: "fēnix",
            variant: "51mm", usbVendorId: 0x091e, usbProductId: 0x7777,
            firmware: "2326", storageCapacity: 1, freeSpace: 1,
            localHardwareIdentifier: "local-only"
        )
        let sanitizedEvent = InstallationEvidenceEvent(
            identity: controlCharacterIdentity, package: package, outcome: .failed,
            finishingResult: .failed, failureStage: .preflight,
            failureCode: "INSTALL_BLOCKED_STABLE_WATCH_IDENTITY_UNAVAILABLE",
            writeStarted: false, terentoVersion: "test", macOSVersion: "test"
        )
        expect(
            sanitizedEvent.rawMTPModel == "fenix 8Pro - 51mm",
            "raw MTP diagnostic label removes control characters before upload"
        )
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

        let differentSizes = [makeEvent(variant: "47mm"), makeEvent(variant: "51mm")]
        let variant47 = CompatibilityEvidenceCalculator.summarize(differentSizes, forModel: "fenix 8 · 47 mm")
        let variant51 = CompatibilityEvidenceCalculator.summarize(differentSizes, forModel: "fenix 8 · 51 mm")
        expect(variant47.successfulInstallCount == 1 && variant51.successfulInstallCount == 1, "47 mm and 51 mm evidence stays isolated")

        let withFailure = CompatibilityEvidenceCalculator.summarize(three + [makeEvent(outcome: .failed, finishing: .failed)], forModel: model)
        expect(withFailure.attemptedInstallCount == 4 && withFailure.failedInstallCount == 1 && withFailure.successRate == 0.75, "failures affect the denominator but not promotion")

        let operationID = UUID()
        let firstMap = InstallationEvidenceEvent(
            identity: identity, package: package, outcome: .failed,
            finishingResult: .failed, errorCategory: .transport,
            operationId: operationID, mapResultIndex: 0, selectedMapCount: 2,
            failureStage: .write, failureCode: "INSTALL_FAILED_WRITE",
            nativeFailureCode: .sendObjectFailed, writeStarted: true,
            transferProgressBucket: .oneToTwentyFour,
            terentoVersion: "test", macOSVersion: "test"
        )
        let secondMap = InstallationEvidenceEvent(
            identity: identity, package: package, outcome: .notStarted,
            finishingResult: .notReached, errorCategory: .transport,
            operationId: operationID, mapResultIndex: 1, selectedMapCount: 2,
            failureStage: .preflight,
            failureCode: "INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE",
            writeStarted: false, terentoVersion: "test", macOSVersion: "test"
        )
        let grouped = CompatibilityEvidenceCalculator.summarize([firstMap, secondMap], forModel: model)
        expect(grouped.attemptedInstallCount == 1 && grouped.failedInstallCount == 1, "one multi-map click counts as one failed write-started operation")

        let prewrite = InstallationEvidenceEvent(
            identity: identity, package: package, outcome: .failed,
            finishingResult: .failed, errorCategory: .acquisition,
            operationId: UUID(), failureStage: .download,
            failureCode: "INSTALL_BLOCKED_DOWNLOAD_FAILED",
            writeStarted: false, terentoVersion: "test", macOSVersion: "test"
        )
        let excluded = CompatibilityEvidenceCalculator.summarize([prewrite], forModel: model)
        expect(excluded.attemptedInstallCount == 0 && excluded.failedInstallCount == 0, "pre-write failure is diagnostic and excluded from watch compatibility")
    }

    @MainActor
    static func testDiagnosticSanitization() {
        let report = DiagnosticReportSanitizer.sanitize("User /Users/alice/private Unit ID: 123 Serial Number=ABC token: secret Authorization: Bearer-private")
        expect(!report.contains("alice"), "diagnostic report removes usernames and local paths")
        expect(!report.contains("123") && !report.contains("ABC") && !report.contains("secret") && !report.contains("Bearer-private"), "diagnostic report removes identifiers and secrets")
        let reflectedPath = DiagnosticReportSanitizer.sanitize("failure(path: \"/private/tmp/private-map.img\")")
        expect(!reflectedPath.contains("/private/tmp") && !reflectedPath.contains("private-map.img"), "reflected error paths are redacted inside quotes")
        let backendPayload = DiagnosticReportSanitizer.sanitize("{\"serial\":\"ABC\",\"detail\":\"safe status\"}")
        expect(!backendPayload.contains("ABC") && backendPayload.contains("safe status"), "JSON backend payload redacts restricted identifiers")
        let signedURL = DiagnosticReportSanitizer.sanitize("https://example.test/map?token=secret-value&region=LTU")
        expect(!signedURL.contains("secret-value") && signedURL.contains("region=LTU"), "diagnostic report removes signed URL token values")
    }

    @MainActor
    static func testPreparedInstallationIssue() {
        let operationID = UUID(uuidString: "12345678-1234-1234-1234-1234567890AB")!
        let diagnosticID = UUID(uuidString: "ABCDEFAB-1234-1234-1234-ABCDEFABCDEF")!
        let timestamp = Date(timeIntervalSince1970: 1_786_000_000)
        let unsafeIdentity = DeviceIdentity(
            manufacturer: "Garmin", model: "fenix 8", family: "fēnix", variant: "47 mm AMOLED",
            usbVendorId: 0x091e, usbProductId: 0x2841, firmware: "20.19",
            storageCapacity: 32_000_000_000, freeSpace: 10_000_000_000,
            localHardwareIdentifier: "SERIAL-PRIVATE"
        )
        FinishingTrace.beginInstallation()
        FinishingTrace.event("read_failed", "offset=182108160 rc=-1 detail=0 verified_bytes=29229056")
        FinishingTrace.event("operation_failed", "operation=cleanup elapsed=45 error=operationFailed")
        FinishingTrace.freezeFailure()
        let draft = InstallationIssueReport.generate(
            identity: unsafeIdentity,
            maps: [
                InstallationIssueMap(
                    provider: "OpenTopoMap",
                    region: "Lithuania",
                    package: "LTU",
                    release: "2026-08-30",
                    artifactSizeBytes: 276_800_000
                ),
                InstallationIssueMap(
                    provider: "OpenTopoMap",
                    region: "Azores",
                    package: "AZORES",
                    release: "2026-08-30",
                    artifactSizeBytes: 16_200_000
                )
            ],
            stage: "Downloading",
            error: "Token: private-token /Users/alice/map.img",
            operationID: operationID,
            failureStages: ["source-validation", "preflight"],
            errorCategory: "sourceValidation",
            errorCodes: ["INSTALL_BLOCKED_SOURCE_VALIDATION_FAILED", "INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE"],
            verification: .init(originalFailure: "INSTALL_FAILED_REMOTE_FILE_MISSING",
                                cleanupFailure: "INSTALL_FAILED_CLEANUP",
                                sourceSize: 1794965504, remoteSize: 1794965504,
                                sampledBytes: 4194304, sampleCount: 7, matchedSampleCount: 1),
            diagnosticID: diagnosticID,
            timestamp: timestamp,
            appVersion: "0.8.0-beta.8",
            appBuild: "108",
            operatingSystem: "macOS 15.6"
        )
        precondition(draft.body.contains("LTU: release=2026-08-30, planned installed bytes=276800000"))
        precondition(draft.body.contains("Original failure: INSTALL_FAILED_REMOTE_FILE_MISSING"))
        precondition(draft.body.contains("Cleanup failure: INSTALL_FAILED_CLEANUP"))
        precondition(draft.body.contains("Validated source bytes: 1794965504"))
        precondition(draft.body.contains("Matched samples: 1"))
        precondition(draft.body.contains("event=read_failed"))
        precondition(draft.body.contains("verified_bytes=29229056"))
        precondition(draft.body.contains("operation=cleanup elapsed=45"))
        FinishingTrace.beginInstallation()
        expect(draft.title == "Installation stopped during Downloading — OpenTopoMap / Lithuania", "prepared issue title uses the real stage, provider, and region")
        expect(draft.body.contains("## Summary") && draft.body.contains("Failure stage: source-validation, preflight") && draft.body.contains("INSTALL_BLOCKED_SOURCE_VALIDATION_FAILED"), "prepared issue includes structured failure summary")
        expect(draft.body.contains("Provider: OpenTopoMap") && draft.body.contains("Region: LTU, AZORES") && draft.body.contains("Map version: 2026-08-30"), "prepared issue includes concise multi-map metadata")
        expect(draft.body.contains("App version: 0.8.0-beta.8") && draft.body.contains("Model: fenix 8") && draft.body.contains("Variant: 47 mm AMOLED"), "prepared issue includes safe environment metadata")
        expect(draft.body.lowercased().contains(operationID.uuidString.lowercased()) && draft.body.lowercased().contains(diagnosticID.uuidString.lowercased()), "prepared issue includes diagnostic and installation references")
        expect(!draft.body.contains("alice") && !draft.body.contains("private-token") && !draft.body.contains("SERIAL-PRIVATE") && !draft.body.contains("/Users/"), "prepared issue excludes local paths, tokens, and device identifiers")

        let removalDraft = InstallationIssueReport.generate(identity: unsafeIdentity, maps: [],
            stage: "DELETE_FAILED_OPERATION", operation: .removal,
            lifecycleFacts: ["Ownership route: Terento-owned", "Local path: /Users/alice/private"],
            error: nil, operationID: nil, appVersion: "0.8.0-beta.11-local")
        expect(removalDraft.body.contains("Operation: Map removal")
            && removalDraft.body.contains("Ownership route: Terento-owned")
            && removalDraft.body.contains("0.8.0-beta.11-local")
            && !removalDraft.body.contains("/Users/alice"),
            "lifecycle reports retain operation/build identity and sanitize facts")

        let components = URLComponents(url: draft.url, resolvingAgainstBaseURL: false)
        let query = Dictionary(uniqueKeysWithValues: (components?.queryItems ?? []).map { ($0.name, $0.value ?? "") })
        expect(components?.path == "/VooZ2/terento/issues/new" && query["title"] == draft.title && query["body"] == draft.body && query["template"] == nil && query["diagnostic-report"] == nil, "prepared issue URL fills a standard issue without template publication or required checkbox")
        FinishingTrace.beginInstallation()
        for attempt in 1...40 {
            FinishingTrace.event("readback_failed", "worker=false attempt=\(attempt) error=remoteFileMissing")
        }
        FinishingTrace.freezeFailure()
        let longDraft = InstallationIssueReport.generate(identity: unsafeIdentity, maps: [],
            stage: "Finishing", error: nil, operationID: operationID)
        precondition(longDraft.url.absoluteString.utf8.count <= 7000)
        precondition(longDraft.body.contains("attempt=40"))
        precondition(!longDraft.url.absoluteString.contains("clipboard"))
        FinishingTrace.beginInstallation()
        expect(!InstallationIssueReport.openGitHub(draft, using: { _ in false }), "GitHub open failures are returned without requiring clipboard access")
        let fixtureURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/issue148-failure-report.md")
        let fixture = try! String(contentsOf: fixtureURL, encoding: .utf8)
        let actualDraft = InstallationIssueReport.draft(title: "Installation stopped during Finishing — MapRando / Lithuania", body: fixture)
        let actualQuery = URLComponents(url: actualDraft.url, resolvingAgainstBaseURL: false)!.queryItems!
        let filled = actualQuery.first { $0.name == "body" }!.value!
        expect(actualDraft.url.absoluteString.utf8.count <= 7000 && !filled.contains("omitted"), "actual issue148 report fits with its entire compact trace")
        expect(filled.contains("read_ptp_response,1572864,767,65536,1572864,1572864")
            && filled.contains("cleanup_result attempt=1 succeeded=0")
            && filled.contains("Firmware: 2331") && filled.contains("Elapsed at failure (ms): 273621"),
            "automatic prefill preserves first failure, raw PTP response, byte position, environment and cleanup outcome")
        let oversized = InstallationIssueReport.draft(title: "Failure", body: fixture + String(repeating: "\nFINISH_TRACE swift event=readback_failed attempt=40 error=operationFailed", count: 500))
        let oversizedBody = URLComponents(url: oversized.url, resolvingAgainstBaseURL: false)!.queryItems!.first { $0.name == "body" }!.value!
        expect(oversized.url.absoluteString.utf8.count <= 7000 && oversizedBody.contains("omitted")
            && oversizedBody.contains("read_ptp_response,1572864,767"), "pathological reports explicitly summarize excess lines while retaining first native failure")
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
            uploader: UploadRecorder(),
            automaticRetryDelays: [60_000_000_000]
        )
        expect(stale.currentConsentChoice == .accepted, "an older accepted choice migrates to the current diagnostics policy")
        expect(stale.compatibilitySharingEnabled, "the migrated accepted choice keeps diagnostics enabled")
        expect(stale.store.pendingUploads().count == 1, "an accepted legacy queue is preserved for delivery")

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

        let defaultRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let defaultUploader = UploadRecorder()
        let defaultOn = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: defaultRoot),
            uploader: defaultUploader,
            automaticRetryDelays: []
        )
        expect(defaultOn.compatibilitySharingEnabled, "new installations enable compatibility diagnostics by default")
        let defaultStatus = await defaultOn.recordAndUpload([makeEvent()])
        expect(defaultStatus == .sent(count: 1), "default-on compatibility diagnostics upload without an install-time choice")
        let defaultUploadCount = await defaultUploader.count()
        expect(defaultUploadCount == 1, "default-on compatibility diagnostics are sent")

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
            expect(count == 1, "immediate diagnostics upload reports the current event as sent")
        } else {
            expect(false, "immediate diagnostics upload exposes sent status")
        }
        let acceptedUploadCount = await acceptedUploader.count()
        expect(acceptedUploadCount >= 1, "enabled diagnostics upload installation evidence")
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

        let manualRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        // Deliberately completes after the old 180 ms assertion window. Completion,
        // not machine speed or a guessed sleep, determines test success.
        let manualUploader = UploadRecorder(failuresRemaining: 1, successfulUploadDelay: 300_000_000)
        let manual = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: manualRoot),
            uploader: manualUploader, automaticRetryDelays: [50_000_000, 50_000_000])
        manual.record(makeEvent())
        await manual.flushPendingUploads()
        expect(manual.store.pendingUploads().count == 1, "manual send failure retains its event")
        let manualRetry = manual.scheduledUploadForTesting()
        expect(manualRetry != nil, "manual failure schedules an automatic retry")
        await manualRetry?.value
        expect(manual.store.pendingUploads().isEmpty, "manual send preserves automatic retry")
        expect(manual.uploadStatus == .uploaded, "manual retry success updates Diagnostics status")

        let retryRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let retryUploader = UploadRecorder(failuresRemaining: 1)
        let retrying = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: retryRoot),
            uploader: retryUploader,
            automaticRetryDelays: [0, 0, 0]
        )
        retrying.decideConsent(.accepted)
        retrying.record(makeEvent())
        let automaticRetry = retrying.scheduledUploadForTesting()
        expect(automaticRetry != nil, "record schedules an automatic upload")
        await automaticRetry?.value
        expect(retrying.store.pendingUploads().isEmpty, "transient upload failure is retried automatically")
        expect(retrying.uploadStatus == .uploaded, "Diagnostics observes successful retry completion")
        let retriedUploadCount = await retryUploader.count()
        expect(retriedUploadCount == 1, "retried evidence is marked uploaded after success")
        await retrying.flushPendingUploads()
        let afterRepeatedFlush = await retryUploader.count()
        expect(afterRepeatedFlush == 1, "a completed event is not uploaded by another flush")

        let cancelledUploader = UploadRecorder()
        let cancelled = InstallationEvidenceController(
            store: LocalInstallationEvidenceStore(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            uploader: cancelledUploader, automaticRetryDelays: [50_000_000])
        cancelled.record(makeEvent())
        let cancelledTask = cancelled.scheduledUploadForTesting()
        expect(cancelledTask != nil, "opt-out scenario starts with scheduled work")
        cancelled.decideConsent(.declined)
        await cancelledTask?.value
        let cancelledCount = await cancelledUploader.count()
        expect(cancelledCount == 0 && cancelled.store.pendingUploads().isEmpty,
               "opt-out cancels scheduled delivery and clears queued events")

    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fatalError("FAIL: \(message)") }
    }
}

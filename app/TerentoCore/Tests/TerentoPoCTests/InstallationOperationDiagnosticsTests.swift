import Foundation
import LibMTPBridge

extension Bundle { static var module: Bundle { .main } }
private actor DiagnosticUploadRecorder: InstallationEvidenceUploading {
    private(set) var received: [InstallationEvidenceEvent] = []
    private(set) var attempts: [UUID] = []
    var failuresRemaining: Int
    var afterFirstUpload: (@Sendable () async -> Void)?
    func onFirstUpload(_ action: @escaping @Sendable () async -> Void) { afterFirstUpload = action }
    init(failuresRemaining: Int = 0) { self.failuresRemaining = failuresRemaining }
    func upload(_ event: InstallationEvidenceEvent) async throws {
        attempts.append(event.id)
        if failuresRemaining > 0 { failuresRemaining -= 1; throw URLError(.cannotConnectToHost) }
        received.append(event)
        if received.count == 1 { await afterFirstUpload?() }
    }
}
private struct NoNetworkStatisticsUploader: MapStatisticsEventUploading {
    func upload(_ event: MapStatisticsEvent) async throws {}
}
@main struct InstallationOperationDiagnosticsTests {
    @MainActor static var emittedFixtures: [InstallationEvidenceEvent] = []
    @MainActor static func main() async throws {
        try await testEngineWithoutScreen()
        try await testReadBoundaryAndPresence()
        try await testObservedReadSurvivesCancellation()
        try testRetainedReadReport()
        try await testContextFreeContourPreflight()
        try await testContextualContours()
        try await testResultsAndPrivacy()
        try await testPartialBatchAndPreflight()
        try await testDisconnectAndCancellation()
        try await testRetryRestartAndConsent()
        try await testOptOutDuringUpload()
        if let output = ProcessInfo.processInfo.environment["TERENTO_DIAGNOSTIC_FIXTURE_OUTPUT"] {
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            try encoder.encode(emittedFixtures).write(to: URL(fileURLWithPath: output))
        }
        print("PASS: operation diagnostic creation, persisted delivery, privacy and per-map outcomes")
    }
    static func check(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fatalError(message) }
        print("PASS: \(message)")
    }
    static let identity = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 47mm", family: "fenix", variant: "47mm",
        usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: "2244", storageCapacity: 32_000_000_000, freeSpace: 20_000_000_000,
        localHardwareIdentifier: "PRIVATE-UNIT-SERIAL", garminModelDescription: "fenix 8 - 47mm", garminModelPartNumber: "006-B4536-00")
    @MainActor static func testEngineWithoutScreen() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalInstallationEvidenceStore(rootURL: root)
        let uploader = DiagnosticUploadRecorder()
        let evidence = InstallationEvidenceController(store: store, uploader: uploader, automaticRetryDelays: [0])
        let stats = MapStatisticsEventController(store: LocalMapStatisticsEventStore(rootURL: root), uploader: NoNetworkStatisticsUploader(), retryDelays: [0])
        let engine = MapEngine(statisticsController: stats, evidenceController: evidence)
        // Missing stable identity reaches a real pre-write failure, without device access.
        let unstable = DeviceIdentity(manufacturer: "Garmin", model: identity.model, family: identity.family, variant: identity.variant,
            usbVendorId: identity.usbVendorId, usbProductId: identity.usbProductId, firmware: identity.firmware,
            storageCapacity: identity.storageCapacity, freeSpace: identity.freeSpace)
        engine.setDiagnosticTestIdentity(unstable)
        let operationID = UUID()
        // Authorization precedes diagnostic-producing installation preflight.
        engine.beginInstallation(plan: plan(), operationId: operationID)
        check(engine.mapStatisticsEvents.isEmpty && store.events().isEmpty,
              "unavailable authorization blocks before installation diagnostics")
        let policyURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../../../contracts/fixtures/installation-policy.valid.json")
        let policy = try JSONDecoder().decode(InstallationAuthorizationDocument.self,
            from: Data(contentsOf: policyURL))
        let authorization = InstallationAuthorizationState.approved(
            record: policy.devices[0], policyVersion: policy.policyVersion)
        check(authorization.matches(identity: unstable), "catalog fixture matches diagnostic test identity")
        engine.setInstallationAuthorization(authorization)
        engine.beginInstallation(plan: plan(), operationId: operationID)
        check(engine.mapStatisticsEvents.contains { $0.eventType == .installFailed && $0.operationId == operationID },
              "fixture reaches the real INSTALL_FAILED branch")
        // Reset all engine/view state before the queued upload gets a main-actor turn.
        engine.resetForDisconnectedDevice()
        await engine.waitForDiagnosticDeliveryForTesting()
        check(store.events().count == 1 && store.events()[0].operationId == operationID && store.events()[0].phaseOutcome == .failed,
              "REGRESSION: real engine creates a correlated device report without ConnectScreen, even after reset")
        check(store.events()[0].model == unstable.presentationModel && store.events()[0].writeStarted == false,
              "original model and observed pre-write facts survive reset")
        let received = await uploader.received
        check(received.count == 1 && store.pendingUploads().isEmpty, "actual controller sends the stored failure")
    }
    @MainActor static func testResultsAndPrivacy() async throws {
        var fixtures: [InstallationEvidenceEvent] = []
        for failure in [InstallationFailure.insufficientSpace, .preflightMTPReadFailed, .writeFailed, .hashMismatch, .deviceDisconnected] {
            let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: root) }
            let store = LocalInstallationEvidenceStore(rootURL: root)
            let upload = DiagnosticUploadRecorder()
            let controller = InstallationEvidenceController(store: store, uploader: upload, automaticRetryDelays: [0])
            let selection = plan()
            let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: selection, controller: controller)
            let package = selection.installItems[0].package
            let artifact = selection.selectedPackagePlans[0].artifactPlan.selectedArtifacts[0]
            let wrote = failure != .insufficientSpace && failure != .preflightMTPReadFailed
            let result = result(package: package, failure: failure, wrote: wrote)
            operation.record(result, packageID: package.id, artifactID: artifact.id)
            operation.record(result, packageID: package.id, artifactID: artifact.id)
            await operation.waitForDeliveryForTesting()
            let events = store.events()
            check(events.count == 1 && events[0].failureCode == failure.rawValue && events[0].phaseOutcome == .failed,
                  "one report for repeated \(failure.rawValue) callback")
            check(events[0].writeStarted == wrote, "writeStarted comes only from result diagnostics")
            check(events[0].failureStage == (failure == .hashMismatch ? .verify : ((failure == .insufficientSpace || failure == .preflightMTPReadFailed) ? .preflight : .write)),
                  "failure stage matches the failed operation")
            let received = await upload.received
            check(received == events, "persisted and uploaded reports match exactly")
            let payload = String(decoding: try JSONEncoder().encode(events), as: UTF8.self)
            check(!payload.contains("PRIVATE") && !payload.contains("/GARMIN") && !payload.contains("/Users") && !payload.contains("SECRET-RAW"),
                  "private identity, paths, hashes and native log text never enter the queue payload")
            fixtures += events
        }
        // Optional transport to the backend regression: actual encoded Swift reports.
        emittedFixtures += fixtures
    }
    @MainActor static func testPartialBatchAndPreflight() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root), uploader: DiagnosticUploadRecorder(), automaticRetryDelays: [0])
        let selection = plan(regions: ["FRA", "LTU", "DEU"], contours: true)
        let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: selection, controller: controller)
        let a = selection.selectedPackagePlans[0], b = selection.selectedPackagePlans[1]
        for artifact in a.artifactPlan.selectedArtifacts {
            operation.record(result(package: a.item.package, failure: nil, wrote: true), packageID: a.item.package.id, artifactID: artifact.id)
        }
        operation.record(result(package: b.item.package, failure: nil, wrote: true), packageID: b.item.package.id, artifactID: b.artifactPlan.selectedArtifacts[0].id)
        operation.record(result(package: b.item.package, failure: .hashMismatch, wrote: true), packageID: b.item.package.id, artifactID: b.artifactPlan.selectedArtifacts[1].id)
        await operation.waitForDeliveryForTesting()
        let events = controller.store.events().sorted { $0.mapResultIndex! < $1.mapResultIndex! }
        check(events.map(\.phaseOutcome) == [.succeeded, .succeeded, .notStarted], "main success survives context-free failed contour; later map NOT_STARTED")
        check(events[1].optionalComponentFailureCode == InstallationFailure.hashMismatch.rawValue
            && events[1].optionalComponentFailureStage == .verify && events[1].failureStage == nil,
              "failed contour details are retained instead of successful main-component details")
        check(events[2].writeStarted == false && events[2].nativeFailureCode == nil,
              "NOT_STARTED never inherits another map's native error or write evidence")
        check(Set(events.map(\.operationId)).count == 1 && events.allSatisfy { $0.selectedMapCount == 3 },
              "batch retains one operation and original per-map indices")
        let preflight = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: selection, controller: controller)
        preflight.record(result(package: a.item.package, failure: nil, wrote: false, confirmation: true), packageID: a.item.package.id, artifactID: a.artifactPlan.selectedArtifacts[0].id)
        preflight.failed(index: 1, stage: .preflight, failure: .insufficientSpace)
        await preflight.waitForDeliveryForTesting()
        let beforeWrite = controller.store.events().filter { $0.operationId == preflight.operationID }.sorted { $0.mapResultIndex! < $1.mapResultIndex! }
        check(beforeWrite.map(\.phaseOutcome) == [.notStarted, .failed, .notStarted],
              "successful preflight does not become a failed or successful installation")
        let afterSuccess = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: plan(regions: ["FRA", "LTU"]), controller: controller)
        let pair = plan(regions: ["FRA", "LTU"])
        afterSuccess.record(result(package: pair.installItems[0].package, failure: nil, wrote: true), packageID: pair.installItems[0].package.id,
            artifactID: pair.selectedPackagePlans[0].artifactPlan.selectedArtifacts[0].id)
        afterSuccess.failed(index: 1, stage: .preflight, failure: .preflightMTPReadFailed,
            native: .preflightMTPReadFailed,
            context: InstallationFailureContext(boundary: .initialInventory,
                classificationSource: .derived, devicePresence: .unknown, operation: .inventory))
        await afterSuccess.waitForDeliveryForTesting()
        let unexpected = controller.store.events().filter { $0.operationId == afterSuccess.operationID }
        check(unexpected.contains { $0.phaseOutcome == .succeeded } && unexpected.contains { $0.failureCode == "INSTALL_FAILED_PREFLIGHT_MTP_READ" && $0.writeStarted == false },
              "later read failure preserves earlier success and does not guess a disconnect")
    }
    @MainActor static func testContextFreeContourPreflight() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root),
            uploader: DiagnosticUploadRecorder(), automaticRetryDelays: [0])
        for thrownFailure in [false, true] {
            let selection = plan(contours: true)
            let packagePlan = selection.selectedPackagePlans[0]
            let package = packagePlan.item.package
            let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
                plan: selection, controller: controller)
            operation.record(result(package: package, failure: nil, wrote: true),
                packageID: package.id, artifactID: packagePlan.artifactPlan.mainArtifact!.id)
            if thrownFailure {
                operation.failed(index: 0, stage: .preflight, failure: .insufficientSpace,
                    componentKind: .contours)
            } else {
                operation.record(result(package: package, failure: .insufficientSpace, wrote: false),
                    packageID: package.id, artifactID: packagePlan.artifactPlan.optionalArtifacts[0].id)
            }
            await operation.waitForDeliveryForTesting()
            let event = controller.store.events().first { $0.operationId == operation.operationID }!
            check(event.phaseOutcome == .succeeded && event.failureStage == nil && event.failureCode == nil
                && event.optionalComponentOutcome == "FAILED" && event.optionalComponentSelected == true
                && event.optionalComponentFailureStage == .preflight
                && event.optionalComponentFailureCode == InstallationFailure.insufficientSpace.rawValue
                && event.failureContext == nil && event.originalFailureContext == nil
                && event.writeStarted == true,
                "context-free contours preflight failure preserves main success without fabricated context")
            emittedFixtures.append(event)
        }
    }

    @MainActor static func testRetainedReadReport() throws {
        let observed = InstallationFailureContext(boundary: .initialSnapshot, classificationSource: .derived,
            devicePresence: .unknown, operation: .snapshot, executionMode: .inProcess,
            resultKind: .nativeError, nativeCategory: .detection,
            nativeCodeNamespace: .terentoSnapshot, nativeResultCode: -2, componentKind: .main)
        let error = InstallationTransportError.contextual(failure: .operationFailed,
            message: "PRIVATE-NATIVE-TEXT /Users/private/map.img", createdItemID: nil, context: observed)
        let engine = MapEngine()
        engine.retainReadFailureContext(error)
        check(engine.installationResult == nil && engine.evidenceFailureContext == observed
            && engine.evidenceFailure == .preflightMTPReadFailed && engine.evidenceFailureStage == .preflight
            && engine.evidenceNativeFailureCode == .preflightMTPReadFailed
            && engine.evidenceOriginalFailureContext == nil,
            "initial read evidence is retained without a coordinator result")
        let report = InstallationIssueReport.generate(identity: identity, maps: [], stage: "preflight",
            error: engine.evidenceFailure?.userLabel, operationID: UUID(),
            failureStages: [engine.evidenceFailureStage!.rawValue],
            errorCodes: [engine.evidenceFailure!.rawValue], writeStarted: false,
            failureContext: engine.evidenceFailureContext,
            originalFailureContext: engine.evidenceOriginalFailureContext)
        check(report.body.contains("initial_snapshot") && report.body.contains("detection")
            && report.body.contains("terento_snapshot") && report.body.contains("-2")
            && !report.body.contains("PRIVATE-NATIVE-TEXT") && !report.body.contains("/Users/private"),
            "local initial-read report uses retained bounded native evidence")
        check(!MapEngine.isObservedCancellation(error) && MapEngine.isObservedCancellation(CancellationError()),
            "actual error provenance distinguishes concrete failure from CancellationError")
        let cancelled = MTPFinishingWorker.failure(for: .inventory, kind: .cancelled)
        check(MapEngine.isObservedCancellation(cancelled), "native cancellation remains an observed cancellation")
    }

    @MainActor static func testObservedReadSurvivesCancellation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root),
            uploader: DiagnosticUploadRecorder(), automaticRetryDelays: [0])
        let observed = InstallationFailureContext(boundary: .initialSnapshot, classificationSource: .derived,
            devicePresence: .unknown, operation: .snapshot, executionMode: .inProcess,
            resultKind: .nativeError, nativeCategory: .detection,
            nativeCodeNamespace: .terentoSnapshot, nativeResultCode: -2, componentKind: .main)
        for laterAbsence in [false, true] {
            let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
                plan: plan(), controller: controller)
            if laterAbsence { operation.deviceDisconnected() }
            operation.failed(index: 0, stage: .preflight, failure: .preflightMTPReadFailed,
                native: .preflightMTPReadFailed, cancelled: true, context: observed)
            await operation.waitForDeliveryForTesting()
            let event = controller.store.events().first { $0.operationId == operation.operationID }!
            check(event.failureCode == InstallationFailure.preflightMTPReadFailed.rawValue
                && event.nativeFailureCode == .preflightMTPReadFailed && event.errorCategory == .transport
                && event.failureContext == observed && event.failureStage == .preflight
                && event.writeStarted == false && event.cleanupAttempted == false,
                "concrete native read failure survives later task cancellation and presence invalidation")
            emittedFixtures.append(event)
        }
        let cancelled = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
            plan: plan(), controller: controller)
        cancelled.failed(index: 0, stage: .preflight, failure: .preflightMTPReadFailed,
            native: .preflightMTPReadFailed, cancelled: true,
            context: InstallationFailureContext(boundary: .prewriteInventory, classificationSource: .derived,
                devicePresence: .unknown, operation: .inventory, resultKind: .cancelled))
        await cancelled.waitForDeliveryForTesting()
        check(!controller.store.events().contains { $0.operationId == cancelled.operationID },
              "actual native cancellation remains cancellation despite preflight mapping")
    }

    @MainActor static func testContextualContours() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root),
            uploader: DiagnosticUploadRecorder(), automaticRetryDelays: [0])
        for cleanupFailed in [false, true] {
            let selection = plan(contours: true)
            let packagePlan = selection.selectedPackagePlans[0]
            let package = packagePlan.item.package
            let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
                plan: selection, controller: controller)
            operation.record(result(package: package, failure: nil, wrote: true, cleanupSucceeded: cleanupFailed),
                packageID: package.id, artifactID: packagePlan.artifactPlan.mainArtifact!.id)
            let protection = InstallationFailureContext(boundary: .postwriteProtection,
                classificationSource: .derived, devicePresence: .unknown, operation: .protectionCheck,
                resultKind: .protectionFailed,
                protection: InstallationProtectionContext(protectionBoundary: .postWrite,
                    protectionReason: .preexistingObjectChanged, stableIdentityComparisonVersion: 1,
                    beforeObjectCount: 3, afterObjectCount: 4, changedObjectCount: 1))
            let terminal = cleanupFailed ? InstallationFailureContext(boundary: .cleanup,
                classificationSource: .derived, devicePresence: .unknown, operation: .cleanup,
                executionMode: .worker, resultKind: .timeout) : protection
            operation.record(result(package: package, failure: cleanupFailed ? .cleanupFailed : .protectionViolation,
                wrote: true, context: terminal, original: cleanupFailed ? protection : nil),
                packageID: package.id, artifactID: packagePlan.artifactPlan.optionalArtifacts[0].id)
            await operation.waitForDeliveryForTesting()
            let event = controller.store.events().first { $0.operationId == operation.operationID }!
            check(event.phaseOutcome == .succeeded && event.failureStage == nil
                && event.optionalComponentSelected == true && event.optionalComponentOutcome == "FAILED"
                && event.failureContext?.componentKind == .contours
                && event.optionalComponentFailureStage == (cleanupFailed ? .cleanup : .verify),
                "successful main retains explicit failing-contours boundary and outcome")
            check(event.originalFailureContext?.protection == (cleanupFailed ? protection.protection : nil),
                "cleanup retains original protection observation")
            if cleanupFailed {
                check(event.cleanupSucceeded == true && event.originalFailureContext?.componentKind == .contours,
                      "aggregate cleanup success does not erase contour cleanup failure")
            }
            emittedFixtures.append(event)
        }
    }

    @MainActor static func testReadBoundaryAndPresence() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root),
            uploader: DiagnosticUploadRecorder(), automaticRetryDelays: [0])
        var category: Int32 = 0
        let snapshotResult = terento_mtp_read_snapshot_diagnostic(nil, nil, 0, &category)
        check(snapshotResult == -1
            && category == TERENTO_READ_INVALID_ARGUMENT,
            "native invalid snapshot argument retains category without opening a device")
        check(terento_mtp_read_file_inventory_diagnostic(nil, nil, 0, &category) == -1
            && category == TERENTO_READ_INVALID_ARGUMENT,
            "native invalid inventory argument retains category without opening a device")
        let observedNative = MTPTransport.nativeReadError(message: "PRIVATE-NATIVE-TEXT",
            result: snapshotResult, operation: .snapshot, namespace: .terentoSnapshot,
            boundary: .initialSnapshot, category: category)
        let nativeOperation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
            plan: plan(), controller: controller)
        let nativePlan = plan().selectedPackagePlans[0]
        nativeOperation.record(result(package: nativePlan.item.package, failure: .preflightMTPReadFailed,
            wrote: false, context: observedNative.failureContext),
            packageID: nativePlan.item.package.id, artifactID: nativePlan.artifactPlan.mainArtifact!.id)
        await nativeOperation.waitForDeliveryForTesting()
        let nativeEvent = controller.store.events().first { $0.operationId == nativeOperation.operationID }!
        check(nativeEvent.failureContext?.classificationSource == .native
            && nativeEvent.failureContext?.nativeCategory == .invalidArgument
            && nativeEvent.failureContext?.nativeResultCode == snapshotResult
            && nativeEvent.failureContext?.componentKind == .main,
            "actual C category survives Swift error, component wrapper and persisted evidence")
        emittedFixtures.append(nativeEvent)
        let categories: [InstallationFailureContext.NativeCategory] = [
            .detection, .sessionOpen, .storageRead, .inventoryRead, .objectRead, .allocation, .invalidArgument
        ]
        for (index, expected) in categories.enumerated() {
            let error = MTPTransport.nativeReadError(message: "PRIVATE-NATIVE-TEXT", result: -2,
                operation: .snapshot, namespace: .terentoSnapshot, boundary: .initialSnapshot,
                category: Int32(index + 1))
            check(error.failureContext?.nativeCategory == expected
                && error.failureContext?.classificationSource == .native
                && error.failureContext?.nativeResultCode == -2,
                "observed category is retained independently of overloaded native result")
        }
        for boundary in [InstallationFailureContext.Boundary.initialSnapshot, .initialInventory, .prewriteInventory] {
            var calls = 0
            do {
                let _: Int = try MapEngine.readAtInstallationBoundary(boundary, componentKind: .main) {
                    calls += 1
                    throw MTPTransportError.readFailed("No such file; private native text")
                }
                fatalError("read unexpectedly succeeded")
            } catch {
                guard let classified = MapEngine.readFailureDiagnostic(error) else { fatalError("lost read context") }
                check(classified.failure == .preflightMTPReadFailed && classified.context.devicePresence == .unknown,
                      "known read boundary is transport failure without inferred disconnect")
                let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
                    plan: plan(), controller: controller)
                operation.failed(index: 0, stage: .preflight, failure: classified.failure,
                    native: classified.native, context: classified.context)
                await operation.waitForDeliveryForTesting()
                let event = controller.store.events().first { $0.operationId == operation.operationID }!
                emittedFixtures.append(event)
                check(event.failureCode == classified.failure.rawValue && event.errorCategory == .transport
                    && event.failureStage == .preflight && event.writeStarted == false
                    && event.cleanupAttempted == false && event.remoteObjectCreated == false,
                    "local classification equals uploaded classification with no write or cleanup facts")
                let encoded = try JSONEncoder().encode(event)
                let decoded = try JSONDecoder().decode(InstallationEvidenceEvent.self, from: encoded)
                check(decoded.failureContext == classified.context && !String(decoding: encoded, as: UTF8.self).contains("private native"),
                      "structured context survives queue serialization without native text")
            }
            check(calls == 1, "read observation adds no probe or retry")
        }
        for presence in [InstallationFailureContext.DevicePresence.unknown, .absent] {
            let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
                plan: plan(), controller: controller)
            let engine = MapEngine(evidenceController: controller)
            engine.setOperationDiagnosticsForTesting(operation)
            engine.resetForDisconnectedDevice(presence: presence)
            operation.failed(index: 0, stage: .preflight, failure: nil, cancelled: true)
            await operation.waitForDeliveryForTesting()
            let event = controller.store.events().first { $0.operationId == operation.operationID }
            check(presence == .absent ? event?.failureCode == InstallationFailure.deviceDisconnected.rawValue : event == nil,
                  "only confirmed absence converts reset cancellation into disconnect")
        }
        check(MTPTransportError.deviceAbsent.devicePresence == .absent
            && MTPTransportError.readFailed("No Garmin connected").devicePresence == .unknown,
            "typed presence evidence never comes from error text")
        for (payload, expected) in [
            ("not JSON", InstallationFailureContext.ResultKind.decodeError),
            ("{}", .invalidResponse)
        ] {
            do {
                _ = try MTPFinishingWorker.decodeResponse(Data(payload.utf8), operation: .inventory)
                fatalError("invalid response accepted")
            } catch let error as InstallationTransportError {
                check(error.failureContext?.resultKind == expected && !error.isConfirmedDeviceDisconnected,
                      "actual worker decoder distinguishes malformed and incomplete responses")
            }
        }
        for kind in [InstallationFailureContext.ResultKind.timeout, .cancelled, .processLaunchError, .requestIOError,
                     .processExit, .responseIOError, .decodeError, .invalidResponse, .nativeError] {
            let error = MTPFinishingWorker.failure(for: .inventory, kind: kind)
            check(error.failureContext?.resultKind == kind && !error.isConfirmedDeviceDisconnected,
                  "worker category survives without inferred disconnect")
            let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
                plan: plan(), controller: controller)
            operation.failed(index: 0, stage: .preflight, failure: .preflightMTPReadFailed,
                native: .preflightMTPReadFailed, cancelled: kind == .cancelled,
                context: error.failureContext)
            await operation.waitForDeliveryForTesting()
            let events = controller.store.events().filter { $0.operationId == operation.operationID }
            check(kind == .cancelled ? events.isEmpty : events.count == 1,
                  "worker cancellation stays separate from failed reports")
            emittedFixtures += events
        }
    }

    @MainActor static func testDisconnectAndCancellation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root), uploader: DiagnosticUploadRecorder(), automaticRetryDelays: [0])
        var screenPlan: InstallationPlan? = plan()
        var screenIdentity: DeviceIdentity? = identity
        let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: screenIdentity!, plan: screenPlan!, controller: controller)
        screenPlan = nil; screenIdentity = nil
        operation.deviceDisconnected()
        operation.failed(index: 0, stage: .preflight, failure: nil, cancelled: true)
        await operation.waitForDeliveryForTesting()
        check(controller.store.events().first?.failureCode == InstallationFailure.deviceDisconnected.rawValue && controller.store.events().first?.writeStarted == false,
              "observed disconnect records original device after view state disappears without inventing a write")
        let cancelled = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: plan(), controller: controller)
        cancelled.failed(index: 0, stage: .download, failure: .downloadFailed, cancelled: true)
        await cancelled.waitForDeliveryForTesting()
        check(controller.store.events().count == 1, "user cancellation is not FAILED or an earlier-failure NOT_STARTED event")
        let batchPlan = plan(regions: ["FRA", "LTU"])
        let batchID = UUID()
        let betweenMaps = InstallationOperationDiagnostics(operationID: batchID, identity: identity, plan: batchPlan, controller: controller)
        let first = batchPlan.selectedPackagePlans[0]
        betweenMaps.record(result(package: first.item.package, failure: nil, wrote: true),
                           packageID: first.item.package.id, artifactID: first.artifactPlan.selectedArtifacts[0].id)
        betweenMaps.deviceDisconnected()
        betweenMaps.failed(index: 0, stage: .preflight, failure: nil, cancelled: true)
        await betweenMaps.waitForDeliveryForTesting()
        let batchEvents = controller.store.events().filter { $0.operationId == batchID }.sorted { $0.mapResultIndex! < $1.mapResultIndex! }
        check(batchEvents.map(\.phaseOutcome) == [.succeeded, .notStarted] && batchEvents[1].writeStarted == false,
              "disconnect between maps preserves success and records the untouched map without a fictitious failure")
    }
    @MainActor static func testRetryRestartAndConsent() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalInstallationEvidenceStore(rootURL: root)
        let failing = DiagnosticUploadRecorder(failuresRemaining: 2)
        let controller = InstallationEvidenceController(store: store, uploader: failing, automaticRetryDelays: [0])
        let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: plan(), controller: controller)
        operation.failed(index: 0, stage: .download, failure: .downloadFailed)
        await operation.waitForDeliveryForTesting()
        await controller.scheduledUploadForTesting()?.value
        check(store.events().count == 1 && store.pendingUploads().count == 1, "failed initial send and automatic retry retain the durable outbox")
        let persistedID = store.events()[0].id
        let retry = DiagnosticUploadRecorder()
        let restarted = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root), uploader: retry, automaticRetryDelays: [0])
        await restarted.scheduledUploadForTesting()?.value
        let received = await retry.received
        check(received.map(\.id) == [persistedID] && store.pendingUploads().isEmpty, "restart sends exactly the original report ID")
        restarted.decideConsent(.declined)
        let optedOut = InstallationOperationDiagnostics(operationID: UUID(), identity: identity, plan: plan(), controller: restarted)
        optedOut.failed(index: 0, stage: .preflight, failure: .insufficientSpace)
        await optedOut.waitForDeliveryForTesting()
        check(store.events().count == 2 && store.pendingUploads().isEmpty && restarted.latestDeliveryStatus == .notShared,
              "sharing off keeps local evidence without queuing or uploading it")
        let afterOptOut = await retry.received
        check(afterOptOut.count == 1, "opt-out does not send a second report")
    }
    @MainActor static func testOptOutDuringUpload() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let uploader = DiagnosticUploadRecorder()
        let controller = InstallationEvidenceController(store: LocalInstallationEvidenceStore(rootURL: root), uploader: uploader, automaticRetryDelays: [0])
        await uploader.onFirstUpload { @MainActor in controller.decideConsent(.declined) }
        let operation = InstallationOperationDiagnostics(operationID: UUID(), identity: identity,
            plan: plan(regions: ["FRA", "LTU"]), controller: controller)
        operation.failed(index: 0, stage: .preflight, failure: .insufficientSpace)
        await operation.waitForDeliveryForTesting()
        let sent = await uploader.received
        check(sent.count == 1 && controller.store.pendingUploads().isEmpty,
              "opt-out during first upload prevents the remaining queued snapshot from being sent")
        check(controller.latestDeliveryStatus == .notShared, "delivery UI reflects changed sharing preference")
    }

    static func plan(regions: [String] = ["FRA"], contours: Bool = false) -> InstallationPlan {
        let comparisons = regions.map { region in
            let package = MapPackage(id: "freizeitkarte-" + region, providerId: "freizeitkarte", regionId: region, name: region,
                version: MapVersion(year: 2026, month: 9)!, sizeBytes: 100, sourceURL: nil, releaseDate: nil, identifier: nil, installSizeBytes: 100,
                artifacts: contours ? [
                    MapArtifact(id: region + "-main", kind: .main, required: true, sizeBytes: 100, validationState: .validated),
                    MapArtifact(id: region + "-contours", kind: .contours, required: false, sourceURL: URL(string: "https://example.com/contours.img"), sizeBytes: 100, validationState: .validated)
                ] : nil)
            return MapComparison(providerName: "Freizeitkarte", regionName: region, catalogMap: package, installedMap: nil, status: .notInstalled)
        }
        let planner = MapSelectionPlanner()
        let items = planner.items(comparisons: comparisons, preflightStatuses: Dictionary(uniqueKeysWithValues: comparisons.map { ($0.id, .readyNewInstall) }), recommendedRegionID: nil)
        return planner.plan(items: items, selectedIDs: Set(items.map(\.id)), currentFreeSpace: 20_000_000_000,
            selectedOptionalArtifactIDs: contours ? Dictionary(uniqueKeysWithValues: items.map { ($0.id, Set([$0.package.regionId + "-contours"])) }) : [:])
    }
    static func result(package: MapPackage, failure: InstallationFailure?, wrote: Bool, confirmation: Bool = false,
                       context: InstallationFailureContext? = nil,
                       original: InstallationFailureContext? = nil,
                       cleanupSucceeded: Bool = false) -> MapInstallationResult {
        var diagnostics = MapInstallationDiagnostics(sourceSizeBytes: 100, sourceSHA256: "PRIVATE-HASH", targetPath: "/GARMIN/PRIVATE.img",
            bytesTransferred: wrote ? 60 : 0, transferTotalBytes: 100, elapsedMilliseconds: 1,
            remoteObjectExists: wrote, remoteSizeBytes: nil, remoteSHA256: nil,
            metadataProvider: nil, metadataRegion: nil, metadataVersion: nil, metadataWarning: "SECRET-RAW-LOG /Users/private",
            freeSpaceBefore: 1000, freeSpaceAfter: nil, projectedFreeSpace: nil, existingFilesProtectionPassed: true,
            unrelatedFilesProtectionPassed: true, writeStarted: wrote, remoteObjectCreated: wrote,
            cleanupAttempted: wrote && failure != nil, cleanupSucceeded: cleanupSucceeded, nativeFailureCode: nil)
        diagnostics.failureContext = context
        diagnostics.originalFailureContext = original
        let preflight = InstallationPreflightResult(selectedMap: package, installedMatch: nil, ownership: .unknown,
            comparisonStatus: .notInstalled, installTarget: nil, proposedFilename: nil, storagePlan: nil,
            replacementRequired: false, replacementConfirmationRequired: false,
            status: .readyNewInstall, reason: "test")
        return MapInstallationResult(status: confirmation ? .confirmationRequired : (failure == nil ? .installVerified : .failed),
            failure: failure, originalFailure: failure, cleanupFailure: nil, preflight: preflight,
            transaction: InstallationTransaction(), verification: nil, diagnostics: diagnostics, installedMap: nil)
    }
}

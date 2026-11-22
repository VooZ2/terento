import Foundation

extension Bundle { static var module: Bundle { .main } }

/// Cancel, Try again, retained artifacts and keep-awake policy. No device,
/// network or provider is used; workspaces live in a private temp directory.
@main
struct InstallationRetryTests {
    static func check(_ condition: Bool, _ message: String) {
        guard condition else {
            print("FAIL: \(message)")
            exit(1)
        }
        print("PASS: \(message)")
    }

    @MainActor static func main() async throws {
        try testRetainedArtifactCache()
        await testCancelBeforeWrite()
        testFreshInventoryIsReused()
        await testDownloadStopStatistics()
        await testMapReadSurvivesCustomMapClose()
        try testBoundedCheckBeforeRemoval()
        testRetryClassification()
        testWatchReconnectQualification()
        testWatchReconnectDecision()
        try await testRetainedDownloadSurvivesDisconnect()
        try await testDisconnectBeforeWriteKeepsDownloads()
        testActivityPolicy()
        print("PASS: installation retry and keep-awake behavior")
    }

    static func makeArtifact(root: URL, packageID: String = "freizeitkarte-fra",
                             version: MapVersion = MapVersion(year: 2026, month: 5)!,
                             sourceKind: MapSourceKind = .provider) throws -> ValidatedMapArtifact {
        let workspace = try MapAcquisitionWorkspace(rootURL: root.appendingPathComponent(UUID().uuidString))
        let img = workspace.extractionURL.appendingPathComponent("map.img")
        try FileManager.default.createDirectory(at: workspace.extractionURL, withIntermediateDirectories: true)
        try Data(repeating: 7, count: 4096).write(to: img)
        return ValidatedMapArtifact(artifactID: packageID, provider: "freizeitkarte", region: "FRA",
            canonicalRegion: "France", rawRelease: "Release 26.05", version: version, localIMGURL: img,
            workspaceRootURL: workspace.rootURL, installSizeBytes: 4096, sha256: String(repeating: "a", count: 64),
            sourcePackageURL: URL(string: "https://provider.example/FRA.zip")!, catalogPackageID: packageID,
            targetFilename: "terento_freizeitkarte_fra.img", downloadSizeBytes: 100, catalogDownloadSizeBytes: 100,
            downloadSizeMatchesCatalog: true, packageFormat: .zip, sourceKind: sourceKind)
    }

    @MainActor static func testRetainedArtifactCache() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-retry-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let engine = MapEngine(operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        let artifact = try makeArtifact(root: root)
        engine.retainArtifactsForTesting(["freizeitkarte-fra": [artifact.artifactID: artifact]])
        check(engine.retainedWorkspaceRoots.contains(artifact.workspaceRootURL!), "a validated artifact is retained after a no-write failure")
        let reused = engine.takeRetainedArtifactForTesting(packageID: "freizeitkarte-fra", artifactID: artifact.artifactID,
                                                            version: artifact.version)
        check(reused == artifact && engine.retainedWorkspaceRoots.isEmpty, "Try again takes the retained artifact instead of downloading")
        check(FileManager.default.fileExists(atPath: artifact.localIMGURL.path), "taking an artifact keeps its file for the new attempt")

        engine.retainArtifactsForTesting(["freizeitkarte-fra": [artifact.artifactID: artifact]])
        let stale = engine.takeRetainedArtifactForTesting(packageID: "freizeitkarte-fra", artifactID: artifact.artifactID,
                                                           version: MapVersion(year: 2026, month: 6)!)
        check(stale == nil && !FileManager.default.fileExists(atPath: artifact.workspaceRootURL!.path),
              "a retained artifact for an older catalog version is discarded with its workspace")

        let truncated = try makeArtifact(root: root)
        try Data(repeating: 1, count: 10).write(to: truncated.localIMGURL)
        engine.retainArtifactsForTesting(["freizeitkarte-fra": [truncated.artifactID: truncated]])
        check(engine.takeRetainedArtifactForTesting(packageID: "freizeitkarte-fra", artifactID: truncated.artifactID,
                                                    version: truncated.version) == nil,
              "a retained artifact whose file changed size is not reused")

        let custom = try makeArtifact(root: root, packageID: "custom-1", sourceKind: .custom)
        engine.retainArtifactsForTesting(["custom-1": [custom.artifactID: custom]])
        check(engine.retainedWorkspaceRoots.isEmpty, "custom imports are never retained")

        let kept = try makeArtifact(root: root)
        engine.retainArtifactsForTesting(["freizeitkarte-fra": [kept.artifactID: kept]])
        engine.purgeRetainedArtifacts()
        check(engine.retainedWorkspaceRoots.isEmpty && !FileManager.default.fileExists(atPath: kept.workspaceRootURL!.path),
              "quitting removes retained workspaces")
        check(MapEngine.retainedArtifactLifetime == 6 * 60 * 60,
              "retained artifacts last 6 hours, so a person who comes back later does not download a large map again")
    }

    @MainActor static func testCancelBeforeWrite() async {
        let engine = MapEngine(operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        check(!engine.canCancelInstallationPreparation, "Cancel is not offered while idle")
        engine.cancelInstallationPreparation()
        check(engine.state == .idle, "Cancel outside preparation is a no-op")
        engine.beginPreparationForTesting()
        check(engine.canCancelInstallationPreparation, "Cancel is offered while downloading")
        engine.cancelInstallationPreparation()
        check(engine.state == .scanned && engine.installationPhase == .idle && engine.acquisitionState == .idle
              && !engine.hasActiveTaskForTesting && !engine.canCancelInstallationPreparation,
              "Cancel stops the download task and returns to the review state")

        // QA 1.3.0-local: the cancelled download's own `.failed` (and late
        // progress) reached the engine after Cancel and opened "Installation
        // stopped". What a stopped run relays afterwards changes nothing.
        engine.beginPreparationForTesting()
        let stopped = engine.acquisitionRelaysForTesting()
        engine.cancelInstallationPreparation()
        stopped.progress(MapDownloadProgress(bytesDownloaded: 10, totalBytes: 100, bytesPerSecond: 1))
        stopped.state(.downloading)
        stopped.state(.failed)
        for _ in 0..<20 { await Task.yield() }
        try? await Task.sleep(for: .milliseconds(300))
        check(engine.state == .scanned && engine.installationPhase == .idle && engine.acquisitionState == .idle
              && engine.installationErrorMessage == nil && engine.acquisitionErrorMessage == nil
              && engine.evidenceFailure == nil && engine.installationResult == nil
              && engine.acquisitionProgress == nil && !engine.canRetryFailedInstallation,
              "Cancel during a download ends with the selection to review: no failure state, no report")

        engine.beginPreparationForTesting()
        let running = engine.acquisitionRelaysForTesting()
        running.state(.validatingDownload)
        for _ in 0..<20 { await Task.yield() }
        check(engine.installationPhase == .preparing, "a running download still reports its progress")
        engine.cancelInstallationPreparation()
    }

    /// QA 1.3.0-local: Install maps read the watch again every time it
    /// opened. The last read is reused while it is fresh: same connection,
    /// nothing written since. A write, a disconnect or a new read ends it.
    @MainActor static func testFreshInventoryIsReused() {
        let identity = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 47mm", family: "fenix", variant: "47mm",
            usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: "2244", storageCapacity: 32_000_000_000,
            freeSpace: 20_000_000_000, localHardwareIdentifier: "PRIVATE-UNIT-SERIAL",
            garminModelDescription: "fenix 8 - 47mm", garminModelPartNumber: "006-B4536-00")
        let other = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 47mm", family: "fenix", variant: "47mm",
            usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: "2244", storageCapacity: 32_000_000_000,
            freeSpace: 20_000_000_000, localHardwareIdentifier: "OTHER-UNIT-SERIAL",
            garminModelDescription: "fenix 8 - 47mm", garminModelPartNumber: "006-B4536-00")
        let engine = MapEngine(operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        check(!engine.hasFreshInventory(for: identity), "nothing to reuse before the first read")
        engine.setDiagnosticTestIdentity(identity, files: [])
        check(engine.hasFreshInventory(for: identity), "a finished read of this watch is reused")
        check(!engine.hasFreshInventory(for: other) && !engine.hasFreshInventory(for: nil),
              "another watch reads again")
        engine.noteDeviceMapsMayChange()
        check(!engine.hasFreshInventory(for: identity), "after an update or removal starts, the watch is read again")
        engine.resetForDisconnectedDevice()
        engine.setDiagnosticTestIdentity(identity, files: [])
        check(engine.hasFreshInventory(for: identity), "a new connection's read is fresh again")
        engine.resetForDisconnectedDevice()
        check(!engine.hasFreshInventory(for: identity), "a disconnect ends the reuse")
    }

    private final class RecordingStatisticsUploader: MapStatisticsEventUploading, @unchecked Sendable {
        private let lock = NSLock()
        private var uploaded: [MapStatisticsEvent] = []
        func upload(_ event: MapStatisticsEvent) async throws { append(event) }
        private func append(_ event: MapStatisticsEvent) { lock.withLock { uploaded.append(event) } }
        var events: [MapStatisticsEvent] { lock.withLock { uploaded } }
    }

    /// A cancelled download in the statistics always means the person pressed
    /// Cancel. A stop the app makes itself ends the download as interrupted.
    @MainActor static func testDownloadStopStatistics() async {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-retry-stats-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let uploader = RecordingStatisticsUploader()
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let stats = MapStatisticsEventController(store: store, uploader: uploader, retryDelays: [0])
        stats.decideConsent(.accepted)
        let engine = MapEngine(operationGate: MTPOperationGate(), statisticsController: stats,
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        let package = MapPackage(id: "bbbike-asia-china", providerId: "bbbike", regionId: "ASIA-CHINA-BBBIKE-LATIN1",
            name: "China", version: MapVersion(year: 2026, month: 5)!, sizeBytes: 100, sourceURL: nil,
            releaseDate: nil, identifier: nil)
        // The store accepts a terminal event only for a download whose start
        // it holds, as the acquisition observer records it in the app.
        func start() -> MapStatisticsEvent {
            let event = MapStatisticsEvent(operationId: UUID(), package: package, eventType: .downloadStarted,
                outcome: .unknown, acquisitionId: UUID(), acquisitionPurpose: .install, componentKind: .main)
            stats.record(event)
            return event
        }
        func terminals(_ acquisition: MapStatisticsEvent) -> [MapStatisticsEventType] {
            var seen = Set<UUID>()
            return (uploader.events + store.pendingEvents())
                .filter { $0.acquisitionId == acquisition.acquisitionId && seen.insert($0.id).inserted }
                .map(\.eventType)
                .filter { $0 != .downloadStarted }
        }

        let cancelled = start()
        engine.beginPreparationForTesting(acquisition: cancelled)
        engine.cancelInstallationPreparation()
        check(terminals(cancelled) == [.downloadCancelled],
              "Cancel pressed during a download is recorded as a cancelled download")

        let interrupted = start()
        engine.beginPreparationForTesting(acquisition: interrupted)
        engine.cancelActiveTaskForTesting()
        check(terminals(interrupted) == [.downloadInterrupted],
              "a download stopped by other work of the app is recorded as interrupted, not cancelled")

        let disconnected = start()
        engine.beginPreparationForTesting(acquisition: disconnected)
        engine.resetForDisconnectedDevice(presence: .absent)
        check(terminals(disconnected) == [.downloadInterrupted],
              "a download stopped by a disconnect is recorded once, as interrupted")
        await stats.flushPendingEvents()
    }

    /// Closing the custom map warning while the maps are being read stops
    /// nothing; a read stopped by other work returns Refresh instead of an
    /// endless "Reading your maps".
    @MainActor static func testMapReadSurvivesCustomMapClose() async {
        let slowCatalog = MapCatalogLoader(endpoint: URL(string: "https://catalog.example/catalog-v5.json"),
            dataLoader: { _ in
                try await Task.sleep(for: .seconds(60))
                throw URLError(.timedOut)
            })
        let engine = MapEngine(catalogLoader: slowCatalog, operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        engine.scanDeviceMaps()
        check(engine.state == .loadingCatalog && engine.hasActiveTaskForTesting, "a map read is running")
        engine.clearCustomMapImport()
        check(engine.state == .loadingCatalog && engine.hasActiveTaskForTesting,
              "closing the custom map warning does not stop the map read")
        engine.cancelActiveTaskForTesting()
        for _ in 0..<100 where engine.state == .loadingCatalog {
            try? await Task.sleep(for: .milliseconds(20))
        }
        check(engine.state == .failed && engine.userErrorMessage == UserFacingErrorMessage.mapReadStopped && !engine.isBusy,
              "a stopped map read ends with the read failure and Refresh, not a locked page")
    }

    private final class RequestLog: @unchecked Sendable {
        private let lock = NSLock()
        private var requests: [MTPFinishingWorker.Request] = []
        func record(_ request: MTPFinishingWorker.Request) { lock.withLock { requests.append(request) } }
        var all: [MTPFinishingWorker.Request] { lock.withLock { requests } }
    }

    /// The check before removal reads the watch in the bounded worker with
    /// the bound of the last map read; a watch that stops answering ends
    /// Remove with the reconnect message, and nothing is removed.
    static func testBoundedCheckBeforeRemoval() throws {
        let profile = try JSONDecoder().decode(DeviceMapOperationProfile.self, from: Data("""
            {"version":2,"vendorID":2334,"productID":20480,"manufacturer":"Garmin","rawModel":"fenix 8",
             "targetDirectory":"/GARMIN","physicalIdentifier":"TEST-UNIT-0001","physicalIdentifierSource":2,
             "expectedStorageID":65537}
            """.utf8))
        let target = SafeDeleteTarget(deviceKey: "test-device",
            mapIdentity: MapIdentity(provider: "freizeitkarte", region: "FRA")!, ownership: .managedByTerento,
            objectID: 7, expectedPath: "/GARMIN/terento_freizeitkarte_fra.img",
            expectedFilename: "terento_freizeitkarte_fra.img", expectedSizeBytes: 4096,
            expectedSHA256: String(repeating: "a", count: 64))
        let log = RequestLog()
        let stalled = MTPSafeDeleteTransport(operationProfile: profile, operationGate: MTPOperationGate(),
            boundedInventoryObjectCount: 470, inventoryWorker: { request in
                log.record(request)
                throw MTPFinishingWorker.failure(for: .inventory, kind: .timeout)
            })
        do {
            _ = try stalled.inspectExactObject(target)
            check(false, "a stalled check before removal must fail")
        } catch let error as SafeDeleteTransportError {
            guard case .deviceBusy = error else {
                check(false, "a stalled check before removal asks to reconnect the device, got \(error)")
                return
            }
        }
        let request = log.all.first
        check(log.all.count == 1 && request?.operation == .inventory && request?.profile == profile
              && request?.mapScope == nil && request?.expectedObjectCount == 470,
              "the check before removal is the same inventory read, run once in the bounded worker")
        check(request.map { abs(MTPFinishingWorker.timeout(for: $0, sampleTimeout: 600) - 74.1) < 0.001 } == true,
              "the check before removal ends after about 75 s for a device with 470 objects")

        let answered = MTPSafeDeleteTransport(operationProfile: profile, operationGate: MTPOperationGate(),
            boundedInventoryObjectCount: 470, inventoryWorker: { _ in
                MTPFinishingWorker.Response(files: [DeviceFile(itemID: 7, parentID: 1, storageID: 65537,
                    path: target.expectedPath, filename: target.expectedFilename, sizeBytes: 4096, isFolder: false)])
            })
        let object = try answered.inspectExactObject(target)
        check(object.file.path == target.expectedPath && !object.contentHashVerified,
              "a device that answers passes the same identity checks as before")
    }

    @MainActor static func testRetryClassification() {
        let engine = MapEngine(operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        for failure in [InstallationFailure.downloadFailed, .preflightMTPReadFailed, .deviceDisconnected,
                        .writeFailed, .installationAuthorizationUnavailable] {
            engine.setFailedInstallationForTesting(failure)
            check(engine.canRetryFailedInstallation, "\(failure.rawValue) offers Try again")
        }
        for failure in [InstallationFailure.sourceArtifactInvalid, .existingMapConflict, .insufficientSpace,
                        .protectionViolation, .hashMismatch, .installationAuthorization, .cleanupFailed] {
            engine.setFailedInstallationForTesting(failure)
            check(!engine.canRetryFailedInstallation, "\(failure.rawValue) does not offer Try again")
        }
        check(!MapEngine.retainsArtifactsForRetry(after: .sourceValidationFailed)
              && !MapEngine.retainsArtifactsForRetry(after: .hashMismatch)
              && MapEngine.retainsArtifactsForRetry(after: .preflightMTPReadFailed)
              && MapEngine.retainsArtifactsForRetry(after: .downloadFailed),
              "only sources that passed validation are retained")
    }

    static func snapshotContext(_ code: Int32, boundary: InstallationFailureContext.Boundary = .initialSnapshot,
                                presence: InstallationFailureContext.DevicePresence = .unknown,
                                namespace: InstallationFailureContext.NativeCodeNamespace = .terentoSnapshot)
        -> InstallationFailureContext {
        InstallationFailureContext(boundary: boundary, classificationSource: .native, devicePresence: presence,
            operation: .snapshot, nativeCodeNamespace: namespace, nativeResultCode: code)
    }

    /// Only a stop before the current write, with nothing of the operation
    /// written, waits for the watch: busy (-5), no longer visible (-2/-3) or
    /// a confirmed unplug.
    static func testWatchReconnectQualification() {
        for code: Int32 in [-5, -2, -3] {
            check(WatchReconnectWaitPolicy.qualifies(failure: .preflightMTPReadFailed,
                    context: snapshotContext(code), wroteAnyComponent: false),
                  "a pre-write snapshot \(code) waits for the device to be reconnected")
        }
        check(WatchReconnectWaitPolicy.qualifies(failure: .deviceDisconnected,
                context: snapshotContext(-1, boundary: .prewriteInventory, presence: .absent, namespace: .terentoInventory),
                wroteAnyComponent: false),
              "an unplug seen by the last read before the write waits for the device")
        check(WatchReconnectWaitPolicy.qualifies(failure: .preflightMTPReadFailed,
                context: snapshotContext(-1, boundary: .initialInventory, presence: .absent, namespace: .terentoInventory),
                wroteAnyComponent: false),
              "a pre-write read of a device confirmed gone waits for the device")
        check(!WatchReconnectWaitPolicy.qualifies(failure: .preflightMTPReadFailed,
                context: snapshotContext(-5), wroteAnyComponent: true),
              "a busy device after an earlier map of the same installation was written does not wait")
        check(!WatchReconnectWaitPolicy.qualifies(failure: .preflightMTPReadFailed,
                context: snapshotContext(-1, boundary: .initialInventory, namespace: .terentoInventory),
                wroteAnyComponent: false),
              "another pre-write read failure ends as before")
        check(!WatchReconnectWaitPolicy.qualifies(failure: .writeFailed,
                context: snapshotContext(-5, boundary: .write), wroteAnyComponent: false),
              "a failure at or after the write never waits")
        check(!WatchReconnectWaitPolicy.qualifies(failure: .preflightMTPReadFailed, context: nil, wroteAnyComponent: false),
              "a failure without its read context never waits")
        check(!WatchReconnectWaitPolicy.qualifies(failure: .protectionViolation,
                context: snapshotContext(-5, boundary: .prewriteInventory), wroteAnyComponent: false),
              "a protection stop never waits")
    }

    static func testWatchReconnectDecision() {
        let start = Date(timeIntervalSince1970: 1_000_000)
        var wait = WatchReconnectWait(watchKey: "watch-a", selectedMapIDs: ["freizeitkarte-fra"],
            selectedOptionalArtifactIDs: [:], mapTitle: "France", failureReason: "Your device may be in use.",
            watchWasBusy: true, now: start)
        let soon = start.addingTimeInterval(30)
        func decide(_ wait: WatchReconnectWait, now: Date? = nil, connected: Bool = true, key: String? = "watch-a",
                    scanned: Bool = true, resolved: Bool = true) -> WatchReconnectWaitPolicy.Decision {
            WatchReconnectWaitPolicy.decision(for: wait, now: now ?? soon, deviceConnected: connected,
                connectedWatchKey: key, mapScanReady: scanned, authorizationResolved: resolved)
        }
        check(WatchReconnectWait.timeout == 5 * 60, "Terento waits up to 5 minutes for the device")
        check(MapEngine.retainedArtifactLifetime > WatchReconnectWait.timeout,
              "the kept download outlives the whole wait")
        check(decide(wait) == .keepWaiting, "the stopped session alone never continues; a reconnect is required")
        wait.watchWasDisconnected = true
        check(decide(wait, connected: false) == .keepWaiting, "while no device is connected Terento keeps waiting")
        check(decide(wait, key: "watch-b") == .differentWatch, "a different device stops the installation")
        check(decide(wait, key: nil) == .differentWatch, "a device without a stable identity stops the installation")
        check(decide(wait, scanned: false) == .keepWaiting, "the same device continues only after its maps are read again")
        check(decide(wait, resolved: false) == .keepWaiting, "the same device continues only after its authorization is resolved")
        check(decide(wait) == .resume, "the same device, read again and authorized, continues the installation")
        check(decide(wait, now: start.addingTimeInterval(WatchReconnectWait.timeout)) == .timedOut,
              "after 5 minutes the wait ends even if the device is back")

        var stayed = wait
        stayed.watchWasDisconnected = false
        check(WatchReconnectWaitPolicy.endMessage(for: stayed, decision: .timedOut, deviceConnected: true)
              == "Your device may be in use.", "a device that never left ends with its original failure")
        check(WatchReconnectWaitPolicy.endMessage(for: wait, decision: .timedOut, deviceConnected: false)
              == WatchReconnectWaitPolicy.timedOutMessage, "a device that never came back says so")
        check(WatchReconnectWaitPolicy.endMessage(for: wait, decision: .timedOut, deviceConnected: true)
              == WatchReconnectWaitPolicy.timedOutAfterReconnectMessage,
              "a device that came back but was not ready in time is not told it never came back")
        check(WatchReconnectWaitPolicy.endMessage(for: wait, decision: .differentWatch, deviceConnected: true)
              == WatchReconnectWaitPolicy.differentWatchMessage, "a different device says so")
        check(WatchReconnectWaitPolicy.endMessage(for: wait, decision: .keepWaiting, deviceConnected: false)
              == "Your device may be in use.", "Cancel after an unplug shows the original failure")
    }

    /// The download kept for Try again survives the unplug that the wait asks
    /// for, so the same watch continues without downloading again.
    @MainActor static func testRetainedDownloadSurvivesDisconnect() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-reconnect-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let engine = MapEngine(operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        let artifact = try makeArtifact(root: root)
        let unkept = try makeArtifact(root: root, packageID: "freizeitkarte-esp")
        engine.retainArtifactsForTesting(["freizeitkarte-fra": [artifact.artifactID: artifact]])
        // Both are still prepared for the stopped attempt when the watch leaves.
        engine.setValidatedArtifactSetsForTesting([
            "freizeitkarte-fra": [artifact.artifactID: artifact],
            "freizeitkarte-esp": [unkept.artifactID: unkept]
        ])
        engine.setStoppedBeforeWriteForWatchReconnectForTesting(true)
        // The stopped attempt has already failed and decided what it keeps.
        engine.setFailedInstallationForTesting(.preflightMTPReadFailed)
        engine.resetForDisconnectedDevice(presence: .absent)
        for _ in 0..<100 where FileManager.default.fileExists(atPath: unkept.workspaceRootURL!.path) {
            try await Task.sleep(for: .milliseconds(20))
        }
        check(!FileManager.default.fileExists(atPath: unkept.workspaceRootURL!.path),
              "a disconnect still removes prepared downloads that are not kept for Try again")
        check(!engine.stoppedBeforeWriteForWatchReconnect, "a disconnect clears the stop fact with the rest of the device state")
        check(engine.retainedWorkspaceRoots.contains(artifact.workspaceRootURL!)
              && FileManager.default.fileExists(atPath: artifact.localIMGURL.path),
              "a disconnect keeps the download kept for Try again")
        check(engine.takeRetainedArtifactForTesting(packageID: "freizeitkarte-fra", artifactID: artifact.artifactID,
                                                    version: artifact.version) == artifact,
              "after reconnecting, the kept download is reused instead of downloading again")
        engine.purgeRetainedArtifacts()
    }

    /// 1.3.0: a device that disappears after a long download but before any
    /// write (waiting for confirmation, or the pre-write check) no longer
    /// costs the download.
    @MainActor static func testDisconnectBeforeWriteKeepsDownloads() async throws {
        for phase in [InstallationProcessPhase.idle, .downloading, .preparing, .awaitingConfirmation] {
            check(MapEngine.keepsDownloadsAfterDisconnect(during: phase), "a disconnect before any write keeps downloads (\(phase))")
        }
        for phase in [InstallationProcessPhase.installing, .finishing, .completed, .failed] {
            check(!MapEngine.keepsDownloadsAfterDisconnect(during: phase),
                  "a disconnect during or after a write, or after a failure, keeps only what the operation kept (\(phase))")
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-keep-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let engine = MapEngine(operationGate: MTPOperationGate(),
            installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in throw URLError(.cancelled) }))
        let france = try makeArtifact(root: root)
        let spain = try makeArtifact(root: root, packageID: "freizeitkarte-esp")
        engine.setValidatedArtifactSetsForTesting([
            "freizeitkarte-fra": [france.artifactID: france],
            "freizeitkarte-esp": [spain.artifactID: spain]
        ])
        engine.resetForDisconnectedDevice(presence: .absent)
        try await Task.sleep(for: .milliseconds(100))
        check(engine.retainedWorkspaceRoots == [france.workspaceRootURL!, spain.workspaceRootURL!]
              && FileManager.default.fileExists(atPath: france.localIMGURL.path)
              && FileManager.default.fileExists(atPath: spain.localIMGURL.path),
              "a disconnect while waiting for confirmation keeps every validated download for Try again")
        check(!engine.releaseRetainedArtifactsForTesting(notIn: ["freizeitkarte-fra", "freizeitkarte-esp"]),
              "downloads the next operation uses are never freed for space")
        check(engine.releaseRetainedArtifactsForTesting(notIn: ["freizeitkarte-fra"])
              && engine.retainedWorkspaceRoots == [france.workspaceRootURL!]
              && !FileManager.default.fileExists(atPath: spain.workspaceRootURL!.path),
              "when the Mac is short of space, kept downloads of other maps are freed first")
        engine.purgeRetainedArtifacts()
    }

    static func testActivityPolicy() {
        check(DeviceOperationActivityPolicy.keepsMacAwake(installationPhase: .downloading, mapPreparationActive: false, lifecyclePhases: []),
              "downloading keeps the Mac awake")
        check(DeviceOperationActivityPolicy.keepsMacAwake(installationPhase: .finishing, mapPreparationActive: false, lifecyclePhases: []),
              "verification keeps the Mac awake")
        check(DeviceOperationActivityPolicy.keepsMacAwake(installationPhase: .idle, mapPreparationActive: false, lifecyclePhases: [.removingOld]),
              "Update keeps the Mac awake")
        check(DeviceOperationActivityPolicy.keepsMacAwake(installationPhase: .idle, mapPreparationActive: false, lifecyclePhases: [.removing]),
              "Remove keeps the Mac awake")
        check(!DeviceOperationActivityPolicy.keepsMacAwake(installationPhase: .completed, mapPreparationActive: false,
                                                          lifecyclePhases: [.completed, .awaitingConfirmation]),
              "an idle app or a waiting dialog lets the Mac sleep")
        check(DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: true, lifecycleOperations: []),
              "an active install warns on Quit")
        check(DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: false, lifecycleOperations: [(.update, .installing)]),
              "an Update write warns on Quit")
        check(!DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: false,
                                                            lifecycleOperations: [(.update, .downloading), (.update, .checking)]),
              "Update's download or pre-write check alone does not warn on Quit")
        check(DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: false, lifecycleOperations: [(.remove, .checking)]),
              "Remove's Checking after the delete warns on Quit")
    }
}

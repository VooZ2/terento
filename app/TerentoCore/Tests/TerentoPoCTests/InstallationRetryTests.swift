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
        await testMapReadSurvivesCustomMapClose()
        try testBoundedCheckBeforeRemoval()
        testRetryClassification()
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
        check(MapEngine.retainedArtifactLifetime == 30 * 60, "retained artifacts expire after 30 minutes")
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
                check(false, "a stalled check before removal asks to reconnect the watch, got \(error)")
                return
            }
        }
        let request = log.all.first
        check(log.all.count == 1 && request?.operation == .inventory && request?.profile == profile
              && request?.mapScope == nil && request?.expectedObjectCount == 470,
              "the check before removal is the same inventory read, run once in the bounded worker")
        check(request.map { abs(MTPFinishingWorker.timeout(for: $0, sampleTimeout: 600) - 74.1) < 0.001 } == true,
              "the check before removal ends after about 75 s for a watch with 470 objects")

        let answered = MTPSafeDeleteTransport(operationProfile: profile, operationGate: MTPOperationGate(),
            boundedInventoryObjectCount: 470, inventoryWorker: { _ in
                MTPFinishingWorker.Response(files: [DeviceFile(itemID: 7, parentID: 1, storageID: 65537,
                    path: target.expectedPath, filename: target.expectedFilename, sizeBytes: 4096, isFolder: false)])
            })
        let object = try answered.inspectExactObject(target)
        check(object.file.path == target.expectedPath && !object.contentHashVerified,
              "a watch that answers passes the same identity checks as before")
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
        check(DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: true, lifecyclePhases: []),
              "an active install warns on Quit")
        check(DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: false, lifecyclePhases: [.installing]),
              "an Update write warns on Quit")
        check(!DeviceOperationActivityPolicy.writesToDevice(mapInstallActive: false, lifecyclePhases: [.downloading, .checking]),
              "downloading or checking alone does not warn on Quit")
    }
}

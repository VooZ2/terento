import Foundation

// SwiftPM normally synthesizes this for the executable target's resources.
// The standalone behavioral runner has no resource bundle, so use the
// process bundle while keeping the production source unchanged.
extension Bundle {
    static var module: Bundle { .main }
}

@main
struct MapLifecycleViewModelBehaviorTests {
    @MainActor
    static func main() async throws {
        try await testUpdateAcquisitionStatisticsCorrelation()
        try await testDetachedCancellationRetainsTransactionResult()
        try testConfirmationDisablesEject()
        try testDisconnectedDeviceCannotStartRemoval()
        try testResetInvalidatesPresentationState()
        try await testUnownedTerentoFilenameReachesRemovalConfirmation()
        try await testExternalPreparationFailure()
        try await testExternalSelectionDeviceChange()
        try await testExternalPreparationReset()
        try await testExternalPreparationReset(cancel: true)
        try testMapEngineOwnershipNamespaceBinding()

        print("PASS: 11 MapLifecycleViewModel behavior tests")
    }

    private actor DetachedEntryGate {
        var entered = false
        var continuation: CheckedContinuation<Void, Never>?
        func wait() async {
            await withCheckedContinuation { continuation in
                self.continuation = continuation
                entered = true
            }
        }
        func finish() { continuation?.resume(); continuation = nil }
    }

    private static func testDetachedCancellationRetainsTransactionResult() async throws {
        let gate = DetachedEntryGate()
        let operation = Task {
            try await CancellableDetached.run {
                await gate.wait()
                // Models the nonthrowing transaction after its write boundary.
                return "measured transaction result"
            }
        }
        while !(await gate.entered) { await Task.yield() }
        operation.cancel()
        await gate.finish()
        let result = try await operation.value
        precondition(result == "measured transaction result",
            "cancellation after transaction entry must not replace its facts with pre-entry defaults")
    }

    @MainActor
    private static func testUpdateAcquisitionStatisticsCorrelation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalMapStatisticsEventStore(rootURL: root)
        let controller = MapStatisticsEventController(store: store, retryDelays: [])
        var engine: MapEngine? = MapEngine(statisticsController: controller)
        let package = MapPackage(id: "freizeitkarte-fra", providerId: "freizeitkarte",
            regionId: "FRA", name: "France", version: MapVersion(year: 2026, month: 9)!,
            sizeBytes: 16, sourceURL: nil, releaseDate: nil, identifier: "FRA")
        let operationID = UUID()
        let observerCreated = Date()
        let observer = engine!.updateAcquisitionObserver(package: package, operationID: operationID)
        engine = nil
        try await Task.sleep(nanoseconds: 1_100_000_000)
        let actualEntry = Date()
        await Task.detached { observer(.started); observer(.processing); observer(.failed) }.value
        // Phases are persisted in callback order on the download context, before
        // any main-actor hop, so a fast terminal cannot overtake its start.
        let events = store.pendingEvents()
        precondition(events.map(\.eventType) == [.downloadStarted, .downloadProcessing, .downloadFailed],
            "update acquisition phases are durable and ordered when the observer returns")
        // The durable store uses ISO8601 seconds, so compare at persisted precision.
        let started = events.first { $0.eventType == .downloadStarted }!.timestamp
        precondition(started.timeIntervalSince1970 >= floor(actualEntry.timeIntervalSince1970)
            && started.timeIntervalSince1970 > floor(observerCreated.timeIntervalSince1970),
            "authorization/preflight time must not be included in download duration")
        precondition(events.count == 3 && Set(events.map(\.eventType)) == [.downloadStarted, .downloadProcessing, .downloadFailed])
        precondition(events.allSatisfy { $0.operationId == operationID && $0.componentKind == .main })
        precondition(Set(events.compactMap(\.acquisitionId)).count == 1)
        precondition(!events.contains { $0.eventType == .installFailed || $0.eventType == .mapUpdateFailed })
        controller.decideConsent(.declined)
        observer(.started); observer(.succeeded)
        for _ in 0..<10 { await Task.yield() }
        precondition(store.pendingEvents().isEmpty, "map-use opt-out applies to update acquisitions")
    }

    @MainActor
    private static func testConfirmationDisablesEject() throws {
        let gate = MTPOperationGate()
        let controller = MapLifecycleOperationController()
        let context = try makeContext()
        let deviceEngine = DeviceEngine(operationGate: gate)
        let mapEngine = MapEngine(operationGate: gate)
        let viewModel = MapLifecycleViewModel(
            deviceEngine: deviceEngine,
            mapEngine: mapEngine,
            operationGate: gate,
            operationController: controller,
            contextProvider: { _ in context },
            connectedDeviceProvider: { true }
        )

        viewModel.requestRemove(itemID: context.item.id)

        guard viewModel.pendingConfirmation?.action == .remove,
              viewModel.isBusy,
              !viewModel.canEject else {
            throw Failure("remove confirmation did not reserve the lifecycle UI")
        }

        viewModel.cancelPendingAction()
        guard !viewModel.isBusy, viewModel.canEject else {
            throw Failure("cancelling confirmation did not release the lifecycle UI")
        }

        guard let token = controller.begin() else {
            throw Failure("could not create a controlled lifecycle operation")
        }
        guard viewModel.isBusy, !viewModel.canEject else {
            throw Failure("an active lifecycle operation left eject enabled")
        }
        controller.finish(token)
        print("PASS: lifecycle confirmation and active operation disable eject")
    }

    @MainActor
    private static func testDisconnectedDeviceCannotStartRemoval() throws {
        let gate = MTPOperationGate()
        let context = try makeContext()
        let viewModel = MapLifecycleViewModel(
            deviceEngine: DeviceEngine(operationGate: gate),
            mapEngine: MapEngine(operationGate: gate),
            operationGate: gate,
            contextProvider: { _ in context },
            connectedDeviceProvider: { false }
        )

        viewModel.requestRemove(itemID: context.item.id)
        guard viewModel.pendingConfirmation?.action == .remove else {
            throw Failure("valid map could not reach explicit removal confirmation")
        }

        viewModel.confirmPendingAction()
        guard viewModel.operation(for: context.item.id)?.phase == .failed,
              gate.isNativeOperationActive == false else {
            throw Failure("disconnected removal was not rejected before native entry")
        }
        print("PASS: disconnected device fails closed before removal")
    }

    @MainActor
    private static func testResetInvalidatesPresentationState() throws {
        let gate = MTPOperationGate()
        let context = try makeContext()
        let viewModel = MapLifecycleViewModel(
            deviceEngine: DeviceEngine(operationGate: gate),
            mapEngine: MapEngine(operationGate: gate),
            operationGate: gate,
            contextProvider: { _ in context },
            connectedDeviceProvider: { true }
        )

        viewModel.requestRemove(itemID: context.item.id)
        viewModel.resetForDisconnectedDevice()

        guard viewModel.pendingConfirmation == nil,
              viewModel.operation(for: context.item.id) == nil,
              !viewModel.isBusy,
              viewModel.canEject else {
            throw Failure("disconnect reset left stale lifecycle presentation state")
        }
        print("PASS: disconnect reset clears stale lifecycle presentation state")
    }

    @MainActor
    private static func waitUntil(_ condition: () -> Bool) async throws {
        for _ in 0..<1000 {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(2))
        }
        throw Failure("timed out waiting for controlled preparation")
    }

    @MainActor
    private static func testUnownedTerentoFilenameReachesRemovalConfirmation() async throws {
        let gate = MTPOperationGate()
        let context = try makeContext(external: true)
        var connected = true
        let viewModel = MapLifecycleViewModel(
            deviceEngine: DeviceEngine(operationGate: gate),
            mapEngine: MapEngine(operationGate: gate), operationGate: gate,
            contextProvider: { _ in context }, connectedDeviceProvider: { connected },
            externalSelectionPreparer: { _, _, _, _, _ in
                ExternalMapSelectionEvidence(sha256: String(repeating: "a", count: 64), displayName: "Captured France")
            }
        )
        viewModel.requestRemove(itemID: context.item.id)
        guard viewModel.pendingConfirmation == nil, viewModel.isBusy else {
            throw Failure("confirmation appeared before external content was captured")
        }
        try await waitUntil { viewModel.pendingConfirmation != nil }
        guard viewModel.confirmationSubtitle == "Captured France", !gate.isNativeOperationActive else {
            throw Failure("confirmation did not use captured metadata")
        }
        connected = false
        viewModel.confirmPendingAction()
        guard viewModel.operation(for: context.item.id)?.phase == .failed, !gate.isNativeOperationActive else {
            throw Failure("external confirmation bypassed disconnected-device protection")
        }
        print("PASS: external content and displayed metadata captured before confirmation")
    }

    @MainActor
    private static func testExternalPreparationFailure() async throws {
        let gate = MTPOperationGate()
        let context = try makeContext(external: true)
        let viewModel = MapLifecycleViewModel(deviceEngine: DeviceEngine(operationGate: gate),
            mapEngine: MapEngine(operationGate: gate), operationGate: gate,
            contextProvider: { _ in context }, connectedDeviceProvider: { true },
            externalSelectionPreparer: { _, _, _, _, _ in throw Failure("injected read failure") })
        viewModel.requestRemove(itemID: context.item.id)
        try await waitUntil { !viewModel.isBusy }
        guard viewModel.pendingConfirmation == nil, viewModel.operation(for: context.item.id)?.phase == .failed else {
            throw Failure("failed preparation permitted confirmation")
        }
    }

    @MainActor
    private static func testExternalSelectionDeviceChange() async throws {
        let gate = MTPOperationGate()
        var context = try makeContext(external: true)
        let viewModel = MapLifecycleViewModel(deviceEngine: DeviceEngine(operationGate: gate),
            mapEngine: MapEngine(operationGate: gate), operationGate: gate,
            contextProvider: { _ in context }, connectedDeviceProvider: { true },
            externalSelectionPreparer: { _, _, _, _, _ in
                ExternalMapSelectionEvidence(sha256: String(repeating: "a", count: 64), displayName: "Captured map")
            })
        viewModel.requestRemove(itemID: context.item.id)
        try await waitUntil { viewModel.pendingConfirmation != nil }
        context = try makeContext(external: true, storageID: 2)
        viewModel.confirmPendingAction()
        guard viewModel.operation(for: context.item.id)?.phase == .failed, !gate.isNativeOperationActive else {
            throw Failure("changed storage crossed external selection binding")
        }
    }

    @MainActor
    private static func testExternalPreparationReset(cancel: Bool = false) async throws {
        let gate = MTPOperationGate()
        let context = try makeContext(external: true)
        let blocker = PreparationBlocker()
        let viewModel = MapLifecycleViewModel(deviceEngine: DeviceEngine(operationGate: gate),
            mapEngine: MapEngine(operationGate: gate), operationGate: gate,
            contextProvider: { _ in context }, connectedDeviceProvider: { true },
            externalSelectionPreparer: { _, _, _, _, _ in
                blocker.wait()
                return ExternalMapSelectionEvidence(sha256: String(repeating: "a", count: 64), displayName: "Old map")
            })
        viewModel.requestRemove(itemID: context.item.id)
        try await waitUntil { blocker.started }
        if cancel { viewModel.cancelPendingAction() }
        else { viewModel.resetForDisconnectedDevice() }
        blocker.release()
        try await waitUntil { !viewModel.isBusy }
        guard viewModel.pendingConfirmation == nil else { throw Failure("disconnect revived stale selection") }
    }

    private final class PreparationBlocker: @unchecked Sendable {
        private let condition = NSCondition()
        private var entered = false
        private var released = false
        var started: Bool { condition.lock(); defer { condition.unlock() }; return entered }
        func wait() {
            condition.lock(); defer { condition.unlock() }
            entered = true
            while !released { condition.wait() }
        }
        func release() { condition.lock(); released = true; condition.broadcast(); condition.unlock() }
    }

    @MainActor
    private static func testMapEngineOwnershipNamespaceBinding() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-engine-ownership-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let context = try makeContext()
        func identity(_ physical: String?) -> DeviceIdentity {
            let base = context.identity
            return DeviceIdentity(manufacturer: base.manufacturer, model: base.model, family: base.family,
                variant: base.variant, usbVendorId: base.usbVendorId, usbProductId: base.usbProductId,
                firmware: base.firmware, storageCapacity: base.storageCapacity, freeSpace: base.freeSpace,
                localHardwareIdentifier: physical, localIdentityResolution: physical == nil ? .unavailable : .mtpSerial)
        }
        let watchA = identity("TEST-WATCH-A")
        let watchB = identity("TEST-WATCH-B")
        let missing = identity(nil)
        let file = context.item.installedMaps[0].sourceFile
        let version = context.item.version!
        let store = LocalTerentoManifestStore(rootDirectory: root)
        func entry(_ key: String) -> TerentoManifestEntry {
            TerentoManifestEntry(deviceKey: key, devicePath: file.path, filename: file.filename,
                providerId: "freizeitkarte", regionId: "FRA", version: version, sizeBytes: file.sizeBytes,
                sha256: String(repeating: "a", count: 64), installedAt: Date(timeIntervalSince1970: 100))
        }
        let legacyA = entry(watchA.legacyManifestDeviceKey)
        let physicalA = entry(watchA.physicalManifestDeviceKey!)
        try store.record(legacyA)
        try store.record(physicalA)
        // Both watches expose identical map coordinates/content. That does not
        // prove that A's model-only local manifest owns the map on B.
        let unavailableKeys = MapEngine.manifestDeviceKeys(for: [watchB, missing])
        guard unavailableKeys.isEmpty,
              MapEngine.ownershipManifestEntries(for: watchB, scanDeviceKeys: unavailableKeys, store: store).isEmpty else {
            throw Failure("physical B plus unavailable live identity loaded a model-only A manifest")
        }
        let conflictKeys = MapEngine.manifestDeviceKeys(for: [watchA, watchB])
        guard conflictKeys.isEmpty,
              MapEngine.ownershipManifestEntries(for: watchB, scanDeviceKeys: conflictKeys, store: store).isEmpty,
              MapEngine.ownershipManifestEntries(for: watchB,
                scanDeviceKeys: [watchA.physicalManifestDeviceKey!], store: store).isEmpty,
              MapEngine.ownershipManifestEntries(for: watchB,
                scanDeviceKeys: [watchA.physicalManifestDeviceKey!, watchB.physicalManifestDeviceKey!], store: store).isEmpty else {
            throw Failure("conflicting physical watches mixed ownership namespaces")
        }
        guard MapEngine.manifestDeviceKeys(for: [missing, missing]).isEmpty,
              MapEngine.ownershipManifestEntries(for: missing,
                scanDeviceKeys: [missing.legacyManifestDeviceKey], store: store).isEmpty else {
            throw Failure("model-only records conferred automatic ownership")
        }
        let coherentB = MapEngine.manifestDeviceKeys(for: [watchB, watchB])
        guard coherentB == [watchB.physicalManifestDeviceKey!],
              MapEngine.ownershipManifestEntries(for: watchB, scanDeviceKeys: coherentB, store: store).isEmpty else {
            throw Failure("B inherited A's legacy or physical ownership")
        }
        let physicalB = entry(watchB.physicalManifestDeviceKey!)
        try store.record(physicalB)
        let upgradedStore = LocalTerentoManifestStore(rootDirectory: root)
        guard MapEngine.ownershipManifestEntries(for: watchB, scanDeviceKeys: coherentB, store: upgradedStore) == [physicalB] else {
            throw Failure("physically bound ownership did not survive app/store reload")
        }
        guard try store.read(deviceKey: watchA.legacyManifestDeviceKey)?.entries == [legacyA],
              try store.read(deviceKey: watchA.physicalManifestDeviceKey!)?.entries == [physicalA] else {
            throw Failure("unproven ownership evidence was deleted or migrated")
        }
        print("PASS: actual MapEngine scan/context namespace path rejects model-only and conflicting keys; physical ownership survives reload")
    }

    private static func makeContext(external: Bool = false, storageID: UInt32 = 1) throws -> MapLifecycleContext {
        guard let version = MapVersion(year: 2026, month: 5),
              MapIdentity(provider: "Freizeitkarte", region: "FRA") != nil else {
            throw Failure("could not construct deterministic lifecycle test identity")
        }

        let sourceFile = InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_fra.img",
            filename: "terento_freizeitkarte_fra.img",
            sizeBytes: 348_684_288,
            itemID: 16777326
        )
        let installedMap = InstalledMap(
            name: "Freizeitkarte France",
            provider: "Freizeitkarte",
            region: "FRA",
            family: "Freizeitkarte",
            rawVersion: "Release 26.05",
            version: version,
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: sourceFile.sizeBytes,
            sourceFile: sourceFile,
            metadataStatus: .parsed,
            managementState: external ? .detectedNotManaged : .managedByTerento
        )
        let item = MapLifecycleItem(
            id: "freizeitkarte-fra",
            title: "Freizeitkarte France",
            provider: "Freizeitkarte",
            region: "FRA",
            version: version,
            rawVersion: "Release 26.05",
            sizeBytes: sourceFile.sizeBytes,
            installedMaps: [installedMap],
            classification: external ? .externalRecognized : .terentoManaged
        )
        let deviceIdentity = DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            family: "fēnix",
            variant: nil,
            usbVendorId: 0x091e,
            usbProductId: 0x51b8,
            firmware: "2244",
            storageCapacity: 31_060_000_000,
            freeSpace: 14_540_000_000,
            localHardwareIdentifier: "local-test-watch", localIdentityResolution: .garminUnitID
        )
        let profile = DeviceInstallProfileRegistry.local.profile(for: deviceIdentity)
        let selectedMap = MapPackage(
            id: "freizeitkarte-fra",
            providerId: "Freizeitkarte",
            regionId: "FRA",
            name: "Freizeitkarte France",
            version: version,
            sizeBytes: sourceFile.sizeBytes,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil
        )
        let comparison = MapComparison(
            providerName: "Freizeitkarte",
            regionName: "France",
            catalogMap: selectedMap,
            installedMap: installedMap,
            status: .upToDate
        )

        guard let profile else {
            throw Failure("known fēnix 8 profile did not resolve")
        }

        return MapLifecycleContext(
            item: item,
            comparison: comparison,
            selectedMap: selectedMap,
            identity: deviceIdentity,
            availableStorage: deviceIdentity.freeSpace,
            profile: profile,
            deviceKey: "test-device",
            expectedSHA256ByItemID: external ? [:] : [sourceFile.itemID ?? 0: String(repeating: "a", count: 64)],
            expectedStorageID: storageID
        )
    }

    private struct Failure: Error {
        let message: String

        init(_ message: String) {
            self.message = message
        }
    }
}

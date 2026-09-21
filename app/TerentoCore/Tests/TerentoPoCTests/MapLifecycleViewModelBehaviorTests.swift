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
        try testConfirmationDisablesEject()
        try testDisconnectedDeviceCannotStartRemoval()
        try testResetInvalidatesPresentationState()
        try await testUnownedTerentoFilenameReachesRemovalConfirmation()
        try await testExternalPreparationFailure()
        try await testExternalSelectionDeviceChange()
        try await testExternalPreparationReset()
        try await testExternalPreparationReset(cancel: true)

        print("PASS: 8 MapLifecycleViewModel behavior tests")
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

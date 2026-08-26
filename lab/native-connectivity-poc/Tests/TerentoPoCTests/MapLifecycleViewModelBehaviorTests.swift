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
    static func main() throws {
        try testConfirmationDisablesEject()
        try testDisconnectedDeviceCannotStartRemoval()
        try testResetInvalidatesPresentationState()

        print("PASS: 3 MapLifecycleViewModel behavior tests")
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

    private static func makeContext() throws -> MapLifecycleContext {
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
            managementState: .managedByTerento
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
            classification: .terentoManaged
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
            freeSpace: 14_540_000_000
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
            expectedSHA256ByItemID: [sourceFile.itemID ?? 0: String(repeating: "a", count: 64)]
        )
    }

    private struct Failure: Error {
        let message: String

        init(_ message: String) {
            self.message = message
        }
    }
}

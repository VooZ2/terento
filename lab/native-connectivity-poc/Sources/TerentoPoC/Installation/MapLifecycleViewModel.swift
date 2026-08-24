import Foundation
import SwiftUI

struct MapLifecycleConfirmation: Identifiable, Equatable, Sendable {
    let itemID: String
    let action: MapLifecycleAction

    var id: String { "\(action.rawValue)-\(itemID)" }
}

private final class MapLifecycleProgressRelay: @unchecked Sendable {
    weak var viewModel: MapLifecycleViewModel?
    let itemID: String
    let action: MapLifecycleAction
    let epoch: UInt64

    init(
        viewModel: MapLifecycleViewModel,
        itemID: String,
        action: MapLifecycleAction,
        epoch: UInt64
    ) {
        self.viewModel = viewModel
        self.itemID = itemID
        self.action = action
        self.epoch = epoch
    }

    func send(_ progress: SafeUpdateProgress) {
        let viewModel = viewModel
        Task { @MainActor in
            viewModel?.receive(
                itemID: itemID,
                action: action,
                epoch: epoch,
                progress: progress
            )
        }
    }
}

/// Presentation coordinator for the Stage 5 lifecycle actions.
///
/// SwiftUI receives only resolved availability and operation state. All
/// ownership, manifest, exact-object, backup, storage, and transaction rules
/// remain in the existing domain adapters. Manual removal does not create a
/// local backup; the separate Backup action and Safe Update transaction retain
/// their own backup behavior.
@MainActor
final class MapLifecycleViewModel: ObservableObject {
    @Published private(set) var operations: [String: MapLifecycleOperationState] = [:]
    @Published private(set) var backupResults: [String: ReadBackupResult] = [:]
    @Published var pendingConfirmation: MapLifecycleConfirmation?

    private let deviceEngine: DeviceEngine
    private let mapEngine: MapEngine
    private let operationGate: MTPOperationGate
    private let operationController: MapLifecycleOperationController
    private let recoveryStore: any TerentoFailedInstallRecoveryStore
    private let contextProvider: (String) -> MapLifecycleContext?
    private let connectedDeviceProvider: () -> Bool
    private let resolver = MapLifecyclePresentationResolver()
    private var lifecycleEpoch: UInt64 = 0
    private var inFlightOperationCount = 0
    private var operationTasks: [String: Task<Void, Never>] = [:]

    init(
        deviceEngine: DeviceEngine,
        mapEngine: MapEngine,
        operationGate: MTPOperationGate = .shared,
        operationController: MapLifecycleOperationController = MapLifecycleOperationController(),
        recoveryStore: any TerentoFailedInstallRecoveryStore = LocalTerentoFailedInstallRecoveryStore(),
        contextProvider: ((String) -> MapLifecycleContext?)? = nil,
        connectedDeviceProvider: (() -> Bool)? = nil
    ) {
        self.deviceEngine = deviceEngine
        self.mapEngine = mapEngine
        self.operationGate = operationGate
        self.operationController = operationController
        self.recoveryStore = recoveryStore
        self.contextProvider = contextProvider ?? { [weak mapEngine] itemID in
            mapEngine?.lifecycleContext(for: itemID)
        }
        self.connectedDeviceProvider = connectedDeviceProvider ?? { [weak deviceEngine] in
            deviceEngine?.hasConnectedDevice == true
        }
    }

    var isBusy: Bool {
        pendingConfirmation != nil
            || inFlightOperationCount > 0
            || operationController.isBusy
            || operations.values.contains { state in
                switch state.phase {
                case .backingUp, .removing, .updating, .verifying:
                    return true
                case .idle, .awaitingConfirmation, .completed, .failed:
                    return false
                }
            }
    }

    var canEject: Bool {
        !isBusy
    }

    func resetForDisconnectedDevice() {
        lifecycleEpoch &+= 1
        operationController.invalidate()
        operationGate.invalidateLifecycleOperations()
        operationTasks.values.forEach { $0.cancel() }
        pendingConfirmation = nil
        operations.removeAll()
        backupResults.removeAll()
    }

    func operation(for itemID: String) -> MapLifecycleOperationState? {
        operations[itemID]
    }

    func availability(for item: MapLifecycleItem) -> MapLifecycleActionAvailability {
        guard let context = lifecycleContext(for: item.id) else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: "Needs refresh",
                reason: "Refresh the connected Garmin device before managing this map."
            )
        }

        return resolver.resolve(
            item: context.item,
            comparison: context.comparison,
            hasIntegrityRecord: context.hasIntegrityRecord,
            hasValidatedUpdateProfile: context.profile?.matches(context.identity) == true
                && context.profile?.supportsMapWrite == true,
            failedInstallRecovery: context.failedInstallRecovery != nil
        )
    }

    func requestBackup(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.backup),
              !isBusy else {
            return
        }

        let operationGate = self.operationGate
        let operationController = self.operationController
        guard let operationToken = operationController.begin() else { return }
        let operationEpoch = lifecycleEpoch
        let relay = MapLifecycleProgressRelay(
            viewModel: self,
            itemID: itemID,
            action: .backup,
            epoch: operationEpoch
        )
        inFlightOperationCount += 1
        setOperation(
            itemID: itemID,
            action: .backup,
            phase: .backingUp,
            progress: nil,
            message: "Creating a verified backup…"
        )

        let task = Task { [weak self] in
            let result: ReadBackupResult
            do {
                result = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await operationGate.beginLifecycleAsync()
                    defer { operationGate.endLifecycle(lease) }
                    guard operationController.isCurrent(operationToken) else {
                        throw CancellationError()
                    }

                    return ReadBackupAdapter(
                        transport: MTPReadBackupAdapter(
                            operationGate: operationGate,
                            lifecycleLease: lease
                        )
                    ).backup(
                        target: ManagedMapBackupTarget(
                            item: context.item,
                            expectedSHA256ByItemID: context.expectedSHA256ByItemID
                        ),
                        onProgress: { progress in
                            relay.send(
                                SafeUpdateProgress(
                                    state: .backingUp,
                                    bytesCompleted: progress.bytesTransferred,
                                    totalBytes: progress.totalBytes,
                                    bytesPerSecond: progress.bytesPerSecond
                                )
                            )
                        }
                    )
                }
            } catch {
                result = ReadBackupResult(
                    mapID: context.item.id,
                    status: .backupFailedDeviceDisconnected,
                    files: [],
                    message: "The Garmin connection changed before the backup could finish."
                )
            }

            guard let self else { return }
            let isCurrent = operationController.isCurrent(operationToken)
            operationController.finish(operationToken)
            operationTasks.removeValue(forKey: itemID)
            inFlightOperationCount = max(0, inFlightOperationCount - 1)
            guard isCurrent, lifecycleEpoch == operationEpoch else { return }

            backupResults[itemID] = result
            if result.isSuccess {
                setOperation(
                    itemID: itemID,
                    action: .backup,
                    phase: .completed,
                    progress: completedProgress(from: result),
                    message: "The map was backed up locally and verified."
                )
            } else {
                setOperation(
                    itemID: itemID,
                    action: .backup,
                    phase: .failed,
                    progress: nil,
                    message: result.message
                )
            }
        }
        operationTasks[itemID] = task
    }

    func requestRemove(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.remove),
              !isBusy else {
            return
        }

        pendingConfirmation = MapLifecycleConfirmation(
            itemID: itemID,
            action: .remove
        )
    }

    func requestUpdate(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.update),
              !isBusy else {
            return
        }

        pendingConfirmation = MapLifecycleConfirmation(
            itemID: itemID,
            action: .update
        )
    }

    func confirmPendingAction() {
        guard let confirmation = pendingConfirmation else { return }
        pendingConfirmation = nil

        switch confirmation.action {
        case .backup:
            requestBackup(itemID: confirmation.itemID)
        case .remove:
            remove(itemID: confirmation.itemID)
        case .update:
            update(itemID: confirmation.itemID)
        }
    }

    func cancelPendingAction() {
        pendingConfirmation = nil
    }

    var confirmationTitle: String {
        switch pendingConfirmation?.action {
        case .remove:
            return "Remove this map?"
        case .update:
            return "Update this map?"
        case .backup, .none:
            return "Confirm map action"
        }
    }

    var confirmationMessage: String {
        switch pendingConfirmation?.action {
        case .remove:
            if let itemID = pendingConfirmation?.itemID,
               contextProvider(itemID)?.failedInstallRecovery != nil {
                return "Terento will verify the exact map left by the failed installation, remove only that object, and confirm that it is gone."
            }
            return "Terento will verify the exact Terento-managed map, remove only that object, and confirm that it is gone. Other maps will be left untouched. No local backup is created."
        case .update:
            return "Terento will download and verify the new map, keep the current map as a backup, then replace only the exact Terento-managed object."
        case .backup, .none:
            return "Terento will perform only the selected safe map action."
        }
    }

    fileprivate func receive(
        itemID: String,
        action: MapLifecycleAction,
        epoch: UInt64,
        progress: SafeUpdateProgress
    ) {
        guard epoch == lifecycleEpoch else { return }

        let phase: MapLifecycleOperationPhase
        switch progress.state {
        case .backingUp:
            phase = .backingUp
        case .writing, .acquiring:
            phase = .updating
        case .validating, .revalidating, .verifying, .committing,
             .postVerifying, .reconcilingManifest:
            phase = .verifying
        case .idle, .completed, .failed:
            phase = operations[itemID]?.phase ?? .updating
        }

        let message: String
        switch phase {
        case .backingUp:
            message = "Creating a verified backup…"
        case .updating:
            message = action == .update
                ? "Preparing the map update…"
                : "Working…"
        case .verifying:
            message = "Verifying the map and device state…"
        default:
            message = operations[itemID]?.message ?? "Working…"
        }

        setOperation(
            itemID: itemID,
            action: action,
            phase: phase,
            progress: progress,
            message: message
        )
    }

    private func remove(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.remove),
              context.item.installedMaps.count == 1,
              let installedMap = context.item.installedMaps.first,
              let objectID = installedMap.sourceFile.itemID,
              let provider = context.item.provider,
              let region = context.item.region,
              let mapIdentity = MapIdentity(provider: provider, region: region),
              let expectedHash = context.expectedSHA256ByItemID[objectID],
              connectedDeviceProvider(),
              !isBusy else {
            fail(itemID: itemID, action: .remove, message: "This map could not be verified for safe removal. Nothing was changed.")
            return
        }

        guard let operationToken = operationController.begin() else { return }
        let operationEpoch = lifecycleEpoch
        inFlightOperationCount += 1
        setOperation(
            itemID: itemID,
            action: .remove,
            phase: .removing,
            progress: nil,
            message: "Removing the Terento-managed map…"
        )

        let target = SafeDeleteTarget(
            deviceKey: context.deviceKey,
            mapIdentity: mapIdentity,
            ownership: .managedByTerento,
            objectID: objectID,
            expectedPath: installedMap.sourceFile.path,
            expectedFilename: installedMap.sourceFile.filename,
            expectedSizeBytes: installedMap.sourceFile.sizeBytes,
            expectedSHA256: expectedHash,
            backup: nil,
            expectedVersion: context.item.version
        )
        let recoveryStore = self.recoveryStore
        let operationGate = self.operationGate
        let operationController = self.operationController

        let task = Task { [weak self] in
            let result: SafeDeleteResult
            do {
                result = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await operationGate.beginLifecycleAsync()
                    defer { operationGate.endLifecycle(lease) }
                    guard operationController.isCurrent(operationToken) else {
                        throw CancellationError()
                    }

                    if let recoveryRecord = context.failedInstallRecovery {
                        do {
                            try recoveryStore.record(recoveryRecord)
                        } catch {
                            return SafeDeleteResult(
                                mapIdentity: mapIdentity,
                                status: .failedManifestCleanup,
                                message: "Terento could not record the failed-install recovery safely. Nothing was changed."
                            )
                        }
                    }

                    guard operationGate.isValid(lease) else {
                        throw CancellationError()
                    }

                    let transport = MTPSafeDeleteTransport(
                        operationGate: operationGate,
                        lifecycleLease: lease
                    )
                    let deviceTransport = MTPTransport(
                        operationGate: operationGate,
                        lifecycleLease: lease
                    )
                    return MapLifecycleManager().delete(
                        target: target,
                        confirmed: true,
                        deviceConnected: operationGate.isValid(lease),
                        rescan: {
                            try deviceTransport.readFileInventory().map {
                                InstalledMapFile(
                                    path: $0.path,
                                    filename: $0.filename,
                                    sizeBytes: $0.sizeBytes,
                                    itemID: $0.itemID
                                )
                            }
                        },
                        transport: transport,
                        ownershipSource: context.failedInstallRecovery == nil
                            ? .manifest
                            : .failedInstallRecovery,
                        requiresVerifiedBackup: false
                    )
                }
            } catch {
                result = SafeDeleteResult(
                    mapIdentity: mapIdentity,
                    status: .failedDeviceDisconnected,
                    message: "The Garmin connection changed before removal could finish. The result must be checked again."
                )
            }

            guard let self else { return }
            let isCurrent = operationController.isCurrent(operationToken)
            operationController.finish(operationToken)
            operationTasks.removeValue(forKey: itemID)
            inFlightOperationCount = max(0, inFlightOperationCount - 1)
            guard isCurrent, lifecycleEpoch == operationEpoch else { return }

            if result.isSuccess {
                setOperation(
                    itemID: itemID,
                    action: .remove,
                    phase: .completed,
                    progress: nil,
                    message: "The map was removed and verified."
                )
                mapEngine.refreshCurrentDeviceMaps()
            } else {
                setOperation(
                    itemID: itemID,
                    action: .remove,
                    phase: .failed,
                    progress: nil,
                    message: result.message
                )
            }
        }
        operationTasks[itemID] = task
    }

    private func update(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.update),
              let selectedMap = context.selectedMap,
              let comparison = context.comparison,
              context.item.installedMaps.count == 1,
              let installedMap = context.item.installedMaps.first,
              let objectID = installedMap.sourceFile.itemID,
              let mapIdentity = context.item.identity,
              let version = context.item.version,
              let expectedHash = context.expectedSHA256ByItemID[objectID],
              let profile = context.profile,
              connectedDeviceProvider(),
              !isBusy else {
            fail(itemID: itemID, action: .update, message: "This map is not ready for a safe update. Nothing was changed.")
            return
        }

        let currentObject = SafeUpdateRemoteObject(
            file: installedMap.sourceFile,
            identity: mapIdentity,
            version: version,
            ownership: .managedByTerento,
            sha256: expectedHash
        )
        let request = SafeUpdateRequest(
            deviceKey: context.deviceKey,
            identity: context.identity,
            profile: profile,
            selectedMap: selectedMap,
            comparison: comparison,
            currentItem: context.item,
            currentObject: currentObject,
            backupDirectory: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
                .appendingPathComponent("Terento", isDirectory: true)
                .appendingPathComponent("Backups", isDirectory: true)
                ?? FileManager.default.temporaryDirectory.appendingPathComponent("Terento-Backups", isDirectory: true),
            confirmed: true,
            deviceConnected: true
        )
        let operationGate = self.operationGate
        let operationController = self.operationController
        guard let operationToken = operationController.begin() else { return }
        let operationEpoch = lifecycleEpoch
        let relay = MapLifecycleProgressRelay(
            viewModel: self,
            itemID: itemID,
            action: .update,
            epoch: operationEpoch
        )
        inFlightOperationCount += 1
        setOperation(
            itemID: itemID,
            action: .update,
            phase: .updating,
            progress: nil,
            message: "Preparing the map update…"
        )

        let task = Task { [weak self] in
            let result: SafeUpdateResult
            do {
                result = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await operationGate.beginLifecycleAsync()
                    defer { operationGate.endLifecycle(lease) }
                    guard operationController.isCurrent(operationToken) else {
                        throw CancellationError()
                    }

                    let liveRequest = SafeUpdateRequest(
                        deviceKey: request.deviceKey,
                        identity: request.identity,
                        profile: request.profile,
                        selectedMap: request.selectedMap,
                        comparison: request.comparison,
                        currentItem: request.currentItem,
                        currentObject: request.currentObject,
                        backupDirectory: request.backupDirectory,
                        confirmed: request.confirmed,
                        deviceConnected: operationGate.isValid(lease),
                        deviceConnectionCheck: { operationGate.isValid(lease) }
                    )
                    return await SafeUpdateTransaction().run(
                        request: liveRequest,
                        provider: MapPackageAcquisitionProvider(),
                        transport: MTPSafeUpdateTransport(
                            operationGate: operationGate,
                            lifecycleLease: lease
                        ),
                        onProgress: relay.send
                    )
                }
            } catch {
                result = SafeUpdateResult(
                    status: .failedDeviceDisconnected,
                    state: .failed,
                    message: "The Garmin connection changed before the update could finish. The result must be checked again.",
                    storagePlan: nil,
                    backup: nil,
                    newObject: nil,
                    finalObjects: [],
                    oldMapPreserved: true
                )
            }

            guard let self else { return }
            let isCurrent = operationController.isCurrent(operationToken)
            operationController.finish(operationToken)
            operationTasks.removeValue(forKey: itemID)
            inFlightOperationCount = max(0, inFlightOperationCount - 1)
            guard isCurrent, lifecycleEpoch == operationEpoch else { return }

            if result.isSuccess {
                setOperation(
                    itemID: itemID,
                    action: .update,
                    phase: .completed,
                    progress: nil,
                    message: "The map was updated and verified."
                )
                mapEngine.refreshCurrentDeviceMaps()
            } else {
                setOperation(
                    itemID: itemID,
                    action: .update,
                    phase: .failed,
                    progress: nil,
                    message: result.message
                )
            }
        }
        operationTasks[itemID] = task
    }

    private func lifecycleContext(for itemID: String) -> MapLifecycleContext? {
        contextProvider(itemID)
    }

    private func setOperation(
        itemID: String,
        action: MapLifecycleAction,
        phase: MapLifecycleOperationPhase,
        progress: SafeUpdateProgress?,
        message: String
    ) {
        operations[itemID] = MapLifecycleOperationState(
            itemID: itemID,
            action: action,
            phase: phase,
            progress: progress,
            message: message
        )
    }

    private func fail(itemID: String, action: MapLifecycleAction, message: String) {
        setOperation(
            itemID: itemID,
            action: action,
            phase: .failed,
            progress: nil,
            message: message
        )
    }

    private func completedProgress(from result: ReadBackupResult) -> SafeUpdateProgress? {
        guard let file = result.files.first else { return nil }
        return SafeUpdateProgress(
            state: .backingUp,
            bytesCompleted: file.sizeBytes,
            totalBytes: file.sizeBytes,
            bytesPerSecond: 0
        )
    }
}

private extension MapLifecycleItem {
    var identity: MapIdentity? {
        guard let provider, let region else { return nil }
        return MapIdentity(provider: provider, region: region)
    }
}

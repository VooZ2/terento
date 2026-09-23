import AppKit
import Foundation
import SwiftUI
import UniformTypeIdentifiers

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

    func sendRemoval(_ progress: SafeDeleteProgress) {
        send(SafeUpdateProgress(
            state: progress.state == .completed ? .completed : .verifying,
            bytesCompleted: progress.bytesCompleted,
            totalBytes: progress.totalBytes,
            bytesPerSecond: progress.bytesPerSecond
        ))
    }
}

/// Presentation coordinator for the Stage 5 lifecycle actions.
///
/// SwiftUI receives only resolved availability and operation state. All
/// ownership, manifest, exact-object, storage, and transaction rules remain in
/// the existing domain adapters. Manual removal does not create a local
/// backup. Safe Update keeps the old device object until the new one is
/// verified, so it does not create a redundant local copy.
@MainActor
final class MapLifecycleViewModel: ObservableObject {
    @Published private(set) var operations: [String: MapLifecycleOperationState] = [:]
    @Published var pendingConfirmation: MapLifecycleConfirmation?

    private let deviceEngine: DeviceEngine
    private let mapEngine: MapEngine
    private let operationGate: MTPOperationGate
    private let operationController: MapLifecycleOperationController
    private let recoveryStore: any TerentoFailedInstallRecoveryStore
    private let contextProvider: (String) -> MapLifecycleContext?
    private let connectedDeviceProvider: () -> Bool
    typealias ExternalSelectionPreparer = @Sendable (
        SafeDeleteTarget, DeviceMapOperationProfile, MTPOperationGate, MTPOperationLease,
        @escaping @Sendable (TransferProgress) -> Void
    ) throws -> ExternalMapSelectionEvidence
    private let externalSelectionPreparer: ExternalSelectionPreparer
    private var externalSelection: (itemID: String, profile: DeviceMapOperationProfile, target: SafeDeleteTarget, displayName: String)?
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
        connectedDeviceProvider: (() -> Bool)? = nil,
        externalSelectionPreparer: ExternalSelectionPreparer? = nil
    ) {
        self.externalSelectionPreparer = externalSelectionPreparer ?? { target, profile, gate, lease, progress in
            try MTPSafeDeleteTransport(operationProfile: profile, operationGate: gate, lifecycleLease: lease)
                .prepareExternalSelection(target, onProgress: progress)
        }
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
                case .removing, .updating, .verifying, .downloading,
                     .checking, .installing, .removingOld, .finishing:
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
        externalSelection = nil
        operations.removeAll()
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
            acquisitionAvailability: context.selectedMap.map {
                MapPackageAcquisitionPolicyResolver().availability(for: $0)
            } ?? .available,
            hasStableWatchIdentity: context.identity.localHardwareIdentifier?.isEmpty == false,
            failedInstallRecovery: context.failedInstallRecovery != nil
        )
    }

    func requestTransferOwnership(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.transferOwnership),
              let manifest = try? LocalTerentoManifestStore().read(deviceKey: context.deviceKey) else {
            return
        }

        let paths = Set(context.item.installedMaps.map(\.sourceFile.path))
        let entries = manifest.entries.filter { paths.contains($0.devicePath) }
        guard !entries.isEmpty,
              let document = try? TerentoManifestExportService().makeDocument(
                manifest: TerentoManifest(entries: entries),
                identity: context.identity
              ),
              let data = try? TerentoManifestExportService().encode(document) else {
            fail(itemID: itemID, action: .transferOwnership, message: "Terento could not prepare the ownership file.")
            return
        }

        let panel = NSSavePanel()
        panel.title = "Save Terento ownership file"
        panel.nameFieldStringValue = "Terento-\(context.item.id)-ownership.json"
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
            setOperation(
                itemID: itemID,
                action: .transferOwnership,
                phase: .completed,
                progress: nil,
                message: "Ownership file saved. Keep it private and import it only for this watch."
            )
        } catch {
            fail(itemID: itemID, action: .transferOwnership, message: "The ownership file could not be saved.")
        }
    }

    func requestRecoverOwnership(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.recoverOwnership),
              !isBusy else { return }

        // Explicit, same-Mac beta migration. A legacy model/VID/PID manifest
        // is never consumed during discovery and never assigned on connect;
        // pressing Recover deliberately binds only the exact matching entry
        // after the complete live IMG verification below.
        if let document = legacyRecoveryDocument(for: context) {
            recoverOwnership(itemID: itemID, document: document)
            return
        }

        let panel = NSOpenPanel()
        panel.title = "Choose a Terento ownership file"
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK,
              let url = panel.url,
              let data = try? Data(contentsOf: url),
              let document = try? TerentoManifestExportService().decode(data) else {
            return
        }
        recoverOwnership(itemID: itemID, document: document)
    }

    private func legacyRecoveryDocument(
        for context: MapLifecycleContext
    ) -> TerentoManifestExportDocument? {
        guard let legacyManifest = try? LocalTerentoManifestStore().read(
            deviceKey: context.identity.legacyManifestDeviceKey
        ) else {
            return nil
        }
        let liveFiles = context.item.installedMaps.map(\.sourceFile)
        let entries = legacyManifest.entries.filter { entry in
            liveFiles.contains { file in
                file.path == entry.devicePath
                    && file.filename == entry.filename
                    && file.sizeBytes == entry.sizeBytes
            }
        }
        guard entries.count == 1 else { return nil }
        return try? TerentoManifestExportService().makeDocument(
            manifest: TerentoManifest(entries: entries),
            identity: context.identity
        )
    }

    func requestRemove(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.remove),
              !isBusy else {
            return
        }

        if context.item.classification == .externalRecognized && context.failedInstallRecovery == nil {
            prepareExternalConfirmation(itemID: itemID, context: context)
        } else {
            pendingConfirmation = MapLifecycleConfirmation(itemID: itemID, action: .remove)
        }
    }

    private func prepareExternalConfirmation(itemID: String, context: MapLifecycleContext) {
        guard connectedDeviceProvider(), context.item.installedMaps.count == 1,
              let file = context.item.installedMaps.first?.sourceFile, let objectID = file.itemID,
              let identity = context.mapIdentity ?? context.item.identity ?? MapIdentity(provider: "external", region: itemID),
              let profile = DeviceMapOperationProfile(identity: context.identity, installProfile: context.profile,
                  expectedStorageID: context.expectedStorageID),
              let token = operationController.begin() else {
            fail(itemID: itemID, action: .remove, message: "The map must be read before removal can be confirmed.")
            return
        }
        externalSelection = nil
        let target = SafeDeleteTarget(deviceKey: context.deviceKey, mapIdentity: identity,
            ownership: .detectedNotManaged, objectID: objectID, expectedPath: file.path,
            expectedFilename: file.filename, expectedSizeBytes: file.sizeBytes, expectedSHA256: "",
            allowsExternalRemoval: true)
        let epoch = lifecycleEpoch
        let gate = operationGate
        let controller = operationController
        let preparer = externalSelectionPreparer
        let relay = MapLifecycleProgressRelay(viewModel: self, itemID: itemID, action: .remove, epoch: epoch)
        inFlightOperationCount += 1
        setOperation(itemID: itemID, action: .remove, phase: .checking, progress: nil,
                     message: "Reading the selected map before confirmation…")
        operationTasks[itemID] = Task { [weak self] in
            do {
                let evidence = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await gate.beginLifecycleAsync()
                    defer { gate.endLifecycle(lease) }
                    guard controller.isCurrent(token), gate.isValid(lease), !Task.isCancelled else { throw CancellationError() }
                    let result = try preparer(target, profile, gate, lease) { progress in
                        relay.send(SafeUpdateProgress(state: .verifying, bytesCompleted: progress.bytesTransferred,
                            totalBytes: progress.totalBytes, bytesPerSecond: progress.bytesPerSecond))
                    }
                    guard controller.isCurrent(token), gate.isValid(lease), !Task.isCancelled else { throw CancellationError() }
                    return result
                }
                guard let self else { controller.finish(token); return }
                let current = controller.isCurrent(token) && lifecycleEpoch == epoch && !Task.isCancelled
                controller.finish(token)
                inFlightOperationCount = max(0, inFlightOperationCount - 1)
                operationTasks.removeValue(forKey: itemID)
                guard current, connectedDeviceProvider(), NativeMutationLedger.Scope.validHash(evidence.sha256) else {
                    if lifecycleEpoch == epoch {
                        fail(itemID: itemID, action: .remove, message: "Map selection changed. Prepare removal again.")
                    }
                    return
                }
                externalSelection = (itemID, profile, SafeDeleteTarget(deviceKey: target.deviceKey,
                    mapIdentity: target.mapIdentity, ownership: target.ownership, objectID: target.objectID,
                    expectedPath: target.expectedPath, expectedFilename: target.expectedFilename,
                    expectedSizeBytes: target.expectedSizeBytes, expectedSHA256: evidence.sha256, allowsExternalRemoval: true),
                    evidence.displayName)
                setOperation(itemID: itemID, action: .remove, phase: .awaitingConfirmation, progress: nil,
                             message: "Selected map verified. Awaiting confirmation.")
                pendingConfirmation = MapLifecycleConfirmation(itemID: itemID, action: .remove)
            } catch {
                guard let self else { controller.finish(token); return }
                let current = controller.isCurrent(token) && lifecycleEpoch == epoch
                controller.finish(token)
                inFlightOperationCount = max(0, inFlightOperationCount - 1)
                operationTasks.removeValue(forKey: itemID)
                guard current else { return }
                externalSelection = nil
                fail(itemID: itemID, action: .remove, message: "The selected map could not be verified. Nothing was removed.")
            }
        }
    }

    func requestUpdate(itemID: String) {
        guard let context = lifecycleContext(for: itemID),
              availability(for: context.item).allows(.update),
              !isBusy else {
            if !deviceEngine.installationAuthorization.canInstall {
                fail(itemID: itemID, action: .update,
                     message: deviceEngine.installationAuthorization.userMessage
                        ?? "Map installation is not available for this device in Terento.")
            }
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
        case .transferOwnership:
            requestTransferOwnership(itemID: confirmation.itemID)
        case .recoverOwnership:
            requestRecoverOwnership(itemID: confirmation.itemID)
        case .remove:
            remove(itemID: confirmation.itemID)
        case .update:
            update(itemID: confirmation.itemID)
        }
    }

    func cancelPendingAction() {
        pendingConfirmation = nil
        externalSelection = nil
        operationTasks.values.forEach { $0.cancel() }
        operations = operations.filter { $0.value.phase != .awaitingConfirmation }
    }

    var confirmationTitle: String {
        switch pendingConfirmation?.action {
        case .remove:
            return "Remove this map?"
        case .update:
            return "Update this map?"
        case .transferOwnership, .recoverOwnership, .none:
            return "Confirm map action"
        }
    }

    var confirmationMessage: String {
        switch pendingConfirmation?.action {
        case .remove:
            if let itemID = pendingConfirmation?.itemID,
               let context = contextProvider(itemID),
               context.failedInstallRecovery != nil {
                return "Terento will verify the map left by the failed installation, remove only that map file, and confirm that it is gone."
            }
            if let itemID = pendingConfirmation?.itemID,
               contextProvider(itemID)?.item.classification == .externalRecognized {
                return "Terento will verify this third-party map, remove only that map file, and confirm that it is gone. Other maps will be left untouched. No local backup is created."
            }
            return "Terento will verify the Terento-managed map, remove only that map file, and confirm that it is gone. Other maps will be left untouched. No local backup is created."
        case .update:
            return "Terento will download and verify the new map, install it while the current map remains on your Garmin, then remove only the old map after the new one is verified. No local backup is created during Update."
        case .transferOwnership, .recoverOwnership, .none:
            return "Terento will perform only the selected safe map action."
        }
    }

    var confirmationSubtitle: String {
        if let selection = externalSelection, pendingConfirmation?.itemID == selection.itemID {
            return selection.displayName
        }
        guard let itemID = pendingConfirmation?.itemID,
              let item = contextProvider(itemID)?.item else {
            return "Selected map"
        }
        return item.title
    }

    private func recoverOwnership(
        itemID: String,
        document: TerentoManifestExportDocument
    ) {
        guard let context = lifecycleContext(for: itemID),
              context.item.installedMaps.count == 1,
              let operationProfile = DeviceMapOperationProfile(
                identity: context.identity,
                installProfile: context.profile,
                expectedStorageID: context.expectedStorageID
              ),
              let operationToken = operationController.begin() else { return }

        let operationEpoch = lifecycleEpoch
        let operationGate = self.operationGate
        let operationController = self.operationController
        inFlightOperationCount += 1
        setOperation(
            itemID: itemID,
            action: .recoverOwnership,
            phase: .verifying,
            progress: nil,
            message: "Verifying the complete map before restoring ownership…"
        )

        let task = Task { [weak self] in
            let result: Result<ManagedMapRecoveryResult, Error>
            do {
                let recovered = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await operationGate.beginLifecycleAsync()
                    defer { operationGate.endLifecycle(lease) }
                    guard operationController.isCurrent(operationToken) else {
                        throw CancellationError()
                    }
                    let deviceTransport = MTPTransport(
                        operationGate: operationGate,
                        lifecycleLease: lease
                    )
                    let liveFiles = try deviceTransport.readFileInventory()
                    return try ManagedMapRecoveryCoordinator().recover(
                        document: document,
                        identity: context.identity,
                        liveFiles: liveFiles,
                        reader: MTPMapReadAdapter(
                            operationProfile: operationProfile,
                            operationGate: operationGate,
                            lifecycleLease: lease
                        )
                    )
                }
                result = .success(recovered)
            } catch {
                result = .failure(error)
            }

            guard let self else { return }
            let isCurrent = operationController.isCurrent(operationToken)
            operationController.finish(operationToken)
            operationTasks.removeValue(forKey: itemID)
            inFlightOperationCount = max(0, inFlightOperationCount - 1)
            guard isCurrent, lifecycleEpoch == operationEpoch else { return }

            switch result {
            case .success:
                setOperation(
                    itemID: itemID,
                    action: .recoverOwnership,
                    phase: .completed,
                    progress: nil,
                    message: "Terento ownership was recovered for this watch."
                )
                mapEngine.refreshCurrentDeviceMaps()
            case .failure(let error):
                fail(
                    itemID: itemID,
                    action: .recoverOwnership,
                    message: error.localizedDescription
                )
            }
        }
        operationTasks[itemID] = task
    }

    fileprivate func receive(
        itemID: String,
        action: MapLifecycleAction,
        epoch: UInt64,
        progress: SafeUpdateProgress
    ) {
        guard epoch == lifecycleEpoch, operationTasks[itemID] != nil else { return }

        let phase: MapLifecycleOperationPhase
        switch progress.state {
        case .acquiring:
            phase = action == .update ? .downloading : .updating
        case .validating, .revalidating:
            phase = action == .update ? .checking : .verifying
        case .writing:
            phase = action == .update ? .installing : .updating
        case .verifying:
            phase = action == .update ? .checking : .verifying
        case .committing:
            phase = action == .update ? .removingOld : .verifying
        case .postVerifying, .reconcilingManifest:
            phase = action == .update ? .finishing : .verifying
        case .idle, .completed, .failed:
            phase = operations[itemID]?.phase ?? .updating
        }

        let message: String
        switch phase {
        case .downloading:
            message = "Downloading the new map…"
        case .checking:
            message = "Checking the map and device…"
        case .installing:
            message = "Installing the new map…"
        case .removingOld:
            message = "Removing the old map…"
        case .finishing:
            message = "Finishing the update…"
        case .updating:
            message = action == .update
                ? "Preparing the map update…"
                : "Working…"
        case .verifying:
            message = action == .remove
                ? "Removing the map and verifying the result…"
                : "Verifying the map and device state…"
        case .removing:
            message = "Removing the map and verifying the result…"
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
              !context.item.installedMaps.isEmpty,
              let operationProfile = DeviceMapOperationProfile(
                identity: context.identity,
                installProfile: context.profile,
                expectedStorageID: context.expectedStorageID
              ),
              connectedDeviceProvider(),
              !isBusy else {
            fail(itemID: itemID, action: .remove, message: "This map could not be verified for safe removal. Nothing was changed.")
            return
        }

        let installedMaps = context.item.installedMaps
        let isExternalRemoval = context.item.classification == .externalRecognized
            && context.failedInstallRecovery == nil
        let capturedSelection = externalSelection
        externalSelection = nil
        guard !isExternalRemoval || (capturedSelection?.itemID == itemID
            && capturedSelection?.profile == operationProfile
            && installedMaps.count == 1
            && capturedSelection?.target.expectedPath == installedMaps.first?.sourceFile.path
            && capturedSelection?.target.expectedFilename == installedMaps.first?.sourceFile.filename
            && capturedSelection?.target.expectedSizeBytes == installedMaps.first?.sourceFile.sizeBytes
            && capturedSelection.map { NativeMutationLedger.Scope.validHash($0.target.expectedSHA256) } == true) else {
            fail(itemID: itemID, action: .remove, message: "Prepare removal again for the current map and device. Nothing was changed.")
            return
        }
        guard Set(installedMaps.map { $0.sourceFile.path }).count == installedMaps.count else {
            fail(itemID: itemID, action: .remove, message: "The selected map components are ambiguous. Nothing was changed.")
            return
        }
        guard !isExternalRemoval || installedMaps.count == 1 else {
            fail(itemID: itemID, action: .remove, message: "Select one map to remove. Nothing was changed.")
            return
        }
        guard let mapIdentity = context.mapIdentity
                ?? context.item.identity
                ?? MapIdentity(provider: "external", region: context.item.id),
              installedMaps.allSatisfy({ $0.sourceFile.itemID != nil }),
              isExternalRemoval || installedMaps.allSatisfy({
                  guard let itemID = $0.sourceFile.itemID else { return false }
                  return context.expectedSHA256ByItemID[itemID] != nil
              }) else {
            fail(itemID: itemID, action: .remove, message: "This map could not be verified for safe removal. Nothing was changed.")
            return
        }

        guard let operationToken = operationController.begin() else { return }
        let operationEpoch = lifecycleEpoch
        FinishingTrace.beginInstallation()
        inFlightOperationCount += 1
        let relay = MapLifecycleProgressRelay(
            viewModel: self,
            itemID: itemID,
            action: .remove,
            epoch: operationEpoch
        )
        setOperation(
            itemID: itemID,
            action: .remove,
            phase: .removing,
            progress: SafeUpdateProgress(
                state: .verifying,
                bytesCompleted: 0,
                totalBytes: installedMaps.reduce(0) { $0 + $1.sourceFile.sizeBytes },
                bytesPerSecond: 0
            ),
            message: isExternalRemoval
                ? "Removing the third-party map…"
                : "Removing the Terento-managed map…"
        )

        let recoveryStore = self.recoveryStore
        let operationGate = self.operationGate
        let operationController = self.operationController

        let task = Task { [weak self] in
            var result: SafeDeleteResult?
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

                    // The approved component list is closed; each distinct artifact
                    // gets one operation-owned transport, never recreated on retry.
                    let plannedComponents = installedMaps.map { map in
                        (map, MTPSafeDeleteTransport(operationProfile: operationProfile,
                            operationGate: operationGate, lifecycleLease: lease))
                    }
                    let deviceTransport = MTPTransport(
                        operationGate: operationGate,
                        lifecycleLease: lease
                    )
                    var lastResult: SafeDeleteResult?
                    for (installedMap, transport) in plannedComponents {
                        guard let objectID = installedMap.sourceFile.itemID else {
                            lastResult = SafeDeleteResult(
                                mapIdentity: mapIdentity,
                                status: .blockedIntegrityCheck,
                                message: "This map no longer has a verified live object identity. Nothing else was removed."
                            )
                            break
                        }

                        let target = SafeDeleteTarget(
                            deviceKey: context.deviceKey,
                            mapIdentity: mapIdentity,
                            ownership: isExternalRemoval ? .detectedNotManaged : .managedByTerento,
                            objectID: objectID,
                            expectedPath: installedMap.sourceFile.path,
                            expectedFilename: installedMap.sourceFile.filename,
                            expectedSizeBytes: installedMap.sourceFile.sizeBytes,
                            expectedSHA256: isExternalRemoval ? (capturedSelection?.target.expectedSHA256 ?? "")
                                : (context.expectedSHA256ByItemID[objectID] ?? ""),
                            expectedVersion: isExternalRemoval ? nil : context.item.version,
                            allowsExternalRemoval: isExternalRemoval
                        )

                        let componentResult = MapLifecycleManager().delete(
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
                            ownershipSource: isExternalRemoval
                                ? .external
                                : (context.failedInstallRecovery == nil
                                    ? .manifest
                                    : .failedInstallRecovery),
                            onProgress: { progress in relay.sendRemoval(progress) }
                        )
                        lastResult = componentResult
                        guard componentResult.isSuccess else { break }
                    }
                    return lastResult ?? SafeDeleteResult(
                        mapIdentity: mapIdentity,
                        status: .failedOperation,
                        message: "No map component was available for removal."
                    )
                }
            } catch {
                result = SafeDeleteResult(
                    mapIdentity: mapIdentity,
                    status: .failedDeviceDisconnected,
                    message: "The Garmin connection changed before removal could finish. The result must be checked again."
                )
            }

            guard let result else { return }
            if !result.isSuccess {
                FinishingTrace.freezeFailure()
                TerentoDiagnosticLog.saveFailureReport(InstallationIssueReport.generate(
                    identity: context.identity,
                    maps: [InstallationIssueMap(provider: mapIdentity.provider,
                        region: mapIdentity.provider == "custom" ? "custom" : mapIdentity.region,
                        package: mapIdentity.provider == "custom" ? "custom-map" : mapIdentity.region,
                        release: mapIdentity.provider == "custom" ? "custom" : context.item.version?.description,
                        artifactSizeBytes: installedMaps.reduce(0) { $0 + $1.sourceFile.sizeBytes })],
                    stage: result.status.rawValue,
                    operation: .removal,
                    lifecycleFacts: ["Planned components: \(installedMaps.count)",
                        "Ownership route: \(isExternalRemoval ? "confirmed third-party removal" : "Terento-owned")"],
                    error: result.message, operationID: nil,
                    errorCodes: [result.status.rawValue]
                ))
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
                mapEngine.refreshCurrentDeviceMaps()
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
              let operationProfile = DeviceMapOperationProfile(
                identity: context.identity,
                installProfile: profile,
                expectedStorageID: context.expectedStorageID
              ),
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
            confirmed: true,
            deviceConnected: true,
            installationAuthorization: deviceEngine.installationAuthorization
        )
        let operationGate = self.operationGate
        let operationController = self.operationController
        let authorizationDeviceEngine = self.deviceEngine
        guard let operationToken = operationController.begin() else { return }
        let operationEpoch = lifecycleEpoch
        let mapStatisticsOperationID = UUID()
        FinishingTrace.beginInstallation()
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
                        confirmed: request.confirmed,
                        deviceConnected: operationGate.isValid(lease),
                        installationAuthorization: request.installationAuthorization,
                        deviceConnectionCheck: { operationGate.isValid(lease) },
                        authorizationRefresh: { identity in
                            await authorizationDeviceEngine.resolveFreshInstallationAuthorization(for: identity)
                        },
                        currentIdentity: {
                            await authorizationDeviceEngine.currentInstallationIdentity
                        }
                    )
                    return await SafeUpdateTransaction().run(
                        request: liveRequest,
                        provider: MapPackageAcquisitionProvider(),
                        transport: MTPSafeUpdateTransport(
                            operationProfile: operationProfile,
                            operationGate: operationGate,
                            lifecycleLease: lease,
                            bbbikeMetadata: BBBikeMapMetadata(package: request.selectedMap)
                        ),
                        onProgress: { progress in relay.send(progress) }
                    )
                }
            } catch {
                result = SafeUpdateResult(
                    status: .failedDeviceDisconnected,
                    state: .failed,
                    message: "The Garmin connection changed before the update could finish. The result must be checked again.",
                    storagePlan: nil,
                    newObject: nil,
                    finalObjects: [],
                    oldMapPreserved: true
                )
            }

            if !result.isSuccess {
                FinishingTrace.freezeFailure()
                TerentoDiagnosticLog.saveFailureReport(InstallationIssueReport.generate(
                    identity: context.identity,
                    maps: [InstallationIssueMap(provider: mapIdentity.provider, region: mapIdentity.region,
                        package: selectedMap.id, release: selectedMap.displayVersionLabel,
                        artifactSizeBytes: result.storagePlan?.selectedMapBytes)],
                    stage: result.status.rawValue,
                    operation: .update,
                    lifecycleFacts: ["Previous version: \(version.description)",
                        "Transaction state: \(result.state.rawValue)",
                        "Old map preserved (transaction result): \(result.oldMapPreserved)",
                        "Local backup: Not used by Safe Update",
                        "New object reported: \(result.newObject != nil)",
                        "Final inventory object count: \(result.finalObjects.count)",
                        "Available device bytes: \(result.storagePlan.map { String($0.currentFreeSpace) } ?? "Unavailable")",
                        "Required temporary bytes: \(result.storagePlan.map { String($0.requiredTemporarySpace) } ?? "Unavailable")"],
                    error: result.message, operationID: nil,
                    errorCodes: [result.status.rawValue]
                ))
            }
            if result.status != .blockedInstallationAuthorization {
                self?.mapEngine.recordMapUpdateStatistics(
                    package: selectedMap,
                    operationID: mapStatisticsOperationID,
                    outcome: result.isSuccess ? .succeeded : .failed
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

}

private extension MapLifecycleItem {
    var identity: MapIdentity? {
        guard let provider, let region else { return nil }
        return MapIdentity(provider: provider, region: region)
    }
}

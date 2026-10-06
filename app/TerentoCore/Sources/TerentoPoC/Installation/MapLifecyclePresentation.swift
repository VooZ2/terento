import Foundation

/// User-facing actions exposed by the map lifecycle screen. The availability
/// decision is kept outside SwiftUI so a button can never become a second
/// implementation of the lifecycle safety rules.
enum MapLifecycleAction: String, CaseIterable, Equatable, Hashable, Sendable {
    case transferOwnership
    case recoverOwnership
    case remove
    case update
}

struct MapLifecycleActionAvailability: Equatable, Sendable {
    let actions: Set<MapLifecycleAction>
    let status: String
    let reason: String?
    var updateBlocked: Bool = false

    func allows(_ action: MapLifecycleAction) -> Bool {
        actions.contains(action)
    }
}

/// Keeps the compact Manage Maps action group in a stable product order while
/// the resolver remains the only authority for which actions are available.
enum ManageMapRowActionPresentation: Sendable {
    static let displayOrder: [MapLifecycleAction] = [
        .update, .transferOwnership, .recoverOwnership, .remove
    ]

    static func actions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        displayOrder.filter(availability.allows)
    }

    static func primaryActions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        [.update, .remove].filter(availability.allows)
    }

    static func advancedActions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        [.transferOwnership, .recoverOwnership].filter(availability.allows)
    }

    /// Production Manage Maps deliberately exposes only product actions.
    /// Ownership export/recovery remain internal lifecycle capabilities and
    /// cannot leak into the normal release action surface.
    static func productionActions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        [.update, .remove].filter(availability.allows)
    }

    static func productionPrimaryActions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        [.update, .remove].filter(availability.allows)
    }

    static func productionMenuActions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        return []
    }
}

struct MapLifecyclePresentationResolver: Sendable {
    func resolve(
        item: MapLifecycleItem,
        comparison: MapComparison?,
        hasIntegrityRecord: Bool,
        hasValidatedUpdateProfile: Bool,
        acquisitionAvailability: MapAcquisitionAvailability = .available,
        hasStableWatchIdentity: Bool = false,
        failedInstallRecovery: Bool = false
    ) -> MapLifecycleActionAvailability {
        guard item.isInstalled else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: "Not installed",
                reason: "There is no installed map to manage."
            )
        }

        if failedInstallRecovery {
            guard item.hasExactObjectIdentity, hasIntegrityRecord else {
                return MapLifecycleActionAvailability(
                    actions: [],
                    status: "Needs verification",
                    reason: "Only the exact incomplete map can be recovered."
                )
            }

            return MapLifecycleActionAvailability(
                actions: [.remove],
                status: "Failed install recovery",
                reason: "Only the exact incomplete map can be recovered."
            )
        }

        if item.classification == .externalRecognized,
           item.hasExactObjectIdentity,
           item.installedMaps.count == 1,
           hasValidatedUpdateProfile,
           hasStableWatchIdentity {
            let hasTerentoManagedFilename = item.installedMaps.allSatisfy {
                TerentoManagedFilenameGenerator().isValid($0.sourceFile.filename)
            }

            if hasTerentoManagedFilename {
                return MapLifecycleActionAvailability(
                    actions: [.remove, .recoverOwnership],
                    status: "Recovery available",
                    reason: "Remove only this map after confirmation, or verify it to restore management."
                )
            }

            return MapLifecycleActionAvailability(
                actions: [.remove],
                status: "External map",
                reason: "Installed outside Terento. Remove only this map after confirmation."
            )
        }

        guard item.classification == .terentoManaged else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: item.classification.userLabel,
                reason: "This map is read-only and will be left unchanged."
            )
        }

        guard item.hasExactObjectIdentity, hasIntegrityRecord else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: "Read-only",
                reason: "Terento needs to verify this map before changing it."
            )
        }

        var actions: Set<MapLifecycleAction> = [.remove]
        if hasStableWatchIdentity {
            actions.insert(.transferOwnership)
        }

        if item.sourceKind == .custom {
            return MapLifecycleActionAvailability(
                actions: actions,
                status: "Custom map",
                reason: "Imported from this Mac. Terento can remove it after confirmation."
            )
        }

        var status = comparison?.status.userLabel ?? "Installed"
        var reason: String?

        if let comparison {
            switch comparison.status {
            case .updateAvailable where acquisitionAvailability != .available:
                status = "Updates are not offered for this map"
                reason = acquisitionAvailability.detailedExplanation
            case .updateAvailable where hasValidatedUpdateProfile:
                actions.insert(.update)
                status = "Update available"
            case .updateAvailable:
                status = "Update available"
                reason = "Safe update is not available for this device yet."
            case .upToDate:
                status = "Up to date"
                reason = "The installed map is current. Replacing it still requires explicit confirmation."
            case .newerInstalled:
                status = "Newer version installed"
                reason = "Terento will not downgrade a newer map."
            case .notInstalled, .unknown:
                break
            }
        }

        return MapLifecycleActionAvailability(
            actions: actions,
            status: status,
            reason: acquisitionAvailability.detailedExplanation ?? reason,
            updateBlocked: acquisitionAvailability != .available
        )
    }
}

struct MapLifecycleContext: Sendable {
    let item: MapLifecycleItem
    let comparison: MapComparison?
    let selectedMap: MapPackage?
    let identity: DeviceIdentity
    let availableStorage: UInt64
    let expectedStorageID: UInt32
    let profile: DeviceInstallProfile?
    let deviceKey: String
    let expectedSHA256ByItemID: [UInt32: String]
    /// Sampled removal proofs from the same manifest entries that supplied
    /// the hashes. Missing entries keep the full content check.
    let removalProofByItemID: [UInt32: ManagedRemovalProof]
    /// Custom maps have no provider metadata in the IMG header. The exact
    /// manifest identity is carried separately for safe lifecycle operations.
    let mapIdentity: MapIdentity?
    let failedInstallRecovery: TerentoFailedInstallRecoveryRecord?

    init(
        item: MapLifecycleItem,
        comparison: MapComparison?,
        selectedMap: MapPackage?,
        identity: DeviceIdentity,
        availableStorage: UInt64,
        profile: DeviceInstallProfile?,
        deviceKey: String,
        expectedSHA256ByItemID: [UInt32: String],
        mapIdentity: MapIdentity? = nil,
        failedInstallRecovery: TerentoFailedInstallRecoveryRecord? = nil,
        expectedStorageID: UInt32 = 0,
        removalProofByItemID: [UInt32: ManagedRemovalProof] = [:]
    ) {
        self.item = item
        self.comparison = comparison
        self.selectedMap = selectedMap
        self.identity = identity
        self.expectedStorageID = expectedStorageID
        self.availableStorage = availableStorage
        self.profile = profile
        self.deviceKey = deviceKey
        self.expectedSHA256ByItemID = expectedSHA256ByItemID
        self.removalProofByItemID = removalProofByItemID
        self.mapIdentity = mapIdentity ?? failedInstallRecovery.flatMap {
            guard MapIdentity.normalizeProvider($0.providerId) == "custom" else { return nil }
            return MapIdentity(provider: $0.providerId, region: $0.regionId)
        }
        self.failedInstallRecovery = failedInstallRecovery
    }

    var hasIntegrityRecord: Bool {
        !item.installedMaps.isEmpty
            && item.installedMaps.allSatisfy { file in
                guard let itemID = file.sourceFile.itemID else { return false }
                let hash = expectedSHA256ByItemID[itemID] ?? ""
                return hash.count == 64 && hash.allSatisfy(\.isHexDigit)
            }
    }
}

enum MapLifecycleOperationPhase: Equatable, Sendable {
    case idle
    case awaitingConfirmation
    case removing
    case updating
    case verifying
    case downloading
    case preparing
    case checking
    case installing
    case removingOld
    case finishing
    case completed
    case failed

    var userLabel: String {
        switch self {
        case .idle: return "Ready"
        case .awaitingConfirmation: return "Confirmation required"
        case .removing: return "Removing"
        case .updating: return "Updating"
        case .verifying: return "Verifying"
        case .downloading: return "Downloading"
        case .preparing: return "Preparing"
        case .checking: return "Checking"
        case .installing: return "Installing"
        case .removingOld: return "Removing old"
        case .finishing: return "Finishing"
        case .completed: return "Complete"
        case .failed: return "Could not complete"
        }
    }
}

struct MapLifecycleOperationState: Equatable, Sendable {
    let itemID: String
    let action: MapLifecycleAction
    let phase: MapLifecycleOperationPhase
    let progress: SafeUpdateProgress?
    let message: String
}

/// Decides when the Mac must stay awake and when quitting would interrupt a
/// device write. Pure presentation policy; it starts or stops nothing itself.
enum DeviceOperationActivityPolicy {
    /// Download, preparation, write, verification, Update and Remove keep the
    /// Mac from idle-sleeping; a sleeping Mac interrupts USB transfers.
    static func keepsMacAwake(
        installationPhase: InstallationProcessPhase,
        mapPreparationActive: Bool,
        lifecyclePhases: [MapLifecycleOperationPhase]
    ) -> Bool {
        let installActive: Bool
        switch installationPhase {
        case .downloading, .preparing, .awaitingConfirmation, .installing, .finishing:
            installActive = true
        case .idle, .completed, .failed:
            installActive = false
        }
        return installActive || mapPreparationActive || lifecyclePhases.contains { phase in
            switch phase {
            case .removing, .updating, .verifying, .downloading, .preparing, .checking,
                 .installing, .removingOld, .finishing:
                return true
            case .idle, .awaitingConfirmation, .completed, .failed:
                return false
            }
        }
    }

    /// True while quitting could leave an incomplete map on the watch.
    static func writesToDevice(
        mapInstallActive: Bool,
        lifecyclePhases: [MapLifecycleOperationPhase]
    ) -> Bool {
        mapInstallActive || lifecyclePhases.contains { phase in
            switch phase {
            case .removing, .updating, .verifying, .installing, .removingOld, .finishing:
                return true
            case .idle, .awaitingConfirmation, .downloading, .preparing, .checking, .completed, .failed:
                return false
            }
        }
    }
}

/// What to tell the user when the watch disconnects during Remove or Update.
/// Pure: derived from the last reported phase and progress, so the message
/// only promises what the safety order guarantees at that point.
enum MapLifecycleInterruption {
    /// Removal sends the delete command only after the full content check
    /// (reported up to 0.90); before that nothing can have been removed.
    static let removalDeleteBoundary = 0.90

    /// `fraction` is the operation's last reported completed fraction (0...1).
    static func notice(action: MapLifecycleAction, phase: MapLifecycleOperationPhase, fraction: Double) -> String? {
        switch phase {
        case .idle, .awaitingConfirmation, .completed, .failed:
            return nil
        default:
            break
        }
        switch action {
        case .remove:
            if fraction < removalDeleteBoundary {
                return "Removal didn't finish because your Garmin was disconnected. Nothing was removed, so the map is still on your watch."
            }
            return "Your Garmin was disconnected while Terento was confirming the removal. Plug it back in and open Manage maps to check whether the map was removed."
        case .update:
            switch phase {
            case .downloading, .preparing, .checking, .removing, .updating:
                return "The update didn't finish because your Garmin was disconnected. Your current map is unchanged."
            case .installing, .verifying:
                return "The update didn't finish because your Garmin was disconnected. Your current map is kept. Plug the watch back in and open Manage maps to check for an unfinished copy."
            case .removingOld, .finishing:
                return "Your Garmin was disconnected after the new version was installed. Plug it back in and open Manage maps to check whether the old version is still there."
            case .idle, .awaitingConfirmation, .completed, .failed:
                return nil
            }
        case .transferOwnership, .recoverOwnership:
            return "Your Garmin was disconnected before Terento finished. No map was changed. Plug it back in and try again."
        }
    }
}

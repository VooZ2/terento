import Foundation

/// User-facing actions exposed by the map lifecycle screen. The availability
/// decision is kept outside SwiftUI so a button can never become a second
/// implementation of the lifecycle safety rules.
enum MapLifecycleAction: String, CaseIterable, Equatable, Sendable {
    case backup
    case transferOwnership
    case recoverOwnership
    case remove
    case update
}

struct MapLifecycleActionAvailability: Equatable, Sendable {
    let actions: Set<MapLifecycleAction>
    let status: String
    let reason: String?

    func allows(_ action: MapLifecycleAction) -> Bool {
        actions.contains(action)
    }
}

/// Keeps the compact Manage Maps action group in a stable product order while
/// the resolver remains the only authority for which actions are available.
enum ManageMapRowActionPresentation: Sendable {
    static let displayOrder: [MapLifecycleAction] = [
        .update, .backup, .transferOwnership, .recoverOwnership, .remove
    ]

    static func actions(
        for availability: MapLifecycleActionAvailability
    ) -> [MapLifecycleAction] {
        displayOrder.filter(availability.allows)
    }
}

struct MapLifecyclePresentationResolver: Sendable {
    func resolve(
        item: MapLifecycleItem,
        comparison: MapComparison?,
        hasIntegrityRecord: Bool,
        hasValidatedUpdateProfile: Bool,
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
           hasValidatedUpdateProfile,
           hasStableWatchIdentity {
            return MapLifecycleActionAvailability(
                actions: [.recoverOwnership],
                status: "Recovery available",
                reason: "Verify this existing Terento map once to restore management."
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
                status: "Needs verification",
                reason: "Terento needs to verify this map before changing it."
            )
        }

        var actions: Set<MapLifecycleAction> = [.backup, .remove]
        if hasStableWatchIdentity {
            actions.insert(.transferOwnership)
        }
        var status = comparison?.status.userLabel ?? "Installed"
        var reason: String?

        if let comparison {
            switch comparison.status {
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
            reason: reason
        )
    }
}

struct MapLifecycleContext: Sendable {
    let item: MapLifecycleItem
    let comparison: MapComparison?
    let selectedMap: MapPackage?
    let identity: DeviceIdentity
    let availableStorage: UInt64
    let profile: DeviceInstallProfile?
    let deviceKey: String
    let expectedSHA256ByItemID: [UInt32: String]
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
        failedInstallRecovery: TerentoFailedInstallRecoveryRecord? = nil
    ) {
        self.item = item
        self.comparison = comparison
        self.selectedMap = selectedMap
        self.identity = identity
        self.availableStorage = availableStorage
        self.profile = profile
        self.deviceKey = deviceKey
        self.expectedSHA256ByItemID = expectedSHA256ByItemID
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
    case backingUp
    case removing
    case updating
    case verifying
    case completed
    case failed

    var userLabel: String {
        switch self {
        case .idle: return "Ready"
        case .awaitingConfirmation: return "Confirmation required"
        case .backingUp: return "Backing up"
        case .removing: return "Removing"
        case .updating: return "Updating"
        case .verifying: return "Verifying"
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

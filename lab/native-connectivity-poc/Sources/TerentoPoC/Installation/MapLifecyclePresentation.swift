import Foundation

/// User-facing actions exposed by the map lifecycle screen. The availability
/// decision is kept outside SwiftUI so a button can never become a second
/// implementation of the lifecycle safety rules.
enum MapLifecycleAction: String, CaseIterable, Equatable, Sendable {
    case backup
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

struct MapLifecyclePresentationResolver: Sendable {
    func resolve(
        item: MapLifecycleItem,
        comparison: MapComparison?,
        hasIntegrityRecord: Bool,
        hasValidatedUpdateProfile: Bool
    ) -> MapLifecycleActionAvailability {
        guard item.isInstalled else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: "Not installed",
                reason: "There is no installed map to manage."
            )
        }

        guard item.classification == .terentoManaged else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: item.classification.userLabel,
                reason: "This map is shown for reference and will be left unchanged."
            )
        }

        guard item.hasExactObjectIdentity, hasIntegrityRecord else {
            return MapLifecycleActionAvailability(
                actions: [],
                status: "Needs verification",
                reason: "Terento needs a complete local ownership record before changing this map."
            )
        }

        var actions: Set<MapLifecycleAction> = [.backup, .remove]
        var status = comparison?.status.userLabel ?? "Installed"
        var reason: String?

        if let comparison {
            switch comparison.status {
            case .updateAvailable where hasValidatedUpdateProfile:
                actions.insert(.update)
                status = "Update available"
            case .updateAvailable:
                status = "Update available"
                reason = "This device is not enabled for the validated update path yet."
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

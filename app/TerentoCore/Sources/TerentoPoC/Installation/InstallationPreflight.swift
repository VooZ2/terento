import Foundation

enum InstallationPreflightStatus: String, Codable, Equatable, Sendable {
    case readyNewInstall = "READY_NEW_INSTALL"
    case readyWithExistingMapConflict = "READY_WITH_EXISTING_MAP_CONFLICT"
    case blockedInsufficientSpace = "BLOCKED_INSUFFICIENT_SPACE"
    case blockedUnknownInstallSize = "BLOCKED_UNKNOWN_INSTALL_SIZE"
    case blockedUnknownTarget = "BLOCKED_UNKNOWN_TARGET"
    case blockedAmbiguousMapIdentity = "BLOCKED_AMBIGUOUS_MAP_IDENTITY"
    case blockedUnsupportedDevice = "BLOCKED_UNSUPPORTED_DEVICE"
    case error = "ERROR"

    var userLabel: String {
        switch self {
        case .readyNewInstall:
            return "Ready to install"
        case .readyWithExistingMapConflict:
            return "Existing map found"
        case .blockedInsufficientSpace:
            return "Not enough space"
        case .blockedUnknownInstallSize:
            return "Install size will be calculated first"
        case .blockedUnknownTarget:
            return "Install target unavailable"
        case .blockedAmbiguousMapIdentity:
            return "Map identity unclear"
        case .blockedUnsupportedDevice:
            return "Device not supported"
        case .error:
            return "Could not prepare installation"
        }
    }
}

struct InstallationPreflightResult: Equatable, Sendable {
    let selectedMap: MapPackage
    let installedMatch: InstalledMap?
    let ownership: InstallMapOwnership
    let comparisonStatus: MapStatus
    let installTarget: String?
    let proposedFilename: String?
    let storagePlan: StoragePlan?
    let replacementRequired: Bool
    let replacementConfirmationRequired: Bool
    let backupDecisionRequired: Bool
    let status: InstallationPreflightStatus
    let reason: String

    var isReady: Bool {
        switch status {
        case .readyNewInstall, .readyWithExistingMapConflict:
            return true
        default:
            return false
        }
    }

    var userNote: String {
        switch status {
        case .readyNewInstall:
            return "The map has been checked and is ready for your confirmation."
        case .readyWithExistingMapConflict:
            if comparisonStatus == .upToDate {
                return "The installed map is up to date. Replacing it would still require your confirmation."
            }
            return "An existing map was found. Replacement requires your confirmation."
        case .blockedInsufficientSpace:
            return "There is not enough free space for a safe replacement."
        case .blockedUnknownInstallSize:
            return "The final Garmin install size will be calculated before storage approval."
        case .blockedUnknownTarget:
            return "This device does not have a validated map installation target."
        case .blockedAmbiguousMapIdentity:
            return "An existing map could not be identified safely."
        case .blockedUnsupportedDevice:
            return "This device has no validated Terento installation profile."
        case .error:
            return reason
        }
    }
}

/// Pure, transport-independent safety coordination for a future installation.
/// It only evaluates already-read domain data and never owns an MTP transport.
struct InstallationPreflightEngine: Sendable {
    private let conflictResolver: MapConflictResolver
    private let storagePlanner: StoragePlanner

    init(
        conflictResolver: MapConflictResolver = MapConflictResolver(),
        storagePlanner: StoragePlanner = StoragePlanner()
    ) {
        self.conflictResolver = conflictResolver
        self.storagePlanner = storagePlanner
    }

    func evaluate(
        identity: DeviceIdentity,
        selectedMap: MapPackage,
        comparison: MapComparison,
        installedMaps: [InstalledMap],
        inspectedFiles: [InstalledMapFile],
        availableStorage: UInt64,
        profile: DeviceInstallProfile?
    ) -> InstallationPreflightResult {
        let installedMatch = comparison.installedMap
        let ownership = ownership(for: installedMatch)

        guard let profile else {
            return blocked(
                selectedMap: selectedMap,
                installedMatch: installedMatch,
                ownership: ownership,
                comparisonStatus: comparison.status,
                status: .blockedUnsupportedDevice,
                reason: "No validated install profile matches this device identity."
            )
        }

        guard profile.matches(identity), profile.supportsMapWrite else {
            return blocked(
                selectedMap: selectedMap,
                installedMatch: installedMatch,
                ownership: ownership,
                comparisonStatus: comparison.status,
                status: .blockedUnsupportedDevice,
                installTarget: profile.targetDirectory,
                reason: "The supplied install profile is not validated for this device."
            )
        }

        guard validTargetDirectory(profile.targetDirectory) else {
            return blocked(
                selectedMap: selectedMap,
                installedMatch: installedMatch,
                ownership: ownership,
                comparisonStatus: comparison.status,
                status: .blockedUnknownTarget,
                installTarget: profile.targetDirectory,
                reason: "The validated profile does not provide a safe target directory."
            )
        }

        let proposedFilename: String
        do {
            proposedFilename = try TerentoManagedFilenameGenerator().filename(
                providerId: selectedMap.providerId,
                regionId: selectedMap.canonicalRegionId
            )
        } catch {
            return blocked(
                selectedMap: selectedMap,
                installedMatch: installedMatch,
                ownership: ownership,
                comparisonStatus: comparison.status,
                status: .error,
                installTarget: profile.targetDirectory,
                reason: "The managed filename could not be generated safely."
            )
        }

        guard selectedMap.installSizeBytes != nil else {
            return blocked(
                selectedMap: selectedMap,
                installedMatch: installedMatch,
                ownership: ownership,
                comparisonStatus: comparison.status,
                status: .blockedUnknownInstallSize,
                installTarget: profile.targetDirectory,
                reason: "The final Garmin install size will be calculated before storage approval."
            )
        }

        let storagePlan = storagePlanner.plan(
            currentFreeSpace: availableStorage,
            selectedMapSizes: [selectedMap.installSizeBytes]
        )
        let common = CommonPreflightValues(
            selectedMap: selectedMap,
            installedMatch: installedMatch,
            ownership: ownership,
            comparisonStatus: comparison.status,
            installTarget: profile.targetDirectory,
            proposedFilename: proposedFilename,
            storagePlan: storagePlan
        )

        guard storagePlan.isAllowed else {
            return result(
                common: common,
                replacementRequired: false,
                replacementConfirmationRequired: false,
                backupDecisionRequired: false,
                status: .blockedInsufficientSpace,
                reason: "The conservative storage plan does not leave the required safety reserve."
            )
        }

        let targetPath: String
        do {
            targetPath = try conflictResolver.targetPath(
                profile: profile,
                selectedPackage: selectedMap
            )
        } catch {
            return result(
                common: common,
                replacementRequired: false,
                replacementConfirmationRequired: false,
                backupDecisionRequired: false,
                status: .blockedUnknownTarget,
                reason: "The device-specific install target could not be resolved."
            )
        }

        let conflict = conflictResolver.resolve(
            selectedPackage: selectedMap,
            targetPath: targetPath,
            installedMaps: installedMaps,
            inspectedFiles: inspectedFiles
        )

        switch conflict {
        case .noConflict:
            // A comparison that contains an installed map must never silently
            // become a clean install, even if identity data is inconsistent.
            guard comparison.status == .notInstalled, installedMatch == nil else {
                return result(
                    common: common,
                    replacementRequired: false,
                    replacementConfirmationRequired: false,
                    backupDecisionRequired: false,
                    status: .blockedAmbiguousMapIdentity,
                    reason: "Installed-map evidence and conflict resolution disagree."
                )
            }

            return result(
                common: common,
                replacementRequired: false,
                replacementConfirmationRequired: false,
                backupDecisionRequired: false,
                status: .readyNewInstall,
                reason: "No matching installed map or occupied managed target was found."
            )

        case .requiresExplicitReplacement(_, let conflictOwnership):
            return result(
                common: common.withOwnership(conflictOwnership),
                replacementRequired: true,
                replacementConfirmationRequired: true,
                backupDecisionRequired: true,
                status: .readyWithExistingMapConflict,
                reason: "A matching map already exists and must be explicitly confirmed before replacement."
            )

        case .blockedAmbiguous:
            return result(
                common: common,
                replacementRequired: false,
                replacementConfirmationRequired: false,
                backupDecisionRequired: false,
                status: .blockedAmbiguousMapIdentity,
                reason: "An existing object occupies the proposed target path without safe identity proof."
            )
        }
    }

    private func ownership(for installedMap: InstalledMap?) -> InstallMapOwnership {
        switch installedMap?.managementState {
        case .managedByTerento:
            return .terentoManaged
        case .detectedNotManaged:
            return .externalRecognized
        case .unknown, .none:
            return .unknown
        }
    }

    private func validTargetDirectory(_ value: String) -> Bool {
        let target = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return target.hasPrefix("/")
            && target != "/"
            && !target.contains("..")
            && !target.contains("//")
    }

    private func blocked(
        selectedMap: MapPackage,
        installedMatch: InstalledMap?,
        ownership: InstallMapOwnership,
        comparisonStatus: MapStatus,
        status: InstallationPreflightStatus,
        installTarget: String? = nil,
        reason: String
    ) -> InstallationPreflightResult {
        result(
            common: CommonPreflightValues(
                selectedMap: selectedMap,
                installedMatch: installedMatch,
                ownership: ownership,
                comparisonStatus: comparisonStatus,
                installTarget: installTarget,
                proposedFilename: nil,
                storagePlan: nil
            ),
            replacementRequired: false,
            replacementConfirmationRequired: false,
            backupDecisionRequired: false,
            status: status,
            reason: reason
        )
    }

    private func result(
        common: CommonPreflightValues,
        replacementRequired: Bool,
        replacementConfirmationRequired: Bool,
        backupDecisionRequired: Bool,
        status: InstallationPreflightStatus,
        reason: String
    ) -> InstallationPreflightResult {
        InstallationPreflightResult(
            selectedMap: common.selectedMap,
            installedMatch: common.installedMatch,
            ownership: common.ownership,
            comparisonStatus: common.comparisonStatus,
            installTarget: common.installTarget,
            proposedFilename: common.proposedFilename,
            storagePlan: common.storagePlan,
            replacementRequired: replacementRequired,
            replacementConfirmationRequired: replacementConfirmationRequired,
            backupDecisionRequired: backupDecisionRequired,
            status: status,
            reason: reason
        )
    }
}

private struct CommonPreflightValues: Sendable {
    let selectedMap: MapPackage
    let installedMatch: InstalledMap?
    let ownership: InstallMapOwnership
    let comparisonStatus: MapStatus
    let installTarget: String?
    let proposedFilename: String?
    let storagePlan: StoragePlan?

    func withOwnership(_ ownership: InstallMapOwnership) -> CommonPreflightValues {
        CommonPreflightValues(
            selectedMap: selectedMap,
            installedMatch: installedMatch,
            ownership: ownership,
            comparisonStatus: comparisonStatus,
            installTarget: installTarget,
            proposedFilename: proposedFilename,
            storagePlan: storagePlan
        )
    }
}

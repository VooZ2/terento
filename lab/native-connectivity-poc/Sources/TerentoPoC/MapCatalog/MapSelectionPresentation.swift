import Foundation

/// Pure list rules keep UI partitioning and search deterministic and testable.
enum MapSelectionPresentationModel: Sendable {
    static func validSelectionIDs(
        _ selectedIDs: Set<String>,
        items: [MapSelectionItem]
    ) -> Set<String> {
        selectedIDs.intersection(Set(items.filter(\.isSelectable).map(\.id)))
    }

    static func installed(_ items: [MapSelectionItem]) -> [MapSelectionItem] {
        items
            .filter { $0.comparison.installedMap != nil }
            .sorted { lhs, rhs in
                if lhs.comparison.status != rhs.comparison.status {
                    return lhs.comparison.status == .updateAvailable
                }
                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }

    /// Returns only supported provider maps that are present in the current
    /// device inventory. Ownership controls lifecycle actions, not whether a
    /// recognized map is visible in the Installed section.
    static func supportedInstalled(
        _ items: [MapSelectionItem],
        inventory: UnifiedMapInventory?
    ) -> [MapSelectionItem] {
        guard let inventory else {
            return []
        }

        let recognizedCatalogIDs = Set(
            inventory.freizeitkarte.compactMap { entry -> String? in
                guard entry.isInstalled,
                      !entry.installedMaps.isEmpty,
                      entry.installedMaps.allSatisfy({ $0.metadataStatus == .parsed }),
                      entry.managementState == .managedByTerento
                        || entry.managementState == .detectedNotManaged else {
                    return nil
                }

                return entry.comparison?.id
            }
        )

        return installed(items).filter { recognizedCatalogIDs.contains($0.id) }
    }

    /// Returns the maps that belong in the Install catalogue.
    ///
    /// Normal browsing is intentionally limited to new-install candidates.
    /// A non-empty search may also reveal an installed catalog match so the
    /// user can understand why that region is not available to install here;
    /// the row remains non-selectable and lifecycle actions stay in Manage.
    static func available(
        _ items: [MapSelectionItem],
        query: String
    ) -> [MapSelectionItem] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return items
            .filter { item in
                if normalizedQuery.isEmpty {
                    return item.comparison.installedMap == nil
                }

                if item.comparison.installedMap != nil {
                    return true
                }

                return true
            }
            .filter { item in
                guard !normalizedQuery.isEmpty else { return true }
                return MapDisplayNameNormalizer.searchableText(
                    package: item.package,
                    displayName: item.title
                ).appending(" \(policySearchAliases(for: item))")
                    .localizedCaseInsensitiveContains(normalizedQuery)
            }
            .sorted { lhs, rhs in
                if lhs.isRecommended != rhs.isRecommended {
                    return lhs.isRecommended
                }
                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }

    private static func policySearchAliases(for item: MapSelectionItem) -> String {
        guard let identity = item.canonicalRegionIdentity else { return "" }
        if identity == CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA") {
            return "UA Ukraine Crimea RUS-CRIMEA RUS_CRIMEA freizeitkarte-rus-crimea"
        }
        return "\(identity.countryCode) \(identity.locality ?? "")"
    }
}

/// A visual-only projection of the conservative storage plan. It keeps the
/// segmented bar aligned with the same plan used by the Continue/Install CTA.
struct StorageBarProjection: Equatable, Sendable {
    let existingUsedBytes: UInt64
    let selectedMapBytes: UInt64
    let freeAfterInstallationBytes: UInt64

    init(plan: StoragePlan, totalCapacity: UInt64) {
        guard totalCapacity > 0 else {
            existingUsedBytes = 0
            selectedMapBytes = 0
            freeAfterInstallationBytes = 0
            return
        }

        let currentFreeSpace = min(plan.currentFreeSpace, totalCapacity)
        let existingUsed = totalCapacity - currentFreeSpace
        let availableBeforeSelection = totalCapacity - existingUsed
        let selected = plan.hasUnresolvedInstallSize
            ? 0
            : min(plan.selectedMapBytes, availableBeforeSelection)
        let availableAfterSelection = availableBeforeSelection - selected
        let freeAfter = plan.hasUnresolvedInstallSize
            ? currentFreeSpace
            : min(plan.projectedFreeSpace, availableAfterSelection)

        existingUsedBytes = existingUsed
        selectedMapBytes = selected
        freeAfterInstallationBytes = freeAfter
    }

    func fraction(for bytes: UInt64) -> Double {
        let total = existingUsedBytes
            .addingReportingOverflow(selectedMapBytes)
        guard !total.overflow else {
            return 0
        }

        let resolvedTotal = total.partialValue
            .addingReportingOverflow(freeAfterInstallationBytes)
        guard !resolvedTotal.overflow, resolvedTotal.partialValue > 0 else {
            return 0
        }

        let fraction = Double(bytes) / Double(resolvedTotal.partialValue)
        return fraction.isFinite ? min(1, max(0, fraction)) : 0
    }
}

enum InstallReviewAction: String, Equatable, Sendable {
    case prepare
    case install
}

enum InstallReviewAvailability: Equatable, Sendable {
    case ready(InstallReviewAction)
    case blocked(String)

    var isEnabled: Bool {
        if case .ready = self {
            return true
        }
        return false
    }

    var userReason: String? {
        if case let .blocked(reason) = self {
            return reason
        }
        return nil
    }
}

/// Resolves the review CTA from the same plan and lifecycle state rendered by
/// the screen. A positive storage message never enables an action that the
/// underlying installation path cannot safely execute.
struct InstallReviewAvailabilityResolver: Sendable {
    func resolve(
        plan: InstallationPlan?,
        deviceConnected: Bool,
        supportedInstallFlow: Bool,
        installationPhase: InstallationProcessPhase,
        hasValidatedArtifact: Bool,
        operationBusy: Bool
    ) -> InstallReviewAvailability {
        guard let plan else {
            return .blocked("Select a map to continue.")
        }
        guard plan.canContinue else {
            return .blocked(plan.reason)
        }
        guard deviceConnected else {
            return .blocked("Reconnect your Garmin to continue.")
        }
        guard supportedInstallFlow else {
            return .blocked("This map cannot be installed safely on this Garmin yet.")
        }
        if let conflictMessage = InstallationFlowPresentation.conflictMessage(
            flowOwnsOperation: false,
            independentOperationBusy: operationBusy
        ) {
            return .blocked(conflictMessage)
        }

        switch installationPhase {
        case .idle:
            return .ready(.prepare)
        case .awaitingConfirmation where hasValidatedArtifact:
            return .ready(.install)
        case .awaitingConfirmation:
            return .blocked("Installation checks are still in progress.")
        case .downloading, .preparing, .installing, .finishing:
            return .blocked("Installation is already in progress.")
        case .completed:
            return .blocked("This installation has already completed.")
        case .failed:
            return .blocked("The installation check needs to be run again.")
        }
    }
}

enum MapRowDividerPolicy: Sendable {
    static func showsDivider(at index: Int, in count: Int) -> Bool {
        index >= 0 && index < count - 1
    }
}

/// Presentation-only state rules for the native installation flow. The map
/// engine remains the source of truth for the transaction itself; this keeps
/// navigation, sidebar status, and the active screen in sync with that state.
enum InstallationFlowPresentation: Sendable {
    static func hasStarted(_ phase: InstallationProcessPhase) -> Bool {
        phase != .idle
    }

    static func isActive(_ phase: InstallationProcessPhase) -> Bool {
        switch phase {
        case .downloading, .preparing, .awaitingConfirmation, .installing, .finishing:
            return true
        case .idle, .completed, .failed:
            return false
        }
    }

    static func conflictMessage(
        flowOwnsOperation: Bool,
        independentOperationBusy: Bool
    ) -> String? {
        guard independentOperationBusy, !flowOwnsOperation else {
            return nil
        }

        return "Another device operation is in progress."
    }

    static func shouldContinueAfterPreflight(
        userAuthorized: Bool,
        preflightSucceeded: Bool
    ) -> Bool {
        userAuthorized && preflightSucceeded
    }
}

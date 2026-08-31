import Foundation

enum MapSelectionAction: String, Equatable, Sendable {
    case install
    case update
    case noAction
    case blocked
}

enum InstallationPlanStatus: String, Equatable, Sendable {
    case noSelection = "NO_SELECTION"
    case ready = "READY"
    case blocked = "BLOCKED"
}

/// The single catalog-backed row used by the Choose screen. It deliberately
/// contains presentation-ready outcomes, rather than device ownership or
/// transport details.
struct MapSelectionItem: Identifiable, Equatable, Sendable {
    let id: String
    let package: MapPackage
    let comparison: MapComparison
    let displayName: String
    let installSizeBytes: UInt64?
    let lifecycleAction: MapSelectionAction
    let canonicalRegionIdentity: CanonicalMapRegionIdentity?
    let acquisitionAvailability: MapAcquisitionAvailability
    let preflightStatus: InstallationPreflightStatus?
    let isRecommended: Bool

    var title: String {
        displayName
    }

    /// Provider rows always expose the provider and catalog release together.
    /// This keeps the country title provider-neutral while retaining enough
    /// context to distinguish identical regions in an `All providers` view.
    var providerVersionLabel: String? {
        guard package.sourceKind == .provider else { return nil }
        let providerName = comparison.providerName.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        var parts: [String] = []
        if !providerName.isEmpty {
            parts.append(providerName)
        }
        if let versionLabel = package.displayVersionLabel {
            parts.append(versionLabel)
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    var action: MapSelectionAction { lifecycleAction }

    var acquisitionAccessibilityLabel: String? {
        guard acquisitionAvailability != .available,
              let explanation = acquisitionAvailability.detailedExplanation else {
            return nil
        }
        return "\(title). Map download unavailable. \(explanation)"
    }

    var installedVersionLabel: String? {
        guard let installedMap = comparison.installedMap else {
            return nil
        }

        return installedMap.version?.description ?? installedMap.rawVersion
    }

    var userStatus: String {
        switch comparison.status {
        case .notInstalled:
            return installSizeBytes == nil ? "Size calculated before installation" : ""
        case .updateAvailable:
            return "Update available · \(installedVersionLabel ?? "Version unavailable") → \(package.displayVersionLabel ?? "Version unavailable")"
        case .upToDate:
            return "Installed · Up to date"
        case .newerInstalled:
            return "Newer version installed"
        case .unknown:
            return "Version unavailable"
        }
    }

    var isSelectable: Bool {
        guard acquisitionAvailability == .available else { return false }
        switch action {
        case .install:
            return preflightStatus == .readyNewInstall
                || preflightStatus == .blockedUnknownInstallSize
        case .update:
            return false
        case .noAction, .blocked:
            return false
        }
    }
}

/// A domain result passed from Choose to the next workflow step. The view does
/// not calculate sizes, conflicts, or whether a selection may continue.
struct InstallationPlan: Equatable, Sendable {
    let selectedItems: [MapSelectionItem]
    let installItems: [MapSelectionItem]
    let updateItems: [MapSelectionItem]
    let noActionItems: [MapSelectionItem]
    let blockedItems: [MapSelectionItem]
    let storagePlan: StoragePlan
    let status: InstallationPlanStatus
    let reason: String

    var canContinue: Bool {
        status == .ready
            && !installItems.isEmpty
            && updateItems.isEmpty
            && blockedItems.isEmpty
            && storagePlan.isAllowed
    }
}

struct MapRegionRecommendation: Sendable {
    private static let alpha2ToAlpha3: [String: String] = [
        "AT": "AUT",
        "BE": "BEL",
        "CZ": "CZE",
        "DE": "DEU",
        "DK": "DNK",
        "EE": "EST",
        "FI": "FIN",
        "FR": "FRA",
        "GB": "GBR",
        "IE": "IRL",
        "LT": "LTU",
        "LU": "LUX",
        "LV": "LVA",
        "NL": "NLD",
        "NO": "NOR",
        "PL": "POL",
        "SE": "SWE",
        "SK": "SVK"
    ]

    /// Uses only the Mac's locale region. It never asks for location access,
    /// reads GPS data, or sends the region anywhere.
    static func regionID(
        systemRegionCode: String?,
        comparisons: [MapComparison]
    ) -> String? {
        guard let systemRegionCode else {
            return nil
        }

        let normalized = systemRegionCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let candidate = alpha2ToAlpha3[normalized] ?? normalized

        return comparisons.first {
            MapIdentity.normalizeRegion($0.catalogMap.regionId) == candidate
        }?.catalogMap.regionId
    }
}

struct MapSelectionPlanner: Sendable {
    private let storagePlanner: StoragePlanner
    private let acquisitionPolicy = MapPackageAcquisitionPolicyResolver()

    init(storagePlanner: StoragePlanner = StoragePlanner()) {
        self.storagePlanner = storagePlanner
    }

    func items(
        comparisons: [MapComparison],
        preflightStatuses: [String: InstallationPreflightStatus],
        recommendedRegionID: String?,
        providerIDs: Set<String>? = nil
    ) -> [MapSelectionItem] {
        var uniqueComparisons: [String: MapComparison] = [:]
        let normalizedProviderIDs = providerIDs.map {
            Set($0.map(MapIdentity.normalizeProvider))
        }
        let displayNames = MapDisplayNameNormalizer.displayNames(
            for: comparisons.map(\.catalogMap)
        )

        for comparison in comparisons {
            if let normalizedProviderIDs,
               !normalizedProviderIDs.contains(
                   MapIdentity.normalizeProvider(comparison.catalogMap.providerId)
               ) {
                continue
            }

            let identityKey = MapCatalogIdentityKey.make(
                provider: comparison.catalogMap.providerId,
                region: comparison.catalogMap.regionId,
                identifier: comparison.catalogMap.identifier,
                fallback: comparison.catalogMap.id,
                namespace: "selection"
            )

            // Collapse only exact package duplicates. Regional variants with
            // real identifiers remain distinct rows.
            uniqueComparisons[identityKey] = uniqueComparisons[identityKey] ?? comparison
        }

        return uniqueComparisons.values
            .map { comparison in
                let package = comparison.catalogMap
                let identity = acquisitionPolicy.canonicalIdentity(for: package)
                let availability = acquisitionPolicy.availability(for: package)
                return MapSelectionItem(
                    id: package.id,
                    package: package,
                    comparison: comparison,
                    displayName: availability == .withheldCrimea
                        ? "Crimea"
                        : displayNames[package.id]
                            ?? MapDisplayNameNormalizer.normalize(
                                package.name,
                                providerID: package.providerId
                            ),
                    installSizeBytes: package.defaultArtifactPlan.installSizeBytes
                        ?? package.installSizeBytes,
                    lifecycleAction: action(for: comparison.status),
                    canonicalRegionIdentity: identity,
                    acquisitionAvailability: availability,
                    preflightStatus: preflightStatuses[comparison.id],
                    isRecommended: recommendedRegionID.map {
                        MapIdentity.normalizeRegion(comparison.catalogMap.regionId)
                            == MapIdentity.normalizeRegion($0)
                    } ?? false
                )
            }
            .sorted { lhs, rhs in
                let lhsInstalled = lhs.comparison.installedMap != nil
                let rhsInstalled = rhs.comparison.installedMap != nil
                if lhsInstalled != rhsInstalled {
                    return lhsInstalled
                }

                if lhs.isRecommended != rhs.isRecommended {
                    return lhs.isRecommended
                }

                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }

    func plan(
        items: [MapSelectionItem],
        selectedIDs: Set<String>,
        currentFreeSpace: UInt64
    ) -> InstallationPlan {
        let selectedItems = items.filter { selectedIDs.contains($0.id) }
        let selectedProviderIDs = Set(
            selectedItems
                .filter { $0.package.sourceKind == .provider }
                .map { MapIdentity.normalizeProvider($0.package.providerId) }
        )
        let installItems = selectedItems.filter {
            $0.action == .install && $0.acquisitionAvailability == .available
        }
        let updateItems = selectedItems.filter { $0.action == .update }
        let noActionItems = selectedItems.filter { $0.action == .noAction }

        let blockedItems = selectedItems.filter { item in
            guard item.acquisitionAvailability == .available else { return true }
            switch item.action {
            case .install:
                return item.preflightStatus != .readyNewInstall
            case .update, .blocked, .noAction:
                return true
            }
        }

        // Install owns only new map additions. An update item can still be
        // represented in a defensive plan for lifecycle tests, but it must
        // never consume the Install screen's storage projection.
        let selectedSizes = selectedItems
            .filter { $0.action == .install && $0.acquisitionAvailability == .available }
            .map(\.installSizeBytes)
        let storagePlan = storagePlanner.plan(
            currentFreeSpace: currentFreeSpace,
            selectedMapSizes: selectedSizes
        )

        let status: InstallationPlanStatus
        let reason: String

        if selectedItems.isEmpty {
            status = .noSelection
            reason = "Select a map to continue."
        } else if selectedProviderIDs.count > 1 {
            status = .blocked
            reason = "Select maps from one provider at a time."
        } else if selectedItems.contains(where: { $0.acquisitionAvailability != .available }) {
            status = .blocked
            reason = "Downloads are not offered for this region under Terento's current policy."
        } else if !updateItems.isEmpty {
            status = .blocked
            reason = "Map updates require a separate safe replacement step."
        } else if storagePlan.status == .blockedUnknownInstallSize {
            status = .blocked
            reason = "The selected map size will be calculated before installation approval."
        } else if storagePlan.status == .blockedInsufficientSpace {
            status = .blocked
            reason = "There is not enough free space for this selection."
        } else if !noActionItems.isEmpty || !blockedItems.isEmpty {
            status = .blocked
            reason = "Choose a map that is ready to install."
        } else if !storagePlan.isAllowed {
            status = .blocked
            reason = "There is not enough free space for this selection."
        } else {
            status = .ready
            reason = "The selected maps are ready for the next step."
        }

        return InstallationPlan(
            selectedItems: selectedItems,
            installItems: installItems,
            updateItems: updateItems,
            noActionItems: noActionItems,
            blockedItems: blockedItems,
            storagePlan: storagePlan,
            status: status,
            reason: reason
        )
    }

    private func action(for status: MapStatus) -> MapSelectionAction {
        switch status {
        case .notInstalled:
            return .install
        case .updateAvailable:
            return .update
        case .upToDate, .newerInstalled:
            return .noAction
        case .unknown:
            return .blocked
        }
    }
}

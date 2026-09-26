import Foundation

/// The lifecycle layer deliberately uses user-facing concepts instead of
/// exposing the internal manifest and scanner terminology to SwiftUI.
enum MapLifecycleClassification: String, Codable, Equatable, Sendable {
    case terentoManaged = "TERENTO_MANAGED"
    case externalRecognized = "EXTERNAL_RECOGNIZED"
    case ambiguous = "AMBIGUOUS"
    case system = "SYSTEM"

    var canBeManaged: Bool {
        self == .terentoManaged
    }

    var userLabel: String {
        switch self {
        case .terentoManaged:
            return "Installed by Terento"
        case .externalRecognized:
            return "Installed on your watch"
        case .ambiguous:
            return "Read-only"
        case .system:
            return "Read-only"
        }
    }
}

struct MapLifecycleItem: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let sourceKind: MapSourceKind
    let provider: String?
    let region: String?
    let version: MapVersion?
    let rawVersion: String?
    let sizeBytes: UInt64
    let installedMaps: [InstalledMap]
    let classification: MapLifecycleClassification
    let failedInstallRecovery: TerentoFailedInstallRecoveryRecord?

    init(
        id: String,
        title: String,
        sourceKind: MapSourceKind? = nil,
        provider: String?,
        region: String?,
        version: MapVersion?,
        rawVersion: String?,
        sizeBytes: UInt64,
        installedMaps: [InstalledMap],
        classification: MapLifecycleClassification,
        failedInstallRecovery: TerentoFailedInstallRecoveryRecord? = nil
    ) {
        self.id = id
        self.title = title
        self.sourceKind = sourceKind ?? (provider == nil ? .custom : .provider)
        self.provider = provider
        self.region = region
        self.version = version
        self.rawVersion = rawVersion
        self.sizeBytes = sizeBytes
        self.installedMaps = installedMaps
        self.classification = classification
        self.failedInstallRecovery = failedInstallRecovery
    }

    var isInstalled: Bool {
        !installedMaps.isEmpty
    }

    var hasExactObjectIdentity: Bool {
        let objectIDs = installedMaps.compactMap { $0.sourceFile.itemID }
        return installedMaps.count == objectIDs.count
            && !objectIDs.isEmpty
            && Set(objectIDs).count == objectIDs.count
            && installedMaps.allSatisfy {
                !$0.sourceFile.path.isEmpty && !$0.sourceFile.filename.isEmpty
            }
    }

    var detailLabel: String {
        guard isInstalled else {
            return "Not installed"
        }

        if let versionLabel = version?.description ?? rawVersion {
            return "Installed · \(versionLabel)"
        }

        return "Installed"
    }

    /// Compact metadata for the consumer-facing Manage Maps row. Provider and
    /// installation state are supplied by the section and page context, so a
    /// normal row only needs its release, installed size, and optional package
    /// component summary.
    var manageMetadataLabel: String {
        guard isInstalled else {
            return ""
        }

        if failedInstallRecovery != nil {
            return [manageReleaseLabel, formattedInstalledSize, "Incomplete installation"]
                .compactMap { $0 }
                .joined(separator: " · ")
        }

        var values = [manageReleaseLabel, formattedInstalledSize].compactMap { $0 }
        if hasInstalledContours {
            values.append("Contours included")
        }
        return values.joined(separator: " · ")
    }

    private var manageReleaseLabel: String? {
        let candidates = [version?.description, rawVersion]
        let placeholders: Set<String> = [
            "", "unknown", "n/a", "na", "none", "null", "2000-01", "1970-01"
        ]
        return candidates.compactMap { candidate -> String? in
            guard let candidate else { return nil }
            let value = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
            return placeholders.contains(value.lowercased()) ? nil : value
        }.first
    }

    private var formattedInstalledSize: String? {
        guard sizeBytes > 0 else { return nil }
        return ByteCountFormatter.string(
            fromByteCount: Int64(min(sizeBytes, UInt64(Int64.max))),
            countStyle: .decimal
        )
    }

    private var hasInstalledContours: Bool {
        guard MapIdentity.normalizeProvider(provider ?? "") == "opentopomap" else {
            return false
        }

        let filenameGenerator = TerentoManagedFilenameGenerator()
        return installedMaps.contains { map in
            map.managementState == .managedByTerento
                && filenameGenerator.artifactKind(for: map.sourceFile.filename) == .contours
        }
    }

    var noteLabel: String {
        if failedInstallRecovery != nil {
            return "Incomplete install · only this exact map can be recovered."
        }

        switch classification {
        case .terentoManaged:
            if sourceKind == .custom {
                return "Imported from this Mac · Managed by Terento."
            }
            return "Managed by Terento · update and removal are available."
        case .externalRecognized:
            return "Installed outside Terento · removal is available after confirmation."
        case .ambiguous:
            return "Read-only · Terento will leave it unchanged."
        case .system:
            return "Read-only · Terento will leave it unchanged."
        }
    }
}

struct MapLifecycleProviderGroup: Identifiable, Equatable, Sendable {
    let id: String
    let providerId: String
    let title: String
    let items: [MapLifecycleItem]
}

struct MapLifecycleInventory: Equatable, Sendable {
    let providerGroups: [MapLifecycleProviderGroup]
    let otherMaps: [MapLifecycleItem]

    init(
        providerGroups: [MapLifecycleProviderGroup],
        otherMaps: [MapLifecycleItem]
    ) {
        self.providerGroups = providerGroups.sorted {
            let titleOrder = $0.title.localizedCaseInsensitiveCompare($1.title)
            if titleOrder != .orderedSame {
                return titleOrder == .orderedAscending
            }
            return $0.id < $1.id
        }
        self.otherMaps = otherMaps
    }

    var allItems: [MapLifecycleItem] {
        providerGroups.flatMap(\.items) + otherMaps
    }

    func item(id: String) -> MapLifecycleItem? {
        allItems.first { $0.id == id }
    }
}

struct MapLifecycleInventoryBuilder: Sendable {
    func build(
        from inventory: UnifiedMapInventory,
        recoveryRecords: [TerentoFailedInstallRecoveryRecord] = []
    ) -> MapLifecycleInventory {
        let providerGroups = inventory.providerGroups.compactMap { group -> MapLifecycleProviderGroup? in
            let items = group.entries
                .filter(\.isInstalled)
                .map { makeItem($0, recoveryRecords: recoveryRecords) }
            guard !items.isEmpty else { return nil }
            return MapLifecycleProviderGroup(
                id: group.id,
                providerId: group.providerId,
                title: group.title,
                items: items
            )
        }

        return MapLifecycleInventory(
            providerGroups: providerGroups,
            otherMaps: inventory.otherMaps
                .filter(\.isInstalled)
                .map { makeItem($0, recoveryRecords: recoveryRecords) }
        )
    }

    private func makeItem(
        _ entry: MapInventoryEntry,
        recoveryRecords: [TerentoFailedInstallRecoveryRecord]
    ) -> MapLifecycleItem {
        let recoveryRecord = recoveryRecords.first { record in
            entry.installedMaps.contains { installedMap in
                record.matches(
                    deviceKey: record.deviceKey,
                    path: installedMap.sourceFile.path,
                    filename: installedMap.sourceFile.filename,
                    sizeBytes: installedMap.sourceFile.sizeBytes,
                    providerId: installedMap.provider,
                    regionId: installedMap.region,
                    version: installedMap.version
                )
            }
        }

        return MapLifecycleItem(
            id: entry.key,
            title: entry.title,
            sourceKind: entry.sourceKind,
            provider: entry.catalogPackage?.providerId ?? entry.installedMaps.first?.provider,
            region: entry.catalogPackage?.canonicalRegionId ?? entry.installedMaps.first?.region,
            version: entry.installedVersion,
            rawVersion: entry.installedRawVersion,
            sizeBytes: entry.installedSizeBytes,
            installedMaps: entry.installedMaps,
            classification: classification(for: entry),
            failedInstallRecovery: recoveryRecord
        )
    }

    private func classification(for entry: MapInventoryEntry) -> MapLifecycleClassification {
        guard !entry.installedMaps.isEmpty else {
            return .ambiguous
        }

        if entry.installedMaps.contains(where: { $0.managementState == .unknown }) {
            return .ambiguous
        }

        switch entry.managementState {
        case .managedByTerento:
            return .terentoManaged
        case .detectedNotManaged:
            return .externalRecognized
        case .unknown:
            return .ambiguous
        }
    }
}

struct MapLifecycleReadTransfer: Equatable, Sendable {
    let itemID: UInt32
    let sourcePath: String
    let reportedSizeBytes: UInt64
}

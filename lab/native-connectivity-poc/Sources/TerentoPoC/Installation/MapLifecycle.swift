import CryptoKit
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
            return "Identity unavailable"
        case .system:
            return "Garmin system map"
        }
    }
}

enum MapLifecycleError: Error, Equatable, Sendable {
    case mapNotInstalled
    case unsafeClassification
    case exactObjectIdentityRequired
    case confirmationRequired
    case staleInventory
    case backupDestinationExists
    case backupVerificationFailed
    case deleteVerificationFailed
    case replacementNotReady
    case insufficientSpace
    case updateNotRequired
    case transportFailure(String)
    case postActionVerificationFailed
}

struct MapLifecycleItem: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let provider: String?
    let region: String?
    let version: MapVersion?
    let rawVersion: String?
    let sizeBytes: UInt64
    let installedMaps: [InstalledMap]
    let classification: MapLifecycleClassification

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

    var fileIdentities: [MapLifecycleFileIdentity] {
        installedMaps.compactMap { MapLifecycleFileIdentity(file: $0.sourceFile) }
            .sorted()
    }

    var detailLabel: String {
        guard isInstalled else {
            return "Not installed"
        }

        if let versionLabel = rawVersion ?? version?.description {
            return "Installed · \(versionLabel)"
        }

        return "Installed"
    }

    var noteLabel: String {
        switch classification {
        case .terentoManaged:
            return "Installed by Terento. Backup and removal are available after confirmation."
        case .externalRecognized:
            return "Already on your watch. Terento will not replace or remove it automatically."
        case .ambiguous:
            return "This map could not be identified safely and will be left untouched."
        case .system:
            return "Garmin system map. Terento will leave it untouched."
        }
    }
}

struct MapLifecycleInventory: Equatable, Sendable {
    let freizeitkarte: [MapLifecycleItem]
    let otherMaps: [MapLifecycleItem]

    var allItems: [MapLifecycleItem] {
        freizeitkarte + otherMaps
    }

    func item(id: String) -> MapLifecycleItem? {
        allItems.first { $0.id == id }
    }

    var fingerprint: MapLifecycleInventoryFingerprint {
        MapLifecycleInventoryFingerprint(items: allItems)
    }
}

struct MapLifecycleInventoryBuilder: Sendable {
    func build(from inventory: UnifiedMapInventory) -> MapLifecycleInventory {
        let items = inventory.allEntries
            .filter(\.isInstalled)
            .map(makeItem)

        return MapLifecycleInventory(
            freizeitkarte: items.filter {
                MapIdentity.normalizeProvider($0.provider ?? "") == "freizeitkarte"
            },
            otherMaps: items.filter {
                MapIdentity.normalizeProvider($0.provider ?? "") != "freizeitkarte"
            }
        )
    }

    private func makeItem(_ entry: MapInventoryEntry) -> MapLifecycleItem {
        MapLifecycleItem(
            id: entry.key,
            title: entry.title,
            provider: entry.catalogPackage?.providerId ?? entry.installedMaps.first?.provider,
            region: entry.catalogPackage?.regionId ?? entry.installedMaps.first?.region,
            version: entry.installedVersion,
            rawVersion: entry.installedRawVersion,
            sizeBytes: entry.installedSizeBytes,
            installedMaps: entry.installedMaps,
            classification: classification(for: entry)
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

struct MapLifecycleFileIdentity: Comparable, Equatable, Hashable, Sendable {
    let itemID: UInt32
    let path: String
    let filename: String
    let sizeBytes: UInt64

    init?(file: InstalledMapFile) {
        guard let itemID = file.itemID else {
            return nil
        }

        self.itemID = itemID
        self.path = file.path
        self.filename = file.filename
        self.sizeBytes = file.sizeBytes
    }

    static func < (lhs: Self, rhs: Self) -> Bool {
        if lhs.itemID != rhs.itemID {
            return lhs.itemID < rhs.itemID
        }
        return lhs.path < rhs.path
    }
}

struct MapLifecycleInventoryFingerprint: Equatable, Sendable {
    let files: [MapLifecycleFileIdentity]

    init(items: [MapLifecycleItem]) {
        files = items
            .flatMap(\.fileIdentities)
            .sorted()
    }

    func removing(_ deleted: Set<MapLifecycleFileIdentity>) -> Self {
        Self(files: files.filter { !deleted.contains($0) })
    }

    private init(files: [MapLifecycleFileIdentity]) {
        self.files = files
    }
}

struct MapLifecycleBackupTransfer: Equatable, Sendable {
    let itemID: UInt32
    let sourcePath: String
    let reportedSizeBytes: UInt64
}

/// The production MTP adapter must implement these operations without using
/// filenames as identity. The current Stage 4 bridge intentionally does not
/// conform yet because it only exposes the validated Latvia install path.
protocol MapLifecycleTransport: Sendable {
    func backup(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer

    func delete(file: InstalledMapFile) throws
}

struct VerifiedBackupFile: Equatable, Sendable {
    let source: MapLifecycleFileIdentity
    let localURL: URL
    let sizeBytes: UInt64
    let sha256: String
}

struct MapBackupResult: Equatable, Sendable {
    let mapID: String
    let files: [VerifiedBackupFile]

    var totalSizeBytes: UInt64 {
        files.reduce(0) { total, file in
            let result = total.addingReportingOverflow(file.sizeBytes)
            return result.overflow ? UInt64.max : result.partialValue
        }
    }
}

struct MapBackupEngine: Sendable {
    func backup(
        item: MapLifecycleItem,
        to destinationDirectory: URL,
        transport: any MapLifecycleTransport,
        onProgress: (@Sendable (TransferProgress) -> Void)? = nil
    ) throws -> MapBackupResult {
        guard item.isInstalled else {
            throw MapLifecycleError.mapNotInstalled
        }
        guard item.classification.canBeManaged else {
            throw MapLifecycleError.unsafeClassification
        }
        guard item.hasExactObjectIdentity else {
            throw MapLifecycleError.exactObjectIdentityRequired
        }

        let fileManager = FileManager.default
        let backupDirectory = destinationDirectory.appendingPathComponent(item.id, isDirectory: true)
        if fileManager.fileExists(atPath: backupDirectory.path) {
            throw MapLifecycleError.backupDestinationExists
        }

        do {
            try fileManager.createDirectory(
                at: backupDirectory,
                withIntermediateDirectories: true
            )
        } catch {
            throw MapLifecycleError.transportFailure(error.localizedDescription)
        }

        var verifiedFiles: [VerifiedBackupFile] = []
        for installedMap in item.installedMaps {
            guard let identity = MapLifecycleFileIdentity(file: installedMap.sourceFile) else {
                throw MapLifecycleError.exactObjectIdentityRequired
            }

            let destinationURL = backupDirectory.appendingPathComponent(
                safeFilename(installedMap.sourceFile.filename)
            )

            do {
                let transfer = try transport.backup(
                    file: installedMap.sourceFile,
                    to: destinationURL,
                    onProgress: onProgress
                )
                let attributes = try fileManager.attributesOfItem(atPath: destinationURL.path)
                guard let number = attributes[.size] as? NSNumber,
                      number.uint64Value == identity.sizeBytes,
                      transfer.itemID == identity.itemID,
                      transfer.sourcePath == identity.path,
                      transfer.reportedSizeBytes == identity.sizeBytes else {
                    throw MapLifecycleError.backupVerificationFailed
                }

                verifiedFiles.append(
                    VerifiedBackupFile(
                        source: identity,
                        localURL: destinationURL,
                        sizeBytes: number.uint64Value,
                        sha256: try sha256(of: destinationURL)
                    )
                )
            } catch let error as MapLifecycleError {
                throw error
            } catch {
                throw MapLifecycleError.transportFailure(error.localizedDescription)
            }
        }

        return MapBackupResult(mapID: item.id, files: verifiedFiles)
    }

    private func safeFilename(_ value: String) -> String {
        let normalized = value.replacingOccurrences(
            of: "[^A-Za-z0-9._-]",
            with: "_",
            options: .regularExpression
        )
        return normalized.isEmpty ? "map.img" : normalized
    }

    fileprivate func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty {
                break
            }
            hasher.update(data: data)
        }

        return hasher.finalize()
            .map { String(format: "%02x", $0) }
            .joined()
    }
}

enum MapUpdatePlanStatus: String, Equatable, Sendable {
    case ready
    case noUpdateRequired
    case newerVersionAlreadyInstalled
    case blockedAmbiguousMapIdentity
    case blockedInsufficientSpace
    case blockedUnknownVersion
}

struct MapUpdatePlan: Equatable, Sendable {
    let status: MapUpdatePlanStatus
    let mapID: String
    let installedVersion: MapVersion?
    let targetVersion: MapVersion
    let targetFilename: String
    let storagePlan: StoragePlan
    let backupRequired: Bool

    var isReady: Bool {
        status == .ready
    }
}

struct MapUpdatePlanner: Sendable {
    func plan(
        item: MapLifecycleItem,
        installedVersion: MapVersion?,
        targetVersion: MapVersion,
        targetFilename: String,
        newMapSizeBytes: UInt64,
        currentFreeSpace: UInt64,
        safetyReserve: UInt64 = StoragePlanner.defaultSafetyReserve
    ) -> MapUpdatePlan {
        let storagePlan = StoragePlanner(safetyReserve: safetyReserve).plan(
            currentFreeSpace: currentFreeSpace,
            selectedMapSizes: [newMapSizeBytes]
        )

        let status: MapUpdatePlanStatus
        if !item.isInstalled || !item.hasExactObjectIdentity || !item.classification.canBeManaged {
            status = .blockedAmbiguousMapIdentity
        } else if installedVersion == nil {
            status = .blockedUnknownVersion
        } else if let installedVersion, installedVersion == targetVersion {
            status = .noUpdateRequired
        } else if let installedVersion, installedVersion > targetVersion {
            status = .newerVersionAlreadyInstalled
        } else if !storagePlan.isAllowed {
            status = .blockedInsufficientSpace
        } else {
            status = .ready
        }

        return MapUpdatePlan(
            status: status,
            mapID: item.id,
            installedVersion: installedVersion,
            targetVersion: targetVersion,
            targetFilename: targetFilename,
            storagePlan: storagePlan,
            backupRequired: status == .ready
        )
    }
}

struct MapUpdateArtifact: Equatable, Sendable {
    let localURL: URL
    let sizeBytes: UInt64
    let sha256: String
}

struct MapReplacementObject: Equatable, Sendable {
    let itemID: UInt32
    let path: String
    let sizeBytes: UInt64
    let sha256: String
}

protocol MapReplacementTransport: MapLifecycleTransport {
    func writeReplacement(
        sourceURL: URL,
        targetFilename: String,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapReplacementObject

    func verifyReplacement(
        _ object: MapReplacementObject,
        expected: MapUpdateArtifact
    ) throws
}

struct MapReplacementResult: Equatable, Sendable {
    let plan: MapUpdatePlan
    let backup: MapBackupResult
    let replacement: MapReplacementObject
    let finalInventory: MapLifecycleInventoryFingerprint
}

/// Executes update operations in the only safe order: verified local backup,
/// write to a new Terento target, verify the new object, then delete the old
/// exact object. Any failure before that final step preserves the old map.
struct MapReplacementEngine: Sendable {
    func replace(
        plan: MapUpdatePlan,
        item: MapLifecycleItem,
        artifact: MapUpdateArtifact,
        backupDirectory: URL,
        confirmed: Bool,
        rescan: @escaping @Sendable () throws -> MapLifecycleInventory,
        transport: any MapReplacementTransport,
        onProgress: (@Sendable (TransferProgress) -> Void)? = nil
    ) throws -> MapReplacementResult {
        guard plan.isReady else {
            throw MapLifecycleError.replacementNotReady
        }
        guard confirmed else {
            throw MapLifecycleError.confirmationRequired
        }
        guard item.id == plan.mapID else {
            throw MapLifecycleError.staleInventory
        }

        let before = try rescan()
        guard before.item(id: item.id)?.fileIdentities == item.fileIdentities else {
            throw MapLifecycleError.staleInventory
        }

        let backup = try MapBackupEngine().backup(
            item: item,
            to: backupDirectory,
            transport: transport
        )

        let replacement: MapReplacementObject
        do {
            replacement = try transport.writeReplacement(
                sourceURL: artifact.localURL,
                targetFilename: plan.targetFilename,
                onProgress: onProgress
            )
            try transport.verifyReplacement(replacement, expected: artifact)
        } catch let error as MapLifecycleError {
            throw error
        } catch {
            throw MapLifecycleError.transportFailure(error.localizedDescription)
        }

        // This is intentionally the first point at which deletion is legal.
        for installedMap in item.installedMaps {
            try transport.delete(file: installedMap.sourceFile)
        }

        let after = try rescan()
        let deleted = Set(item.fileIdentities)
        guard after.fingerprint.files.allSatisfy({ !deleted.contains($0) }),
              after.fingerprint.removing(deleted).files.contains(where: {
                  $0.itemID == replacement.itemID
                      && $0.path == replacement.path
                      && $0.sizeBytes == replacement.sizeBytes
              }) else {
            throw MapLifecycleError.postActionVerificationFailed
        }

        return MapReplacementResult(
            plan: plan,
            backup: backup,
            replacement: replacement,
            finalInventory: after.fingerprint
        )
    }
}

import CryptoKit
import Foundation

/// Read-only transport boundary for lifecycle operations.
///
/// This protocol intentionally has no write, delete, move, rename, or backup
/// method. A native implementation can only read an already identified device
/// object into a local destination.
protocol MapLifecycleReadTransport: Sendable {
    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer
}

enum MapLifecycleReadTransportError: LocalizedError, Equatable, Sendable {
    case deviceDisconnected(String)
    case readFailed(String)

    var errorDescription: String? {
        switch self {
        case .deviceDisconnected(let message),
             .readFailed(let message):
            return message
        }
    }
}

struct ManagedMapBackupTarget: Sendable {
    let item: MapLifecycleItem
    let expectedSHA256ByItemID: [UInt32: String]

    init(
        item: MapLifecycleItem,
        expectedSHA256ByItemID: [UInt32: String]
    ) {
        self.item = item
        self.expectedSHA256ByItemID = expectedSHA256ByItemID
    }
}

enum ReadBackupStatus: String, Codable, Equatable, Sendable {
    case backupSuccess = "BACKUP_SUCCESS"
    case backupFailed = "BACKUP_FAILED"
    case backupFailedSizeMismatch = "BACKUP_FAILED_SIZE_MISMATCH"
    case backupFailedHashMismatch = "BACKUP_FAILED_HASH_MISMATCH"
    case backupFailedDeviceDisconnected = "BACKUP_FAILED_DEVICE_DISCONNECTED"
    case unmanagedObject = "UNMANAGED_OBJECT"
}

struct ReadBackupResult: Equatable, Sendable {
    let mapID: String
    let status: ReadBackupStatus
    let files: [VerifiedBackupFile]
    let message: String

    var isSuccess: Bool {
        status == .backupSuccess
    }
}

/// Coordinates a verified local backup without exposing transport details to
/// SwiftUI. Progress is normalized across every file in the map so the
/// lifecycle UI can show one operation-level transfer state.
struct ReadBackupAdapter: Sendable {
    private let transport: any MapLifecycleReadTransport
    private let backupDirectoryOverride: URL?
    private let now: @Sendable () -> Date

    init(
        transport: any MapLifecycleReadTransport,
        backupDirectory: URL? = nil,
        now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.transport = transport
        self.backupDirectoryOverride = backupDirectory
        self.now = now
    }

    func backup(
        target: ManagedMapBackupTarget,
        onProgress: (@Sendable (TransferProgress) -> Void)? = nil
    ) -> ReadBackupResult {
        let item = target.item

        guard item.isInstalled,
              item.classification == .terentoManaged,
              item.hasExactObjectIdentity else {
            return failure(
                mapID: item.id,
                status: .unmanagedObject,
                message: "This map is not proven to be managed by Terento, so no backup was created."
            )
        }

        for file in item.installedMaps {
            guard let objectID = file.sourceFile.itemID,
                  let expectedHash = target.expectedSHA256ByItemID[objectID],
                  !normalizedHash(expectedHash).isEmpty else {
                return failure(
                    mapID: item.id,
                    status: .backupFailed,
                    message: "The managed map has no complete local integrity record, so the backup was stopped."
                )
            }
        }

        guard let backupRoot = resolvedBackupDirectory() else {
            return failure(
                mapID: item.id,
                status: .backupFailed,
                message: "Terento could not find a safe local backup location."
            )
        }

        let operationDirectory = backupRoot.appendingPathComponent(
            operationDirectoryName(for: item),
            isDirectory: true
        )
        let fileManager = FileManager.default

        do {
            try fileManager.createDirectory(
                at: operationDirectory,
                withIntermediateDirectories: true
            )
        } catch {
            return failure(
                mapID: item.id,
                status: .backupFailed,
                message: "Terento could not create the local backup location."
            )
        }

        let totalExpectedBytes = item.installedMaps.reduce(into: UInt64.zero) { total, installedMap in
            let result = total.addingReportingOverflow(installedMap.sourceFile.sizeBytes)
            total = result.overflow ? UInt64.max : result.partialValue
        }
        var completedBytes: UInt64 = 0
        var stagedFiles: [(stagedURL: URL, finalURL: URL, verified: VerifiedBackupFile)] = []
        defer {
            // A successful operation moves every staged file below and leaves
            // the operation directory in place. On every failure this removes
            // partial local output, never anything on the Garmin device.
            if stagedFiles.contains(where: { fileManager.fileExists(atPath: $0.stagedURL.path) }) {
                for file in stagedFiles {
                    try? fileManager.removeItem(at: file.stagedURL)
                }
            }
        }

        for installedMap in item.installedMaps {
            guard let sourceIdentity = MapLifecycleFileIdentity(file: installedMap.sourceFile),
                  let expectedHash = target.expectedSHA256ByItemID[sourceIdentity.itemID] else {
                removeLocalDirectory(operationDirectory)
                return failure(
                    mapID: item.id,
                    status: .backupFailed,
                    message: "The managed map identity could not be verified locally."
                )
            }

            let safeFilename = safeComponent(installedMap.sourceFile.filename)
            let stagedURL = operationDirectory.appendingPathComponent(
                ".\(safeFilename)-\(sourceIdentity.itemID).part",
                isDirectory: false
            )
            let finalURL = operationDirectory.appendingPathComponent(
                "\(safeComponent(mapIdentity(for: item)))-\(safeComponent(versionLabel(for: item)))-\(timestamp())-\(sourceIdentity.itemID)-\(safeFilename)",
                isDirectory: false
            )
            let completedBeforeFile = completedBytes
            let sourceSizeBytes = sourceIdentity.sizeBytes

            do {
                let transfer = try transport.readExistingFile(
                    file: installedMap.sourceFile,
                    to: stagedURL,
                    onProgress: { progress in
                        let fileBytes = min(progress.bytesTransferred, sourceSizeBytes)
                        let aggregate = completedBeforeFile.addingReportingOverflow(fileBytes)
                        onProgress?(TransferProgress(
                            bytesTransferred: aggregate.overflow ? UInt64.max : aggregate.partialValue,
                            totalBytes: totalExpectedBytes,
                            bytesPerSecond: progress.bytesPerSecond
                        ))
                    }
                )
                let localSize = try fileSize(at: stagedURL)

                guard transfer.itemID == sourceIdentity.itemID,
                      transfer.sourcePath == sourceIdentity.path,
                      transfer.reportedSizeBytes == sourceIdentity.sizeBytes,
                      localSize == sourceIdentity.sizeBytes else {
                    removeLocalDirectory(operationDirectory)
                    return failure(
                        mapID: item.id,
                        status: .backupFailedSizeMismatch,
                        message: "The local backup size did not match the exact map object on the watch."
                    )
                }

                let actualHash = try sha256(of: stagedURL)
                guard actualHash == normalizedHash(expectedHash) else {
                    removeLocalDirectory(operationDirectory)
                    return failure(
                        mapID: item.id,
                        status: .backupFailedHashMismatch,
                        message: "The local backup contents did not match Terento's integrity record."
                    )
                }

                stagedFiles.append(
                    (
                        stagedURL: stagedURL,
                        finalURL: finalURL,
                        verified: VerifiedBackupFile(
                            source: sourceIdentity,
                            localURL: finalURL,
                            sizeBytes: localSize,
                            sha256: actualHash
                        )
                    )
                )
                let completed = completedBytes.addingReportingOverflow(sourceSizeBytes)
                completedBytes = completed.overflow ? UInt64.max : completed.partialValue
            } catch let error as MapLifecycleReadTransportError {
                removeLocalDirectory(operationDirectory)
                let status: ReadBackupStatus = {
                    if case .deviceDisconnected = error {
                        return .backupFailedDeviceDisconnected
                    }
                    return .backupFailed
                }()
                return failure(
                    mapID: item.id,
                    status: status,
                    message: error.localizedDescription
                )
            } catch {
                removeLocalDirectory(operationDirectory)
                return failure(
                    mapID: item.id,
                    status: .backupFailed,
                    message: "Terento could not read the map from the watch."
                )
            }
        }

        do {
            for file in stagedFiles {
                try fileManager.moveItem(at: file.stagedURL, to: file.finalURL)
            }
        } catch {
            removeLocalDirectory(operationDirectory)
            return failure(
                mapID: item.id,
                status: .backupFailed,
                message: "Terento could not finish the local backup safely."
            )
        }

        return ReadBackupResult(
            mapID: item.id,
            status: .backupSuccess,
            files: stagedFiles.map(\.verified),
            message: "The map was backed up locally and its size and SHA-256 were verified."
        )
    }

    private func resolvedBackupDirectory() -> URL? {
        if let backupDirectoryOverride {
            return backupDirectoryOverride
        }

        guard let applicationSupport = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first else {
            return nil
        }

        return applicationSupport
            .appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("Backups", isDirectory: true)
    }

    private func operationDirectoryName(for item: MapLifecycleItem) -> String {
        "\(safeComponent(mapIdentity(for: item)))-\(safeComponent(versionLabel(for: item)))-\(timestamp())-\(UUID().uuidString.lowercased())"
    }

    private func mapIdentity(for item: MapLifecycleItem) -> String {
        let provider = item.provider ?? "map"
        let region = item.region ?? item.id
        return "\(provider)-\(region)"
    }

    private func versionLabel(for item: MapLifecycleItem) -> String {
        item.version?.description ?? "unknown-version"
    }

    private func timestamp() -> String {
        String(Int(now().timeIntervalSince1970))
    }

    private func safeComponent(_ value: String) -> String {
        let normalized = value.replacingOccurrences(
            of: "[^A-Za-z0-9._-]",
            with: "_",
            options: .regularExpression
        )
        return normalized.isEmpty ? "map" : normalized
    }

    private func normalizedHash(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func fileSize(at url: URL) throws -> UInt64 {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard let number = attributes[.size] as? NSNumber else {
            throw MapLifecycleReadTransportError.readFailed("The local backup size is unavailable.")
        }
        return number.uint64Value
    }

    private func sha256(of url: URL) throws -> String {
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

    private func removeLocalDirectory(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }

    private func failure(
        mapID: String,
        status: ReadBackupStatus,
        message: String
    ) -> ReadBackupResult {
        ReadBackupResult(mapID: mapID, status: status, files: [], message: message)
    }
}

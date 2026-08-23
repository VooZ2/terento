import Darwin
import Foundation

enum TerentoManifestStoreError: LocalizedError, Equatable, Sendable {
    case applicationSupportUnavailable
    case invalidDeviceKey
    case unreadableManifest
    case lockFailed
    case newerEntryExists
    case writeFailed
    case cleanupFailed

    var errorDescription: String? {
        switch self {
        case .applicationSupportUnavailable:
            return "Terento could not find its local application data directory."
        case .invalidDeviceKey:
            return "Terento could not safely address the local device manifest."
        case .unreadableManifest:
            return "Terento found a local device manifest it could not safely read."
        case .lockFailed:
            return "Terento could not lock the local device manifest safely."
        case .newerEntryExists:
            return "Terento refused to replace a newer local ownership record."
        case .writeFailed:
            return "Terento could not record local ownership of the installed map."
        case .cleanupFailed:
            return "Terento could not remove the local ownership record after the device change."
        }
    }
}

protocol TerentoManifestStore: Sendable {
    func record(_ entry: TerentoManifestEntry) throws
}

protocol TerentoManifestCleanupStore: Sendable {
    func remove(deviceKey: String, devicePath: String, filename: String) throws -> Bool
}

protocol TerentoManifestUpdateStore: Sendable {
    func replaceAfterUpdate(
        deviceKey: String,
        oldDevicePath: String,
        oldFilename: String,
        newEntry: TerentoManifestEntry
    ) throws
}

struct LocalTerentoManifestStore: TerentoManifestStore, TerentoManifestCleanupStore, TerentoManifestUpdateStore, Sendable {
    private let rootDirectory: URL?

    init(rootDirectory: URL? = nil) {
        self.rootDirectory = rootDirectory
    }

    /// Reads the local ownership record for one device. A missing manifest is
    /// a normal state for a device Terento has not written to yet; an
    /// unreadable manifest remains an error so callers can fail closed.
    func read(deviceKey: String) throws -> TerentoManifest? {
        let manifestURL = try manifestURL(for: deviceKey)
        return try withManifestLock(at: manifestURL, exclusive: false) {
            try readUnlocked(manifestURL)
        }
    }

    func record(_ entry: TerentoManifestEntry) throws {
        let fileManager = FileManager.default
        let manifestURL = try manifestURL(for: entry.deviceKey)
        let deviceDirectory = manifestURL.deletingLastPathComponent()

        do {
            try withManifestLock(at: manifestURL, exclusive: true) {
                var entries = try readUnlocked(manifestURL)?.entries ?? []
                if entries.contains(where: {
                    $0.deviceKey == entry.deviceKey
                        && $0.devicePath == entry.devicePath
                        && $0.filename == entry.filename
                        && $0.installedAt > entry.installedAt
                }) {
                    throw TerentoManifestStoreError.newerEntryExists
                }

                entries.removeAll {
                    $0.deviceKey == entry.deviceKey
                        && $0.devicePath == entry.devicePath
                        && $0.filename == entry.filename
                }
                entries.append(entry)

                try fileManager.createDirectory(
                    at: deviceDirectory,
                    withIntermediateDirectories: true
                )
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                let data = try encoder.encode(TerentoManifest(entries: entries))
                try data.write(to: manifestURL, options: .atomic)
            }
        } catch let error as TerentoManifestStoreError {
            throw error
        } catch {
            throw TerentoManifestStoreError.writeFailed
        }
    }

    /// Removes only the exact local ownership entry that was successfully
    /// removed from the device. A missing entry is reported to the caller so a
    /// successful device mutation cannot be mistaken for a fully synchronized
    /// local lifecycle state.
    func remove(deviceKey: String, devicePath: String, filename: String) throws -> Bool {
        let fileManager = FileManager.default
        let manifestURL = try manifestURL(for: deviceKey)

        do {
            return try withManifestLock(at: manifestURL, exclusive: true) {
                guard let manifest = try readUnlocked(manifestURL) else {
                    return false
                }

                let remainingEntries = manifest.entries.filter { entry in
                    !(entry.deviceKey == deviceKey
                        && entry.devicePath == devicePath
                        && entry.filename == filename)
                }

                guard remainingEntries.count != manifest.entries.count else {
                    return false
                }

                if remainingEntries.isEmpty {
                    try fileManager.removeItem(at: manifestURL)
                } else {
                    let encoder = JSONEncoder()
                    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                    let data = try encoder.encode(TerentoManifest(entries: remainingEntries))
                    try data.write(to: manifestURL, options: .atomic)
                }

                return true
            }
        } catch let error as TerentoManifestStoreError {
            throw error
        } catch {
            throw TerentoManifestStoreError.cleanupFailed
        }
    }

    /// Atomically reconciles one verified update. The old exact entry must
    /// exist; otherwise a device write can never be reported as a completed
    /// managed update with an invented local ownership record.
    func replaceAfterUpdate(
        deviceKey: String,
        oldDevicePath: String,
        oldFilename: String,
        newEntry: TerentoManifestEntry
    ) throws {
        guard newEntry.deviceKey == deviceKey else {
            throw TerentoManifestStoreError.invalidDeviceKey
        }

        let fileManager = FileManager.default
        let manifestURL = try manifestURL(for: deviceKey)
        do {
            try withManifestLock(at: manifestURL, exclusive: true) {
                guard let manifest = try readUnlocked(manifestURL) else {
                    throw TerentoManifestStoreError.cleanupFailed
                }

                guard manifest.entries.contains(where: {
                    $0.deviceKey == deviceKey
                        && $0.devicePath == oldDevicePath
                        && $0.filename == oldFilename
                }) else {
                    throw TerentoManifestStoreError.cleanupFailed
                }

                if manifest.entries.contains(where: {
                    $0.deviceKey == deviceKey
                        && $0.devicePath == newEntry.devicePath
                        && $0.filename == newEntry.filename
                        && $0.version > newEntry.version
                }) {
                    throw TerentoManifestStoreError.newerEntryExists
                }

                var entries = manifest.entries.filter { entry in
                    !(
                        entry.deviceKey == deviceKey
                            && (
                                (entry.devicePath == oldDevicePath && entry.filename == oldFilename)
                                    || (entry.devicePath == newEntry.devicePath && entry.filename == newEntry.filename)
                            )
                    )
                }
                entries.append(newEntry)

                try fileManager.createDirectory(
                    at: manifestURL.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                let data = try encoder.encode(TerentoManifest(entries: entries))
                try data.write(to: manifestURL, options: .atomic)
            }
        } catch let error as TerentoManifestStoreError {
            throw error
        } catch {
            throw TerentoManifestStoreError.cleanupFailed
        }
    }

    private func manifestURL(for deviceKey: String) throws -> URL {
        guard !deviceKey.isEmpty,
              !deviceKey.contains("/"),
              !deviceKey.contains("\\"),
              !deviceKey.contains(".."),
              !deviceKey.contains("\0") else {
            throw TerentoManifestStoreError.invalidDeviceKey
        }

        let applicationSupport: URL
        if let rootDirectory {
            applicationSupport = rootDirectory
        } else {
            let fileManager = FileManager.default
            guard let directory = fileManager.urls(
                for: .applicationSupportDirectory,
                in: .userDomainMask
            ).first else {
                throw TerentoManifestStoreError.applicationSupportUnavailable
            }
            applicationSupport = directory
        }

        return applicationSupport
            .appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("devices", isDirectory: true)
            .appendingPathComponent(deviceKey, isDirectory: true)
            .appendingPathComponent("manifest.json")
    }

    private func readUnlocked(_ manifestURL: URL) throws -> TerentoManifest? {
        guard FileManager.default.fileExists(atPath: manifestURL.path) else {
            return nil
        }

        do {
            let data = try Data(contentsOf: manifestURL)
            return try JSONDecoder().decode(TerentoManifest.self, from: data)
        } catch {
            throw TerentoManifestStoreError.unreadableManifest
        }
    }

    private func withManifestLock<Result>(
        at manifestURL: URL,
        exclusive: Bool,
        operation: () throws -> Result
    ) throws -> Result {
        let directory = manifestURL.deletingLastPathComponent()
        do {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true
            )
        } catch {
            throw TerentoManifestStoreError.applicationSupportUnavailable
        }

        let lockURL = manifestURL.appendingPathExtension("lock")
        let descriptor = lockURL.path.withCString {
            open($0, O_CREAT | O_RDWR, mode_t(0o600))
        }
        guard descriptor >= 0 else {
            throw TerentoManifestStoreError.lockFailed
        }
        defer { close(descriptor) }

        let lockOperation = exclusive ? LOCK_EX : LOCK_SH
        guard flock(descriptor, lockOperation) == 0 else {
            throw TerentoManifestStoreError.lockFailed
        }
        defer { _ = flock(descriptor, LOCK_UN) }

        return try operation()
    }
}

extension DeviceIdentity {
    var localManifestDeviceKey: String {
        let modelKey = GarminDeviceModelNormalizer.normalize(canonicalModel ?? model)
            .replacingOccurrences(of: " ", with: "-")
        return "\(modelKey)-\(String(format: "%04x", usbVendorId))-\(String(format: "%04x", usbProductId))"
    }
}

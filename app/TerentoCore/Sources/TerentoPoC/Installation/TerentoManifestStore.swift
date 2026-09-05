import Darwin
import CryptoKit
import Foundation

enum TerentoManifestStoreError: LocalizedError, Equatable, Sendable {
    case applicationSupportUnavailable
    case invalidDeviceKey
    case unreadableManifest
    case lockFailed
    case newerEntryExists
    case writeFailed
    case cleanupFailed
    case unreadableRecovery
    case recoveryWriteFailed
    case recoveryCleanupFailed

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
        case .unreadableRecovery:
            return "Terento found a failed-install recovery record it could not safely read."
        case .recoveryWriteFailed:
            return "Terento could not record the failed installation safely."
        case .recoveryCleanupFailed:
            return "Terento could not remove the failed-install recovery record."
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

protocol TerentoFailedInstallRecoveryStore: Sendable {
    func read(deviceKey: String) throws -> [TerentoFailedInstallRecoveryRecord]
    func record(_ record: TerentoFailedInstallRecoveryRecord) throws
    func remove(deviceKey: String, devicePath: String, filename: String) throws -> Bool
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

/// Stores only incomplete-install candidates. A candidate is never enough by
/// itself to delete a device object: the recovery delete path still verifies
/// the live object, size, full hash, backup, and post-delete absence.
struct LocalTerentoFailedInstallRecoveryStore: TerentoFailedInstallRecoveryStore, Sendable {
    private let rootDirectory: URL?

    init(rootDirectory: URL? = nil) {
        self.rootDirectory = rootDirectory
    }

    func read(deviceKey: String) throws -> [TerentoFailedInstallRecoveryRecord] {
        let recoveryURL = try recoveryURL()
        return try withRecoveryLock(at: recoveryURL, exclusive: false) {
            guard FileManager.default.fileExists(atPath: recoveryURL.path) else {
                return []
            }

            do {
                let data = try Data(contentsOf: recoveryURL)
                let file = try JSONDecoder().decode(
                    TerentoFailedInstallRecoveryFile.self,
                    from: data
                )
                return file.records.filter { $0.deviceKey == deviceKey }
            } catch {
                throw TerentoManifestStoreError.unreadableRecovery
            }
        }
    }

    func record(_ record: TerentoFailedInstallRecoveryRecord) throws {
        let fileManager = FileManager.default
        let recoveryURL = try recoveryURL()

        do {
            try withRecoveryLock(at: recoveryURL, exclusive: true) {
                var records = try readUnlocked(recoveryURL)
                records.removeAll {
                    $0.deviceKey == record.deviceKey
                        && $0.devicePath == record.devicePath
                        && $0.filename == record.filename
                }
                records.append(record)

                try fileManager.createDirectory(
                    at: recoveryURL.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                let data = try encoder.encode(
                    TerentoFailedInstallRecoveryFile(records: records)
                )
                try data.write(to: recoveryURL, options: .atomic)
            }
        } catch let error as TerentoManifestStoreError {
            throw error
        } catch {
            throw TerentoManifestStoreError.recoveryWriteFailed
        }
    }

    func remove(
        deviceKey: String,
        devicePath: String,
        filename: String
    ) throws -> Bool {
        let fileManager = FileManager.default
        let recoveryURL = try recoveryURL()

        do {
            return try withRecoveryLock(at: recoveryURL, exclusive: true) {
                guard fileManager.fileExists(atPath: recoveryURL.path) else {
                    return false
                }

                var records = try readUnlocked(recoveryURL)
                let originalCount = records.count
                records.removeAll {
                    $0.deviceKey == deviceKey
                        && $0.devicePath == devicePath
                        && $0.filename == filename
                }
                guard records.count != originalCount else {
                    return false
                }

                if records.isEmpty {
                    try fileManager.removeItem(at: recoveryURL)
                } else {
                    let encoder = JSONEncoder()
                    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                    let data = try encoder.encode(
                        TerentoFailedInstallRecoveryFile(records: records)
                    )
                    try data.write(to: recoveryURL, options: .atomic)
                }

                return true
            }
        } catch let error as TerentoManifestStoreError {
            throw error
        } catch {
            throw TerentoManifestStoreError.recoveryCleanupFailed
        }
    }

    private func recoveryURL() throws -> URL {
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
            .appendingPathComponent("failed-install-recovery.json")
    }

    private func readUnlocked(
        _ recoveryURL: URL
    ) throws -> [TerentoFailedInstallRecoveryRecord] {
        guard FileManager.default.fileExists(atPath: recoveryURL.path) else {
            return []
        }

        do {
            let data = try Data(contentsOf: recoveryURL)
            return try JSONDecoder().decode(
                TerentoFailedInstallRecoveryFile.self,
                from: data
            ).records
        } catch {
            throw TerentoManifestStoreError.unreadableRecovery
        }
    }

    private func withRecoveryLock<Result>(
        at recoveryURL: URL,
        exclusive: Bool,
        operation: () throws -> Result
    ) throws -> Result {
        let directory = recoveryURL.deletingLastPathComponent()
        do {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true
            )
        } catch {
            throw TerentoManifestStoreError.applicationSupportUnavailable
        }

        let lockURL = recoveryURL.appendingPathExtension("lock")
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
    var physicalManifestDeviceKey: String? {
        guard let localHardwareIdentifier,
              !localHardwareIdentifier.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }

        return try? LocalPhysicalDeviceKeyDeriver().derive(
            source: localIdentityResolution == .garminUnitID ? "garmin-unit-id" : "mtp-serial",
            value: localHardwareIdentifier
        )
    }

    var legacyManifestDeviceKey: String {
        let modelKey = GarminDeviceModelNormalizer.normalize(canonicalModel ?? model)
            .replacingOccurrences(of: " ", with: "-")
        return "\(modelKey)-\(String(format: "%04x", usbVendorId))-\(String(format: "%04x", usbProductId))"
    }

    var localManifestDeviceKey: String {
        physicalManifestDeviceKey ?? legacyManifestDeviceKey
    }
}

struct LocalPhysicalDeviceKeyDeriver {
    private static let secretByteCount = 32
    private let rootDirectory: URL?

    init(rootDirectory: URL? = nil) {
        self.rootDirectory = rootDirectory
    }

    func derive(source: String, value: String) throws -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else {
            throw TerentoManifestStoreError.invalidDeviceKey
        }

        let secret = try loadOrCreateSecret()
        let input = Data("terento-watch-v2:\(source):\(normalized)".utf8)
        let authenticationCode = HMAC<SHA256>.authenticationCode(
            for: input,
            using: SymmetricKey(data: secret)
        )
        let digest = authenticationCode.map { String(format: "%02x", $0) }.joined()
        return "watch-v2-\(digest)"
    }

    private func loadOrCreateSecret() throws -> Data {
        let directory: URL
        if let rootDirectory {
            directory = rootDirectory
        } else {
            guard let applicationSupport = FileManager.default.urls(
                for: .applicationSupportDirectory,
                in: .userDomainMask
            ).first else {
                throw TerentoManifestStoreError.applicationSupportUnavailable
            }
            directory = applicationSupport.appendingPathComponent("Terento", isDirectory: true)
        }
        do {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
        } catch {
            throw TerentoManifestStoreError.applicationSupportUnavailable
        }

        let secretURL = directory.appendingPathComponent(".device-key-secret", isDirectory: false)
        let lockURL = directory.appendingPathComponent(".device-key-secret.lock", isDirectory: false)
        let descriptor = lockURL.path.withCString {
            open($0, O_CREAT | O_RDWR, mode_t(0o600))
        }
        guard descriptor >= 0, flock(descriptor, LOCK_EX) == 0 else {
            if descriptor >= 0 { close(descriptor) }
            throw TerentoManifestStoreError.lockFailed
        }
        defer {
            _ = flock(descriptor, LOCK_UN)
            close(descriptor)
        }

        if let existing = try? Data(contentsOf: secretURL),
           existing.count == Self.secretByteCount {
            return existing
        }

        var generator = SystemRandomNumberGenerator()
        let secret = Data((0..<Self.secretByteCount).map { _ in UInt8.random(in: .min ... .max, using: &generator) })
        do {
            try secret.write(to: secretURL, options: .atomic)
            guard chmod(secretURL.path, mode_t(0o600)) == 0 else {
                throw TerentoManifestStoreError.writeFailed
            }
        } catch let error as TerentoManifestStoreError {
            throw error
        } catch {
            throw TerentoManifestStoreError.writeFailed
        }
        return secret
    }
}

import CryptoKit
import Foundation

struct TerentoManifestExportEntry: Codable, Equatable, Sendable {
    let devicePath: String
    let filename: String
    let providerId: String
    let regionId: String
    let version: MapVersion
    let sizeBytes: UInt64
    let sha256: String
    let installedAt: Date
}

struct TerentoManifestExportDocument: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1

    let schemaVersion: Int
    let exportedAt: Date
    let watchProofSalt: String
    let watchProofSHA256: String
    let entries: [TerentoManifestExportEntry]
}

enum ManagedMapRecoveryError: LocalizedError, Equatable, Sendable {
    case stableWatchIdentityUnavailable
    case invalidExport
    case exportBelongsToAnotherWatch
    case exactMapNotFound
    case ambiguousMap
    case liveMapChanged
    case readFailed

    var errorDescription: String? {
        switch self {
        case .stableWatchIdentityUnavailable:
            return "This Garmin watch does not expose the stable local identity required for recovery."
        case .invalidExport:
            return "The Terento ownership file is invalid or unsupported."
        case .exportBelongsToAnotherWatch:
            return "This ownership file belongs to a different Garmin watch."
        case .exactMapNotFound:
            return "The exact exported Terento map was not found on this watch."
        case .ambiguousMap:
            return "More than one possible map matched the ownership file. Nothing was recovered."
        case .liveMapChanged:
            return "The complete map on the watch no longer matches the ownership file."
        case .readFailed:
            return "Terento could not read the complete map needed for recovery."
        }
    }
}

struct TerentoManifestExportService: Sendable {
    func makeDocument(
        manifest: TerentoManifest,
        identity: DeviceIdentity,
        now: Date = Date()
    ) throws -> TerentoManifestExportDocument {
        let identifier = try stableIdentifier(from: identity)
        guard !manifest.entries.isEmpty else {
            throw ManagedMapRecoveryError.invalidExport
        }

        var generator = SystemRandomNumberGenerator()
        let salt = Data((0..<32).map { _ in UInt8.random(in: .min ... .max, using: &generator) })
        return TerentoManifestExportDocument(
            schemaVersion: TerentoManifestExportDocument.currentSchemaVersion,
            exportedAt: now,
            watchProofSalt: salt.base64EncodedString(),
            watchProofSHA256: Self.watchProof(identifier: identifier, salt: salt),
            entries: manifest.entries.map {
                TerentoManifestExportEntry(
                    devicePath: $0.devicePath,
                    filename: $0.filename,
                    providerId: $0.providerId,
                    regionId: $0.regionId,
                    version: $0.version,
                    sizeBytes: $0.sizeBytes,
                    sha256: $0.sha256,
                    installedAt: $0.installedAt
                )
            }
        )
    }

    func encode(_ document: TerentoManifestExportDocument) throws -> Data {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(document)
    }

    func decode(_ data: Data) throws -> TerentoManifestExportDocument {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let document = try? decoder.decode(TerentoManifestExportDocument.self, from: data),
              document.schemaVersion == TerentoManifestExportDocument.currentSchemaVersion,
              !document.entries.isEmpty,
              Data(base64Encoded: document.watchProofSalt)?.count == 32,
              Self.normalizedSHA(document.watchProofSHA256) != nil,
              document.entries.allSatisfy({ entry in
                  entry.devicePath == "/GARMIN/\(entry.filename)"
                      && TerentoManagedFilenameGenerator().isValid(entry.filename)
                      && entry.sizeBytes > 0
                      && Self.normalizedSHA(entry.sha256) != nil
              }) else {
            throw ManagedMapRecoveryError.invalidExport
        }
        return document
    }

    func validateWatch(
        _ document: TerentoManifestExportDocument,
        identity: DeviceIdentity
    ) throws {
        let identifier = try stableIdentifier(from: identity)
        guard let salt = Data(base64Encoded: document.watchProofSalt),
              Self.watchProof(identifier: identifier, salt: salt)
                == document.watchProofSHA256.lowercased() else {
            throw ManagedMapRecoveryError.exportBelongsToAnotherWatch
        }
    }

    private func stableIdentifier(from identity: DeviceIdentity) throws -> String {
        guard let value = identity.localHardwareIdentifier?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else {
            throw ManagedMapRecoveryError.stableWatchIdentityUnavailable
        }
        return value
    }

    private static func watchProof(identifier: String, salt: Data) -> String {
        var data = salt
        data.append(Data("terento-watch-export-v1:\(identifier)".utf8))
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func normalizedSHA(_ value: String) -> String? {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.count == 64 && normalized.allSatisfy(\.isHexDigit) ? normalized : nil
    }
}

struct ManagedMapRecoveryResult: Equatable, Sendable {
    let recoveredEntry: TerentoManifestEntry
}

struct ManagedMapRecoveryCoordinator: Sendable {
    private let manifestStore: any TerentoManifestStore
    private let deviceKeyProvider: @Sendable (DeviceIdentity) -> String?

    init(
        manifestStore: any TerentoManifestStore = LocalTerentoManifestStore(),
        deviceKeyProvider: @escaping @Sendable (DeviceIdentity) -> String? = { $0.physicalManifestDeviceKey }
    ) {
        self.manifestStore = manifestStore
        self.deviceKeyProvider = deviceKeyProvider
    }

    func recover(
        document: TerentoManifestExportDocument,
        identity: DeviceIdentity,
        liveFiles: [DeviceFile],
        reader: any MapLifecycleReadTransport
    ) throws -> ManagedMapRecoveryResult {
        let exportService = TerentoManifestExportService()
        try exportService.validateWatch(document, identity: identity)
        guard let deviceKey = deviceKeyProvider(identity) else {
            throw ManagedMapRecoveryError.stableWatchIdentityUnavailable
        }

        let matches: [(TerentoManifestExportEntry, DeviceFile)] = document.entries.flatMap { entry in
            liveFiles.compactMap { file in
                guard !file.isFolder,
                      file.path == entry.devicePath,
                      file.filename == entry.filename,
                      file.sizeBytes == entry.sizeBytes else {
                    return nil
                }
                return (entry, file)
            }
        }
        guard !matches.isEmpty else { throw ManagedMapRecoveryError.exactMapNotFound }
        guard matches.count == 1, let match = matches.first else {
            throw ManagedMapRecoveryError.ambiguousMap
        }

        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-recover-\(UUID().uuidString).img")
        defer { try? FileManager.default.removeItem(at: temporaryURL) }
        let installedFile = InstalledMapFile(
            path: match.1.path,
            filename: match.1.filename,
            sizeBytes: match.1.sizeBytes,
            itemID: match.1.itemID
        )
        do {
            let transfer = try reader.readExistingFile(
                file: installedFile,
                to: temporaryURL,
                onProgress: nil
            )
            guard transfer.itemID != 0,
                  transfer.sourcePath == match.1.path,
                  transfer.reportedSizeBytes == match.1.sizeBytes else {
                throw ManagedMapRecoveryError.liveMapChanged
            }
        } catch let error as ManagedMapRecoveryError {
            throw error
        } catch {
            throw ManagedMapRecoveryError.readFailed
        }

        guard try Self.sha256(of: temporaryURL).caseInsensitiveCompare(match.0.sha256) == .orderedSame else {
            throw ManagedMapRecoveryError.liveMapChanged
        }

        let recovered = TerentoManifestEntry(
            deviceKey: deviceKey,
            devicePath: match.0.devicePath,
            filename: match.0.filename,
            providerId: match.0.providerId,
            regionId: match.0.regionId,
            version: match.0.version,
            sizeBytes: match.0.sizeBytes,
            sha256: match.0.sha256.lowercased(),
            installedAt: match.0.installedAt
        )
        try manifestStore.record(recovered)
        return ManagedMapRecoveryResult(recoveredEntry: recovered)
    }

    private static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty { break }
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

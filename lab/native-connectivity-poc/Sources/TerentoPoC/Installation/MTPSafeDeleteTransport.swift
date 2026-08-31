import Foundation
import CryptoKit

/// Native Stage 5.2 transport. Inspection is read-only; deletion delegates
/// to the existing exact managed-map bridge operation. It is not wired to UI.
struct MTPSafeDeleteTransport: SafeDeleteTransport, Sendable {
    private let operationGate: MTPOperationGate
    private let lifecycleLease: MTPOperationLease?
    private let operationProfile: DeviceMapOperationProfile?

    init(
        operationProfile: DeviceMapOperationProfile? = nil,
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) {
        self.operationProfile = operationProfile
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
    }

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        try inspectExactObject(target, onProgress: nil)
    }

    func inspectExactObject(
        _ target: SafeDeleteTarget,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> SafeDeleteDeviceObject {
        let files: [DeviceFile]
        do {
            files = try MTPTransport(
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ).readFileInventory()
        } catch let error as MTPTransportError {
            switch error {
            case .readFailed(let message):
                if isMissing(message) {
                    throw SafeDeleteTransportError.objectNotFound
                }
                if isDisconnected(message) {
                    throw SafeDeleteTransportError.deviceDisconnected(message)
                }
                throw SafeDeleteTransportError.operationFailed(message)
            }
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }

        let candidates = files.filter { $0.path == target.expectedPath }
        guard !candidates.isEmpty else {
            throw SafeDeleteTransportError.objectNotFound
        }

        guard candidates.count == 1,
              let object = candidates.first,
              object.path == target.expectedPath,
              object.filename == target.expectedFilename,
              object.sizeBytes == target.expectedSizeBytes,
              !object.isFolder else {
            throw SafeDeleteTransportError.operationFailed(
                "The exact managed map identity changed during validation."
            )
        }

        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-remove-verify-\(UUID().uuidString).img")
        defer { try? FileManager.default.removeItem(at: temporaryURL) }

        let verifiedLiveItemID: UInt32
        do {
            let transfer = try MTPReadBackupAdapter(
                operationProfile: operationProfile,
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
                ).readExistingFile(
                file: InstalledMapFile(
                    path: object.path,
                    filename: object.filename,
                    sizeBytes: object.sizeBytes,
                    itemID: object.itemID
                ),
                to: temporaryURL,
                onProgress: onProgress
            )

            guard transfer.itemID != 0 else {
                throw SafeDeleteTransportError.operationFailed(
                    "The exact managed map no longer has a valid live object identity."
                )
            }

            verifiedLiveItemID = transfer.itemID
        } catch let error as MapLifecycleReadTransportError {
            switch error {
            case .deviceDisconnected(let message):
                throw SafeDeleteTransportError.deviceDisconnected(message)
            case .readFailed(let message):
                throw SafeDeleteTransportError.operationFailed(message)
            }
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }

        let liveHash: String
        do {
            liveHash = try sha256(of: temporaryURL)
        } catch {
            throw SafeDeleteTransportError.operationFailed(
                "The complete managed map could not be verified before removal."
            )
        }

        if target.ownership == .detectedNotManaged {
            guard try isRecognizedGarminIMG(at: temporaryURL) else {
                throw SafeDeleteTransportError.operationFailed(
                    "The selected third-party file is not a recognized Garmin map image. Nothing was removed."
                )
            }
        }

        return SafeDeleteDeviceObject(
            file: InstalledMapFile(
                path: object.path,
                filename: object.filename,
                sizeBytes: object.sizeBytes,
                itemID: verifiedLiveItemID
            ),
            sha256: liveHash
        )
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        do {
            let mapTransport = MTPMapInstallationTransport(
                operationProfile: operationProfile,
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            )
            if target.ownership == .detectedNotManaged {
                try mapTransport.deleteExternalExact(
                    targetFilename: target.expectedFilename,
                    expectedItemID: target.objectID,
                    expectedSizeBytes: target.expectedSizeBytes
                )
            } else {
                try mapTransport.deleteExact(
                    targetFilename: target.expectedFilename,
                    expectedItemID: target.objectID,
                    expectedSizeBytes: target.expectedSizeBytes
                )
            }
        } catch let error as InstallationTransportError {
            switch error {
            case .deviceDisconnected(let message, _):
                throw SafeDeleteTransportError.deviceDisconnected(message)
            case .remoteFileMissing:
                throw SafeDeleteTransportError.objectNotFound
            default:
                throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
            }
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }
    }

    private func isMissing(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("not found")
            || value.contains("missing")
            || value.contains("no such file")
    }

    private func isDisconnected(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("disconnected")
            || value.contains("not connected")
            || value.contains("no device")
    }

    private func sha256(of url: URL) throws -> String {
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

    private func isRecognizedGarminIMG(at url: URL) throws -> Bool {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let prefix = try handle.read(upToCount: GarminIMGMetadataParser.prefixLength) ?? Data()
        return GarminIMGMetadataParser().parse(Array(prefix)) != nil
    }

}

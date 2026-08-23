import CryptoKit
import Foundation

/// Native Stage 5.2 transport. Inspection is read-only; deletion delegates
/// to the existing exact managed-map bridge operation. It is not wired to UI.
struct MTPSafeDeleteTransport: SafeDeleteTransport, Sendable {
    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-safe-delete-check-\(UUID().uuidString).img")
        defer { try? FileManager.default.removeItem(at: temporaryURL) }

        let transfer: MapLifecycleBackupTransfer
        do {
            transfer = try MTPReadBackupAdapter().readExistingFile(
                file: target.sourceFile,
                to: temporaryURL,
                onProgress: nil
            )
        } catch let error as MapLifecycleReadTransportError {
            switch error {
            case .deviceDisconnected(let message):
                throw SafeDeleteTransportError.deviceDisconnected(message)
            case .readFailed(let message):
                if isMissing(message) {
                    throw SafeDeleteTransportError.objectNotFound
                }
                throw SafeDeleteTransportError.operationFailed(message)
            }
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }

        guard transfer.itemID == target.objectID,
              transfer.sourcePath == target.expectedPath,
              transfer.reportedSizeBytes == target.expectedSizeBytes else {
            throw SafeDeleteTransportError.operationFailed(
                "The exact managed map identity changed during validation."
            )
        }

        do {
            return SafeDeleteDeviceObject(
                file: target.sourceFile,
                sha256: try sha256(of: temporaryURL)
            )
        } catch {
            throw SafeDeleteTransportError.operationFailed(
                "The managed map could not be hashed before removal."
            )
        }
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        do {
            try MTPMapInstallationTransport().deleteExact(
                targetFilename: target.expectedFilename,
                expectedItemID: target.objectID
            )
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
}

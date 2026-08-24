import Foundation

/// Native Stage 5.2 transport. Inspection is read-only; deletion delegates
/// to the existing exact managed-map bridge operation. It is not wired to UI.
struct MTPSafeDeleteTransport: SafeDeleteTransport, Sendable {
    private let operationGate: MTPOperationGate
    private let lifecycleLease: MTPOperationLease?

    init(
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) {
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
    }

    func inspectExactObject(_ target: SafeDeleteTarget) throws -> SafeDeleteDeviceObject {
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

        let candidates = files.filter {
            $0.itemID == target.objectID || $0.path == target.expectedPath
        }
        guard !candidates.isEmpty else {
            throw SafeDeleteTransportError.objectNotFound
        }

        guard candidates.count == 1,
              let object = candidates.first,
              object.itemID == target.objectID,
              object.path == target.expectedPath,
              object.filename == target.expectedFilename,
              object.sizeBytes == target.expectedSizeBytes,
              !object.isFolder else {
            throw SafeDeleteTransportError.operationFailed(
                "The exact managed map identity changed during validation."
            )
        }

        // Manual Remove intentionally does not copy or hash the complete map.
        // The manifest SHA-256 remains an integrity record, while the live MTP
        // inventory proves the exact object identity and metadata immediately
        // before DeleteObject.
        return SafeDeleteDeviceObject(
            file: InstalledMapFile(
                path: object.path,
                filename: object.filename,
                sizeBytes: object.sizeBytes,
                itemID: object.itemID
            ),
            sha256: nil
        )
    }

    func deleteExactObject(_ target: SafeDeleteTarget) throws {
        do {
            try MTPMapInstallationTransport(
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ).deleteExact(
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

    private func isDisconnected(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("disconnected")
            || value.contains("not connected")
            || value.contains("no device")
    }

}

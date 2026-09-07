import Foundation

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
                if isBusy(message) {
                    throw SafeDeleteTransportError.deviceBusy(message)
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

        let liveFile = InstalledMapFile(
            path: object.path,
            filename: object.filename,
            sizeBytes: object.sizeBytes,
            itemID: object.itemID
        )

        // Manual Remove must not copy/hash a large managed map just to
        // authorize a file already proven Terento-owned by the local
        // manifest. The live inventory above has re-established the exact
        // session-local object identity, path, filename, and size.
        if target.ownership == .managedByTerento {
            onProgress?(TransferProgress(
                bytesTransferred: target.expectedSizeBytes,
                totalBytes: target.expectedSizeBytes
            ))
            return SafeDeleteDeviceObject(
                file: liveFile,
                sha256: target.expectedSHA256,
                contentHashVerified: false
            )
        }

        // A recognized third-party map has no trusted manifest hash. Read
        // only the bounded Garmin IMG header to prove that the exact target
        // is a map; never copy the whole external file merely to remove it.
        do {
            let prefix = try MTPTransport(
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ).readFilePrefix(
                for: object,
                maxLength: GarminIMGMetadataParser.prefixLength
            )
            guard GarminIMGMetadataParser().parse(prefix) != nil else {
                throw SafeDeleteTransportError.operationFailed(
                    "The selected third-party file is not a recognized Garmin map image. Nothing was removed."
                )
            }
        } catch let error as MTPTransportError {
            let message = error.localizedDescription
            if isBusy(message) {
                throw SafeDeleteTransportError.deviceBusy(message)
            }
            if isDisconnected(message) {
                throw SafeDeleteTransportError.deviceDisconnected(message)
            }
            throw SafeDeleteTransportError.operationFailed(message)
        } catch let error as SafeDeleteTransportError {
            throw error
        } catch {
            throw SafeDeleteTransportError.operationFailed(error.localizedDescription)
        }

        return SafeDeleteDeviceObject(
            file: liveFile,
            sha256: String(repeating: "0", count: 64),
            contentHashVerified: false
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
                let message = error.localizedDescription
                if isBusy(message) {
                    throw SafeDeleteTransportError.deviceBusy(message)
                }
                throw SafeDeleteTransportError.operationFailed(message)
            }
        } catch {
            let message = error.localizedDescription
            if isBusy(message) {
                throw SafeDeleteTransportError.deviceBusy(message)
            }
            throw SafeDeleteTransportError.operationFailed(message)
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

    private func isBusy(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("failed to open session")
            || value.contains("could not be opened")
            || value.contains("ptp_error_io")
            || value.contains("libusb")
            || value.contains("claim interface")
            || value.contains("claim_interface")
            || value.contains("resource busy")
            || value.contains("reset device")
            || value.contains("detach_kernel_driver")
            || value.contains("result too large")
    }

}

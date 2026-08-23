import Foundation
#if canImport(LibMTPBridge)
import LibMTPBridge
#endif

/// Native read-only adapter for the Stage 5.1 backup boundary.
///
/// The bridge function used here validates the exact MTP object ID and path
/// before reading it. This adapter deliberately exposes no write or delete
/// operation and is not connected to SwiftUI in Stage 5.1.
struct MTPReadBackupAdapter: MapLifecycleReadTransport, Sendable {
    private static let errorCapacity = 2048
    private let operationGate: MTPOperationGate
    private let lifecycleLease: MTPOperationLease?

    init(
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) {
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
    }

    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        try operationGate.withOperation(
            kind: .backup,
            lifecycleLease: lifecycleLease
        ) {
            try readExistingFileUncoordinated(
                file: file,
                to: destinationURL,
                onProgress: onProgress
            )
        }
    }

    private func readExistingFileUncoordinated(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleBackupTransfer {
        guard let itemID = file.itemID, itemID != 0 else {
            throw MapLifecycleReadTransportError.readFailed(
                "The map does not have an exact device object identity."
            )
        }

        var sizeBytes: UInt64 = 0
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
        let result = file.path.withCString { expectedPath in
            destinationURL.path.withCString { localPath in
                errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                    terento_mtp_read_existing_file_to_local(
                        itemID,
                        expectedPath,
                        localPath,
                        &sizeBytes,
                        errorPointer.baseAddress,
                        errorPointer.count
                    )
                }
            }
        }

        guard result == 0 else {
            let message = errorMessage(from: errorBuffer)
            if isDisconnect(message) {
                throw MapLifecycleReadTransportError.deviceDisconnected(message)
            }
            throw MapLifecycleReadTransportError.readFailed(message)
        }

        onProgress?(TransferProgress(bytesTransferred: sizeBytes, totalBytes: sizeBytes))
        return MapLifecycleBackupTransfer(
            itemID: itemID,
            sourcePath: file.path,
            reportedSizeBytes: sizeBytes
        )
    }

    private func errorMessage(from buffer: [CChar]) -> String {
        buffer.withUnsafeBufferPointer { buffer in
            let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
            let message = String(decoding: bytes, as: UTF8.self)
            return message.isEmpty ? "The map could not be read from the Garmin watch." : message
        }
    }

    private func isDisconnect(_ message: String) -> Bool {
        let value = message.lowercased()
        return value.contains("disconnect")
            || value.contains("no such file")
            || value.contains("no mtp device")
            || value.contains("could not be opened")
    }
}

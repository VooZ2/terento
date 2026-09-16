import Foundation

/// Read-only transport boundary used for exact map verification and ownership
/// recovery. It has no persistent-backup, write, delete, move, or rename API.
protocol MapLifecycleReadTransport: Sendable {
    func readExistingFile(
        file: InstalledMapFile,
        to destinationURL: URL,
        onProgress: (@Sendable (TransferProgress) -> Void)?
    ) throws -> MapLifecycleReadTransfer
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

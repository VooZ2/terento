import Foundation

struct MTPWrittenMapObject: Equatable, Sendable {
    let itemID: UInt32
    let sizeBytes: UInt64
}

struct MTPReadBackMapObject: Equatable, Sendable {
    let itemID: UInt32
    let targetPath: String
    let reportedSizeBytes: UInt64
    let localURL: URL
}

struct MTPWriteAndReadBackResult: Equatable, Sendable {
    let written: MTPWrittenMapObject
    let readBack: MTPReadBackMapObject
}

enum MTPWriteAndReadBackError: Error {
    case write(any Error)
    case readBack(any Error, createdItemID: UInt32?)
}

enum InstallationTransportError: LocalizedError, Equatable, Sendable {
    case targetAlreadyExists
    case remoteFileMissing
    case objectIdentityMismatch
    case unsupportedDevice
    case deviceDisconnected(String, createdItemID: UInt32?)
    case operationFailed(String, createdItemID: UInt32?)

    var errorDescription: String? {
        switch self {
        case .targetAlreadyExists:
            return "The selected map target already exists on the Garmin device."
        case .remoteFileMissing:
            return "The transferred map was not found on the Garmin device."
        case .objectIdentityMismatch:
            return "The Garmin object identity did not match the intended map."
        case .unsupportedDevice:
            return "This Garmin device is not enabled for the validated map installation path."
        case .deviceDisconnected(let message, _),
             .operationFailed(let message, _):
            return message
        }
    }
}

protocol MapInstallationTransport: Sendable {
    func write(
        sourceURL: URL,
        targetFilename: String,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPWrittenMapObject

    func readBack(
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String
    ) throws -> MTPReadBackMapObject

    /// Performs the write and mandatory read-back verification in one native
    /// transport session when the implementation supports it. The default
    /// keeps test and non-native transports source-compatible.
    func writeAndReadBack(
        sourceURL: URL,
        targetFilename: String,
        targetPath: String,
        progress: @escaping @Sendable (TransferProgress) -> Void,
        onWriteCompleted: @escaping @Sendable () -> Void
    ) throws -> MTPWriteAndReadBackResult

    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws
}

extension MapInstallationTransport {
    func writeAndReadBack(
        sourceURL: URL,
        targetFilename: String,
        targetPath: String,
        progress: @escaping @Sendable (TransferProgress) -> Void,
        onWriteCompleted: @escaping @Sendable () -> Void
    ) throws -> MTPWriteAndReadBackResult {
        let written: MTPWrittenMapObject
        do {
            written = try write(
                sourceURL: sourceURL,
                targetFilename: targetFilename,
                progress: progress
            )
        } catch {
            throw MTPWriteAndReadBackError.write(error)
        }
        onWriteCompleted()

        let readBackObject: MTPReadBackMapObject
        do {
            readBackObject = try readBack(
                targetFilename: targetFilename,
                expectedItemID: written.itemID,
                targetPath: targetPath
            )
        } catch {
            throw MTPWriteAndReadBackError.readBack(
                error,
                createdItemID: written.itemID
            )
        }
        return MTPWriteAndReadBackResult(written: written, readBack: readBackObject)
    }
}

protocol InstallationInventoryReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
}

protocol InstallationDeviceReader: InstallationInventoryReader {
    func readSnapshot() throws -> DeviceSnapshot
}

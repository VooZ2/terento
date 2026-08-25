import Foundation

struct MTPWrittenMapObject: Equatable, Sendable {
    let itemID: UInt32
    let sizeBytes: UInt64
}

struct MTPReadBackMapObject: Equatable, Sendable {
    let itemID: UInt32
    let targetPath: String
    let reportedSizeBytes: UInt64
    let sampledBytes: UInt64
    let sampleCount: Int
    let matchedSampleCount: Int
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
        sourceURL: URL,
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String,
        expectedSizeBytes: UInt64,
        sampleOffsets: [UInt64],
        sampleLength: UInt32,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPReadBackMapObject

    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws
}

protocol InstallationInventoryReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
}

protocol InstallationDeviceReader: InstallationInventoryReader {
    func readSnapshot() throws -> DeviceSnapshot
}

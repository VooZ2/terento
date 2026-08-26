import Foundation
#if canImport(LibMTPBridge)
import LibMTPBridge
#endif
extension MTPTransport: InstallationDeviceReader {}

private final class MTPProgressBox: @unchecked Sendable {
    let callback: @Sendable (TransferProgress) -> Void

    init(callback: @escaping @Sendable (TransferProgress) -> Void) {
        self.callback = callback
    }
}

private func terentoMTPProgressCallback(
    _ sent: UInt64,
    _ total: UInt64,
    _ context: UnsafeRawPointer?
) -> Int32 {
    guard let context else {
        return 0
    }

    let box = Unmanaged<MTPProgressBox>
        .fromOpaque(UnsafeMutableRawPointer(mutating: context))
        .takeUnretainedValue()
    box.callback(TransferProgress(bytesTransferred: sent, totalBytes: total))
    return 0
}

struct MTPMapInstallationTransport: MapInstallationTransport, Sendable {
    private static let errorCapacity = 2048
    private static let targetDirectory = "/GARMIN"
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

    func write(
        sourceURL: URL,
        targetFilename: String,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPWrittenMapObject {
        try operationGate.withOperation(
            kind: .install,
            lifecycleLease: lifecycleLease
        ) {
            try writeUncoordinated(
                sourceURL: sourceURL,
                targetFilename: targetFilename,
                progress: progress
            )
        }
    }

    private func writeUncoordinated(
        sourceURL: URL,
        targetFilename: String,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPWrittenMapObject {
        guard let operationProfile else {
            throw InstallationTransportError.unsupportedDevice
        }
        var itemID: UInt32 = 0
        var sizeBytes: UInt64 = 0
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
        let progressBox = MTPProgressBox(callback: progress)

        // The C bridge invokes the callback synchronously and does not retain
        // its context. Keep the box alive for the complete C call anyway so
        // this remains safe if the bridge implementation changes later.
        let result: Int32 = withExtendedLifetime(progressBox) {
            withNativeMapOperationProfile(operationProfile) { nativeProfile in
                sourceURL.path.withCString { sourcePath in
                    targetFilename.withCString { filename in
                        errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                            terento_mtp_install_map_file(
                                nativeProfile,
                                sourcePath,
                                filename,
                                &itemID,
                                &sizeBytes,
                                terentoMTPProgressCallback,
                                UnsafeRawPointer(Unmanaged.passUnretained(progressBox).toOpaque()),
                                errorPointer.baseAddress,
                                errorPointer.count
                            )
                        }
                    }
                }
            }
        }

        guard result == 0 else {
            throw Self.mapError(
                result: result,
                message: errorMessage(from: errorBuffer),
                createdItemID: itemID == 0 ? nil : itemID
            )
        }

        guard itemID != 0 else {
            throw InstallationTransportError.operationFailed(
                "The Garmin device did not return a safe object identity.",
                createdItemID: nil
            )
        }

        return MTPWrittenMapObject(itemID: itemID, sizeBytes: sizeBytes)
    }

    func readBack(
        sourceURL: URL,
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String,
        expectedSizeBytes: UInt64,
        sampleOffsets: [UInt64],
        sampleLength: UInt32,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPReadBackMapObject {
        try operationGate.withOperation(
            kind: .install,
            lifecycleLease: lifecycleLease
        ) {
            try readBackUncoordinated(
                sourceURL: sourceURL,
                targetFilename: targetFilename,
                expectedItemID: expectedItemID,
                targetPath: targetPath,
                expectedSizeBytes: expectedSizeBytes,
                sampleOffsets: sampleOffsets,
                sampleLength: sampleLength,
                progress: progress
            )
        }
    }

    private func readBackUncoordinated(
        sourceURL: URL,
        targetFilename: String,
        expectedItemID: UInt32,
        targetPath: String,
        expectedSizeBytes: UInt64,
        sampleOffsets: [UInt64],
        sampleLength: UInt32,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPReadBackMapObject {
        guard let operationProfile else {
            throw InstallationTransportError.unsupportedDevice
        }
        guard targetPath == "\(Self.targetDirectory)/\(targetFilename)" else {
            throw InstallationTransportError.operationFailed(
                "The managed map target path is invalid.",
                createdItemID: nil
            )
        }

        var sampledBytes: UInt64 = 0
        var matchedSamples: UInt32 = 0
        let requestedSampleCount = sampleOffsets.count
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
        let progressBox = MTPProgressBox(callback: progress)

        let result: Int32 = withExtendedLifetime(progressBox) {
            withNativeMapOperationProfile(operationProfile) { nativeProfile in
                sampleOffsets.withUnsafeBufferPointer { offsetsBuffer in
                    sourceURL.path.withCString { sourcePath in
                        targetFilename.withCString { filename in
                            errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                                terento_mtp_verify_managed_map_samples(
                                    nativeProfile,
                                    sourcePath,
                                    filename,
                                    expectedItemID,
                                    expectedSizeBytes,
                                    offsetsBuffer.baseAddress,
                                    offsetsBuffer.count,
                                    sampleLength,
                                    &sampledBytes,
                                    &matchedSamples,
                                    terentoMTPProgressCallback,
                                    UnsafeRawPointer(Unmanaged.passUnretained(progressBox).toOpaque()),
                                    errorPointer.baseAddress,
                                    errorPointer.count
                                )
                            }
                        }
                    }
                }
            }
        }

        guard result == 0 else {
            throw Self.mapError(
                result: result,
                message: errorMessage(from: errorBuffer)
            )
        }

        return MTPReadBackMapObject(
            itemID: expectedItemID,
            targetPath: targetPath,
            reportedSizeBytes: expectedSizeBytes,
            sampledBytes: sampledBytes,
            sampleCount: requestedSampleCount,
            matchedSampleCount: Int(matchedSamples)
        )
    }

    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws {
        try deleteExact(
            targetFilename: targetFilename,
            expectedItemID: expectedItemID,
            expectedSizeBytes: nil
        )
    }

    func deleteExact(
        targetFilename: String,
        expectedItemID: UInt32,
        expectedSizeBytes: UInt64?
    ) throws {
        try operationGate.withOperation(
            kind: .remove,
            lifecycleLease: lifecycleLease
        ) {
            try deleteExactUncoordinated(
                targetFilename: targetFilename,
                expectedItemID: expectedItemID,
                expectedSizeBytes: expectedSizeBytes
            )
        }
    }

    private func deleteExactUncoordinated(
        targetFilename: String,
        expectedItemID: UInt32,
        expectedSizeBytes: UInt64?
    ) throws {
        guard let operationProfile else {
            throw InstallationTransportError.unsupportedDevice
        }
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
        let result = withNativeMapOperationProfile(operationProfile) { nativeProfile in
            targetFilename.withCString { filename in
                errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                    terento_mtp_delete_managed_map(
                        nativeProfile,
                        filename,
                        expectedItemID,
                        expectedSizeBytes ?? 0,
                        errorPointer.baseAddress,
                        errorPointer.count
                    )
                }
            }
        }

        guard result == 0 else {
            throw Self.mapError(result: result, message: errorMessage(from: errorBuffer))
        }
    }

    private static func mapError(
        result: Int32,
        message: String,
        createdItemID: UInt32? = nil
    ) -> InstallationTransportError {
        switch result {
        case Int32(TERENTO_MTP_MAP_TARGET_EXISTS):
            return .targetAlreadyExists
        case Int32(TERENTO_MTP_MAP_REMOTE_FILE_MISSING):
            return .remoteFileMissing
        case Int32(TERENTO_MTP_MAP_OBJECT_ID_MISMATCH):
            return .objectIdentityMismatch
        case Int32(TERENTO_MTP_MAP_UNSUPPORTED_DEVICE):
            return .unsupportedDevice
        case Int32(TERENTO_MTP_MAP_IDENTITY_MISMATCH):
            return .liveIdentityMismatch
        default:
            let readable = message.isEmpty ? "The native MTP map operation failed." : message
            if readable.localizedCaseInsensitiveContains("disconnect")
                || readable.localizedCaseInsensitiveContains("no such file") {
                return .deviceDisconnected(readable, createdItemID: createdItemID)
            }
            return .operationFailed(readable, createdItemID: createdItemID)
        }
    }

    private func errorMessage(from buffer: [CChar]) -> String {
        buffer.withUnsafeBufferPointer { buffer in
            let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
            return String(decoding: bytes, as: UTF8.self)
        }
    }
}

extension MapInstallationCoordinator {
    static func live(
        operationProfile: DeviceMapOperationProfile? = nil,
        manifestStore: any TerentoManifestStore = LocalTerentoManifestStore(),
        recoveryStore: any TerentoFailedInstallRecoveryStore = LocalTerentoFailedInstallRecoveryStore(),
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) -> MapInstallationCoordinator {
        MapInstallationCoordinator(
            transport: MTPMapInstallationTransport(
                operationProfile: operationProfile,
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ),
            deviceReader: MTPTransport(
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ),
            manifestStore: manifestStore,
            recoveryStore: recoveryStore
        )
    }
}

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
    private let mutationPurpose: MapMutationPurpose
    private let mutationOperation: NativeMutationOperation

    init(
        operationProfile: DeviceMapOperationProfile? = nil,
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil,
        mutationPurpose: MapMutationPurpose = .install
    ) {
        self.operationProfile = operationProfile
        self.mutationPurpose = mutationPurpose
        self.mutationOperation = NativeMutationOperation(mode: mutationPurpose)
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
        let validatedSourceSize: UInt64? = {
            guard let attributes = try? FileManager.default.attributesOfItem(atPath: sourceURL.path),
                  let fileSize = attributes[.size] as? NSNumber else {
                return nil
            }
            return fileSize.uint64Value
        }()
        let progressBox = MTPProgressBox { transfer in
            guard let validatedSourceSize, validatedSourceSize > 0 else {
                progress(transfer)
                return
            }

            // libmtp progress callbacks are not consistent across all
            // Garmin firmware versions. Keep the UI and diagnostics tied to
            // the validated source artifact, never to an invalid callback
            // total or a value beyond the file being transferred.
            progress(TransferProgress(
                bytesTransferred: min(transfer.bytesTransferred, validatedSourceSize),
                totalBytes: validatedSourceSize,
                bytesPerSecond: transfer.bytesPerSecond
            ))
        }

        // The C bridge invokes the callback synchronously and does not retain
        // its context. Keep the box alive for the complete C call anyway so
        // this remains safe if the bridge implementation changes later.
        let result: Int32 = try withExtendedLifetime(progressBox) {
            try withNativeMapOperationProfile(operationProfile) { nativeProfile in
                try sourceURL.path.withCString { sourcePath in
                    try targetFilename.withCString { filename in
                        try errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                            try authorizedMutation(purpose: mutationPurpose, filename: targetFilename,
                                size: validatedSourceSize ?? 0, sha256: nil) { authorization, record in
                            terento_mtp_install_map_file_authorized(
                                nativeProfile, authorization, record,
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
        var lastError: Error?
        let verificationDeadline = ProcessInfo.processInfo.systemUptime + 600
        // Only the parent may retry a completed metadata lookup. Transport failures
        // require reconnect, never another nested reset/open sequence.
        let retryDelays: [TimeInterval] = MTPFinishingWorker.isWorker ? [0] : [0, 1.0]
        for (attempt, delay) in retryDelays.enumerated() {
            FinishingTrace.event("readback_attempt", "worker=\(MTPFinishingWorker.isWorker) attempt=\(attempt + 1) delay=\(delay)")
            if attempt > 0 {
                Thread.sleep(forTimeInterval: delay)
            }

            let remaining = verificationDeadline - ProcessInfo.processInfo.systemUptime
            guard remaining > 0 else {
                throw InstallationTransportError.operationFailed("Map verification exceeded its total time budget.", createdItemID: nil)
            }
            do {
                return try operationGate.withOperation(
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
                        remainingTime: remaining,
                        progress: progress
                    )
                }
            } catch {
                FinishingTrace.event("readback_failed", "worker=\(MTPFinishingWorker.isWorker) attempt=\(attempt + 1) error=\(Self.traceError(error))")
                lastError = error
                guard Self.shouldRetryReadBack(error), attempt < retryDelays.count - 1 else {
                    throw error
                }
            }
        }

        throw lastError ?? InstallationTransportError.operationFailed(
            "The Garmin map could not be read back after verification retries.",
            createdItemID: nil
        )
    }

    fileprivate static func traceError(_ error: Error) -> String {
        guard let error = error as? InstallationTransportError else { return "other" }
        switch error {
        case .contextual:
            return error.isConfirmedDeviceDisconnected ? "deviceDisconnected" : "operationFailed"
        case .deviceDisconnected: return "deviceDisconnected"
        case .operationFailed: return "operationFailed"
        case .remoteFileMissing: return "remoteFileMissing"
        case .objectIdentityMismatch: return "objectIdentityMismatch"
        case .targetAlreadyExists: return "targetAlreadyExists"
        case .unsupportedDevice: return "unsupportedDevice"
        case .liveIdentityMismatch: return "liveIdentityMismatch"
        }
    }

    private static func shouldRetryReadBack(_ error: Error) -> Bool {
        guard let error = error as? InstallationTransportError else { return false }
        switch error {
        case .remoteFileMissing, .objectIdentityMismatch:
            return true
        case .contextual, .deviceDisconnected, .operationFailed, .targetAlreadyExists, .unsupportedDevice, .liveIdentityMismatch:
            return false
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
        remainingTime: TimeInterval,
        progress: @escaping @Sendable (TransferProgress) -> Void
    ) throws -> MTPReadBackMapObject {
        guard let operationProfile else {
            throw InstallationTransportError.unsupportedDevice
        }
        if !MTPFinishingWorker.isWorker {
            let response = try MTPFinishingWorker.perform(.init(
                operation: .samples, profile: operationProfile, sourceURL: sourceURL,
                filename: targetFilename, itemID: expectedItemID, size: expectedSizeBytes,
                offsets: sampleOffsets, length: sampleLength
            ), progress: progress, sampleTimeout: remainingTime)
            guard let object = response.object, object.targetPath == targetPath else {
                throw InstallationTransportError.objectIdentityMismatch
            }
            progress(TransferProgress(bytesTransferred: object.sampledBytes, totalBytes: object.sampledBytes))
            return object
        }
        guard targetPath == "\(Self.targetDirectory)/\(targetFilename)" else {
            throw InstallationTransportError.operationFailed(
                "The managed map target path is invalid.",
                createdItemID: nil
            )
        }

        var sampledBytes: UInt64 = 0
        var matchedSamples: UInt32 = 0
        var resolvedItemID: UInt32 = 0
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
                                    &resolvedItemID,
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

        guard resolvedItemID != 0 else {
            throw InstallationTransportError.objectIdentityMismatch
        }

        return MTPReadBackMapObject(
            itemID: resolvedItemID,
            targetPath: targetPath,
            reportedSizeBytes: expectedSizeBytes,
            sampledBytes: sampledBytes,
            sampleCount: requestedSampleCount,
            matchedSampleCount: Int(matchedSamples)
        )
    }

    /// Upload sessions have ended by this point. Neither a historical handle nor
    /// filename/size proves creation provenance, so automatic cleanup cannot delete.
    func deleteExact(targetFilename: String, expectedItemID: UInt32) throws {
        throw CleanupIdentityUnproven()
    }

    func deleteExact(targetFilename: String, expectedItemID: UInt32, expectedSizeBytes: UInt64?) throws {
        try deleteExact(targetFilename: targetFilename, expectedItemID: expectedItemID)
    }

    func deleteAuthorized(targetFilename: String, expectedItemID: UInt32,
                          expectedSizeBytes: UInt64, expectedSHA256: String,
                          purpose: MapMutationPurpose) throws {
        guard [.removeManaged, .removeExternal, .updateOld].contains(purpose),
              expectedSHA256.count == 64, expectedSHA256.allSatisfy({ $0.isHexDigit }),
              expectedSHA256 != String(repeating: "0", count: 64) else {
            throw InstallationTransportError.operationFailed("Removal evidence is incomplete. Nothing was removed.", createdItemID: nil)
        }
        try operationGate.withOperation(kind: .remove, lifecycleLease: lifecycleLease) {
            guard let operationProfile else { throw InstallationTransportError.unsupportedDevice }
            var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
            let result = try withNativeMapOperationProfile(operationProfile) { nativeProfile in
                try targetFilename.withCString { filename in
                    try errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                        try authorizedMutation(purpose: purpose, filename: targetFilename,
                            size: expectedSizeBytes, sha256: expectedSHA256) { authorization, record in
                            if purpose == .removeExternal {
                                return terento_mtp_delete_external_map_authorized(nativeProfile, authorization, record,
                                    filename, expectedItemID, expectedSizeBytes, errorPointer.baseAddress, errorPointer.count)
                            }
                            return terento_mtp_delete_managed_map_authorized(nativeProfile, authorization, record,
                                filename, expectedItemID, expectedSizeBytes, errorPointer.baseAddress, errorPointer.count)
                        }
                    }
                }
            }
            guard result == 0 else { throw Self.mapError(result: result, message: errorMessage(from: errorBuffer)) }
        }
    }

    func bindUpdateOldTarget(filename: String, size: UInt64, sha256: String) throws {
        try mutationOperation.bindOldTarget(scope: mutationScope(filename: filename, size: size, sha256: sha256))
    }

    func markUpdateVerified(filename: String, size: UInt64, sha256: String) throws {
        try mutationOperation.markUpdateVerified(filename: filename, size: size, sha256: sha256)
    }

    private func mutationScope(filename: String, size: UInt64, sha256: String?) throws -> NativeMutationLedger.Scope {
        guard let profile = operationProfile else { throw InstallationTransportError.unsupportedDevice }
        return NativeMutationLedger.Scope(physicalIdentifierSource: profile.physicalIdentifierSource,
            physicalIdentifier: profile.physicalIdentifier, expectedStorageID: profile.expectedStorageID,
            filename: filename, size: size, sha256: sha256)
    }

    private func authorizedMutation(purpose: MapMutationPurpose, filename: String,
                                    size: UInt64, sha256: String?,
                                    body: (UnsafePointer<TerentoMTPMutationAuthorization>,
                                           UnsafeMutablePointer<TerentoMTPMutationRecord>) -> Int32) throws -> Int32 {
        var ledger = try mutationOperation.begin(purpose: purpose,
            scope: mutationScope(filename: filename, size: size, sha256: sha256))
        try ledger.dispatch()
        var record = TerentoMTPMutationRecord()
        guard let profile = operationProfile else { throw InstallationTransportError.unsupportedDevice }
        let result = ledger.operationID.withCString { operationID in
            ledger.claimPath.withCString { claimPath in
                filename.withCString { filenamePointer in
                    (sha256 ?? "").withCString { hashPointer in
                        profile.physicalIdentifier.withCString { physicalIdentifier in
                            profile.targetDirectory.withCString { targetDirectory in
                                var authorization = TerentoMTPMutationAuthorization()
                                authorization.version = 1
                                authorization.operation_id = operationID
                                authorization.claim_path = claimPath
                                authorization.sequence = ledger.sequence
                                authorization.purpose = purpose.rawValue
                                authorization.mutation_kind = purpose.kind
                                authorization.expected_filename = filenamePointer
                                authorization.expected_size = size
                                authorization.expected_sha256 = hashPointer
                                authorization.expected_physical_identifier = physicalIdentifier
                                authorization.expected_physical_identifier_source = profile.physicalIdentifierSource
                                authorization.expected_storage_id = profile.expectedStorageID
                                authorization.expected_target_directory = targetDirectory
                                return withUnsafePointer(to: &authorization) { body($0, &record) }
                            }
                        }
                    }
                }
            }
        }
        try ledger.finish(.init(authorized: record.authorized != 0, attempted: record.attempted != 0,
            completed: record.completed != 0, nativeResult: record.native_result,
            resultingObjectID: record.resulting_object_id, sessionID: record.session_id,
            sequence: record.sequence, purpose: record.purpose, kind: record.mutation_kind), returnedResult: result)
        return result
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
            deviceReader: BoundedInstallationDeviceReader(
                operationGate: operationGate,
                lifecycleLease: lifecycleLease
            ),
            manifestStore: manifestStore,
            recoveryStore: recoveryStore,
            diagnostic: { event, details in FinishingTrace.event(event, details) }
        )
    }
}

/// IPC is local to a fresh private temporary directory. It never contains
/// raw XML, manifests or map bytes. Physical binding remains private local IPC.
/// No worker can upload maps; legacy cleanup requests fail closed.
enum MTPFinishingWorker {
    enum Operation: String, Codable { case samples, cleanup, inventory, snapshot }
    private static let inventoryTimeout: TimeInterval = 60

    static func failure(
        for operation: Operation, kind: InstallationFailureContext.ResultKind,
        native: InstallationFailureContext? = nil
    ) -> InstallationTransportError {
        let boundary: InstallationFailureContext.Boundary
        let contextOperation: InstallationFailureContext.Operation
        switch operation {
        case .samples: boundary = .readback; contextOperation = .readback
        case .cleanup: boundary = .cleanup; contextOperation = .cleanup
        case .inventory: boundary = .prewriteInventory; contextOperation = .inventory
        case .snapshot: boundary = .postwriteSnapshot; contextOperation = .snapshot
        }
        let context = InstallationFailureContext(boundary: boundary,
            classificationSource: native?.classificationSource ?? .derived,
            devicePresence: native?.devicePresence ?? .unknown, operation: contextOperation,
            executionMode: .worker, resultKind: kind, nativeCategory: native?.nativeCategory,
            nativeCodeNamespace: native?.nativeCodeNamespace, nativeResultCode: native?.nativeResultCode)
        return .contextual(failure: context.devicePresence == .absent ? .deviceDisconnected : .operationFailed,
            message: "The device operation could not be completed.", createdItemID: nil, context: context)
    }

    private static func timeout(
        for operation: Operation,
        sampleTimeout: TimeInterval
    ) -> TimeInterval {
        switch operation {
        case .samples:
            return min(600, sampleTimeout)
        case .inventory:
            // libmtp's LONG_TIMEOUT is 60 seconds per native USB operation.
            // Keep the worker bound finite; do not turn this into an unbounded
            // wait or alter any device-specific USB flags.
            return inventoryTimeout
        case .cleanup, .snapshot:
            return 45
        }
    }

    struct Request: Codable {
        var operation: Operation
        var profile: DeviceMapOperationProfile? = nil
        var sourceURL: URL? = nil
        var filename: String? = nil
        var itemID: UInt32? = nil
        var size: UInt64? = nil
        var offsets: [UInt64]? = nil
        var length: UInt32? = nil
    }
    struct Response: Codable {
        var object: MTPReadBackMapObject? = nil
        var files: [DeviceFile]? = nil
        var snapshot: DeviceSnapshot? = nil
        var error: InstallationTransportError? = nil
    }

    static func decodeResponse(_ data: Data, operation: Operation) throws -> Response {
        let response: Response
        do { response = try JSONDecoder().decode(Response.self, from: data) }
        catch { throw failure(for: operation, kind: .decodeError) }
        if response.error == nil {
            let valid: Bool
            switch operation {
            case .inventory: valid = response.files != nil
            case .snapshot: valid = response.snapshot != nil
            case .samples: valid = response.object != nil
            case .cleanup: valid = true
            }
            guard valid else { throw failure(for: operation, kind: .invalidResponse) }
        }
        return response
    }
    static var isWorker: Bool { CommandLine.arguments.dropFirst().first == "--terento-finishing-worker" }

    static func perform(_ request: Request, progress: (@Sendable (TransferProgress) -> Void)? = nil, sampleTimeout: TimeInterval = 600) throws -> Response {
        guard let executable = Bundle.main.executableURL else {
            throw failure(for: request.operation, kind: .processLaunchError)
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false,
                                                   attributes: [.posixPermissions: 0o700])
        } catch { throw failure(for: request.operation, kind: .requestIOError) }
        defer { try? FileManager.default.removeItem(at: directory) }
        let operationStarted = ProcessInfo.processInfo.systemUptime
        let output = directory.appendingPathComponent("result.json")
        FinishingTrace.event("operation_begin", "operation=\(request.operation.rawValue) trace=\(directory.lastPathComponent)")
        let progressURL = directory.appendingPathComponent("progress.json")
        var lastProgress: [UInt64] = []
        var verifiedBytes: UInt64?
        var progressTotal: UInt64?
        let traceURL = directory.appendingPathComponent("finishing.trace")
        do {
            defer { FinishingTrace.captureWorker(traceURL) }
            try BoundedNativeProcess.run(executable: executable,
                arguments: ["--terento-finishing-worker", output.path],
                input: JSONEncoder().encode(request),
                timeout: Self.timeout(for: request.operation, sampleTimeout: sampleTimeout),
                inactivityTimeout: request.operation == .samples ? 120 : nil,
                verifiedProgress: { verifiedBytes },
                diagnosticFile: traceURL,
                onPoll: {
                    guard request.operation == .samples,
                          let data = try? Data(contentsOf: progressURL),
                          let values = try? JSONDecoder().decode([UInt64].self, from: data),
                          values.count == 2, values[1] > 0, values[0] <= values[1],
                          let length = request.length, let offsets = request.offsets,
                          values[1] <= UInt64(length) * UInt64(offsets.count),
                          progressTotal == nil || progressTotal == values[1],
                          values[0] > (verifiedBytes ?? 0),
                          values != lastProgress else { return }
                    progressTotal = values[1]
                    verifiedBytes = values[0]
                    lastProgress = values
                    progress?(TransferProgress(bytesTransferred: values[0], totalBytes: values[1]))
                },
                // Cleanup is a separate bounded safety operation even if the
                // enclosing install was cancelled. Never cancel it immediately.
                cancelled: { request.operation != .cleanup && Task<Never, Never>.isCancelled })
        } catch {
            FinishingTrace.event("operation_worker_failed", "operation=\(request.operation.rawValue) elapsed=\(ProcessInfo.processInfo.systemUptime - operationStarted) trace=\(directory.lastPathComponent)")
            let kind: InstallationFailureContext.ResultKind
            switch error as? NativeProcessFailure {
            case .timeout: kind = .timeout
            case .cancelled: kind = .cancelled
            case .launchFailed: kind = .processLaunchError
            case .requestIOFailed: kind = .requestIOError
            case .processExit: kind = .processExit
            default: kind = .appError
            }
            throw failure(for: request.operation, kind: kind)
        }
        let data: Data
        do { data = try Data(contentsOf: output) }
        catch { throw failure(for: request.operation, kind: .responseIOError) }
        let response = try decodeResponse(data, operation: request.operation)
        if let error = response.error {
            FinishingTrace.event("operation_failed", "operation=\(request.operation.rawValue) elapsed=\(ProcessInfo.processInfo.systemUptime - operationStarted) error=\(MTPMapInstallationTransport.traceError(error)) trace=\(directory.lastPathComponent)")
            throw error
        }
        FinishingTrace.event("operation_complete", "operation=\(request.operation.rawValue) elapsed=\(ProcessInfo.processInfo.systemUptime - operationStarted) trace=\(directory.lastPathComponent)")
        return response
    }

    static func runIfRequested() -> Bool {
        guard isWorker else { return false }
        guard CommandLine.arguments.count == 3 else { return true }
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        var response = Response()
        var operation: Operation?
        do {
            let input = try FileHandle.standardInput.read(upToCount: 8193) ?? Data()
            guard input.count <= 8192 else { throw NativeProcessFailure.failed }
            let request = try JSONDecoder().decode(Request.self, from: input)
            operation = request.operation
            FinishingTrace.event("worker_operation_begin", "operation=\(request.operation.rawValue) trace=\(output.deletingLastPathComponent().lastPathComponent)")
            let transport = MTPMapInstallationTransport(operationProfile: request.profile)
            switch request.operation {
            case .samples:
                guard let source = request.sourceURL, let filename = request.filename,
                      let itemID = request.itemID, let size = request.size,
                      let offsets = request.offsets, let length = request.length else {
                    throw NativeProcessFailure.failed
                }
                response.object = try transport.readBack(sourceURL: source, targetFilename: filename,
                    expectedItemID: itemID, targetPath: "/GARMIN/\(filename)", expectedSizeBytes: size,
                    sampleOffsets: offsets, sampleLength: length,
                    progress: SampleProgressWriter(url: output.deletingLastPathComponent()
                        .appendingPathComponent("progress.json")).report)
            case .cleanup:
                guard let filename = request.filename, let itemID = request.itemID else {
                    throw NativeProcessFailure.failed
                }
                try transport.deleteExact(targetFilename: filename, expectedItemID: itemID, expectedSizeBytes: request.size)
            case .inventory:
                response.files = try MTPTransport().readFileInventory()
            case .snapshot:
                let snapshot = try MTPTransport().readSnapshot()
                response.snapshot = DeviceSnapshot(manufacturer: snapshot.manufacturer, model: snapshot.model,
                    deviceVersion: snapshot.deviceVersion, vendorID: snapshot.vendorID, productID: snapshot.productID,
                    storages: snapshot.storages)
            }
        } catch let error as InstallationTransportError {
            FinishingTrace.event("worker_operation_failed", "error=\(MTPMapInstallationTransport.traceError(error))")
            response.error = error
        } catch let error as MTPTransportError {
            if let operation {
                response.error = failure(for: operation, kind: .nativeError, native: error.failureContext)
            } else {
                response.error = .operationFailed("Native finishing operation failed.", createdItemID: nil)
            }
        } catch {
            response.error = .operationFailed("Native finishing operation failed.", createdItemID: nil)
        }
        try? JSONEncoder().encode(response).write(to: output, options: .atomic)
        return true
    }
}

private struct BoundedInstallationDeviceReader: InstallationDeviceReader {
    let operationGate: MTPOperationGate
    let lifecycleLease: MTPOperationLease?
    func readFileInventory() throws -> [DeviceFile] {
        try operationGate.withOperation(kind: .inventory, lifecycleLease: lifecycleLease) {
            guard let files = try MTPFinishingWorker.perform(.init(operation: .inventory)).files else {
                throw MTPFinishingWorker.failure(for: .inventory, kind: .invalidResponse)
            }
            return files
        }
    }
    func readSnapshot() throws -> DeviceSnapshot {
        try operationGate.withOperation(kind: .inventory, lifecycleLease: lifecycleLease) {
            guard let snapshot = try MTPFinishingWorker.perform(.init(operation: .snapshot)).snapshot else {
                throw MTPFinishingWorker.failure(for: .snapshot, kind: .invalidResponse)
            }
            return snapshot
        }
    }
}

/// Local progress only; throttled independently of USB reads and never fatal.
private final class SampleProgressWriter: @unchecked Sendable {
    let url: URL
    private let lock = NSLock()
    private var lastWrite: TimeInterval = -.infinity
    init(url: URL) { self.url = url }
    func report(_ progress: TransferProgress) {
        lock.lock()
        defer { lock.unlock() }
        let now = ProcessInfo.processInfo.systemUptime
        guard now - lastWrite >= 0.25 || progress.bytesTransferred == progress.totalBytes else { return }
        lastWrite = now
        if let data = try? JSONEncoder().encode([progress.bytesTransferred, progress.totalBytes]) {
            try? data.write(to: url, options: .atomic)
        }
    }
}

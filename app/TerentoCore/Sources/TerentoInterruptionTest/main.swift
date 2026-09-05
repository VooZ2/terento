import Foundation
import LibMTPBridge

private let sourceFilename = "terento-interrupt-test.bin"
private let sourceSizeBytes = 16 * 1024 * 1024
private let interruptAfterPercent: UInt8 = 50

private enum TestMode: String {
    case controlled
    case physical
}

private enum InterruptionTestError: LocalizedError {
    case invalidArguments
    case transferFailed(String)
    case inspectionFailed(String)
    case cleanupFailed(String)
    case manualReview(String)

    var errorDescription: String? {
        switch self {
        case .invalidArguments:
            return "Usage: swift run TerentoInterruptionTest --mode physical|controlled"
        case .transferFailed(let message),
             .inspectionFailed(let message),
             .cleanupFailed(let message),
             .manualReview(let message):
            return message
        }
    }
}

private struct TransferAttempt {
    let resultCode: Int32
    let itemID: UInt32
    let sizeBytes: UInt64
    let transferWasCancelled: Bool
    let errorMessage: String
}

private struct TestObjectInspection {
    let itemID: UInt32
    let sizeBytes: UInt64
    let matchCount: Int
}

private struct InterruptionTransport {
    private static let errorCapacity = 1024

    func transfer(sourceURL: URL, mode: TestMode) -> TransferAttempt {
        var itemID: UInt32 = 0
        var sizeBytes: UInt64 = 0
        var transferWasCancelled: UInt8 = 0
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let resultCode = sourceURL.path.withCString { sourcePath in
            errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                terento_mtp_interrupt_test_file(
                    sourcePath,
                    interruptAfterPercent,
                    mode == .physical ? 1 : 0,
                    &itemID,
                    &sizeBytes,
                    &transferWasCancelled,
                    errorPointer.baseAddress,
                    errorPointer.count
                )
            }
        }

        return TransferAttempt(
            resultCode: resultCode,
            itemID: itemID,
            sizeBytes: sizeBytes,
            transferWasCancelled: transferWasCancelled != 0,
            errorMessage: Self.errorMessage(from: errorBuffer)
        )
    }

    func inspect() -> Result<TestObjectInspection, InterruptionTestError> {
        var itemID: UInt32 = 0
        var sizeBytes: UInt64 = 0
        var matchCount = 0
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let resultCode = errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
            terento_mtp_inspect_interrupt_test_file(
                &itemID,
                &sizeBytes,
                &matchCount,
                errorPointer.baseAddress,
                errorPointer.count
            )
        }

        guard resultCode == 0 else {
            return .failure(.inspectionFailed(Self.errorMessage(from: errorBuffer)))
        }

        return .success(
            TestObjectInspection(
                itemID: itemID,
                sizeBytes: sizeBytes,
                matchCount: matchCount
            )
        )
    }

    func delete(itemID: UInt32) -> Result<Void, InterruptionTestError> {
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
        let resultCode = errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
            terento_mtp_delete_interrupt_test_file(
                itemID,
                errorPointer.baseAddress,
                errorPointer.count
            )
        }

        guard resultCode == 0 else {
            return .failure(.cleanupFailed(Self.errorMessage(from: errorBuffer)))
        }

        return .success(())
    }

    private static func errorMessage(from buffer: [CChar]) -> String {
        buffer.withUnsafeBufferPointer { buffer in
            let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
            let message = String(decoding: bytes, as: UTF8.self)
            return message.isEmpty ? "The native MTP operation failed." : message
        }
    }
}

@main
private struct TerentoInterruptionTest {
    static func main() {
        do {
            let mode = try mode(from: CommandLine.arguments)
            try run(mode: mode)
        } catch {
            fputs("Interruption Test failed: \(error.localizedDescription)\n", stderr)
            exit(1)
        }
    }

    private static func run(mode: TestMode) throws {
        let temporaryDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-interruption-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(
            at: temporaryDirectory,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: temporaryDirectory) }

        let sourceURL = temporaryDirectory.appendingPathComponent(sourceFilename)
        try Data(repeating: 0x5A, count: sourceSizeBytes).write(to: sourceURL, options: .atomic)

        print("Interruption Test: mode \(mode.rawValue)")
        print("Interruption Test: generated local payload \(sourceSizeBytes / (1024 * 1024)) MiB")
        print("Interruption Test: target is /GARMIN/\(sourceFilename)")
        print("Interruption Test: no existing target will be overwritten")

        let transport = InterruptionTransport()
        let attempt = transport.transfer(sourceURL: sourceURL, mode: mode)

        if attempt.resultCode == 0 {
            if attempt.itemID != 0 {
                try cleanupUnexpectedSuccessfulTransfer(
                    transport: transport,
                    itemID: attempt.itemID
                )
            }

            throw InterruptionTestError.transferFailed(
                "The transfer completed before it was interrupted. No interruption was proven."
            )
        }

        if mode == .physical {
            print("Interruption Test: reconnect the watch, then press Return to inspect cleanup.")
            _ = readLine()
        } else {
            print("Interruption Test: transfer cancellation returned. Press Return to inspect cleanup.")
            _ = readLine()
        }

        let interruptedObject = try inspectAfterReconnect(transport: transport)
        guard interruptedObject.matchCount > 0 else {
            print("Interruption Test: PASS — no test object remained after the interrupted transfer")
            print("Interruption Test: existing device files were not targeted")
            return
        }

        guard interruptedObject.matchCount == 1 else {
            throw InterruptionTestError.manualReview(
                "More than one interruption-test object was found. No object was deleted."
            )
        }

        guard attempt.itemID != 0, interruptedObject.itemID == attempt.itemID else {
            throw InterruptionTestError.manualReview(
                "A test object remained, but its exact creation identity was unavailable. "
                    + "No object was deleted. Stop and inspect the watch before continuing."
            )
        }

        switch transport.delete(itemID: interruptedObject.itemID) {
        case .failure(let error):
            throw error
        case .success:
            break
        }

        let afterCleanup = try inspectAfterReconnect(transport: transport)
        guard afterCleanup.matchCount == 0 else {
            throw InterruptionTestError.cleanupFailed(
                "The exact interruption-test object could not be confirmed removed."
            )
        }

        print("Interruption Test: PASS — exact interrupted test object was removed")
        print("Interruption Test: existing device files were not targeted")
    }

    private static func cleanupUnexpectedSuccessfulTransfer(
        transport: InterruptionTransport,
        itemID: UInt32
    ) throws {
        print("Interruption Test: transfer completed; cleaning up the exact test object")
        switch transport.delete(itemID: itemID) {
        case .failure(let error):
            throw error
        case .success:
            print("Interruption Test: exact test object removed")
        }
    }

    private static func inspection(
        from transport: InterruptionTransport
    ) throws -> TestObjectInspection {
        switch transport.inspect() {
        case .failure(let error):
            throw error
        case .success(let inspection):
            return inspection
        }
    }

    private static func inspectAfterReconnect(
        transport: InterruptionTransport
    ) throws -> TestObjectInspection {
        var lastError: InterruptionTestError?

        for attempt in 1...5 {
            do {
                return try inspection(from: transport)
            } catch let error as InterruptionTestError {
                lastError = error
                if attempt < 5 {
                    print("Interruption Test: watch is not ready yet; retrying (\(attempt)/5)")
                    Thread.sleep(forTimeInterval: 2)
                }
            }
        }

        throw lastError ?? InterruptionTestError.inspectionFailed(
            "The watch could not be inspected after reconnect."
        )
    }

    private static func mode(from arguments: [String]) throws -> TestMode {
        guard arguments.count == 3,
              arguments[1] == "--mode",
              let mode = TestMode(rawValue: arguments[2]) else {
            throw InterruptionTestError.invalidArguments
        }

        return mode
    }
}

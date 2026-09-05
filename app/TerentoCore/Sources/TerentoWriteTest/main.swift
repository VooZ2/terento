import CryptoKit
import Foundation
import LibMTPBridge

private let writeTestFilename = "terento-write-test.txt"
private let maximumSourceBytes: UInt64 = 1024 * 1024
private let expectedMarker = Data("Terento native MTP write test".utf8)

enum WriteTestError: LocalizedError {
    case invalidArguments(String)
    case invalidSource(String)
    case operationFailed(String, createdItemID: UInt32?)
    case verificationFailed(String)
    case cleanupFailed(String)

    var errorDescription: String? {
        switch self {
        case .invalidArguments(let message),
             .invalidSource(let message),
             .operationFailed(let message, _),
             .verificationFailed(let message),
             .cleanupFailed(let message):
            return message
        }
    }
}

struct MTPWriteTestTransport {
    private static let errorCapacity = 1024

    func write(sourceURL: URL) throws -> (itemID: UInt32, sizeBytes: UInt64) {
        var itemID: UInt32 = 0
        var sizeBytes: UInt64 = 0
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let result = sourceURL.path.withCString { sourcePath in
            errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                terento_mtp_write_test_file(
                    sourcePath,
                    &itemID,
                    &sizeBytes,
                    errorPointer.baseAddress,
                    errorPointer.count
                )
            }
        }

        guard result == 0 else {
            throw WriteTestError.operationFailed(
                Self.errorMessage(from: errorBuffer),
                createdItemID: itemID == 0 ? nil : itemID
            )
        }

        guard itemID != 0 else {
            throw WriteTestError.operationFailed(
                "The Write Test completed without a safe remote object identity.",
                createdItemID: nil
            )
        }

        return (itemID, sizeBytes)
    }

    func readBack(itemID: UInt32, destinationURL: URL) throws -> UInt64 {
        var sizeBytes: UInt64 = 0
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let result = destinationURL.path.withCString { destinationPath in
            errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                terento_mtp_read_test_file_to_local(
                    itemID,
                    destinationPath,
                    &sizeBytes,
                    errorPointer.baseAddress,
                    errorPointer.count
                )
            }
        }

        guard result == 0 else {
            throw WriteTestError.verificationFailed(Self.errorMessage(from: errorBuffer))
        }

        return sizeBytes
    }

    func delete(itemID: UInt32) throws {
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)
        let result = errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
            terento_mtp_delete_test_file(
                itemID,
                errorPointer.baseAddress,
                errorPointer.count
            )
        }

        guard result == 0 else {
            throw WriteTestError.cleanupFailed(Self.errorMessage(from: errorBuffer))
        }
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
struct TerentoWriteTest {
    static func main() {
        if CommandLine.arguments.dropFirst().contains("--help") {
            print("Usage: swift run TerentoWriteTest --source ~/Downloads/terento-write-test.txt")
            print("This sends only the Terento fixed test payload, verifies it, and removes it.")
            exit(0)
        }

        do {
            let sourceURL = try sourceURL(from: CommandLine.arguments)
            try run(sourceURL: sourceURL)
        } catch {
            fputs("Write Test failed: \(error.localizedDescription)\n", stderr)
            exit(1)
        }
    }

    private static func run(sourceURL: URL) throws {
        try validateSource(sourceURL)

        let sourceData = try Data(contentsOf: sourceURL)
        let sourceHash = SHA256.hash(data: sourceData).hexString
        let readBackURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-write-test-readback-\(UUID().uuidString).txt")
        let transport = MTPWriteTestTransport()
        var createdItemID: UInt32?
        var operationError: Error?

        print("Write Test: validated local file \(sourceURL.path)")
        print("Write Test: target is /GARMIN/\(writeTestFilename)")
        print("Write Test: no existing target will be overwritten")

        do {
            let result = try transport.write(sourceURL: sourceURL)
            createdItemID = result.itemID
            print("Write Test: PASS — file sent (\(result.sizeBytes) bytes)")

            let reportedRemoteSize = try transport.readBack(
                itemID: result.itemID,
                destinationURL: readBackURL
            )
            let readBackData = try Data(contentsOf: readBackURL)
            let readBackHash = SHA256.hash(data: readBackData).hexString

            guard UInt64(readBackData.count) == result.sizeBytes,
                  reportedRemoteSize == result.sizeBytes else {
                throw WriteTestError.verificationFailed(
                    "Read-back size does not match the local test file."
                )
            }

            guard readBackHash == sourceHash else {
                throw WriteTestError.verificationFailed(
                    "Read-back SHA-256 does not match the local test file."
                )
            }

            print("Write Test: PASS — read-back size and SHA-256 verified")
        } catch {
            operationError = error
        }

        var cleanupError: Error?
        if let createdItemID {
            do {
                try transport.delete(itemID: createdItemID)
                print("Write Test: PASS — exact test object removed")
            } catch {
                cleanupError = error
                fputs(
                    "Write Test: CLEANUP REQUIRED — /GARMIN/\(writeTestFilename) was not confirmed removed.\n",
                    stderr
                )
            }
        }

        try? FileManager.default.removeItem(at: readBackURL)

        if let operationError {
            if let cleanupError {
                throw WriteTestError.cleanupFailed(
                    "\(operationError.localizedDescription) Cleanup also failed: \(cleanupError.localizedDescription)"
                )
            }
            throw operationError
        }

        if let cleanupError {
            throw cleanupError
        }

        print("Write Test complete: PASS — device write, read-back, hash verification, and cleanup")
    }

    private static func sourceURL(from arguments: [String]) throws -> URL {
        guard arguments.count == 3, arguments[1] == "--source" else {
            throw WriteTestError.invalidArguments(
                "Usage: swift run TerentoWriteTest --source ~/Downloads/terento-write-test.txt"
            )
        }

        return URL(fileURLWithPath: arguments[2], isDirectory: false)
    }

    private static func validateSource(_ url: URL) throws {
        guard url.lastPathComponent == writeTestFilename else {
            throw WriteTestError.invalidSource(
                "Choose the exact test file named \(writeTestFilename). Map files are not accepted."
            )
        }

        let attributes: [FileAttributeKey: Any]
        do {
            attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        } catch {
            throw WriteTestError.invalidSource("The selected test file could not be read.")
        }

        guard let fileType = attributes[.type] as? FileAttributeType,
              fileType == .typeRegular else {
            throw WriteTestError.invalidSource("The Write Test source must be a regular file.")
        }

        guard let fileSize = attributes[.size] as? NSNumber,
              fileSize.uint64Value > 0,
              fileSize.uint64Value <= maximumSourceBytes else {
            throw WriteTestError.invalidSource("The Write Test source must be between 1 byte and 1 MiB.")
        }

        let data = try Data(contentsOf: url)
        guard data.range(of: expectedMarker) != nil else {
            throw WriteTestError.invalidSource(
                "This is not the Terento test payload. No file was sent."
            )
        }
    }
}

private extension SHA256.Digest {
    var hexString: String {
        map { String(format: "%02x", $0) }.joined()
    }
}

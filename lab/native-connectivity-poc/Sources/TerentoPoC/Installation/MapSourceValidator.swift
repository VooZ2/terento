import CryptoKit
import Foundation

struct ValidatedMapSource: Equatable, Sendable {
    let url: URL
    let sizeBytes: UInt64
    let sha256: String
    let metadata: GarminIMGMetadata
}

enum MapSourceValidationError: Error, Equatable, Sendable {
    case fileMissing
    case emptyFile
    case readFailed
    case invalidIMG
    case identityMismatch
    case versionMismatch
}

struct MapSourceValidator: Sendable {
    private let parser = GarminIMGMetadataParser()

    func validate(
        fileURL: URL,
        expectedPackage: MapPackage
    ) throws -> ValidatedMapSource {
        guard FileManager.default.isReadableFile(atPath: fileURL.path) else {
            throw MapSourceValidationError.fileMissing
        }

        let handle: FileHandle
        do {
            handle = try FileHandle(forReadingFrom: fileURL)
        } catch {
            throw MapSourceValidationError.readFailed
        }

        defer {
            try? handle.close()
        }

        var prefix: [UInt8] = []
        prefix.reserveCapacity(GarminIMGMetadataParser.prefixLength)
        var hasher = SHA256()
        var sizeBytes: UInt64 = 0

        do {
            while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty {
                if prefix.count < GarminIMGMetadataParser.prefixLength {
                    prefix.append(contentsOf: chunk.prefix(
                        GarminIMGMetadataParser.prefixLength - prefix.count
                    ))
                }

                hasher.update(data: chunk)
                let (newSize, overflow) = sizeBytes.addingReportingOverflow(UInt64(chunk.count))
                guard !overflow else {
                    throw MapSourceValidationError.readFailed
                }
                sizeBytes = newSize
            }
        } catch let error as MapSourceValidationError {
            throw error
        } catch {
            throw MapSourceValidationError.readFailed
        }

        guard sizeBytes > 0 else {
            throw MapSourceValidationError.emptyFile
        }

        guard let metadata = parser.parse(prefix) else {
            throw MapSourceValidationError.invalidIMG
        }

        guard let actualIdentity = MapIdentity(
            provider: metadata.provider,
            region: metadata.region
        ), let expectedIdentity = expectedPackage.identity,
        actualIdentity == expectedIdentity else {
            throw MapSourceValidationError.identityMismatch
        }

        guard metadata.version == expectedPackage.version else {
            throw MapSourceValidationError.versionMismatch
        }

        return ValidatedMapSource(
            url: fileURL,
            sizeBytes: sizeBytes,
            sha256: digestString(hasher.finalize()),
            metadata: metadata
        )
    }

    private func digestString(_ digest: SHA256.Digest) -> String {
        digest.map { String(format: "%02x", $0) }.joined()
    }
}

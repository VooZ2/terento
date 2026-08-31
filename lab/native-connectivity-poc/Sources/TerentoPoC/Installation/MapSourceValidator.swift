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

    /// Validates a user-supplied image without requiring provider, region, or
    /// release metadata. A Garmin IMG header is the strongest format signal
    /// available without executing or fully interpreting the map contents;
    /// provenance and malware safety cannot be proven from an IMG alone.
    func validateCustom(fileURL: URL) throws -> ValidatedMapSource {
        let inspected = try inspect(fileURL: fileURL)
        guard let metadata = parser.parse(
            inspected.prefix,
            filename: fileURL.lastPathComponent
        ) else {
            throw MapSourceValidationError.invalidIMG
        }
        return ValidatedMapSource(
            url: fileURL,
            sizeBytes: inspected.sizeBytes,
            sha256: inspected.sha256,
            metadata: metadata
        )
    }

    func validate(
        fileURL: URL,
        expectedPackage: MapPackage
    ) throws -> ValidatedMapSource {
        let inspected = try inspect(fileURL: fileURL)

        guard let metadata = parser.parse(
            inspected.prefix,
            filename: fileURL.lastPathComponent
        ) else {
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
            sizeBytes: inspected.sizeBytes,
            sha256: inspected.sha256,
            metadata: metadata
        )
    }

    private func inspect(fileURL: URL) throws -> (prefix: [UInt8], sizeBytes: UInt64, sha256: String) {
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

        return (
            prefix: prefix,
            sizeBytes: sizeBytes,
            sha256: digestString(hasher.finalize())
        )
    }

    private func digestString(_ digest: SHA256.Digest) -> String {
        digest.map { String(format: "%02x", $0) }.joined()
    }
}

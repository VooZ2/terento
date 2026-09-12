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
        if MapIdentity.normalizeProvider(expectedPackage.providerId) == "bbbike" {
            return try validateBBBike(fileURL: fileURL, expectedPackage: expectedPackage, inspected: inspected)
        }

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
        MapIdentityMatcher.matches(
            actual: actualIdentity,
            expected: expectedIdentity,
            providerRegionId: expectedPackage.providerRegionId,
            identifier: expectedPackage.identifier
        ) else {
            throw MapSourceValidationError.identityMismatch
        }

        let isContourArtifact = expectedPackage.artifacts.count == 1
            && expectedPackage.artifacts.first?.kind == .contours
        guard metadata.version == expectedPackage.version
            || (isContourArtifact && metadata.version == nil) else {
            throw MapSourceValidationError.versionMismatch
        }

        return ValidatedMapSource(
            url: fileURL,
            sizeBytes: inspected.sizeBytes,
            sha256: inspected.sha256,
            metadata: metadata
        )
    }

    private func validateBBBike(fileURL: URL, expectedPackage package: MapPackage,
        inspected: (prefix: [UInt8], sizeBytes: UInt64, sha256: String, md5: String)) throws -> ValidatedMapSource {
        guard BBBikeProviderAdapter().expectedIMGIdentity(for: package) != nil,
              let proof = package.mainArtifact?.sourceProof,
              let context = BBBikeMapMetadata(package: package),
              inspected.sizeBytes == proof.installSizeBytes,
              inspected.md5 == proof.payloadMD5,
              let metadata = BBBikeIMGMetadata.metadata(inspected.prefix, context: context, version: package.version) else {
            throw MapSourceValidationError.identityMismatch
        }
        // The original provider notices remain alongside IMG until terminal cleanup.
        // Never execute the bundled BaseCamp script.
        let directory = fileURL.deletingLastPathComponent()
        func boundedText(_ name: String) throws -> String {
            let url = directory.appendingPathComponent(name)
            let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true,
                  let size = values.fileSize, size > 0, size <= 65536 else { throw MapSourceValidationError.identityMismatch }
            return try String(contentsOf: url, encoding: .utf8)
        }
        let readme = try boundedText("README.txt")
        let checksum = try boundedText("CHECKSUM.txt")
        func field(_ prefix: String) -> String? {
            let matches = readme.components(separatedBy: .newlines).filter { $0.hasPrefix(prefix) }
            guard matches.count == 1 else { return nil }
            return String(matches[0].dropFirst(prefix.count)).trimmingCharacters(in: .whitespaces)
        }
        let date = DateFormatter()
        date.locale = Locale(identifier: "en_US_POSIX")
        date.timeZone = TimeZone(secondsFromGMT: 0)
        date.dateFormat = "EEE d MMM HH:mm:ss 'UTC' yyyy"
        date.isLenient = false
        let iso = ISO8601DateFormatter()
        guard fileURL.lastPathComponent == "gmapsupp.img",
              fileURL.deletingLastPathComponent().lastPathComponent == proof.payloadPath.split(separator: "/").first.map(String.init),
              field("Name of area:") == proof.sourceRegion,
              field("Garmin map style:") == "\(context.mapType.replacingOccurrences(of: "-latin1", with: "")) (latin1)",
              let creation = field("This Garmin map was created on:"),
              let timestamp = date.date(from: creation),
              timestamp == iso.date(from: proof.generatedAt),
              checksum.trimmingCharacters(in: .whitespacesAndNewlines) == "\(proof.payloadMD5)  gmapsupp.img" else {
            throw MapSourceValidationError.identityMismatch
        }
        return ValidatedMapSource(url: fileURL, sizeBytes: inspected.sizeBytes, sha256: inspected.sha256, metadata: metadata)
    }

    private func inspect(fileURL: URL) throws -> (prefix: [UInt8], sizeBytes: UInt64, sha256: String, md5: String) {
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
        var md5 = Insecure.MD5()
        var sizeBytes: UInt64 = 0

        do {
            while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty {
                if prefix.count < GarminIMGMetadataParser.prefixLength {
                    prefix.append(contentsOf: chunk.prefix(
                        GarminIMGMetadataParser.prefixLength - prefix.count
                    ))
                }

                hasher.update(data: chunk)
                md5.update(data: chunk)
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
            sha256: digestString(hasher.finalize()),
            md5: md5.finalize().map { String(format: "%02x", $0) }.joined()
        )
    }

    private func digestString(_ digest: SHA256.Digest) -> String {
        digest.map { String(format: "%02x", $0) }.joined()
    }
}

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
        expectedPackage: MapPackage,
        onProgress: (@Sendable (Double) -> Void)? = nil
    ) throws -> ValidatedMapSource {
        let isBBBike = MapIdentity.normalizeProvider(expectedPackage.providerId) == "bbbike"
        let isOSMapa = MapIdentity.normalizeProvider(expectedPackage.providerId) == "osmapa"
        let inspected = try inspect(fileURL: fileURL, computeMD5: isBBBike, computeCRC32: isOSMapa, onProgress: onProgress)
        if isBBBike {
            return try validateBBBike(fileURL: fileURL, expectedPackage: expectedPackage, inspected: inspected)
        }
        if isOSMapa {
            return try validateOSMapa(fileURL: fileURL, expectedPackage: expectedPackage, inspected: inspected)
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
        inspected: InspectedSource) throws -> ValidatedMapSource {
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
        let iso = ISO8601DateFormatter()
        guard fileURL.lastPathComponent == "gmapsupp.img",
              fileURL.deletingLastPathComponent().lastPathComponent == proof.payloadPath.split(separator: "/").first.map(String.init),
              field("Name of area:") == proof.sourceRegion,
              field("Garmin map style:") == "\(context.mapType.replacingOccurrences(of: "-latin1", with: "")) (latin1)",
              let creation = field("This Garmin map was created on:"),
              let timestamp = Self.bbbikeCreationDate(creation),
              timestamp == iso.date(from: proof.generatedAt),
              checksum.trimmingCharacters(in: .whitespacesAndNewlines) == "\(proof.payloadMD5)  gmapsupp.img" else {
            throw MapSourceValidationError.identityMismatch
        }
        return ValidatedMapSource(url: fileURL, sizeBytes: inspected.sizeBytes, sha256: inspected.sha256, metadata: metadata)
    }

    /// The whole IMG is bound to the catalog proof (size, CRC-32, header) and
    /// its MPS product file must name only the style's Garmin family ID.
    private func validateOSMapa(fileURL: URL, expectedPackage package: MapPackage,
        inspected: InspectedSource) throws -> ValidatedMapSource {
        guard OSMapaProviderAdapter().expectedIMGIdentity(for: package) != nil,
              let proof = package.mainArtifact?.osmapaSourceProof,
              let (coverage, style) = OSMapaProviderAdapter.region(package.providerRegionId),
              fileURL.lastPathComponent == proof.payloadPath,
              inspected.sizeBytes == proof.installSizeBytes,
              inspected.crc32 == proof.crc32,
              OSMapaIMGMetadata.marker(inspected.prefix) == .map(coverage: coverage, style: style),
              let metadata = OSMapaIMGMetadata.metadata(inspected.prefix),
              OSMapaIMGMetadata.mdrFamilyIDs(inspected.prefix) == [style.familyID],
              (try? OSMapaIMGInspection.mpsFamilyIDs(fileURL: fileURL)) == [style.familyID] else {
            throw MapSourceValidationError.identityMismatch
        }
        guard metadata.version == package.version else {
            throw MapSourceValidationError.versionMismatch
        }
        return ValidatedMapSource(url: fileURL, sizeBytes: inspected.sizeBytes, sha256: inspected.sha256, metadata: metadata)
    }

    static func bbbikeCreationDate(_ value: String) -> Date? {
        let normalized = value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.isLenient = false
        for format in ["EEE d MMM HH:mm:ss 'UTC' yyyy", "EEE MMM d HH:mm:ss 'UTC' yyyy"] {
            formatter.dateFormat = format
            if let date = formatter.date(from: normalized), formatter.string(from: date) == normalized {
                return date
            }
        }
        return nil
    }

    typealias InspectedSource = (prefix: [UInt8], sizeBytes: UInt64, sha256: String, md5: String?, crc32: String?)

    /// MD5 is only the BBBike payload proof and CRC-32 only the OSMapaPL one;
    /// other providers skip them.
    private func inspect(fileURL: URL, computeMD5: Bool = false, computeCRC32: Bool = false,
                         onProgress: (@Sendable (Double) -> Void)? = nil) throws -> InspectedSource {
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

        let expectedSize = (try fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        var prefix: [UInt8] = []
        prefix.reserveCapacity(GarminIMGMetadataParser.prefixLength)
        var hasher = SHA256()
        var md5: Insecure.MD5? = computeMD5 ? Insecure.MD5() : nil
        var crc32: CRC32? = computeCRC32 ? CRC32() : nil
        var sizeBytes: UInt64 = 0

        do {
            while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty {
                if prefix.count < GarminIMGMetadataParser.prefixLength {
                    prefix.append(contentsOf: chunk.prefix(
                        GarminIMGMetadataParser.prefixLength - prefix.count
                    ))
                }

                hasher.update(data: chunk)
                md5?.update(data: chunk)
                crc32?.update(chunk)
                let (newSize, overflow) = sizeBytes.addingReportingOverflow(UInt64(chunk.count))
                guard !overflow else {
                    throw MapSourceValidationError.readFailed
                }
                sizeBytes = newSize
                if expectedSize > 0 { onProgress?(min(1, Double(sizeBytes) / Double(expectedSize))) }
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
            md5: md5?.finalize().map { String(format: "%02x", $0) }.joined(),
            crc32: crc32.map { String(format: "%08x", $0.value) }
        )
    }

    private func digestString(_ digest: SHA256.Digest) -> String {
        digest.map { String(format: "%02x", $0) }.joined()
    }
}

/// Standard ZIP CRC-32 (reflected polynomial 0xEDB88320).
struct CRC32: Sendable {
    private static let table: [UInt32] = (0..<256).map { index in
        (0..<8).reduce(UInt32(index)) { value, _ in value & 1 == 1 ? 0xEDB8_8320 ^ (value >> 1) : value >> 1 }
    }
    private var state: UInt32 = 0xFFFF_FFFF

    var value: UInt32 { state ^ 0xFFFF_FFFF }

    mutating func update(_ data: Data) {
        let table = Self.table
        var crc = state
        data.withUnsafeBytes { buffer in
            for byte in buffer {
                crc = table[Int((crc ^ UInt32(byte)) & 0xFF)] ^ (crc >> 8)
            }
        }
        state = crc
    }
}

/// Reads the mkgmap product file (`MAKEGMAP.MPS`) through the IMG FAT. Its
/// `L` (map) and `F` (family) records carry the Garmin family ID that decides
/// which maps a watch shows together.
enum OSMapaIMGInspection {
    enum Failure: Error { case invalidIMG }

    static func mpsFamilyIDs(fileURL: URL) throws -> Set<UInt16> {
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }
        let size = try handle.seekToEnd()
        func require(_ condition: Bool) throws {
            guard condition else { throw Failure.invalidIMG }
        }
        func read(_ offset: UInt64, _ count: Int) throws -> [UInt8] {
            try require(count >= 0 && count <= 2_097_152 && offset <= size && UInt64(count) <= size - offset)
            try handle.seek(toOffset: offset)
            let bytes = [UInt8](try handle.read(upToCount: count) ?? Data())
            try require(bytes.count == count)
            return bytes
        }
        func number(_ bytes: [UInt8], _ offset: Int, _ count: Int) throws -> Int {
            try require(offset >= 0 && offset + count <= bytes.count)
            return (0..<count).reduce(0) { $0 | Int(bytes[offset + $1]) << ($1 * 8) }
        }
        let head = try read(0, Int(min(size, 2_097_152)))
        try require(OSMapaIMGMetadata.isGarminIMG(head))
        let exponent = Int(head[0x61]) + Int(head[0x62])
        try require(exponent >= 9 && exponent <= 20)
        let blockSize = 1 << exponent
        var mps: [UInt8]?
        var offset = 0x400
        while offset + 0x200 <= head.count, head[offset] == 1 {
            if Array(head[(offset + 1)..<(offset + 12)]) == Array("MAKEGMAPMPS".utf8) {
                try require(mps == nil && number(head, offset + 0x10, 2) == 0)
                let length = try number(head, offset + 0x0C, 4)
                try require(length > 0 && length <= 1_048_576)
                let blockCount = (length + blockSize - 1) / blockSize
                try require(blockCount <= 240)
                var data: [UInt8] = []
                for index in 0..<blockCount {
                    let block = try number(head, offset + 0x20 + index * 2, 2)
                    try require(block != 0xFFFF)
                    data += try read(UInt64(block) * UInt64(blockSize), min(blockSize, length - data.count))
                }
                mps = data
            }
            offset += 0x200
        }
        guard let mps else { throw Failure.invalidIMG }
        var families = Set<UInt16>()
        var kinds = Set<UInt8>()
        var cursor = 0
        while cursor < mps.count {
            let kind = mps[cursor]
            let length = try number(mps, cursor + 1, 2)
            try require(cursor + 3 + length <= mps.count)
            if kind == 0x4C || kind == 0x46 {
                try require(length >= 4)
                families.insert(UInt16(try number(mps, cursor + 5, 2)))
                kinds.insert(kind)
            }
            cursor += 3 + length
        }
        try require(kinds == [0x4C, 0x46])
        return families
    }
}

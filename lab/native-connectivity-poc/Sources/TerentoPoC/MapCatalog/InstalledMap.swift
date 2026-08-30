import Foundation

struct InstalledMapFile: Identifiable, Equatable, Sendable {
    let path: String
    let filename: String
    let sizeBytes: UInt64
    /// The exact MTP object handle, when the inventory came from a live
    /// device scan. A path alone is never sufficient for a destructive
    /// operation.
    let itemID: UInt32?

    init(
        path: String,
        filename: String,
        sizeBytes: UInt64,
        itemID: UInt32? = nil
    ) {
        self.path = path
        self.filename = filename
        self.sizeBytes = sizeBytes
        self.itemID = itemID
    }

    var id: String {
        path
    }
}

enum MapMetadataStatus: String, Sendable, Equatable {
    case parsed = "PARSED"
    case unknown = "UNKNOWN"
}

struct InstalledMap: Identifiable, Equatable, Sendable {
    let name: String
    let provider: String?
    let region: String?
    let family: String?
    let rawVersion: String?
    let version: MapVersion?
    let identifier: String?
    let productId: UInt16?
    let familyId: UInt16?
    let sizeBytes: UInt64
    let sourceFile: InstalledMapFile
    let metadataStatus: MapMetadataStatus
    let managementState: MapManagementState

    var id: String {
        sourceFile.id
    }

    var identity: MapIdentity? {
        MapIdentity(provider: provider, region: region)
    }
}

struct GarminIMGMetadata: Sendable, Equatable {
    let name: String?
    let provider: String?
    let region: String?
    let family: String?
    let rawVersion: String?
    let version: MapVersion?
    let identifier: String?
    let productId: UInt16?
    let familyId: UInt16?
}

struct GarminIMGMetadataParser: Sendable {
    // The identifying strings are in the fixed IMG header. Keep this small so
    // a scan never downloads a complete map image over MTP.
    static let prefixLength = 4 * 1024

    func parse(_ bytes: [UInt8]) -> GarminIMGMetadata? {
        guard bytes.count >= 0x84,
              text(bytes, offset: 0x10, length: 7) == "DSKIMG",
              text(bytes, offset: 0x41, length: 7) == "GARMIN" else {
            return nil
        }

        let description = text(bytes, offset: 0x49, length: 20)
        let headerDetail = text(bytes, offset: 0x65, length: 31)
        let strings = printableStrings(bytes)
        let headerStrings = [description, headerDetail].compactMap { $0 }
        let stitchedHeader = stitchedFreizeitkarteHeader(
            description: description,
            detail: headerDetail
        )
        let stitchedMetadata = stitchedFreizeitkarteMetadata(
            description: description,
            detail: headerDetail
        )
        let combinedText = (
            headerStrings
                + [stitchedHeader].compactMap { $0 }
                + [stitchedMetadata].compactMap { $0 }
                + strings
        ).joined(separator: " ")
        let provider = provider(in: combinedText)
        let region = provider == "Freizeitkarte"
            ? freizeitkarteRegion(in: combinedText)
            : nil
        let rawVersion = releaseLabel(in: combinedText)
        let name: String?
        if let provider, let region {
            name = "\(provider) \(region)"
        } else {
            name = description ?? headerDetail
        }

        let version = MapVersionNormalizer().parse(
            rawValue: rawVersion,
            provider: provider,
            fullText: combinedText
        )

        return GarminIMGMetadata(
            name: name,
            provider: provider,
            region: region,
            family: provider ?? description ?? headerDetail,
            rawVersion: rawVersion,
            version: version,
            // The concrete provider token is represented by `region` after
            // parsing. The catalog's package identifier is joined through
            // MapPackage.identity and MapCatalogIdentityKey.
            identifier: nil,
            productId: nil,
            familyId: nil
        )
    }

    private func text(_ bytes: [UInt8], offset: Int, length: Int) -> String? {
        guard offset >= 0, length > 0, offset + length <= bytes.count else {
            return nil
        }

        let value = bytes[offset..<(offset + length)]
            .prefix { $0 != 0 }
            .map { byte -> Character? in
                guard (0x20...0x7E).contains(byte) else {
                    return nil
                }
                return Character(UnicodeScalar(byte))
            }
            .compactMap { $0 }

        let result = String(value).trimmingCharacters(in: .whitespacesAndNewlines)
        return result.isEmpty ? nil : result
    }

    private func printableStrings(_ bytes: [UInt8]) -> [String] {
        var strings: [String] = []
        var current: [UInt8] = []

        for byte in bytes {
            if (0x20...0x7E).contains(byte) {
                current.append(byte)
            } else {
                if current.count >= 3 {
                    strings.append(String(decoding: current, as: UTF8.self))
                }
                current.removeAll(keepingCapacity: true)
            }
        }

        if current.count >= 3 {
            strings.append(String(decoding: current, as: UTF8.self))
        }

        return strings
    }

    private func provider(in value: String) -> String? {
        value.range(
            of: "freizeitkarte",
            options: [.caseInsensitive, .diacriticInsensitive]
        ) == nil ? nil : "Freizeitkarte"
    }

    /// Garmin IMG descriptions are split across two fixed header fields when
    /// the provider identity is longer than 20 bytes. The fields are separated
    /// by binary header bytes, so generic printable-string extraction cannot
    /// reconstruct values such as `Freizeitkarte_ESP_CANARIAS` by itself.
    private func stitchedFreizeitkarteHeader(
        description: String?,
        detail: String?
    ) -> String? {
        guard let description,
              let detail,
              description.utf8.count == 20,
              provider(in: description) == "Freizeitkarte" else {
            return nil
        }

        let releaseStart = detail.range(
            of: "(release",
            options: [.caseInsensitive, .diacriticInsensitive]
        )?.lowerBound ?? detail.endIndex
        let prefix = String(detail[..<releaseStart])
        let pattern = #"[A-Za-z0-9][A-Za-z0-9_-]*"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                in: prefix,
                range: NSRange(prefix.startIndex..<prefix.endIndex, in: prefix)
              ),
              let range = Range(match.range, in: prefix) else {
            return nil
        }

        let continuation = String(prefix[range])
        guard !continuation.isEmpty else {
            return nil
        }
        return description + continuation
    }

    /// The release marker can itself cross the binary gap between the fixed
    /// fields, for example `(R` + `elease 26.05)`. Keep a second, bounded
    /// joined value for release parsing; region parsing uses the sanitized
    /// identity value above because some images have printable binary bytes
    /// before the continuation.
    private func stitchedFreizeitkarteMetadata(
        description: String?,
        detail: String?
    ) -> String? {
        guard let description,
              let detail,
              description.utf8.count == 20,
              provider(in: description) == "Freizeitkarte" else {
            return nil
        }

        return description + detail
    }

    private func freizeitkarteRegion(in value: String) -> String? {
        // Some provider regions are composite identifiers, for example
        // ESP-CANARIAS. Prefer the longest token found in the header because
        // the fixed description field may contain a truncated prefix while
        // the same IMG also contains the complete printable identifier.
        let pattern = #"(?i)freizeitkarte[\s_-]+([a-z0-9]+(?:[+_-][a-z0-9]+)*)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return nil
        }

        let matches = regex.matches(
                  in: value,
                  range: NSRange(value.startIndex..<value.endIndex, in: value)
        )
        guard let region = matches.compactMap({ match -> String? in
            guard let regionRange = Range(match.range(at: 1), in: value) else {
                return nil
            }
            return String(value[regionRange])
        }).max(by: { $0.count < $1.count }) else {
            return nil
        }

        return region.uppercased()
    }

    private func releaseLabel(in value: String) -> String? {
        let pattern = #"(?i)\brelease\s+([0-9]{2,4}[-/.][0-9]{1,2})\b"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                in: value,
                range: NSRange(value.startIndex..<value.endIndex, in: value)
              ),
              let releaseRange = Range(match.range(at: 1), in: value) else {
            return nil
        }

        return "Release \(value[releaseRange])"
    }
}

struct GarminMapScanner: Sendable {
    private let parser = GarminIMGMetadataParser()

    func scan(
        files: [DeviceFile],
        reader: DeviceFileReader,
        ownershipRecords: [MapOwnershipRecord] = [],
        recognizedProviderIDs: Set<String>? = nil
    ) -> MapScanResult {
        let mapFiles = files.filter(isMapFile)
        let candidateFiles = mapFiles.filter { !isKnownGarminOwned($0) }
        var inspectedFiles: [InstalledMapFile] = []
        var installedMaps: [InstalledMap] = []
        var otherMaps: [InstalledMap] = []
        var unrecognizedIMGFiles = 0
        var skippedNonFreizeitkarteFiles = mapFiles.count - candidateFiles.count
        let prefixes = readPrefixes(
            for: candidateFiles,
            reader: reader
        )

        for file in candidateFiles {
            let installedFile = InstalledMapFile(
                path: file.path,
                filename: file.filename,
                sizeBytes: file.sizeBytes,
                itemID: file.itemID
            )
            inspectedFiles.append(installedFile)

            let metadata = parser.parse(prefixes[file.itemID] ?? [])

            guard let metadata else {
                unrecognizedIMGFiles += 1
                continue
            }

            // Classification is content-first. Garmin-owned images are
            // excluded before inspection. When a catalog is available, its
            // provider IDs decide which parsed community images can enter
            // comparison logic; unknown parsed providers remain read-only.
            let normalizedProvider = MapIdentity.normalizeProvider(metadata.provider ?? "")
            let isRecognizedProvider = metadata.provider != nil
                && (recognizedProviderIDs == nil
                    || recognizedProviderIDs?.contains(normalizedProvider) == true)
            guard isRecognizedProvider else {
                skippedNonFreizeitkarteFiles += 1
                otherMaps.append(
                    InstalledMap(
                        name: metadata.name ?? file.filename,
                        provider: metadata.provider,
                        region: metadata.region,
                        family: metadata.family,
                        rawVersion: metadata.rawVersion,
                        version: metadata.version,
                        identifier: metadata.identifier,
                        productId: metadata.productId,
                        familyId: metadata.familyId,
                        sizeBytes: file.sizeBytes,
                        sourceFile: installedFile,
                        metadataStatus: .parsed,
                        managementState: .unknown
                    )
                )
                continue
            }

            installedMaps.append(
                InstalledMap(
                    name: metadata.name ?? "Unknown map",
                    provider: metadata.provider,
                    region: metadata.region,
                    family: metadata.family,
                    rawVersion: metadata.rawVersion,
                    version: metadata.version,
                    identifier: metadata.identifier,
                    productId: metadata.productId,
                    familyId: metadata.familyId,
                    sizeBytes: file.sizeBytes,
                        sourceFile: installedFile,
                        metadataStatus: .parsed,
                        managementState: MapOwnershipMatcher().managementState(
                            for: installedFile,
                            metadata: metadata,
                            records: ownershipRecords
                        )
                )
            )
        }

        return MapScanResult(
            files: inspectedFiles,
            installedMaps: installedMaps,
            otherMaps: otherMaps,
            parsingFailures: unrecognizedIMGFiles,
            skippedNonFreizeitkarteFiles: skippedNonFreizeitkarteFiles
        )
    }

    private func readPrefixes(
        for files: [DeviceFile],
        reader: DeviceFileReader
    ) -> [UInt32: [UInt8]] {
        if let prefixes = try? reader.readFilePrefixes(
            for: files,
            maxLength: GarminIMGMetadataParser.prefixLength
        ) {
            return prefixes
        }

        var prefixes: [UInt32: [UInt8]] = [:]
        for file in files {
            if let prefix = try? reader.readFilePrefix(
                for: file,
                maxLength: GarminIMGMetadataParser.prefixLength
            ) {
                prefixes[file.itemID] = prefix
            }
        }
        return prefixes
    }

    private func isMapFile(_ file: DeviceFile) -> Bool {
        guard !file.isFolder else {
            return false
        }

        let path = file.path.lowercased()
        let isGarminRootFile = path.split(separator: "/").count == 2
            && path.hasPrefix("/garmin/")
        let isGarminMapFile = path.hasPrefix("/garmin/map/")
        let isIMG = file.filename.lowercased().hasSuffix(".img")
        return isIMG && (isGarminRootFile || isGarminMapFile)
    }

    private func isKnownGarminOwned(_ file: DeviceFile) -> Bool {
        let filename = file.filename.lowercased()

        // These are known Garmin-owned map/system images. They are excluded
        // before any prefix read. `gmapsupp.img` is intentionally not listed:
        // BaseCamp and third-party tools may use that name for a community map,
        // so its content must remain the source of truth.
        let knownNames = Set([
            "gmapbmap.img",
            "gmaptz.img",
            "gmappmap.img",
            "gmapprom.img",
            "gmapdem.img",
            "gmap3d.img",
            "gmaprgn.img"
        ])

        if knownNames.contains(filename) {
            return true
        }

        // Garmin firmware map images commonly use D########A.img names.
        // The safety rule is deliberately conservative: every D*.img is
        // treated as Garmin-owned and is never inspected or modified.
        return filename.hasPrefix("d") && filename.hasSuffix(".img")
    }

}

struct MapScanResult: Sendable, Equatable {
    let files: [InstalledMapFile]
    let installedMaps: [InstalledMap]
    let otherMaps: [InstalledMap]
    let parsingFailures: Int
    let skippedNonFreizeitkarteFiles: Int

    var scanEvidence: EvidenceResult {
        .pass
    }

    var imgParsingEvidence: EvidenceResult {
        parsingFailures == 0 ? .pass : .fail
    }
}

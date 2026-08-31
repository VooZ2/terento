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

    func parse(_ bytes: [UInt8], filename: String? = nil) -> GarminIMGMetadata? {
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
        let stitchedOpenTopoMapHeader = stitchedOpenTopoMapHeader(
            description: description,
            detail: headerDetail
        )
        let stitchedOpenTopoMapMetadata = stitchedOpenTopoMapMetadata(
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
                + [stitchedOpenTopoMapHeader].compactMap { $0 }
                + [stitchedOpenTopoMapMetadata].compactMap { $0 }
                + [stitchedMetadata].compactMap { $0 }
                + strings
        ).joined(separator: " ")
        let provider = provider(in: combinedText)
        let region: String?
        switch provider {
        case "Freizeitkarte":
            region = freizeitkarteRegion(in: combinedText)
        case "OpenTopoMap":
            region = openTopoMapRegion(
                in: combinedText,
                header: stitchedOpenTopoMapHeader,
                filename: filename
            )
        default:
            region = nil
        }
        let rawVersion = releaseLabel(in: combinedText, provider: provider)
        let name: String?
        if let provider, let region {
            if provider == "OpenTopoMap" {
                name = stitchedOpenTopoMapHeader
                    ?? openTopoMapDisplayName(in: combinedText)
                    ?? "\(provider) \(region)"
            } else {
                name = "\(provider) \(region)"
            }
        } else {
            name = stitchedOpenTopoMapHeader ?? stitchedHeader ?? description ?? headerDetail
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
        if value.range(
            of: "freizeitkarte",
            options: [.caseInsensitive, .diacriticInsensitive]
        ) != nil {
            return "Freizeitkarte"
        }
        if value.range(
            of: "opentopomap",
            options: [.caseInsensitive, .diacriticInsensitive]
        ) != nil {
            return "OpenTopoMap"
        }
        return nil
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

    /// OpenTopoMap stores the last character of a country name in the next
    /// fixed field. Reconstructing this bounded header gives imported maps a
    /// useful display name without scanning or executing the rest of the IMG.
    private func stitchedOpenTopoMapHeader(
        description: String?,
        detail: String?
    ) -> String? {
        guard let description,
              let detail,
              description.utf8.count == 20,
              provider(in: description) == "OpenTopoMap" else {
            return nil
        }

        let dateStart = detail.range(
            of: #"\b(?:20\d{2}|0\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"#,
            options: .regularExpression
        )?.lowerBound ?? detail.endIndex
        let continuation = String(detail[..<dateStart])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !continuation.isEmpty,
              continuation.first?.isLetter == true else {
            return nil
        }
        return description + continuation
    }

    /// OpenTopoMap's generated date can cross the binary gap between the
    /// fixed description and detail fields (for example `202` +
    /// `6-05-24`). Keep a separate bounded joined value for release parsing;
    /// the provider and region parser continue to use sanitized identity
    /// values.
    private func stitchedOpenTopoMapMetadata(
        description: String?,
        detail: String?
    ) -> String? {
        guard let description,
              let detail,
              description.utf8.count == 20,
              provider(in: description) == "OpenTopoMap" else {
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

    private func openTopoMapRegion(
        in value: String,
        header: String?,
        filename: String?
    ) -> String? {
        // Managed filenames are an exact fallback for long OTM names whose
        // fixed IMG header is truncated. The header/provider signature is
        // still required before this value is used for identity matching.
        if let filenameRegion = openTopoMapRegionFromFilename(filename) {
            return filenameRegion
        }

        guard let header else {
            let normalized = normalizedOpenTopoMapText(value)
            let pattern = #"(?i)\bopentopomap\s+([a-z0-9][a-z0-9_-]*)\b"#
            guard let regex = try? NSRegularExpression(pattern: pattern),
                  let match = regex.firstMatch(
                      in: normalized,
                      range: NSRange(normalized.startIndex..<normalized.endIndex, in: normalized)
                  ),
                  let range = Range(match.range(at: 1), in: normalized) else {
                return nil
            }
            return String(normalized[range])
                .replacingOccurrences(of: " ", with: "")
                .uppercased()
        }

        let normalizedHeader = normalizedOpenTopoMapText(header)
        let providerPrefix = "opentopomap "
        guard normalizedHeader.hasPrefix(providerPrefix) else { return nil }
        let title = String(normalizedHeader.dropFirst(providerPrefix.count))
        guard !title.isEmpty else { return nil }

        // Keep the legacy LTU identity used by the first beta package. New
        // OTM records use the provider's normalized region slug, so the
        // generic path covers every official country and multi-country row.
        if title == "lithuania" {
            return "LTU"
        }
        return title.replacingOccurrences(of: " ", with: "").uppercased()
    }
    private func openTopoMapDisplayName(in value: String) -> String? {
        let normalized = value
            .folding(options: .diacriticInsensitive, locale: .current)
            .lowercased()
            .map { character in
                character.isLetter || character.isNumber ? character : " "
            }
        let searchable = String(normalized)
            .split(whereSeparator: { $0 == " " })
            .joined(separator: " ")

        let countryNames = [
            "Albania", "Andorra", "Austria", "Belarus", "Belgium",
            "Bosnia and Herzegovina", "Bulgaria", "Croatia", "Cyprus",
            "Czech Republic", "Denmark", "Estonia", "Finland", "France",
            "Germany", "Greece", "Hungary", "Iceland", "Ireland", "Italy",
            "Kosovo", "Latvia", "Liechtenstein", "Lithuania", "Luxembourg",
            "Malta", "Moldova", "Monaco", "Montenegro", "Netherlands",
            "North Macedonia", "Norway", "Poland", "Portugal", "Romania",
            "Russia", "San Marino", "Serbia", "Slovakia", "Slovenia",
            "South Africa", "South Korea", "Spain", "Sweden", "Switzerland",
            "Turkey", "Ukraine", "United Kingdom", "United States", "New Zealand"
        ]

        for country in countryNames {
            let normalizedCountry = country
                .folding(options: .diacriticInsensitive, locale: .current)
                .lowercased()
            if searchable.contains("opentopomap \(normalizedCountry)") {
                return "OpenTopoMap \(country)"
            }
        }
        return nil
    }

    private func normalizedOpenTopoMapText(_ value: String) -> String {
        let normalized = value
            .folding(options: .diacriticInsensitive, locale: .current)
            .lowercased()
            .map { character in
                character.isLetter || character.isNumber ? character : " "
            }
        return String(normalized)
            .split(whereSeparator: { $0 == " " })
            .joined(separator: " ")
    }

    private func openTopoMapRegionFromFilename(_ filename: String?) -> String? {
        guard let filename else { return nil }
        let stem = filename
            .split(separator: ".", omittingEmptySubsequences: false)
            .dropLast()
            .joined(separator: ".")
        let normalized = stem
            .folding(options: .diacriticInsensitive, locale: .current)
            .lowercased()
        let prefix: String
        if normalized.hasPrefix("otm-") {
            prefix = String(normalized.dropFirst(4))
        } else if normalized.hasPrefix("terento_opentopomap_") {
            prefix = String(normalized.dropFirst("terento_opentopomap_".count))
        } else {
            return nil
        }
        guard !prefix.isEmpty,
              prefix.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }) else {
            return nil
        }
        let region = prefix
            .replacingOccurrences(of: "_", with: "")
            .replacingOccurrences(of: "-", with: "")
        return region == "lithuania"
            ? "LTU"
            : region.uppercased()
    }

    private func releaseLabel(in value: String, provider: String?) -> String? {
        if provider == "OpenTopoMap" {
            if let label = OpenTopoMapVersionParser().generatedDateLabel(from: value) {
                return label
            }
        }

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
        var skippedUnrecognizedProviderFiles = mapFiles.count - candidateFiles.count
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

            let metadata = parser.parse(
                prefixes[file.itemID] ?? [],
                filename: file.filename
            )

            guard let metadata else {
                unrecognizedIMGFiles += 1
                continue
            }

            let ownershipMatcher = MapOwnershipMatcher()
            let managementState = ownershipMatcher.managementState(
                for: installedFile,
                metadata: metadata,
                records: ownershipRecords
            )
            let isManagedCustom = ownershipMatcher.isExactCustomRecord(
                for: installedFile,
                records: ownershipRecords
            )
            // A custom import remains custom even when its bytes happen to
            // contain a provider signature. The exact manifest record is the
            // authority for this presentation classification; it does not
            // weaken the separate destructive-operation checks.
            let effectiveProvider = isManagedCustom ? nil : metadata.provider
            let effectiveRegion = isManagedCustom ? nil : metadata.region

            // Classification is content-first. Garmin-owned images are
            // excluded before inspection. When a catalog is available, its
            // provider IDs decide which parsed community images can enter
            // comparison logic; unknown parsed providers remain read-only.
            let normalizedProvider = MapIdentity.normalizeProvider(effectiveProvider ?? "")
            let isRecognizedProvider = effectiveProvider != nil
                && (recognizedProviderIDs == nil
                    || recognizedProviderIDs?.contains(normalizedProvider) == true)
            guard isRecognizedProvider else {
                skippedUnrecognizedProviderFiles += 1
                otherMaps.append(
                    InstalledMap(
                        name: metadata.name ?? file.filename,
                        provider: effectiveProvider,
                        region: effectiveRegion,
                        family: metadata.family,
                        rawVersion: metadata.rawVersion,
                        version: metadata.version,
                        identifier: metadata.identifier,
                        productId: metadata.productId,
                        familyId: metadata.familyId,
                        sizeBytes: file.sizeBytes,
                        sourceFile: installedFile,
                        metadataStatus: .parsed,
                        managementState: managementState
                    )
                )
                continue
            }

            installedMaps.append(
                InstalledMap(
                    name: metadata.name ?? "Unknown map",
                    provider: effectiveProvider,
                    region: effectiveRegion,
                    family: metadata.family,
                    rawVersion: metadata.rawVersion,
                    version: metadata.version,
                    identifier: metadata.identifier,
                    productId: metadata.productId,
                    familyId: metadata.familyId,
                    sizeBytes: file.sizeBytes,
                    sourceFile: installedFile,
                    metadataStatus: .parsed,
                    managementState: managementState
                )
            )
        }

        return MapScanResult(
            files: inspectedFiles,
            installedMaps: installedMaps,
            otherMaps: otherMaps,
            parsingFailures: unrecognizedIMGFiles,
            skippedUnrecognizedProviderFiles: skippedUnrecognizedProviderFiles
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
    let skippedUnrecognizedProviderFiles: Int

    var scanEvidence: EvidenceResult {
        .pass
    }

    var imgParsingEvidence: EvidenceResult {
        parsingFailures == 0 ? .pass : .fail
    }
}

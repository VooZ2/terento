import CryptoKit
import Foundation

enum MapAcquisitionState: String, Codable, Equatable, Sendable {
    case idle = "IDLE"
    case resolvingPackage = "RESOLVING_PACKAGE"
    case downloading = "DOWNLOADING"
    case validatingDownload = "VALIDATING_DOWNLOAD"
    case extracting = "EXTRACTING"
    case inspectingIMG = "INSPECTING_IMG"
    case validatingIdentity = "VALIDATING_IDENTITY"
    case hashing = "HASHING"
    case validated = "VALIDATED"
    case failed = "FAILED"
}

struct MapDownloadProgress: Equatable, Sendable {
    let bytesDownloaded: UInt64
    let totalBytes: UInt64
    let bytesPerSecond: Double

    var fractionCompleted: Double {
        guard totalBytes > 0 else { return 0 }
        return min(1, Double(bytesDownloaded) / Double(totalBytes))
    }
}

enum MapPackageFormat: String, Codable, Equatable, Sendable {
    case rawIMG = "RAW_IMG"
    case zip = "ZIP"

    static func detect(fileURL: URL) throws -> MapPackageFormat {
        let prefix = try readPrefix(from: fileURL, maxLength: 4 * 1024)
        guard !prefix.isEmpty else {
            throw MapAcquisitionError.invalidPackage("The downloaded package is empty.")
        }

        if isZIP(prefix) {
            return .zip
        }

        if GarminIMGMetadataParser().parse(prefix) != nil {
            return .rawIMG
        }

        throw MapAcquisitionError.unsupportedPackageFormat
    }

    private static func isZIP(_ bytes: [UInt8]) -> Bool {
        guard bytes.count >= 4 else {
            return false
        }

        return bytes[0] == 0x50
            && bytes[1] == 0x4B
            && ((bytes[2] == 0x03 && bytes[3] == 0x04)
                || (bytes[2] == 0x05 && bytes[3] == 0x06)
                || (bytes[2] == 0x07 && bytes[3] == 0x08))
    }

    static func readPrefix(from fileURL: URL, maxLength: Int) throws -> [UInt8] {
        let handle: FileHandle
        do {
            handle = try FileHandle(forReadingFrom: fileURL)
        } catch {
            throw MapAcquisitionError.invalidPackage("The downloaded package could not be read.")
        }

        defer {
            try? handle.close()
        }

        do {
            return Array(try handle.read(upToCount: maxLength) ?? Data())
        } catch {
            throw MapAcquisitionError.invalidPackage("The downloaded package could not be read.")
        }
    }
}

enum MapAcquisitionError: LocalizedError, Equatable, Sendable {
    case downloadFailed(String)
    case downloadIncomplete(expected: UInt64?, actual: UInt64)
    case invalidPackage(String)
    case unsupportedPackageFormat
    case unsafeArchivePath(String)
    case sourceIdentityMismatch(expected: MapIdentity, actual: MapIdentity?)
    case sourceVersionMismatch(expected: MapVersion, actual: MapVersion?)
    case noIMGFound
    case ambiguousIMG
    case workspaceFailed(String)

    var errorDescription: String? {
        switch self {
        case .downloadFailed(let message):
            return "The map package could not be downloaded: \(message)"
        case .downloadIncomplete(let expected, let actual):
            if let expected {
                return "The map package is incomplete: expected \(expected) bytes, received \(actual)."
            }
            return "The map package is incomplete: received \(actual) bytes."
        case .invalidPackage(let message):
            return "The downloaded map package is invalid: \(message)"
        case .unsupportedPackageFormat:
            return "The provider package format is not supported."
        case .unsafeArchivePath(let path):
            return "The archive contains an unsafe path: \(path)"
        case .sourceIdentityMismatch:
            return "The downloaded map does not match the selected provider and region."
        case .sourceVersionMismatch:
            return "The downloaded map release does not match the catalog release."
        case .noIMGFound:
            return "The package contains no readable Garmin map image."
        case .ambiguousIMG:
            return "The package contains more than one possible Garmin map image."
        case .workspaceFailed(let message):
            return "The temporary map workspace could not be prepared: \(message)"
        }
    }
}

struct MapPackageDownloadResponse: Sendable, Equatable {
    let statusCode: Int
    let temporaryFileURL: URL
}

protocol MapPackageDownloadClient: Sendable {
    func download(from url: URL) async throws -> MapPackageDownloadResponse

    func download(
        from url: URL,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse
}

extension MapPackageDownloadClient {
    func download(
        from url: URL,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        try await download(from: url)
    }
}

struct FoundationMapPackageDownloadClient: MapPackageDownloadClient, Sendable {
    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        try await download(from: url, onProgress: nil)
    }

    func download(
        from url: URL,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 120

        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MapAcquisitionError.downloadFailed("The provider returned no HTTP response.")
            }

            let temporaryURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("terento-map-download-\(UUID().uuidString)")
            guard FileManager.default.createFile(atPath: temporaryURL.path, contents: nil) else {
                throw MapAcquisitionError.downloadFailed("A local download file could not be created.")
            }

            let handle = try FileHandle(forWritingTo: temporaryURL)
            defer { try? handle.close() }

            let expectedBytes = httpResponse.expectedContentLength > 0
                ? UInt64(httpResponse.expectedContentLength)
                : 0
            var speedEstimator = TransferSpeedEstimator()
            var downloadedBytes: UInt64 = 0
            var buffer = Data()
            buffer.reserveCapacity(64 * 1024)

            for try await byte in bytes {
                buffer.append(byte)
                if buffer.count >= 64 * 1024 {
                    try handle.write(contentsOf: buffer)
                    downloadedBytes += UInt64(buffer.count)
                    buffer.removeAll(keepingCapacity: true)
                    onProgress?(Self.progress(
                        bytesDownloaded: downloadedBytes,
                        totalBytes: expectedBytes,
                        speedEstimator: &speedEstimator
                    ))
                }
            }

            if !buffer.isEmpty {
                try handle.write(contentsOf: buffer)
                downloadedBytes += UInt64(buffer.count)
            }

            onProgress?(Self.progress(
                bytesDownloaded: downloadedBytes,
                totalBytes: expectedBytes,
                speedEstimator: &speedEstimator
            ))

            return MapPackageDownloadResponse(
                statusCode: httpResponse.statusCode,
                temporaryFileURL: temporaryURL
            )
        } catch let error as MapAcquisitionError {
            throw error
        } catch {
            throw MapAcquisitionError.downloadFailed(error.localizedDescription)
        }
    }

    private static func progress(
        bytesDownloaded: UInt64,
        totalBytes: UInt64,
        speedEstimator: inout TransferSpeedEstimator
    ) -> MapDownloadProgress {
        return MapDownloadProgress(
            bytesDownloaded: bytesDownloaded,
            totalBytes: totalBytes,
            bytesPerSecond: speedEstimator.update(bytes: bytesDownloaded)
        )
    }
}

protocol MapPackageArchiveExtractor: Sendable {
    func extract(archiveURL: URL, to extractionDirectory: URL) throws
}

struct SafeArchivePathValidator: Sendable {
    func validate(_ path: String) throws {
        guard !path.isEmpty,
              !path.hasPrefix("/"),
              !path.hasPrefix("\\") else {
            throw MapAcquisitionError.unsafeArchivePath(path)
        }

        let components = path.split(whereSeparator: { $0 == "/" || $0 == "\\" })
        guard !components.contains(where: { $0 == ".." }) else {
            throw MapAcquisitionError.unsafeArchivePath(path)
        }

        guard components.first?.contains(":") != true else {
            throw MapAcquisitionError.unsafeArchivePath(path)
        }
    }
}

/// Uses the macOS archive tools only after every archive entry has been
/// checked. Networking is still performed exclusively by Foundation.
struct SystemZIPArchiveExtractor: MapPackageArchiveExtractor, Sendable {
    private let pathValidator = SafeArchivePathValidator()

    func extract(archiveURL: URL, to extractionDirectory: URL) throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(
            at: extractionDirectory,
            withIntermediateDirectories: true
        )

        guard try fileManager.contentsOfDirectory(atPath: extractionDirectory.path).isEmpty else {
            throw MapAcquisitionError.workspaceFailed("The extraction directory is not empty.")
        }

        let entries = try archiveEntries(archiveURL: archiveURL)
        for entry in entries {
            try pathValidator.validate(entry)
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        process.arguments = ["-x", "-k", archiveURL.path, extractionDirectory.path]
        let errorPipe = Pipe()
        process.standardError = errorPipe

        do {
            try process.run()
        } catch {
            throw MapAcquisitionError.invalidPackage("The ZIP extractor could not be started.")
        }

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let message = String(
                data: errorPipe.fileHandleForReading.readDataToEndOfFile(),
                encoding: .utf8
            )?.trimmingCharacters(in: .whitespacesAndNewlines)
            throw MapAcquisitionError.invalidPackage(
                message.flatMap { $0.isEmpty ? nil : $0 }
                    ?? "The ZIP archive could not be extracted."
            )
        }
    }

    private func archiveEntries(archiveURL: URL) throws -> [String] {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
        process.arguments = ["-Z1", archiveURL.path]
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        do {
            try process.run()
        } catch {
            throw MapAcquisitionError.invalidPackage("The ZIP inspector could not be started.")
        }

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw MapAcquisitionError.invalidPackage("The ZIP archive could not be inspected.")
        }

        let output = outputPipe.fileHandleForReading.readDataToEndOfFile()
        return String(decoding: output, as: UTF8.self)
            .split(whereSeparator: \.isNewline)
            .map(String.init)
    }
}

struct MapAcquisitionWorkspace: Sendable {
    let rootURL: URL
    let downloadURL: URL
    let extractionURL: URL

    init(rootURL: URL) throws {
        self.rootURL = rootURL
        self.downloadURL = rootURL.appendingPathComponent("package.download")
        self.extractionURL = rootURL.appendingPathComponent("extracted", isDirectory: true)

        do {
            try FileManager.default.createDirectory(
                at: rootURL,
                withIntermediateDirectories: true
            )
        } catch {
            throw MapAcquisitionError.workspaceFailed(error.localizedDescription)
        }
    }

    static func make() throws -> MapAcquisitionWorkspace {
        guard let cachesURL = FileManager.default.urls(
            for: .cachesDirectory,
            in: .userDomainMask
        ).first else {
            throw MapAcquisitionError.workspaceFailed("The macOS cache directory is unavailable.")
        }

        let rootURL = cachesURL
            .appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("MapAcquisitions", isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        return try MapAcquisitionWorkspace(rootURL: rootURL)
    }

    func cleanup() throws {
        guard FileManager.default.fileExists(atPath: rootURL.path) else {
            return
        }

        do {
            try FileManager.default.removeItem(at: rootURL)
        } catch {
            throw MapAcquisitionError.workspaceFailed(error.localizedDescription)
        }
    }
}

struct ValidatedMapArtifact: Equatable, Sendable {
    let provider: String
    let region: String
    let canonicalRegion: String
    let rawRelease: String
    let version: MapVersion
    let localIMGURL: URL
    let installSizeBytes: UInt64
    let sha256: String
    let sourcePackageURL: URL
    let catalogPackageID: String
    let targetFilename: String
    let downloadSizeBytes: UInt64
    let catalogDownloadSizeBytes: UInt64?
    let downloadSizeMatchesCatalog: Bool
    let packageFormat: MapPackageFormat
}

struct MapPackageAcquirer: Sendable {
    private let downloadClient: any MapPackageDownloadClient
    private let archiveExtractor: any MapPackageArchiveExtractor
    private let parser = GarminIMGMetadataParser()

    init(
        downloadClient: any MapPackageDownloadClient = FoundationMapPackageDownloadClient(),
        archiveExtractor: any MapPackageArchiveExtractor = SystemZIPArchiveExtractor()
    ) {
        self.downloadClient = downloadClient
        self.archiveExtractor = archiveExtractor
    }

    func acquire(
        package: MapPackage,
        canonicalRegion: String? = nil,
        workspace requestedWorkspace: MapAcquisitionWorkspace? = nil,
        onStateChange: (@Sendable (MapAcquisitionState) -> Void)? = nil,
        onDownloadProgress: (@Sendable (MapDownloadProgress) -> Void)? = nil
    ) async throws -> ValidatedMapArtifact {
        let acquisitionWorkspace: MapAcquisitionWorkspace
        do {
            if let suppliedWorkspace = requestedWorkspace {
                acquisitionWorkspace = suppliedWorkspace
            } else {
                acquisitionWorkspace = try MapAcquisitionWorkspace.make()
            }
        } catch let error as MapAcquisitionError {
            onStateChange?(.failed)
            throw error
        } catch {
            onStateChange?(.failed)
            throw MapAcquisitionError.workspaceFailed(error.localizedDescription)
        }

        do {
            let artifact = try await acquireInWorkspace(
                package: package,
                canonicalRegion: canonicalRegion,
                workspace: acquisitionWorkspace,
                onStateChange: onStateChange,
                onDownloadProgress: onDownloadProgress
            )
            return artifact
        } catch {
            onStateChange?(.failed)
            try? acquisitionWorkspace.cleanup()
            throw error
        }
    }

    private func acquireInWorkspace(
        package: MapPackage,
        canonicalRegion: String?,
        workspace: MapAcquisitionWorkspace,
        onStateChange: (@Sendable (MapAcquisitionState) -> Void)?,
        onDownloadProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> ValidatedMapArtifact {
        state(.resolvingPackage, onStateChange)
        guard let sourceURL = package.downloadURL else {
            throw MapAcquisitionError.downloadFailed("The catalog package has no source URL.")
        }

        state(.downloading, onStateChange)
        let response: MapPackageDownloadResponse
        do {
            response = try await downloadClient.download(
                from: sourceURL,
                onProgress: { progress in
                    let totalBytes = progress.totalBytes > 0
                        ? progress.totalBytes
                        : package.expectedDownloadSizeBytes ?? 0
                    onDownloadProgress?(MapDownloadProgress(
                        bytesDownloaded: progress.bytesDownloaded,
                        totalBytes: totalBytes,
                        bytesPerSecond: progress.bytesPerSecond
                    ))
                }
            )
        } catch let error as MapAcquisitionError {
            throw error
        } catch {
            throw MapAcquisitionError.downloadFailed(error.localizedDescription)
        }

        guard (200...299).contains(response.statusCode) else {
            throw MapAcquisitionError.downloadFailed("Provider returned HTTP \(response.statusCode).")
        }

        state(.validatingDownload, onStateChange)
        let fileManager = FileManager.default
        guard fileManager.isReadableFile(atPath: response.temporaryFileURL.path) else {
            throw MapAcquisitionError.downloadIncomplete(expected: package.expectedDownloadSizeBytes, actual: 0)
        }

        do {
            try fileManager.copyItem(at: response.temporaryFileURL, to: workspace.downloadURL)
        } catch {
            throw MapAcquisitionError.downloadFailed("The downloaded file could not be stored safely.")
        }

        let downloadSize = try fileSize(of: workspace.downloadURL)
        guard downloadSize > 0 else {
            throw MapAcquisitionError.downloadIncomplete(
                expected: package.expectedDownloadSizeBytes,
                actual: downloadSize
            )
        }

        let format = try MapPackageFormat.detect(fileURL: workspace.downloadURL)
        let imgURL: URL
        switch format {
        case .rawIMG:
            imgURL = workspace.downloadURL
        case .zip:
            state(.extracting, onStateChange)
            try archiveExtractor.extract(
                archiveURL: workspace.downloadURL,
                to: workspace.extractionURL
            )
            try validateExtractedTree(at: workspace.extractionURL)
            state(.inspectingIMG, onStateChange)
            imgURL = try locateIMG(
                in: workspace.extractionURL,
                expectedIdentity: package.identity
            )
        }

        state(.validatingIdentity, onStateChange)
        let metadata = try metadata(for: imgURL)
        guard let expectedIdentity = package.identity else {
            throw MapAcquisitionError.invalidPackage(
                "The catalog package does not contain a valid provider and region identity."
            )
        }

        guard let actualIdentity = metadataIdentity(metadata), actualIdentity == expectedIdentity else {
            throw MapAcquisitionError.sourceIdentityMismatch(
                expected: expectedIdentity,
                actual: metadataIdentity(metadata)
            )
        }

        guard let actualVersion = metadata.version, actualVersion == package.version else {
            throw MapAcquisitionError.sourceVersionMismatch(
                expected: package.version,
                actual: metadata.version
            )
        }

        state(.hashing, onStateChange)
        let validatedSource: ValidatedMapSource
        do {
            validatedSource = try MapSourceValidator().validate(
                fileURL: imgURL,
                expectedPackage: package
            )
        } catch MapSourceValidationError.identityMismatch {
            throw MapAcquisitionError.sourceIdentityMismatch(
                expected: expectedIdentity,
                actual: metadataIdentity(metadata)
            )
        } catch MapSourceValidationError.versionMismatch {
            throw MapAcquisitionError.sourceVersionMismatch(
                expected: package.version,
                actual: metadata.version
            )
        } catch {
            throw MapAcquisitionError.invalidPackage("The Garmin IMG failed source validation.")
        }

        let targetFilename: String
        do {
            targetFilename = try TerentoManagedFilenameGenerator().filename(
                providerId: package.providerId,
                regionId: package.canonicalRegionId
            )
        } catch {
            throw MapAcquisitionError.invalidPackage("The managed target filename could not be generated.")
        }

        let artifact = ValidatedMapArtifact(
            provider: expectedIdentity.provider,
            region: expectedIdentity.region,
            canonicalRegion: canonicalRegion ?? canonicalRegionName(for: package),
            rawRelease: validatedSource.metadata.rawVersion ?? "",
            version: validatedSource.metadata.version ?? package.version,
            localIMGURL: imgURL,
            installSizeBytes: validatedSource.sizeBytes,
            sha256: validatedSource.sha256,
            sourcePackageURL: sourceURL,
            catalogPackageID: package.id,
            targetFilename: targetFilename,
            downloadSizeBytes: downloadSize,
            catalogDownloadSizeBytes: package.expectedDownloadSizeBytes,
            downloadSizeMatchesCatalog: package.expectedDownloadSizeBytes.map { $0 == downloadSize } ?? true,
            packageFormat: format
        )
        state(.validated, onStateChange)
        return artifact
    }

    private func locateIMG(
        in extractionDirectory: URL,
        expectedIdentity: MapIdentity?
    ) throws -> URL {
        let fileManager = FileManager.default
        guard let enumerator = fileManager.enumerator(
            at: extractionDirectory,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            throw MapAcquisitionError.noIMGFound
        }

        var candidates: [(url: URL, metadata: GarminIMGMetadata)] = []
        for case let url as URL in enumerator {
            let values = try? url.resourceValues(forKeys: [.isRegularFileKey])
            guard values?.isRegularFile == true,
                  url.pathExtension.lowercased() == "img",
                  let metadata = try? self.metadata(for: url) else {
                continue
            }
            candidates.append((url, metadata))
        }

        guard !candidates.isEmpty else {
            throw MapAcquisitionError.noIMGFound
        }

        let matching = candidates.filter { metadata in
            guard let expectedIdentity,
                  let actualIdentity = metadataIdentity(metadata.metadata) else {
                return false
            }
            return expectedIdentity == actualIdentity
        }

        if matching.count == 1 {
            return matching[0].url
        }
        if matching.count > 1 {
            throw MapAcquisitionError.ambiguousIMG
        }

        let actualIdentity = metadataIdentity(candidates[0].metadata)
        if let expectedIdentity {
            throw MapAcquisitionError.sourceIdentityMismatch(
                expected: expectedIdentity,
                actual: actualIdentity
            )
        }
        throw MapAcquisitionError.noIMGFound
    }

    private func validateExtractedTree(at extractionDirectory: URL) throws {
        let fileManager = FileManager.default
        guard let enumerator = fileManager.enumerator(
            at: extractionDirectory,
            includingPropertiesForKeys: [.isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        ) else {
            throw MapAcquisitionError.noIMGFound
        }

        let rootPath = extractionDirectory.standardizedFileURL.path
        for case let url as URL in enumerator {
            let standardizedPath = url.standardizedFileURL.path
            guard standardizedPath == rootPath
                || standardizedPath.hasPrefix(rootPath + "/") else {
                throw MapAcquisitionError.unsafeArchivePath(url.path)
            }

            let values = try? url.resourceValues(forKeys: [.isSymbolicLinkKey])
            if values?.isSymbolicLink == true {
                throw MapAcquisitionError.unsafeArchivePath(url.path)
            }
        }
    }

    private func metadata(for fileURL: URL) throws -> GarminIMGMetadata {
        let prefix = try MapPackageFormat.readPrefix(
            from: fileURL,
            maxLength: GarminIMGMetadataParser.prefixLength
        )
        guard let metadata = parser.parse(prefix) else {
            throw MapAcquisitionError.invalidPackage("The IMG header could not be parsed.")
        }
        return metadata
    }

    private func metadataIdentity(_ metadata: GarminIMGMetadata) -> MapIdentity? {
        MapIdentity(provider: metadata.provider, region: metadata.region)
    }

    private func fileSize(of url: URL) throws -> UInt64 {
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            guard let number = attributes[.size] as? NSNumber else {
                throw MapAcquisitionError.invalidPackage("The package size is unavailable.")
            }
            return number.uint64Value
        } catch let error as MapAcquisitionError {
            throw error
        } catch {
            throw MapAcquisitionError.invalidPackage("The package size is unavailable.")
        }
    }

    private func canonicalRegionName(for package: MapPackage) -> String {
        package.name
    }

    private func state(
        _ state: MapAcquisitionState,
        _ onStateChange: (@Sendable (MapAcquisitionState) -> Void)?
    ) {
        onStateChange?(state)
    }
}

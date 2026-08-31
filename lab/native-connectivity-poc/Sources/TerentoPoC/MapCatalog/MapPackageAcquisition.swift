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

enum CustomMapImportState: String, Equatable, Sendable {
    case idle
    case validating
    case ready
    case failed
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
    case acquisitionWithheld(MapAcquisitionAvailability)
    case downloadFailed(String)
    case providerUnavailable(providerId: String, statusCode: Int?)
    case downloadIncomplete(expected: UInt64?, actual: UInt64)
    case invalidPackage(String)
    case extractionFailed(String)
    case unsupportedPackageFormat
    case unsafeArchivePath(String)
    case sourceIdentityMismatch(expected: MapIdentity, actual: MapIdentity?)
    case sourceVersionMismatch(expected: MapVersion, actual: MapVersion?)
    case noIMGFound
    case ambiguousIMG
    case workspaceFailed(String)
    case untrustedSourceURL(String)
    case customMapNotConfirmed(String)

    var errorDescription: String? {
        switch self {
        case .acquisitionWithheld(let availability):
            return availability.detailedExplanation
        case .downloadFailed(let message):
            return "The map package could not be downloaded: \(message)"
        case .providerUnavailable:
            return "The selected map provider is currently down. Try again later."
        case .downloadIncomplete(let expected, let actual):
            if let expected {
                return "The map package is incomplete: expected \(expected) bytes, received \(actual)."
            }
            return "The map package is incomplete: received \(actual) bytes."
        case .invalidPackage(let message):
            return "The downloaded map package is invalid: \(message)"
        case .extractionFailed(let message):
            return "The map package could not be extracted: \(message)"
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
        case .untrustedSourceURL:
            return "The map provider address is not in Terento's reviewed HTTPS source list. Refresh the catalog and try again."
        case .customMapNotConfirmed(let message):
            return message
        }
    }
}

struct ReviewedProviderURLPolicy: Sendable {
    static let freizeitkarte = ReviewedProviderURLPolicy(
        allowedHosts: ["download.freizeitkarte-osm.de"]
    )

    static let openTopoMap = ReviewedProviderURLPolicy(
        allowedHosts: ["garmin.opentopomap.org"]
    )

    let allowedHosts: Set<String>

    init(allowedHosts: Set<String>) {
        self.allowedHosts = Set(allowedHosts.map { $0.lowercased() })
    }

    func validate(_ url: URL) throws {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == "https",
              let host = components.host?.lowercased(),
              allowedHosts.contains(host),
              components.user == nil,
              components.password == nil,
              components.port == nil || components.port == 443 else {
            throw MapAcquisitionError.untrustedSourceURL(url.absoluteString)
        }
    }
}

/// Source-host policy is selected from the package provider, never from a
/// global/default provider. A future provider adds its reviewed policy to
/// this registry without changing the acquisition pipeline.
struct ReviewedProviderURLPolicyRegistry: Sendable {
    static let bundled = ReviewedProviderURLPolicyRegistry(
        policies: [
            "freizeitkarte": .freizeitkarte,
            "opentopomap": .openTopoMap
        ]
    )

    private let policies: [String: ReviewedProviderURLPolicy]

    init(policies: [String: ReviewedProviderURLPolicy]) {
        self.policies = Dictionary(
            uniqueKeysWithValues: policies.map {
                (MapIdentity.normalizeProvider($0.key), $0.value)
            }
        )
    }

    func policy(for providerId: String) -> ReviewedProviderURLPolicy? {
        policies[MapIdentity.normalizeProvider(providerId)]
    }
}

struct MapProviderHealthProbeResult: Equatable, Sendable {
    let providerId: String
    let health: MapProviderHealth
    let statusCode: Int?
    let checkedAt: Date

    var isDown: Bool {
        health == .down
    }
}

protocol MapProviderHealthChecking: Sendable {
    func check(package: MapPackage) async -> MapProviderHealthProbeResult
}

struct NoopMapProviderHealthChecker: MapProviderHealthChecking, Sendable {
    func check(package: MapPackage) async -> MapProviderHealthProbeResult {
        MapProviderHealthProbeResult(
            providerId: package.providerId,
            health: .unknown,
            statusCode: nil,
            checkedAt: Date()
        )
    }
}

/// A bounded source check used only to improve an app download failure. It
/// does not download a map binary and does not persist provider health.
struct FoundationMapProviderHealthChecker: MapProviderHealthChecking, Sendable {
    private let sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry
    private let timeout: TimeInterval

    init(
        sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry = .bundled,
        timeout: TimeInterval = 10
    ) {
        self.sourcePolicyRegistry = sourcePolicyRegistry
        self.timeout = timeout
    }

    func check(package: MapPackage) async -> MapProviderHealthProbeResult {
        let unknown = MapProviderHealthProbeResult(
            providerId: package.providerId,
            health: .unknown,
            statusCode: nil,
            checkedAt: Date()
        )

        guard let sourceURL = package.downloadURL,
              let policy = sourcePolicyRegistry.policy(for: package.providerId) else {
            return unknown
        }

        do {
            try policy.validate(sourceURL)
            let response = try await request(
                sourceURL: sourceURL,
                policy: policy,
                method: "HEAD"
            )

            if response.statusCode == 405 || response.statusCode == 501 {
                let rangeResponse = try await request(
                    sourceURL: sourceURL,
                    policy: policy,
                    method: "GET",
                    range: "bytes=0-0"
                )
                return classify(response: rangeResponse, providerId: package.providerId)
            }
            return classify(response: response, providerId: package.providerId)
        } catch {
            return unknown
        }
    }

    private func classify(
        response: HealthHTTPResponse,
        providerId: String
    ) -> MapProviderHealthProbeResult {
        let health: MapProviderHealth
        switch response.statusCode {
        case 200...399:
            health = .healthy
        case 429, 404, 410:
            health = .degraded
        case 500...599:
            health = .down
        default:
            health = .unknown
        }

        return MapProviderHealthProbeResult(
            providerId: providerId,
            health: health,
            statusCode: response.statusCode,
            checkedAt: Date()
        )
    }

    private func request(
        sourceURL: URL,
        policy: ReviewedProviderURLPolicy,
        method: String,
        range: String? = nil
    ) async throws -> HealthHTTPResponse {
        var request = URLRequest(url: sourceURL)
        request.httpMethod = method
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = timeout
        if let range {
            request.setValue(range, forHTTPHeaderField: "Range")
        }

        let redirectDelegate = ReviewedProviderRedirectDelegate(policy: policy)
        let session = URLSession(
            configuration: .ephemeral,
            delegate: redirectDelegate,
            delegateQueue: nil
        )
        defer { session.finishTasksAndInvalidate() }

        let (_, response) = try await session.data(for: request)
        guard redirectDelegate.takeRejectedURL() == nil,
              let httpResponse = response as? HTTPURLResponse else {
            throw MapAcquisitionError.downloadFailed("The provider health response was invalid.")
        }
        if let finalURL = httpResponse.url {
            try policy.validate(finalURL)
        }
        return HealthHTTPResponse(statusCode: httpResponse.statusCode)
    }

    private struct HealthHTTPResponse: Sendable {
        let statusCode: Int
    }
}

private final class ReviewedProviderRedirectDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private let policy: ReviewedProviderURLPolicy
    private let lock = NSLock()
    private var rejectedURL: URL?

    init(policy: ReviewedProviderURLPolicy) {
        self.policy = policy
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        guard let url = request.url else {
            completionHandler(nil)
            return
        }

        do {
            try policy.validate(url)
            completionHandler(request)
        } catch {
            lock.lock()
            rejectedURL = url
            lock.unlock()
            completionHandler(nil)
        }
    }

    func takeRejectedURL() -> URL? {
        lock.lock()
        defer { lock.unlock() }
        return rejectedURL
    }
}

struct MapPackageDownloadResponse: Sendable, Equatable {
    let statusCode: Int
    let temporaryFileURL: URL
}

protocol MapPackageDownloadClient: Sendable {
    func download(from url: URL) async throws -> MapPackageDownloadResponse

    func download(
        package: MapPackage,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse

    func download(
        from url: URL,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse
}

extension MapPackageDownloadClient {
    func download(
        package: MapPackage,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        guard let sourceURL = package.downloadURL else {
            throw MapAcquisitionError.downloadFailed("The catalog package has no source URL.")
        }
        return try await download(from: sourceURL, onProgress: onProgress)
    }

    func download(
        from url: URL,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        try await download(from: url)
    }
}

struct FoundationMapPackageDownloadClient: MapPackageDownloadClient, Sendable {
    private let sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry
    private let directSourcePolicy: ReviewedProviderURLPolicy?

    init(
        sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry = .bundled,
        sourcePolicy: ReviewedProviderURLPolicy? = nil
    ) {
        self.sourcePolicyRegistry = sourcePolicyRegistry
        self.directSourcePolicy = sourcePolicy
    }

    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        try await download(from: url, onProgress: nil)
    }

    func download(
        package: MapPackage,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        guard let sourceURL = package.downloadURL else {
            throw MapAcquisitionError.downloadFailed("The catalog package has no source URL.")
        }
        guard let policy = sourcePolicyRegistry.policy(for: package.providerId) else {
            throw MapAcquisitionError.untrustedSourceURL(sourceURL.absoluteString)
        }
        return try await download(
            from: sourceURL,
            policy: policy,
            onProgress: onProgress
        )
    }

    func download(
        from url: URL,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        guard let directSourcePolicy else {
            throw MapAcquisitionError.untrustedSourceURL(url.absoluteString)
        }
        return try await download(
            from: url,
            policy: directSourcePolicy,
            onProgress: onProgress
        )
    }

    private func download(
        from url: URL,
        policy sourcePolicy: ReviewedProviderURLPolicy,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    ) async throws -> MapPackageDownloadResponse {
        try sourcePolicy.validate(url)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 120
        let redirectDelegate = ReviewedProviderRedirectDelegate(policy: sourcePolicy)
        let session = URLSession(
            configuration: .ephemeral,
            delegate: redirectDelegate,
            delegateQueue: nil
        )
        defer { session.finishTasksAndInvalidate() }

        do {
            let (bytes, response) = try await session.bytes(for: request)
            if let rejectedURL = redirectDelegate.takeRejectedURL() {
                throw MapAcquisitionError.untrustedSourceURL(rejectedURL.absoluteString)
            }
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MapAcquisitionError.downloadFailed("The provider returned no HTTP response.")
            }
            if let finalURL = httpResponse.url {
                try sourcePolicy.validate(finalURL)
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
            throw MapAcquisitionError.extractionFailed("The ZIP extractor could not be started.")
        }

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let message = String(
                data: errorPipe.fileHandleForReading.readDataToEndOfFile(),
                encoding: .utf8
            )?.trimmingCharacters(in: .whitespacesAndNewlines)
            throw MapAcquisitionError.extractionFailed(
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
            throw MapAcquisitionError.extractionFailed("The ZIP inspector could not be started.")
        }

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw MapAcquisitionError.extractionFailed("The ZIP archive could not be inspected.")
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
    let customIMGURL: URL
    let extractionURL: URL

    init(rootURL: URL) throws {
        self.rootURL = rootURL
        self.downloadURL = rootURL.appendingPathComponent("package.download")
        self.customIMGURL = rootURL.appendingPathComponent("custom-map.img")
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
    let sourceKind: MapSourceKind
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

    init(
        provider: String,
        region: String,
        canonicalRegion: String,
        rawRelease: String,
        version: MapVersion,
        localIMGURL: URL,
        installSizeBytes: UInt64,
        sha256: String,
        sourcePackageURL: URL,
        catalogPackageID: String,
        targetFilename: String,
        downloadSizeBytes: UInt64,
        catalogDownloadSizeBytes: UInt64?,
        downloadSizeMatchesCatalog: Bool,
        packageFormat: MapPackageFormat,
        sourceKind: MapSourceKind = .provider
    ) {
        self.sourceKind = sourceKind
        self.provider = provider
        self.region = region
        self.canonicalRegion = canonicalRegion
        self.rawRelease = rawRelease
        self.version = version
        self.localIMGURL = localIMGURL
        self.installSizeBytes = installSizeBytes
        self.sha256 = sha256
        self.sourcePackageURL = sourcePackageURL
        self.catalogPackageID = catalogPackageID
        self.targetFilename = targetFilename
        self.downloadSizeBytes = downloadSizeBytes
        self.catalogDownloadSizeBytes = catalogDownloadSizeBytes
        self.downloadSizeMatchesCatalog = downloadSizeMatchesCatalog
        self.packageFormat = packageFormat
    }

    /// Bridge to the provider-neutral lifecycle seam. The legacy fields stay
    /// available for the current FZK write coordinator while later sources
    /// can hand the same neutral artifact shape to the shared pipeline.
    var mapArtifact: MapArtifact {
        MapArtifact(
            id: catalogPackageID,
            source: sourceKind,
            kind: .main,
            required: true,
            providerId: provider,
            providerRegionId: region,
            canonicalRegionId: canonicalRegion,
            version: version,
            sourceURL: sourcePackageURL,
            localURL: localIMGURL,
            sizeBytes: installSizeBytes,
            checksum: sha256,
            validationState: .validated
        )
    }
}

struct CustomMapImportWarning: Identifiable, Equatable, Sendable {
    let filename: String
    let message: String

    var id: String { filename }
}

struct CustomMapImportRisk: Identifiable, Equatable, Sendable {
    let filename: String
    let message: String

    var id: String { filename }
}

struct CustomMapImportCandidate: Identifiable, Equatable, Sendable {
    let id: String
    let package: MapPackage
    let artifact: ValidatedMapArtifact
    let originalFilename: String
    let metadata: GarminIMGMetadata
    let workspaceRootURL: URL

    var sizeBytes: UInt64 { artifact.installSizeBytes }
}

/// Prepares a user-selected raw IMG in a private cache workspace. The file is
/// never executed, uploaded, or treated as an archive. Header parsing can
/// establish only that the file looks like a Garmin IMG; it cannot prove map
/// provenance, map quality, or that arbitrary embedded bytes are malware-free.
struct CustomMapSourceAcquirer: Sendable {
    private static let customProviderID = "custom"
    private static let fallbackVersion = MapVersion(year: 2000, month: 1)!
    private let workspaceFactory: @Sendable () throws -> MapAcquisitionWorkspace

    init(
        workspaceFactory: @escaping @Sendable () throws -> MapAcquisitionWorkspace = {
            try MapAcquisitionWorkspace.make()
        }
    ) {
        self.workspaceFactory = workspaceFactory
    }

    func prepare(fileURL: URL) throws -> CustomMapImportCandidate {
        let didStartSecurityScopedAccess = fileURL.startAccessingSecurityScopedResource()
        defer {
            if didStartSecurityScopedAccess {
                fileURL.stopAccessingSecurityScopedResource()
            }
        }

        try validateInputFile(fileURL)
        let workspace = try workspaceFactory()

        do {
            try FileManager.default.copyItem(
                at: fileURL,
                to: workspace.customIMGURL
            )
            let validated = try MapSourceValidator().validateCustom(
                fileURL: workspace.customIMGURL
            )
            let package = try makePackage(
                validated: validated
            )
            let artifact = try makeArtifact(
                package: package,
                originalFileURL: fileURL,
                validated: validated,
                workspaceURL: workspace.customIMGURL
            )
            return CustomMapImportCandidate(
                id: package.id,
                package: package,
                artifact: artifact,
                originalFilename: fileURL.lastPathComponent,
                metadata: validated.metadata,
                workspaceRootURL: workspace.rootURL
            )
        } catch let error as MapAcquisitionError {
            try? workspace.cleanup()
            throw error
        } catch let error as MapSourceValidationError {
            try? workspace.cleanup()
            if error == .invalidIMG {
                throw MapAcquisitionError.customMapNotConfirmed(
                    "Terento could not confirm that \(fileURL.lastPathComponent) is a Garmin map image. No file was prepared for installation."
                )
            }
            throw MapAcquisitionError.invalidPackage(
                "The selected IMG could not be safely checked."
            )
        } catch {
            try? workspace.cleanup()
            throw MapAcquisitionError.invalidPackage(
                "The selected IMG could not be safely prepared."
            )
        }
    }

    /// Re-checks the cached copy immediately before preflight. This protects
    /// the install path from a time-of-check/time-of-use change in the local
    /// workspace and returns the already validated artifact only when its
    /// content is still identical.
    func revalidate(_ candidate: CustomMapImportCandidate) throws -> ValidatedMapArtifact {
        try validateInputFile(candidate.artifact.localIMGURL)
        do {
            let validated = try MapSourceValidator().validateCustom(
                fileURL: candidate.artifact.localIMGURL
            )
            guard validated.sizeBytes == candidate.artifact.installSizeBytes else {
                throw MapAcquisitionError.invalidPackage(
                    "The selected custom map changed after it was checked."
                )
            }
            guard validated.sha256.caseInsensitiveCompare(candidate.artifact.sha256) == .orderedSame else {
                throw MapAcquisitionError.invalidPackage(
                    "The selected custom map changed after it was checked."
                )
            }
            return candidate.artifact
        } catch is MapSourceValidationError {
            throw MapAcquisitionError.invalidPackage(
                "The selected custom map is no longer readable or valid."
            )
        }
    }

    private func validateInputFile(_ fileURL: URL) throws {
        guard fileURL.isFileURL,
              fileURL.pathExtension.caseInsensitiveCompare("img") == .orderedSame else {
            throw MapAcquisitionError.invalidPackage(
                "Choose a raw Garmin .img map file. Installer packages and archives are not accepted here."
            )
        }

        let values: URLResourceValues
        do {
            values = try fileURL.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        } catch {
            throw MapAcquisitionError.invalidPackage(
                "The selected file could not be inspected safely."
            )
        }

        guard values.isRegularFile == true,
              values.isSymbolicLink != true,
              FileManager.default.isReadableFile(atPath: fileURL.path) else {
            throw MapAcquisitionError.invalidPackage(
                "The selected file is not a readable regular file."
            )
        }
    }

    private func makePackage(
        validated: ValidatedMapSource
    ) throws -> MapPackage {
        let contentToken = String(validated.sha256.prefix(24))
        let regionToken = "img_\(contentToken)"
        let packageID = "custom-\(contentToken)"
        let version = validated.metadata.version ?? Self.fallbackVersion
        let artifactID = "\(packageID)-main"

        return MapPackage(
            id: packageID,
            providerId: Self.customProviderID,
            regionId: regionToken,
            name: "Custom map",
            version: version,
            sizeBytes: validated.sizeBytes,
            sourceURL: nil,
            releaseDate: validated.metadata.rawVersion,
            identifier: validated.sha256,
            downloadSizeBytes: validated.sizeBytes,
            installSizeBytes: validated.sizeBytes,
            providerRegionId: regionToken,
            canonicalRegionId: regionToken,
            regionKind: .custom,
            releaseMetadata: validated.metadata.rawVersion.map {
                MapReleaseMetadata(
                    releaseId: $0,
                    versionLabel: $0,
                    generatedAt: nil,
                    sourceUpdatedAt: nil
                )
            },
            artifacts: [
                MapArtifact(
                    id: artifactID,
                    source: .custom,
                    kind: .main,
                    required: true,
                    providerId: Self.customProviderID,
                    providerRegionId: regionToken,
                    canonicalRegionId: regionToken,
                    version: version,
                    sourceURL: nil,
                    localURL: nil,
                    sizeBytes: validated.sizeBytes,
                    checksum: validated.sha256,
                    validationState: .validated
                )
            ],
            sourceKind: .custom
        )
    }

    private func makeArtifact(
        package: MapPackage,
        originalFileURL: URL,
        validated: ValidatedMapSource,
        workspaceURL: URL
    ) throws -> ValidatedMapArtifact {
        let targetFilename = try TerentoManagedFilenameGenerator().filename(
            providerId: package.providerId,
            regionId: package.canonicalRegionId
        )
        return ValidatedMapArtifact(
            provider: Self.customProviderID,
            region: package.regionId,
            canonicalRegion: package.canonicalRegionId,
            rawRelease: validated.metadata.rawVersion ?? "",
            version: package.version,
            localIMGURL: workspaceURL,
            installSizeBytes: validated.sizeBytes,
            sha256: validated.sha256,
            sourcePackageURL: originalFileURL,
            catalogPackageID: package.id,
            targetFilename: targetFilename,
            downloadSizeBytes: validated.sizeBytes,
            catalogDownloadSizeBytes: nil,
            downloadSizeMatchesCatalog: true,
            packageFormat: .rawIMG,
            sourceKind: .custom
        )
    }
}

struct MapPackageAcquirer: Sendable {
    private let downloadClient: any MapPackageDownloadClient
    private let providerHealthChecker: any MapProviderHealthChecking
    private let archiveExtractor: any MapPackageArchiveExtractor
    private let workspaceFactory: @Sendable () throws -> MapAcquisitionWorkspace
    private let parser = GarminIMGMetadataParser()

    init(
        downloadClient: any MapPackageDownloadClient = FoundationMapPackageDownloadClient(),
        providerHealthChecker: any MapProviderHealthChecking = NoopMapProviderHealthChecker(),
        archiveExtractor: any MapPackageArchiveExtractor = SystemZIPArchiveExtractor(),
        workspaceFactory: @escaping @Sendable () throws -> MapAcquisitionWorkspace = {
            try MapAcquisitionWorkspace.make()
        }
    ) {
        self.downloadClient = downloadClient
        self.providerHealthChecker = providerHealthChecker
        self.archiveExtractor = archiveExtractor
        self.workspaceFactory = workspaceFactory
    }

    func acquire(
        package: MapPackage,
        canonicalRegion: String? = nil,
        workspace requestedWorkspace: MapAcquisitionWorkspace? = nil,
        onStateChange: (@Sendable (MapAcquisitionState) -> Void)? = nil,
        onDownloadProgress: (@Sendable (MapDownloadProgress) -> Void)? = nil
    ) async throws -> ValidatedMapArtifact {
        state(.resolvingPackage, onStateChange)
        do {
            try MapPackageAcquisitionPolicyResolver().validate(package: package)
        } catch let error as MapAcquisitionPolicyError {
            onStateChange?(.failed)
            throw MapAcquisitionError.acquisitionWithheld(error.availability)
        }

        let acquisitionWorkspace: MapAcquisitionWorkspace
        do {
            if let suppliedWorkspace = requestedWorkspace {
                acquisitionWorkspace = suppliedWorkspace
            } else {
                acquisitionWorkspace = try workspaceFactory()
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
        guard let sourceURL = package.downloadURL else {
            throw MapAcquisitionError.downloadFailed("The catalog package has no source URL.")
        }

        state(.downloading, onStateChange)
        let response: MapPackageDownloadResponse
        do {
            response = try await downloadClient.download(
                package: package,
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
            throw await providerAwareDownloadError(error, package: package)
        } catch {
            throw await providerAwareDownloadError(
                .downloadFailed(error.localizedDescription),
                package: package
            )
        }

        guard (200...299).contains(response.statusCode) else {
            throw await providerAwareDownloadError(
                .downloadFailed("Provider returned HTTP \(response.statusCode)."),
                package: package
            )
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
        guard let metadata = parser.parse(
            prefix,
            filename: fileURL.lastPathComponent
        ) else {
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

    private func providerAwareDownloadError(
        _ error: MapAcquisitionError,
        package: MapPackage
    ) async -> MapAcquisitionError {
        guard shouldProbeProvider(for: error) else {
            return error
        }

        let probe = await providerHealthChecker.check(package: package)
        guard probe.isDown else {
            return error
        }
        return .providerUnavailable(
            providerId: package.providerId,
            statusCode: probe.statusCode
        )
    }

    private func shouldProbeProvider(for error: MapAcquisitionError) -> Bool {
        switch error {
        case .downloadFailed, .downloadIncomplete:
            return true
        case .acquisitionWithheld, .providerUnavailable, .invalidPackage,
             .extractionFailed, .unsupportedPackageFormat, .unsafeArchivePath,
             .sourceIdentityMismatch, .sourceVersionMismatch, .noIMGFound,
             .ambiguousIMG, .workspaceFailed, .untrustedSourceURL,
             .customMapNotConfirmed:
            return false
        }
    }
}

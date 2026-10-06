import CryptoKit
import Darwin
import Foundation
import os

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
    case providerConnectionFailed(providerId: String, code: URLError.Code)
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
    /// The Mac's volume cannot hold the download and its extraction.
    case insufficientMacStorage(requiredBytes: UInt64?)

    var userMessage: String {
        switch self {
        case .acquisitionWithheld(let availability):
            return availability.detailedExplanation
                ?? "This map is not available for download in Terento."
        case .downloadFailed:
            return "The map could not be downloaded. Check your connection and try again."
        case .providerUnavailable(let providerID, let status):
            let name = MapProviderDisplay.downloadName(providerID)
            switch status {
            case 404, 410:
                return "The selected map is unavailable from \(name). Refresh the map list and try again."
            case 429:
                return "\(name) is limiting downloads right now. Try again later."
            case 401, 403:
                return "\(name) refused the map download. Try again later."
            case .some(500...599), .none:
                return "\(name)’s download server is temporarily unavailable. Try again later."
            default:
                return "\(name) could not provide the selected map. Refresh the map list and try again."
            }
        case .providerConnectionFailed(let providerID, let code):
            let name = MapProviderDisplay.downloadName(providerID)
            if code == .notConnectedToInternet {
                return "Your Mac is offline. Connect to the internet to download from \(name), then try again."
            }
            if code == .timedOut {
                return "\(name)’s download server did not respond in time. Check your connection or try again later."
            }
            return "Cannot connect to \(name)’s download server. Check your connection or try again later."
        case .downloadIncomplete:
            return "The map download did not complete. Try again."
        case .invalidPackage, .extractionFailed, .unsupportedPackageFormat,
             .unsafeArchivePath, .noIMGFound, .ambiguousIMG:
            return "The downloaded map could not be verified and opened safely. Refresh the catalog and try again."
        case .sourceIdentityMismatch:
            return "The downloaded map does not match the selected provider and region. Refresh the catalog and try again."
        case .sourceVersionMismatch:
            return "The downloaded map release does not match the catalog. Refresh the catalog and try again."
        case .workspaceFailed:
            return "Terento could not prepare the map on this Mac. Check available storage and try again."
        case .untrustedSourceURL:
            return "The map provider address could not be verified. Refresh the catalog and try again."
        case .customMapNotConfirmed(let message):
            return message
        case .insufficientMacStorage(let requiredBytes):
            return MacStorageCheck.userMessage(requiredBytes: requiredBytes)
        }
    }

    var errorDescription: String? {
        switch self {
        case .acquisitionWithheld(let availability):
            return availability.detailedExplanation
        case .downloadFailed(let message):
            return "The map package could not be downloaded: \(message)"
        case .providerUnavailable, .providerConnectionFailed:
            return userMessage
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
        case .insufficientMacStorage:
            return userMessage
        }
    }
}

/// Mac-side storage for downloads. A download needs room for the package,
/// its extraction and the validated map, so about 2.5 times its size is
/// required before the download starts.
enum MacStorageCheck {
    static let downloadMultiplier = 2.5

    static func requiredBytes(forDownloadBytes bytes: UInt64) -> UInt64 {
        UInt64((Double(bytes) * downloadMultiplier).rounded(.up))
    }

    static func userMessage(requiredBytes: UInt64?) -> String {
        guard let requiredBytes, requiredBytes > 0 else {
            return "Your Mac doesn't have enough free space. Free up space and try again."
        }
        let formatted = ByteCountFormatter.string(fromByteCount: Int64(clamping: requiredBytes), countStyle: .file)
        return "Your Mac doesn't have enough free space (needs \(formatted)). Free up space and try again."
    }

    /// Space usable for important data on the volume holding `url`.
    static func availableBytes(at url: URL) -> UInt64? {
        let values = try? url.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        return values?.volumeAvailableCapacityForImportantUsage.map { UInt64(max(0, $0)) }
    }

    /// Throws before any download when a known size cannot fit.
    static func preflight(downloadBytes: UInt64, locations: [URL],
                          available: (URL) -> UInt64? = availableBytes(at:)) throws {
        guard downloadBytes > 0 else { return }
        let required = requiredBytes(forDownloadBytes: downloadBytes)
        for location in locations {
            if let free = available(location), free < required {
                throw MapAcquisitionError.insufficientMacStorage(requiredBytes: required)
            }
        }
    }

    static func isOutOfSpace(_ error: Error) -> Bool {
        let nsError = error as NSError
        if nsError.domain == NSCocoaErrorDomain, nsError.code == NSFileWriteOutOfSpaceError { return true }
        if nsError.domain == NSPOSIXErrorDomain, nsError.code == Int(ENOSPC) { return true }
        if let underlying = nsError.userInfo[NSUnderlyingErrorKey] as? Error {
            return isOutOfSpace(underlying)
        }
        return false
    }
}

struct ReviewedProviderURLPolicy: Sendable {
    static let freizeitkarte = ReviewedProviderURLPolicy(
        allowedHosts: ["download.freizeitkarte-osm.de"]
    )

    static let openTopoMap = ReviewedProviderURLPolicy(
        allowedHosts: ["garmin.opentopomap.org"]
    )

    static let bbbike = ReviewedProviderURLPolicy(allowedHosts: ["data.bbbike.org"])

    static let mapRando = ReviewedProviderURLPolicy(allowedHosts: ["ravenfeld.fr"])

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
        if host == "data.bbbike.org" {
            let pathParts = url.path.lowercased().split(separator: "/")
            guard !pathParts.contains("russia"), !pathParts.contains("crimea") else {
                throw MapAcquisitionError.untrustedSourceURL(url.absoluteString)
            }
            let isExactExample = BBBikeProviderAdapter.exampleRegions.contains { region in
                BBBikeMapType.allCases.contains { type in
                    BBBikeProviderAdapter.isReviewedSourcePath(url.path, sourceRegion: region, type: type.rawValue)
                }
            }
            guard components.query == nil, components.fragment == nil,
                  (isExactExample || url.path.range(of: #"^/osm/garmin/region/[a-z0-9/-]+/[a-z0-9-]+\.osm\.garmin-(?:bbbike|ontrail)-latin1\.zip$"#, options: .regularExpression) != nil),
                  !url.absoluteString.contains("%"), !url.path.contains("..") else {
                throw MapAcquisitionError.untrustedSourceURL(url.absoluteString)
            }
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
            "opentopomap": .openTopoMap,
            "maprando": .mapRando,
            "bbbike": .bbbike
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
            guard !policy.allowedHosts.contains("data.bbbike.org") else {
                throw MapAcquisitionError.untrustedSourceURL(url.absoluteString)
            }
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

/// Session delegate for one download: applies the reviewed redirect policy,
/// validates the response before the body is stored, writes body chunks to
/// the local file and reports progress. It never follows an unreviewed host.
private final class StreamingDownloadDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let redirectDelegate: ReviewedProviderRedirectDelegate
    private let fileHandle: FileHandle
    private let maximumBytes: UInt64?
    private let validateResponse: (HTTPURLResponse) throws -> Void
    private let onProgress: (@Sendable (MapDownloadProgress) -> Void)?
    private let lock = NSLock()
    private var response: HTTPURLResponse?
    private var receivedBytes: UInt64 = 0
    private var reportedBytes: UInt64 = 0
    private var expectedBytes: UInt64 = 0
    private var failure: Error?
    private var speedEstimator = TransferSpeedEstimator()
    private var continuation: CheckedContinuation<HTTPURLResponse, Error>?
    /// The partial file this request resumes, if any. A 206 must continue
    /// exactly at its end with the same validator and total size; a 200 means
    /// the server sent the whole file again and the partial is replaced.
    private let resuming: MapPartialDownload?

    init(redirectDelegate: ReviewedProviderRedirectDelegate, fileHandle: FileHandle, maximumBytes: UInt64?,
         validateResponse: @escaping (HTTPURLResponse) throws -> Void,
         onProgress: (@Sendable (MapDownloadProgress) -> Void)?,
         resuming: MapPartialDownload? = nil) {
        self.redirectDelegate = redirectDelegate
        self.fileHandle = fileHandle
        self.maximumBytes = maximumBytes
        self.validateResponse = validateResponse
        self.onProgress = onProgress
        self.resuming = resuming
    }

    /// What the server promised about this download, for keeping a partial
    /// file after a failure or cancellation.
    func resumablePartial(fileURL: URL, sourceURL: URL) -> MapPartialDownload? {
        lock.withLock {
            guard let response,
                  receivedBytes >= MapDownloadResumeStore.minimumResumableBytes,
                  expectedBytes > receivedBytes else { return nil }
            return MapPartialDownload.eligible(response: response, sourceURL: sourceURL, fileURL: fileURL,
                                               bytes: receivedBytes, totalBytes: expectedBytes)
        }
    }

    func run(request: URLRequest, session: URLSession) async throws -> HTTPURLResponse {
        let task = session.dataTask(with: request)
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                lock.withLock { self.continuation = continuation }
                if Task.isCancelled { task.cancel() }
                task.resume()
            }
        } onCancel: {
            task.cancel()
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        redirectDelegate.urlSession(session, task: task, willPerformHTTPRedirection: response,
                                    newRequest: request, completionHandler: completionHandler)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        do {
            if let rejectedURL = redirectDelegate.takeRejectedURL() {
                throw MapAcquisitionError.untrustedSourceURL(rejectedURL.absoluteString)
            }
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MapAcquisitionError.downloadFailed("The provider returned no HTTP response.")
            }
            try validateResponse(httpResponse)
            var resumedAt: UInt64?
            if let resuming {
                switch httpResponse.statusCode {
                case 206:
                    guard resuming.accepts(partialResponse: httpResponse) else {
                        throw MapDownloadResumeRejected()
                    }
                    resumedAt = resuming.bytes
                case 200:
                    // If-Range did not match: the full current file follows.
                    try fileHandle.truncate(atOffset: 0)
                default:
                    throw MapDownloadResumeRejected()
                }
            }
            lock.withLock {
                self.response = httpResponse
                if let resumedAt, let resuming {
                    receivedBytes = resumedAt
                    reportedBytes = resumedAt
                    expectedBytes = resuming.totalBytes
                } else {
                    expectedBytes = httpResponse.expectedContentLength > 0 ? UInt64(httpResponse.expectedContentLength) : 0
                }
            }
            completionHandler(.allow)
        } catch {
            record(error)
            completionHandler(.cancel)
        }
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        let progress: MapDownloadProgress? = lock.withLock {
            guard failure == nil else { return nil }
            if let maximumBytes, receivedBytes + UInt64(data.count) > maximumBytes {
                failure = MapAcquisitionError.invalidPackage("The BBBike source exceeded its reviewed size.")
                return nil
            }
            do {
                try fileHandle.write(contentsOf: data)
            } catch {
                failure = error
                return nil
            }
            receivedBytes += UInt64(data.count)
            // Keep the previous cadence: at most one update per 64 KiB.
            guard receivedBytes - reportedBytes >= 64 * 1024 else { return nil }
            reportedBytes = receivedBytes
            return MapDownloadProgress(bytesDownloaded: receivedBytes, totalBytes: expectedBytes,
                                       bytesPerSecond: speedEstimator.update(bytes: receivedBytes))
        }
        if lock.withLock({ failure != nil }) {
            dataTask.cancel()
            return
        }
        if let progress { onProgress?(progress) }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let outcome: Result<HTTPURLResponse, Error> = lock.withLock {
            if let failure { return .failure(failure) }
            if let error { return .failure(error) }
            guard let response else {
                return .failure(MapAcquisitionError.downloadFailed("The provider returned no HTTP response."))
            }
            return .success(response)
        }
        if case .success = outcome {
            let final: MapDownloadProgress = lock.withLock {
                MapDownloadProgress(bytesDownloaded: receivedBytes, totalBytes: expectedBytes,
                                    bytesPerSecond: speedEstimator.update(bytes: receivedBytes))
            }
            onProgress?(final)
        }
        let continuation = lock.withLock { () -> CheckedContinuation<HTTPURLResponse, Error>? in
            defer { self.continuation = nil }
            return self.continuation
        }
        continuation?.resume(with: outcome)
    }

    private func record(_ error: Error) {
        lock.withLock { if failure == nil { failure = error } }
    }
}

/// Identifies a partial provider download: the catalog package, its
/// artifact and the exact reviewed source URL. The server validator is kept
/// with the partial file and must still match when the download resumes.
struct MapDownloadResumeKey: Hashable, Sendable {
    let packageID: String
    let artifactID: String
    let sourceURL: String
}

/// A strong validator from the provider: an ETag that is not weak, or a
/// Last-Modified date. It is sent as `If-Range`.
struct MapDownloadValidator: Equatable, Sendable {
    let etag: String?
    let lastModified: String?

    var ifRangeValue: String? { etag ?? lastModified }
}

/// Thrown when a resumed response cannot continue the partial file; the
/// partial file is discarded and the download restarts from zero.
struct MapDownloadResumeRejected: Error {}

/// Bytes already downloaded for one source, kept after a failure or
/// cancellation so Try again can continue with `Range` and `If-Range`.
/// Final source validation (size, identity, version, SHA-256, BBBike proof)
/// is unchanged and always runs on the completed file.
struct MapPartialDownload: Equatable, Sendable {
    let fileURL: URL
    let bytes: UInt64
    let totalBytes: UInt64
    let validator: MapDownloadValidator
    /// The host that served the bytes; a resume must come from it.
    let host: String
    var expiresAt: Date = .distantFuture

    /// A partial download is kept only when the server advertised byte ranges
    /// (or already answered one), sent a strong validator, served the file
    /// without content encoding and was not redirected to another host.
    static func eligible(response: HTTPURLResponse, sourceURL: URL, fileURL: URL,
                         bytes: UInt64, totalBytes: UInt64) -> MapPartialDownload? {
        guard let sourceHost = sourceURL.host?.lowercased(),
              response.url?.host?.lowercased() == sourceHost,
              hasIdentityEncoding(response),
              bytes > 0, totalBytes > bytes else { return nil }
        switch response.statusCode {
        case 200:
            let ranges = response.value(forHTTPHeaderField: "Accept-Ranges")?.lowercased()
                .split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) } ?? []
            guard ranges.contains("bytes") else { return nil }
        case 206:
            break
        default:
            return nil
        }
        guard let validator = strongValidator(response) else { return nil }
        return MapPartialDownload(fileURL: fileURL, bytes: bytes, totalBytes: totalBytes,
                                  validator: validator, host: sourceHost)
    }

    /// A 206 continues this file only from its exact end, with the same
    /// validator, total size and host.
    func accepts(partialResponse response: HTTPURLResponse) -> Bool {
        guard response.statusCode == 206,
              response.url?.host?.lowercased() == host,
              Self.hasIdentityEncoding(response),
              let range = Self.contentRange(response),
              range.start == bytes, range.total == totalBytes, range.end == totalBytes - 1 else { return false }
        if response.expectedContentLength >= 0,
           UInt64(response.expectedContentLength) != totalBytes - bytes { return false }
        if let etag = validator.etag {
            return response.value(forHTTPHeaderField: "ETag") == etag
        }
        return response.value(forHTTPHeaderField: "Last-Modified") == validator.lastModified
    }

    static func strongValidator(_ response: HTTPURLResponse) -> MapDownloadValidator? {
        let etag = response.value(forHTTPHeaderField: "ETag")?.trimmingCharacters(in: .whitespaces)
        let strongETag = etag.flatMap { $0.isEmpty || $0.hasPrefix("W/") ? nil : $0 }
        let lastModified = response.value(forHTTPHeaderField: "Last-Modified")?
            .trimmingCharacters(in: .whitespaces)
        let modified = lastModified.flatMap { $0.isEmpty ? nil : $0 }
        guard strongETag != nil || modified != nil else { return nil }
        return MapDownloadValidator(etag: strongETag, lastModified: strongETag == nil ? modified : nil)
    }

    private static func hasIdentityEncoding(_ response: HTTPURLResponse) -> Bool {
        let encoding = response.value(forHTTPHeaderField: "Content-Encoding")?
            .trimmingCharacters(in: .whitespaces).lowercased()
        return encoding == nil || encoding == "" || encoding == "identity"
    }

    /// Parses `bytes <start>-<end>/<total>`.
    static func contentRange(_ response: HTTPURLResponse) -> (start: UInt64, end: UInt64, total: UInt64)? {
        guard let value = response.value(forHTTPHeaderField: "Content-Range")?
                .trimmingCharacters(in: .whitespaces),
              value.lowercased().hasPrefix("bytes ") else { return nil }
        let spec = value.dropFirst("bytes ".count)
        let parts = spec.split(separator: "/", maxSplits: 1)
        guard parts.count == 2, let total = UInt64(parts[1]) else { return nil }
        let bounds = parts[0].split(separator: "-", maxSplits: 1)
        guard bounds.count == 2, let start = UInt64(bounds[0]), let end = UInt64(bounds[1]),
              start <= end, end < total else { return nil }
        return (start, end, total)
    }
}

/// Partial downloads kept in memory for this app session, with the same
/// 30-minute lifetime as retained validated artifacts. Files stay in the
/// temporary directory with the scavenged download prefix, so a crash leaves
/// nothing behind after the next launch; quitting removes them.
final class MapDownloadResumeStore: @unchecked Sendable {
    static let shared = MapDownloadResumeStore()
    static let lifetime: TimeInterval = 30 * 60
    /// Shorter downloads are cheaper to restart than to resume.
    static let minimumResumableBytes: UInt64 = 1024 * 1024

    private let lock = NSLock()
    private var entries: [MapDownloadResumeKey: MapPartialDownload] = [:]
    private let now: @Sendable () -> Date

    init(now: @escaping @Sendable () -> Date = { Date() }) {
        self.now = now
    }

    var count: Int { lock.withLock { entries.count } }

    func keep(_ partial: MapPartialDownload, for key: MapDownloadResumeKey) {
        var stored = partial
        stored.expiresAt = now().addingTimeInterval(Self.lifetime)
        let removed: [URL] = lock.withLock {
            var stale = expiredUnlocked()
            if let previous = entries[key], previous.fileURL != partial.fileURL { stale.append(previous.fileURL) }
            entries[key] = stored
            return stale
        }
        removed.forEach { try? FileManager.default.removeItem(at: $0) }
    }

    /// Removes and returns the partial file for `key` when it is still fresh
    /// and exactly as long as recorded.
    func take(_ key: MapDownloadResumeKey) -> MapPartialDownload? {
        let (entry, stale): (MapPartialDownload?, [URL]) = lock.withLock {
            let stale = expiredUnlocked()
            return (entries.removeValue(forKey: key), stale)
        }
        stale.forEach { try? FileManager.default.removeItem(at: $0) }
        guard let entry else { return nil }
        let values = try? entry.fileURL.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values?.isRegularFile == true, values?.isSymbolicLink != true,
              values?.fileSize.map(UInt64.init) == entry.bytes else {
            try? FileManager.default.removeItem(at: entry.fileURL)
            return nil
        }
        return entry
    }

    /// Quitting removes every partial download.
    func purgeAll() {
        let files: [URL] = lock.withLock {
            defer { entries.removeAll() }
            return entries.values.map(\.fileURL)
        }
        files.forEach { try? FileManager.default.removeItem(at: $0) }
    }

    private func expiredUnlocked() -> [URL] {
        let current = now()
        let expired = entries.filter { $0.value.expiresAt <= current }
        for key in expired.keys { entries[key] = nil }
        return expired.values.map(\.fileURL)
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
    private let sessionConfiguration: @Sendable () -> URLSessionConfiguration
    private let resumeStore: MapDownloadResumeStore?

    init(
        sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry = .bundled,
        sourcePolicy: ReviewedProviderURLPolicy? = nil,
        sessionConfiguration: @escaping @Sendable () -> URLSessionConfiguration = { .ephemeral },
        resumeStore: MapDownloadResumeStore? = .shared
    ) {
        self.sourcePolicyRegistry = sourcePolicyRegistry
        self.directSourcePolicy = sourcePolicy
        self.sessionConfiguration = sessionConfiguration
        self.resumeStore = resumeStore
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
            onProgress: onProgress,
            sourceProof: package.mainArtifact?.sourceProof,
            resumeKey: MapDownloadResumeKey(packageID: package.id,
                                            artifactID: package.mainArtifact?.id ?? package.id,
                                            sourceURL: sourceURL.absoluteString)
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
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?,
        sourceProof: BBBikeSourceProof? = nil,
        resumeKey: MapDownloadResumeKey? = nil
    ) async throws -> MapPackageDownloadResponse {
        try sourcePolicy.validate(url)
        // BBBike downloads are bound to an exact source proof and are not resumed.
        let key = sourceProof == nil ? resumeKey : nil
        if let key, let store = resumeStore, let partial = store.take(key) {
            do {
                return try await transfer(from: url, policy: sourcePolicy, onProgress: onProgress,
                                          sourceProof: nil, resumeKey: key, resuming: partial)
            } catch is MapDownloadResumeRejected {
                // 416, a changed validator or size, another host or a
                // malformed range: restart from zero.
                try? FileManager.default.removeItem(at: partial.fileURL)
            }
        }
        do {
            return try await transfer(from: url, policy: sourcePolicy, onProgress: onProgress,
                                      sourceProof: sourceProof, resumeKey: key, resuming: nil)
        } catch is MapDownloadResumeRejected {
            throw MapAcquisitionError.downloadFailed("The provider returned an unexpected partial response.")
        }
    }

    private func transfer(
        from url: URL,
        policy sourcePolicy: ReviewedProviderURLPolicy,
        onProgress: (@Sendable (MapDownloadProgress) -> Void)?,
        sourceProof: BBBikeSourceProof?,
        resumeKey: MapDownloadResumeKey?,
        resuming: MapPartialDownload?
    ) async throws -> MapPackageDownloadResponse {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        // Bound an unresponsive connection without imposing a total map-download limit.
        request.timeoutInterval = 30
        if let sourceProof {
            request.setValue(sourceProof.etag, forHTTPHeaderField: "If-Match")
            request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")
        }
        if let resuming, let ifRange = resuming.validator.ifRangeValue {
            request.setValue("bytes=\(resuming.bytes)-", forHTTPHeaderField: "Range")
            request.setValue(ifRange, forHTTPHeaderField: "If-Range")
            request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")
        }
        let redirectDelegate = ReviewedProviderRedirectDelegate(policy: sourcePolicy)

        let temporaryURL: URL
        if let resuming {
            temporaryURL = resuming.fileURL
        } else {
            temporaryURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(MapAcquisitionWorkspace.temporaryDownloadPrefix)\(UUID().uuidString)")
            guard FileManager.default.createFile(atPath: temporaryURL.path, contents: nil) else {
                throw MapAcquisitionError.downloadFailed("A local download file could not be created.")
            }
        }
        var keepTemporaryFile = false
        defer {
            if !keepTemporaryFile {
                try? FileManager.default.removeItem(at: temporaryURL)
            }
        }

        do {
            let handle = try FileHandle(forWritingTo: temporaryURL)
            defer { try? handle.close() }
            if let resuming {
                guard try handle.seekToEnd() == resuming.bytes else { throw MapDownloadResumeRejected() }
            }
            // URLSession delivers the body in chunks; each chunk is written as
            // it arrives instead of awaiting every byte.
            let streaming = StreamingDownloadDelegate(
                redirectDelegate: redirectDelegate,
                fileHandle: handle,
                maximumBytes: sourceProof?.downloadSizeBytes,
                validateResponse: { httpResponse in
                    if let finalURL = httpResponse.url {
                        try sourcePolicy.validate(finalURL)
                    }
                    if let sourceProof {
                        guard httpResponse.statusCode == 200,
                              httpResponse.url == sourceProof.sourceURL,
                              httpResponse.value(forHTTPHeaderField: "ETag") == sourceProof.etag,
                              httpResponse.value(forHTTPHeaderField: "Last-Modified") == sourceProof.lastModified,
                              httpResponse.expectedContentLength == Int64(sourceProof.downloadSizeBytes) else {
                            throw MapAcquisitionError.invalidPackage("The BBBike source changed. Refresh the catalog.")
                        }
                    }
                },
                onProgress: onProgress,
                resuming: resuming
            )
            let session = URLSession(
                configuration: sessionConfiguration(),
                delegate: streaming,
                delegateQueue: nil
            )
            defer { session.finishTasksAndInvalidate() }
            let httpResponse: HTTPURLResponse
            do {
                httpResponse = try await streaming.run(request: request, session: session)
            } catch {
                // Keep what arrived for a later Try again, unless the response
                // itself was unusable or the Mac ran out of space.
                if let resumeKey, let resumeStore, !(error is MapDownloadResumeRejected),
                   !MacStorageCheck.isOutOfSpace(error),
                   let partial = streaming.resumablePartial(fileURL: temporaryURL, sourceURL: url) {
                    resumeStore.keep(partial, for: resumeKey)
                    keepTemporaryFile = true
                }
                throw error
            }

            keepTemporaryFile = true
            return MapPackageDownloadResponse(
                statusCode: httpResponse.statusCode,
                temporaryFileURL: temporaryURL
            )
        } catch let error as MapAcquisitionError {
            throw error
        } catch let error as MapDownloadResumeRejected {
            throw error
        } catch let error as URLError {
            // Keep structured network failures for the provider-aware acquisition boundary.
            throw error
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            if MacStorageCheck.isOutOfSpace(error) {
                throw MapAcquisitionError.insufficientMacStorage(requiredBytes: nil)
            }
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
            if message?.localizedCaseInsensitiveContains("No space left on device") == true {
                throw MapAcquisitionError.insufficientMacStorage(requiredBytes: nil)
            }
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
    private static let ownerFilename = ".terento-owner"
    /// Prefix of in-flight download files in the temporary directory.
    static let temporaryDownloadPrefix = "terento-map-download-"

    /// Removes download files left in the temporary directory by a crash or
    /// forced quit. Only Terento's own prefix is considered, and files touched
    /// within the last hour are kept.
    @discardableResult
    static func scavengeStaleTemporaryDownloads(
        directory: URL = FileManager.default.temporaryDirectory,
        olderThan age: TimeInterval = 60 * 60,
        now: Date = Date()
    ) -> Int {
        let fileManager = FileManager.default
        guard let entries = try? fileManager.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey, .contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }
        var removed = 0
        for entry in entries where entry.lastPathComponent.hasPrefix(temporaryDownloadPrefix) {
            guard let values = try? entry.resourceValues(
                      forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .contentModificationDateKey]),
                  values.isRegularFile == true,
                  values.isSymbolicLink != true,
                  let modifiedAt = values.contentModificationDate,
                  now.timeIntervalSince(modifiedAt) > age else {
                continue
            }
            if (try? fileManager.removeItem(at: entry)) != nil {
                removed += 1
            }
        }
        return removed
    }
    private static let logger = Logger(
        subsystem: "app.terento.native-connectivity-poc",
        category: "MapAcquisition"
    )

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
            try Data(String(ProcessInfo.processInfo.processIdentifier).utf8)
                .write(to: rootURL.appendingPathComponent(Self.ownerFilename), options: .atomic)
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

    @discardableResult
    static func scavengeStale(
        rootURL: URL? = nil,
        olderThan age: TimeInterval = 24 * 60 * 60,
        now: Date = Date()
    ) -> Int {
        let rootURL = rootURL ?? defaultRootURL()
        let fileManager = FileManager.default
        guard let entries = try? fileManager.contentsOfDirectory(
            at: rootURL,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey, .contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }

        var removedCount = 0
        for entry in entries {
            guard UUID(uuidString: entry.lastPathComponent) != nil,
                  let values = try? entry.resourceValues(
                      forKeys: [.isDirectoryKey, .isSymbolicLinkKey, .contentModificationDateKey]
                  ),
                  values.isDirectory == true,
                  values.isSymbolicLink != true,
                  let modifiedAt = values.contentModificationDate,
                  now.timeIntervalSince(modifiedAt) > age,
                  !isOwnedByLiveProcess(entry) else {
                continue
            }

            do {
                try remove(rootURL: entry)
                removedCount += 1
            } catch {
                // A scavenger failure must not affect startup or an active install.
            }
        }
        return removedCount
    }

    func cleanup() throws {
        try Self.remove(rootURL: rootURL)
    }

    static func cleanup(rootURL: URL) throws {
        try remove(rootURL: rootURL)
    }

    private static func defaultRootURL() -> URL {
        let cachesURL = FileManager.default.urls(
            for: .cachesDirectory,
            in: .userDomainMask
        ).first ?? FileManager.default.temporaryDirectory

        return cachesURL
            .appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("MapAcquisitions", isDirectory: true)
    }

    private static func remove(rootURL: URL) throws {
        guard FileManager.default.fileExists(atPath: rootURL.path) else {
            return
        }

        do {
            try FileManager.default.removeItem(at: rootURL)
        } catch {
            logger.error("Could not remove acquisition workspace: \(error.localizedDescription, privacy: .private)")
            throw MapAcquisitionError.workspaceFailed(error.localizedDescription)
        }
    }

    private static func isOwnedByLiveProcess(_ rootURL: URL) -> Bool {
        let ownerURL = rootURL.appendingPathComponent(ownerFilename)
        guard FileManager.default.fileExists(atPath: ownerURL.path) else { return false }
        guard let data = try? Data(contentsOf: ownerURL),
              let pid = Int32(String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)),
              pid > 0 else { return true } // Ambiguous ownership is retained.
        return Darwin.kill(pid, 0) == 0 || errno != ESRCH
    }
}

struct ValidatedMapArtifact: Equatable, Sendable {
    let artifactID: String
    let artifactKind: MapArtifactKind
    let sourceKind: MapSourceKind
    let provider: String
    let region: String
    let canonicalRegion: String
    let rawRelease: String
    let version: MapVersion
    let localIMGURL: URL
    let workspaceRootURL: URL?
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
        artifactID: String? = nil,
        artifactKind: MapArtifactKind = .main,
        provider: String,
        region: String,
        canonicalRegion: String,
        rawRelease: String,
        version: MapVersion,
        localIMGURL: URL,
        workspaceRootURL: URL? = nil,
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
        self.artifactID = artifactID ?? catalogPackageID
        self.artifactKind = artifactKind
        self.sourceKind = sourceKind
        self.provider = provider
        self.region = region
        self.canonicalRegion = canonicalRegion
        self.rawRelease = rawRelease
        self.version = version
        self.localIMGURL = localIMGURL
        self.workspaceRootURL = workspaceRootURL
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
            id: artifactID,
            source: sourceKind,
            kind: artifactKind,
            required: artifactKind == .main,
            providerId: provider,
            providerRegionId: region,
            canonicalRegionId: canonicalRegion,
            version: version,
            sourceURL: sourcePackageURL,
            localURL: localIMGURL,
            sizeBytes: installSizeBytes,
            downloadSizeBytes: downloadSizeBytes,
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
        var keepWorkspace = false
        defer {
            if !keepWorkspace {
                try? workspace.cleanup()
            }
        }

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
            let candidate = CustomMapImportCandidate(
                id: package.id,
                package: package,
                artifact: artifact,
                originalFilename: fileURL.lastPathComponent,
                metadata: validated.metadata,
                workspaceRootURL: workspace.rootURL
            )
            keepWorkspace = true
            return candidate
        } catch let error as MapAcquisitionError {
            throw error
        } catch let error as MapSourceValidationError {
            if error == .invalidIMG {
                throw MapAcquisitionError.customMapNotConfirmed(
                    "Terento could not confirm that \(fileURL.lastPathComponent) is a Garmin map image. No file was prepared for installation."
                )
            }
            throw MapAcquisitionError.invalidPackage(
                "The selected IMG could not be safely checked."
            )
        } catch {
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
            workspaceRootURL: workspaceURL.deletingLastPathComponent(),
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
    private let availabilityCheck: (@Sendable (MapPackage) async throws -> Void)?

    init(
        availabilityCheck: (@Sendable (MapPackage) async throws -> Void)? = nil,
        downloadClient: any MapPackageDownloadClient = FoundationMapPackageDownloadClient(),
        providerHealthChecker: any MapProviderHealthChecking = NoopMapProviderHealthChecker(),
        archiveExtractor: any MapPackageArchiveExtractor = SystemZIPArchiveExtractor(),
        workspaceFactory: @escaping @Sendable () throws -> MapAcquisitionWorkspace = {
            try MapAcquisitionWorkspace.make()
        }
    ) {
        self.availabilityCheck = availabilityCheck
        self.downloadClient = downloadClient
        self.providerHealthChecker = providerHealthChecker
        self.archiveExtractor = archiveExtractor
        self.workspaceFactory = workspaceFactory
    }

    func acquire(
        package: MapPackage,
        artifact selectedArtifact: MapArtifact? = nil,
        canonicalRegion: String? = nil,
        workspace requestedWorkspace: MapAcquisitionWorkspace? = nil,
        onDownloadStart: (@Sendable () async -> Void)? = nil,
        onStateChange: (@Sendable (MapAcquisitionState) -> Void)? = nil,
        onDownloadProgress: (@Sendable (MapDownloadProgress) -> Void)? = nil,
        onValidationProgress: (@Sendable (Double) -> Void)? = nil
    ) async throws -> ValidatedMapArtifact {
        state(.resolvingPackage, onStateChange)
        let acquisitionPackage = selectedArtifact.map {
            package.acquisitionPackage(for: $0)
        } ?? package
        do {
            try MapPackageAcquisitionPolicyResolver().validate(package: acquisitionPackage)
        } catch let error as MapAcquisitionPolicyError {
            onStateChange?(.failed)
            throw MapAcquisitionError.acquisitionWithheld(error.availability)
        }

        guard !package.requiredMainArtifactUnavailable else {
            throw MapAcquisitionError.acquisitionWithheld(.blocked(
                provider: MapProviderDisplay.downloadName(package.providerId), reason: "PACKAGE_UNAVAILABLE"))
        }
        let availability = MapPackageAcquisitionPolicyResolver().availability(for: package)
        guard availability == .available else {
            throw MapAcquisitionError.acquisitionWithheld(availability)
        }
        try await availabilityCheck?(package)

        if MapIdentity.normalizeProvider(acquisitionPackage.providerId) == "bbbike",
           BBBikeProviderAdapter().expectedIMGIdentity(for: acquisitionPackage) == nil {
            throw MapAcquisitionError.invalidPackage("The BBBike source proof is incomplete. Refresh the catalog.")
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

        var handedOff = false
        defer { if !handedOff { try? acquisitionWorkspace.cleanup() } }
        do {
            let artifact = try await acquireInWorkspace(
                package: acquisitionPackage,
                artifact: selectedArtifact,
                canonicalRegion: canonicalRegion,
                workspace: acquisitionWorkspace,
                onDownloadStart: onDownloadStart,
                onStateChange: onStateChange,
                onDownloadProgress: onDownloadProgress,
                onValidationProgress: onValidationProgress
            )
            handedOff = true
            return artifact
        } catch {
            onStateChange?(.failed)
            throw error
        }
    }

    private func acquireInWorkspace(
        package: MapPackage,
        artifact selectedArtifact: MapArtifact?,
        canonicalRegion: String?,
        workspace: MapAcquisitionWorkspace,
        onDownloadStart: (@Sendable () async -> Void)?,
        onStateChange: (@Sendable (MapAcquisitionState) -> Void)?,
        onDownloadProgress: (@Sendable (MapDownloadProgress) -> Void)?,
        onValidationProgress: (@Sendable (Double) -> Void)?
    ) async throws -> ValidatedMapArtifact {
        guard let sourceURL = selectedArtifact?.sourceURL ?? package.downloadURL else {
            throw MapAcquisitionError.downloadFailed("The catalog package has no source URL.")
        }

        try Task.checkCancellation()
        await onDownloadStart?()
        state(.downloading, onStateChange)
        let response: MapPackageDownloadResponse
        do {
            response = try await downloadClient.download(
                package: package,
                onProgress: { progress in
                    let totalBytes = progress.totalBytes > 0
                        ? progress.totalBytes
                        : selectedArtifact?.downloadSizeBytes
                            ?? package.expectedDownloadSizeBytes
                            ?? 0
                    onDownloadProgress?(MapDownloadProgress(
                        bytesDownloaded: progress.bytesDownloaded,
                        totalBytes: totalBytes,
                        bytesPerSecond: progress.bytesPerSecond
                    ))
                }
            )
        } catch let error as URLError {
            if error.code == .cancelled { throw CancellationError() }
            throw MapAcquisitionError.providerConnectionFailed(providerId: package.providerId, code: error.code)
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as MapAcquisitionError {
            throw await providerAwareDownloadError(error, package: package)
        } catch {
            throw await providerAwareDownloadError(
                .downloadFailed(error.localizedDescription),
                package: package
            )
        }

        defer {
            if response.temporaryFileURL.standardizedFileURL
                != workspace.downloadURL.standardizedFileURL {
                try? FileManager.default.removeItem(at: response.temporaryFileURL)
            }
        }

        guard (200...299).contains(response.statusCode) else {
            throw MapAcquisitionError.providerUnavailable(
                providerId: package.providerId, statusCode: response.statusCode
            )
        }

        state(.validatingDownload, onStateChange)
        let fileManager = FileManager.default
        guard fileManager.isReadableFile(atPath: response.temporaryFileURL.path) else {
            throw MapAcquisitionError.downloadIncomplete(
                expected: selectedArtifact?.downloadSizeBytes ?? package.expectedDownloadSizeBytes,
                actual: 0
            )
        }

        do {
            try fileManager.copyItem(at: response.temporaryFileURL, to: workspace.downloadURL)
        } catch {
            if MacStorageCheck.isOutOfSpace(error) {
                let size = (try? fileSize(of: response.temporaryFileURL)).map(MacStorageCheck.requiredBytes(forDownloadBytes:))
                throw MapAcquisitionError.insufficientMacStorage(requiredBytes: size)
            }
            throw MapAcquisitionError.downloadFailed("The downloaded file could not be stored safely.")
        }

        let downloadSize = try fileSize(of: workspace.downloadURL)
        guard downloadSize > 0 else {
            throw MapAcquisitionError.downloadIncomplete(
                expected: selectedArtifact?.downloadSizeBytes ?? package.expectedDownloadSizeBytes,
                actual: downloadSize
            )
        }

        let format = try MapPackageFormat.detect(fileURL: workspace.downloadURL)
        if MapIdentity.normalizeProvider(package.providerId) == "bbbike",
           (format != .zip || downloadSize != package.expectedDownloadSizeBytes) {
            throw MapAcquisitionError.invalidPackage("The BBBike package changed. Refresh the catalog.")
        }
        let imgURL: URL
        switch format {
        case .rawIMG:
            imgURL = workspace.downloadURL
        case .zip:
            state(.extracting, onStateChange)
            if let proof = package.mainArtifact?.sourceProof, MapIdentity.normalizeProvider(package.providerId) == "bbbike" {
                try BBBikeArchiveSafety.validate(archiveURL: workspace.downloadURL,
                    expectedPayloadPath: proof.payloadPath, expectedIMGBytes: proof.installSizeBytes)
            }
            try archiveExtractor.extract(
                archiveURL: workspace.downloadURL,
                to: workspace.extractionURL
            )
            try validateExtractedTree(at: workspace.extractionURL)
            state(.inspectingIMG, onStateChange)
            imgURL = try locateIMG(
                in: workspace.extractionURL,
                expectedPackage: package
            )
        }

        state(.validatingIdentity, onStateChange)
        let metadata: GarminIMGMetadata
        if MapIdentity.normalizeProvider(package.providerId) == "bbbike",
           let context = BBBikeMapMetadata(package: package),
           let value = BBBikeIMGMetadata.metadata(try MapPackageFormat.readPrefix(from: imgURL, maxLength: GarminIMGMetadataParser.prefixLength), context: context, version: package.version) {
            metadata = value
        } else {
            metadata = try self.metadata(for: imgURL)
        }
        guard let expectedIdentity = package.identity else {
            throw MapAcquisitionError.invalidPackage(
                "The catalog package does not contain a valid provider and region identity."
            )
        }

        guard let actualIdentity = metadataIdentity(metadata),
              MapIdentityMatcher.matches(
                  actual: actualIdentity,
                  expected: expectedIdentity,
                  providerRegionId: package.providerRegionId,
                  identifier: package.identifier
              ) else {
            throw MapAcquisitionError.sourceIdentityMismatch(
                expected: expectedIdentity,
                actual: metadataIdentity(metadata)
            )
        }

        let isContourArtifact = package.artifacts.count == 1
            && package.artifacts.first?.kind == .contours
        guard metadata.version == package.version
            || (isContourArtifact && metadata.version == nil) else {
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
                expectedPackage: package,
                onProgress: onValidationProgress
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
                regionId: package.canonicalRegionId,
                artifactKind: selectedArtifact?.kind ?? .main
            )
        } catch {
            throw MapAcquisitionError.invalidPackage("The managed target filename could not be generated.")
        }

        let artifact = ValidatedMapArtifact(
            artifactID: selectedArtifact?.id ?? package.mainArtifact?.id,
            artifactKind: selectedArtifact?.kind ?? .main,
            provider: expectedIdentity.provider,
            region: expectedIdentity.region,
            canonicalRegion: canonicalRegion ?? canonicalRegionName(for: package),
            rawRelease: validatedSource.metadata.rawVersion ?? "",
            version: validatedSource.metadata.version ?? package.version,
            localIMGURL: imgURL,
            workspaceRootURL: workspace.rootURL,
            installSizeBytes: validatedSource.sizeBytes,
            sha256: validatedSource.sha256,
            sourcePackageURL: sourceURL,
            catalogPackageID: package.id,
            targetFilename: targetFilename,
            downloadSizeBytes: downloadSize,
            catalogDownloadSizeBytes: selectedArtifact?.downloadSizeBytes
                ?? package.expectedDownloadSizeBytes,
            downloadSizeMatchesCatalog: (selectedArtifact?.downloadSizeBytes
                ?? package.expectedDownloadSizeBytes).map { $0 == downloadSize } ?? true,
            packageFormat: format
        )
        state(.validated, onStateChange)
        return artifact
    }

    private func locateIMG(
        in extractionDirectory: URL,
        expectedPackage: MapPackage
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

        if MapIdentity.normalizeProvider(expectedPackage.providerId) == "bbbike" {
            guard candidates.count == 1, let proof = expectedPackage.mainArtifact?.sourceProof,
                  candidates[0].url.standardizedFileURL == extractionDirectory.appendingPathComponent(proof.payloadPath).standardizedFileURL else {
                throw MapAcquisitionError.ambiguousIMG
            }
            return candidates[0].url
        }
        let matching = candidates.filter { metadata in
            guard let expectedIdentity = expectedPackage.identity,
                  let actualIdentity = metadataIdentity(metadata.metadata) else {
                return false
            }
            return MapIdentityMatcher.matches(
                actual: actualIdentity,
                expected: expectedIdentity,
                providerRegionId: expectedPackage.providerRegionId,
                identifier: expectedPackage.identifier
            )
        }

        if matching.count == 1 {
            return matching[0].url
        }
        if matching.count > 1 {
            throw MapAcquisitionError.ambiguousIMG
        }

        let actualIdentity = metadataIdentity(candidates[0].metadata)
        if let expectedIdentity = expectedPackage.identity {
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
        case .acquisitionWithheld, .providerUnavailable, .providerConnectionFailed, .invalidPackage,
             .extractionFailed, .unsupportedPackageFormat, .unsafeArchivePath,
             .sourceIdentityMismatch, .sourceVersionMismatch, .noIMGFound,
             .ambiguousIMG, .workspaceFailed, .untrustedSourceURL,
             .customMapNotConfirmed, .insufficientMacStorage:
            return false
        }
    }
}

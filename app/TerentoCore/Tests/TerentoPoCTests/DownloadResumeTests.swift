import Foundation

// Minimal stand-ins for types outside the acquisition sources compiled here.
enum EvidenceResult {
    case pass
    case fail
}

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
}

/// A provider stub that honours `Range`/`If-Range` like a real HTTP server
/// and can drop the connection after a number of body bytes.
final class ResumableServerProtocol: URLProtocol {
    struct Scenario {
        var body: Data
        var etag: String? = "\"v1\""
        var lastModified: String? = nil
        var acceptRanges = true
        var contentEncoding: String? = nil
        /// Drop the connection after this many body bytes of the next response.
        var failAfter: [Int] = []
        /// How a range request is answered.
        var rangeBehaviour: RangeBehaviour = .honour
        /// Redirect every range request to this host.
        var redirectRangeRequestsTo: String? = nil
    }

    enum RangeBehaviour { case honour, ignore, wrongStart, notSatisfiable }

    struct Seen { let url: URL; let range: String?; let ifRange: String? }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var scenario = Scenario(body: Data())
    nonisolated(unsafe) private static var seen: [Seen] = []

    static func configure(_ value: Scenario) { lock.withLock { scenario = value; seen = [] } }
    static func update(_ change: (inout Scenario) -> Void) { lock.withLock { change(&scenario) } }
    static var requests: [Seen] { lock.withLock { seen } }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let range = request.value(forHTTPHeaderField: "Range")
        let ifRange = request.value(forHTTPHeaderField: "If-Range")
        let (scenario, failAfter): (Scenario, Int?) = Self.lock.withLock {
            Self.seen.append(Seen(url: request.url!, range: range, ifRange: ifRange))
            let next = Self.scenario.failAfter.first
            if !Self.scenario.failAfter.isEmpty { Self.scenario.failAfter.removeFirst() }
            return (Self.scenario, next)
        }
        let url = request.url!
        if range != nil, let host = scenario.redirectRangeRequestsTo, url.host != host {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            components.host = host
            let redirect = HTTPURLResponse(url: url, statusCode: 302, httpVersion: "HTTP/1.1",
                                           headerFields: ["Location": components.url!.absoluteString])!
            var next = request
            next.url = components.url
            client?.urlProtocol(self, wasRedirectedTo: next, redirectResponse: redirect)
            return
        }
        var headers: [String: String] = [:]
        if let etag = scenario.etag { headers["ETag"] = etag }
        if let lastModified = scenario.lastModified { headers["Last-Modified"] = lastModified }
        if scenario.acceptRanges { headers["Accept-Ranges"] = "bytes" }
        if let encoding = scenario.contentEncoding { headers["Content-Encoding"] = encoding }
        var status = 200
        var payload = scenario.body
        let validatorMatches = ifRange == nil || ifRange == scenario.etag || ifRange == scenario.lastModified
        if let range, range.hasPrefix("bytes="), range.hasSuffix("-"),
           let start = Int(range.dropFirst(6).dropLast()), validatorMatches, scenario.rangeBehaviour != .ignore {
            switch scenario.rangeBehaviour {
            case .notSatisfiable:
                status = 416
                payload = Data()
                headers["Content-Range"] = "bytes */\(scenario.body.count)"
            case .wrongStart:
                status = 206
                payload = scenario.body.subdata(in: 0..<scenario.body.count)
                headers["Content-Range"] = "bytes 0-\(scenario.body.count - 1)/\(scenario.body.count)"
            case .honour, .ignore:
                status = 206
                payload = scenario.body.subdata(in: start..<scenario.body.count)
                headers["Content-Range"] = "bytes \(start)-\(scenario.body.count - 1)/\(scenario.body.count)"
            }
        }
        headers["Content-Length"] = "\(payload.count)"
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        let chunk = 64 * 1024
        var offset = 0
        while offset < payload.count {
            let end = min(payload.count, offset + chunk)
            if let failAfter, end > failAfter {
                if failAfter > offset { client?.urlProtocol(self, didLoad: payload.subdata(in: offset..<failAfter)) }
                client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
                return
            }
            client?.urlProtocol(self, didLoad: payload.subdata(in: offset..<end))
            offset = end
        }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@main
struct DownloadResumeTests {
    static let body: Data = {
        var data = Data(count: 8 * 1024 * 1024)
        for index in data.indices { data[index] = UInt8(truncatingIfNeeded: index &* 31 &+ 7) }
        return data
    }()
    static let sourceURL = URL(string: "https://resume.example/maps/fra.zip")!

    static func main() async {
        await testFailedDownloadResumesWithRangeAndIfRange()
        await testCancelledDownloadResumes()
        await testChangedValidatorRestartsFromZero()
        await testIgnoredRangeRestartsFromZero()
        await testRejectedPartialResponseRestartsCleanly()
        await testRedirectToAnotherHostNeverResumes()
        await testIneligibleResponsesKeepNothing()
        await testWeakETagAndLastModified()
        testStoreLifetimeAndPurge()
        testContentRangeParsing()
        print("PASS: resumable provider downloads (Range/If-Range, validators, restart and host rules)")
    }

    static func client(_ store: MapDownloadResumeStore) -> FoundationMapPackageDownloadClient {
        FoundationMapPackageDownloadClient(
            sourcePolicyRegistry: ReviewedProviderURLPolicyRegistry(policies: [
                "freizeitkarte": ReviewedProviderURLPolicy(allowedHosts: ["resume.example", "mirror.example"])
            ]),
            sessionConfiguration: {
                let configuration = URLSessionConfiguration.ephemeral
                configuration.protocolClasses = [ResumableServerProtocol.self]
                return configuration
            },
            resumeStore: store)
    }

    static func package(url: URL = sourceURL) -> MapPackage {
        MapPackage(id: "freizeitkarte-fra", providerId: "freizeitkarte", regionId: "FRA",
                   name: "Republic of France", version: MapVersion(year: 2026, month: 5)!,
                   sizeBytes: UInt64(body.count), sourceURL: url, releaseDate: "2026-05-03", identifier: "FRA+")
    }

    @discardableResult
    static func attempt(_ store: MapDownloadResumeStore, progress: ProgressLog? = nil) async -> Result<Data, Error> {
        do {
            let response = try await client(store).download(package: package(), onProgress: { progress?.append($0) })
            defer { try? FileManager.default.removeItem(at: response.temporaryFileURL) }
            return .success(try Data(contentsOf: response.temporaryFileURL))
        } catch {
            return .failure(error)
        }
    }

    static func testFailedDownloadResumesWithRangeAndIfRange() async {
        let store = MapDownloadResumeStore()
        ResumableServerProtocol.configure(.init(body: body, failAfter: [6 * 1024 * 1024]))
        guard case .failure(let error) = await attempt(store) else { return fail("the first download fails mid-way") }
        expect(error is URLError, "the network failure stays a structured URLError for the acquisition boundary")
        expect(store.count == 1, "a partial download is kept after the failure")
        let progress = ProgressLog()
        guard case .success(let data) = await attempt(store, progress: progress) else { return fail("Try again resumes") }
        let requests = ResumableServerProtocol.requests
        let kept = requests.count == 2 ? requests[1].range.flatMap { UInt64($0.dropFirst(6).dropLast()) } : nil
        expect(requests.count == 2 && requests[1].range?.hasPrefix("bytes=") == true && requests[1].range?.hasSuffix("-") == true
            && kept.map { $0 >= MapDownloadResumeStore.minimumResumableBytes && $0 <= 6 * 1024 * 1024 } == true
            && requests[1].ifRange == "\"v1\"",
            "Try again sends Range from the bytes kept on disk and If-Range with the strong ETag")
        expect(data == body, "the resumed file is byte-identical to the provider file")
        expect(!progress.values.isEmpty && progress.values.allSatisfy {
                $0.bytesDownloaded >= (kept ?? 0) && $0.totalBytes == UInt64(body.count) },
            "resumed progress continues from the kept bytes against the full size")
        expect(store.count == 0, "a completed download leaves no partial entry")
    }

    static func testCancelledDownloadResumes() async {
        let store = MapDownloadResumeStore()
        ResumableServerProtocol.configure(.init(body: body, failAfter: [5 * 1024 * 1024]))
        _ = await attempt(store)
        expect(store.count == 1, "a dropped download keeps its partial file")
        guard case .success(let data) = await attempt(store) else { return fail("resume after a drop") }
        expect(data == body, "resume after a dropped connection completes the exact file")
    }

    static func testChangedValidatorRestartsFromZero() async {
        let store = MapDownloadResumeStore()
        ResumableServerProtocol.configure(.init(body: body, failAfter: [6 * 1024 * 1024]))
        _ = await attempt(store)
        var changed = body
        changed[0] ^= 0xFF
        let newBody = changed
        ResumableServerProtocol.update { $0.body = newBody; $0.etag = "\"v2\"" }
        guard case .success(let data) = await attempt(store) else { return fail("a changed file downloads") }
        expect(data == newBody, "If-Range with an old ETag yields the full new file, never a spliced one")
    }

    static func testIgnoredRangeRestartsFromZero() async {
        let store = MapDownloadResumeStore()
        ResumableServerProtocol.configure(.init(body: body, failAfter: [6 * 1024 * 1024]))
        _ = await attempt(store)
        ResumableServerProtocol.update { $0.rangeBehaviour = .ignore }
        guard case .success(let data) = await attempt(store) else { return fail("a 200 response downloads") }
        expect(data == body, "a 200 answer to a range request replaces the partial file from zero")
    }

    static func testRejectedPartialResponseRestartsCleanly() async {
        for behaviour in [ResumableServerProtocol.RangeBehaviour.wrongStart, .notSatisfiable] {
            let store = MapDownloadResumeStore()
            ResumableServerProtocol.configure(.init(body: body, failAfter: [6 * 1024 * 1024]))
            _ = await attempt(store)
            ResumableServerProtocol.update { $0.rangeBehaviour = behaviour }
            guard case .success(let data) = await attempt(store) else { return fail("restart after \(behaviour)") }
            let requests = ResumableServerProtocol.requests
            expect(data == body && requests.count == 3 && requests[2].range == nil,
                "a \(behaviour) partial response is discarded and the download restarts without Range")
        }
    }

    static func testRedirectToAnotherHostNeverResumes() async {
        let store = MapDownloadResumeStore()
        ResumableServerProtocol.configure(.init(body: body, failAfter: [6 * 1024 * 1024]))
        _ = await attempt(store)
        ResumableServerProtocol.update { $0.redirectRangeRequestsTo = "mirror.example" }
        guard case .success(let data) = await attempt(store) else { return fail("download after a redirect") }
        let requests = ResumableServerProtocol.requests
        expect(data == body && requests.last?.range == nil && requests.last?.url.host == "resume.example",
            "a range request redirected to another host is not resumed; the download restarts at the source")
    }

    static func testIneligibleResponsesKeepNothing() async {
        let cases: [(String, ResumableServerProtocol.Scenario)] = [
            ("no Accept-Ranges", .init(body: body, acceptRanges: false, failAfter: [6 * 1024 * 1024])),
            ("no validator", .init(body: body, etag: nil, failAfter: [6 * 1024 * 1024])),
            ("compressed body", .init(body: body, contentEncoding: "gzip", failAfter: [6 * 1024 * 1024])),
            ("under 1 MiB received", .init(body: body, failAfter: [512 * 1024]))
        ]
        for (name, scenario) in cases {
            let store = MapDownloadResumeStore()
            ResumableServerProtocol.configure(scenario)
            _ = await attempt(store)
            expect(store.count == 0, "\(name): no partial file is kept")
        }
    }

    static func testWeakETagAndLastModified() async {
        let store = MapDownloadResumeStore()
        ResumableServerProtocol.configure(.init(body: body, etag: "W/\"weak\"", failAfter: [6 * 1024 * 1024]))
        _ = await attempt(store)
        expect(store.count == 0, "a weak ETag alone is not a strong validator")

        let dated = MapDownloadResumeStore()
        let modified = "Tue, 05 May 2026 10:00:00 GMT"
        ResumableServerProtocol.configure(.init(body: body, etag: nil, lastModified: modified,
                                                failAfter: [6 * 1024 * 1024]))
        _ = await attempt(dated)
        guard case .success(let data) = await attempt(dated) else { return fail("Last-Modified resume") }
        expect(data == body && ResumableServerProtocol.requests.last?.ifRange == modified,
            "Last-Modified is used as If-Range when there is no strong ETag")
    }

    static func testStoreLifetimeAndPurge() {
        let clock = Clock()
        let store = MapDownloadResumeStore(now: { clock.now })
        func makePartial() -> MapPartialDownload {
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(MapAcquisitionWorkspace.temporaryDownloadPrefix)\(UUID().uuidString)")
            FileManager.default.createFile(atPath: url.path, contents: Data(count: 10))
            return MapPartialDownload(fileURL: url, bytes: 10, totalBytes: 20,
                validator: MapDownloadValidator(etag: "\"a\"", lastModified: nil), host: "resume.example")
        }
        let key = MapDownloadResumeKey(packageID: "p", artifactID: "a", sourceURL: "https://resume.example/a")
        let expired = makePartial()
        store.keep(expired, for: key)
        clock.now = clock.now.addingTimeInterval(MapDownloadResumeStore.lifetime + 1)
        expect(store.take(key) == nil && !FileManager.default.fileExists(atPath: expired.fileURL.path),
            "a partial file older than 30 minutes is removed, not resumed")
        let truncated = makePartial()
        store.keep(truncated, for: key)
        try? Data(count: 4).write(to: truncated.fileURL)
        expect(store.take(key) == nil && !FileManager.default.fileExists(atPath: truncated.fileURL.path),
            "a partial file whose size changed on disk is discarded")
        let kept = makePartial()
        store.keep(kept, for: key)
        store.purgeAll()
        expect(store.count == 0 && !FileManager.default.fileExists(atPath: kept.fileURL.path),
            "quitting removes every partial file")
        expect(MapDownloadResumeStore.lifetime == 30 * 60,
            "partial downloads share the 30-minute retained-artifact lifetime")
    }

    static func testContentRangeParsing() {
        func response(_ range: String) -> HTTPURLResponse {
            HTTPURLResponse(url: sourceURL, statusCode: 206, httpVersion: "HTTP/1.1",
                            headerFields: ["Content-Range": range])!
        }
        expect(MapPartialDownload.contentRange(response("bytes 10-19/20"))! == (10, 19, 20), "a valid range parses")
        expect(MapPartialDownload.contentRange(response("bytes 10-25/20")) == nil, "an end beyond the size is rejected")
        expect(MapPartialDownload.contentRange(response("bytes */20")) == nil, "an unsatisfied range is rejected")
        expect(MapPartialDownload.contentRange(response("items 1-2/3")) == nil, "a non-byte unit is rejected")
    }

    static func fail(_ message: String) {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fail(message); return }
        print("PASS: \(message)")
    }
}

final class ProgressLog: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [MapDownloadProgress] = []
    func append(_ value: MapDownloadProgress) { lock.withLock { stored.append(value) } }
    var values: [MapDownloadProgress] { lock.withLock { stored } }
}

final class Clock: @unchecked Sendable {
    private let lock = NSLock()
    private var value = Date(timeIntervalSince1970: 1_800_000_000)
    var now: Date {
        get { lock.withLock { value } }
        set { lock.withLock { value = newValue } }
    }
}

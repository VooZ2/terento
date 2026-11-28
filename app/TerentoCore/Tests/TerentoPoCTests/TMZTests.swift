import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
}

private struct FixtureDownload: MapPackageDownloadClient {
    let directory: URL
    var overrides: [String: String] = [:]
    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        let name = overrides[url.lastPathComponent] ?? url.lastPathComponent
        let copy = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.copyItem(at: directory.appendingPathComponent(name), to: copy)
        return MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: copy)
    }
}

private struct PathPrefixReader: DeviceFileReader {
    let prefixes: [String: [UInt8]]
    func readFileInventory() throws -> [DeviceFile] { [] }
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8] {
        guard let prefix = prefixes[file.path] else { throw CocoaError(.fileReadUnknown) }
        return Array(prefix.prefix(maxLength))
    }
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]] {
        Dictionary(uniqueKeysWithValues: files.compactMap { file in
            prefixes[file.path].map { (file.stableIdentity, Array($0.prefix(maxLength))) }
        })
    }
}

/// Stub server for testing T-MZ download recovery (drops, silent truncation,
/// transient HTTP 503 on resume, and multi-drop recovery).
private final class FlakyTMZServerProtocol: URLProtocol {
    enum Step {
        case dropAfter(Int)
        case truncateAfter(Int)
        case transientHTTP(Int)
        case complete
    }

    struct Scenario {
        var body: Data
        var etag: String = "\"tmz-v1\""
        var lastModified: String = "Sat, 21 Nov 2026 03:47:18 GMT"
        var steps: [Step] = []
    }

    struct Seen {
        let range: String?
        let ifRange: String?
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var scenario = Scenario(body: Data())
    nonisolated(unsafe) private static var seen: [Seen] = []
    nonisolated(unsafe) private static var delivered: UInt64 = 0

    static func configure(_ value: Scenario) { lock.withLock { scenario = value; seen = []; delivered = 0 } }
    static func noteDelivered(_ bytes: UInt64) { lock.withLock { delivered = max(delivered, bytes) } }
    static var requests: [Seen] { lock.withLock { seen } }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let range = request.value(forHTTPHeaderField: "Range")
        let ifRange = request.value(forHTTPHeaderField: "If-Range")
        let (scenario, step): (Scenario, Step) = Self.lock.withLock {
            Self.seen.append(Seen(range: range, ifRange: ifRange))
            Self.delivered = 0
            let next = Self.scenario.steps.isEmpty ? .complete : Self.scenario.steps.removeFirst()
            return (Self.scenario, next)
        }
        let url = request.url!

        if case .transientHTTP(let code) = step {
            let response = HTTPURLResponse(url: url, statusCode: code, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Length": "0"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocolDidFinishLoading(self)
            return
        }

        var start = 0
        var status = 200
        var headers: [String: String] = [
            "ETag": scenario.etag,
            "Last-Modified": scenario.lastModified,
            "Accept-Ranges": "bytes"
        ]
        if let range, range.hasPrefix("bytes="), range.hasSuffix("-"),
           let offset = Int(range.dropFirst(6).dropLast()),
           ifRange == nil || ifRange == scenario.etag {
            start = offset
            status = 206
            headers["Content-Range"] = "bytes \(start)-\(scenario.body.count - 1)/\(scenario.body.count)"
        }
        let payload = scenario.body.subdata(in: start..<scenario.body.count)
        headers["Content-Length"] = "\(payload.count)"
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)

        let chunk = 64 * 1024
        var offset = 0
        let stopLimit: Int?
        let silentEOF: Bool
        switch step {
        case .dropAfter(let limit): (stopLimit, silentEOF) = (limit, false)
        case .truncateAfter(let limit): (stopLimit, silentEOF) = (limit, true)
        case .complete, .transientHTTP: (stopLimit, silentEOF) = (nil, false)
        }
        while offset < payload.count {
            let end = min(payload.count, offset + chunk)
            if let stopLimit, end > stopLimit {
                if stopLimit > offset {
                    client?.urlProtocol(self, didLoad: payload.subdata(in: offset..<stopLimit))
                }
                let client = self.client
                let reached = UInt64(start + stopLimit)
                DispatchQueue.global().async {
                    let deadline = Date().addingTimeInterval(10)
                    while Self.lock.withLock({ Self.delivered }) < reached, Date() < deadline {
                        usleep(1_000)
                    }
                    if silentEOF {
                        client?.urlProtocolDidFinishLoading(self)
                    } else {
                        client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
                    }
                }
                return
            }
            client?.urlProtocol(self, didLoad: payload.subdata(in: offset..<end))
            offset = end
        }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

typealias Edit = (inout [String: Any], inout [String: Any]) -> Void

@main struct TMZTests {
    static let root = "https://tmz.skr.jp/data/gmap/"
    static let contoursURL = root + "gmapsupp_261119cntr.zip"
    static let standardURL = root + "gmapsupp_261119.zip"
    static let fixtures = URL(fileURLWithPath: ProcessInfo.processInfo.environment["TERENTO_TMZ_FIXTURES"]!)

    static func check(_ condition: Bool, _ label: String) {
        guard condition else { fatalError("FAIL: \(label)") }
        print("PASS: \(label)")
    }

    static func meta(_ archive: String) throws -> [String: Any] {
        let all = try JSONSerialization.jsonObject(with: Data(contentsOf: fixtures.appendingPathComponent("meta.json")))
        return (all as! [String: Any])[archive] as! [String: Any]
    }

    static func prefix(_ image: String, length: Int = 4096) throws -> [UInt8] {
        Array(try Data(contentsOf: fixtures.appendingPathComponent(image)).prefix(length))
    }

    static func document(contours: Bool = true, archive: String? = nil, edit: Edit = { _, _ in }) throws -> [String: Any] {
        let variant: TMZVariant = contours ? .japanContours : .japan
        let url = contours ? contoursURL : standardURL
        let sizes = try meta(archive ?? (contours ? "gmapsupp_261119cntr.zip" : "gmapsupp_261119.zip"))
        var proof: [String: Any] = [
            "sourceURL": url,
            "etag": "\"39f1bcff-660c137991d80\"",
            "lastModified": "Sat, 21 Nov 2026 03:47:18 GMT",
            "downloadSizeBytes": sizes["downloadSizeBytes"]!,
            "installSizeBytes": sizes["installSizeBytes"]!,
            "payloadPath": "gmapsupp.img",
            "crc32": sizes["crc32"]!,
            "sourceIdentity": "tmz:\(variant.key)",
            "variant": variant.key,
            "mapType": variant.mapType,
            "familyId": 42,
            "imgTitle": variant.imgTitle,
            "publishedDate": "2026-11-19",
            "generatedAt": "2026-11-21T00:00:00Z",
            "headerIdentityValidated": true,
            "revision": String(repeating: "cd", count: 32)
        ]
        var map: [String: Any] = [
            "id": "tmz-\(variant.key)",
            "region": variant.key.uppercased(),
            "name": variant.displayName,
            "country": "Japan",
            "version": ["year": 2026, "month": 11, "day": 21],
            "sizeBytes": sizes["downloadSizeBytes"]!,
            "downloadSizeBytes": sizes["downloadSizeBytes"]!,
            "installSizeBytes": sizes["installSizeBytes"]!,
            "sourceURL": url,
            "identifier": variant.key,
            "providerRegionId": variant.key,
            "canonicalRegionId": variant.key.uppercased(),
            "countryCodes": ["JP"],
            "regionKind": "country",
            "tags": [variant.mapType, "cycling", "japan"],
            "capabilities": ["main"],
            "release": "2026-11-21",
            "mapType": variant.mapType,
            "geographicRegionId": "JP"
        ]
        edit(&map, &proof)
        map["artifacts"] = [[
            "id": "tmz-\(variant.key)-main",
            "kind": "main",
            "required": true,
            "sourceURL": proof["sourceURL"] ?? url,
            "sizeBytes": proof["installSizeBytes"] ?? 0,
            "downloadSizeBytes": proof["downloadSizeBytes"] ?? 0,
            "checksum": NSNull(),
            "contentType": "application/zip",
            "validationState": "validated",
            "installPayloadPath": proof["payloadPath"] ?? "gmapsupp.img",
            "sourceProof": proof
        ] as [String: Any]]
        return map
    }

    static func catalog(_ maps: [[String: Any]], status: String = "ACTIVE") throws -> MapCatalog {
        let json: [String: Any] = [
            "catalogVersion": 1,
            "updatedAt": "2026-11-21T00:00:00Z",
            "providers": [[
                "id": "tmz",
                "name": "T-MZ",
                "status": status,
                "website": "https://tmz.skr.jp/data/gmap.html",
                "maps": maps
            ]]
        ]
        return try MapCatalogDocumentDecoder().decode(JSONSerialization.data(withJSONObject: json))
    }

    static func package(contours: Bool = true, archive: String? = nil, edit: Edit = { _, _ in }) throws -> MapPackage {
        try catalog([document(contours: contours, archive: archive, edit: edit)]).packages[0]
    }

    static func compatible(_ package: MapPackage) -> Bool {
        MapCatalogClientCompatibilityValidator().isPackageCompatible(package)
    }

    static func acquire(_ package: MapPackage, serving archive: String? = nil) async throws -> ValidatedMapArtifact {
        let overrides = archive.map { ["gmapsupp_261119cntr.zip": $0, "gmapsupp_261119.zip": $0] } ?? [:]
        let acquisition = MapPackageAcquirer(
            downloadClient: FixtureDownload(directory: fixtures, overrides: overrides),
            workspaceFactory: {
                try MapAcquisitionWorkspace(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
            }
        )
        return try await acquisition.acquire(package: package)
    }

    static func main() async throws {
        try headers()
        try htmlDiscovery()
        try await liveResolverOfflineAndRetry()
        try catalogContract()
        try archiveSafety()
        try sourceValidation()
        try await acquisition()
        try await downloadRecovery()
        try rescanAndConflicts()
        if ProcessInfo.processInfo.environment["TERENTO_TMZ_LIVE_TEST"] == "1" {
            try await liveSiteSmokeTest()
        }
    }

    static func headers() throws {
        let cntr = try prefix("gmapsupp_261119cntr.img")
        let std = try prefix("gmapsupp_261119.img")
        let cntr8k = try prefix("gmapsupp_261119cntr.img", length: 8192)
        let std8k = try prefix("gmapsupp_261119.img", length: 8192)

        check(TMZIMGMetadata.title(cntr) == "\"Japan OSM\"", "contours IMG header title is \"Japan OSM\"")
        check(TMZIMGMetadata.title(std) == "OSM Japan", "standard IMG header title is OSM Japan")
        check(TMZIMGMetadata.hasTMZTYP(cntr8k) && TMZIMGMetadata.hasTMZTYP(std8k),
              "both T-MZ variants contain 00000TMZ.TYP in first 8 KiB")

        let m1 = GarminIMGMetadataParser().parse(cntr)
        check(m1?.provider == "T-MZ" && m1?.region == "JAPAN-CONTOURS" && m1?.identifier == "japan-contours"
            && m1?.version == MapVersion(year: 2026, month: 11, day: 21) && m1?.familyId == 42,
              "contours IMG parses as T-MZ JAPAN-CONTOURS with build date and family ID 42")

        let m2 = GarminIMGMetadataParser().parse(std)
        check(m2?.provider == "T-MZ" && m2?.region == "JAPAN" && m2?.identifier == "japan"
            && m2?.version == MapVersion(year: 2026, month: 11, day: 21) && m2?.familyId == 42,
              "standard IMG parses as T-MZ JAPAN with build date and family ID 42")

        check(TMZIMGMetadata.variant(title: "\"Japan OSM\"", familyIDs: [42]) == .japanContours,
              "\"Japan OSM\" + FID 42 maps to japan-contours")
        check(TMZIMGMetadata.variant(title: "OSM Japan", familyIDs: [42]) == .japan,
              "OSM Japan + FID 42 maps to japan")
        check(TMZIMGMetadata.variant(title: "\"Japan OSM\"", familyIDs: [43]) == nil,
              "wrong family ID is rejected")
        check(TMZIMGMetadata.variant(title: "\"Japan OSM\"", familyIDs: [42, 43]) == nil,
              "multiple family IDs are rejected")
    }

    static func htmlDiscovery() throws {
        let html = """
        <html><body>
        <!--
          <a href="./gmap/gmapsupp_291231cntr.zip">commented future placeholder</a>
          <a href="./gmap/gmapsupp_26????.zip">template</a>
        -->
        <table>
          <tr><th>2026-10-22</th>
            <td><a href="./gmap/gmapsupp_261022.zip">gmapsupp_261022.zip</a></td>
            <td><a href="./gmap/gmapsupp_261022cntr.zip">gmapsupp_261022cntr.zip</a></td>
          </tr>
          <tr><th>2026-11-19</th>
            <td><a href="./gmap/gmapsupp_261119.zip">gmapsupp_261119.zip</a></td>
            <td><a href="./gmap/gmapsupp_261119cntr.zip">gmapsupp_261119cntr.zip</a></td>
          </tr>
          <tr><th>2026-11-06</th>
            <td><a href="./gmap/gmapsupp_261106.zip">gmapsupp_261106.zip</a></td>
            <td><a href="./gmap/gmapsupp_261106cntr.zip">gmapsupp_261106cntr.zip</a></td>
          </tr>
        </table>
        </body></html>
        """
        let discovered = TMZLiveCatalogResolver.discoverLatestSources(inHTML: html)
        check(discovered?[.japanContours]?.url.absoluteString == contoursURL
            && discovered?[.japanContours]?.publishedDate == MapVersion(year: 2026, month: 11, day: 19),
              "HTML discovery strips comments and picks newest contours ZIP")
        check(discovered?[.japan]?.url.absoluteString == standardURL
            && discovered?[.japan]?.publishedDate == MapVersion(year: 2026, month: 11, day: 19),
              "HTML discovery picks newest standard ZIP regardless of table order")
    }

    static func liveResolverOfflineAndRetry() async throws {
        let cntrData = try Data(contentsOf: fixtures.appendingPathComponent("gmapsupp_261119cntr.zip"))
        let stdData = try Data(contentsOf: fixtures.appendingPathComponent("gmapsupp_261119.zip"))
        let htmlData = Data("""
        <html><body>
        <a href="./gmap/gmapsupp_261119.zip">std</a>
        <a href="./gmap/gmapsupp_261119cntr.zip">cntr</a>
        </body></html>
        """.utf8)

        final class Counter: @unchecked Sendable {
            private let lock = NSLock()
            private var value = 0
            func next() -> Int { lock.withLock { value += 1; return value } }
        }
        let counter = Counter()

        let resolver = TMZLiveCatalogResolver(
            dataLoader: { request in
                let call = counter.next()
                let url = request.url!
                // Simulate one transient 503 on the first index fetch to verify retry!
                if call == 1 {
                    let resp = HTTPURLResponse(url: url, statusCode: 503, httpVersion: "HTTP/1.1", headerFields: nil)!
                    return (Data(), resp)
                }
                if url == TMZProviderAdapter.indexURL {
                    let resp = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
                    return (htmlData, resp)
                }
                let body = url.lastPathComponent.contains("cntr") ? cntrData : stdData
                let range = request.value(forHTTPHeaderField: "Range") ?? ""
                let start: Int
                let end: Int
                if range.hasPrefix("bytes=-"), let suffix = Int(range.dropFirst(7)) {
                    start = max(0, body.count - suffix)
                    end = body.count - 1
                } else {
                    let parts = range.dropFirst(6).split(separator: "-")
                    start = Int(parts[0])!
                    end = min(body.count - 1, Int(parts[1])!)
                }
                let slice = body.subdata(in: start..<(end + 1))
                let resp = HTTPURLResponse(
                    url: url, statusCode: 206, httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Range": "bytes \(start)-\(end)/\(body.count)",
                        "ETag": "\"fixture-etag\"",
                        "Last-Modified": "Sat, 21 Nov 2026 03:47:18 GMT"
                    ]
                )!
                return (slice, resp)
            },
            retryDelays: [0, 0],
            sleep: { _ in }
        )

        let resolved = try await resolver.loadCatalogThrowing()
        check(resolved.providers.count == 1 && resolved.packages.count == 2,
              "TMZLiveCatalogResolver retries transient 503 and builds valid 2-package catalog via ranged probes")
        check(MapCatalogClientCompatibilityValidator().isCompatible(resolved),
              "live-resolved T-MZ catalog passes full client compatibility validation")
        let cntrPkg = resolved.packages.first { $0.id == "tmz-japan-contours" }
        check(cntrPkg?.version == MapVersion(year: 2026, month: 11, day: 21)
            && cntrPkg?.downloadURL?.absoluteString == contoursURL
            && cntrPkg?.mainArtifact?.tmzSourceProof?.publishedDate == "2026-11-19",
              "live-resolved contours package carries exact build date, URL, and source proof")
    }

    static func catalogContract() throws {
        let cntr = try package(contours: true)
        let std = try package(contours: false)
        check(cntr.mainArtifact?.tmzSourceProof?.familyId == 42
            && cntr.mainArtifact?.openFietsMapSourceProof == nil
            && cntr.mainArtifact?.osmapaSourceProof == nil
            && cntr.mainArtifact?.luckyMapsSourceProof == nil
            && cntr.mainArtifact?.sourceProof == nil,
              "T-MZ proof decodes exclusively as TMZSourceProof")
        check(compatible(cntr) && compatible(std), "both T-MZ packages are compatible")
        check(MapProviderDisplay.downloadName("tmz") == "T-MZ", "provider display name is T-MZ")

        func url(_ value: String) -> Edit { { map, proof in map["sourceURL"] = value; proof["sourceURL"] = value } }
        let tampering: [(String, Edit)] = [
            ("another host", url("https://tmz.skr.jp.evil.test/data/gmap/gmapsupp_261119cntr.zip")),
            ("HTTP scheme", url("http://tmz.skr.jp/data/gmap/gmapsupp_261119cntr.zip")),
            ("query string", url(contoursURL + "?x=1")),
            ("wrong variant URL", url(standardURL)),
            ("impossible date in URL", url(root + "gmapsupp_260230cntr.zip")),
            ("wrong family ID", { _, proof in proof["familyId"] = 43 }),
            ("wrong title", { _, proof in proof["imgTitle"] = "OSM Japan" }),
            ("build date before filename date", { map, proof in
                map["version"] = ["year": 2026, "month": 11, "day": 18]
                proof["generatedAt"] = "2026-11-18T00:00:00Z"
            }),
            ("build date >14 days after filename date", { map, proof in
                map["version"] = ["year": 2026, "month": 12, "day": 10]
                proof["generatedAt"] = "2026-12-10T00:00:00Z"
            }),
            ("weak ETag", { _, proof in proof["etag"] = "W/\"x\"" }),
            ("non-hex CRC-32", { _, proof in proof["crc32"] = "zzzzzzzz" }),
            ("wrong country code", { map, _ in map["countryCodes"] = ["RU"] }),
        ]
        for (label, edit) in tampering {
            check(!compatible(try package(edit: edit)), "catalog rejects \(label)")
        }

        var unavailableMap = try document()
        var artifact = (unavailableMap["artifacts"] as! [[String: Any]])[0]
        artifact["validationState"] = "unavailable"
        artifact.removeValue(forKey: "sourceProof")
        unavailableMap["artifacts"] = [artifact]
        let unavailable = try catalog([unavailableMap]).packages[0]
        check(compatible(unavailable) && !unavailable.hasUsableMainArtifact,
              "unavailable T-MZ package without proof stays visible and non-installable")
    }

    static func proof(_ archive: String, contours: Bool = true) throws -> TMZSourceProof {
        try package(contours: contours, archive: archive).mainArtifact!.tmzSourceProof!
    }

    static func archiveSafety() throws {
        func safe(_ archive: String, _ proof: TMZSourceProof) -> Bool {
            (try? TMZArchiveSafety.validate(archiveURL: fixtures.appendingPathComponent(archive), proof: proof)) != nil
        }
        check(safe("gmapsupp_261119cntr.zip", try proof("gmapsupp_261119cntr.zip", contours: true)),
              "contours archive with gmapsupp.img, gmapsupp_search.img, and osmmap_license.txt is accepted")
        check(safe("gmapsupp_261119.zip", try proof("gmapsupp_261119.zip", contours: false)),
              "standard archive is accepted")
        for (archive, label) in [
            ("bad-extra-img.zip", "an extra IMG"),
            ("bad-side-file.zip", "an unreviewed side file"),
            ("bad-stored.zip", "a stored payload"),
            ("bad-path.zip", "a subfolder payload"),
        ] {
            check(!safe(archive, try proof(archive)), "archive with \(label) is refused before extraction")
        }
        check(!safe("gmapsupp_261119cntr.zip", try proof("bad-family.zip")),
              "archive whose CRC-32 differs from proof is refused")
    }

    static func sourceValidation() throws {
        func copy(_ image: String) throws -> URL {
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let target = dir.appendingPathComponent("gmapsupp.img")
            try FileManager.default.copyItem(at: fixtures.appendingPathComponent(image), to: target)
            return target
        }
        check((try? MapSourceValidator().validate(fileURL: copy("gmapsupp_261119cntr.img"), expectedPackage: package(contours: true))) != nil,
              "contours IMG validates against size, CRC-32, title, FID 42, 00000TMZ.TYP, and build day")
        check((try? MapSourceValidator().validate(fileURL: copy("gmapsupp_261119.img"), expectedPackage: package(contours: false))) != nil,
              "standard IMG validates against its proof")
        check((try? MapSourceValidator().validate(fileURL: copy("gmapsupp_261119cntr.img"), expectedPackage: package(contours: false))) == nil,
              "contours IMG never validates as standard package")
    }

    static func acquisition() async throws {
        let cntr = try package(contours: true)
        let main = try await acquire(cntr)
        defer { try? FileManager.default.removeItem(at: main.workspaceRootURL!) }
        try Stage42ArtifactValidator().validate(artifact: main, package: cntr)
        check(main.packageFormat == .zip
            && main.targetFilename == "terento_tmz_japan_contours.img"
            && main.version == MapVersion(year: 2026, month: 11, day: 21),
              "ZIP → archive safety → gmapsupp.img (ignoring gmapsupp_search.img) → Stage42 validator")

        for archive in ["bad-extra-img.zip", "bad-side-file.zip", "bad-path.zip", "bad-family.zip", "bad-typ.zip", "bad-title.zip", "bad-date.zip"] {
            do {
                let bound = try package(archive: archive)
                let wrong = try await acquire(bound, serving: archive)
                try? FileManager.default.removeItem(at: wrong.workspaceRootURL!)
                fatalError("FAIL: \(archive) was acquired")
            } catch {
                print("PASS: \(archive) is not acquired")
            }
        }
    }

    static func downloadRecovery() async throws {
        var body = Data(count: 8 * 1024 * 1024)
        for i in body.indices { body[i] = UInt8(truncatingIfNeeded: i &* 17 &+ 3) }
        let pkg = MapPackage(
            id: "tmz-japan-contours", providerId: "tmz", regionId: "JAPAN-CONTOURS",
            name: "Japan (with contours)", version: MapVersion(year: 2026, month: 11, day: 21)!,
            sizeBytes: UInt64(body.count), sourceURL: URL(string: contoursURL)!,
            releaseDate: "2026-11-21", identifier: "japan-contours",
            downloadSizeBytes: UInt64(body.count), installSizeBytes: UInt64(body.count),
            providerRegionId: "japan-contours", canonicalRegionId: "JAPAN-CONTOURS",
            mapType: "tmz-contours", countryCodes: ["JP"], regionKind: .country
        )
        let store = MapDownloadResumeStore()
        let client = FoundationMapPackageDownloadClient(
            sourcePolicyRegistry: .bundled,
            sessionConfiguration: {
                let config = URLSessionConfiguration.ephemeral
                config.protocolClasses = [FlakyTMZServerProtocol.self]
                return config
            },
            resumeStore: store,
            automaticRetryDelays: [0, 0],
            sleep: { _ in }
        )

        // 5 failures in a row (drops + silent premature EOF + transient 503 on resume),
        // exceeding the default 2-3 retry count, yet making progress so T-MZ recovers completely!
        FlakyTMZServerProtocol.configure(.init(
            body: body,
            steps: [
                .dropAfter(2 * 1024 * 1024),
                .transientHTTP(503),
                .truncateAfter(2 * 1024 * 1024),
                .dropAfter(1536 * 1024),
                .transientHTTP(502),
                .complete
            ]
        ))
        let response = try await client.download(package: pkg, onProgress: {
            FlakyTMZServerProtocol.noteDelivered($0.bytesDownloaded)
        })
        defer { try? FileManager.default.removeItem(at: response.temporaryFileURL) }
        let downloaded = try Data(contentsOf: response.temporaryFileURL)
        check(downloaded == body && FlakyTMZServerProtocol.requests.count == 6 && store.count == 0,
              "T-MZ download recovers seamlessly across TCP drops, silent EOF truncation, and transient 503/502 via Range + If-Range")
    }

    static func rescanAndConflicts() throws {
        let cntrPrefix = try prefix("gmapsupp_261119cntr.img")
        let version = MapVersion(year: 2026, month: 11, day: 21)!
        func file(_ name: String, _ id: UInt32) -> DeviceFile {
            DeviceFile(itemID: id, parentID: 9, storageID: 1, path: "/GARMIN/" + name, filename: name, sizeBytes: 65536, isFolder: false)
        }
        let managed = file("terento_tmz_japan_contours.img", 10)
        let copied = file("gmapsupp.img", 11)
        let reader = PathPrefixReader(prefixes: [managed.path: cntrPrefix, copied.path: cntrPrefix])
        let records = [MapOwnershipRecord(
            devicePath: managed.path, filename: managed.filename, providerId: "tmz",
            regionId: "JAPAN-CONTOURS", version: version, sizeBytes: 65536,
            packageID: "tmz-japan-contours", artifactID: "tmz-japan-contours-main", artifactKind: .main
        )]
        let scan = GarminMapScanner().scan(
            files: [managed, copied], reader: reader,
            ownershipRecords: records, recognizedProviderIDs: ["tmz"]
        )
        let own = scan.installedMaps.first { $0.sourceFile.filename == managed.filename }
        check(own?.managementState == .managedByTerento && own?.provider == "T-MZ"
            && own?.region == "JAPAN-CONTOURS" && own?.version == version,
              "Terento's managed T-MZ file is recognized from header and ownership record")
        let foreign = scan.installedMaps.first { $0.sourceFile.filename == copied.filename }
        check(foreign?.provider == "T-MZ" && foreign?.managementState != .managedByTerento,
              "hand-copied T-MZ gmapsupp.img is recognized without claiming ownership")

        // Mutual exclusion between japan-contours and japan
        let cntrPkg = try package(contours: true)
        let stdPkg = try package(contours: false)
        check(TMZProviderAdapter.selectionConflictReason([cntrPkg, stdPkg]) != nil,
              "selecting both T-MZ variants together is blocked")
        check(TMZProviderAdapter.conflicts(stdPkg, provider: own?.provider, region: own?.region),
              "installing standard T-MZ is blocked while contours variant is installed")
        check(TMZProviderAdapter.conflicts(stdPkg, filename: managed.filename),
              "Stage42 filename guard blocks standard T-MZ while contours file exists")
        check(!TMZProviderAdapter.conflicts(cntrPkg, filename: managed.filename),
              "updating the same T-MZ variant is allowed")
    }

    static func liveSiteSmokeTest() async throws {
        let resolved = await TMZLiveCatalogResolver().loadCatalog()
        check(resolved != nil && (resolved?.packages.count ?? 0) >= 1,
              "LIVE: TMZLiveCatalogResolver discovered and verified real package(s) from https://tmz.skr.jp/data/gmap.html")
        if let resolved {
            check(MapCatalogClientCompatibilityValidator().isCompatible(resolved),
                  "LIVE: real T-MZ catalog passes full client compatibility validation")
            for pkg in resolved.packages {
                let proof = pkg.mainArtifact!.tmzSourceProof!
                print("LIVE PACKAGE: id=\(pkg.id) name=\"\(pkg.name)\" build=\(pkg.version.description) osmDate=\(proof.publishedDate) url=\(proof.sourceURL.absoluteString) download=\(proof.downloadSizeBytes) install=\(proof.installSizeBytes) crc32=\(proof.crc32)")
            }
        }
        let merged = try await MapCatalogLoader().loadCurrentMerged()
        let tmzPackages = merged.catalog.packages(forProviderId: "tmz")
        check(merged.source == .remote && merged.catalog.provider(for: "tmz")?.name == "T-MZ" && tmzPackages.count == 2,
              "LIVE: MapCatalogLoader().loadCurrentMerged() merges live api.terento.app catalog with live T-MZ Japan maps")
        if let contours = tmzPackages.first(where: { $0.id == "tmz-japan-contours" }) {
            try await MapCatalogLoader().validateCurrentAvailability(package: contours)
            print("PASS: LIVE: MapCatalogLoader().validateCurrentAvailability() authorizes tmz-japan-contours")
        }
    }
}

import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
}

/// Serves `<url file name>` from the fixture directory, or the named override.
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

typealias Edit = (inout [String: Any], inout [String: Any]) -> Void

/// OpenFietsMap client rules. The IMG and ZIP fixtures are synthetic copies of
/// the measured layouts of the author's GPS files; they are not hardware evidence.
@main struct OpenFietsMapTests {
    static let root = "https://ligfietser.dev.openstreetmap.org/openfietsmap/"
    static let beneluxURL = root + "benelux/full/OpenFietsMap.zip"
    static let europeURL = root + "EU_2026/0310/GPS/OFM(EU2026_C_GPS).zip"
    static let fixtures = URL(fileURLWithPath: ProcessInfo.processInfo.environment["TERENTO_OPENFIETSMAP_FIXTURES"]!)

    static func check(_ condition: Bool, _ label: String) {
        guard condition else { fatalError("FAIL: \(label)") }
        print("PASS: \(label)")
    }

    static func meta(_ archive: String) throws -> [String: Any] {
        let all = try JSONSerialization.jsonObject(with: Data(contentsOf: fixtures.appendingPathComponent("meta.json")))
        return (all as! [String: Any])[archive] as! [String: Any]
    }

    static func prefix(_ image: String) throws -> [UInt8] {
        Array(try Data(contentsOf: fixtures.appendingPathComponent(image)).prefix(4096))
    }

    /// One catalog-v6 package as the API publishes it, its proof bound to a fixture archive.
    static func document(europe: Bool = false, archive: String? = nil, edit: Edit = { _, _ in }) throws -> [String: Any] {
        let key = europe ? "europe-c" : "benelux"
        let url = europe ? europeURL : beneluxURL
        let sizes = try meta(archive ?? (europe ? "OFM(EU2026_C_GPS).zip" : "OpenFietsMap.zip"))
        let payload = europe ? "garmin/gmapsupp.img" : "gmapsupp.img"
        let day = europe ? "2026-03-10" : "2026-11-21"
        var proof: [String: Any] = [
            "sourceURL": url, "etag": "\"6ee27b-6455f3f7d6e80\"", "lastModified": "Sat, 21 Nov 2026 00:46:41 GMT",
            "downloadSizeBytes": sizes["downloadSizeBytes"]!, "installSizeBytes": sizes["installSizeBytes"]!,
            "payloadPath": payload, "crc32": sizes["crc32"]!, "sourceIdentity": "openfietsmap:" + key,
            "area": key, "mapType": "ofm-full", "familyId": europe ? 20264 : 10010,
            "imgTitle": europe ? "OFM(EU2026_C)" : "OFM_BNL(21-11-2026)", "generatedAt": day + "T00:00:00+00:00",
            "headerIdentityValidated": true, "revision": String(repeating: "ab", count: 32)
        ]
        var map: [String: Any] = [
            "id": "openfietsmap-" + key, "region": key.uppercased(), "name": europe ? "Europe: Central Europe" : "Benelux",
            "country": NSNull(),
            "version": europe ? ["year": 2026, "month": 3, "day": 10] : ["year": 2026, "month": 11, "day": 21],
            "sizeBytes": sizes["downloadSizeBytes"]!, "downloadSizeBytes": sizes["downloadSizeBytes"]!,
            "installSizeBytes": sizes["installSizeBytes"]!, "sourceURL": url, "identifier": key, "providerRegionId": key,
            "canonicalRegionId": key.uppercased(),
            "countryCodes": europe ? ["AT", "CH", "CZ", "DE", "DK", "LI", "PL"] : ["BE", "LU", "NL"],
            "regionKind": "multiCountry", "tags": ["ofm-full"], "capabilities": ["main"], "release": day,
            "mapType": "ofm-full", "geographicRegionId": key.uppercased()
        ]
        edit(&map, &proof)
        map["artifacts"] = [[
            "id": "openfietsmap-\(key)-main", "kind": "main", "required": true, "sourceURL": proof["sourceURL"] ?? url,
            "sizeBytes": proof["installSizeBytes"] ?? 0, "downloadSizeBytes": proof["downloadSizeBytes"] ?? 0,
            "checksum": NSNull(), "contentType": "application/zip", "validationState": "validated",
            "installPayloadPath": proof["payloadPath"] ?? payload, "sourceProof": proof
        ] as [String: Any]]
        return map
    }

    static func catalog(_ maps: [[String: Any]], status: String = "ACTIVE", unpaused: Set<String> = []) throws -> MapCatalog {
        let json: [String: Any] = ["catalogVersion": 1, "updatedAt": "2026-11-21T00:00:00Z", "providers": [[
            "id": "openfietsmap", "name": "OpenFietsMap", "status": status, "website": "https://www.openfietsmap.nl/",
            "maps": maps
        ]]]
        return try MapCatalogDocumentDecoder(unpausedProviderIDs: unpaused).decode(JSONSerialization.data(withJSONObject: json))
    }

    static func package(europe: Bool = false, archive: String? = nil, edit: Edit = { _, _ in }) throws -> MapPackage {
        try catalog([document(europe: europe, archive: archive, edit: edit)]).packages[0]
    }

    static func compatible(_ package: MapPackage) -> Bool {
        MapCatalogClientCompatibilityValidator().isPackageCompatible(package)
    }

    static func acquire(_ package: MapPackage, serving archive: String? = nil) async throws -> ValidatedMapArtifact {
        let overrides = archive.map { ["OpenFietsMap.zip": $0] } ?? [:]
        let acquisition = MapPackageAcquirer(downloadClient: FixtureDownload(directory: fixtures, overrides: overrides),
            workspaceFactory: {
                try MapAcquisitionWorkspace(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
            })
        return try await acquisition.acquire(package: package)
    }

    static func main() async throws {
        try headers()
        try catalogContract()
        try archiveSafety()
        try sourceValidation()
        try await acquisition()
        try rescan()
    }

    static func headers() throws {
        let benelux = try prefix("OpenFietsMap.img"), europe = try prefix("OFM(EU2026_C_GPS).img")
        check(OpenFietsMapIMGMetadata.title(benelux) == "OFM_BNL(21-11-2026)"
            && OpenFietsMapIMGMetadata.title(europe) == "OFM(EU2026_C)", "the header description is the map title")
        let metadata = GarminIMGMetadataParser().parse(benelux)
        check(metadata?.provider == "OpenFietsMap" && metadata?.region == "BENELUX"
            && metadata?.version == MapVersion(year: 2026, month: 11, day: 21) && metadata?.familyId == 10010,
              "a Benelux header names provider, package, build day and family ID")
        check(GarminIMGMetadataParser().parse(europe)?.region == "EUROPE-C",
              "a Europe header names its area from title and family ID")
        let keys: [(String, Set<UInt16>, String?)] = [
            ("OFM_light(21-11-2026)", [20010], "benelux-light"), ("OFM_hike(21-11-2026)", [50010], "benelux-hiking"),
            ("OFM_DE(07-11-2026)", [4900], "germany"), ("OFM_Alps(31-07-2026)", [4143], "alps"),
            ("OFM_Atlantic", [34351], "atlantic"), ("OFM_Baleares", [34971], "baleares"), ("OFM_Island", [35400], "iceland"),
            ("OFM(EU2026_GB)", [20261], "europe-gb"), ("OFM(EU2027_E)", [20277], "europe-e"),
            ("OFM_BNL(21-11-2026)", [20010], nil), ("OFM(EU2026_C)", [20263], nil), ("OFM_BNL(31-02-2026)", [10010], nil),
            ("OFM_BNL(21-11-2026)", [10010, 20010], nil), ("OFM_NL(21-11-2026)", [10010], nil)
        ]
        for (title, families, key) in keys {
            check(OpenFietsMapIMGMetadata.key(title: title, familyIDs: families) == key,
                  "title \(title) with family \(families.sorted()) is \(key ?? "not a reviewed package")")
        }
    }

    static func catalogContract() throws {
        let benelux = try package(), europe = try package(europe: true)
        check(benelux.mainArtifact?.openFietsMapSourceProof?.familyId == 10010
            && benelux.mainArtifact?.sourceProof == nil && benelux.mainArtifact?.osmapaSourceProof == nil
            && benelux.mainArtifact?.luckyMapsSourceProof == nil, "catalog-v6 proofs decode only as OpenFietsMap proofs")
        check(compatible(benelux) && OpenFietsMapProviderAdapter().expectedIMGIdentity(for: benelux) == benelux.identity,
              "the Benelux package is compatible")
        check(compatible(europe), "a Europe area with its folder date is compatible")
        check(MapProviderDisplay.downloadName("openfietsmap") == "OpenFietsMap", "the provider is named OpenFietsMap")
        let paused = try catalog([try document()], status: "PAUSED")
        check(paused.packages.allSatisfy { MapPackageAcquisitionPolicyResolver().availability(for: $0) != .available },
              "a paused provider cannot be acquired")
        let serverPaused = try catalog([try document().merging(["downloadBlockReason": "PROVIDER_PAUSED"]) { $1 }],
                                       status: "PAUSED", unpaused: MapCatalogDebugUnpause.parse("openfietsmap"))
        check(serverPaused.packages.allSatisfy { MapPackageAcquisitionPolicyResolver().availability(for: $0) == .available },
              "the Debug unpause option lifts PROVIDER_PAUSED for OpenFietsMap")

        func url(_ value: String) -> Edit { { map, proof in map["sourceURL"] = value; proof["sourceURL"] = value } }
        let tampering: [(String, Edit)] = [
            ("another host", url("https://ligfietser.dev.openstreetmap.org.evil.test/openfietsmap/benelux/full/OpenFietsMap.zip")),
            ("the stale nluug mirror", url("https://ftp.nluug.nl/maps/openfietsmap/benelux/full/OpenFietsMap.zip")),
            ("a query string", url(beneluxURL + "?x=1")),
            ("the BaseCamp edition", url(root + "germany/OFM_DE(07-11-2026_pc).zip")),
            ("another package's file", url(root + "benelux/light/OpenFietsMap_light.zip")),
            ("a title for another date", { _, proof in proof["imgTitle"] = "OFM_BNL(22-11-2026)" }),
            ("another family ID", { _, proof in proof["familyId"] = 10011 }),
            ("another payload path", { _, proof in proof["payloadPath"] = "garmin/gmapsupp.img" }),
            ("another map type", { map, _ in map["mapType"] = "ofm-light" }),
            ("a weak ETag", { _, proof in proof["etag"] = "W/\"x\"" }),
            ("a size that differs from the catalog", { _, proof in proof["installSizeBytes"] = 1 }),
            ("an IMG over 4 GiB", { map, proof in map["installSizeBytes"] = 4_294_967_296; proof["installSizeBytes"] = 4_294_967_296 }),
            ("a non-hex CRC-32", { _, proof in proof["crc32"] = "zzzzzzzz" }),
            ("an id that is not the key", { map, _ in map["id"] = "openfietsmap-benelux-2" }),
            ("Russia as a country", { map, _ in map["countryCodes"] = ["BE", "RU"] }),
            ("an unknown key", { map, proof in
                map["providerRegionId"] = "france"; map["identifier"] = "france"; map["id"] = "openfietsmap-france"
                map["canonicalRegionId"] = "FRANCE"; map["region"] = "FRANCE"; proof["area"] = "france" }),
            ("an OSMapaPL-shaped proof", { _, proof in proof = ["payloadPath": "gmapsupp.img", "crc32": "00000000"] })
        ]
        for (label, edit) in tampering {
            check(!compatible(try package(edit: edit)), "catalog rejects \(label)")
        }
        let europeTampering: [(String, Edit)] = [
            ("a build day more than three days after the folder", { map, proof in
                map["version"] = ["year": 2026, "month": 3, "day": 14]; proof["generatedAt"] = "2026-03-14T00:00:00+00:00" }),
            ("a build day before the folder", { map, proof in
                map["version"] = ["year": 2026, "month": 3, "day": 9]; proof["generatedAt"] = "2026-03-09T00:00:00+00:00" }),
            ("last year's family ID", { _, proof in proof["familyId"] = 20254 }),
            ("a folder year that is not the file year", url(root + "EU_2026/0310/GPS/OFM(EU2025_C_GPS).zip"))
        ]
        for (label, edit) in europeTampering {
            check(!compatible(try package(europe: true, edit: edit)), "catalog rejects a Europe area with \(label)")
        }
        let laterBuild = try package(europe: true) { map, proof in
            map["version"] = ["year": 2026, "month": 3, "day": 11]; proof["generatedAt"] = "2026-03-11T00:00:00+00:00"
        }
        check(compatible(laterBuild), "a Europe area built the day after its folder date is compatible")

        var unavailableMap = try document()
        var artifact = (unavailableMap["artifacts"] as! [[String: Any]])[0]
        artifact["validationState"] = "unavailable"
        artifact.removeValue(forKey: "sourceProof")
        unavailableMap["artifacts"] = [artifact]
        let unavailable = try catalog([unavailableMap]).packages[0]
        check(compatible(unavailable) && !unavailable.hasUsableMainArtifact,
              "an unavailable package without proof stays visible and is never installable")
        artifact["sourceProof"] = (try document()["artifacts"] as! [[String: Any]])[0]["sourceProof"]
        unavailableMap["artifacts"] = [artifact]
        check(!compatible(try catalog([unavailableMap]).packages[0]), "an unavailable package must not carry proof")

        let published = [
            ("benelux/full/OpenFietsMap.zip", "benelux"), ("benelux/light/OpenFietsMap_light.zip", "benelux-light"),
            ("benelux/hike/gmapsupp.zip", "benelux-hiking"), ("germany/OFM_DE(07-11-2026_gps).zip", "germany"),
            ("Alps/OFM_Alps(31-07-2026_gps).zip", "alps"), ("Atlantic/OFM_Atlantic(21-09-2026_gps).zip", "atlantic"),
            ("Baleares/OFM_Baleares(10-01-2026_gps).zip", "baleares"), ("Iceland/OFM_Iceland(10-01-2026_gps).zip", "iceland")
        ] + ["GB", "N", "W", "C", "SW", "SE", "E"].map { ("EU_2026/0310/GPS/OFM(EU2026_\($0)_GPS).zip", "europe-" + $0.lowercased()) }
        let policy = ReviewedProviderURLPolicyRegistry.bundled.policy(for: "openfietsmap")!
        for (path, key) in published {
            let value = URL(string: root + path)!
            check(OpenFietsMapProviderAdapter.reviewedSource(value)?.key == key && (try? policy.validate(value)) != nil,
                  "the published GPS file \(path) is package \(key)")
        }
        check(OpenFietsMapProviderAdapter.reviewedSource(URL(string: europeURL)!)?.familyID == 20264,
              "the Europe 2026 Central area has family ID 20264")
        for value in ["http://ligfietser.dev.openstreetmap.org/openfietsmap/benelux/full/OpenFietsMap.zip",
                      "https://ligfietser.dev.openstreetmap.org:8443/openfietsmap/benelux/full/OpenFietsMap.zip",
                      root + "germany/OFM_DE(31-02-2026_gps).zip", root + "germany/OFM_DE%2807-11-2026_gps%29.zip",
                      root + "germany/OFM_DE(07-11-2026_gmap).zip", root + "EU_2026/0310/PC/OFM(EU2026_C_PC).zip",
                      root + "EU_2026/0310/GPS/OFM(EU2026_X_GPS).zip", root + "benelux/full/../light/OpenFietsMap_light.zip",
                      "https://ligfietser.dev.openstreetmap.org/other/benelux/full/OpenFietsMap.zip"] {
            check((try? policy.validate(URL(string: value)!)) == nil, "unreviewed URL \(value) is refused")
        }
    }

    static func proof(_ archive: String, europe: Bool = false) throws -> OpenFietsMapSourceProof {
        try package(europe: europe, archive: archive).mainArtifact!.openFietsMapSourceProof!
    }

    static func archiveSafety() throws {
        func safe(_ archive: String, _ proof: OpenFietsMapSourceProof) -> Bool {
            (try? OpenFietsMapArchiveSafety.validate(archiveURL: fixtures.appendingPathComponent(archive), proof: proof)) != nil
        }
        check(safe("OpenFietsMap.zip", try proof("OpenFietsMap.zip")),
              "the Benelux archive with readme pages and the Windows installer is accepted")
        check(safe("OFM(EU2026_C_GPS).zip", try proof("OFM(EU2026_C_GPS).zip", europe: true)),
              "the Europe archive with its garmin/ folder and readme texts is accepted")
        for (archive, label) in [("bad-second-img.zip", "a second IMG"), ("bad-side-file.zip", "an unreviewed side file"),
                                 ("bad-stored.zip", "a stored payload"), ("bad-path.zip", "the map in another folder")] {
            check(!safe(archive, try proof(archive)), "an archive with \(label) is refused before extraction")
        }
        check(!safe("OpenFietsMap.zip", try proof("bad-family.zip")), "an archive whose CRC-32 is not the proof is refused")
    }

    static func copy(_ image: String) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = directory.appendingPathComponent("gmapsupp.img")
        try FileManager.default.copyItem(at: fixtures.appendingPathComponent(image), to: target)
        return target
    }

    static func sourceValidation() throws {
        check((try? MapSourceValidator().validate(fileURL: copy("OpenFietsMap.img"), expectedPackage: package())) != nil,
              "the whole Benelux IMG matches size, CRC-32, title, family ID and build day")
        check((try? MapSourceValidator().validate(fileURL: copy("OFM(EU2026_C_GPS).img"),
                                                   expectedPackage: package(europe: true))) != nil,
              "the whole Europe IMG matches its proof")
        check((try? MapSourceValidator().validate(fileURL: copy("OpenFietsMap.img"), expectedPackage: package(europe: true))) == nil,
              "a Benelux IMG never validates as a Europe area")
    }

    static func acquisition() async throws {
        let benelux = try package()
        let main = try await acquire(benelux)
        defer { try? FileManager.default.removeItem(at: main.workspaceRootURL!) }
        try Stage42ArtifactValidator().validate(artifact: main, package: benelux)
        check(main.packageFormat == .zip && main.targetFilename == "terento_openfietsmap_benelux.img"
            && main.version == MapVersion(year: 2026, month: 11, day: 21),
              "ZIP → archive check → extracted IMG → final write validator for Benelux")
        let europe = try package(europe: true)
        let area = try await acquire(europe)
        defer { try? FileManager.default.removeItem(at: area.workspaceRootURL!) }
        try Stage42ArtifactValidator().validate(artifact: area, package: europe)
        check(area.targetFilename == "terento_openfietsmap_europe_c.img" && area.localIMGURL.lastPathComponent == "gmapsupp.img",
              "the Europe map is taken from its garmin/ folder")
        for archive in ["bad-second-img.zip", "bad-side-file.zip", "bad-path.zip", "bad-family.zip", "bad-title.zip", "bad-date.zip"] {
            do {
                let bound = try package(archive: archive)
                let wrong = try await acquire(bound, serving: archive)
                try? FileManager.default.removeItem(at: wrong.workspaceRootURL!)
                fatalError("FAIL: \(archive) was acquired")
            } catch { print("PASS: \(archive) is not acquired") }
        }
        do {
            let wrong = try await acquire(benelux, serving: "bad-family.zip")
            try? FileManager.default.removeItem(at: wrong.workspaceRootURL!)
            fatalError("FAIL: a served file that differs from the proof was acquired")
        } catch { print("PASS: a served file that differs from the proof is not acquired") }
        var changed = try Data(contentsOf: main.localIMGURL)
        changed[changed.count - 1] ^= 1
        try changed.write(to: main.localIMGURL)
        do { try Stage42ArtifactValidator().validate(artifact: main, package: benelux); fatalError("FAIL: tampered map accepted") }
        catch { print("PASS: a changed map is rejected at the final boundary") }
    }

    static func rescan() throws {
        let beneluxPrefix = try prefix("OpenFietsMap.img")
        let version = MapVersion(year: 2026, month: 11, day: 21)!
        func file(_ name: String, _ id: UInt32) -> DeviceFile {
            DeviceFile(itemID: id, parentID: 9, storageID: 1, path: "/GARMIN/" + name, filename: name, sizeBytes: 65536, isFolder: false)
        }
        let managed = file("terento_openfietsmap_benelux.img", 10)
        let copied = file("gmapsupp.img", 11)
        let reader = PathPrefixReader(prefixes: [managed.path: beneluxPrefix, copied.path: beneluxPrefix])
        let records = [MapOwnershipRecord(devicePath: managed.path, filename: managed.filename, providerId: "openfietsmap",
            regionId: "BENELUX", version: version, sizeBytes: 65536, packageID: "openfietsmap-benelux",
            artifactID: "openfietsmap-benelux-main", artifactKind: .main)]
        let result = GarminMapScanner().scan(files: [managed, copied], reader: reader,
                                             ownershipRecords: records, recognizedProviderIDs: ["openfietsmap"])
        let own = result.installedMaps.first { $0.sourceFile.filename == managed.filename }
        check(own?.managementState == .managedByTerento && own?.provider == "OpenFietsMap" && own?.region == "BENELUX"
            && own?.version == version, "Terento's own Benelux file is recognized from its header and record")
        let foreign = result.installedMaps.first { $0.sourceFile.filename == copied.filename }
        check(foreign?.provider == "OpenFietsMap" && foreign?.managementState != .managedByTerento,
              "a hand-copied OpenFietsMap gmapsupp.img is recognized but not claimed")
    }
}

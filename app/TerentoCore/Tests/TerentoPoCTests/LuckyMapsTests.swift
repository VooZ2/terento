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

/// Lucky Maps client rules. The IMG fixtures are built from the real
/// luckymaps.ch Andorra header and MPS bytes; they are not hardware evidence.
@main struct LuckyMapsTests {
    static let root = "https://luckymaps.ch/assets/maps/"
    static let fixtures = URL(fileURLWithPath: ProcessInfo.processInfo.environment["TERENTO_LUCKYMAPS_FIXTURES"]!)

    static func check(_ condition: @autoclosure () -> Bool, _ label: String) {
        guard condition() else { fatalError("FAIL: \(label)") }
        print("PASS: \(label)")
    }

    static func size(_ fixture: String) throws -> Int {
        try Data(contentsOf: fixtures.appendingPathComponent(fixture + ".img")).count
    }

    static func proof(url: String, stem: String, kind: String, created: String, size: Int, family: Int) -> [String: Any] {
        [
            "sourceURL": url, "etag": "\"303400-65cff29397879\"", "lastModified": "Sun, 04 Oct 2026 08:00:38 GMT",
            "downloadSizeBytes": size, "installSizeBytes": size, "sourceIdentity": "luckymaps:\(stem):\(kind)",
            "familyId": family, "imgTitle": stem, "createdAt": created, "publisher": "luckymaps.ch",
            "sha256": NSNull(), "headerIdentityValidated": true, "revision": String(repeating: "ab", count: 32)
        ]
    }

    /// One catalog-v6 package as the API publishes it, proofs bound to fixtures.
    static func document(main mainFixture: String = "andorra", contour contourFixture: String? = "andorra-ct",
                         edit: (inout [String: Any], inout [String: Any], inout [String: Any]) -> Void = { _, _, _ in })
        throws -> [String: Any] {
        let mainURL = root + "andorra.img", contourURL = root + "andorra-ct.img"
        let mainSize = try size(mainFixture)
        var mainProof = proof(url: mainURL, stem: "andorra", kind: "main", created: "2026-10-03", size: mainSize, family: 55001)
        var contourProof = proof(url: contourURL, stem: "andorra-ct", kind: "contours", created: "2024-03-02",
                                 size: try contourFixture.map(size) ?? 0, family: 25001)
        var map: [String: Any] = [
            "id": "luckymaps-andorra", "region": "ANDORRA", "name": "Andorra", "country": "AD",
            "version": ["year": 2026, "month": 10, "day": 3], "sizeBytes": mainSize, "downloadSizeBytes": mainSize,
            "installSizeBytes": mainSize, "sourceURL": mainURL, "identifier": "andorra", "providerRegionId": "andorra",
            "canonicalRegionId": "ANDORRA", "countryCodes": ["AD"], "regionKind": "country", "tags": ["Europe"],
            "capabilities": contourFixture == nil ? ["main"] : ["main", "contours"], "release": "2026-10-03"
        ]
        edit(&map, &mainProof, &contourProof)
        var artifacts: [[String: Any]] = [[
            "id": "luckymaps-andorra-main", "kind": "main", "required": true, "sourceURL": mainProof["sourceURL"] ?? mainURL,
            "sizeBytes": mainProof["installSizeBytes"] ?? mainSize, "downloadSizeBytes": mainProof["downloadSizeBytes"] ?? mainSize,
            "checksum": mainProof["sha256"] ?? NSNull(), "validationState": "validated", "sourceProof": mainProof
        ]]
        if contourFixture != nil {
            artifacts.append([
                "id": "luckymaps-andorra-contours", "kind": "contours", "required": false,
                "sourceURL": contourProof["sourceURL"] ?? contourURL,
                "sizeBytes": contourProof["installSizeBytes"] ?? 0, "downloadSizeBytes": contourProof["downloadSizeBytes"] ?? 0,
                "checksum": contourProof["sha256"] ?? NSNull(), "validationState": "validated", "sourceProof": contourProof
            ])
        }
        map["artifacts"] = artifacts
        return map
    }

    static func catalog(_ maps: [[String: Any]], status: String = "ACTIVE", unpaused: Set<String> = []) throws -> MapCatalog {
        let json: [String: Any] = ["catalogVersion": 1, "updatedAt": "2026-11-21T00:00:00Z", "providers": [[
            "id": "luckymaps", "name": "Lucky Maps", "status": status, "website": "https://luckymaps.ch/", "maps": maps
        ]]]
        return try MapCatalogDocumentDecoder(unpausedProviderIDs: unpaused).decode(JSONSerialization.data(withJSONObject: json))
    }

    static func package(main: String = "andorra", contour: String? = "andorra-ct",
                        edit: (inout [String: Any], inout [String: Any], inout [String: Any]) -> Void = { _, _, _ in })
        throws -> MapPackage {
        try catalog([document(main: main, contour: contour, edit: edit)]).packages[0]
    }

    static func compatible(_ package: MapPackage) -> Bool {
        MapCatalogClientCompatibilityValidator().isPackageCompatible(package)
    }

    static func acquire(_ package: MapPackage, artifact: MapArtifact? = nil,
                        overrides: [String: String] = [:]) async throws -> ValidatedMapArtifact {
        let names = ["andorra.img": "andorra.img", "andorra-ct.img": "andorra-ct.img"]
            .merging(overrides) { $1 }
        let acquisition = MapPackageAcquirer(downloadClient: FixtureDownload(directory: fixtures, overrides: names),
            workspaceFactory: {
                try MapAcquisitionWorkspace(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
            })
        return try await acquisition.acquire(package: package, artifact: artifact)
    }

    static func main() async throws {
        try headers()
        try catalogContract()
        try sourceValidation()
        try await acquisition()
        try rescan()
    }

    static func headers() throws {
        let main = Array(try Data(contentsOf: fixtures.appendingPathComponent("andorra.img")).prefix(4096))
        let contour = Array(try Data(contentsOf: fixtures.appendingPathComponent("andorra-ct.img")).prefix(4096))
        check(LuckyMapsIMGMetadata.title(main) == "andorra" && LuckyMapsIMGMetadata.title(contour) == "andorra-ct",
              "the header description is the file stem")
        let metadata = LuckyMapsIMGMetadata.metadata(main, regionId: "ANDORRA", kind: .main)
        check(metadata?.provider == "Lucky Maps" && metadata?.region == "ANDORRA"
            && metadata?.version == MapVersion(year: 2026, month: 10, day: 3) && metadata?.familyId == 55001,
              "a main header gives region, creation day and one MDR family ID")
        let contourMetadata = LuckyMapsIMGMetadata.metadata(contour, regionId: "ANDORRA", kind: .contours)
        check(contourMetadata?.region == "ANDORRA" && contourMetadata?.version == nil,
              "a contour header belongs to its map and carries no package release")
        check(LuckyMapsIMGMetadata.metadata(main, regionId: "LITHUANIA", kind: .main) == nil
            && LuckyMapsIMGMetadata.metadata(contour, regionId: "ANDORRA", kind: .main) == nil
            && LuckyMapsIMGMetadata.metadata(main, regionId: "ANDORRA", kind: .contours) == nil,
              "another region or the other artifact kind is not accepted")
        check(GarminIMGMetadataParser().parse(main)?.provider == nil,
              "without the catalog or manifest a Lucky Maps header names no provider")
    }

    static func catalogContract() throws {
        let decoded = try catalog([try document()])
        let andorra = decoded.packages[0]
        check(andorra.mainArtifact?.luckyMapsSourceProof?.familyId == 55001
            && andorra.mainArtifact?.sourceProof == nil && andorra.mainArtifact?.osmapaSourceProof == nil
            && andorra.artifacts.last?.luckyMapsSourceProof?.familyId == 25001,
              "catalog-v6 proofs decode only as Lucky Maps proofs")
        check(compatible(andorra) && LuckyMapsProviderAdapter().expectedIMGIdentity(for: andorra) == andorra.identity,
              "a main map with its optional contour add-on is compatible")
        check(compatible(try self.package(contour: nil)), "a map without contours is compatible")
        check(MapCatalogLoader.defaultEndpoint?.absoluteString == "https://api.terento.app/maps/catalog-v6.json",
              "the app reads catalog-v6")
        check(MapProviderDisplay.downloadName("luckymaps") == "Lucky Maps", "the provider is named Lucky Maps")
        let paused = try catalog([try document()], status: "PAUSED")
        check(paused.packages.allSatisfy { MapPackageAcquisitionPolicyResolver().availability(for: $0) != .available },
              "a paused provider cannot be acquired")
        let serverPaused = try catalog([try document().merging(["downloadBlockReason": "PROVIDER_PAUSED"]) { $1 }],
                                       status: "PAUSED", unpaused: MapCatalogDebugUnpause.parse("luckymaps"))
        check(serverPaused.packages.allSatisfy { MapPackageAcquisitionPolicyResolver().availability(for: $0) == .available },
              "the Debug unpause option lifts PROVIDER_PAUSED for Lucky Maps")

        let tampering: [(String, (inout [String: Any], inout [String: Any], inout [String: Any]) -> Void)] = [
            ("another host", { map, proof, _ in
                let url = "https://luckymaps.ch.evil.test/assets/maps/andorra.img"
                map["sourceURL"] = url; proof["sourceURL"] = url }),
            ("a query string", { map, proof, _ in
                let url = root + "andorra.img?x=1"
                map["sourceURL"] = url; proof["sourceURL"] = url }),
            ("a file outside the maps folder", { map, proof, _ in
                let url = "https://luckymaps.ch/assets/andorra.img"
                map["sourceURL"] = url; proof["sourceURL"] = url }),
            ("another file stem", { map, proof, _ in
                let url = root + "lithuania.img"
                map["sourceURL"] = url; proof["sourceURL"] = url }),
            ("a header title that is not the stem", { _, proof, _ in proof["imgTitle"] = "Andorra" }),
            ("another publisher", { _, proof, _ in proof["publisher"] = "example.org" }),
            ("a weak ETag", { _, proof, _ in proof["etag"] = "W/\"x\"" }),
            ("a creation day that is not the release", { _, proof, _ in proof["createdAt"] = "2026-10-04" }),
            ("a size that differs from the catalog", { _, proof, _ in proof["installSizeBytes"] = 1 }),
            ("a non-hex SHA-256", { _, proof, _ in proof["sha256"] = "zz" }),
            ("an id that is not derived from the stem", { map, _, _ in map["id"] = "luckymaps-andorra-2" }),
            ("a contour proof for another stem", { _, _, contour in contour["imgTitle"] = "lithuania-ct" }),
            ("a contour with the map family ID", { _, _, contour in contour["familyId"] = 55001 }),
            ("a contour on another host", { _, _, contour in contour["sourceURL"] = "https://example.org/andorra-ct.img" }),
            ("an OSMapaPL-shaped proof", { _, proof, _ in proof = ["payloadPath": "gmapsupp.img", "crc32": "00000000"] })
        ]
        for (label, edit) in tampering {
            check(!compatible(try package(edit: edit)), "catalog rejects \(label)")
        }

        var unavailableMap = try document(contour: nil)
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

        // Lithuania with Andorra's family IDs: each alone is valid, together neither is.
        let lithuania = try document { map, proof, contour in
            map["id"] = "luckymaps-lithuania"; map["providerRegionId"] = "lithuania"; map["identifier"] = "lithuania"
            map["canonicalRegionId"] = "LITHUANIA"; map["region"] = "LITHUANIA"; map["countryCodes"] = ["LT"]
            map["sourceURL"] = root + "lithuania.img"
            proof["sourceURL"] = root + "lithuania.img"; proof["imgTitle"] = "lithuania"
            proof["sourceIdentity"] = "luckymaps:lithuania:main"
            contour["sourceURL"] = root + "lithuania-ct.img"; contour["imgTitle"] = "lithuania-ct"
            contour["sourceIdentity"] = "luckymaps:lithuania-ct:contours"
        }
        check(compatible(try catalog([lithuania]).packages[0]), "a second region alone is compatible")
        let duplicate = MapCatalogClientCompatibilityValidator().acceptCompatiblePackages(try catalog([try document(), lithuania]))
        check(duplicate == nil || duplicate?.catalog.packages.isEmpty == true,
              "two packages naming one Garmin family ID are both dropped")

        let policy = ReviewedProviderURLPolicyRegistry.bundled.policy(for: "luckymaps")!
        for url in [root + "andorra.img", root + "2027-01/US-West.img"] {
            check((try? policy.validate(URL(string: url)!)) != nil, "reviewed URL \(url) is allowed")
        }
        for url in ["http://luckymaps.ch/assets/maps/andorra.img", root + "andorra.img?x=1", root + "andorra.poly",
                    "https://luckymaps.ch:8443/assets/maps/andorra.img", root + "a%2Fb.img", root + "a/b/c/d/andorra.img",
                    "https://luckymaps.ch/assets/andorra.img", root + "../maps/andorra.img"] {
            check((try? policy.validate(URL(string: url)!)) == nil, "unreviewed URL \(url) is refused")
        }
    }

    static func copy(_ fixture: String) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = directory.appendingPathComponent("andorra.img")
        try FileManager.default.copyItem(at: fixtures.appendingPathComponent(fixture + ".img"), to: target)
        return target
    }

    static func sourceValidation() throws {
        let good = try package()
        check((try? LuckyMapsIMGInspection.product(fileURL: fixtures.appendingPathComponent("andorra.img")))?.familyID == 55001,
              "the MPS product file names family ID 55001 and area andorra")
        check((try? MapSourceValidator().validate(fileURL: copy("andorra"), expectedPackage: good)) != nil,
              "the whole main IMG matches size, title, MDR and MPS family, area and publisher")
        let contourPackage = good.acquisitionPackage(for: good.artifacts[1])
        check((try? MapSourceValidator().validate(fileURL: copy("andorra-ct"), expectedPackage: contourPackage)) != nil,
              "the contour IMG matches its own proof")
        for (fixture, label) in [("bad-publisher", "MPS publisher is not luckymaps.ch"), ("bad-area", "MPS area is not the stem"),
                                 ("bad-mps-family", "MPS family differs from the MDR"), ("bad-title", "header title is another stem"),
                                 ("bad-date", "creation day differs from the release"), ("ct-as-main", "contour file sits in the map slot")] {
            let bound = try package(main: fixture)
            check((try? MapSourceValidator().validate(fileURL: copy(fixture), expectedPackage: bound)) == nil,
                  "nothing reaches the device when the \(label)")
        }
        let sha = try package { _, proof, _ in proof["sha256"] = String(repeating: "0", count: 64) }
        check(compatible(sha), "a published SHA-256 equal to the artifact checksum is accepted")
        let unbound = sha.withArtifacts(sha.artifacts.map { artifact in
            guard artifact.kind == .main else { return artifact }
            return MapArtifact(id: artifact.id, kind: artifact.kind, required: artifact.required,
                sourceURL: artifact.sourceURL, sizeBytes: artifact.sizeBytes, downloadSizeBytes: artifact.downloadSizeBytes,
                checksum: nil, validationState: artifact.validationState,
                luckyMapsSourceProof: artifact.luckyMapsSourceProof)
        })
        check(!compatible(unbound), "a proof SHA-256 without the same artifact checksum is rejected")
        check((try? MapSourceValidator().validate(fileURL: copy("andorra"), expectedPackage: sha)) == nil,
              "a file whose SHA-256 differs from the published one is refused")
    }

    static func acquisition() async throws {
        let package = try package()
        let main = try await acquire(package)
        defer { try? FileManager.default.removeItem(at: main.workspaceRootURL!) }
        try Stage42ArtifactValidator().validate(artifact: main, package: package)
        check(main.packageFormat == .rawIMG && main.artifactKind == .main
            && main.targetFilename == "terento_luckymaps_andorra.img"
            && main.version == MapVersion(year: 2026, month: 10, day: 3),
              "raw IMG → proof → MPS → final write validator for the map")
        let contour = try await acquire(package, artifact: package.artifacts[1])
        defer { try? FileManager.default.removeItem(at: contour.workspaceRootURL!) }
        try Stage42ArtifactValidator().validate(artifact: contour, package: package)
        check(contour.artifactKind == .contours && contour.targetFilename == "terento_luckymaps_andorra_contours.img",
              "the contour add-on is acquired and validated on its own proof")
        do {
            let wrong = try await acquire(package, overrides: ["andorra.img": "bad-publisher.img"])
            try? FileManager.default.removeItem(at: wrong.workspaceRootURL!)
            fatalError("FAIL: a file with another publisher was acquired")
        } catch { print("PASS: a served file that differs from the proof is not acquired") }
        var changed = try Data(contentsOf: main.localIMGURL)
        changed[changed.count - 1] ^= 1
        try changed.write(to: main.localIMGURL)
        do { try Stage42ArtifactValidator().validate(artifact: main, package: package); fatalError("FAIL: tampered map accepted") }
        catch { print("PASS: a changed map is rejected at the final boundary") }
    }

    static func rescan() throws {
        let mainPrefix = Array(try Data(contentsOf: fixtures.appendingPathComponent("andorra.img")).prefix(4096))
        let contourPrefix = Array(try Data(contentsOf: fixtures.appendingPathComponent("andorra-ct.img")).prefix(4096))
        let version = MapVersion(year: 2026, month: 10, day: 3)!
        func file(_ name: String, _ id: UInt32, _ size: UInt64) -> DeviceFile {
            DeviceFile(itemID: id, parentID: 9, storageID: 1, path: "/GARMIN/" + name, filename: name, sizeBytes: size, isFolder: false)
        }
        let mainFile = file("terento_luckymaps_andorra.img", 10, 49152)
        let contourFile = file("terento_luckymaps_andorra_contours.img", 11, 8192)
        let foreign = file("andorra.img", 12, 49152)
        let reader = PathPrefixReader(prefixes: [mainFile.path: mainPrefix, contourFile.path: contourPrefix, foreign.path: mainPrefix])
        let records = [
            MapOwnershipRecord(devicePath: mainFile.path, filename: mainFile.filename, providerId: "luckymaps",
                regionId: "ANDORRA", version: version, sizeBytes: 49152, packageID: "luckymaps-andorra",
                artifactID: "luckymaps-andorra-main", artifactKind: .main),
            MapOwnershipRecord(devicePath: contourFile.path, filename: contourFile.filename, providerId: "luckymaps",
                regionId: "ANDORRA", version: version, sizeBytes: 8192, packageID: "luckymaps-andorra",
                artifactID: "luckymaps-andorra-contours", artifactKind: .contours)
        ]
        let result = GarminMapScanner().scan(files: [mainFile, contourFile, foreign], reader: reader,
                                             ownershipRecords: records, recognizedProviderIDs: ["luckymaps"])
        let managed = result.installedMaps.filter { $0.managementState == .managedByTerento }
        check(managed.count == 2 && managed.allSatisfy { $0.provider == "Lucky Maps" && $0.region == "ANDORRA" },
              "Terento's own map and contour files are restored from the exact manifest records")
        check(managed.first { $0.sourceFile.filename == contourFile.filename }?.managedArtifactKind == .contours,
              "the contour file stays the contour add-on")
        check(MapOwnershipMatcher.lifecycleVersionMatches(scanned: nil, recorded: version, provider: "luckymaps",
                                                          filename: contourFile.filename, artifactKind: .contours),
              "a recorded contour without a header release keeps its lifecycle")
        check(!result.installedMaps.contains { $0.sourceFile.filename == foreign.filename },
              "the same bytes under another name without a record are not claimed")
        let wrongSize = [MapOwnershipRecord(devicePath: mainFile.path, filename: mainFile.filename, providerId: "luckymaps",
            regionId: "ANDORRA", version: version, sizeBytes: 1, artifactKind: .main)]
        let unmatched = GarminMapScanner().scan(files: [mainFile], reader: reader, ownershipRecords: wrongSize,
                                                recognizedProviderIDs: ["luckymaps"])
        check(unmatched.installedMaps.isEmpty, "a record with another size does not restore the identity")
        let otherRegion = [MapOwnershipRecord(devicePath: mainFile.path, filename: mainFile.filename, providerId: "luckymaps",
            regionId: "LITHUANIA", version: version, sizeBytes: 49152, artifactKind: .main)]
        check(GarminMapScanner().scan(files: [mainFile], reader: reader, ownershipRecords: otherRegion,
                                      recognizedProviderIDs: ["luckymaps"]).installedMaps.isEmpty,
              "a record for another region does not restore the identity")
    }
}

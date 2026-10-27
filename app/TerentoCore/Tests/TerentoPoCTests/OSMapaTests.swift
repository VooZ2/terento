import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
}
private struct LocalDownload: MapPackageDownloadClient {
    let source: URL
    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        let copy = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.copyItem(at: source, to: copy)
        return MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: copy)
    }
}
/// A missing path behaves like a prefix read that failed over MTP.
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

@main struct OSMapaTests {
    static let identity = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 51mm", family: "fēnix", variant: "51mm",
        usbVendorId: 0x091e, usbProductId: 0x7777, firmware: "2244", storageCapacity: 32 << 30, freeSpace: 16 << 30,
        localHardwareIdentifier: "OSMAPA-LOCAL-FIXTURE", localIdentityResolution: .garminUnitID)
    static let root = DeviceFile(itemID: 9, parentID: 0, storageID: 1, path: "/GARMIN", filename: "GARMIN", sizeBytes: 0, isFolder: true)

    static func check(_ condition: @autoclosure () -> Bool, _ label: String) {
        guard condition() else { fatalError("FAIL: \(label)") }
        print("PASS: \(label)")
    }

    static let fixtures = URL(fileURLWithPath: ProcessInfo.processInfo.environment["TERENTO_OSMAPA_FIXTURES"]!)

    static func bytes(_ name: String, _ ext: String = "img") throws -> [UInt8] {
        [UInt8](try Data(contentsOf: fixtures.appendingPathComponent("\(name).\(ext)")))
    }

    static func header(_ title: String, date: (Int, Int, Int) = (2026, 10, 24)) -> [UInt8] {
        var prefix = [UInt8](repeating: 0, count: 4096)
        prefix.replaceSubrange(0x10..<0x16, with: "DSKIMG".utf8)
        prefix.replaceSubrange(0x41..<0x47, with: "GARMIN".utf8)
        prefix[0x39] = UInt8(date.0 & 0xFF); prefix[0x3A] = UInt8(date.0 >> 8)
        prefix[0x3B] = UInt8(date.1); prefix[0x3C] = UInt8(date.2)
        let raw = Array(title.utf8) + Array(repeating: UInt8(0x20), count: max(0, 50 - title.utf8.count))
        prefix.replaceSubrange(0x49..<0x5D, with: raw[0..<20])
        prefix.replaceSubrange(0x65..<0x83, with: raw[20..<50])
        return prefix
    }

    static func crc32(_ data: Data) -> String {
        var crc = CRC32()
        crc.update(data)
        return String(format: "%08x", crc.value)
    }

    static func source(_ coverage: OSMapaCoverage, _ style: OSMapaStyle, date: String = "20261024") -> String {
        "https://osmapa-garmin.las.org.pl/products/\(coverage.titlePrefix)-\(style.headerToken)-\(date)V2.03_IMG.zip"
    }

    /// One v5 package exactly as the E1 API publishes it, proof bound to a fixture.
    static func document(_ coverage: OSMapaCoverage, _ style: OSMapaStyle, fixture: String? = nil,
                         edit: (inout [String: Any], inout [String: Any]) -> Void = { _, _ in }) throws -> [String: Any] {
        let name = fixture ?? "\(coverage.rawValue)-\(style.rawValue)"
        let zip = try Data(contentsOf: fixtures.appendingPathComponent(name + ".zip"))
        let img = try Data(contentsOf: fixtures.appendingPathComponent(name + ".img"))
        let token = "\(coverage.rawValue)-\(style.rawValue)"
        let url = source(coverage, style)
        var proof: [String: Any] = [
            "sourceURL": url, "etag": "\"5f2-63f\"", "lastModified": "Sat, 24 Oct 2026 19:31:35 GMT",
            "downloadSizeBytes": zip.count, "installSizeBytes": img.count, "payloadPath": "gmapsupp.img",
            "crc32": crc32(img), "sourceIdentity": "osmapa:\(token.replacingOccurrences(of: "-", with: ":"))",
            "coverage": coverage.rawValue, "mapType": style.rawValue, "familyId": Int(style.familyID),
            "imgTitle": "\(coverage.titlePrefix)-\(style.headerToken)", "sourceVersion": "2.03",
            "generatedAt": "2026-10-24T00:00:00+00:00", "headerIdentityValidated": true,
            "revision": String(repeating: "ab", count: 32)
        ]
        var map: [String: Any] = [
            "id": "osmapa-" + token, "region": token.uppercased(),
            "name": OSMapaProviderAdapter.displayName(coverage: coverage, style: style), "country": "PL",
            "version": ["year": 2026, "month": 10, "day": 24], "sizeBytes": zip.count,
            "downloadSizeBytes": zip.count, "installSizeBytes": img.count, "sourceURL": url,
            "identifier": token, "providerRegionId": token, "canonicalRegionId": token.uppercased(),
            "countryCodes": ["PL"], "regionKind": "country", "tags": [style.rawValue], "capabilities": ["main"],
            "mapType": style.rawValue, "geographicRegionId": coverage == .pl ? "POLAND" : "POLAND-WITH-BORDER-AREAS",
            "conflictGroup": "osmapa-" + style.rawValue
        ]
        edit(&map, &proof)
        map["artifacts"] = [[
            "id": "osmapa-\(token)-main", "kind": "main", "required": true, "sourceURL": map["sourceURL"] ?? url,
            "sizeBytes": img.count, "downloadSizeBytes": zip.count, "validationState": "validated",
            "sourceProof": proof
        ]]
        return map
    }

    static func catalog(_ maps: [[String: Any]], status: String = "ACTIVE",
                        unpaused: Set<String> = []) throws -> MapCatalog {
        let json: [String: Any] = ["catalogVersion": 5, "updatedAt": "2026-10-26T00:00:00Z", "providers": [[
            "id": "osmapa", "name": "OSMapaPL", "status": status, "website": "https://osmapa-garmin.las.org.pl/",
            "maps": maps
        ]]]
        return try MapCatalogDocumentDecoder(unpausedProviderIDs: unpaused).decode(JSONSerialization.data(withJSONObject: json))
    }

    static func package(_ coverage: OSMapaCoverage, _ style: OSMapaStyle, fixture: String? = nil,
                        edit: (inout [String: Any], inout [String: Any]) -> Void = { _, _ in }) throws -> MapPackage {
        try catalog([document(coverage, style, fixture: fixture, edit: edit)]).packages[0]
    }

    static func compatible(_ package: MapPackage) -> Bool {
        MapCatalogClientCompatibilityValidator().isPackageCompatible(package)
    }

    static func acquire(_ package: MapPackage, zip: String) async throws -> ValidatedMapArtifact {
        let acquisition = MapPackageAcquirer(downloadClient: LocalDownload(source: fixtures.appendingPathComponent(zip + ".zip")),
            workspaceFactory: {
                try MapAcquisitionWorkspace(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
            })
        return try await acquisition.acquire(package: package)
    }

    static func authorization(for identity: DeviceIdentity) -> InstallationAuthorizationState {
        let record = InstallationAuthorizationRecord(
            id: identity.catalogDeviceID ?? "test-device", manufacturer: identity.manufacturer, model: identity.model,
            baseModel: identity.canonicalModel ?? identity.model, canonicalModel: identity.canonicalModel ?? identity.model,
            variant: identity.variant ?? "", caseSizeMm: identity.caseSizeMm, displayType: identity.displayType,
            screenTechnology: identity.screenTechnology, solar: identity.solar, inReach: identity.inReach,
            active: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED")
        return .approved(record: record, policyVersion: 1)
    }

    static func main() async throws {
        try headerTable()
        try catalogContract()
        try archiveAndPayload()
        try await acquisition()
        try conflictMatrix()
    }

    static func headerTable() throws {
        for coverage in OSMapaCoverage.allCases {
            for style in OSMapaStyle.allCases {
                let title = "\(coverage.titlePrefix)-\(style.headerToken)"
                let prefix = header(title)
                check(OSMapaIMGMetadata.marker(prefix) == .map(coverage: coverage, style: style),
                      "\(title) maps to its own style group")
                let metadata = GarminIMGMetadataParser().parse(prefix)
                check(metadata?.provider == "OSMapa" && metadata?.region == "\(coverage.rawValue)-\(style.rawValue)".uppercased()
                    && metadata?.version == MapVersion(year: 2026, month: 10, day: 24),
                      "\(title) parses provider, coverage-style region and daily release")
            }
        }
        check(Array(header("OSMapaPLext-PODSTAWOWA")[0x49..<0x5D]) == Array("OSMapaPLext-PODSTAWO".utf8)
            && Array(header("OSMapaPLext-WARSTWICE")[0x5C..<0x5D] + header("OSMapaPLext-WARSTWICE")[0x65..<0x66]) == Array("CE".utf8),
              "long titles are stitched across the two header fields")
        for title in ["OSMapaPL-OGON", "OSMapaPL-SOMETHING", "OSMapaPLext-OGONKI-X", "OSMapaPL"] {
            check(OSMapaIMGMetadata.marker(header(title)) == .ambiguous, "\(title) is ambiguous")
            check(GarminIMGMetadataParser().parse(header(title))?.provider != "OSMapa", "\(title) never identifies a package")
        }
        check(OSMapaIMGMetadata.marker(header("OSMapaPL-OGONKI", date: (2026, 2, 30))) == .ambiguous,
              "an invalid creation date makes the marker ambiguous")
        var latin = header("OSMapaPL-OGONKI")
        latin[0x52] = 0xC4
        check(OSMapaIMGMetadata.marker(latin) == .ambiguous, "non-ASCII after the OSMapaPL prefix is ambiguous")
        check(OSMapaIMGMetadata.marker(header("Copy of OSMapaPL-OGONKI")) == nil,
              "OSMapaPL text not at the start is not an OSMapaPL marker")
        var notIMG = header("OSMapaPL-OGONKI")
        notIMG[0x41] = 0
        check(OSMapaIMGMetadata.marker(notIMG) == nil && !GarminIMGPrefixEvidence(prefix: notIMG).isGarminIMG,
              "invalid IMG magic is not readable evidence")
        for (name, fid) in [("pl-podstawowa", 4), ("pl-ogonki", 5), ("plext-light", 6), ("plext-warstwice", 12)] {
            let head = Array(try bytes(name).prefix(4096))
            check(OSMapaIMGMetadata.mdrFamilyIDs(head) == [UInt16(fid)],
                  "\(name) MDR name gives family ID \(fid)")
        }
        var szlaki = header("OSMapaPL-SZLAKI")
        check(OSMapaIMGMetadata.mdrFamilyIDs(szlaki).isEmpty, "SZLAKI without MDR gives no family hint")
        szlaki[0x800] = 1
        szlaki.replaceSubrange(0x801..<0x80C, with: "0000000AMDR".utf8)
        check(OSMapaIMGMetadata.mdrFamilyIDs(szlaki).isEmpty, "an MDR name with non-digits is ignored")
        var beyond = [UInt8](repeating: 0, count: 0x1200)
        beyond[0x1000] = 1
        beyond.replaceSubrange(0x1001..<0x100C, with: "00000005MDR".utf8)
        check(OSMapaIMGMetadata.mdrFamilyIDs(Array(beyond.prefix(GarminIMGMetadataParser.prefixLength))).isEmpty,
              "an MDR entry beyond the 4 KiB scan prefix is not found and is not an error")
    }

    static func catalogContract() throws {
        var maps: [[String: Any]] = []
        for coverage in OSMapaCoverage.allCases {
            for style in OSMapaStyle.installable { maps.append(try document(coverage, style)) }
        }
        let decoded = try catalog(maps)
        check(decoded.packages.count == 8 && MapCatalogClientCompatibilityValidator().isCompatible(decoded),
              "eight v5 OSMapaPL packages pass native adapter and proof validation")
        check(Set(decoded.packages.compactMap(\.identity)).count == 8, "coverage and style never collapse to one identity")
        let paused = try catalog(maps, status: "PAUSED")
        check(MapCatalogClientCompatibilityValidator().isCompatible(paused)
            && paused.packages.allSatisfy { MapPackageAcquisitionPolicyResolver().availability(for: $0) != .available },
              "a paused provider stays visible and cannot be acquired")
        let serverPaused = maps.map { $0.merging(["downloadBlockReason": "PROVIDER_PAUSED"]) { $1 } }
        let unpaused = try catalog(serverPaused, status: "PAUSED", unpaused: MapCatalogDebugUnpause.parse(" OSMapa ,"))
        check(unpaused.provider(for: "osmapa")?.lifecycleStatus == .active
            && unpaused.packages.allSatisfy { MapPackageAcquisitionPolicyResolver().availability(for: $0) == .available },
              "the Debug unpause option lifts only PROVIDER_PAUSED for the named provider")
        let retired = try catalog(maps, status: "RETIRED", unpaused: ["osmapa"])
        let otherReason = try catalog(maps.map { $0.merging(["downloadBlockReason": "PACKAGE_UNAVAILABLE"]) { $1 } },
                                      status: "PAUSED", unpaused: ["osmapa"])
        check((retired.packages + otherReason.packages).allSatisfy {
            MapPackageAcquisitionPolicyResolver().availability(for: $0) != .available
        }, "the Debug unpause option never lifts RETIRED or another block reason")
        check(Set(decoded.packages.map { MapProviderDisplay.filterID(providerID: $0.providerId, regionID: $0.canonicalRegionId) })
            == Set(OSMapaStyle.installable.map(\.filterID))
            && MapProviderDisplay.filterOptions(providers: decoded.providers).count == 4
            && OSMapaStyle.installable.allSatisfy { MapProviderDisplay.sourceProviderID(filterID: $0.filterID) == "osmapa" },
              "each style is its own filter under one provider")
        let names = MapDisplayNameNormalizer.displayNames(for: decoded.packages)
        check(names["osmapa-pl-ogonki"] == "Poland" && names["osmapa-plext-warstwice"] == "Poland with border areas contour lines",
              "rows keep the source names; the style is shown as the provider label")

        let tampering: [(String, (inout [String: Any], inout [String: Any]) -> Void)] = [
            ("wrong family ID", { _, proof in proof["familyId"] = 4 }),
            ("wrong header title", { _, proof in proof["imgTitle"] = "OSMapaPLext-OGONKI" }),
            ("weak ETag", { _, proof in proof["etag"] = "W/\"x\"" }),
            ("another host", { map, proof in
                let url = "https://example.org/products/OSMapaPL-OGONKI-20261024V2.03_IMG.zip"
                map["sourceURL"] = url; proof["sourceURL"] = url }),
            ("filename date differs from the release", { map, proof in
                let url = source(.pl, .ogonki, date: "20261023")
                map["sourceURL"] = url; proof["sourceURL"] = url }),
            ("SZLAKI is not offered", { map, _ in map["providerRegionId"] = "pl-szlaki" }),
            ("size differs from the proof", { _, proof in proof["installSizeBytes"] = 1 }),
            ("CRC is not hex", { _, proof in proof["crc32"] = "zzzzzzzz" }),
            ("map type differs from the style", { map, _ in map["mapType"] = "light" }),
            ("a BBBike-shaped proof", { _, proof in proof = ["payloadMD5": String(repeating: "a", count: 32)] })
        ]
        for (label, edit) in tampering {
            let tampered = try package(.pl, .ogonki, edit: edit)
            check(!compatible(tampered), "catalog rejects \(label)")
        }
        // Swift JSONDecoder reads an integral 5.0 as 5; the backend mirror follows it.
        let integralJSON: [String: Any] = ["catalogVersion": 5, "updatedAt": "2026-10-26T00:00:00Z", "providers": [[
            "id": "osmapa", "name": "OSMapaPL", "status": "ACTIVE", "website": "https://osmapa-garmin.las.org.pl/",
            "maps": [try document(.pl, .ogonki)]]]]
        let integralText = String(decoding: try JSONSerialization.data(withJSONObject: integralJSON), as: UTF8.self)
            .replacingOccurrences(of: #""familyId":5(?=[,}])"#, with: #""familyId":5.0"#, options: .regularExpression)
        check(integralText.contains(#""familyId":5.0"#), "the fixture writes the family ID as 5.0")
        let integral = try MapCatalogDocumentDecoder().decode(Data(integralText.utf8)).packages[0]
        check(integral.mainArtifact?.osmapaSourceProof?.familyId == 5 && compatible(integral),
              "integral numbers written as 5.0 decode as integers, as in the Python mirror")
        let fraction = try package(.pl, .ogonki) { _, proof in proof["familyId"] = 5.5 }
        check(fraction.mainArtifact?.osmapaSourceProof == nil && !compatible(fraction), "a fractional family ID is rejected")
        let unavailableDocument = try document(.pl, .ogonki) { map, _ in map["sourceURL"] = nil }
        var artifact = (unavailableDocument["artifacts"] as! [[String: Any]])[0]
        artifact["validationState"] = "unavailable"
        artifact.removeValue(forKey: "sourceProof")
        var unavailableMap = unavailableDocument
        unavailableMap["artifacts"] = [artifact]
        let unavailable = try catalog([unavailableMap]).packages[0]
        check(compatible(unavailable) && !unavailable.hasUsableMainArtifact,
              "an unavailable package without proof stays visible and is never installable")
        var withProof = unavailableMap
        artifact["sourceProof"] = (try document(.pl, .ogonki)["artifacts"] as! [[String: Any]])[0]["sourceProof"]
        withProof["artifacts"] = [artifact]
        let unavailableWithProof = try catalog([withProof]).packages[0]
        check(!compatible(unavailableWithProof), "an unavailable package must not carry proof")
        var malformed = (try document(.pl, .ogonki)["artifacts"] as! [[String: Any]])[0]["sourceProof"] as! [String: Any]
        malformed["lastModified"] = true
        for (label, proof) in [("a malformed proof", malformed as Any), ("an empty proof object", [String: Any]() as Any),
                               ("a proof of the wrong JSON type", "proof" as Any)] {
            artifact["sourceProof"] = proof
            var map = unavailableMap
            map["artifacts"] = [artifact]
            let decoded = try catalog([map]).packages[0]
            check(decoded.mainArtifact?.carriesSourceProof == true && !compatible(decoded),
                  "an unavailable package with \(label) is rejected, not read as having no proof")
            let reencoded = try JSONDecoder().decode(MapPackage.self, from: JSONEncoder().encode(decoded))
            check(reencoded.mainArtifact?.carriesSourceProof == true, "\(label) stays marked after re-encoding")
        }
        artifact["sourceProof"] = NSNull()
        var nullProof = unavailableMap
        nullProof["artifacts"] = [artifact]
        let withNullProof = try catalog([nullProof]).packages[0]
        check(compatible(withNullProof), "a JSON null proof counts as no proof")

        let policy = ReviewedProviderURLPolicyRegistry.bundled.policy(for: "osmapa")!
        for url in [source(.pl, .ogonki), source(.plext, .warstwice)] {
            check((try? policy.validate(URL(string: url)!)) != nil, "reviewed URL \(url) is allowed")
        }
        for url in ["http://osmapa-garmin.las.org.pl/products/OSMapaPL-OGONKI-20261024V2.03_IMG.zip",
                    "https://osmapa-garmin.las.org.pl/products/OSMapaPL-SZLAKI-20261024V2.03_IMG.zip",
                    "https://osmapa-garmin.las.org.pl/products/OSMapaPL-OGONKI-20261024V2.03.exe",
                    "https://osmapa-garmin.las.org.pl/products/OSMapaPL-OGONKI-20261024V2.03_IMG.zip?x=1",
                    "https://osmapa-garmin.las.org.pl/products/../OSMapaPL-OGONKI-20261024V2.03_IMG.zip",
                    "https://osmapa-garmin.las.org.pl:8443/products/OSMapaPL-OGONKI-20261024V2.03_IMG.zip",
                    "https://osmapa-garmin.las.org.pl/other/OSMapaPL-OGONKI-20261024V2.03_IMG.zip"] {
            check((try? policy.validate(URL(string: url)!)) == nil, "unreviewed URL \(url) is refused")
        }
    }

    static func archiveAndPayload() throws {
        let good = try package(.pl, .ogonki)
        let proof = good.mainArtifact!.osmapaSourceProof!
        check((try? OSMapaArchiveSafety.validate(archiveURL: fixtures.appendingPathComponent("pl-ogonki.zip"), proof: proof)) != nil,
              "one deflated gmapsupp.img with the proof size and CRC is accepted")
        for name in ["two-entries", "stored", "renamed", "bad-mps"] {
            let other = try package(.pl, .ogonki, fixture: name)
            let otherProof = other.mainArtifact!.osmapaSourceProof!
            let rejected = (try? OSMapaArchiveSafety.validate(archiveURL: fixtures.appendingPathComponent(name + ".zip"), proof: proof)) == nil
            if name == "bad-mps" {
                check((try? OSMapaArchiveSafety.validate(archiveURL: fixtures.appendingPathComponent(name + ".zip"), proof: otherProof)) != nil
                    && rejected, "another payload with its own matching proof passes only its own proof")
            } else {
                check(rejected && (try? OSMapaArchiveSafety.validate(archiveURL: fixtures.appendingPathComponent(name + ".zip"), proof: otherProof)) == nil,
                      "archive \(name) is refused before extraction")
            }
        }
        var trailing = try Data(contentsOf: fixtures.appendingPathComponent("pl-ogonki.zip"))
        trailing.append(0)
        let trailingURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".zip")
        try trailing.write(to: trailingURL)
        defer { try? FileManager.default.removeItem(at: trailingURL) }
        check((try? OSMapaArchiveSafety.validate(archiveURL: trailingURL, proof: proof)) == nil, "a changed ZIP size is refused")

        let img = fixtures.appendingPathComponent("pl-ogonki.img")
        check((try? OSMapaIMGInspection.mpsFamilyIDs(fileURL: img)) == [5], "the MPS product file names family ID 5")
        check((try? OSMapaIMGInspection.mpsFamilyIDs(fileURL: fixtures.appendingPathComponent("bad-mps.img"))) == [4],
              "an MPS family ID different from the style is read as is")
        check((try? MapSourceValidator().validate(fileURL: copyAsPayload("pl-ogonki"), expectedPackage: good)) != nil,
              "the whole IMG matches size, CRC, header, MDR and MPS family ID")
        for (name, label) in [("bad-mps", "MPS family ID differs from the style"), ("bad-mdr", "MDR family ID differs"),
                              ("bad-date", "creation date differs from the filename"), ("bad-title", "header names the other coverage")] {
            let proofBound = try package(.pl, .ogonki, fixture: name)
            check((try? MapSourceValidator().validate(fileURL: copyAsPayload(name), expectedPackage: proofBound)) == nil,
                  "nothing reaches the watch when the \(label)")
        }
    }

    static func copyAsPayload(_ name: String) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = directory.appendingPathComponent("gmapsupp.img")
        try FileManager.default.copyItem(at: fixtures.appendingPathComponent(name + ".img"), to: target)
        return target
    }

    static func acquisition() async throws {
        let package = try package(.pl, .ogonki)
        let artifact = try await acquire(package, zip: "pl-ogonki")
        defer { try? FileManager.default.removeItem(at: artifact.workspaceRootURL!) }
        try Stage42ArtifactValidator().validate(artifact: artifact, package: package)
        check(artifact.packageFormat == .zip && artifact.installSizeBytes == package.installSizeBytes
            && artifact.targetFilename == "terento_osmapa_pl_ogonki.img",
              "ZIP → single IMG → MPS family ID → final write validator")
        try finalBoundary(package, artifact)
        for name in ["bad-mps", "two-entries", "stored"] {
            let bound = try self.package(.pl, .ogonki, fixture: name)
            do {
                let wrong = try await acquire(bound, zip: name)
                try? FileManager.default.removeItem(at: wrong.workspaceRootURL!)
                fatalError("FAIL: \(name) acquired")
            } catch { print("PASS: \(name) is not acquired") }
        }
        do {
            let other = try await acquire(package, zip: "pl-light")
            try? FileManager.default.removeItem(at: other.workspaceRootURL!)
            fatalError("FAIL: another style acquired")
        } catch { print("PASS: a different source file than the proof is not acquired") }
        var changed = try Data(contentsOf: artifact.localIMGURL)
        changed[changed.count - 1] ^= 1
        try changed.write(to: artifact.localIMGURL)
        do { try Stage42ArtifactValidator().validate(artifact: artifact, package: package); fatalError("FAIL: tampered payload accepted") }
        catch { print("PASS: a changed payload is rejected at the final boundary") }
    }

    /// The last check before transfer sees file content through the scan
    /// evidence of the same inventory; a map image without evidence blocks.
    static func finalBoundary(_ package: MapPackage, _ artifact: ValidatedMapArtifact) throws {
        let profile = DeviceInstallProfileRegistry.local.profile(for: identity, deviceFiles: [root])!
        func file(_ name: String, _ id: UInt32, size: UInt64 = 65536) -> DeviceFile {
            DeviceFile(itemID: id, parentID: 9, storageID: 1, path: "/GARMIN/" + name, filename: name, sizeBytes: size, isFolder: false)
        }
        func evidence(_ file: DeviceFile, _ prefix: [UInt8]?, size: UInt64? = nil) -> InstalledMapFile {
            InstalledMapFile(path: file.path, filename: file.filename, sizeBytes: size ?? file.sizeBytes, itemID: file.itemID,
                prefixEvidence: GarminIMGPrefixEvidence(prefix: prefix))
        }
        func passes(_ files: [DeviceFile], _ inspected: [InstalledMapFile]) -> Bool {
            (try? Stage42TargetPolicy().validate(package: package, artifact: artifact, profile: profile, identity: identity,
                deviceFiles: [root] + files, installedMaps: [], inspectedFiles: inspected,
                installationAuthorization: authorization(for: identity))) != nil
        }
        let manual = file("gmapsupp.img", 101)
        let foreign = file("other.img", 102)
        let foreignPrefix = Array(header("Topo Poland").prefix(0x800)) + [1] + Array("00000005MDR".utf8)
            + Array(repeating: 0, count: 4096 - 0x80C)
        check(passes([], []), "an empty watch passes the final boundary")
        check(passes([file("D1234567A.img", 103)], []), "Garmin-owned images are outside the OSMapaPL content check")
        let light = try bytes("pl-light")
        let otherCoverage = try bytes("plext-ogonki")
        check(passes([manual], [evidence(manual, light)]), "another style under a generic name passes")
        check(!passes([manual], []), "a generic-named map image without scan evidence blocks the write")
        check(!passes([manual], [evidence(manual, light, size: 1)]), "evidence for another file size blocks the write")
        check(!passes([manual], [evidence(manual, Array(repeating: 0xFF, count: 4096))]), "an unreadable generic-named image blocks the write")
        check(!passes([manual], [evidence(manual, nil)]), "a generic-named image whose prefix was not read blocks the write")
        check(!passes([manual], [evidence(manual, otherCoverage)]), "the other coverage under a generic name blocks the write")
        check(!passes([foreign], [evidence(foreign, foreignPrefix)]), "a foreign map with the same family ID blocks the write")
    }

    static func conflictMatrix() throws {
        let profile = DeviceInstallProfileRegistry.local.profile(for: identity, deviceFiles: [root])!
        let plOgonki = try package(.pl, .ogonki)
        let plextOgonki = try package(.plext, .ogonki)
        let plPodstawowa = try package(.pl, .podstawowa)
        let plWarstwice = try package(.pl, .warstwice)
        let plextWarstwice = try package(.plext, .warstwice)
        let prefixes: [String: [UInt8]] = [
            "/GARMIN/terento_osmapa_pl_ogonki.img": try bytes("pl-ogonki"),
            "/GARMIN/terento_osmapa_plext_ogonki.img": try bytes("plext-ogonki"),
            "/GARMIN/terento_osmapa_pl_warstwice.img": try bytes("pl-warstwice"),
            "/GARMIN/gmapsupp.img": try bytes("pl-ogonki"),
            "/GARMIN/terento_osmapa_pl_light.img": Array(repeating: 0, count: 4096),
            "/GARMIN/broken.img": Array(repeating: 0xFF, count: 4096),
            "/GARMIN/other.img": Array(header("Topo Poland").prefix(0x800)) + [1] + Array("00000005MDR".utf8)
                + Array(repeating: 0, count: 4096 - 0x80C),
            "/GARMIN/odd.img": header("OSMapaPL-OGON")
        ]
        func scan(_ paths: [String], managed: [String] = []) -> MapScanResult {
            let files = paths.enumerated().map { index, path in
                DeviceFile(itemID: UInt32(100 + index), parentID: 9, storageID: 1, path: path,
                    filename: String(path.split(separator: "/").last!), sizeBytes: 65536, isFolder: false)
            }
            let records = files.filter { managed.contains($0.path) }.compactMap { file -> MapOwnershipRecord? in
                guard let metadata = GarminIMGMetadataParser().parse(prefixes[file.path] ?? []) else { return nil }
                return MapOwnershipRecord(devicePath: file.path, filename: file.filename, providerId: "osmapa",
                    regionId: metadata.region!, version: metadata.version!, sizeBytes: file.sizeBytes)
            }
            return GarminMapScanner().scan(files: files, reader: PathPrefixReader(prefixes: prefixes),
                ownershipRecords: records, recognizedProviderIDs: ["osmapa"])
        }
        func preflight(_ package: MapPackage, _ result: MapScanResult) -> InstallationPreflightResult {
            let comparison = MapComparison(providerName: "OSMapaPL", regionName: package.name, catalogMap: package,
                installedMap: nil, status: .notInstalled)
            return InstallationPreflightEngine().evaluate(identity: identity, selectedMap: package, comparison: comparison,
                installedMaps: result.installedMaps, inspectedFiles: result.files, availableStorage: 16 << 30, profile: profile)
        }
        func blocked(_ package: MapPackage, _ result: MapScanResult, _ expected: OSMapaProviderAdapter.InstalledConflict, _ label: String) {
            let engine = OSMapaProviderAdapter.installedConflict(for: package, installedMaps: result.installedMaps + result.otherMaps,
                inspectedFiles: result.files)
            let checked = preflight(package, result)
            check(engine == expected && checked.status == .blockedMapTypeConflict
                && checked.reason == OSMapaProviderAdapter.installedConflictMessage(for: package, conflict: expected),
                  "\(label): engine and preflight block before any transfer")
        }
        func allowed(_ package: MapPackage, _ result: MapScanResult, _ label: String) {
            check(OSMapaProviderAdapter.installedConflict(for: package, installedMaps: result.installedMaps + result.otherMaps,
                inspectedFiles: result.files) == nil && preflight(package, result).status != .blockedMapTypeConflict, label)
        }

        let empty = scan([])
        allowed(plOgonki, empty, "nothing of the style on the watch allows the install")
        let ownSame = scan(["/GARMIN/terento_osmapa_pl_ogonki.img"], managed: ["/GARMIN/terento_osmapa_pl_ogonki.img"])
        check(ownSame.files.first?.prefixEvidence?.osmapa == .map(coverage: .pl, style: .ogonki)
            && ownSame.installedMaps.first?.managementState == .managedByTerento,
              "the scan keeps prefix evidence and ownership for the managed file")
        allowed(plOgonki, ownSame, "the same managed package is the update path, not a conflict")
        blocked(plextOgonki, ownSame, .otherCoverageManaged(.pl), "managed other coverage of the style")
        check(OSMapaProviderAdapter.installedConflictMessage(for: plextOgonki, conflict: .otherCoverageManaged(.pl))
            == "To install “OSMapaPL Ogonki - Poland with border areas”, first remove “OSMapaPL Ogonki - Poland” in Manage maps. OSMapaPL maps of one style cannot be installed together.",
              "the managed conflict names both maps and the Manage maps step")
        allowed(plPodstawowa, ownSame, "another style with another family ID is allowed")
        allowed(plWarstwice, ownSame, "contour lines next to a main style are allowed")
        let contours = scan(["/GARMIN/terento_osmapa_pl_warstwice.img"], managed: ["/GARMIN/terento_osmapa_pl_warstwice.img"])
        blocked(plextWarstwice, contours, .otherCoverageManaged(.pl), "contour lines of the other coverage")
        let unmanagedName = scan(["/GARMIN/terento_osmapa_pl_ogonki.img"])
        blocked(plOgonki, unmanagedName, .unmanaged, "a Terento-looking name without ownership")
        let manual = scan(["/GARMIN/gmapsupp.img"])
        blocked(plOgonki, manual, .unmanaged, "a manually copied gmapsupp.img of the style, same coverage")
        blocked(plextOgonki, manual, .unmanaged, "a manually copied gmapsupp.img of the style, other coverage")
        allowed(plPodstawowa, manual, "a manual copy of another style does not block")
        let unreadableManaged = scan(["/GARMIN/terento_osmapa_pl_light.img"])
        blocked(plPodstawowa, unreadableManaged, .unreadable, "a managed name with an unreadable header")
        let missingPrefix = scan(["/GARMIN/missing.img"])
        blocked(plPodstawowa, missingPrefix, .unreadable, "a file whose prefix could not be read")
        let broken = scan(["/GARMIN/broken.img"])
        blocked(plWarstwice, broken, .unreadable, "an unreadable foreign IMG blocks every OSMapaPL install")
        let foreign = scan(["/GARMIN/other.img"])
        blocked(plOgonki, foreign, .familyID, "a foreign map whose MDR names the style's family ID")
        allowed(plPodstawowa, foreign, "a foreign map with another family ID is allowed")
        let odd = scan(["/GARMIN/odd.img"])
        blocked(plWarstwice, odd, .ambiguous, "an ambiguous OSMapaPL marker blocks every OSMapaPL install")
        let mixed = scan(["/GARMIN/gmapsupp.img", "/GARMIN/broken.img"])
        blocked(plOgonki, mixed, .unreadable, "the most severe conflict decides the explanation")
        let renamedManaged = MapOwnershipRecord(devicePath: "/GARMIN/gmapsupp.img", filename: "gmapsupp.img", providerId: "osmapa",
            regionId: "PL-OGONKI", version: plOgonki.version, sizeBytes: 65536)
        let manualOwned = GarminMapScanner().scan(files: [DeviceFile(itemID: 100, parentID: 9, storageID: 1, path: "/GARMIN/gmapsupp.img",
            filename: "gmapsupp.img", sizeBytes: 65536, isFolder: false)], reader: PathPrefixReader(prefixes: prefixes),
            ownershipRecords: [renamedManaged], recognizedProviderIDs: ["osmapa"])
        blocked(plOgonki, manualOwned, .unmanaged, "a file outside Terento's name grammar is never its own update path")
        let bbbike = try JSONDecoder().decode(MapPackage.self, from: JSONEncoder().encode(plOgonki).replacingProvider())
        check(OSMapaProviderAdapter.installedConflict(for: bbbike, installedMaps: [], inspectedFiles: broken.files) == nil,
              "other providers keep their existing conflict rules")

        check(OSMapaProviderAdapter.selectionConflictReason([plOgonki, plextOgonki]) != nil
            && OSMapaProviderAdapter.selectionConflictReason([plWarstwice, plextWarstwice]) != nil
            && OSMapaProviderAdapter.selectionConflictReason([plOgonki, plPodstawowa, plWarstwice]) == nil,
              "one batch can hold only one coverage per style")
        let items = [plOgonki, plextOgonki].map { package in
            MapSelectionItem(id: package.id, package: package,
                comparison: MapComparison(providerName: "OSMapaPL", regionName: package.name, catalogMap: package, installedMap: nil, status: .notInstalled),
                displayName: package.name, installSizeBytes: package.installSizeBytes, lifecycleAction: .install,
                canonicalRegionIdentity: CanonicalMapRegionIdentity(countryCode: "PL"), acquisitionAvailability: .available,
                preflightStatus: .readyNewInstall, isRecommended: false)
        }
        let plan = MapSelectionPlanner().plan(items: items, selectedIDs: Set(items.map(\.id)), currentFreeSpace: 16 << 30)
        check(!plan.canContinue && plan.status == .blocked && plan.reason.contains("OSMapaPL Ogonki"),
              "the selection planner blocks both coverages of one style before download")
        check(!MapSelectionPresentationModel.isSelectionEnabled(items[1], selectedIDs: [items[0].id], items: items),
              "the other coverage of a selected style cannot be selected")

        let artifactFiles = ["terento_osmapa_plext_ogonki.img", "terento_osmapa_pl_ogonki_2026-10-17.img", "terento_osmapa_unknown.img"]
        check(OSMapaProviderAdapter.conflicts(plOgonki, filename: artifactFiles[0])
            && !OSMapaProviderAdapter.conflicts(plOgonki, filename: artifactFiles[1])
            && OSMapaProviderAdapter.conflicts(plOgonki, filename: artifactFiles[2])
            && !OSMapaProviderAdapter.conflicts(plOgonki, filename: "terento_osmapa_plext_light.img"),
              "the final target policy blocks the other coverage and unknown names in Terento's namespace")
    }
}

private extension Data {
    func replacingProvider() -> Data {
        Data(String(decoding: self, as: UTF8.self).replacingOccurrences(of: "\"osmapa\"", with: "\"bbbike\"").utf8)
    }
}

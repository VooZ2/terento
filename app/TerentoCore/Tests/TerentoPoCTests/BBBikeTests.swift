import CryptoKit
import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}
private struct LocalDownload: MapPackageDownloadClient {
    let source: URL
    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        let copy = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.copyItem(at: source, to: copy)
        return MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: copy)
    }
}
private struct PrefixReader: DeviceFileReader {
    let prefix: [UInt8]
    func readFileInventory() throws -> [DeviceFile] { [] }
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8] { prefix }
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]] {
        Dictionary(uniqueKeysWithValues: files.map { ($0.itemID, prefix) })
    }
}

@main struct BBBikeTests {
    static func check(_ condition: @autoclosure () -> Bool, _ label: String) {
        guard condition() else { fatalError("FAIL: \(label)") }
        print("PASS: \(label)")
    }
    static func main() async throws {
        let defaultFixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Fixtures/BBBike/catalog.json")
        let fixture = ProcessInfo.processInfo.environment["TERENTO_BBBIKE_CATALOG_PATH"].map { URL(fileURLWithPath: $0) } ?? defaultFixture
        var json = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as! [String: Any]
        var providers = json["providers"] as! [[String: Any]]
        providers[0]["status"] = "ACTIVE"
        json["providers"] = providers
        let catalog = try MapCatalogDocumentDecoder().decode(JSONSerialization.data(withJSONObject: json))
        check(catalog.packages.count >= 6, "both types and real representative geography decode")
        check(MapCatalogClientCompatibilityValidator().isCompatible(catalog), "actual BBBike catalog passes native adapter proof validation")
        check(Set(catalog.packages.compactMap(\.identity)).count == catalog.packages.count, "variants never collapse to geography")
        let andorra = catalog.packages.filter { $0.providerRegionId == "europe/andorra" }
        check(Set(andorra.map { MapProviderDisplay.filterID(providerID: $0.providerId, regionID: $0.canonicalRegionId) }) == ["bbbike", "bbbikeontrail"], "two display filters retain one provider")
        for package in andorra {
            let filename = try TerentoManagedFilenameGenerator().filename(providerId: package.providerId, regionId: package.canonicalRegionId)
            check(TerentoManagedFilenameGenerator().isValid(filename), "variant filename grammar")
            let other = andorra.first { $0.id != package.id }!
            check(!TerentoManagedFilenameGenerator().matchesIdentity(filename, providerId: other.providerId, regionId: other.canonicalRegionId), "wrong type cannot match managed filename")
        }
        check(BBBikeProviderAdapter.selectionConflicts(andorra), "same-region type pair rejected in domain batch policy")
        check(!BBBikeProviderAdapter.selectionConflicts([andorra[0], catalog.packages.first { $0.providerRegionId == "europe/alps" }!]), "different BBBike regions retain ordinary batch behavior")
        let manifest = TerentoManifestEntry(deviceKey: "test", devicePath: "/GARMIN/test.img", filename: "test.img",
            providerId: "freizeitkarte", regionId: "LTU", version: MapVersion(year: 2026, month: 9)!,
            sizeBytes: 132, sha256: String(repeating: "a", count: 64), installedAt: Date(timeIntervalSince1970: 0))
        let oldData = try JSONEncoder().encode(manifest)
        let decodedOld = try JSONDecoder().decode(TerentoManifestEntry.self, from: oldData)
        check(decodedOld.bbbikeMetadata == nil, "legacy manifest has no new required field")
        let unavailable = andorra[0].withArtifacts([MapArtifact(id: "unavailable", kind: .main, required: true,
            sourceURL: URL(string: "https://data.bbbike.org/osm/garmin/example/alias.zip"), validationState: .unavailable)])
        let disabledCatalog = MapCatalog(catalogVersion: catalog.catalogVersion, updatedAt: catalog.updatedAt,
            providers: catalog.providers, regions: catalog.regions, packages: [unavailable])
        check(MapCatalogClientCompatibilityValidator().isCompatible(disabledCatalog) && !unavailable.hasUsableMainArtifact,
            "metadata-only unavailable source does not poison valid catalog or become installable")
        let oldCatalogURL = defaultFixture.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/TerentoPoC/Resources/Maps/catalog.json")
        let oldCatalog = try MapCatalogDocumentDecoder().decode(Data(contentsOf: oldCatalogURL))
        let oldProviders = oldCatalog.providers.filter { $0.id != "bbbike" }
        let oldPackages = oldCatalog.packages.filter { $0.providerId != "bbbike" }.map { package in
            guard package.providerId == "maprando" else { return package }
            return package.withArtifacts(package.artifacts.map { $0.kind == .main ? $0.withValidationState(.unavailable) : $0 })
        }
        let mixed = MapCatalog(catalogVersion: 1, updatedAt: catalog.updatedAt,
            providers: oldProviders + catalog.providers, regions: oldCatalog.regions + catalog.regions,
            packages: oldPackages + catalog.packages.map { $0.id == unavailable.id ? unavailable : $0 })
        check(MapCatalogClientCompatibilityValidator().isCompatible(mixed),
            "mixed catalog preserves unavailable BBBike and existing MapRando membership")
        check(oldPackages.filter { $0.providerId == "maprando" }.allSatisfy(\.hasUsableMainArtifact),
            "new provider does not change legacy unavailable-source client contract")
        do {
            _ = try await MapPackageAcquirer(downloadClient: LocalDownload(source: fixture), workspaceFactory: {
                fatalError("unavailable source allocated workspace")
            }).acquire(package: unavailable)
            fatalError("unavailable source acquired")
        } catch { print("PASS: unavailable source rejected before workspace/download") }
        let russianData = try JSONEncoder().encode(andorra[0])
        let russianJSON = String(data: russianData, encoding: .utf8)!.replacingOccurrences(of: "andorra", with: "russia").replacingOccurrences(of: "ANDORRA", with: "RUSSIA")
        let russian = try JSONDecoder().decode(MapPackage.self, from: Data(russianJSON.utf8))
        do {
            _ = try await MapPackageAcquirer(downloadClient: LocalDownload(source: fixture), workspaceFactory: {
                fatalError("withheld source allocated workspace")
            }).acquire(package: russian)
            fatalError("Russian source acquired")
        } catch MapAcquisitionError.acquisitionWithheld { print("PASS: Russia rejected before workspace/download") }
        let longPath = "north-america/us/california/san-francisco-bay-region"
        let longToken = BBBikeProviderAdapter.regionToken(path: longPath, type: "bbbike-latin1")
        let longPackage = MapPackage(id: "bbbike-" + longToken.lowercased(), providerId: "bbbike", regionId: longToken,
            name: "San Francisco Bay Region – United States", version: andorra[0].version, sizeBytes: 132,
            sourceURL: nil, releaseDate: nil, identifier: nil, providerRegionId: longPath, canonicalRegionId: longToken,
            mapType: "bbbike-latin1", geographicRegionId: "US-SF-BAY")
        var longPrefix = [UInt8](repeating: 0, count: 132)
        longPrefix.replaceSubrange(0x10..<0x16, with: "DSKIMG".utf8)
        longPrefix.replaceSubrange(0x41..<0x47, with: "GARMIN".utf8)
        longPrefix[0x39] = 0xEA; longPrefix[0x3A] = 7; longPrefix[0x3B] = 9; longPrefix[0x3C] = 9
        let description = Array((longPath + " bbbike/latin1 BBBike.org 09-Sep-2026").utf8.prefix(49)) + [UInt8(32)]
        longPrefix.replaceSubrange(0x49..<0x5D, with: description.prefix(20))
        longPrefix.replaceSubrange(0x65..<0x83, with: description.dropFirst(20))
        check(BBBikeIMGMetadata.metadata(longPrefix, context: BBBikeMapMetadata(package: longPackage)!, version: longPackage.version)?.name == longPackage.name,
            "truncated long header restores name only from verified context")
        check(GarminIMGMetadataParser().parse(longPrefix)?.provider == nil,
            "long header without exact manifest remains unidentified")
        // Real provider metadata and full official archives acquired locally by the
        // source gate. No test downloads or device access occur in this suite.
        if let samples = ProcessInfo.processInfo.environment["TERENTO_BBBIKE_SAMPLE_DIRECTORY"] {
            for package in andorra {
                let type = BBBikeMapType(rawValue: package.mapType!)!
                let zip = URL(fileURLWithPath: samples).appendingPathComponent(type.style + ".zip")
                let acquisition = MapPackageAcquirer(downloadClient: LocalDownload(source: zip), workspaceFactory: {
                    try MapAcquisitionWorkspace(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
                })
                let artifact = try await acquisition.acquire(package: package)
                defer { try? FileManager.default.removeItem(at: artifact.workspaceRootURL!) }
                try Stage42ArtifactValidator().validate(artifact: artifact, package: package)
                check(artifact.packageFormat == .zip && artifact.installSizeBytes == package.installSizeBytes, "real \(type.title) ZIP→README/checksum→IMG→final write validator")
                let identity = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 51mm", family: "fēnix", variant: "51mm",
                    usbVendorId: 0x091e, usbProductId: 0x7777, firmware: "2244", storageCapacity: 32 << 30, freeSpace: 16 << 30,
                    localHardwareIdentifier: "BBBIKE-LOCAL-FIXTURE", localIdentityResolution: .garminUnitID)
                let root = DeviceFile(itemID: 9, parentID: 0, storageID: 1, path: "/GARMIN", filename: "GARMIN", sizeBytes: 0, isFolder: true)
                let profile = DeviceInstallProfileRegistry.local.profile(for: identity, deviceFiles: [root])!
                try Stage42TargetPolicy().validate(package: package, artifact: artifact, profile: profile, identity: identity, deviceFiles: [root])
                let sibling = andorra.first { $0.id != package.id }!
                let siblingName = try TerentoManagedFilenameGenerator().filename(providerId: sibling.providerId, regionId: sibling.canonicalRegionId)
                let siblingFile = DeviceFile(itemID: 102, parentID: 9, storageID: 1, path: "/GARMIN/" + siblingName,
                    filename: siblingName, sizeBytes: sibling.installSizeBytes!, isFolder: false)
                do { try Stage42TargetPolicy().validate(package: package, artifact: artifact, profile: profile, identity: identity, deviceFiles: [root, siblingFile]); fatalError("sibling reached target") }
                catch Stage42TargetPolicyError.unsupportedPackage { print("PASS: direct final target rejects installed other type independent of catalog") }
                let comparison = MapComparison(providerName: "BBBike", regionName: package.name, catalogMap: package, installedMap: nil, status: .notInstalled)
                let preflight = InstallationPreflightEngine().evaluate(identity: identity, selectedMap: package, comparison: comparison,
                    installedMaps: [], inspectedFiles: [InstalledMapFile(path: siblingFile.path, filename: siblingFile.filename, sizeBytes: siblingFile.sizeBytes, itemID: siblingFile.itemID)], availableStorage: 16 << 30, profile: profile)
                check(!preflight.isReady, "preflight rejects sibling absent from catalog and parsed inventory")
                let prefix = try MapPackageFormat.readPrefix(from: artifact.localIMGURL, maxLength: GarminIMGMetadataParser.prefixLength)
                let file = DeviceFile(itemID: 101, parentID: 1, storageID: 1, path: "/GARMIN/" + artifact.targetFilename,
                    filename: artifact.targetFilename, sizeBytes: artifact.installSizeBytes, isFolder: false)
                let context = BBBikeMapMetadata(package: package)!
                let record = MapOwnershipRecord(devicePath: file.path, filename: file.filename, providerId: package.providerId,
                    regionId: package.identity!.region, version: package.version, sizeBytes: file.sizeBytes,
                    packageID: package.id, artifactID: package.mainArtifact?.id, artifactKind: .main, bbbikeMetadata: context)
                let scanner = GarminMapScanner()
                let managed = scanner.scan(files: [file], reader: PrefixReader(prefix: prefix), ownershipRecords: [record])
                check(managed.installedMaps.first?.name == "Andorra" && managed.installedMaps.first?.managementState == .managedByTerento,
                    "offline manifest restores exact geographic name/type")
                let unowned = scanner.scan(files: [file], reader: PrefixReader(prefix: prefix))
                check(!unowned.installedMaps.contains { $0.managementState == .managedByTerento }, "managed filename never grants ownership alone")
                let duplicate = scanner.scan(files: [file], reader: PrefixReader(prefix: prefix), ownershipRecords: [record, record])
                check(!duplicate.installedMaps.contains { $0.managementState == .managedByTerento }, "ambiguous manifest matches cannot restore BBBike identity")
                var changed = try Data(contentsOf: artifact.localIMGURL)
                changed[changed.count - 1] ^= 1
                try changed.write(to: artifact.localIMGURL)
                do { try Stage42ArtifactValidator().validate(artifact: artifact, package: package); fatalError("tampered payload accepted") }
                catch { print("PASS: changed BBBike payload rejected by final boundary") }
            }
        } else { print("NOTE: full real ZIP gate requires TERENTO_BBBIKE_SAMPLE_DIRECTORY") }
    }
}

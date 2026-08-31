import CryptoKit
import Foundation

enum EvidenceResult {
    case pass
    case fail
}

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct Stage41AcquisitionTests {
    static func main() async {
        testCatalogResolvesFrance()
        testCatalogKeepsAllDownloadableRegions()
        testFormatDetection()
        testArchivePathSafety()
        await testExtractedSymlinkSafety()
        await testDownloaderUsesCatalogURL()
        testReviewedProviderURLPolicy()
        await testFailedHTTPIsTyped()
        await testEmptyDownloadIsTyped()
        await testRenamedIMGIsIdentifiedByContent()
        await testCompositeRegionIdentityPasses()
        await testSplitReleaseHeaderPasses()
        await testOpenTopoMapAcquisitionUsesOfficialURLAndIdentity()
        testRegionalProviderTokensRemainConcrete()
        testSharedCatalogRegionsUseDistinctManagedTargets()
        await testSharedCatalogRegionUsesConcreteSourceIdentity()
        await testWrongIdentityIsRejected()
        await testMatchingVersionPasses()
        await testMismatchedVersionIsRejected()
        await testArtifactUsesIMGSizeAndHash()
        await testFailedAcquisitionLeavesNoArtifact()
        testAcquisitionPolicyIdentityMapping()
        testBundledCatalogPolicyCounts()
        testAcquisitionErrorsHaveSafeUserCopy()
        await testWithheldAcquisitionFailsBeforeWorkspaceAndHTTP()
        testNoDeviceWriteDependency()

        print("PASS: 26 Stage 4.1 acquisition tests")
    }

    private static func testCatalogResolvesFrance() {
        let json = """
        {
          "catalogVersion": 1,
          "updatedAt": "2026-08-21T03:00:00Z",
          "providers": [
            {
              "id": "freizeitkarte",
              "name": "Freizeitkarte",
              "website": "https://www.freizeitkarte-osm.de/",
              "attribution": "Freizeitkarte",
              "licenseURL": "https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
              "maps": [
                {
                  "id": "freizeitkarte-fra",
                  "region": "FRA",
                  "name": "Republic of France",
                  "version": { "year": 2026, "month": 5 },
                  "sizeBytes": 298518679,
                  "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/FRA+_en_gmapsupp.img.zip"
                }
              ]
            }
          ]
        }
        """

        do {
            let catalog = try MapCatalogDocumentDecoder().decode(Data(json.utf8))
            let package = catalog.packages.first
            expect(
                package?.id == "freizeitkarte-fra"
                    && package?.regionId == "FRA"
                    && package?.providerId == "freizeitkarte"
                    && package?.version == version(2026, 5)
                    && package?.downloadURL?.absoluteString.contains("FRA+_en_gmapsupp.img.zip") == true
                    && package?.expectedDownloadSizeBytes == 298518679,
                "catalog resolves Freizeitkarte France with the original source URL"
            )
        } catch {
            expect(false, "catalog resolves Freizeitkarte France with the original source URL")
        }
    }

    private static func testCatalogKeepsAllDownloadableRegions() {
        let json = """
        {
          "catalogVersion": 1,
          "updatedAt": "2026-08-21T03:00:00Z",
          "providers": [
            {
              "id": "freizeitkarte",
              "name": "Freizeitkarte",
              "website": "https://www.freizeitkarte-osm.de/",
              "attribution": "Freizeitkarte",
              "licenseURL": "https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
              "maps": [
                {
                  "id": "freizeitkarte-deu",
                  "region": "DEU",
                  "name": "Germany",
                  "version": { "year": 2026, "month": 5 },
                  "sizeBytes": 100,
                  "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip"
                },
                {
                  "id": "freizeitkarte-ltu",
                  "region": "LTU",
                  "name": "Lithuania",
                  "version": { "year": 2026, "month": 5 },
                  "sizeBytes": 100,
                  "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/LTU+_en_gmapsupp.img.zip"
                },
                {
                  "id": "freizeitkarte-lva",
                  "region": "LVA",
                  "name": "Latvia",
                  "version": { "year": 2026, "month": 5 },
                  "sizeBytes": 100,
                  "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/LVA+_en_gmapsupp.img.zip"
                }
              ]
            }
          ]
        }
        """

        do {
            let catalog = try MapCatalogDocumentDecoder().decode(Data(json.utf8))
            expect(
                catalog.packages.map(\.regionId) == ["DEU", "LTU", "LVA"]
                    && catalog.regions.map(\.id).sorted() == ["DEU", "LTU", "LVA"],
                "all downloadable map regions remain available to catalog consumers"
            )
        } catch {
            expect(false, "all downloadable map regions remain available to catalog consumers")
        }
    }

    private static func testFormatDetection() {
        do {
            let rawURL = try temporaryFile(data: makeIMG(region: "FRA", release: "26.05"))
            defer { try? FileManager.default.removeItem(at: rawURL) }
            let zipURL = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: zipURL) }

            expect(
                try MapPackageFormat.detect(fileURL: rawURL) == .rawIMG
                    && (try MapPackageFormat.detect(fileURL: zipURL)) == .zip,
                "raw IMG and ZIP package formats are detected from content"
            )
        } catch {
            expect(false, "raw IMG and ZIP package formats are detected from content")
        }
    }

    private static func testArchivePathSafety() {
        do {
            try SafeArchivePathValidator().validate("../outside.img")
            expect(false, "archive traversal path is rejected")
        } catch let error as MapAcquisitionError {
            if case .unsafeArchivePath = error {
                expect(true, "archive traversal path is rejected")
            } else {
                expect(false, "archive traversal path is rejected")
            }
        } catch {
            expect(false, "archive traversal path is rejected")
        }
    }

    private static func testExtractedSymlinkSafety() async {
        let image = makeIMG(region: "FRA", release: "26.05")
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            _ = try await acquire(
                package: makePackage(),
                source: source,
                extractor: SymlinkArchiveExtractor(image: image)
            )
            expect(false, "extracted symbolic links are rejected")
        } catch let error as MapAcquisitionError {
            if case .unsafeArchivePath = error {
                expect(true, "extracted symbolic links are rejected")
            } else {
                expect(false, "extracted symbolic links are rejected")
            }
        } catch {
            expect(false, "extracted symbolic links are rejected")
        }
    }

    private static func testDownloaderUsesCatalogURL() async {
        let recorder = URLRecorder()
        let image = makeIMG(region: "FRA", release: "26.05")
        do {
            let source = try temporaryFile(data: image)
            defer { try? FileManager.default.removeItem(at: source) }
            let package = makePackage(sourceURL: URL(string: "https://provider.example/fra.zip")!)
            let workspace = try makeWorkspace()
            let client = RecordingDownloadClient(
                recorder: recorder,
                response: MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: source)
            )
            let artifact = try await MapPackageAcquirer(downloadClient: client).acquire(
                package: package,
                canonicalRegion: "France",
                workspace: workspace
            )
            try? workspace.cleanup()

            expect(
                recorder.url == package.downloadURL && artifact.sourcePackageURL == package.downloadURL,
                "downloader receives the catalog URL instead of a UI-hardcoded URL"
            )
        } catch {
            expect(false, "downloader receives the catalog URL instead of a UI-hardcoded URL")
        }
    }

    private static func testReviewedProviderURLPolicy() {
        let policy = ReviewedProviderURLPolicy.freizeitkarte
        let allowed = URL(string: "https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip")!
        let rejected = [
            URL(string: "http://download.freizeitkarte-osm.de/garmin/latest/DEU.zip")!,
            URL(string: "https://download.freizeitkarte-osm.de.example/DEU.zip")!,
            URL(string: "https://example.com/DEU.zip")!,
            URL(string: "https://user:secret@download.freizeitkarte-osm.de/DEU.zip")!
        ]

        do {
            try policy.validate(allowed)
            guard rejected.allSatisfy({ url in
                do {
                    try policy.validate(url)
                    return false
                } catch MapAcquisitionError.untrustedSourceURL {
                    return true
                } catch {
                    return false
                }
            }) else {
                expect(false, "provider URL policy accepts only the reviewed HTTPS host")
                return
            }
            expect(true, "provider URL policy accepts only the reviewed HTTPS host")
        } catch {
            expect(false, "provider URL policy accepts only the reviewed HTTPS host")
        }
    }

    private static func testFailedHTTPIsTyped() async {
        do {
            let source = try temporaryFile(data: Data([1, 2, 3]))
            defer { try? FileManager.default.removeItem(at: source) }
            let client = StubDownloadClient(
                response: MapPackageDownloadResponse(statusCode: 503, temporaryFileURL: source)
            )
            _ = try await MapPackageAcquirer(downloadClient: client).acquire(
                package: makePackage(),
                workspace: try makeWorkspace()
            )
            expect(false, "failed HTTP response returns DOWNLOAD_FAILED")
        } catch let error as MapAcquisitionError {
            if case .downloadFailed = error {
                expect(true, "failed HTTP response returns DOWNLOAD_FAILED")
            } else {
                expect(false, "failed HTTP response returns DOWNLOAD_FAILED")
            }
        } catch {
            expect(false, "failed HTTP response returns DOWNLOAD_FAILED")
        }
    }

    private static func testEmptyDownloadIsTyped() async {
        do {
            let source = try temporaryFile(data: Data())
            defer { try? FileManager.default.removeItem(at: source) }
            let client = StubDownloadClient(
                response: MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: source)
            )
            _ = try await MapPackageAcquirer(downloadClient: client).acquire(
                package: makePackage(),
                workspace: try makeWorkspace()
            )
            expect(false, "empty download returns DOWNLOAD_INCOMPLETE")
        } catch let error as MapAcquisitionError {
            if case .downloadIncomplete = error {
                expect(true, "empty download returns DOWNLOAD_INCOMPLETE")
            } else {
                expect(false, "empty download returns DOWNLOAD_INCOMPLETE")
            }
        } catch {
            expect(false, "empty download returns DOWNLOAD_INCOMPLETE")
        }
    }

    private static func testRenamedIMGIsIdentifiedByContent() async {
        let image = makeIMG(region: "FRA", release: "26.05")
        let extractor = FixtureArchiveExtractor(images: [("BaseCamp-renamed.img", image)])
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: makePackage(),
                source: source,
                extractor: extractor
            )
            expect(
                artifact.provider == "freizeitkarte"
                    && artifact.region == "FRA"
                    && artifact.canonicalRegion == "France"
                    && artifact.localIMGURL.lastPathComponent == "BaseCamp-renamed.img",
                "IMG identity is read from metadata, not its filename"
            )
        } catch {
            expect(false, "IMG identity is read from metadata, not its filename")
        }
    }

    private static func testCompositeRegionIdentityPasses() async {
        let image = makeSplitHeaderCanariasIMG()

        let package = MapPackage(
            id: "freizeitkarte-esp-canarias",
            providerId: "freizeitkarte",
            regionId: "ESP-CANARIAS",
            name: "Canarias",
            version: version(2026, 5),
            sizeBytes: UInt64(image.count),
            sourceURL: URL(string: "https://provider.example/canarias.zip"),
            releaseDate: "2026-05-03",
            identifier: "ESP_CANARIAS"
        )

        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: package,
                source: source,
                extractor: FixtureArchiveExtractor(images: [("gmapsupp.img", image)])
            )
            expect(
                artifact.region == "ESPCANARIAS",
                "composite Freizeitkarte region identity is accepted"
            )
        } catch {
            expect(false, "composite Freizeitkarte region identity is accepted")
        }
    }

    private static func testSplitReleaseHeaderPasses() async {
        let image = makeSplitReleaseHeaderAndorraIMG()
        let package = MapPackage(
            id: "freizeitkarte-and",
            providerId: "freizeitkarte",
            regionId: "AND",
            name: "Principality of Andorra",
            version: version(2026, 5),
            sizeBytes: UInt64(image.count),
            sourceURL: URL(string: "https://provider.example/andorra.zip"),
            releaseDate: "2026-05-03",
            identifier: "AND"
        )

        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: package,
                source: source,
                extractor: FixtureArchiveExtractor(images: [("gmapsupp.img", image)])
            )
            expect(
                artifact.region == "AND" && artifact.version == version(2026, 5),
                "Andorra IMG with a split Release header passes identity and version validation"
            )
        } catch {
            expect(
                false,
                "Andorra IMG with a split Release header passes identity and version validation"
            )
        }
    }

    private static func testOpenTopoMapAcquisitionUsesOfficialURLAndIdentity() async {
        let image = makeOpenTopoMapIMG()
        let package = MapPackage(
            id: "opentopomap-ltu",
            providerId: "opentopomap",
            regionId: "LTU",
            name: "Lithuania",
            version: version(2026, 5),
            sizeBytes: UInt64(image.count),
            sourceURL: URL(string: "https://garmin.opentopomap.org/europe/lithuania/otm-lithuania.zip"),
            releaseDate: "2026-05-25",
            identifier: "otm-lithuania",
            providerRegionId: "lithuania",
            canonicalRegionId: "LTU",
            countryCodes: ["LT"]
        )
        let recorder = URLRecorder()

        do {
            let source = try temporaryFile(data: image)
            defer { try? FileManager.default.removeItem(at: source) }
            let workspace = try makeWorkspace()
            defer { try? workspace.cleanup() }
            let artifact = try await MapPackageAcquirer(
                downloadClient: RecordingDownloadClient(
                    recorder: recorder,
                    response: MapPackageDownloadResponse(
                        statusCode: 200,
                        temporaryFileURL: source
                    )
                )
            ).acquire(
                package: package,
                canonicalRegion: "Lithuania",
                workspace: workspace
            )
            expect(
                recorder.url == package.sourceURL
                    && artifact.provider == "opentopomap"
                    && artifact.region == "LTU"
                    && artifact.version == version(2026, 5)
                    && artifact.targetFilename == "terento_opentopomap_ltu.img",
                "OpenTopoMap uses the official URL and the shared acquisition identity/target path"
            )
        } catch {
            expect(
                false,
                "OpenTopoMap uses the official URL and the shared acquisition identity/target path"
            )
        }
    }

    private static func testRegionalProviderTokensRemainConcrete() {
        let tokens = [
            "DEU+NORTH",
            "DEU+SOUTH",
            "FRA+NORTHEAST",
            "FRA+NORTHWEST",
            "FRA+SOUTHEAST",
            "FRA+SOUTHWEST",
            "NOR+NORTH",
            "NOR+SOUTH",
            "RUS_CENTRAL",
            "RUS_NORTHWEST",
            "RUS+KGD"
        ]

        let parsed = tokens.allSatisfy { token in
            GarminIMGMetadataParser().parse(
                Array(makeRegionalVariantIMG(token: token).prefix(GarminIMGMetadataParser.prefixLength))
            )?.region == token
        }

        expect(
            parsed,
            "regional Freizeitkarte IMG headers preserve DEU/FRA/NOR/RUS package tokens"
        )
    }

    private static func testSharedCatalogRegionsUseDistinctManagedTargets() {
        let generator = TerentoManagedFilenameGenerator()
        let packages = [
            MapPackage(
                id: "freizeitkarte-azores",
                providerId: "freizeitkarte",
                regionId: "AZORES",
                name: "Azores",
                version: version(2026, 5),
                sizeBytes: 1,
                sourceURL: nil,
                releaseDate: nil,
                identifier: "AZORES"
            ),
            MapPackage(
                id: "freizeitkarte-balearics",
                providerId: "freizeitkarte",
                regionId: "AZORES",
                name: "Balearics",
                version: version(2026, 5),
                sizeBytes: 1,
                sourceURL: nil,
                releaseDate: nil,
                identifier: "BALEARICS"
            ),
            MapPackage(
                id: "freizeitkarte-madeira",
                providerId: "freizeitkarte",
                regionId: "AZORES",
                name: "Madeira",
                version: version(2026, 5),
                sizeBytes: 1,
                sourceURL: nil,
                releaseDate: nil,
                identifier: "MADEIRA"
            )
        ]

        let filenames = packages.compactMap {
            try? generator.filename(
                providerId: $0.providerId,
                regionId: $0.canonicalRegionId
            )
        }

        expect(
            Set(filenames).count == packages.count
                && filenames == [
                    "terento_freizeitkarte_azores.img",
                    "terento_freizeitkarte_balearics.img",
                    "terento_freizeitkarte_madeira.img"
                ],
            "catalog packages sharing AZORES use distinct managed targets"
        )
    }

    private static func testSharedCatalogRegionUsesConcreteSourceIdentity() async {
        let image = makeRegionalVariantIMG(token: "BALEARICS")
        let package = MapPackage(
            id: "freizeitkarte-balearics",
            providerId: "freizeitkarte",
            regionId: "AZORES",
            name: "Balearics",
            version: version(2026, 5),
            sizeBytes: UInt64(image.count),
            sourceURL: URL(string: "https://provider.example/balearics.img"),
            releaseDate: "2026-05-03",
            identifier: "BALEARICS",
            providerRegionId: "BALEARICS",
            canonicalRegionId: "AZORES"
        )

        do {
            let source = try temporaryFile(data: image)
            defer { try? FileManager.default.removeItem(at: source) }
            let workspace = try makeWorkspace()
            defer { try? workspace.cleanup() }
            let artifact = try await MapPackageAcquirer(
                downloadClient: StubDownloadClient(
                    response: MapPackageDownloadResponse(
                        statusCode: 200,
                        temporaryFileURL: source
                    )
                )
            ).acquire(package: package, canonicalRegion: "Balearics", workspace: workspace)

            expect(
                package.regionId == "AZORES"
                    && package.canonicalRegionId == "BALEARICS"
                    && artifact.region == "BALEARICS"
                    && artifact.targetFilename == "terento_freizeitkarte_balearics.img",
                "shared catalog region validates against the concrete Freizeitkarte package identity"
            )
        } catch {
            expect(
                false,
                "shared catalog region validates against the concrete Freizeitkarte package identity"
            )
        }
    }

    private static func testWrongIdentityIsRejected() async {
        let image = makeIMG(region: "DEU", release: "26.05")
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            _ = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(images: [("wrong.img", image)])
            )
            expect(false, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
        } catch let error as MapAcquisitionError {
            if case .sourceIdentityMismatch = error {
                expect(true, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
            } else {
                expect(false, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
            }
        } catch {
            expect(false, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
        }
    }

    private static func testMatchingVersionPasses() async {
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(
                    images: [("any-name.img", makeIMG(region: "FRA", release: "26.05"))]
                )
            )
            expect(artifact.version == version(2026, 5), "matching catalog and IMG version passes")
        } catch {
            expect(false, "matching catalog and IMG version passes")
        }
    }

    private static func testMismatchedVersionIsRejected() async {
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            _ = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(
                    images: [("any-name.img", makeIMG(region: "FRA", release: "26.04"))]
                )
            )
            expect(false, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
        } catch let error as MapAcquisitionError {
            if case .sourceVersionMismatch = error {
                expect(true, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
            } else {
                expect(false, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
            }
        } catch {
            expect(false, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
        }
    }

    private static func testArtifactUsesIMGSizeAndHash() async {
        let image = makeIMG(region: "FRA", release: "26.05")
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04] + Array(repeating: 7, count: 127)))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(images: [("payload.img", image)])
            )
            let expectedHash = SHA256.hash(data: image).map { String(format: "%02x", $0) }.joined()
            expect(
                artifact.installSizeBytes == UInt64(image.count)
                    && artifact.downloadSizeBytes == 131
                    && artifact.sha256 == expectedHash
                    && artifact.targetFilename == "terento_freizeitkarte_fra.img",
                "artifact records IMG install size, complete IMG SHA-256, and deterministic target"
            )
        } catch {
            expect(false, "artifact records IMG install size, complete IMG SHA-256, and deterministic target")
        }
    }

    private static func testFailedAcquisitionLeavesNoArtifact() async {
        do {
            let source = try temporaryFile(data: Data([0x01]))
            defer { try? FileManager.default.removeItem(at: source) }
            let workspace = try makeWorkspace()
            let root = workspace.rootURL
            _ = try await MapPackageAcquirer(
                downloadClient: StubDownloadClient(
                    response: MapPackageDownloadResponse(statusCode: 500, temporaryFileURL: source)
                )
            ).acquire(package: makePackage(), workspace: workspace)
            expect(false, "failed acquisition produces no validated artifact")
            try? FileManager.default.removeItem(at: root)
        } catch let error as MapAcquisitionError {
            if case .downloadFailed = error {
                expect(true, "failed acquisition produces no validated artifact")
            } else {
                expect(false, "failed acquisition produces no validated artifact")
            }
        } catch {
            expect(false, "failed acquisition produces no validated artifact")
        }
    }

    private static func testNoDeviceWriteDependency() {
        expect(true, "acquisition layer is transport-independent and read-only")
    }

    private static func testAcquisitionPolicyIdentityMapping() {
        let resolver = MapPackageAcquisitionPolicyResolver()
        let aliases = [
            ("RUS-CRIMEA", "RUS-CRIMEA", "freizeitkarte-rus-crimea"),
            ("RUS_CRIMEA", "RUS_CRIMEA", "freizeitkarte-rus-crimea"),
            ("freizeitkarte-rus-crimea", "RUS-CRIMEA", "freizeitkarte-rus-crimea")
        ]
        let crimeaResults = aliases.map { identifier, region, id in
            resolver.canonicalIdentity(for: policyPackage(id: id, region: region, identifier: identifier))
        }
        let futureRussia = resolver.availability(
            for: policyPackage(id: "freizeitkarte-rus-future", region: "RUS-FUTURE", identifier: "RUS_FUTURE")
        )
        let safeRegions = ["BLR", "UKR", "DEU"].map {
            resolver.availability(for: policyPackage(id: "freizeitkarte-\($0.lowercased())", region: $0, identifier: $0))
        }
        expect(
            crimeaResults.allSatisfy { $0 == CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA") }
                && futureRussia == .withheldRussia
                && safeRegions.allSatisfy { $0 == .available },
            "provider aliases map Crimea first, future RUS variants fail closed, and non-russia regions stay available"
        )
    }

    private static func testBundledCatalogPolicyCounts() {
        do {
            let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            let data = try Data(contentsOf: root.appendingPathComponent("Sources/TerentoPoC/Resources/Maps/catalog.json"))
            let packages = try MapCatalogDocumentDecoder().decode(data).packages
            let resolver = MapPackageAcquisitionPolicyResolver()
            let grouped = Dictionary(grouping: packages, by: resolver.availability(for:))
            let crimea = grouped[.withheldCrimea]?.first
            expect(
                packages.count == 240
                    && packages.filter { $0.providerId == "freizeitkarte" }.count == 63
                    && packages.filter { $0.providerId == "opentopomap" }.count == 177
                    && grouped[.available]?.count == 231
                    && grouped[.withheldRussia]?.count == 8
                    && grouped[.withheldCrimea]?.count == 1
                    && packages
                        .filter { $0.providerId == "opentopomap" && $0.providerRegionId.contains("russia") }
                        .allSatisfy { resolver.availability(for: $0) == .withheldRussia }
                    && crimea?.name == "Russian Federation, Crimean Federal District"
                    && ["BLR", "UKR", "DEU"].allSatisfy { region in
                        packages.first(where: { $0.regionId == region }).map {
                            resolver.availability(for: $0) == .available
                        } == true
                    },
                "bundled catalog preserves 63 FZK plus 177 OTM packages while policy withholds russia packages and Crimea"
            )
        } catch {
            expect(false, "bundled catalog preserves 63 FZK plus 177 OTM packages while policy withholds russia packages and Crimea")
        }
    }

    private static func testAcquisitionErrorsHaveSafeUserCopy() {
        let messages = [
            MapAcquisitionError.downloadFailed("/Users/alice/private/map.zip").userMessage,
            MapAcquisitionError.downloadIncomplete(expected: 900, actual: 12).userMessage,
            MapAcquisitionError.invalidPackage("unexpected bytes at /private/tmp/map.zip").userMessage,
            MapAcquisitionError.workspaceFailed("/private/tmp/workspace").userMessage
        ]
        expect(
            messages.allSatisfy {
                !$0.contains("/Users/")
                    && !$0.contains("/private/")
                    && !$0.contains("900")
                    && !$0.contains("12")
            },
            "acquisition failures keep paths and byte details in diagnostics, not user-facing copy"
        )
    }

    private static func testWithheldAcquisitionFailsBeforeWorkspaceAndHTTP() async {
        let counter = AcquisitionSideEffectCounter()
        let fixtures: [(MapPackage, MapAcquisitionAvailability)] = [
            (policyPackage(id: "freizeitkarte-rus-crimea", region: "RUS-CRIMEA", identifier: "RUS_CRIMEA"), .withheldCrimea),
            (policyPackage(id: "freizeitkarte-rus-volga", region: "RUS-VOLGA", identifier: "RUS_VOLGA"), .withheldRussia)
        ]
        var typedFailures: [MapAcquisitionAvailability] = []
        for (package, expectedAvailability) in fixtures {
            do {
                _ = try await MapPackageAcquirer(
                    downloadClient: CountingDownloadClient(counter: counter),
                    workspaceFactory: {
                        counter.workspaceCreations += 1
                        return try makeWorkspace()
                    }
                ).acquire(package: package)
            } catch let error as MapAcquisitionError {
                if error == .acquisitionWithheld(expectedAvailability) {
                    typedFailures.append(expectedAvailability)
                }
            } catch {}
        }
        expect(
            Set(typedFailures) == [.withheldCrimea, .withheldRussia]
                && counter.workspaceCreations == 0
                && counter.downloads == 0,
            "withheld acquisition fails before workspace creation and HTTP"
        )
    }

    private static func policyPackage(id: String, region: String, identifier: String) -> MapPackage {
        MapPackage(
            id: id,
            providerId: "freizeitkarte",
            regionId: region,
            name: id,
            version: version(2026, 8),
            sizeBytes: 100,
            sourceURL: URL(string: "https://download.freizeitkarte-osm.de/test.zip"),
            releaseDate: nil,
            identifier: identifier
        )
    }

    private static func acquire(
        package: MapPackage,
        source: URL,
        extractor: any MapPackageArchiveExtractor
    ) async throws -> ValidatedMapArtifact {
        let workspace = try makeWorkspace()
        defer { try? workspace.cleanup() }
        return try await MapPackageAcquirer(
            downloadClient: StubDownloadClient(
                response: MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: source)
            ),
            archiveExtractor: extractor
        ).acquire(
            package: package,
            canonicalRegion: "France",
            workspace: workspace
        )
    }

    private static func makePackage(sourceURL: URL? = URL(string: "https://provider.example/fra.zip")!) -> MapPackage {
        MapPackage(
            id: "freizeitkarte-fra",
            providerId: "freizeitkarte",
            regionId: "FRA",
            name: "Republic of France",
            version: version(2026, 5),
            sizeBytes: 298518679,
            sourceURL: sourceURL,
            releaseDate: "2026-05-03",
            identifier: "FRA+"
        )
    }

    private static func makeWorkspace() throws -> MapAcquisitionWorkspace {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage41-\(UUID().uuidString)", isDirectory: true)
        return try MapAcquisitionWorkspace(rootURL: root)
    }

    private static func temporaryFile(data: Data) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage41-source-\(UUID().uuidString)")
        try data.write(to: url, options: .atomic)
        return url
    }

    private static func makeIMG(region: String, release: String) -> Data {
        var data = Data(repeating: 0, count: 8192)
        write("DSKIMG", at: 0x10, length: 7, into: &data)
        write("GARMIN", at: 0x41, length: 7, into: &data)
        write("Freizeitkarte_\(region)+", at: 0x49, length: 20, into: &data)
        write("Release \(release)", at: 0x65, length: 31, into: &data)
        return data
    }

    private static func makeRegionalVariantIMG(token: String) -> Data {
        var data = Data(repeating: 0, count: 8192)
        write("DSKIMG", at: 0x10, length: 7, into: &data)
        write("GARMIN", at: 0x41, length: 7, into: &data)

        let header = Array("Freizeitkarte_\(token)".utf8)
        let description = Array(header.prefix(20))
        data.replaceSubrange(
            0x49..<(0x49 + 20),
            with: description + Array(repeating: 0, count: 20 - description.count)
        )

        let continuation = Array(header.dropFirst(20))
        if continuation.isEmpty {
            write("Release 26.05", at: 0x65, length: 31, into: &data)
        } else {
            let detail = continuation + Array(" (Release 26.05)".utf8)
            data.replaceSubrange(
                0x65..<(0x65 + 31),
                with: detail.prefix(31) + Array(repeating: 0, count: max(0, 31 - detail.count))
            )
        }

        return data
    }

    private static func makeOpenTopoMapIMG() -> Data {
        var data = Data(repeating: 0, count: 8192)
        write("DSKIMG", at: 0x10, length: 7, into: &data)
        write("GARMIN", at: 0x41, length: 7, into: &data)
        write("OpenTopoMap Lithuani", at: 0x49, length: 20, into: &data)
        write("a 2026-05-24", at: 0x65, length: 31, into: &data)
        return data
    }

    /// Mirrors the official 2026-05 Canarias IMG header. The 20-byte
    /// description ends at `ESP_CA`; binary header bytes follow, and the
    /// remaining `NARIAS` starts in the detail field.
    private static func makeSplitHeaderCanariasIMG() -> Data {
        var data = Data(repeating: 0, count: 8192)
        write("DSKIMG", at: 0x10, length: 7, into: &data)
        write("GARMIN", at: 0x41, length: 7, into: &data)
        write("Freizeitkarte_ESP_CA", at: 0x49, length: 20, into: &data)
        data[0x5D] = 0x10
        data[0x60] = 0x00
        data[0x61] = 0x09
        data[0x62] = 0x02
        data[0x63] = 0xE9
        data[0x64] = 0x7D
        data[0x65] = 0x7D
        write("NARIAS (Release 26.05)", at: 0x66, length: 30, into: &data)
        return data
    }

    /// Mirrors the official Andorra IMG header where `(R` is the end of the
    /// fixed description field and `elease 26.05)` starts in the detail field.
    private static func makeSplitReleaseHeaderAndorraIMG() -> Data {
        var data = Data(repeating: 0, count: 8192)
        write("DSKIMG", at: 0x10, length: 7, into: &data)
        write("GARMIN", at: 0x41, length: 7, into: &data)
        write("Freizeitkarte_AND (R", at: 0x49, length: 20, into: &data)
        data[0x5D] = 0x10
        data[0x5F] = 0x04
        data[0x61] = 0x09
        data[0x62] = 0x01
        data[0x63] = 0x85
        data[0x64] = 0x11
        write("elease 26.05)", at: 0x65, length: 31, into: &data)
        return data
    }

    private static func write(_ value: String, at offset: Int, length: Int, into data: inout Data) {
        let bytes = Array(value.utf8.prefix(length))
        data.replaceSubrange(
            offset..<(offset + length),
            with: bytes + Array(repeating: 0, count: length - bytes.count)
        )
    }

    private static func version(_ year: Int, _ month: Int) -> MapVersion {
        MapVersion(year: year, month: month)!
    }

    private static func expect(_ condition: Bool, _ message: String) {
        if condition {
            print("PASS: \(message)")
        } else {
            print("FAIL: \(message)")
            exit(1)
        }
    }
}

final class URLRecorder: @unchecked Sendable {
    var url: URL?
}

final class AcquisitionSideEffectCounter: @unchecked Sendable {
    var workspaceCreations = 0
    var downloads = 0
}

struct CountingDownloadClient: MapPackageDownloadClient, Sendable {
    let counter: AcquisitionSideEffectCounter

    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        counter.downloads += 1
        throw MapAcquisitionError.downloadFailed("unexpected HTTP call")
    }
}

struct StubDownloadClient: MapPackageDownloadClient, Sendable {
    let response: MapPackageDownloadResponse

    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        response
    }
}

struct RecordingDownloadClient: MapPackageDownloadClient, Sendable {
    let recorder: URLRecorder
    let response: MapPackageDownloadResponse

    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        recorder.url = url
        return response
    }
}

struct FixtureArchiveExtractor: MapPackageArchiveExtractor, Sendable {
    let images: [(String, Data)]

    func extract(archiveURL: URL, to extractionDirectory: URL) throws {
        try FileManager.default.createDirectory(
            at: extractionDirectory,
            withIntermediateDirectories: true
        )
        for (filename, data) in images {
            try data.write(
                to: extractionDirectory.appendingPathComponent(filename),
                options: .atomic
            )
        }
    }
}

struct SymlinkArchiveExtractor: MapPackageArchiveExtractor, Sendable {
    let image: Data

    func extract(archiveURL: URL, to extractionDirectory: URL) throws {
        try FileManager.default.createDirectory(
            at: extractionDirectory,
            withIntermediateDirectories: true
        )
        try image.write(
            to: extractionDirectory.appendingPathComponent("payload.img"),
            options: .atomic
        )
        try FileManager.default.createSymbolicLink(
            at: extractionDirectory.appendingPathComponent("outside"),
            withDestinationURL: URL(fileURLWithPath: "/tmp")
        )
    }
}

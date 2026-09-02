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
struct Stage1ProviderNeutralTests {
    private static let packageRoot = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()

    private static var identityContractCatalogURL: URL {
        if let path = ProcessInfo.processInfo.environment["TERENTO_CATALOG_CONTRACT_PATH"],
           !path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return URL(fileURLWithPath: path)
        }
        return packageRoot.appendingPathComponent(
            "Sources/TerentoPoC/Resources/Maps/catalog.json"
        )
    }

    static func main() async {
        testLegacyPackageGetsRequiredMainArtifact()
        testOptionalContoursDoesNotHideMainArtifact()
        testProviderNativeMetadataDecodesWithoutFZKSemantics()
        testProviderRegistryHasNoImplicitDefaultAndSortsAlphabetically()
        testCatalogRegionsAreProviderScoped()
        testSourceKindsKeepProviderAndCustomInputsExplicit()
        testSourcePolicyRegistryResolvesByProviderID()
        testBundledOpenTopoMapProviderPolicy()
        testOpenTopoMapIMGMetadataIsIdentified()
        testOpenTopoMapLegacyIdentityAliasIsScoped()
        testOpenTopoMapCompactDateHeaderIsIdentified()
        testOpenTopoMapSplitDateHeadersAreIdentified()
        testEveryBundledOpenTopoMapRowAcceptsBothDateHeaderForms()
        testEveryBundledFreizeitkarteRowMatchesProviderIdentity()
        testConfiguredCatalogContractIsCompatibleWithClient()
        testIncompatibleRemoteIdentityIsRejected()
        testBundledCatalogIncludesOpenTopoMap()
        testBundledProvidersHaveReviewedInstallPaths()
        testRemoteCatalogReceivesBundledProviderSupplement()
        testRemotePausedProviderDoesNotReceiveBundledPackages()
        testProviderLifecycleMetadataDecodesFailClosed()
        await testDownloadFailureUsesConfirmedProviderDownState()

        print("PASS: 23 Stage 1 provider-neutral core tests")
    }

    private static func testLegacyPackageGetsRequiredMainArtifact() {
        let package = makePackage()
        expect(
            package.artifacts.count == 1
                && package.mainArtifact?.kind == .main
                && package.mainArtifact?.required == true
                && package.mainArtifact?.sizeBytes == 300
                && package.hasUsableMainArtifact,
            "legacy catalog packages gain one required usable main artifact"
        )
    }

    private static func testOptionalContoursDoesNotHideMainArtifact() {
        let package = MapPackage(
            id: "opentopomap-ltu",
            providerId: "opentopomap",
            regionId: "LTU",
            name: "Lithuania",
            version: version(2026, 8),
            sizeBytes: 500,
            sourceURL: URL(string: "https://maps.example/ltu.zip"),
            releaseDate: nil,
            identifier: "LTU",
            artifacts: [
                MapArtifact(
                    id: "opentopomap-ltu-main",
                    kind: .main,
                    required: true,
                    providerId: "opentopomap",
                    providerRegionId: "LTU",
                    canonicalRegionId: "LTU",
                    version: version(2026, 8),
                    sourceURL: URL(string: "https://maps.example/ltu.zip"),
                    sizeBytes: 450
                ),
                MapArtifact(
                    id: "opentopomap-ltu-contours",
                    kind: .contours,
                    required: false,
                    providerId: "opentopomap",
                    providerRegionId: "LTU",
                    canonicalRegionId: "LTU",
                    version: version(2026, 8),
                    sourceURL: nil,
                    sizeBytes: nil,
                    validationState: .unavailable
                )
            ]
        )

        expect(
            package.mainArtifact?.required == true
                && package.optionalArtifacts.count == 1
                && package.optionalArtifacts.first?.kind == .contours
                && package.hasUsableMainArtifact,
            "an unavailable optional contours artifact does not block the main map"
        )
    }

    private static func testProviderNativeMetadataDecodesWithoutFZKSemantics() {
        let json = """
        {
          "catalogVersion": 2,
          "updatedAt": "2026-08-31T08:00:00Z",
          "providers": [
            {
              "id": "opentopomap",
              "name": "OpenTopoMap",
              "website": "https://garmin.opentopomap.org/",
              "attribution": "OpenTopoMap",
              "licenseURL": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
              "licenseInformation": "CC BY-NC-SA 4.0",
              "maps": [
                {
                  "id": "opentopomap-ltu",
                  "region": "LTU",
                  "providerRegionId": "lithuania",
                  "canonicalRegionId": "LTU",
                  "name": "Lithuania",
                  "countryCodes": ["LT"],
                  "regionKind": "country",
                  "tags": ["topo", "outdoor"],
                  "capabilities": ["routing", "contours-optional"],
                  "version": { "year": 2026, "month": 8 },
                  "releaseMetadata": {
                    "releaseId": "otm-2026-08-31",
                    "versionLabel": "2026-08-31 generated",
                    "generatedAt": "2026-08-31",
                    "sourceUpdatedAt": "2026-08-30"
                  },
                  "sizeBytes": 500,
                  "artifacts": [
                    {
                      "id": "opentopomap-ltu-main",
                      "kind": "main",
                      "required": true,
                      "sourceURL": "https://garmin.opentopomap.org/europe/lithuania/otm-lithuania.zip",
                      "sizeBytes": 450
                    },
                    {
                      "id": "opentopomap-ltu-contours",
                      "kind": "contours",
                      "required": false,
                      "sourceURL": "https://garmin.opentopomap.org/europe/lithuania/otm-lithuania-contours.zip",
                      "sizeBytes": 50
                    }
                  ]
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
                catalog.providers.first?.licenseInformation == "CC BY-NC-SA 4.0"
                    && package?.providerRegionId == "lithuania"
                    && package?.canonicalRegionId == "LTU"
                    && package?.countryCodes == ["LT"]
                    && package?.tags == ["topo", "outdoor"]
                    && package?.releaseMetadata?.releaseId == "otm-2026-08-31"
                    && package?.artifacts.map(\.kind) == [.main, .contours],
                "provider-native release, region, tags, and artifact metadata decode neutrally"
            )
        } catch {
            expect(false, "provider-native release, region, tags, and artifact metadata decode neutrally")
        }
    }

    private static func testProviderRegistryHasNoImplicitDefaultAndSortsAlphabetically() {
        let registry = MapProviderRegistry(adapters: [])
        let catalog = MapCatalog(
            catalogVersion: 1,
            updatedAt: Date(timeIntervalSince1970: 0),
            providers: [
                MapProvider(id: "z-provider", name: "Zulu", website: nil, attribution: nil, licenseURL: nil),
                MapProvider(id: "a-provider", name: "Alpha", website: nil, attribution: nil, licenseURL: nil)
            ],
            regions: [],
            packages: []
        )

        expect(
            registry.adapter(for: "freizeitkarte") == nil
                && catalog.sortedProviders.map(\.name) == ["Alpha", "Zulu"],
            "provider registry has no implicit provider and catalog presentation is alphabetical"
        )
    }

    private static func testCatalogRegionsAreProviderScoped() {
        let catalog = MapCatalog(
            catalogVersion: 1,
            updatedAt: Date(timeIntervalSince1970: 0),
            providers: [],
            regions: [
                MapRegion(id: "LTU", name: "Alpha Lithuania", country: "LT", providerId: "a-provider"),
                MapRegion(id: "LTU", name: "Zulu Lithuania", country: "LT", providerId: "z-provider")
            ],
            packages: []
        )

        expect(
            catalog.region(for: "LTU", providerId: "a-provider")?.name == "Alpha Lithuania"
                && catalog.region(for: "LTU", providerId: "z-provider")?.name == "Zulu Lithuania",
            "the same region token resolves to the correct provider-scoped region"
        )
    }

    private static func testSourceKindsKeepProviderAndCustomInputsExplicit() {
        let providerSource = MapSource.provider(package: makePackage())
        let customSource = MapSource.custom(
            fileURL: URL(fileURLWithPath: "/tmp/imported.img"),
            displayName: "Imported map"
        )

        expect(
            providerSource.kind == .provider && customSource.kind == .custom,
            "provider downloads and local custom files have explicit source kinds"
        )
    }

    private static func testSourcePolicyRegistryResolvesByProviderID() {
        let registry = ReviewedProviderURLPolicyRegistry(policies: [
            "Example Provider": ReviewedProviderURLPolicy(allowedHosts: ["maps.example"])
        ])
        let accepted = URL(string: "https://maps.example/map.zip")!
        let rejected = URL(string: "https://other.example/map.zip")!

        do {
            guard let policy = registry.policy(for: "example-provider") else {
                expect(false, "source host policy resolves by normalized provider ID")
                return
            }
            try policy.validate(accepted)
            do {
                try policy.validate(rejected)
                expect(false, "source host policy resolves by normalized provider ID")
            } catch MapAcquisitionError.untrustedSourceURL {
                expect(true, "source host policy resolves by normalized provider ID")
            } catch {
                expect(false, "source host policy resolves by normalized provider ID")
            }
        } catch {
            expect(false, "source host policy resolves by normalized provider ID")
        }
    }

    private static func testBundledOpenTopoMapProviderPolicy() {
        let package = MapPackage(
            id: "opentopomap-ltu",
            providerId: "opentopomap",
            regionId: "LTU",
            name: "Lithuania",
            version: version(2026, 5),
            sizeBytes: 219_494_190,
            sourceURL: URL(string: "https://garmin.opentopomap.org/europe/lithuania/otm-lithuania.zip"),
            releaseDate: "2026-05-25",
            identifier: "otm-lithuania",
            countryCodes: ["LT"]
        )
        let resolver = MapPackageAcquisitionPolicyResolver()
        let officialURL = package.sourceURL!

        do {
            try ReviewedProviderURLPolicyRegistry.bundled
                .policy(for: package.providerId)!
                .validate(officialURL)
            expect(
                resolver.canonicalIdentity(for: package)?.countryCode == "LT"
                    && resolver.availability(for: package) == .available,
                "bundled OpenTopoMap adapter resolves an official Lithuania package"
            )
        } catch {
            expect(false, "bundled OpenTopoMap adapter resolves an official Lithuania package")
        }
    }

    private static func testOpenTopoMapIMGMetadataIsIdentified() {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        write("DSKIMG", at: 0x10, to: &bytes)
        write("GARMIN", at: 0x41, to: &bytes)
        write("OpenTopoMap Lithuani", at: 0x49, to: &bytes)
        write("a 2026-05-24", at: 0x65, to: &bytes)

        let metadata = GarminIMGMetadataParser().parse(bytes)
        expect(
            metadata?.provider == "OpenTopoMap"
                && metadata?.region == "LTU"
                && metadata?.name == "OpenTopoMap Lithuania"
                && metadata?.version == version(2026, 5),
            "OpenTopoMap Garmin IMG headers resolve provider, Lithuania, name, and release"
        )

        var longNameBytes = Array(repeating: UInt8(0), count: 8192)
        write("DSKIMG", at: 0x10, to: &longNameBytes)
        write("GARMIN", at: 0x41, to: &longNameBytes)
        write("OpenTopoMap Saint-he", at: 0x49, to: &longNameBytes)
        write("lena-ascension-an 2026-05-10", at: 0x65, to: &longNameBytes)
        let longNameMetadata = GarminIMGMetadataParser().parse(
            longNameBytes,
            filename: "otm-saint-helena-ascension-and-tristan-da-cunha.img"
        )
        expect(
            longNameMetadata?.region == "SAINTHELENAASCENSIONANDTRISTANDACUNHA",
            "long OpenTopoMap IMG names use the exact provider filename when the fixed header is truncated"
        )
    }

    private static func testOpenTopoMapLegacyIdentityAliasIsScoped() {
        let legacyOpenTopoMap = MapIdentity(provider: "OpenTopoMap", region: "LTU")
        let currentOpenTopoMap = MapIdentity(provider: "opentopomap", region: "LITHUANIA")
        let unrelatedFreizeitkarte = MapIdentity(provider: "freizeitkarte", region: "LTU")
        let unrelatedTarget = MapIdentity(provider: "freizeitkarte", region: "LVA")

        expect(
            MapIdentityMatcher.matches(
                actual: legacyOpenTopoMap,
                expected: currentOpenTopoMap
            )
                && !MapIdentityMatcher.matches(
                    actual: unrelatedFreizeitkarte,
                    expected: unrelatedTarget
                ),
            "the OTM Lithuania legacy alias is accepted without weakening other provider identity checks"
        )
    }

    private static func testOpenTopoMapCompactDateHeaderIsIdentified() {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        write("DSKIMG", at: 0x10, to: &bytes)
        write("GARMIN", at: 0x41, to: &bytes)
        write("OpenTopoMap Azores 2", at: 0x49, to: &bytes)
        write("026-05-24", at: 0x65, to: &bytes)

        let metadata = GarminIMGMetadataParser().parse(
            bytes,
            filename: "otm-azores.img"
        )
        expect(
            metadata?.provider == "OpenTopoMap"
                && metadata?.region == "AZORES"
                && metadata?.version == version(2026, 5)
                && metadata?.rawVersion == "Generated 2026-05-24",
            "OpenTopoMap compact Garmin date headers normalize to their 20YY release"
        )
    }

    private static func testOpenTopoMapSplitDateHeadersAreIdentified() {
        let parser = GarminIMGMetadataParser()
        let cases: [(filename: String, description: String, detail: String, version: MapVersion)] = [
            ("otm-alps.img", "OpenTopoMap Alps 202", "6-05-24", version(2026, 5)),
            ("otm-benin.img", "OpenTopoMap Benin 20", "26-08-26", version(2026, 8))
        ]

        let allCasesPass = cases.allSatisfy { item in
            var bytes = Array(repeating: UInt8(0), count: 8192)
            write("DSKIMG", at: 0x10, to: &bytes)
            write("GARMIN", at: 0x41, to: &bytes)
            write(item.description, at: 0x49, to: &bytes)
            write(item.detail, at: 0x65, to: &bytes)

            let metadata = parser.parse(bytes, filename: item.filename)
            return metadata?.provider == "OpenTopoMap"
                && metadata?.version == item.version
        }

        expect(
            allCasesPass,
            "OpenTopoMap dates split across fixed IMG header fields normalize before version validation"
        )
    }

    private static func testEveryBundledOpenTopoMapRowAcceptsBothDateHeaderForms() {
        do {
            let data = try Data(contentsOf: identityContractCatalogURL)
            let catalog = try MapCatalogDocumentDecoder().decode(data)
            let packages = catalog.packages.filter { $0.providerId == "opentopomap" }
            let parser = GarminIMGMetadataParser()
            let versionParser = OpenTopoMapVersionParser()

            if packages.count != 177 {
                print("OpenTopoMap catalog count mismatch: expected 177, got \(packages.count)")
            }

            let allRowsPass = packages.count == 177 && packages.allSatisfy { package in
                let providerRegion = package.providerRegionId
                let version = package.version
                let day = 24
                let fullDate = String(format: "%04d-%02d-%02d", version.year, version.month, day)
                let compactDate = String(format: "0%02d-%02d-%02d", version.year % 100, version.month, day)
                let filename = "otm-\(providerRegion).img"

                let fullVersion = versionParser.parse("Generated \(fullDate)")
                let compactVersion = versionParser.parse("Generated \(compactDate)")
                let fullMetadata = parser.parse(
                    makeOpenTopoMapIMG(date: fullDate),
                    filename: filename
                )
                let compactMetadata = parser.parse(
                    makeOpenTopoMapIMG(date: compactDate),
                    filename: filename
                )
                let splitMetadata = [
                    makeOpenTopoMapIMG(
                        description: "OpenTopoMap test 202",
                        detail: "6-\(String(format: "%02d", version.month))-24"
                    ),
                    makeOpenTopoMapIMG(
                        description: "OpenTopoMap test-#20",
                        detail: "26-\(String(format: "%02d", version.month))-26"
                    )
                ].compactMap {
                    parser.parse($0, filename: filename)
                }

                let metadataMatches = [fullMetadata, compactMetadata]
                    .compactMap { $0 }
                    .allSatisfy { metadata in
                        MapIdentityMatcher.matches(
                            actual: MapIdentity(
                                provider: metadata.provider,
                                region: metadata.region
                            ),
                            expected: package.identity,
                            providerRegionId: package.providerRegionId,
                            identifier: package.identifier
                        )
                    }
                let splitMetadataMatches = splitMetadata.allSatisfy { metadata in
                    MapIdentityMatcher.matches(
                        actual: MapIdentity(
                            provider: metadata.provider,
                            region: metadata.region
                        ),
                        expected: package.identity,
                        providerRegionId: package.providerRegionId,
                        identifier: package.identifier
                    )
                }
                let rowPasses = fullVersion == version
                    && compactVersion == version
                    && fullMetadata?.provider == "OpenTopoMap"
                    && compactMetadata?.provider == "OpenTopoMap"
                    && metadataMatches
                    && fullMetadata?.version == version
                    && compactMetadata?.version == version
                    && splitMetadata.count == 2
                    && splitMetadata.allSatisfy { $0.provider == "OpenTopoMap" }
                    && splitMetadataMatches
                    && (package.mainArtifact?.version ?? package.version) == version
                    && package.optionalArtifacts.allSatisfy {
                        $0.kind == .contours && $0.required == false && $0.version != nil
                    }
                if !rowPasses {
                    print("OpenTopoMap catalog validation failed for \(package.id) [\(providerRegion)] release \(version)")
                }
                return rowPasses
            }

            let contourRows = packages.flatMap(\.optionalArtifacts).filter { $0.kind == .contours }
            let requiresBundledContourFixture = ProcessInfo.processInfo.environment[
                "TERENTO_CATALOG_CONTRACT_PATH"
            ] == nil
            print(
                "OpenTopoMap matrix diagnostics: rows=\(packages.count), "
                    + "rowChecks=\(allRowsPass), contours=\(contourRows.count), "
                    + "externalCatalog=\(!requiresBundledContourFixture)"
            )
            expect(
                allRowsPass
                    && (!requiresBundledContourFixture || contourRows.count == 176),
                "all 177 OpenTopoMap rows accept full, compact, and split generated dates with strict identity/version checks"
            )
        } catch {
            expect(
                false,
                "all 177 OpenTopoMap rows accept full, compact, and split generated dates with strict identity/version checks"
            )
        }
    }

    private static func testEveryBundledFreizeitkarteRowMatchesProviderIdentity() {
        do {
            let data = try Data(contentsOf: identityContractCatalogURL)
            let catalog = try MapCatalogDocumentDecoder().decode(data)
            let packages = catalog.packages.filter { $0.providerId == "freizeitkarte" }
            let parser = GarminIMGMetadataParser()

            let allRowsPass = packages.count == 63 && packages.allSatisfy { package in
                let metadata = parser.parse(
                    Array(
                        makeFreizeitkarteIMG(token: package.providerRegionId)
                            .prefix(GarminIMGMetadataParser.prefixLength)
                    ),
                    filename: "\(package.providerRegionId)_en_gmapsupp.img"
                )
                guard let metadata else { return false }
                let rowPasses = metadata.provider == "Freizeitkarte"
                    && metadata.version == package.version
                    && MapIdentityMatcher.matches(
                        actual: MapIdentity(
                            provider: metadata.provider,
                            region: metadata.region
                        ),
                        expected: package.identity,
                        providerRegionId: package.providerRegionId,
                        identifier: package.identifier
                    )
                if !rowPasses {
                    print(
                        "Freizeitkarte catalog validation failed for \(package.id) "
                            + "[\(package.providerRegionId)] actual="
                            + "\(metadata.provider ?? "nil")/\(metadata.region ?? "nil") "
                            + "version=\(String(describing: metadata.version))"
                    )
                }
                return rowPasses
            }

            expect(
                allRowsPass,
                "all 63 Freizeitkarte rows match their provider-region IMG identity"
            )
        } catch {
            expect(
                false,
                "all 63 Freizeitkarte rows match their provider-region IMG identity"
            )
        }
    }

    private static func testConfiguredCatalogContractIsCompatibleWithClient() {
        do {
            let data = try Data(contentsOf: identityContractCatalogURL)
            let catalog = try MapCatalogDocumentDecoder().decode(data)
            expect(
                MapCatalogClientCompatibilityValidator().isCompatible(catalog),
                "the configured catalog is compatible with this client build"
            )
        } catch {
            expect(false, "the configured catalog is compatible with this client build")
        }
    }

    private static func testIncompatibleRemoteIdentityIsRejected() {
        let validator = MapCatalogClientCompatibilityValidator()
        let valid = makeContractCatalog(
            package: makeOpenTopoMapContractPackage(canonicalRegion: "LITHUANIA")
        )
        let incompatible = makeContractCatalog(
            package: makeOpenTopoMapContractPackage(canonicalRegion: "LIETUVA")
        )
        let empty = MapCatalog(
            catalogVersion: 1,
            updatedAt: Date(timeIntervalSince1970: 0),
            providers: valid.providers,
            regions: [],
            packages: []
        )

        expect(
            validator.isCompatible(valid)
                && !validator.isCompatible(incompatible)
                && !validator.isCompatible(empty),
            "catalog identity drift is rejected before remote metadata becomes active"
        )
    }

    private static func testBundledCatalogIncludesOpenTopoMap() {
        do {
            let root = packageRoot
            let data = try Data(contentsOf: root.appendingPathComponent(
                "Sources/TerentoPoC/Resources/Maps/catalog.json"
            ))
            let catalog = try MapCatalogDocumentDecoder().decode(data)
            let package = catalog.packages.first { $0.id == "opentopomap-ltu" }
            let openTopoMapPackages = catalog.packages.filter {
                $0.providerId == "opentopomap"
            }
            expect(catalog.providers.contains { $0.id == "opentopomap" }, "the bundled catalog exposes OpenTopoMap")
            expect(openTopoMapPackages.count == 177, "the bundled catalog exposes all 177 OpenTopoMap Garmin rows")
            expect(
                package?.sourceURL?.host == "garmin.opentopomap.org"
                    && package?.optionalArtifacts.contains { $0.kind == .contours } == true,
                "the OpenTopoMap Lithuania entry keeps its official source and optional contours"
            )
        } catch {
            print("Catalog decode error: \(error)")
            expect(false, "the bundled OpenTopoMap catalogue decodes")
        }
    }

    private static func testBundledProvidersHaveReviewedInstallPaths() {
        do {
            let root = packageRoot
            let data = try Data(contentsOf: root.appendingPathComponent(
                "Sources/TerentoPoC/Resources/Maps/catalog.json"
            ))
            let catalog = try MapCatalogDocumentDecoder().decode(data)
            let providerIDs = Set(catalog.providers.map { MapIdentity.normalizeProvider($0.id) })
            let registry = MapProviderRegistry.bundled
            let sourcePolicies = ReviewedProviderURLPolicyRegistry.bundled
            let allProvidersRegistered = providerIDs.allSatisfy {
                registry.adapter(for: $0) != nil && sourcePolicies.policy(for: $0) != nil
            }
            let allPackageSourcesReviewed = catalog.packages.allSatisfy { package in
                guard let sourceURL = package.downloadURL,
                      let policy = sourcePolicies.policy(for: package.providerId) else {
                    return false
                }
                do {
                    try policy.validate(sourceURL)
                    return true
                } catch {
                    return false
                }
            }
            expect(
                allProvidersRegistered && allPackageSourcesReviewed,
                "every bundled provider and package uses a reviewed common install path"
            )
        } catch {
            expect(false, "every bundled provider and package uses a reviewed common install path")
        }
    }

    private static func testRemoteCatalogReceivesBundledProviderSupplement() {
        do {
            let root = packageRoot
            let data = try Data(contentsOf: root.appendingPathComponent(
                "Sources/TerentoPoC/Resources/Maps/catalog.json"
            ))
            let bundled = try MapCatalogDocumentDecoder().decode(data)
            let remote = MapCatalog(
                catalogVersion: bundled.catalogVersion,
                updatedAt: bundled.updatedAt,
                providers: bundled.providers.filter { $0.id == "freizeitkarte" },
                regions: bundled.regions.filter { $0.providerId == "freizeitkarte" },
                packages: bundled.packages.filter { $0.providerId == "freizeitkarte" }
            )
            let merged = remote.mergingSupplemental(bundled)
            expect(
                merged.providers.map(\.id).contains("opentopomap")
                    && merged.packages.contains { $0.id == "opentopomap-ltu" },
                "a live catalog without OTM keeps the bundled OTM provider visible"
            )
        } catch {
            expect(false, "a live catalog without OTM keeps the bundled OTM provider visible")
        }
    }

    private static func testRemotePausedProviderDoesNotReceiveBundledPackages() {
        do {
            let root = packageRoot
            let data = try Data(contentsOf: root.appendingPathComponent(
                "Sources/TerentoPoC/Resources/Maps/catalog.json"
            ))
            let bundled = try MapCatalogDocumentDecoder().decode(data)
            let pausedOTM = MapProvider(
                id: "opentopomap",
                name: "OpenTopoMap",
                website: nil,
                attribution: nil,
                licenseURL: nil,
                lifecycleStatus: .paused,
                health: .healthy
            )
            let remote = MapCatalog(
                catalogVersion: bundled.catalogVersion,
                updatedAt: bundled.updatedAt,
                providers: bundled.providers.filter { $0.id == "freizeitkarte" } + [pausedOTM],
                regions: bundled.regions.filter { $0.providerId == "freizeitkarte" },
                packages: bundled.packages.filter { $0.providerId == "freizeitkarte" }
            )
            let merged = remote.mergingSupplemental(bundled)
            expect(
                merged.provider(for: "opentopomap")?.lifecycleStatus == .paused
                    && !merged.packages.contains { $0.providerId == "opentopomap" },
                "a remote paused provider cannot be re-enabled by bundled packages"
            )
        } catch {
            expect(false, "a remote paused provider cannot be re-enabled by bundled packages")
        }
    }

    private static func testProviderLifecycleMetadataDecodesFailClosed() {
        let json = """
        {
          "catalogVersion": 1,
          "updatedAt": "2026-08-31T12:00:00Z",
          "providers": [
            {
              "id": "opentopomap",
              "name": "OpenTopoMap",
              "status": "PAUSED",
              "health": "DOWN",
              "lastCheckedAt": "2026-08-31T11:55:00Z",
              "lastSuccessfulCatalogSync": "2026-08-31T11:50:00Z",
              "maps": []
            }
          ]
        }
        """
        do {
            let catalog = try MapCatalogDocumentDecoder().decode(Data(json.utf8))
            let provider = catalog.providers.first
            expect(
                provider?.lifecycleStatus == .paused
                    && provider?.health == .down
                    && provider?.lastCheckedAt != nil
                    && provider?.lastSuccessfulCatalogSync != nil
                    && provider?.allowsNewInstallCatalog == false,
                "provider lifecycle and health metadata decode into a fail-closed install state"
            )
        } catch {
            expect(false, "provider lifecycle and health metadata decode into a fail-closed install state")
        }
    }

    private static func write(_ value: String, at offset: Int, to bytes: inout [UInt8]) {
        for (index, byte) in value.utf8.enumerated() {
            bytes[offset + index] = byte
        }
    }

    private static func makeOpenTopoMapIMG(date: String) -> [UInt8] {
        makeOpenTopoMapIMG(
            description: "OpenTopoMap test",
            detail: date
        )
    }

    private static func makeOpenTopoMapIMG(
        description: String,
        detail: String
    ) -> [UInt8] {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        write("DSKIMG", at: 0x10, to: &bytes)
        write("GARMIN", at: 0x41, to: &bytes)
        write(description, at: 0x49, to: &bytes)
        write(detail, at: 0x65, to: &bytes)
        return bytes
    }

    private static func makeFreizeitkarteIMG(token: String) -> [UInt8] {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        write("DSKIMG", at: 0x10, to: &bytes)
        write("GARMIN", at: 0x41, to: &bytes)
        let header = Array("Freizeitkarte_\(token)".utf8)
        let description = Array(header.prefix(20))
        bytes.replaceSubrange(
            0x49..<(0x49 + 20),
            with: description + Array(repeating: 0, count: 20 - description.count)
        )

        let continuation = Array(header.dropFirst(20))
        let detail = continuation.isEmpty
            ? Array("Release 26.05".utf8)
            : continuation + Array(" (Release 26.05)".utf8)
        bytes.replaceSubrange(
            0x65..<(0x65 + 31),
            with: Array(detail.prefix(31))
                + Array(repeating: 0, count: max(0, 31 - detail.count))
        )
        return bytes
    }

    private static func testDownloadFailureUsesConfirmedProviderDownState() async {
        do {
            let workspace = try MapAcquisitionWorkspace(
                rootURL: FileManager.default.temporaryDirectory
                    .appendingPathComponent("terento-stage1-health-\(UUID().uuidString)", isDirectory: true)
            )
            let acquirer = MapPackageAcquirer(
                downloadClient: FailingDownloadClient(),
                providerHealthChecker: FixedProviderHealthChecker(
                    result: MapProviderHealthProbeResult(
                        providerId: "freizeitkarte",
                        health: .down,
                        statusCode: 503,
                        checkedAt: Date(timeIntervalSince1970: 0)
                    )
                )
            )
            _ = try await acquirer.acquire(
                package: makePackage(),
                workspace: workspace
            )
            expect(false, "confirmed provider outage becomes a provider-down error")
        } catch let error as MapAcquisitionError {
            expect(
                error == .providerUnavailable(providerId: "freizeitkarte", statusCode: 503)
                    && error.localizedDescription == "The selected map provider is currently down. Try again later.",
                "confirmed provider outage becomes a provider-down error"
            )
        } catch {
            expect(false, "confirmed provider outage becomes a provider-down error")
        }
    }

    private static func makeOpenTopoMapContractPackage(
        canonicalRegion: String
    ) -> MapPackage {
        MapPackage(
            id: "opentopomap-lithuania",
            providerId: "opentopomap",
            regionId: canonicalRegion,
            name: "OpenTopoMap Lithuania",
            version: version(2026, 8),
            sizeBytes: 123_456,
            sourceURL: URL(
                string: "https://garmin.opentopomap.org/europe/lithuania/otm-lithuania.zip"
            ),
            releaseDate: "2026-08-31",
            identifier: "lithuania",
            downloadSizeBytes: 123_456,
            installSizeBytes: 234_567,
            providerRegionId: "lithuania",
            canonicalRegionId: canonicalRegion
        )
    }

    private static func makeContractCatalog(package: MapPackage) -> MapCatalog {
        MapCatalog(
            catalogVersion: 1,
            updatedAt: Date(timeIntervalSince1970: 0),
            providers: [
                MapProvider(
                    id: package.providerId,
                    name: "OpenTopoMap",
                    website: URL(string: "https://opentopomap.org/"),
                    attribution: "OpenTopoMap",
                    licenseURL: URL(string: "https://opentopomap.org/about"),
                    health: .healthy
                )
            ],
            regions: [],
            packages: [package]
        )
    }

    private static func makePackage() -> MapPackage {
        MapPackage(
            id: "freizeitkarte-ltu",
            providerId: "freizeitkarte",
            regionId: "LTU",
            name: "Lithuania",
            version: version(2026, 8),
            sizeBytes: 300,
            sourceURL: URL(string: "https://download.freizeitkarte-osm.de/map.zip"),
            releaseDate: nil,
            identifier: "LTU"
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

private struct FailingDownloadClient: MapPackageDownloadClient, Sendable {
    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        throw MapAcquisitionError.downloadFailed("simulated unavailable source")
    }
}

private struct FixedProviderHealthChecker: MapProviderHealthChecking, Sendable {
    let result: MapProviderHealthProbeResult

    func check(package: MapPackage) async -> MapProviderHealthProbeResult {
        result
    }
}

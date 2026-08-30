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
    static func main() async {
        testLegacyPackageGetsRequiredMainArtifact()
        testOptionalContoursDoesNotHideMainArtifact()
        testProviderNativeMetadataDecodesWithoutFZKSemantics()
        testProviderRegistryHasNoImplicitDefaultAndSortsAlphabetically()
        testCatalogRegionsAreProviderScoped()
        testSourceKindsKeepProviderAndCustomInputsExplicit()
        testSourcePolicyRegistryResolvesByProviderID()
        await testDownloadFailureUsesConfirmedProviderDownState()

        print("PASS: 8 Stage 1 provider-neutral core tests")
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

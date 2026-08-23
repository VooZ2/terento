import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct MapVersionComparisonTests {
    static func main() {
        testFreizeitkarteReleaseIsNormalizedToYearAndMonth()
        testSameVersionIsUpToDate()
        testLaterCatalogVersionMakesUpdateAvailable()
        testEarlierCatalogVersionMeansInstalledVersionIsNewer()
        testInvalidVersionProducesUnknown()
        testEmbeddedDateFragmentIsUnknown()
        testOtherInstalledRegionStillMeansInstallAvailable()
        testKnownDifferentRegionCannotMatchByIdentifier()

        print("PASS: 9 Stage 2 map comparison tests")
    }

    private static func testFreizeitkarteReleaseIsNormalizedToYearAndMonth() {
        let version = FreizeitkarteVersionParser().parse("Release 26.05")

        expect(
            version?.year == 2026 && version?.month == 5 && version?.description == "2026-05",
            "Release 26.05 normalizes to 2026-05"
        )
    }

    private static func testSameVersionIsUpToDate() {
        let status = compare(
            installedRawVersion: "Release 26.05",
            catalogRawVersion: "2026-05"
        )

        expect(status == .upToDate, "same version returns UP_TO_DATE")
    }

    private static func testLaterCatalogVersionMakesUpdateAvailable() {
        let status = compare(
            installedRawVersion: "Release 26.05",
            catalogRawVersion: "2026-06"
        )

        expect(status == .updateAvailable, "later catalog version returns UPDATE_AVAILABLE")
    }

    private static func testEarlierCatalogVersionMeansInstalledVersionIsNewer() {
        let status = compare(
            installedRawVersion: "Release 26.05",
            catalogRawVersion: "2026-04"
        )

        expect(status == .newerInstalled, "earlier catalog version returns NEWER_INSTALLED")
    }

    private static func testInvalidVersionProducesUnknown() {
        let parser = FreizeitkarteVersionParser()
        expect(parser.parse("Unknown format") == nil, "invalid version is not parsed")

        let status = compare(
            installedRawVersion: "Unknown format",
            catalogRawVersion: "2026-05"
        )

        expect(status == .unknown, "invalid installed version returns UNKNOWN")
    }

    private static func testEmbeddedDateFragmentIsUnknown() {
        let version = MapVersionNormalizer().parse(
            rawValue: nil,
            provider: "Freizeitkarte",
            fullText: "Build date 2026-05; device serial 2244"
        )

        expect(
            version == nil,
            "an embedded date fragment is not treated as a map release"
        )
    }

    private static func testOtherInstalledRegionStillMeansInstallAvailable() {
        let installedMap = InstalledMap(
            name: "Freizeitkarte Latvia",
            provider: "Freizeitkarte",
            region: "LVA",
            family: "Freizeitkarte_LVA+",
            rawVersion: "Release 26.05",
            version: FreizeitkarteVersionParser().parse("Release 26.05"),
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: 344_000_000,
            sourceFile: InstalledMapFile(
                path: "/GARMIN/other.img",
                filename: "other.img",
                sizeBytes: 344_000_000
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )

        let comparison = MapComparisonEngine().compare(
            installedMaps: [installedMap],
            provider: MapProvider(
                id: "freizeitkarte",
                name: "Freizeitkarte",
                website: nil,
                attribution: nil,
                licenseURL: nil
            ),
            region: MapRegion(id: "LTU", name: "Lithuania", country: "Lithuania"),
            catalogMap: MapPackage(
                id: "freizeitkarte-ltu",
                providerId: "freizeitkarte",
                regionId: "LTU",
                name: "Lithuania",
                version: MapVersion(year: 2026, month: 5)!,
                sizeBytes: 344_000_000,
                sourceURL: nil,
                releaseDate: nil,
                identifier: nil
            )
        )

        expect(
            comparison.status == .notInstalled,
            "different installed region returns INSTALL_AVAILABLE"
        )
    }

    private static func testKnownDifferentRegionCannotMatchByIdentifier() {
        let installedMap = InstalledMap(
            name: "Freizeitkarte Lithuania",
            provider: "Freizeitkarte",
            region: "LTU",
            family: "Freizeitkarte_LTU+",
            rawVersion: "Release 26.05",
            version: FreizeitkarteVersionParser().parse("Release 26.05"),
            identifier: "shared-provider-identifier",
            productId: nil,
            familyId: nil,
            sizeBytes: 344_000_000,
            sourceFile: InstalledMapFile(
                path: "/GARMIN/freizeitkarte-lithuania.img",
                filename: "freizeitkarte-lithuania.img",
                sizeBytes: 344_000_000
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )

        let catalogMap = MapPackage(
            id: "freizeitkarte-lva",
            providerId: "freizeitkarte",
            regionId: "LVA",
            name: "Latvia",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 298_518_679,
            sourceURL: nil,
            releaseDate: nil,
            identifier: "shared-provider-identifier"
        )

        let comparison = MapComparisonEngine().compare(
            installedMaps: [installedMap],
            provider: MapProvider(
                id: "freizeitkarte",
                name: "Freizeitkarte",
                website: nil,
                attribution: nil,
                licenseURL: nil
            ),
            region: MapRegion(id: "LVA", name: "Latvia", country: "Latvia"),
            catalogMap: catalogMap
        )

        expect(
            comparison.status == .notInstalled,
            "known LTU identity cannot match LVA through a shared identifier"
        )
    }

    private static func compare(
        installedRawVersion: String,
        catalogRawVersion: String
    ) -> MapStatus {
        let installedVersion = FreizeitkarteVersionParser().parse(installedRawVersion)
        guard let catalogVersion = MapVersion(rawValue: catalogRawVersion) else {
            fatalError("Invalid test catalog version: \(catalogRawVersion)")
        }

        let installedMap = InstalledMap(
            name: "Freizeitkarte Lithuania",
            provider: "Freizeitkarte",
            region: "LTU",
            family: "Freizeitkarte_LTU+",
            rawVersion: installedRawVersion,
            version: installedVersion,
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: 344_000_000,
            sourceFile: InstalledMapFile(
                path: "/GARMIN/gmapsupp.img",
                filename: "gmapsupp.img",
                sizeBytes: 344_000_000
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )

        let provider = MapProvider(
            id: "freizeitkarte",
            name: "Freizeitkarte",
            website: nil,
            attribution: nil,
            licenseURL: nil
        )
        let region = MapRegion(
            id: "LTU",
            name: "Lithuania",
            country: "Lithuania"
        )
        let catalogMap = MapPackage(
            id: "freizeitkarte-ltu",
            providerId: "freizeitkarte",
            regionId: "LTU",
            name: "Lithuania",
            version: catalogVersion,
            sizeBytes: 344_000_000,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil
        )

        return MapComparisonEngine().compare(
            installedMaps: [installedMap],
            provider: provider,
            region: region,
            catalogMap: catalogMap
        ).status
    }

    private static func expect(_ condition: Bool, _ message: String) {
        guard condition else {
            fatalError("FAIL: \(message)")
        }

        print("PASS: \(message)")
    }
}

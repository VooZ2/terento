import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct MapInventoryListTests {
    static func main() {
        testFreizeitkarteRegionsAppearInOneList()
        testSelectedCatalogMapIsNotDuplicatedWhenInstalled()
        testCompanionFilesAppearAsOneOtherMap()
        testManifestRecordRestoresManagedOwnership()
        testRemovedMapIsAbsentAfterFreshScan()

        print("PASS: 5 unified map inventory and ownership tests")
    }

    private static func testFreizeitkarteRegionsAppearInOneList() {
        let germany = makeInstalledMap(
            name: "Freizeitkarte Germany",
            provider: "Freizeitkarte",
            region: "DEU",
            path: "/GARMIN/freizeitkarte-germany.img"
        )
        let france = makeInstalledMap(
            name: "Freizeitkarte France",
            provider: "Freizeitkarte",
            region: "FRA",
            path: "/GARMIN/freizeitkarte-france.img"
        )
        let scan = makeScan(
            installedMaps: [germany, france],
            otherMaps: []
        )
        let comparisons = [
            makeComparison(region: "DEU", name: "Germany", installedMap: germany),
            makeComparison(region: "FRA", name: "France", installedMap: france)
        ]

        let list = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: comparisons,
            selectedCatalogPackageID: "freizeitkarte-fra"
        )
        let titles = list.freizeitkarte.map(\.title)

        expect(
            list.freizeitkarte.count == 2
                && titles.contains("France")
                && titles.contains("Germany")
                && list.otherMaps.isEmpty,
            "provider inventory regions use neutral country titles"
        )
    }

    private static func testSelectedCatalogMapIsNotDuplicatedWhenInstalled() {
        let france = makeInstalledMap(
            name: "Freizeitkarte France",
            provider: "Freizeitkarte",
            region: "FRA",
            path: "/GARMIN/BaseCamp-renamed.img"
        )
        let scan = makeScan(installedMaps: [france])
        let comparisons = [makeComparison(region: "FRA", name: "France", installedMap: france)]

        let list = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: comparisons,
            selectedCatalogPackageID: "freizeitkarte-fra"
        )

        expect(
            list.freizeitkarte.count == 1
                && list.freizeitkarte.first?.isSelectedCatalogMap == true
                && list.freizeitkarte.first?.installedFileCount == 1,
            "an installed selected map is represented by one card"
        )
    }

    private static func testCompanionFilesAppearAsOneOtherMap() {
        let main = makeInstalledMap(
            name: "OpenTopoMap Germany",
            provider: nil,
            region: nil,
            path: "/GARMIN/otm-germany.img",
            rawVersion: nil,
            size: 100
        )
        let contours = makeInstalledMap(
            name: "OpenTopoMap Germany",
            provider: nil,
            region: nil,
            path: "/GARMIN/otm-germany-contours.img",
            rawVersion: nil,
            size: 200
        )
        let scan = makeScan(
            installedMaps: [],
            otherMaps: [main, contours]
        )

        let list = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: [],
            selectedCatalogPackageID: "freizeitkarte-fra"
        )

        expect(
            list.otherMaps.count == 1
                && list.otherMaps.first?.installedFileCount == 2
                && list.otherMaps.first?.installedSizeBytes == 300,
            "companion files appear as one read-only other-map entry"
        )
    }

    private static func testManifestRecordRestoresManagedOwnership() {
        let file = InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_fra.img",
            filename: "terento_freizeitkarte_fra.img",
            sizeBytes: 348_684_288,
            itemID: 42
        )
        let metadata = GarminIMGMetadata(
            name: "Freizeitkarte FRA+",
            provider: "Freizeitkarte",
            region: "FRA",
            family: "Freizeitkarte",
            rawVersion: "Release 26.05",
            version: MapVersion(year: 2026, month: 5),
            identifier: nil,
            productId: nil,
            familyId: nil
        )
        let record = MapOwnershipRecord(
            devicePath: file.path,
            filename: file.filename,
            providerId: "freizeitkarte",
            regionId: "FRA",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: file.sizeBytes
        )

        let state = MapOwnershipMatcher().managementState(
            for: file,
            metadata: metadata,
            records: [record]
        )

        expect(
            state == .managedByTerento,
            "manifest-backed France map is shown as managed by Terento"
        )
    }

    private static func testRemovedMapIsAbsentAfterFreshScan() {
        let scan = makeScan(installedMaps: [])
        let comparisons = [
            makeComparison(region: "DEU", name: "Germany", installedMap: nil)
        ]

        let list = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: comparisons,
            selectedCatalogPackageID: nil
        )

        expect(
            list.freizeitkarte.isEmpty && list.otherMaps.isEmpty,
            "a map absent from a fresh device scan is absent from Manage maps"
        )
    }


    private static func makeScan(
        installedMaps: [InstalledMap],
        otherMaps: [InstalledMap] = []
    ) -> MapScanResult {
        MapScanResult(
            files: installedMaps.map(\.sourceFile) + otherMaps.map(\.sourceFile),
            installedMaps: installedMaps,
            otherMaps: otherMaps,
            parsingFailures: 0,
            skippedUnrecognizedProviderFiles: 0
        )
    }

    private static func makeComparison(
        region: String,
        name: String,
        installedMap: InstalledMap?
    ) -> MapComparison {
        let package = MapPackage(
            id: "freizeitkarte-\(region.lowercased())",
            providerId: "freizeitkarte",
            regionId: region,
            name: name,
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 300,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil
        )

        return MapComparison(
            providerName: "Freizeitkarte",
            regionName: name,
            catalogMap: package,
            installedMap: installedMap,
            status: installedMap == nil ? .notInstalled : .upToDate
        )
    }

    private static func makeInstalledMap(
        name: String,
        provider: String?,
        region: String?,
        path: String,
        rawVersion: String? = "Release 26.05",
        size: UInt64 = 300
    ) -> InstalledMap {
        InstalledMap(
            name: name,
            provider: provider,
            region: region,
            family: provider,
            rawVersion: rawVersion,
            version: rawVersion.flatMap { FreizeitkarteVersionParser().parse($0) },
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: size,
            sourceFile: InstalledMapFile(
                path: path,
                filename: URL(fileURLWithPath: path).lastPathComponent,
                sizeBytes: size
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )
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

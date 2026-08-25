import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

/// Diagnostic coverage for the reported stale Freizeitkarte LTU row.
///
/// This test deliberately separates the three layers involved in Manage maps:
/// 1. the device IMG scan;
/// 2. catalog comparison state; and
/// 3. the presentation inventory.
///
/// It does not touch a real Garmin device and does not perform any write or
/// delete operation.
@main
struct LTUStaleDisplayDiagnosticTests {
    static func main() {
        print("LTU stale Manage maps diagnostic")
        testEmptyDeviceScanHasNoLTU()
        testFreshComparisonWithNoLTUHasNoInventoryRow()
        testStaleComparisonAloneIsNotAnInstalledMap()
        testLTUInventoryRequiresARealMatchingIMGObject()
        print("RESULT: domain diagnostic passed; a visible LTU Manage row requires a device-scan LTU object")
    }

    private static func testEmptyDeviceScanHasNoLTU() {
        let scan = GarminMapScanner().scan(
            files: [],
            reader: FixtureReader(prefixes: [:])
        )

        expect(
            scan.installedMaps.isEmpty,
            "empty device file inventory produces no installed LTU map"
        )
    }

    private static func testFreshComparisonWithNoLTUHasNoInventoryRow() {
        let package = makePackage()
        let comparison = MapComparisonEngine().compare(
            installedMaps: [],
            provider: makeProvider(),
            region: makeRegion(),
            catalogMap: package
        )
        let list = MapInventoryListBuilder().build(
            scan: makeScan(installedMaps: []),
            comparisons: [comparison],
            selectedCatalogPackageID: nil
        )

        expect(
            comparison.installedMap == nil
                && comparison.status == .notInstalled
                && list.freizeitkarte.isEmpty,
            "fresh comparison with no LTU scan object removes LTU from the unified inventory"
        )
    }

    private static func testStaleComparisonAloneIsNotAnInstalledMap() {
        let oldLTU = makeInstalledMap(
            name: "Freizeitkarte Lithuania",
            path: "/GARMIN/terento_freizeitkarte_ltu.img"
        )
        let staleComparison = MapComparison(
            providerName: "Freizeitkarte",
            regionName: "Lithuania",
            catalogMap: makePackage(),
            installedMap: oldLTU,
            status: .upToDate
        )
        let list = MapInventoryListBuilder().build(
            scan: makeScan(installedMaps: []),
            comparisons: [staleComparison],
            selectedCatalogPackageID: nil
        )

        guard let entry = list.freizeitkarte.first else {
            expect(false, "stale comparison diagnostic entry is constructed")
            return
        }

        expect(
            entry.title == "Freizeitkarte Lithuania"
                && entry.installedMaps.isEmpty
                && !entry.isInstalled,
            "a stale comparison alone cannot make LTU an installed map"
        )
        print("DIAGNOSTIC CONTROL: stale comparison can leave a raw catalog row, but it has zero scanned device files")
    }

    private static func testLTUInventoryRequiresARealMatchingIMGObject() {
        let file = DeviceFile(
            itemID: 101,
            parentID: 1,
            storageID: 1,
            path: "/GARMIN/gmapsupp.img",
            filename: "gmapsupp.img",
            sizeBytes: 348_684_288,
            isFolder: false
        )
        let scan = GarminMapScanner().scan(
            files: [file],
            reader: FixtureReader(prefixes: [file.itemID: makeLTUIMGPrefix()])
        )

        guard let installed = scan.installedMaps.first else {
            expect(false, "matching LTU IMG is detected by the scanner")
            return
        }

        let list = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: [
                MapComparisonEngine().compare(
                    installedMaps: scan.installedMaps,
                    provider: makeProvider(),
                    region: makeRegion(),
                    catalogMap: makePackage()
                )
            ],
            selectedCatalogPackageID: nil
        )

        expect(
            installed.provider == "Freizeitkarte"
                && installed.region == "LTU"
                && list.freizeitkarte.count == 1
                && list.freizeitkarte.first?.installedMaps.count == 1,
            "a real matching LTU IMG object becomes one installed inventory entry"
        )
        print("DIAGNOSTIC CONTROL: if the real watch produces this object after removal, the remaining LTU is on-device, not only stale UI state")
    }

    private static func makePackage() -> MapPackage {
        MapPackage(
            id: "freizeitkarte-ltu",
            providerId: "freizeitkarte",
            regionId: "LTU",
            name: "Lithuania",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 300,
            sourceURL: nil,
            releaseDate: "2026-05",
            identifier: nil
        )
    }

    private static func makeProvider() -> MapProvider {
        MapProvider(
            id: "freizeitkarte",
            name: "Freizeitkarte",
            website: nil,
            attribution: nil,
            licenseURL: nil
        )
    }

    private static func makeRegion() -> MapRegion {
        MapRegion(id: "LTU", name: "Lithuania", country: "LT")
    }

    private static func makeScan(installedMaps: [InstalledMap]) -> MapScanResult {
        MapScanResult(
            files: installedMaps.map(\.sourceFile),
            installedMaps: installedMaps,
            otherMaps: [],
            parsingFailures: 0,
            skippedNonFreizeitkarteFiles: 0
        )
    }

    private static func makeInstalledMap(name: String, path: String) -> InstalledMap {
        InstalledMap(
            name: name,
            provider: "Freizeitkarte",
            region: "LTU",
            family: "Freizeitkarte_LTU+",
            rawVersion: "Release 26.05",
            version: MapVersion(year: 2026, month: 5),
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: 300,
            sourceFile: InstalledMapFile(
                path: path,
                filename: URL(fileURLWithPath: path).lastPathComponent,
                sizeBytes: 300,
                itemID: 99
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )
    }

    private static func makeLTUIMGPrefix() -> [UInt8] {
        var bytes = Array(repeating: UInt8(0), count: GarminIMGMetadataParser.prefixLength)
        write("DSKIMG", at: 0x10, into: &bytes)
        write("GARMIN", at: 0x41, into: &bytes)
        write("Freizeitkarte_LTU+", at: 0x49, into: &bytes)
        write("Release 26.05", at: 0x65, into: &bytes)
        return bytes
    }

    private static func write(_ value: String, at offset: Int, into bytes: inout [UInt8]) {
        for (index, byte) in value.utf8.enumerated() where offset + index < bytes.count {
            bytes[offset + index] = byte
        }
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

private struct FixtureReader: DeviceFileReader {
    let prefixes: [UInt32: [UInt8]]

    func readFileInventory() throws -> [DeviceFile] {
        []
    }

    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8] {
        Array((prefixes[file.itemID] ?? []).prefix(maxLength))
    }

    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]] {
        Dictionary(uniqueKeysWithValues: files.map { file in
            (file.itemID, Array((prefixes[file.itemID] ?? []).prefix(maxLength)))
        })
    }
}

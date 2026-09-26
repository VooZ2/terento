import Foundation

protocol DeviceFileReader: Sendable {
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
}

private enum Stage5TestError: Error {
    case failed(String)
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else {
        throw Stage5TestError.failed(message)
    }
}

private func version(_ year: Int, _ month: Int) -> MapVersion {
    MapVersion(year: year, month: month)!
}

private func installedMap(
    id: UInt32 = 101,
    path: String = "/GARMIN/freizeitkarte-deu.img",
    filename: String = "freizeitkarte-deu.img",
    sizeBytes: UInt64 = 12,
    version: MapVersion? = version(2026, 5),
    managementState: MapManagementState = .detectedNotManaged
) -> InstalledMap {
    InstalledMap(
        name: "Freizeitkarte DEU+",
        provider: "Freizeitkarte",
        region: "DEU",
        family: "Freizeitkarte",
        rawVersion: version.map { "Release \($0.year - 2000).\(String(format: "%02d", $0.month))" },
        version: version,
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: sizeBytes,
        sourceFile: InstalledMapFile(
            path: path,
            filename: filename,
            sizeBytes: sizeBytes,
            itemID: id
        ),
        metadataStatus: .parsed,
        managementState: managementState
    )
}

private func testInventoryBuilderUsesRealEntries() throws {
    let map = installedMap()
    let entry = MapInventoryEntry(
        key: "freizeitkarte:identity:freizeitkarte:DEU",
        title: "Freizeitkarte Germany",
        catalogPackage: nil,
        comparison: nil,
        installedMaps: [map],
        isSelectedCatalogMap: false
    )
    let result = MapLifecycleInventoryBuilder().build(
        from: UnifiedMapInventory(providerGroups: [MapInventoryProviderGroup(
            id: "freizeitkarte", providerId: "freizeitkarte", title: "Freizeitkarte", entries: [entry]
        )], otherMaps: [])
    )

    let items = result.providerGroups.first {
        MapIdentity.normalizeProvider($0.providerId) == "freizeitkarte"
    }?.items ?? []
    try require(items.count == 1, "inventory should contain one Freizeitkarte item")
    try require(items[0].hasExactObjectIdentity, "live inventory must retain the MTP object handle")
    try require(items[0].classification == .externalRecognized, "unmanaged parsed map should be external-recognized")
}

private func testInventoryBuilderUsesCanonicalPackageIdentity() throws {
    let map = InstalledMap(
        name: "Freizeitkarte Balearics",
        provider: "Freizeitkarte",
        region: "BALEARICS",
        family: "Freizeitkarte",
        rawVersion: "Release 26.05",
        version: version(2026, 5),
        identifier: "BALEARICS",
        productId: nil,
        familyId: nil,
        sizeBytes: 41_537_536,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_balearics.img",
            filename: "terento_freizeitkarte_balearics.img",
            sizeBytes: 41_537_536,
            itemID: 202
        ),
        metadataStatus: .parsed,
        managementState: .managedByTerento
    )
    let package = MapPackage(
        id: "freizeitkarte-esp-balearics",
        providerId: "freizeitkarte",
        regionId: "AZORES",
        name: "Balearics",
        version: version(2026, 5),
        sizeBytes: 1,
        sourceURL: nil,
        releaseDate: nil,
        identifier: "BALEARICS",
        installSizeBytes: map.sizeBytes
    )
    let entry = MapInventoryEntry(
        key: "freizeitkarte:identity:freizeitkarte:BALEARICS",
        title: "Freizeitkarte Balearics",
        catalogPackage: package,
        comparison: nil,
        installedMaps: [map],
        isSelectedCatalogMap: false
    )

    let result = MapLifecycleInventoryBuilder().build(
        from: UnifiedMapInventory(providerGroups: [MapInventoryProviderGroup(
            id: "freizeitkarte", providerId: "freizeitkarte", title: "Freizeitkarte", entries: [entry]
        )], otherMaps: [])
    )

    let items = result.providerGroups.first {
        MapIdentity.normalizeProvider($0.providerId) == "freizeitkarte"
    }?.items ?? []
    try require(
        items.first?.region == "BALEARICS",
        "lifecycle identity must use the concrete package identifier, not the shared catalog region"
    )
}

private func testFailedInstallRecoveryAcceptsProviderAlias() throws {
    let record = TerentoFailedInstallRecoveryRecord(
        deviceKey: "fenix8-local",
        packageID: "opentopomap-lithuania",
        providerId: "opentopomap",
        regionId: "LITHUANIA",
        version: version(2026, 5),
        devicePath: "/GARMIN/terento_opentopomap_lithuania.img",
        filename: "terento_opentopomap_lithuania.img",
        sizeBytes: 123_456,
        sha256: "recovery-hash",
        createdAt: Date(timeIntervalSince1970: 0)
    )

    try require(
        record.matches(
            deviceKey: "fenix8-local",
            path: record.devicePath,
            filename: record.filename,
            sizeBytes: record.sizeBytes,
            providerId: "OpenTopoMap",
            regionId: "LTU",
            version: record.version
        ),
        "failed-install recovery accepts the reviewed OpenTopoMap alias"
    )
}

@main
struct Stage5MapLifecycleTests {
    static func main() {
        let tests: [(String, () throws -> Void)] = [
            ("inventory uses exact object identity", testInventoryBuilderUsesRealEntries),
            ("inventory uses canonical package identity", testInventoryBuilderUsesCanonicalPackageIdentity),
            ("failed-install recovery accepts provider aliases", testFailedInstallRecoveryAcceptsProviderAlias)
        ]

        do {
            for (name, test) in tests {
                try test()
                print("PASS: \(name)")
            }
            print("PASS: \(tests.count) Stage 5 map lifecycle tests")
        } catch {
            print("FAIL: \(error)")
            exit(1)
        }
    }
}

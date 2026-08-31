import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct Stage3GenericLifecycleTests {
    static func main() {
        testRequiredArtifactIsSelectedByDefault()
        testOptionalContoursJoinTheSharedStoragePlanWhenSelected()
        testMissingOptionalArtifactDoesNotBlockMainMap()
        testProviderGroupsAreGenericAndAlphabetical()
        testUncataloguedProviderMapIsStillGroupedByProvider()
        testCustomManagedMapStaysOutsideProviderGroups()
        testManagedCustomMapDoesNotMergeWithExternalSameName()
        testOpenTopoMapHeaderRestoresManagedCustomOwnership()
        testCustomOwnershipSurvivesProviderNeutralRescan()
        testLifecycleBuilderPreservesProviderAndCustomSources()
        print("PASS: 11 Stage 3 generic lifecycle tests")
    }

    private static func testRequiredArtifactIsSelectedByDefault() {
        let package = makePackage(
            provider: "OpenTopoMap",
            name: "Lithuania",
            mainSize: 100,
            contoursSize: 40
        )
        let plan = package.defaultArtifactPlan

        expect(
            plan.selectedArtifactIDs == ["otm-ltu-main"]
                && plan.installSizeBytes == 100,
            "the main artifact is selected by default and optional contours are excluded"
        )
    }

    private static func testOptionalContoursJoinTheSharedStoragePlanWhenSelected() {
        let package = makePackage(
            provider: "OpenTopoMap",
            name: "Lithuania",
            mainSize: 100,
            contoursSize: 40
        )
        let plan = package.artifactPlan(
            includingOptionalArtifactIDs: ["otm-ltu-contours"]
        )

        expect(
            plan.selectedArtifactIDs == ["otm-ltu-main", "otm-ltu-contours"]
                && plan.installSizeBytes == 140,
            "selected main and contours artifacts share one combined storage plan"
        )
    }

    private static func testMissingOptionalArtifactDoesNotBlockMainMap() {
        let package = makePackage(
            provider: "OpenTopoMap",
            name: "Lithuania",
            mainSize: 100,
            contoursSize: nil
        )
        let mainPlan = package.defaultArtifactPlan
        let contoursPlan = package.artifactPlan(
            includingOptionalArtifactIDs: ["otm-ltu-contours"]
        )

        expect(
            mainPlan.installSizeBytes == 100
                && contoursPlan.installSizeBytes == nil,
            "an unavailable optional contours size does not block the main map"
        )
    }

    private static func testProviderGroupsAreGenericAndAlphabetical() {
        let freizeitkarteMap = makeInstalledMap(
            name: "Freizeitkarte Lithuania",
            provider: "Freizeitkarte",
            region: "LTU",
            path: "/GARMIN/freizeitkarte-lithuania.img"
        )
        let openTopoMap = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: "OpenTopoMap",
            region: "LTU",
            path: "/GARMIN/opentopomap-lithuania.img"
        )
        let comparisons = [
            makeComparison(
                provider: "OpenTopoMap",
                region: "LTU",
                name: "Lithuania",
                installedMap: openTopoMap
            ),
            makeComparison(
                provider: "Freizeitkarte",
                region: "LTU",
                name: "Lithuania",
                installedMap: freizeitkarteMap
            )
        ]
        let scan = makeScan(installedMaps: [freizeitkarteMap, openTopoMap])
        let inventory = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: comparisons
        )

        expect(
            inventory.providerGroups.map(\.title) == ["Freizeitkarte", "OpenTopoMap"]
                && inventory.allEntries.count == 2
                && inventory.freizeitkarte.count == 1,
            "provider inventory groups are source-neutral and alphabetically ordered"
        )
    }

    private static func testUncataloguedProviderMapIsStillGroupedByProvider() {
        let map = makeInstalledMap(
            name: "OpenTopoMap Alps",
            provider: "OpenTopoMap",
            region: "ALPS",
            path: "/GARMIN/opentopomap-alps.img"
        )
        let inventory = MapInventoryListBuilder().build(
            scan: makeScan(installedMaps: [], otherMaps: [map]),
            comparisons: []
        )

        expect(
            inventory.providerGroups.count == 1
                && inventory.providerGroups.first?.title == "OpenTopoMap"
                && inventory.otherMaps.isEmpty,
            "a provider-tagged map remains grouped even without a catalog row"
        )
    }

    private static func testCustomManagedMapStaysOutsideProviderGroups() {
        let map = makeInstalledMap(
            name: "Custom map",
            provider: nil,
            region: nil,
            path: "/GARMIN/terento_custom_img_abc.img",
            managementState: .managedByTerento
        )
        let inventory = MapInventoryListBuilder().build(
            scan: makeScan(installedMaps: [], otherMaps: [map]),
            comparisons: []
        )

        expect(
            inventory.providerGroups.isEmpty
                && inventory.otherMaps.count == 1
                && inventory.otherMaps.first?.sourceKind == .custom,
            "a managed custom map stays outside provider groups"
        )
        expect(
            inventory.otherMaps.first?.title == "terento_custom_img_abc.img",
            "a generic custom map falls back to its IMG filename"
        )
    }

    private static func testManagedCustomMapDoesNotMergeWithExternalSameName() {
        let managed = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: nil,
            region: nil,
            path: "/GARMIN/terento_custom_img_abc.img",
            managementState: .managedByTerento
        )
        let external = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: nil,
            region: nil,
            path: "/GARMIN/otm-lithuania-contours.img",
            managementState: .detectedNotManaged
        )

        let inventory = MapInventoryListBuilder().build(
            scan: makeScan(installedMaps: [], otherMaps: [external, managed]),
            comparisons: []
        )

        let custom = inventory.otherMaps.first { $0.sourceKind == .custom }
        let externalEntry = inventory.otherMaps.first { $0.sourceKind == .provider }
        expect(
            inventory.otherMaps.count == 2
                && custom?.title == "OpenTopoMap Lithuania"
                && custom?.installedFileCount == 1
                && custom?.managementState == .managedByTerento
                && externalEntry?.title == "OpenTopoMap Lithuania"
                && externalEntry?.managementState == .detectedNotManaged,
            "a managed custom IMG does not merge with an external map sharing its header name"
        )
    }

    private static func testOpenTopoMapHeaderRestoresManagedCustomOwnership() {
        let path = "/GARMIN/terento_custom_img_abc.img"
        let file = DeviceFile(
            itemID: 78,
            parentID: 1,
            storageID: 1,
            path: path,
            filename: "terento_custom_img_abc.img",
            sizeBytes: 8192,
            isFolder: false
        )
        let record = MapOwnershipRecord(
            devicePath: path,
            filename: file.filename,
            providerId: "custom",
            regionId: "img_abc",
            version: version(),
            sizeBytes: file.sizeBytes
        )
        let scan = GarminMapScanner().scan(
            files: [file],
            reader: FixtureReader(files: [file], prefix: makeOpenTopoMapIMGData()),
            ownershipRecords: [record],
            recognizedProviderIDs: ["freizeitkarte"]
        )
        let inventory = MapInventoryListBuilder().build(
            scan: scan,
            comparisons: []
        )

        expect(
            scan.otherMaps.first?.name == "OpenTopoMap Lithuani"
                && scan.otherMaps.first?.provider == nil
                && inventory.otherMaps.first?.title == "OpenTopoMap Lithuani"
                && inventory.otherMaps.first?.sourceKind == .custom
                && inventory.otherMaps.first?.managementState == .managedByTerento,
            "an OpenTopoMap IMG header remains a managed Custom map when the exact manifest matches"
        )
    }

    private static func testCustomOwnershipSurvivesProviderNeutralRescan() {
        let path = "/GARMIN/terento_custom_img_abc.img"
        let file = DeviceFile(
            itemID: 77,
            parentID: 1,
            storageID: 1,
            path: path,
            filename: "terento_custom_img_abc.img",
            sizeBytes: 8192,
            isFolder: false
        )
        let record = MapOwnershipRecord(
            devicePath: path,
            filename: file.filename,
            providerId: "custom",
            regionId: "img_abc",
            version: version(),
            sizeBytes: file.sizeBytes
        )
        let scan = GarminMapScanner().scan(
            files: [file],
            reader: FixtureReader(files: [file], prefix: makeIMGData()),
            ownershipRecords: [record],
            recognizedProviderIDs: ["freizeitkarte"]
        )

        expect(
            scan.otherMaps.first?.managementState == .managedByTerento,
            "the provider-neutral rescan restores exact custom ownership"
        )
    }

    private static func testLifecycleBuilderPreservesProviderAndCustomSources() {
        let providerMap = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: "OpenTopoMap",
            region: "LTU",
            path: "/GARMIN/opentopomap-lithuania.img"
        )
        let customMap = makeInstalledMap(
            name: "Custom map",
            provider: nil,
            region: nil,
            path: "/GARMIN/terento_custom_img_abc.img",
            managementState: .managedByTerento
        )
        let providerEntry = MapInventoryEntry(
            key: "provider-opentopomap-ltu",
            title: "OpenTopoMap Lithuania",
            catalogPackage: makePackage(
                provider: "OpenTopoMap",
                name: "Lithuania",
                mainSize: providerMap.sizeBytes,
                contoursSize: nil
            ),
            comparison: nil,
            installedMaps: [providerMap],
            isSelectedCatalogMap: false
        )
        let customEntry = MapInventoryEntry(
            key: "other-custom",
            title: "Custom map",
            catalogPackage: nil,
            comparison: nil,
            installedMaps: [customMap],
            isSelectedCatalogMap: false
        )
        let inventory = UnifiedMapInventory(
            providerGroups: [
                MapInventoryProviderGroup(
                    id: "opentopomap",
                    providerId: "opentopomap",
                    title: "OpenTopoMap",
                    entries: [providerEntry]
                )
            ],
            otherMaps: [customEntry]
        )
        let lifecycle = MapLifecycleInventoryBuilder().build(from: inventory)

        expect(
            lifecycle.providerGroups.count == 1
                && lifecycle.providerGroups.first?.title == "OpenTopoMap"
                && lifecycle.providerGroups.first?.items.first?.sourceKind == .provider
                && lifecycle.otherMaps.first?.sourceKind == .custom,
            "the lifecycle model keeps provider and custom sources explicit"
        )
    }

    private static func makePackage(
        provider: String,
        name: String,
        mainSize: UInt64,
        contoursSize: UInt64?
    ) -> MapPackage {
        let packageID = provider == "OpenTopoMap" ? "otm-ltu" : "fzk-ltu"
        var artifacts = [
            MapArtifact(
                id: packageID + "-main",
                kind: .main,
                required: true,
                providerId: provider,
                providerRegionId: "LTU",
                canonicalRegionId: "LTU",
                version: version(),
                sourceURL: URL(string: "https://example.com/main.zip"),
                sizeBytes: mainSize
            )
        ]
        if let contoursSize {
            artifacts.append(
                MapArtifact(
                    id: packageID + "-contours",
                    kind: .contours,
                    required: false,
                    providerId: provider,
                    providerRegionId: "LTU",
                    canonicalRegionId: "LTU",
                    version: version(),
                    sourceURL: URL(string: "https://example.com/contours.zip"),
                    sizeBytes: contoursSize
                )
            )
        } else {
            artifacts.append(
                MapArtifact(
                    id: packageID + "-contours",
                    kind: .contours,
                    required: false,
                    providerId: provider,
                    providerRegionId: "LTU",
                    canonicalRegionId: "LTU",
                    version: version(),
                    sourceURL: nil,
                    sizeBytes: nil,
                    validationState: .unavailable
                )
            )
        }

        return MapPackage(
            id: packageID,
            providerId: provider,
            regionId: "LTU",
            name: name,
            version: version(),
            sizeBytes: mainSize,
            sourceURL: URL(string: "https://example.com/package.zip"),
            releaseDate: nil,
            identifier: "LTU",
            installSizeBytes: mainSize,
            artifacts: artifacts
        )
    }

    private static func makeComparison(
        provider: String,
        region: String,
        name: String,
        installedMap: InstalledMap
    ) -> MapComparison {
        MapComparison(
            providerName: provider,
            regionName: name,
            catalogMap: MapPackage(
                id: provider.lowercased() + "-" + region.lowercased(),
                providerId: provider,
                regionId: region,
                name: name,
                version: version(),
                sizeBytes: installedMap.sizeBytes,
                sourceURL: nil,
                releaseDate: nil,
                identifier: region,
                installSizeBytes: installedMap.sizeBytes
            ),
            installedMap: installedMap,
            status: .upToDate
        )
    }

    private static func makeScan(
        installedMaps: [InstalledMap],
        otherMaps: [InstalledMap] = []
    ) -> MapScanResult {
        MapScanResult(
            files: (installedMaps + otherMaps).map(\.sourceFile),
            installedMaps: installedMaps,
            otherMaps: otherMaps,
            parsingFailures: 0,
            skippedNonFreizeitkarteFiles: 0
        )
    }

    private static func makeInstalledMap(
        name: String,
        provider: String?,
        region: String?,
        path: String,
        managementState: MapManagementState = .detectedNotManaged
    ) -> InstalledMap {
        InstalledMap(
            name: name,
            provider: provider,
            region: region,
            family: provider,
            rawVersion: "Release 26.05",
            version: version(),
            identifier: region,
            productId: nil,
            familyId: nil,
            sizeBytes: 300,
            sourceFile: InstalledMapFile(
                path: path,
                filename: URL(fileURLWithPath: path).lastPathComponent,
                sizeBytes: 300,
                itemID: UInt32(abs(path.hashValue % 10_000) + 1)
            ),
            metadataStatus: .parsed,
            managementState: managementState
        )
    }

    private static func version() -> MapVersion {
        MapVersion(year: 2026, month: 5)!
    }

    private static func makeIMGData() -> [UInt8] {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        for (offset, byte) in Array("DSKIMG".utf8).enumerated() {
            bytes[0x10 + offset] = byte
        }
        for (offset, byte) in Array("GARMIN".utf8).enumerated() {
            bytes[0x41 + offset] = byte
        }
        for (offset, byte) in Array("USER MAP".utf8).enumerated() {
            bytes[0x49 + offset] = byte
        }
        return bytes
    }

    private static func makeOpenTopoMapIMGData() -> [UInt8] {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        for (offset, byte) in Array("DSKIMG".utf8).enumerated() {
            bytes[0x10 + offset] = byte
        }
        for (offset, byte) in Array("GARMIN".utf8).enumerated() {
            bytes[0x41 + offset] = byte
        }
        for (offset, byte) in Array("OpenTopoMap Lithuania".utf8).enumerated() {
            bytes[0x49 + offset] = byte
        }
        return bytes
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
    let files: [DeviceFile]
    let prefix: [UInt8]

    func readFileInventory() throws -> [DeviceFile] {
        files
    }

    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8] {
        Array(prefix.prefix(maxLength))
    }

    func readFilePrefixes(
        for files: [DeviceFile],
        maxLength: Int
    ) throws -> [UInt32: [UInt8]] {
        Dictionary(uniqueKeysWithValues: files.map {
            ($0.itemID, Array(prefix.prefix(maxLength)))
        })
    }
}

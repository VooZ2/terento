import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]]
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
        testManagedContoursUseExactManagedFilenameIdentity()
        testManagedPackageComponentsShareOneLifecycleRow()
        testOptionalContourFailureIsTypedAsPackageWarning()
        testVersionlessContourLifecycleMatch()
        testGarminImagesAreListedReadOnlyAndNeverRead()
        testGarminMapsSummaryRow()
        testManageListCountIncludesGarminRow()
        print("PASS: 18 Stage 3 generic lifecycle tests")
    }

    /// Garmin images come from the file listing only: no prefix read, kept in
    /// `garminMaps`, never in `otherMaps` or the lifecycle inventory.
    private static func testGarminImagesAreListedReadOnlyAndNeverRead() {
        let garminPaths = [
            "/GARMIN/gmapbmap.img", "/GARMIN/gmapdem.img", "/GARMIN/gmaptz.img", "/GARMIN/gmap3d.img",
            "/GARMIN/gmappmap.img", "/GARMIN/gmapprom.img", "/GARMIN/gmaprgn.img",
            "/GARMIN/D1234567A.img", "/GARMIN/MAP/d0099000.img"
        ]
        let communityPaths = ["/GARMIN/gmapsupp.img", "/GARMIN/custom.img"]
        let files = (garminPaths + communityPaths).enumerated().map { index, path in
            DeviceFile(itemID: UInt32(500 + index), parentID: 1, storageID: 1, path: path,
                filename: URL(fileURLWithPath: path).lastPathComponent,
                sizeBytes: UInt64(1_000_000 * (index + 1)), isFolder: false)
        }
        let reader = RecordingReader(files: files, prefix: makeIMGData())
        let scan = GarminMapScanner().scan(files: files, reader: reader, recognizedProviderIDs: ["freizeitkarte"])
        let garmin = Set(garminPaths)

        // (a) Garmin images land in garminMaps only.
        expect(Set(scan.garminMaps.map(\.path)) == garmin && scan.garminMaps.count == garminPaths.count,
               "D*.img and gmap*.img images are listed in garminMaps")
        expect(!(scan.otherMaps + scan.installedMaps).contains { garmin.contains($0.sourceFile.path) }
                && !scan.files.contains { garmin.contains($0.path) },
               "Garmin images never join otherMaps, installedMaps or inspected files")
        expect(scan.garminMaps.allSatisfy { map in
            files.first { $0.path == map.path }.map { $0.sizeBytes == map.sizeBytes && $0.filename == map.filename } == true
        }, "Garmin rows carry the listed filename and size")
        expect(scan.skippedUnrecognizedProviderFiles == garminPaths.count + scan.otherMaps.count,
               "the skipped unrecognized/system count is unchanged")

        // (b) Their content is never read, not even a prefix.
        expect(reader.requestedPaths.isDisjoint(with: garmin),
               "no prefix read reaches a Garmin image")
        expect(reader.requestedPaths == Set(communityPaths),
               "community images are still read for classification")

        // (c) No lifecycle item, so no Remove or Update can target them.
        let lifecycle = MapLifecycleInventoryBuilder().build(
            from: MapInventoryListBuilder().build(scan: scan, comparisons: [])
        )
        expect(!lifecycle.allItems.contains { item in item.installedMaps.contains { garmin.contains($0.sourceFile.path) } }
                && scan.garminMaps.allSatisfy { lifecycle.item(id: $0.id) == nil },
               "Garmin images have no lifecycle item and no Remove action")

        // (d) gmapsupp.img keeps content classification.
        expect(scan.files.contains { $0.path == "/GARMIN/gmapsupp.img" }
                && scan.otherMaps.contains { $0.sourceFile.path == "/GARMIN/gmapsupp.img" }
                && !scan.garminMaps.contains { $0.filename == "gmapsupp.img" },
               "gmapsupp.img stays in content classification")
    }

    private static func testGarminMapsSummaryRow() {
        let maps = [
            GarminSystemMap(path: "/GARMIN/gmapbmap.img", filename: "gmapbmap.img", sizeBytes: 2_000_000_000),
            GarminSystemMap(path: "/GARMIN/gmaptz.img", filename: "gmaptz.img", sizeBytes: 150_000_000),
            GarminSystemMap(path: "/GARMIN/D1234567A.img", filename: "D1234567A.img", sizeBytes: 50_000_000)
        ]
        let summary = GarminMapsSummary(maps)
        let size = ByteCountFormatter.string(fromByteCount: 2_200_000_000, countStyle: .decimal)
        expect(summary?.fileCount == 3 && summary?.totalSizeBytes == 2_200_000_000
                && summary?.detail == "Preinstalled · 3 files · \(size)"
                && GarminMapsSummary.title == "Garmin maps",
               "one Garmin maps row sums every listed file in the Manage size format")
        expect(GarminMapsSummary([maps[0]])?.detail.contains("· 1 file ·") == true
                && GarminMapsSummary([GarminSystemMap(path: "/GARMIN/gmapdem.img", filename: "gmapdem.img", sizeBytes: 0)])?.detail
                    == "Preinstalled · 1 file"
                && GarminMapsSummary([]) == nil,
               "one file is singular, a zero size is left out, and no files means no row")
        expect(GarminMapsSummary([GarminSystemMap(path: "/a", filename: "a.img", sizeBytes: .max),
                                  GarminSystemMap(path: "/b", filename: "b.img", sizeBytes: 1)])?.totalSizeBytes == .max,
               "the total size saturates instead of overflowing")
        expect(GarminMapsSummary.visible(maps, query: "") == summary
                && GarminMapsSummary.visible(maps, query: "garmin") == summary
                && GarminMapsSummary.visible(maps, query: "preinstalled") == summary
                && GarminMapsSummary.visible(maps, query: "lithuania") == nil
                && GarminMapsSummary.visible([], query: "") == nil,
               "Manage search matches the Garmin maps row by its visible words")
        expect(GarminMapsSummary.visible(maps, query: "", providerID: "openTopoMap") == nil,
               "a provider filter hides the Garmin maps row")
    }

    private static func testManageListCountIncludesGarminRow() {
        let maps = ["gmapbmap.img", "gmapdem.img", "D1234567A.img"].map {
            GarminSystemMap(path: "/GARMIN/" + $0, filename: $0, sizeBytes: 1)
        }
        func count(_ lifecycleRows: Int, _ query: String, _ provider: String = "") -> Int {
            GarminMapsSummary.manageListCount(lifecycleItemCount: lifecycleRows,
                visibleGarminSummary: GarminMapsSummary.visible(maps, query: query, providerID: provider))
        }
        expect(count(2, "") == 3 && count(0, "garmin") == 1 && count(0, "lithuania") == 0
                && count(2, "", "openTopoMap") == 2,
               "the Manage map count includes the one Garmin row when search and filters leave it visible")
    }

    private static func testVersionlessContourLifecycleMatch() {
        let release = MapVersion(year: 2026, month: 5)!
        func matches(_ version: MapVersion?, _ provider: String = "OpenTopoMap",
                     _ filename: String = "terento_opentopomap_lithuania_contours.img",
                     _ kind: MapArtifactKind? = .contours) -> Bool {
            MapOwnershipMatcher.lifecycleVersionMatches(scanned: version, recorded: release,
                provider: provider, filename: filename, artifactKind: kind)
        }
        expect(matches(nil), "recorded versionless OTM contours keep lifecycle integrity after reconnect")
        expect(matches(release), "matching dated components remain manageable")
        expect(!matches(MapVersion(year: 2026, month: 4)!), "a conflicting version stays blocked")
        expect(!matches(nil, "Freizeitkarte"), "missing versions on other providers stay blocked")
        expect(!matches(nil, "OpenTopoMap", "terento_opentopomap_lithuania.img", .main), "versionless main maps stay blocked")
        expect(!matches(nil, "OpenTopoMap", "unknown_contours.img"), "unknown contour filenames stay blocked")
        expect(!matches(nil, "OpenTopoMap", "terento_opentopomap_lithuania_contours.img", nil), "legacy records without component proof stay blocked")
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

    private static func testManagedContoursUseExactManagedFilenameIdentity() {
        let managed = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: "opentopomap",
            region: "LTU",
            path: "/GARMIN/terento_opentopomap_ltu_contours.img",
            managementState: .managedByTerento
        )
        let unmanaged = makeInstalledMap(
            name: "OpenTopoMap Lithuania contours",
            provider: "opentopomap",
            region: "LTU",
            path: "/GARMIN/provider-contours.img",
            managementState: .detectedNotManaged
        )
        let managedItem = MapLifecycleItem(
            id: "managed-contours",
            title: "Lithuania",
            provider: "opentopomap",
            region: "LTU",
            version: managed.version,
            rawVersion: managed.rawVersion,
            sizeBytes: managed.sizeBytes,
            installedMaps: [managed],
            classification: .terentoManaged
        )
        let unmanagedItem = MapLifecycleItem(
            id: "unmanaged-contours",
            title: "Lithuania",
            provider: "opentopomap",
            region: "LTU",
            version: unmanaged.version,
            rawVersion: unmanaged.rawVersion,
            sizeBytes: unmanaged.sizeBytes,
            installedMaps: [unmanaged],
            classification: .externalRecognized
        )
        expect(
            managedItem.manageMetadataLabel.contains("Contours included")
                && !unmanagedItem.manageMetadataLabel.contains("Contours included"),
            "managed contours use exact managed filename identity"
        )
    }

    private static func testOptionalContourFailureIsTypedAsPackageWarning() {
        let outcome = MapPackageInstallationOutcome(
            packageID: "opentopomap-lithuania",
            status: .completedWithWarnings,
            components: [
                MapInstallationComponentOutcome(
                    artifactID: "opentopomap-lithuania-main",
                    artifactKind: .main,
                    succeeded: true,
                    failure: nil
                ),
                MapInstallationComponentOutcome(
                    artifactID: "opentopomap-lithuania-contours",
                    artifactKind: .contours,
                    succeeded: false,
                    failure: .deviceDisconnected
                )
            ]
        )
        expect(
            outcome.hasWarnings
                && !outcome.isComplete
                && outcome.failedComponent?.artifactKind == .contours,
            "optional contour failure is typed as a package warning"
        )
    }

    private static func testManagedPackageComponentsShareOneLifecycleRow() {
        let main = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: "opentopomap",
            region: "LTU",
            path: "/GARMIN/terento_opentopomap_ltu.img",
            managementState: .managedByTerento,
            managedPackageID: "otm-ltu",
            managedArtifactKind: .main
        )
        let contours = makeInstalledMap(
            name: "OpenTopoMap Lithuania",
            provider: "opentopomap",
            region: "LTU",
            path: "/GARMIN/terento_opentopomap_ltu_contours.img",
            managementState: .managedByTerento,
            managedPackageID: "otm-ltu",
            managedArtifactKind: .contours
        )
        let inventory = MapInventoryListBuilder().build(
            scan: makeScan(installedMaps: [main, contours]),
            comparisons: []
        )
        expect(
            inventory.providerGroups.first?.entries.count == 1
                && inventory.providerGroups.first?.entries.first?.installedFileCount == 2,
            "managed package components share one lifecycle row"
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
                && inventory.providerGroups.first {
                    MapIdentity.normalizeProvider($0.providerId) == "freizeitkarte"
                }?.entries.count == 1,
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
            scan.otherMaps.first?.name == "OpenTopoMap Lithuania"
                && scan.otherMaps.first?.provider == nil
                && inventory.otherMaps.first?.title == "OpenTopoMap Lithuania"
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
            skippedUnrecognizedProviderFiles: 0
        )
    }

    private static func makeInstalledMap(
        name: String,
        provider: String?,
        region: String?,
        path: String,
        managementState: MapManagementState = .detectedNotManaged,
        managedPackageID: String? = nil,
        managedArtifactKind: MapArtifactKind? = nil
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
            managementState: managementState,
            managedPackageID: managedPackageID,
            managedArtifactKind: managedArtifactKind
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
    ) throws -> [DeviceFileIdentity: [UInt8]] {
        Dictionary(uniqueKeysWithValues: files.map {
            ($0.stableIdentity, Array(prefix.prefix(maxLength)))
        })
    }
}

/// Records every path whose prefix the scanner asks for.
private final class RecordingReader: DeviceFileReader, @unchecked Sendable {
    private let files: [DeviceFile]
    private let prefix: [UInt8]
    private let lock = NSLock()
    private var paths: Set<String> = []

    init(files: [DeviceFile], prefix: [UInt8]) {
        self.files = files
        self.prefix = prefix
    }

    var requestedPaths: Set<String> {
        lock.lock(); defer { lock.unlock() }
        return paths
    }

    func readFileInventory() throws -> [DeviceFile] {
        files
    }

    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8] {
        lock.lock(); paths.insert(file.path); lock.unlock()
        return Array(prefix.prefix(maxLength))
    }

    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [DeviceFileIdentity: [UInt8]] {
        lock.lock(); paths.formUnion(files.map(\.path)); lock.unlock()
        return Dictionary(uniqueKeysWithValues: files.map { ($0.stableIdentity, Array(prefix.prefix(maxLength))) })
    }
}

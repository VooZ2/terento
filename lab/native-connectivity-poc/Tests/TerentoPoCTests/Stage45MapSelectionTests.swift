import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct Stage45MapSelectionTests {
    static func main() {
        testCatalogRegionsProduceOneCanonicalList()
        testMacRegionRecommendsLithuania()
        testUpToDateMapIsNotActionable()
        testNewMapProducesReadyPlan()
        testStorageUsesInstallSizeNotDownloadSize()
        testMultipleNewMapsUseCombinedStorage()
        testUpdateIsRepresentedButDoesNotEnterWriteFlow()
        testUnknownMapIsNotSelectable()
        testInsufficientStorageBlocksPlan()
        testUnknownInstallSizeDoesNotPassStorageGate()
        testFormalCountryNamesArePresentationOnly()
        testRegionalVariantsRemainDistinct()
        testInstalledAndAvailableListsAreSeparated()
        testAvailableSearchUsesDisplayAndRegionNames()
        testSelectionSurvivesFilteredPresentation()
        testInstalledPresentationUsesRecognizedInventoryOwnership()
        testStorageBarProjectionIsBoundedAndSegmented()
        testInstallReviewAvailabilityMatchesRealState()
        testSelectedMapDividerPolicy()
        testInstallationFlowPresentation()

        print("PASS: 20 Stage 4.5 map selection tests")
    }

    private static func testCatalogRegionsProduceOneCanonicalList() {
        let firstLithuania = makeComparison(region: "LTU", name: "Lithuania", status: .notInstalled)
        let duplicateLithuania = makeComparison(
            id: "freizeitkarte-ltu-duplicate",
            region: "LTU",
            name: "Lithuania",
            status: .notInstalled
        )
        let latvia = makeComparison(region: "LVA", name: "Latvia", status: .notInstalled)

        let items = MapSelectionPlanner().items(
            comparisons: [firstLithuania, duplicateLithuania, latvia],
            preflightStatuses: [
                firstLithuania.id: .readyNewInstall,
                duplicateLithuania.id: .readyNewInstall,
                latvia.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        expect(
            items.count == 2
                && Set(items.map(\.comparison.catalogMap.regionId)) == ["LTU", "LVA"],
            "catalog and installed data produce one canonical row per region"
        )
    }

    private static func testMacRegionRecommendsLithuania() {
        let lithuania = makeComparison(region: "LTU", name: "Lithuania", status: .notInstalled)
        let latvia = makeComparison(region: "LVA", name: "Latvia", status: .notInstalled)
        let items = MapSelectionPlanner().items(
            comparisons: [lithuania, latvia],
            preflightStatuses: [
                lithuania.id: .readyNewInstall,
                latvia.id: .readyNewInstall
            ],
            recommendedRegionID: MapRegionRecommendation.regionID(
                systemRegionCode: "LT",
                comparisons: [lithuania, latvia]
            )
        )

        expect(
            items.first?.comparison.catalogMap.regionId == "LTU"
                && items.first?.isRecommended == true,
            "the Mac locale recommends the matching catalog region"
        )
    }

    private static func testUpToDateMapIsNotActionable() {
        let comparison = makeComparison(
            region: "LTU",
            name: "Lithuania",
            installedMap: makeInstalledMap(region: "LTU"),
            status: .upToDate
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyWithExistingMapConflict],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            items.first?.isSelectable == false
                && plan.status == .noSelection
                && plan.canContinue == false,
            "an up-to-date installed map is a success state, not an install action"
        )
    }

    private static func testNewMapProducesReadyPlan() {
        let comparison = makeComparison(region: "LVA", name: "Latvia", status: .notInstalled)
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            plan.status == .ready
                && plan.canContinue
                && plan.installItems.count == 1
                && plan.storagePlan.selectedMapBytes == comparison.catalogMap.sizeBytes,
            "a new map with enough space produces a ready installation plan"
        )
    }

    private static func testMultipleNewMapsUseCombinedStorage() {
        let lithuania = makeComparison(region: "LTU", name: "Lithuania", status: .notInstalled, size: 300)
        let latvia = makeComparison(region: "LVA", name: "Latvia", status: .notInstalled, size: 200)
        let items = MapSelectionPlanner().items(
            comparisons: [lithuania, latvia],
            preflightStatuses: [
                lithuania.id: .readyNewInstall,
                latvia.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [lithuania.id, latvia.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            plan.installItems.count == 2
                && plan.storagePlan.selectedMapBytes == 500
                && plan.canContinue,
            "multiple selected maps use one combined conservative storage plan"
        )
    }

    private static func testStorageUsesInstallSizeNotDownloadSize() {
        let comparison = makeComparison(
            region: "LTU",
            name: "Lithuania",
            status: .notInstalled,
            size: 900,
            installSize: 300
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            plan.storagePlan.selectedMapBytes == 300,
            "storage planning uses final IMG install bytes, not ZIP download bytes"
        )
    }

    private static func testUpdateIsRepresentedButDoesNotEnterWriteFlow() {
        let installed = makeInstalledMap(region: "LTU", version: MapVersion(year: 2026, month: 4)!)
        let comparison = makeComparison(
            region: "LTU",
            name: "Lithuania",
            installedMap: installed,
            status: .updateAvailable
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyWithExistingMapConflict],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            items.first?.action == .update
                && plan.updateItems.count == 1
                && plan.status == .blocked
                && plan.canContinue == false,
            "an update is visible as an update but cannot enter the new-install write path"
        )
    }

    private static func testUnknownMapIsNotSelectable() {
        let comparison = makeComparison(region: "LTU", name: "Lithuania", status: .unknown)
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .blockedAmbiguousMapIdentity],
            recommendedRegionID: nil
        )

        expect(
            items.first?.action == .blocked && items.first?.isSelectable == false,
            "unknown or ambiguous map state remains outside the selectable list"
        )
    }

    private static func testInsufficientStorageBlocksPlan() {
        let comparison = makeComparison(region: "LVA", name: "Latvia", status: .notInstalled, size: 300)
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 300 + StoragePlanner.defaultSafetyReserve - 1
        )

        expect(
            plan.status == .blocked
                && plan.storagePlan.status == .blockedInsufficientSpace
                && plan.canContinue == false,
            "the one-gibibyte safety reserve blocks insufficient storage"
        )
    }

    private static func testUnknownInstallSizeDoesNotPassStorageGate() {
        let comparison = makeComparison(
            region: "LTU",
            name: "Lithuania",
            status: .notInstalled,
            includeInstallSize: false
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .blockedUnknownInstallSize],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            items.first?.isSelectable == true
                && plan.storagePlan.hasUnresolvedInstallSize
                && plan.storagePlan.status == .blockedUnknownInstallSize
                && !plan.canContinue,
            "unknown install size remains visible but cannot pass storage approval"
        )
    }

    private static func testFormalCountryNamesArePresentationOnly() {
        let package = MapPackage(
            id: "freizeitkarte-ltu",
            providerId: "freizeitkarte",
            regionId: "LTU",
            name: "Republic of Lithuania",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 300,
            sourceURL: nil,
            releaseDate: nil,
            identifier: "LTU",
            installSizeBytes: 300
        )

        expect(
            MapDisplayNameNormalizer.normalize(package.name) == "Lithuania"
                && package.name == "Republic of Lithuania",
            "formal country names are normalized only at the presentation layer"
        )
    }

    private static func testRegionalVariantsRemainDistinct() {
        let north = makeComparison(
            id: "freizeitkarte-deu-north",
            region: "DEU",
            name: "Federal Republic of Germany",
            status: .notInstalled,
            identifier: "DEU+NORTH"
        )
        let south = makeComparison(
            id: "freizeitkarte-deu-south",
            region: "DEU",
            name: "Federal Republic of Germany",
            status: .notInstalled,
            identifier: "DEU+SOUTH"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [north, south],
            preflightStatuses: [
                north.id: .readyNewInstall,
                south.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        expect(
            items.count == 2
                && Set<String>(items.map { $0.title }) == ["Germany · North", "Germany · South"],
            "catalog regional variants remain distinct and readable"
        )
    }

    private static func testInstalledAndAvailableListsAreSeparated() {
        let installed = makeComparison(
            region: "LTU",
            name: "Republic of Lithuania",
            installedMap: makeInstalledMap(region: "LTU"),
            status: .upToDate
        )
        let available = makeComparison(
            region: "LVA",
            name: "Republic of Latvia",
            status: .notInstalled
        )
        let items = MapSelectionPlanner().items(
            comparisons: [installed, available],
            preflightStatuses: [
                installed.id: .readyWithExistingMapConflict,
                available.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        let installedRows = MapSelectionPresentationModel.installed(items)
        let availableRows = MapSelectionPresentationModel.available(items, query: "")

        expect(
            installedRows.map(\.title) == ["Lithuania"]
                && availableRows.map(\.title) == ["Latvia"]
                && !availableRows.contains(where: { $0.title == "Lithuania" }),
            "installed catalog maps appear once and are excluded from Available"
        )
    }

    private static func testAvailableSearchUsesDisplayAndRegionNames() {
        let lithuania = makeComparison(
            region: "LTU",
            name: "Republic of Lithuania",
            status: .notInstalled
        )
        let latvia = makeComparison(
            region: "LVA",
            name: "Republic of Latvia",
            status: .notInstalled
        )
        let items = MapSelectionPlanner().items(
            comparisons: [lithuania, latvia],
            preflightStatuses: [
                lithuania.id: .readyNewInstall,
                latvia.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        expect(
            MapSelectionPresentationModel.available(items, query: "ltu")
                .map(\.title) == ["Lithuania"]
                && MapSelectionPresentationModel.available(items, query: "latvia")
                    .map(\.title) == ["Latvia"],
            "Available search filters display names and region identifiers"
        )

        expect(
            MapSelectionPresentationModel.available(items, query: "LITHUANIA")
                .map(\.title) == ["Lithuania"]
                && MapSelectionPresentationModel.available(items, query: "")
                    .map(\.title) == ["Latvia", "Lithuania"],
            "search is case-insensitive and clearing restores the full list"
        )
    }

    private static func testSelectionSurvivesFilteredPresentation() {
        let estonia = makeComparison(
            region: "EST",
            name: "Estonia",
            status: .notInstalled,
            size: 300
        )
        let france = makeComparison(
            region: "FRA",
            name: "France",
            status: .notInstalled,
            size: 200
        )
        let items = MapSelectionPlanner().items(
            comparisons: [estonia, france],
            preflightStatuses: [
                estonia.id: .readyNewInstall,
                france.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        let filtered = MapSelectionPresentationModel.available(items, query: "France")
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [estonia.id, france.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            filtered.map(\.title) == ["France"]
                && Set(plan.selectedItems.map(\.id)) == Set([estonia.id, france.id])
                && plan.storagePlan.selectedMapBytes == 500,
            "filtering changes visible rows without rebuilding selected map state"
        )
    }

    private static func testInstalledPresentationUsesRecognizedInventoryOwnership() {
        let managed = makeComparison(
            region: "LTU",
            name: "Lithuania",
            installedMap: makeInstalledMap(
                region: "LTU",
                managementState: .managedByTerento
            ),
            status: .upToDate
        )
        let external = makeComparison(
            region: "LVA",
            name: "Latvia",
            installedMap: makeInstalledMap(
                region: "LVA",
                managementState: .detectedNotManaged
            ),
            status: .upToDate
        )
        let unknown = makeComparison(
            region: "EST",
            name: "Estonia",
            installedMap: makeInstalledMap(
                region: "EST",
                managementState: .unknown
            ),
            status: .upToDate
        )
        let systemComparison = makeComparison(
            region: "DEU",
            name: "Garmin system map",
            installedMap: makeInstalledMap(
                region: "DEU",
                provider: "Garmin",
                managementState: .unknown
            ),
            status: .upToDate
        )
        let comparisons = [managed, external, unknown, systemComparison]
        let items = MapSelectionPlanner().items(
            comparisons: comparisons,
            preflightStatuses: Dictionary(uniqueKeysWithValues: comparisons.map {
                ($0.id, InstallationPreflightStatus.readyWithExistingMapConflict)
            }),
            recommendedRegionID: nil
        )
        let inventory = UnifiedMapInventory(
            freizeitkarte: [managed, external, unknown].map {
                MapInventoryEntry(
                    key: $0.id,
                    title: $0.regionName,
                    catalogPackage: $0.catalogMap,
                    comparison: $0,
                    installedMaps: [$0.installedMap!],
                    isSelectedCatalogMap: false
                )
            },
            otherMaps: [
                MapInventoryEntry(
                    key: "garmin-system",
                    title: "Garmin system map",
                    catalogPackage: nil,
                    comparison: nil,
                    installedMaps: [
                        makeInstalledMap(
                            region: "DEU",
                            provider: "Garmin",
                            managementState: .unknown
                        )
                    ],
                    isSelectedCatalogMap: false
                )
            ]
        )

        let installed = MapSelectionPresentationModel.supportedInstalled(
            items,
            inventory: inventory
        )

        expect(
            installed.map(\.title) == ["Latvia", "Lithuania"],
            "managed and external recognized maps appear while unknown and system maps stay out"
        )
    }

    private static func testStorageBarProjectionIsBoundedAndSegmented() {
        let plan = StoragePlanner(safetyReserve: 0).plan(
            currentFreeSpace: 600,
            selectedMapSizes: [100, 200]
        )
        let projection = StorageBarProjection(plan: plan, totalCapacity: 1_000)
        let insufficientPlan = StoragePlanner(safetyReserve: 0).plan(
            currentFreeSpace: 100,
            selectedMapSizes: [200]
        )
        let insufficientProjection = StorageBarProjection(
            plan: insufficientPlan,
            totalCapacity: 1_000
        )
        let zeroCapacityProjection = StorageBarProjection(
            plan: plan,
            totalCapacity: 0
        )

        expect(
            projection.existingUsedBytes == 400
                && projection.selectedMapBytes == 300
                && projection.freeAfterInstallationBytes == 300
                && abs(projection.fraction(for: 400) - 0.4) < 0.0001
                && abs(projection.fraction(for: 300) - 0.3) < 0.0001
                && insufficientProjection.selectedMapBytes == 100
                && insufficientProjection.freeAfterInstallationBytes == 0
                && zeroCapacityProjection.existingUsedBytes == 0
                && zeroCapacityProjection.selectedMapBytes == 0,
            "storage bar segments aggregate selected bytes and stay within capacity"
        )
    }

    private static func testInstallReviewAvailabilityMatchesRealState() {
        let comparison = makeComparison(
            region: "LVA",
            name: "Latvia",
            status: .notInstalled
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte
        )
        let resolver = InstallReviewAvailabilityResolver()
        let readyToPrepare = resolver.resolve(
            plan: plan,
            deviceConnected: true,
            supportedInstallFlow: true,
            installationPhase: .idle,
            hasValidatedArtifact: false,
            operationBusy: false
        )
        let readyToInstall = resolver.resolve(
            plan: plan,
            deviceConnected: true,
            supportedInstallFlow: true,
            installationPhase: .awaitingConfirmation,
            hasValidatedArtifact: true,
            operationBusy: false
        )
        let blockedByDevice = resolver.resolve(
            plan: plan,
            deviceConnected: false,
            supportedInstallFlow: true,
            installationPhase: .idle,
            hasValidatedArtifact: false,
            operationBusy: false
        )
        let blockedByOperation = resolver.resolve(
            plan: plan,
            deviceConnected: true,
            supportedInstallFlow: true,
            installationPhase: .idle,
            hasValidatedArtifact: false,
            operationBusy: true
        )
        let blockedByUnsupportedFlow = resolver.resolve(
            plan: plan,
            deviceConnected: true,
            supportedInstallFlow: false,
            installationPhase: .idle,
            hasValidatedArtifact: false,
            operationBusy: false
        )

        expect(
            readyToPrepare == .ready(.prepare)
                && readyToInstall == .ready(.install)
                && blockedByDevice.userReason == "Reconnect your Garmin to continue."
                && blockedByOperation.userReason == "Another device operation is in progress."
                && blockedByUnsupportedFlow.userReason == "This map cannot be installed safely on this Garmin yet.",
            "Install maps is enabled only for an executable ready state and explains real blockers"
        )
    }

    private static func testSelectedMapDividerPolicy() {
        expect(
            !MapRowDividerPolicy.showsDivider(at: 0, in: 1)
                && MapRowDividerPolicy.showsDivider(at: 0, in: 2)
                && !MapRowDividerPolicy.showsDivider(at: 1, in: 2)
                && MapRowDividerPolicy.showsDivider(at: 0, in: 4)
                && MapRowDividerPolicy.showsDivider(at: 2, in: 4)
                && !MapRowDividerPolicy.showsDivider(at: 3, in: 4),
            "selected-map dividers appear only between rows"
        )
    }

    private static func testInstallationFlowPresentation() {
        expect(
            !InstallationFlowPresentation.hasStarted(.idle)
                && InstallationFlowPresentation.isActive(.downloading)
                && InstallationFlowPresentation.isActive(.awaitingConfirmation)
                && InstallationFlowPresentation.hasStarted(.failed)
                && !InstallationFlowPresentation.isActive(.failed)
                && InstallationFlowPresentation.conflictMessage(
                    flowOwnsOperation: true,
                    independentOperationBusy: true
                ) == nil
                && InstallationFlowPresentation.conflictMessage(
                    flowOwnsOperation: false,
                    independentOperationBusy: true
                ) == "Another device operation is in progress."
                && InstallationFlowPresentation.shouldContinueAfterPreflight(
                    userAuthorized: true,
                    preflightSucceeded: true
                )
                && !InstallationFlowPresentation.shouldContinueAfterPreflight(
                    userAuthorized: false,
                    preflightSucceeded: true
                )
                && !InstallationFlowPresentation.shouldContinueAfterPreflight(
                    userAuthorized: true,
                    preflightSucceeded: false
                ),
            "active installation owns its UI state while independent MTP conflicts remain visible"
        )
    }

    private static func makeComparison(
        id: String? = nil,
        region: String,
        name: String,
        installedMap: InstalledMap? = nil,
        status: MapStatus,
        size: UInt64 = 300,
        installSize: UInt64? = nil,
        identifier: String? = nil,
        includeInstallSize: Bool = true
    ) -> MapComparison {
        let package = MapPackage(
            id: id ?? "freizeitkarte-\(region.lowercased())",
            providerId: "freizeitkarte",
            regionId: region,
            name: name,
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: size,
            sourceURL: nil,
            releaseDate: nil,
            identifier: identifier,
            installSizeBytes: includeInstallSize ? (installSize ?? size) : nil
        )

        return MapComparison(
            providerName: "Freizeitkarte",
            regionName: name,
            catalogMap: package,
            installedMap: installedMap,
            status: status
        )
    }

    private static func makeInstalledMap(
        region: String,
        version: MapVersion = MapVersion(year: 2026, month: 5)!,
        provider: String = "Freizeitkarte",
        managementState: MapManagementState = .detectedNotManaged,
        metadataStatus: MapMetadataStatus = .parsed
    ) -> InstalledMap {
        let path = "/GARMIN/freizeitkarte-\(region.lowercased()).img"
        return InstalledMap(
            name: "Freizeitkarte \(region)",
            provider: provider,
            region: region,
            family: "Freizeitkarte",
            rawVersion: "Release 26.05",
            version: version,
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: 300,
            sourceFile: InstalledMapFile(
                path: path,
                filename: URL(fileURLWithPath: path).lastPathComponent,
                sizeBytes: 300
            ),
            metadataStatus: metadataStatus,
            managementState: managementState
        )
    }

    private static let gigabyte: UInt64 = 1024 * 1024 * 1024

    private static func expect(_ condition: Bool, _ message: String) {
        if condition {
            print("PASS: \(message)")
        } else {
            print("FAIL: \(message)")
            exit(1)
        }
    }
}

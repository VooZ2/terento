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
        testMacRegionsRecommendLithuaniaAndLatvia()
        testUpToDateMapIsNotActionable()
        testNewMapProducesReadyPlan()
        testStorageUsesInstallSizeNotDownloadSize()
        testMultipleNewMapsUseCombinedStorage()
        testUpdateIsRepresentedButDoesNotEnterWriteFlow()
        testUnknownMapIsNotSelectable()
        testInsufficientStorageBlocksPlan()
        testUnknownInstallSizeDoesNotPassStorageGate()
        testFormalCountryNamesArePresentationOnly()
        testProviderTitlesAreCountryOnlyAndIncludeProviderVersionDetail()
        testLegacyProviderDecoratedTitlesNormalizeToCountryNames()
        testDifferentProvidersCannotShareInstallBatchInBeta8()
        testRegionalVariantsRemainDistinct()
        testInstalledAndAvailableListsAreSeparated()
        testAvailableSearchUsesDisplayAndRegionNames()
        testSelectionSurvivesFilteredPresentation()
        testInstalledPresentationUsesRecognizedInventoryOwnership()
        testStorageBarProjectionIsBoundedAndSegmented()
        testInstallReviewAvailabilityMatchesRealState()
        testSelectedMapDividerPolicy()
        testInstallationFlowPresentation()
        testWithheldCatalogRowsRemainVisibleAndNonSelectable()
        testCrimeaSearchAliasesAndPresentation()
        testStaleWithheldSelectionIsClearedAndBlocked()
        testAcquisitionAccessibilityLabels()
        testDefaultPlanRemainsMainOnly()
        testSelectedOptionalArtifactUsesExactCombinedSize()
        testInvalidOptionalArtifactBlocksThePlan()
        testOptionalArtifactMustBelongToThePackage()
        testTwoRegionsKeepIndependentOptionalSelections()
        testOptionalArtifactDoesNotChangeRegionCount()
        testPackagesWithoutUsableOptionalArtifactsExposeNoChoice()
        testParentDeselectionInvalidatesOptionalSelection()
        testDuplicateArtifactDefinitionsAreRejected()

        testCatalogGeographyIndex()
        testCatalogFilterPerformance()
        testBundledCatalogGeography()
        print("PASS: 39 Stage 4.5 map selection tests")
    }

    private static func testCatalogRegionsProduceOneCanonicalList() {
        let firstGermany = makeComparison(region: "DEU", name: "Germany", status: .notInstalled)
        let duplicateGermany = makeComparison(
            id: "freizeitkarte-deu-duplicate",
            region: "DEU",
            name: "Germany",
            status: .notInstalled
        )
        let france = makeComparison(region: "FRA", name: "France", status: .notInstalled)

        let items = MapSelectionPlanner().items(
            comparisons: [firstGermany, duplicateGermany, france],
            preflightStatuses: [
                firstGermany.id: .readyNewInstall,
                duplicateGermany.id: .readyNewInstall,
                france.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        expect(
            items.count == 2
                && Set(items.map(\.comparison.catalogMap.regionId)) == ["DEU", "FRA"],
            "catalog and installed data produce one canonical row per region"
        )
    }

    private static func testMacRegionsRecommendLithuaniaAndLatvia() {
        let lithuania = makeComparison(region: "LTU", name: "Lithuania", status: .notInstalled)
        let latvia = makeComparison(region: "LVA", name: "Latvia", status: .notInstalled)
        let comparisons = [lithuania, latvia]
        let preflightStatuses: [String: InstallationPreflightStatus] = [
            lithuania.id: .readyNewInstall,
            latvia.id: .readyNewInstall
        ]
        let lithuanianItems = MapSelectionPlanner().items(
            comparisons: comparisons,
            preflightStatuses: preflightStatuses,
            recommendedRegionID: MapRegionRecommendation.regionID(
                systemRegionCode: "LT",
                comparisons: comparisons
            )
        )
        let latvianItems = MapSelectionPlanner().items(
            comparisons: comparisons,
            preflightStatuses: preflightStatuses,
            recommendedRegionID: MapRegionRecommendation.regionID(
                systemRegionCode: "LV",
                comparisons: comparisons
            )
        )

        expect(
            lithuanianItems.first?.comparison.catalogMap.regionId == "LTU"
                && lithuanianItems.first?.isRecommended == true
                && latvianItems.first?.comparison.catalogMap.regionId == "LVA"
                && latvianItems.first?.isRecommended == true,
            "the Mac locale recommends the matching Lithuania and Latvia catalog regions"
        )
    }

    private static func testUpToDateMapIsNotActionable() {
        let comparison = makeComparison(
            region: "DEU",
            name: "Germany",
            installedMap: makeInstalledMap(region: "DEU"),
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
        let comparison = makeComparison(region: "FRA", name: "France", status: .notInstalled)
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
        let germany = makeComparison(region: "DEU", name: "Germany", status: .notInstalled, size: 300)
        let france = makeComparison(region: "FRA", name: "France", status: .notInstalled, size: 200)
        let items = MapSelectionPlanner().items(
            comparisons: [germany, france],
            preflightStatuses: [
                germany.id: .readyNewInstall,
                france.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [germany.id, france.id],
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
            region: "DEU",
            name: "Germany",
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
        let installed = makeInstalledMap(region: "DEU", version: MapVersion(year: 2026, month: 4)!)
        let comparison = makeComparison(
            region: "DEU",
            name: "Germany",
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
                && plan.storagePlan.selectedMapBytes == 0
                && plan.status == .blocked
                && plan.canContinue == false,
            "an update remains Manage-only and never consumes Install storage"
        )
    }

    private static func testUnknownMapIsNotSelectable() {
        let comparison = makeComparison(region: "DEU", name: "Germany", status: .unknown)
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
        let comparison = makeComparison(region: "FRA", name: "France", status: .notInstalled, size: 300)
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
            region: "DEU",
            name: "Germany",
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
            id: "freizeitkarte-deu",
            providerId: "freizeitkarte",
            regionId: "DEU",
            name: "Republic of Germany",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 300,
            sourceURL: nil,
            releaseDate: nil,
            identifier: "DEU",
            installSizeBytes: 300
        )

        expect(
            MapDisplayNameNormalizer.normalize(package.name) == "Germany"
                && package.name == "Republic of Germany",
            "formal country names are normalized only at the presentation layer"
        )
    }

    private static func testProviderTitlesAreCountryOnlyAndIncludeProviderVersionDetail() {
        let freizeitkarte = makeComparison(
            id: "freizeitkarte-azores",
            region: "AZORES",
            name: "Azores · AZORES",
            status: .notInstalled
        )
        let openTopoMap = makeComparison(
            id: "opentopomap-azores",
            providerID: "opentopomap",
            providerName: "OpenTopoMap",
            region: "AZORES",
            name: "Azores · Otm Azores",
            status: .notInstalled
        )
        let items = MapSelectionPlanner().items(
            comparisons: [freizeitkarte, openTopoMap],
            preflightStatuses: [
                freizeitkarte.id: .readyNewInstall,
                openTopoMap.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )
        let byID = Dictionary(uniqueKeysWithValues: items.map { ($0.id, $0) })

        expect(
            byID[freizeitkarte.id]?.title == "Azores"
                && byID[openTopoMap.id]?.title == "Azores"
                && byID[freizeitkarte.id]?.providerVersionLabel == "Freizeitkarte · 2026-05"
                && byID[openTopoMap.id]?.providerVersionLabel == "OpenTopoMap · 2026-05",
            "provider rows keep the country title and put provider plus version in the detail"
        )
    }

    private static func testLegacyProviderDecoratedTitlesNormalizeToCountryNames() {
        let freizeitkarte = makeComparison(
            id: "freizeitkarte-ltu",
            region: "LTU",
            name: "Republic of Lithuania",
            status: .notInstalled
        )
        let openTopoMap = makeComparison(
            id: "opentopomap-ltu",
            providerID: "opentopomap",
            providerName: "OpenTopoMap",
            region: "LTU",
            name: "Lithuania · Otm Lithuania",
            status: .notInstalled,
            identifier: "otm-lithuania"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [freizeitkarte, openTopoMap],
            preflightStatuses: [
                freizeitkarte.id: .readyNewInstall,
                openTopoMap.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        let byID = Dictionary(uniqueKeysWithValues: items.map { ($0.id, $0) })
        expect(
            byID[freizeitkarte.id]?.title == "Lithuania"
                && byID[openTopoMap.id]?.title == "Lithuania",
            "legacy provider-decorated Lithuania titles are normalized consistently"
        )
    }

    private static func testDifferentProvidersCannotShareInstallBatchInBeta8() {
        let freizeitkarte = makeComparison(
            id: "freizeitkarte-azores",
            region: "AZORES",
            name: "Azores",
            status: .notInstalled
        )
        let openTopoMap = makeComparison(
            id: "opentopomap-azores",
            providerID: "opentopomap",
            providerName: "OpenTopoMap",
            region: "AZORES",
            name: "Azores",
            status: .notInstalled
        )
        let items = MapSelectionPlanner().items(
            comparisons: [freizeitkarte, openTopoMap],
            preflightStatuses: [
                freizeitkarte.id: .readyNewInstall,
                openTopoMap.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )
        let fzkItem = items.first { $0.id == freizeitkarte.id }!
        let otmItem = items.first { $0.id == openTopoMap.id }!
        let planner = MapSelectionPlanner()
        let mixedPlan = planner.plan(
            items: items,
            selectedIDs: [freizeitkarte.id, openTopoMap.id],
            currentFreeSpace: 15 * gigabyte
        )

        expect(
            MapSelectionPresentationModel.isSelectionEnabled(
                fzkItem,
                selectedIDs: [freizeitkarte.id],
                items: items
            )
                && !MapSelectionPresentationModel.isSelectionEnabled(
                    otmItem,
                    selectedIDs: [freizeitkarte.id],
                    items: items
                )
                && mixedPlan.status == .blocked
                && mixedPlan.reason == "Select maps from one provider at a time.",
            "the current product locks the other provider and blocks mixed-provider install plans"
        )
    }

    private static func testRegionalVariantsRemainDistinct() {
        let north = makeComparison(
            id: "freizeitkarte-deu-north",
            region: "DEU-NORTH",
            name: "Federal Republic of Germany",
            status: .notInstalled,
            identifier: "DEU+NORTH"
        )
        let south = makeComparison(
            id: "freizeitkarte-deu-south",
            region: "DEU-SOUTH",
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
                && Set<String>(items.map { $0.title }) == ["Germany (North)", "Germany (South)"],
            "catalog regional variants remain distinct and readable"
        )
    }

    private static func testInstalledAndAvailableListsAreSeparated() {
        let installed = makeComparison(
            region: "DEU",
            name: "Republic of Germany",
            installedMap: makeInstalledMap(region: "DEU"),
            status: .upToDate
        )
        let available = makeComparison(
            region: "FRA",
            name: "Republic of France",
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
            installedRows.map(\.title) == ["Germany"]
                && availableRows.map(\.title) == ["France"]
                && !availableRows.contains(where: { $0.title == "Germany" })
                && MapSelectionPresentationModel.available(items, query: "Germany").map(\.title) == ["Germany"]
                && MapSelectionPresentationModel.available(items, query: "Germany").allSatisfy({ !$0.isSelectable }),
            "installed catalog maps are excluded from normal browsing but appear as non-selectable search results"
        )
    }

    private static func testAvailableSearchUsesDisplayAndRegionNames() {
        let germany = makeComparison(
            region: "DEU",
            name: "Republic of Germany",
            status: .notInstalled
        )
        let france = makeComparison(
            region: "FRA",
            name: "Republic of France",
            status: .notInstalled
        )
        let items = MapSelectionPlanner().items(
            comparisons: [germany, france],
            preflightStatuses: [
                germany.id: .readyNewInstall,
                france.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )

        expect(
            MapSelectionPresentationModel.available(items, query: "deu")
                .map(\.title) == ["Germany"]
                && MapSelectionPresentationModel.available(items, query: "france")
                    .map(\.title) == ["France"],
            "Available search filters display names and region identifiers"
        )

        expect(
            MapSelectionPresentationModel.available(items, query: "GERMANY")
                .map(\.title) == ["Germany"]
                && MapSelectionPresentationModel.available(items, query: "")
                    .map(\.title) == ["France", "Germany"],
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
            region: "DEU",
            name: "Germany",
            installedMap: makeInstalledMap(
                region: "DEU",
                managementState: .managedByTerento
            ),
            status: .upToDate
        )
        let external = makeComparison(
            region: "FRA",
            name: "France",
            installedMap: makeInstalledMap(
                region: "FRA",
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
            id: "garmin-system",
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
            installed.map(\.title) == ["France", "Germany"],
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
            region: "FRA",
            name: "France",
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

    private static func testWithheldCatalogRowsRemainVisibleAndNonSelectable() {
        let russia = makeComparison(
            id: "freizeitkarte-rus-central",
            region: "RUS-CENTRAL",
            name: "Russian Federation, Central Federal District",
            status: .notInstalled,
            identifier: "RUS_CENTRAL"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [russia],
            preflightStatuses: [russia.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        expect(
            MapSelectionPresentationModel.available(items, query: "").count == 1
                && items.first?.acquisitionAvailability == .withheldRussia
                && items.first?.lifecycleAction == .install
                && items.first?.isSelectable == false
                && items.first?.package == russia.catalogMap,
            "withheld russia packages remain unchanged and visible while acquisition is non-selectable"
        )
    }

    private static func testCrimeaSearchAliasesAndPresentation() {
        let crimea = makeComparison(
            id: "freizeitkarte-rus-crimea",
            region: "RUS-CRIMEA",
            name: "Russian Federation, Crimean Federal District",
            status: .notInstalled,
            identifier: "RUS_CRIMEA"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [crimea],
            preflightStatuses: [crimea.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let queries = ["Crimea", "Ukraine", "UA"]
        expect(
            items.first?.title == "Crimea"
                && items.first?.acquisitionAvailability.detailedExplanation
                    == "Crimea is part of Ukraine and is temporarily occupied by russia."
                && queries.allSatisfy { MapSelectionPresentationModel.available(items, query: $0).count == 1 },
            "Crimea uses the policy title and is searchable by geographic identities only"
        )
    }

    private static func testStaleWithheldSelectionIsClearedAndBlocked() {
        let crimea = makeComparison(
            id: "freizeitkarte-rus-crimea",
            region: "RUS-CRIMEA",
            name: "Russian Federation, Crimean Federal District",
            status: .notInstalled,
            identifier: "RUS_CRIMEA"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [crimea],
            preflightStatuses: [crimea.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let staleIDs: Set<String> = [crimea.id]
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: staleIDs,
            currentFreeSpace: 15 * gigabyte
        )
        expect(
            MapSelectionPresentationModel.validSelectionIDs(staleIDs, items: items).isEmpty
                && plan.status == .blocked
                && !plan.canContinue
                && plan.installItems.isEmpty,
            "stale withheld selections are cleared and cannot enter the install plan"
        )
    }

    private static func testAcquisitionAccessibilityLabels() {
        let russia = makeComparison(
            id: "freizeitkarte-rus-central",
            region: "RUS-CENTRAL",
            name: "Russian Federation, Central Federal District",
            status: .notInstalled,
            identifier: "RUS_CENTRAL"
        )
        let crimea = makeComparison(
            id: "freizeitkarte-rus-crimea",
            region: "RUS-CRIMEA",
            name: "Russian Federation, Crimean Federal District",
            status: .notInstalled,
            identifier: "RUS_CRIMEA"
        )
        let germany = makeComparison(region: "DEU", name: "Germany", status: .notInstalled)
        let items = MapSelectionPlanner().items(
            comparisons: [russia, crimea, germany],
            preflightStatuses: [
                russia.id: .readyNewInstall,
                crimea.id: .readyNewInstall,
                germany.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )
        let byID = Dictionary(uniqueKeysWithValues: items.map { ($0.id, $0) })
        expect(
            byID[russia.id]?.acquisitionAccessibilityLabel
                == "Russian Federation, Central Federal District. Map download unavailable. Terento does not offer map downloads for russia while its war of aggression against Ukraine continues."
                && byID[crimea.id]?.acquisitionAccessibilityLabel
                    == "Crimea. Map download unavailable. Crimea is part of Ukraine and is temporarily occupied by russia."
                && byID[germany.id]?.acquisitionAccessibilityLabel == nil
                && byID[germany.id]?.isSelectable == true,
            "VoiceOver labels distinguish withheld rows while normal selection stays accessible"
        )
    }

    private static func testDefaultPlanRemainsMainOnly() {
        let comparison = makeComparisonWithContours(
            region: "LTU",
            name: "Lithuania"
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
            plan.selectedPackagePlans.first?.artifactPlan.selectedArtifactIDs
                == [comparison.catalogMap.id + "-main"]
                && plan.storagePlan.selectedMapBytes == 300,
            "the default artifact plan remains main-only for old clients"
        )
    }

    private static func testSelectedOptionalArtifactUsesExactCombinedSize() {
        let comparison = makeComparisonWithContours(
            region: "LTU",
            name: "Lithuania",
            contourSize: 80
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let contourID = comparison.catalogMap.optionalArtifacts[0].id
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte,
            selectedOptionalArtifactIDs: [comparison.id: [contourID]]
        )

        expect(
            plan.status == .ready
                && plan.selectedPackagePlans.first?.selection.selectedOptionalArtifactIDs == [contourID]
                && plan.storagePlan.selectedMapBytes == 380,
            "selected optional artifacts use one immutable combined storage plan"
        )
    }

    private static func testInvalidOptionalArtifactBlocksThePlan() {
        let comparison = makeComparisonWithContours(
            region: "LTU",
            name: "Lithuania",
            contourSize: nil
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let contourID = comparison.catalogMap.optionalArtifacts[0].id
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte,
            selectedOptionalArtifactIDs: [comparison.id: [contourID]]
        )

        expect(
            items[0].usableOptionalArtifacts.isEmpty
                && plan.status == .blocked
                && plan.canContinue == false,
            "an optional artifact without an exact install size cannot be selected"
        )
    }

    private static func testOptionalArtifactMustBelongToThePackage() {
        let comparison = makeComparisonWithContours(
            region: "LTU",
            name: "Lithuania"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte,
            selectedOptionalArtifactIDs: [comparison.id: ["other-package-contours"]]
        )

        expect(
            plan.status == .blocked && plan.reason.contains("component"),
            "an optional artifact from another package is rejected"
        )
    }

    private static func testTwoRegionsKeepIndependentOptionalSelections() {
        let lithuania = makeComparisonWithContours(region: "LTU", name: "Lithuania")
        let latvia = makeComparisonWithContours(region: "LVA", name: "Latvia")
        let items = MapSelectionPlanner().items(
            comparisons: [lithuania, latvia],
            preflightStatuses: [
                lithuania.id: .readyNewInstall,
                latvia.id: .readyNewInstall
            ],
            recommendedRegionID: nil
        )
        let lithuaniaContours = lithuania.catalogMap.optionalArtifacts[0].id
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [lithuania.id, latvia.id],
            currentFreeSpace: 15 * gigabyte,
            selectedOptionalArtifactIDs: [lithuania.id: [lithuaniaContours]]
        )

        let lithuaniaPlan = plan.selectedPackagePlans.first { $0.item.id == lithuania.id }
        let latviaPlan = plan.selectedPackagePlans.first { $0.item.id == latvia.id }
        expect(
            lithuaniaPlan?.artifactPlan.optionalArtifacts.map(\.id) == [lithuaniaContours]
                && latviaPlan?.artifactPlan.optionalArtifacts.isEmpty == true
                && plan.storagePlan.selectedMapBytes == 640,
            "two regions keep optional selections independent"
        )
    }

    private static func testOptionalArtifactDoesNotChangeRegionCount() {
        let comparison = makeComparisonWithContours(
            region: "LTU",
            name: "Lithuania"
        )
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let contourID = comparison.catalogMap.optionalArtifacts[0].id
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [comparison.id],
            currentFreeSpace: 15 * gigabyte,
            selectedOptionalArtifactIDs: [comparison.id: [contourID]]
        )

        expect(
            plan.selectedItems.count == 1
                && plan.installItems.count == 1
                && plan.selectedPackagePlans.count == 1,
            "an optional artifact remains part of one selected region"
        )
    }

    private static func testPackagesWithoutUsableOptionalArtifactsExposeNoChoice() {
        let comparison = makeComparison(region: "DEU", name: "Germany", status: .notInstalled)
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )

        expect(
            items.first?.usableOptionalArtifacts.isEmpty == true,
            "packages without a usable optional artifact expose no optional choice"
        )
    }

    private static func testParentDeselectionInvalidatesOptionalSelection() {
        let comparison = makeComparisonWithContours(region: "LTU", name: "Lithuania")
        let items = MapSelectionPlanner().items(
            comparisons: [comparison],
            preflightStatuses: [comparison.id: .readyNewInstall],
            recommendedRegionID: nil
        )
        let contourID = comparison.catalogMap.optionalArtifacts[0].id
        let plan = MapSelectionPlanner().plan(
            items: items,
            selectedIDs: [],
            currentFreeSpace: 15 * gigabyte,
            selectedOptionalArtifactIDs: [comparison.id: [contourID]]
        )

        expect(
            plan.status == .blocked
                && plan.selectedPackagePlans.isEmpty
                && plan.canContinue == false,
            "a child selection cannot survive when its parent package is deselected"
        )
    }

    private static func testDuplicateArtifactDefinitionsAreRejected() {
        let packageID = "opentopomap-ltu"
        let main = MapArtifact(
            id: packageID + "-main",
            kind: .main,
            required: true,
            sourceURL: URL(string: "https://garmin.opentopomap.org/lithuania.zip"),
            sizeBytes: 300,
            validationState: .validated
        )
        let contours = MapArtifact(
            id: packageID + "-contours",
            kind: .contours,
            required: false,
            sourceURL: URL(string: "https://garmin.opentopomap.org/lithuania-contours.zip"),
            sizeBytes: 40,
            validationState: .validated
        )
        let package = MapPackage(
            id: packageID,
            providerId: "opentopomap",
            regionId: "LTU",
            name: "Lithuania",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 300,
            sourceURL: main.sourceURL,
            releaseDate: nil,
            identifier: "LTU",
            installSizeBytes: 300,
            artifacts: [main, contours, contours]
        )

        do {
            _ = try MapPackageSelection(
                package: package,
                selectedOptionalArtifactIDs: [contours.id]
            )
            expect(false, "duplicate artifact definitions are rejected")
        } catch let error as MapPackageSelectionError {
            expect(
                error == .duplicateArtifact(contours.id),
                "duplicate artifact definitions are rejected"
            )
        } catch {
            expect(false, "duplicate artifact definitions are rejected")
        }
    }

    private static func testCatalogGeographyIndex() {
        let comparisons = [
            makeComparison(id: "raw-secret-a", providerID: "maprando", region: "FRA", name: "France (IGN contours)", status: .notInstalled, countryCodes: ["FR"]),
            makeComparison(id: "raw-secret-b", providerID: "bbbike", region: "MULTI", name: "Border region", status: .notInstalled, countryCodes: ["France", "JP"]),
            makeComparison(id: "unknown", region: "UNKNOWN", name: "Unclassified region", status: .notInstalled),
            makeComparison(id: "diacritic", region: "RE", name: "Réunion", status: .notInstalled, countryCodes: ["RE"])
        ]
        let items = MapSelectionPlanner().items(comparisons: comparisons, preflightStatuses: [:], recommendedRegionID: nil)
        let index = MapCatalogPresentationIndex(items: items)
        expect(index.filtered(query: " france  fr ").count == 2, "Country aliases combine with AND and whitespace normalization")
        expect(index.filtered(query: "REUNION").map(\.id) == ["diacritic"], "Query and index share diacritic folding")
        expect(["raw-secret", "maprando", "bbbike", "IGN", "contours"].allSatisfy { index.filtered(query: $0).isEmpty }, "Provider, raw identifiers and style are excluded from geographic search")
        expect(index.filtered(query: "", geography: .asia).map(\.id) == ["raw-secret-b"], "Multi-country row belongs to every relevant geography")
        expect(index.filtered(query: "", geography: .other).map(\.id) == ["unknown"], "Unknown geography remains available in Other")
        expect(index.filtered(query: "France", providerID: "MAPRANDO").count == 1, "Provider and query filters intersect")
        expect(index.geographyOptions.contains(.other), "Other is exposed when needed")
        expect(!MapCatalogPresentationIndex(items: []).geographyOptions.contains(.other), "Other is hidden without unknown packages")
        let reversed = MapCatalogPresentationIndex(items: items.reversed())
        expect(index.filtered(query: "").map(\.id) == reversed.filtered(query: "").map(\.id), "Ordering is independent of input order")
    }

    private static func testBundledCatalogGeography() {
        guard let path = ProcessInfo.processInfo.environment["TERENTO_TEST_CATALOG"],
              let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let providers = root["providers"] as? [[String: Any]] else {
            expect(false, "Bundled catalog must be provided to geography test"); return
        }
        var comparisons: [MapComparison] = []
        for provider in providers {
            for map in provider["maps"] as? [[String: Any]] ?? [] {
                comparisons.append(makeComparison(id: map["id"] as? String,
                    providerID: provider["id"] as! String, providerName: provider["name"] as! String,
                    region: map["region"] as! String, name: map["name"] as! String,
                    status: .notInstalled, identifier: map["identifier"] as? String, countryCodes: map["countryCodes"] as? [String] ?? (map["country"] as? String).map { [$0] } ?? []))
            }
        }
        let items = MapSelectionPlanner().items(comparisons: comparisons, preflightStatuses: [:], recommendedRegionID: nil)
        let index = MapCatalogPresentationIndex(items: items)
        expect(items.count == comparisons.count, "Bundled geography audit retains every distinct provider package")
        let unknown = index.filtered(query: "", geography: .other)
        if !unknown.isEmpty { print("UNKNOWN GEOGRAPHY: \(unknown.map { $0.package.id + ": " + $0.title })") }
        expect(unknown.isEmpty, "Every known bundled package has reviewed geography")
        expect(index.filtered(query: "Canary", geography: .africa).count > 0, "Canary Islands follow geographic Africa")
        expect(!index.filtered(query: "", geography: .europe).contains { $0.package.regionId == "RUSSIAASIANPART" }, "Asian russia extract is not categorized as Europe")
        expect(!index.filtered(query: "", geography: .asia).contains { $0.package.regionId == "RUSSIAEUROPEANPART" }, "European russia extract is not categorized as Asia")
    }

    private static func testCatalogFilterPerformance() {
        for count in [500, 1000, 2000] {
            let providers = ["freizeitkarte", "opentopomap", "maprando", "bbbike"]
            let comparisons = (0..<count).map { index in
                makeComparison(id: "fixture-\(index)", providerID: providers[index % 4], region: "FR-\(index)", name: "France region \(index)", status: .notInstalled, countryCodes: ["FR"])
            }
            let items = MapSelectionPlanner().items(comparisons: comparisons, preflightStatuses: [:], recommendedRegionID: nil)
            let index = MapCatalogPresentationIndex(items: items)
            var durations: [Double] = []
            var resultCount = 0
            for iteration in 0..<105 {
                let start = DispatchTime.now().uptimeNanoseconds
                let rows = index.filtered(query: iteration.isMultiple(of: 2) ? "france region" : "no matching region", providerID: iteration.isMultiple(of: 3) ? "maprando" : "", geography: .europe)
                resultCount += rows.count
                let duration = Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000
                if iteration >= 5 { durations.append(duration) }
            }
            let p95 = durations.sorted()[94]
            expect(resultCount > 0 && items.count == count, "Performance fixture retains \(count) rows across four providers")
            print("PERF: \(count) rows filter p95 \(String(format: "%.3f", p95)) ms")
            #if !DEBUG
            expect(p95 < 16, "Filter p95 is below 16 ms")
            #endif
        }
    }

    private static func makeComparison(
        id: String? = nil,
        providerID: String = "freizeitkarte",
        providerName: String = "Freizeitkarte",
        region: String,
        name: String,
        installedMap: InstalledMap? = nil,
        status: MapStatus,
        size: UInt64 = 300,
        installSize: UInt64? = nil,
        identifier: String? = nil,
        includeInstallSize: Bool = true,
        artifacts: [MapArtifact]? = nil,
        countryCodes: [String] = []
    ) -> MapComparison {
        let package = MapPackage(
            id: id ?? "\(providerID)-\(region.lowercased())",
            providerId: providerID,
            regionId: region,
            name: name,
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: size,
            sourceURL: nil,
            releaseDate: nil,
            identifier: identifier,
            installSizeBytes: includeInstallSize ? (installSize ?? size) : nil,
            countryCodes: countryCodes,
            artifacts: artifacts
        )

        return MapComparison(
            providerName: providerName,
            regionName: name,
            catalogMap: package,
            installedMap: installedMap,
            status: status
        )
    }

    private static func makeComparisonWithContours(
        region: String,
        name: String,
        contourSize: UInt64? = 40
    ) -> MapComparison {
        let packageID = "opentopomap-" + region.lowercased()
        let main = MapArtifact(
            id: packageID + "-main",
            kind: .main,
            required: true,
            providerId: "opentopomap",
            providerRegionId: region,
            canonicalRegionId: region,
            version: MapVersion(year: 2026, month: 5)!,
            sourceURL: URL(string: "https://garmin.opentopomap.org/" + region.lowercased() + ".zip"),
            sizeBytes: 300,
            validationState: .validated
        )
        let contours = MapArtifact(
            id: packageID + "-contours",
            kind: .contours,
            required: false,
            providerId: "opentopomap",
            providerRegionId: region,
            canonicalRegionId: region,
            version: MapVersion(year: 2026, month: 5)!,
            sourceURL: URL(string: "https://garmin.opentopomap.org/" + region.lowercased() + "-contours.zip"),
            sizeBytes: contourSize,
            validationState: .validated
        )
        return makeComparison(
            id: packageID,
            providerID: "opentopomap",
            providerName: "OpenTopoMap",
            region: region,
            name: name,
            status: .notInstalled,
            size: 300,
            installSize: 300,
            artifacts: [main, contours]
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

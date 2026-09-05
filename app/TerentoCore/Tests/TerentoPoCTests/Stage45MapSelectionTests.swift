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

        print("PASS: 27 Stage 4.5 map selection tests")
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
        let queries = ["Crimea", "Ukraine", "RUS-CRIMEA", "RUS_CRIMEA", "freizeitkarte-rus-crimea"]
        expect(
            items.first?.title == "Crimea"
                && items.first?.acquisitionAvailability.detailedExplanation
                    == "Crimea is part of Ukraine and is temporarily occupied by russia."
                && queries.allSatisfy { MapSelectionPresentationModel.available(items, query: $0).count == 1 },
            "Crimea uses the policy title and is searchable by geographic and provider identities"
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
        includeInstallSize: Bool = true
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
            installSizeBytes: includeInstallSize ? (installSize ?? size) : nil
        )

        return MapComparison(
            providerName: providerName,
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

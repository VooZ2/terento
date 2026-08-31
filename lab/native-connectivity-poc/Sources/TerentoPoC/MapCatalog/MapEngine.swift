import Foundation

struct MapInventoryResult: Sendable, Equatable {
    let scan: MapScanResult
    /// Complete pre-install inventory. `scan.files` intentionally contains
    /// only files inspected as map candidates; installation protection needs
    /// the complete device inventory.
    let deviceFiles: [DeviceFile]
    let comparisons: [MapComparison]

    var comparisonEvidence: EvidenceResult {
        guard !comparisons.isEmpty else {
            return .pending
        }

        return comparisons.allSatisfy { $0.status != .unknown } ? .pass : .fail
    }

    func unifiedMapInventory(selectedCatalogPackageID: String? = nil) -> UnifiedMapInventory {
        MapInventoryListBuilder().build(
            scan: scan,
            comparisons: comparisons,
            selectedCatalogPackageID: selectedCatalogPackageID
        )
    }
}

private final class MapEngineAcquisitionRelay: @unchecked Sendable {
    weak var engine: MapEngine?

    init(engine: MapEngine) {
        self.engine = engine
    }

    func send(_ state: MapAcquisitionState) {
        let engine = self.engine
        Task { @MainActor in
            engine?.receiveAcquisitionState(state)
        }
    }
}

private final class MapEngineProgressRelay: @unchecked Sendable {
    weak var engine: MapEngine?

    init(engine: MapEngine) {
        self.engine = engine
    }

    func send(_ progress: TransferProgress) {
        let engine = self.engine
        Task { @MainActor in
            engine?.receiveInstallationProgress(progress)
        }
    }
}

private final class MapEnginePhaseRelay: @unchecked Sendable {
    weak var engine: MapEngine?

    init(engine: MapEngine) {
        self.engine = engine
    }

    func send(_ phase: InstallationProcessPhase) {
        let engine = self.engine
        Task { @MainActor in
            engine?.receiveInstallationPhase(phase)
        }
    }
}

private final class MapEnginePhaseProgressRelay: @unchecked Sendable {
    weak var engine: MapEngine?

    init(engine: MapEngine) {
        self.engine = engine
    }

    func send(_ phase: InstallationProcessPhase, _ progress: Double) {
        let engine = self.engine
        Task { @MainActor in
            engine?.receiveInstallationPhaseProgress(phase, progress: progress)
        }
    }
}

private final class MapEngineDownloadProgressRelay: @unchecked Sendable {
    weak var engine: MapEngine?

    init(engine: MapEngine) {
        self.engine = engine
    }

    func send(_ progress: MapDownloadProgress) {
        let engine = self.engine
        Task { @MainActor in
            engine?.receiveDownloadProgress(progress)
        }
    }
}

private final class InstallationMapIndexState: @unchecked Sendable {
    private let lock = NSLock()
    private var storedValue = 0

    var value: Int {
        lock.withLock { storedValue }
    }

    func set(_ value: Int) {
        lock.withLock { storedValue = value }
    }
}

struct MapInventoryEngine<Reader: DeviceFileReader>: Sendable {
    let reader: Reader
    let catalog: MapCatalog
    let ownershipRecords: [MapOwnershipRecord]
    let additionalPackages: [MapPackage]

    init(
        reader: Reader,
        catalog: MapCatalog,
        ownershipRecords: [MapOwnershipRecord] = [],
        additionalPackages: [MapPackage] = []
    ) {
        self.reader = reader
        self.catalog = catalog
        self.ownershipRecords = ownershipRecords
        self.additionalPackages = additionalPackages
    }

    func scan() throws -> MapInventoryResult {
        let files = try reader.readFileInventory()
        let scan = GarminMapScanner().scan(
            files: files,
            reader: reader,
            ownershipRecords: ownershipRecords,
            recognizedProviderIDs: Set(
                catalog.providers.map { MapIdentity.normalizeProvider($0.id) }
            )
        )
        let packages = catalog.packages + additionalPackages.filter { additional in
            !catalog.packages.contains(where: { $0.id == additional.id })
        }
        let comparisons = packages.compactMap { package -> MapComparison? in
            if package.sourceKind == .custom {
                return MapComparison(
                    providerName: "Custom map",
                    regionName: "Custom map",
                    catalogMap: package,
                    installedMap: nil,
                    status: .notInstalled
                )
            }

            guard let provider = catalog.provider(for: package.providerId),
                  let region = catalog.region(
                      for: package.regionId,
                      providerId: package.providerId
                  ) else {
                return nil
            }

            return MapComparisonEngine().compare(
                installedMaps: scan.installedMaps,
                provider: provider,
                region: region,
                catalogMap: package
            )
        }

        return MapInventoryResult(
            scan: scan,
            deviceFiles: files,
            comparisons: comparisons
        )
    }
}

enum MapEngineState: Equatable {
    case idle
    case loadingCatalog
    case scanning
    case acquiringArtifact
    case preparingInstallation
    case installing
    case scanned
    case failed
}

private struct MapInventoryScanOutput: Sendable {
    let inventory: MapInventoryResult
    let ownershipManifestDeviceKeys: Set<String>
    let preferredOwnershipManifestDeviceKey: String?
}

@MainActor
final class MapEngine: ObservableObject {
    @Published private(set) var state: MapEngineState = .idle
    @Published private(set) var result: MapInventoryResult?
    @Published private(set) var selectedPreflight: InstallationPreflightResult?
    @Published private(set) var validatedArtifacts: [String: ValidatedMapArtifact] = [:]
    @Published private(set) var acquisitionState: MapAcquisitionState = .idle
    @Published private(set) var acquisitionProgress: MapDownloadProgress?
    @Published private(set) var acquisitionErrorMessage: String?
    @Published private(set) var customMapImportState: CustomMapImportState = .idle
    @Published private(set) var customMapImportCandidate: CustomMapImportCandidate?
    @Published private(set) var customMapImportErrorMessage: String?
    @Published private(set) var customMapImportWarning: CustomMapImportWarning?
    @Published private(set) var customMapImportRisk: CustomMapImportRisk?
    @Published private(set) var installationResult: MapInstallationResult?
    @Published private(set) var installationBatchResults: [MapInstallationResult] = []
    @Published private(set) var installationProgress: TransferProgress?
    @Published private(set) var finishingTransferProgress: TransferProgress?
    @Published private(set) var installationPhase: InstallationProcessPhase = .idle
    @Published private(set) var installationPhaseProgress: Double?
    @Published private(set) var installationPhaseProgressIsMeasured = false
    @Published private(set) var installationErrorMessage: String?
    @Published private(set) var evidenceFailureStage: EvidenceFailureStage?
    @Published private(set) var evidenceFailure: InstallationFailure?
    @Published private(set) var evidenceNativeFailureCode: EvidenceNativeFailureCode?
    @Published private(set) var evidencePrimaryFailureMapIndex: Int?
    @Published private(set) var catalogSource: MapCatalogSource?
    @Published private(set) var catalogUpdatedAt: Date?
    @Published private(set) var errorMessage: String?
    @Published private(set) var userErrorMessage: String?

    private let reader: MTPTransport
    private let operationGate: MTPOperationGate
    private let catalogLoader: MapCatalogLoader
    private var activeTask: Task<Void, Never>?
    private var loadedCatalog: MapCatalog?
    private var currentIdentity: DeviceIdentity?
    private var currentAvailableStorage: UInt64?
    private var ownershipManifestDeviceKeys: Set<String> = []
    private var preferredOwnershipManifestDeviceKey: String?
    private var installationSpeedEstimator = TransferSpeedEstimator()
    private var installationAuthorizationGranted = false
    private var customMapImportAcknowledged = false
    private var selectedInstallationPlan: InstallationPlan?

    var validatedArtifact: ValidatedMapArtifact? {
        guard let firstPackageID = selectedInstallationPlan?.installItems.first?.package.id else {
            return nil
        }
        return validatedArtifacts[firstPackageID]
    }

    var customMapImportReadyForInstallation: Bool {
        customMapImportCandidate == nil || customMapImportAcknowledged
    }

    init(
        reader: MTPTransport = MTPTransport(),
        catalogLoader: MapCatalogLoader = MapCatalogLoader(),
        operationGate: MTPOperationGate = .shared
    ) {
        self.reader = reader
        self.catalogLoader = catalogLoader
        self.operationGate = operationGate
    }

    /// Invalidates all device-derived map state after a disconnect or eject.
    /// This only cancels local work and clears memory; it never calls an MTP
    /// write, delete, move, or rename operation.
    func resetForDisconnectedDevice() {
        operationGate.invalidateLifecycleOperations()
        activeTask?.cancel()
        activeTask = nil
        discardCustomMapImport()
        state = .idle
        result = nil
        selectedPreflight = nil
        validatedArtifacts = [:]
        acquisitionState = .idle
        acquisitionProgress = nil
        acquisitionErrorMessage = nil
        installationResult = nil
        installationBatchResults = []
        evidenceFailureStage = nil
        evidenceFailure = nil
        evidenceNativeFailureCode = nil
        evidencePrimaryFailureMapIndex = nil
        installationProgress = nil
        finishingTransferProgress = nil
        installationPhase = .idle
        installationPhaseProgress = nil
        installationPhaseProgressIsMeasured = false
        installationErrorMessage = nil
        catalogSource = nil
        catalogUpdatedAt = nil
        errorMessage = nil
        userErrorMessage = nil
        loadedCatalog = nil
        currentIdentity = nil
        currentAvailableStorage = nil
        ownershipManifestDeviceKeys.removeAll()
        preferredOwnershipManifestDeviceKey = nil
        installationSpeedEstimator.reset()
        installationAuthorizationGranted = false
        selectedInstallationPlan = nil
    }

    func scanDeviceMaps(
        deviceIdentity: DeviceIdentity? = nil,
        availableStorage: UInt64? = nil,
        preservingInstallationResult: Bool = false
    ) {
        guard state != .loadingCatalog, state != .scanning else {
            return
        }

        discardCustomMapImport()

        let preservedInstallationResult = preservingInstallationResult ? installationResult : nil
        let preservedInstallationPhase = preservingInstallationResult ? installationPhase : .idle
        let preservedInstallationPhaseProgress = preservingInstallationResult
            ? installationPhaseProgress
            : nil

        state = .loadingCatalog
        result = nil
        selectedPreflight = nil
        validatedArtifacts = [:]
        acquisitionState = .idle
        acquisitionProgress = nil
        acquisitionErrorMessage = nil
        if !preservingInstallationResult {
            installationResult = nil
        }
        installationProgress = nil
        finishingTransferProgress = nil
        if !preservingInstallationResult {
            installationPhase = .idle
            installationPhaseProgress = nil
            installationErrorMessage = nil
        }
        catalogSource = nil
        catalogUpdatedAt = nil
        errorMessage = nil
        userErrorMessage = nil
        loadedCatalog = nil
        currentIdentity = deviceIdentity
        currentAvailableStorage = availableStorage
        installationAuthorizationGranted = false
        installationPhaseProgressIsMeasured = false

        let operationGate = self.operationGate
        let catalogLoader = self.catalogLoader
        ownershipManifestDeviceKeys = Self.manifestDeviceKeys(for: deviceIdentity)
        activeTask?.cancel()
        activeTask = Task { [weak self] in
            do {
                let loaded = try await CancellableDetached.run(priority: .userInitiated) {
                    try await operationGate.withAsyncOperation(kind: .catalog) {
                        try await catalogLoader.loadRemoteThenFallback()
                    }
                }

                guard !Task.isCancelled else { return }

                self?.loadedCatalog = loaded.catalog
                self?.catalogSource = loaded.source
                self?.catalogUpdatedAt = loaded.catalog.updatedAt
                self?.state = .scanning

                let scanOutput = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await operationGate.beginLifecycleAsync()
                    defer { operationGate.endLifecycle(lease) }

                    let lifecycleReader = MTPTransport(
                        operationGate: operationGate,
                        lifecycleLease: lease
                    )

                    // DeviceEngine's initial identity and the identity read
                    // immediately before a map scan can use different
                    // identifiers (for example a legacy model key first and
                    // an MTP serial after the native session is ready). Read
                    // both manifest namespaces for this same live device so
                    // an exact ownership record is not lost between phases.
                    let liveIdentity = (try? lifecycleReader.readSnapshot())
                        .map { CompatibilityEngine().evaluate(snapshot: $0).identity }
                    let manifestKeys = Self.manifestDeviceKeys(
                        for: [deviceIdentity, liveIdentity]
                    )
                    let ownershipRecords = Self.loadOwnershipRecords(
                        forDeviceKeys: manifestKeys,
                        recoveryIdentities: [deviceIdentity, liveIdentity]
                    )
                    let inventory = try MapInventoryEngine(
                        reader: lifecycleReader,
                        catalog: loaded.catalog,
                        ownershipRecords: ownershipRecords
                    ).scan()
                    return MapInventoryScanOutput(
                        inventory: inventory,
                        ownershipManifestDeviceKeys: manifestKeys,
                        preferredOwnershipManifestDeviceKey: liveIdentity?.localManifestDeviceKey
                            ?? deviceIdentity?.localManifestDeviceKey
                    )
                }

                guard !Task.isCancelled else { return }

                self?.ownershipManifestDeviceKeys = scanOutput.ownershipManifestDeviceKeys
                self?.preferredOwnershipManifestDeviceKey = scanOutput.preferredOwnershipManifestDeviceKey
                self?.result = scanOutput.inventory
                TerentoDiagnosticLog.recordMapInventoryScan(
                    scanOutput.inventory,
                    trigger: preservingInstallationResult
                        ? "post-operation-refresh"
                        : "device-or-navigation-refresh"
                )
                if preservingInstallationResult {
                    self?.installationResult = preservedInstallationResult
                    self?.installationPhase = preservedInstallationPhase
                    self?.installationPhaseProgress = preservedInstallationPhaseProgress
                    self?.installationPhaseProgressIsMeasured = preservedInstallationPhaseProgress != nil
                }
                self?.state = .scanned
            } catch {
                guard !Task.isCancelled else { return }

                self?.state = .failed
                self?.errorMessage = error.localizedDescription
                self?.userErrorMessage = UserFacingErrorMessage.forMapScan(error)
            }
        }
    }

    /// Validates and stages a user-selected raw IMG without changing the
    /// device. A ready candidate is added to the same selection/preflight
    /// model as provider maps, so the later installation path stays shared.
    func importCustomMap(fileURL: URL) {
        guard state == .scanned,
              installationPhase == .idle,
              !isBusy else {
            return
        }

        discardCustomMapImport()
        customMapImportState = .validating
        customMapImportErrorMessage = nil
        customMapImportRisk = nil
        customMapImportWarning = nil

        let acquirer = CustomMapSourceAcquirer()
        activeTask?.cancel()
        activeTask = Task { [weak self] in
            do {
                let candidate = try await CancellableDetached.run(priority: .userInitiated) {
                    try acquirer.prepare(fileURL: fileURL)
                }

                guard !Task.isCancelled else {
                    try? FileManager.default.removeItem(at: candidate.workspaceRootURL)
                    return
                }
                self?.customMapImportCandidate = candidate
                self?.customMapImportState = .ready
                self?.customMapImportErrorMessage = nil
                self?.appendCustomComparison(candidate.package)
                self?.customMapImportRisk = CustomMapImportRisk(
                    filename: candidate.originalFilename,
                    message: "Garmin IMG structure was detected, but Terento cannot verify who produced this file, whether its map data is complete, or guarantee that it is free from malicious content. Terento will not execute it or upload it. Continue only if you trust the source."
                )
            } catch {
                guard !Task.isCancelled else { return }
                self?.customMapImportState = .failed
                self?.customMapImportErrorMessage = error.localizedDescription
                if let acquisitionError = error as? MapAcquisitionError,
                   case .customMapNotConfirmed = acquisitionError {
                    self?.customMapImportWarning = CustomMapImportWarning(
                        filename: fileURL.lastPathComponent,
                        message: error.localizedDescription
                    )
                }
            }
        }
    }

    /// Discards only a local staged import. It never touches the Garmin.
    func clearCustomMapImport() {
        activeTask?.cancel()
        activeTask = nil
        discardCustomMapImport()
    }

    func dismissCustomMapImportWarning() {
        customMapImportWarning = nil
    }

    func acknowledgeCustomMapImportRisk() {
        guard customMapImportCandidate != nil else { return }
        customMapImportAcknowledged = true
        customMapImportRisk = nil
    }

    func dismissCustomMapImportRisk() {
        customMapImportRisk = nil
    }

    private func appendCustomComparison(_ package: MapPackage) {
        guard let result else { return }
        guard !result.comparisons.contains(where: { $0.catalogMap.id == package.id }) else {
            return
        }

        let customComparison = MapComparison(
            providerName: "Custom map",
            regionName: "Custom map",
            catalogMap: package,
            installedMap: nil,
            status: .notInstalled
        )
        self.result = MapInventoryResult(
            scan: result.scan,
            deviceFiles: result.deviceFiles,
            comparisons: result.comparisons + [customComparison]
        )
    }

    private func discardCustomMapImport() {
        if let workspaceRootURL = customMapImportCandidate?.workspaceRootURL {
            try? FileManager.default.removeItem(at: workspaceRootURL)
        }
        customMapImportCandidate = nil
        customMapImportState = .idle
        customMapImportErrorMessage = nil
        customMapImportWarning = nil
        customMapImportRisk = nil
        customMapImportAcknowledged = false
        if let result {
            self.result = MapInventoryResult(
                scan: result.scan,
                deviceFiles: result.deviceFiles,
                comparisons: result.comparisons.filter {
                    $0.catalogMap.sourceKind != .custom
                }
            )
        }
    }

    private nonisolated static func manifestDeviceKeys(
        for identity: DeviceIdentity?
    ) -> Set<String> {
        guard let identity else {
            return []
        }

        return manifestDeviceKeys(for: [identity])
    }

    private nonisolated static func manifestDeviceKeys(
        for identities: [DeviceIdentity?]
    ) -> Set<String> {
        Set(identities.compactMap { identity in
            identity?.localManifestDeviceKey
        })
    }

    private nonisolated static func loadOwnershipRecords(
        for identity: DeviceIdentity?
    ) -> [MapOwnershipRecord] {
        guard let identity else {
            return []
        }

        return loadOwnershipRecords(
            forDeviceKeys: manifestDeviceKeys(for: identity),
            recoveryIdentities: [identity]
        )
    }

    private nonisolated static func loadOwnershipRecords(
        forDeviceKeys deviceKeys: Set<String>,
        recoveryIdentities: [DeviceIdentity?] = []
    ) -> [MapOwnershipRecord] {
        let manifestRecords = deviceKeys.sorted().flatMap { deviceKey in
            let manifest = try? LocalTerentoManifestStore().read(
                deviceKey: deviceKey
            )
            return (manifest?.entries ?? []).map { entry in
                MapOwnershipRecord(
                    devicePath: entry.devicePath,
                    filename: entry.filename,
                    providerId: entry.providerId,
                    regionId: entry.regionId,
                    version: entry.version,
                    sizeBytes: entry.sizeBytes
                )
            }
        }

        let recoveryRecords = recoveryIdentities
            .compactMap { $0 }
            .flatMap { identity in
                loadFailedInstallRecoveryRecords(for: identity)
            }
            .map { record in
                MapOwnershipRecord(
                    devicePath: record.devicePath,
                    filename: record.filename,
                    providerId: record.providerId,
                    regionId: record.regionId,
                    version: record.version,
                    sizeBytes: record.sizeBytes
                )
            }

        return manifestRecords + recoveryRecords
    }

    private nonisolated static func loadFailedInstallRecoveryRecords(
        for identity: DeviceIdentity?
    ) -> [TerentoFailedInstallRecoveryRecord] {
        guard let identity else {
            return []
        }

        return (try? LocalTerentoFailedInstallRecoveryStore().read(
            deviceKey: identity.localManifestDeviceKey
        )) ?? []
    }

    private nonisolated static func failedInstallRecoveryRecords(
        for inventory: UnifiedMapInventory,
        identity: DeviceIdentity
    ) -> [TerentoFailedInstallRecoveryRecord] {
        // Recovery records are the only safe source for an incomplete write.
        // An unknown or legacy device object must remain read-only; it must
        // never be reconstructed from a filename or a heuristic size.
        let manifestEntries = (try? LocalTerentoManifestStore().read(
            deviceKey: identity.localManifestDeviceKey
        ))?.entries ?? []
        var records = loadFailedInstallRecoveryRecords(for: identity)
        records.removeAll { recoveryRecord in
            manifestEntries.contains { entry in
                recoveryRecord.matches(
                    deviceKey: identity.localManifestDeviceKey,
                    path: entry.devicePath,
                    filename: entry.filename,
                    sizeBytes: entry.sizeBytes,
                    providerId: entry.providerId,
                    regionId: entry.regionId,
                    version: entry.version
                )
            }
        }
        return records
    }

    var catalogRecordCount: Int {
        loadedCatalog?.packages.count ?? 0
    }

    var availableMapProviders: [MapProvider] {
        guard let loadedCatalog else { return [] }
        return loadedCatalog.sortedProviders
    }

    /// The canonical, catalog-backed list for the Choose screen. Unlike the
    /// diagnostic inventory, this list contains one row per provider/region
    /// and never adds a second row for an installed file.
    var mapSelectionItems: [MapSelectionItem] {
        guard let inventory = result,
              let identity = currentIdentity,
              let availableStorage = currentAvailableStorage else {
            return []
        }

        let preflightEngine = InstallationPreflightEngine()
        var preflightStatuses: [String: InstallationPreflightStatus] = [:]
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: inventory.deviceFiles
        )

        for comparison in inventory.comparisons {
            let preflight = preflightEngine.evaluate(
                identity: identity,
                selectedMap: comparison.catalogMap,
                comparison: comparison,
                installedMaps: inventory.scan.installedMaps,
                inspectedFiles: inventory.scan.files,
                availableStorage: availableStorage,
                profile: profile
            )
            preflightStatuses[comparison.id] = preflight.status
        }

        let recommendedRegionID = MapRegionRecommendation.regionID(
            systemRegionCode: Locale.current.region?.identifier,
            comparisons: inventory.comparisons
        )

        return MapSelectionPlanner().items(
            comparisons: inventory.comparisons,
            preflightStatuses: preflightStatuses,
            recommendedRegionID: recommendedRegionID
        )
    }

    func installationPlan(for selectedIDs: Set<String>) -> InstallationPlan? {
        guard let availableStorage = currentAvailableStorage,
              result != nil else {
            return nil
        }

        return MapSelectionPlanner().plan(
            items: mapSelectionItems,
            selectedIDs: selectedIDs,
            currentFreeSpace: availableStorage
        )
    }

    /// Builds the single inventory used by the lifecycle screen. The view
    /// must not rebuild ownership or comparison state independently because
    /// doing so could make a destructive action disagree with the scanner.
    func mapLifecycleInventory() -> MapLifecycleInventory? {
        guard let result else {
            return nil
        }

        let inventory = result.unifiedMapInventory()
        let recoveryRecords = currentIdentity.map {
            Self.failedInstallRecoveryRecords(for: inventory, identity: $0)
        } ?? []
        return MapLifecycleInventoryBuilder().build(
            from: inventory,
            recoveryRecords: recoveryRecords
        )
    }

    /// Resolves one lifecycle item together with the exact local integrity
    /// records needed by backup/delete/update. Manifest entries are matched by
    /// path, filename, size, identity, and version; a filename alone never
    /// grants an operation.
    func lifecycleContext(for itemID: String) -> MapLifecycleContext? {
        guard let result,
              let identity = currentIdentity,
              let availableStorage = currentAvailableStorage else {
            return nil
        }

        let inventory = result.unifiedMapInventory()
        let recoveryRecords = Self.failedInstallRecoveryRecords(
            for: inventory,
            identity: identity
        )
        let lifecycleInventory = MapLifecycleInventoryBuilder().build(
            from: inventory,
            recoveryRecords: recoveryRecords
        )
        guard let item = lifecycleInventory.item(id: itemID) else {
            return nil
        }

        let manifestEntries = ownershipManifestEntries(for: identity)
        let itemManifestEntry = item.installedMaps.compactMap { installedMap in
            manifestEntries.first { entry in
                entry.devicePath == installedMap.sourceFile.path
                    && entry.filename == installedMap.sourceFile.filename
                    && entry.sizeBytes == installedMap.sourceFile.sizeBytes
            }
        }.first
        let itemDeviceKey = itemManifestEntry?.deviceKey ?? identity.localManifestDeviceKey
        let itemMapIdentity = MapIdentity(provider: item.provider, region: item.region)
        let manifestMapIdentity = itemMapIdentity == nil
            ? item.installedMaps
                .compactMap { installedMap in
                    manifestEntries.first { entry in
                        entry.devicePath == installedMap.sourceFile.path
                            && entry.filename == installedMap.sourceFile.filename
                            && entry.sizeBytes == installedMap.sourceFile.sizeBytes
                            && MapIdentity.normalizeProvider(entry.providerId) == "custom"
                    }
                }
                .compactMap { MapIdentity(provider: $0.providerId, region: $0.regionId) }
                .first
            : nil
        let hashes = Dictionary(uniqueKeysWithValues: item.installedMaps.compactMap { installedMap -> (UInt32, String)? in
            guard let objectID = installedMap.sourceFile.itemID else {
                return nil
            }

            if installedMap.provider == nil,
               installedMap.region == nil,
               let manifestEntry = manifestEntries.first(where: { entry in
                   entry.devicePath == installedMap.sourceFile.path
                       && entry.filename == installedMap.sourceFile.filename
                       && entry.sizeBytes == installedMap.sourceFile.sizeBytes
                       && MapIdentity.normalizeProvider(entry.providerId) == "custom"
                       && (installedMap.version == nil || entry.version == installedMap.version)
               }),
               !manifestEntry.sha256.isEmpty {
                return (objectID, manifestEntry.sha256)
            }

            if let version = installedMap.version,
               let provider = installedMap.provider,
               let region = installedMap.region,
               let manifestEntry = manifestEntries.first(where: { entry in
                   entry.devicePath == installedMap.sourceFile.path
                       && entry.filename == installedMap.sourceFile.filename
                       && entry.sizeBytes == installedMap.sourceFile.sizeBytes
                       && MapIdentity.normalizeProvider(entry.providerId) == MapIdentity.normalizeProvider(provider)
                       && MapIdentity.normalizeRegion(entry.regionId) == MapIdentity.normalizeRegion(region)
                       && entry.version == version
               }),
               !manifestEntry.sha256.isEmpty {
                return (objectID, manifestEntry.sha256)
            }

            guard let recoveryRecord = recoveryRecords.first(where: { record in
                record.matches(
                    deviceKey: identity.localManifestDeviceKey,
                    path: installedMap.sourceFile.path,
                    filename: installedMap.sourceFile.filename,
                    sizeBytes: installedMap.sourceFile.sizeBytes,
                    providerId: installedMap.provider,
                    regionId: installedMap.region,
                    version: installedMap.version
                )
            }), !recoveryRecord.sha256.isEmpty else {
                return nil
            }

            return (objectID, recoveryRecord.sha256)
        })

        return MapLifecycleContext(
            item: item,
            comparison: inventory.allEntries.first(where: { $0.key == itemID })?.comparison,
            selectedMap: inventory.allEntries.first(where: { $0.key == itemID })?.catalogPackage,
            identity: identity,
            availableStorage: availableStorage,
            profile: DeviceInstallProfileRegistry.local.profile(
                for: identity,
                deviceFiles: result.deviceFiles
            ),
            deviceKey: itemDeviceKey,
            expectedSHA256ByItemID: hashes,
            mapIdentity: itemMapIdentity ?? manifestMapIdentity,
            failedInstallRecovery: item.failedInstallRecovery
        )
    }

    private func ownershipManifestEntries(
        for identity: DeviceIdentity
    ) -> [TerentoManifestEntry] {
        let keys = ownershipManifestDeviceKeys.isEmpty
            ? Set([identity.localManifestDeviceKey])
            : ownershipManifestDeviceKeys.union([identity.localManifestDeviceKey])

        var orderedKeys: [String] = []
        if let preferredOwnershipManifestDeviceKey,
           keys.contains(preferredOwnershipManifestDeviceKey) {
            orderedKeys.append(preferredOwnershipManifestDeviceKey)
        }
        if keys.contains(identity.localManifestDeviceKey),
           !orderedKeys.contains(identity.localManifestDeviceKey) {
            orderedKeys.append(identity.localManifestDeviceKey)
        }
        orderedKeys.append(contentsOf: keys.sorted().filter {
            !orderedKeys.contains($0)
        })

        return orderedKeys.flatMap { deviceKey in
            (try? LocalTerentoManifestStore().read(deviceKey: deviceKey))?.entries ?? []
        }
    }

    /// Refreshes the device-derived inventory after a successful lifecycle
    /// operation. This is read-only and reuses the normal scanner/catalog
    /// pipeline.
    func refreshCurrentDeviceMaps() {
        guard let identity = currentIdentity,
              let availableStorage = currentAvailableStorage else {
            return
        }

        scanDeviceMaps(
            deviceIdentity: identity,
            availableStorage: availableStorage,
            preservingInstallationResult: true
        )
    }

    var isPreparingArtifact: Bool {
        state == .acquiringArtifact
    }

    var isInstalling: Bool {
        state == .installing
    }

    /// True while any map lifecycle work owns the workflow, including the
    /// catalog/inventory phase before a native session is opened. Eject must
    /// remain unavailable for the whole operation, not only during transfer.
    var isBusy: Bool {
        if customMapImportState == .validating {
            return true
        }

        switch state {
        case .loadingCatalog, .scanning, .acquiringArtifact,
             .preparingInstallation, .installing:
            return true
        case .idle, .scanned, .failed:
            return false
        }
    }

    var isPreparingInstallation: Bool {
        state == .preparingInstallation
    }

    fileprivate func receiveAcquisitionState(_ state: MapAcquisitionState) {
        acquisitionState = state
        installationPhaseProgressIsMeasured = false

        switch state {
        case .resolvingPackage:
            installationPhase = .preparing
            installationPhaseProgress = 0
        case .downloading:
            installationPhase = .downloading
            installationPhaseProgress = nil
        case .validatingDownload:
            installationPhase = .preparing
            installationPhaseProgress = 0.2
        case .extracting:
            installationPhase = .preparing
            installationPhaseProgress = 0.4
        case .inspectingIMG:
            installationPhase = .preparing
            installationPhaseProgress = 0.6
        case .validatingIdentity:
            installationPhase = .preparing
            installationPhaseProgress = 0.75
        case .hashing:
            installationPhase = .preparing
            installationPhaseProgress = 0.9
        case .validated:
            installationPhase = .preparing
            installationPhaseProgress = 1
        case .failed:
            installationPhase = .failed
            installationPhaseProgress = nil
        case .idle:
            break
        }
    }

    fileprivate func receiveDownloadProgress(_ progress: MapDownloadProgress) {
        acquisitionProgress = progress
    }

    fileprivate func receiveInstallationProgress(_ progress: TransferProgress) {
        let updatedProgress = TransferProgress(
            bytesTransferred: progress.bytesTransferred,
            totalBytes: progress.totalBytes,
            bytesPerSecond: installationSpeedEstimator.update(bytes: progress.bytesTransferred)
        )
        if installationPhase == .finishing {
            finishingTransferProgress = updatedProgress
            if progress.totalBytes > 0 {
                let readBackFraction = progress.fractionCompleted
                let readBackProgress = 0.05 + (readBackFraction * 0.20)
                installationPhaseProgress = max(
                    installationPhaseProgress ?? 0.05,
                    min(0.25, readBackProgress)
                )
                installationPhaseProgressIsMeasured = true
            }
        } else {
            installationProgress = updatedProgress
        }
    }

    fileprivate func receiveInstallationPhase(_ phase: InstallationProcessPhase) {
        installationPhase = phase
        installationPhaseProgressIsMeasured = false

        switch phase {
        case .preparing:
            installationPhaseProgress = 0
        case .finishing:
            installationPhaseProgress = 0
            finishingTransferProgress = nil
            installationSpeedEstimator.reset()
        case .completed:
            installationPhaseProgress = 1
            finishingTransferProgress = nil
        default:
            installationPhaseProgress = nil
            if phase != .finishing {
                finishingTransferProgress = nil
            }
        }
    }

    fileprivate func receiveInstallationPhaseProgress(
        _ phase: InstallationProcessPhase,
        progress: Double
    ) {
        guard installationPhase == phase else {
            return
        }

        installationPhaseProgress = min(1, max(0, progress))
        installationPhaseProgressIsMeasured = true
    }

    /// Starts a catalog-driven installation. One or more selected maps are
    /// downloaded and validated first; device writes then run sequentially in
    /// one guarded operation. No second map is written if its own validation
    /// or preflight fails.
    func beginInstallation(plan: InstallationPlan) {
        guard state == .scanned,
              installationPhase == .idle,
              plan.canContinue,
              customMapImportReadyForInstallation,
              !plan.installItems.isEmpty else {
            return
        }

        installationAuthorizationGranted = true
        selectedInstallationPlan = plan
        selectedPreflight = nil
        installationResult = nil
        installationBatchResults = []
        evidenceFailureStage = nil
        evidenceFailure = nil
        evidenceNativeFailureCode = nil
        evidencePrimaryFailureMapIndex = nil
        TerentoDiagnosticLog.recordInstallationStarted(
            maps: plan.installItems.map(\.package)
        )
        let preflightIdentity = currentIdentity
        guard let identity = preflightIdentity,
              identity.localHardwareIdentifier?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            evidenceFailureStage = .preflight
            evidenceFailure = .stableWatchIdentityUnavailable
            if let identity = preflightIdentity,
               identity.garminDeviceXMLStatus == .ambiguous
                || identity.garminDeviceXMLStatus == .oversized
                || identity.garminDeviceXMLStatus == .readFailed {
                evidenceNativeFailureCode = .garminDeviceXMLInvalid
            } else {
                evidenceNativeFailureCode = .stableWatchIdentityUnavailable
            }
            installationErrorMessage = InstallationFailure.stableWatchIdentityUnavailable.userLabel
            installationPhase = .failed
            installationPhaseProgress = nil
            state = .failed
            recordInstallationFailure(installationErrorMessage)
            return
        }
        prepareInstallationArtifacts()
    }

    private func prepareInstallationArtifacts() {
        guard state == .scanned,
              let plan = selectedInstallationPlan,
              plan.canContinue,
              customMapImportReadyForInstallation else {
            return
        }

        state = .acquiringArtifact
        installationPhase = .preparing
        installationPhaseProgress = 0
        acquisitionState = .resolvingPackage
        acquisitionProgress = MapDownloadProgress(
            bytesDownloaded: 0,
            totalBytes: plan.installItems.first?.package.expectedDownloadSizeBytes ?? 0,
            bytesPerSecond: 0
        )
        acquisitionErrorMessage = nil
        validatedArtifacts = [:]
        installationResult = nil
        installationErrorMessage = nil

        let packages = plan.installItems.map(\.package)
        let acquirer = MapPackageAcquirer(
            providerHealthChecker: FoundationMapProviderHealthChecker()
        )
        let customAcquirer = CustomMapSourceAcquirer()
        let customCandidate = customMapImportCandidate
        let stateRelay = MapEngineAcquisitionRelay(engine: self)
        let progressRelay = MapEngineDownloadProgressRelay(engine: self)
        activeTask?.cancel()
        activeTask = Task { [weak self] in
            var activePackageIndex = 0
            do {
                var artifacts: [String: ValidatedMapArtifact] = [:]
                for (index, package) in packages.enumerated() {
                    activePackageIndex = index
                    try Task.checkCancellation()
                    let artifact: ValidatedMapArtifact
                    if package.sourceKind == .custom {
                        guard let customCandidate,
                              customCandidate.package.id == package.id else {
                            throw MapAcquisitionError.invalidPackage(
                                "The selected custom map is no longer available."
                            )
                        }
                        stateRelay.send(.validatingDownload)
                        artifact = try await CancellableDetached.run(priority: .userInitiated) {
                            try customAcquirer.revalidate(customCandidate)
                        }
                        stateRelay.send(.inspectingIMG)
                        stateRelay.send(.hashing)
                        stateRelay.send(.validated)
                    } else {
                        artifact = try await CancellableDetached.run(priority: .userInitiated) {
                            try await acquirer.acquire(
                                package: package,
                                canonicalRegion: package.canonicalRegionId,
                                onStateChange: { state in stateRelay.send(state) },
                                onDownloadProgress: { progress in progressRelay.send(progress) }
                            )
                        }
                    }
                    artifacts[package.id] = artifact
                }

                guard !Task.isCancelled else { return }
                self?.validatedArtifacts = artifacts
                self?.acquisitionState = .validated
                self?.state = .scanned
                Task { @MainActor [weak self] in
                    self?.prepareInstallationConfirmation()
                }
            } catch {
                guard !Task.isCancelled else { return }
                self?.evidencePrimaryFailureMapIndex = activePackageIndex
                if let acquisitionError = error as? MapAcquisitionError {
                    let diagnostic = Self.evidenceDiagnostic(for: acquisitionError)
                    self?.evidenceFailureStage = diagnostic.stage
                    self?.evidenceFailure = diagnostic.failure
                } else {
                    self?.evidenceFailureStage = .download
                    self?.evidenceFailure = .downloadFailed
                }
                self?.acquisitionState = .failed
                self?.acquisitionErrorMessage = error.localizedDescription
                self?.installationErrorMessage = error.localizedDescription
                self?.installationPhase = .failed
                self?.state = .failed
                self?.recordInstallationFailure(
                    error.localizedDescription,
                    technicalError: String(reflecting: error)
                )
            }
        }
    }

    /// Runs a no-write preflight for every selected package. The actual device
    /// write is reachable only after all selected packages pass this phase.
    private func prepareInstallationConfirmation() {
        guard let plan = selectedInstallationPlan,
              let inventory = result,
              let identity = currentIdentity,
              let availableStorage = currentAvailableStorage,
              !validatedArtifacts.isEmpty else {
            return
        }

        state = .preparingInstallation
        installationPhase = .preparing
        installationPhaseProgress = 0
        installationErrorMessage = nil
        let artifacts = validatedArtifacts
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: inventory.deviceFiles
        )
        let coordinator = MapInstallationCoordinator.live()
        let activeMapIndex = InstallationMapIndexState()
        activeTask?.cancel()
        activeTask = Task { [weak self] in
            do {
                let results = try await CancellableDetached.run(priority: .userInitiated) {
                    var results: [MapInstallationResult] = []
                    for (index, item) in plan.installItems.enumerated() {
                        activeMapIndex.set(index)
                        guard let artifact = artifacts[item.package.id],
                              let comparison = inventory.comparisons.first(where: {
                                  $0.catalogMap.id == item.package.id
                              }) else {
                            throw MapAcquisitionError.invalidPackage(
                                "The selected catalog entry is unavailable."
                            )
                        }

                        let request = MapInstallationRequest(
                            identity: identity,
                            selectedMap: comparison.catalogMap,
                            comparison: comparison,
                            installedMaps: inventory.scan.installedMaps,
                            inspectedFiles: inventory.scan.files,
                            beforeDeviceFiles: inventory.deviceFiles,
                            availableStorage: availableStorage,
                            profile: profile,
                            artifact: artifact,
                            userConfirmed: false
                        )
                        let result = coordinator.run(request)
                        results.append(result)
                        guard result.status == .confirmationRequired else { break }
                    }
                    return results
                }

                guard !Task.isCancelled, let first = results.first else { return }
                let allReady = results.count == plan.installItems.count
                    && results.allSatisfy { $0.status == .confirmationRequired }
                let finalResult = allReady ? first : (results.last ?? first)
                self?.installationResult = finalResult
                self?.selectedPreflight = first.preflight
                self?.installationProgress = TransferProgress(
                    bytesTransferred: 0,
                    totalBytes: artifacts[plan.installItems.first!.package.id]?.installSizeBytes ?? 0
                )
                self?.installationErrorMessage = finalResult.failure?.userLabel
                self?.installationPhase = allReady ? .awaitingConfirmation : .failed
                self?.installationPhaseProgress = allReady ? 1 : nil
                self?.state = .scanned

                if !allReady {
                    self?.evidencePrimaryFailureMapIndex = results.firstIndex {
                        $0.status != .confirmationRequired
                    } ?? activeMapIndex.value
                    self?.evidenceFailureStage = Self.evidenceStage(for: finalResult.failure)
                    self?.evidenceFailure = finalResult.failure
                    self?.recordInstallationFailure(finalResult.failure?.userLabel)
                }

                let shouldContinue = InstallationFlowPresentation.shouldContinueAfterPreflight(
                    userAuthorized: self?.installationAuthorizationGranted == true,
                    preflightSucceeded: allReady
                )
                if shouldContinue {
                    Task { @MainActor [weak self] in
                        self?.installSelectedMaps()
                    }
                }
            } catch {
                guard !Task.isCancelled else { return }
                self?.evidencePrimaryFailureMapIndex = activeMapIndex.value
                if let acquisitionError = error as? MapAcquisitionError {
                    let diagnostic = Self.evidenceDiagnostic(for: acquisitionError)
                    self?.evidenceFailureStage = diagnostic.stage
                    self?.evidenceFailure = diagnostic.failure
                } else {
                    self?.evidenceFailureStage = .preflight
                    self?.evidenceFailure = .sourceArtifactInvalid
                }
                self?.installationErrorMessage = error.localizedDescription
                self?.installationPhase = .failed
                self?.installationPhaseProgress = nil
                self?.state = .failed
                self?.recordInstallationFailure(
                    error.localizedDescription,
                    technicalError: String(reflecting: error)
                )
            }
        }
    }

    /// Re-reads the device before each selected map write and executes the
    /// shared coordinator sequentially. A successful batch refreshes the
    /// catalog-backed inventory so Install and Manage show the same state.
    func installSelectedMaps() {
        guard let plan = selectedInstallationPlan,
              installationResult?.status == .confirmationRequired,
              validatedArtifacts.count == plan.installItems.count,
              state != .installing else {
            return
        }

        state = .installing
        installationBatchResults = []
        installationPhase = .installing
        installationPhaseProgress = nil
        installationSpeedEstimator.reset()
        installationProgress = TransferProgress(
            bytesTransferred: 0,
            totalBytes: validatedArtifact?.installSizeBytes ?? 0
        )
        installationErrorMessage = nil

        let operationGate = self.operationGate
        let artifacts = validatedArtifacts
        let sessionIdentity = currentIdentity
        let sessionManifestDeviceKeys = ownershipManifestDeviceKeys
        let customPackages = plan.installItems
            .map(\.package)
            .filter { $0.sourceKind == .custom }
        let catalog = loadedCatalog
        let progressRelay = MapEngineProgressRelay(engine: self)
        let phaseRelay = MapEnginePhaseRelay(engine: self)
        let phaseProgressRelay = MapEnginePhaseProgressRelay(engine: self)
        let activeMapIndex = InstallationMapIndexState()
        activeTask?.cancel()
        activeTask = Task { [weak self] in
            do {
                guard let catalog else {
                    throw MapAcquisitionError.invalidPackage("The selected map catalog is unavailable.")
                }

                let results = try await CancellableDetached.run(priority: .userInitiated) {
                    let lease = try await operationGate.beginLifecycleAsync()
                    defer { operationGate.endLifecycle(lease) }

                    var results: [MapInstallationResult] = []
                    for (index, item) in plan.installItems.enumerated() {
                        activeMapIndex.set(index)
                        guard let artifact = artifacts[item.package.id] else {
                            throw MapAcquisitionError.invalidPackage(
                                "The validated source for the selected map is unavailable."
                            )
                        }

                        let lifecycleReader = MTPTransport(
                            operationGate: operationGate,
                            lifecycleLease: lease
                        )
                        let snapshot = try lifecycleReader.readSnapshot()
                        let identity = CompatibilityEngine().evaluate(snapshot: snapshot).identity
                        let inventory = try MapInventoryEngine(
                            reader: lifecycleReader,
                            catalog: catalog,
                            ownershipRecords: Self.loadOwnershipRecords(
                                forDeviceKeys: Set(
                                    sessionManifestDeviceKeys
                                        .union(Self.manifestDeviceKeys(for: identity))
                                ),
                                recoveryIdentities: [sessionIdentity, identity]
                            ),
                            additionalPackages: customPackages
                        ).scan()
                        guard let comparison = inventory.comparisons.first(where: {
                            $0.catalogMap.id == item.package.id
                        }) else {
                            throw MapAcquisitionError.invalidPackage(
                                "The selected catalog entry is unavailable."
                            )
                        }

                        let installProfile = DeviceInstallProfileRegistry.local.profile(
                            for: identity,
                            deviceFiles: inventory.deviceFiles
                        )
                        let operationProfile = DeviceMapOperationProfile(
                            identity: identity,
                            installProfile: installProfile
                        )

                        let request = MapInstallationRequest(
                            identity: identity,
                            selectedMap: comparison.catalogMap,
                            comparison: comparison,
                            installedMaps: inventory.scan.installedMaps,
                            inspectedFiles: inventory.scan.files,
                            beforeDeviceFiles: inventory.deviceFiles,
                            availableStorage: snapshot.freeSpace,
                            profile: installProfile,
                            artifact: artifact,
                            userConfirmed: true
                        )

                        let result = MapInstallationCoordinator.live(
                            operationProfile: operationProfile,
                            operationGate: operationGate,
                            lifecycleLease: lease
                        ).run(
                            request,
                            onProgress: { progress in progressRelay.send(progress) },
                            onPhase: { phase in phaseRelay.send(phase) },
                            onPhaseProgress: { phase, progress in
                                phaseProgressRelay.send(phase, progress)
                            }
                        )
                        results.append(result)
                        guard result.isSuccess else { break }
                    }
                    return results
                }

                guard !Task.isCancelled, let finalResult = results.last else { return }
                let batchSucceeded = results.count == plan.installItems.count
                    && results.allSatisfy(\.isSuccess)
                self?.installationResult = finalResult
                self?.installationBatchResults = results
                self?.selectedPreflight = finalResult.preflight
                self?.installationProgress = TransferProgress(
                    bytesTransferred: finalResult.diagnostics.bytesTransferred,
                    totalBytes: finalResult.diagnostics.transferTotalBytes,
                    bytesPerSecond: 0
                )
                self?.installationErrorMessage = finalResult.failure?.userLabel
                self?.installationPhase = batchSucceeded ? .completed : .failed
                self?.installationPhaseProgress = batchSucceeded ? 1 : nil
                self?.state = batchSucceeded ? .scanned : .failed
                if batchSucceeded {
                    self?.refreshCurrentDeviceMaps()
                } else {
                    self?.evidenceFailureStage = Self.evidenceStage(for: finalResult.failure)
                    self?.evidenceFailure = finalResult.failure
                    self?.recordInstallationFailure(finalResult.failure?.userLabel)
                }
            } catch {
                guard !Task.isCancelled else { return }
                self?.evidencePrimaryFailureMapIndex = activeMapIndex.value
                self?.evidenceFailureStage = .preflight
                self?.evidenceFailure = .deviceDisconnected
                self?.evidenceNativeFailureCode = .preflightMTPReadFailed
                self?.installationErrorMessage = error.localizedDescription
                self?.installationPhase = .failed
                self?.installationPhaseProgress = nil
                self?.state = .failed
                self?.recordInstallationFailure(
                    error.localizedDescription,
                    technicalError: String(reflecting: error)
                )
            }
        }
    }

    private static func evidenceDiagnostic(
        for error: MapAcquisitionError
    ) -> (stage: EvidenceFailureStage, failure: InstallationFailure) {
        switch error {
        case .acquisitionWithheld:
            return (.preflight, .sourceArtifactInvalid)
        case .downloadFailed, .providerUnavailable, .downloadIncomplete, .untrustedSourceURL:
            return (.download, .downloadFailed)
        case .workspaceFailed, .unsafeArchivePath, .extractionFailed:
            return (.extract, .sourceValidationFailed)
        case .unsupportedPackageFormat, .invalidPackage, .sourceIdentityMismatch,
             .sourceVersionMismatch, .noIMGFound, .ambiguousIMG:
            return (.sourceValidation, .sourceValidationFailed)
        case .customMapNotConfirmed:
            return (.sourceValidation, .sourceValidationFailed)
        }
    }

    private static func evidenceStage(for failure: InstallationFailure?) -> EvidenceFailureStage {
        switch failure {
        case .manifestFailed: return .manifest
        case .cleanupFailed: return .cleanup
        case .sizeMismatch, .hashMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired:
            return .verify
        case .writeFailed, .deviceDisconnected: return .write
        case .sourceArtifactInvalid, .sourceValidationFailed: return .sourceValidation
        default: return .preflight
        }
    }

    private func recordInstallationFailure(
        _ message: String?,
        technicalError: String? = nil
    ) {
        TerentoDiagnosticLog.recordInstallationFailure(
            maps: selectedInstallationPlan?.installItems.map(\.package) ?? [],
            phase: installationPhase,
            engineState: state,
            acquisitionState: acquisitionState,
            message: message,
            technicalError: technicalError,
            acquisitionError: acquisitionErrorMessage,
            preflight: selectedPreflight,
            result: installationResult,
            inventory: result
        )
    }
}

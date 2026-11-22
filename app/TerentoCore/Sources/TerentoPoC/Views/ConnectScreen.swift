import AppKit
#if TERENTO_APP_STORE
import StoreKit
#endif
import SwiftUI
import UniformTypeIdentifiers

enum LocalInstallStep: String, CaseIterable, Identifiable {
    case choose = "Choose"
    case install = "Install"
    case done = "Done"

    var id: String { rawValue }
}

private enum InstallationStepState {
    case complete
    case active
    case pending
    case failed
}

private enum InstallationTimelineLayout {
    static let markerSize: CGFloat = 24
    static let connectorWidth: CGFloat = 2
    static let progressBarHeight: CGFloat = 6
    /// Fits the longest removal step, "Checking map contents before removal"
    /// (224 pt in Inter caption), on one line.
    static let manageProgressWidth: CGFloat = 236
}

struct ConnectScreen: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var lifecycleViewModel: MapLifecycleViewModel
    @ObservedObject var evidenceController: InstallationEvidenceController
    @ObservedObject var mapStatisticsController: MapStatisticsEventController
    @ObservedObject var appUpdateController: AppUpdateController
    @State private var selectedSection: TerentoSection = .device
    #if !TERENTO_APP_STORE
    @State private var showsDonationLine = false
    #endif
    @State private var localInstallStep: LocalInstallStep = .choose
    @State private var selectedMapIDs: Set<String> = []
    @State private var selectedOptionalArtifactIDs: [String: Set<String>] = [:]
    @State private var selectedInstallationPlan: InstallationPlan?
    @State private var importedMapsExpanded = false
    @State private var externalMapsExpanded = false
    @State private var expandedProviderMapGroups: Set<String> = []
    @State private var customMapImportExpanded = false
    @State private var customMapImportDidContinue = false
    @State private var updatePrompt: TerentoAppUpdateManifest?
    // UI snapshots: rebuilding catalog/preflight rows during View.body blocks
    // scrolling and every keystroke. Refresh only when their inputs change.
    @State private var mapSelectionItems: [MapSelectionItem] = []
    @State private var providerMapSelectionItems: [MapSelectionItem] = []
    @State private var catalogPresentationIndex = MapCatalogPresentationIndex(items: [])
    @State private var selectedGeography: MapGeographyGroup = .all
    @State private var revealedSelectionID: String?
    @State private var filteredAvailableSelectionItems: [MapSelectionItem] = []
    @State private var managedInventory: MapLifecycleInventory?
    @State private var managedPresentationIndex: MapInventoryListPresentationIndex?
    @State private var filteredManagedInventory: MapLifecycleInventory?
    // Read-only Garmin images. Kept apart from the lifecycle inventory so no
    // Remove, Update or storage path can reach them.
    @State private var managedGarminMaps: [GarminSystemMap] = []
    @State private var visibleGarminSummary: GarminMapsSummary?
    // The map in the last Remove dialog, and maps removed since the last fresh list.
    @State private var removingManagedMapID: String?
    @State private var removedManagedMapIDs: Set<String> = []
    // Row actions from the last full list, drawn disabled while a rescan keeps that list.
    @State private var keptManagedAvailability: [String: MapLifecycleActionAvailability] = [:]
    @State private var managedSearchText = ""
    @State private var managedProviderID = ""
    @FocusState private var managedSearchFocused: Bool
    @State private var displayedInstallationPlan: InstallationPlan?
    @State private var mapSearchText = ""
    @State private var selectedMapProviderID = ""
    @State private var isShowingCustomMapImporter = false
    @State private var customMapDropTargeted = false
    @FocusState private var mapSearchFieldFocused: Bool
    @State private var resolvedDeviceAsset = ResolvedDeviceAsset.fallback
    @State private var diagnosticLogMessage: String?
    @State private var isShowingInstallationFailure = false
    #if TERENTO_APP_STORE
    /// The sharing question waiting for an answer, after the installation or
    /// update it would share. Shown on that operation's page only.
    @State private var sharingQuestion: SharingQuestion?
    /// The operation whose rating request waits until its page is on screen.
    @State private var pendingReviewRequest: UUID?
    @Environment(\.requestReview) private var requestReview
    #endif
    @State private var supportReportPayload: SupportReportPayload?
    @State private var supportReportSummary: String?
    @State private var installationFailureFollowUp: InstallationFailureFollowUp = .backToDevice
    @State private var retryInstallationAfterScan = false
    @State private var watchReconnectWait: WatchReconnectWait?
    @State private var watchReconnectFollowUp: WatchReconnectFollowUp?
    @State private var installationFailureOverride: InstallationFailureOverride?
    @State private var installationFailureSnapshot: InstallationFailureSnapshot?
    @State private var evidenceOperationID = UUID()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.openWindow) private var openWindow

    private var snapshot: DeviceSnapshot? {
        deviceEngine.snapshot
    }

    private var identity: DeviceIdentity? {
        if let identity = deviceEngine.compatibility?.identity {
            return identity
        }
        guard let snapshot = deviceEngine.snapshot else { return nil }
        return GarminDeviceIdentityAdapter().makeIdentity(from: snapshot)
    }

    private var currentDeviceFreeSpace: UInt64? {
        deviceEngine.snapshot?.freeSpace
    }

    private var authorizationPresentation: DeviceAuthorizationPresentation {
        DeviceAuthorizationPresentation(deviceEngine.installationAuthorization)
    }

    /// Map lifecycle access is determined from the live MTP scan, not from a
    /// model allowlist. This keeps Manage maps available for every Garmin
    /// watch that has a Terento-owned map; the lifecycle resolver remains
    /// fail-closed until the exact live profile and manifest are verified.
    private var canOpenMapSections: Bool {
        deviceEngine.hasConnectedDevice
    }

    private var mapProviderOptions: [MapProviderFilterOption] {
        MapProviderDisplay.filterOptions(providers: mapEngine.availableMapProviders)
    }

    private var customMapSelectionItems: [MapSelectionItem] {
        mapSelectionItems.filter { $0.package.sourceKind == .custom }
    }

    private func refreshMapSelectionPresentation() {
        mapSelectionItems = mapEngine.mapSelectionItems
        refreshManagedPresentation()
        catalogPresentationIndex = MapCatalogPresentationIndex(items: mapSelectionItems)
        refreshProviderPresentation()
        refreshDisplayedInstallationPlan()
    }

    private func refreshProviderPresentation() {
        let providerID = MapIdentity.normalizeProvider(selectedMapProviderID)
        providerMapSelectionItems = mapSelectionItems.filter { item in
            item.package.sourceKind == .provider
                && (selectedMapProviderID.isEmpty
                    || MapProviderDisplay.filterID(providerID: item.package.providerId,
                        regionID: item.package.canonicalRegionId) == providerID)
        }
        refreshSearchPresentation()
    }

    private func refreshSearchPresentation() {
        filteredAvailableSelectionItems = catalogPresentationIndex.filtered(
            query: mapSearchText,
            providerID: selectedMapProviderID,
            geography: selectedGeography
        )
    }

    private func refreshDisplayedInstallationPlan() {
        // Display only. Continue still requests a fresh authoritative plan.
        displayedInstallationPlan = currentInstallationPlan
    }

    private func isMapSelectionEnabled(_ item: MapSelectionItem) -> Bool {
        MapSelectionPresentationModel.isSelectionEnabled(
            item,
            selectedIDs: selectedMapIDs,
            items: mapSelectionItems
        )
    }

    private var customMapImportIsBusy: Bool {
        mapEngine.customMapImportState == .validating
    }

    private var planContainsOnlyCustomMaps: Bool {
        guard let plan = selectedInstallationPlan,
              !plan.installItems.isEmpty else {
            return false
        }
        return plan.installItems.allSatisfy { $0.package.sourceKind == .custom }
    }

    private var currentInstallationPlan: InstallationPlan? {
        guard mapEngine.customMapImportReadyForInstallation else {
            return nil
        }
        return mapEngine.installationPlan(
            for: selectedMapIDs,
            selectedOptionalArtifactIDs: selectedOptionalArtifactIDs
        )
    }

    private var installationFlowHasStarted: Bool {
        InstallationFlowPresentation.hasStarted(mapEngine.installationPhase)
    }

    private var installationOperationIsActive: Bool {
        InstallationFlowPresentation.isActive(mapEngine.installationPhase)
    }

    private var canSafelyEject: Bool {
        SafeEjectPolicy.canEject(
            isConnected: deviceEngine.hasConnectedDevice,
            transportAvailable: deviceEngine.canEject,
            mapOperationBusy: mapEngine.isBusy,
            lifecycleOperationBusy: lifecycleViewModel.isBusy,
            installationActive: installationOperationIsActive
        )
    }

    /// The map scan that follows every connection is still running.
    private var isReadingDeviceMaps: Bool {
        mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
    }

    private var mapManagementActionsBusy: Bool {
        mapEngine.isBusy
            || lifecycleViewModel.isBusy
            || installationOperationIsActive
    }

    private var updatePresentationIsSafe: Bool {
        !deviceEngine.isReading
            && deviceEngine.state != .ejecting
            && !mapEngine.isBusy
            && !lifecycleViewModel.isBusy
            && !installationOperationIsActive
            && updatePrompt == nil
            && watchReconnectWait == nil
            && !isShowingInstallationFailure
    }

    var body: some View {
        HStack(spacing: 0) {
            TerentoSidebar(
                selectedSection: $selectedSection,
                connectionState: deviceEngine.state,
                detectionPhase: deviceEngine.detectionPhase,
                canEject: canSafelyEject,
                isInstalling: installationOperationIsActive,
                // The reconnect wait replaces the page until it ends, as its dialog did.
                navigationLocked: installationOperationIsActive || watchReconnectWait != nil,
                mapNavigationEnabled: canOpenMapSections,
                // The Device page has its own "Eject device" button.
                showsEject: selectedSection != .device || snapshot == nil,
                onNavigate: navigate,
                onEject: performSafeEject
            )

            Rectangle()
                .fill(TerentoColors.sidebarBorder)
                .frame(width: 1)

            mainContent
        }
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
        .frame(
            minWidth: TerentoWindowPresentation.minimumWidth,
            minHeight: TerentoWindowPresentation.minimumHeight
        )
        .transaction { transaction in
            if reduceMotion {
                transaction.animation = nil
            }
        }
        .task {
            guard deviceEngine.state == .disconnected else { return }
            deviceEngine.readDevice()
        }
        .task(id: deviceAssetTaskKey) {
            guard let identity else {
                resolvedDeviceAsset = .fallback
                return
            }

            resolvedDeviceAsset = await DeviceAssetResolver().resolve(identity: identity)
        }
        .onChange(of: deviceEngine.state) { newState in
            if newState != .connected && newState != .ready {
                resolvedDeviceAsset = .fallback
                selectedSection = .device
                localInstallStep = .choose
                selectedMapIDs.removeAll()
                selectedOptionalArtifactIDs.removeAll()
                selectedInstallationPlan = nil
                selectedMapProviderID = ""
                lifecycleViewModel.resetForDisconnectedDevice()
                mapEngine.resetForDisconnectedDevice(presence: deviceEngine.invalidationDevicePresence)
                watchReconnectWait?.watchWasDisconnected = true
            }

            guard newState == .connected || newState == .ready else {
                return
            }

            selectedSection = .device
            localInstallStep = .choose
            mapEngine.scanDeviceMaps(
                deviceIdentity: identity,
                availableStorage: deviceEngine.snapshot?.freeSpace
            )
        }
        .onChange(of: mapEngine.state) { newState in
            updatePresenceMonitoring(for: newState)
            // A rescan that ends without a list replaces the kept list.
            if mapEngine.result == nil, managedInventory != nil { refreshManagedPresentation() }
            continueRetryAfterScanIfReady(newState)
            continueWatchReconnectWaitIfReady()
        }
        .onChange(of: mapEngine.customMapImportState) { _ in
            updatePresenceMonitoring(for: mapEngine.state)
        }
        .onChange(of: mapEngine.customMapImportCandidate?.id) { candidateID in
            guard let candidateID else { return }
            customMapImportExpanded = true
            selectedMapIDs.insert(candidateID)
        }
        .onAppear {
            refreshMapSelectionPresentation()
            mapEngine.setInstallationAuthorization(deviceEngine.installationAuthorization)
        }
        .onChange(of: deviceEngine.installationAuthorization) { authorization in
            mapEngine.setInstallationAuthorization(authorization)
            continueWatchReconnectWaitIfReady()
        }
        .task(id: watchReconnectWait?.id) {
            guard let deadline = watchReconnectWait?.deadline else { return }
            let remaining = deadline.timeIntervalSinceNow
            if remaining > 0 {
                try? await Task.sleep(for: .seconds(remaining))
            }
            guard !Task.isCancelled else { return }
            continueWatchReconnectWaitIfReady()
        }
        .onChange(of: mapEngine.latestDeviceStorage) { storage in
            guard let storage else { return }
            deviceEngine.refreshStorage(storage)
        }
        .onChange(of: mapEngine.freshInstallationAuthorization) { fresh in
            guard let fresh else { return }
            deviceEngine.applyFreshInstallationAuthorization(fresh.state, for: fresh.identity)
        }
        .onReceive(Timer.publish(every: 300, on: .main, in: .common).autoconnect()) { _ in
            deviceEngine.retryInstallationAuthorizationIfUnavailable()
            // Never refresh (and prune selections) during review or install.
            guard !lifecycleViewModel.isBusy, selectedInstallationPlan == nil else { return }
            Task { await mapEngine.refreshCatalogAvailability() }
        }
        .onChange(of: mapEngine.result) { _ in refreshMapSelectionPresentation() }
        .onChange(of: selectedMapProviderID) { _ in refreshProviderPresentation() }
        .onChange(of: mapSearchText) { _ in refreshSearchPresentation() }
        .onChange(of: selectedGeography) { _ in refreshSearchPresentation() }
        .onChange(of: managedSearchText) { _ in refreshManagedFilters() }
        .onChange(of: managedProviderID) { _ in refreshManagedFilters() }
        .onChange(of: lifecycleViewModel.pendingConfirmation) { confirmation in
            guard let confirmation, confirmation.action == .remove else { return }
            removingManagedMapID = confirmation.itemID
        }
        .onChange(of: selectedMapIDs) { _ in refreshDisplayedInstallationPlan() }
        .onChange(of: selectedOptionalArtifactIDs) { _ in refreshDisplayedInstallationPlan() }
        .onChange(of: mapEngine.customMapImportReadyForInstallation) { _ in
            refreshDisplayedInstallationPlan()
        }
        .onChange(of: mapSelectionItems) { items in
            selectedMapIDs = MapSelectionPresentationModel.validSelectionIDs(
                selectedMapIDs,
                items: items
            )
            let validIDs = Set(items.map(\.id))
            selectedOptionalArtifactIDs = selectedOptionalArtifactIDs.reduce(
                into: [:]
            ) { result, entry in
                guard validIDs.contains(entry.key),
                      let item = items.first(where: { $0.id == entry.key }) else {
                    return
                }
                result[entry.key] = entry.value.intersection(
                    Set(item.usableOptionalArtifacts.map(\.id))
                )
            }
        }
        .onChange(of: mapProviderOptions) { providers in
            guard !selectedMapProviderID.isEmpty else { return }
            let isStillAvailable = providers.contains {
                MapIdentity.normalizeProvider($0.id)
                    == MapIdentity.normalizeProvider(selectedMapProviderID)
            }
            if !isStillAvailable {
                selectedMapProviderID = ""
            }
        }
        .onChange(of: mapEngine.installationPhase) { phase in
            updatePresenceMonitoring(for: mapEngine.state)
            if phase == .failed {
                installationFailureSnapshot = makeInstallationFailureSnapshot()
                if let wait = makeWatchReconnectWait() {
                    watchReconnectWait = wait
                    mapEngine.recordReconnectWait(.shown)
                } else {
                    isShowingInstallationFailure = true
                }
            } else {
                diagnosticLogMessage = nil
            }
            if phase == .completed {
                selectedSection = .installMaps
                localInstallStep = .done
                // A partial installation is not a successful operation.
                #if TERENTO_APP_STORE
                if hasPartialInstallation {
                    sharingQuestion = nil
                } else {
                    handleSuccessfulOperation(operationID: evidenceOperationID, isUpdate: false)
                }
                #else
                showsDonationLine = !hasPartialInstallation
                    && DonationPromptPolicy.recordSuccessfulOperation(version: TerentoTelemetryMetadata.version)
                #endif
            }
        }
        // A verified map update counts like a completed installation.
        .onChange(of: lifecycleViewModel.lastSuccessfulUpdate) { update in
            #if TERENTO_APP_STORE
            if let update { handleSuccessfulOperation(operationID: update.operationID, isUpdate: true) }
            #else
            if update != nil {
                DonationPromptPolicy.recordSuccessfulOperation(version: TerentoTelemetryMetadata.version, mayShow: false)
            }
            #endif
        }
        #if TERENTO_APP_STORE
        // The rating request runs outside any view update, once the page of
        // the operation (Map installed, or Manage maps after an update) has
        // been on screen for a moment. Navigation state is not touched here.
        .task(id: pendingReviewRequest) {
            guard pendingReviewRequest != nil else { return }
            try? await Task.sleep(for: AppStoreReviewPolicy.requestDelay)
            guard !Task.isCancelled, pendingReviewRequest != nil else { return }
            pendingReviewRequest = nil
            requestReview()
        }
        // Leaving Manage maps without choosing leaves the question unanswered,
        // like leaving the Done page; it counts as one of the two asks.
        .onChange(of: selectedSection) { section in
            if section != .manageMaps, sharingQuestion?.isUpdate == true { sharingQuestion = nil }
        }
        #endif
        .onChange(of: lifecycleViewModel.isBusy) { _ in
            updatePresenceMonitoring(for: mapEngine.state)
        }
        // App Store builds have no update check, so no update prompt either.
        #if !TERENTO_APP_STORE
        .onAppear {
            presentUpdatePromptIfSafe()
        }
        .onChange(of: appUpdateController.state) { _ in
            presentUpdatePromptIfSafe()
        }
        .onChange(of: updatePresentationIsSafe) { _ in
            presentUpdatePromptIfSafe()
        }
        #endif
        .sheet(
            isPresented: $isShowingInstallationFailure,
            onDismiss: handleInstallationFailureDismissed
        ) {
            InstallationFailureDialog(
                mapTitle: installationFailureDialogMapTitle,
                reason: installationFailureReason,
                safetyMessage: installationFailureSafetyMessage,
                reportError: diagnosticLogMessage,
                onReportIssue: { reportInstallationIssue(for: selectedInstallationPlan) },
                onBackToDevice: {
                    installationFailureFollowUp = .backToDevice
                    isShowingInstallationFailure = false
                },
                onTryAgain: mapEngine.canRetryFailedInstallation && selectedInstallationPlan != nil ? {
                    installationFailureFollowUp = .tryAgain
                    isShowingInstallationFailure = false
                } : nil,
                onManageMaps: mapEngine.installationResult?.mayHaveLeftMapOnWatch == true ? {
                    installationFailureFollowUp = .manageMaps
                    isShowingInstallationFailure = false
                } : nil,
                helpTopic: installationFailureHelpTopic,
                onSendSupportReport: offersInstallationSupportReport
                    ? { sendInstallationSupportReport(for: selectedInstallationPlan) } : nil
            )
            .sheet(item: $supportReportPayload) { payload in
                SupportReportSheet(controller: SupportReportController(payload: payload),
                                   summary: supportReportSummary,
                                   onClose: { supportReportPayload = nil })
            }
            .interactiveDismissDisabled(false)
        }
    }

    #if TERENTO_APP_STORE
    /// After one successful installation or update, App Store builds show at
    /// most one thing: the sharing question while no choice is recorded
    /// (asked twice at most), otherwise, from the second success and once
    /// per version, the macOS rating request (AppStoreReviewPolicy).
    private func handleSuccessfulOperation(operationID: UUID, isUpdate: Bool) {
        switch AppStoreReviewPolicy.recordSuccessfulOperation(
            version: TerentoTelemetryMetadata.version,
            sharingUndecided: evidenceController.needsSharingDecision) {
        case .sharingQuestion:
            sharingQuestion = SharingQuestion(operationID: operationID, isUpdate: isUpdate)
        case .review:
            sharingQuestion = nil
            // Not from here: this runs inside the view update that opens
            // Map installed. Requested here, the 2026-11-21 local test lost the
            // Done page. The request waits for `.task(id: pendingReviewRequest)`
            // instead, after the page is on screen.
            pendingReviewRequest = operationID
        case .none:
            sharingQuestion = nil
        }
    }

    /// Share, Not now or Don't share in the sharing callout; nothing is
    /// pre-selected. Not now records no choice: the question comes back once,
    /// after the next successful operation, and then no more.
    private func decideSharing(_ decision: SharingDecision) {
        guard let question = sharingQuestion else { return }
        sharingQuestion = nil
        guard decision != .notNow else { return }
        let share = decision == .share
        evidenceController.decideConsent(share ? .accepted : .declined)
        // A map usage refusal carried over from the DMG app stands.
        if mapStatisticsController.store.consent() == nil {
            mapStatisticsController.decideConsent(share ? .accepted : .declined)
        }
        if share { evidenceController.shareOperation(question.operationID) }
    }
    #endif

    private var mainContent: some View {
        Group {
            if let wait = watchReconnectWait {
                // The wait stays in place across the unplug, which resets the
                // section to Device, until it continues or ends.
                watchReconnectWaitContent(wait)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else if selectedSection == .installMaps {
                if localInstallStep == .choose {
                    mapsContent
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if localInstallStep == .install {
                    installContent
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                } else {
                    finishContent
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
            } else if selectedSection == .device && snapshot == nil {
                connectContent
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if selectedSection == .manageMaps {
                managedMapsContent
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else {
                ScrollView {
                    workflowContent
                }
                .scrollIndicators(.automatic)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        #if !TERENTO_APP_STORE
        // An offer, not a dialog: one quiet line at the top of Device.
        .safeAreaInset(edge: .top, spacing: 0) {
            if selectedSection == .device, watchReconnectWait == nil, let update = updatePrompt {
                AppUpdateBanner(
                    update: update,
                    onDownload: {
                        if appUpdateController.openDownload(for: update) {
                            updatePrompt = nil
                        }
                    },
                    onLater: {
                        appUpdateController.deferPrompt(for: update)
                        updatePrompt = nil
                    },
                    onReleaseNotes: {
                        _ = appUpdateController.openReleaseNotes(for: update)
                    }
                )
                .frame(maxWidth: TerentoPageLayout.maxWidth, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, TerentoPageLayout.horizontalPadding)
                .padding(.top, 16)
            }
        }
        #endif
    }

    private func watchReconnectWaitContent(_ wait: WatchReconnectWait) -> some View {
        TerentoInstallationProgressPageShell {
            VStack(alignment: .leading, spacing: 0) {
                Text("Installing maps")
                    .font(.terento(.pageTitle))
                    .foregroundStyle(TerentoColors.graphite)

                WatchReconnectWaitPanel(
                    watchWasBusy: wait.watchWasBusy,
                    isCheckingWatch: wait.watchWasDisconnected && deviceEngine.hasConnectedDevice,
                    onCancel: {
                        // Cancel ends the wait with the failure dialog, as before
                        // the wait existed, so Report issue stays available.
                        watchReconnectFollowUp = endFollowUp(for: wait, decision: .keepWaiting)
                        mapEngine.recordReconnectWait(WatchReconnectWaitPolicy.funnelOutcome(for: .keepWaiting))
                        endWatchReconnectWait()
                    }
                )
                .padding(.top, 18)
            }
        }
    }

    private var deviceAssetTaskKey: String {
        guard let identity else { return "no-device" }
        return "\(identity.manufacturer)-\(identity.model)-\(identity.variant ?? "")-\(identity.usbVendorId)-\(identity.usbProductId)"
    }

    private func startReadOnlyCheck() {
        selectedSection = .device
        deviceEngine.readDevice()
    }

    private func navigate(to section: TerentoSection) {
        guard selectedSection != section else {
            return
        }

        if (section == .installMaps || section == .manageMaps),
           !canOpenMapSections {
            return
        }

        // Install maps shows the last read while it still describes the
        // watch (same connection, nothing written since); Refresh reads again.
        let shouldRefreshMapInventory = section == .manageMaps
            || (section == .installMaps && !installationFlowHasStarted
                && !mapEngine.hasFreshInventory(for: identity))

        if section == .installMaps, !installationFlowHasStarted {
            localInstallStep = .choose
            selectedInstallationPlan = nil
        }

        if section == .manageMaps {
            importedMapsExpanded = false
            externalMapsExpanded = false
            expandedProviderMapGroups.formUnion(mapEngine.availableMapProviders.map(\.id))
        }

        selectedSection = section

        if shouldRefreshMapInventory,
           !mapEngine.isBusy,
           !lifecycleViewModel.isBusy {
            refreshMapInventory()
        }
    }

    private func updatePresenceMonitoring(for mapState: MapEngineState) {
        let mapWorkIsBusy = mapEngine.isBusy || mapState == .loadingCatalog || mapState == .scanning
        let installationFlowIsActive = InstallationFlowPresentation.isActive(
            mapEngine.installationPhase
        )
        deviceEngine.setPresenceMonitoringEnabled(
            !mapWorkIsBusy
                && !installationFlowIsActive
                && !lifecycleViewModel.isBusy
        )
    }

    @ViewBuilder
    private var workflowContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            switch selectedSection {
            case .device:
                deviceContent
            case .installMaps:
                switch localInstallStep {
                case .choose:
                    mapsContent
                case .install:
                    installContent
                case .done:
                    finishContent
                }
            case .manageMaps:
                managedMapsContent
            }
        }
    }

    private func refreshMapInventory() {
        guard let identity,
              let snapshot = deviceEngine.snapshot else {
            return
        }

        mapEngine.scanDeviceMaps(
            deviceIdentity: identity,
            availableStorage: snapshot.freeSpace
        )
        selectedMapIDs.removeAll()
        selectedOptionalArtifactIDs.removeAll()
        mapSearchText = ""
    }

    private func checkForAppUpdate() {
        appUpdateController.checkForUpdates()
    }

    private func presentUpdatePromptIfSafe() {
        guard let update = appUpdateController.claimPromptIfSafe(updatePresentationIsSafe) else {
            return
        }

        updatePrompt = update
    }

    private func handleInstallationFailureDismissed() {
        let followUp = installationFailureFollowUp
        installationFailureFollowUp = .backToDevice
        installationFailureOverride = nil
        installationFailureSnapshot = nil
        switch followUp {
        case .backToDevice:
            returnToDeviceAfterFailure()
        case .tryAgain:
            retryInstallationAfterFailure()
        case .manageMaps:
            selectedInstallationPlan = nil
            selectedOptionalArtifactIDs.removeAll()
            localInstallStep = .choose
            navigate(to: .manageMaps)
        }
    }

    /// Try again keeps the selection, rereads the watch and then starts the
    /// normal install flow; a retained artifact skips the download and every
    /// safety check runs again.
    private func retryInstallationAfterFailure() {
        guard let identity,
              deviceEngine.snapshot != nil,
              selectedInstallationPlan != nil else {
            returnToDeviceAfterFailure()
            return
        }
        retryInstallationAfterScan = true
        selectedSection = .installMaps
        localInstallStep = .install
        mapEngine.scanDeviceMaps(
            deviceIdentity: identity,
            availableStorage: currentDeviceFreeSpace
        )
    }

    private func continueRetryAfterScanIfReady(_ state: MapEngineState) {
        guard retryInstallationAfterScan else { return }
        switch state {
        case .scanned:
            retryInstallationAfterScan = false
            guard let plan = currentInstallationPlan, !plan.installItems.isEmpty else {
                selectedInstallationPlan = nil
                localInstallStep = .choose
                return
            }
            selectedInstallationPlan = plan
            if installAvailability(for: plan).isEnabled {
                beginInstallationAfterConsent(plan)
            }
        case .failed, .idle:
            retryInstallationAfterScan = false
        case .loadingCatalog, .scanning, .acquiringArtifact, .preparingInstallation, .installing:
            break
        }
    }

    /// A stop before any write because the watch was busy or no longer
    /// visible waits for the same watch instead of ending the installation.
    /// Custom maps are not kept across a disconnect, so they stop as before.
    private func makeWatchReconnectWait() -> WatchReconnectWait? {
        guard mapEngine.stoppedBeforeWriteForWatchReconnect,
              mapEngine.canRetryFailedInstallation,
              let plan = selectedInstallationPlan,
              !plan.installItems.isEmpty,
              !plan.installItems.contains(where: { $0.package.sourceKind == .custom }),
              let watchKey = identity?.physicalManifestDeviceKey else {
            return nil
        }
        return WatchReconnectWait(
            watchKey: watchKey,
            selectedMapIDs: selectedMapIDs,
            selectedOptionalArtifactIDs: selectedOptionalArtifactIDs,
            mapTitle: installationFailureMapTitle(in: plan),
            failureReason: installationFailureReason,
            watchWasBusy: mapEngine.evidenceFailureContext?.isWatchSessionBusy == true
        )
    }

    private func continueWatchReconnectWaitIfReady() {
        guard let wait = watchReconnectWait, watchReconnectFollowUp == nil else { return }
        let decision = WatchReconnectWaitPolicy.decision(
            for: wait,
            now: Date(),
            deviceConnected: deviceEngine.hasConnectedDevice,
            connectedWatchKey: identity?.physicalManifestDeviceKey,
            mapScanReady: mapEngine.state == .scanned,
            authorizationResolved: deviceEngine.installationAuthorization != .resolving
        )
        switch decision {
        case .keepWaiting:
            return
        case .resume:
            watchReconnectFollowUp = .resume(wait)
        case .differentWatch, .timedOut:
            watchReconnectFollowUp = endFollowUp(for: wait, decision: decision)
        }
        mapEngine.recordReconnectWait(WatchReconnectWaitPolicy.funnelOutcome(for: decision))
        endWatchReconnectWait()
    }

    /// Every end of the wait runs its follow-up exactly once (the sheet's
    /// onDismiss did this while the wait was a dialog).
    private func endWatchReconnectWait() {
        guard watchReconnectWait != nil else { return }
        watchReconnectWait = nil
        handleWatchReconnectWaitEnded()
    }

    /// While the watch never left, the engine still holds the original
    /// failure and the normal failure dialog shows it unchanged (Try again,
    /// Report issue). After a disconnect it shows what happened instead.
    private func endFollowUp(for wait: WatchReconnectWait,
                             decision: WatchReconnectWaitPolicy.Decision) -> WatchReconnectFollowUp {
        if !wait.watchWasDisconnected, mapEngine.installationPhase == .failed {
            return .showFailure
        }
        return .stop(wait.mapTitle, WatchReconnectWaitPolicy.endMessage(
            for: wait, decision: decision, deviceConnected: deviceEngine.hasConnectedDevice))
    }

    private func handleWatchReconnectWaitEnded() {
        let followUp = watchReconnectFollowUp ?? .showFailure
        watchReconnectFollowUp = nil
        switch followUp {
        case .showFailure:
            isShowingInstallationFailure = true
        case let .stop(mapTitle, reason):
            installationFailureOverride = InstallationFailureOverride(mapTitle: mapTitle, reason: reason)
            isShowingInstallationFailure = true
        case let .resume(wait):
            resumeInstallationAfterReconnect(wait)
        }
    }

    /// The same watch is back and read again: start the normal flow exactly
    /// like Try again. Every check runs again; a kept download is reused only
    /// after it is revalidated.
    private func resumeInstallationAfterReconnect(_ wait: WatchReconnectWait) {
        selectedMapIDs = wait.selectedMapIDs
        selectedOptionalArtifactIDs = wait.selectedOptionalArtifactIDs
        selectedSection = .installMaps
        guard let plan = currentInstallationPlan, !plan.installItems.isEmpty else {
            selectedInstallationPlan = nil
            localInstallStep = .choose
            return
        }
        let availability = installAvailability(for: plan)
        guard availability.isEnabled else {
            selectedInstallationPlan = nil
            localInstallStep = .choose
            installationFailureOverride = InstallationFailureOverride(mapTitle: wait.mapTitle,
                reason: availability.userReason ?? "Installation could not be completed safely.")
            isShowingInstallationFailure = true
            return
        }
        selectedInstallationPlan = plan
        localInstallStep = .install
        beginInstallationAfterConsent(plan)
    }

    private func installAvailability(for plan: InstallationPlan) -> InstallReviewAvailability {
        InstallReviewAvailabilityResolver().resolve(
            plan: plan,
            deviceConnected: deviceEngine.hasConnectedDevice,
            installationAuthorization: deviceEngine.installationAuthorization,
            deviceIdentity: identity,
            mapScanReady: mapEngine.state == .scanned,
            supportedInstallFlow: !plan.installItems.isEmpty,
            installationPhase: mapEngine.installationPhase,
            hasValidatedArtifact: mapEngine.validatedArtifact != nil,
            operationBusy: mapEngine.isBusy
                || lifecycleViewModel.isBusy
        )
    }

    private func returnToDeviceAfterFailure() {
        selectedInstallationPlan = nil
        selectedOptionalArtifactIDs.removeAll()
        localInstallStep = .choose
        selectedSection = .device
        refreshMapInventory()
    }

    private func performSafeEject() {
        guard canSafelyEject else {
            return
        }

        lifecycleViewModel.resetForDisconnectedDevice()
        mapEngine.resetForDisconnectedDevice()
        deviceEngine.ejectDevice()
    }

    private var connectContent: some View {
        TerentoPageShell(
            topPadding: TerentoPageLayout.primaryTopPadding,
            bottomPadding: TerentoPageLayout.primaryBottomPadding,
            maxHeight: .infinity
        ) {
            GeometryReader { page in
                VStack(alignment: .center, spacing: 0) {
                    Spacer(minLength: 0)

                    VStack(alignment: .center, spacing: 0) {
                        ResourceImage(name: connectionIllustrationName, subdirectory: "Illustrations")
                            .scaledToFit()
                            .frame(
                                maxWidth: 720,
                                maxHeight: connectionIllustrationHeight(pageHeight: page.size.height)
                            )
                            .frame(maxWidth: .infinity, alignment: .center)

                        connectionStatusView
                            .padding(.top, 14)

                        if let issue = shownConnectIssue {
                            connectHelpBox(heading: issue.finding, steps: issue.steps, note: issue.note)
                                .padding(.top, 14)
                                .frame(maxWidth: 460, alignment: .center)
                        } else if showsNoUSBHelp {
                            connectHelpBox(
                                heading: "Still not showing up?",
                                steps: Self.noUSBHelpSteps,
                                note: "Terento keeps looking while you try these."
                            )
                                .padding(.top, 14)
                                .frame(maxWidth: 460, alignment: .center)
                        } else if showsConnectChecklist {
                            connectChecklist
                                .padding(.top, 14)
                                .frame(maxWidth: 420, alignment: .center)
                        }

                        if deviceEngine.state == .disconnected || deviceEngine.state == .failed {
                            PrimaryButton(
                                title: deviceEngine.state == .failed ? "Try again" : "Connect device",
                                action: startReadOnlyCheck
                            )
                                .padding(.top, 14)
                        }

                    }
                    .frame(maxWidth: .infinity, alignment: .center)

                    Spacer(minLength: 0)
                }
                .frame(maxHeight: .infinity, alignment: .center)
            }
        }
    }

    private var connectionStatusView: some View {
        VStack(alignment: .center, spacing: TerentoPageLayout.titleSubtitleSpacing) {
            if let statusIcon = connectionStatusIcon {
                Image(systemName: statusIcon.name)
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(statusIcon.color)
                    .accessibilityHidden(true)
            }

            Text(connectionStatusTitle)
                .font(.terento(.pageTitle))
                .foregroundStyle(TerentoColors.graphite)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .center)

            Text(connectionStatusDescription)
                .font(.terento(.lede))
                .foregroundStyle(TerentoColors.secondaryText)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(connectionStatusTitle) \(connectionStatusDescription)")
    }

    private var connectionIllustrationName: String {
        switch deviceEngine.state {
        case .connected, .ready, .safeToDisconnect:
            return "connect-illustration"
        case .disconnected, .detecting, .ejecting, .failed:
            return "connect-illustration-connecting"
        }
    }

    /// The illustration has two sizes: a larger one without a help box and a
    /// smaller one while a help box is shown. Each depends only on the page
    /// height, never on the message, so switching states doesn't resize it.
    /// The reserves fit the tallest content of each kind at the minimum
    /// window (a final failure's box and Try again; a three-line disconnect
    /// notice with the checklist).
    private func connectionIllustrationHeight(pageHeight: CGFloat) -> CGFloat {
        if showsConnectHelpBox {
            return min(180, max(80, pageHeight - 410))
        }
        return min(300, max(120, pageHeight - 290))
    }

    private var showsConnectHelpBox: Bool {
        shownConnectIssue != nil || showsNoUSBHelp
    }

    /// Every connect status pairs its text with an icon; colour only supports it.
    private var connectionStatusIcon: (name: String, color: Color)? {
        switch deviceEngine.state {
        case .detecting:
            switch deviceEngine.detectionPhase {
            case .waitingForWatch:
                // After an unplug the title and the plug-in line say it all.
                return disconnectExplanation == nil ? ("cable.connector", TerentoColors.secondaryText) : nil
            case .connecting:
                return ("arrow.triangle.2.circlepath", TerentoColors.interactive)
            case .needsAttention:
                return ("exclamationmark.circle", TerentoColors.warning)
            }
        case .failed:
            return ("exclamationmark.triangle", TerentoColors.error)
        case .disconnected, .connected, .ready, .ejecting, .safeToDisconnect:
            return nil
        }
    }

    /// First-connection tips; a watch that was just unplugged needs none.
    private var showsConnectChecklist: Bool {
        deviceEngine.state == .detecting && deviceEngine.detectionPhase == .waitingForWatch
            && disconnectExplanation == nil
    }

    private var connectChecklist: some View {
        VStack(alignment: .leading, spacing: 7) {
            troubleshootingRow("Use a USB data cable, not a charge-only cable", icon: "cable.connector")
            troubleshootingRow("Unlock your device", icon: "lock.open")
            troubleshootingRow("Quit Garmin Express", icon: "xmark.app")
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Before you connect: use a USB data cable, unlock your device, and quit Garmin Express.")
    }

    /// After the whole connection window with nothing on USB, the calm
    /// waiting page adds fuller steps; detection keeps polling unchanged.
    private var showsNoUSBHelp: Bool {
        showsConnectChecklist && deviceEngine.hasWaitedWithoutUSB
    }

    private static let noUSBHelpSteps: [ConnectStep] = [
        ConnectStep(systemImage: "cable.connector", text: "Use a USB data cable, not a charge-only cable"),
        ConnectStep(systemImage: "desktopcomputer", text: "Plug it directly into the Mac, not into a USB hub"),
        ConnectStep(systemImage: "cable.connector", text: "Try another USB port"),
        ConnectStep(systemImage: "lock.open", text: "Unlock your device"),
        ConnectStep(systemImage: "arrow.clockwise", text: "Restart your device"),
        ConnectStep(systemImage: "xmark.app", text: "Quit Garmin Express")
    ]

    /// The problem on screen: a live attention state or the final failure.
    private var shownConnectIssue: ConnectIssueMessage? {
        switch deviceEngine.state {
        case .failed:
            return deviceEngine.connectFailure
        case .detecting:
            guard case let .needsAttention(outcome) = deviceEngine.detectionPhase else { return nil }
            return UserFacingErrorMessage.detectionAttention(outcome)
        case .disconnected, .connected, .ready, .ejecting, .safeToDisconnect:
            return nil
        }
    }

    /// The guide section for the help box on screen; none while plainly
    /// waiting or connecting.
    private var connectHelpTopic: TroubleshootingTopic? {
        TroubleshootingHelp.connectHelpTopic(
            state: deviceEngine.state,
            phase: deviceEngine.detectionPhase,
            failure: deviceEngine.connectFailure,
            waitedWithoutUSB: deviceEngine.hasWaitedWithoutUSB
        )
    }

    /// Every Connect problem uses this light box: what Terento found (or the
    /// question it answers), the steps with icons, the guide link and what
    /// Terento does meanwhile. VoiceOver reads the heading and steps as one
    /// element, then the link, then the note.
    private func connectHelpBox(heading: String, steps: [ConnectStep], note: String) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            VStack(alignment: .leading, spacing: 7) {
                Text(heading)
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.bottom, 2)
                ForEach(steps, id: \.text) { step in
                    troubleshootingRow(step.text, icon: step.systemImage)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(([heading] + steps.map(\.text)).joined(separator: ". "))

            if let topic = connectHelpTopic {
                TerentoHelpLink(topic: topic, title: "More help in the troubleshooting guide", iconColumnWidth: 18)
            }

            Text(note)
                .font(.terento(.caption))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 2)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.helpSurface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border.opacity(0.5), lineWidth: 1)
        }
    }

    /// The interrupted operation's outcome takes precedence over the generic
    /// disconnect line, so the user learns what happened to their map.
    private var disconnectExplanation: String? {
        lifecycleViewModel.interruptedOperationNotice ?? deviceEngine.disconnectNotice
    }

    private var connectionStatusTitle: String {
        switch deviceEngine.state {
        case .disconnected:
            return "Ready when you are."
        case .detecting:
            switch deviceEngine.detectionPhase {
            case .waitingForWatch:
                return disconnectExplanation == nil ? "Connect your device" : "Your Garmin was disconnected"
            case .connecting:
                return "Waiting for your Garmin…"
            case .needsAttention(let outcome):
                return UserFacingErrorMessage.detectionAttention(outcome)?.title
                    ?? "Waiting for your Garmin…"
            }
        case .connected, .ready:
            return "Garmin \(deviceEngine.compatibility?.displayName ?? "device") connected"
        case .ejecting:
            return "Releasing your Garmin…"
        case .safeToDisconnect:
            return "Safe to disconnect"
        case .failed:
            if let failure = deviceEngine.connectFailure {
                return failure.title
            }
            return "Couldn't connect to Garmin"
        }
    }

    private var connectionStatusDescription: String {
        switch deviceEngine.state {
        case .disconnected:
            return "Connect your device to this Mac."
        case .detecting:
            switch deviceEngine.detectionPhase {
            case .waitingForWatch:
                return disconnectExplanation
                    ?? "Plug your Garmin into this Mac. Terento finds it automatically."
            case .connecting:
                return "This may take up to 2 minutes. Terento tells you if something is wrong."
            case .needsAttention(let outcome):
                return UserFacingErrorMessage.detectionAttention(outcome)?.reason
                    ?? "This may take up to 2 minutes."
            }
        case .connected, .ready:
            return "Your Garmin is ready."
        case .ejecting:
            return "Finishing the connection safely."
        case .safeToDisconnect:
            return "You can unplug your Garmin."
        case .failed:
            if let failure = deviceEngine.connectFailure {
                return failure.reason
            }
            if let message = deviceEngine.userErrorMessage {
                return message
            }
            return "We couldn't connect to your Garmin. Reconnect it and try again."
        }
    }

    private func troubleshootingRow(_ text: String, icon: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .frame(width: 18)
                .accessibilityHidden(true)

            Text(text)
                .font(.terento(.meta))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var deviceContent: some View {
        Group {
            if let snapshot {
                connectedDeviceContent(snapshot)
            } else {
                connectContent
            }
        }
    }

    private var managedFiltersAreActive: Bool {
        !managedSearchText.isEmpty || !managedProviderID.isEmpty
    }

    private func refreshManagedPresentation() {
        let inventory = mapEngine.mapLifecycleInventory()
        // A rescan of the same watch (after Remove, Refresh or opening the
        // page) keeps the current list; the reading card is only for no list.
        if inventory == nil, managedInventory != nil, isReadingDeviceMaps { return }
        removedManagedMapIDs = []
        managedInventory = inventory
        managedGarminMaps = inventory == nil ? [] : mapEngine.garminSystemMaps()
        keptManagedAvailability = Dictionary((inventory?.allItems ?? []).map {
            ($0.id, lifecycleViewModel.availability(for: $0))
        }, uniquingKeysWith: { first, _ in first })
        managedPresentationIndex = managedInventory.map(MapInventoryListPresentationIndex.init)
        if !managedProviderID.isEmpty,
           !(managedPresentationIndex?.providerOptions.contains { $0.id == managedProviderID } ?? false) {
            managedProviderID = ""
        }
        refreshManagedFilters()
    }

    private func refreshManagedFilters() {
        filteredManagedInventory = managedPresentationIndex.map {
            withoutRemovedMaps($0.filtered(query: managedSearchText, providerID: managedProviderID))
        }
        visibleGarminSummary = GarminMapsSummary.visible(managedGarminMaps,
            query: managedSearchText, providerID: managedProviderID)
        if managedFiltersAreActive, let inventory = filteredManagedInventory {
            expandedProviderMapGroups.formUnion(inventory.providerGroups.map(\.id))
            importedMapsExpanded = true
            externalMapsExpanded = true
        }
    }

    /// Hides a removed map from the kept list until the rescan replaces it.
    private func withoutRemovedMaps(_ inventory: MapLifecycleInventory) -> MapLifecycleInventory {
        guard !removedManagedMapIDs.isEmpty else { return inventory }
        let kept = { (item: MapLifecycleItem) in !removedManagedMapIDs.contains(item.id) }
        return MapLifecycleInventory(
            providerGroups: inventory.providerGroups.compactMap { group in
                let items = group.items.filter(kept)
                return items.isEmpty ? nil : MapLifecycleProviderGroup(id: group.id,
                    providerId: group.providerId, title: group.title, items: items)
            },
            otherMaps: inventory.otherMaps.filter(kept)
        )
    }

    private var managedCatalogToolbar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    TextField("Search installed maps", text: $managedSearchText)
                        .textFieldStyle(.plain)
                        .focused($managedSearchFocused)
                        .accessibilityLabel("Search installed maps")
                        .accessibilityHint("Search a country, region or imported map name.")
                    if !managedSearchText.isEmpty {
                        Button {
                            managedSearchText = ""
                            managedSearchFocused = true
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(TerentoColors.secondaryText)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Clear installed map search")
                    }
                }
                .toolbarControlChrome(isFocused: managedSearchFocused)
                .frame(minWidth: 240, maxWidth: .infinity)
                Picker("Map provider", selection: $managedProviderID) {
                    Text("All providers").tag("")
                    ForEach(managedPresentationIndex?.providerOptions ?? []) { provider in
                        Text(provider.title).tag(provider.id)
                    }
                }
                .toolbarMenuPicker(
                    width: 175,
                    title: managedPresentationIndex?.providerOptions
                        .first { $0.id == managedProviderID }?.title ?? "All providers"
                )
                .accessibilityLabel("Installed map provider")
            }
            HStack {
                let count = GarminMapsSummary.manageListCount(
                    lifecycleItemCount: filteredManagedInventory?.allItems.count ?? 0
                )
                Text("\(count) \(count == 1 ? "map" : "maps")")
                    .foregroundStyle(TerentoColors.secondaryText)
                Spacer()
                if managedFiltersAreActive {
                    Button("Clear filters") {
                        managedSearchText = ""
                        managedProviderID = ""
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(TerentoColors.interactive)
                }
            }
            .font(.terento(.caption))
        }
        .padding(.bottom, 4)
        .accessibilityElement(children: .contain)
    }

    private var managedMapsContent: some View {
        TerentoFooterPageShell(bodyScrolls: false) {
            VStack(alignment: .leading, spacing: 0) {
            // Same header row as Install maps, so Refresh sits in the same place.
            HStack(alignment: .firstTextBaseline, spacing: 16) {
                TerentoPageHeader(
                    title: "Manage maps",
                    subtitle: "Maps on your Garmin."
                )

                Spacer(minLength: 20)

                // Kept list during a rescan: Refresh stays in place, disabled.
                if mapEngine.state == .scanned || (isReadingDeviceMaps && managedInventory != nil) {
                    Button {
                        refreshMapInventory()
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                            .font(.terento(.meta))
                            .foregroundStyle(mapManagementActionsBusy
                                ? TerentoGeneratedTokens.Light.textDisabled : TerentoColors.secondaryText)
                    }
                    .buttonStyle(TerentoKeyIndependentButtonStyle())
                    .disabled(mapManagementActionsBusy)
                    .help("Refresh map information")
                    .accessibilityLabel("Refresh map information")
                }
            }

            if let lifecycleInventory = filteredManagedInventory {
                if !(managedInventory?.allItems.isEmpty ?? true) || !managedGarminMaps.isEmpty {
                    managedCatalogToolbar
                        .padding(.top, TerentoPageLayout.firstSectionTopPadding)
                }
                if let notice = lifecycleViewModel.removalNotice {
                    Label {
                        Text(notice)
                            .font(.terento(.meta))
                            .foregroundStyle(TerentoColors.secondaryText)
                    } icon: {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(TerentoColors.lichenDark)
                    }
                    .padding(.top, 10)
                    .accessibilityElement(children: .combine)
                }
                #if TERENTO_APP_STORE
                // After a verified update the question sits above the list,
                // as it sits on the Done page after an installation.
                if let sharingQuestion, sharingQuestion.isUpdate {
                    InstallSharingCallout(onDecide: decideSharing)
                        .padding(.top, 10)
                }
                #endif
                ScrollView {
                    managedMapGroups(lifecycleInventory)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                        .padding(.vertical, 2)
                }
                .scrollIndicators(.automatic)
                // As in Install maps: a 12 pt gap under the count line (4 + 8)
                // outside the scroll view, and rows clipped at its edge, so
                // they never scroll visibly under the count line.
                .clipped()
                .padding(.top, 8)
                // VoiceOver hears "<Map> · <style> removed." even when focus is elsewhere.
                .onChange(of: lifecycleViewModel.removalNotice) { notice in
                    guard let notice else { return }
                    if let itemID = removingManagedMapID,
                       let operation = lifecycleViewModel.operation(for: itemID),
                       operation.action == .remove, operation.phase == .completed {
                        removedManagedMapIDs.insert(itemID)
                        refreshManagedFilters()
                    }
                    NSAccessibility.post(element: NSApp as Any, notification: .announcementRequested, userInfo: [
                        .announcement: notice,
                        .priority: NSAccessibilityPriorityLevel.high.rawValue
                    ])
                }
            } else if mapEngine.mapScanFailed && deviceEngine.hasConnectedDevice {
                MapStatusRow(
                    title: "Couldn't read your maps",
                    detail: "Your device is connected, but its maps couldn't be read.",
                    status: "Error",
                    note: mapEngine.userErrorMessage,
                    isError: true,
                    onRetry: refreshMapInventory
                )
                .padding(.top, 18)
            } else {
                MapStatusRow(
                    title: mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
                        ? "Reading your maps"
                        : "Map information is not available",
                    detail: deviceEngine.hasConnectedDevice
                        ? (mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
                            ? "This can take a minute."
                            : "Refresh the connected Garmin device to try again.")
                        : "Connect your Garmin device first",
                    status: deviceEngine.hasConnectedDevice
                        ? (mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
                            ? "Checking"
                            : "Pending")
                        : "Pending",
                    note: mapEngine.userErrorMessage
                )
                .padding(.top, 18)
            }

            }
        } footer: {
            TerentoPageFooter(
                leading: {
                    // The sidebar already navigates back to Device.
                    EmptyView()
                },
                trailing: {
                    EmptyView()
                }
            )
        }
        .sheet(item: $lifecycleViewModel.pendingConfirmation) { confirmation in
            MapLifecycleConfirmationSheet(
                title: mapConfirmationTitle(for: confirmation),
                subtitle: confirmation.action == .remove
                    ? mapConfirmationMetadata(for: confirmation)
                    : mapConfirmationSubtitle(for: confirmation),
                message: confirmation.action == .remove
                    ? MapLifecycleConfirmationCopy.removeMessage
                    : lifecycleViewModel.confirmationMessage,
                actionTitle: confirmation.action == .remove ? "Remove map" : "Update map",
                isDestructive: confirmation.action == .remove,
                onCancel: { lifecycleViewModel.cancelPendingAction() },
                onConfirm: { lifecycleViewModel.confirmPendingAction() }
            )
        }
    }

    @ViewBuilder
    private func managedMapGroups(_ lifecycleInventory: MapLifecycleInventory) -> some View {
        LazyVStack(alignment: .leading, spacing: 0) {
                let hasProviderMaps = !lifecycleInventory.providerGroups.isEmpty
                let importedMaps = lifecycleInventory.otherMaps.filter {
                    $0.sourceKind == .custom && $0.classification == .terentoManaged
                }
                let externalMaps = lifecycleInventory.otherMaps.filter {
                    !($0.sourceKind == .custom && $0.classification == .terentoManaged)
                }

                ForEach(Array(lifecycleInventory.providerGroups.enumerated()), id: \.element.id) { index, group in
                    TerentoMapSection(
                        title: group.title,
                        count: group.items.count,
                        isExpanded: providerGroupExpansionBinding(for: group.id)
                    ) {
                        ForEach(group.items) { item in
                            managedMapRow(item, provider: group.title)
                        }
                    }
                    .padding(
                        .top,
                        index == 0
                            ? TerentoPageLayout.firstSectionTopPadding
                            : TerentoPageLayout.sectionSpacing
                    )
                }

                if !importedMaps.isEmpty {
                    TerentoMapSection(
                        title: "Imported maps",
                        count: importedMaps.count,
                        isExpanded: $importedMapsExpanded
                    ) {
                        ForEach(importedMaps) { item in
                            managedMapRow(item)
                        }
                    }
                    .padding(
                        .top,
                        hasProviderMaps
                            ? TerentoPageLayout.sectionSpacing
                            : TerentoPageLayout.firstSectionTopPadding
                    )
                }

                if !externalMaps.isEmpty {
                    TerentoMapSection(
                        title: "External maps",
                        count: externalMaps.count,
                        isExpanded: $externalMapsExpanded
                    ) {
                        ForEach(externalMaps) { item in
                            managedMapRow(item)
                        }
                    }
                    .padding(
                        .top,
                        hasProviderMaps || !importedMaps.isEmpty
                            ? TerentoPageLayout.sectionSpacing
                            : TerentoPageLayout.firstSectionTopPadding
                    )
                }

                if let garminSummary = visibleGarminSummary {
                    // Read-only: one summary row at the bottom without a group
                    // header (the row already says "Garmin maps"). It takes no
                    // actions and is not counted in "N maps".
                    GarminMapsSummaryRow(summary: garminSummary)
                    .padding(
                        .top,
                        hasProviderMaps || !importedMaps.isEmpty || !externalMaps.isEmpty
                            ? TerentoPageLayout.sectionSpacing
                            : TerentoPageLayout.firstSectionTopPadding
                    )
                }

                if lifecycleInventory.allItems.isEmpty && visibleGarminSummary == nil {
                    MapStatusRow(
                        title: managedFiltersAreActive ? "No matching maps" : "No maps detected",
                        detail: managedFiltersAreActive
                            ? "Try another country or region, or clear the filters."
                            : (deviceEngine.hasConnectedDevice
                                ? "No installed maps were found on this Garmin."
                                : "Connect your Garmin device first"),
                        status: deviceEngine.hasConnectedDevice ? "Ready" : "Pending",
                        note: nil
                    )
                    .padding(.top, 30)
                }
        }
        // A removed row fades out when the list refreshes in place.
        .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: lifecycleInventory.allItems.map(\.id))
    }

    private func confirmationItem(for confirmation: MapLifecycleConfirmation) -> (item: MapLifecycleItem, provider: String?)? {
        guard let inventory = mapEngine.mapLifecycleInventory() else { return nil }
        let items = inventory.providerGroups.flatMap(\.items) + inventory.otherMaps
        guard let item = items.first(where: { $0.id == confirmation.itemID }) else { return nil }
        let provider = inventory.providerGroups.first(where: { group in
            group.items.contains(where: { $0.id == item.id })
        })?.title ?? item.provider
        return (item, provider)
    }

    private func mapConfirmationTitle(for confirmation: MapLifecycleConfirmation) -> String {
        let name = confirmationItem(for: confirmation)?.item.title
        return confirmation.action == .remove
            ? MapLifecycleConfirmationCopy.removeTitle(mapName: name)
            : "Update this map?"
    }

    /// "BBBike (Ontrail) · 2026-11-18 · 483 KB" for the Remove dialog.
    private func mapConfirmationMetadata(for confirmation: MapLifecycleConfirmation) -> String {
        guard let (item, provider) = confirmationItem(for: confirmation) else {
            return lifecycleViewModel.confirmationSubtitle
        }
        return MapLifecycleConfirmationCopy.metadata(item: item, provider: provider)
    }

    private func mapConfirmationSubtitle(for confirmation: MapLifecycleConfirmation) -> String {
        guard let (item, provider) = confirmationItem(for: confirmation) else {
            return lifecycleViewModel.confirmationSubtitle
        }
        return [item.title, provider, item.manageMetadataLabel]
            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func connectedDeviceContent(_ snapshot: DeviceSnapshot) -> some View {
        TerentoPageShell {
            VStack(alignment: .leading, spacing: 0) {
            let presentation = DevicePresentation(
                identity: identity
                    ?? GarminDeviceIdentityAdapter().makeIdentity(from: snapshot),
                deviceName: deviceEngine.compatibility?.displayName
                    ?? "\(snapshot.manufacturer) \(snapshot.model)",
                variant: deviceVariantLine(snapshot),
                compatibility: deviceEngine.compatibility?.status,
                asset: resolvedDeviceAsset
            )

            HStack(alignment: .top, spacing: 24) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Your Garmin")
                        .font(.terento(.pageTitle))
                        .foregroundStyle(TerentoColors.graphite)

                    Text("Connected and ready.")
                        .font(.terento(.lede))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 20)

            }

            DeviceCard(
                presentation: presentation,
                canEject: canSafelyEject,
                onEject: performSafeEject,
                authorization: DeviceAuthorizationPresentation(deviceEngine.installationAuthorization),
                onRetryAuthorization: { deviceEngine.retryInstallationAuthorization() }
            )
            .padding(.top, 30)

            StorageCard(
                total: formatBytes(snapshot.totalCapacity),
                available: formatBytes(snapshot.freeSpace),
                fillRatio: storageFillRatio(for: snapshot)
            )
            .padding(.top, 12)

            Divider()
                .overlay(TerentoColors.border)
                .padding(.top, 24)

            HStack(spacing: 12) {
                PrimaryButton(title: "Install maps") {
                    navigate(to: .installMaps)
                }
                .disabled(mapManagementActionsBusy)

                SecondaryButton(title: "Manage maps") {
                    navigate(to: .manageMaps)
                }
                .disabled(mapManagementActionsBusy)

                // Says why the two buttons are disabled right after connecting.
                if isReadingDeviceMaps {
                    HStack(spacing: 6) {
                        ProgressView()
                            .controlSize(.small)
                            .accessibilityHidden(true)
                        Text("Reading your maps…")
                            .font(.terento(.meta))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .lineLimit(1)
                    }
                    .accessibilityElement(children: .combine)
                }

                Spacer()
            }
            .padding(.top, 20)
            .padding(.bottom, 42)
            }
        }
    }

    private func providerGroupExpansionBinding(for providerID: String) -> Binding<Bool> {
        Binding(
            get: { expandedProviderMapGroups.contains(providerID) },
            set: { isExpanded in
                if isExpanded {
                    expandedProviderMapGroups.insert(providerID)
                } else {
                    expandedProviderMapGroups.remove(providerID)
                }
            }
        )
    }

    /// True only when the Manage row for this installed map offers Update,
    /// so the Install list never points to an Update that is not there.
    private func isUpdateOfferedInManage(_ item: MapSelectionItem) -> Bool {
        guard item.comparison.status == .updateAvailable,
              let path = item.comparison.installedMap?.sourceFile.path,
              let lifecycleItem = managedInventory?.allItems.first(where: { candidate in
                  candidate.installedMaps.contains { $0.sourceFile.path == path }
              })
        else { return false }
        return lifecycleViewModel.availability(for: lifecycleItem).allows(.update)
    }

    @ViewBuilder
    private func managedMapRow(_ item: MapLifecycleItem, provider: String? = nil) -> some View {
        ManageMapRow(
            item: item,
            providerLabel: item.sourceKind == .custom ? "" : MapProviderDisplay.title(providerID: item.provider ?? "",
                regionID: item.region, fallback: provider ?? item.provider ?? ""),
            availability: isReadingDeviceMaps
                ? keptManagedAvailability[item.id] ?? lifecycleViewModel.availability(for: item)
                : lifecycleViewModel.availability(for: item),
            operation: lifecycleViewModel.operation(for: item.id),
            timeRemaining: lifecycleViewModel.timeRemaining(for: item.id),
            isLifecycleBusy: mapManagementActionsBusy,
            onRemove: { lifecycleViewModel.requestRemove(itemID: item.id) },
            onUpdate: { lifecycleViewModel.requestUpdate(itemID: item.id) }
        )
        .transition(.opacity)
    }

    private func deviceVariantLine(_ snapshot: DeviceSnapshot) -> String {
        ConnectedDeviceSubtitleFormatter.format(
            identity: identity ?? GarminDeviceIdentityAdapter().makeIdentity(from: snapshot),
            fallbackModel: snapshot.model,
            manufacturer: snapshot.manufacturer
        )
    }

    private var catalogFiltersAreActive: Bool {
        !mapSearchText.isEmpty || !selectedMapProviderID.isEmpty || selectedGeography != .all
    }

    private func clearCatalogFilters() {
        mapSearchText = ""
        selectedMapProviderID = ""
        selectedGeography = .all
        refreshProviderPresentation()
    }

    private var catalogToolbar: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) {
                    catalogSearchField
                    catalogFilterMenus
                }
                VStack(alignment: .leading, spacing: 10) {
                    catalogSearchField
                    catalogFilterMenus
                }
            }
            HStack {
                let count = filteredAvailableSelectionItems.count
                Text("\(count) \(count == 1 ? "map" : "maps")")
                    .foregroundStyle(TerentoColors.secondaryText)
                // Next to the provider filter: the rule is about providers.
                catalogSelectionNotice
                Spacer()
                if catalogFiltersAreActive {
                    Button("Clear filters") { clearCatalogFilters() }
                        .buttonStyle(.plain)
                        .foregroundStyle(TerentoColors.interactive)
                }
            }
            .font(.terento(.caption))
        }
        .accessibilityElement(children: .contain)
    }

    private var catalogSearchField: some View {
        HStack(spacing: 6) {
            TextField("Search countries and regions", text: $mapSearchText)
                .textFieldStyle(.plain)
                .focused($mapSearchFieldFocused)
                .accessibilityLabel("Search countries and regions")
                .accessibilityHint("\(filteredAvailableSelectionItems.count) matching maps. Search by country or region.")
            if !mapSearchText.isEmpty {
                Button {
                    mapSearchText = ""
                    mapSearchFieldFocused = true
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(TerentoColors.secondaryText)
                }
                .buttonStyle(.plain)
                .help("Clear search")
                .accessibilityLabel("Clear search")
            }
        }
        .toolbarControlChrome(isFocused: mapSearchFieldFocused)
        .frame(minWidth: 240, maxWidth: .infinity)
    }

    private var catalogFilterMenus: some View {
        HStack(spacing: 10) {
            Picker("Geography", selection: $selectedGeography) {
                ForEach(catalogPresentationIndex.geographyOptions) { group in
                    Text(group.title).tag(group)
                }
            }
            .toolbarMenuPicker(width: 190, title: selectedGeography.title)
            .accessibilityLabel("Geographic region")

            Picker("Map provider", selection: $selectedMapProviderID) {
                Text("All providers").tag("")
                ForEach(mapProviderOptions) { provider in
                    Text(provider.title).tag(provider.id)
                }
            }
            .toolbarMenuPicker(
                width: 175,
                title: mapProviderOptions.first { $0.id == selectedMapProviderID }?.title ?? "All providers"
            )
            .accessibilityLabel("Map provider")
            .accessibilityHint("Filters maps without choosing a default provider.")
        }
        .fixedSize(horizontal: true, vertical: false)
    }

    private var isFirstMapSelection: Bool {
        mapEngine.isFirstMapSelection
    }

    @ViewBuilder
    private var catalogSelectionNotice: some View {
        let selectedProviderItems = mapSelectionItems.filter {
            $0.package.sourceKind == .provider && selectedMapIDs.contains($0.id)
        }
        if !selectedProviderItems.isEmpty {
            let visibleIDs = Set(filteredAvailableSelectionItems.map(\.id))
            let hiddenItems = selectedProviderItems.filter { !visibleIDs.contains($0.id) }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("Choose maps from one provider at a time.")
                if !hiddenItems.isEmpty {
                    Text("\(hiddenItems.count) selected hidden.")
                    Button("Show selected") {
                        clearCatalogFilters()
                        revealedSelectionID = selectedProviderItems.first?.id
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(TerentoColors.interactive)
                }
            }
            .font(.terento(.caption))
            .foregroundStyle(TerentoColors.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var catalogMapRegion: some View {
        GeometryReader { geometry in
            if !customMapImportExpanded {
                availableCatalogList
            } else if geometry.size.height < 300 {
                // At the minimum window size, scroll the import content rather
                // than clipping its file controls or pushing Storage offscreen.
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        availableCatalogList.frame(height: 180)
                        customMapImportPanel
                    }
                }
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    availableCatalogList
                    customMapImportPanel
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 12)
                }
            }
        }
        // Keep this gap outside both scroll views so rows cannot slide under
        // the toolbar; it matches the gap before the custom import panel.
        .padding(.top, 12)
        .clipped()
    }

    @ViewBuilder
    private var availableCatalogList: some View {
        if providerMapSelectionItems.isEmpty || filteredAvailableSelectionItems.isEmpty {
            Text(availableMapsEmptyMessage)
                .font(.terento(.meta))
                .foregroundStyle(TerentoColors.secondaryText)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(.top, 10)
        } else {
            ScrollViewReader { scrollProxy in
                TerentoBoundedMapSelectionRegion {
                    LazyVStack(spacing: 0) {
                        ForEach(filteredAvailableSelectionItems) { item in
                            MapSelectionRow(
                                item: item,
                                isSelected: Binding(
                                    get: { selectedMapIDs.contains(item.id) },
                                    set: { selected in
                                        guard MapSelectionPresentationModel.isSelectionEnabled(
                                            item,
                                            selectedIDs: selectedMapIDs,
                                            items: mapSelectionItems
                                        ) else { return }
                                        if selected {
                                            selectedMapIDs.insert(item.id)
                                        } else {
                                            selectedMapIDs.remove(item.id)
                                            selectedOptionalArtifactIDs.removeValue(forKey: item.id)
                                        }
                                    }
                                ),
                                selectedOptionalArtifactIDs: Binding(
                                    get: {
                                        selectedOptionalArtifactIDs[item.id] ?? []
                                    },
                                    set: { value in
                                        if value.isEmpty {
                                            selectedOptionalArtifactIDs.removeValue(forKey: item.id)
                                        } else {
                                            selectedOptionalArtifactIDs[item.id] = value
                                        }
                                    }
                                ),
                                isAvailable: true,
                                selectionEnabled: isMapSelectionEnabled(item),
                                highlightsRecommendation: isFirstMapSelection,
                                // Every install selection shows its download
                                // size and time; the highlight stays first-map only.
                                downloadEstimate: FirstMapGuidance.downloadEstimateText(
                                    bytes: item.package.expectedDownloadSizeBytes,
                                    recentBytesPerSecond: mapEngine.recentDownloadBytesPerSecond),
                                updateOfferedInManage: isUpdateOfferedInManage(item)
                            )
                        }
                    }
                }
                .onChange(of: revealedSelectionID) { itemID in
                    if let itemID {
                        scrollProxy.scrollTo(itemID, anchor: .top)
                        revealedSelectionID = nil
                    }
                }
            }
        }
    }

    private var mapsContent: some View {
        TerentoInstallFooterPageShell(bodyScrolls: false) {
            TerentoInstallMapsVerticalLayout {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(alignment: .firstTextBaseline, spacing: 16) {
                        TerentoPageHeader(
                            title: "Install maps",
                            subtitle: "Choose maps to install on your Garmin."
                        )

                        Spacer(minLength: 20)

                        if mapEngine.state == .scanned {
                            Button {
                                refreshMapInventory()
                            } label: {
                                Label("Refresh", systemImage: "arrow.clockwise")
                                    .font(.terento(.meta))
                                    .foregroundStyle(TerentoColors.secondaryText)
                            }
                            .buttonStyle(TerentoKeyIndependentButtonStyle())
                            .help("Refresh map information")
                            .accessibilityLabel("Refresh map information")

                            // Opens the import panel under the list and closes it
                            // again; it looks selected while the panel is open.
                            SecondaryButton(title: "Import map file", isSelected: customMapImportExpanded) {
                                customMapImportExpanded.toggle()
                            }
                            .accessibilityLabel("Import map file")
                            .accessibilityValue(customMapImportExpanded ? "Expanded" : "Collapsed")
                            .accessibilityHint("Shows or hides the local Garmin IMG import controls.")
                        }
                    }

                    if let notice = authorizationPresentation.browsingNotice {
                        Label(notice, systemImage: authorizationPresentation.systemImage)
                            .font(.terento(.caption))
                            .foregroundStyle(authorizationPresentation.tone.color)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 10)
                    }

                    if mapEngine.catalogSource == .bundledFallback {
                        Label(
                            MapCatalogSource.bundledFallback.userLabel,
                            systemImage: "wifi.slash"
                        )
                        .font(.terento(.caption))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .padding(.top, 10)
                        .accessibilityHint("Terento is using its bundled local map list. It may be out of date.")
                    } else if mapEngine.catalogSource == .appUpdateRequired {
                        Label(
                            MapCatalogSource.appUpdateRequired.userLabel,
                            systemImage: "arrow.down.circle"
                        )
                        .font(.terento(.caption))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .padding(.top, 10)
                        .accessibilityHint("This Terento version can't use the current map catalog. Maps can be browsed; installing needs a Terento update.")
                    }

                    if mapEngine.state == .loadingCatalog || mapEngine.state == .scanning {
                        MapStatusRow(
                            title: "Reading your maps",
                            detail: "This can take a minute.",
                            status: "Checking",
                            note: nil
                        )
                        .padding(.top, 18)
                    } else if mapEngine.mapScanFailed && deviceEngine.hasConnectedDevice {
                        MapStatusRow(
                            title: "Couldn't read your maps",
                            detail: "Your device is connected, but its maps couldn't be read.",
                            status: "Error",
                            note: mapEngine.userErrorMessage,
                            isError: true,
                            onRetry: refreshMapInventory
                        )
                        .padding(.top, 18)
                    } else if mapEngine.state != .scanned {
                        MapStatusRow(
                            title: "Maps are not ready yet",
                            detail: "Connect your Garmin device first",
                            status: "Pending",
                            note: mapEngine.userErrorMessage
                                ?? "Available maps will appear here after the device is checked."
                        )
                        .padding(.top, 18)
                    } else {
                        catalogToolbar
                        .padding(.top, TerentoPageLayout.firstSectionTopPadding)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
            } mapRegion: {
                if mapEngine.state == .scanned {
                    catalogMapRegion
                } else {
                    Color.clear
                        .accessibilityHidden(true)
                }
            }
        } footer: {
            TerentoPageFooter {
                // First Install step: the sidebar already navigates back, so
                // the leading slot holds Storage on the same row as Continue.
                if let plan = displayedInstallationPlan {
                    MapSelectionStorageLine(
                        plan: plan,
                        totalCapacity: snapshot?.totalCapacity ?? 0,
                        formatBytes: formatBytes
                    )
                }
            } trailing: {
                PrimaryButton(title: "Continue") {
                    guard let plan = currentInstallationPlan, plan.canContinue else {
                        return
                    }

                    selectedInstallationPlan = plan
                    localInstallStep = .install
                }
                .disabled(!(displayedInstallationPlan?.canContinue ?? false))
            }
        }
        .fileImporter(
            isPresented: $isShowingCustomMapImporter,
            allowedContentTypes: [UTType(filenameExtension: "img") ?? .data],
            allowsMultipleSelection: false
        ) { result in
            guard case let .success(urls) = result,
                  let url = urls.first else {
                return
            }
            mapEngine.importCustomMap(fileURL: url)
        }
        .sheet(
            item: Binding(
                get: { mapEngine.customMapImportWarning },
                set: { _ in mapEngine.dismissCustomMapImportWarning() }
            )
        ) { warning in
            TerentoConfirmationDialog(
                icon: "exclamationmark.triangle",
                role: .warning,
                title: "File could not be confirmed as a map",
                message: warning.message,
                secondaryLabel: nil,
                primaryLabel: "Choose another file",
                isDestructive: false,
                onConfirm: { mapEngine.dismissCustomMapImportWarning() }
            )
        }
        .sheet(
            item: Binding(
                get: { mapEngine.customMapImportRisk },
                set: { _ in mapEngine.dismissCustomMapImportRisk() }
            ),
            onDismiss: {
                if !customMapImportDidContinue {
                    mapEngine.clearCustomMapImport()
                }
                customMapImportDidContinue = false
            }
        ) { risk in
            CustomMapImportConfirmationSheet(
                filename: risk.filename,
                onCancel: {
                    mapEngine.clearCustomMapImport()
                },
                onContinue: {
                    customMapImportDidContinue = true
                    mapEngine.acknowledgeCustomMapImportRisk()
                }
            )
        }
    }

    private var selectedMapProviderLabel: String {
        guard !selectedMapProviderID.isEmpty,
              let provider = mapProviderOptions.first(where: {
                  MapIdentity.normalizeProvider($0.id)
                      == MapIdentity.normalizeProvider(selectedMapProviderID)
              }) else {
            return "All providers"
        }
        return provider.title
    }

    private var selectedMapProvider: MapProvider? {
        guard !selectedMapProviderID.isEmpty else { return nil }
        let providerID = MapProviderDisplay.sourceProviderID(filterID: selectedMapProviderID)
        return mapEngine.availableMapProviders.first {
            MapIdentity.normalizeProvider($0.id) == MapIdentity.normalizeProvider(providerID)
        }
    }

    private var availableMapsEmptyMessage: String {
        let query = mapSearchText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !query.isEmpty {
            return "No maps match your search."
        }

        if !selectedMapProviderID.isEmpty {
            if let provider = selectedMapProvider,
               let status = provider.temporaryUnavailableReason {
                if let checkedAt = provider.lastCheckedAt {
                    return "\(status). Last checked: \(checkedAt.formatted(date: .abbreviated, time: .shortened))."
                }
                return "\(status)."
            }
            return "No maps are available from \(selectedMapProviderLabel)."
        }

        return selectedGeography == .all ? "No maps are available." : "No maps match these filters."
    }

    /// Shown under the list while "Import map file" in the header is on. The
    /// drop zone says what to do, so the panel has no extra first line.
    private var customMapImportPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let candidate = mapEngine.customMapImportCandidate {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(TerentoColors.lichenDark)
                        .accessibilityHidden(true)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Custom map")
                            .font(.terento(.meta, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)
                        Text("\(candidate.originalFilename) · \(formatBytes(candidate.sizeBytes))")
                            .font(.terento(.caption))
                            .foregroundStyle(TerentoColors.secondaryText)
                        Text("Map structure checked · source is not verified.")
                            .font(.terento(.caption))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 8)

                    Button("Remove") {
                        mapEngine.clearCustomMapImport()
                    }
                    .buttonStyle(.borderless)
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.interactive)
                    .disabled(mapEngine.isBusy)
                    .accessibilityLabel("Remove staged custom map")
                    .accessibilityHint("Removes the local staged file. It does not change the Garmin device.")
                }
                .padding(10)
                .background(TerentoColors.canvas, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control))
            } else {
                customMapDropZone
            }

            Text("Processed locally on your Mac. Not sent to Terento servers.")
                .font(.terento(.caption))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)

            if let errorMessage = mapEngine.customMapImportErrorMessage,
               mapEngine.customMapImportCandidate == nil {
                Text(errorMessage)
                    .font(.terento(.caption))
                    .foregroundStyle(TerentoColors.error)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .background(TerentoColors.surface.opacity(0.62), in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border.opacity(0.48), lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
    }

    private var customMapDropZone: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: customMapDropTargeted ? "arrow.down.doc.fill" : "arrow.down.doc")
                .font(.system(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.interactive)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text(customMapImportIsBusy ? "Checking map file…" : "Drop a third-party map (.img) here")
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                if customMapImportIsBusy {
                    Text("Checking it before installation")
                        .font(.terento(.caption))
                        .foregroundStyle(TerentoColors.secondaryText)
                }
            }

            Spacer(minLength: 8)

            if !customMapImportIsBusy {
                Button("Choose File…") {
                    isShowingCustomMapImporter = true
                }
                .buttonStyle(.bordered)
                .controlSize(.regular)
                .disabled(mapEngine.isBusy)
                .accessibilityHint("Opens a file picker for a third-party map IMG file.")
            } else {
                ProgressView()
                    .controlSize(.small)
                    .accessibilityLabel("Checking map file")
            }
        }
        .frame(maxWidth: .infinity, minHeight: 66, maxHeight: 74, alignment: .leading)
        .padding(.horizontal, 12)
        .background(
            customMapDropTargeted
                ? TerentoColors.interactive.opacity(0.10)
                : TerentoColors.canvas,
            in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
        )
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
                .stroke(
                    customMapDropTargeted
                        ? TerentoColors.interactive
                        : TerentoColors.border.opacity(0.72),
                    style: StrokeStyle(lineWidth: 1, dash: [5, 5])
                )
        }
        .contentShape(Rectangle())
        .onDrop(
            of: [UTType.fileURL.identifier],
            isTargeted: $customMapDropTargeted,
            perform: loadDroppedCustomMap
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Drop a third-party map IMG file or choose one")
        .accessibilityHint("Choose File opens an accessible file picker. The selected file will be checked locally before installation.")
    }

    private func loadDroppedCustomMap(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }

        provider.loadItem(
            forTypeIdentifier: UTType.fileURL.identifier,
            options: nil
        ) { item, _ in
            let url: URL?
            if let itemURL = item as? URL {
                url = itemURL
            } else if let itemURL = item as? NSURL {
                url = itemURL as URL
            } else if let data = item as? Data {
                url = URL(dataRepresentation: data, relativeTo: nil)
            } else {
                url = nil
            }

            guard let url else { return }
            DispatchQueue.main.async {
                mapEngine.importCustomMap(fileURL: url)
            }
        }
        return true
    }

    private var unifiedMapInventory: UnifiedMapInventory? {
        mapEngine.result?.unifiedMapInventory()
    }

    @ViewBuilder
    private var installContent: some View {
        if let selectedInstallationPlan {
            plannedInstallContent(selectedInstallationPlan)
        } else if installationFlowHasStarted {
            activeInstallationFallbackContent
        } else {
            mapsContent
        }
    }

    private var activeInstallationFallbackContent: some View {
        return TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                Text("Installing maps")
                    .font(.terento(.pageTitle))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Keep your Garmin connected until installation is complete.")
                    .font(.terento(.lede))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                installationJourneyView
                    .padding(.top, 16)
            }
        } footer: {
            EmptyView()
        }
    }

    @ViewBuilder
    private func plannedInstallContent(_ plan: InstallationPlan) -> some View {
        if installationFlowHasStarted {
            activeInstallationContent(plan)
        } else {
            reviewInstallContent(plan)
        }
    }

    private func reviewInstallContent(_ plan: InstallationPlan) -> some View {
        let installAvailability = installAvailability(for: plan)

        return TerentoInstallFooterPageShell(bodyScrolls: true) {
            VStack(alignment: .leading, spacing: 0) {
                Text("Ready to install")
                    .font(.terento(.pageTitle))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Review your selection before installing.")
                    .font(.terento(.lede))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)
                    .padding(.top, 18)

                ReadyToInstallSelectedMapsList(plan: plan)
                    .padding(.top, 4)

                if let reason = installAvailability.userReason {
                    let authorization = DeviceAuthorizationPresentation(deviceEngine.installationAuthorization)
                    let authorizationBlocks = reason == authorization.reviewReason
                    VStack(alignment: .leading, spacing: 8) {
                        // Icon and colour agree: the authorization verdict keeps
                        // its own icon; other blockers are warnings.
                        Label(reason, systemImage: authorizationBlocks
                            ? authorization.systemImage
                            : "exclamationmark.circle.fill")
                            .font(.terento(.meta, weight: .semibold))
                            .foregroundStyle(authorizationBlocks
                                ? authorization.tone.color
                                : TerentoColors.warning)
                            .fixedSize(horizontal: false, vertical: true)

                        if authorizationBlocks && authorization.canRetry {
                            SecondaryButton(title: "Try again") {
                                deviceEngine.retryInstallationAuthorization()
                            }
                            .accessibilityHint("Checks again whether this device can install maps.")
                        }
                    }
                    .padding(.top, 18)
                }

            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } footer: {
            VStack(spacing: TerentoPageLayout.sectionSpacing + 18) {
                MapSelectionStorageSummary(
                    plan: plan,
                    totalCapacity: snapshot?.totalCapacity ?? 0,
                    formatBytes: formatBytes
                )
                .fixedSize(horizontal: false, vertical: true)

            TerentoPageFooter {
                TerentoBackButton {
                    selectedInstallationPlan = nil
                    localInstallStep = .choose
                }
            } trailing: {
                PrimaryButton(title: "Install maps") {
                    switch installAvailability {
                    case .ready(.install):
                        beginInstallationAfterConsent(plan)
                    case .ready(.prepare):
                        beginInstallationAfterConsent(plan)
                    case .blocked:
                        return
                    }
                }
                // Only the resolved availability (server authorization, live
                // identity, plan and scan) gates Install. The local map
                // capability registry is information, never a veto.
                .disabled(!installAvailability.isEnabled)
            }
            }
        }
        .onAppear {
            mapEngine.recordInstallReviewBlocked(plan: plan,
                authorization: deviceEngine.installationAuthorization, supportedInstallFlow: true)
        }
        .onChange(of: deviceEngine.installationAuthorization) { authorization in
            mapEngine.recordInstallReviewBlocked(plan: plan,
                authorization: authorization, supportedInstallFlow: true)
        }
    }

    private func activeInstallationContent(_ plan: InstallationPlan) -> some View {
        return TerentoInstallationProgressPageShell {
            VStack(alignment: .leading, spacing: 0) {
                Text("Installing maps")
                    .font(.terento(.pageTitle))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Keep your Garmin connected until installation is complete.")
                    .font(.terento(.lede))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                InstallationMapsSectionHeader(count: plan.selectedItems.count)
                    .padding(.top, 18)

                InstallationMapsList(items: plan.selectedItems)
                    .padding(.top, 4)

                installationJourneyView
                    .padding(.top, 10)

                if mapEngine.canCancelInstallationPreparation {
                    HStack(spacing: 12) {
                        SecondaryButton(title: "Cancel") {
                            mapEngine.cancelInstallationPreparation()
                        }
                        .accessibilityHint("Stops downloading and preparing. Nothing has been written to your device.")

                        Text("Nothing has been written to your device yet.")
                            .font(.terento(.caption))
                            .foregroundStyle(TerentoColors.secondaryText)
                    }
                    .padding(.top, 14)
                } else if mapEngine.installationPhase == .preparing {
                    // The install step owns the device from here: Cancel stays
                    // in view, disabled, and says why.
                    HStack(spacing: 12) {
                        SecondaryButton(title: "Cancel") {}
                            .disabled(true)

                        Text("Can’t cancel while the map is being prepared.")
                            .font(.terento(.caption))
                            .foregroundStyle(TerentoColors.secondaryText)
                    }
                    .padding(.top, 14)
                }
            }
        }
    }

    private var installationJourneyView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Installation progress")
                .font(.terento(.rowTitle))
                .foregroundStyle(TerentoColors.graphite)
                .padding(.bottom, 10)

            installationStepRow(
                title: "Downloading",
                detail: downloadStepDetail,
                state: installationStepState(for: .downloading),
                progress: mapEngine.acquisitionProgress.flatMap {
                    $0.totalBytes > 0 ? $0.fractionCompleted : nil
                },
                bytes: mapEngine.acquisitionProgress.map {
                    (current: $0.bytesDownloaded, total: $0.totalBytes, speed: $0.bytesPerSecond)
                },
                timeRemaining: mapEngine.downloadTimeRemaining,
                isLast: false
            )

            installationStepRow(
                title: "Preparing",
                detail: planContainsOnlyCustomMaps
                    ? "Checking the custom IMG and preparing the Garmin image"
                    : "Verifying files and preparing the Garmin image",
                state: installationStepState(for: .preparing),
                progress: mapEngine.installationPhase == .preparing
                    && mapEngine.installationPhaseProgressIsMeasured
                    && (mapEngine.installationPhaseProgress ?? 0) > 0.05
                    ? mapEngine.installationPhaseProgress
                    : nil,
                bytes: nil,
                isLast: false
            )

            installationStepRow(
                title: "Installing",
                detail: "Writing the validated map to your Garmin device",
                state: installationStepState(for: .installing),
                progress: mapEngine.installationProgress.flatMap {
                    $0.totalBytes > 0 ? $0.fractionCompleted : nil
                },
                bytes: mapEngine.installationProgress.map {
                    (current: $0.bytesTransferred, total: $0.totalBytes, speed: $0.bytesPerSecond)
                },
                timeRemaining: mapEngine.installTimeRemaining,
                isLast: false
            )

            installationStepRow(
                title: "Finishing",
                detail: "Checking the transferred map and completing final checks",
                state: installationStepState(for: .finishing),
                // Finishing is several waits; only the read-back is measured, so one
                // indeterminate bar for the whole step never moves backwards.
                progress: nil,
                bytes: nil,
                timeRemaining: mapEngine.finishingTimeRemaining,
                isLast: true
            )
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private func installationStepRow(
        title: String,
        detail: String,
        state: InstallationStepState,
        progress: Double?,
        bytes: (current: UInt64, total: UInt64, speed: Double)?,
        timeRemaining: RemainingTimeEstimate? = nil,
        isLast: Bool
    ) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 0) {
                installationStepMarker(for: state)

                if !isLast {
                    Rectangle()
                        .fill(state == .complete ? TerentoColors.lichen : TerentoColors.border)
                        .frame(width: InstallationTimelineLayout.connectorWidth)
                        .frame(maxHeight: .infinity)
                }
            }
            .frame(width: InstallationTimelineLayout.markerSize)
            .frame(maxHeight: .infinity, alignment: .top)

            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(title)
                        .font(.terento(.meta, weight: .semibold))
                        .foregroundStyle(
                            state == .pending
                                ? TerentoColors.secondaryText
                                : TerentoColors.graphite
                        )

                    Spacer()

                    if state == .active,
                       let measured = TerentoProgressBar.measured(progress) {
                        Text("\(Int(measured * 100))%")
                            .font(.terento(.meta, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)
                    }
                }

                Text(state == .failed ? (mapEngine.installationErrorMessage ?? detail) : detail)
                    .font(.terento(.meta))
                    .foregroundStyle(
                        state == .failed
                            ? TerentoColors.error
                            : TerentoColors.secondaryText
                    )
                    .fixedSize(horizontal: false, vertical: true)

                if state == .active {
                    TerentoProgressBar(value: progress, label: title)

                    if title == "Finishing" {
                        Text(finishingProgressDetail)
                            .font(.terento(.caption))
                            .foregroundStyle(TerentoColors.secondaryText.opacity(0.82))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                if let bytes,
                   InstallationDownloadStepPresentation.showsByteLine(current: bytes.current, total: bytes.total),
                   state == .active || state == .complete {
                    HStack {
                        Text("\(formatBytes(bytes.current)) of \(formatBytes(bytes.total))")
                        Spacer()
                        if state == .active, bytes.speed > 0 {
                            Text("\(formatBytesPerSecond(bytes.speed))/s")
                        }
                    }
                    .font(.terento(.caption))
                    .foregroundStyle(TerentoColors.secondaryText)
                }

                if state == .active, let timeRemaining {
                    TimeRemainingLabel(estimate: timeRemaining)
                }
            }
            .padding(.bottom, isLast ? 0 : 16)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) — \(installationStepAccessibilityLabel(for: state))")
        .accessibilityValue(installationStepAccessibilityValue(progress: progress, bytes: bytes,
            timeRemaining: state == .active ? timeRemaining?.text(at: Date()) : nil))
    }

    private func installationStepMarker(for state: InstallationStepState) -> some View {
        ZStack {
            Circle()
                .fill(installationStepMarkerFill(for: state))
                .overlay {
                    Circle()
                        .stroke(
                            state == .pending
                                ? TerentoColors.inactiveBorder
                                : installationStepColor(for: state),
                            lineWidth: 2
                        )
                }

            if state == .active {
                ProgressView()
                    .controlSize(.small)
                    .tint(TerentoColors.sky)
                    .accessibilityHidden(true)
            } else if state != .pending {
                Image(systemName: installationStepIcon(for: state))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.white)
            }
        }
        .frame(
            width: InstallationTimelineLayout.markerSize,
            height: InstallationTimelineLayout.markerSize
        )
    }

    private func installationStepMarkerFill(for state: InstallationStepState) -> Color {
        switch state {
        case .complete:
            return TerentoColors.lichen
        case .active:
            return TerentoColors.sky.opacity(0.20)
        case .pending:
            return TerentoColors.canvas
        case .failed:
            return TerentoColors.error
        }
    }

    private func installationStepState(for phase: InstallationProcessPhase) -> InstallationStepState {
        let customOnly = planContainsOnlyCustomMaps
        let current = InstallationDownloadStepPresentation.displayedPhase(mapEngine.installationPhase,
            resolvingPackage: mapEngine.acquisitionState == .resolvingPackage, customOnly: customOnly)

        if phase == .downloading, customOnly {
            return .complete
        }

        if current == .failed {
            if mapEngine.acquisitionState == .failed {
                return phase == (customOnly ? .preparing : .downloading) ? .failed : .pending
            }

            if let result = mapEngine.installationResult {
                if result.verification != nil || result.diagnostics.remoteObjectExists {
                    return phase == .finishing ? .failed : phase == .downloading || phase == .preparing || phase == .installing ? .complete : .pending
                }

                switch result.preflight.status {
                case .readyNewInstall, .readyWithExistingMapConflict:
                    return phase == .installing ? .failed : phase == .downloading || phase == .preparing ? .complete : .pending
                default:
                    return phase == .preparing ? .failed : phase == .downloading ? .complete : .pending
                }
            }

            if phase == .preparing,
               mapEngine.state == .failed || mapEngine.state == .preparingInstallation {
                return .failed
            }

            return .pending
        }

        if current == .awaitingConfirmation {
            switch phase {
            case .downloading, .preparing:
                return .complete
            default:
                return .pending
            }
        }

        if current == .completed {
            return .complete
        }

        switch (current, phase) {
        case (.downloading, .downloading):
            return .active
        case (.preparing, .downloading):
            return .complete
        case (.preparing, .preparing):
            return .active
        case (.installing, .downloading), (.finishing, .downloading), (.completed, .downloading):
            return .complete
        case (.installing, .preparing):
            return .complete
        case (.installing, .installing):
            return .active
        case (.finishing, .preparing), (.finishing, .installing):
            return .complete
        case (.finishing, .finishing):
            return .active
        default:
            return .pending
        }
    }

    private func installationStepIcon(for state: InstallationStepState) -> String {
        switch state {
        case .complete:
            return "checkmark"
        case .active:
            return "circle"
        case .pending:
            return "circle"
        case .failed:
            return "exclamationmark"
        }
    }

    private func installationStepColor(for state: InstallationStepState) -> Color {
        switch state {
        case .complete:
            return TerentoColors.lichenDark
        case .active:
            return TerentoColors.sky
        case .pending:
            return TerentoColors.inactiveBorder
        case .failed:
            return TerentoColors.error
        }
    }

    private func installationStepAccessibilityLabel(for state: InstallationStepState) -> String {
        switch state {
        case .complete:
            return "completed"
        case .active:
            return "in progress"
        case .pending:
            return "pending"
        case .failed:
            return "failed"
        }
    }

    private func installationStepAccessibilityValue(
        progress: Double?,
        bytes: (current: UInt64, total: UInt64, speed: Double)?,
        timeRemaining: String? = nil
    ) -> String {
        let value: String
        if let progress {
            value = "\(Int(progress * 100)) percent"
        } else if let bytes, bytes.total > 0 {
            value = "\(formatBytes(bytes.current)) of \(formatBytes(bytes.total))"
        } else {
            value = ""
        }
        guard let timeRemaining else { return value }
        return value.isEmpty ? timeRemaining : "\(value), \(timeRemaining)"
    }

    private var downloadStepDetail: String {
        InstallationDownloadStepPresentation.detail(
            customOnly: planContainsOnlyCustomMaps,
            stepIsComplete: installationStepState(for: .downloading) == .complete
                || mapEngine.acquisitionState == .validated,
            isDownloading: mapEngine.acquisitionState == .downloading
        )
    }

    private var finishingProgressDetail: String {
        let progress = mapEngine.installationPhaseProgress ?? 0
        switch progress {
        case ..<0.25:
            if let readBack = mapEngine.finishingTransferProgress, readBack.totalBytes > 0 {
                let completed = ByteCountFormatter.string(fromByteCount: Int64(readBack.bytesTransferred), countStyle: .decimal)
                let total = ByteCountFormatter.string(fromByteCount: Int64(readBack.totalBytes), countStyle: .decimal)
                return "Checking your map · \(completed) of \(total) checked"
            }
            return "Waiting for your Garmin to finish saving the map, then checking it"
        case ..<0.45:
            return "Confirming the transferred file size and content"
        case ..<0.65:
            return "Confirming the map identity and release"
        case ..<0.85:
            return "Checking the target file and unchanged device files"
        default:
            return "Recording ownership and completing the installation"
        }
    }

    private var installationFailureStageLabel: String {
        switch mapEngine.evidenceFailureStage {
        case .download:
            return "Downloading"
        case .extract, .preflight, .sourceValidation:
            return "Preparing"
        case .write:
            return "Installing"
        case .verify, .cleanup, .manifest:
            return "Finishing"
        case nil:
            if mapEngine.acquisitionState == .failed { return "Downloading" }
            if mapEngine.installationResult?.diagnostics.remoteObjectExists == true { return "Finishing" }
            if mapEngine.installationResult != nil { return "Installing" }
            return "Preparing"
        }
    }

    private var installationIssueError: String? {
        let values = [
            mapEngine.evidenceFailure?.rawValue,
            mapEngine.installationErrorMessage
        ]
        .compactMap { value -> String? in
            let normalized = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return normalized.isEmpty ? nil : normalized
        }
        return values.isEmpty ? nil : values.joined(separator: " — ")
    }

    private var installationIssueFailureStages: [String] {
        var stages = [mapEngine.evidenceFailureStage?.rawValue].compactMap { $0 }
        if (selectedInstallationPlan?.installItems.count ?? 0) > 1,
           mapEngine.installationBatchResults.count < (selectedInstallationPlan?.installItems.count ?? 0) {
            stages.append(EvidenceFailureStage.preflight.rawValue)
        }
        var seen = Set<String>()
        return stages.filter { seen.insert($0).inserted }
    }

    private var installationIssueErrorCodes: [String] {
        var codes = [
            mapEngine.evidenceFailure?.rawValue,
            mapEngine.evidenceNativeFailureCode?.rawValue
        ].compactMap { $0 }
        if (selectedInstallationPlan?.installItems.count ?? 0) > 1,
           mapEngine.installationBatchResults.count < (selectedInstallationPlan?.installItems.count ?? 0) {
            codes.append("INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE")
        }
        var seen = Set<String>()
        return codes.filter { seen.insert($0).inserted }
    }

    private var installationIssueErrorCategory: String {
        switch mapEngine.evidenceFailure {
        case .sourceArtifactInvalid:
            return EvidenceErrorCategory.sourceValidation.rawValue
        case .insufficientSpace:
            return EvidenceErrorCategory.storage.rawValue
        case .deviceDisconnected:
            return EvidenceErrorCategory.deviceDisconnected.rawValue
        case .hashMismatch, .sizeMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired:
            return EvidenceErrorCategory.verification.rawValue
        case .downloadFailed:
            return EvidenceErrorCategory.acquisition.rawValue
        case .some:
            return EvidenceErrorCategory.transport.rawValue
        case .none:
            return EvidenceErrorCategory.unknown.rawValue
        }
    }

    private var installationIssueTransferProgressPercent: Int {
        guard let diagnostics = mapEngine.installationResult?.diagnostics,
              diagnostics.transferTotalBytes > 0 else {
            return 0
        }
        return min(
            100,
            Int((Double(diagnostics.bytesTransferred) / Double(diagnostics.transferTotalBytes)) * 100)
        )
    }

    private func installationFailureMapTitle(in plan: InstallationPlan) -> String? {
        if let index = mapEngine.evidencePrimaryFailureMapIndex,
           plan.installItems.indices.contains(index) {
            return plan.installItems[index].title
        }
        return plan.installItems.count == 1 ? plan.installItems.first?.title : nil
    }

    /// What the failure dialog shows, captured when the installation failed.
    private func makeInstallationFailureSnapshot() -> InstallationFailureSnapshot {
        InstallationFailureSnapshot(
            mapTitle: selectedInstallationPlan.flatMap(installationFailureMapTitle),
            reason: liveInstallationFailureReason,
            safetyMessage: liveInstallationFailureSafetyMessage,
            helpTopic: liveInstallationFailureHelpTopic,
            issueDraft: installationIssueDraft(for: selectedInstallationPlan)
        )
    }

    /// A disconnect clears the engine's failure state and the selected plan
    /// while the failure dialog is open or about to open. The dialog then
    /// keeps what was captured at the failure instead of a generic reason.
    private var retainedInstallationFailure: InstallationFailureSnapshot? {
        mapEngine.installationPhase == .failed ? nil : installationFailureSnapshot
    }

    private var installationFailureDialogMapTitle: String? {
        if let override = installationFailureOverride { return override.mapTitle }
        if let retained = retainedInstallationFailure { return retained.mapTitle }
        return selectedInstallationPlan.flatMap(installationFailureMapTitle)
    }

    private var installationFailureReason: String {
        if let override = installationFailureOverride { return override.reason }
        if let retained = retainedInstallationFailure { return retained.reason }
        return liveInstallationFailureReason
    }

    private var liveInstallationFailureReason: String {
        let normalized = mapEngine.installationErrorMessage?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return normalized.isEmpty
            ? "Installation could not be completed safely."
            : normalized
    }

    private var installationFailureHelpTopic: TroubleshootingTopic {
        retainedInstallationFailure?.helpTopic ?? liveInstallationFailureHelpTopic
    }

    private var liveInstallationFailureHelpTopic: TroubleshootingTopic {
        if mapEngine.evidenceFailure == nil,
           mapEngine.installationFailureAcquisitionError == nil,
           let topic = TroubleshootingHelp.topic(for: deviceEngine.installationAuthorization) {
            return topic
        }
        return TroubleshootingHelp.installationTopic(
            failure: mapEngine.evidenceFailure,
            acquisitionError: mapEngine.installationFailureAcquisitionError,
            mayHaveLeftMapOnWatch: mapEngine.installationResult?.mayHaveLeftMapOnWatch == true,
            failureContext: mapEngine.evidenceFailureContext
        )
    }

    private var installationFailureSafetyMessage: String? {
        // A reconnect wait ends only after a stop before any write.
        if installationFailureOverride != nil { return "Your existing maps were not changed." }
        if let retained = retainedInstallationFailure { return retained.safetyMessage }
        return liveInstallationFailureSafetyMessage
    }

    private var liveInstallationFailureSafetyMessage: String? {
        if let diagnostics = mapEngine.installationResult?.diagnostics {
            return diagnostics.existingFilesProtectionPassed
                && diagnostics.unrelatedFilesProtectionPassed
                ? "Your existing maps were not changed."
                : nil
        }

        switch mapEngine.evidenceFailureStage {
        case .download, .extract, .preflight, .sourceValidation:
            return "Your existing maps were not changed."
        case .write, .verify, .cleanup, .manifest, nil:
            return nil
        }
    }

    private func reportInstallationIssue(for plan: InstallationPlan?) {
        let draft = retainedInstallationFailure?.issueDraft ?? installationIssueDraft(for: plan)
        diagnosticLogMessage = InstallationIssueReport.openGitHub(draft)
            ? nil
            : "GitHub could not be opened. Please try again."
    }

    /// The failure dialog offers to send this one report to Terento. App
    /// Store builds offer it only while results are not shared (declined or
    /// not chosen yet); sending it is a one-time choice and changes no
    /// sharing choice. Shared results already reach Terento.
    private var offersInstallationSupportReport: Bool {
        #if TERENTO_APP_STORE
        return !evidenceController.compatibilitySharingEnabled
        #else
        return true
        #endif
    }

    /// The same sanitised report as the GitHub option, as a support report.
    private func sendInstallationSupportReport(for plan: InstallationPlan?) {
        let draft = retainedInstallationFailure?.issueDraft ?? installationIssueDraft(for: plan)
        guard let saved = draft.supportReport else { return }
        supportReportSummary = saved.summaryLine
        supportReportPayload = SupportReportPayload(category: saved.category, operationID: saved.operationID,
                                                    userMessage: nil, report: saved.report)
    }

    private func installationIssueDraft(for plan: InstallationPlan?) -> InstallationIssueDraft {
        let result = mapEngine.installationResult
        let verification = result?.verification
        return InstallationIssueReport.generate(
            identity: identity,
            mapName: plan?.installItems.count == 1 ? plan?.installItems.first?.title : nil,
            maps: (plan?.installItems ?? []).map { item in
                InstallationIssueMap(
                    provider: item.package.sourceKind == .custom ? "Custom import" : item.comparison.providerName,
                    region: item.title,
                    package: item.package.providerRegionId,
                    release: item.package.displayVersionLabel,
                    artifactSizeBytes: item.installSizeBytes
                )
            },
            stage: installationFailureStageLabel,
            error: installationIssueError,
            operationID: evidenceOperationID,
            failureStages: installationIssueFailureStages,
            errorCategory: installationIssueErrorCategory,
            errorCodes: installationIssueErrorCodes,
            writeStarted: mapEngine.installationResult?.diagnostics.writeStarted ?? false,
            transferProgressPercent: installationIssueTransferProgressPercent,
            remoteObjectCreated: mapEngine.installationResult?.diagnostics.remoteObjectCreated ?? false,
            cleanupAttempted: mapEngine.installationResult?.diagnostics.cleanupAttempted ?? false,
            cleanupSucceeded: mapEngine.installationResult?.diagnostics.cleanupSucceeded ?? false,
            verification: InstallationIssueVerification(
                originalFailure: (result?.originalFailure ?? result?.failure)?.rawValue,
                cleanupFailure: result?.cleanupFailure?.rawValue,
                transportClassification: result?.diagnostics.nativeFailureCode?.rawValue,
                artifactKind: mapEngine.packageInstallationOutcomes.compactMap { $0.failedComponent }.first?.artifactKind.rawValue,
                sourceSize: result?.diagnostics.sourceSizeBytes,
                remoteSize: result?.diagnostics.remoteSizeBytes,
                transferredBytes: result?.diagnostics.bytesTransferred,
                elapsedMilliseconds: result?.diagnostics.elapsedMilliseconds,
                sampledBytes: verification?.sampledBytes,
                sampleCount: verification?.sampleCount,
                matchedSampleCount: verification?.matchedSampleCount,
                inventoryMetrics: result?.diagnostics.inventoryMetrics
            ),
            failureContext: mapEngine.evidenceFailureContext ?? result?.failureContext,
            originalFailureContext: mapEngine.evidenceFailureContext == nil
                ? result?.originalFailureContext : mapEngine.evidenceOriginalFailureContext
        )
    }

    private var finishContent: some View {
        let installedItems = successfullyInstalledItems
        let installedCount = installedItems.count

        return TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                TerentoPageHeader(
                    title: installedCount == 1 ? "Map installed" : "Maps installed",
                    // A complete install needs no subtitle; the title says it.
                    subtitle: hasPartialInstallation
                        ? "The main map is ready. An optional contour component needs attention."
                        : ""
                )

                if mapEngine.installationPhase == .completed, !installedItems.isEmpty {
                    InstalledMapsSectionHeader(count: installedCount)
                        .padding(.top, TerentoPageLayout.firstSectionTopPadding)

                    InstallationMapsList(
                        items: installedItems,
                        accessibilityLabel: "Installed maps"
                    )
                        .padding(.top, TerentoPageLayout.sectionContentTopPadding)

                    InstallationResultCallout(
                        mapNames: installedItems.map(\.title),
                        isPartial: hasPartialInstallation
                    )
                        .padding(.top, TerentoPageLayout.sectionSpacing)

                    #if TERENTO_APP_STORE
                    if let sharingQuestion, !sharingQuestion.isUpdate {
                        InstallSharingCallout(onDecide: decideSharing)
                            .padding(.top, TerentoPageLayout.sectionSpacing)
                    }
                    #endif

                    #if !TERENTO_APP_STORE
                    // One quiet line after a complete installation, from the
                    // third one and once per version (DonationPromptPolicy).
                    // The donation unlocks nothing; App Store builds carry no
                    // external payment link (guideline 3.1.1).
                    if showsDonationLine, !hasPartialInstallation {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("Terento is free and open source. If it saved you time, you can support it.")
                                .font(.terento(.meta))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                            Link("Donate ↗", destination: TerentoAppLinks.donate)
                                .font(.terento(.meta))
                                .foregroundStyle(TerentoColors.interactive)
                        }
                        .padding(.top, TerentoPageLayout.sectionSpacing)
                    }
                    #endif
                }
            }
        } footer: {
            TerentoPageFooter {
                EmptyView()
            } trailing: {
                PrimaryButton(title: "Back to device") {
                    returnToDeviceAfterSuccess()
                }
            }
        }
    }

    private var successfullyInstalledItems: [MapSelectionItem] {
        guard mapEngine.installationPhase == .completed,
              let plan = selectedInstallationPlan,
              mapEngine.installationBatchResults.count == plan.installItems.count,
              mapEngine.packageInstallationOutcomes.count == plan.installItems.count else {
            return []
        }

        let successfulPackageIDs = Set(
            mapEngine.packageInstallationOutcomes
                .filter { $0.status != .failed }
                .map(\.packageID)
        )
        let resultSuccessfulPackageIDs = Set(
            zip(plan.installItems, mapEngine.installationBatchResults)
                .filter { $0.1.isSuccess }
                .map { $0.0.package.id }
        )
        return plan.selectedItems.filter {
            successfulPackageIDs.contains($0.package.id)
                && resultSuccessfulPackageIDs.contains($0.package.id)
        }
    }

    private var hasPartialInstallation: Bool {
        mapEngine.packageInstallationOutcomes.contains { $0.hasWarnings }
    }

    private func returnToDeviceAfterSuccess() {
        selectedSection = .device
        selectedInstallationPlan = nil
        localInstallStep = .choose
        refreshMapInventory()
    }

    private func storageFillRatio(for snapshot: DeviceSnapshot) -> Double {
        guard snapshot.totalCapacity > 0 else {
            return 0
        }

        let usedBytes = snapshot.totalCapacity >= snapshot.freeSpace
            ? snapshot.totalCapacity - snapshot.freeSpace
            : 0

        return min(
            1,
            max(0, Double(usedBytes) / Double(snapshot.totalCapacity))
        )
    }

    private func formatBytes(_ bytes: UInt64) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(bytes, UInt64(Int64.max))),
            countStyle: .decimal
        )
    }

    private func formatBytesPerSecond(_ bytes: Double) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(max(bytes, 0), Double(Int64.max))),
            countStyle: .decimal
        )
    }

    private func beginInstallationAfterConsent(_ plan: InstallationPlan) {
        let operationID = UUID()
        evidenceOperationID = operationID
        mapEngine.beginInstallation(plan: plan, operationId: operationID)
    }


}

struct TerentoSidebar: View {
    @Binding var selectedSection: TerentoSection
    let connectionState: DeviceConnectionState
    let detectionPhase: DeviceDetectionPhase
    let canEject: Bool
    let isInstalling: Bool
    let navigationLocked: Bool
    let mapNavigationEnabled: Bool
    var showsEject = true
    let onNavigate: (TerentoSection) -> Void
    let onEject: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            TerentoBrandLockup()
                .padding(.horizontal, 14)
                .padding(.top, 25)
                .padding(.bottom, 22)

            Divider()
                .overlay(TerentoColors.sidebarBorder)

            VStack(alignment: .leading, spacing: 9) {
                ForEach([
                    TerentoSection.device,
                    TerentoSection.installMaps,
                    TerentoSection.manageMaps
                ]) { section in
                    Button {
                        onNavigate(section)
                    } label: {
                        SidebarSectionRow(
                            title: section.rawValue,
                            icon: icon(for: section),
                            isSelected: selectedSection == section
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(
                        navigationLocked
                            || ((section == .installMaps || section == .manageMaps)
                                && !mapNavigationEnabled)
                    )
                    .accessibilityLabel(section.rawValue)
                    .accessibilityAddTraits(
                        selectedSection == section ? .isSelected : []
                    )
                }
            }
            .padding(.top, 28)

            Spacer(minLength: 28)

            SidebarConnectionStatus(
                state: connectionState,
                detectionPhase: detectionPhase,
                canEject: canEject,
                isInstalling: isInstalling,
                showsEject: showsEject,
                onEject: onEject
            )
                .padding(.top, 7)
                .padding(.horizontal, 14)
                .padding(.bottom, 20)
        }
        .padding(.horizontal, 20)
        .frame(width: 218)
        .background(TerentoColors.sidebar)
    }

    // Lucide `watch` (bundled asset): SF Symbols has no round watch before macOS 14.
    private func icon(for section: TerentoSection) -> Image {
        switch section {
        case .device:
            return Image("Watch")
        case .installMaps:
            return Image(systemName: "arrow.down.circle")
        case .manageMaps:
            return Image(systemName: "square.stack.3d.up")
        }
    }
}

private struct TerentoBrandLockup: View {
    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            ResourceImage(name: "logo", subdirectory: "Brand")
                .scaledToFit()
                .frame(width: 28, height: 32)

            Text("Terento")
                // The website lockup uses the canonical logo symbol with the
                // Instrument Sans brand face; this uses the same native font
                // token rather than a default SwiftUI wordmark.
                .font(.terentoWordmark)
                .tracking(-0.66)
                .foregroundStyle(TerentoColors.graphite)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Terento")
    }
}

/// The update offer as one quiet line at the top of Device (DMG build only).
private struct AppUpdateBanner: View {
    let update: TerentoAppUpdateManifest
    let onDownload: () -> Void
    let onLater: () -> Void
    let onReleaseNotes: () -> Void

    private var summary: String {
        let value = update.summary?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? "A newer version of Terento is ready." : value
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "arrow.down.circle")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(TerentoColors.interactive)
                .accessibilityHidden(true)
            Text("Terento \(update.releaseLabel) is available")
                .font(.terento(.meta, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .layoutPriority(1)
            Text(summary)
                .font(.terento(.meta))
                .foregroundStyle(TerentoColors.secondaryText)
                .lineLimit(1)
                .truncationMode(.tail)
                .help(summary)
            Spacer(minLength: 12)
            if update.releaseNotesURL != nil {
                Button("What’s new ↗", action: onReleaseNotes)
                    .buttonStyle(.plain)
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.interactive)
            }
            Button("Later", action: onLater)
                .buttonStyle(.plain)
                .font(.terento(.meta, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
            Button("Download", action: onDownload)
                .buttonStyle(.plain)
                .font(.terento(.meta, weight: .semibold))
                .foregroundStyle(TerentoColors.interactive)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Terento \(update.releaseLabel) is available")
    }
}

private struct CustomMapImportConfirmationSheet: View {
    let filename: String
    let onCancel: () -> Void
    let onContinue: () -> Void

    private var safeFilename: String {
        let basename = URL(fileURLWithPath: filename).lastPathComponent
        return basename.isEmpty ? "Selected map file" : basename
    }

    var body: some View {
        TerentoConfirmationDialog(
            icon: "exclamationmark.triangle",
            role: .warning,
            title: "Import this map?",
            subtitle: safeFilename,
            message: "Terento can verify that this is a Garmin map file, but cannot verify who created it or whether you trust its source.",
            supportingMessage: "Imported map files are transferred directly from your Mac to your device. They are not sent to Terento servers.",
            primaryLabel: "Continue import",
            isDestructive: false,
            onCancel: onCancel,
            onConfirm: onContinue
        )
    }
}

private struct MapLifecycleConfirmationSheet: View {
    let title: String
    let subtitle: String
    let message: String
    let actionTitle: String
    let isDestructive: Bool
    let onCancel: () -> Void
    let onConfirm: () -> Void

    var body: some View {
        if isDestructive {
            // Destructive: the map's provider, release and size as the
            // subtitle, one body line, no Return shortcut on Remove.
            TerentoConfirmationDialog(
                icon: "trash",
                role: .error,
                title: title,
                subtitle: subtitle,
                message: message,
                primaryLabel: actionTitle,
                isDestructive: true,
                onCancel: onCancel,
                onConfirm: onConfirm
            )
        } else {
            TerentoConfirmationDialog(
                icon: "arrow.triangle.2.circlepath",
                role: .info,
                title: title,
                subtitle: subtitle,
                message: message,
                supportingMessage: "Terento will keep the current map until the new one is verified.",
                primaryLabel: actionTitle,
                isDestructive: false,
                onCancel: onCancel,
                onConfirm: onConfirm
            )
        }
    }
}

private enum InstallationFailureFollowUp {
    case backToDevice
    case tryAgain
    case manageMaps
}

/// The reason shown when a reconnect wait ends without continuing; the
/// engine no longer holds the original failure after a disconnect.
private struct InstallationFailureOverride {
    let mapTitle: String?
    let reason: String
}

/// The failure dialog's content as it was when the installation failed. A
/// disconnect resets the engine while the dialog can still be open.
private struct InstallationFailureSnapshot {
    let mapTitle: String?
    let reason: String
    let safetyMessage: String?
    let helpTopic: TroubleshootingTopic
    let issueDraft: InstallationIssueDraft
}

private enum WatchReconnectFollowUp {
    case showFailure
    case stop(String?, String)
    case resume(WatchReconnectWait)
}

/// Shown on the page instead of the failure dialog after a stop before any
/// write because the watch was busy or no longer visible. It only waits;
/// reconnecting the same watch starts the normal installation again.
private struct WatchReconnectWaitPanel: View {
    let watchWasBusy: Bool
    let isCheckingWatch: Bool
    let onCancel: () -> Void

    private var message: String {
        if isCheckingWatch {
            return "Your device is back. Terento is checking it again before it continues with the map it already downloaded."
        }
        let steps = "Unplug your device, wait 5 seconds and plug it back in. Terento then checks it again and continues with the map it already downloaded."
        return watchWasBusy
            ? "Your device may be in use by another app. Quit Garmin Express and similar apps. " + steps
            : "Terento could not reach your device before installing. " + steps
    }

    private var title: String {
        isCheckingWatch ? "Checking your device" : "Reconnect your device"
    }

    private var icon: String {
        isCheckingWatch ? "arrow.triangle.2.circlepath" : "cable.connector"
    }

    private var role: TerentoDialogRole {
        isCheckingWatch ? .info : .warning
    }

    /// VoiceOver hears the state when the wait appears and when it changes.
    private func announceState() {
        NSAccessibility.post(element: NSApp as Any, notification: .announcementRequested, userInfo: [
            .announcement: title,
            .priority: NSAccessibilityPriorityLevel.high.rawValue
        ])
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // No map name here: the wait is about the watch, not one map.
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(role.color)
                    .frame(width: 15)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.terento(.meta, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                    Text(message)
                        .font(.terento(.meta, weight: .regular))
                        .foregroundStyle(TerentoColors.graphite)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Nothing was written to your device. Terento waits up to 5 minutes.")
                        .font(.terento(.caption))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 4)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
            .overlay {
                RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                    .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
            }
            .accessibilityElement(children: .combine)

            // The only action: Escape ends the wait like Cancel, as the dialog did.
            SecondaryButton(title: "Cancel", action: onCancel)
                .keyboardShortcut(.cancelAction)
        }
        .accessibilityElement(children: .contain)
        .onAppear(perform: announceState)
        .onChange(of: isCheckingWatch) { _ in announceState() }
    }
}

private struct InstallationFailureDialog: View {
    let mapTitle: String?
    let reason: String
    let safetyMessage: String?
    let reportError: String?
    let onReportIssue: () -> Void
    let onBackToDevice: () -> Void
    /// Offered only for transient failures where nothing was written.
    var onTryAgain: (() -> Void)? = nil
    /// Offered when a map file may remain on the watch after the failure.
    var onManageMaps: (() -> Void)? = nil
    var helpTopic: TroubleshootingTopic? = nil
    var onSendSupportReport: (() -> Void)? = nil

    private static let gitHubReportGuidance = "Report issue copies the full report and opens GitHub. If the form is not filled in, click its report field and press ⌘A, then ⌘V. Review before submitting."

    private var reportGuidance: String {
        onSendSupportReport == nil ? Self.gitHubReportGuidance
            : Self.gitHubReportGuidance + " No GitHub account? Send the report to Terento instead."
    }

    private var primaryAction: (label: String, action: () -> Void)? {
        if let onTryAgain { return ("Try again", onTryAgain) }
        if let onManageMaps { return ("Go to Manage maps", onManageMaps) }
        return nil
    }

    private var supportingMessage: String? {
        [safetyMessage, onManageMaps == nil ? nil : InstallationFailure.leftoverMapFollowUp,
         reportGuidance, reportError]
            .compactMap { value in
                let normalized = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return normalized.isEmpty ? nil : normalized
            }
            .joined(separator: "\n\n")
            .nilIfEmpty
    }

    var body: some View {
        TerentoConfirmationDialog(
            icon: "exclamationmark.circle",
            role: .error,
            title: "Installation stopped",
            subtitle: mapTitle ?? "",
            message: "The map could not be installed.",
            detailMessage: reason,
            supportingMessage: supportingMessage,
            secondaryLabel: "Report issue",
            secondaryAssetIcon: "GitHubMark",
            secondaryUsesCancelShortcut: false,
            tertiaryLabel: primaryAction == nil ? nil : "Back to device",
            onTertiary: onBackToDevice,
            primaryLabel: primaryAction?.label ?? "Back to device",
            isDestructive: false,
            onCancel: onReportIssue,
            onConfirm: primaryAction?.action ?? onBackToDevice,
            helpTopic: helpTopic,
            onSendSupportReport: onSendSupportReport
        )
        .accessibilityElement(children: .contain)
    }
}

#if TERENTO_APP_STORE
/// The answer to the sharing question. Not now records no choice.
private enum SharingDecision: Equatable {
    case share
    case notNow
    case dontShare
}

/// A sharing question waiting after one successful operation: on the Done
/// page after an installation, above the list in Manage maps after an update.
private struct SharingQuestion: Equatable {
    let operationID: UUID
    let isUpdate: Bool
}

/// Shown in App Store builds after a successful installation or update while
/// no sharing choice is recorded, at most twice (AppStoreReviewPolicy).
/// Nothing is pre-selected: Share, Not now and Don't share carry equal
/// weight and none is the default action.
private struct InstallSharingCallout: View {
    let onDecide: (SharingDecision) -> Void

    private var shareDetails: AttributedString {
        var link = AttributedString("Privacy Policy ↗")
        link.link = TerentoAppLinks.privacyFromApp
        link.foregroundColor = TerentoColors.interactive
        link.font = Font.terento(.caption, weight: .semibold)
        return AttributedString("Share whether installs work on your watch, so we can fix problems faster. No serial numbers or files. ") + link
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Help improve Terento")
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .accessibilityAddTraits(.isHeader)
                Text(shareDetails)
                    .font(.terento(.caption))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                SecondaryButton(title: "Share") { onDecide(.share) }
                SecondaryButton(title: "Not now") { onDecide(.notNow) }
                SecondaryButton(title: "Don't share") { onDecide(.dontShare) }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
    }
}
#endif

private struct TerentoConfirmationDialog: View {
    let icon: String
    let iconIsAsset: Bool
    let role: TerentoDialogRole
    let title: String
    let subtitle: String
    let message: String
    let detailMessage: String?
    let supportingMessage: String?
    /// nil leaves only the primary action (a result the user acknowledges).
    let secondaryLabel: String?
    let secondaryAssetIcon: String?
    let secondaryUsesCancelShortcut: Bool
    let tertiaryLabel: String?
    let onTertiary: () -> Void
    /// nil shows only the secondary action, for a dialog that only waits.
    let primaryLabel: String?
    let isDestructive: Bool
    let onCancel: () -> Void
    let onConfirm: () -> Void
    /// Extra content under the message, e.g. a sharing choice or a link.
    let accessory: AnyView?
    /// Optional text links below the message: the matching guide section and
    /// the Terento support report. Neither is a primary action.
    var helpTopic: TroubleshootingTopic? = nil
    var onSendSupportReport: (() -> Void)? = nil

    init(
        icon: String,
        iconIsAsset: Bool = false,
        role: TerentoDialogRole,
        title: String,
        subtitle: String = "",
        message: String,
        detailMessage: String? = nil,
        supportingMessage: String? = nil,
        secondaryLabel: String? = "Cancel",
        secondaryAssetIcon: String? = nil,
        secondaryUsesCancelShortcut: Bool = true,
        tertiaryLabel: String? = nil,
        onTertiary: @escaping () -> Void = {},
        primaryLabel: String?,
        isDestructive: Bool,
        onCancel: @escaping () -> Void = {},
        onConfirm: @escaping () -> Void,
        accessory: AnyView? = nil,
        helpTopic: TroubleshootingTopic? = nil,
        onSendSupportReport: (() -> Void)? = nil
    ) {
        self.helpTopic = helpTopic
        self.onSendSupportReport = onSendSupportReport
        self.icon = icon
        self.iconIsAsset = iconIsAsset
        self.role = role
        self.title = title
        self.subtitle = subtitle
        self.message = message
        self.detailMessage = detailMessage
        self.supportingMessage = supportingMessage
        self.secondaryLabel = secondaryLabel
        self.secondaryAssetIcon = secondaryAssetIcon
        self.secondaryUsesCancelShortcut = secondaryUsesCancelShortcut
        self.tertiaryLabel = tertiaryLabel
        self.onTertiary = onTertiary
        self.primaryLabel = primaryLabel
        self.isDestructive = isDestructive
        self.onCancel = onCancel
        self.onConfirm = onConfirm
        self.accessory = accessory
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            TerentoDialogHeader(icon: icon, iconIsAsset: iconIsAsset, role: role, title: title, subtitle: subtitle)

            // Body text lines up with the title, not with the icon.
            VStack(alignment: .leading, spacing: 0) {
                Text(message)
                    .font(.terento(TerentoDialogMetrics.bodyRole, weight: .regular))
                    .foregroundStyle(TerentoColors.graphite)
                    .fixedSize(horizontal: false, vertical: true)

                if let detailMessage, !detailMessage.isEmpty {
                    Text(detailMessage)
                        .font(.terento(TerentoDialogMetrics.bodyRole, weight: .semibold))
                        .foregroundStyle(TerentoColors.error)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 10)
                }

                if let supportingMessage, !supportingMessage.isEmpty {
                    Text(supportingMessage)
                        .font(.terento(TerentoDialogMetrics.supportingRole, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 10)
                }

                if let accessory {
                    accessory.padding(.top, 14)
                }

                if helpTopic != nil || onSendSupportReport != nil {
                    HStack(spacing: 18) {
                        if let onSendSupportReport {
                            Button(action: onSendSupportReport) {
                                Label("Send report to Terento", systemImage: "paperplane")
                            }
                            .buttonStyle(.plain)
                            .font(.terento(.meta, weight: .semibold))
                            .foregroundStyle(TerentoColors.interactive)
                            .accessibilityHint("Shows exactly what will be sent before anything is sent.")
                        }
                        if let helpTopic {
                            TerentoHelpLink(topic: helpTopic)
                        }
                    }
                    .padding(.top, 12)
                }
            }
            .padding(.leading, TerentoDialogMetrics.iconCircle + TerentoDialogMetrics.iconTitleGap)
            .padding(.top, 12)

            HStack(spacing: TerentoDialogMetrics.buttonGap) {
                Spacer(minLength: 0)

                if let secondaryLabel {
                    if secondaryUsesCancelShortcut {
                        TerentoDialogButton(secondaryLabel, assetIcon: secondaryAssetIcon, action: onCancel)
                            .keyboardShortcut(.cancelAction)
                    } else {
                        TerentoDialogButton(secondaryLabel, assetIcon: secondaryAssetIcon, action: onCancel)
                    }
                }

                if let tertiaryLabel {
                    TerentoDialogButton(tertiaryLabel, action: onTertiary)
                }

                if let primaryLabel {
                    if isDestructive {
                        // Return never confirms a destructive action; Escape still cancels.
                        TerentoDialogButton(primaryLabel, kind: .destructive, action: onConfirm)
                    } else {
                        TerentoDialogButton(primaryLabel, kind: .primary, action: onConfirm)
                            .keyboardShortcut(.defaultAction)
                    }
                }
            }
            .padding(.top, 20)
        }
        .padding(TerentoDialogMetrics.padding)
        .frame(width: TerentoDialogMetrics.width)
        .background(
            TerentoColors.canvas,
            in: RoundedRectangle(cornerRadius: TerentoDialogMetrics.sheetRadius, style: .continuous)
        )
        .clipShape(RoundedRectangle(cornerRadius: TerentoDialogMetrics.sheetRadius, style: .continuous))
        .preferredColorScheme(.light)
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

private struct SidebarConnectionStatus: View {
    let state: DeviceConnectionState
    let detectionPhase: DeviceDetectionPhase
    let canEject: Bool
    let isInstalling: Bool
    let showsEject: Bool
    let onEject: () -> Void

    private var label: String {
        isInstalling ? "Installing…" : ConnectionStatusPresentation.label(for: state, phase: detectionPhase)
    }

    private var statusColor: Color {
        isInstalling ? TerentoColors.interactive : ConnectionStatusPresentation.color(for: state, phase: detectionPhase)
    }

    private var statusIcon: String {
        isInstalling ? "arrow.down.circle" : ConnectionStatusPresentation.systemImage(for: state, phase: detectionPhase)
    }

    private var ejectPresentation: SafeEjectPresentation {
        SafeEjectPresentation.resolve(state: state, canEject: canEject)
    }

    var body: some View {
        HStack(spacing: 8) {
            HStack(spacing: 7) {
                Image(systemName: statusIcon)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(statusColor)
                    .frame(width: 14)
                    .accessibilityHidden(true)

                Text(label)
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(
                isInstalling
                    ? "Map installation status: Installing"
                    : "Connection status: \(label)"
            )

            Spacer(minLength: 8)

            if showsEject, ejectPresentation != .hidden {
                Button(action: onEject) {
                    Image(systemName: "eject")
                        .font(.system(size: 11, weight: .regular))
                        .foregroundStyle(
                            ejectPresentation == .enabled
                                ? TerentoColors.interactive
                                : TerentoColors.inactiveBorder
                        )
                        .frame(width: 28, height: 28)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(ejectPresentation != .enabled)
                .help(
                    isInstalling
                        ? "Eject is unavailable while installing maps."
                        : "Eject Garmin"
                )
                .accessibilityLabel("Eject Garmin")
                .accessibilityHint(
                    isInstalling
                        ? "Eject is unavailable while installing maps."
                        : ejectPresentation == .enabled
                        ? "Safely disconnects your Garmin device."
                        : "Unavailable while a device operation is in progress."
                )
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

}

/// Every sidebar status pairs its text with an icon; colour only supports it.
/// The icons reuse the Connect page's symbols.
private enum ConnectionStatusPresentation {
    static func label(for state: DeviceConnectionState, phase: DeviceDetectionPhase) -> String {
        switch state {
        case .disconnected:
            return "Disconnected"
        case .detecting:
            if case .needsAttention = phase {
                return "Needs attention"
            }
            return "Waiting…"
        case .connected, .ready:
            return "Connected"
        case .ejecting:
            return "Disconnecting…"
        case .safeToDisconnect:
            return "Safe to disconnect"
        case .failed:
            return "Couldn't connect to Garmin"
        }
    }

    static func systemImage(for state: DeviceConnectionState, phase: DeviceDetectionPhase) -> String {
        switch state {
        case .disconnected:
            return "cable.connector"
        case .detecting:
            switch phase {
            case .waitingForWatch:
                return "cable.connector"
            case .connecting:
                return "arrow.triangle.2.circlepath"
            case .needsAttention:
                return "exclamationmark.circle.fill"
            }
        case .connected, .ready, .safeToDisconnect:
            return "checkmark.circle.fill"
        case .ejecting:
            return "eject"
        case .failed:
            return "exclamationmark.triangle.fill"
        }
    }

    static func color(for state: DeviceConnectionState, phase: DeviceDetectionPhase) -> Color {
        switch state {
        case .connected, .ready:
            return TerentoColors.lichen
        case .detecting:
            if case .needsAttention = phase {
                return TerentoColors.warning
            }
            return TerentoColors.sky
        case .ejecting:
            return TerentoColors.sky
        case .safeToDisconnect:
            return TerentoColors.lichenDark
        case .failed:
            return TerentoColors.error
        case .disconnected:
            return TerentoColors.secondaryText
        }
    }
}

private struct SidebarSectionRow: View {
    let title: String
    let icon: Image
    let isSelected: Bool

    var body: some View {
        HStack(spacing: 13) {
            icon
                .font(.system(size: 17, weight: .regular))
                .foregroundStyle(isSelected ? TerentoColors.interactive : TerentoColors.secondaryText)
                .frame(width: 24)
                .accessibilityHidden(true)

            Text(title)
                .font(.terento(.meta, weight: isSelected ? .medium : .regular))
                // Interactive Hover: 4.6:1 on the selected tint (Interactive Primary is 4.1:1, below AA for text).
                .foregroundStyle(isSelected ? TerentoColors.interactiveHover : TerentoColors.secondaryText)
                .lineLimit(1)
                // Fill the row instead of a Spacer, whose own gap left "Manage maps" too little width.
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 14)
        .frame(height: 50)
        .background(
            isSelected ? TerentoColors.selectedBackground : .clear,
            in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
        )
    }
}

private struct TerentoPageShell<Content: View>: View {
    let topPadding: CGFloat
    let bottomPadding: CGFloat
    let maxHeight: CGFloat?
    private let content: () -> Content

    init(
        topPadding: CGFloat = TerentoPageLayout.primaryTopPadding,
        bottomPadding: CGFloat = TerentoPageLayout.primaryBottomPadding,
        maxHeight: CGFloat? = nil,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.topPadding = topPadding
        self.bottomPadding = bottomPadding
        self.maxHeight = maxHeight
        self.content = content
    }

    var body: some View {
        content()
            .frame(maxWidth: TerentoPageLayout.maxWidth, alignment: .topLeading)
            .frame(maxWidth: .infinity, maxHeight: maxHeight, alignment: .topLeading)
            .padding(.horizontal, TerentoPageLayout.horizontalPadding)
            .padding(.top, topPadding)
            .padding(.bottom, bottomPadding)
    }
}

/// One shared action row for every page with Back and/or a primary action.
/// Both slots inherit the same content grid and vertical center.
private struct TerentoPageFooter<Leading: View, Trailing: View>: View {
    private let leading: () -> Leading
    private let trailing: () -> Trailing

    init(
        @ViewBuilder leading: @escaping () -> Leading,
        @ViewBuilder trailing: @escaping () -> Trailing
    ) {
        self.leading = leading
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            leading()

            Spacer(minLength: 0)

            trailing()
        }
        .frame(
            maxWidth: TerentoPageLayout.maxWidth,
            minHeight: TerentoPageLayout.footerMinHeight,
            alignment: .center
        )
    }
}

/// The Install Maps body has two explicit vertical regions: header/content
/// and the bounded map-selection viewport. Storage shares the footer row with
/// Continue, so the list keeps all remaining height and cannot consume the
/// footer.
private struct TerentoInstallMapsVerticalLayout<Header: View, MapRegion: View>: View {
    private let header: () -> Header
    private let mapRegion: () -> MapRegion

    init(
        @ViewBuilder header: @escaping () -> Header,
        @ViewBuilder mapRegion: @escaping () -> MapRegion
    ) {
        self.header = header
        self.mapRegion = mapRegion
    }

    var body: some View {
        TerentoInstallMapsVerticalRegionLayout {
            header()
            mapRegion()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

private struct TerentoInstallMapsVerticalRegionLayout: Layout {
    private static let minimumListHeight: CGFloat = 90

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        guard subviews.count == 2 else {
            return CGSize(
                width: proposal.width ?? 0,
                height: proposal.height ?? 0
            )
        }

        let width = proposal.width ?? intrinsicWidth(for: subviews)
        let headerHeight = subviews[0]
            .sizeThatFits(ProposedViewSize(width: width, height: nil))
            .height
        let minimumHeight = headerHeight + Self.minimumListHeight

        let height: CGFloat
        if let proposedHeight = proposal.height, proposedHeight.isFinite {
            height = proposedHeight
        } else {
            height = minimumHeight
        }

        return CGSize(width: width, height: height)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        guard subviews.count == 2 else { return }

        let headerHeight = subviews[0]
            .sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
            .height
        let listHeight = max(0, bounds.height - headerHeight)

        subviews[0].place(
            at: CGPoint(x: bounds.minX, y: bounds.minY),
            anchor: .topLeading,
            proposal: ProposedViewSize(width: bounds.width, height: headerHeight)
        )
        subviews[1].place(
            at: CGPoint(x: bounds.minX, y: bounds.minY + headerHeight),
            anchor: .topLeading,
            proposal: ProposedViewSize(width: bounds.width, height: listHeight)
        )
    }

    private func intrinsicWidth(for subviews: Subviews) -> CGFloat {
        subviews.reduce(CGFloat.zero) { width, subview in
            max(width, subview.sizeThatFits(.unspecified).width)
        }
    }
}

/// A scroll view whose height is supplied by TerentoInstallMapsVerticalLayout.
/// It owns only the map rows; the footer with Storage is a sibling.
private struct TerentoBoundedMapSelectionRegion<Content: View>: View {
    private let content: () -> Content

    init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }

    var body: some View {
        ScrollView {
            content()
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.vertical, 2)
        }
        .scrollIndicators(.automatic)
        .frame(
            maxWidth: .infinity,
            minHeight: 0,
            maxHeight: .infinity,
            alignment: .topLeading
        )
        .clipped()
        .accessibilityLabel("Available maps list")
    }
}

/// Page shell with a body that absorbs available height and a footer that is
/// independent from the body's content height. Long bodies scroll inside the
/// body region; short bodies remain top anchored with flexible space below.
private struct TerentoFooterPageShell<Content: View, Footer: View>: View {
    let topPadding: CGFloat
    let bottomPadding: CGFloat
    let bodyScrolls: Bool
    private let content: () -> Content
    private let footer: () -> Footer

    init(
        topPadding: CGFloat = TerentoPageLayout.primaryTopPadding,
        bottomPadding: CGFloat = TerentoPageLayout.footerBottomPadding,
        bodyScrolls: Bool = true,
        @ViewBuilder content: @escaping () -> Content,
        @ViewBuilder footer: @escaping () -> Footer
    ) {
        self.topPadding = topPadding
        self.bottomPadding = bottomPadding
        self.bodyScrolls = bodyScrolls
        self.content = content
        self.footer = footer
    }

    var body: some View {
        VStack(spacing: 0) {
            Group {
                if bodyScrolls {
                    ScrollView {
                        pageContent
                    }
                    .scrollIndicators(.automatic)
                } else {
                    GeometryReader { proxy in
                        pageContent
                            .frame(
                                width: proxy.size.width,
                                height: proxy.size.height,
                                alignment: .topLeading
                            )
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            footer()
                .frame(
                    maxWidth: TerentoPageLayout.maxWidth,
                    minHeight: TerentoPageLayout.footerMinHeight,
                    alignment: .center
                )
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.top, 18)
                .padding(.horizontal, TerentoPageLayout.horizontalPadding)
                .padding(.bottom, bottomPadding)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private var pageContent: some View {
        content()
            .frame(maxWidth: TerentoPageLayout.maxWidth, alignment: .topLeading)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(.horizontal, TerentoPageLayout.horizontalPadding)
            .padding(.top, topPadding)
    }
}

/// Install-flow variant of the shared footer shell. Install pages use the
/// same global title origin as Device and Manage maps.
private struct TerentoInstallFooterPageShell<Content: View, Footer: View>: View {
    let bodyScrolls: Bool
    private let content: () -> Content
    private let footer: () -> Footer

    init(
        bodyScrolls: Bool = true,
        @ViewBuilder content: @escaping () -> Content,
        @ViewBuilder footer: @escaping () -> Footer
    ) {
        self.bodyScrolls = bodyScrolls
        self.content = content
        self.footer = footer
    }

    var body: some View {
        TerentoFooterPageShell(
            topPadding: TerentoPageLayout.primaryTopPadding,
            bottomPadding: TerentoPageLayout.footerBottomPadding,
            bodyScrolls: bodyScrolls,
            content: content,
            footer: footer
        )
    }
}

/// The active installation page has no footer. It measures the real body
/// viewport so short operations remain stationary with a visible bottom gap,
/// while genuinely taller content receives one native page scroll surface.
private struct TerentoInstallationProgressPageShell<Content: View>: View {
    private let bottomBreathingRoom: CGFloat = 28
    private let content: () -> Content

    init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                content()
                    .frame(maxWidth: TerentoPageLayout.maxWidth, alignment: .topLeading)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .frame(
                        minHeight: max(
                            0,
                            proxy.size.height
                                - TerentoPageLayout.primaryTopPadding
                                - bottomBreathingRoom
                        ),
                        alignment: .topLeading
                    )
                    .padding(.horizontal, TerentoPageLayout.horizontalPadding)
                    .padding(.top, TerentoPageLayout.primaryTopPadding)
                    .padding(.bottom, bottomBreathingRoom)
            }
            .scrollIndicators(.automatic)
            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .topLeading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

/// Shared title/subtitle treatment for pages that expose map sections.
private struct TerentoPageHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: TerentoPageLayout.titleSubtitleSpacing) {
            Text(title)
                .font(.terento(.pageTitle))
                .foregroundStyle(TerentoColors.graphite)

            if !subtitle.isEmpty {
                Text(subtitle)
                    .font(.terento(.lede))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// Shared section container keeps Manage Maps and Install Maps on one rhythm.
private struct TerentoMapSection<Content: View>: View {
    let title: String
    let count: Int
    @Binding var isExpanded: Bool
    private let content: () -> Content

    init(
        title: String,
        count: Int,
        isExpanded: Binding<Bool>,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.title = title
        self.count = count
        self._isExpanded = isExpanded
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            TerentoMapSectionHeader(
                title: title,
                count: count,
                isExpanded: $isExpanded
            )

            if isExpanded {
                content()
                    .padding(.top, TerentoPageLayout.sectionContentTopPadding)
            }
        }
    }
}

/// One shared footer action control for every page that navigates back.
private struct TerentoBackButton: View {
    let title: String
    let action: () -> Void

    init(title: String = "Back", action: @escaping () -> Void) {
        self.title = title
        self.action = action
    }

    var body: some View {
        SecondaryButton(title: title, action: action)
    }
}

struct PrimaryButton: View {
    let title: String
    let systemImage: String?
    let height: CGFloat
    let width: CGFloat?
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    init(
        title: String,
        systemImage: String? = nil,
        height: CGFloat = 44,
        width: CGFloat? = nil,
        action: @escaping () -> Void = {}
    ) {
        self.title = title
        self.systemImage = systemImage
        self.height = height
        self.width = width
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 9) {
                if let systemImage {
                    Image(systemName: systemImage)
                }

                Text(title)
            }
            .font(.terento(.meta, weight: .semibold))
            .foregroundStyle(isEnabled ? .white : TerentoColors.secondaryText)
            .padding(.horizontal, 16)
            .frame(width: width, height: height)
            .background(
                isEnabled ? TerentoColors.interactive : TerentoColors.border,
                in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
            )
        }
        .buttonStyle(.plain)
        .keyboardShortcut(.defaultAction)
        .opacity(isEnabled ? 1 : 0.78)
    }
}

struct DeviceCard: View {
    let presentation: DevicePresentation
    let canEject: Bool
    let onEject: () -> Void
    /// Server-owned install verdict. Shown only while it is not "Ready for
    /// maps": the page subtitle and the sidebar already say connected and
    /// ready. The local capability line is information in the same states.
    var authorization: DeviceAuthorizationPresentation? = nil
    var onRetryAuthorization: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .center, spacing: 20) {
            DeviceAssetImage(asset: presentation.asset)
                .frame(width: 178, height: 214)
                .accessibilityLabel("Garmin device image")

            VStack(alignment: .leading, spacing: 0) {
                Text(presentation.deviceName)
                    .font(.terento(.deviceName))
                    .foregroundStyle(TerentoColors.graphite)

                Text(presentation.variant)
                    .font(.terento(.rowTitle, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .padding(.top, 6)

                if let authorization, authorization.tone != .success {
                    DeviceAuthorizationStatusView(
                        presentation: authorization,
                        onRetry: onRetryAuthorization
                    )
                    .padding(.top, 9)
                }

                if authorization?.tone != .success {
                    MapSupportView(status: presentation.mapSupport)
                        .padding(.top, 9)
                }

                Button(action: onEject) {
                    Label("Eject device", systemImage: "eject")
                        .font(.terento(.meta))
                        .foregroundStyle(canEject ? TerentoColors.interactive : TerentoColors.secondaryText)
                        .padding(.horizontal, 10)
                        .frame(minHeight: 44) // page action: 44 like Install/Manage maps; 40 is for dialogs
                        .background(
                            canEject
                                ? TerentoColors.canvas
                                : TerentoColors.border.opacity(0.55),
                            in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
                        )
                        .overlay {
                            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
                                .strokeBorder(
                                    canEject
                                        ? TerentoColors.border
                                        : TerentoColors.inactiveBorder,
                                    lineWidth: 1
                                )
                        }
                }
                .buttonStyle(.plain)
                .disabled(!canEject)
                .accessibilityLabel("Eject device")
                .accessibilityHint(
                    canEject
                        ? "Safely disconnects your Garmin device."
                        : "Unavailable while a device operation is in progress."
                )
                .padding(.top, 12)
            }

            Spacer(minLength: 16)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension DeviceAuthorizationPresentation.Tone {
    var color: Color {
        switch self {
        case .neutral: return TerentoColors.interactive
        case .success: return TerentoColors.lichenDark
        case .warning: return TerentoColors.warning
        case .error: return TerentoColors.error
        }
    }
}

/// Text + icon verdict for map installation; colour only supports it.
private struct DeviceAuthorizationStatusView: View {
    let presentation: DeviceAuthorizationPresentation
    let onRetry: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: presentation.systemImage)
                    .font(.system(size: 12, weight: .semibold))
                    .padding(.top, 2)

                VStack(alignment: .leading, spacing: 2) {
                    Text(presentation.title)
                        .font(.terento(.meta))

                    if let detail = presentation.detail {
                        Text(detail)
                            .font(.terento(.caption, weight: .regular))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .foregroundStyle(presentation.tone.color)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Map installation: \(presentation.title). \(presentation.detail ?? "")")

            if presentation.canRetry, let onRetry {
                Button("Try again", action: onRetry)
                    .buttonStyle(.plain)
                    .font(.terento(.caption, weight: .semibold))
                    .foregroundStyle(TerentoColors.interactive)
                    .padding(.leading, 18)
                    .accessibilityHint("Checks again whether this device can install maps.")
            }
        }
    }
}

private struct MapSupportView: View {
    let status: GarminMapSupportStatus

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 2) {
                Text(status.userLabel)
                    .font(.terento(.meta))

                if !status.canUseTerentoMaps {
                    Text(status.userMessage)
                        .font(.terento(.caption, weight: .regular))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .foregroundStyle(color)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(status.userLabel). \(status.userMessage)")
    }

    private var icon: String {
        status.canUseTerentoMaps ? "checkmark.circle.fill" : "info.circle.fill"
    }

    private var color: Color {
        status.canUseTerentoMaps
            ? TerentoColors.lichenDark
            : TerentoColors.secondaryText
    }
}

private struct DeviceAssetImage: View {
    let asset: ResolvedDeviceAsset

    var body: some View {
        if let image = loadImage() {
            Image(nsImage: image)
                .resizable()
                .interpolation(.high)
                .scaledToFit()
                // Official Garmin product media currently has a white studio
                // background. Multiply lets that white surface visually
                // resolve to Terento's canvas without altering the source
                // asset or its attribution metadata.
                .blendMode(asset.isFallback ? .normal : .multiply)
                .accessibilityLabel(asset.isFallback ? "Generic Garmin device" : "Garmin device")
        } else {
            ZStack {
                Circle()
                    .fill(TerentoColors.lichen.opacity(0.18))

                Image(systemName: "applewatch")
                    .font(.system(size: 80, weight: .light))
                    .foregroundStyle(TerentoColors.lichenDark)
            }
            .padding(28)
            .accessibilityLabel("Generic Garmin device placeholder")
        }
    }

    private func loadImage() -> NSImage? {
        if let url = asset.cachedFileURL,
           let image = NSImage(contentsOf: url) {
            return image
        }

        // A catalog asset can become unreadable after a cache or bundle
        // change. Keep the Device screen visual rather than leaving an empty
        // image area; the neutral bundled watch is never used as identity or
        // compatibility evidence.
        guard let url = Bundle.module.url(
                  forResource: "generic-garmin-watch",
                  withExtension: "png",
                  subdirectory: "Devices"
              ) ?? Bundle.module.url(
                  forResource: "generic-garmin-watch",
                  withExtension: "png"
              ) else {
            return nil
        }

        return NSImage(contentsOf: url)
    }
}

private struct ManageMapRow: View {
    let item: MapLifecycleItem
    /// Names the provider for VoiceOver, as the provider filter does.
    let providerLabel: String
    let availability: MapLifecycleActionAvailability
    let operation: MapLifecycleOperationState?
    var timeRemaining: RemainingTimeEstimate? = nil
    let isLifecycleBusy: Bool
    let onRemove: () -> Void
    let onUpdate: () -> Void

    private var operationIsActive: Bool {
        guard let operation else { return false }
        switch operation.phase {
        case .removing, .updating, .verifying, .downloading, .checking,
             .preparing, .installing, .removingOld, .finishing:
            return true
        case .idle, .awaitingConfirmation, .completed, .failed:
            return false
        }
    }

    private var availableActions: [MapLifecycleAction] {
        ManageMapRowActionPresentation.productionActions(for: availability)
    }

    private var primaryActions: [MapLifecycleAction] {
        ManageMapRowActionPresentation.productionPrimaryActions(for: availability)
    }

    var body: some View {
        TerentoMapRow(
            title: item.title,
            detail: item.manageRowMetadata,
            status: manageStatus,
            note: operation == nil && !availability.updateBlocked ? availability.updateNotice : nil,
            contentSpacing: 9,
            rowVerticalPadding: 10
        ) {
            Image(systemName: item.failedInstallRecovery == nil ? "map" : "exclamationmark.triangle")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(item.failedInstallRecovery == nil ? TerentoColors.lichenDark : TerentoColors.error)
                .frame(width: 24, height: 24)
        } trailing: {
            if let operation, operationIsActive {
                VStack(alignment: .leading, spacing: 4) {
                    ManageOperationProgress(operation: operation)
                    // The time line keeps its height while empty, so the row
                    // does not grow when "Less than a minute left" appears.
                    HStack(spacing: 10) {
                        ZStack(alignment: .leading) {
                            Label("Less than a minute left", systemImage: "clock")
                                .labelStyle(.titleAndIcon)
                                .font(.terento(.caption))
                                .hidden()
                            if let timeRemaining {
                                TimeRemainingLabel(estimate: timeRemaining)
                            }
                        }
                        Spacer(minLength: 0)
                    }
                }
                .frame(width: InstallationTimelineLayout.manageProgressWidth, alignment: .leading)
            } else if !availableActions.isEmpty {
                ManageActionGroup(
                    mapTitle: providerLabel.isEmpty ? item.title : "\(item.title), \(providerLabel)",
                    primaryActions: primaryActions,
                    updateBlocked: availability.updateBlocked,
                    isEnabled: !isLifecycleBusy,
                    onAction: perform
                )
            }
        }
    }

    /// Line 3: a failed operation (error) or why Update is blocked (warning).
    private var manageStatus: TerentoMapRowStatus? {
        if let operation, case .failed = operation.phase {
            return TerentoMapRowStatus(text: operation.message, color: TerentoColors.error)
        }
        guard availability.updateBlocked, let reason = availability.reason, !reason.isEmpty else { return nil }
        return TerentoMapRowStatus(text: reason)
    }

    private func perform(_ action: MapLifecycleAction) {
        switch action {
        case .remove:
            onRemove()
        case .update:
            onUpdate()
        case .transferOwnership, .recoverOwnership:
            break
        }
    }
}

/// All Garmin-installed images in Manage as one row: file count and total size
/// only. It takes no actions and has no context menu.
private struct GarminMapsSummaryRow: View {
    let summary: GarminMapsSummary

    var body: some View {
        TerentoMapRow(
            title: GarminMapsSummary.title,
            detail: summary.detail,
            contentSpacing: 9,
            rowVerticalPadding: 10
        ) {
            Image(systemName: "map")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
                .frame(width: 24, height: 24)
                .accessibilityHidden(true)
        } trailing: {
            EmptyView()
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(GarminMapsSummary.title), \(summary.detail)")
    }
}

private struct ManageActionGroup: View {
    let mapTitle: String
    let primaryActions: [MapLifecycleAction]
    var updateBlocked: Bool = false
    let isEnabled: Bool
    let onAction: (MapLifecycleAction) -> Void

    var body: some View {
        HStack(spacing: 9) {
            if updateBlocked {
                ManageActionButton(action: .update, mapTitle: mapTitle, isEnabled: false, onAction: onAction)
            }
            ForEach(primaryActions.filter { $0 == .update }, id: \.rawValue) { action in
                ManageActionButton(
                    action: action,
                    mapTitle: mapTitle,
                    isEnabled: isEnabled,
                    onAction: onAction
                )
            }

            ForEach(primaryActions.filter { $0 == .remove }, id: \.rawValue) { action in
                ManageActionButton(
                    action: action,
                    mapTitle: mapTitle,
                    isEnabled: isEnabled,
                    onAction: onAction
                )
            }
        }
        .frame(width: 152, alignment: .trailing)
        .frame(minHeight: 36, alignment: .center)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Map actions")
    }
}

/// Draws the label exactly as the view colours it. The system plain and
/// borderless styles fade their content when the window is not key, and
/// Remove and Refresh then nearly disappeared (QA 1.3.0-local); text here
/// keeps its token colour, and with it AA contrast, in an inactive window.
/// Disabled colours are set by the label itself.
private struct TerentoKeyIndependentButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.78 : 1)
            .contentShape(Rectangle())
    }
}

private struct ManageActionButton: View {
    let action: MapLifecycleAction
    let mapTitle: String
    let isEnabled: Bool
    let onAction: (MapLifecycleAction) -> Void
    @Environment(\.isEnabled) private var environmentIsEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @FocusState private var isFocused: Bool
    @State private var isHovered = false

    private var title: String {
        switch action {
        case .update:
            return "Update"
        case .transferOwnership, .recoverOwnership:
            return "Action unavailable"
        case .remove:
            return "Remove"
        }
    }

    private var isInteractive: Bool {
        isEnabled && environmentIsEnabled
    }

    var body: some View {
        Button {
            onAction(action)
        } label: {
            Text(title)
                .font(.terento(.caption, weight: .semibold))
                .foregroundStyle(foregroundColor)
                .lineLimit(1)
                .padding(.horizontal, 8)
                .frame(minWidth: action == .update ? 72 : 68, minHeight: 30)
                .background(
                    backgroundColor,
                    in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control, style: .continuous)
                )
                .overlay {
                    RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control, style: .continuous)
                        .stroke(focusColor, lineWidth: isFocused ? 2 : 1)
                }
        }
        .buttonStyle(TerentoKeyIndependentButtonStyle())
        .controlSize(.small)
        .focused($isFocused)
        .disabled(!isEnabled)
        .contentShape(RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control, style: .continuous))
        .onHover { hovering in
            if reduceMotion {
                isHovered = hovering
            } else {
                withAnimation(.easeOut(duration: 0.12)) {
                    isHovered = hovering
                }
            }
        }
        .help(title)
        .accessibilityLabel("\(title) \(mapTitle)")
    }

    private var backgroundColor: Color {
        guard isInteractive else {
            return Color.clear
        }
        if action == .update {
            if isFocused {
                return TerentoColors.interactive.opacity(0.88)
            }
            if isHovered {
                return TerentoColors.interactive.opacity(0.90)
            }
            return TerentoColors.interactive
        }
        if isFocused {
            return TerentoColors.sky.opacity(0.20)
        }
        if isHovered {
            return TerentoColors.sky.opacity(0.12)
        }
        return Color.clear
    }

    private var foregroundColor: Color {
        // Disabled text token: plain grey Remove text read as still active.
        guard isInteractive else {
            return TerentoGeneratedTokens.Light.textDisabled
        }
        return action == .update ? .white : TerentoColors.graphite
    }

    private var focusColor: Color {
        guard isInteractive else {
            return Color.clear
        }
        if isFocused {
            return TerentoColors.interactive.opacity(0.86)
        }
        if isHovered {
            return TerentoColors.border.opacity(0.72)
        }
        return Color.clear
    }
}

private struct ManageOperationProgress: View {
    let operation: MapLifecycleOperationState

    private var isRemoval: Bool {
        operation.action == .remove
    }

    private var progress: SafeUpdateProgress? {
        guard let progress = operation.progress,
              (progress.totalBytes > 0 || progress.phaseFraction != nil) else {
            return nil
        }
        return progress
    }

    private var measuredFraction: Double? {
        TerentoProgressBar.measured(progress?.fractionCompleted)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(operation.phase.userLabel)
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Spacer()

                // Same rule as the install steps: % only for a measured value.
                if let measuredFraction {
                    Text("\(Int(measuredFraction * 100))%")
                        .font(.terento(.meta, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                }
            }

            if let progress {
                TerentoProgressBar(value: progress.fractionCompleted, label: operation.phase.userLabel)

                if isRemoval {
                    Text(progress.detail ?? "Verifying map removal")
                        .font(.terento(.caption))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .lineLimit(1)
                } else if progress.phaseFraction != nil {
                    Text(progress.detail ?? operation.message)
                        .font(.terento(.caption))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    HStack(spacing: 8) {
                        Text("\(formatBytes(progress.bytesCompleted)) of \(formatBytes(progress.totalBytes))")
                        if progress.bytesPerSecond > 0 {
                            Text("\(formatBytesPerSecond(progress.bytesPerSecond))/s")
                        }
                    }
                    .font(.terento(.caption))
                    .foregroundStyle(TerentoColors.secondaryText)
                }
            } else if isRemoval {
                TerentoProgressBar(value: 0, label: operation.phase.userLabel)

                Text("Verifying map removal")
                    .font(.terento(.caption))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .lineLimit(1)
            } else {
                TerentoProgressBar(value: 0, label: operation.phase.userLabel)
                Text(operation.message)
                    .font(.terento(.caption))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
        }
        .frame(width: InstallationTimelineLayout.manageProgressWidth, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(operation.message)
        .accessibilityValue(accessibilityValue)
    }

    private var accessibilityValue: String {
        guard let progress else {
            return operation.message
        }
        if isRemoval || progress.phaseFraction != nil {
            return "\(Int(progress.fractionCompleted * 100)) percent, \(progress.detail ?? operation.message)"
        }
        var value = "\(Int(progress.fractionCompleted * 100)) percent, "
            + "\(formatBytes(progress.bytesCompleted)) of \(formatBytes(progress.totalBytes))"
        if progress.bytesPerSecond > 0 {
            value += ", \(formatBytesPerSecond(progress.bytesPerSecond)) per second"
        }
        return value
    }

    private func formatBytes(_ bytes: UInt64) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(bytes, UInt64(Int64.max))),
            countStyle: .decimal
        )
    }

    private func formatBytesPerSecond(_ bytes: Double) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(max(bytes, 0), Double(Int64.max))),
            countStyle: .decimal
        )
    }
}

/// The third line of a map row: a blocked or warning message, never part of
/// the metadata line. Its colour matches the row's status icon.
struct TerentoMapRowStatus: Equatable {
    let text: String
    var color: Color = TerentoColors.warning
}

private struct TerentoMapRow<LeadingContent: View, TrailingContent: View>: View {
    let title: String
    let detail: String?
    let status: TerentoMapRowStatus?
    let note: String?
    let contentSpacing: CGFloat
    let rowVerticalPadding: CGFloat
    let showsDivider: Bool
    /// An optional status shown next to the title, always with an icon.
    let badge: (text: String, systemImage: String)?
    let leadingContent: LeadingContent
    let trailingContent: TrailingContent

    init(
        title: String,
        detail: String?,
        status: TerentoMapRowStatus? = nil,
        note: String? = nil,
        contentSpacing: CGFloat = 14,
        rowVerticalPadding: CGFloat = 13,
        showsDivider: Bool = true,
        badge: (text: String, systemImage: String)? = nil,
        @ViewBuilder leading: () -> LeadingContent,
        @ViewBuilder trailing: () -> TrailingContent
    ) {
        self.badge = badge
        self.title = title
        self.detail = detail
        self.status = status
        self.note = note
        self.contentSpacing = contentSpacing
        self.rowVerticalPadding = rowVerticalPadding
        self.showsDivider = showsDivider
        self.leadingContent = leading()
        self.trailingContent = trailing()
    }

    var body: some View {
        HStack(alignment: .top, spacing: contentSpacing) {
            leadingContent

            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(title)
                        .font(.terento(.rowTitle))
                        .foregroundStyle(TerentoColors.graphite)

                    if let badge {
                        Label(badge.text, systemImage: badge.systemImage)
                            .labelStyle(.titleAndIcon)
                            .font(.terento(.caption, weight: .semibold))
                            .foregroundStyle(TerentoColors.interactive)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 2)
                            .background(TerentoColors.interactive.opacity(0.10), in: Capsule())
                    }
                }

                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.terento(.meta))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

                if let status, !status.text.isEmpty {
                    Text(status.text)
                        .font(.terento(.meta, weight: .semibold))
                        .foregroundStyle(status.color)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let note, !note.isEmpty {
                    Text(note)
                        .font(.terento(.meta))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 2)
                }
            }

            Spacer(minLength: 12)

            trailingContent
        }
        .modifier(
            MapRowSurface(
                verticalPadding: rowVerticalPadding,
                showsDivider: showsDivider
            )
        )
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The one Terento progress bar: 6 pt, capsule ends, border-colour track.
/// Activity fills with interactive; storage with lichen plus an optional sky
/// segment for the selected maps. A nil value is indeterminate.
struct TerentoProgressBar: View {
    let value: Double?
    var selectedValue: Double = 0
    var fill: Color = TerentoColors.interactive
    var label: String = "Progress"
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var sweeping = false

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(TerentoColors.border)
                if let value {
                    let filled = width * Self.clamped(value)
                    if selectedValue > 0 {
                        Capsule()
                            .fill(TerentoColors.sky)
                            .frame(width: min(width, filled + width * Self.clamped(selectedValue)))
                    }
                    Capsule()
                        .fill(fill)
                        .frame(width: filled)
                } else {
                    Capsule()
                        .fill(fill)
                        .frame(width: width * 0.3)
                        .offset(x: sweeping ? width * 0.7 : 0)
                }
            }
            .clipShape(Capsule())
        }
        .frame(height: InstallationTimelineLayout.progressBarHeight)
        .onAppear(perform: startSweepIfNeeded)
        .onChange(of: value == nil) { _ in startSweepIfNeeded() }
        .accessibilityElement()
        .accessibilityLabel(label)
        .accessibilityValue(value.map { "\(Int(Self.clamped($0) * 100)) percent" } ?? "In progress")
    }

    private func startSweepIfNeeded() {
        guard value == nil, !reduceMotion, !sweeping else { return }
        withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
            sweeping = true
        }
    }

    static func clamped(_ value: Double) -> Double {
        value.isFinite ? min(1, max(0, value)) : 0
    }

    /// The % next to a bar, only once something was measured; before that the
    /// bar is shown without a number (no "0%").
    static func measured(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0 else { return nil }
        return value
    }
}

struct StorageCard: View {
    let total: String
    let available: String
    let fillRatio: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Storage")
                .font(.terento(.rowTitle))
                .foregroundStyle(TerentoColors.graphite)

            Text("\(available) free of \(total)")
                .font(.terento(.meta))
                .foregroundStyle(TerentoColors.graphite)

            TerentoProgressBar(value: normalizedFillRatio, fill: TerentoColors.lichen, label: "Storage")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage: \(available) free of \(total)")
        .accessibilityValue("\(Int(normalizedFillRatio * 100)) percent used")
    }

    private var normalizedFillRatio: Double {
        min(1, max(0, fillRatio.isFinite ? fillRatio : 0))
    }
}

struct MapStatusRow: View {
    let title: String
    let detail: String
    let status: String
    let note: String?
    /// An error row uses the error icon and colour together, never colour alone.
    var isError: Bool = false
    var onRetry: (() -> Void)? = nil

    private var accent: Color { isError ? TerentoColors.error : TerentoColors.lichenDark }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: isError ? "exclamationmark.triangle.fill" : "map")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(accent)
                    .frame(width: 24, height: 24)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 5) {
                    Text(title)
                        .font(.terento(.rowTitle))
                        .foregroundStyle(TerentoColors.graphite)

                    Text(detail)
                        .font(.terento(.meta))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

                Spacer(minLength: 8)

                Text(status)
                    .font(.terento(.caption, weight: .semibold))
                    .foregroundStyle(accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background((isError ? TerentoColors.error.opacity(0.12) : TerentoColors.lichen.opacity(0.22)), in: Capsule())
            }

            if let note, !note.isEmpty {
                Text(note)
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let onRetry {
                SecondaryButton(title: "Try again", action: onRetry)
                    .accessibilityHint("Reads the maps on your device again.")
            }
        }
        .padding(22)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }
}

private struct ReadyToInstallSelectedMapsHeader: View {
    let count: Int

    private var countLabel: String {
        "\(count) \(count == 1 ? "map" : "maps")"
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: TerentoPageLayout.sectionHeaderItemSpacing) {
            Text("Selected maps")
                .font(.terento(.rowTitle))
                .foregroundStyle(TerentoColors.graphite)

            Text(countLabel)
                .font(.terento(.caption, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Selected maps, \(countLabel)")
    }
}

private struct InstallationMapsSectionHeader: View {
    let count: Int

    private var countLabel: String {
        "\(count) \(count == 1 ? "map" : "maps")"
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: TerentoPageLayout.sectionHeaderItemSpacing) {
            Text("Selected maps")
                .font(.terento(.rowTitle))
                .foregroundStyle(TerentoColors.graphite)

            Text(countLabel)
                .font(.terento(.caption, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Installing maps, \(countLabel)")
    }
}

/// The result of a finished installation and what to do on the Garmin, in
/// one card so the steps line up with the result.
private struct InstallationResultCallout: View {
    let mapNames: [String]
    let isPartial: Bool

    private static let iconSize: CGFloat = 15
    private static let iconTextGap: CGFloat = 8

    private var resultTitle: String {
        mapNames.count == 1 ? "\(mapNames[0]) is on your Garmin" : "\(mapNames.count) maps are on your Garmin"
    }

    private var steps: [String] {
        [
            "Eject it here, then unplug it.",
            mapNames.count == 1 ? "Open map settings and turn the new map on." : "Open map settings and turn the new maps on.",
            "Not in the list? Restart the device."
        ]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: Self.iconTextGap) {
                Image(systemName: isPartial ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                    .font(.system(size: Self.iconSize, weight: .semibold))
                    .foregroundStyle(isPartial ? TerentoColors.error : TerentoColors.lichenDark)
                    .frame(width: Self.iconSize)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text(resultTitle)
                        .font(.terento(.meta, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                    if isPartial {
                        Text("The optional contours were not completed.")
                            .font(.terento(.meta, weight: .regular))
                            .foregroundStyle(TerentoColors.graphite)
                    }
                }
            }
            .accessibilityElement(children: .combine)

            VStack(alignment: .leading, spacing: 8) {
                Text("On your Garmin")
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("\(index + 1).")
                            .monospacedDigit()
                        Text(step)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .font(.terento(.meta, weight: .regular))
                    .foregroundStyle(TerentoColors.graphite)
                    .accessibilityElement(children: .combine)
                }
            }
            .padding(.leading, Self.iconSize + Self.iconTextGap)
            .padding(.top, 14)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card))
        .overlay {
            RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.card)
                .stroke(TerentoColors.border, lineWidth: 1)
        }
    }
}

private struct InstalledMapsSectionHeader: View {
    let count: Int

    private var countLabel: String {
        "\(count) \(count == 1 ? "map" : "maps")"
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: TerentoPageLayout.sectionHeaderItemSpacing) {
            Text(count == 1 ? "Installed map" : "Installed maps")
                .font(.terento(.rowTitle))
                .foregroundStyle(TerentoColors.graphite)

            if count > 1 {
                Text(countLabel)
                    .font(.terento(.caption, weight: .semibold))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(count == 1 ? "Installed map" : "Installed maps, \(countLabel)")
    }
}

private struct InstallationMapsList: View {
    let items: [MapSelectionItem]
    let accessibilityLabel: String

    private static let visibleRowCapacity = 3
    private static let rowHeight: CGFloat = 62
    private static let contentTopPadding: CGFloat = 2
    private var visibleListHeight: CGFloat {
        CGFloat(min(items.count, Self.visibleRowCapacity)) * Self.rowHeight
            + Self.contentTopPadding
    }

    init(items: [MapSelectionItem], accessibilityLabel: String = "Maps being installed") {
        self.items = items
        self.accessibilityLabel = accessibilityLabel
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                    MapSelectionRow(
                        item: item,
                        isSelected: .constant(false),
                        isAvailable: false,
                        showsSelectionControl: false,
                        showsSize: true,
                        showsDivider: MapRowDividerPolicy.showsDivider(
                            at: index,
                            in: items.count
                        )
                    )
                    .frame(minHeight: Self.rowHeight)
                }
            }
            .padding(.top, Self.contentTopPadding)
        }
        .scrollIndicators(items.count > Self.visibleRowCapacity ? .automatic : .hidden)
        .frame(
            maxWidth: .infinity,
            minHeight: visibleListHeight,
            idealHeight: visibleListHeight,
            maxHeight: visibleListHeight,
            alignment: .topLeading
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel(accessibilityLabel)
    }
}

private struct ReadyToInstallSelectedMapsList: View {
    let plan: InstallationPlan

    private static let visibleRowCapacity = 3
    private static let rowHeight: CGFloat = 62
    private static let contentTopPadding: CGFloat = 2
    private var visibleListHeight: CGFloat {
        CGFloat(min(componentRowCount, Self.visibleRowCapacity)) * Self.rowHeight
            + Self.contentTopPadding
    }

    var body: some View {
        ScrollView {
            rows
        }
        .scrollIndicators(
            componentRowCount > Self.visibleRowCapacity ? .automatic : .hidden
        )
        .frame(
            maxWidth: .infinity,
            minHeight: 0,
            idealHeight: visibleListHeight,
            maxHeight: visibleListHeight,
            alignment: .topLeading
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Selected maps list")
    }

    private var rows: some View {
        VStack(spacing: 0) {
            ForEach(Array(plan.selectedPackagePlans.enumerated()), id: \.element.item.id) { packageIndex, packagePlan in
                MapSelectionRow(
                    item: packagePlan.item,
                    isSelected: .constant(false),
                    isAvailable: false,
                    showsSelectionControl: false,
                    showsSize: true,
                    showsDivider: packagePlan.artifactPlan.optionalArtifacts.isEmpty
                        ? !isLastComponent(packageIndex: packageIndex, artifactIndex: nil)
                        : true
                )
                .frame(minHeight: Self.rowHeight)

                ForEach(
                    Array(packagePlan.artifactPlan.optionalArtifacts.enumerated()),
                    id: \.element.id
                ) { artifactIndex, artifact in
                    SelectedMapArtifactSummaryRow(
                        artifact: artifact,
                        providerVersionLabel: packagePlan.item.providerVersionLabel,
                        showsDivider: !isLastComponent(
                            packageIndex: packageIndex,
                            artifactIndex: artifactIndex
                        )
                    )
                }
            }
        }
        .padding(.top, Self.contentTopPadding)
    }

    private var componentRowCount: Int {
        plan.selectedPackagePlans.reduce(0) { count, packagePlan in
            count + 1 + packagePlan.artifactPlan.optionalArtifacts.count
        }
    }

    private func isLastComponent(packageIndex: Int, artifactIndex: Int?) -> Bool {
        guard packageIndex == plan.selectedPackagePlans.count - 1,
              let lastPackage = plan.selectedPackagePlans.last else {
            return false
        }

        guard let artifactIndex else {
            return lastPackage.artifactPlan.optionalArtifacts.isEmpty
        }

        return artifactIndex == lastPackage.artifactPlan.optionalArtifacts.count - 1
    }
}

private struct SelectedMapArtifactSummaryRow: View {
    let artifact: MapArtifact
    let providerVersionLabel: String?
    let showsDivider: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: "map")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(TerentoColors.lichenDark)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 5) {
                Text(artifactTitle)
                    .font(.terento(.rowTitle))
                    .foregroundStyle(TerentoColors.graphite)

                Text(providerVersionLabel ?? "Optional map component")
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.secondaryText)
            }

            Spacer(minLength: 12)

            Text(artifact.sizeBytes.map(formatBytes) ?? "Size calculated before installation")
                .font(.terento(.meta))
                .foregroundStyle(TerentoColors.secondaryText)
                .multilineTextAlignment(.trailing)
                .frame(maxWidth: 190, alignment: .trailing)
        }
        .padding(.leading, 38)
        .modifier(
            MapRowSurface(
                verticalPadding: 10,
                showsDivider: showsDivider
            )
        )
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(artifactTitle), \(artifact.sizeBytes.map(formatBytes) ?? "size calculated before installation")")
    }

    private var artifactTitle: String {
        switch artifact.kind {
        case .contours:
            return "Contour lines"
        case .main:
            return "Map"
        }
    }

    private func formatBytes(_ bytes: UInt64) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(bytes, UInt64(Int64.max))),
            countStyle: .decimal
        )
    }
}

struct MapSelectionRow: View {
    let item: MapSelectionItem
    @Binding var isSelected: Bool
    @Binding var selectedOptionalArtifactIDs: Set<String>
    let isAvailable: Bool
    let selectionEnabled: Bool
    let showsSelectionControl: Bool
    let showsSize: Bool
    let showsDivider: Bool
    /// First map selection only: highlight the locale recommendation.
    let highlightsRecommendation: Bool
    /// Install selection: "Download 412 MB · about 4 min".
    let downloadEstimate: String?
    /// Already installed: Manage maps offers a safe Update for this map.
    let updateOfferedInManage: Bool

    init(
        item: MapSelectionItem,
        isSelected: Binding<Bool>,
        selectedOptionalArtifactIDs: Binding<Set<String>> = .constant([]),
        isAvailable: Bool,
        selectionEnabled: Bool = true,
        showsSelectionControl: Bool = true,
        showsSize: Bool? = nil,
        showsDivider: Bool = true,
        highlightsRecommendation: Bool = false,
        downloadEstimate: String? = nil,
        updateOfferedInManage: Bool = false
    ) {
        self.updateOfferedInManage = updateOfferedInManage
        self.highlightsRecommendation = highlightsRecommendation
        self.downloadEstimate = downloadEstimate
        self.item = item
        self._isSelected = isSelected
        self._selectedOptionalArtifactIDs = selectedOptionalArtifactIDs
        self.isAvailable = isAvailable
        self.selectionEnabled = selectionEnabled
        self.showsSelectionControl = showsSelectionControl
        self.showsSize = showsSize ?? (isAvailable && item.comparison.installedMap == nil)
        self.showsDivider = showsDivider
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            TerentoMapRow(
                title: item.title,
                detail: detail,
                status: rowStatus.map { TerentoMapRowStatus(text: $0) },
                note: item.acquisitionAvailability.detailedExplanation,
                contentSpacing: 9,
                rowVerticalPadding: 6,
                showsDivider: !showsOptionalControl,
                badge: showsRecommendation
                    ? (FirstMapGuidance.recommendedLabel, "star.fill") : nil
            ) {
                HStack(spacing: 6) {
                    if showsSelectionControl {
                        ZStack {
                            // Keep the map icon and title in the same column when
                            // an installed or unavailable row has no checkbox.
                            Color.clear
                                .accessibilityHidden(true)

                            if isAvailable && item.isSelectable && selectionEnabled {
                                Toggle("", isOn: $isSelected)
                                    .toggleStyle(.checkbox)
                                    .tint(TerentoColors.interactive)
                                    .labelsHidden()
                            } else if crossProviderSelectionDisabled {
                                Toggle("", isOn: .constant(false))
                                    .toggleStyle(.checkbox)
                                    .tint(TerentoColors.interactive)
                                    .labelsHidden()
                                    .disabled(true)
                                    .help("Choose maps from one provider at a time.")
                            } else if item.acquisitionAvailability == .available
                                && !isAlreadyInstalledSearchResult {
                                Image(systemName: statusIcon)
                                    .font(.system(size: 17, weight: .semibold))
                                    .foregroundStyle(statusColor)
                                    .frame(width: 18)
                            }
                        }
                        .frame(width: 18, height: 18)
                    }

                    Image(systemName: "map")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(TerentoColors.lichenDark)
                        .frame(width: 24)
                }
            } trailing: {
                if showsSize && item.acquisitionAvailability == .available {
                    VStack(alignment: .trailing, spacing: 3) {
                        Text(item.installSizeBytes.map(formatBytes) ?? "Size calculated before installation")
                            .font(.terento(.meta))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .multilineTextAlignment(.trailing)
                        if let downloadEstimate {
                            Text(downloadEstimate)
                                .font(.terento(.caption))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                    .frame(maxWidth: 190, alignment: .trailing)
                } else if item.acquisitionAvailability != .available {
                    Text("Unavailable")
                        .font(.terento(.meta))
                        .foregroundStyle(TerentoColors.secondaryText)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .onTapGesture {
                guard isAvailable, item.isSelectable, selectionEnabled else { return }
                isSelected.toggle()
            }
            .opacity(crossProviderSelectionDisabled || item.acquisitionAvailability != .available ? 0.62 : 1)
            .help(crossProviderSelectionDisabled ? "Choose maps from one provider at a time." : "")
            .accessibilityElement(children: .combine)
            .accessibilityLabel(accessibilityLabel)
            .accessibilityValue(isAvailable && item.isSelectable && selectionEnabled && showsSelectionControl
                ? (isSelected ? "Selected" : "Not selected")
                : [detail, rowStatus].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", "))
            .accessibilityHint(
                crossProviderSelectionDisabled
                    ? "Unavailable for this installation because maps from another provider are already selected."
                    : ""
            )

            if showsOptionalControl {
                VStack(alignment: .leading, spacing: 4) {
                    Toggle(
                        "Add contour lines",
                        isOn: Binding(
                            get: {
                                selectedOptionalArtifactIDs.contains(
                                    item.usableOptionalArtifacts[0].id
                                )
                            },
                            set: { selected in
                                let artifactID = item.usableOptionalArtifacts[0].id
                                if selected {
                                    selectedOptionalArtifactIDs.insert(artifactID)
                                } else {
                                    selectedOptionalArtifactIDs.remove(artifactID)
                                }
                            }
                        )
                    )
                    .toggleStyle(.checkbox)
                    .tint(TerentoColors.interactive)
                    .font(.terento(.meta, weight: .semibold))
                    .accessibilityLabel("Add contour lines for \(item.title)")
                    .accessibilityHint("Adds elevation lines for understanding terrain and steepness.")

                    Text("Shows elevation and terrain steepness. Useful for hiking and mountain biking.")
                        .font(.terento(.caption, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.leading, 24)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 38)
                .padding(.bottom, 10)
                .overlay(alignment: .bottom) {
                    if showsDivider {
                        Rectangle()
                            .fill(TerentoColors.border.opacity(0.82))
                            .frame(height: 1)
                    }
                }
            }
        }
    }

    /// Line 2: provider and release, plus "Already installed" or the size
    /// note where it applies. Blocked and warning messages are `rowStatus`.
    private var detail: String {
        let baseDetail: String

        if item.package.sourceKind == .custom, item.acquisitionAvailability.shortStatus == nil {
            return "From this Mac"
        } else if rowStatus != nil {
            baseDetail = ""
        } else if isAlreadyInstalledSearchResult {
            baseDetail = item.alreadyInstalledDetail(updateOffered: updateOfferedInManage)
        } else {
            switch item.comparison.status {
            case .notInstalled:
                baseDetail = item.installSizeBytes == nil || item.preflightStatus == .blockedUnknownInstallSize
                    ? "Size calculated before installation"
                    : ""
            case .updateAvailable:
                baseDetail = "Installed · Update available"
            case .upToDate:
                baseDetail = "Installed · Up to date"
            case .newerInstalled:
                baseDetail = "Installed · Newer version installed"
            case .unknown:
                baseDetail = "Installed · Version unavailable"
            }
        }

        guard item.package.sourceKind == .provider else {
            return baseDetail
        }

        let providerVersion = item.providerVersionLabel
        let values = [providerVersion, baseDetail.isEmpty ? nil : baseDetail]
            .compactMap { $0 }
        return values.joined(separator: " · ")
    }

    /// Line 3: why this map can't be installed now, on its own line.
    private var rowStatus: String? {
        if let status = item.acquisitionAvailability.shortStatus {
            return status
        }
        guard item.package.sourceKind != .custom,
              !isAlreadyInstalledSearchResult,
              item.comparison.status == .notInstalled,
              let preflightStatus = item.preflightStatus else { return nil }
        switch preflightStatus {
        case .blockedUnsupportedDevice:
            return "This device has no validated Terento install profile yet"
        case .blockedUnknownTarget:
            return "Install target is not validated for this device"
        case .blockedAmbiguousMapIdentity:
            return "Map identity needs to be checked before installation"
        case .blockedMapTypeConflict:
            return item.preflightReason ?? BBBikeProviderAdapter.unverifiedTypeConflictMessage(for: item.package)
        case .blockedInsufficientSpace:
            return "Not enough space for a safe installation"
        case .error:
            return "Could not prepare this map for installation"
        case .blockedUnknownInstallSize, .readyNewInstall, .readyWithExistingMapConflict:
            return nil
        }
    }

    private var statusIcon: String {
        if rowStatus != nil {
            return "exclamationmark.triangle"
        }
        switch item.comparison.status {
        case .updateAvailable:
            return "arrow.clockwise.circle"
        case .upToDate:
            return "checkmark.circle.fill"
        case .notInstalled, .newerInstalled, .unknown:
            return "circle"
        }
    }

    private var statusColor: Color {
        if rowStatus != nil {
            return TerentoColors.warning
        }
        switch item.comparison.status {
        case .updateAvailable:
            return TerentoColors.interactive
        case .upToDate:
            return TerentoColors.lichenDark
        case .notInstalled, .newerInstalled, .unknown:
            return TerentoColors.secondaryText
        }
    }

    private var accessibilityLabel: String {
        if item.acquisitionAvailability != .available {
            return "\(item.comparison.providerName), \(item.acquisitionAccessibilityLabel ?? "\(item.title), unavailable")"
        }

        if isAlreadyInstalledSearchResult {
            return "\(item.title), \(item.comparison.providerName), \(item.alreadyInstalledDetail(updateOffered: updateOfferedInManage))"
        }

        if showsSize {
            let guidance = [showsRecommendation ? FirstMapGuidance.recommendedLabel : nil, downloadEstimate]
                .compactMap { $0 }.map { ", \($0)" }.joined()
            return (item.installSizeBytes.map {
                "\(item.title), \(item.comparison.providerName), \(formatBytes($0))"
            } ?? "\(item.title), \(item.comparison.providerName), size calculated before installation") + guidance
        }
        return [item.title, detail, rowStatus].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", ")
    }

    private var isAlreadyInstalledSearchResult: Bool {
        isAvailable && item.comparison.installedMap != nil
    }

    private var showsRecommendation: Bool {
        // Only rows the user can actually tick get the recommendation badge.
        highlightsRecommendation && item.isRecommended && isAvailable
            && item.comparison.installedMap == nil && item.acquisitionAvailability == .available
            && item.isSelectable && selectionEnabled
    }

    private var crossProviderSelectionDisabled: Bool {
        isAvailable
            && item.isSelectable
            && !selectionEnabled
            && showsSelectionControl
            && item.package.sourceKind == .provider
            && item.acquisitionAvailability == .available
            && !isAlreadyInstalledSearchResult
    }

    private var showsOptionalControl: Bool {
        isAvailable
            && isSelected
            && !crossProviderSelectionDisabled
            && !item.usableOptionalArtifacts.isEmpty
            && showsSelectionControl
    }

    private func formatBytes(_ bytes: UInt64) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(bytes, UInt64(Int64.max))),
            countStyle: .decimal
        )
    }
}

private struct MapRowSurface: ViewModifier {
    let verticalPadding: CGFloat
    let showsDivider: Bool

    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 4)
            .padding(.vertical, verticalPadding)
            .overlay(alignment: .bottom) {
                if showsDivider {
                    Rectangle()
                        .fill(TerentoColors.border.opacity(0.82))
                        .frame(height: 1)
                }
            }
    }
}

private struct TerentoDisclosureIndicator: View {
    let isExpanded: Bool

    var body: some View {
        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(TerentoColors.secondaryText)
            .frame(
                width: TerentoPageLayout.sectionHeaderChevronWidth,
                height: TerentoPageLayout.sectionHeaderChevronHeight,
                alignment: .center
            )
            .accessibilityHidden(true)
    }
}

private struct TerentoMapSectionHeader: View {
    let title: String
    let count: Int
    @Binding var isExpanded: Bool

    private var countLabel: String {
        "\(count) \(count == 1 ? "map" : "maps")"
    }

    var body: some View {
        Button {
            isExpanded.toggle()
        } label: {
            HStack(
                alignment: .center,
                spacing: TerentoPageLayout.sectionHeaderItemSpacing
            ) {
                TerentoDisclosureIndicator(isExpanded: isExpanded)

                Text(title)
                    .font(.terento(.rowTitle))
                    .foregroundStyle(TerentoColors.graphite)

                Text(countLabel)
                    .font(.terento(.caption, weight: .semibold))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
            .frame(minHeight: TerentoPageLayout.sectionHeaderMinHeight, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(title), \(countLabel)")
        .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")
        .accessibilityHint("Shows or hides \(title.lowercased()).")
    }
}

struct MapSelectionStorageSummary: View {
    let plan: InstallationPlan
    let totalCapacity: UInt64
    let formatBytes: (UInt64) -> String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text("Storage")
                    .font(.terento(.rowTitle))
                    .foregroundStyle(TerentoColors.graphite)

                Spacer(minLength: 12)

                Text("\(formatBytes(plan.storagePlan.currentFreeSpace)) free of \(formatBytes(totalCapacity))")
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.graphite)
                    .multilineTextAlignment(.trailing)
            }

            let projection = StorageBarProjection(
                plan: plan.storagePlan,
                totalCapacity: totalCapacity
            )
            TerentoProgressBar(
                value: projection.fraction(for: projection.existingUsedBytes),
                selectedValue: projection.fraction(for: projection.selectedMapBytes),
                fill: TerentoColors.lichen,
                label: "Storage"
            )
            .accessibilityHidden(true)

            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(selectedMapSummary)
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.secondaryText)

                Spacer(minLength: 12)

                Text(afterInstallationSummary)
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .multilineTextAlignment(.trailing)
            }

            if !statusText.isEmpty {
                Text(statusText)
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(statusColor)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage")
        .accessibilityValue(storageAccessibilityValue)
    }

    fileprivate var statusText: String {
        if plan.selectedItems.isEmpty {
            return ""
        }
        if plan.selectedItems.count > InstallationPlan.maximumMapsPerOperation {
            return InstallationPlan.tooManyMapsReason
        }
        if plan.storagePlan.hasUnresolvedInstallSize {
            return "Map size will be checked before installation."
        }
        if plan.storagePlan.isAllowed {
            return ""
        }
        return plan.storagePlan.insufficientSpaceMessage(formatBytes: formatBytes)
    }

    fileprivate var statusColor: Color {
        if plan.selectedItems.count > InstallationPlan.maximumMapsPerOperation {
            return TerentoColors.error
        }
        if plan.selectedItems.isEmpty || plan.storagePlan.hasUnresolvedInstallSize {
            return TerentoColors.secondaryText
        }
        return plan.storagePlan.isAllowed ? TerentoColors.lichenDark : TerentoColors.error
    }

    fileprivate var storageAccessibilityValue: String {
        "\(formatBytes(plan.storagePlan.currentFreeSpace)) free of \(formatBytes(totalCapacity)), \(selectedMapSummary), \(afterInstallationSummary), \(Int(projectedUsedFraction * 100)) percent used"
            + (statusText.isEmpty ? "" : ". \(statusText)")
    }

    /// The Install maps footer line, one line at the default window size
    /// (owner decision 2026-11-22): "14.77 GB free · 0 maps selected", and
    /// with a selection "1 map · 4.07 MB selected · 14.77 GB free after
    /// installation". The provider is already on the selected rows.
    fileprivate var footerLine: String {
        let count = plan.selectedItems.count
        guard count > 0 else {
            return "\(formatBytes(plan.storagePlan.currentFreeSpace)) free · 0 maps selected"
        }
        let countLabel = "\(count) \(count == 1 ? "map" : "maps")"
        if plan.storagePlan.hasUnresolvedInstallSize {
            return "\(countLabel) selected · Size calculated before installation"
        }
        return "\(countLabel) · \(formatBytes(plan.storagePlan.selectedMapBytes)) selected · "
            + "\(formatBytes(plan.storagePlan.projectedFreeSpace)) free after installation"
    }

    fileprivate var selectedMapSummary: String {
        let count = plan.selectedItems.count
        let countLabel = "\(count) \(count == 1 ? "map" : "maps")"
        guard count > 0 else {
            return "0 maps selected"
        }
        if plan.storagePlan.hasUnresolvedInstallSize {
            return appendSelectedProvider(
                to: "\(countLabel) selected · Size calculated before installation"
            )
        }
        return appendSelectedProvider(
            to: "\(countLabel) · \(formatBytes(plan.storagePlan.selectedMapBytes)) selected"
        )
    }

    private func appendSelectedProvider(to summary: String) -> String {
        let providerNames = Set(
            plan.selectedItems.compactMap { item -> String? in
                guard item.package.sourceKind == .provider else { return nil }
                let name = item.comparison.providerName.trimmingCharacters(
                    in: .whitespacesAndNewlines
                )
                // The same "Provider (Style)" name as the row's second line.
                return name.isEmpty ? nil : MapProviderDisplay.title(providerID: item.package.providerId,
                    regionID: item.package.canonicalRegionId, fallback: name)
            }
        )
        guard providerNames.count == 1, let providerName = providerNames.first else {
            return summary
        }
        return "\(summary) · \(providerName)"
    }

    fileprivate var afterInstallationSummary: String {
        if plan.storagePlan.hasUnresolvedInstallSize {
            return "Available after size check"
        }
        return "\(formatBytes(plan.storagePlan.projectedFreeSpace)) after installation"
    }

    private var projectedUsedFraction: CGFloat {
        let projection = StorageBarProjection(
            plan: plan.storagePlan,
            totalCapacity: totalCapacity
        )
        let usedBytes = projection.existingUsedBytes + projection.selectedMapBytes
        return CGFloat(projection.fraction(for: usedBytes))
    }
}

/// Install maps Storage on the footer row, left of Continue: the bar, then
/// "14.77 GB free · 0 maps selected" and, with a selection, the free space
/// after installation. A blocking note goes on its own line below.
struct MapSelectionStorageLine: View {
    let plan: InstallationPlan
    let totalCapacity: UInt64
    let formatBytes: (UInt64) -> String

    private var summary: MapSelectionStorageSummary {
        MapSelectionStorageSummary(plan: plan, totalCapacity: totalCapacity, formatBytes: formatBytes)
    }

    private var lineText: String { summary.footerLine }

    var body: some View {
        let summary = summary
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .center, spacing: 12) {
                let projection = StorageBarProjection(
                    plan: plan.storagePlan,
                    totalCapacity: totalCapacity
                )
                TerentoProgressBar(
                    value: projection.fraction(for: projection.existingUsedBytes),
                    selectedValue: projection.fraction(for: projection.selectedMapBytes),
                    fill: TerentoColors.lichen,
                    label: "Storage"
                )
                .frame(width: 160)
                .accessibilityHidden(true)

                Text(lineText)
                    .font(.terento(.meta))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !summary.statusText.isEmpty {
                Text(summary.statusText)
                    .font(.terento(.meta, weight: .semibold))
                    .foregroundStyle(summary.statusColor)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage")
        .accessibilityValue(summary.storageAccessibilityValue)
    }
}

/// One look for the Install and Manage search field and filter pop-ups:
/// 38 pt tall, control radius, surface fill, and a focus border.
private struct ToolbarControlChrome: ViewModifier {
    var isFocused = false

    func body(content: Content) -> some View {
        content
            .font(.terento(.meta, weight: .regular))
            .padding(.horizontal, 10)
            .frame(height: 38)
            .background(
                RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control, style: .continuous)
                    .fill(TerentoColors.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control, style: .continuous)
                    .strokeBorder(isFocused ? TerentoColors.interactive : TerentoColors.border, lineWidth: isFocused ? 2 : 1)
            )
    }
}

private extension View {
    func toolbarControlChrome(isFocused: Bool = false) -> some View {
        modifier(ToolbarControlChrome(isFocused: isFocused))
    }

    /// Filter pop-up drawn in the toolbar chrome: the selected title on the
    /// left, the chevron 12 pt from the right edge, the whole field clickable.
    /// The options stay a native Picker inside the menu (checkmark, keyboard).
    func toolbarMenuPicker(width: CGFloat, title: String) -> some View {
        Menu {
            self
                .labelsHidden()
                .pickerStyle(.inline)
        } label: {
            HStack(spacing: 8) {
                Text(title)
                    .foregroundStyle(TerentoColors.graphite)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .padding(.trailing, 2) // chrome pads 10; chevron sits 12 from the edge
                    .accessibilityHidden(true)
            }
            .toolbarControlChrome()
            .frame(width: width)
            .contentShape(Rectangle())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .accessibilityValue(title)
    }
}

private struct SecondaryButton: View {
    let title: String
    /// Non-nil makes it an on/off button (Import map file). Off, its border is
    /// Text Muted, 3.45:1 against the page (WCAG 1.4.11 needs 3:1). On, it
    /// looks like the other selected controls: selected tint, Interactive
    /// border (4.07:1 on the tint) and Interactive Hover text (4.63:1).
    var isSelected: Bool? = nil
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    private var selected: Bool { isEnabled && isSelected == true }

    private var textColor: Color {
        guard isEnabled else { return TerentoColors.secondaryText }
        return selected ? TerentoColors.interactiveHover : TerentoColors.graphite
    }

    private var fillColor: Color {
        guard isEnabled else { return TerentoColors.border.opacity(0.55) }
        return selected ? TerentoColors.selectedBackground : TerentoColors.canvas
    }

    private var borderColor: Color {
        guard isEnabled else { return TerentoColors.inactiveBorder }
        if selected { return TerentoColors.interactive }
        return isSelected == nil ? TerentoColors.border : TerentoGeneratedTokens.Light.textMuted
    }

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.terento(.meta, weight: .semibold))
                .foregroundStyle(textColor)
                .padding(.horizontal, 16)
                .frame(height: 44)
                .background(fillColor, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control))
                .overlay {
                    RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
                        .strokeBorder(borderColor, lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.78)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct ResourceImage: View {
    let name: String
    let subdirectory: String

    var body: some View {
        if let image = loadImage() {
            Image(nsImage: image)
                .resizable()
                .interpolation(.high)
                .renderingMode(name == "logo" ? .template : .original)
                .foregroundStyle(name == "logo" ? TerentoColors.sky : .primary)
        } else {
            Color.clear
        }
    }

    private func loadImage() -> NSImage? {
        let fileExtension = name == "logo" ? "svg" : "png"
        let url = Bundle.module.url(
            forResource: name,
            withExtension: fileExtension
        ) ?? Bundle.module.url(
            forResource: name,
            withExtension: fileExtension,
            subdirectory: subdirectory
        )
        return url.flatMap(NSImage.init(contentsOf:))
    }
}

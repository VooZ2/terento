import AppKit
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
    static let manageProgressWidth: CGFloat = 220
}

struct ConnectScreen: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var lifecycleViewModel: MapLifecycleViewModel
    @ObservedObject var evidenceController: InstallationEvidenceController
    @ObservedObject var mapStatisticsController: MapStatisticsEventController
    @ObservedObject var appUpdateController: AppUpdateController
    @State private var selectedSection: TerentoSection = .device
    @State private var localInstallStep: LocalInstallStep = .choose
    @State private var troubleshootingExpanded = false
    @State private var selectedMapIDs: Set<String> = []
    @State private var selectedInstallationPlan: InstallationPlan?
    @State private var availableMapsExpanded = true
    @State private var importedMapsExpanded = false
    @State private var externalMapsExpanded = false
    @State private var expandedProviderMapGroups: Set<String> = []
    @State private var customMapImportExpanded = false
    @State private var customMapImportDidContinue = false
    @State private var updatePrompt: TerentoAppUpdateManifest?
    @State private var mapSearchText = ""
    @State private var selectedMapProviderID = ""
    @State private var isShowingCustomMapImporter = false
    @State private var customMapDropTargeted = false
    @FocusState private var mapSearchFieldFocused: Bool
    @State private var resolvedDeviceAsset = ResolvedDeviceAsset.fallback
    @State private var diagnosticLogMessage: String?
    @State private var isShowingInstallationFailure = false
    @State private var evidenceOperationID = UUID()
    @State private var evidenceOperationIdentity: DeviceIdentity?
    @State private var evidenceRecordedForCurrentWrite = false
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

    private var mapSupport: GarminMapSupportStatus {
        guard let identity else { return .unknown }
        return GarminMapCapabilityRegistry.local.evaluate(identity: identity)
    }

    /// Unknown map capability is still a useful read-only state. Let the user
    /// open the map screens so the app can explain the missing validation;
    /// only a model explicitly known not to support additional maps is kept
    /// out of the flow. Installation remains fail-closed at preflight.
    private var canOpenMapSections: Bool {
        deviceEngine.hasConnectedDevice && mapSupport.showsTerentoCompatibility
    }

    private var mapSelectionItems: [MapSelectionItem] {
        mapEngine.mapSelectionItems
    }

    private var providerMapSelectionItems: [MapSelectionItem] {
        mapSelectionItems.filter { item in
            guard item.package.sourceKind == .provider else { return false }
            guard !selectedMapProviderID.isEmpty else { return true }
            return MapIdentity.normalizeProvider(item.package.providerId)
                == MapIdentity.normalizeProvider(selectedMapProviderID)
        }
    }

    private var mapProviderOptions: [MapProvider] {
        mapEngine.availableMapProviders
    }

    private var customMapSelectionItems: [MapSelectionItem] {
        mapSelectionItems.filter { $0.package.sourceKind == .custom }
    }

    private var availableSelectionItems: [MapSelectionItem] {
        MapSelectionPresentationModel.available(providerMapSelectionItems, query: "")
    }

    private var filteredAvailableSelectionItems: [MapSelectionItem] {
        MapSelectionPresentationModel.available(
            providerMapSelectionItems,
            query: mapSearchText
        )
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
        return mapEngine.installationPlan(for: selectedMapIDs)
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
    }

    var body: some View {
        HStack(spacing: 0) {
            TerentoSidebar(
                selectedSection: $selectedSection,
                connectionState: deviceEngine.state,
                canEject: canSafelyEject,
                isInstalling: installationOperationIsActive,
                navigationLocked: installationOperationIsActive,
                mapNavigationEnabled: canOpenMapSections,
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
                selectedInstallationPlan = nil
                selectedMapProviderID = ""
                lifecycleViewModel.resetForDisconnectedDevice()
                mapEngine.resetForDisconnectedDevice()
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
        }
        .onChange(of: mapEngine.customMapImportState) { _ in
            updatePresenceMonitoring(for: mapEngine.state)
        }
        .onChange(of: mapEngine.customMapImportCandidate?.id) { candidateID in
            guard let candidateID else { return }
            customMapImportExpanded = true
            selectedMapIDs.insert(candidateID)
        }
        .onChange(of: mapSelectionItems) { items in
            selectedMapIDs = MapSelectionPresentationModel.validSelectionIDs(
                selectedMapIDs,
                items: items
            )
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
            recordInstallationEvidenceIfNeeded()
            if phase == .failed {
                isShowingInstallationFailure = true
            } else {
                diagnosticLogMessage = nil
            }
            if phase == .completed {
                selectedSection = .installMaps
                localInstallStep = .done
            }
        }
        .onChange(of: mapEngine.mapStatisticsEvents) { events in
            for event in events {
                mapStatisticsController.record(event)
            }
        }
        .onChange(of: lifecycleViewModel.isBusy) { _ in
            updatePresenceMonitoring(for: mapEngine.state)
        }
        .onChange(of: availableMapsExpanded) { isExpanded in
            if !isExpanded {
                mapSearchFieldFocused = false
            }
        }
        .onAppear {
            presentUpdatePromptIfSafe()
        }
        .onChange(of: appUpdateController.state) { _ in
            presentUpdatePromptIfSafe()
        }
        .onChange(of: updatePresentationIsSafe) { _ in
            presentUpdatePromptIfSafe()
        }
        .sheet(item: $updatePrompt) { update in
            AppUpdatePromptView(
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
        }
        .sheet(
            isPresented: $isShowingInstallationFailure,
            onDismiss: returnToDeviceAfterFailure
        ) {
            InstallationFailureDialog(
                mapTitle: selectedInstallationPlan.flatMap(installationFailureMapTitle),
                reason: installationFailureReason,
                safetyMessage: installationFailureSafetyMessage,
                reportError: diagnosticLogMessage,
                onReportIssue: { reportInstallationIssue(for: selectedInstallationPlan) },
                onBackToDevice: { isShowingInstallationFailure = false }
            )
            .interactiveDismissDisabled(false)
        }
    }

    private var mainContent: some View {
        Group {
            if selectedSection == .installMaps {
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

        let shouldRefreshMapInventory = section == .manageMaps
            || (section == .installMaps && !installationFlowHasStarted)

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
            case .about:
                aboutContent
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

    private func returnToDeviceAfterFailure() {
        selectedInstallationPlan = nil
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
            VStack(alignment: .center, spacing: 0) {
                Spacer(minLength: 0)

                VStack(alignment: .center, spacing: 0) {
                    ResourceImage(name: connectionIllustrationName, subdirectory: "Illustrations")
                        .scaledToFit()
                        .frame(
                            maxWidth: 720,
                            maxHeight: connectionIllustrationMaxHeight
                        )
                        .frame(maxWidth: .infinity, alignment: .center)

                    connectionStatusView
                        .padding(.top, 14)

                    if deviceEngine.state == .disconnected || deviceEngine.state == .failed {
                        PrimaryButton(
                            title: deviceEngine.state == .failed ? "Try again" : "Connect device",
                            action: startReadOnlyCheck
                        )
                            .padding(.top, 14)
                    }

                    if shouldShowTroubleshooting {
                        VStack(alignment: .leading, spacing: 0) {
                            Button {
                                troubleshootingExpanded.toggle()
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: troubleshootingExpanded ? "chevron.down" : "chevron.right")
                                        .font(.system(size: 11, weight: .semibold))

                                    Text("Having trouble connecting?")
                                        .font(.terentoUI(size: 13, weight: .medium))
                                }
                                .foregroundStyle(TerentoColors.secondaryText)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Having trouble connecting?")
                            .accessibilityValue(troubleshootingExpanded ? "Expanded" : "Collapsed")
                            .accessibilityHint("Shows troubleshooting steps.")

                            if troubleshootingExpanded {
                                troubleshootingContent
                                    .padding(.top, 7)
                            }
                        }
                        .padding(.top, 12)
                        .frame(maxWidth: 620, alignment: .center)
                    }

                }
                .frame(maxWidth: .infinity, alignment: .center)

                Spacer(minLength: 0)
            }
            .frame(maxHeight: .infinity, alignment: .center)
        }
    }

    private var connectionStatusView: some View {
        VStack(alignment: .center, spacing: TerentoPageLayout.titleSubtitleSpacing) {
            Text(connectionStatusTitle)
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, alignment: .center)

            Text(connectionStatusDescription)
                .font(.terentoBody(size: 19, weight: .medium))
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

    private var connectionIllustrationMaxHeight: CGFloat {
        if deviceEngine.state == .failed {
            return troubleshootingExpanded ? 180 : 220
        }
        return troubleshootingExpanded ? 220 : 300
    }

    private var connectionStatusTitle: String {
        switch deviceEngine.state {
        case .disconnected:
            return "Ready when you are."
        case .detecting:
            return "Waiting for your Garmin…"
        case .connected, .ready:
            return "Garmin \(deviceEngine.compatibility?.displayName ?? "watch") connected"
        case .ejecting:
            return "Releasing your Garmin…"
        case .safeToDisconnect:
            return "Safe to disconnect"
        case .failed:
            return "Garmin not found"
        }
    }

    private var connectionStatusDescription: String {
        switch deviceEngine.state {
        case .disconnected:
            return "Connect your watch to this Mac."
        case .detecting:
            return "This may take up to 2 minutes."
        case .connected, .ready:
            return "Your Garmin is ready."
        case .ejecting:
            return "Finishing the connection safely."
        case .safeToDisconnect:
            return "You can unplug your Garmin."
        case .failed:
            if let message = deviceEngine.userErrorMessage {
                return message
            }
            return "We couldn't find your Garmin within 2 minutes. Reconnect your watch and try again."
        }
    }

    private var shouldShowTroubleshooting: Bool {
        deviceEngine.state == .failed
    }

    private var troubleshootingContent: some View {
        VStack(alignment: .leading, spacing: 7) {
            troubleshootingRow("Try a different cable", icon: "cable.connector")
            troubleshootingRow("Connect directly to your Mac", icon: "desktopcomputer")
            troubleshootingRow("Make sure your watch is unlocked", icon: "lock.open")
            troubleshootingRow("Restart your watch and try again", icon: "arrow.clockwise")
            troubleshootingRow("Close other Garmin apps", icon: "xmark.app")

            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text("Still having trouble?")
                    .font(.terentoUI(size: 13, weight: .semibold))

                externalLink(
                    "Garmin connection guide ↗",
                    urlString: "https://support.garmin.com/"
                )
            }
            .foregroundStyle(TerentoColors.secondaryText)
            .padding(.top, 6)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.helpSurface, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(TerentoColors.border.opacity(0.5), lineWidth: 1)
        }
    }

    private func troubleshootingRow(_ text: String, icon: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .frame(width: 18)
                .accessibilityHidden(true)

            Text(text)
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
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

    private var aboutContent: some View {
        TerentoPageShell {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(alignment: .center, spacing: 16) {
                        ResourceImage(name: "logo", subdirectory: "Brand")
                            .scaledToFit()
                            .frame(width: 64, height: 64)

                        VStack(alignment: .leading, spacing: 5) {
                            Text("About Terento")
                                .font(.terentoHeading(size: 30, weight: .semibold))
                                .foregroundStyle(TerentoColors.graphite)

                            Text("Install maps on Garmin watches, simply.")
                                .font(.terentoBody(size: 17, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)

                            Text(TerentoAppMetadata.displayVersion)
                                .font(.terentoUI(size: 14, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                        }
                    }
                    .padding(.top, TerentoPageLayout.firstSectionTopPadding)

                    HStack(spacing: 12) {
                        PrimaryButton(title: "Update") {
                            aboutUpdateAction()
                        }
                        .disabled(appUpdateController.isChecking)

                        SecondaryButton(title: "Manage diagnostics") {
                            openWindow(id: "diagnostics")
                        }
                    }
                    .padding(.top, 20)

                    aboutUpdateStatus

                    aboutSection(title: "Support") {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 18) {
                                externalLink("GitHub repository ↗", urlString: TerentoAppLinks.repository.absoluteString)
                                externalLink("Report an issue ↗", urlString: TerentoAppLinks.issues.absoluteString)
                                externalLink("Website ↗", urlString: TerentoAppLinks.websiteFromApp.absoluteString)
                                externalLink("Donate ↗", urlString: TerentoAppLinks.donate.absoluteString)
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                externalLink("GitHub repository ↗", urlString: TerentoAppLinks.repository.absoluteString)
                                externalLink("Report an issue ↗", urlString: TerentoAppLinks.issues.absoluteString)
                                externalLink("Website ↗", urlString: TerentoAppLinks.websiteFromApp.absoluteString)
                                externalLink("Donate ↗", urlString: TerentoAppLinks.donate.absoluteString)
                            }
                        }
                    }

                    aboutSection(title: "Privacy") {
                        Text("Terento sends anonymous diagnostics by default to help improve the app and its services. Device state, maps, manifests, Unit IDs, serial numbers, and local paths stay on this Mac.")
                            .font(.terentoUI(size: 15, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)

                        Text("Terento may contact terento.app when the app starts to check whether a newer version is available. This request is not used for analytics or user tracking.")
                            .font(.terentoUI(size: 13, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)

                        HStack(spacing: 18) {
                            externalLink("Privacy ↗", urlString: TerentoAppLinks.privacyFromApp.absoluteString)
                            externalLink("Legal ↗", urlString: TerentoAppLinks.legalFromApp.absoluteString)
                        }
                        .padding(.top, 5)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private var aboutUpdateStatus: some View {
        switch appUpdateController.state {
        case .idle:
            EmptyView()
        case .checking:
            Text("Checking for updates…")
                .font(.terentoUI(size: 13, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .padding(.top, 8)
        case .upToDate:
            Text("You're using the latest version.")
                .font(.terentoUI(size: 13, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .padding(.top, 8)
        case let .available(update):
            Text("Terento \(update.displayVersion) is available. Press Update to download it.")
                .font(.terentoUI(size: 13, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 8)
        case let .incompatible(update):
            Text(
                "Terento \(update.displayVersion) requires macOS "
                    + "\(update.minimumMacOS ?? "a newer version") or later."
            )
                .font(.terentoUI(size: 13, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 8)
        case let .failed(message):
            Text(message)
                .font(.terentoUI(size: 13, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 8)
        }
    }

    private func aboutUpdateAction() {
        if case let .available(update) = appUpdateController.state {
            _ = appUpdateController.openDownload(for: update)
        } else {
            checkForAppUpdate()
        }
    }

    @ViewBuilder
    private func aboutSection<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(title)
                .font(.terentoUI(size: 18, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            content()
        }
        .padding(.top, TerentoPageLayout.sectionSpacing + 4)
    }

    @ViewBuilder
    private func externalLink(_ title: String, urlString: String) -> some View {
        if let url = URL(string: urlString) {
            Link(title, destination: url)
                .font(.terentoUI(size: 14, weight: .medium))
                .foregroundStyle(TerentoColors.interactive)
        } else {
            Text(title)
                .font(.terentoUI(size: 14, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
        }
    }

    private var managedMapsContent: some View {
        TerentoFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 16) {
                TerentoPageHeader(
                    title: "Manage maps",
                    subtitle: "Maps on your Garmin."
                )

                Spacer(minLength: 12)

                if mapEngine.state == .scanned {
                    Button {
                        refreshMapInventory()
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                            .font(.terentoUI(size: 13, weight: .medium))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(TerentoColors.secondaryText)
                    .help("Refresh map information")
                    .accessibilityLabel("Refresh map information")
                }
            }

            if let lifecycleInventory = mapEngine.mapLifecycleInventory() {
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
                            managedMapRow(item)
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

                if lifecycleInventory.allItems.isEmpty {
                    MapStatusRow(
                        title: "No maps detected",
                        detail: deviceEngine.hasConnectedDevice
                            ? "No installed maps were found on this Garmin."
                            : "Connect your Garmin watch first",
                        status: deviceEngine.hasConnectedDevice ? "Ready" : "Pending",
                        note: nil
                    )
                    .padding(.top, 30)
                }
            } else {
                MapStatusRow(
                    title: mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
                        ? "Reading your maps"
                        : "Map information is not available",
                    detail: deviceEngine.hasConnectedDevice
                        ? (mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
                            ? "Checking your Garmin watch…"
                            : "Refresh the connected Garmin watch to try again.")
                        : "Connect your Garmin watch first",
                    status: deviceEngine.hasConnectedDevice
                        ? (mapEngine.state == .loadingCatalog || mapEngine.state == .scanning
                            ? "Checking"
                            : "Pending")
                        : "Pending",
                    note: mapEngine.userErrorMessage
                )
                .padding(.top, 30)
            }

            }
        } footer: {
            TerentoPageFooter(
                leading: {
                    TerentoBackButton {
                        selectedSection = .device
                    }
                },
                trailing: {
                    EmptyView()
                }
            )
        }
        .sheet(item: $lifecycleViewModel.pendingConfirmation) { confirmation in
            MapLifecycleConfirmationSheet(
                title: confirmation.action == .remove ? "Remove this map?" : "Update this map?",
                subtitle: lifecycleViewModel.confirmationSubtitle,
                message: lifecycleViewModel.confirmationMessage,
                actionTitle: confirmation.action == .remove ? "Remove map" : "Update map",
                isDestructive: confirmation.action == .remove,
                onCancel: { lifecycleViewModel.cancelPendingAction() },
                onConfirm: { lifecycleViewModel.confirmPendingAction() }
            )
        }
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
                        .font(.terentoHeading(size: 42, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Text("Connected and ready.")
                        .font(.terentoBody(size: 19, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 20)

            }

            DeviceCard(
                presentation: presentation,
                canEject: canSafelyEject,
                onEject: performSafeEject
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
                .disabled(mapManagementActionsBusy || !presentation.mapSupport.showsTerentoCompatibility)

                SecondaryButton(title: "Manage maps") {
                    navigate(to: .manageMaps)
                }
                .disabled(mapManagementActionsBusy || !presentation.mapSupport.showsTerentoCompatibility)

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

    @ViewBuilder
    private func managedMapRow(_ item: MapLifecycleItem) -> some View {
        ManageMapRow(
            item: item,
            availability: lifecycleViewModel.availability(for: item),
            operation: lifecycleViewModel.operation(for: item.id),
            isLifecycleBusy: mapManagementActionsBusy,
            onRemove: { lifecycleViewModel.requestRemove(itemID: item.id) },
            onUpdate: { lifecycleViewModel.requestUpdate(itemID: item.id) }
        )
    }

    private func deviceVariantLine(_ snapshot: DeviceSnapshot) -> String {
        ConnectedDeviceSubtitleFormatter.format(
            identity: identity ?? GarminDeviceIdentityAdapter().makeIdentity(from: snapshot),
            fallbackModel: snapshot.model,
            manufacturer: snapshot.manufacturer
        )
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
                                    .font(.terentoUI(size: 13, weight: .medium))
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(TerentoColors.secondaryText)
                            .help("Refresh map information")
                            .accessibilityLabel("Refresh map information")
                        }
                    }

                    if mapEngine.catalogSource == .bundledFallback {
                        Label(
                            MapCatalogSource.bundledFallback.userLabel,
                            systemImage: "wifi.slash"
                        )
                        .font(.terentoUI(size: 12, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .padding(.top, 10)
                        .accessibilityHint("Terento is using its bundled local map list. It may be out of date.")
                    }

                    if mapEngine.state == .loadingCatalog || mapEngine.state == .scanning {
                        MapStatusRow(
                            title: "Reading your maps",
                            detail: "Checking your Garmin watch…",
                            status: "Checking",
                            note: "Map information will appear here when your watch is ready."
                        )
                        .padding(.top, 18)
                    } else if mapEngine.state != .scanned {
                        MapStatusRow(
                            title: "Maps are not ready yet",
                            detail: "Connect your Garmin watch first",
                            status: "Pending",
                            note: mapEngine.userErrorMessage
                                ?? "Available maps will appear here after the device is checked."
                        )
                        .padding(.top, 18)
                    } else {
                        HStack(alignment: .center, spacing: 14) {
                            TerentoMapSectionHeader(
                                title: "Available maps",
                                count: availableSelectionItems.count,
                                isExpanded: $availableMapsExpanded
                            )

                            Spacer(minLength: 10)

                            if availableMapsExpanded {
                                HStack(spacing: 10) {
                                    Picker(selection: $selectedMapProviderID) {
                                        Text("All providers").tag("")
                                        ForEach(mapProviderOptions) { provider in
                                            Text(provider.name).tag(provider.id)
                                        }
                                    } label: {
                                        EmptyView()
                                    }
                                    .labelsHidden()
                                    .pickerStyle(.menu)
                                    .frame(minWidth: 160, idealWidth: 168, maxWidth: 175, alignment: .leading)
                                    .layoutPriority(1)
                                    .accessibilityLabel("Map provider")
                                    .accessibilityHint("Filters maps without choosing a default provider.")

                                    TextField("Search countries and regions", text: $mapSearchText)
                                        .textFieldStyle(.roundedBorder)
                                        .focused($mapSearchFieldFocused)
                                        .frame(minWidth: 190, idealWidth: 290, maxWidth: 300)

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
                                .accessibilityLabel("Search available maps")
                                .accessibilityHint("Filters maps by country, region, or region code.")
                                .accessibilityValue("\(filteredAvailableSelectionItems.count) results")
                            }
                        }
                        .padding(.top, TerentoPageLayout.firstSectionTopPadding)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
            } mapRegion: {
                if mapEngine.state == .scanned {
                    VStack(alignment: .leading, spacing: 0) {
                        if availableMapsExpanded {
                            if providerMapSelectionItems.isEmpty || filteredAvailableSelectionItems.isEmpty {
                                Text(availableMapsEmptyMessage)
                                    .font(.terentoUI(size: 13, weight: .medium))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                .frame(maxWidth: .infinity, alignment: .topLeading)
                                .padding(.top, 10)
                            } else {
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
                                                        }
                                                    }
                                                ),
                                                isAvailable: true,
                                                selectionEnabled: isMapSelectionEnabled(item)
                                            )
                                        }
                                    }
                                }
                            }
                        }

                        customMapImportPanel
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, providerMapSelectionItems.isEmpty ? 12 : 22)
                    }
                    .clipped()
                } else {
                    Color.clear
                        .accessibilityHidden(true)
                }
            } storageRegion: {
                if let plan = currentInstallationPlan {
                    MapSelectionStorageSummary(
                        plan: plan,
                        totalCapacity: snapshot?.totalCapacity ?? 0,
                        formatBytes: formatBytes
                    )
                    .fixedSize(horizontal: false, vertical: true)
                } else {
                    Color.clear
                        .frame(height: 0)
                        .accessibilityHidden(true)
                }
            }
        } footer: {
            TerentoPageFooter {
                TerentoBackButton {
                    selectedSection = .device
                }
            } trailing: {
                PrimaryButton(title: "Continue") {
                    guard let plan = currentInstallationPlan, plan.canContinue else {
                        return
                    }

                    selectedInstallationPlan = plan
                    localInstallStep = .install
                }
                .disabled(!(currentInstallationPlan?.canContinue ?? false))
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
        .alert(
            item: Binding(
                get: { mapEngine.customMapImportWarning },
                set: { _ in mapEngine.dismissCustomMapImportWarning() }
            )
        ) { warning in
            Alert(
                title: Text("File could not be confirmed as a map"),
                message: Text(warning.message),
                dismissButton: .default(Text("Choose another file")) {
                    mapEngine.dismissCustomMapImportWarning()
                }
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
        return provider.name
    }

    private var selectedMapProvider: MapProvider? {
        guard !selectedMapProviderID.isEmpty else { return nil }
        return mapProviderOptions.first {
            MapIdentity.normalizeProvider($0.id)
                == MapIdentity.normalizeProvider(selectedMapProviderID)
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

        return "No maps are available."
    }

    private var customMapImportPanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                customMapImportExpanded.toggle()
            } label: {
                HStack(alignment: .center, spacing: 10) {
                    TerentoDisclosureIndicator(isExpanded: customMapImportExpanded)

                    VStack(alignment: .leading, spacing: 3) {
                        Text("Import a map from Mac")
                            .font(.terentoUI(size: 15, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)

                        Text("Install a third-party map (.img) from this Mac.")
                            .font(.terentoUI(size: 12, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 8)
                }
                .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 12)
            .accessibilityLabel("Import a map from Mac")
            .accessibilityValue(customMapImportExpanded ? "Expanded" : "Collapsed")
            .accessibilityHint("Shows or hides the local Garmin IMG import controls.")

            if customMapImportExpanded {
                VStack(alignment: .leading, spacing: 10) {
                    if let candidate = mapEngine.customMapImportCandidate {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundStyle(TerentoColors.lichenDark)
                                .accessibilityHidden(true)

                            VStack(alignment: .leading, spacing: 4) {
                                Text("Custom map")
                                    .font(.terentoUI(size: 14, weight: .semibold))
                                    .foregroundStyle(TerentoColors.graphite)
                                Text("\(candidate.originalFilename) · \(formatBytes(candidate.sizeBytes))")
                                    .font(.terentoUI(size: 12, weight: .medium))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                Text("Map structure checked · source is not verified.")
                                    .font(.terentoUI(size: 12, weight: .medium))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                    .fixedSize(horizontal: false, vertical: true)
                            }

                            Spacer(minLength: 8)

                            Button("Remove") {
                                mapEngine.clearCustomMapImport()
                            }
                            .buttonStyle(.borderless)
                            .font(.terentoUI(size: 13, weight: .semibold))
                            .foregroundStyle(TerentoColors.interactive)
                            .disabled(mapEngine.isBusy)
                            .accessibilityLabel("Remove staged custom map")
                            .accessibilityHint("Removes the local staged file. It does not change the Garmin watch.")
                        }
                        .padding(10)
                        .background(TerentoColors.canvas, in: RoundedRectangle(cornerRadius: 9))
                    } else {
                        customMapDropZone
                    }

                    Text("Processed locally on your Mac. Not sent to Terento servers.")
                        .font(.terentoUI(size: 11, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)

                    if let errorMessage = mapEngine.customMapImportErrorMessage,
                       mapEngine.customMapImportCandidate == nil {
                        Text(errorMessage)
                            .font(.terentoUI(size: 12, weight: .medium))
                            .foregroundStyle(TerentoColors.error)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 12)
            }
        }
        .background(TerentoColors.surface.opacity(0.62), in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
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
                    .font(.terentoUI(size: 13, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                if customMapImportIsBusy {
                    Text("Checking it before installation")
                        .font(.terentoUI(size: 11, weight: .medium))
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
            in: RoundedRectangle(cornerRadius: 9)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 9)
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
                    .font(.terentoHeading(size: 42, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Keep your Garmin connected until installation is complete.")
                    .font(.terentoBody(size: 19, weight: .medium))
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
        let supportedInstallFlow = !plan.installItems.isEmpty
        let installAvailability = InstallReviewAvailabilityResolver().resolve(
            plan: plan,
            deviceConnected: deviceEngine.hasConnectedDevice,
            supportedInstallFlow: supportedInstallFlow,
            installationPhase: mapEngine.installationPhase,
            hasValidatedArtifact: mapEngine.validatedArtifact != nil,
            operationBusy: mapEngine.isBusy
                || lifecycleViewModel.isBusy
        )

        return TerentoInstallFooterPageShell(
            bodyScrolls: mapEngine.installationPhase == .failed
        ) {
            VStack(alignment: .leading, spacing: 0) {
                Text("Ready to install")
                    .font(.terentoHeading(size: 42, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Review your selection before installing.")
                    .font(.terentoBody(size: 19, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                ReadyToInstallSelectedMapsHeader(count: plan.selectedItems.count)
                    .padding(.top, 18)

                ReadyToInstallSelectedMapsList(items: plan.selectedItems)
                    .padding(.top, 4)

                MapSelectionStorageSummary(
                    plan: plan,
                    totalCapacity: snapshot?.totalCapacity ?? 0,
                    formatBytes: formatBytes
                )
                .padding(.top, 12)

                if plan.canContinue {
                    Text("Terento will install these maps to your Garmin. Existing Garmin maps will not be changed.")
                        .font(.terentoUI(size: 13, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 10)

                    Text("Terento sends anonymous diagnostics by default to help improve the app and its services. You can turn this off anytime in Terento → Diagnostics.")
                        .font(.terentoUI(size: 13, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 10)

                    Spacer(minLength: TerentoPageLayout.sectionSpacing)
                        .padding(.bottom, TerentoPageLayout.sectionSpacing)

                } else if let reason = installAvailability.userReason {
                    Text(reason)
                        .font(.terentoUI(size: 15, weight: .semibold))
                        .foregroundStyle(TerentoColors.error)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 18)
                }

            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } footer: {
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
                .disabled(
                    !mapSupport.canAttemptTerentoMapInstall
                        || !installAvailability.isEnabled
                )
            }
        }
    }

    private func activeInstallationContent(_ plan: InstallationPlan) -> some View {
        return TerentoInstallationProgressPageShell {
            VStack(alignment: .leading, spacing: 0) {
                Text("Installing maps")
                    .font(.terentoHeading(size: 42, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Keep your Garmin connected until installation is complete.")
                    .font(.terentoBody(size: 19, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                InstallationMapsSectionHeader(count: plan.selectedItems.count)
                    .padding(.top, 18)

                InstallationMapsList(items: plan.selectedItems)
                    .padding(.top, 4)

                installationJourneyView
                    .padding(.top, 10)
            }
        }
    }

    private var installationJourneyView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Installation progress")
                .font(.terentoUI(size: 16, weight: .semibold))
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
                    ? mapEngine.installationPhaseProgress
                    : nil,
                bytes: nil,
                isLast: false
            )

            installationStepRow(
                title: "Installing",
                detail: "Writing the validated map to your Garmin watch",
                state: installationStepState(for: .installing),
                progress: mapEngine.installationProgress.flatMap {
                    $0.totalBytes > 0 ? $0.fractionCompleted : nil
                },
                bytes: mapEngine.installationProgress.map {
                    (current: $0.bytesTransferred, total: $0.totalBytes, speed: $0.bytesPerSecond)
                },
                isLast: false
            )

            installationStepRow(
                title: "Finishing",
                detail: "Checking the transferred map and completing final checks",
                state: installationStepState(for: .finishing),
                progress: mapEngine.installationPhase == .finishing
                    && mapEngine.installationPhaseProgressIsMeasured
                    ? mapEngine.installationPhaseProgress
                    : nil,
                bytes: nil,
                isLast: true
            )
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private func installationStepRow(
        title: String,
        detail: String,
        state: InstallationStepState,
        progress: Double?,
        bytes: (current: UInt64, total: UInt64, speed: Double)?,
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
                        .font(.terentoUI(size: 15, weight: .semibold))
                        .foregroundStyle(
                            state == .pending
                                ? TerentoColors.secondaryText.opacity(0.72)
                                : TerentoColors.graphite
                        )

                    Spacer()

                    if state == .active,
                       let progress {
                        Text("\(Int(progress * 100))%")
                            .font(.terentoUI(size: 13, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)
                    }
                }

                Text(state == .failed ? (mapEngine.installationErrorMessage ?? detail) : detail)
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(
                        state == .failed
                            ? TerentoColors.error
                            : TerentoColors.secondaryText.opacity(state == .pending ? 0.68 : 1)
                    )
                    .fixedSize(horizontal: false, vertical: true)

                if state == .active {
                    if let progress {
                        ProgressView(value: progress)
                            .progressViewStyle(.linear)
                            .tint(TerentoColors.interactive)
                            .frame(height: InstallationTimelineLayout.progressBarHeight)
                    } else {
                        ProgressView()
                            .progressViewStyle(.linear)
                            .tint(TerentoColors.interactive)
                            .frame(height: InstallationTimelineLayout.progressBarHeight)
                    }

                    if title == "Finishing" {
                        Text(finishingProgressDetail)
                            .font(.terentoUI(size: 11, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText.opacity(0.82))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                if let bytes,
                   bytes.total > 0,
                   state == .active || state == .complete {
                    HStack {
                        Text("\(formatBytes(bytes.current)) of \(formatBytes(bytes.total))")
                        Spacer()
                        if state == .active, bytes.speed > 0 {
                            Text("\(formatBytesPerSecond(bytes.speed))/s")
                        }
                    }
                    .font(.terentoUI(size: 11, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                }
            }
            .padding(.bottom, isLast ? 0 : 6.5)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) — \(installationStepAccessibilityLabel(for: state))")
        .accessibilityValue(installationStepAccessibilityValue(progress: progress, bytes: bytes))
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
        let current = mapEngine.installationPhase
        let customOnly = planContainsOnlyCustomMaps

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
        bytes: (current: UInt64, total: UInt64, speed: Double)?
    ) -> String {
        if let progress {
            return "\(Int(progress * 100)) percent"
        }
        if let bytes, bytes.total > 0 {
            return "\(formatBytes(bytes.current)) of \(formatBytes(bytes.total))"
        }
        return ""
    }

    private var downloadStepDetail: String {
        if planContainsOnlyCustomMaps {
            return "Custom map is already on this Mac"
        }
        if mapEngine.acquisitionState == .downloading {
            return "Downloading the map package to this Mac"
        }
        if mapEngine.acquisitionState == .validated || mapEngine.installationPhase == .awaitingConfirmation {
            return "Download complete"
        }
        return "Waiting to download the selected map"
    }

    private var finishingProgressDetail: String {
        let progress = mapEngine.installationPhaseProgress ?? 0
        switch progress {
        case ..<0.25:
            return "Checking sampled regions on your Garmin"
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

    private var installationFailureReason: String {
        let normalized = mapEngine.installationErrorMessage?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return normalized.isEmpty
            ? "Installation could not be completed safely."
            : normalized
    }

    private var installationFailureSafetyMessage: String? {
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
        let draft = InstallationIssueReport.generate(
            identity: identity,
            maps: (plan?.installItems ?? []).map { item in
                InstallationIssueMap(
                    provider: item.comparison.providerName,
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
            cleanupSucceeded: mapEngine.installationResult?.diagnostics.cleanupSucceeded ?? false
        )
        diagnosticLogMessage = InstallationIssueReport.copyAndOpenGitHub(draft)
            ? nil
            : "GitHub could not be opened. The report is still copied and ready to paste."
    }

    private var finishContent: some View {
        let installedItems = successfullyInstalledItems
        let installedCount = installedItems.count

        return TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                TerentoPageHeader(
                    title: "Maps installed",
                    subtitle: installedCount == 1
                        ? "Your selected map is ready on your Garmin."
                        : "Your selected maps are ready on your Garmin."
                )

                if mapEngine.installationPhase == .completed, !installedItems.isEmpty {
                    InstalledMapsSectionHeader(count: installedCount)
                        .padding(.top, TerentoPageLayout.firstSectionTopPadding)

                    InstallationMapsList(
                        items: installedItems,
                        accessibilityLabel: "Installed maps"
                    )
                        .padding(.top, TerentoPageLayout.sectionContentTopPadding)

                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(TerentoColors.lichen)
                            .accessibilityHidden(true)

                        Text(installedCount == 1
                            ? "Your map is ready and verified. You can safely disconnect your Garmin."
                            : "Your maps are ready and verified. You can safely disconnect your Garmin.")
                            .font(.terentoUI(size: 14, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                        .accessibilityElement(children: .combine)
                        .padding(.top, TerentoPageLayout.sectionSpacing)
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
              mapEngine.installationBatchResults.count == plan.installItems.count else {
            return []
        }

        let successfulPackageIDs = Set(
            zip(plan.installItems, mapEngine.installationBatchResults)
                .filter { $0.1.isSuccess }
                .map { $0.0.package.id }
        )
        return plan.selectedItems.filter { successfulPackageIDs.contains($0.package.id) }
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
        evidenceOperationIdentity = identity
        evidenceRecordedForCurrentWrite = false
        evidenceController.resetLatestDeliveryStatus()
        mapEngine.beginInstallation(plan: plan, operationId: operationID)
    }

    private func recordInstallationEvidenceIfNeeded() {
        guard !evidenceRecordedForCurrentWrite,
              let identity = evidenceOperationIdentity,
              let plan = selectedInstallationPlan,
              mapEngine.installationPhase == .completed || mapEngine.installationPhase == .failed else {
            return
        }

        let succeeded = mapEngine.installationPhase == .completed
            && mapEngine.installationResult?.isSuccess == true
        let category: EvidenceErrorCategory? = succeeded ? nil : {
            switch mapEngine.installationResult?.failure {
            case .insufficientSpace: return .storage
            case .deviceDisconnected: return .deviceDisconnected
            case .sourceArtifactInvalid: return .sourceValidation
            case .stableWatchIdentityUnavailable: return .unknown
            case .hashMismatch, .sizeMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired: return .verification
            case .some: return .transport
            case .none: return .unknown
            }
        }()
        let results = mapEngine.installationBatchResults
        let primaryFailureIndex = mapEngine.evidencePrimaryFailureMapIndex ?? 0
        var events: [InstallationEvidenceEvent] = []
        for (index, item) in plan.installItems.enumerated() {
            let result = results.indices.contains(index)
                ? results[index]
                : (results.isEmpty && index == primaryFailureIndex ? mapEngine.installationResult : nil)
            let itemSucceeded = result?.isSuccess == true || (plan.installItems.count == 1 && succeeded)
            let isPrimaryFailure = !itemSucceeded && (
                result != nil || (results.isEmpty && index == primaryFailureIndex)
            )
            let outcome: InstallationEvidenceOutcome = itemSucceeded
                ? .succeeded
                : (isPrimaryFailure ? .failed : .notStarted)
            let failure = result?.failure ?? (isPrimaryFailure ? mapEngine.evidenceFailure : nil)
            let stage = result.map { evidenceStage(for: $0) }
                ?? (isPrimaryFailure ? mapEngine.evidenceFailureStage ?? .preflight : .preflight)
            let writeStarted = result?.diagnostics.writeStarted ?? false
            let remoteCreated = result?.diagnostics.remoteObjectCreated ?? false
            let cleanupAttempted = result?.diagnostics.cleanupAttempted ?? false
            events.append(InstallationEvidenceEvent(
                identity: identity,
                package: item.package,
                outcome: outcome,
                finishingResult: itemSucceeded ? .verified : (outcome == .notStarted ? .notReached : .failed),
                errorCategory: itemSucceeded ? nil : category,
                operationId: evidenceOperationID,
                mapResultIndex: index,
                selectedMapCount: plan.installItems.count,
                failureStage: itemSucceeded ? nil : stage,
                failureCode: itemSucceeded ? nil : (failure?.rawValue ?? "INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE"),
                nativeFailureCode: itemSucceeded ? nil : (
                    result?.diagnostics.nativeFailureCode.flatMap {
                        EvidenceNativeFailureCode(rawValue: $0.rawValue)
                    } ?? (result == nil ? mapEngine.evidenceNativeFailureCode : nil)
                        ?? evidenceNativeCode(for: failure)
                ),
                writeStarted: writeStarted,
                remoteObjectCreated: remoteCreated,
                cleanupAttempted: cleanupAttempted,
                cleanupSucceeded: result?.diagnostics.cleanupSucceeded ?? false,
                transferProgressBucket: EvidenceTransferProgressBucket(
                    bytes: result?.diagnostics.bytesTransferred ?? 0,
                    total: result?.diagnostics.transferTotalBytes ?? 0
                )
            ))
        }
        evidenceRecordedForCurrentWrite = true

        Task { @MainActor in
            _ = await evidenceController.recordAndUpload(events)
        }
    }

    private func evidenceStage(for result: MapInstallationResult) -> EvidenceFailureStage {
        switch result.failure {
        case .manifestFailed: return .manifest
        case .cleanupFailed: return .cleanup
        case .sizeMismatch, .hashMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired:
            return .verify
        case .writeFailed, .deviceDisconnected: return .write
        case .sourceArtifactInvalid, .sourceValidationFailed: return .sourceValidation
        default: return .preflight
        }
    }

    private func evidenceNativeCode(for failure: InstallationFailure?) -> EvidenceNativeFailureCode? {
        switch failure {
        case .existingMapConflict: return .targetAlreadyExists
        case .remoteFileMissing: return .remoteFileMissing
        case .unknownInstallTarget: return .unsupportedDevice
        case .stableWatchIdentityUnavailable: return .stableWatchIdentityUnavailable
        case .deviceDisconnected: return .deviceDisconnected
        case .writeFailed: return .sendObjectFailed
        default: return nil
        }
    }

}

struct TerentoSidebar: View {
    @Binding var selectedSection: TerentoSection
    let connectionState: DeviceConnectionState
    let canEject: Bool
    let isInstalling: Bool
    let navigationLocked: Bool
    let mapNavigationEnabled: Bool
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
                            systemImage: systemImage(for: section),
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

            Button {
                onNavigate(.about)
            } label: {
                SidebarSectionRow(
                    title: "About",
                    systemImage: "info.circle",
                    isSelected: selectedSection == .about
                )
            }
            .buttonStyle(.plain)
            .disabled(navigationLocked)
            .accessibilityLabel(TerentoSection.about.rawValue)
            .accessibilityAddTraits(
                selectedSection == .about ? .isSelected : []
            )

            SidebarConnectionStatus(
                state: connectionState,
                canEject: canEject,
                isInstalling: isInstalling,
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

    private func systemImage(for section: TerentoSection) -> String {
        switch section {
        case .device:
            return "applewatch"
        case .installMaps:
            return "arrow.down.circle"
        case .manageMaps:
            return "square.stack.3d.up"
        case .about:
            return "info.circle"
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
                .font(.terentoHeading(size: 22, weight: .semibold))
                .tracking(-0.66)
                .foregroundStyle(TerentoColors.graphite)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Terento")
    }
}

private struct AppUpdatePromptView: View {
    let update: TerentoAppUpdateManifest
    let onDownload: () -> Void
    let onLater: () -> Void
    let onReleaseNotes: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 7) {
                Text("Terento \(update.releaseLabel) is available")
                    .font(.title3.weight(.semibold))

                Text(
                    update.summary?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
                        ? update.summary!
                        : "A newer version of Terento is ready."
                )
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                if update.releaseNotesURL != nil {
                    Button("What’s new ↗", action: onReleaseNotes)
                        .buttonStyle(.plain)
                        .foregroundStyle(TerentoColors.interactive)
                }

                Spacer()

                Button("Later", action: onLater)
                    .keyboardShortcut(.cancelAction)
                Button("Download", action: onDownload)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(width: 420)
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
            iconColor: TerentoColors.warning,
            title: "Import this map?",
            subtitle: safeFilename,
            message: "Terento can verify that this is a Garmin map file, but cannot verify who created it or whether you trust its source.",
            supportingMessage: "Imported map files are transferred directly from your Mac to your watch. They are not sent to Terento servers.",
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

    @ViewBuilder
    var body: some View {
        if isDestructive {
            TerentoConfirmationDialog(
                icon: "trash",
                iconColor: TerentoColors.error,
                title: title,
                subtitle: subtitle,
                message: "This map will be removed from your Garmin.",
                supportingMessage: "Other maps will not be changed. No backup will be created.",
                primaryLabel: actionTitle,
                isDestructive: true,
                onCancel: onCancel,
                onConfirm: onConfirm
            )
        } else {
            unchangedUpdateDialog
        }
    }

    private var unchangedUpdateDialog: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundStyle(TerentoColors.interactive)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 5) {
                    Text(title)
                        .font(.terentoHeading(size: 20, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Text(subtitle)
                        .font(.terentoUI(size: 13, weight: .semibold))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .lineLimit(2)
                }
            }

            Text(message)
                .font(.terentoUI(size: 14, weight: .regular))
                .foregroundStyle(TerentoColors.graphite)
                .fixedSize(horizontal: false, vertical: true)

            Text("Terento will keep the current map until the new one is verified.")
                .font(.terentoUI(size: 12, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 10) {
                Spacer(minLength: 0)

                Button("Cancel", action: onCancel)
                    .buttonStyle(.plain)
                    .font(.terentoUI(size: 14, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .padding(.horizontal, 16)
                    .frame(minHeight: 38)
                    .background(TerentoColors.canvas, in: RoundedRectangle(cornerRadius: 8))
                    .overlay {
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(TerentoColors.border, lineWidth: 1)
                    }
                    .keyboardShortcut(.cancelAction)

                Button(actionTitle, action: onConfirm)
                    .buttonStyle(.plain)
                    .font(.terentoUI(size: 14, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .frame(minHeight: 38)
                    .background(
                        TerentoColors.interactive,
                        in: RoundedRectangle(cornerRadius: 8)
                    )
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(width: 430)
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
    }
}

private struct InstallationFailureDialog: View {
    let mapTitle: String?
    let reason: String
    let safetyMessage: String?
    let reportError: String?
    let onReportIssue: () -> Void
    let onBackToDevice: () -> Void

    private var supportingMessage: String? {
        [safetyMessage, reportError]
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
            iconColor: TerentoColors.error,
            title: "Installation stopped",
            subtitle: mapTitle ?? "",
            message: "The map could not be installed.",
            detailMessage: reason,
            supportingMessage: supportingMessage,
            secondaryLabel: "Report issue",
            secondaryAssetIcon: "GitHubMark",
            secondaryUsesCancelShortcut: false,
            primaryLabel: "Back to device",
            isDestructive: false,
            onCancel: onReportIssue,
            onConfirm: onBackToDevice
        )
        .accessibilityElement(children: .contain)
    }
}

private struct TerentoConfirmationDialog: View {
    private static let cornerRadius: CGFloat = 27
    private static let outerPadding: CGFloat = 28
    private static let iconFrame: CGFloat = 40
    private static let iconSize: CGFloat = 29
    private static let iconTextGap: CGFloat = 14
    private static let buttonHeight: CGFloat = 38
    private static let buttonRadius: CGFloat = 8
    private static let buttonGap: CGFloat = 10

    let icon: String
    let iconColor: Color
    let title: String
    let subtitle: String
    let message: String
    let detailMessage: String?
    let supportingMessage: String?
    let secondaryLabel: String
    let secondaryAssetIcon: String?
    let secondaryUsesCancelShortcut: Bool
    let primaryLabel: String
    let isDestructive: Bool
    let onCancel: () -> Void
    let onConfirm: () -> Void

    init(
        icon: String,
        iconColor: Color,
        title: String,
        subtitle: String,
        message: String,
        detailMessage: String? = nil,
        supportingMessage: String? = nil,
        secondaryLabel: String = "Cancel",
        secondaryAssetIcon: String? = nil,
        secondaryUsesCancelShortcut: Bool = true,
        primaryLabel: String,
        isDestructive: Bool,
        onCancel: @escaping () -> Void,
        onConfirm: @escaping () -> Void
    ) {
        self.icon = icon
        self.iconColor = iconColor
        self.title = title
        self.subtitle = subtitle
        self.message = message
        self.detailMessage = detailMessage
        self.supportingMessage = supportingMessage
        self.secondaryLabel = secondaryLabel
        self.secondaryAssetIcon = secondaryAssetIcon
        self.secondaryUsesCancelShortcut = secondaryUsesCancelShortcut
        self.primaryLabel = primaryLabel
        self.isDestructive = isDestructive
        self.onCancel = onCancel
        self.onConfirm = onConfirm
    }

    var body: some View {
        HStack(alignment: .top, spacing: Self.iconTextGap) {
            Image(systemName: icon)
                .font(.system(size: Self.iconSize, weight: .medium))
                .foregroundStyle(iconColor)
                .frame(width: Self.iconFrame, height: Self.iconFrame, alignment: .top)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 0) {
                Text(title)
                    .font(.terentoHeading(size: 27, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .accessibilityAddTraits(.isHeader)

                if !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.terentoUI(size: 13, weight: .semibold))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .lineLimit(2)
                        .truncationMode(.middle)
                        .padding(.top, 5)
                }

                Text(message)
                    .font(.terentoUI(size: 14, weight: .regular))
                    .foregroundStyle(TerentoColors.graphite)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 22)

                if let detailMessage, !detailMessage.isEmpty {
                    Text(detailMessage)
                        .font(.terentoUI(size: 14, weight: .semibold))
                        .foregroundStyle(TerentoColors.error)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 14)
                }

                if let supportingMessage, !supportingMessage.isEmpty {
                    Text(supportingMessage)
                        .font(.terentoUI(size: 12, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 16)
                }

                HStack(spacing: Self.buttonGap) {
                    Spacer(minLength: 0)

                    if secondaryUsesCancelShortcut {
                        dialogButton(
                            secondaryLabel,
                            assetIcon: secondaryAssetIcon,
                            color: TerentoColors.graphite,
                            background: TerentoColors.canvas,
                            border: TerentoColors.border,
                            role: nil,
                            action: onCancel
                        )
                        .keyboardShortcut(.cancelAction)
                    } else {
                        dialogButton(
                            secondaryLabel,
                            assetIcon: secondaryAssetIcon,
                            color: TerentoColors.graphite,
                            background: TerentoColors.canvas,
                            border: TerentoColors.border,
                            role: nil,
                            action: onCancel
                        )
                    }

                    dialogButton(
                        primaryLabel,
                        assetIcon: nil,
                        color: .white,
                        background: isDestructive ? TerentoColors.error : TerentoColors.interactive,
                        border: nil,
                        role: isDestructive ? .destructive : nil,
                        action: onConfirm
                    )
                    .keyboardShortcut(.defaultAction)
                }
                .padding(.top, 24)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(Self.outerPadding)
        .frame(width: 500)
        .background(
            TerentoColors.canvas,
            in: RoundedRectangle(cornerRadius: Self.cornerRadius, style: .continuous)
        )
        .clipShape(RoundedRectangle(cornerRadius: Self.cornerRadius, style: .continuous))
        .preferredColorScheme(.light)
    }

    private func dialogButton(
        _ label: String,
        assetIcon: String?,
        color: Color,
        background: Color,
        border: Color?,
        role: ButtonRole?,
        action: @escaping () -> Void
    ) -> some View {
        Button(role: role, action: action) {
            HStack(spacing: 7) {
                if let assetIcon {
                    Image(assetIcon)
                        .renderingMode(.template)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 15, height: 15)
                        .accessibilityHidden(true)
                }

                Text(label)
                    .font(.terentoUI(size: 14, weight: .semibold))
            }
            .foregroundStyle(color)
            .padding(.horizontal, 16)
            .frame(minHeight: Self.buttonHeight)
            .background(
                background,
                in: RoundedRectangle(cornerRadius: Self.buttonRadius, style: .continuous)
            )
            .overlay {
                if let border {
                    RoundedRectangle(cornerRadius: Self.buttonRadius, style: .continuous)
                        .stroke(border, lineWidth: 1)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

private struct SidebarConnectionStatus: View {
    let state: DeviceConnectionState
    let canEject: Bool
    let isInstalling: Bool
    let onEject: () -> Void

    private var label: String {
        isInstalling ? "Installing…" : ConnectionStatusPresentation.label(for: state)
    }

    private var statusColor: Color {
        isInstalling ? TerentoColors.interactive : ConnectionStatusPresentation.color(for: state)
    }

    private var ejectPresentation: SafeEjectPresentation {
        SafeEjectPresentation.resolve(state: state, canEject: canEject)
    }

    var body: some View {
        HStack(spacing: 8) {
            HStack(spacing: 8) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)
                    .accessibilityHidden(true)

                Text(label)
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(
                isInstalling
                    ? "Map installation status: Installing"
                    : "Connection status: \(label)"
            )

            Spacer(minLength: 8)

            if ejectPresentation != .hidden {
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

private enum ConnectionStatusPresentation {
    static func label(for state: DeviceConnectionState) -> String {
        switch state {
        case .disconnected:
            return "Disconnected"
        case .detecting:
            return "Waiting…"
        case .connected, .ready:
            return "Connected"
        case .ejecting:
            return "Disconnecting…"
        case .safeToDisconnect:
            return "Safe to disconnect"
        case .failed:
            return "Garmin not found"
        }
    }

    static func color(for state: DeviceConnectionState) -> Color {
        switch state {
        case .connected, .ready:
            return TerentoColors.lichen
        case .detecting, .ejecting:
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
    let systemImage: String
    let isSelected: Bool

    var body: some View {
        HStack(spacing: 13) {
            Image(systemName: systemImage)
                .font(.system(size: 17, weight: .regular))
                .foregroundStyle(isSelected ? TerentoColors.lichenDark : TerentoColors.secondaryText)
                .frame(width: 24)
                .accessibilityHidden(true)

            Text(title)
                .font(.terentoUI(size: 15, weight: isSelected ? .medium : .regular))
                .foregroundStyle(isSelected ? TerentoColors.lichenDark : TerentoColors.secondaryText)

            Spacer()
        }
        .padding(.horizontal, 14)
        .frame(height: 50)
        .background(
            isSelected ? TerentoColors.selectedBackground : .clear,
            in: RoundedRectangle(cornerRadius: 10)
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

/// The Install Maps body has three explicit vertical regions:
/// header/content, the bounded map-selection viewport, and Storage. The
/// shared footer is outside this layout and therefore cannot be consumed by
/// the map list.
private struct TerentoInstallMapsVerticalLayout<Header: View, MapRegion: View, StorageRegion: View>: View {
    private let header: () -> Header
    private let mapRegion: () -> MapRegion
    private let storageRegion: () -> StorageRegion

    init(
        @ViewBuilder header: @escaping () -> Header,
        @ViewBuilder mapRegion: @escaping () -> MapRegion,
        @ViewBuilder storageRegion: @escaping () -> StorageRegion
    ) {
        self.header = header
        self.mapRegion = mapRegion
        self.storageRegion = storageRegion
    }

    var body: some View {
        TerentoInstallMapsVerticalRegionLayout {
            header()
            mapRegion()
            storageRegion()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

private struct TerentoInstallMapsVerticalRegionLayout: Layout {
    private static let listStorageSpacing = TerentoPageLayout.sectionSpacing
    private static let storageFooterSpacing = TerentoPageLayout.sectionSpacing
    private static let minimumListHeight: CGFloat = 90

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        guard subviews.count == 3 else {
            return CGSize(
                width: proposal.width ?? 0,
                height: proposal.height ?? 0
            )
        }

        let width = proposal.width ?? intrinsicWidth(for: subviews)
        let headerHeight = subviews[0]
            .sizeThatFits(ProposedViewSize(width: width, height: nil))
            .height
        let storageHeight = subviews[2]
            .sizeThatFits(ProposedViewSize(width: width, height: nil))
            .height
        let minimumHeight = headerHeight
            + Self.listStorageSpacing
            + Self.minimumListHeight
            + Self.storageFooterSpacing
            + storageHeight

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
        guard subviews.count == 3 else { return }

        let headerHeight = subviews[0]
            .sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
            .height
        let storageHeight = subviews[2]
            .sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
            .height
        let listHeight = max(
            0,
            bounds.height
                - headerHeight
                - Self.listStorageSpacing
                - Self.storageFooterSpacing
                - storageHeight
        )

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
        subviews[2].place(
            at: CGPoint(
                x: bounds.minX,
                y: bounds.maxY - Self.storageFooterSpacing - storageHeight
            ),
            anchor: .topLeading,
            proposal: ProposedViewSize(width: bounds.width, height: storageHeight)
        )
    }

    private func intrinsicWidth(for subviews: Subviews) -> CGFloat {
        subviews.reduce(CGFloat.zero) { width, subview in
            max(width, subview.sizeThatFits(.unspecified).width)
        }
    }
}

/// A scroll view whose height is supplied by TerentoInstallMapsVerticalLayout.
/// It owns only the map rows; Storage and the shared footer are siblings.
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
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text(subtitle)
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
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
        height: CGFloat = 50,
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
            .font(.terentoUI(size: 15, weight: .semibold))
            .foregroundStyle(isEnabled ? .white : TerentoColors.secondaryText)
            .padding(.horizontal, 24)
            .frame(width: width, height: height)
            .background(
                isEnabled ? TerentoColors.interactive : TerentoColors.border,
                in: RoundedRectangle(cornerRadius: 9)
            )
        }
        .buttonStyle(.plain)
        .keyboardShortcut(.defaultAction)
        .opacity(isEnabled ? 1 : 0.78)
    }
}

struct ConnectionStatusRow: View {
    let title: String
    let description: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 20) {
            ZStack {
                Circle()
                    .fill(TerentoColors.lichen.opacity(0.22))

                Image(systemName: systemImage)
                    .font(.system(size: 27, weight: .medium))
                    .foregroundStyle(TerentoColors.lichenDark)
            }
            .frame(width: 70, height: 70)

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.terentoUI(size: 17, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text(description)
                    .font(.terentoUI(size: 15, weight: .regular))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
        }
    }
}

struct DeviceCard: View {
    let presentation: DevicePresentation
    let canEject: Bool
    let onEject: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 20) {
            DeviceAssetImage(asset: presentation.asset)
                .frame(width: 178, height: 214)
                .accessibilityLabel("Garmin device image")

            VStack(alignment: .leading, spacing: 0) {
                Text(presentation.deviceName)
                    .font(.terentoHeading(size: 28, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text(presentation.variant)
                    .font(.terentoUI(size: 16, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .padding(.top, 6)

                if presentation.mapSupport.showsTerentoCompatibility,
                   let compatibility = presentation.compatibility {
                    CompatibilityStatusView(status: compatibility)
                        .padding(.top, 12)
                }

                MapSupportView(status: presentation.mapSupport)
                    .padding(.top, 9)

                Button(action: onEject) {
                    Label("Eject device", systemImage: "eject")
                        .font(.terentoUI(size: 13, weight: .medium))
                        .foregroundStyle(canEject ? TerentoColors.interactive : TerentoColors.secondaryText)
                        .padding(.horizontal, 10)
                        .frame(minHeight: 36)
                        .background(
                            canEject
                                ? TerentoColors.canvas
                                : TerentoColors.border.opacity(0.55),
                            in: RoundedRectangle(cornerRadius: 7)
                        )
                        .overlay {
                            RoundedRectangle(cornerRadius: 7)
                                .stroke(
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

private struct MapSupportView: View {
    let status: GarminMapSupportStatus

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 2) {
                Text(status.userLabel)
                    .font(.terentoUI(size: 13, weight: .medium))

                if !status.canUseTerentoMaps {
                    Text(status.userMessage)
                        .font(.terentoUI(size: 12, weight: .regular))
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
                .accessibilityLabel(asset.isFallback ? "Generic Garmin watch" : "Garmin device")
        } else {
            ZStack {
                Circle()
                    .fill(TerentoColors.lichen.opacity(0.18))

                Image(systemName: "applewatch")
                    .font(.system(size: 80, weight: .light))
                    .foregroundStyle(TerentoColors.lichenDark)
            }
            .padding(28)
            .accessibilityLabel("Generic Garmin watch placeholder")
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

private struct CompatibilityStatusView: View {
    let status: CompatibilityStatus

    var body: some View {
        Text(status.userLabel)
            .font(.terentoUI(size: 12, weight: .semibold))
            .foregroundStyle(statusColor)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(statusColor.opacity(0.16), in: Capsule())
            .overlay(Capsule().stroke(statusColor.opacity(0.38), lineWidth: 1))
            .help(compatibilityExplanation)
            .accessibilityLabel("\(status.userLabel) compatibility status")
            .accessibilityValue(compatibilityExplanation)
    }

    private var compatibilityExplanation: String {
        CompatibilityPresentation.explanation(for: status)
    }

    private var statusColor: Color {
        switch status {
        case .tested:
            return TerentoColors.warmStone
        case .supported:
            return TerentoColors.interactive
        case .verified:
            return TerentoColors.lichenDark
        case .testing:
            return TerentoColors.secondaryText
        }
    }
}

private struct ManageMapRow: View {
    let item: MapLifecycleItem
    let availability: MapLifecycleActionAvailability
    let operation: MapLifecycleOperationState?
    let isLifecycleBusy: Bool
    let onRemove: () -> Void
    let onUpdate: () -> Void

    private var operationIsActive: Bool {
        guard let operation else { return false }
        switch operation.phase {
        case .backingUp, .removing, .updating, .verifying:
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
            detail: manageDetail,
            contentSpacing: 9,
            rowVerticalPadding: 10
        ) {
            Image(systemName: "map")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(TerentoColors.lichenDark)
                .frame(width: 24, height: 24)
        } trailing: {
            if let operation, operationIsActive {
                ManageOperationProgress(operation: operation)
            } else if !availableActions.isEmpty {
                ManageActionGroup(
                    mapTitle: item.title,
                    primaryActions: primaryActions,
                    isEnabled: !isLifecycleBusy,
                    onAction: perform
                )
            }
        }
    }

    private var manageDetail: String {
        if let operation {
            switch operation.phase {
            case .completed:
                return "Action complete"
            case .failed:
                return operation.message
            case .idle, .awaitingConfirmation, .backingUp, .removing, .updating, .verifying:
                break
            }
        }

        return item.manageMetadataLabel
    }

    private func perform(_ action: MapLifecycleAction) {
        switch action {
        case .remove:
            onRemove()
        case .update:
            onUpdate()
        case .backup, .transferOwnership, .recoverOwnership:
            break
        }
    }
}

private struct ManageActionGroup: View {
    let mapTitle: String
    let primaryActions: [MapLifecycleAction]
    let isEnabled: Bool
    let onAction: (MapLifecycleAction) -> Void

    var body: some View {
        HStack(spacing: 9) {
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
        case .backup, .transferOwnership, .recoverOwnership:
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
                .font(.terentoUI(size: 12, weight: .semibold))
                .foregroundStyle(foregroundColor)
                .lineLimit(1)
                .padding(.horizontal, 8)
                .frame(minWidth: action == .update ? 72 : 68, minHeight: 30)
                .background(
                    backgroundColor,
                    in: RoundedRectangle(cornerRadius: 5, style: .continuous)
                )
                .overlay {
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                        .stroke(focusColor, lineWidth: isFocused ? 2 : 1)
                }
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .focused($isFocused)
        .disabled(!isEnabled)
        .contentShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
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
        guard isInteractive else {
            return TerentoColors.secondaryText
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
              progress.totalBytes > 0 else {
            return nil
        }
        return progress
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(operation.phase.userLabel)
                    .font(.terentoUI(size: 15, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Spacer()

                if let progress {
                    Text("\(Int(progress.fractionCompleted * 100))%")
                        .font(.terentoUI(size: 13, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                } else if isRemoval {
                    Text("0%")
                        .font(.terentoUI(size: 13, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                }
            }

            if let progress {
                ProgressView(value: progress.fractionCompleted)
                    .progressViewStyle(.linear)
                    .tint(TerentoColors.interactive)
                    .frame(height: InstallationTimelineLayout.progressBarHeight)

                if isRemoval {
                    Text("Verifying map removal")
                        .font(.terentoUI(size: 10, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .lineLimit(1)
                } else {
                    HStack(spacing: 8) {
                        Text("\(formatBytes(progress.bytesCompleted)) of \(formatBytes(progress.totalBytes))")
                        if progress.bytesPerSecond > 0 {
                            Text("\(formatBytesPerSecond(progress.bytesPerSecond))/s")
                        }
                    }
                    .font(.terentoUI(size: 10, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                }
            } else if isRemoval {
                ProgressView(value: 0)
                    .progressViewStyle(.linear)
                    .tint(TerentoColors.interactive)
                    .frame(height: InstallationTimelineLayout.progressBarHeight)

                Text("Verifying map removal")
                    .font(.terentoUI(size: 10, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .lineLimit(1)
            } else {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(TerentoColors.interactive)
                    .frame(height: InstallationTimelineLayout.progressBarHeight)
            }
        }
        .frame(width: InstallationTimelineLayout.manageProgressWidth, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(operation.message)
        .accessibilityValue(accessibilityValue)
    }

    private var accessibilityValue: String {
        guard let progress else {
            return isRemoval ? "0 percent" : "In progress"
        }
        if isRemoval {
            return "\(Int(progress.fractionCompleted * 100)) percent"
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

private struct TerentoMapRow<LeadingContent: View, TrailingContent: View>: View {
    let title: String
    let detail: String?
    let note: String?
    let contentSpacing: CGFloat
    let rowVerticalPadding: CGFloat
    let showsDivider: Bool
    let leadingContent: LeadingContent
    let trailingContent: TrailingContent

    init(
        title: String,
        detail: String?,
        note: String? = nil,
        contentSpacing: CGFloat = 14,
        rowVerticalPadding: CGFloat = 13,
        showsDivider: Bool = true,
        @ViewBuilder leading: () -> LeadingContent,
        @ViewBuilder trailing: () -> TrailingContent
    ) {
        self.title = title
        self.detail = detail
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

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.terentoUI(size: 16, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

                if let note, !note.isEmpty {
                    Text(note)
                        .font(.terentoUI(size: 13, weight: .medium))
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

struct CompatibilityBadge: View {
    let title: String

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(TerentoColors.lichenDark)
                .frame(width: 8, height: 8)

            Text(title)
                .font(.terentoUI(size: 14, weight: .semibold))
                .foregroundStyle(TerentoColors.lichenDark)
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 9)
        .background(TerentoColors.lichen.opacity(0.22), in: Capsule())
    }
}

struct StorageCard: View {
    let total: String
    let available: String
    let fillRatio: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Storage")
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("\(available) available of \(total)")
                .font(.terentoUI(size: 15, weight: .medium))
                .foregroundStyle(TerentoColors.graphite)

            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(TerentoColors.border)

                    Capsule()
                        .fill(TerentoColors.lichen)
                        .frame(width: proxy.size.width * normalizedFillRatio)
                }
            }
            .frame(height: 7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage: \(available) available of \(total)")
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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "map")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(TerentoColors.lichenDark)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 5) {
                    Text(title)
                        .font(.terentoUI(size: 16, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Text(detail)
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

                Spacer(minLength: 8)

                Text(status)
                    .font(.terentoUI(size: 12, weight: .semibold))
                    .foregroundStyle(TerentoColors.lichenDark)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(TerentoColors.lichen.opacity(0.22), in: Capsule())
            }

            if let note, !note.isEmpty {
                Text(note)
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(22)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
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
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text(countLabel)
                .font(.terentoUI(size: 12, weight: .semibold))
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
            Text("Installing maps")
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text(countLabel)
                .font(.terentoUI(size: 12, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Installing maps, \(countLabel)")
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
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text(countLabel)
                .font(.terentoUI(size: 12, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(count == 1 ? "Installed map" : "Installed maps"), \(countLabel)")
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
    let items: [MapSelectionItem]

    private static let visibleRowCapacity = 3
    private static let rowHeight: CGFloat = 62
    private static let contentTopPadding: CGFloat = 2
    private static let maximumListHeight = CGFloat(visibleRowCapacity) * rowHeight
        + contentTopPadding

    var body: some View {
        ScrollView {
            rows
        }
        .scrollIndicators(
            items.count > Self.visibleRowCapacity ? .automatic : .hidden
        )
        .frame(
            maxWidth: .infinity,
            minHeight: 0,
            idealHeight: Self.maximumListHeight,
            maxHeight: Self.maximumListHeight,
            alignment: .topLeading
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Selected maps list")
    }

    private var rows: some View {
        VStack(spacing: 0) {
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
}

struct MapSelectionRow: View {
    let item: MapSelectionItem
    @Binding var isSelected: Bool
    let isAvailable: Bool
    let selectionEnabled: Bool
    let showsSelectionControl: Bool
    let showsSize: Bool
    let showsDivider: Bool

    init(
        item: MapSelectionItem,
        isSelected: Binding<Bool>,
        isAvailable: Bool,
        selectionEnabled: Bool = true,
        showsSelectionControl: Bool = true,
        showsSize: Bool? = nil,
        showsDivider: Bool = true
    ) {
        self.item = item
        self._isSelected = isSelected
        self.isAvailable = isAvailable
        self.selectionEnabled = selectionEnabled
        self.showsSelectionControl = showsSelectionControl
        self.showsSize = showsSize ?? (isAvailable && item.comparison.installedMap == nil)
        self.showsDivider = showsDivider
    }

    var body: some View {
        TerentoMapRow(
            title: item.title,
            detail: detail,
            note: item.acquisitionAvailability.detailedExplanation,
            contentSpacing: 9,
            rowVerticalPadding: 10,
            showsDivider: showsDivider
        ) {
            HStack(spacing: 6) {
                if isAvailable && item.isSelectable && selectionEnabled && showsSelectionControl {
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
                } else if showsSelectionControl
                    && item.acquisitionAvailability == .available
                    && !isAlreadyInstalledSearchResult {
                    Image(systemName: statusIcon)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(statusColor)
                        .frame(width: 18)
                }

                Image(systemName: "map")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(TerentoColors.lichenDark)
                    .frame(width: 24)
            }
        } trailing: {
            if showsSize && item.acquisitionAvailability == .available {
                Text(item.installSizeBytes.map(formatBytes) ?? "Size calculated before installation")
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .multilineTextAlignment(.trailing)
                    .frame(maxWidth: 190, alignment: .trailing)
            } else if item.acquisitionAvailability != .available {
                Text("Unavailable")
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture {
            guard isAvailable, item.isSelectable, selectionEnabled else { return }
            isSelected.toggle()
        }
        .opacity(crossProviderSelectionDisabled ? 0.62 : 1)
        .help(crossProviderSelectionDisabled ? "Choose maps from one provider at a time." : "")
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityValue(isAvailable && item.isSelectable && selectionEnabled && showsSelectionControl
            ? (isSelected ? "Selected" : "Not selected")
            : detail)
        .accessibilityHint(
            crossProviderSelectionDisabled
                ? "Unavailable for this installation because maps from another provider are already selected."
                : ""
        )
    }

    private var detail: String {
        let baseDetail: String

        if let status = item.acquisitionAvailability.shortStatus {
            baseDetail = status
        } else if item.package.sourceKind == .custom {
            return "From this Mac"
        } else if isAlreadyInstalledSearchResult {
            baseDetail = "Already installed"
        } else {
            switch item.comparison.status {
            case .notInstalled:
                if let preflightStatus = item.preflightStatus {
                    switch preflightStatus {
                    case .blockedUnsupportedDevice:
                        baseDetail = "This watch has no validated Terento install profile yet"
                    case .blockedUnknownTarget:
                        baseDetail = "Install target is not validated for this watch"
                    case .blockedAmbiguousMapIdentity:
                        baseDetail = "Map identity needs to be checked before installation"
                    case .blockedInsufficientSpace:
                        baseDetail = "Not enough space for a safe installation"
                    case .blockedUnknownInstallSize:
                        baseDetail = "Size calculated before installation"
                    case .error:
                        baseDetail = "Could not prepare this map for installation"
                    case .readyNewInstall, .readyWithExistingMapConflict:
                        baseDetail = item.installSizeBytes == nil
                            ? "Size calculated before installation"
                            : ""
                    }
                } else {
                    baseDetail = item.installSizeBytes == nil
                        ? "Size calculated before installation"
                        : ""
                }
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

    private var statusIcon: String {
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
            return item.acquisitionAccessibilityLabel ?? "\(item.title), unavailable"
        }

        if isAlreadyInstalledSearchResult {
            return "\(item.title), Already installed"
        }

        if showsSize {
            return item.installSizeBytes.map {
                "\(item.title), \(formatBytes($0))"
            } ?? "\(item.title), size calculated before installation"
        }
        return "\(item.title), \(detail)"
    }

    private var isAlreadyInstalledSearchResult: Bool {
        isAvailable && item.comparison.installedMap != nil
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

    private func formatBytes(_ bytes: UInt64) -> String {
        ByteCountFormatter.string(
            fromByteCount: Int64(min(bytes, UInt64(Int64.max))),
            countStyle: .decimal
        )
    }
}

struct OtherMapSelectionRow: View {
    let entry: MapInventoryEntry

    var body: some View {
        TerentoMapRow(title: entry.title, detail: entry.installedRawVersion.map { "Installed · \($0)" } ?? "Installed") {
            Image(systemName: "map")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
                .frame(width: 24)
        } trailing: {
            Text("Other")
                .font(.terentoUI(size: 12, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(TerentoColors.border.opacity(0.45), in: Capsule())
        }
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
                    .font(.terentoUI(size: 17, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text(countLabel)
                    .font(.terentoUI(size: 12, weight: .semibold))
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
                    .font(.terentoUI(size: 16, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Spacer(minLength: 12)

                Text("\(formatBytes(plan.storagePlan.currentFreeSpace)) available of \(formatBytes(totalCapacity))")
                    .font(.terentoUI(size: 14, weight: .medium))
                    .foregroundStyle(TerentoColors.graphite)
                    .multilineTextAlignment(.trailing)
            }

            GeometryReader { proxy in
                let projection = StorageBarProjection(
                    plan: plan.storagePlan,
                    totalCapacity: totalCapacity
                )
                let existingWidth = proxy.size.width * projection.fraction(
                    for: projection.existingUsedBytes
                )
                let selectedWidth = proxy.size.width * projection.fraction(
                    for: projection.selectedMapBytes
                )

                HStack(spacing: 0) {
                    Rectangle()
                        .fill(TerentoColors.lichen)
                        .frame(width: existingWidth)

                    Rectangle()
                        .fill(TerentoColors.sky)
                        .frame(width: selectedWidth)

                    Rectangle()
                        .fill(TerentoColors.border)
                        .frame(maxWidth: .infinity)
                }
                .clipShape(Capsule())
            }
            .frame(height: 8)
            .accessibilityHidden(true)

            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(selectedMapSummary)
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)

                Spacer(minLength: 12)

                Text(afterInstallationSummary)
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .multilineTextAlignment(.trailing)
            }

            if !statusText.isEmpty {
                Text(statusText)
                    .font(.terentoUI(size: 13, weight: .semibold))
                    .foregroundStyle(statusColor)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage")
        .accessibilityValue(storageAccessibilityValue)
    }

    private var statusText: String {
        if plan.selectedItems.isEmpty {
            return ""
        }
        if plan.storagePlan.hasUnresolvedInstallSize {
            return "Map size will be checked before installation."
        }
        if plan.storagePlan.isAllowed {
            return ""
        }
        return "Not enough space available. Remove a map or select fewer maps."
    }

    private var statusColor: Color {
        if plan.selectedItems.isEmpty || plan.storagePlan.hasUnresolvedInstallSize {
            return TerentoColors.secondaryText
        }
        return plan.storagePlan.isAllowed ? TerentoColors.lichenDark : TerentoColors.error
    }

    private var storageAccessibilityValue: String {
        "\(formatBytes(plan.storagePlan.currentFreeSpace)) available of \(formatBytes(totalCapacity)), \(selectedMapSummary), \(afterInstallationSummary), \(Int(projectedUsedFraction * 100)) percent used"
    }

    private var selectedMapSummary: String {
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
                return name.isEmpty ? nil : name
            }
        )
        guard providerNames.count == 1, let providerName = providerNames.first else {
            return summary
        }
        return "\(summary) · \(providerName)"
    }

    private var afterInstallationSummary: String {
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

private struct DeviceValue: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.terentoUI(size: 12, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)

            Text(value)
                .font(.terentoUI(size: 14, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
        }
    }
}

private struct SecondaryButton: View {
    let title: String
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.terentoUI(size: 15, weight: .semibold))
                .foregroundStyle(isEnabled ? TerentoColors.graphite : TerentoColors.secondaryText)
                .padding(.horizontal, 22)
                .frame(height: 50)
                .background(
                    isEnabled ? TerentoColors.canvas : TerentoColors.border.opacity(0.55),
                    in: RoundedRectangle(cornerRadius: 9)
                )
                .overlay {
                    RoundedRectangle(cornerRadius: 9)
                        .stroke(
                            isEnabled ? TerentoColors.border : TerentoColors.inactiveBorder,
                            lineWidth: 1
                        )
                }
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.78)
    }
}

private struct RefreshControl: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label("Refresh", systemImage: "arrow.clockwise")
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .buttonStyle(.plain)
        .help("Refresh device information")
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

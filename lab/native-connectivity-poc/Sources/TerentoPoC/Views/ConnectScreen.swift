import AppKit
import SwiftUI

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

private enum AboutUpdateState: Equatable {
    case idle
    case checking
    case latest
    case available(TerentoAppUpdateManifest)
    case unavailable(String)
}

struct ConnectScreen: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var lifecycleViewModel: MapLifecycleViewModel
    @ObservedObject var evidenceController: InstallationEvidenceController
    @State private var selectedSection: TerentoSection = .device
    @State private var localInstallStep: LocalInstallStep = .choose
    @State private var troubleshootingExpanded = false
    @State private var selectedMapIDs: Set<String> = []
    @State private var selectedInstallationPlan: InstallationPlan?
    @State private var availableMapsExpanded = true
    @State private var otherMapsExpanded = false
    @State private var freizeitkarteMapsExpanded = true
    @State private var aboutUpdateState: AboutUpdateState = .idle
    @State private var mapSearchText = ""
    @FocusState private var mapSearchFieldFocused: Bool
    @State private var resolvedDeviceAsset = ResolvedDeviceAsset.fallback
    @State private var privacyActionMessage: String?
    @State private var diagnosticLogMessage: String?
    @State private var evidenceWriteStarted = false
    @State private var evidenceRecordedForCurrentWrite = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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

    private var mapSelectionItems: [MapSelectionItem] {
        mapEngine.mapSelectionItems
    }

    private var availableSelectionItems: [MapSelectionItem] {
        MapSelectionPresentationModel.available(mapSelectionItems, query: "")
    }

    private var filteredAvailableSelectionItems: [MapSelectionItem] {
        MapSelectionPresentationModel.available(
            mapSelectionItems,
            query: mapSearchText
        )
    }

    private var currentInstallationPlan: InstallationPlan? {
        mapEngine.installationPlan(for: selectedMapIDs)
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
            || !deviceEngine.canEject
    }

    var body: some View {
        HStack(spacing: 0) {
            TerentoSidebar(
                selectedSection: $selectedSection,
                connectionState: deviceEngine.state,
                canEject: canSafelyEject,
                isInstalling: installationOperationIsActive,
                navigationLocked: installationOperationIsActive,
                mapNavigationEnabled: mapSupport.canUseTerentoMaps,
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
        .onChange(of: mapEngine.installationPhase) { phase in
            updatePresenceMonitoring(for: mapEngine.state)
            recordInstallationEvidenceIfNeeded()
            if phase != .failed {
                diagnosticLogMessage = nil
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
        .onChange(of: mapEngine.installationResult) { result in
            guard let result, result.isSuccess else {
                return
            }

            selectedSection = .installMaps
            localInstallStep = .done
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
           !mapSupport.canUseTerentoMaps {
            return
        }

        let shouldRefreshMapInventory = section == .manageMaps
            || (section == .installMaps && !installationFlowHasStarted)

        if section == .installMaps, !installationFlowHasStarted {
            localInstallStep = .choose
            selectedInstallationPlan = nil
        }

        if section == .manageMaps {
            otherMapsExpanded = false
        }

        selectedSection = section

        if shouldRefreshMapInventory,
           !mapEngine.isBusy,
           !lifecycleViewModel.isBusy {
            refreshMapInventory()
        }
    }

    private func updatePresenceMonitoring(for mapState: MapEngineState) {
        let mapWorkIsBusy = switch mapState {
        case .loadingCatalog, .scanning, .acquiringArtifact, .preparingInstallation, .installing:
            true
        case .idle, .scanned, .failed:
            false
        }
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
        guard aboutUpdateState != .checking else {
            return
        }

        aboutUpdateState = .checking
        Task { @MainActor in
            do {
                let result = try await TerentoAppUpdateService().check()
                switch result {
                case .latest:
                    aboutUpdateState = .latest
                case let .available(update):
                    aboutUpdateState = .available(update)
                }
            } catch {
                aboutUpdateState = .unavailable(
                    error.localizedDescription
                )
            }
        }
    }

    private func openAppUpdate(_ update: TerentoAppUpdateManifest) {
        guard NSWorkspace.shared.open(update.downloadURL) else {
            aboutUpdateState = .unavailable(
                "The update download could not be opened. Try again later."
            )
            return
        }
    }

    /// Leaves a failed install flow without discarding its recovery record,
    /// then rebuilds the catalog and device inventory from live read-only
    /// data. This prevents the failed engine phase from trapping Install maps
    /// in its loading fallback after the user presses Back.
    private func returnToMapSelectionAfterFailure() {
        selectedInstallationPlan = nil
        localInstallStep = .choose
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

                            Text("Your device, ready for where you're going.")
                                .font(.terentoBody(size: 17, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)

                            Text("Version \(TerentoAppMetadata.version)")
                                .font(.terentoUI(size: 14, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                        }
                    }
                    .padding(.top, TerentoPageLayout.firstSectionTopPadding)

                    Text(TerentoAppMetadata.description)
                        .font(.terentoBody(size: 16, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 14)

                    aboutSection(title: "Updates") {
                        switch aboutUpdateState {
                        case .idle:
                            Text("Check whether a newer Terento version is available.")
                                .font(.terentoUI(size: 15, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)

                            SecondaryButton(title: "Check for updates") {
                                checkForAppUpdate()
                            }
                            .padding(.top, 8)
                        case .checking:
                            Text("Checking for updates…")
                                .font(.terentoUI(size: 15, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)

                            SecondaryButton(title: "Check for updates") {
                                checkForAppUpdate()
                            }
                            .disabled(true)
                            .padding(.top, 8)
                        case .latest:
                            Text("You're using the latest version.")
                                .font(.terentoUI(size: 15, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)

                            SecondaryButton(title: "Check for updates") {
                                checkForAppUpdate()
                            }
                            .padding(.top, 8)
                        case let .available(update):
                            Text("Terento \(update.displayVersion) is available.")
                                .font(.terentoUI(size: 15, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)

                            SecondaryButton(title: "Install update") {
                                openAppUpdate(update)
                            }
                            .padding(.top, 8)
                        case let .unavailable(message):
                            Text(message)
                                .font(.terentoUI(size: 15, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)

                            SecondaryButton(title: "Check for updates") {
                                checkForAppUpdate()
                            }
                            .padding(.top, 8)
                        }
                    }

                    aboutSection(title: "Support") {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 18) {
                                externalLink("GitHub repository ↗", urlString: TerentoAppLinks.repository.absoluteString)
                                externalLink("Report an issue ↗", urlString: TerentoAppLinks.issues.absoluteString)
                                externalLink("Website ↗", urlString: TerentoAppLinks.website.absoluteString)
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                externalLink("GitHub repository ↗", urlString: TerentoAppLinks.repository.absoluteString)
                                externalLink("Report an issue ↗", urlString: TerentoAppLinks.issues.absoluteString)
                                externalLink("Website ↗", urlString: TerentoAppLinks.website.absoluteString)
                            }
                        }
                    }

                    aboutSection(title: "Privacy") {
                        Text("Device state, maps, and Terento manifests stay on this Mac. Optional privacy-minimised installation reports are sent only when you choose to share them.")
                            .font(.terentoUI(size: 15, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)

                        Toggle("Share compatibility reports", isOn: compatibilitySharingBinding)
                            .toggleStyle(.checkbox)
                            .padding(.top, 8)

                        Text("Reports include watch and firmware details, map and software versions, and the installation result. They do not include a Garmin Unit ID, serial number, account information, file paths, manifests, or map files.")
                            .font(.terentoUI(size: 13, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)

                        switch evidenceController.uploadStatus {
                        case .idle:
                            EmptyView()
                        case let .uploading(count):
                            Text("Sending \(count) compatibility report\(count == 1 ? "" : "s")…")
                                .font(.terentoUI(size: 13, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                        case .uploaded:
                            Text("Compatibility reports are up to date.")
                                .font(.terentoUI(size: 13, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                        case let .waiting(count, _, willRetry):
                            Text(
                                willRetry
                                    ? "\(count) compatibility report\(count == 1 ? " is" : "s are") waiting to upload. Terento will retry automatically."
                                    : "\(count) compatibility report\(count == 1 ? " is" : "s are") waiting to upload. Terento will try again when the app is reopened."
                            )
                            .font(.terentoUI(size: 13, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                        }

                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 14) {
                                externalLink("Privacy notice ↗", urlString: TerentoAppLinks.privacy.absoluteString)
                                deleteUploadedReportsLink
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                externalLink("Privacy notice ↗", urlString: TerentoAppLinks.privacy.absoluteString)
                                deleteUploadedReportsLink
                            }
                        }
                        .padding(.top, 5)

                        if let privacyActionMessage {
                            Text(privacyActionMessage)
                                .font(.terentoUI(size: 13, weight: .regular))
                                .foregroundStyle(TerentoColors.secondaryText)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private var deleteUploadedReportsLink: some View {
        if !evidenceController.store.uploadedEvents().isEmpty {
            Button("Delete uploaded reports") {
                Task {
                    let deleted = await evidenceController.deleteUploadedReports()
                    privacyActionMessage = deleted > 0
                        ? "Uploaded reports deleted."
                        : "Uploaded reports could not be deleted. Try again later or contact privacy@terento.app."
                }
            }
            .buttonStyle(.plain)
            .font(.terentoUI(size: 14, weight: .medium))
            .foregroundStyle(TerentoColors.interactive)
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
                let hasManagedMaps = !lifecycleInventory.freizeitkarte.isEmpty

                if hasManagedMaps {
                    TerentoMapSection(
                        title: "Freizeitkarte",
                        count: lifecycleInventory.freizeitkarte.count,
                        isExpanded: $freizeitkarteMapsExpanded
                    ) {
                        ForEach(lifecycleInventory.freizeitkarte) { item in
                            ManageMapRow(
                                item: item,
                                availability: lifecycleViewModel.availability(for: item),
                                operation: lifecycleViewModel.operation(for: item.id),
                                isLifecycleBusy: mapManagementActionsBusy,
                                onBackup: { lifecycleViewModel.requestBackup(itemID: item.id) },
                                onRemove: { lifecycleViewModel.requestRemove(itemID: item.id) },
                                onUpdate: { lifecycleViewModel.requestUpdate(itemID: item.id) }
                            )
                        }
                    }
                    .padding(.top, TerentoPageLayout.firstSectionTopPadding)
                }

                if !lifecycleInventory.otherMaps.isEmpty {
                    TerentoMapSection(
                        title: "Other maps",
                        count: lifecycleInventory.otherMaps.count,
                        isExpanded: $otherMapsExpanded
                    ) {
                        ForEach(lifecycleInventory.otherMaps) { item in
                            ManageMapRow(
                                item: item,
                                availability: lifecycleViewModel.availability(for: item),
                                operation: lifecycleViewModel.operation(for: item.id),
                                isLifecycleBusy: mapManagementActionsBusy,
                                onBackup: { lifecycleViewModel.requestBackup(itemID: item.id) },
                                onRemove: { lifecycleViewModel.requestRemove(itemID: item.id) },
                                onUpdate: { lifecycleViewModel.requestUpdate(itemID: item.id) }
                            )
                        }
                    }
                    .padding(
                        .top,
                        hasManagedMaps
                            ? TerentoPageLayout.sectionSpacing
                            : TerentoPageLayout.firstSectionTopPadding
                    )

                }

                if lifecycleInventory.allItems.isEmpty {
                    MapStatusRow(
                        title: "No maps detected",
                        detail: "Connect your Garmin watch first",
                        status: "Pending",
                        note: nil
                    )
                    .padding(.top, 30)
                }
            } else {
                MapStatusRow(
                    title: "Map information is not available",
                    detail: "Connect your Garmin watch first",
                    status: "Pending",
                    note: nil
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
        .confirmationDialog(
            lifecycleViewModel.confirmationTitle,
            isPresented: Binding(
                get: { lifecycleViewModel.pendingConfirmation != nil },
                set: { isPresented in
                    if !isPresented {
                        lifecycleViewModel.cancelPendingAction()
                    }
                }
            ),
            titleVisibility: .visible
        ) {
            Button(
                lifecycleViewModel.pendingConfirmation?.action == .remove
                    ? "Remove map"
                    : "Update map",
                role: lifecycleViewModel.pendingConfirmation?.action == .remove
                    ? .destructive
                    : nil
            ) {
                lifecycleViewModel.confirmPendingAction()
            }
            Button("Cancel", role: .cancel) {
                lifecycleViewModel.cancelPendingAction()
            }
        } message: {
            Text(lifecycleViewModel.confirmationMessage)
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
                compatibility: deviceEngine.compatibility?.status ?? .unknown,
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
                .disabled(mapManagementActionsBusy || !presentation.mapSupport.canUseTerentoMaps)

                SecondaryButton(title: "Manage maps") {
                    navigate(to: .manageMaps)
                }
                .disabled(mapManagementActionsBusy || !presentation.mapSupport.canUseTerentoMaps)

                Spacer()
            }
            .padding(.top, 20)
            .padding(.bottom, 42)
            }
        }
    }

    private func deviceVariantLine(_ snapshot: DeviceSnapshot) -> String {
        let rawVariant = identity?.variant ?? snapshot.model
        let variant = rawVariant
            .replacingOccurrences(of: "47mm", with: "47 mm", options: .caseInsensitive)
        let rawFirmware = identity?.firmware ?? snapshot.deviceVersion
        let firmware = GarminFirmwareVersionFormatter.display(
            rawValue: rawFirmware,
            manufacturer: snapshot.manufacturer
        )
        return firmware.isEmpty ? variant : "\(variant) · Firmware \(firmware)"
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

                    if mapEngine.state == .loadingCatalog || mapEngine.state == .scanning {
                        MapStatusRow(
                            title: "Reading your maps",
                            detail: "Checking your Garmin watch…",
                            status: "Checking",
                            note: "Map information will appear here when your watch is ready."
                        )
                        .padding(.top, 18)
                    } else if mapSelectionItems.isEmpty {
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
                                title: "Available Freizeitkarte maps",
                                count: availableSelectionItems.count,
                                isExpanded: $availableMapsExpanded
                            )

                            Spacer(minLength: 10)

                            if availableMapsExpanded {
                                HStack(spacing: 5) {
                                    TextField("Search countries and regions", text: $mapSearchText)
                                        .textFieldStyle(.roundedBorder)
                                        .focused($mapSearchFieldFocused)

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
                                .frame(minWidth: 170, idealWidth: 238, maxWidth: 250)
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
                if mapEngine.state == .scanned, !mapSelectionItems.isEmpty, availableMapsExpanded {
                    if filteredAvailableSelectionItems.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(mapSearchText.isEmpty
                                ? "No new Freizeitkarte maps are available to install."
                                : "No maps match your search.")
                                .font(.terentoUI(size: 13, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)

                            if mapSearchText.isEmpty {
                                Button("Manage maps") {
                                    navigate(to: .manageMaps)
                                }
                                .buttonStyle(.borderless)
                                .font(.terentoUI(size: 13, weight: .semibold))
                                .foregroundStyle(TerentoColors.interactive)
                                .accessibilityHint("Opens installed map management.")
                            }
                        }
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
                                                guard item.isSelectable else { return }
                                                if selected {
                                                    selectedMapIDs.insert(item.id)
                                                } else {
                                                    selectedMapIDs.remove(item.id)
                                                }
                                            }
                                        ),
                                        isAvailable: true
                                    )
                                }
                            }
                        }
                    }
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
        TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                if mapEngine.installationPhase == .failed {
                    Text("Installation stopped")
                        .font(.terentoHeading(size: 42, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                } else {
                    Text("Installing maps")
                        .font(.terentoHeading(size: 42, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                }

                Text(installationFlowSubtitle)
                    .font(.terentoBody(size: 19, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                installationJourneyView
                    .padding(.top, 16)
            }
        } footer: {
            TerentoPageFooter {
                if mapEngine.installationPhase == .failed {
                    TerentoBackButton {
                        returnToMapSelectionAfterFailure()
                    }
                } else {
                    EmptyView()
                }
            } trailing: {
                EmptyView()
            }
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
            && plan.installItems.allSatisfy {
                MapIdentity.normalizeProvider($0.package.providerId) == "freizeitkarte"
            }
        let selectedMapListHeight = min(
            CGFloat(220),
            max(CGFloat(52), CGFloat(plan.selectedItems.count) * 48 + 4)
        )
        let installAvailability = InstallReviewAvailabilityResolver().resolve(
            plan: plan,
            deviceConnected: deviceEngine.hasConnectedDevice,
            supportedInstallFlow: supportedInstallFlow,
            installationPhase: mapEngine.installationPhase,
            hasValidatedArtifact: mapEngine.validatedArtifact != nil,
            operationBusy: mapEngine.isBusy
                || lifecycleViewModel.isBusy
                || !deviceEngine.canEject
        )

        return TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                Text("Ready to install")
                    .font(.terentoHeading(size: 42, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Review your selection before installing.")
                    .font(.terentoBody(size: 19, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                Text("Selected maps")
                    .font(.terentoUI(size: 16, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .padding(.top, 22)

                ScrollView {
                    LazyVStack(spacing: 0) {
                ForEach(Array(plan.selectedItems.enumerated()), id: \.element.id) { index, item in
                            MapSelectionRow(
                                item: item,
                                isSelected: .constant(false),
                                isAvailable: false,
                                showsSelectionControl: false,
                                showsSize: true,
                                showsDivider: MapRowDividerPolicy.showsDivider(
                                    at: index,
                                    in: plan.selectedItems.count
                                )
                            )
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(height: selectedMapListHeight)
            .padding(.top, 8)
            .accessibilityLabel("Selected maps list")

                MapSelectionStorageSummary(
                    plan: plan,
                    totalCapacity: snapshot?.totalCapacity ?? 0,
                    formatBytes: formatBytes
                )
                .padding(.top, 18)

                if plan.canContinue {
                    Text("Terento will install these maps to your Garmin.\nExisting Garmin maps will not be changed.")
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 22)

                    Toggle(isOn: compatibilitySharingBinding) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Help improve Terento")
                                .font(.terentoUI(size: 14, weight: .semibold))
                            Text("Share anonymous installation data to help us understand device compatibility and improve support for other Garmin users.")
                                .font(.terentoUI(size: 13, weight: .regular))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                            Link("What is shared and how to stop sharing ↗", destination: TerentoAppLinks.privacy)
                                .font(.terentoUI(size: 13, weight: .medium))
                                .foregroundStyle(TerentoColors.interactive)
                        }
                    }
                    .toggleStyle(.checkbox)
                    .padding(.top, 18)

                } else if plan.storagePlan.status == .blockedInsufficientSpace {
                    Text(plan.reason)
                        .font(.terentoUI(size: 15, weight: .semibold))
                        .foregroundStyle(TerentoColors.error)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 18)
                }

            }
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
                    !mapSupport.canUseTerentoMaps
                        || !installAvailability.isEnabled
                )
            }
        }
    }

    private func activeInstallationContent(_ plan: InstallationPlan) -> some View {
        let selectedMapListHeight = min(
            CGFloat(132),
            max(CGFloat(48), CGFloat(plan.selectedItems.count) * 44)
        )

        return TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                if mapEngine.installationPhase == .failed {
                    Text("Installation stopped")
                        .font(.terentoHeading(size: 42, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                } else {
                    Text("Installing maps")
                        .font(.terentoHeading(size: 42, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                }

                Text(installationFlowSubtitle)
                    .font(.terentoBody(size: 19, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)

                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(Array(plan.selectedItems.enumerated()), id: \.element.id) { index, item in
                            MapSelectionRow(
                                item: item,
                                isSelected: .constant(false),
                                isAvailable: false,
                                showsSelectionControl: false,
                                showsSize: true,
                                showsDivider: MapRowDividerPolicy.showsDivider(
                                    at: index,
                                    in: plan.selectedItems.count
                                )
                            )
                        }
                    }
                }
                .frame(height: selectedMapListHeight)
                .padding(.top, 14)
                .accessibilityLabel("Maps being installed")

                installationJourneyView
                    .padding(.top, 16)

                if mapEngine.installationPhase == .failed {
                    Text("Installation did not complete. Review the status above before trying again.")
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(TerentoColors.error)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, TerentoPageLayout.sectionSpacing)

                    installationEvidenceDeliveryView
                        .padding(.top, 8)

                    VStack(alignment: .leading, spacing: TerentoPageLayout.sectionContentTopPadding) {
                        HStack(alignment: .center, spacing: TerentoPageLayout.sectionSpacing) {
                            InstallationSupportActionButton(
                                title: "View diagnostic log",
                                isExternal: false
                            ) {
                                diagnosticLogMessage = TerentoDiagnosticLog.revealLog()
                                    ? nil
                                    : "The diagnostic log is not available yet."
                            }

                            InstallationSupportActionButton(
                                title: "Report an issue ↗",
                                isExternal: true
                            ) {
                                let report = InstallationIssueReport.generate(
                                    identity: identity,
                                    packages: plan.installItems.map(\.package),
                                    phase: mapEngine.installationPhase,
                                    error: mapEngine.installationErrorMessage
                                )
                                InstallationIssueReport.copyAndOpenGitHub(report)
                            }
                        }

                        if let diagnosticLogMessage {
                            Text(diagnosticLogMessage)
                                .font(.terentoUI(size: 13, weight: .medium))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(.top, TerentoPageLayout.sectionSpacing)
                    .padding(.bottom, TerentoPageLayout.sectionSpacing)
                }
            }
        } footer: {
            TerentoPageFooter {
                if mapEngine.installationPhase == .failed {
                    TerentoBackButton {
                        returnToMapSelectionAfterFailure()
                    }
                } else {
                    EmptyView()
                }
            } trailing: {
                EmptyView()
            }
        }
    }

    private var installationFlowSubtitle: String {
        mapEngine.installationPhase == .failed
            ? "The map was not marked as installed. Review the status below."
            : "Keep your Garmin connected until installation is complete."
    }

    private var installationJourneyView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Installation progress")
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .padding(.bottom, 12)

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
                detail: "Verifying files and preparing the Garmin image",
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
                        .foregroundStyle(TerentoColors.graphite)

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
                    .foregroundStyle(state == .failed ? TerentoColors.error : TerentoColors.secondaryText)
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
                            .font(.terentoUI(size: 12, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                if let bytes,
                   bytes.total > 0,
                   state == .active || state == .complete {
                    HStack {
                        Text("\(formatBytes(bytes.current)) of \(formatBytes(bytes.total))")
                        Spacer()
                        if bytes.speed > 0 {
                            Text("\(formatBytesPerSecond(bytes.speed))/s")
                        }
                    }
                    .font(.terentoUI(size: 11, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                }
            }
            .padding(.bottom, isLast ? 0 : 8)
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

        if current == .failed {
            if mapEngine.acquisitionState == .failed {
                return phase == .downloading ? .failed : .pending
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

    private var finishContent: some View {
        TerentoInstallFooterPageShell {
            VStack(alignment: .leading, spacing: 0) {
                TerentoPageHeader(
                    title: "Maps installed",
                    subtitle: selectedInstallationPlan?.selectedItems.count == 1
                        ? "Your selected map is ready on your Garmin."
                        : "Your selected maps are ready on your Garmin."
                )

                if mapEngine.installationResult?.isSuccess == true {
                    Text(selectedInstallationPlan?.selectedItems.count == 1 ? "Installed map" : "Installed maps")
                        .font(.terentoUI(size: 16, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                        .padding(.top, TerentoPageLayout.firstSectionTopPadding)

                    if let plan = selectedInstallationPlan {
                        LazyVStack(spacing: 0) {
                            ForEach(Array(plan.selectedItems.enumerated()), id: \.element.id) { index, item in
                                // Reuse the same map row used by Manage maps;
                                // only the selection control is hidden here.
                                MapSelectionRow(
                                    item: item,
                                    isSelected: .constant(false),
                                    isAvailable: false,
                                    showsSelectionControl: false,
                                    showsSize: true,
                                    showsDivider: MapRowDividerPolicy.showsDivider(
                                        at: index,
                                        in: plan.selectedItems.count
                                    )
                                )
                            }
                        }
                        .padding(.top, TerentoPageLayout.sectionContentTopPadding)
                        .accessibilityLabel("Installed maps list")
                    }

                    Text(selectedInstallationPlan?.selectedItems.count == 1
                        ? "Your map is ready and verified. You can safely disconnect your Garmin."
                        : "Your maps are ready and verified. You can safely disconnect your Garmin.")
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, TerentoPageLayout.sectionSpacing)

                    installationEvidenceDeliveryView
                        .padding(.top, 8)

                }
            }
        } footer: {
            TerentoPageFooter {
                TerentoBackButton(title: "Back to device") {
                    selectedSection = .device
                    selectedInstallationPlan = nil
                    localInstallStep = .choose
                }
            } trailing: {
                EmptyView()
            }
        }
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
        evidenceWriteStarted = false
        evidenceRecordedForCurrentWrite = false
        evidenceController.resetLatestDeliveryStatus()
        evidenceController.commitCurrentSharingChoice()
        mapEngine.beginInstallation(plan: plan)
    }

    private var compatibilitySharingBinding: Binding<Bool> {
        Binding(
            get: { evidenceController.compatibilitySharingEnabled },
            set: { enabled in
                privacyActionMessage = nil
                evidenceController.decideConsent(enabled ? .accepted : .declined)
            }
        )
    }

    private func recordInstallationEvidenceIfNeeded() {
        if mapEngine.installationPhase == .installing || mapEngine.installationPhase == .finishing {
            evidenceWriteStarted = true
            return
        }
        guard evidenceWriteStarted,
              !evidenceRecordedForCurrentWrite,
              let identity,
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
            case .hashMismatch, .sizeMismatch, .remoteFileMissing, .metadataMismatch, .verificationRequired: return .verification
            case .some: return .transport
            case .none: return .unknown
            }
        }()
        let results = mapEngine.installationBatchResults
        let startedCount = max(1, results.count)
        var events: [InstallationEvidenceEvent] = []
        for (index, item) in plan.installItems.prefix(startedCount).enumerated() {
            let itemSucceeded = results.indices.contains(index) ? results[index].isSuccess : succeeded
            events.append(InstallationEvidenceEvent(
                identity: identity,
                package: item.package,
                outcome: itemSucceeded ? .succeeded : .failed,
                finishingResult: itemSucceeded ? .verified : .failed,
                errorCategory: itemSucceeded ? nil : category
            ))
        }
        evidenceRecordedForCurrentWrite = true

        Task { @MainActor in
            _ = await evidenceController.recordAndUpload(events)
        }
    }

    @ViewBuilder
    private var installationEvidenceDeliveryView: some View {
        switch evidenceController.latestDeliveryStatus {
        case .idle:
            EmptyView()
        case .notShared:
            EmptyView()
        case let .sending(count):
            Text("Sending \(count) compatibility report\(count == 1 ? "" : "s")…")
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        case let .sent(count):
            Text(count == 1 ? "Compatibility report sent." : "Compatibility reports sent.")
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        case let .queued(count, _, _):
            Text(count == 1
                ? "Compatibility report could not be sent. It remains on this Mac."
                : "Compatibility reports could not be sent. They remain on this Mac.")
            .font(.terentoUI(size: 13, weight: .medium))
            .foregroundStyle(TerentoColors.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
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
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
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

private struct InstallationSupportActionButton: View {
    let title: String
    let isExternal: Bool
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.terentoUI(size: 14, weight: .medium))
                .foregroundStyle(isEnabled ? TerentoColors.interactive : TerentoColors.secondaryText)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .frame(minHeight: 32)
                .contentShape(Rectangle())
        }
        .buttonStyle(.link)
        .help(isExternal ? "Opens GitHub in your browser." : "Opens the local diagnostic log on this Mac.")
        .accessibilityLabel(title.replacingOccurrences(of: " ↗", with: ""))
        .accessibilityHint(
            isExternal
                ? "Opens GitHub in your browser."
                : "Opens the local diagnostic log on this Mac."
        )
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

                if presentation.mapSupport.showsTerentoCompatibility {
                    CompatibilityStatusView(status: presentation.compatibility)
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

        guard asset.isFallback,
              let url = Bundle.module.url(
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
    @State private var showingCompatibilityInfo = false

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: statusIcon)
                .font(.system(size: 13, weight: .semibold))
                .accessibilityHidden(true)

            Text(status.userLabel)
                .font(.terentoUI(size: 13, weight: .medium))

            Button {
                showingCompatibilityInfo = true
            } label: {
                Image(systemName: "info.circle")
                    .font(.system(size: 13, weight: .medium))
                    .frame(width: 22, height: 22)
            }
            .buttonStyle(.plain)
            .help(compatibilityPopoverBody)
            .accessibilityLabel("\(status.userLabel) compatibility information")
            .accessibilityHint("Opens an explanation of this device's compatibility status.")
            .popover(isPresented: $showingCompatibilityInfo) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(status.userLabel)
                        .font(.terentoUI(size: 15, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Text(compatibilityPopoverBody)
                        .font(.terentoUI(size: 13, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(14)
                .frame(width: 258, alignment: .leading)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(status.userLabel). \(compatibilityPopoverBody)")
            }
        }
        .foregroundStyle(statusColor)
        .accessibilityElement(children: .contain)
    }

    private var compatibilityPopoverBody: String {
        switch status {
        case .tested:
            return "Tested with this Garmin model on real hardware.\n\nDevice detection and supported capabilities have been verified."
        default:
            return CompatibilityPresentation.explanation(for: status)
        }
    }

    private var statusIcon: String {
        switch status {
        case .tested, .supported, .verified:
            return "checkmark"
        case .testing:
            return "hourglass"
        case .unknown:
            return "questionmark"
        }
    }

    private var statusColor: Color {
        switch status {
        case .tested, .supported, .verified:
            return TerentoColors.lichenDark
        case .testing:
            return TerentoColors.interactive
        case .unknown:
            return TerentoColors.secondaryText
        }
    }
}

private struct ManageMapRow: View {
    let item: MapLifecycleItem
    let availability: MapLifecycleActionAvailability
    let operation: MapLifecycleOperationState?
    let isLifecycleBusy: Bool
    let onBackup: () -> Void
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
        ManageMapRowActionPresentation.actions(for: availability)
    }

    var body: some View {
        TerentoMapRow(
            title: item.title,
            detail: operation?.phase == .completed ? "Action complete" : item.manageDetailLabel,
            note: operation?.message,
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
                    actions: availableActions,
                    isEnabled: !isLifecycleBusy,
                    onAction: perform
                )
            }
        }
    }

    private func perform(_ action: MapLifecycleAction) {
        switch action {
        case .backup:
            onBackup()
        case .remove:
            onRemove()
        case .update:
            onUpdate()
        }
    }
}

private struct ManageActionGroup: View {
    let actions: [MapLifecycleAction]
    let isEnabled: Bool
    let onAction: (MapLifecycleAction) -> Void

    var body: some View {
        HStack(spacing: 2) {
            ForEach(actions, id: \.rawValue) { action in
                ManageActionButton(
                    action: action,
                    isEnabled: isEnabled,
                    onAction: onAction
                )
            }
        }
        .padding(3)
        .background(
            TerentoColors.surface.opacity(0.86),
            in: RoundedRectangle(cornerRadius: 8, style: .continuous)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
        .frame(minHeight: 36, alignment: .center)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Map actions")
    }
}

private struct ManageActionButton: View {
    let action: MapLifecycleAction
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
        case .backup:
            return "Back up"
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
                .foregroundStyle(isInteractive ? TerentoColors.graphite : TerentoColors.secondaryText)
                .lineLimit(1)
                .padding(.horizontal, 8)
                .frame(minWidth: 44, minHeight: 30)
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
        .accessibilityLabel(title)
    }

    private var backgroundColor: Color {
        guard isInteractive else {
            return Color.clear
        }
        if isFocused {
            return TerentoColors.sky.opacity(0.20)
        }
        if isHovered {
            return TerentoColors.sky.opacity(0.12)
        }
        return Color.clear
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
                }
            }

            if let progress {
                ProgressView(value: progress.fractionCompleted)
                    .progressViewStyle(.linear)
                    .tint(TerentoColors.interactive)
                    .frame(height: InstallationTimelineLayout.progressBarHeight)

                HStack(spacing: 8) {
                    Text("\(formatBytes(progress.bytesCompleted)) of \(formatBytes(progress.totalBytes))")
                    if progress.bytesPerSecond > 0 {
                        Text("\(formatBytesPerSecond(progress.bytesPerSecond))/s")
                    }
                }
                .font(.terentoUI(size: 10, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
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
        guard let progress else { return "In progress" }
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

struct MapSelectionRow: View {
    let item: MapSelectionItem
    @Binding var isSelected: Bool
    let isAvailable: Bool
    let showsSelectionControl: Bool
    let showsSize: Bool
    let showsDivider: Bool

    init(
        item: MapSelectionItem,
        isSelected: Binding<Bool>,
        isAvailable: Bool,
        showsSelectionControl: Bool = true,
        showsSize: Bool? = nil,
        showsDivider: Bool = true
    ) {
        self.item = item
        self._isSelected = isSelected
        self.isAvailable = isAvailable
        self.showsSelectionControl = showsSelectionControl
        self.showsSize = showsSize ?? (isAvailable && item.comparison.installedMap == nil)
        self.showsDivider = showsDivider
    }

    var body: some View {
        TerentoMapRow(
            title: item.title,
            detail: detail,
            contentSpacing: 9,
            rowVerticalPadding: 10,
            showsDivider: showsDivider
        ) {
            HStack(spacing: 6) {
                if isAvailable && item.isSelectable && showsSelectionControl {
                    Toggle("", isOn: $isSelected)
                        .toggleStyle(.checkbox)
                        .labelsHidden()
                } else if showsSelectionControl && !isAlreadyInstalledSearchResult {
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
            if showsSize {
                Text(item.installSizeBytes.map(formatBytes) ?? "Size calculated before installation")
                    .font(.terentoUI(size: 13, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .multilineTextAlignment(.trailing)
                    .frame(maxWidth: 190, alignment: .trailing)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture {
            guard isAvailable, item.isSelectable else { return }
            isSelected.toggle()
        }
        .opacity(item.isSelectable || item.comparison.status == .upToDate ? 1 : 0.78)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityValue(isAvailable && item.isSelectable && showsSelectionControl
            ? (isSelected ? "Selected" : "Not selected")
            : detail)
    }

    private var detail: String {
        if isAlreadyInstalledSearchResult {
            return "Already installed"
        }

        switch item.comparison.status {
        case .notInstalled:
            return item.installSizeBytes == nil ? "Size calculated before installation" : ""
        case .updateAvailable:
            return "Installed · Update available"
        case .upToDate:
            return "Installed · Up to date"
        case .newerInstalled:
            return "Installed · Newer version installed"
        case .unknown:
            return "Installed · Version unavailable"
        }
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
                alignment: .firstTextBaseline,
                spacing: TerentoPageLayout.sectionHeaderItemSpacing
            ) {
                Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .frame(
                        width: TerentoPageLayout.sectionHeaderChevronWidth,
                        height: TerentoPageLayout.sectionHeaderChevronHeight
                    )

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
            return "\(countLabel) selected · Size calculated before installation"
        }
        return "\(countLabel) · \(formatBytes(plan.storagePlan.selectedMapBytes)) selected"
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

private enum TerentoColors {
    static let sky = Color(hex: 0x7898A8)
    static let lichen = Color(hex: 0x9AA58B)
    static let lichenDark = Color(hex: 0x5F6D53)
    static let warmStone = Color(hex: 0xB39A78)
    static let canvas = Color(hex: 0xF7F3EC)
    static let sidebar = Color(hex: 0xF1EEE7)
    static let surface = Color.white.opacity(0.78)
    static let helpSurface = Color.white.opacity(0.48)
    static let graphite = Color(hex: 0x222A2B)
    static let secondaryText = Color(hex: 0x6D706F)
    static let border = Color(hex: 0xD7DDDA)
    static let sidebarBorder = Color(hex: 0xD7DDDA).opacity(0.72)
    static let selectedBackground = Color(hex: 0xE7EEF1)
    static let inactiveBorder = Color(hex: 0xC7C9C5)
    static let progressTrack = Color(hex: 0xDDE6E5)
    static let interactive = Color(hex: 0x577787)
    static let error = Color(hex: 0x8A4F47)
}

private extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

private extension Font {
    static func terentoHeading(size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: "Instrument Sans", size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom("Instrument Sans", size: size).weight(weight)
    }

    static func terentoUI(size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: "Inter", size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom("Inter", size: size).weight(weight)
    }

    static func terentoBody(size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: "Inter", size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom("Inter", size: size).weight(weight)
    }
}

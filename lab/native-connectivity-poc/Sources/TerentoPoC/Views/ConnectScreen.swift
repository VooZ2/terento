import AppKit
import SwiftUI

enum TerentoStage: String, CaseIterable, Identifiable {
    case connect = "Connect"
    case device = "Device"
    case choose = "Choose"
    case install = "Install"
    case finish = "Finish"

    var id: String { rawValue }
}

enum TerentoSection: String, CaseIterable, Identifiable {
    case device = "Device"
    case maps = "Maps"
    case settings = "Settings"

    var id: String { rawValue }
}

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

struct ConnectScreen: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var lifecycleViewModel: MapLifecycleViewModel
    @State private var selectedSection: TerentoSection = .device
    @State private var localInstallStep: LocalInstallStep = .choose
    @State private var showingManagedMaps = false
    @State private var troubleshootingExpanded = false
    @State private var selectedMapIDs: Set<String> = []
    @State private var selectedInstallationPlan: InstallationPlan?
    @State private var installedMapsExpanded = true
    @State private var availableMapsExpanded = true
    @State private var otherMapsExpanded = true
    @State private var freizeitkarteMapsExpanded = true
    @State private var mapSearchText = ""
    @State private var resolvedDeviceAsset = ResolvedDeviceAsset.fallback
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var snapshot: DeviceSnapshot? {
        deviceEngine.snapshot
    }

    private var identity: DeviceIdentity? {
        deviceEngine.compatibility?.identity
    }

    private var mapSelectionItems: [MapSelectionItem] {
        mapEngine.mapSelectionItems
    }

    private var installedSelectionItems: [MapSelectionItem] {
        MapSelectionPresentationModel.installed(mapSelectionItems)
            .filter { $0.comparison.managementState == .managedByTerento }
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

    var body: some View {
        HStack(spacing: 0) {
            TerentoSidebar(
                selectedSection: $selectedSection,
                connectionState: deviceEngine.state
            )

            Rectangle()
                .fill(TerentoColors.sidebarBorder)
                .frame(width: 1)

            mainContent
        }
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
        .frame(minWidth: 980, minHeight: 720)
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
                showingManagedMaps = false
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
            showingManagedMaps = false
            mapEngine.scanDeviceMaps(
                deviceIdentity: deviceEngine.compatibility?.identity,
                availableStorage: deviceEngine.snapshot?.freeSpace
            )
        }
        .onChange(of: mapEngine.state) { newState in
            let transportIsBusy = switch newState {
            case .loadingCatalog, .scanning, .acquiringArtifact, .preparingInstallation, .installing:
                true
            case .idle, .scanned, .failed:
                false
            }
            deviceEngine.setPresenceMonitoringEnabled(!transportIsBusy)
        }
        .onChange(of: mapEngine.installationResult) { result in
            guard result?.isSuccess == true else {
                return
            }

            selectedSection = .maps
            localInstallStep = .done
            showingManagedMaps = false
        }
    }

    private var mainContent: some View {
        Group {
            if selectedSection == .maps && !showingManagedMaps {
                VStack(spacing: 0) {
                    LocalInstallProgress(activeStep: localInstallStep)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                        .padding(.bottom, 20)

                    Divider()
                        .overlay(TerentoColors.border)

                    ScrollView {
                        workflowContent
                            .frame(maxWidth: 980)
                            .frame(maxWidth: .infinity, alignment: .top)
                            .padding(.vertical, 24)
                    }
                    .scrollIndicators(.automatic)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            } else {
                ScrollView {
                    workflowContent
                        .frame(maxWidth: 980)
                        .frame(maxWidth: .infinity, alignment: .top)
                        .padding(.vertical, 24)
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

    @ViewBuilder
    private var workflowContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            if selectedSection == .maps && showingManagedMaps {
                managedMapsContent
            } else {
                switch selectedSection {
                case .device:
                    deviceContent
                case .maps:
                    switch localInstallStep {
                    case .choose:
                        mapsContent
                    case .install:
                        installContent
                    case .done:
                        finishContent
                    }
                case .settings:
                    settingsContent
                }
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

    private var connectContent: some View {
        VStack(alignment: .center, spacing: 0) {
            ResourceImage(name: "connect-illustration", subdirectory: "Illustrations")
                .scaledToFit()
                .frame(maxWidth: 760, maxHeight: 360)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 28)

            connectionStatusView
                .padding(.top, 20)

            if deviceEngine.state == .disconnected || deviceEngine.state == .failed {
                PrimaryButton(title: "Connect device", action: startReadOnlyCheck)
                    .padding(.top, 18)
            }

            if shouldShowTroubleshooting {
                DisclosureGroup(isExpanded: $troubleshootingExpanded) {
                    troubleshootingContent
                        .padding(.top, 10)
                } label: {
                    Label("Having trouble connecting?", systemImage: "questionmark.circle")
                        .font(.terentoUI(size: 14, weight: .semibold))
                        .foregroundStyle(TerentoColors.secondaryText)
                }
                .tint(TerentoColors.secondaryText)
                .padding(.top, 20)
                .frame(maxWidth: 620, alignment: .center)
            }

            Spacer(minLength: 20)
        }
        .frame(maxWidth: 900, maxHeight: .infinity, alignment: .top)
        .padding(.horizontal, 48)
        .padding(.top, 18)
        .padding(.bottom, 24)
    }

    private var connectionStatusView: some View {
        VStack(spacing: 5) {
            HStack(spacing: 8) {
                Circle()
                    .fill(connectionStatusColor)
                    .frame(width: 9, height: 9)

                Text(connectionStatusTitle)
                    .font(.terentoUI(size: 17, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
            }

            Text(connectionStatusDescription)
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)

        }
    }

    private var connectionStatusTitle: String {
        switch deviceEngine.state {
        case .disconnected:
            return "Ready when you are."
        case .detecting:
            return "Getting ready for the trail."
        case .connected, .ready:
            return "Garmin \(deviceEngine.compatibility?.displayName ?? "watch") connected"
        case .ejecting:
            return "Releasing your Garmin…"
        case .safeToDisconnect:
            return "Safe to disconnect"
        case .failed:
            return "We couldn’t connect yet"
        }
    }

    private var connectionStatusDescription: String {
        switch deviceEngine.state {
        case .disconnected:
            return "Connect your watch to this Mac with a USB cable."
        case .detecting:
            return "Looking for your Garmin…"
        case .connected, .ready:
            return "Your Garmin is ready."
        case .ejecting:
            return "Finishing the connection safely."
        case .safeToDisconnect:
            return "You can unplug your Garmin."
        case .failed:
            return deviceEngine.userErrorMessage
                ?? "Make sure your watch is connected and unlocked."
        }
    }

    private var connectionStatusColor: Color {
        switch deviceEngine.state {
        case .connected, .ready, .safeToDisconnect:
            return TerentoColors.lichenDark
        case .detecting, .ejecting:
            return TerentoColors.sky
        case .failed:
            return TerentoColors.error
        default:
            return TerentoColors.secondaryText
        }
    }

    private var shouldShowTroubleshooting: Bool {
        deviceEngine.state == .failed || deviceEngine.readingAttempt >= 3
    }

    private var troubleshootingContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            troubleshootingRow("Try a different USB cable", icon: "cable.connector")
            troubleshootingRow("Connect directly to your Mac", icon: "desktopcomputer")
            troubleshootingRow("Make sure your watch is unlocked", icon: "lock.open")
            troubleshootingRow("Restart your watch and try again", icon: "arrow.clockwise")
            troubleshootingRow("Close other Garmin apps", icon: "xmark.app")

            VStack(alignment: .leading, spacing: 6) {
                Text("Need more help?")
                    .font(.terentoUI(size: 13, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                externalLink(
                    "Garmin connection guide ↗",
                    urlString: "https://support.garmin.com/"
                )
            }
            .padding(.top, 8)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private func troubleshootingRow(_ text: String, icon: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
                .frame(width: 18)

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

    private var settingsContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Settings")
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("Manage Terento preferences and app information.")
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)

            Text("Your device data stays on this Mac.")
                .font(.terentoUI(size: 15, weight: .semibold))
                .foregroundStyle(TerentoColors.lichenDark)
                .padding(.top, 18)

            VStack(alignment: .leading, spacing: 9) {
                Text("About Terento")
                    .font(.terentoUI(size: 18, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text("Open source")
                    .font(.terentoUI(size: 14, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)

                externalLink("View source code ↗", urlString: "https://github.com/VooZ2/terento")
                externalLink("Report an issue ↗", urlString: "https://github.com/VooZ2/terento/issues")
                externalLink("Website ↗", urlString: "https://terento.app")
                externalLink("GitHub repository ↗", urlString: "https://github.com/VooZ2/terento")
            }
            .font(.terentoUI(size: 14, weight: .medium))
            .foregroundStyle(TerentoColors.interactive)
            .padding(.top, 26)
        }
        .frame(maxWidth: 760, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
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
        VStack(alignment: .leading, spacing: 0) {
            Text("Manage maps")
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("Maps on your Garmin.")
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .padding(.top, 14)

            if let lifecycleInventory = mapEngine.mapLifecycleInventory() {

                if !lifecycleInventory.freizeitkarte.isEmpty {
                    DisclosureGroup(isExpanded: $freizeitkarteMapsExpanded) {
                        ForEach(lifecycleInventory.freizeitkarte) { item in
                            ManageMapRow(
                                item: item,
                                availability: lifecycleViewModel.availability(for: item),
                                operation: lifecycleViewModel.operation(for: item.id),
                                isLifecycleBusy: lifecycleViewModel.isBusy,
                                onBackup: { lifecycleViewModel.requestBackup(itemID: item.id) },
                                onRemove: { lifecycleViewModel.requestRemove(itemID: item.id) },
                                onUpdate: { lifecycleViewModel.requestUpdate(itemID: item.id) }
                            )
                        }
                    } label: {
                        mapSectionLabel("Freizeitkarte maps", count: lifecycleInventory.freizeitkarte.count)
                    }
                    .tint(TerentoColors.secondaryText)
                    .padding(.top, 28)
                }

                if !lifecycleInventory.otherMaps.isEmpty {
                    DisclosureGroup(isExpanded: $otherMapsExpanded) {
                        ForEach(lifecycleInventory.otherMaps) { item in
                            ManageMapRow(
                                item: item,
                                availability: lifecycleViewModel.availability(for: item),
                                operation: lifecycleViewModel.operation(for: item.id),
                                isLifecycleBusy: lifecycleViewModel.isBusy,
                                onBackup: { lifecycleViewModel.requestBackup(itemID: item.id) },
                                onRemove: { lifecycleViewModel.requestRemove(itemID: item.id) },
                                onUpdate: { lifecycleViewModel.requestUpdate(itemID: item.id) }
                            )
                        }
                    } label: {
                        mapSectionLabel("Other maps", count: lifecycleInventory.otherMaps.count)
                    }
                    .tint(TerentoColors.secondaryText)
                    .padding(.top, 22)
                }

                if lifecycleInventory.allItems.isEmpty {
                    MapStatusRow(
                        title: "No maps detected",
                        detail: "Connect your Garmin watch first",
                        status: "Pending",
                        note: "Garmin system maps are not included in this list."
                    )
                    .padding(.top, 30)
                }
            } else {
                MapStatusRow(
                    title: "Map information is not available",
                    detail: "Connect your Garmin watch first",
                    status: "Pending",
                    note: "Only maps detected from the connected watch are shown."
                )
                .padding(.top, 30)
            }

            Text("Other maps are shown for reference and left unchanged.")
                .font(.terentoUI(size: 14, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 22)

            SecondaryButton(title: "Back") {
                showingManagedMaps = false
            }
            .padding(.top, 26)
            .padding(.bottom, 42)
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
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
        VStack(alignment: .leading, spacing: 0) {
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
                presentation: DevicePresentation(
                    identity: deviceEngine.compatibility?.identity
                        ?? GarminDeviceIdentityAdapter().makeIdentity(from: snapshot),
                    deviceName: deviceEngine.compatibility?.displayName
                        ?? "\(snapshot.manufacturer) \(snapshot.model)",
                    variant: deviceVariantLine(snapshot),
                    compatibility: deviceEngine.compatibility?.status ?? .unknown,
                    asset: resolvedDeviceAsset
                ),
                canEject: deviceEngine.canEject
                    && !mapEngine.isBusy
                    && !lifecycleViewModel.isBusy,
                onEject: {
                    guard deviceEngine.canEject,
                          !mapEngine.isBusy,
                          !lifecycleViewModel.isBusy else {
                        return
                    }

                    lifecycleViewModel.resetForDisconnectedDevice()
                    mapEngine.resetForDisconnectedDevice()
                    deviceEngine.ejectDevice()
                }
            )
            .padding(.top, 30)

            StorageCard(
                total: formatBytes(snapshot.totalCapacity),
                available: formatBytes(snapshot.freeSpace),
                fillRatio: storageFillRatio(for: snapshot)
            )
            .padding(.top, 18)

            Divider()
                .overlay(TerentoColors.border)
                .padding(.top, 30)

            HStack(spacing: 12) {
                SecondaryButton(title: "Manage maps") {
                    selectedSection = .maps
                    showingManagedMaps = true
                }

                PrimaryButton(title: "Install maps") {
                    selectedSection = .maps
                    showingManagedMaps = false
                    localInstallStep = .choose
                }

                Spacer()
            }
            .padding(.top, 24)
            .padding(.bottom, 42)
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
    }

    private func deviceVariantLine(_ snapshot: DeviceSnapshot) -> String {
        let rawVariant = identity?.variant ?? snapshot.model
        let variant = rawVariant
            .replacingOccurrences(of: "47mm", with: "47 mm", options: .caseInsensitive)
        let firmware = identity?.firmware ?? snapshot.deviceVersion
        return firmware.isEmpty ? variant : "\(variant) · Firmware \(firmware)"
    }

    private func mapSectionLabel(_ title: String, count: Int) -> some View {
        HStack(spacing: 8) {
            Text(title)
                .font(.terentoUI(size: 17, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("\(count)")
                .font(.terentoUI(size: 12, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
        }
    }

    private var waitingForDeviceContent: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Your device")
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("Connect your Garmin watch to read its device and map information.")
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)

            PrimaryButton(title: "Connect device", action: startReadOnlyCheck)
                .padding(.top, 12)

            if let message = deviceEngine.userErrorMessage {
                Text(message)
                    .font(.terentoUI(size: 14, weight: .medium))
                    .foregroundStyle(TerentoColors.error)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
    }

    private var mapsContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Install maps")
                        .font(.terentoHeading(size: 42, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Text("Choose the maps you want on your Garmin.")
                        .font(.terentoBody(size: 19, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

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
                }
            }

            if mapEngine.state == .loadingCatalog || mapEngine.state == .scanning {
                MapStatusRow(
                    title: "Reading your maps",
                    detail: "Checking your Garmin watch…",
                    status: "Checking",
                    note: "Only map information is read. Nothing is changed."
                )
                .padding(.top, 24)
            } else if mapSelectionItems.isEmpty {
                MapStatusRow(
                    title: "Maps are not ready yet",
                    detail: "Connect your Garmin watch first",
                    status: "Pending",
                    note: mapEngine.userErrorMessage
                        ?? "Available community maps will appear here after the device is checked."
                )
                .padding(.top, 24)
            } else {
                DisclosureGroup(isExpanded: $installedMapsExpanded) {
                    if installedSelectionItems.isEmpty {
                        Text("No maps installed by Terento")
                            .font(.terentoUI(size: 13, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .padding(.top, 10)
                    } else {
                        LazyVStack(spacing: 8) {
                            ForEach(installedSelectionItems) { item in
                                MapSelectionRow(
                                    item: item,
                                    isSelected: .constant(false),
                                    isAvailable: false
                                )
                            }
                        }
                        .padding(.top, 10)
                    }
                } label: {
                    sectionLabel("Installed maps", count: installedSelectionItems.count)
                }
                .tint(TerentoColors.secondaryText)
                .padding(.top, 22)

                DisclosureGroup(isExpanded: $availableMapsExpanded) {
                    if filteredAvailableSelectionItems.isEmpty {
                        Text(mapSearchText.isEmpty
                            ? "No maps are currently available for installation."
                            : "No maps match your search.")
                            .font(.terentoUI(size: 13, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .padding(.vertical, 18)
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 8) {
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
                            .padding(.vertical, 2)
                        }
                        .frame(maxHeight: 238)
                        .scrollIndicators(.automatic)
                    }
                } label: {
                    HStack(spacing: 14) {
                        sectionLabel("Available maps", count: availableSelectionItems.count)
                        Spacer(minLength: 14)
                        TextField("Search countries and regions", text: $mapSearchText)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 238)
                            .accessibilityLabel("Search available maps")
                    }
                }
                .tint(TerentoColors.secondaryText)
                .padding(.top, 18)
                .frame(maxHeight: .infinity, alignment: .top)

                if let plan = currentInstallationPlan {
                    MapSelectionStorageSummary(
                        plan: plan,
                        totalCapacity: snapshot?.totalCapacity ?? 0,
                        formatBytes: formatBytes
                    )
                    .padding(.top, 14)
                }
            }

            Spacer(minLength: 12)

            HStack(spacing: 12) {
                SecondaryButton(title: "Back") {
                    selectedSection = .device
                }

                Spacer()

                PrimaryButton(title: "Continue") {
                    guard let plan = currentInstallationPlan, plan.canContinue else {
                        return
                    }

                    selectedInstallationPlan = plan
                    localInstallStep = .install
                }
                .disabled(!(currentInstallationPlan?.canContinue ?? false))
            }
            .padding(.top, 16)
        }
        .frame(maxWidth: 1050, maxHeight: .infinity, alignment: .topLeading)
        .padding(.horizontal, 42)
        .padding(.top, 30)
        .padding(.bottom, 22)
    }

    private func sectionLabel(_ title: String, count: Int) -> some View {
        HStack(spacing: 8) {
            Text(title)
                .font(.terentoUI(size: 17, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
            Text("\(count) maps")
                .font(.terentoUI(size: 12, weight: .semibold))
                .foregroundStyle(TerentoColors.secondaryText)
        }
    }

    private var unifiedMapInventory: UnifiedMapInventory? {
        mapEngine.result?.unifiedMapInventory(
            selectedCatalogPackageID: Stage42ArtifactValidator.expectedPackageID
        )
    }

    @ViewBuilder
    private var installContent: some View {
        if let selectedInstallationPlan {
            plannedInstallContent(selectedInstallationPlan)
        } else {
            legacyInstallContent
        }
    }

    private var legacyInstallContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Your maps are ready.")
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("Review the safety check before anything is sent to your Garmin watch.")
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .padding(.top, 14)

            if let preflight = mapEngine.latviaPreflight {
                MapStatusRow(
                    title: "Freizeitkarte Latvia",
                    detail: preflight.selectedMap.installSizeBytes.map {
                        "Map size · \(formatBytes($0))"
                    } ?? "Size calculated before installation",
                    status: preflight.status.userLabel,
                    note: preflight.userNote
                )
                .padding(.top, 30)
            }

            if let artifact = mapEngine.validatedArtifact {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Installation details")
                        .font(.terentoUI(size: 18, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    installDetail(label: "Device", value: identityDisplayName)
                    installDetail(label: "Map", value: "Freizeitkarte Latvia · 2026-05")
                    installDetail(label: "Size", value: formatBytes(artifact.installSizeBytes))
                    installDetail(label: "Target", value: artifact.targetFilename)
                    Text("Existing maps, including Lithuania, will not be replaced by this new-map installation.")
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 6)
                }
                .padding(22)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 14))
                .overlay {
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
                }
                .padding(.top, 18)
            }

            if let storagePlan = mapEngine.latviaPreflight?.storagePlan {
                installationStorageView(storagePlan)
                    .padding(.top, 18)
            }

            if mapEngine.installationPhase != .idle {
                installationJourneyView
                    .padding(.top, 22)
            }

            HStack(spacing: 12) {
                if mapEngine.installationPhase == .awaitingConfirmation {
                    PrimaryButton(title: "Install maps") {
                        mapEngine.installLatvia()
                    }
                }

                SecondaryButton(title: "Back") {
                    selectedInstallationPlan = nil
                    localInstallStep = .choose
                }

                Spacer()
            }
            .padding(.top, 22)
            .padding(.bottom, 42)
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
    }

    private func plannedInstallContent(_ plan: InstallationPlan) -> some View {
        let canRunLatviaFlow = plan.installItems.count == 1
            && plan.installItems.first?.package.id == Stage42ArtifactValidator.expectedPackageID

        return VStack(alignment: .leading, spacing: 0) {
            Text("Your maps are ready.")
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("Review your selection before installing.")
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 14)

            VStack(alignment: .leading, spacing: 12) {
                ForEach(plan.selectedItems) { item in
                    HStack {
                        Image(systemName: item.action == .install ? "plus.circle" : "map")
                            .foregroundStyle(TerentoColors.lichenDark)

                        Text(item.title)
                            .font(.terentoUI(size: 16, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)

                        Spacer()

                        Text(item.installSizeBytes.map(formatBytes) ?? "Size calculated before installation")
                            .font(.terentoUI(size: 14, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                    }
                }
            }
            .padding(22)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 14))
            .overlay {
                RoundedRectangle(cornerRadius: 14)
                    .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
            }
            .padding(.top, 28)

            installationStorageView(plan.storagePlan)
                .padding(.top, 18)

            if plan.canContinue {
                if canRunLatviaFlow {
                    Text("Ready to prepare the selected map. No device write has started.")
                        .font(.terentoUI(size: 15, weight: .semibold))
                        .foregroundStyle(TerentoColors.lichenDark)
                        .padding(.top, 20)

                    if mapEngine.installationPhase != .idle {
                        installationJourneyView
                            .padding(.top, 18)
                    }
                } else {
                    Text("This selection is ready. Multi-region installation will be enabled in a later step.")
                        .font(.terentoUI(size: 15, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 20)
                }
            } else {
                Text(plan.reason)
                    .font(.terentoUI(size: 15, weight: .semibold))
                    .foregroundStyle(TerentoColors.error)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 20)
            }

            HStack(spacing: 12) {
                if plan.canContinue && canRunLatviaFlow {
                    if mapEngine.validatedArtifact != nil,
                       mapEngine.installationPhase == .awaitingConfirmation {
                        PrimaryButton(title: "Install maps") {
                            mapEngine.installLatvia()
                        }
                    } else if mapEngine.installationPhase == .idle {
                        PrimaryButton(title: "Install maps") {
                            mapEngine.prepareLatviaArtifact()
                        }
                    }
                }

                SecondaryButton(title: "Back") {
                    selectedInstallationPlan = nil
                    localInstallStep = .choose
                }

                Spacer()
            }
            .padding(.top, 24)
            .padding(.bottom, 42)
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
    }

    private var installationJourneyView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Installation progress")
                .font(.terentoUI(size: 18, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .padding(.bottom, 20)

            installationStepRow(
                title: "Downloading",
                detail: downloadStepDetail,
                state: installationStepState(for: .downloading),
                progress: mapEngine.acquisitionProgress?.fractionCompleted,
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
                    ? mapEngine.installationPhaseProgress
                    : nil,
                bytes: nil,
                isLast: false
            )

            installationStepRow(
                title: "Installing",
                detail: "Writing the validated map to your Garmin watch",
                state: installationStepState(for: .installing),
                progress: mapEngine.installationProgress?.fractionCompleted,
                bytes: mapEngine.installationProgress.map {
                    (current: $0.bytesTransferred, total: $0.totalBytes, speed: $0.bytesPerSecond)
                },
                isLast: false
            )

            installationStepRow(
                title: "Finishing",
                detail: "Reading the map back and completing final checks",
                state: installationStepState(for: .finishing),
                progress: mapEngine.installationPhase == .finishing
                    ? mapEngine.installationPhaseProgress
                    : nil,
                bytes: nil,
                isLast: true
            )
        }
        .padding(22)
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
        HStack(alignment: .top, spacing: 16) {
            VStack(spacing: 0) {
                Image(systemName: installationStepIcon(for: state))
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(installationStepColor(for: state))
                    .frame(width: 28, height: 28)
                    .background(TerentoColors.canvas, in: Circle())

                if !isLast {
                    Rectangle()
                        .fill(TerentoColors.border)
                        .frame(width: 2, height: 66)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    Text(title)
                        .font(.terentoUI(size: 16, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Spacer()

                    if state == .active,
                       let progress {
                        Text("\(Int(progress * 100))%")
                            .font(.terentoUI(size: 14, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)
                    }
                }

                Text(state == .failed ? (mapEngine.installationErrorMessage ?? detail) : detail)
                    .font(.terentoUI(size: 14, weight: .medium))
                    .foregroundStyle(state == .failed ? TerentoColors.error : TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)

                if state == .active {
                    if let progress {
                        ProgressView(value: progress)
                            .progressViewStyle(.linear)
                            .tint(TerentoColors.interactive)
                    } else {
                        ProgressView()
                            .progressViewStyle(.linear)
                            .tint(TerentoColors.interactive)
                    }
                }

                if let bytes,
                   state == .active || state == .complete {
                    HStack {
                        Text("\(formatBytes(bytes.current)) of \(formatBytes(bytes.total))")
                        Spacer()
                        if bytes.speed > 0 {
                            Text("\(formatBytesPerSecond(bytes.speed)) /s")
                        }
                    }
                    .font(.terentoUI(size: 12, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
                }
            }
            .padding(.bottom, isLast ? 0 : 10)
        }
    }

    private func installationStepState(for phase: InstallationProcessPhase) -> InstallationStepState {
        let current = mapEngine.installationPhase

        if current == .failed {
            if phase == .downloading,
               mapEngine.acquisitionState == .downloading {
                return .failed
            }
            if phase == .preparing,
               mapEngine.state == .acquiringArtifact || mapEngine.state == .preparingInstallation {
                return .failed
            }
            if phase == .finishing,
               mapEngine.installationProgress?.fractionCompleted == 1 {
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
            return "arrow.right"
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
            return TerentoColors.interactive
        case .pending:
            return TerentoColors.inactiveBorder
        case .failed:
            return TerentoColors.error
        }
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

    private var finishContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Installation complete")
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("Your community map was installed and verified on your Garmin watch.")
                .font(.terentoBody(size: 19, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 14)

            if let result = mapEngine.installationResult {
                MapStatusRow(
                    title: "Freizeitkarte Latvia",
                    detail: "Installed · 2026-05 · \(formatBytes(result.diagnostics.transferTotalBytes))",
                    status: result.isSuccess ? "Verified" : "Not verified",
                    note: result.isSuccess
                        ? "The map was read back from the watch and matched the validated source."
                        : (result.failure?.userLabel ?? "The installation result is unavailable.")
                )
                .padding(.top, 30)
            }

            HStack(spacing: 12) {
                SecondaryButton(title: "Back") {
                    selectedSection = .device
                    selectedInstallationPlan = nil
                    localInstallStep = .choose
                }

                Spacer()
            }
            .padding(.top, 30)
            .padding(.bottom, 42)
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(.horizontal, 58)
        .padding(.top, 58)
    }

    private var mapStateLabel: String {
        if mapEngine.isPreparingArtifact { return "Preparing" }
        if mapEngine.validatedArtifact != nil { return "Ready" }
        return mapEngine.latviaPreflight?.status.userLabel ?? "Checking"
    }

    private var mapStateNote: String {
        if mapEngine.isPreparingArtifact {
            return "The package is being downloaded and validated on this Mac."
        }
        if mapEngine.validatedArtifact != nil {
            return "The source passed provider, region, version, size, and hash checks."
        }
        return mapEngine.latviaPreflight?.userNote ?? "No files are changed."
    }

    private func installationStorageView(_ plan: StoragePlan) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Storage after installation")
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            HStack {
                Text("Current free space")
                Spacer()
                Text(formatBytes(plan.currentFreeSpace))
            }

            HStack {
                Text("Map size")
                Spacer()
                Text(formatBytes(plan.selectedMapBytes))
            }

            HStack {
                Text("Remaining after installation")
                    .fontWeight(.semibold)
                Spacer()
                Text(formatBytes(plan.projectedFreeSpace))
                    .fontWeight(.semibold)
            }

            Text(
                plan.isAllowed
                    ? "Enough space remains after installation."
                    : "There is not enough free space for a safe installation."
            )
            .foregroundStyle(plan.isAllowed ? TerentoColors.lichenDark : TerentoColors.error)
        }
        .font(.terentoUI(size: 14, weight: .medium))
        .foregroundStyle(TerentoColors.secondaryText)
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private func downloadProgressView(_ progress: MapDownloadProgress) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text(acquisitionPhaseLabel)
                    .fontWeight(.semibold)
                Spacer()
                Text("\(Int(progress.fractionCompleted * 100))%")
                    .fontWeight(.semibold)
            }

            ProgressView(value: progress.fractionCompleted)
                .progressViewStyle(.linear)
                .tint(TerentoColors.interactive)

            HStack {
                Text("\(formatBytes(progress.bytesDownloaded)) of \(formatBytes(progress.totalBytes))")
                Spacer()
                Text("\(formatBytesPerSecond(progress.bytesPerSecond)) /s")
            }
            .font(.terentoUI(size: 13, weight: .medium))
            .foregroundStyle(TerentoColors.secondaryText)
        }
        .font(.terentoUI(size: 14, weight: .medium))
        .foregroundStyle(TerentoColors.graphite)
        .padding(18)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private func installationProgressView(_ progress: TransferProgress) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("Uploading map to your Garmin watch")
                    .fontWeight(.semibold)
                Spacer()
                Text("\(Int(progress.fractionCompleted * 100))%")
                    .fontWeight(.semibold)
            }

            ProgressView(value: progress.fractionCompleted)
                .progressViewStyle(.linear)
                .tint(TerentoColors.interactive)

            Text("\(formatBytes(progress.bytesTransferred)) of \(formatBytes(progress.totalBytes))")
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .font(.terentoUI(size: 14, weight: .medium))
        .foregroundStyle(TerentoColors.graphite)
        .padding(18)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private var acquisitionPhaseLabel: String {
        switch mapEngine.acquisitionState {
        case .resolvingPackage:
            return "Preparing download"
        case .downloading:
            return "Downloading map"
        case .validatingDownload:
            return "Validating download"
        case .extracting:
            return "Extracting package"
        case .inspectingIMG:
            return "Reading map image"
        case .validatingIdentity:
            return "Checking map identity"
        case .hashing:
            return "Checking file integrity"
        default:
            return "Preparing map"
        }
    }

    private var identityDisplayName: String {
        if let identity {
            return "\(identity.manufacturer) \(identity.model)"
        }
        return "Connected Garmin watch"
    }

    private func installDetail(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(label)
                .font(.terentoUI(size: 14, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .frame(width: 90, alignment: .leading)

            Text(value)
                .font(.terentoUI(size: 14, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
        }
    }

    @ViewBuilder
    private func installationResultView(_ result: MapInstallationResult) -> some View {
        if result.status == .confirmationRequired {
            Text("Ready for your explicit confirmation. No device write has started.")
                .font(.terentoUI(size: 15, weight: .semibold))
                .foregroundStyle(TerentoColors.lichenDark)
        } else if result.isSuccess {
            MapStatusRow(
                title: "Installation verified",
                detail: "Freizeitkarte Latvia",
                status: "Verified",
                note: "The complete remote file was read back and matched the validated source."
            )
        } else if let failure = result.failure {
            installErrorText(failure.userLabel)
        }
    }

    private func installErrorText(_ message: String) -> some View {
        Text(message)
            .font(.terentoUI(size: 14, weight: .medium))
            .foregroundStyle(TerentoColors.error)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var mapStatusView: some View {
        if let preflight = mapEngine.preflight {
            MapStatusRow(
                title: "\(preflight.selectedMap.name)",
                detail: installedMapDetail(for: preflight),
                status: preflight.status.userLabel,
                note: preflight.userNote
            )
        } else if let comparison = mapEngine.result?.comparisons.first {
            MapStatusRow(
                title: "\(comparison.providerName) \(comparison.regionName)",
                detail: installedMapDetail(for: comparison),
                status: comparison.userStatusLabel,
                note: "Preparing the safe installation check…"
            )
        } else if mapEngine.state == .loadingCatalog {
            MapStatusRow(
                title: "Map catalog",
                detail: "Checking latest metadata…",
                status: "Checking",
                note: "No files are changed."
            )
        } else if mapEngine.state == .scanning {
            MapStatusRow(
                title: "Installed maps",
                detail: "Reading map information…",
                status: "Checking",
                note: "Only existing map metadata is read."
            )
        } else if let message = mapEngine.userErrorMessage {
            MapStatusRow(
                title: "Map information",
                detail: "Could not be read",
                status: "Error",
                note: message
            )
        } else {
            MapStatusRow(
                title: "Map information",
                detail: "Not checked yet",
                status: "Pending",
                note: "Map information will be checked after the device connects."
            )
        }
    }

    private func installedMapDetail(for preflight: InstallationPreflightResult) -> String {
        guard let installedMap = preflight.installedMatch else {
            return preflight.selectedMap.installSizeBytes.map {
                "Not installed · \(formatBytes($0))"
            } ?? "Not installed · Size calculated before installation"
        }

        let version = installedMap.rawVersion
            ?? installedMap.version?.description
            ?? ""
        if version.isEmpty {
            return "Installed"
        }
        return "Installed · \(version)"
    }

    private func installedMapDetail(for comparison: MapComparison) -> String {
        guard let installedMap = comparison.installedMap else {
            return comparison.catalogMap.installSizeBytes.map {
                "Not installed · \(formatBytes($0))"
            } ?? "Not installed · Size calculated before installation"
        }

        let version = installedMap.rawVersion
            ?? installedMap.version?.description
            ?? ""
        if version.isEmpty {
            return "Installed"
        }
        return "Installed · \(version)"
    }

    private func installedMapDetail(for entry: MapInventoryEntry) -> String {
        guard entry.isInstalled else {
            guard let installSize = entry.catalogPackage?.installSizeBytes else {
                return "Not installed · Size calculated before installation"
            }
            return "Not installed · \(formatBytes(installSize))"
        }

        let version = entry.installedRawVersion
            ?? entry.installedVersion?.description
            ?? ""
        var detail = version.isEmpty ? "Installed" : "Installed · \(version)"

        if entry.installedFileCount > 1 {
            detail += " · \(entry.installedFileCount) files · \(formatBytes(entry.installedSizeBytes)) total"
        }

        return detail
    }

    private func freizeitkarteNote(for entry: MapInventoryEntry) -> String {
        if entry.installedFileCount > 1 {
            return "Already on the watch in \(entry.installedFileCount) files. This map is not selected for the current installation and will not be changed."
        }

        return "Already on the watch. This map is not selected for the current installation and will not be changed."
    }

    private func storageFillRatio(for snapshot: DeviceSnapshot) -> Double {
        guard snapshot.totalCapacity > 0 else {
            return 0
        }

        return min(
            1,
            max(0, Double(snapshot.freeSpace) / Double(snapshot.totalCapacity))
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
}

struct TerentoSidebar: View {
    @Binding var selectedSection: TerentoSection
    let connectionState: DeviceConnectionState

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(spacing: 4) {
                ResourceImage(name: "logo", subdirectory: "Brand")
                    .scaledToFit()
                    .frame(width: 40, height: 46)

                Text("Terento")
                    .font(.terentoHeading(size: 18, weight: .semibold))
                    .tracking(-0.25)
                    .foregroundStyle(TerentoColors.sky)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 28)
            .padding(.bottom, 28)

            Divider()
                .overlay(TerentoColors.sidebarBorder)

            VStack(alignment: .leading, spacing: 9) {
                ForEach([TerentoSection.device, TerentoSection.maps]) { section in
                    Button {
                        selectedSection = section
                    } label: {
                        SidebarSectionRow(
                            title: section.rawValue,
                            systemImage: section == .device ? "applewatch" : "map",
                            isSelected: selectedSection == section
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.top, 28)

            Spacer(minLength: 28)

            Button {
                selectedSection = .settings
            } label: {
                SidebarSectionRow(
                    title: "Settings",
                    systemImage: "gearshape",
                    isSelected: selectedSection == .settings
                )
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    connectionIndicator

                    Text(connectionStatusLabel)
                        .font(.terentoUI(size: 12, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.bottom, 22)
            .accessibilityElement(children: .combine)
            .accessibilityLabel(connectionStatusLabel)

            Spacer(minLength: 24)
        }
        .padding(.horizontal, 20)
        .frame(width: 218)
        .background(TerentoColors.sidebar)
    }

    private var connectionStatusLabel: String {
        switch connectionState {
        case .disconnected, .failed, .safeToDisconnect:
            return "Disconnected"
        case .detecting:
            return "Connecting..."
        case .connected, .ready:
            return "Connected"
        case .ejecting:
            return "Disconnecting…"
        }
    }

    @ViewBuilder
    private var connectionIndicator: some View {
        Circle()
            .fill(connectionIndicatorColor)
            .frame(width: 8, height: 8)
    }

    private var connectionIndicatorColor: Color {
        switch connectionState {
        case .connected, .ready:
            return TerentoColors.lichen
        case .detecting, .ejecting:
            return TerentoColors.sky
        case .disconnected, .failed, .safeToDisconnect:
            return TerentoColors.error
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

private struct LocalInstallProgress: View {
    let activeStep: LocalInstallStep

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(LocalInstallStep.allCases.enumerated()), id: \.element.id) { index, step in
                HStack(spacing: 8) {
                    Circle()
                        .fill(stepIndex(step) <= stepIndex(activeStep)
                            ? TerentoColors.lichen
                            : TerentoColors.canvas)
                        .overlay {
                            Circle()
                                .stroke(
                                    stepIndex(step) <= stepIndex(activeStep)
                                        ? TerentoColors.lichen
                                        : TerentoColors.inactiveBorder,
                                    lineWidth: 2
                                )
                        }
                        .frame(width: 18, height: 18)

                    Text(step.rawValue)
                        .font(.terentoUI(size: 13, weight: step == activeStep ? .semibold : .medium))
                        .foregroundStyle(step == activeStep ? TerentoColors.lichenDark : TerentoColors.secondaryText)
                }

                if index < LocalInstallStep.allCases.count - 1 {
                    Rectangle()
                        .fill(index < stepIndex(activeStep)
                            ? TerentoColors.lichen
                            : TerentoColors.progressTrack)
                        .frame(height: 2)
                        .frame(maxWidth: .infinity)
                        .padding(.horizontal, 12)
                }
            }
        }
        .frame(maxWidth: 560)
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 40)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Installation step \(activeStep.rawValue) of 3")
    }

    private func stepIndex(_ step: LocalInstallStep) -> Int {
        LocalInstallStep.allCases.firstIndex(of: step) ?? 0
    }
}

struct WorkflowProgress: View {
    let activeStage: TerentoStage

    var body: some View {
        GeometryReader { proxy in
            let horizontalPadding: CGFloat = 60
            let contentWidth = max(0, proxy.size.width - (horizontalPadding * 2))
            let stepWidth = contentWidth / CGFloat(TerentoStage.allCases.count)

            ZStack(alignment: .topLeading) {
                Canvas { context, size in
                    let centerY: CGFloat = 14.5

                    for index in 0..<(TerentoStage.allCases.count - 1) {
                        let startX = stepWidth * CGFloat(index) + stepWidth / 2
                        let endX = stepWidth * CGFloat(index + 1) + stepWidth / 2
                        var path = Path()
                        path.move(to: CGPoint(x: startX, y: centerY))
                        path.addLine(to: CGPoint(x: endX, y: centerY))
                        context.stroke(
                            path,
                            with: .color(
                                index < activeStageIndex
                                    ? TerentoColors.lichen
                                    : TerentoColors.progressTrack
                            ),
                            lineWidth: 3
                        )
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: 29)
                .padding(.horizontal, horizontalPadding)

                HStack(spacing: 0) {
                    ForEach(Array(TerentoStage.allCases.enumerated()), id: \.element.id) { index, stage in
                        ProgressStep(
                            stage: stage,
                            isActive: stage == activeStage,
                            isComplete: index < activeStageIndex
                        )
                        .frame(width: stepWidth)
                    }
                }
                .padding(.horizontal, horizontalPadding)
            }
        }
        .frame(height: 75)
    }

    private var activeStageIndex: Int {
        TerentoStage.allCases.firstIndex(of: activeStage) ?? 0
    }
}

private struct ProgressStep: View {
    let stage: TerentoStage
    let isActive: Bool
    let isComplete: Bool

    var body: some View {
        VStack(spacing: 12) {
            Circle()
                .fill(isActive || isComplete ? TerentoColors.lichen : TerentoColors.canvas)
                .overlay {
                    Circle()
                        .stroke(
                            isActive || isComplete
                                ? TerentoColors.lichen
                                : TerentoColors.inactiveBorder,
                            lineWidth: 2
                        )
                }
                .overlay {
                    if isActive {
                        Circle()
                            .fill(TerentoColors.canvas)
                            .frame(width: 8, height: 8)
                    }
                }
                .frame(width: 29, height: 29)

            Text(stage.rawValue)
                .font(.terentoUI(size: 14, weight: isActive ? .semibold : .medium))
                .foregroundStyle(isActive ? TerentoColors.lichenDark : TerentoColors.secondaryText)
        }
        .frame(width: 76)
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
    @State private var showingCompatibilityInfo = false

    var body: some View {
        HStack(alignment: .top, spacing: 28) {
            DeviceAssetImage(asset: presentation.asset)
                .frame(width: 178, height: 220)
                .accessibilityLabel("Garmin device image")

            VStack(alignment: .leading, spacing: 10) {
                Text(presentation.deviceName)
                    .font(.terentoHeading(size: 28, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text(presentation.variant)
                    .font(.terentoUI(size: 16, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)

                HStack(spacing: 12) {
                    ReadyStatus()

                    CompatibilityStatusView(status: presentation.compatibility) {
                        showingCompatibilityInfo = true
                    }
                }
                .padding(.top, 4)

                Button(action: onEject) {
                    Label("Eject device", systemImage: "eject")
                        .font(.terentoUI(size: 14, weight: .medium))
                        .foregroundStyle(canEject ? TerentoColors.interactive : TerentoColors.secondaryText)
                }
                .buttonStyle(.plain)
                .disabled(!canEject)

            }

            Spacer(minLength: 16)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .popover(isPresented: $showingCompatibilityInfo, arrowEdge: .top) {
            VStack(alignment: .leading, spacing: 8) {
                Text(presentation.compatibility.userLabel)
                    .font(.terentoUI(size: 15, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)

                Text(CompatibilityPresentation.explanation(for: presentation.compatibility))
                    .font(.terentoUI(size: 13, weight: .regular))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(16)
            .frame(width: 290, alignment: .leading)
        }
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

private struct ReadyStatus: View {
    var body: some View {
        Label("Ready", systemImage: "circle.fill")
            .font(.terentoUI(size: 14, weight: .semibold))
            .foregroundStyle(TerentoColors.lichenDark)
            .accessibilityLabel("Device ready")
    }
}

private struct CompatibilityStatusView: View {
    let status: CompatibilityStatus
    let showInfo: () -> Void

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: statusIcon)
                .font(.system(size: 13, weight: .semibold))

            Text(status.userLabel)
                .font(.terentoUI(size: 13, weight: .medium))

            Button(action: showInfo) {
                Image(systemName: "info.circle")
                    .font(.system(size: 13, weight: .medium))
            }
            .buttonStyle(.plain)
            .help(CompatibilityPresentation.explanation(for: status))
            .accessibilityLabel("What compatibility means")
            .accessibilityHint("Opens an explanation of this device's compatibility status")
        }
        .foregroundStyle(statusColor)
        .accessibilityElement(children: .contain)
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

    var body: some View {
        TerentoMapRow(
            title: item.title,
            detail: operation?.phase == .completed ? "Backup or map action complete" : item.detailLabel,
            note: operation?.message ?? item.noteLabel
        ) {
            Image(systemName: "map")
                .font(.system(size: 21, weight: .medium))
                .foregroundStyle(TerentoColors.lichenDark)
                .frame(width: 30, height: 30)
        } trailing: {
            HStack(spacing: 10) {
                if let operation,
                   operation.phase == .backingUp
                    || operation.phase == .removing
                    || operation.phase == .updating
                    || operation.phase == .verifying {
                    VStack(alignment: .trailing, spacing: 4) {
                        ProgressView(value: operation.progress?.fractionCompleted ?? 0)
                            .frame(width: 112)
                        Text(operation.phase.userLabel)
                            .font(.terentoUI(size: 11, weight: .semibold))
                            .foregroundStyle(TerentoColors.secondaryText)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(operation.message)
                }

                if item.isInstalled {
                Menu {
                        Button("Back up map", action: onBackup)
                            .disabled(!availability.allows(.backup))
                        if availability.allows(.update) {
                            Button("Update map", action: onUpdate)
                        }
                        Button("Remove map", role: .destructive, action: onRemove)
                            .disabled(!availability.allows(.remove))
                        if let reason = availability.reason {
                            Divider()
                            Text(reason)
                        }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .frame(width: 32, height: 32)
                        .contentShape(Rectangle())
                }
                .menuStyle(.borderlessButton)
                .help("Map actions")
                    .disabled(isLifecycleBusy
                        || operation?.phase == .backingUp
                        || operation?.phase == .removing
                        || operation?.phase == .updating
                        || operation?.phase == .verifying)
                    .accessibilityLabel("Map actions for \(item.title)")
                }
            }
        }
    }
}

private struct TerentoMapRow<LeadingContent: View, TrailingContent: View>: View {
    let title: String
    let detail: String?
    let note: String?
    let leadingContent: LeadingContent
    let trailingContent: TrailingContent

    init(
        title: String,
        detail: String?,
        note: String? = nil,
        @ViewBuilder leading: () -> LeadingContent,
        @ViewBuilder trailing: () -> TrailingContent
    ) {
        self.title = title
        self.detail = detail
        self.note = note
        self.leadingContent = leading()
        self.trailingContent = trailing()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
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
        .modifier(MapRowSurface())
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
        VStack(alignment: .leading, spacing: 11) {
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
                        .frame(width: proxy.size.width * fillRatio)
                }
            }
            .frame(height: 7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage: \(available) available of \(total)")
    }
}

struct MapStatusRow: View {
    let title: String
    let detail: String
    let status: String
    let note: String

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

            Text(note)
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
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

    var body: some View {
        TerentoMapRow(title: item.title, detail: detail) {
            HStack(spacing: 10) {
                if isAvailable && item.isSelectable {
                    Toggle("", isOn: $isSelected)
                        .toggleStyle(.checkbox)
                        .labelsHidden()
                } else {
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
            if isAvailable {
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
        .accessibilityValue(isAvailable && item.isSelectable
            ? (isSelected ? "Selected" : "Not selected")
            : detail)
    }

    private var detail: String {
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
        if isAvailable {
            return item.installSizeBytes.map {
                "\(item.title), \(formatBytes($0))"
            } ?? "\(item.title), size calculated before installation"
        }
        return "\(item.title), \(detail)"
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
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 4)
            .padding(.vertical, 13)
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(TerentoColors.border.opacity(0.82))
                    .frame(height: 1)
            }
    }
}

struct MapSelectionStorageSummary: View {
    let plan: InstallationPlan
    let totalCapacity: UInt64
    let formatBytes: (UInt64) -> String

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            Text("Storage")
                .font(.terentoUI(size: 16, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("\(formatBytes(plan.storagePlan.currentFreeSpace)) available of \(formatBytes(totalCapacity))")
                .font(.terentoUI(size: 15, weight: .medium))
                .foregroundStyle(TerentoColors.graphite)

            GeometryReader { proxy in
                let total = max(totalCapacity, 1)
                let available = min(total, plan.storagePlan.currentFreeSpace)

                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(TerentoColors.border)

                    Capsule()
                        .fill(TerentoColors.lichen)
                        .frame(width: proxy.size.width * CGFloat(Double(available) / Double(total)))
                }
            }
            .frame(height: 7)

            storageLine(
                label: "Selected maps",
                value: plan.storagePlan.hasUnresolvedInstallSize
                    ? "Size calculated before installation"
                    : formatBytes(plan.storagePlan.selectedMapBytes)
            )
            storageLine(
                label: "After installation",
                value: plan.storagePlan.hasUnresolvedInstallSize
                    ? "Calculated before installation"
                    : formatBytes(plan.storagePlan.projectedFreeSpace)
            )

            Text(statusText)
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(statusColor)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Storage")
        .accessibilityValue(storageAccessibilityValue)
    }

    private func storageLine(label: String, value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value)
        }
        .font(.terentoUI(size: 13, weight: .medium))
        .foregroundStyle(TerentoColors.secondaryText)
    }

    private var statusText: String {
        if plan.storagePlan.hasUnresolvedInstallSize {
            return "The final install size will be calculated before approval."
        }
        if plan.storagePlan.isAllowed {
            return "Enough space remains after installation."
        }
        return "There is not enough free space for this selection."
    }

    private var statusColor: Color {
        if plan.storagePlan.hasUnresolvedInstallSize {
            return TerentoColors.secondaryText
        }
        return plan.storagePlan.isAllowed ? TerentoColors.lichenDark : TerentoColors.error
    }

    private var storageAccessibilityValue: String {
        let selected = plan.storagePlan.hasUnresolvedInstallSize
            ? "size calculated before installation"
            : formatBytes(plan.storagePlan.selectedMapBytes)
        let remaining = plan.storagePlan.hasUnresolvedInstallSize
            ? "calculated before installation"
            : formatBytes(plan.storagePlan.projectedFreeSpace)
        return "\(formatBytes(plan.storagePlan.currentFreeSpace)) available of \(formatBytes(totalCapacity)), selected maps \(selected), after installation \(remaining)"
    }
}

struct TechnicalDetailsAccordion: View {
    let connectivityEvidence: CompatibilityEvidence?
    let mapResult: MapInventoryResult?
    let catalogLoaded: Bool
    let preflight: InstallationPreflightResult?
    @State private var isExpanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            VStack(alignment: .leading, spacing: 9) {
                TechnicalDetail(label: "USB", value: evidenceValue(connectivityEvidence?.usb))
                TechnicalDetail(label: "MTP", value: evidenceValue(connectivityEvidence?.mtp) + " · read-only")
                TechnicalDetail(label: "Device information", value: evidenceValue(connectivityEvidence?.deviceInfo))
                TechnicalDetail(label: "Storage information", value: evidenceValue(connectivityEvidence?.storage))
                TechnicalDetail(
                    label: "Map inventory",
                    value: mapResult == nil ? "PENDING" : "PASS"
                )
                TechnicalDetail(
                    label: "IMG metadata",
                    value: evidenceValue(mapResult?.scan.imgParsingEvidence)
                )
                TechnicalDetail(
                    label: "Identity matching",
                    value: evidenceValue(mapResult?.comparisonEvidence)
                )
                TechnicalDetail(
                    label: "Catalog",
                    value: catalogLoaded ? "PASS" : "PENDING"
                )
                TechnicalDetail(
                    label: "Version comparison",
                    value: evidenceValue(mapResult?.comparisonEvidence)
                )
                TechnicalDetail(
                    label: "Preflight",
                    value: preflight?.status.rawValue ?? "PENDING"
                )
                TechnicalDetail(
                    label: "Ownership",
                    value: preflight?.ownership.rawValue ?? "PENDING"
                )
                TechnicalDetail(
                    label: "Install target",
                    value: preflight?.installTarget ?? "PENDING"
                )
                TechnicalDetail(
                    label: "Replacement confirmation",
                    value: preflight == nil
                        ? "PENDING"
                        : (preflight?.replacementConfirmationRequired == true ? "REQUIRED" : "NOT REQUIRED")
                )
                TechnicalDetail(label: "Map installation", value: "PENDING")
            }
            .padding(.top, 14)
            .padding(.leading, 4)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "wrench.and.screwdriver")
                    .foregroundStyle(TerentoColors.secondaryText)

                Text("Technical details")
                    .font(.terentoUI(size: 15, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
            }
        }
        .font(.terentoUI(size: 14, weight: .medium))
        .tint(TerentoColors.secondaryText)
        .padding(18)
        .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .stroke(TerentoColors.border.opacity(0.72), lineWidth: 1)
        }
    }

    private func evidenceValue(_ evidence: EvidenceResult?) -> String {
        evidence?.rawValue ?? "PENDING"
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

private struct TechnicalDetail: View {
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .frame(width: 150, alignment: .leading)

            Text(value)
                .foregroundStyle(TerentoColors.lichenDark)
        }
        .font(.system(size: 12, design: .monospaced))
        .foregroundStyle(TerentoColors.secondaryText)
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

private struct StagePlaceholder: View {
    let stage: TerentoStage

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(stage.rawValue)
                .font(.terentoHeading(size: 42, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)

            Text("This step is ready for the next Terento implementation milestone.")
                .font(.terentoBody(size: 18, weight: .regular))
                .foregroundStyle(TerentoColors.secondaryText)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(60)
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
    static let graphite = Color(hex: 0x222A2B)
    static let secondaryText = Color(hex: 0x6D706F)
    static let border = Color(hex: 0xD7DDDA)
    static let sidebarBorder = Color(hex: 0xD7DDDA).opacity(0.72)
    static let selectedBackground = Color(hex: 0xE7EEF1)
    static let inactiveBorder = Color(hex: 0xC7C9C5)
    static let progressTrack = Color(hex: 0xDDE6E5)
    static let interactive = Color(hex: 0x577787)
    static let error = Color(hex: 0x9A4D45)
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

import SwiftUI

struct DiagnosticsView: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var evidenceController: InstallationEvidenceController
    @ObservedObject var mapStatisticsController: MapStatisticsEventController
    @State private var isSending = false
    @State private var actionMessage: String?
    @State private var failureReportMessage: String?
    @Environment(\.openWindow) private var openWindow

    private var pendingCompatibilityCount: Int {
        evidenceController.store.pendingUploads().count
    }

    private var pendingMapStatisticsCount: Int {
        mapStatisticsController.store.pendingEvents().count
    }

    private var pendingCount: Int {
        pendingCompatibilityCount + pendingMapStatisticsCount
    }

    private var pendingSummary: String {
        let noun = pendingCount == 1 ? "diagnostic" : "diagnostics"
        return "\(pendingCount) \(noun) waiting to send"
    }

    var body: some View {
        ZStack {
            TerentoColors.canvas
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Diagnostics")
                            .font(.terentoHeading(size: 30, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)

                        Text("Privacy-minimized diagnostics help improve the Terento app and its services.")
                            .font(.terentoBody(size: 15, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.bottom, 22)

                    #if DEBUG
                    if TerentoTelemetryMetadata.releaseLabel.hasSuffix("-local") {
                        diagnosticsSection(title: "Your Garmin") {
                            if let compatibility = deviceEngine.compatibility {
                                let identity = compatibility.identity
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Text([compatibility.displayName, identity.screenTechnology]
                                        .compactMap { $0 }.joined(separator: ", "))
                                        .font(.terentoUI(size: 14, weight: .semibold))
                                        .foregroundStyle(TerentoColors.graphite)
                                    Label("Connected", systemImage: "checkmark.circle.fill")
                                        .font(.terentoUI(size: 13, weight: .medium))
                                        .foregroundStyle(TerentoColors.lichenDark)
                                }
                                DisclosureGroup("Technical details") {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("Connected device identity")
                                            .font(.terentoUI(size: 13, weight: .semibold))
                                        Text("MTP model: \(identity.model)")
                                        Text("XML model: \(identity.garminModelDescription ?? "Unavailable")")
                                        Text("XML part number: \(identity.garminModelPartNumber ?? "Unavailable")")
                                        Text("XML read status: \(String(describing: identity.garminDeviceXMLStatus))")
                                        Text(String(format: "USB VID/PID: %04x:%04x", identity.usbVendorId, identity.usbProductId))
                                        Text("Screen: \(identity.screenTechnology ?? "Unknown") · Solar: \(identity.solar == true ? "Yes" : "Unknown") · inReach: \(identity.inReach == true ? "Yes" : "Unknown")")
                                        Text("Screen source: \(identity.screenTechnologySource)")
                                        Text("API catalog candidate: \(identity.catalogDeviceID ?? "Not uniquely identified")")
                                        Text("MTP/XML fields above are original device metadata. Additional known properties come from the Terento API catalog. The API independently verifies installation assignments. Opening this window does not send a report.")
                                            .foregroundStyle(TerentoColors.secondaryText)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.top, 6)
                                }
                                .font(.terentoUI(size: 13, weight: .regular))
                                .foregroundStyle(TerentoColors.graphite)
                                .textSelection(.enabled)
                            } else {
                                Text("Connect your device to view its model information.")
                                    .font(.terentoUI(size: 13, weight: .regular))
                            }
                        }
                    }
                    #endif

                    diagnosticsSection(title: "Sharing") {
                        sharingToggle(
                            isOn: compatibilitySharingBinding,
                            title: "Send privacy-minimized compatibility diagnostics",
                            detail: "Device model, firmware and install result. Never your serial number or files."
                        )
                        sharingToggle(
                            isOn: mapStatisticsSharingBinding,
                            title: "Send privacy-minimized map usage diagnostics",
                            detail: "Which maps are installed and removed. Never device identity."
                        )

                        #if TERENTO_APP_STORE
                        // App Store builds share only after an opt-in.
                        Text("Both are off until you turn them on. Turning one off also deletes what is waiting to be sent.")
                            .font(.terentoUI(size: 12, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                        #else
                        Text("Both are on by default. Turning one off also deletes what is waiting to be sent.")
                            .font(.terentoUI(size: 12, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                        #endif

                        DisclosureGroup("What is sent") {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Compatibility diagnostics: device model and variant, firmware, connection details, map and software versions, and the installation result. No Unit ID, serial number, local path, manifest, or map file is included.")
                                Text("Map usage diagnostics: provider, map, region, event type, outcome, operation ID, timestamp, and app build. These events never include device identity or local file information.")
                                Text("Custom IMG installations are sent only as compatibility diagnostics, never as map usage diagnostics.")
                            }
                            .font(.terentoUI(size: 12, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.top, 6)
                        }
                        .font(.terentoUI(size: 13, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                    }

                    diagnosticsSection(title: "Problem with a map?") {
                        Text("If an install, update or removal failed, send us the saved report.")
                            .font(.terentoUI(size: 14, weight: .regular))
                            .foregroundStyle(TerentoColors.graphite)
                            .fixedSize(horizontal: false, vertical: true)

                        #if TERENTO_APP_STORE
                        // App Store builds compile out sending reports to Terento.
                        DiagnosticsActionButton(title: "Report on GitHub (public)", action: reportOnGitHub)
                        Text(Self.gitHubTip)
                            .font(.terentoUI(size: 12, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                        #else
                        DiagnosticsActionButton(title: "Send report to Terento") {
                            openWindow(id: "support-report")
                        }
                        .accessibilityHint("Shows exactly what will be sent before anything is sent.")
                        HStack(alignment: .firstTextBaseline, spacing: 18) {
                            VStack(alignment: .leading, spacing: 2) {
                                Button("Report on GitHub (public)", action: reportOnGitHub)
                                    .buttonStyle(.plain)
                                    .font(.terentoUI(size: 13, weight: .semibold))
                                    .foregroundStyle(TerentoColors.interactive)
                                Text(Self.gitHubTip)
                                    .font(.terentoUI(size: 12, weight: .regular))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            TerentoHelpLink(topic: .sendReport)
                        }
                        #endif

                        if let failureReportMessage {
                            Text(failureReportMessage)
                                .font(.terentoUI(size: 13, weight: .regular))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    // Shown only while something waits, or right after sending.
                    if pendingCount > 0 || actionMessage != nil {
                        diagnosticsSection(title: "Delivery") {
                            if pendingCount > 0 {
                                HStack(alignment: .firstTextBaseline, spacing: 6) {
                                    Text(pendingSummary)
                                        .font(.terentoUI(size: 13, weight: .medium))
                                        .foregroundStyle(TerentoColors.graphite)
                                    Text("·").foregroundStyle(TerentoColors.secondaryText)
                                    Button(isSending ? "Sending…" : "Send now", action: sendDiagnostics)
                                        .buttonStyle(.plain)
                                        .font(.terentoUI(size: 13, weight: .semibold))
                                        .foregroundStyle(TerentoColors.interactive)
                                        .disabled(pendingCount == 0 || isSending)
                                }
                            }

                            if let actionMessage {
                                Text(actionMessage)
                                    .font(.terentoUI(size: 13, weight: .regular))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }

                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(28)
            }
        }
        .frame(minWidth: 520, minHeight: 600)
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
    }

    private static let gitHubTip = "Copies the report and opens GitHub. If the form is empty, click its report field and press ⌘A, then ⌘V."

    private func reportOnGitHub() {
        failureReportMessage = TerentoDiagnosticLog.reportLatestFailure()
            ? "The report is copied. Paste it into the GitHub form and review it before submitting."
            : "No saved report is available, or GitHub could not be opened. If copied, the report is still ready to paste."
    }

    private func sharingToggle(isOn: Binding<Bool>, title: String, detail: String) -> some View {
        Toggle(isOn: isOn) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.terentoUI(size: 14, weight: .semibold))
                Text(detail)
                    .font(.terentoUI(size: 12, weight: .regular))
                    .foregroundStyle(TerentoColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .toggleStyle(.checkbox)
        .tint(TerentoColors.interactive)
    }

    private var compatibilitySharingBinding: Binding<Bool> {
        Binding(
            get: { evidenceController.compatibilitySharingEnabled },
            set: { enabled in
                // Only a real change is a choice. A same-value set must not
                // record "declined" while an App Store build is still undecided.
                guard enabled != evidenceController.compatibilitySharingEnabled else { return }
                actionMessage = nil
                evidenceController.decideConsent(enabled ? .accepted : .declined)
            }
        )
    }

    private var mapStatisticsSharingBinding: Binding<Bool> {
        Binding(
            get: { mapStatisticsController.sharingEnabled },
            set: { enabled in
                guard enabled != mapStatisticsController.sharingEnabled else { return }
                actionMessage = nil
                mapStatisticsController.decideConsent(enabled ? .accepted : .declined)
            }
        )
    }

    private func sendDiagnostics() {
        guard pendingCount > 0, !isSending else { return }
        isSending = true
        actionMessage = nil

        Task { @MainActor in
            await evidenceController.flushPendingUploads()
            await mapStatisticsController.flushPendingEvents()
            isSending = false
            actionMessage = pendingCount == 0
                ? "Diagnostics sent."
                : "Some diagnostics could not be sent yet. Terento will retry automatically."
        }
    }

    @ViewBuilder
    private func diagnosticsSection<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.terentoUI(size: 18, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
            content()
        }
        .padding(.top, 18)
    }

}

private struct DiagnosticsActionButton: View {
    let title: String
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.terentoUI(size: 15, weight: .semibold))
                .foregroundStyle(isEnabled ? .white : TerentoColors.secondaryText)
                .padding(.horizontal, 16)
                .frame(height: 44)
                .background(
                    isEnabled ? TerentoColors.interactive : TerentoColors.border,
                    in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control)
                )
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.78)
    }
}

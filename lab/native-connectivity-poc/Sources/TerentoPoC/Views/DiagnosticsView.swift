import SwiftUI

struct DiagnosticsView: View {
    @ObservedObject var evidenceController: InstallationEvidenceController
    @ObservedObject var mapStatisticsController: MapStatisticsEventController
    @State private var isSending = false
    @State private var actionMessage: String?

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
        return "\(pendingCount) privacy-minimised \(noun) stored locally and waiting to send."
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

                        Text("Privacy-minimised diagnostics help improve the Terento app and its services.")
                            .font(.terentoBody(size: 17, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.bottom, 22)

                    diagnosticsSection(title: "Sharing") {
                        Toggle(isOn: compatibilitySharingBinding) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Send privacy-minimised compatibility diagnostics")
                                    .font(.terentoUI(size: 14, weight: .semibold))
                                Text("Watch model, firmware, connection details, map and software versions, and the installation result. No Unit ID, serial number, local path, manifest, or map file is included.")
                                    .font(.terentoUI(size: 12, weight: .regular))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .toggleStyle(.checkbox)
                        .tint(TerentoColors.interactive)

                        Toggle(isOn: mapStatisticsSharingBinding) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Send privacy-minimised map usage diagnostics")
                                    .font(.terentoUI(size: 14, weight: .semibold))
                                Text("Provider, map, region, event type, outcome, operation ID, timestamp, and app build. These events never include watch identity or local file information.")
                                    .font(.terentoUI(size: 12, weight: .regular))
                                    .foregroundStyle(TerentoColors.secondaryText)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .toggleStyle(.checkbox)
                        .tint(TerentoColors.interactive)

                        Text("Both diagnostics streams are enabled by default. Turning either option off stops future sharing and clears its unsent local queue. Custom IMG installations are sent only as compatibility diagnostics, never as map usage diagnostics.")
                            .font(.terentoUI(size: 12, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 4)
                    }

                    diagnosticsSection(title: "Delivery") {
                        VStack(alignment: .leading, spacing: 8) {
                            diagnosticCountRow(
                                title: "Compatibility diagnostics",
                                count: pendingCompatibilityCount
                            )
                            diagnosticCountRow(
                                title: "Map usage diagnostics",
                                count: pendingMapStatisticsCount
                            )
                        }

                        Text(
                            pendingCount == 0
                                ? "There are no privacy-minimised diagnostics waiting to send."
                                : pendingSummary
                        )
                            .font(.terentoUI(size: 13, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 12)

                        DiagnosticsActionButton(title: isSending ? "Sending diagnostics…" : "Send diagnostics") {
                            sendDiagnostics()
                        }
                        .disabled(pendingCount == 0 || isSending)
                        .padding(.top, 5)

                        if let actionMessage {
                            Text(actionMessage)
                                .font(.terentoUI(size: 13, weight: .regular))
                                .foregroundStyle(TerentoColors.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.top, 8)
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

    private var compatibilitySharingBinding: Binding<Bool> {
        Binding(
            get: { evidenceController.compatibilitySharingEnabled },
            set: { enabled in
                actionMessage = nil
                evidenceController.decideConsent(enabled ? .accepted : .declined)
            }
        )
    }

    private var mapStatisticsSharingBinding: Binding<Bool> {
        Binding(
            get: { mapStatisticsController.sharingEnabled },
            set: { enabled in
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

    private func diagnosticCountRow(title: String, count: Int) -> some View {
        HStack {
            Text(title)
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)
            Spacer()
            Text("\(count)")
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .monospacedDigit()
        }
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
                .padding(.horizontal, 22)
                .frame(height: 46)
                .background(
                    isEnabled ? TerentoColors.interactive : TerentoColors.border,
                    in: RoundedRectangle(cornerRadius: 9)
                )
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.78)
    }
}

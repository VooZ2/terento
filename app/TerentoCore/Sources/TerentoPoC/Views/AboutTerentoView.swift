import AppKit
import SwiftUI

enum TerentoAppMetadata {
    static let version = TerentoTelemetryMetadata.version
    static let build = TerentoTelemetryMetadata.build
    static let releaseLabel: String? = TerentoTelemetryMetadata.releaseLabel.isEmpty
        ? nil
        : TerentoTelemetryMetadata.releaseLabel
    static let displayVersion: String = {
        let label = releaseLabel?.isEmpty == false ? releaseLabel! : version
        return "Version \(label) (\(build))"
    }()
    static let description = "Open-source macOS app for installing and managing third-party maps on compatible Garmin smartwatches."
}

struct AboutTerentoView: View {
    @ObservedObject var appUpdateController: AppUpdateController
    @Environment(\.openWindow) private var openWindow
    // The bundled, reviewed catalog is local and read once for notices.
    private static let mapSources = (try? MapCatalogLoader().loadBundled().sortedProviders) ?? []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 16) {
                    Image(nsImage: NSApplication.shared.applicationIconImage)
                        .resizable()
                        .interpolation(.high)
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 64, height: 64)
                        .accessibilityHidden(true)

                    VStack(alignment: .leading, spacing: 5) {
                        Text("Terento")
                            .font(.terentoHeading(size: 30, weight: .semibold))
                            .foregroundStyle(TerentoColors.graphite)
                        Text("Install maps on Garmin watches, simply.")
                            .font(.terentoUI(size: 15, weight: .medium))
                            .foregroundStyle(TerentoColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(TerentoAppMetadata.displayVersion)
                            .font(.terentoUI(size: 13, weight: .regular))
                            .foregroundStyle(TerentoColors.secondaryText)
                    }
                }

                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 12) {
                        AboutPrimaryButton(title: "Update", action: updateAction)
                            .disabled(appUpdateController.isChecking)
                        AboutSecondaryButton(title: "Manage diagnostics") {
                            openWindow(id: "diagnostics")
                        }
                    }
                    updateStatus
                }

                section(title: "Support") {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 16) { supportLinks }
                        VStack(alignment: .leading, spacing: 10) { supportLinks }
                    }
                }

                DisclosureGroup("Map sources and licenses") {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(Self.mapSources) { provider in
                            VStack(alignment: .leading, spacing: 4) {
                                if let url = provider.licenseURL {
                                    supportLink(provider.name + " ↗", destination: url)
                                } else {
                                    Text(provider.name)
                                }
                                if let attribution = provider.attribution {
                                    Text(attribution).font(.terentoUI(size: 12, weight: .regular))
                                }
                                if let information = provider.licenseInformation {
                                    Text(information).font(.terentoUI(size: 12, weight: .regular))
                                }
                            }
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.secondaryText)

                section(title: "Privacy") {
                    Text("Terento sends privacy-minimised diagnostics by default to help improve the app and its services. Device state, maps, manifests, Unit IDs, serial numbers, and local paths stay on this Mac.")
                        .font(.terentoUI(size: 15, weight: .medium))
                    Text("Terento may contact terento.app when the app starts to check whether a newer version is available. This request is not used for analytics or user tracking.")
                        .font(.terentoUI(size: 13, weight: .regular))
                    HStack(spacing: 18) {
                        supportLink("Privacy ↗", destination: TerentoAppLinks.privacyFromApp)
                        supportLink("Legal ↗", destination: TerentoAppLinks.legalFromApp)
                    }
                    .padding(.top, 5)
                }
                .foregroundStyle(TerentoColors.secondaryText)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: 680, alignment: .leading)
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(minWidth: 520, idealWidth: 560, minHeight: 440, idealHeight: 580)
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
    }

    @ViewBuilder
    private var supportLinks: some View {
        supportLink("GitHub repository ↗", destination: TerentoAppLinks.repository)
        supportLink("Report an issue ↗", destination: TerentoAppLinks.issues)
        supportLink("Website ↗", destination: TerentoAppLinks.websiteFromApp)
        supportLink("Donate ↗", destination: TerentoAppLinks.donate)
    }

    private func section<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.terentoUI(size: 18, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
            content()
        }
    }

    @ViewBuilder
    private var updateStatus: some View {
        switch appUpdateController.state {
        case .idle:
            EmptyView()
        case .checking:
            status("Checking for updates…", icon: "arrow.triangle.2.circlepath")
        case .upToDate:
            status("You're using the latest version.", icon: "checkmark.circle")
        case let .available(update):
            status("Terento \(update.displayVersion) is available. Press Update to download it.", icon: "arrow.down.circle")
        case let .incompatible(update):
            status(
                "Terento \(update.displayVersion) requires macOS "
                    + "\(update.minimumMacOS ?? "a newer version") or later.",
                icon: "info.circle"
            )
        case let .failed(message):
            status(message, icon: "exclamationmark.circle")
        }
    }

    private func status(_ message: String, icon: String) -> some View {
        Label(message, systemImage: icon)
            .font(.terentoUI(size: 13, weight: .regular))
            .foregroundStyle(TerentoColors.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func updateAction() {
        if case let .available(update) = appUpdateController.state {
            _ = appUpdateController.openDownload(for: update)
        } else {
            appUpdateController.checkForUpdates()
        }
    }

    private func supportLink(_ title: String, destination: URL) -> some View {
        Link(title, destination: destination)
            .font(.terentoUI(size: 13, weight: .medium))
            .foregroundStyle(TerentoColors.interactive)
    }
}

private struct AboutSecondaryButton: View {
    let title: String
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.terentoUI(size: 15, weight: .semibold))
                .foregroundStyle(isEnabled ? TerentoColors.graphite : TerentoColors.secondaryText)
                .padding(.horizontal, 18)
                .frame(height: 46)
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

private struct AboutPrimaryButton: View {
    let title: String
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.terentoUI(size: 15, weight: .semibold))
                .foregroundStyle(isEnabled ? .white : TerentoColors.secondaryText)
                .padding(.horizontal, 20)
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

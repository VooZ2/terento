import AppKit
import SwiftUI

enum TerentoAppMetadata {
    static let version = (Bundle.main.object(
        forInfoDictionaryKey: "CFBundleShortVersionString"
    ) as? String) ?? "1.0.0"
    static let build = (Bundle.main.object(
        forInfoDictionaryKey: "CFBundleVersion"
    ) as? String) ?? "1"
    static let releaseLabel = (Bundle.main.object(
        forInfoDictionaryKey: "TerentoReleaseLabel"
    ) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    static let displayVersion: String = {
        let label = releaseLabel?.isEmpty == false ? releaseLabel! : version
        return "Version \(label) (\(build))"
    }()
    static let description = "Open-source macOS app for installing and managing third-party maps on compatible Garmin smartwatches."
}

struct AboutTerentoView: View {
    @ObservedObject var appUpdateController: AppUpdateController
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        ZStack {
            TerentoColors.canvas
                .ignoresSafeArea()

            VStack(spacing: 14) {
                Image(nsImage: NSApplication.shared.applicationIconImage)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 84, height: 84)

                VStack(spacing: 5) {
                    Text("Terento")
                        .font(.terentoHeading(size: 24, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)

                    Text("Install maps on Garmin watches, simply.")
                        .font(.terentoUI(size: 15, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(TerentoAppMetadata.displayVersion)
                        .font(.terentoUI(size: 13, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

                HStack(spacing: 16) {
                    AboutPrimaryButton(title: "Update") {
                        updateAction()
                    }
                    .disabled(appUpdateController.isChecking)

                    AboutSecondaryButton(title: "Manage diagnostics") {
                        openWindow(id: "diagnostics")
                    }
                }

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 14) {
                        supportLink("Website", destination: TerentoAppLinks.websiteFromApp)
                        supportLink("GitHub", destination: TerentoAppLinks.repository)
                        supportLink("Report an issue", destination: TerentoAppLinks.issues)
                        supportLink("Donate", destination: TerentoAppLinks.donate)
                    }

                    VStack(spacing: 7) {
                        supportLink("Website", destination: TerentoAppLinks.websiteFromApp)
                        supportLink("GitHub", destination: TerentoAppLinks.repository)
                        supportLink("Report an issue", destination: TerentoAppLinks.issues)
                        supportLink("Donate", destination: TerentoAppLinks.donate)
                    }
                }
            }
        }
        .padding(28)
        .frame(width: 420)
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
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

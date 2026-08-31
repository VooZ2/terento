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

                VStack(spacing: 4) {
                    Text("Terento")
                        .font(.terentoHeading(size: 24, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                    Text(TerentoAppMetadata.displayVersion)
                        .font(.terentoUI(size: 13, weight: .regular))
                        .foregroundStyle(TerentoColors.secondaryText)
                }

                Text(TerentoAppMetadata.description)
                    .font(.terentoUI(size: 13, weight: .regular))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(TerentoColors.secondaryText)
                    .frame(width: 300)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 16) {
                    Link("Website", destination: TerentoAppLinks.website)
                    Link("GitHub", destination: TerentoAppLinks.repository)
                    Link("Report an issue", destination: TerentoAppLinks.issues)
                }
                .font(.terentoUI(size: 13, weight: .medium))
                .foregroundStyle(TerentoColors.interactive)
                .tint(TerentoColors.interactive)
            }
        }
        .padding(28)
        .frame(width: 360)
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
    }
}

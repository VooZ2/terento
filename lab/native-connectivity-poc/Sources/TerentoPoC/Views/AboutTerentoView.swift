import AppKit
import SwiftUI

enum TerentoAppMetadata {
    static let version = (Bundle.main.object(
        forInfoDictionaryKey: "CFBundleShortVersionString"
    ) as? String) ?? "1.0.0"
    static let build = (Bundle.main.object(
        forInfoDictionaryKey: "CFBundleVersion"
    ) as? String) ?? "1"
    static let description = "Open-source macOS app for installing and managing Freizeitkarte maps on Garmin devices."
}

struct AboutTerentoView: View {
    var body: some View {
        VStack(spacing: 14) {
            Image(nsImage: NSApplication.shared.applicationIconImage)
                .resizable()
                .interpolation(.high)
                .aspectRatio(contentMode: .fit)
                .frame(width: 84, height: 84)

            VStack(spacing: 4) {
                Text("Terento")
                    .font(.system(size: 24, weight: .semibold))
                Text("Version \(TerentoAppMetadata.version)")
                    .foregroundStyle(.secondary)
            }

            Text(TerentoAppMetadata.description)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .frame(maxWidth: 300)

            HStack(spacing: 16) {
                Link("Website", destination: TerentoAppLinks.website)
                Link("GitHub", destination: TerentoAppLinks.repository)
                Link("Report an issue", destination: TerentoAppLinks.issues)
            }
            .font(.callout)
        }
        .padding(28)
        .frame(width: 360)
    }
}

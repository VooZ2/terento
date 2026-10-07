import SwiftUI

/// A "Help" text link to the matching troubleshooting guide section. It is a
/// plain Interactive Primary text link, never a second primary button. It
/// appears inside error dialogs, in the Diagnostics send-report help and on
/// the Connect page for a connection error, never in normal or in-progress
/// states.
struct TerentoHelpLink: View {
    let topic: TroubleshootingTopic
    var size: CGFloat = 13

    var body: some View {
        Link(destination: topic.url) {
            Label("Help", systemImage: "questionmark.circle")
                .labelStyle(.titleAndIcon)
        }
        .buttonStyle(.plain)
        .font(.terentoUI(size: size, weight: .semibold))
        .foregroundStyle(TerentoColors.interactive)
        .help("Open the Terento troubleshooting guide")
        .accessibilityLabel("Help")
        .accessibilityHint("Opens the Terento troubleshooting guide in your browser.")
    }
}

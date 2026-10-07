import SwiftUI

/// A "Help" text link to the matching troubleshooting guide section. It is a
/// plain Interactive Primary text link, never a second primary button. It
/// appears inside error dialogs, in the Diagnostics send-report help and in
/// the Connect page's help box about a problem, never in normal or
/// in-progress states.
struct TerentoHelpLink: View {
    let topic: TroubleshootingTopic
    var title = "Help"
    var size: CGFloat = 13
    /// Aligns the icon to a list's icon column (fixed width, 10 pt spacing),
    /// as in the Connect help box; `nil` keeps the compact label.
    var iconColumnWidth: CGFloat? = nil

    var body: some View {
        Link(destination: topic.url) {
            Label(title, systemImage: "questionmark.circle")
                .labelStyle(HelpLinkLabelStyle(iconColumnWidth: iconColumnWidth))
        }
        .buttonStyle(.plain)
        .font(.terentoUI(size: size, weight: .semibold))
        .foregroundStyle(TerentoColors.interactive)
        .help("Open the Terento troubleshooting guide")
        .accessibilityLabel(title)
        .accessibilityHint("Opens the Terento troubleshooting guide in your browser.")
    }
}

private struct HelpLinkLabelStyle: LabelStyle {
    let iconColumnWidth: CGFloat?

    @ViewBuilder
    func makeBody(configuration: Configuration) -> some View {
        if let iconColumnWidth {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                configuration.icon
                    .font(.system(size: 14, weight: .regular))
                    .frame(width: iconColumnWidth)
                configuration.title
            }
        } else {
            TitleAndIconLabelStyle().makeBody(configuration: configuration)
        }
    }
}

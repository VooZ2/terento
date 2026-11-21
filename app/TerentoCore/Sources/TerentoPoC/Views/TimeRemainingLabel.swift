import SwiftUI

/// "About N min left" for a measured phase. The text counts down between
/// measured samples and disappears when progress stalls; it is never shown
/// for a phase without measured progress.
struct TimeRemainingLabel: View {
    let estimate: RemainingTimeEstimate
    var role: TerentoTypography.Role = .caption

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            if let text = estimate.text(at: context.date) {
                Label(text, systemImage: "clock")
                    .labelStyle(.titleAndIcon)
                    .font(.terento(role))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
        }
    }
}

import SwiftUI

/// "About N min left" for a measured phase. The text counts down between
/// measured samples and disappears when progress stalls; it is never shown
/// for a phase without measured progress.
struct TimeRemainingLabel: View {
    let estimate: RemainingTimeEstimate
    var size: CGFloat = 11

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            if let text = estimate.text(at: context.date) {
                Label(text, systemImage: "clock")
                    .labelStyle(.titleAndIcon)
                    .font(.terentoUI(size: size, weight: .medium))
                    .foregroundStyle(TerentoColors.secondaryText)
            }
        }
    }
}

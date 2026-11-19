import AppKit
import SwiftUI

/// Review-and-send sheet for "Send report to Terento". It shows exactly the
/// JSON that Send uploads; nothing is sent until the user presses Send.
struct SupportReportSheet: View {
    @StateObject private var controller: SupportReportController
    /// What failed and when, in plain words, above the JSON.
    let summary: String?
    /// The Send report window aligns with About and Diagnostics (28).
    let padding: CGFloat
    let onClose: () -> Void

    init(controller: @autoclosure @escaping () -> SupportReportController, summary: String? = nil,
         padding: CGFloat = TerentoDialogMetrics.padding, onClose: @escaping () -> Void) {
        _controller = StateObject(wrappedValue: controller())
        self.summary = summary
        self.padding = padding
        self.onClose = onClose
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // The wide variant of the shared dialog standard.
            TerentoDialogHeader(icon: "paperplane", role: .info, title: "Send report to Terento")
            Text("No GitHub account needed. Terento receives exactly what is shown below, only when you press Send.")
                .font(.terentoUI(size: TerentoDialogMetrics.bodySize, weight: .regular))
                .foregroundStyle(TerentoColors.graphite)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 12)

            if controller.allowsCategoryChoice {
                Picker("What is this about?", selection: $controller.category) {
                    Text("Connecting the device").tag(SupportReportCategory.connection)
                    Text("Something else").tag(SupportReportCategory.other)
                }
                .pickerStyle(.menu)
                .font(.terentoUI(size: 13, weight: .medium))
                .frame(maxWidth: 320)
                .padding(.top, 16)
                .disabled(!controller.canSend)
            }

            Text("Description (optional)")
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .padding(.top, 16)
            TextEditor(text: $controller.userMessage)
                .font(.terentoUI(size: 13, weight: .regular))
                .frame(height: 70)
                .overlay { RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control).stroke(TerentoColors.border, lineWidth: 1) }
                .disabled(!controller.canSend)
                .accessibilityLabel("Description, optional")
                .accessibilityHint("Don't include personal information.")
                .padding(.top, 6)
            HStack {
                Text("Don't include personal information.")
                Spacer()
                Text("\(controller.userMessage.unicodeScalars.count)/\(SupportReportController.maximumDescriptionLength)")
                    .monospacedDigit()
            }
            // Help-text level shared with About and Diagnostics: 12, secondary.
            .font(.terentoUI(size: 12, weight: .regular))
            .foregroundStyle(TerentoColors.secondaryText)
            .padding(.top, 4)

            Text("What will be sent")
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .padding(.top, 14)
            if let summary {
                Text(summary)
                    .font(.terentoUI(size: 13, weight: .regular))
                    .foregroundStyle(TerentoColors.graphite)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 6)
            }
            ScrollView {
                Text(controller.payload.previewText)
                    .font(Self.diagnosticFont)
                    .foregroundStyle(TerentoColors.graphite)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
            .frame(height: 200)
            .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control))
            .overlay { RoundedRectangle(cornerRadius: TerentoGeneratedTokens.Radius.control).stroke(TerentoColors.border, lineWidth: 1) }
            .accessibilityLabel("Report content that will be sent")
            .padding(.top, 6)

            statusView
                .padding(.top, 12)

            HStack(spacing: TerentoDialogMetrics.buttonGap) {
                Spacer(minLength: 0)
                if case .sent = controller.state {
                    TerentoDialogButton("Done", kind: .primary, action: onClose)
                        .keyboardShortcut(.defaultAction)
                } else {
                    TerentoDialogButton("Cancel", action: onClose)
                        .keyboardShortcut(.cancelAction)
                        .disabled(controller.state == .sending)
                    TerentoDialogButton(controller.isFailed ? "Try again" : "Send", kind: .primary) {
                        Task { await controller.send() }
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!controller.canSend)
                }
            }
            .padding(.top, 14)
        }
        .padding(padding)
        .frame(width: TerentoDialogMetrics.wideWidth)
        .background(TerentoColors.canvas)
        .preferredColorScheme(.light)
    }

    @ViewBuilder
    private var statusView: some View {
        switch controller.state {
        case .editing:
            EmptyView()
        case .sending:
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Sending…")
            }
            .font(.terentoUI(size: 13, weight: .medium))
            .foregroundStyle(TerentoColors.secondaryText)
        case .sent(let reference):
            Label("Report \(reference) sent", systemImage: "checkmark.circle.fill")
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(TerentoColors.lichenDark)
                .textSelection(.enabled)
        case .failed(let message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(TerentoColors.error)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// JetBrains Mono for the technical preview, as the brand reserves it for
    /// diagnostics; the system monospaced face when it is not installed.
    private static var diagnosticFont: Font {
        NSFont(name: TerentoGeneratedTokens.Typography.monoFontName, size: 11) == nil
            ? .system(size: 11, design: .monospaced)
            : .custom(TerentoGeneratedTokens.Typography.monoFontName, size: 11)
    }

}

/// Builds the report for the Diagnostics window and Help menu: the latest
/// saved failure with its structured fields, or a minimal report the user
/// describes.
enum SupportReportSource {
    @MainActor
    static func latest(outbox: SupportReportOutbox = SupportReportOutbox())
        -> (payload: SupportReportPayload, allowsCategoryChoice: Bool, summary: String?) {
        let saved = TerentoDiagnosticLog.latestSavedSupportReport()
        // An unsent report is offered again first; its id is unchanged, so a
        // report that did arrive is not stored twice.
        if let unsent = outbox.load() {
            let matches = unsent.report == saved?.report && unsent.category == saved?.category
            return (unsent, false, matches ? saved?.summaryLine : nil)
        }
        if let saved {
            return (SupportReportPayload(category: saved.category, operationID: saved.operationID,
                                         userMessage: nil, report: saved.report), false, saved.summaryLine)
        }
        return (SupportReportPayload(category: .other, operationID: nil, userMessage: nil,
                                     report: .minimal()), true, SavedSupportReport.noSavedReportLine)
    }
}

/// Window content for the Help menu and Diagnostics entry points.
struct SupportReportWindow: View {
    @Environment(\.dismiss) private var dismiss
    @State private var session = UUID()

    var body: some View {
        let source = SupportReportSource.latest()
        SupportReportSheet(controller: SupportReportController(payload: source.payload,
                                                               allowsCategoryChoice: source.allowsCategoryChoice),
                           summary: source.summary,
                           padding: 28,
                           onClose: { dismiss() })
            .id(session)
            .onAppear { session = UUID() }
    }
}

// Shared dialog standard. It lives here, outside ConnectScreen.swift, because
// test harnesses that compile the app without ConnectScreen also build this sheet.
/// One dialog standard for every custom sheet. Sizes live here so a dialog
/// cannot drift from the others; `SupportReportSheet` is the wide variant.
enum TerentoDialogMetrics {
    static let iconSize: CGFloat = 20
    static let iconCircle: CGFloat = 36
    static let iconTintOpacity: Double = 0.12
    static let iconTitleGap: CGFloat = 12
    static let titleSize: CGFloat = 20
    static let bodySize: CGFloat = 14
    static let supportingSize: CGFloat = 13
    static let padding: CGFloat = 24
    static let width: CGFloat = 440
    static let wideWidth: CGFloat = 560
    static let buttonHeight: CGFloat = 40
    static let buttonGap: CGFloat = 8
    static let sheetRadius: CGFloat = TerentoGeneratedTokens.Radius.large
    static let buttonRadius: CGFloat = TerentoGeneratedTokens.Radius.control
}

/// The icon colour follows what the dialog is about, never the screen it is on.
enum TerentoDialogRole {
    case error, warning, success, info

    var color: Color {
        switch self {
        case .error: return TerentoColors.error
        case .warning: return TerentoColors.warning
        case .success: return TerentoColors.lichenDark
        case .info: return TerentoColors.interactive
        }
    }
}

struct TerentoDialogHeader: View {
    let icon: String
    var iconIsAsset = false
    let role: TerentoDialogRole
    let title: String
    var subtitle: String = ""

    var body: some View {
        HStack(alignment: .center, spacing: TerentoDialogMetrics.iconTitleGap) {
            ZStack {
                Circle().fill(role.color.opacity(TerentoDialogMetrics.iconTintOpacity))
                iconImage
                    .foregroundStyle(role.color)
            }
            .frame(width: TerentoDialogMetrics.iconCircle, height: TerentoDialogMetrics.iconCircle)
            .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.terentoHeading(size: TerentoDialogMetrics.titleSize, weight: .semibold))
                    .foregroundStyle(TerentoColors.graphite)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.terentoUI(size: TerentoDialogMetrics.supportingSize, weight: .semibold))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .lineLimit(2)
                        .truncationMode(.middle)
                }
            }
        }
    }

    @ViewBuilder private var iconImage: some View {
        if iconIsAsset {
            Image(icon)
                .renderingMode(.template)
                .resizable()
                .scaledToFit()
                .frame(width: TerentoDialogMetrics.iconSize, height: TerentoDialogMetrics.iconSize)
        } else {
            Image(systemName: icon)
                .font(.system(size: TerentoDialogMetrics.iconSize - 2, weight: .semibold))
                .frame(width: TerentoDialogMetrics.iconSize, height: TerentoDialogMetrics.iconSize)
        }
    }
}

/// The only dialog button. Primary is Interactive Primary, destructive is the
/// error colour, secondary is outlined.
struct TerentoDialogButton: View {
    enum Kind { case primary, secondary, destructive }

    let label: String
    var kind: Kind = .secondary
    var assetIcon: String? = nil
    let action: () -> Void

    init(_ label: String, kind: Kind = .secondary, assetIcon: String? = nil, action: @escaping () -> Void) {
        self.label = label
        self.kind = kind
        self.assetIcon = assetIcon
        self.action = action
    }

    var body: some View {
        Button(role: kind == .destructive ? .destructive : nil, action: action) {
            HStack(spacing: 7) {
                if let assetIcon {
                    Image(assetIcon)
                        .renderingMode(.template)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 15, height: 15)
                        .accessibilityHidden(true)
                }
                Text(label)
                    .font(.terentoUI(size: TerentoDialogMetrics.bodySize, weight: .semibold))
            }
            .foregroundStyle(kind == .secondary ? TerentoColors.graphite : .white)
            .padding(.horizontal, 16)
            .frame(minHeight: TerentoDialogMetrics.buttonHeight)
            .background(background, in: RoundedRectangle(cornerRadius: TerentoDialogMetrics.buttonRadius, style: .continuous))
            .overlay {
                if kind == .secondary {
                    RoundedRectangle(cornerRadius: TerentoDialogMetrics.buttonRadius, style: .continuous)
                        .strokeBorder(TerentoColors.border, lineWidth: 1)
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: TerentoDialogMetrics.buttonRadius, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }

    private var background: Color {
        switch kind {
        case .primary: return TerentoColors.interactive
        case .destructive: return TerentoColors.error
        case .secondary: return TerentoColors.canvas
        }
    }
}

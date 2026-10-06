import AppKit
import SwiftUI

/// Review-and-send sheet for "Send report to Terento". It shows exactly the
/// JSON that Send uploads; nothing is sent until the user presses Send.
struct SupportReportSheet: View {
    @StateObject private var controller: SupportReportController
    let onClose: () -> Void

    init(controller: @autoclosure @escaping () -> SupportReportController, onClose: @escaping () -> Void) {
        _controller = StateObject(wrappedValue: controller())
        self.onClose = onClose
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "paperplane")
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(TerentoColors.interactive)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 5) {
                    Text("Send report to Terento")
                        .font(.terentoHeading(size: 24, weight: .semibold))
                        .foregroundStyle(TerentoColors.graphite)
                        .accessibilityAddTraits(.isHeader)
                    Text("No GitHub account needed. Terento receives exactly what is shown below, only when you press Send.")
                        .font(.terentoUI(size: 13, weight: .medium))
                        .foregroundStyle(TerentoColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if controller.allowsCategoryChoice {
                Picker("What is this about?", selection: $controller.category) {
                    Text("Connecting the watch").tag(SupportReportCategory.connection)
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
                .overlay { RoundedRectangle(cornerRadius: 6).stroke(TerentoColors.border, lineWidth: 1) }
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
            .font(.terentoUI(size: 11, weight: .medium))
            .foregroundStyle(TerentoColors.secondaryText)
            .padding(.top, 4)

            Text("What will be sent")
                .font(.terentoUI(size: 13, weight: .semibold))
                .foregroundStyle(TerentoColors.graphite)
                .padding(.top, 14)
            ScrollView {
                Text(controller.payload.previewText)
                    .font(Self.diagnosticFont)
                    .foregroundStyle(TerentoColors.graphite)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
            .frame(height: 200)
            .background(TerentoColors.surface, in: RoundedRectangle(cornerRadius: 8))
            .overlay { RoundedRectangle(cornerRadius: 8).stroke(TerentoColors.border, lineWidth: 1) }
            .accessibilityLabel("Report content that will be sent")
            .padding(.top, 6)

            statusView
                .padding(.top, 12)

            HStack(spacing: 10) {
                Spacer(minLength: 0)
                if case .sent = controller.state {
                    sheetButton("Done", primary: true, action: onClose)
                        .keyboardShortcut(.defaultAction)
                } else {
                    sheetButton("Cancel", primary: false, action: onClose)
                        .keyboardShortcut(.cancelAction)
                        .disabled(controller.state == .sending)
                    sheetButton(controller.isFailed ? "Try again" : "Send", primary: true) {
                        Task { await controller.send() }
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!controller.canSend)
                }
            }
            .padding(.top, 14)
        }
        .padding(24)
        .frame(width: 560)
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
                .font(.terentoUI(size: 14, weight: .semibold))
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

    private func sheetButton(_ title: String, primary: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.terentoUI(size: 14, weight: .semibold))
                .foregroundStyle(primary ? .white : TerentoColors.graphite)
                .padding(.horizontal, 16)
                .frame(minHeight: 38)
                .background(primary ? TerentoColors.interactive : TerentoColors.canvas,
                            in: RoundedRectangle(cornerRadius: 8))
                .overlay {
                    if !primary { RoundedRectangle(cornerRadius: 8).stroke(TerentoColors.border, lineWidth: 1) }
                }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
    }
}

/// Builds the report for the Diagnostics window and Help menu: the latest
/// saved failure with its structured fields, or a minimal report the user
/// describes.
enum SupportReportSource {
    @MainActor
    static func latest(outbox: SupportReportOutbox = SupportReportOutbox())
        -> (payload: SupportReportPayload, allowsCategoryChoice: Bool) {
        // An unsent report is offered again first; its id is unchanged, so a
        // report that did arrive is not stored twice.
        if let unsent = outbox.load() {
            return (unsent, false)
        }
        if let saved = TerentoDiagnosticLog.latestSavedSupportReport() {
            return (SupportReportPayload(category: saved.category, operationID: saved.operationID,
                                         userMessage: nil, report: saved.report), false)
        }
        return (SupportReportPayload(category: .other, operationID: nil, userMessage: nil,
                                     report: .minimal()), true)
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
                           onClose: { dismiss() })
            .id(session)
            .onAppear { session = UUID() }
    }
}

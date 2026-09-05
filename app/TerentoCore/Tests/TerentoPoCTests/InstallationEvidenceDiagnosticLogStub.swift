import Foundation

/// The focused evidence harness does not compile the full AppKit diagnostics
/// surface. The production target provides the real logger with the same API.
@MainActor
enum TerentoDiagnosticLog {
    static func recordCompatibilityReportDeliveryFailure(
        reportIDs: [UUID],
        error: Error,
        willRetry: Bool,
        pendingCount: Int
    ) {}
}

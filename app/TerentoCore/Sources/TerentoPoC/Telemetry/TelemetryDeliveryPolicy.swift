import Foundation

/// The last non-retryable server rejection of one queued telemetry event.
/// It is local delivery bookkeeping only and is never part of a payload.
struct TelemetryRejection: Codable, Equatable, Sendable {
    let statusCode: Int
    let rejectionCount: Int
    let lastRejectedAt: Date
    /// The `appBuild` of the app that observed the rejection. A different
    /// running build may have a corrected encoder or a newer server contract.
    let rejectedAppBuild: String
}

/// Shared parking rules for every durable telemetry queue (map usage,
/// compatibility/update diagnostics and the first-run funnel).
///
/// A non-retryable rejection (HTTP 4xx except 408/425/429) parks only that
/// event. Independent later events continue. A parked event is retried only
/// after a new app build or after a 24-hour back-off, at most
/// `maximumRejectionsPerBuild` times by one build and `maximumRejections` times
/// overall. It expires with the existing 24-month telemetry retention window.
/// Retryable failures (network, 408/425/429, 5xx) never park and never drop an
/// event; they keep queue order and use the existing bounded retry schedule.
enum TelemetryDeliveryPolicy {
    static let parkedRetryInterval: TimeInterval = 24 * 60 * 60
    static let maximumRejectionsPerBuild = 3
    static let maximumRejections = 10
    /// Matches the server's 24-month diagnostic and map-event retention.
    static let retentionInterval: TimeInterval = 730 * 24 * 60 * 60
    /// Bounds local storage if an incompatible server rejects every event.
    static let maximumParkedEvents = 500

    static func isNonRetryableRejection(statusCode: Int) -> Bool {
        (400..<500).contains(statusCode) && ![408, 425, 429].contains(statusCode)
    }

    static func rejection(
        after previous: TelemetryRejection?,
        statusCode: Int,
        now: Date,
        appBuild: String
    ) -> TelemetryRejection {
        TelemetryRejection(
            statusCode: statusCode,
            rejectionCount: (previous?.rejectionCount ?? 0) + 1,
            lastRejectedAt: now,
            rejectedAppBuild: appBuild
        )
    }

    /// Whether a parked event may be offered to the server again.
    static func isEligibleForRetry(
        _ rejection: TelemetryRejection,
        now: Date,
        appBuild: String
    ) -> Bool {
        guard rejection.rejectionCount < maximumRejections else { return false }
        if rejection.rejectedAppBuild != appBuild { return true }
        return rejection.rejectionCount < maximumRejectionsPerBuild
            && now.timeIntervalSince(rejection.lastRejectedAt) >= parkedRetryInterval
    }

    /// Parked events are dropped after the retention window or after the
    /// overall rejection limit. Retryable pending events are never expired here.
    static func isExpired(
        _ rejection: TelemetryRejection,
        occurredAt: Date,
        now: Date
    ) -> Bool {
        rejection.rejectionCount >= maximumRejections
            || now.timeIntervalSince(occurredAt) > retentionInterval
    }
}

import Foundation

/// Time left for one measured phase (download, device write, verification
/// read-back, Update/Remove content check). It is derived only from measured
/// progress: nothing is shown before a short warm-up, the rate is smoothed,
/// and the estimate disappears when progress stalls or is not measurable.
/// No timer ever advances it.
struct RemainingTimeEstimate: Equatable, Sendable {
    let seconds: TimeInterval
    let measuredAt: Date

    /// The estimate at `now`, or `nil` once no progress has been measured for
    /// `RemainingTimeEstimator.stallInterval`.
    func remaining(at now: Date) -> TimeInterval? {
        let age = now.timeIntervalSince(measuredAt)
        guard age >= 0, age <= RemainingTimeEstimator.stallInterval else { return nil }
        return max(0, seconds - age)
    }

    func text(at now: Date) -> String? {
        remaining(at: now).flatMap(RemainingTimeEstimate.text(seconds:))
    }

    /// "About N min left"; under a minute reads "Less than a minute left".
    static func text(seconds: TimeInterval) -> String? {
        guard seconds.isFinite, seconds >= 0, seconds <= RemainingTimeEstimator.maximumSeconds else { return nil }
        if seconds < 60 { return "Less than a minute left" }
        let minutes = Int((seconds / 60).rounded(.up))
        if minutes < 120 { return "About \(minutes) min left" }
        return "About \(Int((Double(minutes) / 60).rounded())) h left"
    }
}

struct RemainingTimeEstimator: Sendable {
    /// No estimate during the first seconds of a phase.
    static let warmUpInterval: TimeInterval = 5
    /// At least this share of the phase must be measured first.
    static let minimumFraction = 0.02
    /// An estimate older than this is hidden: progress has stalled.
    static let stallInterval: TimeInterval = 15
    /// Exponential smoothing of the measured rate.
    static let smoothing = 0.2
    /// Longer than a day is not a useful estimate.
    static let maximumSeconds: TimeInterval = 24 * 60 * 60

    private var startedAt: Date?
    private var lastSample: (completed: Double, at: Date)?
    private var smoothedRate: Double?
    private var total: Double = 0

    mutating func reset() {
        startedAt = nil
        lastSample = nil
        smoothedRate = nil
        total = 0
    }

    /// Feeds one measured sample. `completed` and `total` share one unit
    /// (bytes or a measured fraction). Returns `nil` while the estimate is
    /// not yet trustworthy or the progress is not measurable.
    mutating func update(completed: Double, total: Double, at now: Date = Date()) -> RemainingTimeEstimate? {
        guard completed.isFinite, total.isFinite, total > 0, completed >= 0 else {
            reset()
            return nil
        }
        if total != self.total || (lastSample.map { completed < $0.completed } ?? false) {
            // A new transfer or a restarted one: measure again from here.
            reset()
            self.total = total
        }
        guard let startedAt, let previous = lastSample else {
            self.startedAt = now
            lastSample = (completed, now)
            return nil
        }
        let elapsed = now.timeIntervalSince(previous.at)
        if completed > previous.completed, elapsed > 0 {
            let rate = (completed - previous.completed) / elapsed
            smoothedRate = smoothedRate.map { $0 + Self.smoothing * (rate - $0) } ?? rate
            lastSample = (completed, now)
        } else if completed == previous.completed {
            // No advance: keep the last measured sample and its time so a
            // stall eventually hides the estimate.
        }
        guard now.timeIntervalSince(startedAt) >= Self.warmUpInterval,
              completed / total >= Self.minimumFraction,
              completed < total,
              let rate = smoothedRate, rate > 0,
              let measured = lastSample else {
            return nil
        }
        let seconds = (total - completed) / rate
        guard seconds.isFinite, seconds <= Self.maximumSeconds else { return nil }
        return RemainingTimeEstimate(seconds: seconds, measuredAt: measured.at)
    }
}

/// Which lifecycle progress is measured, and in which unit. Stage weights and
/// checkpoint jumps are never estimated.
enum LifecycleRemainingTimeUnits {
    static func units(action: MapLifecycleAction, phase: MapLifecycleOperationPhase,
                      progress: SafeUpdateProgress?) -> (completed: Double, total: Double)? {
        guard let progress else { return nil }
        switch phase {
        case .downloading, .installing:
            guard progress.phaseFraction == nil, progress.totalBytes > 0 else { return nil }
            return (Double(progress.bytesCompleted), Double(progress.totalBytes))
        case .checking:
            // Content check of the installed map (recorded sampled regions, or
            // the full read and hash without a proof): 25–95 % of Checking.
            // A short sampled check ends inside the warm-up, so no estimate.
            return band(progress.phaseFraction, lower: 0.25, upper: 0.95)
        case .verifying:
            if progress.phaseFraction == nil, progress.totalBytes > 0 {
                // Measured read of an external map before its confirmation.
                return (Double(progress.bytesCompleted), Double(progress.totalBytes))
            }
            // Remove: content check before deletion (20–90 %).
            // Update: sampled read-back of the new map.
            return action == .remove
                ? band(progress.phaseFraction, lower: 0.20, upper: 0.90)
                : band(progress.phaseFraction, lower: 0, upper: 0.99)
        case .removing, .removingOld:
            // Content check before deletion: 20–90 %.
            return band(progress.phaseFraction, lower: 0.20, upper: 0.90)
        case .idle, .awaitingConfirmation, .updating, .preparing, .finishing, .completed, .failed:
            return nil
        }
    }

    private static func band(_ fraction: Double?, lower: Double, upper: Double) -> (completed: Double, total: Double)? {
        guard let fraction, fraction.isFinite, fraction >= lower, fraction < upper else { return nil }
        return (fraction - lower, upper - lower)
    }
}

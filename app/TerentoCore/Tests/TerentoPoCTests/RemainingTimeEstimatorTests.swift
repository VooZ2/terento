import Foundation

// Whole-app test binaries have no SwiftPM resource bundle.
extension Bundle { static var module: Bundle { .main } }

@main
struct RemainingTimeEstimatorTests {
    static let start = Date(timeIntervalSince1970: 1_800_000_000)

    static func main() {
        testWarmUpAndSteadyRate()
        testSmoothingDampsSpikes()
        testStallHidesTheEstimate()
        testRestartAndUnmeasurableProgress()
        testText()
        testLifecycleUnits()
        print("PASS: measured time-remaining estimates, warm-up, smoothing, stall and lifecycle units")
    }

    static func testWarmUpAndSteadyRate() {
        var estimator = RemainingTimeEstimator()
        // 1 MB/s on a 600 MB transfer.
        let total = 600_000_000.0
        var result: RemainingTimeEstimate?
        for second in 0...4 {
            result = estimator.update(completed: Double(second) * 1_000_000 + 20_000_000, total: total,
                                      at: start.addingTimeInterval(Double(second)))
            expect(result == nil, "no estimate during the warm-up (second \(second))")
        }
        result = estimator.update(completed: 25_000_000, total: total, at: start.addingTimeInterval(5))
        guard let estimate = result else { return fail("an estimate appears after the warm-up") }
        expect(abs(estimate.seconds - 575) < 1, "the steady measured rate predicts the remaining bytes")
        expect(estimate.text(at: start.addingTimeInterval(5)) == "About 10 min left", "rounded up to whole minutes")

        var early = RemainingTimeEstimator()
        _ = early.update(completed: 0, total: total, at: start)
        expect(early.update(completed: 1_000_000, total: total, at: start.addingTimeInterval(10)) == nil,
            "no estimate before 2 % of the phase is measured")
    }

    static func testSmoothingDampsSpikes() {
        var estimator = RemainingTimeEstimator()
        let total = 1_000.0
        _ = estimator.update(completed: 100, total: total, at: start)
        for second in 1...5 {
            _ = estimator.update(completed: 100 + Double(second) * 10, total: total, at: start.addingTimeInterval(Double(second)))
        }
        // One burst of 100 units in a second must not make the estimate collapse.
        let burst = estimator.update(completed: 250, total: total, at: start.addingTimeInterval(6))!
        let unsmoothed = (total - 250) / 100
        let steady = (total - 250) / 10
        expect(burst.seconds > unsmoothed * 2 && burst.seconds < steady, "the rate is smoothed, not the last sample")
    }

    static func testStallHidesTheEstimate() {
        var estimator = RemainingTimeEstimator()
        let total = 100.0
        _ = estimator.update(completed: 10, total: total, at: start)
        let estimate = estimator.update(completed: 20, total: total, at: start.addingTimeInterval(10))!
        expect(estimate.remaining(at: start.addingTimeInterval(14)) != nil, "a fresh estimate counts down")
        expect(abs(estimate.remaining(at: start.addingTimeInterval(14))! - (estimate.seconds - 4)) < 0.001,
            "the estimate counts down between measured samples")
        expect(estimate.remaining(at: start.addingTimeInterval(26)) == nil, "a stalled transfer hides the estimate")
        let repeated = estimator.update(completed: 20, total: total, at: start.addingTimeInterval(30))
        expect(repeated?.remaining(at: start.addingTimeInterval(30)) == nil,
            "repeating the same byte count is not progress and keeps the estimate hidden")
    }

    static func testRestartAndUnmeasurableProgress() {
        var estimator = RemainingTimeEstimator()
        _ = estimator.update(completed: 10, total: 100, at: start)
        _ = estimator.update(completed: 40, total: 100, at: start.addingTimeInterval(6))
        expect(estimator.update(completed: 5, total: 100, at: start.addingTimeInterval(7)) == nil,
            "a restarted transfer starts a new warm-up")
        expect(estimator.update(completed: 50, total: 200, at: start.addingTimeInterval(20)) == nil,
            "a new total starts a new warm-up")
        expect(estimator.update(completed: 10, total: 0, at: start.addingTimeInterval(30)) == nil,
            "an unknown total is not measurable")
        expect(estimator.update(completed: .nan, total: 10, at: start.addingTimeInterval(31)) == nil,
            "an invalid value is not measurable")
        expect(estimator.update(completed: 100, total: 100, at: start.addingTimeInterval(40)) == nil,
            "a complete phase shows no time left")
    }

    static func testText() {
        expect(RemainingTimeEstimate.text(seconds: 30) == "Less than a minute left", "under a minute")
        expect(RemainingTimeEstimate.text(seconds: 61) == "About 2 min left", "minutes round up")
        expect(RemainingTimeEstimate.text(seconds: 3 * 3600) == "About 3 h left", "long phases use hours")
        expect(RemainingTimeEstimate.text(seconds: 2 * 24 * 3600) == nil, "more than a day is not shown")
        expect(RemainingTimeEstimate.text(seconds: -1) == nil, "negative values are not shown")
    }

    static func testLifecycleUnits() {
        func progress(_ state: SafeUpdateState, bytes: UInt64 = 0, total: UInt64 = 0, fraction: Double? = nil) -> SafeUpdateProgress {
            SafeUpdateProgress(state: state, bytesCompleted: bytes, totalBytes: total, bytesPerSecond: 0,
                               phaseFraction: fraction, detail: nil)
        }
        let download = LifecycleRemainingTimeUnits.units(action: .update, phase: .downloading,
            progress: progress(.acquiring, bytes: 5, total: 10))
        expect(download?.completed == 5 && download?.total == 10, "Update download is measured in bytes")
        expect(LifecycleRemainingTimeUnits.units(action: .update, phase: .installing,
            progress: progress(.writing, bytes: 0, total: 0)) == nil, "an unknown write total is not measurable")
        expect(LifecycleRemainingTimeUnits.units(action: .update, phase: .preparing,
            progress: progress(.preparing, fraction: 0.5)) == nil, "Preparing checkpoints are not estimated")
        expect(LifecycleRemainingTimeUnits.units(action: .update, phase: .finishing,
            progress: progress(.postVerifying, fraction: 0.5)) == nil, "Finishing checkpoints are not estimated")
        expect(LifecycleRemainingTimeUnits.units(action: .update, phase: .checking,
            progress: progress(.validating, fraction: 0.1)) == nil, "local source checks are not estimated")
        let readBack = LifecycleRemainingTimeUnits.units(action: .update, phase: .checking,
            progress: progress(.revalidating, fraction: 0.60))
        expect(readBack.map { abs($0.completed - 0.35) < 1e-9 && abs($0.total - 0.70) < 1e-9 } == true,
            "installed-map read-back is measured within its band")
        let removal = LifecycleRemainingTimeUnits.units(action: .remove, phase: .verifying,
            progress: progress(.verifying, bytes: 50, total: 100, fraction: 0.5))
        expect(removal.map { abs($0.completed - 0.30) < 1e-9 && abs($0.total - 0.70) < 1e-9 } == true,
            "the removal content check is measured within 20–90 %")
        expect(LifecycleRemainingTimeUnits.units(action: .remove, phase: .verifying,
            progress: progress(.verifying, bytes: 93, total: 100, fraction: 0.93)) == nil,
            "confirming removal is not estimated")
        expect(LifecycleRemainingTimeUnits.units(action: .update, phase: .removingOld,
            progress: progress(.committing, fraction: 0.95)) == nil, "removal confirmation is not estimated")
        expect(LifecycleRemainingTimeUnits.units(action: .update, phase: .verifying, progress: nil) == nil,
            "no progress is not measurable")
    }

    static func fail(_ message: String) {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fail(message); return }
    }
}

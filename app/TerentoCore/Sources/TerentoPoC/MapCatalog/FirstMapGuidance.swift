import Foundation

/// Install selection guidance. Every selectable map shows its download size
/// and an estimated download time. On a watch with no map installed by
/// Terento yet, the existing locale recommendation is also highlighted (never
/// selected automatically) and one line asks to keep the watch connected.
enum FirstMapGuidance {
    static let recommendedLabel = "Recommended for your region"
    static let keepConnectedLine = "Keep the watch connected and the Mac awake until Terento finishes."
    /// Used until a download on this Mac has been measured: 1 MB/s is a
    /// deliberately slow connection, so the estimate errs on the long side.
    static let conservativeBytesPerSecond: Double = 1_000_000

    /// True while no map on this watch is managed by Terento.
    static func isFirstMapSelection(installedMaps: [InstalledMap]) -> Bool {
        !installedMaps.contains { $0.managementState == .managedByTerento }
    }

    /// "Download 412 MB · about 4 min". `nil` without a known download size.
    static func downloadEstimateText(bytes: UInt64?, recentBytesPerSecond: Double?) -> String? {
        guard let bytes, bytes > 0 else { return nil }
        let size = ByteCountFormatter.string(fromByteCount: Int64(clamping: bytes), countStyle: .decimal)
        return "Download \(size) · \(durationText(bytes: bytes, recentBytesPerSecond: recentBytesPerSecond))"
    }

    /// Always labelled "about": a measured speed predicts, it does not promise.
    static func durationText(bytes: UInt64, recentBytesPerSecond: Double?) -> String {
        let rate = recentBytesPerSecond.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? conservativeBytesPerSecond
        let minutes = max(1, Int((Double(bytes) / rate / 60).rounded(.up)))
        if minutes < 120 { return "about \(minutes) min" }
        return "about \(Int((Double(minutes) / 60).rounded())) h"
    }
}

/// Recently measured provider download speeds on this Mac (local only,
/// never sent anywhere). The median of the last few downloads within 30 days
/// feeds the first-map estimate.
struct DownloadSpeedHistory {
    static let defaultsKey = "Terento.recentDownloadSpeeds.v1"
    static let maximumSamples = 5
    static let maximumAge: TimeInterval = 30 * 24 * 60 * 60
    /// Short downloads do not reach a representative speed.
    static let minimumSampleBytes: UInt64 = 1024 * 1024

    private struct Sample: Codable { let bytesPerSecond: Double; let measuredAt: Date }

    let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func record(bytesPerSecond: Double, downloadedBytes: UInt64, at now: Date = Date()) {
        guard bytesPerSecond.isFinite, bytesPerSecond > 0, downloadedBytes >= Self.minimumSampleBytes else { return }
        var samples = load(now: now)
        samples.append(Sample(bytesPerSecond: bytesPerSecond, measuredAt: now))
        samples = Array(samples.suffix(Self.maximumSamples))
        if let data = try? JSONEncoder().encode(samples) {
            defaults.set(data, forKey: Self.defaultsKey)
        }
    }

    func recentBytesPerSecond(now: Date = Date()) -> Double? {
        let rates = load(now: now).map(\.bytesPerSecond).sorted()
        guard !rates.isEmpty else { return nil }
        let middle = rates.count / 2
        return rates.count % 2 == 1 ? rates[middle] : (rates[middle - 1] + rates[middle]) / 2
    }

    private func load(now: Date) -> [Sample] {
        guard let data = defaults.data(forKey: Self.defaultsKey),
              let samples = try? JSONDecoder().decode([Sample].self, from: data) else { return [] }
        return samples.filter { now.timeIntervalSince($0.measuredAt) <= Self.maximumAge && $0.bytesPerSecond > 0 }
    }
}

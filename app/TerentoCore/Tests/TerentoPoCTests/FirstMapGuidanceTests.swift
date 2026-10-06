import Foundation

// Whole-app test binaries have no SwiftPM resource bundle.
extension Bundle { static var module: Bundle { .main } }

@main
struct FirstMapGuidanceTests {
    static func main() {
        testFirstMapSelection()
        testDownloadEstimateText()
        testSpeedHistory()
        print("PASS: first-map recommendation highlight, download size/time estimate and keep-connected line")
    }

    static func installed(_ state: MapManagementState) -> InstalledMap {
        InstalledMap(name: "Freizeitkarte DEU", provider: "Freizeitkarte", region: "DEU",
                     family: "Freizeitkarte_DEU+", rawVersion: "Release 26.05",
                     version: MapVersion(year: 2026, month: 5), identifier: nil, productId: nil, familyId: nil,
                     sizeBytes: 1, sourceFile: InstalledMapFile(path: "/GARMIN/a.img", filename: "a.img", sizeBytes: 1),
                     metadataStatus: .parsed, managementState: state)
    }

    static func testFirstMapSelection() {
        expect(FirstMapGuidance.isFirstMapSelection(installedMaps: []), "an empty watch is a first map selection")
        expect(FirstMapGuidance.isFirstMapSelection(installedMaps: [installed(.detectedNotManaged), installed(.unknown)]),
            "maps not installed by Terento still make it the first Terento selection")
        expect(!FirstMapGuidance.isFirstMapSelection(installedMaps: [installed(.detectedNotManaged), installed(.managedByTerento)]),
            "a watch with a Terento map is no longer a first selection")
    }

    static func testDownloadEstimateText() {
        expect(FirstMapGuidance.downloadEstimateText(bytes: 412_000_000, recentBytesPerSecond: nil)
            == "Download 412 MB · about 7 min", "without a measured speed the conservative 1 MB/s default is labelled about")
        expect(FirstMapGuidance.downloadEstimateText(bytes: 412_000_000, recentBytesPerSecond: 10_000_000)
            == "Download 412 MB · about 1 min", "a measured speed shortens the estimate, still labelled about")
        expect(FirstMapGuidance.downloadEstimateText(bytes: 5_000_000, recentBytesPerSecond: 50_000_000)
            == "Download 5 MB · about 1 min", "tiny downloads read about 1 min, never 0")
        expect(FirstMapGuidance.downloadEstimateText(bytes: 9_000_000_000, recentBytesPerSecond: 1_000_000)
            == "Download 9 GB · about 3 h", "long downloads use hours")
        expect(FirstMapGuidance.downloadEstimateText(bytes: nil, recentBytesPerSecond: 1) == nil,
            "an unknown download size shows no estimate")
        expect(FirstMapGuidance.downloadEstimateText(bytes: 1_000_000, recentBytesPerSecond: .nan)
            == "Download 1 MB · about 1 min", "an invalid speed falls back to the default")
        expect(FirstMapGuidance.keepConnectedLine == "Keep the watch connected and the Mac awake until Terento finishes.",
            "the keep-connected line is the approved copy")
    }

    static func testSpeedHistory() {
        let suite = "terento-first-map-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let history = DownloadSpeedHistory(defaults: defaults)
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        expect(history.recentBytesPerSecond(now: now) == nil, "no measured speed before a download")
        history.record(bytesPerSecond: 9_000_000, downloadedBytes: 1000, at: now)
        expect(history.recentBytesPerSecond(now: now) == nil, "a download under 1 MiB is not a representative sample")
        for (index, rate) in [1_000_000.0, 3_000_000, 2_000_000, 50_000_000, 4_000_000, 5_000_000].enumerated() {
            history.record(bytesPerSecond: rate, downloadedBytes: 50_000_000, at: now.addingTimeInterval(Double(index)))
        }
        expect(history.recentBytesPerSecond(now: now.addingTimeInterval(10)) == 4_000_000,
            "the median of the last five downloads damps one fast outlier")
        expect(history.recentBytesPerSecond(now: now.addingTimeInterval(DownloadSpeedHistory.maximumAge + 100)) == nil,
            "speeds older than 30 days are ignored")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else {
            fputs("FAIL: \(message)\n", stderr)
            exit(1)
        }
    }
}

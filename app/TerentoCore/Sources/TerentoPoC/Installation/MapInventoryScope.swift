import Foundation

/// The part of the watch that one pre/post-write protection inventory covers.
/// `garmin` is every storage-root entry plus the complete subtree of the single
/// root folder named GARMIN (ASCII case ignored); `full` is every object on
/// every storage. This is a comparison scope, never mutation authority.
enum DeviceInventoryScope: String, Codable, Equatable, Sendable {
    case full = "FULL"
    case garmin = "GARMIN"
}

/// Why a map-scope request was answered by the full walk. Local trace only.
enum DeviceInventoryFallback: String, Codable, Equatable, Sendable {
    case none
    case noRoot = "no_root"
    case ambiguousRoot = "ambiguous_root"
    case scopedFailed = "scoped_failed"
}

/// One inventory read together with the scope it actually covers.
struct DeviceInventoryRead: Codable, Equatable, Sendable {
    let files: [DeviceFile]
    let scope: DeviceInventoryScope
    var fallback: DeviceInventoryFallback = .none

    static func full(_ files: [DeviceFile]) -> Self {
        DeviceInventoryRead(files: files, scope: .full)
    }
}

/// Projection of a full inventory onto the map scope, so that a full baseline
/// (for example the map scan) can be compared with a scoped live read. The
/// predicate is the Swift twin of the native scoped walk.
enum MapInventoryScope {
    /// Storage-root entries and everything below a root named GARMIN (ASCII
    /// case ignored). Malformed paths are kept so the classifier still fails
    /// closed on them instead of silently dropping them.
    static func contains(_ file: DeviceFile) -> Bool {
        let components = file.path.split(separator: "/", omittingEmptySubsequences: false)
        guard components.count >= 2, components[0].isEmpty else { return true }
        if components.count == 2 { return true }
        return isGarminName(components[1])
    }

    static func project(_ files: [DeviceFile]) -> [DeviceFile] {
        files.filter(contains)
    }

    /// Both sides of a comparison in their narrowest common scope: unchanged
    /// when both are full, otherwise both projected onto the map scope.
    static func comparable(
        _ before: [DeviceFile], scope beforeScope: DeviceInventoryScope,
        _ after: [DeviceFile], scope afterScope: DeviceInventoryScope
    ) -> (before: [DeviceFile], after: [DeviceFile], scope: DeviceInventoryScope) {
        guard beforeScope == .garmin || afterScope == .garmin else { return (before, after, .full) }
        return (beforeScope == .garmin ? before : project(before),
                afterScope == .garmin ? after : project(after), .garmin)
    }

    private static func isGarminName(_ text: Substring) -> Bool {
        let bytes = Array(text.utf8)
        return bytes.count == 6 && zip(bytes, "GARMIN".utf8).allSatisfy {
            ($0.0 >= 97 && $0.0 <= 122 ? $0.0 - 32 : $0.0) == $0.1
        }
    }
}

/// Privacy-safe timing evidence for the pre/post-write inventories: only the
/// scope, object counts and durations. No path, name, size or handle.
/// `scope` is `GARMIN` only when every measured read used the scoped walk.
struct InstallationInventoryMetrics: Codable, Equatable, Sendable {
    private(set) var scope: DeviceInventoryScope
    let prewriteObjectCount: Int
    let prewriteDurationMs: Int
    private(set) var postwriteObjectCount: Int? = nil
    private(set) var postwriteDurationMs: Int? = nil

    init(prewrite: DeviceInventoryRead, durationMilliseconds: UInt64) {
        scope = prewrite.scope
        prewriteObjectCount = prewrite.files.count
        prewriteDurationMs = Self.bounded(durationMilliseconds)
    }

    /// The post-write duration covers every post-write inventory read of the
    /// operation (including the single retry when the target was transiently
    /// absent); the count is that of the read actually compared.
    func withPostwrite(_ read: DeviceInventoryRead, durationMilliseconds: UInt64) -> Self {
        var copy = self
        copy.postwriteObjectCount = read.files.count
        copy.postwriteDurationMs = Self.bounded(durationMilliseconds)
        if read.scope == .full { copy.scope = .full }
        return copy
    }

    private static func bounded(_ milliseconds: UInt64) -> Int {
        Int(min(milliseconds, UInt64(Int32.max)))
    }

    /// Local finishing-trace fields; fixed keys and numeric values only.
    static func traceFields(_ read: DeviceInventoryRead, durationMilliseconds: UInt64, baseline: Int?) -> String {
        "scope=\(read.scope.rawValue) fallback=\(read.fallback.rawValue) objects=\(read.files.count)"
            + (baseline.map { " baseline=\($0)" } ?? "") + " duration_ms=\(durationMilliseconds)"
    }
}

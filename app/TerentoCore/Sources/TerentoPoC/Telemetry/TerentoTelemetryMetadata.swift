import Foundation

/// The release identity shared by both privacy-minimised telemetry streams.
///
/// A SwiftPM executable has no generated app Info.plist, so it deliberately
/// uses the local fallback. An app bundle must provide TerentoReleaseLabel;
/// Xcode Debug does so with the `-local` suffix and Release provides the
/// public label. We never emit `development` as a telemetry identity.
enum TerentoTelemetryMetadata {
    static let fallbackLocalReleaseLabel = "1.0.0-beta.10-local"

    static let version = (Bundle.main.object(
        forInfoDictionaryKey: "CFBundleShortVersionString"
    ) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty
        ?? "1.0.0"

    static let build = (Bundle.main.object(
        forInfoDictionaryKey: "CFBundleVersion"
    ) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty
        ?? "local"

    static let releaseLabel: String = {
        let configured = (Bundle.main.object(
            forInfoDictionaryKey: "TerentoReleaseLabel"
        ) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let configured, isSemanticVersion(configured) {
            return configured
        }

        // SwiftPM and native test runners are local executables rather than
        // distributed app bundles. Their missing Info.plist is expected and
        // must still produce a purgeable, deterministic local identity.
        if Bundle.main.bundleURL.pathExtension.caseInsensitiveCompare("app") != .orderedSame {
            return fallbackLocalReleaseLabel
        }

        // A malformed/missing Release bundle label must fail server-side
        // validation instead of silently becoming a production or local event.
        return ""
    }()

    static let isLocalTest: Bool = isLocalReleaseLabel(releaseLabel)

    /// `appBuild` remains useful for build diagnostics while carrying the
    /// local marker for older admin views that only display the build column.
    static let eventBuild: String = {
        let base = build.isEmpty ? "local" : build
        guard isLocalTest, !base.lowercased().hasSuffix("-local") else {
            return String(base.prefix(80))
        }
        return String("\(base)-local".prefix(80))
    }()

    static func isSemanticVersion(_ value: String) -> Bool {
        let pattern = #"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"#
        return value.range(of: pattern, options: .regularExpression) != nil
    }

    static func isLocalReleaseLabel(_ value: String) -> Bool {
        isSemanticVersion(value) && value.hasSuffix("-local")
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

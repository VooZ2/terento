import Foundation

/// The release identity shared by both privacy-minimized telemetry streams.
///
/// A SwiftPM executable has no generated app Info.plist, so it deliberately
/// uses the local fallback. An app bundle must provide TerentoReleaseLabel;
/// Xcode Debug does so with the `-local` suffix and Release provides the
/// public label. We never emit `development` as a telemetry identity.
enum TerentoTelemetryMetadata {
    static let fallbackLocalReleaseLabel = "1.0.0-beta.11-local"

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

    /// The label sent with diagnostics. App Store builds add SemVer build
    /// metadata, so Admin tells them apart without another field.
    static let eventReleaseLabel: String = {
        #if TERENTO_APP_STORE
        return appStoreEventReleaseLabel(releaseLabel)
        #else
        return releaseLabel
        #endif
    }()

    static func appStoreEventReleaseLabel(_ label: String) -> String {
        // A local test label must keep its "-local" ending: the server marks
        // a build as a purgeable local test only by that suffix.
        guard !label.isEmpty, !isLocalReleaseLabel(label) else { return label }
        return label + (label.contains("+") ? ".appstore" : "+appstore")
    }

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

/// What an App Store build does at start-up with a sharing choice that was
/// recorded under an earlier notice. One rule for both diagnostic streams
/// (`VersionedEvidenceConsent`, `VersionedMapStatisticsConsent`).
enum AppStoreConsentNotice {
    /// The 1.2.x question: Share or Not now, and Not now was recorded as a
    /// refusal.
    static let firstQuestionVersion = 100
    /// From 1.2.3: Share, Not now or Don't share. Not now records nothing and
    /// Don't share is final.
    static let currentVersion = 101

    enum Migration: Equatable, Sendable {
        /// Recorded under the current notice: nothing changes.
        case unchanged
        /// An opt-in under the 1.2.x notice stands, with what it queued.
        case keepAccepted
        /// A refusal copied from the direct-download app stands; queues go.
        case keepDeclined
        /// No choice: the sharing question is asked again; queues go.
        case undecided
    }

    /// `noticeVersion` is nil when no choice is recorded. A refusal under the
    /// 1.2.x notice may have been a Not now, so it becomes undecided and the
    /// person is asked once more with the new question. Any other notice
    /// number is the direct-download app's, where only a refusal carries over.
    static func migration(noticeVersion: Int?, declined: Bool) -> Migration {
        guard let noticeVersion else { return .undecided }
        if noticeVersion == currentVersion { return .unchanged }
        if noticeVersion == firstQuestionVersion { return declined ? .undecided : .keepAccepted }
        return declined ? .keepDeclined : .undecided
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

import Foundation

// Whole-app test binaries have no SwiftPM resource bundle.
extension Bundle { static var module: Bundle { .main } }

@main
struct TroubleshootingHelpTests {
    /// Spec S2: the exact anchors of the public troubleshooting guide.
    static let specifiedAnchors: [String] = [
        "connect-watch", "garmin-busy", "multiple-garmin", "usb-mode", "connection-timeout",
        "watch-not-responding", "model-not-enabled", "couldnt-check", "catalog-unavailable",
        "download-failed", "mac-storage", "watch-storage", "leftover-map", "update-remove", "send-report"
    ]

    static func main() {
        testAnchorsMatchTheGuide()
        testEveryTopicHasAGuideAnchor()
        testConnectionOutcomes()
        testAuthorizationVerdicts()
        testCatalogAndAcquisition()
        testInstallationFailures()
        testLifecycleAndReview()
        print("PASS: every user-facing error and hint maps to a troubleshooting guide anchor")
    }

    static func testAnchorsMatchTheGuide() {
        expect(TroubleshootingAnchor.allCases.map(\.rawValue) == specifiedAnchors,
            "the app knows exactly the S2 guide anchors, in guide order")
        let referral = "utm_source=terento_app&utm_medium=referral&utm_campaign=app_troubleshooting"
        let sitePattern = try! NSRegularExpression(pattern: "^[A-Za-z0-9._~-]{1,80}$")
        for anchor in TroubleshootingAnchor.allCases {
            let url = anchor.url
            expect(url.absoluteString
                == "https://terento.app/guides/troubleshooting/?\(referral)&utm_content=\(anchor.rawValue)#\(anchor.rawValue)",
                "\(anchor.rawValue) links the English guide with the app referral, then the section fragment")
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            let items = components.queryItems ?? []
            expect(items.map(\.name) == ["utm_source", "utm_medium", "utm_campaign", "utm_content"],
                "\(anchor.rawValue) carries only the four campaign parameters")
            expect(items.allSatisfy { value in value.value.map {
                    sitePattern.firstMatch(in: $0, range: NSRange($0.startIndex..., in: $0)) != nil } == true },
                "\(anchor.rawValue) campaign values pass the site's attribution filter")
            expect(components.fragment == anchor.rawValue && url.absoluteString.firstIndex(of: "?")! < url.absoluteString.firstIndex(of: "#")!,
                "\(anchor.rawValue) keeps the fragment after the query string")
        }
        let menu = TroubleshootingGuide.helpMenuURL
        expect(menu.absoluteString == "https://terento.app/guides/troubleshooting/?\(referral)&utm_content=help_menu"
            && menu.fragment == nil, "Help → Troubleshooting opens the guide top with the help_menu content")
    }

    static func testEveryTopicHasAGuideAnchor() {
        var used = Set<TroubleshootingAnchor>()
        for topic in TroubleshootingTopic.allCases {
            expect(specifiedAnchors.contains(topic.anchor.rawValue), "\(topic.rawValue) maps to an S2 anchor")
            expect(topic.url == topic.anchor.url, "\(topic.rawValue) opens its anchor URL")
            used.insert(topic.anchor)
        }
        expect(used == Set(TroubleshootingAnchor.allCases), "every guide section is reachable from the app")
    }

    static func testConnectionOutcomes() {
        let expected: [DeviceConnectOutcome: String?] = [
            .connected: nil, .timeoutNoUSB: "connect-watch", .timeoutUSBPresent: "connection-timeout",
            .busy: "garmin-busy", .multipleDevices: "multiple-garmin", .notMTPMode: "usb-mode",
            .disconnected: "connect-watch", .failed: "watch-not-responding"
        ]
        for outcome in DeviceConnectOutcome.allCases {
            expect(TroubleshootingHelp.topic(for: outcome)?.anchor.rawValue == expected[outcome] ?? nil,
                "connect outcome \(outcome.rawValue) has its guide section")
        }
        expect(TroubleshootingHelp.topic(detectionPhase: .waitingForWatch).anchor == .connectWatch,
            "waiting for a watch links the connect steps")
        expect(TroubleshootingHelp.topic(detectionPhase: .connecting).anchor == .connectWatch,
            "connecting links the connect steps")
        expect(TroubleshootingHelp.topic(detectionPhase: .needsAttention(.busy)).anchor == .garminBusy,
            "a live busy hint links the busy section")
        testFailureMessagesMatchTheirSections()
    }

    /// Each final connect failure has its own title, a reason and steps, and
    /// its outcome maps to the guide section about the same cause.
    static func testFailureMessagesMatchTheirSections() {
        let expected: [DeviceConnectOutcome: (anchor: TroubleshootingAnchor, cue: String)] = [
            .timeoutNoUSB: (.connectWatch, "Use a USB data cable, not a charge-only cable."),
            .timeoutUSBPresent: (.connectionTimeout, "didn't become ready within 2 minutes"),
            .busy: (.garminBusy, "only one app at a time"),
            .multipleDevices: (.multipleGarmin, "one Garmin at a time"),
            .notMTPMode: (.usbMode, "open USB Mode, usually under Settings › System, and choose MTP"),
            .disconnected: (.connectWatch, "firmly plugged in"),
            .failed: (.watchNotResponding, "stopped answering")
        ]
        var titles = Set<String>()
        for outcome in DeviceConnectOutcome.allCases where outcome != .connected {
            guard let entry = expected[outcome] else {
                expect(false, "connect failure \(outcome.rawValue) has an expected guide section")
                return
            }
            let message = UserFacingErrorMessage.detectionFailure(
                outcome, garminUSBPresent: outcome != .timeoutNoUSB, detectedConflicts: [])
            expect(titles.insert(message.title).inserted && !message.reason.isEmpty && message.steps.count >= 2,
                "connect failure \(outcome.rawValue) has a distinct title, a reason and steps")
            expect(message.text.contains(entry.cue),
                "connect failure \(outcome.rawValue) explains the cause its guide section covers")
            expect(TroubleshootingHelp.topic(for: outcome)?.anchor == entry.anchor,
                "connect failure \(outcome.rawValue) maps to #\(entry.anchor.rawValue)")
            expect(message.outcome == outcome
                && TroubleshootingHelp.connectionErrorTopic(state: .failed, phase: .waitingForWatch, failure: message)?.anchor
                    == entry.anchor,
                "the final \(outcome.rawValue) screen links #\(entry.anchor.rawValue)")
        }
        testConnectionErrorHelpOnlyForErrors()
    }

    /// Connect links the guide only for a connection error, never while
    /// waiting or connecting (including the "Still not showing up?" steps).
    static func testConnectionErrorHelpOnlyForErrors() {
        for phase in [DeviceDetectionPhase.waitingForWatch, .connecting] {
            expect(TroubleshootingHelp.connectionErrorTopic(state: .detecting, phase: phase, failure: nil) == nil,
                "\(phase) shows no Help link")
        }
        let attention: [DeviceConnectOutcome: TroubleshootingAnchor] = [
            .busy: .garminBusy, .multipleDevices: .multipleGarmin, .notMTPMode: .usbMode
        ]
        for (outcome, anchor) in attention {
            expect(TroubleshootingHelp.connectionErrorTopic(state: .detecting, phase: .needsAttention(outcome),
                                                            failure: nil)?.anchor == anchor,
                "the live \(outcome.rawValue) state links #\(anchor.rawValue)")
        }
        let lost = UserFacingErrorMessage.connectionTimeout(garminUSBPresent: false, detectedConflicts: [])
        expect(TroubleshootingHelp.connectionErrorTopic(state: .failed, phase: .waitingForWatch, failure: lost)?.anchor
            == .connectionTimeout, "a watch that left USB before it was ready links the connection-timeout section")
        expect(TroubleshootingHelp.connectionErrorTopic(state: .failed, phase: .waitingForWatch, failure: nil) == nil,
            "a failure without a known cause shows no Help link")
        let stale = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true, detectedConflicts: [])
        for state in [DeviceConnectionState.disconnected, .connected, .ready, .ejecting, .safeToDisconnect] {
            expect(TroubleshootingHelp.connectionErrorTopic(state: state, phase: .needsAttention(.busy), failure: stale) == nil,
                "\(state) shows no connection Help link")
        }
    }

    static func testAuthorizationVerdicts() {
        let reasons: [InstallationAuthorizationBlockReason: TroubleshootingAnchor] = [
            .pending: .modelNotEnabled, .unknownModel: .modelNotEnabled, .ambiguousCatalogMatch: .modelNotEnabled,
            .outOfScope: .modelNotEnabled, .notAuthorized: .modelNotEnabled,
            .catalogUnavailable: .couldntCheck, .updateRequired: .catalogUnavailable
        ]
        for (reason, anchor) in reasons {
            expect(TroubleshootingHelp.topic(for: reason).anchor == anchor, "verdict \(reason.rawValue) has its section")
            expect(TroubleshootingHelp.topic(for: InstallationAuthorizationState.blocked(reason))?.anchor == anchor,
                "blocked state \(reason.rawValue) has its section")
        }
        expect(TroubleshootingHelp.topic(for: InstallationAuthorizationState.resolving) == nil,
            "checking shows no help link")
    }

    static func testCatalogAndAcquisition() {
        expect(TroubleshootingHelp.topic(for: MapCatalogSource.bundledFallback)?.anchor == .catalogUnavailable,
            "local catalog fallback links catalog help")
        expect(TroubleshootingHelp.topic(for: MapCatalogSource.appUpdateRequired)?.anchor == .catalogUnavailable,
            "an app too old for the catalog links catalog help")
        expect(TroubleshootingHelp.topic(for: MapCatalogSource.remote) == nil, "a current catalog has no help link")
        let identity = MapIdentity(provider: "freizeitkarte", region: "LTU")!
        let cases: [(MapAcquisitionError, TroubleshootingAnchor)] = [
            (.acquisitionWithheld(.blocked(provider: "OpenTopoMap", reason: "STATUS_UNVERIFIED")), .catalogUnavailable),
            (.acquisitionWithheld(.blocked(provider: "OpenTopoMap", reason: "APP_UPDATE_REQUIRED")), .catalogUnavailable),
            (.acquisitionWithheld(.blocked(provider: "OpenTopoMap", reason: "PROVIDER_DOWN")), .downloadFailed),
            (.acquisitionWithheld(.withheldRussia), .downloadFailed),
            (.downloadFailed("x"), .downloadFailed),
            (.providerUnavailable(providerId: "maprando", statusCode: 503), .downloadFailed),
            (.providerConnectionFailed(providerId: "maprando", code: .timedOut), .downloadFailed),
            (.downloadIncomplete(expected: 2, actual: 1), .downloadFailed),
            (.untrustedSourceURL("x"), .downloadFailed),
            (.invalidPackage("x"), .downloadFailed),
            (.extractionFailed("x"), .downloadFailed),
            (.unsupportedPackageFormat, .downloadFailed),
            (.unsafeArchivePath("x"), .downloadFailed),
            (.sourceIdentityMismatch(expected: identity, actual: nil), .downloadFailed),
            (.sourceVersionMismatch(expected: MapVersion(year: 2024, month: 1)!, actual: nil), .downloadFailed),
            (.noIMGFound, .downloadFailed),
            (.ambiguousIMG, .downloadFailed),
            (.customMapNotConfirmed("x"), .downloadFailed),
            (.workspaceFailed("x"), .macStorage),
            (.insufficientMacStorage(requiredBytes: 10), .macStorage)
        ]
        for (error, anchor) in cases {
            expect(TroubleshootingHelp.topic(for: error).anchor == anchor, "acquisition error \(error) has its section")
        }
    }

    static func testInstallationFailures() {
        let all: [InstallationFailure] = [
            .existingMapConflict, .sourceArtifactInvalid, .insufficientSpace, .unknownInstallSize,
            .unknownInstallTarget, .stableWatchIdentityUnavailable, .mapIdentityAmbiguous, .downloadFailed,
            .sourceValidationFailed, .deviceDisconnected, .preflightMTPReadFailed, .writeFailed, .sizeMismatch,
            .hashMismatch, .remoteFileMissing, .metadataMismatch, .manifestFailed, .protectionViolation,
            .cleanupFailed, .transactionAlreadyRunning, .invalidStateTransition, .verificationRequired,
            .installationAuthorization, .installationAuthorizationUnavailable
        ]
        for failure in all {
            expect(specifiedAnchors.contains(TroubleshootingHelp.topic(for: failure).anchor.rawValue),
                "installation failure \(failure.rawValue) has an S2 section")
        }
        expect(TroubleshootingHelp.topic(for: .insufficientSpace).anchor == .watchStorage, "watch storage")
        expect(TroubleshootingHelp.topic(for: .cleanupFailed).anchor == .leftoverMap, "failed cleanup")
        expect(TroubleshootingHelp.installationTopic(failure: .writeFailed, acquisitionError: nil,
            mayHaveLeftMapOnWatch: true).anchor == .leftoverMap,
            "a map that may remain after writing links the leftover-map section first")
        expect(TroubleshootingHelp.installationTopic(failure: .sourceValidationFailed,
            acquisitionError: .insufficientMacStorage(requiredBytes: nil), mayHaveLeftMapOnWatch: false).anchor == .macStorage,
            "the typed acquisition error wins over its coarse diagnostic failure")
        expect(TroubleshootingHelp.installationTopic(failure: nil, acquisitionError: nil,
            mayHaveLeftMapOnWatch: false).anchor == .sendReport, "an unknown stop links sending a report")
    }

    static func testLifecycleAndReview() {
        let active: [MapLifecycleOperationPhase] = [.removing, .updating, .verifying, .downloading, .preparing,
            .checking, .installing, .removingOld, .finishing]
        for phase in active {
            expect(TroubleshootingHelp.topic(for: phase)?.anchor == .updateRemove, "lifecycle \(phase) links update-remove")
        }
        expect(TroubleshootingHelp.topic(for: MapLifecycleOperationPhase.failed)?.anchor == .updateRemove,
            "a failed update or removal links update-remove")
        expect(TroubleshootingHelp.topic(for: MapLifecycleOperationPhase.completed) == nil, "completion has no link")
        let blocks: [(AppFunnelInstallBlockedReason, TroubleshootingAnchor?)] = [
            (.authorization, .modelNotEnabled), (.deviceStorage, .watchStorage), (.macStorage, .macStorage),
            (.catalogUnverified, .catalogUnavailable), (.localCapability, .watchNotResponding), (.other, nil)
        ]
        for (block, anchor) in blocks {
            expect(TroubleshootingHelp.topic(for: block, authorization: .blocked(.pending))?.anchor == anchor,
                "review block \(block.rawValue) has its section")
        }
        expect(TroubleshootingTopic.sendReport.anchor == .sendReport, "reporting links send-report")
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else {
            fputs("FAIL: \(message)\n", stderr)
            exit(1)
        }
    }
}

import Foundation

/// Section anchors of the public troubleshooting guide
/// (`https://terento.app/guides/troubleshooting/`). The ids are stable and
/// identical in every site locale; the app always links the English URL and
/// lets the site's language handling redirect. No query string is added.
enum TroubleshootingAnchor: String, CaseIterable, Sendable {
    case connectWatch = "connect-watch"
    case garminBusy = "garmin-busy"
    case multipleGarmin = "multiple-garmin"
    case usbMode = "usb-mode"
    case connectionTimeout = "connection-timeout"
    case watchNotResponding = "watch-not-responding"
    case modelNotEnabled = "model-not-enabled"
    case couldntCheck = "couldnt-check"
    case catalogUnavailable = "catalog-unavailable"
    case downloadFailed = "download-failed"
    case macStorage = "mac-storage"
    case watchStorage = "watch-storage"
    case leftoverMap = "leftover-map"
    case updateRemove = "update-remove"
    case sendReport = "send-report"

    var url: URL { TroubleshootingGuide.url(self) }
}

/// The public guide; kept beside the anchors so this mapping has no UI dependency.
/// Links reuse the app's existing referral convention (`TerentoAppLinks`:
/// utm_source=terento_app, utm_medium=referral) with the troubleshooting
/// campaign and the entry point as content. No model, version or id is added.
enum TroubleshootingGuide {
    static let guideURL = URL(string: "https://terento.app/guides/troubleshooting/")!
    static let campaign = "app_troubleshooting"
    static let helpMenuContent = "help_menu"

    /// A per-error Help link: query first, then the section fragment.
    static func url(_ anchor: TroubleshootingAnchor) -> URL {
        url(content: anchor.rawValue, fragment: anchor.rawValue)
    }

    /// Help → Troubleshooting opens the top of the guide.
    static var helpMenuURL: URL { url(content: helpMenuContent, fragment: nil) }

    private static func url(content: String, fragment: String?) -> URL {
        var components = URLComponents(url: guideURL, resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "utm_source", value: "terento_app"),
            URLQueryItem(name: "utm_medium", value: "referral"),
            URLQueryItem(name: "utm_campaign", value: campaign),
            URLQueryItem(name: "utm_content", value: content)
        ]
        components.fragment = fragment
        return components.url!
    }
}

/// Every user-facing error or hint that offers a "Help" link. This is the
/// single place where an error is mapped to a guide section.
enum TroubleshootingTopic: String, CaseIterable, Sendable {
    // Connection
    case waitingForWatch
    case connectionNoUSB
    case garminBusy
    case multipleGarmin
    case notReadyForFileTransfer
    case connectionTimeout
    case watchStoppedResponding
    case watchDisconnected
    case mapReadFailed
    // Authorization verdicts
    case modelNotEnabled
    case authorizationUnavailable
    case appUpdateRequired
    // Catalog and acquisition
    case catalogFallback
    case catalogUnverified
    case providerDownloadFailed
    case downloadedMapRejected
    // Storage
    case macStorageFull
    case watchStorageFull
    // Writing and verification
    case watchIdentityUnavailable
    case transferFailed
    case leftoverMapAfterFailure
    case unexpectedSafetyStop
    // Update and Remove
    case updateRemoveInProgress
    case updateRemoveFailed
    // Reports
    case sendReport

    var anchor: TroubleshootingAnchor {
        switch self {
        case .waitingForWatch, .connectionNoUSB, .watchDisconnected: return .connectWatch
        case .garminBusy: return .garminBusy
        case .multipleGarmin: return .multipleGarmin
        case .notReadyForFileTransfer: return .usbMode
        case .connectionTimeout: return .connectionTimeout
        case .watchStoppedResponding, .mapReadFailed, .watchIdentityUnavailable, .transferFailed:
            return .watchNotResponding
        case .modelNotEnabled: return .modelNotEnabled
        case .authorizationUnavailable: return .couldntCheck
        case .appUpdateRequired, .catalogFallback, .catalogUnverified: return .catalogUnavailable
        case .providerDownloadFailed, .downloadedMapRejected: return .downloadFailed
        case .macStorageFull: return .macStorage
        case .watchStorageFull: return .watchStorage
        case .leftoverMapAfterFailure: return .leftoverMap
        case .updateRemoveInProgress, .updateRemoveFailed: return .updateRemove
        case .unexpectedSafetyStop, .sendReport: return .sendReport
        }
    }

    var url: URL { anchor.url }
}

/// Maps the app's domain errors to help topics. Each switch is exhaustive, so
/// a new error case cannot ship without a guide section.
enum TroubleshootingHelp {
    /// `nil` only for a successful connection.
    static func topic(for outcome: DeviceConnectOutcome) -> TroubleshootingTopic? {
        switch outcome {
        case .connected: return nil
        case .timeoutNoUSB: return .connectionNoUSB
        case .timeoutUSBPresent: return .connectionTimeout
        case .busy: return .garminBusy
        case .multipleDevices: return .multipleGarmin
        case .notMTPMode: return .notReadyForFileTransfer
        case .disconnected: return .watchDisconnected
        case .failed: return .watchStoppedResponding
        }
    }

    /// The Connect page's current state; `nil` once a watch is connected.
    static func topic(detectionPhase: DeviceDetectionPhase) -> TroubleshootingTopic {
        switch detectionPhase {
        case .waitingForWatch, .connecting: return .waitingForWatch
        case .needsAttention(let outcome): return topic(for: outcome) ?? .waitingForWatch
        }
    }

    /// Connect links the guide only inside a help box about a problem: a live
    /// attention state, a final failure, or the "Still not showing up?"
    /// steps after a whole connection window with nothing on USB. Plain
    /// waiting and connecting have no link.
    static func connectHelpTopic(state: DeviceConnectionState,
                                 phase: DeviceDetectionPhase,
                                 failure: ConnectIssueMessage?,
                                 waitedWithoutUSB: Bool) -> TroubleshootingTopic? {
        switch state {
        case .detecting:
            switch phase {
            case .needsAttention(let outcome): return topic(for: outcome)
            case .waitingForWatch: return waitedWithoutUSB ? .connectionNoUSB : nil
            case .connecting: return nil
            }
        case .failed:
            return failure.flatMap { topic(for: $0.outcome) }
        case .disconnected, .connected, .ready, .ejecting, .safeToDisconnect:
            return nil
        }
    }

    /// `nil` while resolving or approved.
    static func topic(for authorization: InstallationAuthorizationState) -> TroubleshootingTopic? {
        switch authorization {
        case .resolving, .approved: return nil
        case .blocked(let reason): return topic(for: reason)
        }
    }

    static func topic(for reason: InstallationAuthorizationBlockReason) -> TroubleshootingTopic {
        switch reason {
        case .pending, .unknownModel, .ambiguousCatalogMatch, .outOfScope, .notAuthorized:
            return .modelNotEnabled
        case .catalogUnavailable: return .authorizationUnavailable
        case .updateRequired: return .appUpdateRequired
        }
    }

    /// `nil` for a current remote catalog.
    static func topic(for source: MapCatalogSource?) -> TroubleshootingTopic? {
        switch source {
        case .bundledFallback: return .catalogFallback
        case .appUpdateRequired: return .appUpdateRequired
        case .remote, .cachedRemote, nil: return nil
        }
    }

    static func topic(for error: MapAcquisitionError) -> TroubleshootingTopic {
        switch error {
        case .acquisitionWithheld(.blocked(_, let reason))
            where reason == "STATUS_UNVERIFIED" || reason == "APP_UPDATE_REQUIRED":
            return .catalogUnverified
        case .acquisitionWithheld, .downloadFailed, .providerUnavailable, .providerConnectionFailed,
             .downloadIncomplete, .untrustedSourceURL:
            return .providerDownloadFailed
        case .invalidPackage, .extractionFailed, .unsupportedPackageFormat, .unsafeArchivePath,
             .sourceIdentityMismatch, .sourceVersionMismatch, .noIMGFound, .ambiguousIMG,
             .customMapNotConfirmed:
            return .downloadedMapRejected
        case .workspaceFailed, .insufficientMacStorage:
            return .macStorageFull
        }
    }

    static func topic(for failure: InstallationFailure) -> TroubleshootingTopic {
        switch failure {
        case .insufficientSpace, .unknownInstallSize: return .watchStorageFull
        case .downloadFailed: return .providerDownloadFailed
        case .sourceArtifactInvalid, .sourceValidationFailed: return .downloadedMapRejected
        case .deviceDisconnected: return .watchDisconnected
        case .preflightMTPReadFailed, .writeFailed, .sizeMismatch, .hashMismatch,
             .remoteFileMissing, .metadataMismatch:
            return .transferFailed
        case .stableWatchIdentityUnavailable, .unknownInstallTarget: return .watchIdentityUnavailable
        case .cleanupFailed: return .leftoverMapAfterFailure
        case .installationAuthorization: return .modelNotEnabled
        case .installationAuthorizationUnavailable: return .authorizationUnavailable
        case .existingMapConflict, .mapIdentityAmbiguous, .manifestFailed, .protectionViolation,
             .transactionAlreadyRunning, .invalidStateTransition, .verificationRequired:
            return .unexpectedSafetyStop
        }
    }

    /// The help topic for a stopped installation. A map that may remain on
    /// the watch takes precedence, then the acquisition error, then the
    /// recorded failure. Unknown causes point to sending a report.
    static func installationTopic(
        failure: InstallationFailure?,
        acquisitionError: MapAcquisitionError?,
        mayHaveLeftMapOnWatch: Bool
    ) -> TroubleshootingTopic {
        if mayHaveLeftMapOnWatch { return .leftoverMapAfterFailure }
        if let acquisitionError { return topic(for: acquisitionError) }
        if let failure { return topic(for: failure) }
        return .sendReport
    }

    static func topic(for block: AppFunnelInstallBlockedReason,
                      authorization: InstallationAuthorizationState) -> TroubleshootingTopic? {
        switch block {
        case .authorization: return topic(for: authorization) ?? .modelNotEnabled
        case .deviceStorage: return .watchStorageFull
        case .macStorage: return .macStorageFull
        case .catalogUnverified: return .catalogUnverified
        case .localCapability: return .watchIdentityUnavailable
        case .other: return nil
        }
    }

    /// Help for a blocked review step, from the same classification the
    /// review step uses; `nil` when Install is available or no guide applies.
    static func reviewTopic(plan: InstallationPlan,
                            authorization: InstallationAuthorizationState) -> TroubleshootingTopic? {
        AppFunnelInstallBlockedReason.forReview(plan: plan, installationAuthorization: authorization,
                                                supportedInstallFlow: true)
            .flatMap { topic(for: $0, authorization: authorization) }
    }

    /// Update and Remove: long measured phases and failures share one section.
    static func topic(for phase: MapLifecycleOperationPhase) -> TroubleshootingTopic? {
        switch phase {
        case .removing, .updating, .verifying, .downloading, .preparing, .checking,
             .installing, .removingOld, .finishing:
            return .updateRemoveInProgress
        case .failed: return .updateRemoveFailed
        case .idle, .awaitingConfirmation, .completed: return nil
        }
    }
}

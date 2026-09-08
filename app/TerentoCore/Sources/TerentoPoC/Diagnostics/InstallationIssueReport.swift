import AppKit
import Foundation

struct InstallationIssueDraft: Equatable, Sendable {
    let title: String
    let body: String
    let url: URL
}

struct InstallationIssueMap: Equatable, Sendable {
    let provider: String
    let region: String
    let package: String
    let release: String?
    let artifactSizeBytes: UInt64?
}

/// Explicitly shareable facts only: no paths, object IDs, map hashes or raw errors.
struct InstallationIssueVerification: Sendable {
    var originalFailure: String? = nil
    var cleanupFailure: String? = nil
    var transportClassification: String? = nil
    var artifactKind: String? = nil
    var sourceSize: UInt64? = nil
    var remoteSize: UInt64? = nil
    var transferredBytes: UInt64? = nil
    var elapsedMilliseconds: UInt64? = nil
    var sampledBytes: UInt64? = nil
    var sampleCount: Int? = nil
    var matchedSampleCount: Int? = nil
}

@MainActor
enum InstallationIssueReport {
    static func generate(
        identity: DeviceIdentity?,
        maps: [InstallationIssueMap],
        stage: String,
        error: String?,
        operationID: UUID?,
        failureStages: [String] = [],
        errorCategory: String? = nil,
        errorCodes: [String] = [],
        writeStarted: Bool = false,
        transferProgressPercent: Int = 0,
        remoteObjectCreated: Bool = false,
        cleanupAttempted: Bool = false,
        cleanupSucceeded: Bool = false,
        verification: InstallationIssueVerification = .init(),
        diagnosticID: UUID = UUID(),
        timestamp: Date = Date(),
        appVersion: String = TerentoTelemetryMetadata.releaseLabel,
        appBuild: String = TerentoTelemetryMetadata.eventBuild,
        operatingSystem: String = ProcessInfo.processInfo.operatingSystemVersionString
    ) -> InstallationIssueDraft {
        let safeStage = sanitizedLine(stage, fallback: "Installation")
        let safeError = error.map { sanitizedLine($0, fallback: "Unavailable") }
        let primaryMap = maps.first
        let primaryProvider = primaryMap.map { sanitizedLine($0.provider, fallback: "Map provider") }
            ?? "Map provider"
        let primaryRegion = primaryMap.map { sanitizedLine($0.region, fallback: "Map") } ?? "Map"
        let title = String(
            DiagnosticReportSanitizer.sanitize(
                "Installation stopped during \(safeStage) — \(primaryProvider) / \(primaryRegion)"
            ).prefix(180)
        )

        let reportedMaps = Array(maps.prefix(8))
        let regions = reportedMaps.map { sanitizedLine($0.package, fallback: $0.region) }
        let releases = Array(Set(reportedMaps.compactMap { nonEmpty($0.release) })).sorted()
        let providers = Array(Set(reportedMaps.map { sanitizedLine($0.provider, fallback: "Unavailable") })).sorted()
        let normalizedFailureStages = failureStages
            .map { sanitizedLine($0, fallback: safeStage) }
            .filter { !$0.isEmpty }
        let normalizedErrorCodes = errorCodes
            .map { sanitizedLine($0, fallback: "UNKNOWN") }
            .filter { !$0.isEmpty }
        let boundedProgress = min(100, max(0, transferProgressPercent))

        var deviceLines: [String] = []
        if let identity {
            deviceLines.append("- Model: \(sanitizedLine(identity.presentationModel, fallback: "Unavailable"))")
            deviceLines.append("- Variant: \(sanitizedLine(identity.variant ?? "Unavailable", fallback: "Unavailable"))")
            deviceLines.append("- Family: \(sanitizedLine(identity.family ?? "Unavailable", fallback: "Unavailable"))")
            deviceLines.append("- Firmware: \(sanitizedLine(identity.firmware ?? "Unavailable", fallback: "Unavailable"))")
            deviceLines.append("- Raw MTP model: \(sanitizedLine(identity.model, fallback: "Unavailable"))")
        } else {
            deviceLines.append("- Model: Unavailable")
        }

        var referenceLines = ["- Diagnostic ID: \(diagnosticID.uuidString.lowercased())"]
        if let operationID {
            referenceLines.append("- Installation ID: \(operationID.uuidString.lowercased())")
        }

        let facts: [(String, String?)] = [
            ("Original failure", verification.originalFailure),
            ("Cleanup failure", verification.cleanupFailure),
            ("Transport classification (mapped; native return codes are in the trace)", verification.transportClassification),
            ("Failed component", verification.artifactKind),
            ("Validated source bytes", verification.sourceSize.map(String.init)),
            ("Reported remote bytes (not proof of content verification)", verification.remoteSize.map(String.init)),
            ("Transferred bytes", verification.transferredBytes.map(String.init)),
            ("Elapsed at failure (ms)", verification.elapsedMilliseconds.map(String.init)),
            ("Verified sample bytes", verification.sampledBytes.map(String.init)),
            ("Planned samples", verification.sampleCount.map(String.init)),
            ("Matched samples", verification.matchedSampleCount.map(String.init))
        ]
        let verificationLines = facts.map { label, value in
            "- \(label): \(value.map { sanitizedLine($0, fallback: "Unavailable") } ?? "Unavailable")"
        }.joined(separator: "\n")
        let body = DiagnosticReportSanitizer.sanitize("""
        ## Summary

        - Result: FAILED
        - Failure stage: \((normalizedFailureStages.isEmpty ? [safeStage] : normalizedFailureStages).joined(separator: ", "))
        - Error category: \(sanitizedLine(errorCategory ?? "unknown", fallback: "unknown"))
        - Error code: \((normalizedErrorCodes.isEmpty ? ["UNKNOWN"] : normalizedErrorCodes).joined(separator: ", "))

        ## Device

        \(deviceLines.joined(separator: "\n"))

        ## Installation

        - Operation: Map installation
        - Provider: \(providers.isEmpty ? "Unavailable" : providers.joined(separator: ", "))
        - Region: \(regions.isEmpty ? "Unavailable" : regions.joined(separator: ", "))
        - Map version: \(releases.isEmpty ? "Unavailable" : releases.joined(separator: ", "))
        - App version: \(sanitizedLine(appVersion, fallback: TerentoTelemetryMetadata.version))
        - Build: \(sanitizedLine(appBuild, fallback: TerentoTelemetryMetadata.eventBuild))
        - macOS: \(sanitizedLine(operatingSystem, fallback: "Unavailable"))
        - Timestamp: \(ISO8601DateFormatter().string(from: timestamp))

        ## Failure details

        - Write started: \(writeStarted ? "Yes" : "No")
        - Transfer progress: \(boundedProgress)%
        - Object created: \(remoteObjectCreated ? "Yes" : "No")
        - Cleanup attempted: \(cleanupAttempted ? "Yes" : "No")
        - Cleanup succeeded: \(cleanupSucceeded ? "Yes" : "No")
        - Transport: MTP
        \(safeError.map { "- Detail: \($0)" } ?? "")

        ## Verification details

        \(verificationLines)

        ## Finishing diagnostics

        Fixed-field diagnostic sequence; raw native return codes use rc. Swift elapsed values are seconds except installation_failure, which uses milliseconds. target_matches detail is the match count; target_size detail is the reported size, with expected bytes in offset. Missing events are unavailable evidence, not success.

        \(FinishingTrace.failureReport.isEmpty ? "Unavailable" : FinishingTrace.failureReport)

        ## Reference

        \(referenceLines.joined(separator: "\n"))

        ---
        Prepared by Terento. Please review before submitting.
        """)

        var components = URLComponents(string: "https://github.com/VooZ2/terento/issues/new")!
        components.queryItems = [
            URLQueryItem(name: "template", value: "installation-failure.yml"),
            URLQueryItem(name: "title", value: title),
            URLQueryItem(name: "diagnostic-report", value: body)
        ]
        // Extended diagnostics can exceed browser/server URL limits. The complete
        // report is already copied before opening the form; never silently trim it.
        if (components.url?.absoluteString.utf8.count ?? Int.max) > 7000 {
            components.queryItems = [
                URLQueryItem(name: "template", value: "installation-failure.yml"),
                URLQueryItem(name: "title", value: title),
                URLQueryItem(name: "diagnostic-report", value: "The complete diagnostic report has been copied to your clipboard. Replace this text by pasting it here, review it, then submit.")
            ]
        }
        return InstallationIssueDraft(title: title, body: body, url: components.url!)
    }

    static func copyAndOpenGitHub(
        _ draft: InstallationIssueDraft,
        clipboard: (String) -> Void = { value in
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(value, forType: .string)
        },
        using opener: (URL) -> Bool = { NSWorkspace.shared.open($0) }
    ) -> Bool {
        clipboard(draft.body)
        return opener(draft.url)
    }

    private static func sanitizedLine(_ value: String, fallback: String) -> String {
        let sanitized = DiagnosticReportSanitizer.sanitize(value)
            .replacingOccurrences(of: "\r", with: " ")
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return sanitized.isEmpty ? fallback : String(sanitized.prefix(500))
    }

    private static func nonEmpty(_ value: String?) -> String? {
        let normalized = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return normalized.isEmpty ? nil : normalized
    }
}

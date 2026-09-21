import AppKit
import Foundation

struct InstallationIssueDraft: Equatable, Sendable {
    let title: String
    let body: String
    let url: URL
}

enum DiagnosticMapOperation: String, Sendable {
    case installation = "Map installation"
    case update = "Map update"
    case removal = "Map removal"
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
        operation: DiagnosticMapOperation = .installation,
        lifecycleFacts: [String] = [],
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
        failureContext: InstallationFailureContext? = nil,
        originalFailureContext: InstallationFailureContext? = nil,
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
                "\(operation == .installation ? "Installation" : operation.rawValue) stopped during \(safeStage) — \(primaryProvider) / \(primaryRegion)"
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
        let mapLines = reportedMaps.map { map in
            "- \(sanitizedLine(map.provider, fallback: "Unavailable")) / \(sanitizedLine(map.package, fallback: "Unavailable")): release=\(sanitizedLine(map.release ?? "Unavailable", fallback: "Unavailable")), planned installed bytes=\(map.artifactSizeBytes.map(String.init) ?? "Unavailable")"
        }.joined(separator: "\n")
        let lifecycleLines = lifecycleFacts.map { "- \(sanitizedLine($0, fallback: "Unavailable"))" }.joined(separator: "\n")
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

        ## Operation

        - Operation: \(operation.rawValue)
        - Provider: \(providers.isEmpty ? "Unavailable" : providers.joined(separator: ", "))
        - Region: \(regions.isEmpty ? "Unavailable" : regions.joined(separator: ", "))
        - Map version: \(releases.isEmpty ? "Unavailable" : releases.joined(separator: ", "))
        - App version: \(sanitizedLine(appVersion, fallback: TerentoTelemetryMetadata.version))
        - Build: \(sanitizedLine(appBuild, fallback: TerentoTelemetryMetadata.eventBuild))
        - macOS: \(sanitizedLine(operatingSystem, fallback: "Unavailable"))
        - Timestamp: \(ISO8601DateFormatter().string(from: timestamp))

        ## Map packages

        \(mapLines.isEmpty ? "Unavailable" : mapLines)

        ## Failure details

        - Write started: \(operation == .installation ? (writeStarted ? "Yes" : "No") : "Unavailable")
        - Transfer progress: \(operation == .installation ? "\(boundedProgress)%" : "Unavailable")
        - Object created: \(operation == .installation ? (remoteObjectCreated ? "Yes" : "No") : "Unavailable")
        - Cleanup attempted: \(operation == .installation ? (cleanupAttempted ? "Yes" : "No") : "Unavailable")
        - Cleanup succeeded: \(operation == .installation ? (cleanupSucceeded ? "Yes" : "No") : "Unavailable")
        - Transport: MTP
        \(safeError.map { "- Detail: \($0)" } ?? "")

        ## Verification details

        \(verificationLines)
        \(lifecycleLines)

        ## Structured failure context

        \(contextLines(failureContext))

        ## Original failure context

        \(contextLines(originalFailureContext))

        ## Finishing diagnostics

        Fixed-field diagnostic sequence; raw native return codes use rc. Swift elapsed values are seconds except installation_failure, which uses milliseconds. target_matches detail is the match count; target_size detail is the reported size, with expected bytes in offset. Missing events are unavailable evidence, not success.

        \(FinishingTrace.failureReport.isEmpty ? "Unavailable" : FinishingTrace.failureReport)

        ## Reference

        \(referenceLines.joined(separator: "\n"))

        ---
        Prepared by Terento. Please review before submitting.
        """)

        return draft(title: title, body: body)
    }

    private static func contextLines(_ context: InstallationFailureContext?) -> String {
        guard let context else { return "Unavailable" }
        let protection = context.protection
        func count(_ value: Int?) -> String? {
            guard let value, (0...16384).contains(value) else { return nil }
            return String(value)
        }
        func flag(_ value: Bool?) -> String? { value.map { $0 ? "true" : "false" } }
        let fields: [(String, String?)] = [
            ("Boundary", context.boundary.rawValue),
            ("Classification source", context.classificationSource.rawValue),
            ("Device presence", context.devicePresence.rawValue),
            ("Last successful boundary", context.lastSuccessfulBoundary?.rawValue),
            ("Operation", context.operation?.rawValue),
            ("Execution mode", context.executionMode?.rawValue),
            ("Result kind", context.resultKind?.rawValue),
            ("Native category", context.nativeCategory?.rawValue),
            ("Native code namespace", context.nativeCodeNamespace?.rawValue),
            ("Native result code", context.nativeCodeNamespace == nil ? nil : context.nativeResultCode.map(String.init)),
            ("Retry count", context.retryCount.map(String.init)),
            ("Component", context.componentKind?.rawValue),
            ("Protection boundary", protection?.protectionBoundary.rawValue),
            ("Protection reason", protection?.protectionReason.rawValue),
            ("Comparison version", protection?.stableIdentityComparisonVersion.flatMap { (1...2).contains($0) ? String($0) : nil }),
            ("Before object count", count(protection?.beforeObjectCount)),
            ("After object count", count(protection?.afterObjectCount)),
            ("Added object count", count(protection?.addedObjectCount)),
            ("Removed object count", count(protection?.removedObjectCount)),
            ("Changed object count", count(protection?.changedObjectCount)),
            ("Target present", flag(protection?.targetPresent)),
            ("Target unique", flag(protection?.targetUnique)),
            ("Target kind matches", flag(protection?.targetKindMatches)),
            ("Target filename matches", flag(protection?.targetFilenameMatches)),
            ("Target size matches", flag(protection?.targetSizeMatches)),
            ("Target path matches", flag(protection?.targetPathMatches)),
            ("Target item ID matches", flag(protection?.targetItemIDMatches))
        ]
        return fields.map { "- \($0.0): \($0.1 ?? "Unavailable")" }.joined(separator: "\n")
    }

    static func draft(title: String, body: String) -> InstallationIssueDraft {
        let safeTitle = String(DiagnosticReportSanitizer.sanitize(title).prefix(180))
        let safeBody = DiagnosticReportSanitizer.sanitize(body)
        var report = safeBody
        if issueURL(title: safeTitle, body: report).absoluteString.utf8.count > 7000 {
            report = compactReport(safeBody)
        }
        // A pathological report still has a bounded, explicitly summarized draft.
        // Keep the full sanitized report locally; never replace the form with paste instructions.
        if issueURL(title: safeTitle, body: report).absoluteString.utf8.count > 7000 {
            let lines = report.components(separatedBy: "\n")
            var retained = Set<Int>()
            let notice = "\nCompact report: additional diagnostic lines omitted; full report retained locally."
            let ordered = lines.indices.sorted { left, right in
                let lp = reportPriority(lines[left]), rp = reportPriority(lines[right])
                return lp == rp ? left < right : lp < rp
            }
            for index in ordered {
                let candidate = retained.union([index]).sorted().map { lines[$0] }.joined(separator: "\n") + notice
                if issueURL(title: safeTitle, body: candidate).absoluteString.utf8.count <= 7000 {
                    retained.insert(index)
                }
            }
            report = retained.sorted().map { lines[$0] }.joined(separator: "\n") + notice
        }
        return InstallationIssueDraft(title: safeTitle, body: safeBody,
                                      url: issueURL(title: safeTitle, body: report))
    }

    private static func issueURL(title: String, body: String) -> URL {
        var components = URLComponents(string: "https://github.com/VooZ2/terento/issues/new")!
        components.queryItems = [
            URLQueryItem(name: "title", value: title),
            URLQueryItem(name: "body", value: body)
        ]
        return components.url!
    }

    private static func compactReport(_ body: String) -> String {
        var lines: [String] = []
        var traceLegendAdded = false
        for line in body.components(separatedBy: "\n") {
            if line.isEmpty || line.hasSuffix(": Unavailable") || line.hasPrefix("Fixed-field diagnostic sequence;") { continue }
            if line.hasPrefix("FINISH_TRACE ") {
                if !traceLegendAdded {
                    lines.append("Trace: N=native event,offset,rc,detail,last_verified_end,verified_bytes; S=Swift event and fields. rc is native; elapsed seconds except installation_failure milliseconds. Remote size alone is not content verification.")
                    traceLegendAdded = true
                }
                let fields = line.split(separator: " ").dropFirst()
                if fields.first == "native" {
                    let values = fields.dropFirst().map { String($0.split(separator: "=", maxSplits: 1).last ?? $0) }
                    lines.append("N " + values.joined(separator: ","))
                } else {
                    lines.append("S " + fields.dropFirst().joined(separator: " ").replacingOccurrences(of: "event=", with: ""))
                }
            } else {
                lines.append(line.replacingOccurrences(of: "Transport classification (mapped; native return codes are in the trace)", with: "Mapped transport classification")
                    .replacingOccurrences(of: "Reported remote bytes (not proof of content verification)", with: "Reported remote bytes"))
            }
        }
        return lines.joined(separator: "\n")
    }

    private static func reportPriority(_ line: String) -> Int {
        if line.hasPrefix("Trace:") || line.contains("read_failed") || line.contains("read_ptp_response")
            || line.contains("read_error_code") || line.contains("Original failure:")
            || line.contains("Error code:") || line.contains("Diagnostic ID:")
            || line.contains("Installation ID:") || line.contains("Boundary:")
            || line.contains("Classification source:") || line.contains("Device presence:")
            || line.contains("Protection reason:") { return 0 }
        if !line.hasPrefix("N ") && !line.hasPrefix("S ") { return 1 }
        if line.contains("failed") || line.contains("failure") || line.contains("cleanup")
            || line.contains("deadline") || line.contains("retry_close") { return 2 }
        return 3
    }

    static func openGitHub(
        _ draft: InstallationIssueDraft,
        using opener: (URL) -> Bool = { NSWorkspace.shared.open($0) }
    ) -> Bool {
        opener(draft.url)
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

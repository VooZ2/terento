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
        diagnosticID: UUID = UUID(),
        timestamp: Date = Date(),
        appVersion: String = (Bundle.main.infoDictionary?["TerentoReleaseLabel"] as? String)
            ?? (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String)
            ?? "development",
        appBuild: String = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "development",
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
        - App version: \(sanitizedLine(appVersion, fallback: "development"))
        - Build: \(sanitizedLine(appBuild, fallback: "development"))
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

import AppKit
import Foundation

@MainActor
enum InstallationIssueReport {
    static func generate(
        identity: DeviceIdentity?,
        packages: [MapPackage],
        phase: InstallationProcessPhase,
        error: String?
    ) -> String {
        let rawLog = (try? String(contentsOf: TerentoDiagnosticLog.fileURL, encoding: .utf8)) ?? "Log unavailable."
        let details = [
            "Terento version: \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "development")",
            "macOS: \(ProcessInfo.processInfo.operatingSystemVersionString)",
            "Device model: \(identity?.canonicalModel ?? identity?.model ?? "unknown")",
            "Firmware: \(identity?.firmware ?? "unknown")",
            "Map region: \(packages.map(\.canonicalRegionId).joined(separator: ", "))",
            "Installation phase: \(phase.rawValue)",
            "Error summary: \(error ?? "unknown")"
        ].joined(separator: "\n")
        return DiagnosticReportSanitizer.sanitize("""
        ## Installation failure

        \(details)

        ## Sanitized log

        ```text
        \(rawLog)
        ```
        """)
    }

    static func copyAndOpenGitHub(_ report: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(report, forType: .string)
        var components = URLComponents(string: "https://github.com/VooZ2/terento/issues/new")!
        components.queryItems = [
            URLQueryItem(name: "template", value: "installation-failure.yml"),
            URLQueryItem(name: "title", value: "Installation failed: "),
            URLQueryItem(name: "body", value: "Paste the diagnostic report copied by Terento here, review it, then submit.")
        ]
        if let url = components.url { NSWorkspace.shared.open(url) }
    }
}

import AppKit
import Foundation

/// Small, user-retrievable diagnostics for beta failures. The log is local to
/// the Mac and contains operation state, not map binaries or credentials.
@MainActor
enum TerentoDiagnosticLog {
    static let fileURL: URL = {
        let libraryURL = FileManager.default.urls(
            for: .libraryDirectory,
            in: .userDomainMask
        ).first ?? FileManager.default.homeDirectoryForCurrentUser

        return libraryURL
            .appendingPathComponent("Logs", isDirectory: true)
            .appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("log.txt")
    }()

    static func recordInstallationStarted(maps: [MapPackage]) {
        let mapLines = maps.map { map in
            "- \(map.name) [\(map.id), region=\(map.regionId), release=\(map.version)]"
        }

        append([
            "INSTALLATION STARTED",
            "App version: \(appVersion)",
            "macOS: \(ProcessInfo.processInfo.operatingSystemVersionString)",
            "Selected maps:",
            mapLines.isEmpty ? "- none" : mapLines.joined(separator: "\n")
        ].joined(separator: "\n"))
    }

    static func recordInstallationFailure(
        maps: [MapPackage],
        phase: InstallationProcessPhase,
        engineState: MapEngineState,
        acquisitionState: MapAcquisitionState,
        message: String?,
        technicalError: String?,
        acquisitionError: String?,
        preflight: InstallationPreflightResult?,
        result: MapInstallationResult?,
        inventory: MapInventoryResult?
    ) {
        var lines = [
            "INSTALLATION FAILED",
            "Time: \(Self.timestamp())",
            "App version: \(appVersion)",
            "macOS: \(ProcessInfo.processInfo.operatingSystemVersionString)",
            "Phase: \(phase.rawValue)",
            "Engine state: \(String(describing: engineState))",
            "Acquisition state: \(acquisitionState.rawValue)",
            "Error: \(message ?? "No user-facing error was produced.")"
        ]

        if let technicalError, technicalError != message {
            lines.append("Technical error: \(technicalError)")
        }

        if let acquisitionError, acquisitionError != message {
            lines.append("Acquisition error: \(acquisitionError)")
        }

        if let preflight {
            lines.append("Preflight map: \(preflight.selectedMap.id) [region=\(preflight.selectedMap.regionId)]")
            lines.append("Preflight status: \(preflight.status.rawValue)")
            lines.append("Preflight reason: \(preflight.reason)")
            lines.append("Install target: \(preflight.installTarget ?? "none")")
            lines.append("Proposed filename: \(preflight.proposedFilename ?? "none")")
        }

        if let result {
            lines.append("Installation result: \(result.status.rawValue)")
            lines.append("Installation failure: \(result.failure?.rawValue ?? "none")")
            lines.append("Remote object exists: \(result.diagnostics.remoteObjectExists)")
            lines.append("Bytes transferred: \(result.diagnostics.bytesTransferred)/\(result.diagnostics.transferTotalBytes)")
            lines.append("Target path: \(result.diagnostics.targetPath ?? "none")")
            if let metadataWarning = result.diagnostics.metadataWarning {
                lines.append("Metadata warning: \(metadataWarning)")
            }
        }

        if let inventory {
            lines.append("Scanned Freizeitkarte maps:")
            if inventory.scan.installedMaps.isEmpty {
                lines.append("- none")
            } else {
                lines.append(contentsOf: inventory.scan.installedMaps.map { map in
                    let objectID = map.sourceFile.itemID.map(String.init) ?? "none"
                    return "- \(map.sourceFile.path) [object=\(objectID), bytes=\(map.sourceFile.sizeBytes), provider=\(map.provider ?? "unknown"), region=\(map.region ?? "unknown"), version=\(map.version?.description ?? "unknown"), ownership=\(map.managementState.rawValue)]"
                })
            }
        }

        lines.append("Selected map IDs: \(maps.map(\.id).joined(separator: ", "))")
        append(lines.joined(separator: "\n"))
    }

    static func revealLog() {
        let directoryURL = fileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(
            at: directoryURL,
            withIntermediateDirectories: true
        )

        if FileManager.default.fileExists(atPath: fileURL.path) {
            NSWorkspace.shared.activateFileViewerSelecting([fileURL])
        } else {
            NSWorkspace.shared.open(directoryURL)
        }
    }

    private static var appVersion: String {
        Bundle.main.object(
            forInfoDictionaryKey: "CFBundleShortVersionString"
        ) as? String ?? "development"
    }

    private static func timestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    private static func append(_ entry: String) {
        let directoryURL = fileURL.deletingLastPathComponent()
        do {
            try FileManager.default.createDirectory(
                at: directoryURL,
                withIntermediateDirectories: true
            )

            let block = "\n=== \(timestamp()) ===\n\(entry)\n"
            let data = Data(block.utf8)
            if FileManager.default.fileExists(atPath: fileURL.path) {
                let handle = try FileHandle(forWritingTo: fileURL)
                try handle.seekToEnd()
                try handle.write(contentsOf: data)
                try handle.close()
            } else {
                try data.write(to: fileURL, options: .atomic)
            }
        } catch {
            // Diagnostics must never change the installation result.
        }
    }
}

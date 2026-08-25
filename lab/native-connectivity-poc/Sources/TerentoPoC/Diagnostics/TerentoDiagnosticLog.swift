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
            "- \(map.name) [\(map.id), region=\(map.canonicalRegionId), release=\(map.version)]"
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
            lines.append("Preflight map: \(preflight.selectedMap.id) [region=\(preflight.selectedMap.canonicalRegionId)]")
            lines.append("Preflight status: \(preflight.status.rawValue)")
            lines.append("Preflight reason: \(preflight.reason)")
            lines.append("Install target: \(preflight.installTarget ?? "none")")
            lines.append("Proposed filename: \(preflight.proposedFilename ?? "none")")
        }

        if let result {
            lines.append("Installation result: \(result.status.rawValue)")
            lines.append("Installation failure: \(result.failure?.rawValue ?? "none")")
            lines.append("Remote object exists: \(result.diagnostics.remoteObjectExists)")
            lines.append("Source IMG bytes: \(result.diagnostics.sourceSizeBytes)")
            lines.append("Transfer callback bytes: \(result.diagnostics.bytesTransferred)/\(result.diagnostics.transferTotalBytes)")
            lines.append("Remote object bytes: \(result.diagnostics.remoteSizeBytes.map(String.init) ?? "none")")
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

    static func recordCompatibilityReportDeliveryFailure(
        reportIDs: [UUID],
        error: Error,
        willRetry: Bool,
        pendingCount: Int
    ) {
        let details = compatibilityReportErrorDetails(error)
        append([
            "COMPATIBILITY REPORT DELIVERY FAILED",
            "Time: \(Self.timestamp())",
            "App version: \(appVersion)",
            "Schema version: \(InstallationEvidenceEvent.schemaVersion)",
            "Local report IDs: \(reportIDs.map { $0.uuidString.lowercased() }.joined(separator: ", "))",
            "Pending report count: \(pendingCount)",
            "Retry scheduled: \(willRetry)",
            "Failure category: \(details.category)",
            "HTTP status: \(details.httpStatus)",
            "Backend payload: \(details.backendPayload)",
            "Technical detail: \(details.technicalDetail)"
        ].joined(separator: "\n"))
    }

    /// Records the complete read-only inventory used to build Install maps
    /// and Manage maps. This is intentionally metadata-only: it never reads
    /// or stores map bytes. The inventory is needed to distinguish a stale UI
    /// value from an IMG object that is still returned by the device.
    static func recordMapInventoryScan(
        _ inventory: MapInventoryResult,
        trigger: String
    ) {
        var lines = [
            "MAP INVENTORY SCAN",
            "Time: \(Self.timestamp())",
            "App version: \(appVersion)",
            "Trigger: \(trigger)",
            "Device files: \(inventory.deviceFiles.count)",
            "Inspected map files: \(inventory.scan.files.count)",
            "Freizeitkarte maps: \(inventory.scan.installedMaps.count)",
            "Other maps: \(inventory.scan.otherMaps.count)",
            "Parsing failures: \(inventory.scan.parsingFailures)",
            "Skipped Garmin-owned files: \(inventory.scan.skippedNonFreizeitkarteFiles)",
            "Device file inventory:"
        ]

        if inventory.deviceFiles.isEmpty {
            lines.append("- none")
        } else {
            lines.append(contentsOf: inventory.deviceFiles.map { file in
                "- \(file.path) [object=\(file.itemID), bytes=\(file.sizeBytes), folder=\(file.isFolder)]"
            })
        }

        lines.append("Scanned Freizeitkarte maps:")
        if inventory.scan.installedMaps.isEmpty {
            lines.append("- none")
        } else {
            lines.append(contentsOf: inventory.scan.installedMaps.map { map in
                let objectID = map.sourceFile.itemID.map(String.init) ?? "none"
                return "- \(map.sourceFile.path) [object=\(objectID), bytes=\(map.sourceFile.sizeBytes), provider=\(map.provider ?? "unknown"), region=\(map.region ?? "unknown"), version=\(map.version?.description ?? "unknown"), ownership=\(map.managementState.rawValue)]"
            })
        }

        lines.append("Scanned other maps:")
        if inventory.scan.otherMaps.isEmpty {
            lines.append("- none")
        } else {
            lines.append(contentsOf: inventory.scan.otherMaps.map { map in
                let objectID = map.sourceFile.itemID.map(String.init) ?? "none"
                return "- \(map.sourceFile.path) [object=\(objectID), bytes=\(map.sourceFile.sizeBytes), provider=\(map.provider ?? "unknown"), region=\(map.region ?? "unknown"), version=\(map.version?.description ?? "unknown")]"
            })
        }

        append(lines.joined(separator: "\n"))
    }

    @discardableResult
    static func revealLog() -> Bool {
        let directoryURL = fileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(
            at: directoryURL,
            withIntermediateDirectories: true
        )

        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return false
        }

        // Let macOS open the local .txt file with its normal default viewer.
        return NSWorkspace.shared.open(fileURL)
    }

    private static var appVersion: String {
        Bundle.main.object(
            forInfoDictionaryKey: "CFBundleShortVersionString"
        ) as? String ?? "development"
    }

    private static func timestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    private static func compatibilityReportErrorDetails(_ error: Error) -> (
        category: String,
        httpStatus: String,
        backendPayload: String,
        technicalDetail: String
    ) {
        if let uploadError = error as? InstallationEvidenceUploadError {
            switch uploadError {
            case .invalidResponse:
                return (
                    category: "invalid_response",
                    httpStatus: "not available",
                    backendPayload: "not available",
                    technicalDetail: "The service did not return an HTTP response."
                )
            case let .httpStatus(code, body):
                let payload = DiagnosticReportSanitizer.sanitize(
                    body.isEmpty ? "[empty]" : body
                )
                return (
                    category: code >= 500 || code == 408 || code == 425 || code == 429
                        ? "temporary_service_failure"
                        : "http_response_failure",
                    httpStatus: String(code),
                    backendPayload: payload,
                    technicalDetail: "The compatibility service rejected the request."
                )
            }
        }

        if let urlError = error as? URLError {
            return (
                category: "network",
                httpStatus: "not available",
                backendPayload: "not available",
                technicalDetail: DiagnosticReportSanitizer.sanitize(urlError.localizedDescription)
            )
        }

        return (
            category: "local_or_unknown",
            httpStatus: "not available",
            backendPayload: "not available",
            technicalDetail: DiagnosticReportSanitizer.sanitize(error.localizedDescription)
        )
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

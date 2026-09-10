import AppKit
import Foundation

struct MTPRunningApplication {
    let bundleIdentifier: String?
    let displayName: String?
    var isRegularApplication: Bool = true
}

/// Read-only, local diagnostics for applications that are known to compete for
/// a camera/PTP/MTP USB interface. A running application is only a candidate:
/// macOS does not expose the actual interface owner through NSWorkspace.
enum MTPConnectionConflictDiagnostics {
    private struct Candidate {
        let exactBundleIdentifiers: Set<String>
        let exactNames: Set<String>
        let bundleIdentifierFragments: [String]
        let namePrefixes: [String]
    }

    private static let candidates = [
        Candidate(
            exactBundleIdentifiers: ["com.garmin.renu.client"],
            exactNames: ["garmin express"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: [],
            exactNames: ["openmtp"],
            bundleIdentifierFragments: ["openmtp"],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: [],
            exactNames: ["macdroid"],
            bundleIdentifierFragments: ["macdroid"],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: [],
            exactNames: ["android file transfer"],
            bundleIdentifierFragments: ["androidfiletransfer"],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: ["com.apple.imagecapture"],
            exactNames: ["image capture"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: ["com.apple.preview"],
            exactNames: ["preview"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: ["com.apple.photos"],
            exactNames: ["photos"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            exactBundleIdentifiers: [],
            exactNames: ["lightroom"],
            bundleIdentifierFragments: ["adobe.lightroom"],
            namePrefixes: ["adobe lightroom", "lightroom classic"]
        )
    ]

    static func runningApplicationNames() -> [String] {
        detectedApplicationNames(
            NSWorkspace.shared.runningApplications.map {
                MTPRunningApplication(
                    bundleIdentifier: $0.bundleIdentifier,
                    displayName: $0.localizedName,
                    isRegularApplication: $0.activationPolicy == .regular
                )
            }
        )
    }

    static func detectedApplicationNames(_ applications: [MTPRunningApplication]) -> [String] {
        // An app extension can survive after its parent has quit. Do not turn
        // that into a claim that the main app is running. Labels come from the
        // actual running application, never from the candidate recognition list.
        let names = applications.compactMap { application -> String? in
            guard application.isRegularApplication,
                  let name = application.displayName?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !name.isEmpty else { return nil }
            let bundleIdentifier = normalize(application.bundleIdentifier)
            let displayName = normalize(name)
            let recognized = candidates.contains { candidate in
                candidate.exactBundleIdentifiers.contains(bundleIdentifier)
                    || candidate.exactNames.contains(displayName)
                    || candidate.bundleIdentifierFragments.contains {
                        !bundleIdentifier.isEmpty && bundleIdentifier.contains($0)
                    }
                    || candidate.namePrefixes.contains { displayName.hasPrefix($0) }
            }
            return recognized ? name : nil
        }
        return Array(Set(names)).sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    private static func normalize(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    }
}

enum UserFacingErrorMessage {
    static func forConnectionTimeout(
        garminUSBPresent: Bool,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> String {
        guard garminUSBPresent else {
            return "We couldn't connect to your Garmin within 2 minutes. Reconnect it and try again."
        }
        guard !detectedConflicts.isEmpty else {
            return "Your Garmin was detected, but the connection did not become ready within 2 minutes. Reconnect it and try again."
        }
        return usbConflictMessage(detectedConflicts: detectedConflicts)
    }

    static func forDevice(
        _ error: Error,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> String {
        let message = error.localizedDescription.lowercased()

        if message.contains("no mtp device") || message.contains("no garmin") {
            return "No Garmin watch was found. Connect it and try again."
        }

        if message.contains("more than one garmin") {
            return "More than one Garmin device is connected. Leave only one connected and try again."
        }

        if isBusyConnectionError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts)
        }

        if message.contains("storage") {
            return "The watch connected, but it was not ready yet. Reconnect it and try again."
        }

        return "The Garmin watch could not be connected. Reconnect it and try again."
    }

    static func forMapScan(
        _ error: Error,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> String {
        let message = error.localizedDescription.lowercased()

        if message.contains("no mtp device") || message.contains("no garmin") {
            return "The Garmin watch was disconnected while reading its maps. Reconnect it and try again."
        }

        if isBusyConnectionError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts)
        }

        if message.contains("catalog") || message.contains("metadata") {
            return "Map information is temporarily unavailable. Choose Refresh and try again."
        }

        return "The watch's installed maps could not be read. Reconnect it and try again."
    }

    static func forInstallation(
        _ error: Error,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> String {
        let message = error.localizedDescription.lowercased()
        if message.contains("no mtp device")
            || message.contains("no garmin")
            || message.contains("disconnect") {
            return "The Garmin watch disconnected. Reconnect it, refresh its maps, and try again."
        }
        if message.contains("space") || message.contains("storage") {
            return "There is not enough available storage to install this map safely."
        }
        if isBusyConnectionError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts)
        }
        return "The map could not be installed safely. Reconnect the watch, refresh its maps, and try again."
    }

    private static func isBusyConnectionError(_ message: String) -> Bool {
        // A failed read/session is not evidence that another app owns USB.
        // Only an explicit busy/claim result can support this suggestion.
        message.contains("libusb_error_busy")
            || message.contains("resource busy")
            || message.contains("already opened for exclusive access")
            || message.contains("libusb_claim_interface() = -6")
    }

    private static func usbConflictMessage(detectedConflicts: [String]) -> String {
        guard !detectedConflicts.isEmpty else {
            return "Reconnect your Garmin and try connecting again."
        }
        return "Close \(joinedNames(detectedConflicts)) and try connecting again."
    }

    private static func joinedNames(_ names: [String]) -> String {
        switch names.count {
        case 0:
            return ""
        case 1:
            return names[0]
        case 2:
            return "\(names[0]) and \(names[1])"
        default:
            return names.dropLast().joined(separator: ", ") + ", and " + names[names.count - 1]
        }
    }
}

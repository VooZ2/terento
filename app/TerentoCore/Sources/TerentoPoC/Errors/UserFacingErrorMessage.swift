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
    ]
    // Preview, Photos and Lightroom are not listed: they only claim a device
    // while their own import window is open, so "Close Preview" merely
    // because it is running would be wrong advice.

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

/// What the Connect page shows after a detection episode ends without a
/// connection: the cause as the title, one sentence of reason, then numbered
/// steps. The last step says how to retry, because detection resumes only
/// after the watch is reconnected or Try again is clicked.
struct ConnectFailureMessage: Equatable, Sendable {
    let title: String
    let reason: String
    let steps: [String]

    /// The reason followed by the numbered steps, as one plain text.
    var text: String {
        ([reason] + steps.enumerated().map { "\($0.offset + 1). \($0.element)" })
            .joined(separator: "\n")
    }
}

enum UserFacingErrorMessage {
    /// Final message after a detection episode ends without a connection.
    static func forDetectionFailure(
        _ outcome: DeviceConnectOutcome,
        garminUSBPresent: Bool,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> String {
        detectionFailure(outcome, garminUSBPresent: garminUSBPresent, detectedConflicts: detectedConflicts).text
    }

    /// Cause-specific title, reason and steps for a final detection failure.
    /// Only BUSY and a timeout with the watch on USB name a detected app.
    static func detectionFailure(
        _ outcome: DeviceConnectOutcome,
        garminUSBPresent: Bool,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> ConnectFailureMessage {
        switch outcome {
        case .busy:
            return ConnectFailureMessage(
                title: "Another app may be using your watch",
                reason: "Terento couldn't open the connection to your watch, and only one app at a time can use it.",
                steps: [
                    detectedConflicts.isEmpty
                        ? "Quit Garmin Express and other apps that connect to your watch."
                        : "Quit \(joinedNames(detectedConflicts)).",
                    reconnectStep
                ]
            )
        case .multipleDevices:
            return ConnectFailureMessage(
                title: "More than one Garmin is connected",
                reason: "Terento works with one Garmin at a time.",
                steps: [
                    "Unplug every other Garmin device, such as other watches, bike computers or handheld devices.",
                    reconnectStep
                ]
            )
        case .notMTPMode:
            return ConnectFailureMessage(
                title: "Your watch isn't ready for file transfer",
                reason: "Your Garmin is connected, but it didn't switch to file transfer within 2 minutes.",
                steps: [
                    "Unlock the watch.",
                    usbModeStep,
                    reconnectStep
                ]
            )
        case .failed:
            return ConnectFailureMessage(
                title: "Your watch stopped responding",
                reason: "The watch stopped answering while Terento was checking it.",
                steps: [
                    "Unplug the watch and wait 5 seconds.",
                    "If this keeps happening, restart the watch.",
                    connectAgainStep
                ]
            )
        case .disconnected:
            return ConnectFailureMessage(
                title: "Your watch was disconnected",
                reason: "The connection to your watch ended before it was ready.",
                steps: [
                    "Check that the cable is firmly plugged in at both ends.",
                    connectAgainStep
                ]
            )
        case .timeoutNoUSB:
            return ConnectFailureMessage(
                title: "Your watch isn't showing up",
                reason: "Terento can't find your Garmin on this Mac.",
                steps: [
                    "Use a USB data cable, not a charge-only cable.",
                    "Plug it directly into the Mac, not into a USB hub, and unlock the watch.",
                    connectAgainStep
                ]
            )
        case .timeoutUSBPresent, .connected:
            return connectionTimeout(garminUSBPresent: garminUSBPresent, detectedConflicts: detectedConflicts)
        }
    }

    /// Shown when a bounded device read reaches its deadline.
    static let stoppedResponding = "The watch stopped responding. Unplug it, wait 5 seconds, plug it back in."

    /// The watch's USB Mode setting, worded like the guide's #usb-mode section.
    /// "MTP" appears only as the value to choose.
    static let usbModeStep = "On the watch, open USB Mode, usually under Settings › System, and choose MTP. Not every model has this setting; if yours doesn't, skip this step."

    private static let retryNote = "Terento doesn't check again until you do."
    private static let reconnectStep = "Then unplug the watch and connect it again, or click Try again. \(retryNote)"
    private static let connectAgainStep = "Then connect the watch again, or click Try again. \(retryNote)"

    /// Live title and description while detection keeps polling. Only BUSY
    /// reads the running applications, and only when it is shown.
    static func detectionAttention(
        _ outcome: DeviceConnectOutcome,
        detectedConflicts: @autoclosure () -> [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> (title: String, description: String)? {
        switch outcome {
        case .multipleDevices:
            return ("More than one Garmin connected",
                    "Unplug the other Garmin devices. Terento continues as soon as only your watch is connected.")
        case .busy:
            let conflicts = detectedConflicts()
            let quit = conflicts.isEmpty
                ? "Quit Garmin Express and similar apps."
                : "Quit \(joinedNames(conflicts))."
            return ("Your Garmin is busy",
                    "Another app may be using your watch. \(quit) Terento connects automatically when the watch is free.")
        case .notMTPMode:
            return ("Your Garmin isn't ready yet",
                    "Unlock the watch. If your model has USB Mode, usually under Settings › System, choose MTP. Terento keeps checking.")
        case .connected, .timeoutNoUSB, .timeoutUSBPresent, .disconnected, .failed:
            return nil
        }
    }

    static func forConnectionTimeout(
        garminUSBPresent: Bool,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> String {
        connectionTimeout(garminUSBPresent: garminUSBPresent, detectedConflicts: detectedConflicts).text
    }

    /// A Garmin was on USB during the connection window. Without USB at the
    /// end, it dropped off before it was ready. A detected app is named only
    /// while the watch is on USB; the replug step is kept either way.
    static func connectionTimeout(
        garminUSBPresent: Bool,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> ConnectFailureMessage {
        guard garminUSBPresent else {
            return ConnectFailureMessage(
                title: "Your watch disconnected before it was ready",
                reason: "Terento found your Garmin, but the connection dropped before it became ready.",
                steps: [
                    "Check that the cable is firmly plugged in at both ends.",
                    "Try another USB port or cable, plugged directly into the Mac.",
                    connectAgainStep
                ]
            )
        }
        let replug = "Then unplug the watch, wait 5 seconds and connect it again, or click Try again. \(retryNote)"
        let steps = detectedConflicts.isEmpty
            ? [
                "Unlock the watch.",
                "Try another USB port or cable, plugged directly into the Mac.",
                "If this keeps happening, restart the watch.",
                replug
            ]
            : [
                "Quit \(joinedNames(detectedConflicts)), which may be using the watch.",
                "Unlock the watch.",
                replug
            ]
        return ConnectFailureMessage(
            title: "Your watch was detected but didn't get ready",
            reason: "Terento found your Garmin, but it didn't become ready within 2 minutes.",
            steps: steps
        )
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

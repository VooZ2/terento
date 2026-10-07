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

/// One line in a Connect help box: an SF Symbol already used on the Connect
/// page and a short instruction.
struct ConnectStep: Equatable, Sendable {
    let systemImage: String
    let text: String
}

/// A connection problem on the Connect page, in the calm "Still not showing
/// up?" style: the cause as the title (one heading line at the minimum window
/// width), one short sentence saying what is wrong, then a light box that
/// leads with what Terento found, lists the steps with icons, links the guide
/// and ends with what Terento does meanwhile. A final failure's last step and
/// note say how to retry, because detection resumes only after the watch is
/// reconnected or Try again is clicked.
struct ConnectIssueMessage: Equatable, Sendable {
    /// The outcome the message explains; it selects the guide section.
    let outcome: DeviceConnectOutcome
    let title: String
    /// One short sentence: what is wrong.
    let reason: String
    /// What Terento found; the box's first line.
    let finding: String
    let steps: [ConnectStep]
    /// What Terento does meanwhile, or what makes it check again.
    let note: String

    /// The message as plain text: reason, finding, numbered steps and note.
    var text: String {
        ([reason, finding] + steps.enumerated().map { "\($0.offset + 1). \($0.element.text)" } + [note])
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

    /// The cause-specific message for a final detection failure. Only BUSY
    /// and a timeout with the watch on USB name a detected app.
    static func detectionFailure(
        _ outcome: DeviceConnectOutcome,
        garminUSBPresent: Bool,
        detectedConflicts: [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> ConnectIssueMessage {
        switch outcome {
        case .busy:
            return ConnectIssueMessage(
                outcome: .busy,
                title: "Your watch may be in use",
                reason: "Another app may be using your watch.",
                finding: busyFinding(detectedConflicts),
                steps: [
                    ConnectStep(systemImage: "xmark.app", text: detectedConflicts.isEmpty
                        ? "Quit Garmin Express and other apps that connect to your watch"
                        : "Quit \(joinedNames(detectedConflicts))"),
                    reconnectStep
                ],
                note: retryNote
            )
        case .multipleDevices:
            return ConnectIssueMessage(
                outcome: .multipleDevices,
                title: "More than one Garmin",
                reason: "Terento works with one Garmin at a time.",
                finding: "More than one Garmin is plugged in",
                steps: [
                    ConnectStep(systemImage: "cable.connector", text: "Unplug every other Garmin device"),
                    reconnectStep
                ],
                note: retryNote
            )
        case .notMTPMode:
            return ConnectIssueMessage(
                outcome: .notMTPMode,
                title: "Not ready for file transfer",
                reason: "Your watch didn't switch to file transfer within 2 minutes.",
                finding: notOfferingFileTransfer,
                steps: [unlockStep, usbModeStep, reconnectStep],
                note: retryNote
            )
        case .failed:
            return ConnectIssueMessage(
                outcome: .failed,
                title: "Your watch stopped responding",
                reason: "The watch stopped answering while Terento was checking it.",
                finding: "Your watch didn't answer for about 90 seconds",
                steps: [
                    ConnectStep(systemImage: "cable.connector", text: "Unplug the watch and wait 5 seconds"),
                    restartStep,
                    connectAgainStep
                ],
                note: retryNote
            )
        case .disconnected:
            return ConnectIssueMessage(
                outcome: .disconnected,
                title: "Your watch was disconnected",
                reason: "The connection ended before your watch was ready.",
                finding: "Your Garmin is no longer plugged in",
                steps: [cableStep, connectAgainStep],
                note: retryNote
            )
        case .timeoutNoUSB:
            return ConnectIssueMessage(
                outcome: .timeoutNoUSB,
                title: "Your watch isn't showing up",
                reason: "Terento can't find your Garmin on this Mac.",
                finding: "No Garmin is plugged in to this Mac",
                steps: [
                    ConnectStep(systemImage: "cable.connector", text: "Use a USB data cable, not a charge-only cable"),
                    ConnectStep(systemImage: "desktopcomputer", text: "Plug it directly into the Mac, not into a USB hub"),
                    unlockStep,
                    connectAgainStep
                ],
                note: retryNote
            )
        case .timeoutUSBPresent, .connected:
            return connectionTimeout(garminUSBPresent: garminUSBPresent, detectedConflicts: detectedConflicts)
        }
    }

    /// Shown when a bounded device read reaches its deadline.
    static let stoppedResponding = "The watch stopped responding. Unplug it, wait 5 seconds, plug it back in."

    /// The watch's USB Mode setting, hedged like the guide's #usb-mode section
    /// (usually under Settings › System; not every model has it). "MTP"
    /// appears only as the value to choose.
    static let usbModeStep = ConnectStep(
        systemImage: "gearshape",
        text: "If your watch has USB Mode (usually under Settings › System), choose MTP"
    )

    /// After a final failure, detection resumes only on a replug or Try again.
    static let retryNote = "Terento checks again only after you reconnect or click Try again."

    private static let notOfferingFileTransfer = "Your Garmin is plugged in but isn't offering file transfer"
    private static let unlockStep = ConnectStep(systemImage: "lock.open", text: "Unlock the watch")
    private static let restartStep = ConnectStep(systemImage: "arrow.clockwise", text: "If it keeps happening, restart the watch")
    private static let cableStep = ConnectStep(systemImage: "cable.connector",
                                               text: "Check that the cable is firmly plugged in at both ends")
    private static let otherPortStep = ConnectStep(systemImage: "cable.connector",
                                                   text: "Try another USB port or cable, plugged directly into the Mac")
    private static let reconnectStep = ConnectStep(systemImage: "arrow.triangle.2.circlepath",
                                                   text: "Unplug the watch and connect it again, or click Try again")
    private static let replugAfterWaitStep = ConnectStep(systemImage: "arrow.triangle.2.circlepath",
                                                         text: "Unplug for 5 seconds, then reconnect or click Try again")
    private static let connectAgainStep = ConnectStep(systemImage: "arrow.triangle.2.circlepath",
                                                      text: "Connect the watch again, or click Try again")

    private static func busyFinding(_ conflicts: [String]) -> String {
        conflicts.isEmpty
            ? "Only one app at a time can use the watch"
            : "\(joinedNames(conflicts)) \(conflicts.count == 1 ? "is" : "are") open"
    }

    /// The live message while detection keeps polling. Only BUSY reads the
    /// running applications, and only when it is shown.
    static func detectionAttention(
        _ outcome: DeviceConnectOutcome,
        detectedConflicts: @autoclosure () -> [String] = MTPConnectionConflictDiagnostics.runningApplicationNames()
    ) -> ConnectIssueMessage? {
        switch outcome {
        case .multipleDevices:
            return ConnectIssueMessage(
                outcome: .multipleDevices,
                title: "More than one Garmin found",
                reason: "Terento works with one Garmin at a time.",
                finding: "More than one Garmin is plugged in",
                steps: [ConnectStep(systemImage: "cable.connector", text: "Unplug the other Garmin devices")],
                note: "Terento continues as soon as only your watch is connected."
            )
        case .busy:
            let conflicts = detectedConflicts()
            return ConnectIssueMessage(
                outcome: .busy,
                title: "Your Garmin is busy",
                reason: "Another app may be using your watch.",
                finding: busyFinding(conflicts),
                steps: [ConnectStep(systemImage: "xmark.app", text: conflicts.isEmpty
                    ? "Quit Garmin Express and similar apps"
                    : "Quit \(joinedNames(conflicts))")],
                note: "Terento connects automatically when the watch is free."
            )
        case .notMTPMode:
            return ConnectIssueMessage(
                outcome: .notMTPMode,
                title: "Your Garmin isn't ready yet",
                reason: "Your watch hasn't switched to file transfer yet.",
                finding: notOfferingFileTransfer,
                steps: [unlockStep, usbModeStep],
                note: "Terento keeps checking while you try these."
            )
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
    ) -> ConnectIssueMessage {
        guard garminUSBPresent else {
            return ConnectIssueMessage(
                outcome: .timeoutUSBPresent,
                title: "Your watch lost connection",
                reason: "The connection dropped before your watch was ready.",
                finding: "Your Garmin was found, then disconnected",
                steps: [cableStep, otherPortStep, connectAgainStep],
                note: retryNote
            )
        }
        let named = !detectedConflicts.isEmpty
        return ConnectIssueMessage(
            outcome: .timeoutUSBPresent,
            title: "Your watch didn't get ready",
            reason: "The connection didn't become ready within 2 minutes.",
            finding: named
                ? "\(joinedNames(detectedConflicts)) \(detectedConflicts.count == 1 ? "is" : "are") open and may be using the watch"
                : "Your Garmin is plugged in to this Mac",
            steps: named
                ? [ConnectStep(systemImage: "xmark.app", text: "Quit \(joinedNames(detectedConflicts))"),
                   unlockStep, replugAfterWaitStep]
                : [unlockStep, otherPortStep, restartStep, replugAfterWaitStep],
            note: retryNote
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

import AppKit
import Foundation

struct MTPRunningApplication {
    let bundleIdentifier: String?
    let displayName: String?
}

/// Read-only, local diagnostics for applications that are known to compete for
/// a camera/PTP/MTP USB interface. A running application is only a candidate:
/// macOS does not expose the actual interface owner through NSWorkspace.
enum MTPConnectionConflictDiagnostics {
    private struct Candidate {
        let displayName: String
        let exactBundleIdentifiers: Set<String>
        let exactNames: Set<String>
        let bundleIdentifierFragments: [String]
        let namePrefixes: [String]
    }

    private static let candidates = [
        Candidate(
            displayName: "Garmin Express",
            exactBundleIdentifiers: ["com.garmin.renu.client"],
            exactNames: ["garmin express"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            displayName: "OpenMTP",
            exactBundleIdentifiers: [],
            exactNames: ["openmtp"],
            bundleIdentifierFragments: ["openmtp"],
            namePrefixes: []
        ),
        Candidate(
            displayName: "MacDroid",
            exactBundleIdentifiers: [],
            exactNames: ["macdroid"],
            bundleIdentifierFragments: ["macdroid"],
            namePrefixes: []
        ),
        Candidate(
            displayName: "Android File Transfer",
            exactBundleIdentifiers: [],
            exactNames: ["android file transfer"],
            bundleIdentifierFragments: ["androidfiletransfer"],
            namePrefixes: []
        ),
        Candidate(
            displayName: "Image Capture",
            exactBundleIdentifiers: ["com.apple.imagecapture"],
            exactNames: ["image capture"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            displayName: "Preview",
            exactBundleIdentifiers: ["com.apple.preview"],
            exactNames: ["preview"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            displayName: "Photos",
            exactBundleIdentifiers: ["com.apple.photos"],
            exactNames: ["photos"],
            bundleIdentifierFragments: [],
            namePrefixes: []
        ),
        Candidate(
            displayName: "Adobe Lightroom",
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
                    displayName: $0.localizedName
                )
            }
        )
    }

    static func detectedApplicationNames(_ applications: [MTPRunningApplication]) -> [String] {
        let normalizedApplications = applications.map {
            (
                bundleIdentifier: normalize($0.bundleIdentifier),
                displayName: normalize($0.displayName)
            )
        }

        return candidates.compactMap { candidate in
            let matched = normalizedApplications.contains { application in
                candidate.exactBundleIdentifiers.contains(application.bundleIdentifier)
                    || candidate.exactNames.contains(application.displayName)
                    || candidate.bundleIdentifierFragments.contains {
                        !application.bundleIdentifier.isEmpty
                            && application.bundleIdentifier.contains($0)
                    }
                    || candidate.namePrefixes.contains {
                        !application.displayName.isEmpty
                            && application.displayName.hasPrefix($0)
                    }
            }
            return matched ? candidate.displayName : nil
        }
    }

    private static func normalize(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    }
}

enum UserFacingErrorMessage {
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

        if isUSBInterfaceUnavailableError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts, finalAction: "try again")
        }

        if isBusyConnectionError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts, finalAction: "try again")
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

        if isUSBInterfaceUnavailableError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts, finalAction: "choose Refresh")
        }

        if isBusyConnectionError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts, finalAction: "try again")
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
        if isUSBInterfaceUnavailableError(message) || isBusyConnectionError(message) {
            return usbConflictMessage(detectedConflicts: detectedConflicts, finalAction: "try again")
        }
        return "The map could not be installed safely. Reconnect the watch, refresh its maps, and try again."
    }

    private static func isUSBInterfaceUnavailableError(_ message: String) -> Bool {
        message.contains("libmtp panic")
            || message.contains("unable to initialize device")
            || message.contains("could not be opened")
            || message.contains("claim_interface")
            || message.contains("claim interface")
            || message.contains("libusb_error_access")
            || message.contains("resource busy")
    }

    private static func isBusyConnectionError(_ message: String) -> Bool {
        message.contains("ptp_error_io")
            || message.contains("failed to open session")
            || message.contains("libusb")
            || message.contains("claim interface")
            || message.contains("reset device")
            || message.contains("detach_kernel_driver")
    }

    private static func usbConflictMessage(
        detectedConflicts: [String],
        finalAction: String
    ) -> String {
        let detectedPrefix: String
        if detectedConflicts.isEmpty {
            detectedPrefix = "Another app may be using your Garmin's USB connection. Close Garmin Express, OpenMTP, or another file-transfer app."
        } else {
            detectedPrefix = "Terento detected \(joinedNames(detectedConflicts)) running. One of these apps may be using your Garmin's USB connection. Close the listed app or apps."
        }

        return "\(detectedPrefix) Close the Garmin Finder window, eject the Garmin from Finder, reconnect it, and \(finalAction)."
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

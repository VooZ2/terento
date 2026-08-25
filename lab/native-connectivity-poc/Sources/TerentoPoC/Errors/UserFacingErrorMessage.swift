import Foundation

enum UserFacingErrorMessage {
    static func forDevice(_ error: Error) -> String {
        let message = error.localizedDescription.lowercased()

        if message.contains("no mtp device") || message.contains("no garmin") {
            return "No Garmin watch was found. Connect it and try again."
        }

        if message.contains("more than one garmin") {
            return "More than one Garmin device is connected. Leave only one connected and try again."
        }

        if isUSBInterfaceUnavailableError(message) {
            return "Your Garmin is connected, but another app is using its USB connection. Close the Garmin Finder window and Garmin Express, eject the Garmin from Finder, reconnect it, and try again."
        }

        if isBusyConnectionError(message) {
            return "Your Garmin watch is busy. Close any other Garmin apps, reconnect it, and try again."
        }

        if message.contains("storage") {
            return "The watch connected, but it was not ready yet. Reconnect it and try again."
        }

        return "The Garmin watch could not be connected. Reconnect it and try again."
    }

    static func forMapScan(_ error: Error) -> String {
        let message = error.localizedDescription.lowercased()

        if message.contains("no mtp device") || message.contains("no garmin") {
            return "The Garmin watch was disconnected while reading its maps. Reconnect it and try again."
        }

        if isUSBInterfaceUnavailableError(message) {
            return "Terento found your Garmin, but another app is using its USB connection. Close the Garmin Finder window and Garmin Express, eject the Garmin from Finder, reconnect it, and choose Refresh."
        }

        if isBusyConnectionError(message) {
            return "The watch's map information could not be read because the device is busy. Close other Garmin or file-transfer apps, reconnect the watch, and try again."
        }

        if message.contains("catalog") || message.contains("metadata") {
            return "Map information is temporarily unavailable. Restart the test and try again."
        }

        return "The watch's installed maps could not be read. Reconnect it and try again."
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
}

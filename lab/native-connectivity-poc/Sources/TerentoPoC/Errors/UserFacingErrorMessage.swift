import Foundation

enum UserFacingErrorMessage {
    static func forDevice(_ error: Error) -> String {
        let message = error.localizedDescription.lowercased()

        if message.contains("no mtp device") || message.contains("no garmin") {
            return "No Garmin watch was found. Connect the watch and try again."
        }

        if message.contains("more than one garmin") {
            return "More than one Garmin device is connected. Leave only one connected and try again."
        }

        if isBusyConnectionError(message) {
            return "The Garmin watch is busy or another app is using it. Close other Garmin or file-transfer apps, disconnect the watch, reconnect it, and try again."
        }

        if message.contains("storage") {
            return "The watch connected, but its storage could not be read. Disconnect it, reconnect it, and try again."
        }

        return "The Garmin watch could not be read. Disconnect it, reconnect it, and try again."
    }

    static func forMapScan(_ error: Error) -> String {
        let message = error.localizedDescription.lowercased()

        if message.contains("no mtp device") || message.contains("no garmin") {
            return "The Garmin watch was disconnected while reading its maps. Reconnect it and try again."
        }

        if isBusyConnectionError(message) {
            return "The watch's map information could not be read because the device is busy. Close other Garmin or file-transfer apps, reconnect the watch, and try again."
        }

        if message.contains("catalog") || message.contains("metadata") {
            return "Map information is temporarily unavailable. Restart the test and try again."
        }

        return "The watch's installed maps could not be read. Reconnect it and try again."
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

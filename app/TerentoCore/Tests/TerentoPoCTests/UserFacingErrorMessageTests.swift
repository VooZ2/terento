import Foundation

@main
struct UserFacingErrorMessageTests {
    static func main() {
        let openError = SyntheticError(message: "Garmin MTP device could not be opened")
        let claimError = SyntheticError(
            message: "error returned by libusb_claim_interface() = -3 LIBMTP PANIC: Unable to initialize device"
        )

        let deviceMessage = UserFacingErrorMessage.forDevice(openError, detectedConflicts: [])
        let mapMessage = UserFacingErrorMessage.forMapScan(
            claimError,
            detectedConflicts: ["Garmin Express", "OpenMTP"]
        )

        expect(
            deviceMessage.contains("Another app")
                && deviceMessage.contains("Finder")
                && deviceMessage.contains("Garmin Express"),
            "device USB ownership failure gets an actionable UI message"
        )
        expect(
            mapMessage.contains("Garmin Express and OpenMTP")
                && mapMessage.contains("may be using")
                && mapMessage.contains("choose Refresh"),
            "map scan USB ownership failure names detected candidates and explains recovery"
        )

        let busyMessage = UserFacingErrorMessage.forDevice(
            SyntheticError(message: "PTP_ERROR_IO: failed to open session"),
            detectedConflicts: ["Preview"]
        )
        expect(
            busyMessage.contains("Terento detected Preview running")
                && busyMessage.contains("may be using"),
            "MTP session-busy failures use the same candidate-aware recovery"
        )

        let detected = MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.garmin.renu.client", displayName: "Express Helper"),
            MTPRunningApplication(bundleIdentifier: "com.apple.Preview", displayName: "Preview"),
            MTPRunningApplication(bundleIdentifier: "com.vendor.openmtp", displayName: nil),
            MTPRunningApplication(bundleIdentifier: "com.adobe.LightroomClassicCC7", displayName: "Lightroom Classic"),
            MTPRunningApplication(bundleIdentifier: "app.terento.mac", displayName: "Terento"),
            MTPRunningApplication(bundleIdentifier: "com.getdropbox.dropbox", displayName: "Dropbox")
        ])
        expect(
            detected == ["Garmin Express", "OpenMTP", "Preview", "Adobe Lightroom"],
            "only known MTP/PTP conflict candidates are reported in stable priority order"
        )

        let unrelatedMessage = UserFacingErrorMessage.forDevice(
            SyntheticError(message: "No Garmin MTP device detected"),
            detectedConflicts: ["OpenMTP"]
        )
        expect(
            unrelatedMessage == "No Garmin watch was found. Connect it and try again.",
            "running-app diagnostics do not alter unrelated device errors"
        )

        print("PASS: 6 user-facing USB/MTP error and conflict diagnostic tests")
    }

    private static func expect(_ condition: Bool, _ message: String) {
        if condition {
            print("PASS: \(message)")
        } else {
            print("FAIL: \(message)")
            exit(1)
        }
    }
}

private struct SyntheticError: LocalizedError {
    let message: String

    var errorDescription: String? { message }
}

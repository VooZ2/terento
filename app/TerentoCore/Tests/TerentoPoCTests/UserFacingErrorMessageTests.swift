import Foundation

@main
struct UserFacingErrorMessageTests {
    static func main() {
        let openError = SyntheticError(message: "Garmin MTP device could not be opened")
        let genericMessage = UserFacingErrorMessage.forDevice(openError, detectedConflicts: ["MacDroid"])
        expect(!genericMessage.contains("MacDroid"), "generic open failure does not blame a running app")
        for error in ["PTP_ERROR_IO: failed to open session", "LIBMTP PANIC: Unable to initialize device", "libusb read failed", "error returned by libusb_claim_interface() = -3"] {
            let scanMessage = UserFacingErrorMessage.forMapScan(SyntheticError(message: error), detectedConflicts: ["MacDroid"])
            let installMessage = UserFacingErrorMessage.forInstallation(SyntheticError(message: error), detectedConflicts: ["MacDroid"])
            expect(!scanMessage.contains("MacDroid") && !installMessage.contains("MacDroid"), "unrelated post-install I/O failure has no app-conflict attribution")
        }
        expect(UserFacingErrorMessage.forDevice(
            SyntheticError(message: "libusb_claim_interface() = -6"), detectedConflicts: ["MacDroid"]
        ) == "Close MacDroid and try connecting again.", "explicit busy evidence uses agreed short message with actual app name")
        expect(UserFacingErrorMessage.forDevice(
            SyntheticError(message: "LIBUSB_ERROR_BUSY"), detectedConflicts: []
        ) == "Reconnect your Garmin and try connecting again.", "no detected app means no canned list")

        let detected = MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.garmin.renu.client", displayName: "Garmin Express"),
            MTPRunningApplication(bundleIdentifier: "com.vendor.openmtp", displayName: nil),
            MTPRunningApplication(bundleIdentifier: "com.adobe.LightroomClassicCC7", displayName: "Lightroom Classic"),
            MTPRunningApplication(bundleIdentifier: "com.eltima.MacDroid.AFTFinderSync", displayName: "AFTFinderSync", isRegularApplication: false),
            MTPRunningApplication(bundleIdentifier: "com.eltima.MacDroid", displayName: "MacDroid", isRegularApplication: false),
            MTPRunningApplication(bundleIdentifier: "app.terento.mac", displayName: "Terento"),
            MTPRunningApplication(bundleIdentifier: "com.getdropbox.dropbox", displayName: "Dropbox")
        ])
        expect(detected == ["Garmin Express", "Lightroom Classic"], "only running main apps with actual names are shown; helpers and invented labels excluded")
        expect(UserFacingErrorMessage.forDevice(
            SyntheticError(message: "No Garmin MTP device detected"), detectedConflicts: ["OpenMTP"]
        ) == "No Garmin watch was found. Connect it and try again.", "absent device does not blame an app")
        expect(UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: true, detectedConflicts: ["MacDroid"]
        ) == "Close MacDroid and try connecting again.", "USB-present connection timeout uses agreed message")
        expect(!UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: false, detectedConflicts: ["MacDroid"]
        ).contains("MacDroid"), "USB-absent timeout has no unrelated conflict")
        expect(!UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: true, detectedConflicts: []
        ).contains("Close"), "connection timeout does not invent a competing application")
        expect(MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.eltima.MacDroid", displayName: "MacDroid")
        ]) == ["MacDroid"], "actual running MacDroid main application is detected")
        print("PASS: focused error attribution and running application diagnostics")
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

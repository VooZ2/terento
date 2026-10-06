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
        expect(detected == ["Garmin Express"], "only running main apps with actual names are shown; helpers, invented labels and import-only apps excluded")
        expect(MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.apple.Preview", displayName: "Preview"),
            MTPRunningApplication(bundleIdentifier: "com.apple.Photos", displayName: "Photos")
        ]).isEmpty, "a running Preview or Photos is not advice to close it")
        expect(UserFacingErrorMessage.forDevice(
            SyntheticError(message: "No Garmin MTP device detected"), detectedConflicts: ["OpenMTP"]
        ) == "No Garmin watch was found. Connect it and try again.", "absent device does not blame an app")
        expect(UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: true, detectedConflicts: ["MacDroid"]
        ) == "Close MacDroid and try connecting again.", "USB-present connection timeout uses agreed message")
        expect(UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: true, detectedConflicts: []
        ) == "Your Garmin was detected, but it didn't become ready within 2 minutes. Unplug it, wait 5 seconds, and plug it back in.", "USB-present timeout without conflicts gives a concrete next step")
        expect(UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: false, detectedConflicts: []
        ) == "We couldn't connect to your Garmin within 2 minutes. Reconnect it and try again.", "USB-absent timeout preserves the existing timeout description")
        expect(!UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: false, detectedConflicts: ["MacDroid"]
        ).contains("MacDroid"), "USB-absent timeout has no unrelated conflict")
        expect(!UserFacingErrorMessage.forConnectionTimeout(
            garminUSBPresent: true, detectedConflicts: []
        ).contains("Close"), "connection timeout does not invent a competing application")
        expect(MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.eltima.MacDroid", displayName: "MacDroid")
        ]) == ["MacDroid"], "actual running MacDroid main application is detected")
        for outcome in [DeviceConnectOutcome.busy, .multipleDevices, .notMTPMode] {
            let attention = UserFacingErrorMessage.detectionAttention(outcome)
            expect(attention != nil && !attention!.title.isEmpty && !attention!.description.isEmpty,
                   "\(outcome) has a live title and description while detection continues")
            let final = UserFacingErrorMessage.forDetectionFailure(outcome, garminUSBPresent: true, detectedConflicts: ["MacDroid"])
            expect(!final.contains("MacDroid"), "\(outcome) final message does not blame a running app")
        }
        expect(UserFacingErrorMessage.detectionAttention(.connected) == nil, "connected has no attention copy")
        expect(UserFacingErrorMessage.forDetectionFailure(.failed, garminUSBPresent: true, detectedConflicts: [])
            == "The watch stopped responding. Unplug it, wait 5 seconds, plug it back in.", "a stalled read gives the replug recovery step")
        expect(UserFacingErrorMessage.forDetectionFailure(.notMTPMode, garminUSBPresent: true, detectedConflicts: []).contains("USB Mode"),
               "a Garmin invisible to file transfer gets the USB-mode hint")
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

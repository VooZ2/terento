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
        let namedTimeout = UserFacingErrorMessage.connectionTimeout(garminUSBPresent: true, detectedConflicts: ["MacDroid"])
        expect(namedTimeout.steps.first == "Quit MacDroid, which may be using the watch.",
               "USB-present connection timeout names the detected app first")
        expect(namedTimeout.steps.last?.hasPrefix("Then unplug the watch, wait 5 seconds and connect it again, or click Try again.") == true,
               "USB-present timeout with a named app keeps the replug step")
        let plainTimeout = UserFacingErrorMessage.connectionTimeout(garminUSBPresent: true, detectedConflicts: [])
        expect(plainTimeout.title == "Your watch was detected but didn't get ready"
            && plainTimeout.reason == "Terento found your Garmin, but it didn't become ready within 2 minutes."
            && plainTimeout.steps.contains("Try another USB port or cable, plugged directly into the Mac.")
            && plainTimeout.steps.last?.hasPrefix("Then unplug the watch, wait 5 seconds and connect it again") == true,
               "USB-present timeout without conflicts gives concrete next steps and the replug step")
        let absentTimeout = UserFacingErrorMessage.connectionTimeout(garminUSBPresent: false, detectedConflicts: ["MacDroid"])
        expect(absentTimeout.title == "Your watch disconnected before it was ready" && !absentTimeout.text.contains("MacDroid"),
               "a timeout after the watch dropped off USB has its own title and no unrelated conflict")
        expect(!absentTimeout.text.contains("charge-only"),
               "a watch that was already detected is not told to swap a charge-only cable")
        expect(UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: false, detectedConflicts: [])
            != UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: true, detectedConflicts: []),
               "USB-absent and USB-present timeouts stay distinguishable")
        expect(UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: true, detectedConflicts: []) == plainTimeout.text
            && plainTimeout.text.hasPrefix(plainTimeout.reason + "\n1. Unlock the watch.\n2. "),
               "the plain text is the reason followed by the numbered steps")
        expect(!plainTimeout.text.contains("Quit") && !plainTimeout.text.contains("Close"),
               "connection timeout does not invent a competing application")
        expect(MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.eltima.MacDroid", displayName: "MacDroid")
        ]) == ["MacDroid"], "actual running MacDroid main application is detected")
        for outcome in [DeviceConnectOutcome.busy, .multipleDevices, .notMTPMode] {
            let attention = UserFacingErrorMessage.detectionAttention(outcome, detectedConflicts: [])
            expect(attention != nil && !attention!.title.isEmpty && !attention!.description.isEmpty,
                   "\(outcome) has a live title and description while detection continues")
        }
        for outcome in [DeviceConnectOutcome.multipleDevices, .notMTPMode] {
            let final = UserFacingErrorMessage.forDetectionFailure(outcome, garminUSBPresent: true, detectedConflicts: ["MacDroid"])
            expect(!final.contains("MacDroid"), "\(outcome) final message does not blame a running app")
            let attention = UserFacingErrorMessage.detectionAttention(outcome, detectedConflicts: ["MacDroid"])!
            expect(!attention.description.contains("MacDroid"), "\(outcome) live message does not blame a running app")
        }
        expect(UserFacingErrorMessage.detectionAttention(.connected) == nil, "connected has no attention copy")
        testBusyNamesTheDetectedApp()
        testEveryFailureHasItsOwnMessage()
        testUSBModeNamesTheMenuPath()
        print("PASS: focused error attribution and running application diagnostics")
    }

    /// The failures a detection episode can report, each with its own message.
    static let failureOutcomes = DeviceConnectOutcome.allCases.filter { $0 != .connected }

    static func testBusyNamesTheDetectedApp() {
        let named = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true,
                                                            detectedConflicts: ["Android File Transfer"])
        expect(named.steps.first == "Quit Android File Transfer." && !named.text.contains("Garmin Express"),
               "BUSY names the app the scan detected instead of Garmin Express")
        expect(UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true,
                                                       detectedConflicts: ["OpenMTP", "Garmin Express"]).steps.first
            == "Quit OpenMTP and Garmin Express.", "BUSY names every detected app")
        let unnamed = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true, detectedConflicts: [])
        expect(unnamed.steps.first == "Quit Garmin Express and other apps that connect to your watch.",
               "BUSY without a detected app keeps the Garmin Express wording")
        expect(named.steps.last?.hasPrefix("Then unplug the watch and connect it again, or click Try again.") == true,
               "BUSY keeps the replug step")
        let liveNamed = UserFacingErrorMessage.detectionAttention(.busy, detectedConflicts: ["Android File Transfer"])!
        expect(liveNamed.description.contains("Quit Android File Transfer.") && !liveNamed.description.contains("Garmin Express"),
               "the live BUSY state names the detected app")
        let liveUnnamed = UserFacingErrorMessage.detectionAttention(.busy, detectedConflicts: [])!
        expect(liveUnnamed.description.contains("Quit Garmin Express and similar apps."),
               "the live BUSY state without a detected app keeps the Garmin Express wording")
        var scanned = false
        _ = UserFacingErrorMessage.detectionAttention(.multipleDevices, detectedConflicts: { scanned = true; return [] }())
        expect(!scanned, "only the BUSY attention reads the running applications")
    }

    /// Every final message: each failure outcome, plus a timeout that ended
    /// after the watch dropped off USB (the reachable USB-absent case).
    static var failureMessages: [(name: String, message: ConnectFailureMessage)] {
        failureOutcomes.map {
            ($0.rawValue, UserFacingErrorMessage.detectionFailure($0, garminUSBPresent: $0 != .timeoutNoUSB, detectedConflicts: []))
        } + [("timeoutUSBPresent without USB",
              UserFacingErrorMessage.detectionFailure(.timeoutUSBPresent, garminUSBPresent: false, detectedConflicts: []))]
    }

    static func testEveryFailureHasItsOwnMessage() {
        var titles = Set<String>()
        for (outcome, message) in failureMessages {
            expect(titles.insert(message.title).inserted, "\(outcome) has a distinct title: \(message.title)")
            expect(message.title != "Couldn't connect to Garmin", "\(outcome) names the cause instead of the generic title")
            expect(message.reason.hasSuffix(".") && !message.reason.dropLast().contains(". "),
                   "\(outcome) gives the reason in one sentence")
            expect(message.steps.count >= 2 && message.steps.allSatisfy { $0.hasSuffix(".") },
                   "\(outcome) has numbered, actionable steps")
            let last = message.steps.last ?? ""
            expect(last.hasPrefix("Then ") && last.contains("click Try again")
                && last.hasSuffix("Terento doesn't check again until you do."),
                   "\(outcome) ends with how to retry and says detection resumes only then")
            for text in [message.title, message.reason] + message.steps where text != UserFacingErrorMessage.usbModeStep {
                expect(!text.contains("MTP"), "\(outcome) describes the outcome, not MTP: \(text)")
            }
        }
        for outcome in failureOutcomes {
            expect(UserFacingErrorMessage.forDetectionFailure(outcome, garminUSBPresent: true, detectedConflicts: [])
                == UserFacingErrorMessage.detectionFailure(outcome, garminUSBPresent: true, detectedConflicts: []).text,
                   "\(outcome) stores the same text as its structured message")
        }
        expect(UserFacingErrorMessage.detectionFailure(.failed, garminUSBPresent: true, detectedConflicts: []).title
            == "Your watch stopped responding", "a stalled read is named")
        expect(UserFacingErrorMessage.detectionFailure(.failed, garminUSBPresent: true, detectedConflicts: []).steps.first
            == "Unplug the watch and wait 5 seconds.", "a stalled read gives the replug recovery step")
        expect(UserFacingErrorMessage.detectionFailure(.timeoutNoUSB, garminUSBPresent: true, detectedConflicts: []).title
            == "Your watch isn't showing up", "TIMEOUT_NO_USB never claims the watch was detected")
        let busy = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true, detectedConflicts: [])
        expect(busy.title == "Another app may be using your watch",
               "BUSY is inferred from session-open failures, so its title does not state it as fact")
        for (outcome, message) in failureMessages {
            expect(!message.text.contains("adapter"), "\(outcome) does not rule out the adapter a USB-C Mac needs")
        }
    }

    static func testUSBModeNamesTheMenuPath() {
        let final = UserFacingErrorMessage.detectionFailure(.notMTPMode, garminUSBPresent: true, detectedConflicts: [])
        expect(final.title == "Your watch isn't ready for file transfer",
               "NOT_MTP_MODE describes the outcome in the guide's words")
        expect(final.steps.contains(UserFacingErrorMessage.usbModeStep)
            && UserFacingErrorMessage.usbModeStep.hasPrefix("On the watch, open USB Mode, usually under Settings › System, and choose MTP.")
            && UserFacingErrorMessage.usbModeStep.contains("Not every model has this setting"),
               "NOT_MTP_MODE names the USB Mode menu path and the models without it")
        let live = UserFacingErrorMessage.detectionAttention(.notMTPMode)!
        expect(live.description.contains("USB Mode, usually under Settings › System, choose MTP")
            && live.description.contains("If your model has USB Mode"),
               "the live NOT_MTP_MODE state names the same menu path")
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

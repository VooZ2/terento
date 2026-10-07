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
        expect(namedTimeout.finding == "MacDroid is open and may be using the watch"
            && namedTimeout.steps.first?.text == "Quit MacDroid",
               "USB-present connection timeout names the detected app first")
        expect(namedTimeout.steps.last?.text == "Unplug for 5 seconds, then reconnect or click Try again",
               "USB-present timeout with a named app keeps the replug step")
        let plainTimeout = UserFacingErrorMessage.connectionTimeout(garminUSBPresent: true, detectedConflicts: [])
        expect(plainTimeout.title == "Your watch didn't get ready"
            && plainTimeout.reason == "The connection didn't become ready within 2 minutes."
            && plainTimeout.finding == "Your Garmin is plugged in to this Mac"
            && plainTimeout.steps.map(\.text).contains("Try another USB port or cable, plugged directly into the Mac")
            && plainTimeout.steps.last?.text == "Unplug for 5 seconds, then reconnect or click Try again",
               "USB-present timeout without conflicts gives concrete next steps and the replug step")
        let absentTimeout = UserFacingErrorMessage.connectionTimeout(garminUSBPresent: false, detectedConflicts: ["MacDroid"])
        expect(absentTimeout.title == "Your watch lost connection" && !absentTimeout.text.contains("MacDroid"),
               "a timeout after the watch dropped off USB has its own title and no unrelated conflict")
        expect(!absentTimeout.text.contains("charge-only"),
               "a watch that was already detected is not told to swap a charge-only cable")
        expect(UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: false, detectedConflicts: [])
            != UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: true, detectedConflicts: []),
               "USB-absent and USB-present timeouts stay distinguishable")
        expect(UserFacingErrorMessage.forConnectionTimeout(garminUSBPresent: true, detectedConflicts: []) == plainTimeout.text
            && plainTimeout.text.hasPrefix(plainTimeout.reason + "\n" + plainTimeout.finding + "\n1. Unlock the watch\n2. ")
            && plainTimeout.text.hasSuffix("\n" + plainTimeout.note),
               "the plain text is the reason, the finding, the numbered steps and the note")
        expect(!plainTimeout.text.contains("Quit") && !plainTimeout.text.contains("Close"),
               "connection timeout does not invent a competing application")
        expect(MTPConnectionConflictDiagnostics.detectedApplicationNames([
            MTPRunningApplication(bundleIdentifier: "com.eltima.MacDroid", displayName: "MacDroid")
        ]) == ["MacDroid"], "actual running MacDroid main application is detected")
        for outcome in [DeviceConnectOutcome.multipleDevices, .notMTPMode] {
            let final = UserFacingErrorMessage.forDetectionFailure(outcome, garminUSBPresent: true, detectedConflicts: ["MacDroid"])
            expect(!final.contains("MacDroid"), "\(outcome) final message does not blame a running app")
            let attention = UserFacingErrorMessage.detectionAttention(outcome, detectedConflicts: ["MacDroid"])!
            expect(!attention.text.contains("MacDroid"), "\(outcome) live message does not blame a running app")
        }
        expect(UserFacingErrorMessage.detectionAttention(.connected) == nil, "connected has no attention copy")
        testBusyNamesTheDetectedApp()
        testEveryProblemFollowsTheHelpBoxPattern()
        testEveryFailureHasItsOwnMessage()
        testUSBModeNamesTheMenuPath()
        print("PASS: focused error attribution and running application diagnostics")
    }

    /// The failures a detection episode can report, each with its own message.
    static let failureOutcomes = DeviceConnectOutcome.allCases.filter { $0 != .connected }
    /// The live states shown while detection keeps polling.
    static let attentionOutcomes: [DeviceConnectOutcome] = [.busy, .multipleDevices, .notMTPMode]
    /// SF Symbols the Connect page already uses for its help rows.
    static let connectSymbols: Set<String> = [
        "cable.connector", "desktopcomputer", "lock.open", "arrow.clockwise", "xmark.app",
        "arrow.triangle.2.circlepath", "gearshape"
    ]

    static func testBusyNamesTheDetectedApp() {
        let named = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true,
                                                            detectedConflicts: ["Android File Transfer"])
        expect(named.finding == "Android File Transfer is open"
            && named.steps.first?.text == "Quit Android File Transfer" && !named.text.contains("Garmin Express"),
               "BUSY names the app the scan detected instead of Garmin Express")
        let both = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true,
                                                           detectedConflicts: ["OpenMTP", "Garmin Express"])
        expect(both.finding == "OpenMTP and Garmin Express are open" && both.steps.first?.text == "Quit OpenMTP and Garmin Express",
               "BUSY names every detected app")
        let unnamed = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true, detectedConflicts: [])
        expect(unnamed.steps.first?.text == "Quit Garmin Express and other apps that connect to your watch",
               "BUSY without a detected app keeps the Garmin Express wording")
        expect(named.steps.last?.text == "Unplug the watch and connect it again, or click Try again",
               "BUSY keeps the replug step")
        let liveNamed = UserFacingErrorMessage.detectionAttention(.busy, detectedConflicts: ["Android File Transfer"])!
        expect(liveNamed.finding == "Android File Transfer is open"
            && liveNamed.steps.map(\.text) == ["Quit Android File Transfer"] && !liveNamed.text.contains("Garmin Express"),
               "the live BUSY state names the detected app")
        let liveUnnamed = UserFacingErrorMessage.detectionAttention(.busy, detectedConflicts: [])!
        expect(liveUnnamed.steps.map(\.text) == ["Quit Garmin Express and similar apps"],
               "the live BUSY state without a detected app keeps the Garmin Express wording")
        var scanned = false
        _ = UserFacingErrorMessage.detectionAttention(.multipleDevices, detectedConflicts: { scanned = true; return [] }())
        expect(!scanned, "only the BUSY attention reads the running applications")
    }

    /// Every final message: each failure outcome, plus a timeout that ended
    /// after the watch dropped off USB (the reachable USB-absent case).
    static var failureMessages: [(name: String, message: ConnectIssueMessage)] {
        failureOutcomes.map {
            ($0.rawValue, UserFacingErrorMessage.detectionFailure($0, garminUSBPresent: $0 != .timeoutNoUSB, detectedConflicts: []))
        } + [("timeoutUSBPresent without USB",
              UserFacingErrorMessage.detectionFailure(.timeoutUSBPresent, garminUSBPresent: false, detectedConflicts: []))]
    }

    /// Every problem uses the calm help-box pattern: a one-line title, one
    /// short sentence of what is wrong, then a box with a finding, icon
    /// steps and a note. Measured at the 920 pt minimum window: 29
    /// characters fill one 42 pt heading line, 64 characters one 19 pt
    /// description line.
    static func testEveryProblemFollowsTheHelpBoxPattern() {
        let live = attentionOutcomes.map {
            ("live \($0.rawValue)", UserFacingErrorMessage.detectionAttention($0, detectedConflicts: [])!)
        }
        for (name, message) in failureMessages + live {
            expect(message.title.count <= 29, "\(name) title fits one heading line at the minimum window width")
            expect(message.reason.count <= 64 && message.reason.hasSuffix(".")
                && !message.reason.dropLast().contains(". "),
                   "\(name) says what is wrong in one short sentence: \(message.reason)")
            expect(!message.finding.isEmpty && !message.finding.hasSuffix(".") && message.finding.count <= 60,
                   "\(name) leads the box with a short finding")
            expect(!message.steps.isEmpty && message.steps.allSatisfy {
                    connectSymbols.contains($0.systemImage) && !$0.text.hasSuffix(".") && !$0.text.isEmpty
                }, "\(name) lists its steps as icon bullets using Connect symbols")
            expect(message.note.hasSuffix(".") && !message.note.isEmpty, "\(name) ends the box with a note")
            for text in [message.title, message.reason, message.finding, message.note]
                + message.steps.filter({ $0 != UserFacingErrorMessage.usbModeStep }).map(\.text) {
                expect(!text.contains("MTP"), "\(name) describes the outcome, not MTP: \(text)")
                expect(!text.contains("adapter"), "\(name) does not rule out the adapter a USB-C Mac needs")
            }
        }
    }

    static func testEveryFailureHasItsOwnMessage() {
        var titles = Set<String>()
        for (outcome, message) in failureMessages {
            expect(titles.insert(message.title).inserted, "\(outcome) has a distinct title: \(message.title)")
            expect(message.title != "Couldn't connect to Garmin", "\(outcome) names the cause instead of the generic title")
            expect(message.steps.count >= 2, "\(outcome) has actionable steps before the retry")
            let last = message.steps.last
            expect(last?.systemImage == "arrow.triangle.2.circlepath" && last?.text.hasSuffix("click Try again") == true,
                   "\(outcome) ends with how to retry")
            expect(message.note == "Terento checks again only after you reconnect or click Try again.",
                   "\(outcome) says detection resumes only after a reconnect or Try again")
        }
        for outcome in failureOutcomes {
            expect(UserFacingErrorMessage.forDetectionFailure(outcome, garminUSBPresent: true, detectedConflicts: [])
                == UserFacingErrorMessage.detectionFailure(outcome, garminUSBPresent: true, detectedConflicts: []).text,
                   "\(outcome) stores the same text as its structured message")
        }
        let stalled = UserFacingErrorMessage.detectionFailure(.failed, garminUSBPresent: true, detectedConflicts: [])
        expect(stalled.title == "Your watch stopped responding"
            && stalled.steps.first?.text == "Unplug the watch and wait 5 seconds",
               "a stalled read is named and gives the replug recovery step")
        expect(UserFacingErrorMessage.detectionFailure(.timeoutNoUSB, garminUSBPresent: true, detectedConflicts: []).title
            == "Your watch isn't showing up", "TIMEOUT_NO_USB never claims the watch was detected")
        let busy = UserFacingErrorMessage.detectionFailure(.busy, garminUSBPresent: true, detectedConflicts: [])
        expect(busy.title == "Your watch may be in use" && busy.reason == "Another app may be using your watch.",
               "BUSY is inferred from session-open failures, so it is not stated as fact")
        let live = attentionOutcomes.map { UserFacingErrorMessage.detectionAttention($0, detectedConflicts: [])! }
        expect(live.allSatisfy { !$0.text.contains("Try again") },
               "live states have no Try again; detection keeps polling")
    }

    static func testUSBModeNamesTheMenuPath() {
        let final = UserFacingErrorMessage.detectionFailure(.notMTPMode, garminUSBPresent: true, detectedConflicts: [])
        expect(final.title == "Not ready for file transfer",
               "NOT_MTP_MODE describes the outcome in the guide's words")
        expect(final.steps.contains(UserFacingErrorMessage.usbModeStep)
            && UserFacingErrorMessage.usbModeStep.text
                == "If your watch has USB Mode (usually under Settings › System), choose MTP"
            && UserFacingErrorMessage.usbModeStep.systemImage == "gearshape",
               "NOT_MTP_MODE names the USB Mode menu path, hedged for models without it")
        let live = UserFacingErrorMessage.detectionAttention(.notMTPMode)!
        expect(live.steps.contains(UserFacingErrorMessage.usbModeStep),
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

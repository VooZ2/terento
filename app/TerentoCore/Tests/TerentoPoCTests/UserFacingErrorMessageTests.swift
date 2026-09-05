import Foundation

@main
struct UserFacingErrorMessageTests {
    static func main() {
        let openError = SyntheticError(message: "Garmin MTP device could not be opened")
        let claimError = SyntheticError(
            message: "error returned by libusb_claim_interface() = -3 LIBMTP PANIC: Unable to initialize device"
        )

        let deviceMessage = UserFacingErrorMessage.forDevice(openError)
        let mapMessage = UserFacingErrorMessage.forMapScan(claimError)

        expect(
            deviceMessage.contains("another app")
                && deviceMessage.contains("Finder")
                && deviceMessage.contains("Garmin Express"),
            "device USB ownership failure gets an actionable UI message"
        )
        expect(
            mapMessage.contains("another app")
                && mapMessage.contains("choose Refresh"),
            "map scan USB ownership failure explains how to recover"
        )

        print("PASS: 2 user-facing USB/MTP error message tests")
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

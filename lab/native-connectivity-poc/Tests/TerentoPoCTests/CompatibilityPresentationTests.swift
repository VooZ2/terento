import Foundation

private func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else {
        print("FAIL: \(message)")
        exit(1)
    }
}

@main
struct CompatibilityPresentationTests {
    static func main() {
        let expected: [CompatibilityStatus: String] = [
            .unknown: "Terento hasn't tested this exact device yet.",
            .testing: "This exact device is currently being tested with Terento.",
            .tested: "Testing confirms device identification and specific validated capabilities.",
            .supported: "Supported for Terento map installation.",
            .verified: "Verified across multiple devices."
        ]

        for status in CompatibilityStatus.allCases {
            let explanation = CompatibilityPresentation.explanation(for: status)
            require(!explanation.isEmpty, "\(status.rawValue) explanation is empty")
            require(explanation.contains(expected[status]!), "\(status.rawValue) explanation changed unexpectedly")
            require(status.userLabel != status.rawValue, "\(status.rawValue) is exposed as a raw technical label")
        }

        print("PASS: compatibility presentation covers all five domain statuses")

        require(
            GarminFirmwareVersionFormatter.display(rawValue: "2244", manufacturer: "Garmin") == "22.44",
            "compact Garmin firmware 2244 should display as 22.44"
        )
        require(
            GarminFirmwareVersionFormatter.display(rawValue: "2243", manufacturer: "Garmin") == "22.43",
            "compact Garmin firmware 2243 should display as 22.43"
        )
        require(
            GarminFirmwareVersionFormatter.display(rawValue: "707", manufacturer: "Garmin") == "7.07",
            "compact one-digit-major Garmin firmware should keep the two-digit minor"
        )
        require(
            GarminFirmwareVersionFormatter.display(rawValue: "22.44", manufacturer: "Garmin") == "22.44",
            "already formatted Garmin firmware should remain unchanged"
        )
        require(
            GarminFirmwareVersionFormatter.display(rawValue: "2244", manufacturer: "Other") == "2244",
            "non-Garmin device versions must not be guessed"
        )
        require(
            GarminFirmwareVersionFormatter.display(rawValue: "22445", manufacturer: "Garmin") == "22445",
            "unknown-length Garmin versions must remain raw"
        )

        print("PASS: Garmin firmware display normalizes compact MTP versions safely")
    }
}

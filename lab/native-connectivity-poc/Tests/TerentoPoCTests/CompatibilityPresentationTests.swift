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
    }
}

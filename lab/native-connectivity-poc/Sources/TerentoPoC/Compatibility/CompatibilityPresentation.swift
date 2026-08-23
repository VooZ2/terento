import Foundation

/// User-facing explanations for the domain compatibility status.
///
/// The status itself remains owned by the compatibility registry. This type
/// only translates that existing domain value into restrained UI copy.
enum CompatibilityPresentation {
    static func explanation(for status: CompatibilityStatus) -> String {
        switch status {
        case .unknown:
            return "Terento hasn't tested this exact device yet."
        case .testing:
            return "This exact device is currently being tested with Terento."
        case .tested:
            return "Tested with real hardware.\n\nTerento has real hardware evidence for this exact Garmin model.\n\nTesting confirms device identification and specific validated capabilities. It does not necessarily mean all map installation features are supported."
        case .supported:
            return "Supported for Terento map installation.\n\nThis Garmin model has successfully completed the Terento installation workflow.\n\nTerento verified map installation, reconnect behavior, and that the installed map is visible on the device."
        case .verified:
            return "Verified across multiple devices.\n\nThis Garmin model has completed successful Terento workflows on multiple physical devices, including firmware variations."
        }
    }
}

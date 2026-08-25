import Foundation

/// User-facing explanations for the domain compatibility status.
///
/// The status itself remains owned by the compatibility registry. This type
/// only translates that existing domain value into restrained UI copy.
enum CompatibilityPresentation {
    static func explanation(for status: CompatibilityStatus) -> String {
        switch status {
        case .unknown:
            return "This exact device is known, but Terento does not have enough real hardware evidence yet."
        case .testing:
            return "This exact device is currently under validation or has only partial evidence."
        case .tested:
            return "Real hardware testing exists for this exact model and variant."
        case .supported:
            return "A successful verified map installation exists for this exact model and variant."
        case .verified:
            return "Successful installations are confirmed across at least two operator-reviewed physical devices and two firmware versions."
        }
    }
}

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
            return "Real hardware evidence exists for this model, but it is not yet a full support claim."
        case .supported:
            return "A real map installation completed successfully for this exact model."
        case .verified:
            return "Confirmed across multiple physical devices and firmware versions."
        }
    }
}

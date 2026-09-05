import Foundation

/// User-facing explanations for the domain compatibility status.
///
/// The public status is resolved by the canonical compatibility service. This
/// type only translates that resolved domain value into restrained UI copy.
enum CompatibilityPresentation {
    static func explanation(for status: CompatibilityStatus) -> String {
        switch status {
        case .testing:
            return "Terento has recognized this model as map-capable, but no successful shared installation has been received yet."
        case .tested:
            return "1–2 successful installations have been shared by Terento users."
        case .supported:
            return "3–4 successful installations have been shared by Terento users."
        case .verified:
            return "5 or more successful installations have been shared by Terento users."
        }
    }
}

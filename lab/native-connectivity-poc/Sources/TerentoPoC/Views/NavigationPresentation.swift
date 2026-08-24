import Foundation

/// The sidebar exposes the product destinations. Installation steps remain an
/// internal flow owned by the Install maps destination.
enum TerentoSection: String, CaseIterable, Identifiable, Sendable {
    case device = "Device"
    case installMaps = "Install maps"
    case manageMaps = "Manage maps"
    case about = "About"

    var id: String { rawValue }
}

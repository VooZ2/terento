import Foundation

/// Map Manager capability is separate from public compatibility evidence.
/// During beta it is one of several required inputs to a live-bound install
/// profile; by itself it never authorizes a device write.
enum GarminMapSupportStatus: Equatable, Sendable {
    case supported
    case unsupported(reason: String)
    case unknown

    var canUseTerentoMaps: Bool {
        if case .supported = self { return true }
        return false
    }

    var isKnownUnsupported: Bool {
        if case .unsupported = self { return true }
        return false
    }

    var showsTerentoCompatibility: Bool {
        !isKnownUnsupported
    }

    var userLabel: String {
        switch self {
        case .supported:
            return "Maps available"
        case .unsupported:
            return "This watch does not support maps."
        case .unknown:
            return "Map support unknown"
        }
    }

    var userMessage: String {
        switch self {
        case .supported:
            return "Garmin Map Manager lists this model for additional maps."
        case let .unsupported(reason):
            return reason.isEmpty
                ? "Additional maps are not available for this model."
                : reason
        case .unknown:
            return "Terento could not determine whether this model supports additional maps."
        }
    }
}

struct GarminMapCapabilityRegistry: Sendable {
    static let local = GarminMapCapabilityRegistry()

    /// Garmin's Map Manager model families that can receive additional map
    /// data. The list intentionally excludes handhelds, Edge computers, and
    /// golf-only CourseView devices.
    private let supportedPrefixes: Set<String> = [
        "d2 mach 1",
        "d2 mach 2",
        "descent mk1",
        "descent mk2",
        "descent mk3",
        "enduro 2",
        "enduro 3",
        "epix gen 2",
        "epix pro gen 2",
        "fenix 5x",
        "fenix 5 plus",
        "fenix 6",
        "fenix 7",
        "fenix 8",
        "fenix e",
        "forerunner 945",
        "forerunner 955",
        "forerunner 965",
        "forerunner 970",
        "marq",
        "quatix 6",
        "quatix 7",
        "quatix 8",
        "tactix charlie",
        "tactix delta",
        "tactix 7",
        "tactix 8",
        "venu x1"
    ]

    /// Models known to Garmin but not eligible for Terento's additional map
    /// flow. This is intentionally conservative: an unrecognised Garmin model
    /// returns `.unknown`, not a false negative.
    private let knownNonMapPrefixes: Set<String> = [
        "approach",
        "descent g1",
        "descent g2",
        "forerunner 55",
        "forerunner 165",
        "forerunner 255",
        "forerunner 265",
        "forerunner 570",
        "instinct",
        "lily",
        "venu",
        "vivoactive",
        "vivomove"
    ]

    func evaluate(identity: DeviceIdentity) -> GarminMapSupportStatus {
        guard isGarmin(identity.manufacturer) else {
            return .unknown
        }

        var model = GarminDeviceModelNormalizer.normalize(identity.model)
        if model.hasPrefix("garmin ") {
            model.removeFirst("garmin ".count)
        }
        guard !model.isEmpty else { return .unknown }

        if model.hasPrefix("approach s70") {
            return .unsupported(
                reason: "This model uses Garmin golf CourseView maps, not additional Terento maps."
            )
        }

        if supportedPrefixes.contains(where: model.hasPrefix) {
            return .supported
        }

        if knownNonMapPrefixes.contains(where: model.hasPrefix) {
            return .unsupported(
                reason: "Garmin Map Manager does not list this model for additional maps."
            )
        }

        return .unknown
    }

    private func isGarmin(_ manufacturer: String) -> Bool {
        manufacturer.range(
            of: "garmin",
            options: [.caseInsensitive, .diacriticInsensitive]
        ) != nil
    }
}
